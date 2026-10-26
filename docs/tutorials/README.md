# Learn Clack

These tutorials teach the language that the current compiler accepts. Start with a short program, then build up to a native inventory report with parallel warehouse jobs. You do not need to know a proof assistant or write C to follow them.

## Before you begin

You need Python 3.11 or newer and a C11 compiler with POSIX threads. Linux and macOS with GCC or Clang are the intended platforms. From the repository root, install the compiler and activate its environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
clack --version
```

Commands in these lessons assume you stay in the repository root with this environment active. Without activation, replace `clack` with `.venv/bin/python -m clack`. See the [command-line guide](../cli.md) for compiler selection and build options.

## Your learning path

| Lesson | What you will build | What you will learn |
| --- | --- | --- |
| [1. Your first program](01-first-program.md) | A small numeric calculation | Main, local values, output, native execution |
| [2. Functions and promises](02-functions-contracts.md) | A verified doubling function | Types, requires, ensures, assertions |
| [3. Records and arrays](03-records-arrays.md) | Points and independent array copies | Named data, fixed lengths, value semantics |
| [4. Loops you can reason about](04-loops.md) | A batch counter | Bounds, invariants, termination |
| [5. Independent work in parallel](05-parallel-work.md) | Two batch counters at once | Thread-backed jobs, input values, result ordering |
| [6. Learn from a rejected program](06-fixing-errors.md) | A safe increment function | Counterexamples, contracts, guarded arithmetic |
| [7. Build an inventory report](07-project.md) | Two warehouse reports | Putting the pieces together |
| [8. Reuse code with libraries](08-libraries.md) | A program using supplied and local helpers | Imports, library contracts, code reuse |

Every lesson contains a complete source file, a command, exact output, and exercises with answers. The complete files live in [examples/tutorials](../../examples/tutorials/). They are checked with the repository's documentation checks so the listings and runnable files stay in sync.

`print` and `len` are available without imports. Names such as `double`, `count_nonzero`, and `analyze` are ordinary functions defined in the first seven lessons. Lesson eight explicitly imports supplied source helpers and a local function. Clack 0.2 also supplies explicitly imported `sum`, `all`, `any`, and `count` operators for any supported fixed-array length; try the [reduction example](../../examples/reductions.clack) and read the [library catalog](../libraries.md). No import is hidden from the examples.

## How to use the exercises

Run the unchanged program first. Predict what an edit will do before making it, then run `clack check your-file.clack` to check the reasoning without starting the executable. Use `clack run your-file.clack` when you want its output. Exercise answers explain both a result and the property the compiler needs.

Keep the distinction between a program's implementation and its promise in view. A loop can count correctly while a weak contract proves only that its answer is within a range. These lessons point out that distinction rather than claiming every visible behavior has been formally specified.

After the lessons, use the [language reference](../reference/README.md), [error guide](../errors.md), and [verification model](../verification.md) for lookup. The [documentation index](../README.md) links the rest of the handbook.
