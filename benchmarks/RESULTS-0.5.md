# Clack 0.5 measurements

Clack 0.5 reduces copies when assigning a filled array and lowers verification overhead. A paired benchmark that fills and sums all 512 array elements over 200,000 iterations fell from **53.47 to 28.73 ms**, or **1.86×** faster on this machine. The 512-literal-array compiler fixture also improved, while the corrected text proof representation added some cost.

These are selected workloads. They do not establish a universal runtime or compiler speedup, or general C/Rust performance.

## Revisions and method

The baseline is Clack 0.4 at [`4c12059`](https://github.com/155xp/clack/commit/4c12059ab7d426a84210e4675d263e077f066a3f), extracted into an immutable source tree. Its compiler files were checked against that Git revision before measurement. Both revisions used the same benchmark source, Python environment, GCC 14.2.0, and flags: `-std=c11 -O3 -Wall -Wextra -pthread`. The recorded platform is Linux x86-64 with Python 3.12.

The full suite records five compiler-pipeline samples and seven native-process samples per case, with native work scaled by two. Clack and hand-written C runs are interleaved in a seeded shuffled order. Every native binary must match an independent reference before timing, and every timed output is checked too. The focused fill benchmark additionally builds actual baseline and current compiler outputs and interleaves seven before/after native samples. Fresh CLI checks use nine paired, shuffled samples per fixture.

Warm compiler and C-compilation measurements were collected in separate baseline and current runs. Changes in system load can contribute to small differences. The paired native and cold measurements reduce that ordering effect; they do not remove all scheduling noise.

- [Before full suite](results/0.5-before-suite.json)
- [After full suite, including paired native fill samples](results/0.5-after-suite.json)
- [Paired cold checks](results/0.5-cold-paired.json)
- [Before/after line counts](results/0.5-loc-before-after.json)

The baseline compiler fingerprint is `9a14f92c6c5871a3bb6619901c2b4fc17ac4cfdcbf49fde5b8cd628c129a0c81`; the measured 0.5 fingerprint is `4d18904021950d6e996b1beb72b4cd83aaad765cb3ae71c57dd804bdfb66cd5f`. Both full-suite files record the same benchmark fingerprint. The paired native and cold reports record the same compiler fingerprints, and paired measurements reject source trees that change during timing. Every shared fixture retains the same obligation count across revisions.

## Native fill and sum

The focused kernel performs 200,000 iterations. On iteration `i`, it fills a 512-element integer array with `i`, sums every element, and adds that sum to a checksum. Every iteration contributes to the final output. The independent closed-form reference is `512 * N * (N - 1) / 2`, yielding `10239948800000` for this run. Both actual compiler revisions pass the same source and exact output checks.

| Measurement | 0.4 | 0.5 |
| --- | ---: | ---: |
| Paired native-process median | 53.47 ms | 28.73 ms |

This is **1.86×** faster, or about **46% less time**, for this selected fill-and-reduce workload. Verification and C compilation finish before timing; process startup, output, and exit remain included.

Previously, `values = fill(value, N)` went through an array-valued helper result and assignment. The backend now evaluates the scalar value once before any target writes and fills the existing local array directly. Nested or value-returning fill expressions still use the ordinary value representation. This avoids unnecessary temporary-array copying while preserving source value semantics, including expressions that read the old target array.

The hand-written C reference uses an equivalent direct fill loop and full reduction. No timing barriers, external calls, or artificial no-inline attributes are inserted to force work. An optimizing compiler remains free to simplify either implementation. The result measures the generated programs under this toolchain, not an abstract memory-bandwidth limit.

## Compiler pipeline

These medians include source loading, parsing/linking, static checking, proofs, and C emission inside an already imported Python process. They exclude Python startup and native C compilation.

| Fixture | 0.4 | 0.5 | Before / after time | Obligations |
| --- | ---: | ---: | ---: | ---: |
| Minimal program | 0.30 ms | 0.30 ms | 1.01× | 1 |
| Standard-library imports | 63.71 ms | 66.21 ms | 0.96× | 248 |
| 128 constant increments | 26.26 ms | 20.16 ms | 1.30× | 257 |
| 128 symbolic increments | 73.39 ms | 62.30 ms | 1.18× | 259 |
| Eight Boolean branches | 16.19 ms | 17.81 ms | 0.91× | 18 |
| 512-element literal-array sum | 161.63 ms | 129.64 ms | 1.25× | 710 |
| 1,024-byte text pass-through | 0.95 ms | 1.56 ms | 0.61× | 0 |
| 150 unused arithmetic helpers | 1643.81 ms | 1196.79 ms | 1.37× | 6,155 |
| Nested record constructors | 4.40 ms | 3.16 ms | 1.39× | 1 |

The verifier reuses immutable signed-bound numeral terms rather than repeatedly constructing them. When a goal is already literal `true`, it avoids another simplifier call. All obligations are still recorded; a false goal is still checked against its path; unknown results still fail; and exported queries remain replayable. This is not a proof-result cache.

The array fixture improved from **161.63 to 129.64 ms**. Standard-library and branch fixtures did not improve in this run. The text fixture also became slower; that correctness tradeoff is described below. Small differences should not be treated as guaranteed speed changes.

## Cold CLI checks

These include Python/Z3 imports, loading, verification, CLI output, and process exit. They exclude C emission and native compilation.

| Fixture | 0.4 | 0.5 |
| --- | ---: | ---: |
| Minimal program | 109.11 ms | 102.48 ms |
| Standard-library imports | 167.98 ms | 162.27 ms |
| 512-element literal-array sum | 257.54 ms | 226.12 ms |
| 1,024-byte text pass-through | 103.34 ms | 108.65 ms |

Complete array-check latency improved by about **12%**. Startup remains a substantial fixed cost. The text pass-through check regressed in this run; the new representation is required for correct byte-level reasoning, not a speed improvement.

## Text correctness and cost

Clack 0.5 adds text equality and `len(text)`, where length counts UTF-8 bytes. The shared 1,024-byte text fixture only passes a text parameter through a helper and prints it, which was already supported in 0.4. It contains mixed Unicode characters and literal escape-like text. Both revisions' native output is checked against the same exact string. The new equality and length operations themselves are not presented as a before/after benchmark because 0.4 did not support them.

The verifier now models UTF-8 bytes explicitly, including escaped backslashes and characters outside Z3's direct character range. This prevents distinct source strings from aliasing in the proof model. Text lengths are also bounded by the signed integer representation. Encoding and reasoning about those bytes has a cost: this fixture's warm pipeline grew from **0.95 to 1.56 ms**. Its paired cold check grew from **103.34 to 108.65 ms**. No text compilation speedup is claimed.

## Shared native workloads

Current native-process medians across the nine cases were:

| Workload | Clack | Hand-written C | Clack / C time |
| --- | ---: | ---: | ---: |
| LCG single | 42.24 ms | 42.29 ms | 0.999 |
| LCG sequential2 | 78.63 ms | 80.83 ms | 0.973 |
| LCG sequential4 | 157.64 ms | 154.70 ms | 1.019 |
| LCG parallel2 | 41.09 ms | 40.32 ms | 1.019 |
| LCG parallel4 | 44.45 ms | 41.75 ms | 1.065 |
| Variable-input Euclidean GCD | 28.75 ms | 29.68 ms | 0.969 |
| Branch-heavy integer square root | 43.60 ms | 43.49 ms | 1.003 |
| Eight-state fixed-array updates | 38.58 ms | 39.67 ms | 0.972 |
| Repeated 512-value fill and sum | 28.61 ms | 28.40 ms | 1.007 |

The first eight cases do not establish a new runtime improvement from this revision. Five are variants of one linear congruential generator. The additional fill-and-sum case isolates the changed array-assignment behavior; its stronger paired comparison appears above. This remains a small set of algorithm families, with no Rust implementation, peak-memory measurement, or application benchmark.

Native timing includes process startup, output, thread setup/join where applicable, and exit. Clack runs the final parallel job on the caller, while the C comparison starts one worker thread per job, so those scheduling policies differ. Generated programs contain no Python interpreter or solver.

## Implementation size and validation

The compiler and bundled standard library grew from **2,315 to 2,343 physical lines**, an increase of **28 lines (1.2%)**. Nonblank, non-comment-only source grew from **2,025 to 2,049 lines**. Tests, benchmarks, examples, and documentation are counted separately in the linked report.

Validation passed 217 core regressions, 36 optional-library tests, and all 13 runnable tutorial outcomes. A clean wheel was checked outside the checkout with direct fill assignments, copy isolation, Unicode equality and byte lengths, and a native terminal UI provider. Native regressions include strict C11 compilation and undefined-behavior sanitization. The compiler, solver, C toolchain, operating system, and explicitly linked native C providers remain trusted. Matching reference outputs is useful evidence, not an independent proof of the whole implementation.

## Reproduce

```sh
mkdir -p /tmp/clack-05-baseline
git archive 4c12059 | tar -x -C /tmp/clack-05-baseline
.venv/bin/python benchmarks/suite.py --compiler-root /tmp/clack-05-baseline --label 0.5-before --scale 2 --repeats 7 --compile-repeats 5 --output build/0.5-before-suite.json
.venv/bin/python benchmarks/suite.py --label 0.5-after --scale 2 --repeats 7 --compile-repeats 5 --paired-root /tmp/clack-05-baseline --output build/0.5-after-suite.json
.venv/bin/python benchmarks/cold.py --before /tmp/clack-05-baseline --repeats 9 --output build/0.5-cold-paired.json
.venv/bin/python tools/loc.py --compare 4c12059
```

Run from the measured 0.5 source revision with pinned dependencies. The [suite guide](SUITE.md) describes timing boundaries and workload sources. Raw files retain every sample, including regressions and variation.
