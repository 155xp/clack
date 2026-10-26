# 3. Records and arrays

[Previous: Functions and promises](02-functions-contracts.md) · [Tutorial index](README.md) · [Next: Loops](04-loops.md)

The goal of this lesson is to give related values names and to understand what happens when data is copied. We will move a point and edit an independent copy of a four-element array.

## A complete data example

<!-- clack:file=../../examples/tutorials/03-records-arrays.clack -->
```clack
type Point:
    x: int
    y: int

fn move_right(point: Point) -> Point:
    requires -1000000 <= point.x <= 1000000
    ensures result.x == point.x + 1
    ensures result.y == point.y
    return Point(point.x + 1, point.y)

fn main():
    original = Point(3, 4)
    moved = move_right(original)
    counts = [3, 0, 7, 2]
    updated = counts
    updated[1] = moved.x
    print(original.x)
    print(moved.x)
    print(counts[1])
    print(updated[1])
    print(len(counts))
```

Run it:

```sh
clack run examples/tutorials/03-records-arrays.clack
```

The exact output is:

```text
3
4
0
4
4
```

`type Point:` declares a record. Its fields have names and types. `Point(3, 4)` constructs one in field declaration order; `.x` and `.y` read those fields. The `move_right` function accepts and returns a `Point`, proving that x increases by one and y stays the same. Its x bound makes that addition safe. Nothing changes the original point.

Record fields are immutable in this version. To represent a changed point, construct another `Point` and assign it to a new or existing local binding. Parameters are also immutable. If a function needs to edit an input array, it first assigns it to a local copy.

## Arrays have a known shape

`[3, 0, 7, 2]` creates an array with type `int[4]`. Length is part of the type, so an `int[3]` cannot be passed where an `int[4]` is expected. `len(counts)` is four. Indices start at zero: `counts[1]` is the second entry.

An array must be nonempty and contain only integers or only Booleans. Arrays of records and nested arrays are not supported yet. A record can contain an array or another record.

The compiler proves every read and write is within bounds. Here the literal index `1` is between zero and three. A computed index needs a fact that establishes its bounds; the next lesson supplies those facts with a loop invariant.

## Copies are independent values

`updated = counts` copies the array value. Changing `updated[1]` does not change `counts[1]`. That is why the third output line is zero while the fourth is four. The same value semantics apply to function arguments and results, including records containing arrays.

This rule is useful before parallel work: two jobs can receive values without accidentally modifying the same shared array. The language does not expose pointers or mutable global data in this prototype.

## Exercises

1. Set `updated[3] = 99`, then print both `counts[3]` and `updated[3]`.
2. Try `updated[4] = 99`. Why is the index rejected?
3. Replace the input point with `Point(-2, 8)`. Predict the first two output lines.

<details>
<summary>Answers</summary>

1. They print `2` and `99`; the copies are independent.
2. A four-element array ends at index three. The compiler cannot prove `4 < 4`, so it rejects the update before producing a binary.
3. They become `-2` and `-1`. The remaining output changes too: the edited array entry receives the moved x value, so it prints `-1`.

</details>

Use the [type reference](../reference/README.md) when you need the exact supported data forms.
