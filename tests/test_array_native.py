"""Native array construction, extrema, and pruning after strict verification."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import CompileError
from clack.modules import load_program
from clack.verifier import verify


CC = shutil.which("cc")


@unittest.skipUnless(CC, "native tests need a C11 compiler")
class ArrayNativeTests(unittest.TestCase):
    def native(self, source, instrument=False):
        with tempfile.TemporaryDirectory(prefix="clack-array-native-") as directory:
            root = Path(directory)
            path = root / "main.clack"
            path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
            program = load_program(path)
            checked = verify(program)
            generated = emit_c(program, checked.local_types, checked.expr_types)
            if instrument:
                generated = generated.replace("#include <pthread.h>\n", "#include <pthread.h>\n#include <assert.h>\nstatic int test_calls;\n")
                marker = "static int64_t clack_fn_source(void) {"
                self.assertIn(marker, generated)
                generated = generated.replace(marker, marker + "\n    ++test_calls;")
                generated = generated.replace("    clack_fn_main();", "    clack_fn_main();\n    assert(test_calls == 1);")
            c_path, binary = root / "program.c", root / "program"
            c_path.write_text(generated, encoding="utf-8")
            result = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-Wall", "-Wextra", "-Werror", "-O3", "-pthread", "-fsanitize=undefined", str(c_path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout, generated

    def test_int_and_bool_fills_of_same_length_have_distinct_native_helpers(self):
        output, _ = self.native("""
            from std.array import fill, minimum, maximum, count, all
            fn main():
                values = fill(-9223372036854775808, 5)
                flags = fill(true, 5)
                copy = values
                copy[0] = 9223372036854775807
                print(values[0])
                print(copy[0])
                print(minimum(copy))
                print(maximum(copy))
                print(count(flags))
                print(all(flags))
        """)
        self.assertEqual(output, "-9223372036854775808\n9223372036854775807\n-9223372036854775808\n9223372036854775807\n5\ntrue\n")

    def test_extrema_match_reference_for_singletons_duplicates_and_extreme_integers(self):
        datasets = [[0], [-7], [2, 2, 2], [5, -7, 9, -11], [-(1 << 63), (1 << 63) - 1], [(1 << 63) - 1, 0, -(1 << 63)]]
        source = "from std.array import minimum, maximum\nfn main():\n"
        expected = []
        for values in datasets:
            literal = "[" + ", ".join(map(str, values)) + "]"
            source += f"    print(minimum({literal}))\n    print(maximum({literal}))\n"
            expected.extend([min(values), max(values)])
        output, _ = self.native(source)
        self.assertEqual(output, "".join(f"{value}\n" for value in expected))

    def test_fill_evaluates_its_value_once(self):
        output, _ = self.native("""
            from std.array import fill
            fn source() -> int:
                ensures result == 7
                return 7
            fn main():
                values = fill(source(), 16)
                print(values[0])
                print(values[15])
        """, instrument=True)
        self.assertEqual(output, "7\n7\n")

    def test_extrema_accept_array_return_values_and_record_fields(self):
        output, _ = self.native("""
            from std.array import fill, minimum, maximum
            type Batch:
                values: int[3]
            fn numbers() -> int[3]:
                return [-8, 3, 5]
            fn main():
                print(minimum(numbers()))
                batch = Batch(fill(12, 3))
                print(maximum(batch.values))
        """)
        self.assertEqual(output, "-8\n12\n")

    def test_filled_values_work_with_parallel_source_workers(self):
        output, _ = self.native("""
            from std.array import fill, minimum
            fn low(values: int[4]) -> int:
                ensures result <= values[0]
                ensures result <= values[1]
                ensures result <= values[2]
                ensures result <= values[3]
                return minimum(values)
            fn main():
                parallel:
                    left = low(fill(7, 4))
                    right = low(fill(-8, 4))
                print(left)
                print(right)
        """)
        self.assertEqual(output, "7\n-8\n")

    def test_unreachable_parallel_workers_and_array_helpers_are_not_emitted(self):
        output, generated = self.native("""
            from std.array import fill, minimum
            fn dead_worker(x: int) -> int:
                ensures result == x
                return x
            fn unused() -> int:
                parallel:
                    left = dead_worker(1)
                    right = dead_worker(2)
                values = fill(left, 8)
                return minimum(values)
            fn inner() -> int:
                return 42
            fn live() -> int:
                return inner()
            fn main():
                print(live())
        """)
        self.assertEqual(output, "42\n")
        for omitted in ("clack_fn_unused", "clack_fn_dead_worker", "clack_worker_", "clack_reduce_fill_", "clack_reduce_minimum_"):
            self.assertNotIn(omitted, generated)
        self.assertIn("clack_fn_inner", generated)
        self.assertIn("clack_fn_live", generated)

    def test_unused_invalid_functions_still_fail_verification(self):
        with tempfile.TemporaryDirectory(prefix="clack-array-invalid-") as directory:
            path = Path(directory) / "main.clack"
            path.write_text("fn unused() -> int:\n    return 1 / 0\nfn main():\n    print(42)\n")
            with self.assertRaisesRegex(CompileError, "nonzero divisor"):
                verify(load_program(path))

    def test_reachability_does_not_add_recursion_depth_for_long_call_chains(self):
        with tempfile.TemporaryDirectory(prefix="clack-array-chain-") as directory:
            path = Path(directory) / "main.clack"
            parts = [f"fn f{i}() -> int:\n    return " + (f"f{i + 1}()" if i < 299 else "42") for i in range(300)]
            path.write_text("\n\n".join(parts) + "\n\nfn main():\n    print(f0())\n")
            program = load_program(path)
            checked = verify(program)
            generated = emit_c(program, checked.local_types, checked.expr_types)
            self.assertIn("clack_fn_f299", generated)

    def test_large_fill_emits_a_loop_without_expanding_element_literals(self):
        output, generated = self.native("""
            from std.array import fill
            fn main():
                values = fill(7, 4096)
                print(values[4095])
                print(len(values))
        """)
        self.assertEqual(output, "7\n4096\n")
        self.assertLess(len(generated), 2000)

    def test_assignment_fill_snapshots_old_target_before_writing_any_element(self):
        output, generated = self.native("""
            from std.array import fill
            fn main():
                values = fill(3, 4)
                copied = values
                values = fill(values[0] + values[1], 4)
                flags = fill(false, 4)
                original = flags
                flags = fill(not flags[0], 4)
                print(values[0])
                print(values[3])
                print(copied[0])
                print(flags[0])
                print(flags[3])
                print(original[0])
        """)
        self.assertEqual(output, "6\n6\n3\ntrue\ntrue\nfalse\n")
        self.assertNotIn("clack_reduce_fill_", generated)

    def test_assignment_fill_keeps_nested_value_calls_and_rvalue_helpers_reachable(self):
        output, generated = self.native("""
            from std.array import fill, maximum
            fn identity(value: int) -> int:
                ensures result == value
                return value
            fn main():
                values = fill(identity(maximum(fill(9, 2))), 4)
                print(values[0])
                print(values[3])
        """)
        self.assertEqual(output, "9\n9\n")
        self.assertIn("clack_fn_identity", generated)
        self.assertIn("clack_reduce_fill_int_2", generated)
        self.assertNotIn("clack_reduce_fill_int_4", generated)

    def test_fill_rvalue_returns_and_record_fields_keep_value_semantics(self):
        output, generated = self.native("""
            from std.array import fill, minimum
            type Batch:
                values: int[4]
            fn values() -> int[4]:
                return fill(9, 4)
            fn main():
                batch = Batch(fill(-2, 4))
                print(minimum(values()))
                print(minimum(batch.values))
        """)
        self.assertEqual(output, "9\n-2\n")
        self.assertIn("clack_reduce_fill_int_4", generated)

    def test_fill_assignment_temporary_names_do_not_collide_with_counted_loops(self):
        output, _ = self.native("""
            from std.array import fill
            fn main():
                for i in range(2):
                    values = fill(i, 3)
                    for j in range(2):
                        flags = fill(j == 1, 2)
                        print(values[2])
                        print(flags[1])
        """)
        self.assertEqual(output, "0\nfalse\n0\ntrue\n1\nfalse\n1\ntrue\n")


if __name__ == "__main__":
    unittest.main()
