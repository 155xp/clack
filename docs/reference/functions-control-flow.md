# Functions and control flow

[Reference index](README.md) · [Previous: types and values](types-values.md) · [Next: contracts and verification](contracts-verification.md)

## Programs and declarations

A complete program has one root source file containing exactly one `main` function. Execution begins there. A source file may also import names and declare helper functions and records. There are no top-level executable statements or mutable globals. Imported modules contain reusable declarations and must not define their own `main`.

```clack
fn main():
    print(larger(12, 7))

fn larger(a: int, b: int) -> int:
    ensures result >= a and result >= b
    ensures result == a or result == b
    if a >= b:
        return a
    return b
```

This prints `12`. A function may be used before its textual declaration. The compiler collects declarations before checking their bodies and verifies callees before callers.

Every function is checked, including an unused helper in an imported module. An invalid unused definition cannot hide an unproved contract or an unsafe operation. Duplicate function names, duplicate parameter names, duplicate type names, and colliding declarations or imported names are rejected.

## Imports and libraries

Use a top-level `from` declaration to bring selected functions or record types into the current module:

```clack
from std.math import clamp
from std.array import sum4

fn main():
    bounded = clamp(150, 0, 100)
    total = sum4([10, 20, 30, 40])
    print(bounded)
    print(total)
```

This prints `100` and `100`. Imported functions use ordinary call syntax and ordinary verified contracts. They are not extra compiler built-ins. Importing a name is explicit; qualified calls such as `std.math.clamp(...)`, wildcard imports, and import aliases are unsupported.

Standard modules currently provide `std.math` (`min`, `max`, `abs`, `clamp`) and `std.array` (`sum2`, `sum3`, `sum4`, `sum8`, `all4`, `any4`). The fixed-size sum functions require every left-to-right cumulative sum to fit in a signed 64-bit integer. They do not impose a blanket small-value bound on each element. `abs` excludes the minimum signed integer, whose positive magnitude is not representable.

A local module can live in `helpers.clack` and be used with `from helpers import twice`. Dotted names describe subdirectories, for example `from tools.numeric import twice` for `tools/numeric.clack`. Imported definitions are resolved separately from a caller's local names. See the [library guide](../libraries.md) for file layout, resolution rules, record imports, and complete reusable-module examples.

Local module paths are relative to the importing file's directory, not the shell's working directory. Names starting with `std.` resolve only inside the bundled standard library. There is no implicit search path, leading-dot relative import syntax, package download step, or runtime module initializer.

A module exports its own functions and records plus names it explicitly imports. This permits a small facade module to reexport selected helpers. Names not explicitly imported into the caller are not made callable there merely because the loader also checks the rest of a library's implementation. Repeating an import that introduces the same local name is a conflict, even if it would refer to the same declaration.

The loader reads each resolved module once. Cyclic module imports are rejected, independently of the later check for recursive function calls. Diagnostics for an imported definition identify its original source file and line. The public command interface handles loading and verification together; using the parser alone does not resolve imports.

## Signatures and calls

Function parameters have explicit types. Every function except `main` also needs an explicit result type. The result can be an integer, Boolean, fixed array, or record. Only `main` may return `unit`.

Calls use a locally declared or imported function name and positional arguments. There are no default arguments, keyword arguments, variadic arguments, function-valued variables, or closures. At a call, the compiler checks argument count, corresponding argument types, and all declared preconditions. A result is described to the caller by the callee's verified postconditions and its declared type.

Parameters cannot be reassigned, and array parameters cannot be mutated. A local copy may be changed. Keeping input values immutable also gives postconditions a stable meaning: references to parameters always denote the inputs received by that invocation.

Calls to `main` are forbidden. Helpers cannot print. Their observable language-level result is their returned value; they may use local mutation and may invoke independent parallel work. Direct and mutual recursion are rejected, including a cycle involving calls made by parallel jobs.

## Local bindings

The assignment `name = expression` introduces a local binding when that name is new. Its inferred type remains fixed throughout the function. Reassignment changes its value, not its type. Names cannot shadow parameters by assigning a new local with the same spelling.

A local must be assigned on every path that reaches a use. Branches do not create separately shadowed variables. This complete program assigns the same local in both arms:

```clack
fn label(is_positive: bool) -> int:
    ensures result == 1 or result == -1
    if is_positive:
        value = 1
    else:
        value = -1
    return value

fn main():
    print(label(false))
```

It prints `-1`. If the `else` assignment were removed, `value` could be undefined at the return. A branch that returns does not need to establish bindings for later statements because that path never reaches them.

A binding introduced only inside a loop is unavailable after the loop: the loop may execute zero times. Initialize values needed after a loop before entering it. The compiler applies these structural rules even when a condition appears mathematically constant.

## Conditional statements

`if`, optional `elif` arms, and an optional final `else` choose a branch using Boolean conditions. Each arm has an indented, nonempty body. Integer truthiness and conditional expressions are unsupported.

The verifier checks a branch with its condition added to the known facts. Thus an `if divisor == 0` branch can return early, leaving a provably nonzero divisor on the path after it. Static type checking still visits all branches, including one the solver could prove unreachable.

## Return and expression statements

`return expression` ends a value-returning function. All paths must return a value of the declared result type. An implicit final expression is not a return. The compiler does not synthesize an arbitrary default result.

`main` may finish at the end of its body or use bare `return`. It cannot return a value. A statement after an unconditional return is rejected as unreachable. The native executable's wrapper exits with status zero after `main` completes normally; the language currently has no user-controlled exit-status API.

Only `print(...)` may stand alone as an expression statement. A non-unit helper result cannot simply be discarded by writing `helper(...)`. Assign the result to a local and use it as appropriate. `_` is an ordinary local name if a result is deliberately not needed.

## While loops

`while` is the only loop form. Its condition is a Boolean. The body begins with one or more `invariant` clauses, followed by exactly one `decreases` clause, then executable statements:

```clack
fn count_to(n: int) -> int:
    requires 0 <= n <= 1000000
    ensures result == n
    i = 0
    while i < n:
        invariant 0 <= i <= n
        decreases n - i
        i = i + 1
    return i

fn main():
    print(count_to(3))
```

This prints `3`. Annotations are proof expressions, not executable statements. The body must still contain an executable statement after the annotations.

A return may exit a loop. There are no `break`, `continue`, `for`, `range`, or generator constructs. Every loop needs a verified termination argument. See [contracts and verification](contracts-verification.md) for what the annotations must establish.

## Parallel blocks

`parallel:` contains named calls to locally declared or imported functions. It waits for all jobs before execution continues. It is a statement, not an expression producing a future or task handle. Parallel bindings become ordinary local values after the block. The detailed input and dependency rules are in [parallel execution](parallelism.md).

## Built-in functions

| Built-in | Input | Result and restrictions |
| --- | --- | --- |
| `print(value)` | One `int` or `bool` | Prints one line; callable only in `main`; no assignable value |
| `len(values)` | One fixed scalar array | Returns its length as `int`; allowed in executable and proof expressions |

Standard-library helpers are ordinary Clack definitions supplied through explicit imports; they do not change this built-in table. Console input, file I/O, networking, command-line arguments, clocks, random numbers, and foreign-function calls are not current language APIs. Native POSIX threads are used by the generated implementation of `parallel`, rather than exposed as low-level library objects.
