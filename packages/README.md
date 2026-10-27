# Clack packages

Optional libraries live here as source, separate from the compiler and bundled `std` modules. Start with the [package guide](../docs/packages.md) or the [machine-readable catalog](catalog.json).

| Directory | Purpose |
| --- | --- |
| [geometry](geometry/README.md) | Integer points and rectangles |
| [matrix](matrix/README.md) | Small fixed-shape integer linear algebra |
| [fixed](fixed/README.md) | Scale-1,000 integer fixed-point arithmetic |
| [stats](stats/README.md) | Summaries and exact rational statistics |
| [algorithms](algorithms/README.md) | Fixed-shape sorting, search, and selection |
| [ml](ml/README.md) | Bounded integer learning and inference |
| [tui](tui/README.md) | Native POSIX terminal interfaces |

From the repository root, try:

```sh
python -m clack run packages/geometry/demo.clack
python -m clack run packages/ml/demo.clack
```

An application at the repository root can import `from packages.geometry.geometry import Point, squared_distance`. Imports resolve relative to the importing file; a demo inside a package instead imports its neighboring source module.

Copy whole package directories into an application layout that preserves their imports and native provider paths. Installing the Python compiler package does not download these optional sources. There is no package resolver or registry yet.

Source packages use the normal Clack checks, including imported helper bodies and declared contracts. The TUI's C implementation remains trusted and unproved. Fixed-size APIs and numeric bounds are deliberate parts of each package's interface; consult its README before choosing inputs.

Each package includes its own license, demo, and tests. The catalog supplies concrete source signatures, file checksums, demo paths, and expected outputs; each README explains validation. For language-generation tools, see [Clack for coding agents](../docs/agents.md).

Run the complete package checks from the checkout root:

```sh
python tools/check_packages.py
```

This checks catalog signatures and hashes, compiles all nine demos, checks their outputs, and runs each package's regression tests. After editing package sources, refresh generated catalog fields with `python tools/check_packages.py --update --metadata-only`, then run the complete checks again. Metadata refresh does not prove a package's source or test its behavior.
