# Working on Clack

Start with a behavior you can describe precisely: what source should mean, what the compiler should accept, and what should be rejected. Clack's goal is a small language that supports useful programs, rather than a large collection of familiar syntax without a coherent model.

The source is [MIT licensed](../LICENSE). There is no assumed hosted issue tracker or contribution service; these instructions apply to the local repository.

## Set up a development environment

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
clack --version
python -m unittest discover -s tests -v
```

Python 3.11 or newer is required. Native tests need a C11 compiler with POSIX thread support. The tested environment is Linux. The compiler has one pinned runtime Python dependency, Z3; see [pyproject.toml](../pyproject.toml).

The tests use Python's standard `unittest` runner. Parser tests cover accepted syntax and diagnostics. Verification regressions exercise both valid programs and tempting unsound shortcuts. Native tests compile emitted C, execute it, and check results, including real threads and the fallback when a thread cannot be created.

## Find the relevant layer

Read [compiler internals](internals.md) before changing semantics. Syntax lives in the frontend; module loading and source mappings live in the module loader; static type, scope, and purity rules live in the type checker; proof obligations live in the verifier; representation and runtime support live in the C emitter. The CLI controls public options and file handling.

A feature often crosses several layers. Adding a parser production alone does not make a feature implemented. The verifier must model its behavior, the backend must preserve that meaning, and errors must remain understandable.

Bundled library helpers live in [clack/stdlib](../clack/stdlib). They are ordinary Clack source and follow the same verification rules as application helpers. Add a precise contract, test useful allowed inputs and rejected calls, and include the module as a package resource when adding a new bundled source file. Do not bypass verification by treating an imported contract as an axiom. All declarations of a loaded library are checked, including unused ones.

The length-independent array reductions are compiler operations instead. Their shared metadata lives in [reductions.py](../clack/reductions.py), with direct verifier models and C lowering. Changes to these operations need agreement between type checking, mathematical results, overflow obligations, evaluation order, and native behavior. Keep source helpers and compiler operators clearly distinguished in documentation.

Native C providers are a third category: explicitly trusted implementations outside verification. Keep their calls in main, preserve scalar/immutable-text ABI checks and confined source paths, and test their C behavior separately. Never describe a passing Clack check as a proof of the provider's memory behavior or effects. The [native guide](native.md) defines the current boundary.

Module changes should preserve file-relative local resolution, the protected bundled `std` namespace, explicit imported names, and diagnostics that point back to original source. Include cross-file tests where a change affects name resolution, record types, or the call graph.

## Make a semantic change reviewable

For a language feature or bug fix, work through these questions:

1. What are the types, evaluation rules, effects, and failure cases?
2. Which new obligations establish safety or the stated contracts?
3. Does the solver model match C for all supported values, especially boundaries?
4. Can aliasing, shared state, or skipped evaluation invalidate an assumption?
5. What information can a caller safely learn from a verified helper?
6. Which short program should pass, and which nearby wrong program should fail?

Use meaningful regressions for semantic changes. A rejected example should reach the intended checking layer: a syntax error is not evidence that the verifier rejected an invalid claim. For code generation, include native execution where the representation or evaluation behavior matters. Test arithmetic limits, negative division, branches, repeated loop iterations, and value copies as relevant.

Loop changes deserve special attention to forgetting modified values and preserving all invariants. Parallel changes need clear ownership, input-state, joining, and effect semantics. Resource failures must not silently expose an unfinished result.

## Documentation and examples

Keep the [reference](reference/README.md) about implemented behavior. Put unimplemented proposals in [design.md](design.md). Do not document planned syntax as though the current compiler accepts it.

Run the documentation check after editing tutorials, linked files, or runnable examples:

```sh
python tools/check_docs.py
```

Use complete runnable examples when teaching a new concept; label fragments and intentionally failing snippets clearly. Give exact expected output when it helps a learner check their progress. Documentation corrections generally need example validation, not new unit tests that merely duplicate prose.

## Performance work

Use the [benchmark experiment](../benchmarks/README.md) to check the native path:

```sh
python benchmarks/compare.py --iterations 10000000 --repeats 5 --output build/benchmark.json
```

Separate verification and compilation time from executable time. Compare equivalent algorithms with the same compiler and flags, check outputs against an independent result, and record samples rather than a single best run. Small jobs include process and thread overhead. A faster microbenchmark does not justify a claim about all Clack programs.

## Describe the final change

Explain the concrete behavior before and after the change, why the implementation preserves the model, and which relevant checks passed. Identify any remaining limitations accurately. For larger features, update the language reference, error guidance, tutorial examples, and design status together so users can tell what exists today.

[Handbook](README.md) · [Compiler internals](internals.md)
