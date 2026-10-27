# Design direction

Clack aims for a small language surface that can grow into systems work without requiring users to manage every low-level detail. The first compiler establishes a testable foundation. It does not yet provide a complete general-purpose ecosystem.

## Principles

Everyday programs should need ordinary expressions, functions, records, collections, and clear control flow. More advanced work should compose those same ideas. Syntax should reveal a meaningful choice, such as running independent calls together, rather than expose implementation bookkeeping.

Fast execution needs a predictable representation and a good native backend. Proofs need precise semantics and explicit behavioral promises. Simple source syntax alone cannot supply either property. Clack keeps those responsibilities in its compiler and type system where possible.

There is also a practical tradeoff: arbitrary program correctness cannot be decided automatically. The goal is to prove common properties with little help, show useful counterexamples, and request stronger specifications when necessary. It is not to promise a push-button proof of any program.

## Implemented foundation

| Area | Current implementation |
| --- | --- |
| Syntax | Indentation, inferred local types, plain functions and records, counted `for` loops |
| Execution | Optimized C11 output and native executables |
| Data | Signed 64-bit integers, Booleans, immutable text with equality and byte length, fixed scalar arrays, value records |
| Verification | SMT checks for arithmetic, bounds, contracts, assertions, loops |
| Parallelism | Independent function calls using POSIX threads and value arguments |
| Effects | Output restricted to main; no mutable globals |
| Native boundary | Explicit main-only scalar/text C calls; provider implementations remain outside verification |
| Libraries | Explicit source imports, isolated module names, verified math/fixed-size helpers, compiler-modeled array operators, and optional numeric, ML, algorithm, and terminal packages |

## Next steps

These are design proposals, not syntax accepted by the current compiler.

1. **Better daily tooling.** A formatter, language-server integration, package dependency resolution, and concise explanations for failed obligations. Source maps, a source-package layout, an API catalog, and agent documentation already exist. Error messages should distinguish an actual counterexample from insufficient solver knowledge.
2. **More useful data.** Text concatenation, indexing, dynamic text, slices, dynamic arrays, tagged unions, pattern matching, and generic functions. Tagged unions should make absent values and recoverable errors explicit without making every call ceremonial.
3. **A memory model that scales.** Use values by default, infer moves and regions when possible, and introduce explicit borrowing only where it expresses a real aliasing choice. Dynamic storage must have a precise lifetime and alias model before it participates in proofs or shared work.
4. **Structured parallel collections.** Add collection operations that distribute independent work over a worker pool. Preserve deterministic result ordering and establish that each task owns its mutable output. GPU support would require a separate backend and a defined supported subset.
5. **Deeper specifications.** Reusable predicates, refinement types, mathematical sequences, quantified collection properties, and verified libraries would make useful contracts shorter. Recursive definitions need a termination story before recursive functions are accepted.
6. **Systems integration.** Package management above the current source-import system, richer effect tracking above the current main-only C boundary, complex native data layouts, and independently reviewed runtime support. Native contracts would need a precise assurance story before the verifier could accept them as facts.
7. **Stronger assurance.** Differential testing, compiler fuzzing, small-step reference semantics, and independently checked proof artifacts. A proof-assistant model could then validate parts of the verifier or compiler rather than treating them all as trusted.
8. **Measured performance.** Representative kernels and applications compared against equivalent C and Rust, with matching algorithms and safety behavior. Inspect generated code and optimize demonstrated bottlenecks before claiming parity.

The target is a language that feels small at the keyboard while supporting rich libraries and large programs. Reaching that target requires extending the semantics and tooling carefully; adding more syntax is not the main measure of progress.
