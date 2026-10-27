# Optional packages

[Handbook](README.md) · [Package catalog](../packages/catalog.json) · [Agent guide](agents.md)

The [packages directory](../packages/README.md) contains reusable Clack libraries outside the compiler and standard library. They ship as source: importing one checks its loaded Clack functions with the same verifier as the application. The terminal UI package also contains a C provider whose implementation is outside that proof model.

## Choose a package

| Package | Use it for | Source and guide |
| --- | --- | --- |
| Geometry | Integer points, rectangles, distances, containment, and intersections | [Geometry](../packages/geometry/README.md) |
| Matrix | Small fixed-shape integer linear algebra | [Matrix](../packages/matrix/README.md) |
| Fixed point | Scale-1,000 arithmetic represented by integers | [Fixed point](../packages/fixed/README.md) |
| Statistics | Four-value summaries and exact rational results | [Statistics](../packages/stats/README.md) |
| Algorithms | Four-value sorting, search, and first-tie selection | [Algorithms](../packages/algorithms/README.md) |
| ML | Bounded integer learning and inference with four features | [ML](../packages/ml/README.md) |
| Terminal UI | Panels, rows, metrics, progress bars, and keyboard menus | [TUI](../packages/tui/README.md) |

Names such as `sort4` or `score4` describe a fixed shape. These packages do not add generic types, floating-point arrays, or dynamically sized collections to the language. Each package README states the accepted domain and the properties its source contracts establish.

The fixed-point package uses integer values with an explicit scale of 1,000. The ML package uses plain bounded integer features and weights. Neither introduces a floating-point type or automatic numeric conversion.

## Run a demo

Clone the repository and install the compiler:

```sh
git clone https://github.com/155xp/clack.git
cd clack
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m clack run packages/geometry/demo.clack
.venv/bin/python -m clack run packages/ml/demo.clack
```

The geometry demo uses only checked Clack. The ML demo trains and evaluates a small integer model; its README explains feature ranges, updates, and the dataset. Proofs of arithmetic safety or update bounds do not imply convergence, prediction accuracy on other data, or suitability for a larger model.

For a terminal UI demo, run `clack run packages/tui/demo.clack` in a POSIX terminal. A non-interactive stream uses its documented plain-output fallback. Its C provider is compiled with the generated program and is reported as outside verification.

## Use packages in an application

Keep `app.clack` beside the copied `packages/` directory:

```text
my-app/
  app.clack
  packages/
    geometry/
      geometry.clack
```

Then use the module path relative to `app.clack`:

```clack
from packages.geometry.geometry import Point, squared_distance

fn main():
    print(squared_distance(Point(0, 0), Point(3, 4)))
```

This prints `25`. Run `clack check app.clack`, then `clack run app.clack` or `clack build app.clack -o build/app`.

You can also install the compiler with `python -m pip install 'git+https://github.com/155xp/clack.git'`. That installs the compiler and bundled `std` modules; copy the optional source packages separately from a checkout. There is no Clack package downloader, dependency lockfile, or registry. Keep the complete directory when copying a package, including any native provider and sibling source modules it uses.

Local imports are relative to the file containing the import, not the process working directory. A package demo uses a shorter neighboring-module import because its entry file lives inside that package's directory. See [imports and libraries](libraries.md) for exact resolution and naming rules.

## Check and extend a package

Read the `.clack` signatures and contracts before calling a function. A helper may require bounded inputs to prove every multiplication or addition safe. Rational results carry an explicit numerator and denominator; interpret them according to the package's documented convention rather than treating them as floating-point values.

All loaded source definitions are checked, including unused helpers. After verification, unreachable functions may be omitted from generated C. Each package also contains native-output tests against independent references. Run `python tools/check_packages.py` from the checkout root to check API metadata, source hashes, demo outputs, and all package tests. The [packages directory](../packages/README.md) describes updating generated catalog fields when a source API changes.

When extending a package, retain its explicit numeric domain, document changed contracts, and test boundary cases and algorithm outputs. Use `parallel:` around independent source workers where measurement shows useful work exceeds scheduling cost. The [agent guide](agents.md) covers generation and repair rules, and the [machine-readable language reference](agent-reference.json) provides structured capability data.
