"""End-to-end checks for the verified native backend and public CLI."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import parse
from clack.verifier import verify


CC = shutil.which("cc")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(CC, "a C11 compiler is needed for native integration tests")
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clack-native-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def native(self, source, transform=None):
        program = parse(textwrap.dedent(source).lstrip("\n"))
        checked = verify(program)
        c_source = emit_c(program, checked.local_types, checked.expr_types)
        if transform:
            c_source = transform(c_source)
        source_path = self.directory / "program.c"
        binary = self.directory / "program"
        source_path.write_text(c_source, encoding="utf-8")
        compiled = subprocess.run(
            [CC, "-std=c11", "-O3", "-Wall", "-Wextra", "-pthread", str(source_path), "-o", str(binary)],
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        return executed.stdout

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "clack", *map(str, arguments)], cwd=ROOT,
            text=True, capture_output=True, timeout=30,
        )

    def test_machine_arithmetic_matches_proved_negative_division_and_remainder(self):
        output = self.native("""
            fn quotient(x: int, y: int) -> int:
                requires y != 0
                requires x != -9223372036854775808 or y != -1
                ensures result == x / y
                return x / y

            fn remainder(x: int, y: int) -> int:
                requires y != 0
                requires x != -9223372036854775808 or y != -1
                ensures result == x % y
                return x % y

            fn main():
                print(quotient(-7, 3))
                print(quotient(7, -3))
                print(quotient(-7, -3))
                print(remainder(-7, 3))
                print(remainder(7, -3))
                print(-9223372036854775808)
                print(9223372036854775807)
                print(0 == 1 and 1 / 0 == 0)
                print(0 == 0 or 1 / 0 == 0)
        """)
        self.assertEqual(output, "-2\n-2\n2\n-1\n1\n-9223372036854775808\n9223372036854775807\nfalse\ntrue\n")

    def test_native_control_flow_runs_verified_loop_and_both_branches(self):
        output = self.native("""
            fn count(n: int) -> int:
                requires 0 <= n <= 1000000
                ensures result == n
                i = 0
                while i < n:
                    invariant 0 <= i <= n
                    decreases n - i
                    i = i + 1
                return i

            fn positive(x: int) -> bool:
                ensures result == (x > 0)
                if x > 0:
                    return true
                else:
                    return false

            fn main():
                print(count(0))
                print(count(10000))
                print(positive(7))
                print(positive(-7))
        """)
        self.assertEqual(output, "0\n10000\ntrue\nfalse\n")

    def test_nested_records_and_arrays_have_value_semantics(self):
        output = self.native("""
            type Packet:
                location: Point
                data: int[2]
                flags: bool[2]

            type Point:
                x: int
                y: int

            fn copy(packet: Packet) -> Packet:
                ensures result.location.x == packet.location.x
                ensures result.data[0] == packet.data[0]
                ensures result.flags[1] == packet.flags[1]
                return packet

            fn main():
                original = Packet(Point(3, 4), [10, 20], [true, false])
                copied = copy(original)
                values = copied.data
                values[0] = 99
                changed = Packet(copied.location, values, copied.flags)
                print(original.data[0])
                print(changed.data[0])
                print(changed.location.y)
                print(changed.flags[0])
                print(changed.flags[1])
                print(len(changed.data))
        """)
        self.assertEqual(output, "10\n99\n4\ntrue\nfalse\n2\n")

    def test_parallel_jobs_launch_real_threads_before_join_and_copy_inputs(self):
        source = """
            type Payload:
                values: int[2]

            fn first(values: int[2]) -> int:
                ensures result == values[0]
                return values[0]

            fn swapped(values: int[2]) -> int[2]:
                ensures result[0] == values[1]
                ensures result[1] == values[0]
                return [values[1], values[0]]

            fn packed(values: int[2]) -> Payload:
                ensures result.values[0] == values[0]
                return Payload(values)

            fn main():
                input = [3, 9]
                parallel:
                    scalar = first(input)
                    array = swapped(input)
                    record = packed(input)
                input[0] = 77
                print(scalar)
                print(array[0])
                print(array[1])
                print(record.values[0])
                print(input[0])
        """

        def instrument(c_source, fail_threads):
            # Wrappers delegate to POSIX threads in the normal case. They also
            # enforce launch-before-join and verify distinct successful IDs.
            wrappers = """
#include <assert.h>
#include <errno.h>
static int native_test_created;
static int native_test_joined;
static pthread_t native_test_threads[3];
static int native_test_create(pthread_t *thread, const pthread_attr_t *attr,
                              void *(*worker)(void *), void *arg) {
    int slot = native_test_created++;
    assert(slot < 3);
    if (FAIL_THREADS) return EAGAIN;
    int status = pthread_create(thread, attr, worker, arg);
    assert(status == 0);
    for (int i = 0; i < slot; i++) assert(!pthread_equal(*thread, native_test_threads[i]));
    native_test_threads[slot] = *thread;
    return status;
}
static int native_test_join(pthread_t thread, void **result) {
    assert(!FAIL_THREADS);
    assert(native_test_created == 3);
    native_test_joined++;
    return pthread_join(thread, result);
}
#define pthread_create native_test_create
#define pthread_join native_test_join
""".replace("FAIL_THREADS", "1" if fail_threads else "0")
            c_source = c_source.replace("#include <pthread.h>\n", "#include <pthread.h>\n" + wrappers, 1)
            before, separator, after = c_source.rpartition("    return 0;")
            self.assertTrue(separator)
            return before + f"    assert(native_test_created == 3);\n    assert(native_test_joined == {0 if fail_threads else 3});\n" + separator + after

        for fail_threads in (False, True):
            with self.subTest(thread_creation_fails=fail_threads):
                output = self.native(source, lambda c: instrument(c, fail_threads))
                self.assertEqual(output, "3\n9\n3\n3\n77\n")

    def test_cli_run_emits_the_native_program_output(self):
        source = self.directory / "answer.clack"
        source.write_text("fn main():\n    print(42)\n", encoding="utf-8")
        result = self.cli("run", source, "--cc", CC)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "42\n")

    def test_failed_build_preserves_existing_binary_and_source(self):
        source = self.directory / "answer.clack"
        original = "fn main():\n    print(42)\n"
        source.write_text(original, encoding="utf-8")
        binary = self.directory / "answer"
        sentinel = b"previous working binary\n"
        binary.write_bytes(sentinel)

        failed_cc = self.cli("build", source, "-o", binary, "--cc", sys.executable + " -c 'raise SystemExit(1)'")
        self.assertNotEqual(failed_cc.returncode, 0)
        self.assertIn("C compiler failed", failed_cc.stderr)
        self.assertEqual(binary.read_bytes(), sentinel)
        self.assertEqual(source.read_text(encoding="utf-8"), original)

        bad = self.directory / "unsafe.clack"
        bad.write_text("fn main():\n    print(1 / 0)\n", encoding="utf-8")
        failed_verification = self.cli("build", bad, "-o", binary, "--cc", CC)
        self.assertNotEqual(failed_verification.returncode, 0)
        self.assertEqual(binary.read_bytes(), sentinel)
        for command in ("build", "emit-c"):
            result = self.cli(command, source, "-o", source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output must differ", result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
