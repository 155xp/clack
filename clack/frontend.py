"""Clack's syntax tree and indentation-based recursive descent parser.

Python's tokenizer supplies tokens and indentation markers only. Clack source is
never evaluated or passed to Python's AST/compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import re
import token
import tokenize


@dataclass(frozen=True)
class Span:
    line: int
    column: int = 1


class CompileError(Exception):
    """A source diagnostic with one-based line and column coordinates."""

    def __init__(self, message: str, line: int = 1, column: int = 1, source_path: str | None = None):
        self.message = message
        self.line = line
        self.column = column
        self.col = column
        self.source_path = source_path
        super().__init__(message)

    def __str__(self) -> str:
        return f"line {self.line}:{self.column}: {self.message}"


@dataclass(frozen=True)
class Expr:
    line: int


@dataclass(frozen=True)
class IntLit(Expr):
    value: int


@dataclass(frozen=True)
class BoolLit(Expr):
    value: bool


@dataclass(frozen=True)
class Name(Expr):
    name: str


@dataclass(frozen=True)
class Unary(Expr):
    op: str
    operand: Expr


@dataclass(frozen=True)
class Binary(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Call(Expr):
    name: str
    args: list[Expr]


@dataclass(frozen=True)
class Field(Expr):
    value: Expr
    name: str


@dataclass(frozen=True)
class ArrayLit(Expr):
    items: list[Expr]


@dataclass(frozen=True)
class Index(Expr):
    value: Expr
    index: Expr


@dataclass(frozen=True)
class Stmt:
    line: int


@dataclass(frozen=True)
class Assign(Stmt):
    name: str
    value: Expr


@dataclass(frozen=True)
class IndexAssign(Stmt):
    name: str
    index: Expr
    value: Expr


@dataclass(frozen=True)
class Return(Stmt):
    value: Expr | None


@dataclass(frozen=True)
class ExprStmt(Stmt):
    value: Expr


@dataclass(frozen=True)
class If(Stmt):
    condition: Expr
    then_body: list[Stmt]
    else_body: list[Stmt]


@dataclass(frozen=True)
class While(Stmt):
    condition: Expr
    invariants: list[Expr]
    decreases: Expr
    body: list[Stmt]


@dataclass(frozen=True)
class Assert(Stmt):
    condition: Expr


@dataclass(frozen=True)
class Parallel(Stmt):
    bindings: list[Assign]


@dataclass(frozen=True)
class Function:
    name: str
    params: list[tuple[str, str]]
    return_type: str
    requires: list[Expr]
    ensures: list[Expr]
    body: list[Stmt]
    line: int


@dataclass(frozen=True)
class Record:
    name: str
    fields: list[tuple[str, str]]
    line: int


@dataclass(frozen=True)
class Import:
    module: str
    names: list[str]
    line: int


@dataclass(frozen=True)
class Program:
    functions: list[Function]
    records: list[Record] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    locations: dict[int, tuple[str, int]] = field(default_factory=dict)
    symbol_names: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Token:
    kind: int
    text: str
    line: int
    column: int


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_KEYWORDS = frozenset(
    "fn type parallel if elif else while return assert requires ensures invariant decreases "
    "and or not true false int bool unit from import".split()
)
_OPERATORS = frozenset(
    {"(", ")", "[", "]", ".", ":", ",", "->", "=", "+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">="}
)


def _lex(source: str) -> list[_Token]:
    for line_number, line in enumerate(source.splitlines(), start=1):
        indentation = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in indentation:
            raise CompileError("use spaces for indentation, not tabs", line_number, 1)

    output: list[_Token] = []
    try:
        for item in tokenize.generate_tokens(io.StringIO(source).readline):
            if item.type in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}:
                continue
            if item.type == token.NAME:
                if not _IDENTIFIER.fullmatch(item.string):
                    raise CompileError("names must use ASCII letters, digits, and underscores", item.start[0], item.start[1] + 1)
            elif item.type == token.NUMBER:
                if not _INTEGER.fullmatch(item.string):
                    raise CompileError("only decimal integer literals are supported", item.start[0], item.start[1] + 1)
            elif item.type == token.OP:
                if item.string not in _OPERATORS:
                    raise CompileError(f"unsupported operator {item.string!r}", item.start[0], item.start[1] + 1)
            elif item.type == token.STRING:
                raise CompileError("strings are not supported in this version", item.start[0], item.start[1] + 1)
            elif item.type not in {token.INDENT, token.DEDENT, token.NEWLINE, token.ENDMARKER}:
                raise CompileError(f"unexpected character {item.string!r}", item.start[0], item.start[1] + 1)
            output.append(_Token(item.type, item.string, item.start[0], item.start[1] + 1))
    except IndentationError as error:
        raise CompileError("inconsistent indentation", error.lineno or 1, error.offset or 1) from None
    except tokenize.TokenError as error:
        message, location = error.args
        raise CompileError(message, location[0], location[1] + 1) from None
    return output


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.position = 0

    @property
    def current(self) -> _Token:
        return self.tokens[self.position]

    def advance(self) -> _Token:
        item = self.current
        if item.kind != token.ENDMARKER:
            self.position += 1
        return item

    def error(self, message: str, item: _Token | None = None) -> CompileError:
        item = item or self.current
        return CompileError(message, item.line, item.column)

    def accept(self, text: str) -> _Token | None:
        if self.current.text == text:
            return self.advance()
        return None

    def expect(self, text: str) -> _Token:
        if self.current.text != text:
            raise self.error(f"expected {text!r}, found {self.describe()}")
        return self.advance()

    def describe(self) -> str:
        if self.current.kind == token.ENDMARKER:
            return "end of file"
        if self.current.kind == token.NEWLINE:
            return "end of line"
        if self.current.kind == token.INDENT:
            return "unexpected indentation"
        if self.current.kind == token.DEDENT:
            return "end of block"
        return repr(self.current.text)

    def expect_kind(self, kind: int, description: str) -> _Token:
        if self.current.kind != kind:
            raise self.error(f"expected {description}, found {self.describe()}")
        return self.advance()

    def identifier(self) -> _Token:
        if self.current.kind != token.NAME or self.current.text in _KEYWORDS:
            raise self.error(f"expected a name, found {self.describe()}")
        return self.advance()

    def type_name(self) -> str:
        if self.current.kind != token.NAME or self.current.text in _KEYWORDS - {"int", "bool", "unit"}:
            raise self.error("expected a type name, such as int, bool, or Point")
        result = self.advance().text
        if self.accept("["):
            length = self.expect_kind(token.NUMBER, "a fixed array length")
            try:
                length_value = int(length.text)
            except ValueError:
                raise self.error("array length is too large to read", length) from None
            if length_value <= 0:
                raise self.error("fixed arrays need a positive length", length)
            self.expect("]")
            result += f"[{length.text}]"
        return result

    def line_end(self) -> None:
        self.expect_kind(token.NEWLINE, "end of line")

    def block_start(self) -> None:
        self.expect(":")
        self.line_end()
        self.expect_kind(token.INDENT, "an indented block")

    def program(self) -> Program:
        functions: list[Function] = []
        records: list[Record] = []
        imports: list[Import] = []
        while self.current.kind != token.ENDMARKER:
            if self.current.kind == token.NEWLINE:
                self.advance()
                continue
            if self.current.text == "fn":
                functions.append(self.function())
            elif self.current.text == "type":
                records.append(self.record())
            elif self.current.text == "from":
                imports.append(self.import_statement())
            else:
                raise self.error("top level declarations must start with 'fn', 'type', or 'from'")
        if not functions and not records and not imports:
            raise self.error("a source file needs at least one function, record, or import declaration")
        return Program(functions=functions, records=records, imports=imports)

    def import_statement(self) -> Import:
        start = self.expect("from")
        parts = [self.identifier().text]
        while self.accept("."):
            parts.append(self.identifier().text)
        self.expect("import")
        names = [self.identifier().text]
        while self.accept(","):
            if self.current.kind == token.NEWLINE:
                break
            names.append(self.identifier().text)
        self.line_end()
        return Import(module=".".join(parts), names=names, line=start.line)

    def record(self) -> Record:
        start = self.expect("type")
        name = self.identifier().text
        self.block_start()
        fields: list[tuple[str, str]] = []
        while self.current.kind not in {token.DEDENT, token.ENDMARKER}:
            field_name = self.identifier().text
            self.expect(":")
            fields.append((field_name, self.type_name()))
            self.line_end()
        self.expect_kind(token.DEDENT, "end of type declaration")
        if not fields:
            raise self.error("a record needs at least one field", start)
        return Record(name=name, fields=fields, line=start.line)

    def function(self) -> Function:
        start = self.expect("fn")
        name = self.identifier().text
        self.expect("(")
        params: list[tuple[str, str]] = []
        if self.current.text != ")":
            while True:
                param_name = self.identifier().text
                self.expect(":")
                params.append((param_name, self.type_name()))
                if not self.accept(",") or self.current.text == ")":
                    break
        self.expect(")")
        if self.accept("->"):
            return_type = self.type_name()
        elif name == "main":
            return_type = "unit"
        else:
            raise self.error("function results need '-> int' or '-> bool'")
        self.block_start()
        requires: list[Expr] = []
        ensures: list[Expr] = []
        while self.current.text in {"requires", "ensures"}:
            kind = self.advance().text
            condition = self.expression()
            self.line_end()
            (requires if kind == "requires" else ensures).append(condition)
        body = self.statements()
        self.expect_kind(token.DEDENT, "end of function")
        if not body:
            raise self.error("a function needs at least one executable statement", start)
        return Function(name=name, params=params, return_type=return_type, requires=requires, ensures=ensures, body=body, line=start.line)

    def statements(self) -> list[Stmt]:
        body: list[Stmt] = []
        while self.current.kind not in {token.DEDENT, token.ENDMARKER}:
            body.append(self.statement())
        return body

    def suite(self) -> list[Stmt]:
        self.block_start()
        body = self.statements()
        self.expect_kind(token.DEDENT, "end of block")
        if not body:
            raise self.error("blocks cannot be empty")
        return body

    def statement(self) -> Stmt:
        start = self.current
        if self.accept("parallel"):
            body = self.suite()
            bindings: list[Assign] = []
            for item in body:
                if not isinstance(item, Assign) or not isinstance(item.value, Call):
                    raise CompileError("parallel blocks contain only 'name = function(arguments)' bindings", item.line)
                bindings.append(item)
            return Parallel(line=start.line, bindings=bindings)
        if start.text == "if":
            self.advance()
            return self.if_statement(start)
        if start.text == "while":
            self.advance()
            condition = self.expression()
            self.block_start()
            invariants: list[Expr] = []
            while self.accept("invariant"):
                invariants.append(self.expression())
                self.line_end()
            if not invariants:
                raise self.error("a while loop must start with 'invariant <condition>'", start)
            if not self.accept("decreases"):
                raise self.error("a while loop needs 'decreases <integer measure>' after its invariants")
            decreases = self.expression()
            self.line_end()
            body = self.statements()
            self.expect_kind(token.DEDENT, "end of loop")
            if not body:
                raise self.error("a while loop needs an executable body", start)
            return While(line=start.line, condition=condition, invariants=invariants, decreases=decreases, body=body)
        if self.accept("return"):
            value = None if self.current.kind == token.NEWLINE else self.expression()
            self.line_end()
            return Return(line=start.line, value=value)
        if self.accept("assert"):
            condition = self.expression()
            self.line_end()
            return Assert(line=start.line, condition=condition)
        if start.text in {"requires", "ensures"}:
            raise self.error("function contracts must appear before executable statements")
        if start.text in {"invariant", "decreases"}:
            raise self.error("loop annotations must appear at the start of a while body")
        value = self.expression()
        if self.accept("="):
            assigned_value = self.expression()
            self.line_end()
            if isinstance(value, Name):
                return Assign(line=start.line, name=value.name, value=assigned_value)
            if isinstance(value, Index) and isinstance(value.value, Name):
                return IndexAssign(line=start.line, name=value.value.name, index=value.index, value=assigned_value)
            if isinstance(value, Field):
                raise self.error("record fields are immutable; create a replacement record", start)
            raise self.error("assignment needs a variable name or variable[index] target", start)
        self.line_end()
        return ExprStmt(line=start.line, value=value)

    def if_statement(self, start: _Token) -> If:
        condition = self.expression()
        then_body = self.suite()
        else_body: list[Stmt] = []
        if branch := self.accept("elif"):
            else_body = [self.if_statement(branch)]
        elif self.accept("else"):
            else_body = self.suite()
        return If(line=start.line, condition=condition, then_body=then_body, else_body=else_body)

    def expression(self) -> Expr:
        return self.disjunction()

    def disjunction(self) -> Expr:
        result = self.conjunction()
        while item := self.accept("or"):
            result = Binary(line=item.line, op="or", left=result, right=self.conjunction())
        return result

    def conjunction(self) -> Expr:
        result = self.negation()
        while item := self.accept("and"):
            result = Binary(line=item.line, op="and", left=result, right=self.negation())
        return result

    def negation(self) -> Expr:
        if item := self.accept("not"):
            return Unary(line=item.line, op="not", operand=self.negation())
        return self.comparison()

    def comparison(self) -> Expr:
        left = self.sum()
        result: Expr | None = None
        while self.current.text in {"==", "!=", "<", "<=", ">", ">="}:
            operator = self.advance()
            right = self.sum()
            comparison = Binary(line=operator.line, op=operator.text, left=left, right=right)
            result = comparison if result is None else Binary(line=operator.line, op="and", left=result, right=comparison)
            left = right
        return left if result is None else result

    def sum(self) -> Expr:
        result = self.product()
        while self.current.text in {"+", "-"}:
            item = self.advance()
            result = Binary(line=item.line, op=item.text, left=result, right=self.product())
        return result

    def product(self) -> Expr:
        result = self.unary()
        while self.current.text in {"*", "/", "%"}:
            item = self.advance()
            result = Binary(line=item.line, op=item.text, left=result, right=self.unary())
        return result

    def unary(self) -> Expr:
        if self.current.text in {"+", "-"}:
            item = self.advance()
            return Unary(line=item.line, op=item.text, operand=self.unary())
        return self.atom()

    def atom(self) -> Expr:
        result = self.primary()
        while True:
            if self.accept("."):
                name = self.identifier()
                result = Field(line=name.line, value=result, name=name.text)
            elif bracket := self.accept("["):
                index = self.expression()
                self.expect("]")
                result = Index(line=bracket.line, value=result, index=index)
            else:
                return result

    def primary(self) -> Expr:
        item = self.current
        if item.kind == token.NUMBER:
            self.advance()
            try:
                value = int(item.text)
            except ValueError:
                raise self.error("integer literal is too large to read", item) from None
            return IntLit(line=item.line, value=value)
        if item.text in {"true", "false"}:
            self.advance()
            return BoolLit(line=item.line, value=item.text == "true")
        if self.accept("("):
            result = self.expression()
            self.expect(")")
            return result
        if self.accept("["):
            items: list[Expr] = []
            if self.current.text == "]":
                raise self.error("array literals need at least one element")
            while True:
                items.append(self.expression())
                if not self.accept(",") or self.current.text == "]":
                    break
            self.expect("]")
            return ArrayLit(line=item.line, items=items)
        if item.kind == token.NAME and item.text not in _KEYWORDS:
            self.advance()
            if not self.accept("("):
                return Name(line=item.line, name=item.text)
            args: list[Expr] = []
            if self.current.text != ")":
                while True:
                    args.append(self.expression())
                    if not self.accept(",") or self.current.text == ")":
                        break
            self.expect(")")
            return Call(line=item.line, name=item.text, args=args)
        raise self.error(f"expected an expression, found {self.describe()}")


def parse(source: str) -> Program:
    """Parse a complete Clack source file, or raise CompileError."""
    return _Parser(_lex(source)).program()
