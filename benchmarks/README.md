# Native performance experiment

Run from the repository root after installing Clack's dependencies:

```sh
python benchmarks/compare.py --iterations 10000000 --repeats 5 --output build/benchmark.json
```

The script verifies and compiles three Clack programs and two hand-written C programs with the same C compiler and `-std=c11 -O3 -Wall -Wextra -pthread`. The timed programs are native executables. Python runs the experiment; it does not execute the kernel.

Each kernel advances the integer recurrence `x = (x * 48271) % 2147483647`. Its loop carries invariants and a decreasing iteration count. Clack proves that integer operations remain within signed 64-bit range and that results stay within the stated interval. The experiment compares one kernel in Clack and C, two sequential kernels in both languages, and two Clack jobs using `parallel:`. Each job owns its inputs and result.

Verification and compilation finish before timing begins. Each program runs once to check its output and warm caches, then the script records interleaved samples in a reproducible shuffled order. Every run must match an independent result computed using modular exponentiation. The JSON report records every sample, medians, compiler details, platform, flags, and proof-obligation counts.

Timings include native process startup, thread creation/joining, printing, and process exit. They exclude the compiler and verifier. For a quick correctness smoke test, use `--iterations 10000 --repeats 1`; its timings mostly reflect startup overhead and should not support performance claims. `--cc` selects the compiler, and `CC` supplies its default.

This is one scalar integer workload on one machine. It does not establish general C or Rust performance, memory behavior, vectorization, or GPU speed. Parallel results depend on available CPU time and scheduling; a container may report more CPUs than its allocation permits. Small jobs can run slower in parallel because creating threads has a cost.

## Recorded run: October 26, 2026

Linux x86-64, GCC 14.2.0, 10,000,000 iterations per kernel, five timed samples per program:

| Native program | Median wall time |
| --- | ---: |
| C, one kernel | 43.012 ms |
| Clack, one kernel | 41.726 ms |
| C, two sequential kernels | 82.545 ms |
| Clack, two sequential kernels | 89.143 ms |
| Clack, two parallel kernels | 41.721 ms |

The single-kernel times are similar. Clack's two parallel jobs took about 2.14 times less wall time than its two sequential jobs in this run; sample variation and scheduling affect that ratio. All outputs matched the independent mathematical reference. [Full samples and environment metadata](results/2026-10-26.json) are included so the result can be inspected and compared with another machine.
