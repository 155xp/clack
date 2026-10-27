"""Native regressions for parallel caller participation and counted ranges."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import parse
from clack.verifier import verify


CC = shutil.which("cc")


@unittest.skipUnless(CC, "a C11 compiler is needed")
class NativeOptimizationTests(unittest.TestCase):
    def native(self, source, instrument="", argument_instrument=""):
        program = parse(textwrap.dedent(source).lstrip("\n"))
        checked = verify(program)
        generated = emit_c(program, checked.local_types, checked.expr_types)
        if instrument:
            generated = generated.replace("#include <pthread.h>\n", "#include <pthread.h>\n#include <assert.h>\nstatic pthread_t test_caller;\nstatic int test_arguments;\n")
            generated = generated.replace("    clack_fn_main();", "    test_caller = pthread_self();\n    clack_fn_main();")
            # Insert at the user function definition, rather than its prototype.
            marker = "static int64_t clack_fn_work(int64_t const clack_v_x) {"
            self.assertIn(marker, generated)
            generated = generated.replace(marker, marker + "\n" + instrument)
            if argument_instrument:
                marker = "static int64_t clack_fn_argument(int64_t const clack_v_x) {"
                self.assertIn(marker, generated)
                generated = generated.replace(marker, marker + "\n" + argument_instrument)
        with tempfile.TemporaryDirectory(prefix="clack-parallel-caller-") as directory:
            source_path, binary = Path(directory) / "program.c", Path(directory) / "program"
            source_path.write_text(generated, encoding="utf-8")
            result = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-O3", "-pthread", "-fsanitize=undefined", str(source_path), "-o", str(binary)], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_final_job_uses_caller_and_other_jobs_use_distinct_threads(self):
        output = self.native("""
            fn work(x: int) -> int:
                ensures result == x
                return x

            fn main():
                parallel:
                    first = work(1)
                    second = work(2)
                    final = work(3)
                print(first)
                print(second)
                print(final)
        """, "assert(pthread_equal(pthread_self(), test_caller) == (clack_v_x == 3));")
        self.assertEqual(output, "1\n2\n3\n")

    def test_single_job_executes_on_the_caller(self):
        output = self.native("""
            fn work(x: int) -> int:
                ensures result == x
                return x

            fn main():
                parallel:
                    value = work(7)
                print(value)
        """, "assert(pthread_equal(pthread_self(), test_caller));")
        self.assertEqual(output, "7\n")

    def test_every_argument_is_evaluated_before_any_job_starts(self):
        output = self.native("""
            fn argument(x: int) -> int:
                ensures result == x
                return x

            fn work(x: int) -> int:
                ensures result == x
                return x

            fn main():
                parallel:
                    first = work(argument(1))
                    second = work(argument(2))
                    final = work(argument(3))
                print(first)
                print(second)
                print(final)
        """, "assert(test_arguments == 3);", "++test_arguments;")
        self.assertEqual(output, "1\n2\n3\n")

    def test_counted_range_extrema_do_not_overflow_the_native_increment(self):
        output = self.native("""
            fn main():
                for i in range(9223372036854775806, 9223372036854775807):
                    print(i)
                for i in range(-9223372036854775808, -9223372036854775807):
                    print(i)
                for i in range(9223372036854775807, 9223372036854775807):
                    print(11)
                for i in range(9223372036854775807, -9223372036854775808):
                    print(22)
        """)
        self.assertEqual(output, "9223372036854775806\n-9223372036854775808\n")

    def test_counted_range_snapshots_bounds_before_the_body_mutates_them(self):
        output = self.native("""
            fn main():
                start = -1
                stop = 2
                for i in range(start, stop):
                    start = 100
                    stop = -100
                    print(i)
                print(start)
                print(stop)
        """)
        self.assertEqual(output, "-1\n0\n1\n100\n-100\n")

    def test_counted_range_index_has_block_scope_in_generated_c(self):
        output = self.native("""
            fn main():
                for i in range(2):
                    print(i)
                for i in range(-1, 1):
                    print(i)
                i = true
                print(i)
        """)
        self.assertEqual(output, "0\n1\n-1\n0\ntrue\n")


if __name__ == "__main__":
    unittest.main()
