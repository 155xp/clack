# Clack Geometry

Integer 2D geometry for Clack: points, closed rectangles, translation, squared distance, containment, intersection, area, and bounding rectangles. This is a separate source library, so applications can use it without adding geometry APIs to Clack's standard library.

The implementation is in [geometry.clack](geometry.clack). It uses signed 64-bit integers throughout. There are no floating-point coordinates, angles, rotations, or square-root approximation hidden behind the API.

## Install and import

Use Clack 0.5 or newer. This package ships in the main repository:

```sh
git clone https://github.com/155xp/clack.git
cd clack
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
.venv/bin/python -m clack run packages/geometry/demo.clack
```

Put an application at the checkout root and import `packages.geometry.geometry`. For a separate application, copy this entire folder beside its entry file as `geometry/`, then import `geometry.geometry`. Module paths resolve relative to the importing file.

Save this complete program as `app.clack`:

```clack
from packages.geometry.geometry import Point, Rect, translate, squared_distance
from packages.geometry.geometry import contains, intersects, area, bounding_rect

fn main():
    point = Point(3, 4)
    moved = translate(point, 2, -1)
    print(moved.x)
    print(squared_distance(Point(0, 0), point))

    box = Rect(0, 0, 10, 10)
    print(contains(box, Point(10, 10)))
    print(intersects(box, Rect(10, 0, 20, 10)))
    print(area(box))

    bounds = bounding_rect(Point(-1, 7), Point(3, -2))
    print(bounds.top)
```

Run it with:

```sh
python -m clack run app.clack
```

Output:

```text
5
25
true
true
100
-2
```

Clack resolves a local import relative to the importing file, not the terminal's working directory. Keep the copied library directory beside `app.clack`, or adjust the module path to match your layout. No package registry or automatic dependency resolver is involved.

## Types and coordinate rules

| Type | Fields |
| --- | --- |
| `Point` | `x: int`, `y: int` |
| `Rect` | `left: int`, `top: int`, `right: int`, `bottom: int` |

A valid rectangle has `left <= right` and `top <= bottom`. Here `top` names the lower Y bound; the library does not assume a screen-coordinate direction. Rectangles are closed intervals on both axes, so a point on an edge or corner is inside. Rectangles that share only an edge or a corner intersect. Zero-width and zero-height rectangles are valid, with zero area.

Records have Clack's value semantics. Functions do not mutate their inputs. Imported `Point` and `Rect` remain the nominal types defined by this library; redeclaring an identically shaped record in an application creates a different type.

## Function catalog

| Function | Supported inputs | Result |
| --- | --- | --- |
| `translate(point, dx, dy)` | Both coordinates and each offset in `[-1000000, 1000000]` | Exact `Point(point.x + dx, point.y + dy)`; output coordinates lie within ±2000000 |
| `squared_distance(a, b)` | All four coordinates in `[-1000000, 1000000]` | Exact `(a.x - b.x)² + (a.y - b.y)²`, between zero and 8000000000000 |
| `contains(rect, point)` | Valid rectangle; coordinates may use the full `int` range | Whether the point lies within both closed intervals |
| `intersects(a, b)` | Both rectangles valid; coordinates may use the full `int` range | Whether the closed rectangles have any shared point |
| `area(rect)` | Valid rectangle with all coordinates in `[-1000000, 1000000]` | Exact `(right - left) * (bottom - top)`, between zero and 4000000000000 |
| `bounding_rect(a, b)` | Any two integer points | The smallest axis-aligned closed rectangle containing both points |

Read each function's `requires` and `ensures` clauses for the accepted domain and exact promised behavior. The arithmetic bounds give the verifier enough information to establish that every intermediate fits in `int`; calls outside those domains are rejected rather than silently wrapping.

Squared distance is useful for ordering distances or comparing against a squared radius without introducing floating point. It is not the ordinary Euclidean distance: a squared distance of 25 corresponds to a distance of 5, and the function intentionally returns 25.

## Run the demo and tests

From the Clack checkout root, with its Python environment active:

```sh
python -m clack check packages/geometry/demo.clack
python -m clack run packages/geometry/demo.clack
python -m unittest discover -s packages/geometry/tests -v
```

The [demo](demo.clack) imports the adjacent library file directly. The [tests](tests/test_geometry.py) cover contracts, boundaries, rejected inputs, and native execution. The library file itself has no `main`; it is imported by a program that supplies the entry point.

Importing the library makes its source part of Clack's normal verification process. That establishes the stated contracts in the compiler's model. The compiler, solver, C backend, and native toolchain remain trusted; this library does not claim an independently certified source-to-machine-code proof.

## For coding agents

Use the exported nominal `Point` and `Rect` records. Preserve closed-edge semantics, allow zero-area rectangles, and prove each function's stated domain before calling it. `top` and `bottom` name ordered Y bounds without assuming a screen-coordinate direction. Keep distances squared when comparing them; `squared_distance` does not return a square root. Run the native integer-reference tests after changing formulas.

MIT licensed; see [LICENSE](LICENSE).
