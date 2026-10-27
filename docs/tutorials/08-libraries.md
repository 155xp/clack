# 8. Reuse code with libraries

[Previous: Inventory project](07-project.md) · [Tutorial index](README.md) · [Next: Text and byte lengths](09-text.md)

The goal of this lesson is to use supplied helpers and move your own function into another file. The earlier lessons defined every helper in place so you could read a complete program. Imports let you reuse those definitions without copying their bodies.

## Import a few names

<!-- clack:file=../../examples/tutorials/08-libraries.clack -->
```clack
from std.math import min, max, abs, clamp
from std.array import sum4
from tutorial_helpers import twice

fn main():
    total = sum4([20, 35, 0, 45])
    bounded = clamp(total, 0, 80)
    bonus = twice(6)
    parallel:
        left = abs(-7)
        right = max(9, 12)
    print(total)
    print(bounded)
    print(min(left, right))
    print(bonus)
```

This program imports supplied functions from `std.math` and `std.array`, plus one function from a local file. Create `examples/tutorials/tutorial_helpers.clack` beside it with this content:

<!-- clack:file=../../examples/tutorials/tutorial_helpers.clack -->
```clack
fn twice(value: int) -> int:
    requires -100 <= value <= 100
    ensures result == 2 * value
    return value + value
```

The helper file defines functions but does not define main. The importing program supplies the entry point. The included files already have this layout, so run from the repository root:

```sh
clack run examples/tutorials/08-libraries.clack
```

The exact output is:

```text
100
80
7
12
```

## Understand the supplied helpers

`sum4` sums exactly four integers and promises their exact sum. `sum2`, `sum3`, and `sum8` cover the other supplied fixed sizes. These named source functions remain supported. Clack also provides `from std.array import sum` for any supported fixed length, so a five-element array does not need a new helper. See the [reduction example](../../examples/reductions.clack) for `sum`, `all`, `any`, and `count`.

Each intermediate addition must fit into a signed 64-bit integer. A final sum fitting is not enough if an earlier prefix would overflow. The helpers state those requirements in their contracts, so callers must establish them just as they establish requirements for their own functions. The small literal array in this lesson makes those facts straightforward.

`min` and `max` return one of their two input values. `abs` returns a nonnegative magnitude and excludes the smallest signed integer, whose positive magnitude cannot fit. `clamp(value, low, high)` restricts a value to the supplied interval and requires `low <= high`. Here the total is one hundred and the upper limit is eighty, so bounded becomes eighty.

The functions used in this lesson are implemented in Clack source and verified with the program. The new length-independent reductions are different: they are compiler operators modeled by the verifier and emitted as native loops. Both groups require explicit imports. Only `print` and `len` are available without an import.

## Fill an array and select its smallest or largest value

<!-- clack:file=../../examples/tutorials/08-array-operators.clack -->
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

Run `clack run examples/tutorials/08-array-operators.clack`. The output is `5`, `-3`, `7`, `25`, `7`, `3`, and `false`, one per line.

`fill(7, 5)` creates an `int[5]` initialized to seven. The value is evaluated once, and the count is a decimal integer literal from `1` through `1000000`. A runtime length or an expression such as `2 + 3` is not accepted there. `fill(true, 4)` similarly creates a `bool[4]`. These are fixed arrays with normal value semantics: changing `changed[2]` leaves the original `values[2]` equal to seven.

`minimum` and `maximum` work on any supported nonempty integer array. They compare values without adding or negating them, so they support the full signed range. Their names are distinct from the two-argument scalar helpers `std.math.min` and `std.math.max`. Like the other compiler array operators, they belong in executable statements, not inside proof annotations or as direct parallel jobs. The [library catalog](../libraries.md) lists their complete rules and verification costs.

## Reuse your own functions

`from tutorial_helpers import twice` looks for `tutorial_helpers.clack` relative to the importing file's directory. You do not need to run from that directory or change the process search path. Imports name specific functions or record types; they do not introduce a module object. There is no alias syntax in the current language.

The local helper has the same parameter types and contract it would have inside the main file. Its body is checked, and its postcondition describes the result at each call. Imported pure helpers can also be parallel jobs: `abs` and `max` in this example receive independent values and return results before main prints them.

## Exercises

1. Change the array to `[10, 20, 30, 40]`. What changes in the output?
2. Replace `sum4` with `sum3` without changing the array. Why does the call fail?
3. Move a function you wrote in an earlier lesson into another local module. What belongs in the importing file?

<details>
<summary>Answers</summary>

1. Nothing changes: both arrays total one hundred.
2. `sum3` accepts `int[3]`, while the supplied value is `int[4]`. Import the intended helper and match its parameter type.
3. Keep the helper definition and any record types or imports it needs in its module. Do not define main there. Import the required names into the program containing main, then call them normally.

</details>

The [library reference](../libraries.md) lists available helpers and import rules. The first seven lessons remain useful standalone examples; this lesson adds a way to share their building blocks.
