# Clack 0.6: libraries, documentation, and measurements

Clack 0.6 publishes seven optional source packages, including a trainable integer perceptron, while keeping the compiler and bundled standard library at **2,343 physical lines**. A text-proof encoding optimization reduces the selected warm compiler workloads by **1.79–2.61×**, with identical generated C and exported SMT queries.

The packages live in the main repository's [packages directory](../packages/README.md), separate from the installed compiler and bundled `std` modules. They can be copied into an application without a package registry or compiler extension.

## Available packages

| Package | Implemented capabilities |
| --- | --- |
| [ML](../packages/ml/README.md) | Four-feature integer linear scores, predictions, bounded online perceptron updates, squared distances, nearest-centroid classification |
| [Fixed point](../packages/fixed/README.md) | Scale-1,000 arithmetic, exact documented formulas, integer truncation toward zero |
| [Algorithms](../packages/algorithms/README.md) | Four-value sorting with exact permutation contracts, first-match search, first-tie argmin, lower bound |
| [Statistics](../packages/stats/README.md) | Four-value summaries, rational means, squared sums, exact rational population variance |
| [Matrix](../packages/matrix/README.md) | 2×2 matrices, 2D transforms, four-component dot products and squared norms |
| [Geometry](../packages/geometry/README.md) | Points, rectangles, distances, containment, intersections, bounding rectangles |
| [TUI](../packages/tui/README.md) | Native POSIX terminal panels, rows, metrics, progress, keyboard menus, plain-output fallback |

The catalog records **37 source functions, 9 record types, and 10 native bindings**. All loaded Clack source bodies are verified. TUI's C implementation is an explicit trusted boundary, as reported by the compiler. Numeric APIs have fixed shapes and documented bounds; these packages do not introduce floating-point types, arbitrary tensors, automatic differentiation, or GPU execution.

The ML demo trains an OR classifier through eight deterministic dataset passes. Independent tests compare updates to a Python integer reference, including clipping, signed boundaries, and nonseparable XOR data. Training contracts establish safe bounded updates and unchanged models for already-correct predictions; they do not prove general convergence or statistical accuracy. The package README describes those distinctions and the exact algorithm.

## Human and agent documentation

The [package guide](../docs/packages.md) explains installation, imports, copying libraries, and validation. Each package includes API documentation, source contracts, a license, tests, and runnable demos.

Coding agents have a [workflow guide](../docs/agents.md), a [structured language reference](../docs/agent-reference.json), a [generated package API catalog](../packages/catalog.json), and [llms.txt](../llms.txt). The catalog includes concrete signatures, source line numbers, reexports, source hashes, and expected demo outcomes. The checkers detect stale catalog fields and broken local documentation links. These are documentation and validation tools, not an online dependency resolver.

## Compiler measurements

The immutable baseline is [Clack 0.5 at `a3c7ef9`](https://github.com/155xp/clack/commit/a3c7ef9c470ebc7efaf8443d4a73ead908092ef4). Both actual compiler revisions ran the same byte-exact text fixtures with seven shuffled paired warm samples and nine paired cold samples. Warm timing includes loading, verification, and C emission in an already imported process; cold timing includes a fresh CLI check and Python/Z3 startup. Neither includes native C compilation.

| UTF-8 text size | Warm pipeline, 0.5 | Warm pipeline, 0.6 | Before / after | Cold CLI, 0.5 | Cold CLI, 0.6 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 KB | 2.505 ms | 1.401 ms | 1.79× | 97.011 ms | 89.402 ms |
| 16 KB | 24.228 ms | 9.293 ms | 2.61× | 119.353 ms | 108.167 ms |

The verifier maps UTF-8 bytes to Latin-1 codepoints and protects backslashes before constructing a solver string. This preserves the exact byte model while avoiding explicit hexadecimal formatting for every byte. It caches no proof results and removes no obligations. A corpus regression covers mixed Unicode and escape-looking strings, including characters through U+10FFFF.

Both revisions produced **identical generated C and SMT query hashes** for these fixtures. Native output validation and independent fresh-solver replay passed before timing. This is a compilation improvement for selected text workloads, not a native runtime improvement or a guarantee about every command. Startup and system scheduling still contribute to cold results. [All samples and fingerprints](results/0.6-text-encoding.json) are retained.

## Selected integer ML inference kernel

The [ML benchmark](ml.py) compiles the actual optional package and an equivalent C implementation using GCC 14.2.0 and `-std=c11 -O3 -Wall -Wextra -pthread`. Fifty million iterations score a four-feature integer linear model and accumulate a checksum. Nine native-process samples per implementation are shuffled; every output must match the independent closed-form reference, `749999916`.

| Implementation | Median | Sample range |
| --- | ---: | ---: |
| Clack package | 54.35 ms | 51.86–60.07 ms |
| Equivalent C | 60.92 ms | 50.10–70.04 ms |

Verification and compilation finish before timing. Native timing includes process startup, output, and exit. Sample ranges overlap. Constant coefficients can be inlined and simplified in both implementations; no artificial optimization barriers are inserted. This supports a result for one small integer inference kernel, not a claim that Clack generally beats C or that it measures training, floating-point ML, neural networks, or GPU work. [Raw samples, sources, flags, and hashes](results/0.6-ml.json) make the comparison reproducible.

## Size and validation

The compiler plus bundled standard library remains **2,343 physical lines / 2,049 nonblank, non-comment-only lines**, unchanged from 0.5. The optional packages add **500 lines of Clack and 283 lines of C**. Their examples, regression tests, documentation, catalog, and developer tools are counted separately in the [line-count snapshot](results/0.6-loc-before-after.json).

Validation passes **218 core tests, 65 package tests, 9 native package demos, and 13 tutorial outcomes**. A clean installed wheel also compiled a combined application using all seven copied packages outside the checkout, and reproduced the ML training demo. Native package regressions compare independent references and exercise strict C11 and undefined-behavior sanitization; TUI tests also exercise real pseudo-terminals, cancellation, resize, and cleanup. Proofs are against the implemented model and written contracts. The compiler, Z3, C toolchain, operating system, and explicit C providers remain trusted; exported SMT conditions are not independently checked proof certificates.

## Reproduce

```sh
python tools/check_docs.py
python tools/check_packages.py
python -m unittest discover -s tests -q
mkdir -p /tmp/clack-library-baseline
git archive a3c7ef9 | tar -x -C /tmp/clack-library-baseline
python benchmarks/text_encoding.py --before /tmp/clack-library-baseline --output build/text-encoding.json
python benchmarks/ml.py --rounds 50000000 --repeats 9 --output build/ml.json
python tools/loc.py --compare a3c7ef9
```

Use the installed compiler environment with the pinned dependencies, and run from the repository root. The scripts expose sample counts and compiler selection in `--help`.
