# 6. Learn from a rejected program

[Previous: Parallel work](05-parallel-work.md) · [Tutorial index](README.md) · [Next: Inventory project](07-project.md)

The goal of this lesson is to turn a compiler counterexample into a useful design decision. A rejected program may contain a real bug, a contract that accepts too much, or a property the solver has not established. This example contains a real overflow possibility.

## Start with an unsafe function

This file is intentionally rejected:

<!-- clack:file=../../examples/tutorials/06-overflow-rejected.clack -->
```clack
fn next_number(n: int) -> int:
    ensures result == n + 1
    return n + 1

fn main():
    print(next_number(41))
```

Check it without running:

```sh
clack check examples/tutorials/06-overflow-rejected.clack
```

The command exits with status one. Its diagnostic includes:

```text
error: cannot prove integer arithmetic stays within signed 64-bit range
  counterexample: n = 9223372036854775807
```

The actual call passes `41`, but Clack verifies every function over its entire declared input domain. There is no precondition here, so `n` can be any signed 64-bit integer. Adding one to the largest integer overflows. The postcondition describes an exact mathematical result; it cannot make the machine operation fit.

## Decide which inputs you support

One reasonable design is to accept every integer except the largest one:

<!-- clack:file=../../examples/tutorials/06-fixing-errors.clack -->
```clack
fn next_number(n: int) -> int:
    requires n < 9223372036854775807
    ensures result == n + 1
    return n + 1

fn main():
    print(next_number(41))
```

Run the corrected version:

```sh
clack run examples/tutorials/06-fixing-errors.clack
```

Its exact output is:

```text
42
```

The precondition excludes precisely the problematic upper endpoint. Main proves that `41` is below it. The function now proves both that its addition is safe and that its returned value satisfies the postcondition.

Adding `assert n < 9223372036854775807` inside the original function would not repair it: that assertion must itself be proved for every allowed input. An assertion is a checked claim, not a way to assume the caller behaved.

## Change behavior instead

A different design accepts every integer and leaves the maximum unchanged. The exercise solution below uses a conditional to make that choice explicit. This is often the right response to an error: decide whether to narrow the inputs or handle an edge case.

## Exercises

1. Call the corrected function with the largest signed integer. Does the error now point to the addition or the call?
2. Implement `next_or_same`, which returns n when n is already the maximum and otherwise returns n + 1. Give it a contract describing both cases.
3. Suppose an error reports a solver timeout instead of a counterexample. Does that establish a bug?

<details>
<summary>Answers and a complete guarded implementation</summary>

1. The call cannot prove `next_number`'s precondition. Its implementation remains verified for inputs inside its domain.
2. This implementation handles both cases without excluding either input:

<!-- clack:file=../../examples/tutorials/06-saturating.clack -->
```clack
fn next_or_same(n: int) -> int:
    ensures result >= n
    ensures n < 9223372036854775807 or result == n
    ensures n == 9223372036854775807 or result == n + 1
    if n == 9223372036854775807:
        return n
    return n + 1

fn main():
    print(next_or_same(41))
    print(next_or_same(9223372036854775807))
```

Run it with `clack run examples/tutorials/06-saturating.clack`. The exact output is:

```text
42
9223372036854775807
```

The `or` expressions encode the two case-specific promises. In the maximum branch, the function returns without performing the unsafe addition.

3. A timeout means the solver did not establish the claim within the limit. It does not establish that the program is wrong or right. Inspect the specification, strengthen useful invariants, simplify the reasoning, or deliberately increase the documented solver timeout. Strict compilation still requires a proof.

</details>

The [error guide](../errors.md) covers other common diagnostics. When a counterexample involves a loop variable, it may describe an arbitrary loop head allowed by the invariant; it is not necessarily a concrete trace from main.
