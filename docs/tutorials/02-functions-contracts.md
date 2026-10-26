# 2. Functions and promises

[Previous: Your first program](01-first-program.md) · [Tutorial index](README.md) · [Next: Records and arrays](03-records-arrays.md)

The goal of this lesson is to define a reusable function and prove a useful fact about every call. We will double an integer within a small allowed range.

## A function with a contract

<!-- clack:file=../../examples/tutorials/02-functions-contracts.clack -->
```clack
fn double(n: int) -> int:
    requires 0 <= n <= 100
    ensures result == 2 * n
    return n + n

fn main():
    answer = double(21)
    assert answer == 42
    print(answer)
```

Run it:

```sh
clack run examples/tutorials/02-functions-contracts.clack
```

The exact output is:

```text
42
```

`double` is a function we define here, not a built-in. `n: int` gives its parameter a type, and `-> int` gives its returned value a type. Function parameters and results have explicit types; locals such as `answer` infer theirs. Only main omits its result type because it is the entry point and returns no value.

`requires` describes which inputs the function accepts. Here, the accepted domain is the integers from zero through one hundred. `0 <= n <= 100` is a chained comparison: both bounds must hold. Callers must prove that their argument meets this condition.

`ensures` describes the returned value. The reserved name `result` means that value. The compiler checks that `n + n` equals the mathematical expression `2 * n` for every allowed `n`. The proof covers the whole stated domain, rather than just the call with `21`.

The domain also makes runtime arithmetic safe. Executable integers have signed 64-bit bounds. An unrestricted doubling function would overflow for some integers; this one cannot reach those inputs. A precondition may describe a useful business rule as well as a safety requirement.

## What the caller knows

Clack checks functions using their contracts. After `answer = double(21)`, the caller can use the proved postcondition to establish `answer == 42`. The `assert` asks the compiler to prove exactly that fact. It is checked during compilation and erased from the executable after success; it does not turn into a runtime exception or an instruction to trust an unproved statement.

Keep proof annotations above executable statements. Parameters are immutable, so the `n` in the postcondition still denotes the input value. Contract arithmetic uses mathematical integers, while the actual `n + n` must also fit into a runtime integer.

If a different function simply returns its argument, it may need no precondition at all. Contracts are written for the properties a function needs and promises; the compiler does not require every function to invent an input restriction.

## Exercises

1. Make `double` accept values from `-100` through `100`, then call it with `-21`.
2. Remove the `ensures` line but keep the assertion in main. Why does verification fail?
3. Call the original function with `101`. Where does the error appear?

<details>
<summary>Answers</summary>

1. Change the precondition to `requires -100 <= n <= 100`; the result is `-42`. Update the assertion to `answer == -42` too.
2. The body still doubles its input, but its contract no longer tells callers that fact. Clack treats the returned integer conservatively at the call site, so the exact assertion is unproved. Restore the useful postcondition.
3. The call cannot establish `n <= 100`. The compiler reports a failed precondition at that call. Change the input or intentionally broaden the function's supported domain and recheck it.

</details>

The [verification model](../verification.md) explains this separation between checking a function and using its promise.
