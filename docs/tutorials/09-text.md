# 9. Text and byte lengths

[Previous: Libraries](08-libraries.md) · [Tutorial index](README.md)

The goal of this lesson is to choose a text result, carry it in a record, and prove properties about text equality and length. Text needs no import.

<!-- clack:file=../../examples/tutorials/09-text.clack -->
```clack
type Label:
    value: text

fn status(command: text) -> text:
    ensures (command == "build" and result == "Ready") or (command != "build" and result == "Unknown")
    if command == "build":
        return "Ready"
    return "Unknown"

fn same_size(left: text, right: text) -> bool:
    ensures result == (len(left) == len(right))
    return len(left) == len(right)

fn main():
    label = Label(status("build"))
    print(label.value)
    print(label.value == "Ready")
    print(len("café"))
    print(len(""))
    print("é" != "e\u0301")
    print(same_size("é", "ab"))
```

Run:

```sh
clack run examples/tutorials/09-text.clack
```

The exact output is:

```text
Ready
true
5
0
true
true
```

## Compare text and describe the result

`==` and `!=` compare matching text values by their exact UTF-8 bytes. Comparison preserves case: `"build"` differs from `"Build"`. The `status` contract describes both branches. A caller using `"build"` can prove that the result is `"Ready"`; other inputs receive `"Unknown"`.

Text can be a parameter, a result, or a record field. `label.value == "Ready"` uses the same comparison as a local text value. Equality also works in `requires`, `ensures`, assertions, and loop invariants. Mixed types such as `"3" == 3` are rejected.

## Count UTF-8 bytes

`len(text)` counts UTF-8 bytes and returns an integer. The ASCII letters `c`, `a`, and `f` occupy one byte each; `é` occupies two, giving `len("café") == 5`. Empty text has length zero. `same_size("é", "ab")` returns true because both inputs contain two UTF-8 bytes.

Comparison performs no Unicode normalization. The composed literal `"é"` has two bytes, while `"e\u0301"` contains an `e` followed by a combining accent and has three. They can appear similar when displayed but compare unequal. The byte-length rule remains the same in executable code and proof annotations.

`len` also continues to accept fixed arrays, where it counts elements. Neither text lengths nor text equality require a native binding or a library import.

## Current text storage

Text contents are immutable and currently originate in static literals. A local text binding may be reassigned another text value. There is no concatenation, text indexing, mutable input buffer, or native function returning text. The [text and native guide](../native.md) explains literal escapes, storage, and the explicit C boundary used for terminal UIs.

## Exercises

1. Change `status("build")` to `status("Build")`. What changes?
2. Replace `"café"` with `"Clack"`. What length is printed?
3. Change `same_size("é", "ab")` to `same_size("é", "e\u0301")`. Why does the answer change?

<details>
<summary>Answers</summary>

1. The first two lines become `Unknown` and `false`. Comparison preserves case.
2. It still prints `5`, since the five ASCII letters occupy five UTF-8 bytes.
3. The answer becomes `false`: the inputs contain two and three UTF-8 bytes.

</details>

Use the [type reference](../reference/types-values.md#immutable-text) for the complete text rules and the [contract reference](../reference/contracts-verification.md) when a text promise fails verification.
