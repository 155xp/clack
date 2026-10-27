# Types and values

[Reference index](README.md) · [Previous: lexical syntax](lexical-syntax.md) · [Next: functions and control flow](functions-control-flow.md)

Clack is statically typed. Function signatures and record fields declare types. A local binding gets its type from its first assignment, and later assignments must retain that type. The compiler does not implicitly convert between unrelated types.

## Primitive types

| Type | Values | Executable representation |
| --- | --- | --- |
| `int` | Integers from −9,223,372,036,854,775,808 through 9,223,372,036,854,775,807 | Signed 64-bit integer |
| `bool` | `true` and `false` | Native Boolean |
| `text` | Immutable UTF-8 literals | Read-only NUL-terminated bytes |
| `unit` | No user-constructible value | No returned value; used by `main` and native procedures |

Integer arithmetic must remain within the signed 64-bit range at every executable intermediate. There is no wrapping, saturating, floating-point, or arbitrary-precision runtime mode. The verifier proves safety before the native operation is emitted.

Booleans support `not`, `and`, `or`, `==`, and `!=`. An `if` or `while` condition must be a Boolean. Integers do not have a truthiness conversion, and Booleans do not participate in arithmetic. `true + 1` and `if 1:` are type errors.

`main` returns `unit`. Its signature can be written `fn main():` or `fn main() -> unit:`. A native procedure may explicitly declare a `unit` result too. Ordinary source helpers must return values; no parameter, record field, or local binding may use `unit`. In particular, `print` cannot supply a value to an assignment.

## Immutable text

`text` uses double-quoted JSON-style literals such as `"Clack"` and `"Ready\n"`. Contents must be valid UTF-8 without embedded NUL. An ordinary function may accept or return text, and a record may contain a text field. Text contents cannot be mutated, though a local text binding may be reassigned another text value.

Text currently originates only from static literals. `==` and `!=` compare exact UTF-8 byte sequences, with case preserved and no Unicode normalization. `len(text)` counts UTF-8 bytes: `len("café")` is `5`, and `len("")` is `0`. Equality and length are available in executable code and proof annotations. Concatenation, ordering, indexing, text arrays, and native text returns remain unsupported. See [the text guide](../native.md#text-values) for escapes and output examples.

## Fixed arrays

An array type records an element type and a fixed length: `int[3]` or `bool[2]`. Its literal determines the same type:

```clack
fn main():
    readings = [12, 18, 9]
    enabled = [true, false]
    readings[1] = 20
    print(readings[1])
    print(enabled[0])
    print(len(readings))
```

This prints `20`, `true`, and `3`. Array indexing starts at zero. For an array of length `N`, a readable or writable index must satisfy `0 <= index < N`. The compiler must prove that condition; it does not silently clamp or wrap indices.

Arrays contain only `int` or only `bool`. Empty arrays, mixed arrays such as `[1, true]`, nested arrays, and arrays of records are unsupported. Accepted lengths are between `1` and `1000000`, inclusive. This is an implementation limit, not a promise that every such value will fit the native stack or a chosen platform's resources.

The imported `fill` operator constructs a fixed array without listing every element: `fill(0, 100)` has type `int[100]`, and `fill(false, 8)` has type `bool[8]`. Its first argument is evaluated once; its second must be a decimal integer literal from `1` through `1000000`. It does not accept a length variable or computed length and does not create a dynamic collection. Import it with `from std.array import fill`.

Length is part of type identity. A function accepting `int[3]` does not accept `int[4]`, and a local first assigned a three-element array cannot later receive a four-element array. The length cannot be a parameter name or runtime expression in a type annotation. `len(array)` returns an `int` whose value is known from the type.

The standard `sum`, `minimum`, `maximum`, `all`, `any`, and `count` operators accept any supported fixed length using the argument's type; they do not introduce user-defined generic type syntax. Integer-array extrema use comparisons and accept all signed 64-bit elements. See [array operators](../libraries.md#stdarray-any-supported-fixed-length) for exact types and safety requirements.

Assignment to an array element is supported only through a local variable, for example `readings[i] = value`. A function parameter is immutable, including its elements. Copy a parameter to a local when making a changed version:

```clack
fn replace_first(values: int[3], first: int) -> int[3]:
    ensures result[0] == first
    ensures result[1] == values[1]
    ensures result[2] == values[2]
    changed = values
    changed[0] = first
    return changed

fn main():
    original = [1, 2, 3]
    changed = replace_first(original, 9)
    print(original[0])
    print(changed[0])
```

The output is `1` followed by `9`. The caller's array stays unchanged.

## Records

A record gives names and types to a nonempty collection of fields:

```clack
type Point:
    x: int
    y: int

type Sample:
    position: Point
    readings: int[3]
    valid: bool

fn main():
    sample = Sample(Point(3, 4), [10, 20, 30], true)
    print(sample.position.x)
    print(sample.readings[2])
    print(sample.valid)
```

This prints `3`, `30`, and `true`. The constructor takes one argument for each field, in declaration order. Constructors have no default values or named arguments. Each argument must have exactly the corresponding field's type.

Fields may contain integers, Booleans, text, fixed scalar arrays, or other records. A record cannot contain itself directly or indirectly by value. Such a layout would require infinite storage. There are no user-visible pointers or references with which to express a recursive data structure in version 0.5.

Field access uses `.` and may be chained with further field or array access. Fields cannot be assigned directly. To update a record, construct and assign a replacement. The following is a fragment inside a function where `point` is already a `Point` and the addition is known safe:

```clack
point = Point(point.x + 1, point.y)
```

To modify an array field, copy the field to a local, update that local, and build a replacement record. `record.readings[0] = value` is not an accepted assignment target.

Record types are identified by their declarations. Two separately declared records remain distinct even if their field types happen to match. A record imported from a [library module](../libraries.md) retains the identity of that declaration; importing its constructor does not create a new type.

## Value semantics

Assignment, parameter passing, and returning a result all have value semantics. If `b = a`, changing a permitted part of `b` later does not change `a`. This applies recursively when records contain arrays or other records.

The compiler represents composites as native C structures. It may use ordinary optimization to eliminate a physical copy when doing so preserves the language's behavior. The source-level rule is independence of values, not a required number of memory copies.

These rules also apply at parallel boundaries. Two workers receiving the same array receive independent input values, and neither can change the other's data. See [parallel execution](parallelism.md) for the job rules.

## Comparison and output

`==` and `!=` compare matching pairs of integers, Booleans, or text values. Mixed-type equality is rejected. Ordering comparisons accept two integers. Composite equality is not implemented; compare the fields or elements needed for the property.

`print` accepts one integer, Boolean, or text value and appends a newline. It prints Booleans as `true` and `false`. It cannot print a whole record or array, so print selected fields or elements. Only `main` may call `print`.

Text concatenation and indexing, dynamic arrays, slices, enums, tagged unions, generic types, and user-defined operators remain [design proposals](../design.md).
