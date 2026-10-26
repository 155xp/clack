# 1. Your first program

[Tutorial index](README.md) · [Next: Functions and promises](02-functions-contracts.md)

The goal of this lesson is to run a complete Clack program and understand each line. The example calculates six hours at seven units per hour. It also prints whether the answer is what we expect.

## Write and run

Open the included file `examples/tutorials/01-first-program.clack`:

<!-- clack:file=../../examples/tutorials/01-first-program.clack -->
```clack
fn main():
    hours = 6
    rate = 7
    answer = hours * rate
    print(answer)
    print(answer == 42)
```

With the environment active, run from the repository root:

```sh
clack run examples/tutorials/01-first-program.clack
```

The exact output is:

```text
42
true
```

`fn main():` names the program's entry point. The indented statements belong to it. Use spaces; four spaces per indentation level make examples easy to read. Blank lines and comments beginning with `#` are welcome.

The first assignment gives `hours` an integer value. Clack infers a local variable's type from that assignment, so you do not write a type beside every name. `rate` and `answer` are integers too. A name keeps its type if you assign another value later.

`*` multiplies integers. `==` compares two values and produces a Boolean: either `true` or `false`. Assignment uses one `=`, while comparison uses two. `print` writes one integer or Boolean followed by a newline. String values are not implemented yet, so this first program prints numbers rather than a text greeting.

## What run actually does

The `run` command parses and checks the source, proves its safety obligations, generates C, asks a C compiler to build a temporary native executable, and runs that executable. Python and Z3 belong to the compiler; the generated program does not run inside Python.

These particular values make overflow easy to rule out: `6 * 7` fits within a signed 64-bit integer. In the next lesson, a function will accept arbitrary inputs within a stated domain, and its proof will cover all those inputs.

You can check without running:

```sh
clack check examples/tutorials/01-first-program.clack
```

To keep an executable, build it:

```sh
clack build examples/tutorials/01-first-program.clack -o build/first-program
./build/first-program
```

## Exercises

1. Change `hours` to `8`. Predict both output lines.
2. Change the comparison so it checks whether the new answer is at least `50`.
3. Add `# payment calculation` above the first assignment. What changes?

<details>
<summary>Answers</summary>

1. The output becomes `56` and `false`.
2. Use `answer >= 50`. With eight hours, the Boolean output is `true`.
3. Nothing about execution changes. A comment explains the source to readers and is ignored by the parser.

</details>

Next, put a calculation behind a typed function and tell the compiler what that function promises.
