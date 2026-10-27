# Clack language reference

This reference specifies the language accepted by Clack 0.6. It describes the current compiler, including its restrictions. The [design direction](../design.md) covers features that are still proposals.

If you are learning Clack for the first time, start with the [tutorials](../tutorials/README.md). Use this reference when you need the exact rule for an expression, declaration, proof, or parallel block.

| Chapter | Questions it answers |
| --- | --- |
| [Lexical syntax and expressions](lexical-syntax.md) | How do indentation, names, literals, and operator precedence work? |
| [Types and values](types-values.md) | What can a value contain? When does assignment make a copy? |
| [Functions and control flow](functions-control-flow.md) | How do calls, local bindings, branches, loops, and built-ins behave? |
| [Contracts and verification](contracts-verification.md) | What must be proved? What can a failed proof mean? |
| [Parallel execution](parallelism.md) | Which jobs may run together, and how are their results collected? |
| [Grammar](grammar.md) | What is the accepted syntax in one place? |

Clack programs are verified before C generation. A syntactically valid program may still fail type checking or verification. For example, `x + 1` has the right type when `x` is an integer, but it needs a proof that the addition cannot overflow.

Examples explicitly labelled **fragment** belong inside a larger definition or program. Other `clack` examples in this reference are complete source files with their own `main` entry point.

For compiler commands, use `clack --help` and `clack <command> --help`. The [library guide](../libraries.md) covers standard helpers and reusable local modules. The [verification model](../verification.md) explains the trusted components behind the checks, and the [benchmark notes](../../benchmarks/README.md) explain the scope of the recorded performance measurements.
