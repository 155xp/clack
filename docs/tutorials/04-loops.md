# 4. Loops you can reason about

[Previous: Records and arrays](03-records-arrays.md) · [Tutorial index](README.md) · [Next: Parallel work](05-parallel-work.md)

The goal of this lesson is to visit an array safely and explain why the loop finishes. Start with a counted loop, then use an explicit while loop to see the reasoning behind it.

## Start with a counted loop

<!-- clack:file=../../examples/tutorials/04-counted-loops.clack -->
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
    values = [10, 20, 30]
    for i in range(len(values)):
        print(values[i])
    for i in range(3, 5):
        print(i)
    print(count_to(10))
```

Run `clack run examples/tutorials/04-counted-loops.clack`. It prints `10`, `20`, `30`, `3`, `4`, and `10`, one per line.

`range(stop)` starts at zero; `range(start, stop)` uses the given start. Both advance by one and stop before the upper bound. Bounds are evaluated once. A range whose start is at least its stop does nothing. The compiler supplies the index bounds, checks indexing, and establishes termination. The array-printing loop needs no annotations.

The index is immutable and exists only inside its body. It cannot shadow an existing binding, but separate loops may reuse `i`. Initialize values needed after the loop before entering it; body locals may never be created if the range is empty.

The count function changes `total`, so `invariant total == i` carries the relationship needed to prove its result. Before the first iteration both are zero. Every completed iteration increases both by one, including the compiler's generated index increment. At exit, the invariant and final index establish `total == n`. Counted loops automate index progress, not arbitrary facts about accumulators.

## Count a batch

An explicit while loop exposes the index and termination annotations. This example counts the nonzero values in a fixed batch of four entries:

<!-- clack:file=../../examples/tutorials/04-loops.clack -->
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
    print(count_nonzero([5, 0, -2, 8]))
    print(count_nonzero([0, 0, 0, 0]))
```

Run it:

```sh
clack run examples/tutorials/04-loops.clack
```

The exact output is:

```text
3
0
```

`count_nonzero` is our function, defined in this file. It is not a standard-library operation. The `int[4]` parameter fixes the batch shape. The loop starts at index zero and advances one entry at a time. `if values[i] != 0:` decides whether the count increases.

## Tell the compiler what stays true

An invariant describes a fact that is true before the first iteration and after every completed iteration. It also supplies the facts for reasoning about an arbitrary iteration. Clack does not assume that seeing a safe first iteration proves all later ones safe.

The first invariant, `0 <= i <= len(values)`, says the index stays in a known range. Inside the body, the loop condition adds `i < len(values)`. Together these facts establish that `values[i]` exists. At loop exit, the condition is false, so the same invariant tells us `i == len(values)`.

The second invariant, `0 <= count <= i`, says the count cannot exceed the number of entries already visited. Both variables start at zero, so it holds initially. An iteration adds at most one to count and exactly one to i, preserving the relationship.

These small bounds also prove that the executable increments fit into signed 64-bit integers. The verifier checks the actual operations as well as the final result.

## Explain why it finishes

`decreases len(values) - i` is the number of entries remaining. It is nonnegative when an iteration begins and gets smaller after the body. An integer cannot keep decreasing through nonnegative values forever, so this establishes loop termination in the language's execution model.

In a while body, all invariants come first, followed by one `decreases` annotation, then executable statements. A counted for body allows optional invariants and supplies the termination measure itself. There is no unchecked loop mode. A missing required annotation, an unproved invariant, or a nondecreasing termination measure stops compilation.

## Know what was proved

The implementation counts nonzero entries. Its contract currently proves only that the result lies between zero and the array length. A function returning zero would also satisfy that weak contract. This example teaches bounds and loop reasoning; it does not claim that a range condition alone proves the full counting algorithm. Richer collection specifications are part of Clack's future design.

## Exercises

1. Change `!= 0` to `> 0`. Predict the output for the first batch.
2. Replace the first invariant with `invariant i == 0`. Why does it fail?
3. Change `decreases len(values) - i` to `decreases len(values)`. What is missing?

<details>
<summary>Answers</summary>

1. Only `5` and `8` are positive, so the output is `2`. Rename the function to `count_positive` to make its purpose clear.
2. The first increment makes i equal one. The proposed invariant is true initially but is not preserved.
3. The array length is constant, so the measure never becomes smaller. Use the remaining work, which depends on i.

</details>

See [verification](../verification.md) for the rules used at loop entry, the arbitrary loop head, and exit.
