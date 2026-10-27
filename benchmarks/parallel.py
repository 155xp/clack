#!/usr/bin/env python3
"""Compare repeated small parallel blocks between two actual compiler trees."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import sys
import tempfile

from suite import FLAGS, checked_run, source_fingerprint, summary


ROOT = Path(__file__).resolve().parents[1]
EMIT = """import pathlib, sys
sys.path.insert(0, sys.argv[1])
from clack.codegen import emit_c
from clack.modules import load_program
from clack.verifier import verify
for source in pathlib.Path(sys.argv[2]).glob('*.clack'):
    program = load_program(source)
    checked = verify(program)
    source.with_suffix('.c').write_text(emit_c(program, checked.local_types, checked.expr_types))
"""


def source(jobs: int, blocks: int) -> str:
    bindings = "".join(f"            answer{i} = work(i)\n" for i in range(jobs))
    total = " + ".join(f"answer{i}" for i in range(jobs))
    return f"""fn work(x: int) -> int:
    requires 0 <= x <= {blocks}
    ensures 0 <= result <= {blocks}
    return x

fn main():
    i = 0
    total = 0
    while i < {blocks}:
        invariant 0 <= i <= {blocks}
        invariant 0 <= total <= {4 * blocks}
        decreases {blocks} - i
        parallel:
{bindings}        total = {total}
        i = i + 1
    print(total)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=ROOT)
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--blocks", type=int, default=2000)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or not 1 <= args.blocks <= 1000000:
        parser.error("repeats must be positive; blocks must be between 1 and 1000000")
    roots = {"before": args.before.resolve(), "after": args.after.resolve()}
    for root in roots.values():
        if not (root / "clack/codegen.py").is_file():
            parser.error(f"not a Clack compiler source tree: {root}")
    fingerprints = {label: source_fingerprint(root) for label, root in roots.items()}
    command = shlex.split(args.cc)
    if not command:
        parser.error("--cc cannot be empty")
    _, version = checked_run([*command, "--version"])
    samples = {str(jobs): {label: [] for label in roots} for jobs in (1, 2, 4)}
    with tempfile.TemporaryDirectory(prefix="clack-small-parallel-") as directory:
        folder = Path(directory)
        for label, root in roots.items():
            destination = folder / label
            destination.mkdir()
            for jobs in (1, 2, 4):
                (destination / f"jobs{jobs}.clack").write_text(source(jobs, args.blocks))
            checked_run([sys.executable, "-c", EMIT, str(root), str(destination)], cwd=root)
            for jobs in (1, 2, 4):
                binary = destination / f"jobs{jobs}"
                checked_run([*command, *FLAGS, str(binary.with_suffix(".c")), "-o", str(binary)])
                checked_run([str(binary)], f"{jobs * (args.blocks - 1)}\n")
        order = [(jobs, label) for jobs in (1, 2, 4) for label in roots]
        rng = random.Random(9)
        for _ in range(args.repeats):
            rng.shuffle(order)
            for jobs, label in order:
                elapsed, _ = checked_run([str(folder / label / f"jobs{jobs}")], f"{jobs * (args.blocks - 1)}\n")
                samples[str(jobs)][label].append(elapsed)
    if fingerprints != {label: source_fingerprint(root) for label, root in roots.items()}:
        raise RuntimeError("compiler source changed during measurement; repeat with stable trees")
    results = {jobs: {label: summary(values) for label, values in labels.items()}
               for jobs, labels in samples.items()}
    report = {"scope": "Native process wall time for repeated tiny parallel blocks, including startup, output, thread creation/join, and exit; no verification or compilation.",
              "compiler_source_sha256": fingerprints, "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "c_compiler": version.stdout.splitlines()[0], "flags": FLAGS, "blocks": args.blocks,
              "repeats": args.repeats, "seed": 9, "all_outputs_match_reference": True, "results": results,
              "limits": ["Identity workers intentionally isolate scheduling overhead, not useful throughput.",
                         "With one job, eliminating thread creation also permits the C optimizer to fold the loop.",
                         "A thread pool is not used; small jobs may still be slower than sequential calls."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for jobs, labels in results.items():
        print(jobs, {label: round(value["median_seconds"] * 1000, 2) for label, value in labels.items()})


if __name__ == "__main__":
    main()
