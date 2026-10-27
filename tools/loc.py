#!/usr/bin/env python3
"""Count Clack's implementation separately from tests, benchmarks, and docs."""

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def group(name):
    path = Path(name)
    if name.startswith("clack/"):
        return "standard_library" if path.suffix == ".clack" else "compiler" if path.suffix == ".py" else None
    if name.startswith("packages/"):
        if path.suffix in {".clack", ".c"}:
            return "package_examples" if path.name.endswith("demo.clack") else "optional_libraries"
        if path.suffix == ".py":
            return "package_tests"
    for folder, extension in (("tests", ".py"), ("benchmarks", ".py"), ("tools", ".py"), ("examples", ".clack")):
        if path.parts[0] == folder and path.suffix == extension:
            return folder
    if (path.suffix == ".md" and (path.parts[0] in {"docs", "benchmarks", "packages"} or name == "README.md")) or name in {"llms.txt", "docs/agent-reference.json", "packages/catalog.json"}:
        return "documentation"


def count(ref=None):
    if ref:
        tree = subprocess.check_output(["git", "rev-parse", "--verify", "--end-of-options", ref + "^{tree}"], cwd=ROOT, text=True).strip()
        names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", tree], cwd=ROOT).decode().split("\0")
        read = lambda name: subprocess.check_output(["git", "show", f"{tree}:{name}"], cwd=ROOT, text=True)
    else:
        names = ["README.md", "llms.txt"]
        for folder in ("clack", "tests", "benchmarks", "tools", "examples", "docs", "packages"):
            names.extend(str(path.relative_to(ROOT)) for path in (ROOT / folder).rglob("*")
                         if path.is_file() and "__pycache__" not in path.parts)
        read = lambda name: (ROOT / name).read_text(encoding="utf-8")
    groups, files = {}, []
    for name in sorted(set(names) - {""}):
        category = group(name)
        if category is None:
            continue
        lines = read(name).splitlines()
        comments = Path(name).suffix in {".py", ".clack"}
        row = {"path": name, "group": category, "physical": len(lines),
               "nonblank_noncomment": sum(bool(line.strip()) and not (comments and line.lstrip().startswith("#")) for line in lines)}
        files.append(row)
        total = groups.setdefault(category, {"physical": 0, "nonblank_noncomment": 0})
        for metric in total:
            total[metric] += row[metric]
    implementation = {metric: sum(groups.get(category, {}).get(metric, 0) for category in ("compiler", "standard_library"))
                      for metric in ("physical", "nonblank_noncomment")}
    return {"ref": ref or "working tree", "implementation": implementation, "groups": groups, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="count a committed revision instead of the working tree")
    parser.add_argument("--compare", help="compare this revision with the selected tree")
    parser.add_argument("--json", action="store_true", help="emit exact counts and per-file data")
    args = parser.parse_args()
    after = count(args.ref)
    before = count(args.compare) if args.compare else None
    result = {"before": before, "after": after} if before else after
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print("Physical lines; blank/comment-only lines excluded in the second count. Docstrings count as source.")
    print("Implementation = compiler + bundled .clack library. Other categories are separate.")
    for category, row in {"implementation": after["implementation"], **after["groups"]}.items():
        previous = before["implementation"] if before and category == "implementation" else before["groups"].get(category, {}) if before else {}
        change = f" (before {previous.get('physical', 0):,}; delta {row['physical'] - previous.get('physical', 0):+,})" if before else ""
        print(f"{category:20s} {row['physical']:7,d} / {row['nonblank_noncomment']:7,d}{change}")


if __name__ == "__main__":
    main()
