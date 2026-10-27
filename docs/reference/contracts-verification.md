# Contracts and verification

[Reference index](README.md) · [Previous: functions and control flow](functions-control-flow.md) · [Next: parallel execution](parallelism.md)

## A contract states a precise promise

`requires` limits the inputs a function accepts. `ensures` states a property every returned value must satisfy for those inputs. The reserved name `result` denotes the return value.

```clack
fn increment(x: int) -> int:
    requires x < 9223372036854775807
    ensures result == x + 1
    return x + 1

fn main():
    print(increment(41))
```

This prints `42`. The precondition excludes the one integer for which addition would overflow. The postcondition tells callers exactly how the result relates to the input.

All clauses precede executable statements in the function body. Multiple clauses of the same kind are conjunctive: all must hold. The parser permits `requires` and `ensures` lines to be interleaved, but grouping preconditions before postconditions is clearer. Within each kind, source order matters when checking whether later expressions are defined.

Preconditions and postconditions may refer to parameters. Only postconditions may also use `result`. They cannot name local variables. Conditions support operators, fields, array indexing, and `len`, but cannot call a local or imported function or a constructor. A contract must have Boolean type. Importing a standard helper does not make it callable inside an annotation.

Text equality and `len(text)` have the same byte semantics in contracts as in executable code. For example, `ensures result == "Ready"` describes a text result, and `requires len(label) <= 80` limits its UTF-8 byte length. No implicit case conversion or Unicode normalization occurs.

This restriction also applies to all compiler array operators, including `fill`, `minimum`, and `maximum`. Call an operator in executable code, then express a property using its returned local value. The verifier uses its exact model and must prove every intermediate integer sum is safe.

`main` cannot declare a precondition. Program entry has no caller that could establish one. It can contain assertions and may have postconditions that do not mention a nonexistent result, although assertions usually express useful facts more directly.

## Safety is checked even without a postcondition

A function without `ensures` still needs safe arithmetic, defined division, in-bounds indexing, valid calls, and terminating loops. Its callers know only the result's declared type and any postconditions that were actually supplied.

The verifier does not expose a helper's body as an automatic definition at every call. It checks the helper once, then uses its summary. If a caller needs `twice(x) == 2 * x`, the helper should state that relation in an `ensures` clause. This keeps proofs modular when an implementation changes.

All functions, including unused ones and those in imported modules, are checked in callee-before-caller order. Standard-library code is verified too; an import does not create an unchecked foreign boundary. Recursive call cycles are rejected. There is no `assume` statement, unchecked build mode, or runtime fallback that silently accepts an unproved obligation.

A contradictory precondition describes no admissible inputs. The current compiler does not separately reject that specification as unsatisfiable: its body obligations can pass vacuously, while no reachable call can establish the precondition. Write preconditions that express inputs you actually intend to support; successful verification alone does not show that those inputs exist.

## Executable integers and mathematical integers

Executable arithmetic uses signed 64-bit integers. Every intermediate must fit, not only the final answer. For arbitrary `x`, `(x + 1) - 1` can overflow in the first addition even though the algebraic result is `x`.

Proof expressions use mathematical integers. `requires`, `ensures`, `assert`, `invariant`, and `decreases` annotations are erased after successful verification; they do not compute their arithmetic in the binary. This complete program is accepted even for inputs whose mathematical square exceeds 64 bits:

```clack
fn identity(x: int) -> int:
    ensures result * result == x * x
    return x

fn main():
    print(identity(9223372036854775807))
```

The executable returns an integer it already received; it never calculates the square. Putting `x * x` in an executable assignment would require a different range proof.

Mathematical arithmetic does not make undefined expressions acceptable. Division needs a nonzero divisor, and array access needs an in-bounds index in annotations too. Executable `/` and `%` additionally rule out the minimum integer divided by `-1`. Mathematical division uses the same truncation-toward-zero interpretation, with no 64-bit overflow limit.

## Definedness and guards

Preconditions are established in order. A first clause `requires divisor != 0` can justify division in a later clause. It cannot retroactively justify division in an earlier clause. The same principle applies to postconditions proved in sequence.

Boolean short-circuit operators supply guards inside one condition. For example, the fragment `requires divisor != 0 and value / divisor >= 0` reaches its division only when the divisor is nonzero. The fragment `requires divisor == 0 or value / divisor >= 0` is also defined: its right operand runs only with a nonzero divisor.

Executable branches supply guards too. The verifier checks only the safety obligations of an expression on the paths that reach it. Static name and type checking still applies throughout the source.

## Assertions

`assert condition` requests a proof at that source point. If the current path facts imply it, the assertion is erased and the fact may be used later. A false or unproved assertion stops compilation; it never asks the compiler to trust the programmer.

Assertions are useful for stating an expected intermediate relation and finding where reasoning first breaks. Their mathematical interpretation also lets them state properties without introducing overflow-prone runtime calculations.

## Loop invariants

A loop proof must cover any iteration, not just the first one. Before reasoning about the body, the verifier forgets the current values of local bindings the body may change and gives them arbitrary values of their declared types. Updating an array element counts as changing the array. The invariant supplies the relations that remain known at that arbitrary loop head.

For each loop the compiler checks:

1. Every invariant holds on entry using the actual incoming values.
2. The condition and body are safe under the invariant and the true condition.
3. Every continuing path through the body reestablishes all invariants.
4. The integer termination measure is nonnegative when an iteration starts.
5. Every continuing body path makes that measure strictly smaller.

After the loop, the verifier knows the invariant and the false condition. It does not retain an old value of a modified binding merely because that value was known before the loop. A return from the body proves the function's postconditions directly.

For a counted `for` loop, the compiler supplies invariant facts about the index and snapshotted bounds, plus a decreasing measure. Optional user invariants carry facts about other changing locals and are checked after the generated index increment. A counted loop does not infer an accumulator's relationship to its inputs. See [counted loops](functions-control-flow.md#counted-for-loops) for an example.

For `while i < n` with invariant `0 <= i <= n`, the false condition gives `i >= n`, so together they establish `i == n`. Without the upper-bound part of the invariant, the exit state might include values larger than `n`.

The measure is mathematical and may be negative after the final iteration if the loop will not continue. What matters is nonnegativity at each active iteration and strict decrease along each body path that reaches the next condition. A condition such as `true` does not waive the termination check.

## Reading a failed proof

For an obligation `claim`, the verifier asks Z3 whether the current path facts and `not claim` can both hold.

| Solver result | Meaning for compilation |
| --- | --- |
| `unsat` | No counterexample exists within the implemented model; this obligation passes |
| `sat` | A model violates the claim under the available facts; compilation fails with a counterexample |
| `unknown` or timeout | The solver has not established the obligation; strict compilation fails |

A `sat` model at an arbitrary loop head or a modular call can reflect an invariant or postcondition that is too weak, rather than an input that reaches a bug in the full program. Inspect the obligation and the facts that should justify it. Supply the missing true relation when appropriate. Do not strengthen a precondition merely to exclude valid inputs you intended to support.

Increasing `--timeout-ms` may help a difficult but valid proof. It cannot repair a false claim. Nonlinear arithmetic and quantified array facts can be harder for a solver than small linear relationships.

`--proof-dir PATH` exports SMT-LIB queries and an `obligations.json` manifest. Follow the manifest's query filenames when replaying a run. Replaying uses the verification conditions; it does not independently establish that the source-to-binary compiler is correct.

## Assurance boundary

The proven properties concern the written specifications and the implemented execution model. They do not establish unstated intent. A weak contract can be true of a program that does the wrong job.

The parser, module loader, type checker, obligation generator, Z3, C emitter, C compiler, operating system, and hardware remain trusted. The implementation has not been verified in a proof assistant. Resource exhaustion, scheduling fairness, output behavior, and performance are not proved by return-value contracts. See the [verification model](../verification.md) for the full boundary and the [design direction](../design.md) for stronger-assurance work proposed for later versions.
