# Libraries and imports

[Handbook](README.md) · [Library tutorial](tutorials/08-libraries.md) · [Function reference](reference/functions-control-flow.md)

Clack supports source libraries: files containing functions, records, and imports that another program can reuse. The compiler includes their source in the same verification and native compilation process as the entry file. `std.array` also exposes seven compiler-implemented array operators with the same explicit import syntax.

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

Imports are explicit. The names in the import become available in that source file. An imported source function is called with ordinary call syntax and can also be used as a job in a `parallel:` block. The array operators described below use call syntax too, but must be called inside a worker function when used in parallel work.

## Built-in functions

These two functions are available without an import:

| Function | Input | Result and behavior |
| --- | --- | --- |
| `print(value)` | One `int`, `bool`, or `text` | Prints the value and a newline. Only `main` may call it. It produces no assignable value. |
| `len(value)` | A fixed array or `text` | Returns its length as an `int`: array elements or UTF-8 text bytes. Array length is part of the type. |

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

## `std.array`: any supported fixed length

Import `sum`, `all`, `any`, and `count` for reductions that accept any supported nonempty fixed-array length:

<!-- clack:file=../examples/reductions.clack -->
```clack
from std.array import sum, all, any, count

fn main():
    values = [1, 2, 3, 4, 5]
    flags = [true, false, true]
    print(sum(values))
    print(all(flags))
    print(any(flags))
    print(count(flags))
```

Run `clack run examples/reductions.clack`. Output:

```text
15
false
true
2
```

| Operator | Input | Result |
| --- | --- | --- |
| `sum(values)` | Any nonempty `int` array | Exact left-to-right integer sum |
| `minimum(values)` | Any nonempty `int` array | Smallest element |
| `maximum(values)` | Any nonempty `int` array | Largest element |
| `all(values)` | Any nonempty `bool` array | Whether every element is true |
| `any(values)` | Any nonempty `bool` array | Whether at least one element is true |
| `count(values)` | Any nonempty `bool` array | Number of true elements, from zero through `len(values)` |
| `fill(value, count)` | An `int` or `bool` value; a positive integer literal count | A fixed array with every element initialized to that value |

The array type supplies the length. `sum([1, 2, 3])` and `sum([1, 2, 3, 4, 5])` are both valid; no user-defined generic signature or new annotation syntax is needed. The accepted array-length limit remains `1` through `1000000`. This does not promise that a very large array fits a native stack or verifies quickly.

`sum` must prove that **every cumulative addition** fits signed 64-bit range. `sum([9223372036854775807, 1, -1])` is rejected even though its final mathematical sum fits. Arrays received as parameters may need preconditions to establish the required bounds. `count` counts Boolean values, not arbitrary integers, and `all` and `any` require Boolean arrays too.

`minimum` and `maximum` compare elements without arithmetic, so both accept the full signed 64-bit element range. They return an existing element. The two-input source helpers remain `std.math.min(a, b)` and `std.math.max(a, b)`; the array operators use different names so the imports can coexist.

Arguments are evaluated before the reduction. For example, `all([false, 1 / 0 > 0])` is rejected: constructing the second array element would divide by zero. After construction, the pure array value is read by the reduction; it cannot be modified by the operation.

These seven names are **compiler operators**, registered in [arrayops.py](../clack/arrayops.py), modeled by the [verifier](../clack/verifier.py), and lowered to native loops by the [C backend](../clack/codegen.py). They are part of the trusted compiler implementation rather than source functions whose bodies are checked. Reductions construct element-level logical terms and sum-prefix obligations, so verification work grows with array length and solver complexity. `fill` has a constant-array logical representation; reducing its result can still require element-level work. Runtime loops need no Python or solver.

These operators are currently allowed only in executable expressions. Proof annotations still permit only the `len` call; assign an operator's result to a local and assert a property about that local. A direct job such as `parallel: total = sum(values)` is also unsupported: jobs require source functions. A typed worker may call an array operator in its body and participate in a parallel block normally.

## Fill an array and find its bounds

`fill(7, 5)` infers `int[5]`, and `fill(true, 4)` infers `bool[4]`. The count must be a decimal integer literal between `1` and `1000000`. A variable such as `fill(0, size)` or an expression such as `fill(0, 2 + 3)` is rejected even if its value could be proved constant. This keeps the array type fixed during compilation; `fill` does not allocate a dynamically sized collection.

The value expression is evaluated once, then copied to each element. Copies and updates retain the usual array value semantics:

<!-- clack:file=../examples/tutorials/08-array-operators.clack -->
```clack
from std.array import fill, minimum, maximum, sum, all, count

fn main():
    values = fill(7, 5)
    changed = values
    changed[2] = -3
    print(len(values))
    print(minimum(changed))
    print(maximum(changed))
    print(sum(changed))
    print(values[2])
    flags = fill(true, 4)
    flags[1] = false
    print(count(flags))
    print(all(flags))
```

Run `clack run examples/tutorials/08-array-operators.clack`. It prints `5`, `-3`, `7`, `25`, `7`, `3`, and `false`, one per line. Changing `changed[2]` leaves `values[2]` equal to `7`.

## `std.array`: fixed-size source helpers

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

These functions remain available for compatibility and can be direct parallel jobs because they have ordinary source bodies and contracts. Use `sum`, `all`, or `any` when the array's length differs. General user-defined generic functions, dynamic collections, and `sort` remain unimplemented.

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

You can import source functions, declared native bindings, and record types. Imported definitions keep their own module's function and type bindings, so two libraries can each have a private helper named `calculate` without those helpers colliding in the native program. Only explicitly selected names enter the importing file's scope. There is no explicit `public` or `private` keyword: a declaration can be selected by an import, while unselected helper names stay out of the caller's scope.

Import names cannot collide with another imported binding or an existing declaration. Clack currently has no import aliases, wildcard imports, or module objects. Reorganize the selected names or rename a helper when needed. Import cycles are rejected; organize dependencies as a directed acyclic graph.

Record types remain associated with their defining module. Use their exported constructors and annotations through explicit imports; a separately declared record with identical fields is still a different nominal type.

## Verification and distribution

The compiler verifies all declarations in every loaded source module, including helpers the entry program does not call. Importing a library does not trust a precompiled binary or accept its postconditions without checking its body. A malformed or unproved library can therefore reject a build even if the particular failing function is unused.

Ordinary imported source functions retain the normal purity rule: only the entry program's `main` may print or make native calls. Library files may not define `main`. A library can export explicit native declarations and their confined C providers; their implementations are reported as unproved and can be called only from main. A source library can use `parallel:` internally, but recursive function calls and import cycles remain unsupported. See [native bindings](native.md) for the boundary used by optional terminal UI libraries.

Diagnostics for imported code identify its original file and source line. `--proof-dir` exports the combined program's obligations; their metadata identifies the relevant source files. The same trusted compiler and solver described in the [verification model](verification.md) remain involved.

Distribute local libraries as `.clack` source files beside the program or in the expected subdirectories, including any declared native `.c` providers. There is no package version resolver, lockfile, separate library binary format, or third-party dependency registry yet. The bundled standard-library sources are included in the Python compiler distribution.
