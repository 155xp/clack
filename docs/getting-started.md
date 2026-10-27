# Install Clack and run your first program

[Handbook](README.md) · Next: [Tutorial 1](tutorials/01-first-program.md)

This guide takes you from the source distribution to a native executable. You do not need to install a proof assistant or learn C to use Clack.

## Requirements

The compiler needs Python 3.11 or newer, its `z3-solver` dependency, and a C11 compiler with POSIX threads. Development and the recorded tests use Linux. GCC and Clang are suitable C compilers; the backend targets POSIX environments, including macOS, but the repository does not contain a macOS test run. Native Windows support is not implemented; a Linux environment such as WSL is the practical starting point on Windows.

Check the tools already on your machine:

```sh
python3 --version
cc --version
```

The Python compiler and solver run during development. A generated program uses neither Python nor Z3 when it runs. The executable still depends on the platform's native C and thread facilities.

## Install from the source directory

Open a terminal in the directory containing `pyproject.toml` and `README.md`. If you downloaded a ZIP, extract it first and enter its `clack` directory.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
clack --version
```

The version command should print `Clack 0.4.0`. Installation downloads Python dependencies; compiling an installed project needs no network connection.

Activation makes the `clack` command available in the current shell. In a new terminal, activate the environment again. You can also use the explicit command without activation:

```sh
.venv/bin/python -m clack --version
```

An entry file contains `main` and may import functions and record types from other `.clack` files or the bundled standard library. There is no package registry or package manager yet. The [library guide](libraries.md) explains local imports and the available standard helpers.

## Run a program

Try the supplied first example:

```sh
clack run examples/hello.clack
```

Output:

```text
42
```

The `run` command checks the source, builds a temporary native executable, runs it, then removes the temporary build. It does this on each invocation; it is not an interpreter or a build cache.

For your own file, save the following as `answer.clack`:

```clack
fn main():
    answer = 6 * 7
    print(answer)
```

Run it with `clack run answer.clack`. Execution starts at `main`. The local `answer` gets its type from `6 * 7`, and `print` writes its value followed by a newline. Use spaces to indent blocks; four spaces is the convention used throughout this handbook.

You can also write `print("Hello, Clack")` in main. Text literals are immutable UTF-8 values with JSON-style escapes. Text manipulation is still limited; see [text and native bindings](native.md) when you want labels or an optional terminal UI package.

## Check, build, and inspect

Use `check` when you only want verification. Use `build` to keep a native executable:

```sh
clack check examples/hello.clack
clack build examples/hello.clack -o build/hello
./build/hello
```

The checking and building commands report their success and the number of proved obligations. The executable itself prints `42`. You can run `./build/hello` again without invoking the Clack compiler.

To inspect the C backend:

```sh
clack emit-c examples/hello.clack -o build/hello.c
```

`emit-c` performs the same type and proof checks before writing C. Contracts and proved assertions do not become runtime solver calls.

## Understand a rejected program

Try an intentionally invalid example:

```sh
clack check examples/rejected/out_of_bounds.clack
```

The command exits with an error because the requested array access cannot be proved in bounds. Diagnostics name the source line and failed obligation. They may include a counterexample: values that make the claimed fact fail in the verifier's model. For loop errors, these may describe an arbitrary loop head rather than a complete execution from `main`.

All builds require verification. Clack has no flag to ignore a failed proof. The [error guide](errors.md) shows how to repair common mistakes and distinguish a real bug from a missing specification.

## Next steps

Start [the tutorials](tutorials/README.md) for functions, data, loops, and parallel work. If you already know the basics, use the [quick reference](quick-reference.md) or [CLI reference](cli.md).
