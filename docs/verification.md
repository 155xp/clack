# Verification model

Clack checks a small static language before emitting native code. Verification is required for `check`, `emit-c`, `build`, and `run`.

## Obligations

The verifier symbolically executes function bodies. Parameters begin as arbitrary values of their declared types, restricted by the function's preconditions. Calls are checked against callee preconditions, and the callee's verified postconditions describe the result.

Claims that simplify unconditionally to `true` are discharged directly. For other obligations the verifier asks Z3 whether the current facts and the negation of the required fact can hold together. An unsatisfiable answer establishes the obligation within the model. A satisfiable answer supplies a counterexample; an unknown answer or timeout does not establish anything and must stop compilation. A constant-false claim is accepted only if its path is proved unreachable.

The implemented checks cover executable arithmetic overflow, defined division and remainder, array bounds, call preconditions, return postconditions, assertions, and loop invariants and termination. Both branches of a conditional are checked under their respective conditions. Boolean short-circuit evaluation supplies the appropriate guard when checking the right operand.

## Two integer contexts

Executable `int` values are signed 64-bit integers. Each executable intermediate must remain between `-9223372036854775808` and `9223372036854775807`. Arithmetic does not silently wrap.

Proof annotations use mathematical integers. This lets a property such as `result * result == x * x` describe large mathematical products without requiring those products to be computed in the executable. Division and indexing in annotations still need to be well-defined.

Do not infer runtime safety from the final answer alone. For example, `(x + 1) - 1` still needs `x + 1` to fit, even when the final value equals `x`.

The imported array operators are modeled directly by the compiler. `fill` constructs an array whose elements all equal its once-evaluated input; its literal count fixes the type. `minimum` and `maximum` select exact integer-array extrema using comparisons. `sum` requires each left-to-right partial addition to fit signed 64-bit range, while `count` produces the exact number of true Boolean elements and `all`/`any` use their logical meanings. These are not source helpers whose contracts are merely assumed, and they cannot be called inside proof annotations. Their verifier models and native loops are part of the trusted compiler. See the [library guide](libraries.md) for accepted inputs and array-length costs.

## Loop reasoning

A loop invariant must hold when entering the loop and remain true after each body execution that continues the loop. The verifier reasons from an arbitrary loop head, forgetting the previous values of bindings the body may modify. It must not assume the first iteration represents every iteration.

The termination measure must be an integer, must be nonnegative when an iteration begins, and must strictly decrease on continuing iterations. Reasoning after the loop uses the invariant together with the false loop condition. A return from inside the body must satisfy the function's postconditions directly.

Counted `for` loops supply their own index bounds and termination measure over bounds evaluated once. Optional user invariants establish relationships involving other changing values. General `while` loops require both invariants and an explicit `decreases` measure. Both forms use the same arbitrary-iteration checking discipline.

The current language rejects recursive call cycles. Termination of loops is checked; functions cannot hide divergence behind recursion.

This statement covers ordinary Clack functions. Main may call explicitly declared native C implementations, whose blocking, recursion, and termination are outside the mathematical model.

## Parallel reasoning

A parallel block is a group of independent calls. Each call's preconditions are checked against the same input state, and its postconditions describe its own result. Parameters and composite values have value semantics. Jobs cannot perform output or call main, and there is no mutable global state.

These restrictions remove shared-memory data races from this form of parallelism. They do not prove operating-system scheduling fairness, successful thread creation, or a performance improvement. The native implementation falls back to synchronous execution when thread creation fails.

## Trust and limits

`native` and `extern fn` establish an explicit trusted boundary for C effects such as terminal UI. C bodies are not verified, and native declarations cannot supply assumed contracts. Only main may make direct calls, and returned scalars carry no facts beyond their declared types. Guards can establish useful bounds before subsequent Clack arithmetic. The CLI reports native bindings and providers as outside the verification model. See [native bindings](native.md) for the exact restrictions and ABI.

The trusted chain includes the parser, type checker, verification-condition generator, Z3, C emitter, C compiler, runtime support, any explicitly linked native implementation, operating system, and hardware. This is an SMT-verified prototype, not a compiler verified in a proof assistant. A successful check of a mixed program establishes Clack obligations under its native boundary; it does not establish memory safety or behavior of the C provider.

Exported `.smt2` files expose the proof obligations for inspection and replay. They are not proof certificates, and exporting them does not independently certify the source-to-binary translation.

Contracts describe behavior the author chose to state. A proof of an incomplete or mistaken contract does not establish unstated intent. Output formatting and performance are outside the return-value contract system. Resource exhaustion, hardware faults, and operating-system failures are outside the mathematical execution model.

The verifier is intentionally incomplete: a correct program may be rejected because an invariant is too weak or the solver cannot establish a fact within the time limit. Strengthening a useful specification or simplifying the reasoning is the supported response; there is no unchecked escape hatch.
