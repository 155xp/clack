# Clack 0.3 measurements

Clack 0.3 reduces proof-checking overhead and removes one thread creation per parallel block. On this machine, the symbolic arithmetic fixture's warm compiler pipeline fell from **250.54 to 59.58 ms**. Repeated tiny two-job parallel blocks fell from **81.22 to 51.17 ms**. A fresh minimal CLI check remained approximately **86 ms**.

These are measurements of selected workloads. They do not establish universal C/Rust performance or predict an application's speed.

## Revisions and method

The baseline is Clack 0.2 at [`80104fe`](https://github.com/155xp/clack/commit/80104fea55bd0058e4aa2819284b6003eca613dc), extracted into an immutable source tree. Both revisions ran through the same benchmark source, Python environment, C compiler, and flags. The recorded platform is Linux x86-64 with Python 3.12 and GCC 14.2.0. Flags are `-std=c11 -O3 -Wall -Wextra -pthread`.

The full suite uses five compiler-pipeline samples and seven native-runtime samples per case, with runtime work scaled by two. Timed Clack and C executions are interleaved in a deterministic shuffled order. Each binary must produce the independent reference output before timing, and every timed output is checked too. Cold CLI measurements and small parallel-block measurements use separate paired, shuffled before/after runs.

Raw files contain every sample, medians, source fingerprints, and timing scopes:

- [Before full suite](results/0.3-before-suite.json)
- [After full suite](results/0.3-after-suite.json)
- [Paired small parallel blocks](results/0.3-parallel-paired.json)
- [Paired cold CLI checks](results/0.3-cold-paired.json)
- [Before/after line counts](results/0.3-loc-before-after.json)

The baseline compiler source fingerprint is `6cb0fb4e8b9daf741995193803f004f06e36768c1bfbdf5e08ceeb2c815eeddc`; the measured 0.3 fingerprint is `1296c392083e759d0fad020bb23fb5ca6b5124eb50fc9c77ff23591dd9f777fa`. Both full-suite files record the same benchmark fingerprint. The paired scripts reject a compiler tree that changes during their measurement.

## Compiler pipeline

These medians include loading, parsing, linking, type checking, verification, and C emission in a Python process that has already imported the compiler. They exclude Python startup and native C compilation.

| Fixture | 0.2 | 0.3 | Before / after time |
| --- | ---: | ---: | ---: |
| Minimal program | 0.46 ms | 0.42 ms | 1.11× |
| Standard-library imports | 89.54 ms | 52.12 ms | 1.72× |
| 128 constant increments | 33.93 ms | 28.56 ms | 1.19× |
| 128 symbolic increments | 250.54 ms | 59.58 ms | 4.21× |
| Eight Boolean branches | 25.50 ms | 14.22 ms | 1.79× |
| Nested record constructors | 5.39 ms | 3.73 ms | 1.44× |

The symbolic fixture accepts any integer input from zero through 100,000, increments it 128 times, and proves the exact result. Each arithmetic operation still has a safety obligation. All full-suite fixtures retain the same number of obligations across revisions.

The verifier now reuses a solver within one verification run. Each obligation gets its own `push`/`pop` scope, complete path, and negated claim. There is no reuse of an earlier obligation's assumptions or unchecked proof-result cache. Unknown results still fail, and SMT exports retain complete queries. Regression tests cover function and branch isolation, failed queries, and transcript replay. Short constant-only fixtures are less affected; differences there include measurement noise and surrounding compiler work.

## Fresh CLI checks

These are nine paired, interleaved samples per fixture, including Python/Z3 imports, source loading, type checking, verification, CLI output, and process exit. They exclude C emission and native compilation.

| Fixture | 0.2 | 0.3 |
| --- | ---: | ---: |
| Minimal program | 85.51 ms | 85.55 ms |
| Standard-library imports | 168.59 ms | 140.22 ms |

Startup remains a substantial fixed cost. The 4.21× warm symbolic-fixture result is not a claim that every command starts four times faster.

## Parallel scheduling overhead

The focused benchmark executes 2,000 parallel blocks with identity workers and checks the final output. Each row has eleven paired, shuffled native-process samples; verification and compilation finish before timing.

| Jobs per block | 0.2 | 0.3 | Before / after time |
| --- | ---: | ---: | ---: |
| One | 51.22 ms | 0.95 ms | See below |
| Two | 81.22 ms | 51.17 ms | 1.59× |
| Four | 134.45 ms | 106.80 ms | 1.26× |

Clack 0.3 snapshots every argument, starts the first N−1 jobs on native threads, executes the last job on the calling thread, then joins before exposing results. This preserves N concurrent jobs while avoiding one thread creation and join per block. Thread-creation failure still falls back to a synchronous call.

With one job, no new thread is needed. Removing that side effect also lets GCC fold this intentionally trivial loop, explaining the much larger change in that row. Identity workers isolate scheduling overhead; they do not measure useful parallel throughput. A thread pool is not used, so tiny parallel jobs can still cost more than sequential calls.

## Substantial native workloads

The full suite covers four algorithm families with eight cases. Five cases are variants of the same linear congruential generator (LCG). Independent references use modular exponentiation, Python's `math.gcd`/`math.isqrt`, and matrix exponentiation. Here are the 0.3 native-process medians:

| Workload | Clack | Hand-written C | Clack / C time |
| --- | ---: | ---: | ---: |
| LCG, one job | 41.78 ms | 40.11 ms | 1.042 |
| LCG, two sequential jobs | 78.81 ms | 77.62 ms | 1.015 |
| LCG, four sequential jobs | 155.12 ms | 155.44 ms | 0.998 |
| LCG, two parallel jobs | 40.31 ms | 41.99 ms | 0.960 |
| LCG, four parallel jobs | 42.92 ms | 41.93 ms | 1.024 |
| Variable-input Euclidean GCD | 28.09 ms | 29.48 ms | 0.953 |
| Integer square root | 45.71 ms | 44.54 ms | 1.026 |
| Eight-state array update | 39.09 ms | 39.44 ms | 0.991 |

Clack took **0.95–1.04× the C time** in these cases. Differences near one are small enough to be sensitive to scheduling and CPU allocation. The heavier workers did not show a clear runtime improvement from removing one thread per block; the focused benchmark above measures where that change matters. The C parallel comparison launches one worker thread per job, while 0.3 uses the caller for the final job. Computation and compiler flags match, but thread scheduling policies differ.

Native timing includes process startup, output, thread setup/join, and exit. No Rust implementation, peak memory, or application benchmark is included. Verified bounds, loop invariants, and declared contracts describe the language's proof model; matching independent runtime outputs does not by itself prove complete mathematical behavior. The compiler, solver, C toolchain, operating system, and explicit native C bindings remain trusted components.

## Size and features

The compiler and bundled standard library grew from **2,155 to 2,274 physical lines**, an increase of **119 lines (5.5%)**. Nonblank, non-comment-only source grew from **1,879 to 1,985 lines**. Tests, benchmark tooling, examples, and documentation are counted separately in the raw line-count report.

Besides solver and scheduling changes, this includes counted `for … in range(…)` loops with automatic index bounds and termination checking, optional invariants for accumulated state, `--timings` phase reporting, and source-file protection for proof and C outputs. Counted loops emit ordinary native C loops; no interpreter or solver is linked into the resulting program.

Validation passed 168 compiler, verification, CLI, and native execution tests; 36 optional-library regressions; and all 11 runnable tutorial outcomes. Native regressions include strict C11 compilation with undefined-behavior sanitization. The built wheel was also checked outside the source tree with bundled imports, counted loops, and a native terminal UI provider.

## Reproduce

```sh
mkdir -p /tmp/clack-03-baseline
git archive 80104fe | tar -x -C /tmp/clack-03-baseline
.venv/bin/python benchmarks/suite.py --compiler-root /tmp/clack-03-baseline --label 0.3-before --scale 2 --repeats 7 --compile-repeats 5 --output build/0.3-before-suite.json
.venv/bin/python benchmarks/suite.py --label 0.3-after --scale 2 --repeats 7 --compile-repeats 5 --output build/0.3-after-suite.json
.venv/bin/python benchmarks/parallel.py --before /tmp/clack-03-baseline --repeats 11 --blocks 2000 --output build/0.3-parallel-paired.json
.venv/bin/python benchmarks/cold.py --before /tmp/clack-03-baseline --repeats 9 --output build/0.3-cold-paired.json
.venv/bin/python tools/loc.py --compare 80104fe
```

Run from the measured 0.3 source revision with its pinned dependencies. The [suite guide](SUITE.md) explains the individual workloads and timing boundaries.
