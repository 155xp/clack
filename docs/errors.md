# Understanding compiler errors

A diagnostic starts with `file:line:column: error:` and usually prints the relevant source line. For a loaded module, the file and line identify its original source. Syntax and type errors describe a rule the program violates. Verification errors begin with `cannot prove` and describe the obligation that failed.

A `counterexample` is a model where that obligation is false. At a function boundary it can expose a real allowed input that breaks the claim. Inside a loop it may instead show that the invariant admits states the real loop never reaches. Read the claim first, then decide whether to fix the implementation, the specification, or the facts supplied to the verifier.

The snippets below are fragments unless described as complete programs. Keep a `fn main():` entry point in files you check. All functions are checked, even unused ones.

## Arithmetic may overflow

This function rejects with `cannot prove integer arithmetic stays within signed 64-bit range`:

```clack
fn next(x: int) -> int:
    return x + 1
```

An `int` input may be `9223372036854775807`. If the function is meant only for smaller values, state that condition:

```clack
fn next(x: int) -> int:
    requires x < 9223372036854775807
    ensures result == x + 1
    return x + 1
```

Every caller must now prove the condition. If all integer inputs must be accepted, choose a different behavior, such as returning the maximum unchanged. Do not add an arbitrary bound just to silence the verifier. Also inspect intermediate expressions: `(x + 1) - 1` can overflow even though the final mathematical answer equals `x`.

## A precondition is missing at a call

After defining the repaired `next`, `next(9223372036854775807)` fails with `cannot prove precondition of next`. The diagnostic points to the call, while the claim also identifies the precondition's source line.

Use an allowed input, prove an appropriate guard, or change the function's intended behavior. Adding an `assert` of the missing fact is not an escape: Clack must prove the assertion too. `main` cannot have `requires`, because the executable entry point must work without assumed caller conditions.

## A postcondition does not describe the returned value

```clack
fn identity(x: int) -> int:
    ensures result == x + 1
    return x
```

This fails with `cannot prove postcondition of identity`. To implement identity, change the promise to `ensures result == x`. To implement increment, change the body and provide the necessary overflow precondition. The compiler cannot choose which intent you meant.

Postconditions also matter to callers. A helper without an `ensures` clause may be safe but tell its caller very little about its result. Add useful, true summaries when later reasoning needs them.

## An index may be outside its array

```clack
fn read(values: int[3], index: int) -> int:
    return values[index]
```

This fails with `cannot prove array index is in bounds`. Repair the input contract:

```clack
fn read(values: int[3], index: int) -> int:
    requires 0 <= index < len(values)
    ensures result == values[index]
    return values[index]
```

The valid indices are `0`, `1`, and `2`. The index `len(values)` is already one beyond the end. Writes are checked too, using the claim `array update is in bounds`. An index inside a contract must be valid under the earlier assumptions; proof annotations do not turn arrays into infinite sequences.

## Division must be defined

`return x / divisor` must establish `divisor != 0`. For unrestricted integer numerators, also exclude `x == -9223372036854775808 and divisor == -1`, which overflows signed division. The same exceptional pair is rejected for `%`, matching the C backend's requirements.

Use a precondition or a branch that implements the desired exceptional behavior. Short-circuit guards can establish safety: `x == 0 or 10 / x > 0` skips the division at zero; `x != 0 or 10 / x > 0` does not.

## A value is not returned on every path

```clack
fn nonnegative(x: int) -> int:
    if x >= 0:
        return x
```

The error is `function 'nonnegative' must return a int on every path`. Add the missing behavior, for example `return 0` after the conditional. The check follows the source control flow; a value function needs explicit returns on all syntactic paths that reach its end. Main returns no value and may simply end.

## A local exists on only one branch

This fragment fails with `'answer' is not defined on every path before use`:

```clack
if ready:
    answer = 42
print(answer)
```

Assign `answer` before the `if`, or assign it in both branches. A local first created inside a loop is also unavailable after the loop, since the loop might run zero times. Locals keep their inferred type: replacing an integer with a Boolean is a type error, not a dynamic type change.

## A parameter or record field is changed

Assigning to a parameter reports `parameter 'x' is immutable; assign to a new local variable`. Copy it first:

```clack
copy = values
copy[0] = 99
```

This is also the way to update an array parameter's contents locally. Arrays have value semantics, so changing `copy` does not change `values`.

Writing `point.x = 5` reports `record fields are immutable; create a replacement record`. Given a two-field `Point`, write `point = Point(5, point.y)` instead. Parameters remain immutable even if their type is a record.

## A loop has no annotations

The parser requires a loop body to start with `invariant` and then `decreases`. For a bounded counter:

```clack
i = 0
while i < n:
    invariant 0 <= i <= n
    decreases n - i
    i = i + 1
```

This fragment needs a surrounding function with a suitable bound such as `requires 0 <= n <= 1000000`. The invariant describes the allowed loop states. The measure explains why iteration finishes.

## An invariant is too weak or false

`loop invariant holds on entry` means the property is not established before the first iteration. For example, `invariant i > 0` cannot describe a counter initialized to zero.

`loop invariant is preserved` means the body may leave the stated set of states. An invariant saying `i == 0` cannot survive `i = i + 1`.

A safety or postcondition failure inside or after a loop can instead mean useful facts were omitted. Clack forgets the old values of modified locals before reasoning about an arbitrary iteration. It cannot use the first iteration's `i == 0` forever. For a counter, both `0 <= i` and `i <= n` are often needed. For a sum or count, describe how the accumulator relates to the progress variable as well. A counterexample at this stage is evidence about the current invariant, not automatically a reachable execution trace.

## A loop may not make progress

`loop termination measure is nonnegative` means the measure may start an iteration below zero. `loop termination measure strictly decreases` means a continuing body may leave the measure unchanged or increase it.

For `while i < n`, `decreases n - i` works when `i` increases each iteration and the invariant establishes the needed bounds. `decreases i` does not work for that same body. A constant measure cannot establish repeated progress. Returning from inside the loop still needs to establish the function's postcondition.

## Parallel jobs depend on each other

With a suitable `next` function, this fragment rejects:

```clack
parallel:
    first = next(10)
    second = next(first)
```

The error is `parallel jobs must be independent; input references result 'first'`. Move `second = next(first)` after the block. A block's arguments all come from its input state; sibling results become available after all jobs finish.

The same restriction applies even if `first` was assigned before the block. Use a separate input name when you intend to pass the previous value. Duplicate targets report `parallel jobs need distinct result names`. Each job must call a user function; printing and record constructors are not jobs. Printing inside a worker reports `print is allowed only in main; worker functions are pure`.

## The solver reports unknown or times out

A message ending with `strict mode rejects unknown results` means the obligation was not established. It is different from a `counterexample`: the solver has not necessarily shown the program wrong.

First simplify complicated arithmetic, add a missing useful invariant, and state the needed helper postcondition. For a query that needs more time, try:

```sh
clack check program.clack --timeout-ms 15000 --proof-dir build/investigation
```

The timeout is per query. There is no option to accept an unproved result. See the [CLI guide](cli.md) for inspecting the exported conditions.

## The construct is not implemented

Text requires double-quoted JSON-style literals; unsupported quoting reports `use double-quoted JSON text literals`. Text concatenation, comparison, indexing, text arrays, and `len(text)` are not supported. Nondecimal and floating-point literals report `only decimal integer literals are supported`. Recursive calls report `recursive call cycle ... is unsupported; use a loop with decreases`.

Clack also has no dynamic arrays, `for`, `break`, `continue`, exceptions, or user-defined operators. These require language work rather than an alternative flag. Check the [current reference](reference/README.md) and [design direction](design.md) before assuming familiar syntax is available.

Native calls are explicit main-only statements or direct assignments. `native calls belong only in main's direct assignments or unit call statements` means a call was nested, used in a condition, or attempted from a helper. Assign a native return to a local first, then check that local before arithmetic. The [native guide](native.md) explains the supported ABI and why native implementations are unproved.

## An import cannot be loaded or does not export the requested name

Use an explicit import such as `from helpers import twice`. A local import looks for `helpers.clack` beside the importing file, not beside the shell's current directory. A dotted local module such as `tools.numeric` follows the path `tools/numeric.clack`. Check the module path and the exact name of the function or record you are importing.

Library files define reusable declarations and must not define `main`. Only the entry program has an entry point. Wildcard imports and aliases are not supported. Bundled `std` modules come from the compiler package; placing a local file under a `std` directory does not override them.

`cyclic module import` means files depend on each other in a loop. Move shared helpers into a separate module that both can import. `import 'name' conflicts with another declaration or import` means that name is already present in the importing file; use distinct exported names rather than importing two meanings under one name.

If an imported function fails verification, repair its implementation or contract just as you would for a function in the entry file. Every loaded declaration is checked, including unused declarations, so removing a call to a bad library function does not make that loaded library valid. See [libraries and modules](libraries.md) for the available modules and exact helper signatures.

[Handbook](README.md) · [CLI](cli.md) · [Verification model](verification.md)
