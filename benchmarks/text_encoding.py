#!/usr/bin/env python3
"""Compare actual compiler revisions on byte-exact Unicode text fixtures."""

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
DRIVER = """import hashlib, json, pathlib, sys, time
root, source, destination = map(pathlib.Path, sys.argv[1:4])
sys.path.insert(0, str(root))
import clack, z3
assert pathlib.Path(clack.__file__).resolve().is_relative_to(root)
from clack.modules import load_program
from clack.verifier import verify
from clack.codegen import emit_c
def compile(proofs=None):
    start = time.perf_counter()
    program = load_program(source)
    loaded = time.perf_counter()
    checked = verify(program, proof_dir=proofs)
    verified = time.perf_counter()
    generated = emit_c(program, checked.local_types, checked.expr_types)
    emitted = time.perf_counter()
    return generated, checked, dict(load=loaded-start, verify=verified-loaded,
                                   emit=emitted-verified, total=emitted-start)
proofs = destination.with_suffix('.proofs') if sys.argv[4] == 'proofs' else None
_, warm, _ = compile(proofs)
queries = []
if proofs:
    for obligation in warm.obligations:
        query = proofs / obligation['query']
        solver = z3.Solver()
        solver.from_file(str(query))
        assert solver.check() == z3.unsat
        queries.append(hashlib.sha256(query.read_bytes()).hexdigest())
generated, checked, timing = compile()
destination.write_text(generated)
print(json.dumps(dict(version=clack.__version__, timing=timing,
    obligations=len(checked.obligations), c_sha256=hashlib.sha256(generated.encode()).hexdigest(),
    replayed_query_sha256=queries)))
"""


def fixture(size):
    unit = "Clack\\u{30000} é😀𰀀"
    value = unit * (size // len(unit.encode("utf-8")))
    value += "x" * (size - len(value.encode("utf-8")))
    literal = json.dumps(value, ensure_ascii=False)
    source = f'''fn echo(value: text) -> text:
    return value
fn main():
    assert len({literal}) == {size}
    print(echo({literal}))
'''
    return source, value + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=ROOT)
    parser.add_argument("--warm-repeats", type=int, default=7)
    parser.add_argument("--cold-repeats", type=int, default=9)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.warm_repeats, args.cold_repeats) < 1:
        parser.error("repeat counts must be positive")
    roots = {"before": args.before.resolve(), "after": args.after.resolve()}
    for root in roots.values():
        if not (root / "clack/verifier.py").is_file():
            parser.error(f"not a Clack source tree: {root}")
    fingerprints = {label: source_fingerprint(root) for label, root in roots.items()}
    command = shlex.split(args.cc)
    if not command:
        parser.error("--cc cannot be empty")
    _, compiler = checked_run([*command, "--version"])
    samples = {str(size): {label: {phase: [] for phase in ("load", "verify", "emit", "total", "cold")}
                          for label in roots} for size in (1024, 16384)}
    metadata, sources = {}, {}
    rng = random.Random(619)
    with tempfile.TemporaryDirectory(prefix="clack-text-encoding-") as folder:
        folder = Path(folder)
        for size in samples:
            source, expected = fixture(int(size))
            sources[size] = folder / (size + ".clack")
            sources[size].write_text(source, encoding="utf-8")
            metadata[size] = {"utf8_bytes": int(size), "source_sha256": hashlib.sha256(source.encode()).hexdigest()}
        order = [(size, label) for size in samples for label in roots]
        def run_driver(size, label, mode):
            destination = folder / (size + "_" + label + ".c")
            _, process = checked_run([sys.executable, "-c", DRIVER, str(roots[label]), str(sources[size]),
                                      str(destination), mode], cwd=roots[label])
            return destination, json.loads(process.stdout)

        for size, label in order:
            destination, result = run_driver(size, label, "proofs")
            metadata[size][label] = {key: value for key, value in result.items() if key != "timing"}
            binary = destination.with_suffix("")
            checked_run([*command, *FLAGS, str(destination), "-o", str(binary)])
            checked_run([str(binary)], fixture(int(size))[1])
        for _ in range(args.warm_repeats):
            rng.shuffle(order)
            for size, label in order:
                _, result = run_driver(size, label, "warm")
                assert result["c_sha256"] == metadata[size][label]["c_sha256"]
                assert result["obligations"] == metadata[size][label]["obligations"]
                for phase, value in result["timing"].items():
                    samples[size][label][phase].append(value)
        for size, row in metadata.items():
            for key in ("obligations", "c_sha256", "replayed_query_sha256"):
                assert row["before"][key] == row["after"][key], (size, key)
        for _ in range(args.cold_repeats):
            rng.shuffle(order)
            for size, label in order:
                env = dict(os.environ, PYTHONPATH=str(roots[label]))
                elapsed, _ = checked_run([sys.executable, "-m", "clack", "check", str(sources[size])], cwd=roots[label], env=env)
                samples[size][label]["cold"].append(elapsed)
    if fingerprints != {label: source_fingerprint(root) for label, root in roots.items()}:
        raise RuntimeError("compiler source changed during measurement")
    report = {"compiler_source_sha256": fingerprints, "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "seed": 619, "warm_repeats": args.warm_repeats, "cold_repeats": args.cold_repeats,
              "c_compiler": compiler.stdout.splitlines()[0], "flags": FLAGS, "fixtures": metadata,
              "scope": "Shuffled paired actual revisions; warm phases exclude imports and native compilation; cold includes fresh CLI startup. Native outputs and fresh SMT replays checked before timing; no native speedup claim.",
              "results": {size: {label: {phase: summary(values) for phase, values in phases.items()}
                                  for label, phases in labels.items()} for size, labels in samples.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for size, labels in report["results"].items():
        print(size, {label: {phase: round(data["median_seconds"] * 1000, 3) for phase, data in phases.items()}
                     for label, phases in labels.items()})


if __name__ == "__main__":
    main()
