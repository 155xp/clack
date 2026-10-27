# Clack Stats

Exact integer statistics for batches of four values. This optional source package lives outside the compiler and standard library. Inputs are signed integers in `[-1000000, 1000000]`; results preserve fractions instead of silently truncating them.

## Install and run

From the main Clack repository, use Clack 0.5 or newer and a C11 compiler:

```sh
git clone https://github.com/155xp/clack.git
cd clack
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
.venv/bin/python -m clack run packages/stats/demo.clack
.venv/bin/python -m clack run packages/stats/variance_demo.clack
```

Save this as `app.clack` at the checkout root:

```clack
from packages.stats.stats import summarize4, mean4, variance4

fn main():
    values = [3, 7, -2, 8]
    summary = summarize4(values)
    average = mean4(values)
    variance = variance4(values)
    print(summary.total)
    print(average.numerator)
    print(average.denominator)
    print(variance.numerator)
    print(variance.denominator)
```

This prints `16`, `16`, `4`, `248`, and `16`, one per line. The exact mean is `16/4`, and the exact population variance is `248/16`.

For a separate application, copy this folder beside its entry file as `stats/`, then use `from stats.stats import ...`. Keep `stats.clack` alongside the supplied demos, whose shorter imports resolve relative to their own files.

## API

| Function | Result | Exact promise |
| --- | --- | --- |
| `summarize4(values: int[4])` | `Summary` | Sum, minimum, and maximum of the four inputs |
| `mean4(values: int[4])` | `Rational` | Numerator is the sum; denominator is four |
| `variance4(values: int[4])` | `Rational` | Population variance: `(4 * sum(x²) - sum(x)²) / 16` |
| `span(summary: Summary)` | `int` | `summary.maximum - summary.minimum` |
| `sum_squares4(values: int[4])` | `int` | Sum of the four squared inputs |

`Summary` has `total`, `minimum`, and `maximum` integer fields. The extrema contracts establish both their ordering against every input and that each result is an input value.

`Rational` has integer `numerator` and `denominator` fields. Fractions are exact and **not reduced**. Every supplied fraction function returns a strictly positive constant denominator. Dividing the fields with `/` would perform truncating integer division; preserve the pair when a fractional result matters.

`variance4` measures **population** variance, dividing the sum of squared deviations by four. It does not implement the sample estimator that divides by three. It computes the equivalent sum of all six squared pairwise differences, making nonnegativity explicit. The contracts prove the exact formula, denominator `16`, and a nonnegative numerator. Constant batches have zero variance, and fractional variances are retained.

`span` requires `-1000000 <= summary.minimum <= summary.maximum <= 1000000`. A directly constructed `Summary` must meet those preconditions too. All arithmetic bounds are inclusive and chosen to keep every native intermediate inside signed 64-bit range. There are no floats, dynamic collections, implicit numeric conversions, or generic array lengths.

Read [stats.clack](stats.clack) for complete contracts. Functions are pure, introduce no runtime dependencies, and can be called inside source workers in parallel blocks.

## Test

Run from the Clack checkout root with its Python environment active:

```sh
python -m unittest discover -s packages/stats/tests -v
clack check packages/stats/demo.clack
clack check packages/stats/variance_demo.clack
```

Tests cover exact contracts, rejected domains, fraction preservation, variance against independent Python `Fraction` calculations, and native outputs for boundary and seeded cases. Clack's compiler, Z3, and C toolchain remain trusted; tests do not independently certify the source-to-native translation.

## For coding agents

Use the explicit four-value signatures. Prove each input lies within ±1000000 before calling arithmetic helpers, preserve `Rational` pairs, and select population versus sample variance deliberately. Do not substitute floating-point arithmetic or silently widen accepted ranges. Run the native reference tests after changing formulas. The package is MIT licensed; see [LICENSE](LICENSE).
