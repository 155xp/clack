# The Clack Handbook

Documentation for **Clack 0.3**, the native language implemented in this repository.

Clack combines a small syntax with static types, value records, fixed arrays, checked contracts, and independent parallel calls. This handbook teaches the current compiler. Proposed features live in the [design direction](design.md).

## Start here

1. [Install Clack and run a program](getting-started.md).
2. Work through the [eight tutorials](tutorials/README.md), from the first function to a parallel data-processing project and reusable libraries.
3. Keep the [quick reference](quick-reference.md) nearby while writing code.
4. Use the [error guide](errors.md) when a program fails to compile.

You can follow the tutorials with basic programming knowledge. The first lessons explain Clack's proof annotations as ordinary promises about inputs and outputs; no proof-assistant experience is needed.

## Look something up

| Topic | Where to read |
| --- | --- |
| Syntax and semantics | [Language guide](language.md) and [detailed reference](reference/README.md) |
| Operators, names, indentation | [Lexical syntax](reference/lexical-syntax.md) |
| Numbers, records, arrays, copies | [Types and values](reference/types-values.md) |
| Functions, conditions, loops, built-ins | [Functions and control flow](reference/functions-control-flow.md) |
| Contracts and proof obligations | [Contract reference](reference/contracts-verification.md) and [verification model](verification.md) |
| Threads and independent tasks | [Parallelism reference](reference/parallelism.md) |
| Complete syntax | [Grammar](reference/grammar.md) |
| Compiler flags and outputs | [Command-line reference](cli.md) |
| Small reusable patterns | [Cookbook](cookbook.md) |
| Imports, built-ins, and standard helpers | [Libraries](libraries.md) |
| Text, C providers, and terminal UI boundaries | [Native bindings](native.md) |
| Common questions and limitations | [FAQ](faq.md) |

## Work on the compiler

Read [how the compiler works](internals.md), then the [contribution guide](contributing.md). The [performance experiment](../benchmarks/README.md) includes the kernel, timing procedure, recorded samples, and limitations.

The [design direction](design.md) separates implemented behavior from possible extensions. `print` and `len` are available without imports. Standard modules supply verified source helpers plus the explicitly imported array operators `sum`, `all`, `any`, and `count`, which the compiler models directly. Earlier tutorials define their own helpers to explain how they work; later lessons import reusable versions. See the [library catalog](libraries.md) for the exact available operations and their implementation boundaries.

## Reading and running examples

Commands assume you are in the repository root with its virtual environment activated. Source examples use `.clack` files. An output block shows the exact printed lines; compiler progress messages are explained separately where relevant.

Tutorials link complete source files under [examples/tutorials](../examples/tutorials/). Small snippets labeled as fragments belong inside a function or alongside the declarations shown in that lesson. They are not standalone files.

Run the documentation checker from the repository root:

```sh
python tools/check_docs.py
```

It checks local links, checks that marked tutorial excerpts match their source files, and runs the documented programs against their expected results. See [contributing](contributing.md) for the compiler regression suite.
