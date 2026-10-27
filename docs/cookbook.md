# Clack cookbook

[Handbook](README.md) · [Tutorials](tutorials/README.md) · [Error guide](errors.md)

These patterns show how to write ordinary Clack functions. `print` and `len` are available without imports; `std.math` and `std.array` supply explicitly imported source helpers. `std.array` also supplies the compiler-implemented reductions `sum`, `all`, `any`, and `count` for any supported fixed length. The [library catalog](libraries.md) explains that distinction. You can reuse these operations or study the functions below to understand their contracts. Each example below is a complete program you can save in its own `.clack` file.

## Minimum and maximum

Choosing an existing input does not introduce integer overflow, so these functions need no input bound:

```clack
fn minimum(a: int, b: int) -> int:
    ensures result <= a and result <= b
    ensures result == a or result == b
    if a < b:
        return a
    return b

fn maximum(a: int, b: int) -> int:
    ensures result >= a and result >= b
    ensures result == a or result == b
    if a > b:
        return a
    return b

fn main():
    print(minimum(12, 7))
    print(maximum(12, 7))
```

Output: `7`, then `12` on the next line. The two postconditions describe both ordering and membership in the input pair. A function returning an unrelated very small number would fail the second promise of `minimum`.

## Absolute value with an explicit domain

The smallest signed 64-bit integer has no positive counterpart in the same type. State the supported domain:

```clack
fn absolute(x: int) -> int:
    requires x > -9223372036854775808
    ensures result >= 0
    ensures result == x or result == -x
    if x < 0:
        return -x
    return x

fn main():
    print(absolute(-42))
```

Output: `42`. The mathematical `-x` in the postcondition does not itself overflow, but the executable negation still needs the precondition. A total API could instead return a tagged result type once tagged unions are implemented.

## Clamp a value to an interval

```clack
fn clamp(x: int, low: int, high: int) -> int:
    requires low <= high
    ensures low <= result <= high
    ensures (x < low and result == low) or (x > high and result == high) or (low <= x <= high and result == x)
    if x < low:
        return low
    if x > high:
        return high
    return x

fn main():
    print(clamp(150, 0, 100))
    print(clamp(25, 0, 100))
```

Output: `100`, then `25`. The interval promise alone would allow returning `low` for every input. The second postcondition states how the original value should be treated.

## Guard division with short-circuit logic

```clack
fn divides_100(x: int) -> bool:
    ensures result == (x != 0 and 100 % x == 0)
    return x != 0 and 100 % x == 0

fn main():
    print(divides_100(0))
    print(divides_100(25))
    print(divides_100(3))
```

Output: `false`, `true`, `false`. The right operand of `and` is reached only when `x != 0`. The verifier uses that guard to establish that remainder is defined. Reversing the operands would attempt the remainder before checking zero.

## Change a copy of an array

```clack
fn replace_first(values: int[3], value: int) -> int[3]:
    ensures result[0] == value
    ensures result[1] == values[1]
    ensures result[2] == values[2]
    changed = values
    changed[0] = value
    return changed

fn main():
    original = [10, 20, 30]
    changed = replace_first(original, 99)
    print(original[0])
    print(changed[0])
```

Output: `10`, then `99`. Assigning `values` to a local produces a value copy that may be updated. The input parameter remains immutable, and the caller's `original` keeps its contents.

## Read several results from a function

Use a record instead of output parameters or mutable shared state:

```clack
type Division:
    quotient: int
    remainder: int

fn divide(a: int, b: int) -> Division:
    requires b != 0
    requires a != -9223372036854775808 or b != -1
    ensures result.quotient == a / b
    ensures result.remainder == a % b
    return Division(a / b, a % b)

fn main():
    result_pair = divide(17, 5)
    print(result_pair.quotient)
    print(result_pair.remainder)
```

Output: `3`, then `2`. Record results also work in a `parallel:` block. See the [parallel tutorial](tutorials/05-parallel-work.md) and [project](tutorials/07-project.md) for combining independent record-valued computations.

## Visit array indices

```clack
fn main():
    values = [10, 20, 30]
    for i in range(len(values)):
        print(values[i])
```

Output: `10`, `20`, `30`. The compiler supplies index bounds and termination. `range(start, stop)` starts at an explicit integer and still excludes the stop. For an accumulator, add an invariant relating the changing value to completed iterations, as shown in the [loop tutorial](tutorials/04-loops.md).

## Pick the right next pattern

For summing any supported fixed integer array, import `sum` from `std.array`; the [reduction example](../examples/reductions.clack) also demonstrates Boolean reductions. To write your own algorithm, start with [the functions tutorial](tutorials/02-functions-contracts.md) and [array tutorial](tutorials/03-records-arrays.md), then learn to carry bounds through [a loop invariant](tutorials/04-loops.md). For failures, prefer a guard or a meaningful input contract; an `assert` cannot turn an unproved fact into a trusted assumption.
