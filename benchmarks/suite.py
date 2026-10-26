#!/usr/bin/env python3
"""Compare verified Clack/C kernels and separately time the compiler pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FLAGS = ["-std=c11", "-O3", "-Wall", "-Wextra", "-pthread"]
MODULUS = 2147483647


def positive(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def summary(samples: list[float]) -> dict:
    return {"median_seconds": statistics.median(samples), "samples_seconds": samples,
            "min_seconds": min(samples), "max_seconds": max(samples)}


def lcg_cases(scale: int) -> list[dict]:
    iterations = 5_000_000 * scale
    clack = """fn kernel(seed: int, steps: int) -> int:
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
    native = """#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <pthread.h>
#include <stdlib.h>
static int64_t kernel(int64_t seed, int64_t steps) {
    int64_t x = seed;
    for (int64_t i = 0; i < steps; i++) x = (x * INT64_C(48271)) % INT64_C(2147483647);
    return x;
}
typedef struct { int64_t seed, steps, result; } Job;
static void *worker(void *opaque) {
    Job *job = opaque; job->result = kernel(job->seed, job->steps); return NULL;
}
"""
    cases = []
    for mode, count in [("single", 1), ("sequential2", 2), ("sequential4", 4), ("parallel2", 2), ("parallel4", 4)]:
        seeds = [1, 7, 11, 17][:count]
        parallel = mode.startswith("parallel")
        body = "fn main():\n" + ("    parallel:\n" if parallel else "")
        body += "".join(f"{'        ' if parallel else '    '}answer{i} = kernel({seed}, {iterations})\n" for i, seed in enumerate(seeds))
        body += "".join(f"    print(answer{i})\n" for i in range(count))
        c_body = "int main(void) {\n"
        if parallel:
            c_body += "".join(f"    Job job{i} = {{INT64_C({seed}), INT64_C({iterations}), 0}}; pthread_t thread{i};\n" for i, seed in enumerate(seeds))
            c_body += "".join(f"    int started{i} = pthread_create(&thread{i}, NULL, worker, &job{i}) == 0; if (!started{i}) worker(&job{i});\n" for i in range(count))
            c_body += "".join(f"    if (started{i} && pthread_join(thread{i}, NULL) != 0) abort();\n" for i in range(count))
            c_body += "".join(f'    printf("%" PRId64 "\\n", job{i}.result);\n' for i in range(count))
        else:
            c_body += "".join(f"    int64_t answer{i} = kernel(INT64_C({seed}), INT64_C({iterations}));\n" for i, seed in enumerate(seeds))
            c_body += "".join(f'    printf("%" PRId64 "\\n", answer{i});\n' for i in range(count))
        c_body += "    return 0;\n}\n"
        factor = pow(48271, iterations, MODULUS)
        cases.append({"name": "lcg_" + mode, "label": "LCG " + mode,
                      "clack": clack + body, "c": native + c_body,
                      "expected": "".join(f"{seed * factor % MODULUS}\n" for seed in seeds),
                      "work_units": iterations * count, "jobs": count})
    return cases


def checked_run(command: list[str], expected: str | None = None, *, cwd: Path | None = None,
                env: dict | None = None) -> tuple[float, subprocess.CompletedProcess]:
    start = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(f"command failed: {command[0]}\n{result.stderr}")
    if expected is not None and result.stdout != expected:
        raise RuntimeError(f"wrong output for {command[0]}: expected {expected!r}, got {result.stdout!r}")
    return elapsed, result


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted((root / "clack").rglob("*")):
        if file.is_file() and file.suffix in {".py", ".clack"}:
            digest.update(str(file.relative_to(root)).encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-root", type=Path, default=ROOT, help="compiler source tree to measure (supports immutable baseline snapshots)")
    parser.add_argument("--label", default="current")
    parser.add_argument("--scale", type=positive, default=1, help="kernel work multiplier, 1-20")
    parser.add_argument("--repeats", type=positive, default=5)
    parser.add_argument("--compile-repeats", type=positive, default=3)
    parser.add_argument("--only", help="comma-separated native case names, useful for development")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.scale > 20:
        parser.error("--scale must be at most 20")
    compiler_root = args.compiler_root.resolve()
    if not (compiler_root / "clack/verifier.py").is_file():
        parser.error("--compiler-root must contain the Clack compiler sources")
    sys.path.insert(0, str(compiler_root))
    import clack
    if not Path(clack.__file__).resolve().is_relative_to(compiler_root):
        raise RuntimeError("selected compiler root was shadowed by another Clack installation")
    from clack.codegen import emit_c
    from clack.modules import load_program
    from clack.verifier import verify
    from kernels import cases as other_cases

    command = shlex.split(args.cc)
    if not command:
        parser.error("--cc cannot be empty")
    _, version = checked_run([*command, "--version"])
    cases = lcg_cases(args.scale) + other_cases(args.scale)
    if args.only:
        selected = set(args.only.split(","))
        cases = [case for case in cases if case["name"] in selected]
        if {case["name"] for case in cases} != selected:
            parser.error("unknown --only case")
    pipeline = {}
    native_compile = {}
    samples = {case["name"]: {"clack": [], "c": []} for case in cases}
    cold = {}
    branch8 = (
        "fn count_flags(" + ", ".join(f"flag{i}: bool" for i in range(8)) + ") -> int:\n"
        "    ensures 0 <= result <= 8\n    count = 0\n"
        + "".join(f"    if flag{i}:\n        count = count + 1\n" for i in range(8))
        + "    return count\n\nfn main():\n    print(count_flags(true, false, true, false, true, false, true, false))\n"
    )
    fixtures = {
        "hello": "fn main():\n    print(42)\n",
        "stdlib": "from std.math import min, max, abs, clamp\nfrom std.array import sum4\nfn main():\n    print(clamp(sum4([1, 2, 3, 4]), 0, 100))\n",
        "arithmetic128": "fn main():\n    value = 0\n" + "    value = value + 1\n" * 128 + "    print(value)\n",
        "branch8": branch8,
    }
    nested = "7"
    for depth in range(17):
        nested = f"Layer{depth}({nested})"
    fixtures["constructors16"] = "".join(
        f"type Layer{depth}:\n    value: {'int' if depth == 0 else 'Layer' + str(depth - 1)}\n\n"
        for depth in range(17)
    ) + f"fn main():\n    value = {nested}\n    print(value{'.value' * 17})\n"
    with tempfile.TemporaryDirectory(prefix="clack-suite-") as directory:
        folder = Path(directory)

        def measure(source_file: Path) -> tuple[str, dict]:
            timings = {}
            started = time.perf_counter()
            program = load_program(source_file)
            timings["load_parse_link"] = time.perf_counter() - started
            started = time.perf_counter()
            verified = verify(program)
            timings["types_and_proofs"] = time.perf_counter() - started
            started = time.perf_counter()
            generated = emit_c(program, verified.local_types, verified.expr_types)
            timings["emit_c"] = time.perf_counter() - started
            timings["total"] = sum(timings.values())
            timings["obligations"] = len(verified.obligations)
            timings["solver_checks"] = getattr(verified, "solver_checks", None)
            return generated, timings

        sources = {case["name"]: case["clack"] for case in cases} | fixtures
        generated = {}
        for name, source in sources.items():
            source_file = folder / (name + ".clack")
            source_file.write_text(source, encoding="utf-8")
            measurements = []
            for _ in range(args.compile_repeats):
                generated[name], timing = measure(source_file)
                measurements.append(timing)
            pipeline[name] = {stage: summary([sample[stage] for sample in measurements])
                              for stage in ["load_parse_link", "types_and_proofs", "emit_c", "total"]}
            pipeline[name]["obligations"] = measurements[-1]["obligations"]
            pipeline[name]["solver_checks"] = measurements[-1]["solver_checks"]
            print(f"Verified {name}: {pipeline[name]['total']['median_seconds'] * 1000:.2f} ms", flush=True)
        for case in cases:
            name = case["name"]
            native_compile[name] = {}
            for language, source in [("clack", generated[name]), ("c", case["c"])]:
                source_file = folder / f"{name}_{language}.c"
                binary = folder / f"{name}_{language}"
                source_file.write_text(source, encoding="utf-8")
                compile_samples = [checked_run([*command, *FLAGS, str(source_file), "-o", str(binary)])[0]
                                   for _ in range(args.compile_repeats)]
                native_compile[name][language] = summary(compile_samples)
                checked_run([str(binary)], case["expected"])
        rng = random.Random(0)
        order = [(case, language) for case in cases for language in ("clack", "c")]
        for _ in range(args.repeats):
            rng.shuffle(order)
            for case, language in order:
                binary = folder / f"{case['name']}_{language}"
                samples[case["name"]][language].append(checked_run([str(binary)], case["expected"])[0])
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(compiler_root)
        for name in fixtures:
            cold_samples = [checked_run([sys.executable, "-m", "clack", "check", str(folder / (name + ".clack"))],
                                        cwd=compiler_root, env=environment)[0] for _ in range(args.compile_repeats)]
            cold[name] = summary(cold_samples)

    results = {}
    for case in cases:
        name = case["name"]
        row = {language: summary(samples[name][language]) for language in ("clack", "c")}
        row.update({"label": case["label"], "work_units": case["work_units"], "expected_stdout": case["expected"],
                    "clack_over_c_ratio": row["clack"]["median_seconds"] / row["c"]["median_seconds"],
                    "source_sha256": {language: hashlib.sha256(case[language].encode()).hexdigest() for language in ("clack", "c")}})
        results[name] = row
        print(f"{case['label']:25s} Clack {row['clack']['median_seconds'] * 1000:8.3f} ms  C {row['c']['median_seconds'] * 1000:8.3f} ms  ratio {row['clack_over_c_ratio']:.3f}")
    scaling = {}
    for jobs in (2, 4):
        sequential, parallel = f"lcg_sequential{jobs}", f"lcg_parallel{jobs}"
        if sequential in results and parallel in results:
            scaling[str(jobs)] = {language: results[sequential][language]["median_seconds"] / results[parallel][language]["median_seconds"] for language in ("clack", "c")}
    report = {"label": args.label, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "compiler_root": str(compiler_root), "compiler_source_sha256": source_fingerprint(compiler_root),
              "suite_sha256": hashlib.sha256(Path(__file__).read_bytes() + (HERE / "kernels.py").read_bytes()).hexdigest(),
              "platform": platform.platform(), "machine": platform.machine(), "logical_cpus_reported": os.cpu_count(),
              "python": sys.version, "c_compiler": version.stdout.splitlines()[0], "flags": FLAGS,
              "scale": args.scale, "repeats": args.repeats, "compile_repeats": args.compile_repeats,
              "all_outputs_match_reference": True, "runtime": results, "parallel_speedup": scaling,
              "in_process_compiler_pipeline": pipeline, "native_c_compilation": native_compile, "cold_cli_check": cold,
              "timing_scope": {"runtime": "native subprocess wall time including process startup, output, thread setup/join, and exit; no compilation or verification",
                               "in_process_compiler_pipeline": "repeated full source load, parse/link, type/proof checks, and C emission in an already imported Python process; no native compilation",
                               "cold_cli_check": "fresh Python process plus package imports, source loading, type checking, verification, and CLI output; no native compilation"},
              "limits": ["These are selected kernels, not general C/Rust parity evidence.",
                         "Short native runs include process startup; OS scheduling and CPU allocation affect scaling.",
                         "Verifier annotations are erased; hand C runs matching algorithms with the same optimization flags."]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        raise SystemExit(1)
