# 5. Independent work in parallel

[Previous: Loops](04-loops.md) · [Tutorial index](README.md) · [Next: Fixing errors](06-fixing-errors.md)

The goal of this lesson is to run two independent calculations together without writing locks, joining threads manually, or sharing a mutable array. We will reuse the batch counter from the last lesson.

## Group independent calls

<!-- clack:file=../../examples/tutorials/05-parallel-work.clack -->
```clack
fn count_nonzero(values: int[4]) -> int:
    ensures 0 <= result <= len(values)
    i = 0
    count = 0
    while i < len(values):
        invariant 0 <= i <= len(values)
        invariant 0 <= count <= i
        decreases len(values) - i
        if values[i] != 0:
            count = count + 1
        i = i + 1
    return count

fn main():
    values = [5, 0, -2, 8]
    parallel:
        left = count_nonzero(values)
        right = count_nonzero([0, 1, 0, 2])
    values[0] = 0
    print(left)
    print(right)
    print(left + right)
    print(values[0])
```

Run it:

```sh
clack run examples/tutorials/05-parallel-work.clack
```

The exact output is:

```text
3
2
5
0
```

The helper is repeated here so this is a complete runnable file. The library lesson will show how to reuse a helper from another source file.

Each line of the `parallel:` block calls a user-defined function and gives its result a distinct name. The compiler creates native POSIX threads for those jobs. The block waits for all jobs to finish before execution continues below it. If the platform cannot create a thread, that job runs synchronously with the same result semantics.

No worker can call `print`; output belongs to main. That means the output order comes from the four print statements after the block, rather than from whichever worker happens to finish first.

## Inputs and results stay separate

All job arguments use the values available before the block. Each array is passed by value, and parameters cannot be mutated. Changing `values[0]` after the block does not alter the completed `left` result.

The calls cannot read one another's result bindings. For example, a second job that calls a function with `left` as an argument belongs after the first block, once left exists. The restriction also applies if a result name previously existed: choose result names that clearly separate inputs from outputs.

Constructors and `print` are not parallel jobs. A job is a call to a typed worker function; that function may use normal local data and control flow. The compiler checks each call's precondition and uses its proved postcondition to reason about the returned result. Here the counter's bounds show that `left + right` is safe.

## Use parallelism where work justifies it

These two four-element jobs are intentionally small enough to understand. Creating threads costs time, so this example teaches behavior rather than demonstrating a speedup. Larger independent tasks can benefit from parallel execution. The current runtime does not provide a worker pool, GPU execution, or an automatic promise of faster results. The [benchmark](../../benchmarks/README.md) measures one larger workload separately.

## Exercises

1. Add `third = count_nonzero([1, 2, 3, 4])` to the block and print it afterward.
2. Move `values[0] = 0` before the block. How does the output change?
3. Try to print from inside `count_nonzero`. What rule does that break?

<details>
<summary>Answers</summary>

1. The new result prints `4`. Its name is distinct and its input does not depend on another result, so it is independent.
2. Left becomes `2`, right stays `2`, the sum becomes `4`, and the final array entry still prints `0`.
3. Only main may print. Keeping helpers free of output makes them suitable for independent worker calls without output-order surprises. Return data to main and print it there.

</details>
