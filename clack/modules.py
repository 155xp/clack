"""Load source libraries with explicit imports and independent module scopes.

Imports are resolved and linked before type checking. Library implementation
names are made unique, but the merged program retains original source locations
and readable symbol names for verification diagnostics and proof exports.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
from pathlib import Path

from . import frontend as ast
from .reductions import EXPORTS, PREFIX as REDUCTION_PREFIX


_RESERVED_PREFIX = "_clack_module_"
_PRIMITIVES = {"int", "bool", "unit", "text"}
_BUILTINS = {"print", "len"}
_DECLARATION_RESERVED = _PRIMITIVES | _BUILTINS | {"result"}


@dataclass(frozen=True)
class _Symbol:
    name: str
    kind: str


@dataclass
class _Module:
    path: Path
    label: str
    source: str
    program: ast.Program
    scope: dict[str, _Symbol]


class _Loader:
    def __init__(self, entry: Path):
        self.entry = entry.resolve()
        self.bundled = Path(__file__).resolve().parent / "stdlib"
        self.modules: dict[Path, _Module] = {}
        self.active: list[Path] = []
        self.symbol_names: dict[str, str] = {}

    @staticmethod
    def fail(module: _Module, message: str, line: int) -> None:
        raise ast.CompileError(message, line, source_path=str(module.path))

    def module_path(self, owner: _Module, declaration: ast.Import) -> Path:
        parts = declaration.module.split(".")
        if parts[0] == "std":
            if len(parts) == 1:
                self.fail(owner, "import a standard-library module such as std.math", declaration.line)
            candidate = self.bundled.joinpath(*parts[1:]).with_suffix(".clack")
        else:
            candidate = owner.path.parent.joinpath(*parts).with_suffix(".clack")
        if not candidate.is_file():
            self.fail(owner, f"module {declaration.module!r} was not found: {candidate}", declaration.line)
        return candidate.resolve()

    def read(self, path: Path, label: str) -> _Module:
        path = path.resolve()
        if path in self.modules:
            return self.modules[path]
        source = path.read_text(encoding="utf-8")
        try:
            program = ast.parse(source)
        except ast.CompileError as error:
            error.source_path = str(path)
            raise
        module = _Module(path, label, source, program, {})
        # Insert before following imports, retaining entry-first order for the
        # source map while the active stack separately detects cycles.
        self.modules[path] = module
        self.active.append(path)
        if path == (self.bundled / "array.clack").resolve():
            for name, internal in EXPORTS.items():
                module.scope[name] = _Symbol(internal, "reduction")
                self.symbol_names[internal] = f"std.array.{name}"
        declarations = [*program.records, *program.functions]
        for declaration in declarations:
            name = declaration.name
            if name.startswith((_RESERVED_PREFIX, REDUCTION_PREFIX)):
                self.fail(module, "compiler-internal names are reserved for linked libraries and reductions", declaration.line)
            if name in _DECLARATION_RESERVED:
                self.fail(module, f"{name!r} is reserved and cannot name a declaration", declaration.line)
            if name in module.scope:
                self.fail(module, f"duplicate declaration {name!r}", declaration.line)
            if path != self.entry and name == "main":
                self.fail(module, "a library cannot define main; put its entry point in a separate program", declaration.line)
            canonical = name
            if path != self.entry:
                digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
                canonical = f"{_RESERVED_PREFIX}{digest}_{name}"
                self.symbol_names[canonical] = f"{label}.{name}"
            kind = "type" if isinstance(declaration, ast.Record) else "function"
            module.scope[name] = _Symbol(canonical, kind)
        for declaration in program.imports:
            target_path = self.module_path(module, declaration)
            if target_path in self.active:
                chain = " -> ".join(item.name for item in [*self.active, target_path])
                self.fail(module, f"cyclic module import: {chain}", declaration.line)
            target = self.read(target_path, declaration.module)
            for name in declaration.names:
                if name == "main":
                    self.fail(module, "main is an entry point and cannot be imported", declaration.line)
                if name in _DECLARATION_RESERVED or name.startswith((_RESERVED_PREFIX, REDUCTION_PREFIX)):
                    self.fail(module, f"{name!r} is reserved and cannot be imported", declaration.line)
                if name in module.scope:
                    self.fail(module, f"import {name!r} conflicts with another declaration or import", declaration.line)
                if name not in target.scope:
                    self.fail(module, f"module {declaration.module!r} does not export {name!r}", declaration.line)
                module.scope[name] = target.scope[name]
        self.active.pop()
        return module

    def resolve_type(self, module: _Module, name: str, line: int) -> str:
        if name in _PRIMITIVES or "[" in name:
            return name
        symbol = module.scope.get(name)
        if symbol is None or symbol.kind != "type":
            self.fail(module, f"unknown or unsupported type {name!r}", line)
        return symbol.name

    def rewrite(self, value, module: _Module, offset: int):
        if isinstance(value, list):
            return [self.rewrite(item, module, offset) for item in value]
        if not is_dataclass(value):
            return value
        changed = {field.name: self.rewrite(getattr(value, field.name), module, offset) for field in fields(value)}
        if "line" in changed:
            changed["line"] += offset
        if isinstance(value, ast.Call):
            symbol = module.scope.get(value.name)
            if value.name in _BUILTINS:
                pass
            elif symbol is None:
                self.fail(module, f"unknown function or constructor {value.name!r}; import it explicitly before use", value.line)
            else:
                changed["name"] = symbol.name
        elif isinstance(value, ast.Function):
            changed["name"] = module.scope[value.name].name
            changed["params"] = [(name, self.resolve_type(module, typ, value.line)) for name, typ in value.params]
            changed["return_type"] = self.resolve_type(module, value.return_type, value.line)
        elif isinstance(value, ast.Record):
            changed["name"] = module.scope[value.name].name
            changed["fields"] = [(name, self.resolve_type(module, typ, value.line)) for name, typ in value.fields]
        return type(value)(**changed)

    def load(self) -> ast.Program:
        self.read(self.entry, "")
        functions: list[ast.Function] = []
        records: list[ast.Record] = []
        locations: dict[int, tuple[str, int]] = {}
        native_sources: list[str] = []
        offset = 0
        for module in self.modules.values():
            for declaration in module.program.native_files:
                name = Path(declaration.path)
                native = (module.path.parent / name).resolve()
                if name.is_absolute() or ".." in name.parts or name.suffix != ".c" or not native.is_relative_to(module.path.parent):
                    self.fail(module, "native sources must be relative .c files inside their module directory", declaration.line)
                if not native.is_file():
                    self.fail(module, f"native C source was not found: {name}", declaration.line)
                if str(native) not in native_sources:
                    native_sources.append(str(native))
            line_count = max(1, len(module.source.splitlines()))
            for line in range(1, line_count + 1):
                locations[line + offset] = (str(module.path), line)
            functions.extend(self.rewrite(module.program.functions, module, offset))
            records.extend(self.rewrite(module.program.records, module, offset))
            offset += line_count + 1
        return ast.Program(functions, records, locations=locations, symbol_names=self.symbol_names, native_sources=native_sources)


def load_program(path: str | Path) -> ast.Program:
    """Read an entry file and all explicit imports, ready for strict checking.

    Standard imports resolve only inside the bundled source library. Other
    dotted names resolve to a .clack file relative to the importing file.
    The returned AST contains no unresolved imports and no executable module
    initialization: only ordinary function and record declarations.
    """
    return _Loader(Path(path)).load()
