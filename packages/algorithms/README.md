# Clack algorithms

Small, verified comparison algorithms for fixed four-element integer arrays. These are ordinary Clack source functions. They compile to native code and add no compiler features or runtime dependency.

The functions accept the full signed 64-bit integer range. Their implementations compare and move values; they do not subtract keys or add array elements, so sorting extreme integers cannot overflow.

## Run the example

From the Clack repository root after installing its compiler:

```sh
clack run packages/algorithms/demo.clack
```

It prints `-3`, `1`, `7`, `7`, `0`, `-1`, `1`, and `2`, one per line.

For an application at the repository root, use:

```clack
from packages.algorithms.algorithms import sort4, first_index4, argmin4, lower_bound4

fn main():
    values = [7, -3, 7, 1]
    ordered = sort4(values)
    print(ordered[0])
    print(first_index4(values, 7))
    print(argmin4(values))
    print(lower_bound4(ordered, 7))
```

Imports resolve relative to the importing file. To vendor this package, copy its directory under your application directory and adjust that import path. A neighboring `algorithms.clack` can instead be imported with `from algorithms import sort4`.

## API

| Function | Input | Result and proved behavior |
| --- | --- | --- |
| `sort4(values) -> int[4]` | `int[4]` | Nondecreasing order and an exact permutation of all four inputs, preserving duplicate multiplicities |
| `first_index4(values, target) -> int` | `int[4]`, `int` | First matching index, or `-1` exactly when no element matches |
| `argmin4(values) -> int` | `int[4]` | Index of the minimum element; the earliest index wins ties |
| `lower_bound4(values, target) -> int` | Sorted `int[4]`, `int` | First index whose value is at least `target`, or `4`; the insertion point before equal values |

`lower_bound4` requires `values[0] <= values[1] <= values[2] <= values[3]`. A preceding call to `sort4` proves this requirement. The result may equal four; check `index < 4` before indexing the input.

The other functions have no value preconditions. Arrays are values: `sort4` returns a new value and leaves its input unchanged. The names make the supported size explicit. There is no arbitrary-length sort, mutable slice API, comparator callback, or stability guarantee for hypothetical associated payloads.

## How the contracts are checked

`sort4` uses a five-comparator sorting network. Its contract separately requires sorted order and a disjunction of the 24 permutations of input indices. This preserves multiplicity even when input values are equal; mere membership of each output would be insufficient.

The search functions state exact index conditions, including absence and tie rules. Every loaded function is verified, including an unused definition. Verification time includes those contracts; successful native execution uses no solver or Python interpreter.

Run the package regressions from the repository root:

```sh
python -m unittest discover -s packages/algorithms/tests -v
```

Tests compare native output with Python sorting, multiset counting, first-index search, and `bisect_left`, including all 24 permutations of distinct values, duplicates, signed extremes, and seeded random inputs. Native tests compile as strict C11 with undefined-behavior sanitization. The compiler, solver, C toolchain, and native platform remain trusted.

MIT licensed; see [LICENSE](LICENSE).
