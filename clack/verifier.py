"""Path-sensitive, modular verification for Clack's deliberately small core.

The solver proves that the negation of each obligation is unsatisfiable. It is
never used to execute source. This verifier and the C backend are trusted code;
SMT transcripts are reproducible queries, not independently checked certificates.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import json
from pathlib import Path

import z3

from . import frontend as ast
from .reductions import REDUCTIONS
from .typecheck import array_type, check


MIN_INT = -(1 << 63)
MAX_INT = (1 << 63) - 1


@dataclass(frozen=True)
class Value:
    type: str
    term: z3.ExprRef


@dataclass
class State:
    env: dict[str, Value]
    path: z3.BoolRef

    def under(self, condition: z3.BoolRef) -> State:
        return State(self.env.copy(), z3.And(self.path, condition))


@dataclass
class Verification:
    program: ast.Program
    local_types: dict[str, dict[str, str]]
    expr_types: dict[int, str]
    obligations: list[dict]


class _Verifier:
    def __init__(self, program: ast.Program, timeout_ms: int, proof_dir: Path | None):
        self.program = program
        self.info = check(program)
        self.solver = z3.Solver()
        self.solver.set(timeout=timeout_ms)
        self.proof_dir = proof_dir
        self.sorts: dict[str, z3.SortRef] = {"int": z3.IntSort(), "bool": z3.BoolSort(), "text": z3.StringSort()}
        self.serial = 0
        self.obligations: list[dict] = []
        self.function: ast.Function | None = None
        self.entry: dict[str, Value] = {}
        if proof_dir is not None:
            proof_dir.mkdir(parents=True, exist_ok=True)

    def sort(self, type_name: str) -> z3.SortRef:
        if type_name in self.sorts:
            return self.sorts[type_name]
        array = array_type(type_name)
        if array:
            result = z3.ArraySort(z3.IntSort(), self.sort(array[0]))
        else:
            record = self.info.records[type_name]
            definition = z3.Datatype(f"Clack_{type_name}")
            definition.declare(f"make_{type_name}", *[(name, self.sort(t)) for name, t in record.fields])
            result = definition.create()
        self.sorts[type_name] = result
        return result

    def fresh(self, type_name: str, hint: str) -> Value:
        self.serial += 1
        return Value(type_name, z3.Const(f"{hint}@{self.serial}", self.sort(type_name)))

    def bounds(self, value: Value) -> z3.BoolRef:
        if value.type == "int":
            return z3.And(value.term >= MIN_INT, value.term <= MAX_INT)
        if value.type in {"bool", "text"}:
            return z3.BoolVal(True)
        array = array_type(value.type)
        if array:
            if array[0] == "bool":
                return z3.BoolVal(True)
            self.serial += 1
            index = z3.Int(f"index@{self.serial}")
            item = Value(array[0], z3.Select(value.term, index))
            return z3.ForAll([index], z3.Implies(z3.And(index >= 0, index < array[1]), self.bounds(item)))
        record = self.info.records[value.type]
        sort = self.sort(value.type)
        return z3.And(*[self.bounds(Value(t, sort.accessor(0, i)(value.term))) for i, (_, t) in enumerate(record.fields)])

    def prove(self, state: State, claim: z3.BoolRef, line: int, message: str) -> None:
        # A constant True claim needs no solver. False still needs its path:
        # an unreachable operation may legitimately have a false safety goal.
        trivial = z3.is_true(z3.simplify(claim))
        # Reuse solver machinery, never assertions: each obligation has its
        # own push/pop scope, including exported queries and failure paths.
        solver = self.solver
        with solver if not trivial or self.proof_dir is not None else nullcontext():
            status = z3.unsat
            if not trivial or self.proof_dir is not None:
                solver.add(state.path, z3.Not(claim))
                if not trivial:
                    status = solver.check()
            number = len(self.obligations) + 1
            location = getattr(self.program, "locations", {}).get(line)
            names = getattr(self.program, "symbol_names", {})
            entry = {"id": number, "function": names.get(self.function.name, self.function.name),
                     "line": location[1] if location else line, "claim": message, "status": str(status)}
            if location:
                entry["source"] = location[0]
            if self.proof_dir is not None:
                filename = f"{number:04d}.smt2"
                entry["query"] = filename
                (self.proof_dir / filename).write_text(solver.to_smt2(), encoding="utf-8")
            self.obligations.append(entry)
            if status == z3.unsat:
                return
            if status == z3.unknown:
                raise ast.CompileError(f"cannot prove {message}: {solver.reason_unknown()} (strict mode rejects unknown results)", line)
            model = solver.model()
            shown: list[str] = []
            for name, value in state.env.items():
                display = str(model.eval(value.term, model_completion=True))
                if len(display) > 150:
                    display = display[:147] + "..."
                shown.append(f"{name} = {display}")
            witness = "; ".join(shown[:12]) or "no inputs"
            raise ast.CompileError(f"cannot prove {message}\n  counterexample: {witness}", line)

    def int_result(self, term: z3.ArithRef, state: State, line: int, spec: bool) -> Value:
        result = Value("int", term)
        if not spec:
            self.prove(state, self.bounds(result), line, "integer arithmetic stays within signed 64-bit range")
        return result

    def expr(self, expression: ast.Expr, state: State, spec: bool = False) -> Value:
        line = expression.line
        if isinstance(expression, ast.IntLit):
            return self.int_result(z3.IntVal(expression.value), state, line, spec)
        if isinstance(expression, ast.BoolLit):
            return Value("bool", z3.BoolVal(expression.value))
        if isinstance(expression, ast.StringLit):
            return Value("text", z3.StringVal(expression.value))
        if isinstance(expression, ast.Name):
            return state.env[expression.name]
        if isinstance(expression, ast.Unary):
            # The signed minimum is one literal, not an overflowing positive
            # intermediate followed by negation.
            if expression.op == "-" and isinstance(expression.operand, ast.IntLit):
                return self.int_result(z3.IntVal(-expression.operand.value), state, line, spec)
            operand = self.expr(expression.operand, state, spec)
            if expression.op == "not":
                return Value("bool", z3.Not(operand.term))
            return self.int_result(-operand.term if expression.op == "-" else operand.term, state, line, spec)
        if isinstance(expression, ast.Binary):
            left = self.expr(expression.left, state, spec)
            if expression.op in {"and", "or"}:
                guard = left.term if expression.op == "and" else z3.Not(left.term)
                right_state = state.under(guard)
                right = self.expr(expression.right, right_state, spec)
                # A call on the RHS contributes its verified summary only on
                # the path where short-circuit evaluation actually reaches it.
                state.path = z3.And(state.path, z3.Implies(guard, right_state.path))
                operation = z3.And if expression.op == "and" else z3.Or
                return Value("bool", operation(left.term, right.term))
            right = self.expr(expression.right, state, spec)
            a, b = left.term, right.term
            op = expression.op
            if op in {"==", "!=", "<", "<=", ">", ">="}:
                operations = {"==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
                              "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b}
                return Value("bool", operations[op]())
            if op in {"/", "%"}:
                self.prove(state, b != 0, line, "division has a nonzero divisor")
                if not spec:
                    self.prove(state, z3.Not(z3.And(a == MIN_INT, b == -1)), line, "signed division does not overflow")
                # SMT integer division is Euclidean. Clack and C truncate toward
                # zero; calculate the quotient from nonnegative magnitudes.
                magnitude = z3.Abs(a) / z3.Abs(b)
                quotient = z3.If((a < 0) == (b < 0), magnitude, -magnitude)
                term = quotient if op == "/" else a - quotient * b
            else:
                term = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b}[op]()
            return self.int_result(term, state, line, spec)
        if isinstance(expression, ast.ArrayLit):
            values = [self.expr(value, state, spec) for value in expression.items]
            term = z3.K(z3.IntSort(), z3.IntVal(0) if values[0].type == "int" else z3.BoolVal(False))
            for i, value in enumerate(values):
                term = z3.Store(term, i, value.term)
            return Value(self.info.expr_types[id(expression)], term)
        if isinstance(expression, ast.Field):
            value = self.expr(expression.value, state, spec)
            fields = self.info.records[value.type].fields
            index = next(i for i, (name, _) in enumerate(fields) if name == expression.name)
            return Value(fields[index][1], self.sort(value.type).accessor(0, index)(value.term))
        if isinstance(expression, ast.Index):
            value = self.expr(expression.value, state, spec)
            index = self.expr(expression.index, state, spec)
            array = array_type(value.type)
            self.prove(state, z3.And(index.term >= 0, index.term < array[1]), line, "array index is in bounds")
            return Value(array[0], z3.Select(value.term, index.term))
        if isinstance(expression, ast.Call):
            if expression.name == "len":
                # Evaluate its argument too: source semantics must not hide
                # unsafe indexing/calls just because length is statically known.
                value = self.expr(expression.args[0], state, spec)
                return Value("int", z3.IntVal(array_type(value.type)[1]))
            args = [self.expr(value, state, spec) for value in expression.args]
            if expression.name in REDUCTIONS:
                operation = REDUCTIONS[expression.name]
                values = [z3.Select(args[0].term, i) for i in range(array_type(args[0].type)[1])]
                if operation.name == "sum":
                    total, bounds = values[0], []
                    for value in values[1:]:
                        total = total + value
                        bounds.append(self.bounds(Value("int", total)))
                    self.prove(state, z3.And(*bounds), line, "every partial sum stays within signed 64-bit range")
                else:
                    total = {"all": z3.And, "any": z3.Or, "count": lambda xs: z3.Sum([z3.If(x, 1, 0) for x in xs])}[operation.name](values)
                return Value(operation.result, total)
            if expression.name == "print":
                return Value("unit", z3.BoolVal(True))
            if expression.name in self.info.records:
                return Value(expression.name, self.sort(expression.name).constructor(0)(*[value.term for value in args]))
            return self.call(expression, args, state)
        raise TypeError(f"unhandled expression {type(expression).__name__}")

    def call(self, expression: ast.Call, args: list[Value], state: State) -> Value:
        function = self.info.functions[expression.name]
        if function.foreign_symbol is not None:
            if function.return_type == "unit":
                return Value("unit", z3.BoolVal(True))
            result = self.fresh(function.return_type, "native.result")
            state.path = z3.And(state.path, self.bounds(result))
            return result
        display_name = getattr(self.program, "symbol_names", {}).get(function.name, function.name)
        env = {name: value for (name, _), value in zip(function.params, args)}
        invocation = State(env, state.path)
        for requirement in function.requires:
            claim = self.expr(requirement, invocation, spec=True)
            requirement_location = getattr(self.program, "locations", {}).get(requirement.line)
            description = f"{requirement_location[0]}:{requirement_location[1]}" if requirement_location else f"line {requirement.line}"
            self.prove(invocation, claim.term, expression.line, f"precondition of {display_name} ({description})")
            invocation.path = z3.And(invocation.path, claim.term)
        result = self.fresh(function.return_type, f"{function.name}.result")
        invocation.env["result"] = result
        facts = [self.bounds(result)]
        for postcondition in function.ensures:
            # Callees are already checked. Rechecking well-definedness under
            # their precondition and prior postconditions is conservative.
            summary_state = State(invocation.env, z3.And(invocation.path, *facts))
            facts.append(self.expr(postcondition, summary_state, spec=True).term)
        state.path = z3.And(state.path, *facts)
        return result

    def postconditions(self, state: State, result: Value | None, line: int) -> None:
        env = self.entry.copy()
        if result is not None:
            env["result"] = result
        post = State(env, state.path)
        display_name = getattr(self.program, "symbol_names", {}).get(self.function.name, self.function.name)
        for condition in self.function.ensures:
            claim = self.expr(condition, post, spec=True)
            condition_location = getattr(self.program, "locations", {}).get(condition.line)
            description = f"{condition_location[0]}:{condition_location[1]}" if condition_location else f"line {condition.line}"
            self.prove(post, claim.term, line, f"postcondition of {display_name} ({description})")
            post.path = z3.And(post.path, claim.term)

    def assigned(self, statements: list[ast.Stmt]) -> set[str]:
        names: set[str] = set()
        for statement in statements:
            if isinstance(statement, (ast.Assign, ast.IndexAssign)):
                names.add(statement.name)
            elif isinstance(statement, ast.Parallel):
                names.update(value.name for value in statement.bindings)
            elif isinstance(statement, ast.If):
                names.update(self.assigned(statement.then_body))
                names.update(self.assigned(statement.else_body))
            elif isinstance(statement, (ast.While, ast.For)):
                names.update(self.assigned(statement.body))
        return names

    def counted_loop(self, statement: ast.For, state: State) -> State:
        # Snapshot both endpoints once, including any verified call summaries.
        start, stop = self.expr(statement.start, state), self.expr(statement.stop, state)
        self.serial += 1
        lower, upper = f"for.start@{self.serial}", f"for.stop@{self.serial}"
        state.env.update({lower: start, upper: stop, statement.name: start})
        line = statement.line
        index = ast.Name(line, statement.name)
        first, last = ast.Name(line, lower), ast.Name(line, upper)
        invariant = ast.Binary(line, "and", ast.Binary(line, ">=", index, first),
                               ast.Binary(line, "or", ast.Binary(line, "<=", index, last),
                                          ast.Binary(line, "==", index, first)))
        step = ast.Assign(line, statement.name, ast.Binary(line, "+", index, ast.IntLit(line, 1)))
        loop = ast.While(line, ast.Binary(line, "<", index, last),
                         [invariant, *statement.invariants], ast.Binary(line, "-", last, index),
                         [*statement.body, step])
        state = self.loop(loop, state)
        for name in (lower, upper, statement.name):
            del state.env[name]
        return state

    def loop(self, statement: ast.While, state: State) -> State:
        # Prove initiation with actual incoming values.
        for invariant in statement.invariants:
            value = self.expr(invariant, state, spec=True)
            self.prove(state, value.term, invariant.line, "loop invariant holds on entry")

        # Forget ALL modified values and path facts involving them by replacing
        # the environment, retaining only relations to old symbols. New symbols
        # are unrelated to old ones except through the declared invariant.
        head = State(state.env.copy(), state.path)
        for name in self.assigned(statement.body):
            if name in head.env:
                value = self.fresh(head.env[name].type, f"{self.function.name}.{name}.loop")
                head.env[name] = value
                head.path = z3.And(head.path, self.bounds(value))
        for invariant in statement.invariants:
            value = self.expr(invariant, head, spec=True)
            head.path = z3.And(head.path, value.term)
        condition = self.expr(statement.condition, head)
        active = head.under(condition.term)
        before = self.expr(statement.decreases, active, spec=True)
        self.prove(active, before.term >= 0, statement.decreases.line, "loop termination measure is nonnegative")
        outcomes = self.block(statement.body, [active])
        for outcome in outcomes:
            for invariant in statement.invariants:
                value = self.expr(invariant, outcome, spec=True)
                self.prove(outcome, value.term, invariant.line, "loop invariant is preserved")
            after = self.expr(statement.decreases, outcome, spec=True)
            self.prove(outcome, after.term < before.term, statement.decreases.line, "loop termination measure strictly decreases")
        return head.under(z3.Not(condition.term))

    def block(self, statements: list[ast.Stmt], states: list[State]) -> list[State]:
        for statement in statements:
            following: list[State] = []
            for state in states:
                if isinstance(statement, ast.Assign):
                    value = self.expr(statement.value, state)
                    state.env[statement.name] = value
                elif isinstance(statement, ast.IndexAssign):
                    array = state.env[statement.name]
                    index = self.expr(statement.index, state)
                    shape = array_type(array.type)
                    self.prove(state, z3.And(index.term >= 0, index.term < shape[1]), statement.line, "array update is in bounds")
                    value = self.expr(statement.value, state)
                    state.env[statement.name] = Value(array.type, z3.Store(array.term, index.term, value.term))
                elif isinstance(statement, ast.ExprStmt):
                    self.expr(statement.value, state)
                elif isinstance(statement, ast.Assert):
                    value = self.expr(statement.condition, state, spec=True)
                    self.prove(state, value.term, statement.line, "assertion")
                    state.path = z3.And(state.path, value.term)
                elif isinstance(statement, ast.Return):
                    result = self.expr(statement.value, state) if statement.value is not None else None
                    self.postconditions(state, result, statement.line)
                    continue
                elif isinstance(statement, ast.If):
                    condition = self.expr(statement.condition, state)
                    branches = self.block(statement.then_body, [state.under(condition.term)])
                    branches += self.block(statement.else_body, [state.under(z3.Not(condition.term))])
                    following.extend(self.join(branches))
                    continue
                elif isinstance(statement, ast.While):
                    state = self.loop(statement, state)
                elif isinstance(statement, ast.For):
                    state = self.counted_loop(statement, state)
                elif isinstance(statement, ast.Parallel):
                    # All arguments see the incoming environment. Function
                    # summaries may add facts but cannot mutate any inputs.
                    values = [(binding.name, self.expr(binding.value, state)) for binding in statement.bindings]
                    state.env.update(values)
                else:
                    raise TypeError(f"unhandled statement {type(statement).__name__}")
                following.append(state)
            states = following
        return states

    def join(self, states: list[State]) -> list[State]:
        """Merge continuing, disjoint branches; return paths were checked already."""
        if len(states) < 2:
            return states
        common = set.intersection(*(set(state.env) for state in states))
        env = {name: value for name, value in states[0].env.items() if name in common}
        for state in states[1:]:
            for name, value in env.items():
                alternative = state.env[name]
                if not value.term.eq(alternative.term):
                    env[name] = Value(value.type, z3.If(state.path, alternative.term, value.term))
        return [State(env, z3.Or(*(state.path for state in states)))]

    def run(self) -> Verification:
        try:
            for name in self.info.call_order:
                self.function = self.info.functions[name]
                if self.function.foreign_symbol is not None:
                    continue
                self.entry = {param: self.fresh(t, f"{name}.{param}") for param, t in self.function.params}
                state = State(self.entry.copy(), z3.And(*[self.bounds(value) for value in self.entry.values()]))
                for condition in self.function.requires:
                    value = self.expr(condition, state, spec=True)
                    state.path = z3.And(state.path, value.term)
                remaining = self.block(self.function.body, [state])
                if self.function.return_type == "unit":
                    for outcome in remaining:
                        self.postconditions(outcome, None, self.function.line)
            return Verification(self.program, self.info.local_types, self.info.expr_types, self.obligations)
        finally:
            if self.proof_dir is not None:
                (self.proof_dir / "obligations.json").write_text(json.dumps(self.obligations, indent=2) + "\n", encoding="utf-8")


def verify(program: ast.Program, timeout_ms: int = 5000, proof_dir: str | Path | None = None) -> Verification:
    """Reject any unproved obligation; return the checked types and SMT results."""
    if timeout_ms <= 0:
        raise ValueError("solver timeout must be positive")
    return _Verifier(program, timeout_ms, Path(proof_dir) if proof_dir is not None else None).run()
