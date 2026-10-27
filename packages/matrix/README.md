# Matrix and vector arithmetic

Exact integer 2×2 matrices and two- or four-component vectors for Clack. This optional source package adds no compiler code or runtime dependency.

`Matrix2(a, b, c, d)` represents the row-major matrix `[[a, b], [c, d]]`. Vectors are columns: applying that matrix to `Vec2(x, y)` produces `(a*x + b*y, c*x + d*y)`. `Vec4(x, y, z, w)` supports dot products and squared Euclidean norms.

## Install and run

The package ships in the [Clack repository](https://github.com/155xp/clack), outside its standard library. From a checkout with Clack 0.5 or newer:

```sh
git clone https://github.com/155xp/clack.git
cd clack
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m clack run packages/matrix/demo.clack
.venv/bin/python -m clack run packages/matrix/vector_demo.clack
```

The compiler needs Python 3.11 or newer and a C11 compiler with POSIX threads. Generated programs need neither Python nor the solver.

Save an application beside the checkout's `packages` directory, for example as `app.clack` in the repository root:

```clack
from packages.matrix.matrices import Matrix2, Vec2, Vec4, multiply, apply, dot4, squared_norm4

fn main():
    left = Matrix2(1, 2, 3, 4)
    right = Matrix2(5, 6, 7, 8)
    product = multiply(left, right)
    vector = apply(left, Vec2(2, 3))
    print(product.a)
    print(product.d)
    print(vector.x)
    print(vector.y)
    print(dot4(Vec4(1, 2, 3, 4), Vec4(5, 6, 7, 8)))
    print(squared_norm4(Vec4(1, 2, 3, 4)))
```

Run `clack run app.clack` in an activated environment, or use `.venv/bin/python -m clack run app.clack`. Output is `19`, `50`, `8`, `18`, `70`, and `30`, one per line.

Imports resolve relative to the importing file. The package demos import their neighboring `matrices.clack` as `from matrices import ...`. To vendor this package elsewhere, copy the complete `matrix` directory and adjust the application's import path to its location.

## API and domains

All records have integer fields:

| Type | Fields |
| --- | --- |
| `Matrix2` | `a`, `b`, `c`, `d` |
| `Vec2` | `x`, `y` |
| `Vec4` | `x`, `y`, `z`, `w` |

| Function | Result | Required input domain |
| --- | --- | --- |
| `identity() -> Matrix2` | Diagonal entries 1, other entries 0 | No inputs |
| `transpose(matrix: Matrix2) -> Matrix2` | Swapped rows and columns | Every signed 64-bit field value |
| `determinant(matrix: Matrix2) -> int` | Exact `a*d - b*c` | Every field in `[-1000000, 1000000]` |
| `multiply(left: Matrix2, right: Matrix2) -> Matrix2` | Exact `left × right` | Every field in that interval |
| `apply(matrix: Matrix2, vector: Vec2) -> Vec2` | Exact matrix-vector product | Every field in that interval |
| `add(left: Matrix2, right: Matrix2) -> Matrix2` | Elementwise sum | Every field in that interval |
| `dot4(left: Vec4, right: Vec4) -> int` | Sum of four corresponding products | Every component in that interval |
| `squared_norm4(vector: Vec4) -> int` | Sum of the four squared components | Every component in that interval |

Bounds include both endpoints. Matrix arithmetic can produce fields as large as ±2,000,000,000,000. Dot products lie in ±4,000,000,000,000; squared norms lie between zero and 4,000,000,000,000. A large result is a valid integer or record, but passing it into another bounded operation still requires proving that operation's input conditions.

These are simple sufficient domains for signed 64-bit safety. Some larger inputs would also be safe, but are outside this API's contracts. Transpose has no small-value restriction because it only rearranges existing values. Squared norm deliberately omits a square root: a result of `25` corresponds to a Euclidean norm of `5`.

## Contracts and agent use

The complete source API and exact equations are in [matrices.clack](matrices.clack). Import these declared names explicitly; records are nominal types, so a separately declared lookalike is not interchangeable. There are no aliases, implicit conversions, generic dimensions, floating-point matrices, inversion, or normalization in this package.

All functions are pure and may be direct `parallel:` jobs. Keep values within the documented input domain before each call. Every loaded function is verified, including unused helpers, and the compiler rejects an unproved precondition. Clack's verifier, solver, C backend, and toolchain remain trusted; these contracts are not an independently certified compiler proof.

## Examples and tests

The [matrix demo](demo.clack) prints `19`, `50`, `8`, `18`, and `-2`. The [vector demo](vector_demo.clack) runs two independent jobs and prints `70` and `30`.

From the Clack repository root:

```sh
.venv/bin/python -m clack check packages/matrix/demo.clack
.venv/bin/python -m clack check packages/matrix/vector_demo.clack
.venv/bin/python -m unittest discover -s packages/matrix/tests -v
```

Tests cover algebraic identities, negative and boundary values, rejected input domains, nominal record types, parallel use, and native outputs compared with independent Python integer references. MIT licensed; see [LICENSE](LICENSE).
