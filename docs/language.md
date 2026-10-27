# Language guide

Clack combines plain functions and value types with compile-time contracts and independent parallel calls. This guide gives an overview of the implemented language. Use the [tutorials](tutorials/README.md) for a step-by-step introduction and the [language reference](reference/README.md) for exact rules.

## A small complete program

```clack
fn twice(x: int) -> int:
    requires -1000000 <= x <= 1000000
    ensures result == 2 * x
    return x + x

fn main():
    parallel:
        left = twice(12)
        right = twice(9)
    print(left + right)
```

The program prints `42`. `main` is the entry point. Function parameters and results have explicit types; local bindings infer their types. `requires` describes accepted inputs, and `ensures` describes the returned value. Both jobs receive their own inputs, and the parallel block waits for both before the addition.

Store the program in a `.clack` file. With the compiler installed and the virtual environment activated, use `clack run program.clack`. `clack check program.clack` checks it without running it, and `clack build program.clack -o build/program` creates a native executable. All three commands require successful verification.

## Everyday rules

| Topic | Current rule | Details |
| --- | --- | --- |
| Layout | Consistent space indentation; `#` comments; no semicolons | [Lexical syntax](reference/lexical-syntax.md) |
| Numbers | Signed 64-bit integers; every executable intermediate must fit | [Types and values](reference/types-values.md) |
| Booleans | `true`, `false`, `and`, `or`, `not`; no integer truthiness | [Expressions](reference/lexical-syntax.md) |
| Text | Immutable UTF-8 literals; pass, return, and print; no manipulation API yet | [Text and native bindings](native.md) |
| Data | Named records and nonempty fixed `int[N]` or `bool[N]` arrays | [Types and values](reference/types-values.md) |
| Libraries | Explicit `from module import name` for standard or local definitions | [Library guide](libraries.md) |
| Mutation | Locals may change; parameters and record fields are immutable | [Functions and control flow](reference/functions-control-flow.md) |
| Copies | Assignment, arguments, and results have value semantics | [Types and values](reference/types-values.md) |
| Loops | Counted `for` with automatic progress; `while` with invariants and a decreasing measure | [Control flow](reference/functions-control-flow.md#counted-for-loops) |
| Jobs | Direct independent function calls inside `parallel:` | [Parallel execution](reference/parallelism.md) |
| Output | Only `main` may `print` one integer, Boolean, or text value at a time | [Built-ins](reference/functions-control-flow.md) |

## Proofs in daily code

Annotations use mathematical integers; executable values use signed 64-bit integers. `assert` asks the compiler to prove a fact, rather than trust it. A function's preconditions must hold at every call, and its postconditions must hold on every return path. Array bounds, division safety, and loop termination are checked as well.

A failed proof may reveal a bug, a missing true contract or invariant, or a solver limitation. Timeouts and unknown solver results stop compilation. The [verification reference](reference/contracts-verification.md) explains how to distinguish these cases and what the compiler still trusts.

## Reusing code

Import only the names a program needs:

```clack
from std.math import clamp
from std.array import sum

fn main():
    print(clamp(150, 0, 100))
    print(sum([10, 20, 30, 40]))
```

This prints `100` twice. `sum` accepts any supported fixed integer-array length and proves that every partial addition fits. `all`, `any`, and `count` operate on fixed Boolean arrays. These four operators are modeled directly by the compiler; ordinary source helpers are verified from their bodies.

Local libraries use the same form: `from helpers import twice` loads `helpers.clack` relative to the importing file. Imports bring in checked definitions; all reached source module code is verified, including unused helpers. The [library guide](libraries.md) explains reusable files, source helpers, and compiler operators.

## Continue learning

- Follow the [tutorial sequence](tutorials/README.md) to build and check programs.
- Use the [reference index](reference/README.md) or [complete grammar](reference/grammar.md) to look up syntax.
- Try the [example programs](../examples/) and compare their source with the generated C.
- Read [native bindings](native.md) for the explicit trusted C boundary used by optional terminal UI packages.
- Read the [design direction](design.md) for planned text manipulation, dynamic collections, richer proofs, and broader systems integration. Those proposals are not features accepted by version 0.3.
