# Libraries and imports

[Handbook](README.md) · [Library tutorial](tutorials/08-libraries.md) · [Function reference](reference/functions-control-flow.md)

Clack supports source libraries: files containing functions, records, and imports that another program can reuse. The compiler includes their source in the same verification and native compilation process as the entry file.

## Use a standard helper

```clack
from std.math import min, max, abs, clamp
from std.array import sum4, all4

fn main():
    print(min(12, 7))
    print(max(12, 7))
    print(abs(-42))
    print(clamp(150, 0, 100))
    print(sum4([10, 20, 30, 40]))
    print(all4([true, true, false, true]))
```

Output:

```text
7
12
42
100
100
false
```

Imports are explicit. The names in the import become available in that source file. An imported function is called with ordinary call syntax and can also be used as a job in a `parallel:` block.

## Built-in functions

These two functions are available without an import:

| Function | Input | Result and behavior |
| --- | --- | --- |
| `print(value)` | One `int` or `bool` | Prints the value and a newline. Only `main` may call it. It produces no assignable value. |
| `len(values)` | A fixed array | Returns its length as an `int`. Length is part of the array type. |

`len` is also allowed in proof expressions. Other function calls, including standard-library helpers, are not allowed inside `requires`, `ensures`, `assert`, `invariant`, or `decreases`. Write properties in terms of operators, fields, elements, and `len` instead.

## `std.math`

Source: [math.clack](../clack/stdlib/math.clack).

| Function | Signature | Domain and result |
| --- | --- | --- |
| `min` | `(a: int, b: int) -> int` | Returns the smaller input. All `int` inputs are supported. |
| `max` | `(a: int, b: int) -> int` | Returns the larger input. All `int` inputs are supported. |
| `abs` | `(value: int) -> int` | Returns the nonnegative magnitude. Requires `value > -9223372036854775808`. |
| `clamp` | `(value: int, low: int, high: int) -> int` | Requires `low <= high`. Returns `low` below the interval, `high` above it, and `value` inside it. |

`abs` excludes the smallest signed integer because its positive magnitude cannot fit in `int`. Callers must prove that exclusion, just as they must establish the ordered interval for `clamp`. Standard imports do not bypass safety checks.

## `std.array`

Source: [array.clack](../clack/stdlib/array.clack).

| Function | Signature | Result |
| --- | --- | --- |
| `sum2` | `(values: int[2]) -> int` | Sum of two elements |
| `sum3` | `(values: int[3]) -> int` | Sum of three elements |
| `sum4` | `(values: int[4]) -> int` | Sum of four elements |
| `sum8` | `(values: int[8]) -> int` | Sum of eight elements |
| `all4` | `(values: bool[4]) -> bool` | Whether all four elements are true |
| `any4` | `(values: bool[4]) -> bool` | Whether at least one of four elements is true |

Each sum adds from left to right. Its contract requires every cumulative addition to fit in signed 64-bit range. This permits large inputs when all those intermediate sums are safe; there is no arbitrary small per-element bound. A final sum that fits does not excuse an earlier overflowing partial sum.

Lengths are explicit because Clack does not yet have generic functions. For a five-element array, write a suitably verified helper or compose smaller helpers when their contracts fit your data. There is no generic `sum(values)` or `sort(values)` today.

## Write your own library

Create `helpers.clack` beside your entry file:

```clack
fn twice(x: int) -> int:
    requires -1000000 <= x <= 1000000
    ensures result == x * 2
    return x + x
```

A library file has no `main`. In `app.clack`, import its function:

```clack
from helpers import twice

fn main():
    print(twice(21))
```

Then run `clack run app.clack`. Local module names refer to paths relative to the **importing file's directory**, so `from numeric.tools import twice` looks for `numeric/tools.clack` below that directory. When a library imports another local module, the search starts from that library's directory.

The `std` namespace is reserved for bundled standard-library source. A local directory named `std` cannot replace it. There is no search through the network, environment-wide package registry, or Python packages.

## Module boundaries

You can import functions and record types. Imported definitions keep their own module's function and type bindings, so two libraries can each have a private helper named `calculate` without those helpers colliding in the native program. Only explicitly selected names enter the importing file's scope. There is no explicit `public` or `private` keyword: a declaration can be selected by an import, while unselected helper names stay out of the caller's scope.

Import names cannot collide with another imported binding or an existing declaration. Clack currently has no import aliases, wildcard imports, or module objects. Reorganize the selected names or rename a helper when needed. Import cycles are rejected; organize dependencies as a directed acyclic graph.

Record types remain associated with their defining module. Use their exported constructors and annotations through explicit imports; a separately declared record with identical fields is still a different nominal type.

## Verification and distribution

The compiler verifies all declarations in every loaded source module, including helpers the entry program does not call. Importing a library does not trust a precompiled binary or accept its postconditions without checking its body. A malformed or unproved library can therefore reject a build even if the particular failing function is unused.

Imported functions retain the normal purity rule: only the entry program's `main` may print. Library files may not define `main`. A library can use `parallel:` internally, but recursive function calls and import cycles remain unsupported.

Diagnostics for imported code identify its original file and source line. `--proof-dir` exports the combined program's obligations; their metadata identifies the relevant source files. The same trusted compiler and solver described in the [verification model](verification.md) remain involved.

Distribute local libraries as `.clack` source files beside the program or in the expected subdirectories. There is no package version resolver, lockfile, separate library binary format, C FFI, or third-party dependency registry yet. The bundled standard-library sources are included in the Python compiler distribution.
