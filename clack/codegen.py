"""Emit portable C11 for a verified Clack program.

The native program contains no interpreter, boxed numeric values, or solver.
Contracts, loop invariants, and assertions have already been proved by the
verifier and are erased here. This emitter is part of the trusted compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass

from . import frontend as ast
from .arrayops import OPERATIONS
from .typecheck import array_type


def _ctype(type_name: str) -> str:
    primitive = {"int": "int64_t", "bool": "bool", "unit": "void", "text": "const char *"}
    if type_name in primitive:
        return primitive[type_name]
    array = array_type(type_name)
    if array:
        return f"clack_t_array_{array[0]}_{array[1]}"
    return f"clack_t_record_{type_name}"


def _var(name: str) -> str:
    return f"clack_v_{name}"


def _func(name: str) -> str:
    return f"clack_fn_{name}"


def _field(name: str) -> str:
    return f"clack_field_{name}"


def _is_fill(expression) -> bool:
    return isinstance(expression, ast.Call) and expression.name in OPERATIONS and OPERATIONS[expression.name].name == "fill"


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
        self.array_operations: set[tuple[str, str]] = set()
        self.serial = 0
        self._collect_reachable()

    def _collect_reachable(self) -> None:
        reachable = {"main"}
        pending = ["main"]
        def visit(node) -> None:
            if isinstance(node, list):
                for value in node:
                    visit(value)
            elif is_dataclass(node):
                if isinstance(node, ast.Assign) and _is_fill(node.value):
                    visit(node.value.args)
                    return
                if isinstance(node, ast.Parallel):
                    for binding in node.bindings:
                        self.tasks[id(binding)] = _Task(len(self.tasks), binding, self.functions[binding.value.name])
                if isinstance(node, ast.Call) and node.name in OPERATIONS:
                    shape = node if OPERATIONS[node.name].name == "fill" else node.args[0]
                    self.array_operations.add((node.name, self.expr_types[id(shape)]))
                if isinstance(node, ast.Call) and node.name in self.functions and node.name not in reachable:
                    reachable.add(node.name)
                    pending.append(node.name)
                for field in fields(node):
                    visit(getattr(node, field.name))
        while pending:
            visit(self.functions[pending.pop()])
        self.functions = {name: fn for name, fn in self.functions.items() if name in reachable}

    def _type_definitions(self) -> list[str]:
        types = set(self.expr_types.values())
        for function in self.functions.values():
            types.add(function.return_type)
            types.update(value for _, value in function.params)
            types.update(self.local_types.get(function.name, {}).values())
        for record in self.records.values():
            types.update(value for _, value in record.fields)
        output: list[str] = []
        for type_name in sorted(types):
            array = array_type(type_name)
            if array:
                output.append(f"typedef struct {{ {_ctype(array[0])} data[{array[1]}]; }} {_ctype(type_name)};")
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

    def _operation_name(self, name: str, type_name: str) -> str:
        element, length = array_type(type_name)
        return f"clack_reduce_{OPERATIONS[name].name}_{element}_{length}"

    def _operation_definitions(self) -> list[str]:
        output = []
        for name, type_name in sorted(self.array_operations):
            operation = OPERATIONS[name]
            if operation.name == "fill":
                output.extend([
                    f"static {_ctype(type_name)} {self._operation_name(name, type_name)}({_ctype(array_type(type_name)[0])} value) {{",
                    f"    {_ctype(type_name)} result;",
                    f"    for (size_t i = 0; i < {array_type(type_name)[1]}; ++i) result.data[i] = value;",
                    "    return result;", "}",
                ])
                continue
            numeric = operation.result == "int"
            extrema = operation.name in {"minimum", "maximum"}
            step = {"sum": "result += values->data[i];", "count": "result += values->data[i];",
                    "all": "if (!values->data[i]) return false;", "any": "if (values->data[i]) return true;",
                    "minimum": "if (values->data[i] < result) result = values->data[i];",
                    "maximum": "if (values->data[i] > result) result = values->data[i];"}[operation.name]
            output.extend([
                f"static {_ctype(operation.result)} {self._operation_name(name, type_name)}(const {_ctype(type_name)} *values) {{",
                *([f"    int64_t result = {'values->data[0]' if extrema else '0'};"] if numeric else []),
                f"    for (size_t i = {1 if extrema else 0}; i < {array_type(type_name)[1]}; ++i) {{ {step} }}",
                f"    return {'result' if numeric else 'true' if operation.name == 'all' else 'false'};", "}",
            ])
        return output

    def _prototype(self, function: ast.Function) -> str:
        args = ", ".join(f"{_ctype(type_name)} const {_var(name)}" for name, type_name in function.params) or "void"
        foreign = function.foreign_symbol is not None
        return f"{'extern' if foreign else 'static'} {_ctype(function.return_type)} {function.foreign_symbol if foreign else _func(function.name)}({args})"

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
        if kind == "StringLit":
            # Fixed-width octal escapes preserve UTF-8 bytes and avoid C trigraphs.
            return '"' + ''.join(chr(byte) if 32 <= byte < 127 and byte not in (34, 63, 92) else f"\\{byte:03o}" for byte in expression.value.encode("utf-8")) + '"'
        if kind == "Name":
            return _var(expression.name)
        if kind == "Unary":
            # Source INT64_MIN is represented as unary minus of a literal.
            if expression.op == "-" and type(expression.operand).__name__ == "IntLit" and expression.operand.value == (1 << 63):
                return "(-INT64_C(9223372036854775807) - INT64_C(1))"
            op = {"not": "!"}.get(expression.op, expression.op)
            return f"({op}({self.expression(expression.operand)}))"
        if kind == "Binary":
            if expression.op in {"==", "!="} and self.expr_types[id(expression.left)] == "text":
                return f"(strcmp({self.expression(expression.left)}, {self.expression(expression.right)}) {expression.op} 0)"
            op = {"and": "&&", "or": "||"}.get(expression.op, expression.op)
            return f"({self.expression(expression.left)} {op} {self.expression(expression.right)})"
        if kind == "Call":
            if expression.name in OPERATIONS:
                value = expression.args[0]
                if OPERATIONS[expression.name].name == "fill":
                    return f"{self._operation_name(expression.name, self.expr_types[id(expression)])}({self.expression(value)})"
                type_name = self.expr_types[id(value)]
                source = self.expression(value)
                argument = f"&({source})" if isinstance(value, (ast.Name, ast.ArrayLit)) else f"((const {_ctype(type_name)}[]){{ {source} }})"
                return f"{self._operation_name(expression.name, type_name)}({argument})"
            if expression.name in self.records:
                record = self.records[expression.name]
                fields = ", ".join(f".{_field(name)} = {self.expression(value)}" for (name, _), value in zip(record.fields, expression.args))
                return f"(({_ctype(expression.name)}){{ {fields} }})"
            if expression.name == "len":
                if self.expr_types[id(expression.args[0])] == "text":
                    return f"((int64_t)strlen({self.expression(expression.args[0])}))"
                array = array_type(self.expr_types[id(expression.args[0])])
                if array is None:
                    raise ValueError("len of a non-array reached code generation")
                return f"INT64_C({array[1]})"
            if expression.name == "print":
                value = expression.args[0]
                if self.expr_types[id(value)] == "text":
                    return f"puts({self.expression(value)})"
                if self.expr_types[id(value)] == "bool":
                    return f'puts(({self.expression(value)}) ? "true" : "false")'
                return f'printf("%" PRId64 "\\n", {self.expression(value)})'
            args = ", ".join(self.expression(value) for value in expression.args)
            return f"{self.functions[expression.name].foreign_symbol or _func(expression.name)}({args})"
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
            output.append(f"{inner}clack_task_{task.number} task_{task.number} = {initializer};")
            if binding is not statement.bindings[-1]:
                output.extend([f"{inner}pthread_t thread_{task.number};", f"{inner}bool started_{task.number};"])
        for binding in statement.bindings[:-1]:
            task = self.tasks[id(binding)]
            output.extend([
                f"{inner}started_{task.number} = pthread_create(&thread_{task.number}, NULL, clack_worker_{task.number}, &task_{task.number}) == 0;",
                f"{inner}if (!started_{task.number}) (void)clack_worker_{task.number}(&task_{task.number});",
            ])
        # The caller participates instead of idling behind one extra pthread.
        task = self.tasks[id(statement.bindings[-1])]
        output.append(f"{inner}(void)clack_worker_{task.number}(&task_{task.number});")
        for binding in statement.bindings[:-1]:
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
                if _is_fill(statement.value):
                    self.serial += 1
                    element, length = array_type(self.expr_types[id(statement.value)])
                    value, index = f"clack_for_{self.serial}_fill", f"clack_for_{self.serial}_index"
                    output.extend([f"{indent}{{",
                                   f"{indent}    const {_ctype(element)} {value} = {self.expression(statement.value.args[0])};",
                                   f"{indent}    for (size_t {index} = 0; {index} < {length}; ++{index}) {_var(statement.name)}.data[{index}] = {value};",
                                   indent + "}"])
                else:
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
            elif kind == "For":
                self.serial += 1
                start, stop = f"clack_for_{self.serial}_start", f"clack_for_{self.serial}_stop"
                output.extend([f"{indent}{{",
                               f"{indent}    const int64_t {start} = {self.expression(statement.start)};",
                               f"{indent}    const int64_t {stop} = {self.expression(statement.stop)};",
                               f"{indent}    for (int64_t {_var(statement.name)} = {start}; {_var(statement.name)} < {stop}; ++{_var(statement.name)}) {{"])
                output.extend(self.statements(statement.body, indent + "        "))
                output.extend([indent + "    }", indent + "}"])
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
            "#include <string.h>",
            "#include <pthread.h>",
            "",
            *self._type_definitions(),
            *self._operation_definitions(),
            "",
            *[self._prototype(function) + ";" for function in self.functions.values()],
            "",
            *self._worker_definitions(),
        ]
        for function in self.functions.values():
            if function.foreign_symbol is not None:
                continue
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
