"""The command-line interface. Every emission path verifies first."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from time import perf_counter

from . import __version__
from .frontend import CompileError


def _positive(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clack", description="Native compilation with strict compile-time verification.")
    parser.add_argument("--version", action="version", version=f"Clack {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [("check", "prove contracts and safety"), ("build", "verify and build a native executable"),
                            ("run", "verify, build, and run"), ("emit-c", "verify and emit C11")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("source", type=Path, help="a .clack source file")
        command.add_argument("--timeout-ms", type=_positive, default=5000, help="solver timeout per obligation (default: 5000)")
        command.add_argument("--proof-dir", type=Path, help="save SMT queries and their obligation results")
        command.add_argument("--timings", action="store_true", help="report compiler phase timings on standard error")
        if name in {"build", "emit-c"}:
            command.add_argument("-o", "--output", type=Path)
        if name in {"build", "run"}:
            command.add_argument("--cc", default=os.environ.get("CC", "cc"), help="C compiler command (default: CC or cc)")
    return parser


def _protect_proofs(directory: Path | None, inputs: set[Path]) -> None:
    if directory is None:
        return
    directory = directory.resolve()
    candidates = inputs | (set(directory.iterdir()) if directory.is_dir() else set())
    for candidate in candidates:
        if candidate.parent != directory or not (candidate.name == "obligations.json" or re.fullmatch(r"[0-9]{4,}\.smt2", candidate.name)):
            continue
        if candidate.resolve() in inputs or (candidate.exists() and any(candidate.samefile(path) for path in inputs)):
            raise RuntimeError("proof outputs must differ from every input source, including imported libraries")


def _write_c(source: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".clack-", dir=output.parent) as directory:
        temporary = Path(directory) / "program.c"
        temporary.write_text(source, encoding="utf-8")
        os.replace(temporary, output)


def _compile(c_source: str, output: Path, cc: str, native_sources: Sequence[str] = ()) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    # A failed C compilation must not replace a previously working binary.
    with tempfile.TemporaryDirectory(prefix=".clack-", dir=output.parent) as directory:
        temporary = Path(directory)
        source = temporary / "program.c"
        binary = temporary / "program"
        source.write_text(c_source, encoding="utf-8")
        command = shlex.split(cc)
        if not command:
            raise RuntimeError("C compiler command cannot be empty")
        result = subprocess.run([*command, "-std=c11", "-O3", "-Wall", "-Wextra", "-pthread", str(source), *native_sources, "-o", str(binary)],
                                text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(f"C compiler failed:\n{result.stderr.strip()}")
        os.replace(binary, output)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = ""
    program = None
    timings: list[str] = []

    def measure(phase, action, *values, **options):
        if not args.timings:
            return action(*values, **options)
        started = perf_counter()
        try:
            return action(*values, **options)
        finally:
            timings.append(f"{phase}={(perf_counter() - started) * 1000:.2f}ms")

    try:
        # Keep --help / --version usable before the solver is installed.
        from .codegen import emit_c
        from .modules import load_program
        from .verifier import verify

        source = args.source.read_text(encoding="utf-8")
        program = measure("load", load_program, args.source)
        source_paths = {Path(path).resolve() for path, _ in program.locations.values()}
        source_paths.update(Path(path).resolve() for path in program.native_sources)
        _protect_proofs(args.proof_dir, source_paths)
        checked = measure("verify", verify, program, timeout_ms=args.timeout_ms, proof_dir=args.proof_dir)
        count = len(checked.obligations)
        native_count = sum(fn.foreign_symbol is not None for fn in program.functions)
        native_note = f" Native bindings: {native_count}; C sources: {len(program.native_sources)} (outside verification model)." if native_count or program.native_sources else ""
        if args.command == "check":
            print(f"Verified {args.source}: {count} obligations proved across {len(program.functions) - native_count} Clack functions.{native_note}")
            return 0
        c_source = measure("emit", emit_c, program, checked.local_types, checked.expr_types)
        if args.command == "emit-c":
            if args.output:
                if args.output.resolve() in source_paths:
                    raise RuntimeError("output must differ from every input source, including imported libraries")
                _write_c(c_source, args.output)
            else:
                sys.stdout.write(c_source)
            return 0
        if args.command == "build":
            output = args.output or Path("build") / args.source.stem
            if output.resolve() in source_paths:
                raise RuntimeError("output must differ from every input source, including imported libraries")
            measure("cc", _compile, c_source, output, args.cc, program.native_sources)
            print(f"Built {output} ({count} obligations proved).{native_note}")
            return 0
        with tempfile.TemporaryDirectory(prefix="clack-run-") as directory:
            output = Path(directory) / "program"
            measure("cc", _compile, c_source, output, args.cc, program.native_sources)
            result = subprocess.run([str(output)])
            return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except CompileError as error:
        error_path = error.source_path or args.source
        error_line = error.line
        if program is not None and not error.source_path:
            error_path, error_line = program.locations.get(error.line, (str(args.source), error.line))
        message = error.message
        if program is not None:
            for internal, display in sorted(program.symbol_names.items(), key=lambda item: -len(item[0])):
                message = message.replace(internal, display)
        print(f"{error_path}:{error_line}:{error.column}: error: {message}", file=sys.stderr)
        if Path(error_path).resolve() != args.source.resolve():
            try:
                source = Path(error_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                source = ""
        lines = source.splitlines()
        if 1 <= error_line <= len(lines):
            print(f"  {lines[error_line - 1]}", file=sys.stderr)
        return 1
    except ModuleNotFoundError as error:
        if error.name != "z3":
            raise
        print("clack: install the compiler dependencies with: python -m pip install -e .", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, RuntimeError, ValueError) as error:
        print(f"clack: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("clack: interrupted", file=sys.stderr)
        return 130
    finally:
        if timings:
            print("clack timings: " + ", ".join(timings), file=sys.stderr)
