# Frequently asked questions

## What is Clack trying to make easier?

Clack aims to combine a small, readable language surface with native execution and explicit, checkable promises. Ordinary code uses functions, inferred local variables, records, arrays, and control flow. Independent work uses a `parallel:` block rather than thread objects, locks, and manual joins.

The current release is an original prototype of that design. It is useful for learning the model and writing small verified native programs. It is not yet a complete replacement for Go, Rust, Python, or C. See the [implemented reference](reference/README.md) and the separate [roadmap](design.md).

## Does Clack run on Python?

The compiler is written in Python. It parses and checks a Clack program, asks Z3 to discharge proof obligations, emits C11, and invokes a native C compiler. The resulting executable runs without Python or Z3. Clack source is not passed to Python's evaluator or executed as Python code.

An indentation-based syntax does not require an interpreted runtime. It also does not, by itself, guarantee performance: data layout, generated code, algorithms, and the backend matter.

## Is it as fast as C or Rust?

It has an efficient starting point: signed machine integers, by-value native records and fixed arrays, optimized C output, and no interpreter in the resulting binary. One recorded arithmetic workload had similar Clack and C timings. That is useful evidence for that kernel, not a universal promise.

There is no representative application suite or Rust comparison yet. Copying a large by-value array can cost time, and creating a thread for a tiny job can make it slower. The [benchmark guide](../benchmarks/README.md) explains the recorded experiment and how to reproduce it.

## How much type annotation is required?

Function parameters, function results other than main's, and record fields declare types. Locals infer a type from their first assignment and retain it. `int` means signed 64-bit integer; `bool` means `true` or `false`. There are no implicit integer/Boolean conversions.

Array lengths are part of their types. `[1, 2, 3]` has type `int[3]`, so it cannot be passed to a function expecting `int[4]`. Records give a name to a fixed collection of fields. Strings, floating-point numbers, generic types, slices, and dynamic collections are not implemented yet.

## Do I need to write a proof for every statement?

No. The verifier generates safety obligations for ordinary executable operations and tries to establish them automatically. You state behavioral promises with `requires` and `ensures`; `assert` asks it to prove a fact at a particular point.

Loops need invariants and a decreasing integer measure. These supply information that cannot generally be inferred automatically. A straight-line function may need very little annotation, while a more complicated loop needs a stronger explanation. The [tutorials](tutorials/README.md) build up to this gradually.

## Is there a standard library with sum, min, or sorting?

There is a small verified standard library. Import scalar helpers with `from std.math import min, max, abs, clamp`. Import fixed-array helpers with `from std.array import sum2, sum3, sum4, sum8, all4, any4`. These are Clack functions loaded from bundled source and verified when used; the compiler's only builtins remain `len` and `print`.

The sums accept integer arrays of exactly the named length. Their contracts require each cumulative addition to fit signed 64-bit range. `all4` and `any4` accept `bool[4]`. There is no generic `sum`, dynamic collection library, or `sort` yet. In some self-contained examples, `sum4` is defined directly in the example instead of imported; neither form makes it a compiler builtin.

The [library reference](libraries.md) gives signatures and preconditions. The [library tutorial](tutorials/08-libraries.md) shows both bundled helpers and your own modules.

## Does a successful check mean the program does what I wanted?

It establishes the implemented safety checks and the contracts you wrote, within Clack's model. It does not establish a behavior you did not specify. A function can satisfy `ensures result >= 0` while returning the wrong nonnegative answer for your application.

The compiler, verification-condition generator, Z3, C backend, C compiler, operating system, and hardware remain trusted. The compiler itself has not been formally verified in a proof assistant. Exported SMT files are queries for inspection and replay, not independently checked certificates of the source-to-binary translation. Read the [verification model](verification.md) for the exact scope.

## Can a correct program be rejected?

Yes. A loop invariant may be too weak to describe a useful fact. A helper may have no postcondition that tells the caller what it returns. The solver may time out on a hard arithmetic query. The type checker also uses conservative control-flow rules rather than proving all possible reachability facts.

Improve the available specification or simplify the reasoning. Increasing the query timeout is sometimes useful. There is no unchecked build switch, and an `assert` must itself be proved. The [error guide](errors.md) distinguishes failed claims from unknown solver results.

## Why are proof integers different from executable integers?

Executable arithmetic must fit signed 64-bit bounds at every intermediate. Proof annotations describe mathematical properties without computing them in the native program. A property such as `result * result == x * x` can therefore describe an integer's square even when that mathematical square would not fit in an executable `int`.

Division and array indexing inside annotations still have to be well-defined. Mathematical annotations are not permission to execute an overflowing expression in a function body.

## Is parallelism asynchronous?

A `parallel:` block runs independent calls concurrently and waits for all of them. It is structured parallel work, not an asynchronous event loop or a collection of futures that outlive their scope. Results become available after the block.

The current backend creates POSIX threads for the jobs. There is no persistent worker pool, task-stealing scheduler, cancellation interface, GPU backend, automatic loop parallelization, or `async`/`await`. A failed thread launch executes that job synchronously to preserve result semantics.

## How are data races avoided?

Workers receive values. Arrays and records are passed by value, parameters are immutable, there are no mutable globals, and only main can print. A worker can modify its own local copy of an array, but cannot modify another worker's input through a shared reference. The compiler also rejects arguments that depend on a sibling result in the same parallel block.

These rules remove shared-memory races from the supported job model. They do not establish scheduling fairness or guarantee a speedup. Any future shared-memory or foreign-function feature will need its own precise rules.

## Is there a garbage collector or ownership syntax?

Neither is exposed by the current language. Data consists of fixed-size native values, with no language-level dynamic allocation or user-visible pointers. This keeps the prototype's lifetime and sharing rules small. The operating system's thread implementation can still allocate resources internally.

Dynamic collections will require a larger memory model. The [design direction](design.md) discusses ownership and regions as future work; it does not describe syntax accepted today.

## Can I split code across files?

Yes. A program can import explicit functions and records from local `.clack` modules. `from helpers import twice` loads a neighboring `helpers.clack`; `from tools.numeric import twice` loads `tools/numeric.clack` relative to the importing file. Reusable library files must not define `main`. Imports have no aliases or wildcard form, and there is no package registry or dependency manager yet.

Bundled `std` modules come from installed package resources rather than a local directory. All declarations in loaded libraries are checked, including unused ones. An import is a reuse mechanism, not a way to trust an unchecked contract.

## Can I write recursive functions?

Direct and mutual recursion are still rejected, including cycles that cross module boundaries. Loops express repeated work and carry explicit termination measures. Clack also has no foreign-function interface yet. These are current limits; the [design direction](design.md) describes possible extensions separately.

## Where should I start?

Use the [tutorial path](tutorials/README.md) for guided learning, the [language reference](reference/README.md) for exact rules, the [CLI handbook](cli.md) for commands, and the [error guide](errors.md) when a check fails. To work on Clack itself, read [compiler internals](internals.md) and [contributing](contributing.md).

[Handbook](README.md)
