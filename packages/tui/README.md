# Clack TUI

Small native terminal interfaces for Clack: panels, status rows, progress bars, and keyboard-selectable actions. The application compiles to a native executable; Python is used by the compiler and tests, not by the running interface.

This is an optional source package. It does not add widgets or terminal handling to Clack's standard library.

## Requirements

- Clack 0.5 or newer with `text` and native-module support.
- A C11 compiler and a POSIX terminal. Linux is the tested platform; the backend also targets macOS.
- No curses installation, terminal framework, or Python runtime is required by the executable.

The package contains [tui.clack](tui.clack), its explicit native declarations, and [terminal.c](terminal.c), the rendering and input implementation. Clack builds the C implementation when a program imports the module.

## Put an interface in your program

The package ships in the main Clack repository. Install its compiler and run the demo from the checkout root:

```sh
git clone https://github.com/155xp/clack.git
cd clack
python3 -m venv .venv
.venv/bin/python -m pip install -e .
. .venv/bin/activate
.venv/bin/python -m clack run packages/tui/demo.clack
```

Save this as `app.clack` at the checkout root:

```clack
from packages.tui.tui import begin, panel, label, metric, progress, option, run, end

fn main():
    begin("Build dashboard")
    panel("Compiler")
    label("Native output. Checked source.")
    metric("Jobs ready", 4)
    progress("Build", 7, 10)
    option(1, "Run benchmarks")
    option(2, "Inspect results")
    selected = run()
    end()
    print(selected)
```

```sh
clack run app.clack
# Or keep the executable:
clack build app.clack -o build/dashboard
./build/dashboard
```

`begin` starts collecting a scene. The following calls add its contents. `run` draws the interface, returns the selected action ID, and restores the terminal before returning. `end` is an idempotent cleanup call. Action IDs should be distinct positive integers; nonpositive options are ignored, and `0` means cancellation or noninteractive execution.

The package's [demo.clack](demo.clack) imports its adjacent `tui.clack` directly. For a separate application, copy this entire folder, including `terminal.c`, beside its entry file as `tui/`, then import `from tui.tui import ...`. Module paths are relative to the importing file.

## Just need a menu?

```clack
from packages.tui.tui import menu3

fn main():
    selected = menu3("Choose a task", "Build", "Benchmark", "Quit")
    print(selected)
```

The choices return `1`, `2`, or `3`; cancellation returns `0`. The convenience function restores the terminal before returning.

## API

| Function | Purpose |
| --- | --- |
| `begin(title: text)` | Start a new scene with a title. |
| `panel(title: text)` | Add a section heading. |
| `label(value: text)` | Add a line of text. |
| `row(name: text, value: text)` | Add a label and textual value. |
| `metric(name: text, value: int)` | Add a label and an integer value. |
| `progress(name: text, value: int, total: int)` | Add a bounded progress indicator. |
| `option(id: int, name: text)` | Add a selectable action. |
| `run() -> int` | Display the scene, wait for selection or cancellation, and restore the terminal. |
| `end()` | Restore the terminal if needed; safe to call more than once. |
| `menu3(title: text, first: text, second: text, third: text) -> int` | Display and finish a three-choice menu. |

Functions without a shown result return `unit`. These are native effects: call them only from `main`, as standalone statements or direct assignments. Write `selected = run()` followed by `print(selected)`; nesting the input operation in `print(run())` is not accepted. Arguments may contain ordinary pure expressions.

## Keyboard and output behavior

- Up/Down arrows or `k`/`j` move between actions.
- Enter selects the highlighted action.
- `q` or Escape cancels.
- The renderer adapts to the terminal's current size and crops content that does not fit.

Interactive mode uses terminal raw input and an alternate screen, then restores normal terminal settings and cursor state on completion. Cleanup also covers normal process exit and handled interruption signals. Prefer calling `end` explicitly when building a scene yourself.

When input or output is not a terminal, or `TERM=dumb`, `run` prints a plain report and returns `0` without waiting for a key. This makes redirected output and unattended checks usable. `NO_COLOR` disables color while retaining interactive keyboard behavior in a normal terminal. Set `CLACK_TUI_ASCII` to a nonempty value to use ASCII borders and arrows.

The scene holds at most 128 items, and each text field holds 255 UTF-8 bytes plus its terminator. Long text is truncated at a UTF-8 boundary rather than allowing writes past a buffer, and ASCII terminal control characters in labels are sanitized. This first package builds one scene at a time; it does not provide mutable widget objects, callback registration, or an asynchronous event loop.

## Verification boundary

Clack checks the typed expressions and contracts in your Clack code. The `native` and `extern` declarations explicitly introduce a C implementation that is outside that proof model. Terminal rendering, input, native memory handling, and operating-system behavior are trusted native code, not formally verified widget behavior.

The library tests exercise the native implementation, including selection, cancellation, and terminal cleanup. Those tests provide evidence about behavior; they are not formal proofs of the C code.

## Develop and test

With Clack installed in the active Python environment, run:

```sh
python -m unittest discover -s packages/tui/tests -v
clack check packages/tui/demo.clack
clack run packages/tui/demo.clack
```

The tests use Python's pseudo-terminal support to drive real native executables. Python is test infrastructure only. See [LICENSE](LICENSE) for the MIT terms.

## For coding agents

Import only the names used by the program. Keep every TUI call in `main`, assign `run()` or `menu3(...)` directly to a local, and treat result `0` as cancellation or noninteractive output. The C provider is trusted, so successful Clack verification does not prove terminal or memory behavior inside it. Preserve the nonblocking plain-output fallback when extending the package.
