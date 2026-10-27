# Compiler and native workload suite

Run the suite from the repository root using the compiler's Python environment:

```sh
.venv/bin/python benchmarks/suite.py --repeats 5 --compile-repeats 3 --output build/suite.json
```

The suite checks eight native workloads against independent results and matching hand-written C programs. Clack and C use the same compiler and flags: `-std=c11 -O3 -Wall -Wextra -pthread`. Correct outputs are required before any timing report is written.

| Workload | What it exercises | Independent output reference |
| --- | --- | --- |
| LCG, one job | Integer multiplication and remainder dependency chain | Modular exponentiation |
| LCG, two sequential jobs | Two independent scalar kernels | Modular exponentiation |
| LCG, four sequential jobs | Four independent scalar kernels | Modular exponentiation |
| LCG, two parallel jobs | Two concurrent jobs, thread creation and join | Modular exponentiation |
| LCG, four parallel jobs | Four concurrent jobs, thread creation and join | Modular exponentiation |
| Variable-input Euclidean GCD | Nested variable-length remainder loops | Python `math.gcd` |
| Integer square root | Repeated binary search and branches | Python `math.isqrt` |
| Eight-state array update | Fixed-array reads, writes, and recurrence state | Logarithmic matrix exponentiation |

The source generators are in [suite.py](suite.py) and [kernels.py](kernels.py). The GCD and square-root contracts establish safety, termination, and result bounds; their full mathematical behavior is checked by independent runtime output comparisons. Do not confuse those output checks with formal functional proofs.

## Timing scopes

The JSON report separates three kinds of cost:

1. **Native runtime.** The programs are verified and compiled before timing starts. Samples include launching a native process, computing, printing its result, and exiting. Parallel samples also include thread creation and joining. One untimed run checks and warms each binary. Timed Clack and C runs are interleaved in a deterministic shuffled order.
2. **In-process compiler pipeline.** An already imported Python process repeatedly loads and parses source modules, checks types and proofs, and emits C. The report records those three stages and their total. This total excludes Python startup and native C compilation.
3. **Cold CLI checks.** Each sample starts a new Python process and runs `python -m clack check` on a fixture. This includes imports, parsing, verification, and CLI output. It excludes native C compilation and execution.

Native C compilation is measured separately for both generated and hand-written source. Every statistic includes its raw samples and median, minimum, and maximum. The report also records the compiler fingerprint, benchmark fingerprint, exact source hashes, compiler flags, Python version, and platform.

Cold and in-process fixture checks cover a minimal program, standard-library imports, two synthetic 128-assignment arithmetic workloads, and a synthetic eight-Boolean-branch function. The constant arithmetic fixture isolates trivial verification overhead. The symbolic arithmetic fixture repeatedly increments a bounded function parameter and proves its exact result; its safety checks require reasoning about an arbitrary input. The branch fixture counts enabled flags and checks its result bounds; eight independent conditions expose whether a verifier retains every path separately or safely joins continuation states. These synthetic programs should not stand in for application compile time.

A nested-record-constructor fixture checks whether C emission visits each child expression once. The source has 17 finite record layers, with no recursive types. It exposes repeated traversal costs without enlarging the native runtime workload or relying on a flaky wall-time assertion in the regression suite.

A 512-element integer-literal sum checks the cost of creating exact constant values, proving their range, and verifying every partial sum. Its asserted reference total is 1,533. An unused-code fixture contains 150 arithmetic helpers, a small used helper chain, and an unused parallel helper. All source bodies must still verify. The report records generated C bytes and separately measures C compilation for that fixture and the standard-library fixture, with native output checked after compilation. These measurements distinguish source verification from avoiding unnecessary backend work. The paired [cold-check script](cold.py) also includes the array fixture to show how import and process startup affect the change.

## Compare an immutable baseline

Use the same benchmark source and parameters for both compiler revisions. An explicit compiler root lets the benchmark import a snapshot without changing the active checkout:

```sh
mkdir -p /tmp/clack-before
git archive COMMIT_SHA | tar -x -C /tmp/clack-before
.venv/bin/python benchmarks/suite.py --compiler-root /tmp/clack-before --label before --output build/before-suite.json
.venv/bin/python benchmarks/suite.py --label after --output build/after-suite.json
```

Replace `COMMIT_SHA` with the revision you want to compare. The script verifies that it imported the selected compiler tree. A snapshot needs its compiler source, while the Python environment supplies the pinned solver dependency.

`--scale N` multiplies runtime work, with `1 <= N <= 20`. Default work is designed to last tens of milliseconds on the recorded machine, so process startup remains visible but does not normally dominate. Use larger work on faster machines, and keep it identical across comparisons. `--only gcd,array`, for example, selects particular native cases during development; compiler fixtures still run.

## Small parallel jobs

[parallel.py](parallel.py) compares actual native output from two compiler trees on repeated small parallel blocks:

```sh
.venv/bin/python benchmarks/parallel.py --before /tmp/clack-before --repeats 11 --output build/parallel.json
```

The default workload executes 2,000 blocks containing one, two, or four identity workers. Both revisions verify the same source and compile it with identical flags. Output must match before timing begins, and timed samples are interleaved in a seeded shuffled order. The JSON includes every sample and checks that neither compiler tree changed during measurement.

This isolates thread overhead. Clack 0.3 lets the caller execute the last job while other jobs run on native threads. A single-job block therefore needs no new thread; this also lets the C optimizer fold this intentionally trivial loop. Those results do not predict throughput for substantial workers. The main suite retains its hand-written C comparison, which launches one worker thread per parallel job, so the scheduling policies differ even though the computation and compiler flags match.

## Reading results honestly

These programs exercise four algorithm families, with five variants of the arithmetic workload. They are broader than a single kernel, but they are not a representative application suite and do not establish universal C or Rust performance. Both Clack and the hand-written C comparison use GCC or Clang's optimizer. Rust is not measured here.

Scheduling, CPU allocation, thermal state, and competing processes affect runtimes and parallel scaling. The report's logical CPU count is a host observation, not a guarantee of available CPU time. Small differences around a ratio of one should be treated as noise until larger repeated experiments support them.

The suite reports wall time, not peak memory, generated instruction counts, or security assurance. Verification rejects unsupported or unproved programs before runtime sampling; the resulting timing does not include proving the program.
