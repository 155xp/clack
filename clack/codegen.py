"""Emit portable C11 for a verified Clack program.

The native program contains no interpreter, boxed numeric values, or solver.
Contracts, loop invariants, and assertions have already been proved by the
verifier and are erased here. This emitter is part of the trusted compiler.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from . import frontend as ast


_ARRAY = re.compile(r"(int|bool)\[([0-9]+)\]\Z")


def _ctype(type_name: str) -> str:
    primitive = {"int": "int64_t", "bool": "bool", "unit": "void"}
    if type_name in primitive:
        return primitive[type_name]
    array = _ARRAY.fullmatch(type_name)
    if array:
        return f"clack_t_array_{array[1]}_{int(array[2])}"
    return f"clack_t_record_{type_name}"


def _var(name: str) -> str:
    return f"clack_v_{name}"


def _func(name: str) -> str:
    return f"clack_fn_{name}"


def _field(name: str) -> str:
    return f"clack_field_{name}"


@dataclass
class _Task:
    number: int
    binding: ast.Assign
    callee: ast.Function


class _Emitter:
    def __init__(self, program: ast.Program, local_types: dict[str, dict[str, str]], expr_types: dict[int, str]):
        self.program = program
        self.local_types = local_types
        self.expr_types = expr_types
        self.records = {record.name: record for record in getattr(program, "records", [])}
        self.functions = {function.name: function for function in program.functions}
        self.tasks: dict[int, _Task] = {}
        self._collect_tasks()

    def _collect_tasks(self) -> None:
        def visit(body: list[ast.Stmt]) -> None:
            for statement in body:
                kind = type(statement).__name__
                if kind == "Parallel":
                    for binding in statement.bindings:
                        callee = self.functions[binding.value.name]
                        self.tasks[id(binding)] = _Task(len(self.tasks), binding, callee)
                elif kind == "If":
                    visit(statement.then_body)
                    visit(statement.else_body)
                elif kind == "While":
                    visit(statement.body)
        for function in self.program.functions:
            visit(function.body)

    def _type_definitions(self) -> list[str]:
        types = set(self.expr_types.values())
        for function in self.program.functions:
            types.add(function.return_type)
            types.update(value for _, value in function.params)
            types.update(self.local_types.get(function.name, {}).values())
        for record in self.records.values():
            types.update(value for _, value in record.fields)
        output: list[str] = []
        for type_name in sorted(types):
            array = _ARRAY.fullmatch(type_name)
            if array:
                output.append(f"typedef struct {{ {_ctype(array[1])} data[{int(array[2])}]; }} {_ctype(type_name)};")
        emitted: set[str] = set()
        visiting: set[str] = set()

        def record_definition(name: str) -> None:
            if name in emitted:
                return
            if name in visiting:
                raise ValueError("recursive record layout reached code generation")
            visiting.add(name)
            record = self.records[name]
            for _, field_type in record.fields:
                if field_type in self.records:
                    record_definition(field_type)
            fields = " ".join(f"{_ctype(field_type)} {_field(field_name)};" for field_name, field_type in record.fields)
            output.append(f"typedef struct {{ {fields} }} {_ctype(name)};")
            visiting.remove(name)
            emitted.add(name)

        for name in self.records:
            record_definition(name)
        return output

    def _prototype(self, function: ast.Function) -> str:
        args = ", ".join(f"const {_ctype(type_name)} {_var(name)}" for name, type_name in function.params) or "void"
        return f"static {_ctype(function.return_type)} {_func(function.name)}({args})"

    def expression(self, expression: ast.Expr) -> str:
        kind = type(expression).__name__
        if kind == "IntLit":
            value = expression.value
            if value == -(1 << 63):
                return "(-INT64_C(9223372036854775807) - INT64_C(1))"
            if value < 0:
                return f"(-INT64_C({-value}))"
            return f"INT64_C({value})"
        if kind == "BoolLit":
            return "true" if expression.value else "false"
        if kind == "Name":
            return _var(expression.name)
        if kind == "Unary":
            # Source INT64_MIN is represented as unary minus of a literal.
            if expression.op == "-" and type(expression.operand).__name__ == "IntLit" and expression.operand.value == (1 << 63):
                return "(-INT64_C(9223372036854775807) - INT64_C(1))"
            op = {"not": "!"}.get(expression.op, expression.op)
            return f"({op}({self.expression(expression.operand)}))"
        if kind == "Binary":
            op = {"and": "&&", "or": "||"}.get(expression.op, expression.op)
            return f"({self.expression(expression.left)} {op} {self.expression(expression.right)})"
        if kind == "Call":
            args = ", ".join(self.expression(value) for value in expression.args)
            if expression.name in self.records:
                record = self.records[expression.name]
                fields = ", ".join(f".{_field(name)} = {self.expression(value)}" for (name, _), value in zip(record.fields, expression.args))
                return f"(({_ctype(expression.name)}){{ {fields} }})"
            if expression.name == "len":
                array = _ARRAY.fullmatch(self.expr_types[id(expression.args[0])])
                if array is None:
                    raise ValueError("len of a non-array reached code generation")
                return f"INT64_C({int(array[2])})"
            if expression.name == "print":
                value = expression.args[0]
                if self.expr_types[id(value)] == "bool":
                    return f'puts(({self.expression(value)}) ? "true" : "false")'
                return f'printf("%" PRId64 "\\n", {self.expression(value)})'
            return f"{_func(expression.name)}({args})"
        if kind == "Field":
            return f"(({self.expression(expression.value)}).{_field(expression.name)})"
        if kind == "ArrayLit":
            values = ", ".join(self.expression(value) for value in expression.items)
            return f"(({_ctype(self.expr_types[id(expression)])}){{ .data = {{ {values} }} }})"
        if kind == "Index":
            return f"(({self.expression(expression.value)}).data[{self.expression(expression.index)}])"
        raise TypeError(f"unhandled expression {kind}")

    def _worker_definitions(self) -> list[str]:
        output: list[str] = []
        for task in self.tasks.values():
            fields = [f"    {_ctype(type_name)} arg_{index};" for index, (_, type_name) in enumerate(task.callee.params)]
            fields.append(f"    {_ctype(task.callee.return_type)} result;")
            output.extend([
                f"typedef struct {{",
                *fields,
                f"}} clack_task_{task.number};",
                f"static void *clack_worker_{task.number}(void *opaque) {{",
                f"    clack_task_{task.number} *task = (clack_task_{task.number} *)opaque;",
                f"    task->result = {_func(task.callee.name)}({', '.join(f'task->arg_{index}' for index in range(len(task.callee.params)))});",
                "    return NULL;",
                "}",
            ])
        return output

    def _parallel(self, statement: ast.Stmt, indent: str) -> list[str]:
        output = [indent + "{"]
        inner = indent + "    "
        # Snapshot every task argument before launching work or changing any
        # result binding, including when a binding reuses an existing local.
        for binding in statement.bindings:
            task = self.tasks[id(binding)]
            initializers = ", ".join(f".arg_{index} = {self.expression(value)}" for index, value in enumerate(binding.value.args))
            initializer = "{ " + initializers + " }" if initializers else "{0}"
            output.extend([
                f"{inner}clack_task_{task.number} task_{task.number} = {initializer};",
                f"{inner}pthread_t thread_{task.number};",
                f"{inner}bool started_{task.number};",
            ])
        for binding in statement.bindings:
            task = self.tasks[id(binding)]
            output.extend([
                f"{inner}started_{task.number} = pthread_create(&thread_{task.number}, NULL, clack_worker_{task.number}, &task_{task.number}) == 0;",
                f"{inner}if (!started_{task.number}) (void)clack_worker_{task.number}(&task_{task.number});",
            ])
        for binding in statement.bindings:
            task = self.tasks[id(binding)]
            output.append(f"{inner}if (started_{task.number} && pthread_join(thread_{task.number}, NULL) != 0) abort();")
        for binding in statement.bindings:
            task = self.tasks[id(binding)]
            output.append(f"{inner}{_var(binding.name)} = task_{task.number}.result;")
        output.append(indent + "}")
        return output

    def statements(self, body: list[ast.Stmt], indent: str = "    ") -> list[str]:
        output: list[str] = []
        for statement in body:
            kind = type(statement).__name__
            if kind == "Assign":
                output.append(f"{indent}{_var(statement.name)} = {self.expression(statement.value)};")
            elif kind == "IndexAssign":
                output.append(f"{indent}{_var(statement.name)}.data[{self.expression(statement.index)}] = {self.expression(statement.value)};")
            elif kind == "Return":
                value = " " + self.expression(statement.value) if statement.value is not None else ""
                output.append(f"{indent}return{value};")
            elif kind == "ExprStmt":
                output.append(f"{indent}(void)({self.expression(statement.value)});")
            elif kind == "If":
                output.append(f"{indent}if ({self.expression(statement.condition)}) {{")
                output.extend(self.statements(statement.then_body, indent + "    "))
                if statement.else_body:
                    output.append(indent + "} else {")
                    output.extend(self.statements(statement.else_body, indent + "    "))
                output.append(indent + "}")
            elif kind == "While":
                output.append(f"{indent}while ({self.expression(statement.condition)}) {{")
                output.extend(self.statements(statement.body, indent + "    "))
                output.append(indent + "}")
            elif kind == "Assert":
                output.append(f"{indent}/* assertion proved at source line {statement.line} */")
            elif kind == "Parallel":
                output.extend(self._parallel(statement, indent))
            else:
                raise TypeError(f"unhandled statement {kind}")
        return output

    def emit(self) -> str:
        output = [
            "/* Generated by Clack. Contracts and assertions were checked before emission.",
            " * The C backend, C compiler, solver, and OS remain trusted components. */",
            "#include <stdint.h>",
            "#include <inttypes.h>",
            "#include <stdbool.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <pthread.h>",
            "",
            *self._type_definitions(),
            "",
            *[self._prototype(function) + ";" for function in self.program.functions],
            "",
            *self._worker_definitions(),
        ]
        for function in self.program.functions:
            output.append("")
            output.append(self._prototype(function) + " {")
            for name, type_name in self.local_types.get(function.name, {}).items():
                output.append(f"    {_ctype(type_name)} {_var(name)};")
            output.extend(self.statements(function.body))
            output.append("}")
        output.extend(["", "int main(void) {", "    clack_fn_main();", "    return 0;", "}", ""])
        return "\n".join(output)


def emit_c(program: ast.Program, local_types: dict[str, dict[str, str]], expr_types: dict[int, str]) -> str:
    """Return C11 source. Call only after successful strict verification."""
    return _Emitter(program, local_types, expr_types).emit()
