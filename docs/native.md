# Text and native bindings

[Handbook](README.md) · [Types](reference/types-values.md) · [CLI](cli.md)

Clack supports immutable `text` values and an explicit native C boundary. This is enough for labels, terminal output, and optional terminal UI libraries while keeping verified worker functions separate from operating-system effects.

## Text values

```clack
fn label() -> text:
    return "Clack"

fn main():
    title = label()
    print(title)
    print("Ready\nPress a key")
```

Output:

```text
Clack
Ready
Press a key
```

Text uses double-quoted JSON-style literals. Supported escapes are `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, and `\uXXXX`; valid Unicode surrogate pairs are accepted, and lone surrogates are rejected. Source text must encode valid UTF-8 and cannot contain an embedded NUL. Single quotes, triple quotes, and Python-style string prefixes are not accepted.

Text contents are immutable. A local binding may be assigned another text value, and ordinary functions and records may pass or return text. All current runtime text originates in static literals; there is no dynamic text allocation or mutable character buffer in the language.

This is a small text API, not a general string library. Text concatenation, equality, ordering, character indexing, `len(text)`, text arrays, and native functions returning text are unsupported. `len` still accepts only fixed integer or Boolean arrays.

## Declare an explicit C boundary

Create these two files in one directory. Save the Clack file as `app.clack`:

```clack
native "terminal.c"

extern fn show_title(title: text) -> unit = "clack_demo_title"
extern fn terminal_width() -> int = "clack_demo_width"

fn main():
    show_title("Clack")
    width = terminal_width()
    if 0 <= width <= 10000:
        padded = width + 1
        print(padded)
```

Save the C provider as `terminal.c`:

```c
#include <stdint.h>
#include <stdio.h>

void clack_demo_title(const char *title) {
    puts(title);
}

int64_t clack_demo_width(void) {
    return INT64_C(80);
}
```

Then run:

```sh
clack check app.clack
clack run app.clack
```

The run prints `Clack` and then `81`. The successful `check` message also identifies the native bindings and C sources as **outside the verification model**. Checking does not compile or prove the C provider; `run` and `build` compile it with the generated C.

The `native` path is relative to the file declaring it. It must identify a `.c` file below that module's directory: absolute paths, `..` traversal, and symlink escapes are rejected. Imported modules may declare their own providers, and resolved C paths are linked once. The compiler also protects these input files from being overwritten by build outputs.

An `extern fn` declaration has no body or `requires`/`ensures` clauses. It names the C symbol after `=`. Symbols must begin with `clack_`, use ASCII C identifier characters, and avoid compiler prefixes such as `clack_fn_`, `clack_t_`, `clack_v_`, `clack_worker_`, `clack_task_`, `clack_reduce_`, and `clack_for_`.

## C ABI

| Clack type | C representation | Allowed at the native boundary |
| --- | --- | --- |
| `int` | `int64_t` | Parameter or result |
| `bool` | C `bool` / `_Bool` | Parameter or result |
| `text` | `const char *`, NUL-terminated UTF-8 | Parameter only |
| `unit` | `void` | Result only |

Use `<stdint.h>` for integers and `<stdbool.h>` when writing C Boolean signatures. C definitions must match the declared types exactly. Native calls do not accept records or arrays. Text bytes are read-only; the C provider must not mutate or free them.

`emit-c` emits declarations and calls but does not combine provider contents into the generated file. Link the providers explicitly if compiling that output manually:

```sh
clack emit-c app.clack -o build/app.c
cc -std=c11 -O3 -Wall -Wextra -pthread build/app.c terminal.c -o build/app
```

## Where native calls are allowed

Only `main` may call a native binding. A unit-returning binding is a standalone statement, and an integer- or Boolean-returning binding is the direct right-hand side of an assignment. These statements may occur in main's ordinary control flow.

Calls cannot be nested inside another call, arithmetic, a condition, a return expression, or a proof annotation. A native binding also cannot be a parallel job or be called by an ordinary helper. Store a result in a local first, then use that local in checked code.

For example, `width = terminal_width()` is accepted. `print(terminal_width())`, `if terminal_width() > 0:`, and `width = terminal_width() + 1` are rejected. After assignment, `if width > 0:` is ordinary checked control flow.

## What is proved

A native return value is a fresh arbitrary value of its declared result type. The verifier does not assume the C implementation returns `80` in this example; `width` could be any signed 64-bit integer. The explicit upper bound in the branch is what makes `width + 1` provably safe.

The C provider's memory behavior, output, system calls, blocking, termination, and implementation correctness are trusted and unproved. A successful Clack check verifies the Clack portion under that boundary, not the entire mixed C program. Native bindings intentionally do not accept user-written contracts that would turn unverified C promises into trusted postconditions.

An optional terminal UI package can use this boundary for screen drawing and input events while leaving application data and pure worker functions in checked Clack. Its native code and terminal-resource handling still need ordinary review and tests. See [the verification model](verification.md) for the overall trust chain.
