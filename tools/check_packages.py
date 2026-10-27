#!/usr/bin/env python3
"""Check package API metadata, source hashes, native demos, and regressions."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "packages/catalog.json"
sys.path.insert(0, str(ROOT))
from clack.frontend import CompileError, parse
from clack.modules import load_program


def inside(path):
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT / "packages"):
        raise ValueError(f"package path escapes packages/: {path}")
    return resolved


def metadata(package):
    source = inside(package["source"])
    program = parse(source.read_text(encoding="utf-8"))
    exports = []
    for record in program.records:
        fields = ", ".join(f"{name}: {typ}" for name, typ in record.fields)
        exports.append({"kind": "type", "name": record.name,
                        "signature": f"type {record.name}({fields})", "line": record.line})
    for function in program.functions:
        args = ", ".join(f"{name}: {typ}" for name, typ in function.params)
        exports.append({"kind": "native" if function.foreign_symbol else "function", "name": function.name,
                        "signature": f"fn {function.name}({args}) -> {function.return_type}", "line": function.line})
    files = [{"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(source.parent.rglob("*")) if path.is_file() and path.suffix in {".clack", ".c"}]
    reexports = [{"module": item.module, "names": item.names, "line": item.line} for item in program.imports]
    loaded = load_program(source)
    assurance = "native-boundary" if loaded.native_sources or any(fn.foreign_symbol for fn in loaded.functions) else "verified-source"
    return {"exports": exports, "reexports": reexports, "files": files, "assurance": assurance}


def check(catalog, update):
    errors = []
    seen = set()
    for package in catalog["packages"]:
        label = package["id"]
        if label in seen:
            errors.append(f"duplicate package id: {label}")
        seen.add(label)
        source = inside(package["source"])
        if package["module"] != str(source.relative_to(ROOT).with_suffix("")).replace(os.sep, "."):
            errors.append(f"{label}: module does not match source path")
        for key in ("source", "readme", "license_file", "tests"):
            if not inside(package[key]).exists():
                errors.append(f"{label}: missing {key}: {package[key]}")
        for demo in package["demos"]:
            if not inside(demo["path"]).is_file():
                errors.append(f"{label}: missing demo: {demo['path']}")
            if ("stdout" in demo) == ("stdout_contains" in demo):
                errors.append(f"{label}: demo needs exact stdout or stdout_contains")
        expected = metadata(package)
        for key, value in expected.items():
            if update:
                package[key] = value
            elif package.get(key) != value:
                errors.append(f"{label}: stale {key}; run tools/check_packages.py --update --metadata-only")
    return errors


def execute(catalog):
    errors, demos = [], 0
    env = dict(os.environ, CLACK_TUI_ASCII="1", NO_COLOR="1")
    for package in catalog["packages"]:
        for demo in package["demos"]:
            demos += 1
            result = subprocess.run([sys.executable, "-m", "clack", "run", str(inside(demo["path"]))],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
            correct = result.stdout == demo["stdout"] if "stdout" in demo else all(text in result.stdout for text in demo["stdout_contains"])
            correct = correct and result.stdout.endswith(demo.get("stdout_endswith", ""))
            if result.returncode or not correct:
                errors.append(f"{demo['path']}: unexpected exit/output: {result.returncode}, {result.stdout!r}, {result.stderr.strip()}")
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(inside(package["tests"])), "-q"],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        if result.returncode:
            errors.append(f"{package['id']}: regression tests failed\n{result.stderr}")
        else:
            print(f"{package['id']}: " + result.stderr.strip().replace("\n", " "))
    return errors, demos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="refresh generated API signatures and source hashes")
    parser.add_argument("--metadata-only", action="store_true", help="skip compiling demos and running tests")
    args = parser.parse_args()
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        if catalog["schema_version"] != 1:
            raise ValueError("unsupported package catalog schema")
        errors = check(catalog, args.update)
        if errors:
            raise ValueError("\n".join(errors))
        if args.update:
            CATALOG.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        demos = 0
        if not args.metadata_only:
            errors, demos = execute(catalog)
            if errors:
                raise ValueError("\n".join(errors))
        print(f"Packages checked: {len(catalog['packages'])}; native demo outcomes: {demos}.")
        return 0
    except (CompileError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"packages: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
