# Fixed-point arithmetic

This optional source package represents a number as `Fixed(raw)`, whose numeric value is `raw / 1000`. For example, `Fixed(1500)` represents 1.5. It supplies deterministic integer arithmetic with checked overflow domains; it does not add floating-point types to Clack.

Run the demo from a Clack checkout:

```sh
python -m clack run packages/fixed/demo.clack
```

It prints `1500`, `2250`, `3000`, `-1`, `3500`, and `2000`, one per line.

For an application beside the repository's `packages` directory:

```clack
from packages.fixed.fixed import Fixed, from_ratio, multiply

fn main():
    value = from_ratio(3, 2)
    squared = multiply(value, value)
    print(squared.raw)
```

To distribute this package alone, copy its directory next to your application, then use `from fixed.fixed import ...`. The included demo lives inside the package and therefore imports its neighboring module with `from fixed import ...`.

## API and verified domains

Every result below is an exact statement about integer arithmetic. `/` truncates toward zero. The compiler verifies all seven functions, including ones the caller does not use.

| Function | Input restriction | Result |
| --- | --- | --- |
| `from_int(value)` | `abs(value) <= 10^12` | `Fixed(value * 1000)` |
| `to_int(value)` | Any signed-64 `raw` | `value.raw / 1000` as an integer |
| `from_ratio(numerator, denominator)` | `abs(numerator) <= 10^12`; nonzero denominator | `Fixed(numerator * 1000 / denominator)` |
| `add(left, right)` | Each `abs(raw) <= 10^15` | `Fixed(left.raw + right.raw)` |
| `subtract(left, right)` | Each `abs(raw) <= 10^15` | `Fixed(left.raw - right.raw)` |
| `multiply(left, right)` | Each `abs(raw) <= 10^9` | `Fixed(left.raw * right.raw / 1000)` |
| `divide(left, right)` | `abs(left.raw) <= 10^12`; `right.raw != 0` | `Fixed(left.raw * 1000 / right.raw)` |

`Fixed(raw)` itself accepts any signed-64 raw value. The domains belong to the arithmetic operations, rather than to the record constructor. Multiplication, division, and ratio construction return raw values bounded by `10^15`; addition and subtraction return values bounded by `2 * 10^15`. A result can therefore require a narrower bound before another operation accepts it. These ranges do not promise automatic closure under repeated arithmetic.

## Precision and rounding

One raw unit is one thousandth. There is no implicit rescaling, decimal parser, rounding-to-nearest, saturation, or arbitrary precision. Discarded fractions move toward zero: `from_ratio(-1, 3).raw` is `-333`, and `to_int(Fixed(-1999))` is `-1`. Small products can truncate to zero. Choose the scale and units of your application's inputs deliberately.

The package uses verified Clack source with no native providers or runtime dependencies. Its contracts prove the documented formulas and finite-width safety, not an error bound for a larger numerical model.

## Validation

```sh
python -m unittest discover -s packages/fixed/tests -v
```

Tests compare native results with independent exact-integer references, including negative division, signed limits, and rejected zero divisors. Native tests compile as strict C11 with undefined-behavior sanitization.
