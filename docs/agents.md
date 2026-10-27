# Clack for coding agents

[Handbook](README.md) · [Machine-readable reference](agent-reference.json) · [Optional packages](packages.md)

This page describes the implemented Clack 0.6 language. The [design direction](design.md) contains proposals, not additional accepted syntax. Use the [grammar](reference/grammar.md) and [quick reference](quick-reference.md) when generating source. Clack resembles Python in indentation; it is a separate compiled language and does not execute Python.

## Find the right reference

| Need | Source |
| --- | --- |
| Structured capabilities and commands | [agent-reference.json](agent-reference.json) |
| Package locations, demos, and checks | [Package guide](packages.md) and [package catalog](../packages/catalog.json) |
| Exact package signatures and contracts | The selected package's `.clack` source and README |
| Syntax and types | [Grammar](reference/grammar.md) and [types](reference/types-values.md) |
| Proof failures | [Error guide](errors.md) and [verification model](verification.md) |
| Runtime evidence | [Recorded benchmark reports](../benchmarks/RESULTS-0.6.md) |

The package catalog describes optional source files in this repository. It is not an online registry or a dependency resolver. A package's numeric bounds and supported shapes are part of its API; read its contracts before choosing inputs.

## Build and verify a program

From a repository checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m clack check app.clack
.venv/bin/python -m clack run app.clack
.venv/bin/python -m clack build app.clack -o build/app --timings
```

`check` proves the Clack portion without requiring a C compiler. `run` and `build` also need a C11 compiler and POSIX threads. They verify before emitting code; there is no unchecked compilation option. Generated executables do not require Python or Z3 at runtime.

All ordinary functions in every loaded module are checked, including unused functions. The C backend may omit unreachable definitions after verification. Removing a call to a bad imported function does not make that loaded module valid.

Use `clack emit-c app.clack -o build/app.c` to inspect native output. Use `--proof-dir build/proofs` on a source command to retain SMT queries and an `obligations.json` manifest. These are replayable verification conditions, not independently checked proof certificates. `--timeout-ms` applies to each query, and an unknown or timed-out result rejects the program.

## Generate supported source

- Use spaces, indented blocks, decimal integers, and double-quoted JSON-style text literals. Do not emit Python imports, f-strings, comprehensions, tuples, or implicit final-expression returns.
- Declare function parameter and result types. Only `main` may omit its `-> unit` annotation; ordinary source helpers must return a value on every continuing path.
- Locals infer a type that stays fixed through the function. Parameters are immutable. Copy an array parameter into a local before updating it.
- `int` is signed 64-bit, `bool` is distinct from `int`, and `text` is immutable UTF-8 originating in literals. Records have immutable named fields and finite value layouts. Arrays contain `int` or `bool`, with fixed lengths from 1 through 1,000,000.
- Array indexing must be proved in bounds. Record or array equality is unavailable; compare the fields or elements that express the property.
- `/` truncates integer division toward zero. `%` has the dividend's sign when nonzero. Every executable arithmetic intermediate must fit the signed range; a safe final result does not excuse an overflowing earlier expression.
- Text equality is exact byte equality without case folding or normalization. `len(text)` counts UTF-8 bytes; `len("café")` is 5. `len(array)` counts elements.
- Proof expressions use mathematical integers. They support operators, fields, indexing, and `len`; they cannot call source helpers, constructors, or imported array operators.
- Put `requires` and `ensures` before executable statements. `assert` is a fact to prove, not an assumption.

For example, this complete program needs an input bound before incrementing:

```clack
fn next(value: int) -> int:
    requires value < 9223372036854775807
    ensures result == value + 1
    return value + 1

fn main():
    print(next(41))
```

The language has no floating-point types, dynamic arrays, general generics, recursion, pattern matching, exceptions, or closures. Fixed-shape numeric and ML packages use explicit sizes and bounded integer arithmetic. Do not generate APIs from a larger ecosystem merely because their names are familiar.

## Loops and parallel work

`for i in range(stop):` and `for i in range(start, stop):` use a unit positive step and exclude the upper bound. Bounds are evaluated once. The index is immutable, scoped to its body, and cannot shadow an existing binding. Index bounds and termination are automatic; useful relationships involving modified locals still need invariants.

A `while` body begins with one or more `invariant` clauses and one `decreases` clause. Verification reasons about an arbitrary loop iteration, forgetting previous values of modified locals. A counterexample involving a loop may show that the invariant is too weak rather than identify a reachable execution trace.

`parallel:` contains named independent calls to ordinary source functions. Arguments cannot refer to any result name from the same block. All arguments see the incoming state, results become available together, and the block waits for every job. Source workers are pure and exchange values, not shared mutable references. Imported array operators must be wrapped in source worker functions when used as jobs.

Creating native threads has a cost. Keep jobs substantial and measure the intended workload. The current implementation has no worker pool, GPU backend, or automatic parallelization guarantee.

## Resolve package imports from the importing file

For an `app.clack` at the repository root:

```clack
from packages.geometry.geometry import Point, squared_distance

fn main():
    print(squared_distance(Point(0, 0), Point(3, 4)))
```

This prints `25`. A source file in `examples/` would search below `examples/` for that same import. The shell's working directory does not change import resolution. Put application source beside the copied `packages/` directory, or choose a layout with the needed modules below the importing file's directory.

Imports select explicit function or record names. There are no aliases, wildcard imports, environment search paths, network downloads, or module initializers. Imported source retains its own module scope; record types are nominal.

## Repair a rejected program

1. Read the diagnostic's actual source path and line, including imported files. Run `check` before spending time on native compilation.
2. Establish the needed input domain or control-flow guard for arithmetic, indices, and callee preconditions. Preserve the intended behavior when changing contracts.
3. For a loop, write the relationship between its modified state and progress. Increasing the timeout does not add a missing invariant.
4. For `sat`, inspect the counterexample against the current contracts and path. For `unknown`, inspect the exported query or simplify the specification; neither result may be accepted as a proof.
5. Run the documented demo or a native reference comparison after verification. A contract proves only the property it states, so runtime tests should also check the intended algorithm and outputs.

## Preserve the native trust boundary

Only main may print or call declared native bindings. A native call is a direct assignment or a standalone unit call; it cannot appear inside a condition, nested call, proof, or parallel job. C providers are trusted and unproved. Their scalar results are arbitrary typed values until checked code establishes a useful guard.

The terminal UI package uses this boundary for drawing and input. A successful check verifies the Clack portion, not the C provider's memory handling, terminal restoration, operating-system behavior, or termination. See the [native guide](native.md) for ABI and path restrictions.
