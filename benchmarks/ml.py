#!/usr/bin/env python3
"""Measure one native integer linear-model kernel against equivalent C."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shlex
import sys
import tempfile

from suite import FLAGS, checked_run, positive, source_fingerprint, summary


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/ml/ml.clack"


def sources(rounds):
    clack = f'''from ml import Linear4, score4
fn main():
    model = Linear4([2, -3, 1, 4], -5)
    checksum = 0
    for i in range({rounds}):
        invariant 0 <= checksum <= 30 * i
        x = i % 31
        checksum = checksum + score4(model, [x, 1, -x, 2])
    print(checksum)
'''
    native = f'''#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
typedef struct {{ int64_t weights[4], bias; }} Linear4;
static int64_t score4(Linear4 model, const int64_t features[4]) {{
    return model.weights[0]*features[0] + model.weights[1]*features[1]
         + model.weights[2]*features[2] + model.weights[3]*features[3] + model.bias;
}}
int main(void) {{
    Linear4 model = {{{{2, -3, 1, 4}}, -5}};
    int64_t checksum = 0;
    for (int64_t i = 0; i < {rounds}; ++i) {{
        int64_t x = i % 31;
        int64_t features[4] = {{x, 1, -x, 2}};
        checksum += score4(model, features);
    }}
    printf("%" PRId64 "\\n", checksum);
    return 0;
}}
'''
    return clack, native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=positive, default=50000000)
    parser.add_argument("--repeats", type=positive, default=9)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rounds > 1000000000:
        parser.error("rounds must be at most 1000000000")
    command = shlex.split(args.cc)
    if not command:
        parser.error("--cc cannot be empty")
    sys.path.insert(0, str(ROOT))
    import clack
    if not Path(clack.__file__).resolve().is_relative_to(ROOT):
        raise RuntimeError("compiler checkout was shadowed by another Clack installation")
    from clack.codegen import emit_c
    from clack.modules import load_program
    from clack.verifier import verify
    digest = lambda data: hashlib.sha256(data).hexdigest()
    fingerprints = {"compiler": source_fingerprint(ROOT), "package": digest(PACKAGE.read_bytes())}
    clack_source, c_source = sources(args.rounds)
    quotient, remainder = divmod(args.rounds, 31)
    expected = f"{quotient * 465 + remainder * (remainder - 1) // 2}\n"
    _, compiler_version = checked_run([*command, "--version"])
    samples = {label: [] for label in ("clack", "c")}
    with tempfile.TemporaryDirectory(prefix="clack-ml-benchmark-") as directory:
        folder = Path(directory)
        (folder / "ml.clack").symlink_to(PACKAGE)
        source = folder / "main.clack"
        source.write_text(clack_source, encoding="utf-8")
        program = load_program(source)
        checked = verify(program)
        generated = emit_c(program, checked.local_types, checked.expr_types)
        binaries = {label: folder / label for label in samples}
        for label, content in (("clack", generated), ("c", c_source)):
            path = folder / f"{label}.c"
            path.write_text(content, encoding="utf-8")
            checked_run([*command, *FLAGS, str(path), "-o", str(binaries[label])])
            checked_run([str(binaries[label])], expected)
        order, rng = list(samples), random.Random(43)
        for _ in range(args.repeats):
            rng.shuffle(order)
            for label in order:
                samples[label].append(checked_run([str(binaries[label])], expected)[0])
    if fingerprints != {"compiler": source_fingerprint(ROOT), "package": digest(PACKAGE.read_bytes())}:
        raise RuntimeError("compiler or ML source changed during measurement")
    results = {label: summary(values) for label, values in samples.items()}
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": sys.version.split()[0], "c_compiler": compiler_version.stdout.splitlines()[0], "flags": FLAGS,
              "rounds": args.rounds, "repeats": args.repeats, "seed": 43, "expected_stdout": expected,
              "compiler_source_sha256": fingerprints["compiler"], "package_source_sha256": fingerprints["package"],
              "benchmark_sha256": digest(Path(__file__).read_bytes()), "harness_sha256": digest((ROOT / "benchmarks/suite.py").read_bytes()),
              "clack_source_sha256": digest(clack_source.encode()),
              "c_source_sha256": digest(c_source.encode()), "generated_c_sha256": digest(generated.encode()),
              "obligations": len(checked.obligations), "all_outputs_match_reference": True,
              "timing_scope": "Native process wall time including startup, output, and exit; verification and compilation excluded.",
              "results": results, "clack_over_c_time": results["clack"]["median_seconds"] / results["c"]["median_seconds"],
              "limits": ["One four-feature integer linear score with constant weights and bounded inputs.",
                         "Both compilers may inline and simplify the equivalent score expressions; no artificial barriers.",
                         "Does not measure training throughput, floating-point ML, neural networks, GPU work, or general performance."]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print({label: round(value["median_seconds"] * 1000, 2) for label, value in results.items()})


if __name__ == "__main__":
    main()
