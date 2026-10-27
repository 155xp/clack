# Clack quick reference

[Handbook](README.md) · [Full reference](reference/README.md)

This page summarizes accepted Clack 0.3 syntax. Except where a complete program is shown, code blocks are fragments to place in an appropriate function.

## Program and functions

```clack
fn double(x: int) -> int:
    requires -1000000 <= x <= 1000000
    ensures result == x * 2
    return x + x

fn main():
    print(double(21))
```

Only `main` may omit the result annotation and perform output. Other functions must return their declared value on every path. Inputs are immutable. Functions may be declared in any order, but recursive call cycles are rejected.

## Values and bindings

| Write | Meaning |
| --- | --- |
| `number = 42` | Infer an `int` local |
| `number = number + 1` | Reassign that local with the same type |
| `ready = true` | Infer a `bool` local |
| `title = "Clack"` | Infer an immutable `text` value |
| `values = [10, 20, 30]` | Infer `int[3]` |
| `flags = [true, false]` | Infer `bool[2]` |
| `values[0]` | Read the first element |
| `values[1] = 7` | Update a local array |
| `copy = values` | Copy an array value |

`int` ranges from `-9223372036854775808` to `9223372036854775807`. Array lengths are part of their types. Empty arrays, nested arrays, and arrays of records are not implemented.

## Operators

| Kind | Operators |
| --- | --- |
| Arithmetic | `+`, `-`, `*`, `/`, `%`, unary `+` and `-` |
| Comparison | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| Boolean | `and`, `or`, `not` |
| Grouping and access | `(expression)`, `record.field`, `array[index]` |

`/` truncates integer division toward zero. `%` has the dividend's sign for a nonzero remainder. `and` and `or` short-circuit. `0 <= x <= 10` is a chained comparison. Booleans and integers do not implicitly convert to one another. Equality applies to scalar values; compare record fields or array elements individually.

## Records

```clack
type Point:
    x: int
    y: int

fn main():
    point = Point(3, 4)
    moved = Point(point.x + 1, point.y)
    print(moved.x)
```

Constructors take positional fields in declaration order. Record fields are immutable; construct a replacement value to update them. Records may contain other records and scalar arrays, but their layout cannot be recursive.

## Decisions and loops

Fragment:

```clack
if score < 0:
    return 0
elif score > 100:
    return 100
else:
    return score
```

A complete loop example:

```clack
fn count_to(n: int) -> int:
    requires 0 <= n <= 1000000
    ensures result == n
    total = 0
    for i in range(n):
        invariant total == i
        total = total + 1
    return total

fn main():
    print(count_to(10))
```

`for i in range(stop)` visits `0` through `stop - 1`; `range(start, stop)` uses an explicit start. Bounds are evaluated once. The index is immutable, cannot shadow an existing binding, and is available only inside the body. Empty or reversed ranges do nothing. Index bounds and termination are automatic; optional `invariant` lines describe changing values such as `total` above.

Use `while condition:` for other loop shapes. A while body begins with one or more `invariant` lines followed by one `decreases` line. `break`, `continue`, range steps, and range values outside a for header are not implemented.

## Contracts

| Annotation | Who must establish it? | Meaning |
| --- | --- | --- |
| `requires condition` | Every caller | Allowed inputs |
| `ensures condition` | Every return path | Promised result; `result` names the returned value |
| `assert condition` | Compiler at that statement | A fact that must follow from current knowledge |
| `invariant condition` | Loop entry and continuing iterations | Facts available at an arbitrary loop head |
| `decreases expression` | Continuing loop iterations | Nonnegative integer measure that strictly decreases |

Proof arithmetic uses mathematical integers. Executable arithmetic must keep **every intermediate** within signed 64-bit bounds. Division and indexing must remain well-defined in both contexts. Proof expressions can call only `len`, not arbitrary helper functions or constructors.

## Parallel work

Fragment, using the `count_to` declaration above:

```clack
parallel:
    first = count_to(100000)
    second = count_to(200000)
print(first + second)
```

The block waits for all results. Each job is a call to a user function. All arguments see the incoming state; they must not mention any result name from the block. Values are copied, and workers cannot print. The caller runs the last job while POSIX threads run the preceding jobs, with synchronous fallback if thread creation fails. A single job runs directly. A block does not guarantee a speedup.

## Built-ins and commands

| Function | Use |
| --- | --- |
| `print(value)` | Print one `int`, `bool`, or `text`, only in `main` |
| `len(array)` | Return a fixed array's length |

Import the standard helpers explicitly:

```clack
from std.math import min, max, abs, clamp
from std.array import sum, all, any, count

fn main():
    print(max(12, 7))
    print(sum([1, 2, 3, 4, 5]))
    print(count([true, false, true]))
```

`sum` accepts any supported nonempty integer array and checks every partial addition. `all`, `any`, and `count` accept Boolean arrays; `count` counts true elements. These four imported compiler operators are modeled directly and emitted as native loops. They cannot appear in proof annotations or as direct parallel jobs, though a source worker function can use them. The fixed-size source helpers remain supported. User-defined generic functions and `sort` are not implemented. Local libraries still use the same import syntax, such as `from helpers import twice`. See [the library catalog](libraries.md) for details.

```sh
clack check program.clack
clack run program.clack
clack build program.clack -o build/program --timings
clack emit-c program.clack -o build/program.c
```

See the [CLI reference](cli.md) for proof exports, solver timeouts, and C compiler selection.

## Explicit native boundary

`native "terminal.c"` includes a module-relative C provider. `extern fn title(value: text) -> unit = "clack_demo_title"` declares a main-only native call. C implementations are trusted and unproved, their returns are unconstrained typed values, and the CLI reports the boundary. See [text and native bindings](native.md) for the complete example, ABI, path rules, and call restrictions.
