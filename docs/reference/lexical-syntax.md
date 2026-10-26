# Lexical syntax and expressions

[Reference index](README.md) · [Next: types and values](types-values.md)

## Source structure

A `.clack` file contains imports, function and record declarations, and optional explicit native source/binding declarations. These top-level forms start at the left margin. Indentation groups the statements inside a declaration, branch, loop, or parallel block. A colon ends the opening line of each block; native declarations have no body.

Use spaces for indentation. Four spaces per level is the documentation convention; the parser accepts other consistent widths. Tabs in indentation are rejected. A block must contain at least one statement. A main function with nothing to do can contain `return`.

```clack
fn main():
    # Comments explain the source; they do not execute.
    answer = 40 + 2
    print(answer)
```

Blank lines and text after `#` are ignored. Comments may contain Unicode text; identifiers must use ASCII characters. Statements normally end at a newline. Parentheses and brackets allow an expression to continue over several physical lines:

```clack
fn main():
    values = [
        10,
        20,
        30,
    ]
    print(len(values))
```

The final comma in a nonempty array, function argument list, or parameter list is optional. A trailing comma does not construct a tuple. There are no tuple literals, semicolons, inline block bodies, or explicit block-ending keywords.

## Identifiers and reserved names

An identifier starts with an ASCII letter or underscore. Subsequent characters may also be digits. Names are case-sensitive: `count`, `Count`, and `COUNT` are different names. `_` is an ordinary identifier, not a discard operator.

These words have grammatical meaning and cannot be ordinary identifiers:

```text
fn type from import native extern parallel if elif else while return assert
requires ensures invariant decreases and or not
true false int bool unit text
```

The compiler additionally reserves `result`, `print`, and `len` from function names, type names, parameter names, and local bindings. `result` denotes the returned value inside postconditions. `print` and `len` identify built-ins. Field names are parsed separately; the grammatical keywords still cannot name fields.

Top-level declarations and imports cannot use names beginning with `_clack_module_` or `_clack_reduce_`; those prefixes are reserved for internal linked-library and reduction symbols. Local bindings and parameters also cannot use the `_clack_reduce_` prefix. The public names `sum`, `all`, `any`, and `count` are not keywords; use explicit imports to access the standard operators.

`main` is the required entry-point name of the root program. It is not a general callable function: another function cannot invoke it. Imported library modules must not define it. User functions, record constructors, and explicitly imported names share a module's declaration namespace, so colliding names are rejected. There are no overloaded function declarations.

## Literals

Integer literals use decimal digits: `0`, `7`, and `123456`. Except for `0` itself, they begin with a nonzero digit. Hexadecimal, binary, digit separators, decimal fractions, and exponent notation are unsupported.

Unary `-` produces negative values. The spelling `-9223372036854775808` is accepted as the minimum signed 64-bit integer. The positive number `9223372036854775808` cannot be an executable integer value. Proof annotations have a separate mathematical interpretation described under [contracts](contracts-verification.md).

The Boolean literals are `true` and `false`. They are not interchangeable with `1` and `0`. Double-quoted JSON-style literals construct immutable `text`, so `print("hello")` is accepted in main. Text must be valid UTF-8 without embedded NUL; single quotes, triple quotes, string prefixes, and character literals are unsupported. See [text literals](../native.md#text-values) for escapes and current API limits.

Array literals use square brackets and must be nonempty. Record values use their record name as a positional constructor. See [types and values](types-values.md).

## Operator precedence

The table is ordered from strongest binding to weakest binding.

| Level | Syntax | Meaning |
| --- | --- | --- |
| 1 | `name(...)`, `value.field`, `value[index]`, parentheses | Calls, access, explicit grouping |
| 2 | unary `+`, unary `-` | Integer sign |
| 3 | `*`, `/`, `%` | Multiplication, truncating division, remainder |
| 4 | `+`, `-` | Integer addition and subtraction |
| 5 | `==`, `!=`, `<`, `<=`, `>`, `>=` | Scalar comparisons and comparison chains |
| 6 | `not` | Boolean negation |
| 7 | `and` | Short-circuit conjunction |
| 8 | `or` | Short-circuit disjunction |

Arithmetic operators at the same level associate left to right. For example, `20 / 3 * 2` means `(20 / 3) * 2`, giving `12`. Unary signs bind more tightly than multiplication. `not x < y` means `not (x < y)`, not `(not x) < y`.

Comparison operators share one precedence level. `0 <= x < 10` means `0 <= x and x < 10`; it does not compare a Boolean intermediate with `10`. A mixed chain such as `a == b < c` also means adjacent pairwise comparisons. Each pair must have compatible scalar types.

Ordinary user functions have no output or shared mutation, so repeated occurrences of a function call in a comparison chain cannot expose an ordering effect. Native calls are prohibited in expression chains. The current compiler may evaluate a shared middle expression more than once. Keep expensive computations in a local binding when using them in several comparisons.

## Division and Boolean guards

Integer division truncates toward zero. The remainder satisfies `a == (a / b) * b + a % b`, and a nonzero remainder has the sign of `a`:

```clack
fn main():
    print(-7 / 3)
    print(-7 % 3)
    print(7 / -3)
    print(7 % -3)
```

This prints `-2`, `-1`, `-2`, and `1`, each on its own line. Both `/` and `%` require a nonzero divisor. Executable division and remainder also reject the minimum integer with divisor `-1`, because the native operation would overflow.

`and` evaluates its right side only when the left side is true. `or` evaluates its right side only when the left side is false. The verifier uses that guard:

```clack
fn safe_test(x: int) -> bool:
    ensures result == (x == 0 or 10 / x > 0)
    return x == 0 or 10 / x > 0

fn main():
    print(safe_test(0))
```

The division is reached only with `x != 0`. This program prints `true`. The compiler still type-checks both operands; short-circuiting does not permit unknown names or incompatible types on a skipped branch.
