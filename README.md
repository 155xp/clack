# Clack

A small language with plain syntax, native binaries, and checked contracts.

[GitHub repository](https://github.com/155xp/clack)

Clack is an original working prototype inspired by the goals of languages such as Bend: make useful programs easy to express, run them efficiently, and check what they promise. This implementation does not use Bend's code.

```clack
fn clamp(x: int, low: int, high: int) -> int:
    requires low <= high
    ensures low <= result and result <= high

    if x < low:
        return low
    if x > high:
        return high
    return x

fn main():
    print(clamp(150, 0, 100))
```

Locals infer their types. Indentation groups statements. There are no semicolons, ownership annotations, or pointers in this version.

## Learn Clack

Start with [the Clack Handbook](docs/README.md) or go directly to:

- [Installation and your first program](docs/getting-started.md).
- [Step-by-step tutorials](docs/tutorials/README.md), including a parallel data project and your own libraries.
- [Quick reference](docs/quick-reference.md) and [full language reference](docs/reference/README.md).
- [Built-ins and standard libraries](docs/libraries.md), [cookbook](docs/cookbook.md), and [common errors](docs/errors.md).
- [CLI reference](docs/cli.md), [FAQ](docs/faq.md), and [compiler internals](docs/internals.md).

## Run it

You need Python 3.11 or newer and a C11 compiler with POSIX threads, such as GCC or Clang on Linux or macOS.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m clack run examples/hello.clack
```

The compiler uses Python and Z3. The resulting executable uses neither Python nor Z3.

```sh
# Check types, arithmetic safety, contracts, and loop termination.
.venv/bin/python -m clack check examples/contracts.clack

# Save verification conditions in SMT-LIB format for inspection.
.venv/bin/python -m clack check examples/contracts.clack --proof-dir build/proofs

# Produce a native executable.
.venv/bin/python -m clack build examples/parallel.clack -o build/parallel
./build/parallel

# Inspect the generated C.
.venv/bin/python -m clack emit-c examples/arrays.clack -o build/arrays.c
```

Activate the virtual environment to use the shorter `clack` command.

## Parallel work

Independent calls go in a `parallel:` block:

```clack
fn sum4(values: int[4]) -> int:
    requires 0 <= values[0] and values[0] <= 1000000
    requires 0 <= values[1] and values[1] <= 1000000
    requires 0 <= values[2] and values[2] <= 1000000
    requires 0 <= values[3] and values[3] <= 1000000
    ensures 0 <= result and result <= 4000000
    return values[0] + values[1] + values[2] + values[3]

fn main():
    parallel:
        left = sum4([10, 20, 30, 40])
        right = sum4([1, 2, 3, 4])
    print(left + right)
```

Each call runs as a native thread, and the block waits for all results. Arguments are values; a worker cannot change another worker's data. The compiler rejects dependencies between jobs in the same block. Use another block or a normal statement when one job needs an earlier result.

This makes small independent jobs easy to express. Thread creation has a cost, so larger jobs are the intended use. This prototype has no worker pool, GPU backend, or automatic speedup guarantee.

## Data without a type puzzle

```clack
type Point:
    x: int
    y: int

fn main():
    point = Point(3, 4)
    values = [10, 20, 30, 40]
    values[1] = point.x
    print(values[1])
```

`int` is a signed 64-bit integer. `bool` has `true` and `false`. Records group named fields. Arrays have a fixed element type and length, such as `int[4]`. Records and arrays are passed and copied by value. Array access must be proved in bounds before compilation.

Function inputs are immutable. Local bindings can be reassigned; local array elements can be changed. Record fields are immutable: build a replacement record when changing a field.

## Reuse a library

```clack
from std.math import max, clamp
from std.array import sum4

fn main():
    print(max(12, 7))
    print(clamp(150, 0, 100))
    print(sum4([10, 20, 30, 40]))
```

The bundled helpers are verified Clack source. You can also import functions and records from your own files, such as `from helpers import twice` for a neighboring `helpers.clack`. Library scopes remain separate, and imported declarations go through the same checks as the entry program. See the [library catalog](docs/libraries.md) and [library tutorial](docs/tutorials/08-libraries.md).

## What “checked” means

Every build checks all functions. Z3 must establish that:

- Arithmetic stays within signed 64-bit bounds, and division is defined.
- Array indices stay in bounds.
- Calls satisfy the callee's `requires` clauses.
- Returned values satisfy the function's `ensures` clauses.
- Every `assert` follows from the current facts.
- Loop invariants hold initially and remain true, and a `decreases` measure establishes termination.

An unproved obligation, solver timeout, or unsupported feature stops compilation. There is no unchecked build switch.

These are proofs against the written contracts and the implemented model. They do not prove that a contract captures your intent, that the compiler is bug-free, or that the operating system will provide unlimited memory or threads. The compiler, Z3, C compiler, and native platform remain trusted. SMT-LIB exports are verification conditions, not independently checked proof certificates.

## What exists today

The current compiler supports functions, conditionals, loops, assertions, records, fixed arrays, source-library imports, signed integer and Boolean expressions, and independent parallel calls. It emits C11 and builds with optimization and POSIX threads.

Native execution is a foundation for C-like performance, not evidence that every Clack program matches C or Rust. No broad performance claim has been established.

One local experiment with 10 million iterations of an integer arithmetic kernel measured **41.7 ms for Clack and 43.0 ms for C**. Two Clack jobs measured **89.1 ms sequentially and 41.7 ms in parallel** (five-run medians). See the [reproducible benchmark and recorded samples](benchmarks/README.md). These measurements cover one workload on this machine.

Dynamic collections, strings, floating-point types, generics, recursion, foreign-function calls, and shared-memory concurrency are future work. This first implementation is deliberately small enough to inspect and test.

Read [the language guide](docs/language.md), [verification model](docs/verification.md), and [design direction](docs/design.md). Try the files under [examples](examples/); programs in `examples/rejected/` demonstrate errors the compiler should catch.

## Compiler development

Run the parser, verification, and native execution regressions with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The native tests exercise real POSIX threads and the synchronous fallback when thread creation fails. The source is MIT licensed.

Check tutorial outputs, local documentation links, and synchronized source listings with:

```sh
.venv/bin/python tools/check_docs.py
```
