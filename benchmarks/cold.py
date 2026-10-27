#!/usr/bin/env python3
"""Interleave two compiler revisions to measure fresh-process CLI latency."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

from suite import source_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    roots = {"before": args.before.resolve(), "after": args.after.resolve()}
    for root in roots.values():
        if not (root / "clack/cli.py").is_file():
            parser.error(f"not a Clack source tree: {root}")
    fingerprints = {label: source_fingerprint(root) for label, root in roots.items()}
    fixtures = {
        "hello": "fn main():\n    print(42)\n",
        "stdlib": "from std.math import clamp\nfrom std.array import sum4\nfn main():\n    print(clamp(sum4([1,2,3,4]),0,100))\n",
    }
    samples = {name: {label: [] for label in roots} for name in fixtures}
    order = [(name, label) for name in fixtures for label in roots]
    rng = random.Random(2026)
    with tempfile.TemporaryDirectory(prefix="clack-paired-cold-") as directory:
        paths = {name: Path(directory) / (name + ".clack") for name in fixtures}
        for name, source in fixtures.items():
            paths[name].write_text(source)
        for _ in range(args.repeats):
            rng.shuffle(order)
            for name, label in order:
                env = dict(os.environ, PYTHONPATH=str(roots[label]))
                start = time.perf_counter()
                result = subprocess.run([sys.executable, "-m", "clack", "check", str(paths[name])],
                                        cwd=roots[label], env=env, capture_output=True, text=True, timeout=120)
                elapsed = time.perf_counter() - start
                if result.returncode:
                    raise RuntimeError(result.stderr)
                samples[name][label].append(elapsed)
    if fingerprints != {label: source_fingerprint(root) for label, root in roots.items()}:
        raise RuntimeError("compiler source changed during measurement; repeat with stable trees")
    report = {"scope": "Interleaved fresh-process CLI checks; includes Python/Z3 startup; no C emission or native compilation.",
              "compiler_source_sha256": fingerprints, "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "seed": 2026, "repeats": args.repeats,
              "results": {name: {label: {"median_seconds": statistics.median(values), "samples_seconds": values}
                                 for label, values in labels.items()} for name, labels in samples.items()}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    for name, labels in report["results"].items():
        print(name, {label: round(value["median_seconds"] * 1000, 2) for label, value in labels.items()})


if __name__ == "__main__":
    main()
