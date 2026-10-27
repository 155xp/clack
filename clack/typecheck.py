"""Static types, definite assignment, purity, and acyclic call checking.

Proof expressions and executable expressions share types, but only ``len`` may
be called inside proofs. The verifier supplies the mathematical interpretation
of proof arithmetic and the finite-width checks for executable arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from . import frontend as f
from .arrayops import PREFIX as ARRAY_PREFIX, OPERATIONS


@dataclass
class TypeInfo:
    local_types: dict[str, dict[str, str]]
    expr_types: dict[int, str]
    call_order: list[str]
    records: dict[str, f.Record]
    functions: dict[str, f.Function]


_ARRAY = re.compile(r"(int|bool)\[([0-9]+)\]\Z")
_RESERVED = frozenset(
    "fn type parallel if elif else while for in range return assert requires ensures invariant "
    "decreases and or not true false int bool unit text result print len from import native extern".split()
)


def array_type(type_name: str) -> tuple[str, int] | None:
    """Return a fixed array's element type and length, or None."""
    match = _ARRAY.fullmatch(type_name)
    return (match[1], int(match[2])) if match else None


def _names(expr: f.Expr) -> set[str]:
    if isinstance(expr, f.Name):
        return {expr.name}
    if isinstance(expr, f.Unary):
        return _names(expr.operand)
    if isinstance(expr, f.Binary):
        return _names(expr.left) | _names(expr.right)
    if isinstance(expr, f.Call):
        return set().union(*(_names(arg) for arg in expr.args))
    if isinstance(expr, f.ArrayLit):
        return set().union(*(_names(item) for item in expr.items))
    if isinstance(expr, f.Field):
        return _names(expr.value)
    if isinstance(expr, f.Index):
        return _names(expr.value) | _names(expr.index)
    return set()


class _Checker:
    def __init__(self, program: f.Program):
        self.program = program
        self.records: dict[str, f.Record] = {}
        self.functions: dict[str, f.Function] = {}
        self.local_types: dict[str, dict[str, str]] = {}
        self.expr_types: dict[int, str] = {}
        self.calls: dict[str, set[str]] = {}
        self.fn: f.Function | None = None
        self.params: set[str] = set()
        self.indices: set[str] = set()

    @staticmethod
    def fail(message: str, line: int) -> None:
        raise f.CompileError(message, line=line)

    def valid_name(self, name: str, line: int, role: str) -> None:
        if name in _RESERVED or name.startswith(ARRAY_PREFIX):
            self.fail(f"{name!r} is reserved and cannot name a {role}", line)

    def valid_type(self, name: str, line: int, allow_unit: bool = False) -> None:
        if name in {"int", "bool", "text"} or (allow_unit and name == "unit"):
            return
        arr = array_type(name)
        if arr is not None:
            if not 1 <= arr[1] <= 1_000_000:
                self.fail("fixed array length must be between 1 and 1000000", line)
            return
        if name in self.records:
            return
        self.fail(f"unknown or unsupported type {name!r}", line)

    def check_declarations(self) -> None:
        for record in self.program.records:
            self.valid_name(record.name, record.line, "type")
            if record.name in self.records:
                self.fail(f"duplicate type {record.name!r}", record.line)
            self.records[record.name] = record
        for fn in self.program.functions:
            self.valid_name(fn.name, fn.line, "function")
            if fn.name in self.functions or fn.name in self.records:
                self.fail(f"duplicate declaration {fn.name!r}", fn.line)
            self.functions[fn.name] = fn
            self.calls[fn.name] = set()
            self.local_types[fn.name] = {}
        for record in self.program.records:
            seen = set()
            if not record.fields:
                self.fail(f"type {record.name!r} needs at least one field", record.line)
            for name, typ in record.fields:
                if name in seen:
                    self.fail(f"duplicate field {name!r} in {record.name}", record.line)
                seen.add(name)
                self.valid_type(typ, record.line)
        # A by-value native layout cannot contain itself, even indirectly.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                self.fail(f"recursive by-value type {name!r} is unsupported", self.records[name].line)
            if name in visited:
                return
            visiting.add(name)
            for _, typ in self.records[name].fields:
                if typ in self.records:
                    visit(typ)
            visiting.remove(name)
            visited.add(name)

        for name in self.records:
            visit(name)
        main = self.functions.get("main")
        if main is None:
            self.fail("program needs a fn main(): entry point", 1)
        if main.params or main.return_type != "unit" or main.foreign_symbol is not None:
            self.fail("main must have no parameters and return unit: fn main():", main.line)
        if main.requires:
            self.fail("main cannot have requires: entry conditions must hold unconditionally", main.line)
        native_signatures = {}
        for fn in self.program.functions:
            self.valid_type(fn.return_type, fn.line, allow_unit=fn.name == "main" or fn.foreign_symbol is not None)
            if fn.foreign_symbol is not None:
                symbol = fn.foreign_symbol
                if not re.fullmatch(r"clack_[A-Za-z_0-9]+", symbol) or symbol.startswith(("clack_fn_", "clack_t_", "clack_v_", "clack_worker_", "clack_task_", "clack_reduce_", "clack_for_")):
                    self.fail("native symbols need a clack_ prefix and a non-reserved C identifier", fn.line)
                signature = (tuple(typ for _, typ in fn.params), fn.return_type)
                if fn.return_type not in {"int", "bool", "unit"} or any(typ not in {"int", "bool", "text"} for _, typ in fn.params):
                    self.fail("native parameters support int, bool, text; results support int, bool, unit", fn.line)
                if fn.body or fn.requires or fn.ensures or native_signatures.setdefault(symbol, signature) != signature:
                    self.fail("native declarations cannot have bodies/contracts or conflicting C signatures", fn.line)
            elif fn.name != "main" and fn.return_type == "unit":
                self.fail("only main can return unit in this version", fn.line)
            seen = set()
            for name, typ in fn.params:
                self.valid_name(name, fn.line, "parameter")
                if name in seen:
                    self.fail(f"duplicate parameter {name!r}", fn.line)
                seen.add(name)
                self.valid_type(typ, fn.line)

    def need(self, actual: str, wanted: str, line: int, context: str) -> None:
        if actual != wanted:
            self.fail(f"{context} needs {wanted}, got {actual}", line)

    def expr(self, expr: f.Expr, scope: dict[str, str], proof: bool = False, allow_native: bool = False) -> str:
        if isinstance(expr, f.IntLit):
            typ = "int"
        elif isinstance(expr, f.BoolLit):
            typ = "bool"
        elif isinstance(expr, f.StringLit):
            typ = "text"
        elif isinstance(expr, f.Name):
            if expr.name not in scope:
                self.fail(f"{expr.name!r} is not defined on every path before use", expr.line)
            typ = scope[expr.name]
        elif isinstance(expr, f.Unary):
            operand = self.expr(expr.operand, scope, proof)
            if expr.op == "not":
                self.need(operand, "bool", expr.line, "not")
                typ = "bool"
            elif expr.op in {"+", "-"}:
                self.need(operand, "int", expr.line, f"unary {expr.op}")
                typ = "int"
            else:
                self.fail(f"unsupported unary operator {expr.op!r}", expr.line)
        elif isinstance(expr, f.Binary):
            left = self.expr(expr.left, scope, proof)
            right = self.expr(expr.right, scope, proof)
            if expr.op in {"+", "-", "*", "/", "%"}:
                self.need(left, "int", expr.line, expr.op)
                self.need(right, "int", expr.line, expr.op)
                typ = "int"
            elif expr.op in {"and", "or"}:
                self.need(left, "bool", expr.line, expr.op)
                self.need(right, "bool", expr.line, expr.op)
                typ = "bool"
            elif expr.op in {"==", "!="}:
                if left != right or left not in {"int", "bool"}:
                    self.fail("equality compares matching int or bool values; compare record fields or array elements", expr.line)
                typ = "bool"
            elif expr.op in {"<", "<=", ">", ">="}:
                self.need(left, "int", expr.line, expr.op)
                self.need(right, "int", expr.line, expr.op)
                typ = "bool"
            else:
                self.fail(f"unsupported binary operator {expr.op!r}", expr.line)
        elif isinstance(expr, f.ArrayLit):
            if not expr.items:
                self.fail("arrays need at least one element", expr.line)
            element = self.expr(expr.items[0], scope, proof)
            if element not in {"int", "bool"}:
                self.fail("arrays currently contain int or bool elements", expr.line)
            for item in expr.items[1:]:
                self.need(self.expr(item, scope, proof), element, item.line, "array element")
            if len(expr.items) > 1_000_000:
                self.fail("array length exceeds 1000000", expr.line)
            typ = f"{element}[{len(expr.items)}]"
        elif isinstance(expr, f.Field):
            owner = self.expr(expr.value, scope, proof)
            record = self.records.get(owner)
            if record is None:
                self.fail(f"{owner} has no record fields", expr.line)
            fields = dict(record.fields)
            if expr.name not in fields:
                self.fail(f"type {owner} has no field {expr.name!r}", expr.line)
            typ = fields[expr.name]
        elif isinstance(expr, f.Index):
            owner = self.expr(expr.value, scope, proof)
            arr = array_type(owner)
            if arr is None:
                self.fail(f"cannot index {owner}; expected a fixed array", expr.line)
            self.need(self.expr(expr.index, scope, proof), "int", expr.line, "array index")
            typ = arr[0]
        elif isinstance(expr, f.Call):
            if proof and expr.name != "len":
                self.fail("proof expressions cannot call functions or constructors; use fields, operators, and len", expr.line)
            args = [self.expr(arg, scope, proof) for arg in expr.args]
            if expr.name == "len":
                if len(args) != 1 or array_type(args[0]) is None:
                    self.fail("len needs exactly one fixed array", expr.line)
                typ = "int"
            elif expr.name in OPERATIONS:
                operation = OPERATIONS[expr.name]
                if self.program.symbol_names.get(expr.name) != f"std.array.{operation.name}":
                    self.fail("array operators require an explicit import from std.array", expr.line)
                if operation.name == "fill":
                    if len(args) != 2 or args[0] not in {"int", "bool"}:
                        self.fail("fill needs an int or bool value and a literal array length", expr.line)
                    length = expr.args[1]
                    if not isinstance(length, f.IntLit) or not 1 <= length.value <= 1_000_000:
                        self.fail("fill length must be an integer literal between 1 and 1000000", length.line)
                    typ = f"{args[0]}[{length.value}]"
                else:
                    shape = array_type(args[0]) if len(args) == 1 else None
                    if shape is None or shape[0] != operation.element:
                        self.fail(f"{operation.name} needs exactly one fixed {operation.element} array", expr.line)
                    typ = operation.result
            elif expr.name == "print":
                if self.fn is None or self.fn.name != "main":
                    self.fail("print is allowed only in main; worker functions are pure", expr.line)
                if len(args) != 1 or args[0] not in {"int", "bool", "text"}:
                    self.fail("print needs exactly one int, bool, or text", expr.line)
                typ = "unit"
            elif expr.name == "main":
                self.fail("main is an entry point and cannot be called", expr.line)
            elif expr.name in self.records:
                record = self.records[expr.name]
                self.match_args(expr, args, record.fields, "constructor")
                typ = record.name
            elif expr.name in self.functions:
                fn = self.functions[expr.name]
                self.match_args(expr, args, fn.params, "function")
                assert self.fn is not None
                if fn.foreign_symbol is not None and (self.fn.name != "main" or not allow_native):
                    self.fail("native calls belong only in main's direct assignments or unit call statements", expr.line)
                self.calls[self.fn.name].add(fn.name)
                typ = fn.return_type
            else:
                self.fail(f"unknown function or constructor {expr.name!r}", expr.line)
        else:
            self.fail(f"unsupported expression {type(expr).__name__}", expr.line)
        self.expr_types[id(expr)] = typ
        return typ

    def match_args(self, expr: f.Call, args: list[str], params: list[tuple[str, str]], role: str) -> None:
        if len(args) != len(params):
            self.fail(f"{role} {expr.name} needs {len(params)} arguments, got {len(args)}", expr.line)
        for actual, (name, expected), argument in zip(args, params, expr.args):
            self.need(actual, expected, argument.line, f"argument {name!r} of {expr.name}")

    def bind(self, name: str, typ: str, line: int, scope: dict[str, str]) -> None:
        self.valid_name(name, line, "variable")
        if name in self.indices:
            self.fail(f"for index {name!r} is immutable", line)
        if name in self.params:
            self.fail(f"parameter {name!r} is immutable; assign to a new local variable", line)
        if typ == "unit":
            self.fail("unit expressions do not produce assignable values", line)
        assert self.fn is not None
        locals_ = self.local_types[self.fn.name]
        if name in locals_:
            self.need(typ, locals_[name], line, f"assignment to {name!r}")
        else:
            locals_[name] = typ
        scope[name] = typ

    def block(self, body: list[f.Stmt], entry: dict[str, str]) -> dict[str, str] | None:
        scope: dict[str, str] | None = dict(entry)
        assert self.fn is not None
        for stmt in body:
            if scope is None:
                self.fail("unreachable statement after an unconditional return", stmt.line)
            if isinstance(stmt, f.Assign):
                typ = self.expr(stmt.value, scope, allow_native=True)
                self.bind(stmt.name, typ, stmt.line, scope)
            elif isinstance(stmt, f.IndexAssign):
                if stmt.name in self.params:
                    self.fail(f"parameter {stmt.name!r} is immutable; copy it to a local before updating", stmt.line)
                if stmt.name not in scope:
                    self.fail(f"{stmt.name!r} is not defined on every path before use", stmt.line)
                arr = array_type(scope[stmt.name])
                if arr is None:
                    self.fail(f"cannot index {scope[stmt.name]}; expected a fixed array", stmt.line)
                self.need(self.expr(stmt.index, scope), "int", stmt.line, "array index")
                self.need(self.expr(stmt.value, scope), arr[0], stmt.line, "array element assignment")
            elif isinstance(stmt, f.Return):
                if self.fn.name == "main" and stmt.value is not None:
                    self.fail("main returns unit; use return without a value", stmt.line)
                actual = "unit" if stmt.value is None else self.expr(stmt.value, scope)
                self.need(actual, self.fn.return_type, stmt.line, "return")
                scope = None
            elif isinstance(stmt, f.ExprStmt):
                actual = self.expr(stmt.value, scope, allow_native=True)
                self.need(actual, "unit", stmt.line, "expression statement")
                if not isinstance(stmt.value, f.Call) or (stmt.value.name != "print" and self.functions.get(stmt.value.name, self.fn).foreign_symbol is None):
                    self.fail("only print and native unit calls can be used as expression statements", stmt.line)
            elif isinstance(stmt, f.Assert):
                self.need(self.expr(stmt.condition, scope, proof=True), "bool", stmt.line, "assert")
            elif isinstance(stmt, f.If):
                self.need(self.expr(stmt.condition, scope), "bool", stmt.line, "if condition")
                then_scope = self.block(stmt.then_body, scope)
                else_scope = self.block(stmt.else_body, scope)
                if then_scope is None:
                    scope = else_scope
                elif else_scope is None:
                    scope = then_scope
                else:
                    scope = {name: typ for name, typ in then_scope.items() if name in else_scope}
            elif isinstance(stmt, f.While):
                self.need(self.expr(stmt.condition, scope), "bool", stmt.line, "while condition")
                if not stmt.invariants:
                    self.fail("while needs at least one invariant", stmt.line)
                for invariant in stmt.invariants:
                    self.need(self.expr(invariant, scope, proof=True), "bool", invariant.line, "invariant")
                if stmt.decreases is None:
                    self.fail("while needs a decreases expression", stmt.line)
                self.need(self.expr(stmt.decreases, scope, proof=True), "int", stmt.line, "decreases")
                self.block(stmt.body, scope)
                # A loop may run zero times, so its new locals are unavailable.
            elif isinstance(stmt, f.For):
                self.valid_name(stmt.name, stmt.line, "for index")
                if stmt.name in scope:
                    self.fail(f"for index {stmt.name!r} would shadow an existing binding; choose a new name", stmt.line)
                self.need(self.expr(stmt.start, scope), "int", stmt.line, "range start")
                self.need(self.expr(stmt.stop, scope), "int", stmt.line, "range stop")
                inner = {**scope, stmt.name: "int"}
                for invariant in stmt.invariants:
                    self.need(self.expr(invariant, inner, proof=True), "bool", invariant.line, "invariant")
                self.indices.add(stmt.name)
                try:
                    self.block(stmt.body, inner)
                finally:
                    self.indices.remove(stmt.name)
            elif isinstance(stmt, f.Parallel):
                if not stmt.bindings:
                    self.fail("parallel needs at least one independent job", stmt.line)
                targets = [binding.name for binding in stmt.bindings]
                if len(set(targets)) != len(targets):
                    self.fail("parallel jobs need distinct result names", stmt.line)
                pending: list[tuple[f.Assign, str]] = []
                for binding in stmt.bindings:
                    value = binding.value
                    if not isinstance(value, f.Call) or value.name not in self.functions or value.name == "main":
                        self.fail("each parallel job must call a worker function", binding.line)
                    dependencies = _names(value) & set(targets)
                    if dependencies:
                        self.fail(f"parallel jobs must be independent; input references result {sorted(dependencies)[0]!r}", binding.line)
                    typ = self.expr(value, scope)
                    pending.append((binding, typ))
                for binding, typ in pending:
                    self.bind(binding.name, typ, binding.line, scope)
            else:
                self.fail(f"unsupported statement {type(stmt).__name__}", stmt.line)
        return scope

    def run(self) -> TypeInfo:
        unresolved = [*self.program.imports, *self.program.native_files]
        if unresolved:
            self.fail("unresolved imports: use clack.modules.load_program(path), or the clack command", unresolved[0].line)
        self.check_declarations()
        for fn in self.program.functions:
            if fn.foreign_symbol is not None:
                continue
            self.fn = fn
            self.params = {name for name, _ in fn.params}
            params = dict(fn.params)
            for requires in fn.requires:
                self.need(self.expr(requires, params, proof=True), "bool", requires.line, "requires")
            post_scope = dict(params)
            if fn.return_type != "unit":
                post_scope["result"] = fn.return_type
            for ensures in fn.ensures:
                self.need(self.expr(ensures, post_scope, proof=True), "bool", ensures.line, "ensures")
            end = self.block(fn.body, params)
            if end is not None and fn.return_type != "unit":
                self.fail(f"function {fn.name!r} must return a {fn.return_type} on every path", fn.line)
        active: set[str] = set()
        done: set[str] = set()
        order: list[str] = []

        def visit(name: str) -> None:
            if name in active:
                self.fail(f"recursive call cycle involving {name!r} is unsupported; use a loop with decreases", self.functions[name].line)
            if name in done:
                return
            active.add(name)
            for callee in sorted(self.calls[name]):
                visit(callee)
            active.remove(name)
            done.add(name)
            order.append(name)

        for name in self.functions:
            visit(name)
        return TypeInfo(self.local_types, self.expr_types, order, self.records, self.functions)


def check(program: f.Program) -> TypeInfo:
    """Check all source paths and return data required by verification/codegen."""
    return _Checker(program).run()
