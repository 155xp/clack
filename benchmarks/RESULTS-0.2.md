# Clack 0.2: code size and measured performance

Baseline: commit `ae2b05023c2dfd4b4f3273d6af5ed4cfb9ffbb9c`. Measurements recorded October 26, 2026 on Linux x86-64 with cc (Debian 14.2.0-19) 14.2.0. This is a prototype benchmark, not a claim of general C or Rust parity.

## Code size

Physical source lines are counted separately from blank/comment-only exclusions. Docstrings and inline comments count as source. Compiler implementation means the `clack/` Python files plus bundled `.clack` standard-library source; tests, benchmark harnesses, documentation, and optional libraries are separate.

| Category | Before | After | Change |
| --- | ---: | ---: | ---: |
| Compiler + standard library | 1,968 | 2,155 | +187 (9.5%) |
| Same, excluding blank/comment-only lines | 1,709 | 1,879 | +170 (9.9%) |
| Compiler tests | 1,335 | 2,010 | +675 |
| Benchmark code | 241 | 756 | +515 |
| Development tools | 132 | 206 | +74 |

The implementation gained four length-independent array reductions, immutable UTF-8 text, and explicit native C bindings. It also replaced unnecessary solver calls and branch-state explosion. No source minification or safety-check removal was used. The standard-library source remains 72 lines.

Optional library implementation sizes are not hidden in the core count: integer statistics 49 Clack lines, geometry 63 Clack lines, matrices 75 Clack lines, and terminal UI 12 Clack + 283 C lines (295 total). Native terminal code is outside the proof model.

Reproduce the size comparison from the repository root:

```sh
python tools/loc.py --compare ae2b050
python tools/loc.py --compare ae2b050 --json
```

The JSON includes per-file and per-category counts. Later documentation/report edits can change the non-implementation categories; the implementation measurement is tied to the compiler fingerprint in the reports.

## Compiler pipeline

Three-sample medians in an already imported Python process. Each pass performs fresh source loading, parsing/linking, type/proof checking, and C emission. Python startup and native C compilation are excluded. The before snapshot is immutable; both revisions use the same harness and solver installation.

| Workload | Before | After | Speedup |
| --- | ---: | ---: | ---: |
| Minimal numeric program | 0.84 ms | 0.34 ms | 2.47x |
| Standard-library imports | 174.56 ms | 74.39 ms | 2.35x |
| 128 arithmetic assignments | 120.32 ms | 29.98 ms | 4.01x |
| Eight independent branches | 393.11 ms | 25.91 ms | 15.17x |
| 17 nested record constructors | 205.68 ms | 3.10 ms | 66.43x |

The branch fixture drops from 767 obligations to 18 by joining continuing paths with conditional values. Constant-true goals are established by simplification; constant-false goals still require their path, so unreachable operations remain handled correctly. Exported conditions remain replayable. Lazy call-argument rendering avoids repeated traversal of nested constructors.

## Cold command-line checks

`clack check` does not emit C. It includes Python/Z3 startup and verification, so its latency differs from the complete warm compiler pipeline. A follow-up paired experiment interleaved both revisions, using nine fresh-process samples per fixture to reduce time-of-run bias:

| Fixture | Before | After |
| --- | ---: | ---: |
| Minimal program | 100.40 ms | 103.84 ms |
| Standard-library imports | 311.59 ms | 191.54 ms |

Tiny-program cold startup is essentially unchanged and slightly slower in this sample. Most of that cost is interpreter/solver initialization. Library checking improves, but the large warm-pipeline speedups must not be presented as equivalent cold-start gains. Native C compilation is measured separately in the full suite JSON.

## Native runtime versus matching C

Nine-sample medians at `--scale 4`. All Clack and hand-written C programs use identical C compiler flags (`-std=c11 -O3 -Wall -Wextra -pthread`) and matching algorithms. Every output must match an independent reference. Native process startup, printing, and thread creation/joining are included; parsing, verification, and compilation are excluded.

| Workload | Clack | C | Clack/C time |
| --- | ---: | ---: | ---: |
| LCG single | 80.17 ms | 81.26 ms | 0.986 |
| LCG sequential2 | 166.09 ms | 166.90 ms | 0.995 |
| LCG sequential4 | 330.74 ms | 311.43 ms | 1.062 |
| LCG parallel2 | 82.08 ms | 87.41 ms | 0.939 |
| LCG parallel4 | 83.87 ms | 82.97 ms | 1.011 |
| Variable-input Euclidean GCD | 57.91 ms | 56.61 ms | 1.023 |
| Branch-heavy integer square root | 89.44 ms | 85.98 ms | 1.040 |
| Eight-state fixed-array updates | 78.26 ms | 85.21 ms | 0.918 |

Clack parallel scaling in this run: 2 jobs: 2.02x versus the same number of sequential jobs, 4 jobs: 3.94x versus the same number of sequential jobs. These ratios depend on CPU allocation and scheduling.

The initial shorter five-sample after run varied more (ratios about 0.88–1.18). Its complete samples are retained, rather than discarded. The longer run reduces startup/scheduling sensitivity; it still covers selected kernels, not representative whole applications. Rust and peak memory were not measured. The main demonstrated improvements in this pass are compiler work, not a universal native-runtime speedup.

## Validation and raw evidence

136 compiler tests pass, including strict rejection tests, replayed SMT queries, branch-join safety, native-module restrictions, C compilation/execution, and bounded emitter traversal. Optional libraries have their own test suites; the terminal package exercises a real pseudo-terminal, signal/resize cleanup, strict C11, and undefined-behavior sanitization. Native C remains a trusted boundary, not a formally verified implementation.

- [Before suite: raw samples and fingerprints](results/0.2-before-suite.json).
- [After suite: raw samples and fingerprints](results/0.2-after-suite.json).
- [Longer native run](results/0.2-runtime-steady.json).
- [Interleaved cold-start samples](results/0.2-cold-paired.json).
- [Before/after line counts](results/0.2-loc-before-after.json).
- [Benchmark methodology and reproduction commands](SUITE.md).

```sh
mkdir -p /tmp/clack-before
git archive ae2b050 | tar -x -C /tmp/clack-before
python benchmarks/suite.py --compiler-root /tmp/clack-before --label before --output build/before-suite.json
python benchmarks/suite.py --label after --output build/after-suite.json
python benchmarks/suite.py --label runtime-longer --scale 4 --repeats 9 --compile-repeats 1 --output build/runtime-steady.json
python benchmarks/cold.py --before /tmp/clack-before --output build/cold-paired.json
```
