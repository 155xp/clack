# Clack 0.4 measurements

Clack 0.4 adds `fill`, `minimum`, and `maximum` array operators and reduces constant-proof and backend work. On this machine, the 512-element literal-array fixture's warm compiler pipeline fell from **164.86 to 132.88 ms**. Its paired fresh CLI check fell from **264.15 to 221.94 ms**. Minimal CLI startup remained approximately **91 ms**.

These changes target compilation. The measurements do not establish faster native execution or general C/Rust performance.

## Revisions and method

The baseline is Clack 0.3 at [`117991a`](https://github.com/155xp/clack/commit/117991a1f20fb4baca87789bbe10e1be32d7301d), extracted into an immutable source tree. Both revisions used the same suite source, Python environment, C compiler, and flags: `-std=c11 -O3 -Wall -Wextra -pthread`. The recorded platform is Linux x86-64 with Python 3.12 and GCC 14.2.0.

The full suite records five compiler samples and seven native-process samples per case, with native work scaled by two. Native Clack/C samples are interleaved in a seeded shuffled order. Both binaries must match independent reference outputs before timing, and every timed output is checked. Separate cold checks use nine paired, shuffled before/after samples per fixture. Warm-pipeline and C-compilation samples were collected in separate baseline and current runs; small differences can include changes in system load.

- [Before full suite](results/0.4-before-suite.json)
- [After full suite](results/0.4-after-suite.json)
- [Paired cold checks](results/0.4-cold-paired.json)
- [Before/after line counts](results/0.4-loc-before-after.json)

The baseline compiler fingerprint is `1296c392083e759d0fad020bb23fb5ca6b5124eb50fc9c77ff23591dd9f777fa`; the measured 0.4 fingerprint is `9a14f92c6c5871a3bb6619901c2b4fc17ac4cfdcbf49fde5b8cd628c129a0c81`. Both full-suite reports record the same benchmark fingerprint, and the paired cold report records matching compiler fingerprints. Every shared fixture retains the same obligation count across revisions.

## Compiler pipeline

These medians include source loading, parsing/linking, static checking, proofs, and C emission inside an already imported Python process. They exclude Python startup and native C compilation.

| Fixture | 0.3 | 0.4 | Before / after time | Obligations |
| --- | ---: | ---: | ---: | ---: |
| Minimal program | 0.34 ms | 0.32 ms | 1.06× | 1 |
| Standard-library imports | 50.73 ms | 45.94 ms | 1.10× | 248 |
| 128 constant increments | 28.38 ms | 21.83 ms | 1.30× | 257 |
| 128 symbolic increments | 57.04 ms | 47.33 ms | 1.21× | 259 |
| Eight Boolean branches | 13.67 ms | 14.53 ms | 0.94× | 18 |
| 512-element literal-array sum | 164.86 ms | 132.88 ms | 1.24× | 710 |
| 150 unused arithmetic helpers | 1,489.85 ms | 1,352.59 ms | 1.10× | 6,155 |
| Nested record constructors | 4.45 ms | 3.44 ms | 1.29× | 1 |

For an integer numeral, the verifier can compute its signed-range condition directly using exact arbitrary-precision integer comparisons. It still passes that condition through the existing proof path, retains the obligation, and checks reachability when the condition is false. This avoids repeatedly constructing symbolic inequalities for known constants. There is no unchecked proof-result cache or relaxed overflow rule. Unknown solver results still fail, and exported queries remain replayable.

The array fixture sums 512 literals cycling from zero through six and asserts the exact total, 1,533. Every partial addition remains checked. This is a selected synthetic workload, not an application benchmark. The branch fixture did not improve in this run; small timing changes should not be treated as guaranteed gains.

## Cold CLI checks

These paired process measurements include Python/Z3 imports, source loading, verification, CLI output, and exit. They exclude C emission and native compilation.

| Fixture | 0.3 | 0.4 |
| --- | ---: | ---: |
| Minimal program | 90.58 ms | 91.11 ms |
| Standard-library imports | 137.75 ms | 140.73 ms |
| 512-element literal-array sum | 264.15 ms | 221.94 ms |

The array fixture improved by about 16% in complete check latency. The minimal and standard-library checks did not improve. Fixed startup costs remain substantial, so the warm compiler ratios do not describe every command.

## Avoiding unused C output

The backend now follows calls from `main` and emits only reachable source functions, task trampolines, and array helpers. All loaded Clack functions are still type-checked and verified first, including unused definitions. An invalid unused helper still rejects a program.

The synthetic unused-code fixture contains 150 arithmetic helpers, a small called helper chain, and an unused parallel helper. Main prints `42`. The standard-library fixture also prints its checked reference output after compilation.

| Fixture | Generated C, 0.3 | Generated C, 0.4 | C compile, 0.3 | C compile, 0.4 |
| --- | ---: | ---: | ---: | ---: |
| Standard-library imports | 4,625 bytes | 1,782 bytes | 36.88 ms | 37.78 ms |
| 150 unused arithmetic helpers | 157,091 bytes | 768 bytes | 49.10 ms | 37.32 ms |

The larger fixture emits about 99.5% less C and its C compilation took about 24% less time. The smaller fixture's C compilation did not improve despite emitting less source. These are five standalone C-compilation samples per revision, excluding verification and execution. Generated source size is not final executable size: an optimizing C compiler could already discard unused functions from a binary.

## Native execution

The eight shared kernels still produce their independent reference results. Current native-process medians were:

| Workload | Clack | Hand-written C | Clack / C time |
| --- | ---: | ---: | ---: |
| LCG, one job | 41.33 ms | 40.72 ms | 1.015 |
| LCG, two sequential jobs | 81.86 ms | 77.84 ms | 1.052 |
| LCG, four sequential jobs | 162.74 ms | 163.04 ms | 0.998 |
| LCG, two parallel jobs | 42.63 ms | 42.54 ms | 1.002 |
| LCG, four parallel jobs | 42.44 ms | 42.77 ms | 0.992 |
| Variable-input Euclidean GCD | 30.71 ms | 29.70 ms | 1.034 |
| Integer square root | 46.41 ms | 43.74 ms | 1.061 |
| Eight-state array update | 41.31 ms | 41.22 ms | 1.002 |

Clack took **0.99–1.06× the C time** on these selected cases. No native execution speedup is established by this revision. The suite covers four algorithm families; five cases are variants of the same linear congruential generator. Native timings include process startup, output, thread setup/join, and exit. Clack uses the caller for the last parallel job; the hand-written C comparison starts one thread per job. Scheduling policies therefore differ despite matching computation and compiler flags. No Rust, peak-memory, or application benchmark is included.

## Features and implementation size

`fill(value, N)` creates a fixed integer or Boolean array without a long literal list. `minimum(values)` and `maximum(values)` select an integer element using comparisons, including the full signed 64-bit range. The compiler models their exact results and emits native loops. They are new features, so this report does not present a before/after speed comparison for them.

The compiler and bundled standard library grew from **2,274 to 2,315 physical lines**, an increase of **41 lines (1.8%)**. Nonblank, non-comment-only source grew from **1,985 to 2,025 lines**. Tests, benchmarks, documentation, and examples are counted separately in the linked line-count report. The compiler, solver, C toolchain, operating system, and explicit native C providers remain trusted; matching runtime outputs is not an independent proof of the whole implementation.

Validation passed 195 core regressions, 36 optional-library tests, and all 12 runnable tutorial outcomes. The cleanly built wheel was also checked outside the source tree with the new array operators and a native terminal UI provider.

## Reproduce

```sh
mkdir -p /tmp/clack-04-baseline
git archive 117991a | tar -x -C /tmp/clack-04-baseline
.venv/bin/python benchmarks/suite.py --compiler-root /tmp/clack-04-baseline --label 0.4-before --scale 2 --repeats 7 --compile-repeats 5 --output build/0.4-before-suite.json
.venv/bin/python benchmarks/suite.py --label 0.4-after --scale 2 --repeats 7 --compile-repeats 5 --output build/0.4-after-suite.json
.venv/bin/python benchmarks/cold.py --before /tmp/clack-04-baseline --repeats 9 --output build/0.4-cold-paired.json
.venv/bin/python tools/loc.py --compare 117991a
```

Run from the measured 0.4 source revision with its pinned dependencies. The [suite guide](SUITE.md) describes the workload sources and timing boundaries. Raw files retain every sample rather than only the selected medians.
