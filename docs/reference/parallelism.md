# Parallel execution

[Reference index](README.md) · [Previous: contracts and verification](contracts-verification.md) · [Next: grammar](grammar.md)

`parallel:` groups independent function calls and waits for their results. It is the current high-level interface to native multithreading. Users do not create thread objects, lock a mutex, or choose an atomic memory ordering.

## A complete example

```clack
fn square(x: int) -> int:
    requires -1000000 <= x <= 1000000
    ensures result == x * x
    return x * x

fn main():
    parallel:
        left = square(12)
        right = square(20)
    print(left + right)
```

This prints `544`. Both jobs satisfy `square`'s precondition. Their verified postconditions establish their result values, which also make the final addition provably safe. This is a syntax example; such small jobs usually do not justify thread-creation overhead.

## Job syntax and result bindings

Each job has the form `name = worker(arguments)`, where `worker` is a locally declared or imported ordinary Clack function other than `main`. A job must be a direct function call. A constructor, native binding, built-in, arithmetic expression, branch, or arbitrary statement cannot occupy a job line. Standard helpers such as an explicitly imported `sum4` can be jobs because they are ordinary verified Clack functions.

The imported `sum`, `all`, `any`, and `count` operators are implemented by the compiler, so they are not direct job targets. Put a reduction inside a typed worker function when the larger operation should run as a job. Such a worker follows the same ordinary contract and purity rules as any other function.

The block contains at least one job, and result names must be distinct. Each name follows the ordinary local-binding rules: an existing binding may receive another value of the same type, but parameters cannot be overwritten. A job may return an integer, Boolean, array, or record.

Result bindings become available after all jobs finish. There is no syntax for awaiting just one job or using a partially completed block. Result collection follows the names in source; task completion order does not affect which result is assigned to which name.

## Inputs are snapshots

Every argument is evaluated before the block's jobs are launched, using the incoming local state. All arguments and returned composites have [value semantics](types-values.md). A worker cannot change a caller's value or another worker's input.

The compiler rejects any argument expression that mentions any result name from the same parallel block. This rule also applies when that name existed before the block. For example, this fragment is rejected even if `left` already held a value:

```clack
parallel:
    left = square(12)
    right = square(left)
```

The second job reads a result name of its own block. If it needs the old value, copy that value to a differently named local before the block. If it needs the new result, put the dependent work after the block:

```clack
parallel:
    left = square(12)
    right = square(20)
combined = left + right
```

These fragments assume the `square` definition and a surrounding function, with the necessary range facts. Constructors and helper calls may appear inside job arguments as ordinary expressions, provided all type and proof requirements hold and none reads a result binding of the block.

## Why workers cannot race over language values

Helpers receive values, parameters are immutable, and there is no mutable global state. Only `main` can print, and helpers cannot call `main`. A worker can mutate its local bindings and local array copies without exposing that state to another worker.

As a result, supported jobs have no shared mutable language data to race over. This is a restriction on the language's permitted effects, not a dynamic race detector. There are no user-visible shared references, atomics, locks, or channels. Explicit native bindings are restricted to main and cannot be reached from workers; the C implementations themselves are outside the proof model.

Each worker's contract is checked in the same way as an ordinary call. Parallelism does not weaken preconditions, permit overflow, or turn unknown solver results into accepted programs. The callee's verified postconditions describe its output after the block.

## Nested work and loops

A parallel block may appear inside a helper or a loop. A helper called as a job may itself create a parallel block, wait for its child jobs, and return a result. Nested work is therefore supported through ordinary function calls.

The static call graph must remain acyclic. Nested blocks do not enable recursive task spawning. Enclosing while loops need invariants and a termination measure; counted for loops supply index bounds and progress automatically. The block waits for all of its own jobs before the caller continues; there are no detached tasks.

The current implementation does not bound the number of simultaneously active native threads with a worker pool. A deep chain of helpers or a large fan-out can create more threads than is useful. Keep the first programs' groups small and jobs substantial, and measure the workload you care about.

## Native execution and failure behavior

The C backend prepares separate argument/result storage for every job and snapshots every argument before starting any job. For a block with N jobs, it attempts to create POSIX threads for the first N−1, runs the last job on the calling thread, then joins the successfully started threads before assigning result bindings. A one-job block runs directly without creating a thread. This lets the caller contribute work and avoids one thread creation and join per block.

If `pthread_create` fails, that job runs synchronously in the caller. It still produces the same language-level value. Synchronous fallback can delay launching later jobs, so the implementation does not promise simultaneous execution or a particular interleaving. If joining a successfully created thread fails, the generated process aborts; that operating-system failure is outside the mathematical contract model.

The operating system chooses scheduling and CPU placement. Clack has no public thread-count option, priority control, cancellation API, futures API, or GPU backend. Native thread availability and sufficient memory are resource conditions, not consequences of a proof about returned values.

## Choosing useful parallel work

Parallelism can reduce wall time when jobs perform enough independent computation and CPU time is available. Creating and joining threads has a cost, as can passing large values. Running several tiny arithmetic functions may take longer than direct calls.

Use the same algorithm and input to compare sequential and parallel versions. Check that they produce identical results, exclude verification and compilation from execution timing when measuring the binary, and report repeated measurements. The [benchmark experiment](../../benchmarks/README.md) provides a reproducible example and records its limited scope.
