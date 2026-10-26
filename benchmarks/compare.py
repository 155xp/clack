#!/usr/bin/env python3
"""Verify/build once, then compare native Clack and C process runtimes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import shlex
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clack.codegen import emit_c
from clack.frontend import CompileError, parse
from clack.verifier import verify


MODULUS = 2_147_483_647
MULTIPLIER = 48_271
MAX_ITERATIONS = 100_000_000
FLAGS = ["-std=c11", "-O3", "-Wall", "-Wextra", "-pthread"]

CLACK_KERNEL = """fn kernel(seed: int, steps: int) -> int:
    requires 0 < seed < 2147483647
    requires 0 <= steps <= 100000000
    ensures 0 <= result < 2147483647
    x = seed
    i = 0
    while i < steps:
        invariant 0 <= i <= steps
        invariant 0 <= x < 2147483647
        decreases steps - i
        x = (x * 48271) % 2147483647
        i = i + 1
    return x

"""

C_KERNEL = """#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>

static int64_t kernel(int64_t seed, int64_t steps) {
    int64_t x = seed;
    int64_t i = 0;
    while (i < steps) {
        x = (x * INT64_C(48271)) % INT64_C(2147483647);
        i = i + INT64_C(1);
    }
    return x;
}

"""


def clack_source(iterations: int, mode: str) -> str:
    if mode == "single":
        body = f"    print(kernel(1, {iterations}))\n"
    elif mode == "sequential":
        body = (
            f"    a = kernel(1, {iterations})\n"
            f"    b = kernel(7, {iterations})\n"
            "    print(a)\n    print(b)\n"
        )
    elif mode == "parallel":
        body = (
            "    parallel:\n"
            f"        a = kernel(1, {iterations})\n"
            f"        b = kernel(7, {iterations})\n"
            "    print(a)\n    print(b)\n"
        )
    else:
        raise ValueError(mode)
    return CLACK_KERNEL + "fn main():\n" + body


def c_source(iterations: int, two_kernels: bool) -> str:
    body = (
        f"    int64_t a = kernel(INT64_C(1), INT64_C({iterations}));\n"
    )
    if two_kernels:
        body += f"    int64_t b = kernel(INT64_C(7), INT64_C({iterations}));\n"
    body += '    printf("%" PRId64 "\\n", a);\n'
    if two_kernels:
        body += '    printf("%" PRId64 "\\n", b);\n'
    return C_KERNEL + "int main(void) {\n" + body + "    return 0;\n}\n"


def run(binary: Path, expected: str) -> float:
    started = time.perf_counter()
    result = subprocess.run([str(binary)], text=True, capture_output=True, check=True)
    elapsed = time.perf_counter() - started
    if result.stdout != expected:
        raise RuntimeError(
            f"{binary.name} gave an incorrect result: "
            f"expected {expected!r}, got {result.stdout!r}"
        )
    return elapsed


def build(command: list[str], source: str, target: Path) -> None:
    path = target.with_suffix(".c")
    path.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [*command, *FLAGS, str(path), "-o", str(target)],
        text=True, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"building {target.name} failed:\n{result.stderr}")


def bounded_iterations(text: str) -> int:
    value = int(text)
    if not 0 <= value <= MAX_ITERATIONS:
        raise argparse.ArgumentTypeError(f"must be between 0 and {MAX_ITERATIONS}")
    return value


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=bounded_iterations, default=10_000_000)
    parser.add_argument("--repeats", type=positive, default=5)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path, help="also save metadata and raw samples as JSON")
    args = parser.parse_args()
    command = shlex.split(args.cc)
    if not command:
        parser.error("--cc must name a compiler")

    # Independent reference: the recurrence has the closed form seed*a**n mod m.
    factor = pow(MULTIPLIER, args.iterations, MODULUS)
    first = f"{factor}\n"
    both = first + f"{(7 * factor) % MODULUS}\n"
    cases = [
        ("c_single", "C, one kernel", 1, first),
        ("clack_single", "Clack, one kernel", 1, first),
        ("c_sequential", "C, two sequential kernels", 2, both),
        ("clack_sequential", "Clack, two sequential kernels", 2, both),
        ("clack_parallel", "Clack, two parallel kernels", 2, both),
    ]
    samples = {name: [] for name, _, _, _ in cases}
    obligations: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="clack-benchmark-") as directory:
        folder = Path(directory)
        for name, _, _, _ in cases:
            if name.startswith("c_"):
                source = c_source(args.iterations, name == "c_sequential")
            else:
                mode = name.removeprefix("clack_")
                original = clack_source(args.iterations, mode)
                (folder / f"{name}.clack").write_text(original, encoding="utf-8")
                program = parse(original)
                checked = verify(program)
                obligations[name] = len(checked.obligations)
                source = emit_c(program, checked.local_types, checked.expr_types)
            build(command, source, folder / name)

        # Check outputs and warm caches before collecting interleaved samples.
        for name, _, _, expected in cases:
            run(folder / name, expected)
        rng = random.Random(0)
        for _ in range(args.repeats):
            ordered = list(cases)
            rng.shuffle(ordered)
            for name, _, _, expected in ordered:
                samples[name].append(run(folder / name, expected))

    compiler = subprocess.run(
        [*command, "--version"], text=True, capture_output=True, check=True,
    ).stdout.splitlines()[0]
    results = {
        name: {
            "description": label,
            "kernels": kernels,
            "median_seconds": statistics.median(samples[name]),
            "samples_seconds": samples[name],
            "expected_stdout": expected,
        }
        for name, label, kernels, expected in cases
    }
    medians = {name: case["median_seconds"] for name, case in results.items()}
    ratios = {
        "single_clack_seconds_over_c_seconds": medians["clack_single"] / medians["c_single"],
        "sequential_clack_seconds_over_c_seconds": medians["clack_sequential"] / medians["c_sequential"],
        "clack_parallel_speedup_over_clack_sequential": medians["clack_sequential"] / medians["clack_parallel"],
    }
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpus_reported": os.cpu_count(),
        "compiler": compiler,
        "compiler_command": command,
        "flags": FLAGS,
        "iterations_per_kernel": args.iterations,
        "repeats": args.repeats,
        "verified_obligations": obligations,
        "timing_scope": "native process wall time including startup, pthread setup, output, and exit; excludes verification and compilation",
        "reference": "pow(48271, iterations, 2147483647) * seed % 2147483647",
        "all_outputs_match_reference": True,
        "results": results,
        "ratios": ratios,
    }
    print(f"{args.iterations:,} iterations per kernel; {args.repeats} samples; {compiler}")
    print("Verification and compilation excluded; native process startup and output included.\n")
    for name, label, _, _ in cases:
        print(f"{label:34s} {medians[name] * 1000:10.3f} ms median")
    print(f"\nClack/C single-kernel time ratio: {ratios['single_clack_seconds_over_c_seconds']:.3f}")
    print(f"Clack parallel speedup over Clack sequential: {ratios['clack_parallel_speedup_over_clack_sequential']:.3f}x")
    print("All outputs match an independent modular-exponentiation reference.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CompileError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        raise SystemExit(1)
