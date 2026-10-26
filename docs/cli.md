# Command-line handbook

The `clack` command checks a source file, produces a native executable, runs it, or emits the C that implements it. Every source command verifies ordinary Clack code first. There is no flag to ignore failed obligations. Explicit native C bindings are a separate trusted boundary, reported as outside the verification model.

## Install and check the installation

Run these commands from the Clack repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
clack --version
clack run examples/hello.clack
```

The last command prints `42`. Activation makes `clack` available on your shell's command path. Without activation, use `.venv/bin/python -m clack` in place of `clack`.

The compiler requires Python 3.11 or newer and its pinned Z3 dependency. Building and running additionally require a C11 compiler and POSIX threads. The implementation has been tested on Linux. Its backend targets POSIX environments such as Linux and macOS; native Windows builds are not currently supported.

`clack --help` lists commands. `clack build --help`, for example, lists that command's options. Help and version reporting work before the solver dependency is installed.

## Command summary

| Command | Result | Needs a C compiler? |
| --- | --- | --- |
| `clack check SOURCE` | Types and verification obligations checked | No |
| `clack build SOURCE` | Native executable saved | Yes |
| `clack run SOURCE` | Temporary executable built and run | Yes |
| `clack emit-c SOURCE` | Verified C11 source written | No |

Each invocation accepts one entry source file and loads the modules that file imports. Command-line paths are interpreted relative to the current working directory unless absolute. Local import paths are instead resolved relative to the importing file. There is no REPL or dependency manager for Clack programs.

For example, a program may start with `from std.array import sum4`, or load a neighboring `helpers.clack` with `from helpers import twice`. The bundled standard library is found through the installed compiler package; a local `std` directory cannot replace it. See [libraries and modules](libraries.md) and the [library tutorial](tutorials/08-libraries.md) for complete examples.

## Check without compiling

```sh
clack check examples/contracts.clack
```

A successful check prints the source path, the number of obligations proved, and the number of functions checked. An obligation is a fact such as an array index being in bounds or a return satisfying its postcondition. The count is an implementation detail; more obligations do not necessarily mean a more useful specification.

All ordinary loaded functions are checked, including functions that `main` does not call and unused source declarations from loaded libraries. Importing a function does not make its contracts trusted assumptions. A successful check verifies the supported properties in Clack's model. It does not produce an executable or a proof certificate for a particular machine binary.

When a program declares native bindings or C providers, `check` and `build` append `Native bindings: ...; C sources: ... (outside verification model).` to their success messages. Foreign declarations are type-checked, but C implementations are not inspected or proved. `check` does not compile or link their bodies. See [native bindings](native.md) for the ABI and call restrictions.

## Build a persistent executable

```sh
clack build examples/parallel.clack
./build/parallel

clack build examples/parallel.clack -o build/my-program
./build/my-program
```

Without `-o`, the output is `build/` followed by the source filename without its suffix. The build directory belongs to the current working directory, not necessarily the directory containing the source file. The compiler creates missing output directories.

Verification and C compilation must succeed before an existing executable is replaced. `build` and `run` compile every resolved `native` C provider with the generated file. `build` and `emit-c` refuse to overwrite any input source, including imported Clack or native C files. The generated C used during a normal build is temporary; request `emit-c` separately to keep a readable copy.

## Run without keeping a binary

```sh
clack run examples/arrays.clack
```

`run` verifies, compiles in a temporary directory, executes the native program, and removes the temporary files. It forwards the program's output directly. It does not print a verification banner before the program's output.

There are no built-in command-line argument or standard-input APIs. Native C bindings may provide input effects in main, but their behavior is unproved. `run` does not accept trailing application arguments, and it keeps native execution's standard output free of a compiler success banner.

## Inspect generated C

```sh
clack emit-c examples/parallel.clack -o build/parallel.c
```

Without `-o`, `emit-c` writes C to standard output, so redirection also works:

```sh
clack emit-c examples/parallel.clack > build/parallel.c
```

Create `build` first when using shell redirection; the shell opens the destination before Clack runs. The `-o` form creates parent directories itself.

For an experiment, compile the emitted file using the backend's flags:

```sh
cc -std=c11 -O3 -Wall -Wextra -pthread build/parallel.c -o build/parallel
```

Assertions and proof annotations have been checked and removed from executable code. Editing the emitted C changes the program outside Clack's verification process. See [compiler internals](internals.md) for the translation.

For a program with native providers, emitted C contains external declarations and calls; it does not copy provider bodies into that file. Supply those `.c` files when compiling emitted output manually, as shown in the [native guide](native.md).

## Choose the C compiler

`build` and `run` accept `--cc`. The default is the `CC` environment variable when set, otherwise `cc`.

```sh
clack build examples/hello.clack --cc gcc
CC=clang clack run examples/hello.clack
clack build examples/hello.clack --cc 'ccache clang'
```

The command is split into arguments using shell-like quoting and invoked directly. It is not executed through a shell: shell pipes, redirects, and variable substitutions inside `--cc` are not interpreted. Clack appends `-std=c11 -O3 -Wall -Wextra -pthread`, the temporary C path, and the output arguments.

## Give a proof more time

Every source command accepts a positive `--timeout-ms`, defaulting to `5000`:

```sh
clack check examples/loops.clack --timeout-ms 15000
```

This is the limit for each solver query, not for the entire command. A program may generate many queries. A timeout or other `unknown` solver result stops compilation. Raising the timeout can help a difficult query; it cannot repair a false contract or replace a missing invariant.

## Export verification conditions

```sh
clack check examples/contracts.clack --proof-dir build/proofs
```

The directory contains numbered SMT-LIB queries such as `0001.smt2` and an `obligations.json` manifest. An entry has this shape:

```json
{
  "id": 1,
  "function": "clamp",
  "line": 8,
  "claim": "postcondition of clamp (line 3)",
  "status": "unsat",
  "query": "0001.smt2"
}
```

Names, counts, and line numbers depend on the program. For a program loaded from files, entries also include a `source` path; the `line` identifies the original source line and imported function names use a readable module name. The solver checks the current facts together with the negation of the claim. `unsat` means no counterexample exists in that query's model; `sat` means one exists; `unknown` means the query was not established.

An attempted verification writes results accumulated before failure. A parse or type error can occur before any new export is created. Reusing a directory does not remove older numbered files, so use the manifest from the current run, or choose a fresh directory. These files are reproducible verification conditions, not independently checked proof certificates. The [verification model](verification.md) explains the trust boundary.

## Exit status and common setup problems

Successful checks and builds return status `0`. Source diagnostics, missing files or dependencies, and C compiler failures return `1`. Invalid command usage returns argparse's status `2`. Interrupting compilation returns `130`. `run` propagates the native process status; a process terminated by a signal is represented as `128 + signal number`.

If `clack` is not found, activate the environment or use `python -m clack` with the environment's Python. If Z3 is missing, reinstall with `python -m pip install -e .`. If the C compiler is missing, install a compiler with POSIX thread support or select one with `--cc`. A diagnostic arising in a loaded module reports that module's original file and line, so open the named file rather than assuming the problem is in the entry file. For source failures, start with the [error guide](errors.md).

[Handbook](README.md) · [Tutorials](tutorials/README.md)
