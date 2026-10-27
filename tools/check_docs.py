#!/usr/bin/env python3
"""Check local documentation links and execute the documented tutorial files.

Run with the project's Python environment. Only explicit clack:file snippets
and manifest programs are executable documentation; unlabeled fragments are
not assumed to be complete files. No Markdown content is evaluated as Python.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SNIPPET = re.compile(r"<!--\s*clack:file=([^\s>]+)\s*-->\s*```clack\s*\n(.*?)\n```", re.DOTALL)
FENCES = re.compile(r"^```[^\n]*\n.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


def markdown_files() -> list[Path]:
    return [ROOT / "README.md", ROOT / "llms.txt", *sorted((ROOT / "docs").rglob("*.md")),
            *sorted((ROOT / "benchmarks").rglob("*.md")), *sorted((ROOT / "packages").rglob("*.md"))]


def anchors(source: str) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in FENCES.sub("", source).splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        text = re.sub(r"<[^>]+>", "", match[1]).lower()
        text = re.sub(r"[^\w\- ]", "", text)
        slug = re.sub(r"\s", "-", text)
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        found.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return found


def check_links_and_snippets() -> tuple[list[str], int, int]:
    errors: list[str] = []
    link_count = 0
    snippet_count = 0
    for path in markdown_files():
        source = path.read_text(encoding="utf-8")
        label = path.relative_to(ROOT)
        for match in LINK.finditer(FENCES.sub("", source)):
            target = match[1].strip().split(' "', 1)[0].strip("<>")
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            destination = (path.parent / unquote(url.path)).resolve() if url.path else path
            link_count += 1
            if not destination.exists():
                errors.append(f"{label}: missing link target {target}")
            elif url.fragment and destination.suffix == ".md":
                if unquote(url.fragment) not in anchors(destination.read_text(encoding="utf-8")):
                    errors.append(f"{label}: missing heading in {target}")
        marker_count = len(re.findall(r"<!--\s*clack:file=", source))
        snippets = list(SNIPPET.finditer(source))
        if marker_count != len(snippets):
            errors.append(f"{label}: each clack:file marker must be followed by a clack code fence")
        for match in snippets:
            snippet_count += 1
            file = (path.parent / match[1]).resolve()
            if not file.is_file():
                errors.append(f"{label}: missing snippet file {match[1]}")
            elif match[2].strip() != file.read_text(encoding="utf-8").strip():
                errors.append(f"{label}: excerpt differs from {match[1]}")
    return errors, link_count, snippet_count


def run_tutorials(timeout_seconds: int) -> tuple[list[str], int]:
    errors: list[str] = []
    manifest_path = ROOT / "examples/tutorials/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    programs = manifest["programs"]
    for entry in programs:
        path = entry["path"]
        source = ROOT / path
        if not source.is_file():
            errors.append(f"missing tutorial program {path}")
            continue
        if ("stdout" in entry) == ("error" in entry):
            errors.append(f"{path}: manifest needs exactly one of stdout or error")
            continue
        action = "check" if "error" in entry else "run"
        try:
            result = subprocess.run([sys.executable, "-m", "clack", action, str(source)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            errors.append(f"{path}: timed out after {timeout_seconds} seconds")
            continue
        if "error" in entry:
            if result.returncode != 1 or entry["error"] not in result.stderr:
                errors.append(f"{path}: expected diagnostic {entry['error']!r}, got exit {result.returncode}: {result.stderr.strip()}")
        elif result.returncode != 0 or result.stdout != entry["stdout"]:
            errors.append(f"{path}: expected output {entry['stdout']!r}, got exit {result.returncode}, output {result.stdout!r}: {result.stderr.strip()}")
    return errors, len(programs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-run", action="store_true", help="check links and excerpts without running programs")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="timeout per tutorial program (default: 30)")
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    errors, links, snippets = check_links_and_snippets()
    try:
        from clack import __version__
        reference = json.loads((ROOT / "docs/agent-reference.json").read_text(encoding="utf-8"))
        if reference["language_version"] != __version__:
            errors.append("agent reference version differs from compiler version")
        for name, target in reference["entrypoints"].items():
            if not (ROOT / target).is_file():
                errors.append(f"agent reference: missing {name} target {target}")
    except (OSError, ValueError, KeyError) as error:
        errors.append(f"agent reference: {error}")
    programs = 0
    if not args.skip_run:
        try:
            run_errors, programs = run_tutorials(args.timeout_seconds)
            errors.extend(run_errors)
        except (OSError, ValueError, KeyError) as error:
            errors.append(f"tutorial manifest: {error}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Documentation checked: {len(markdown_files())} pages, {links} local links, {snippets} synchronized excerpts, {programs} tutorial programs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
