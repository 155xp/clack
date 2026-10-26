"""Exact, typed array reductions through explicit source imports."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import CompileError, parse
from clack.modules import load_program
from clack.typecheck import check
from clack.verifier import verify


CC = shutil.which("cc")


class ReductionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-reductions-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def program(self, source):
        path = self.directory / "main.clack"
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        return load_program(path)

    def checked(self, source):
        return verify(self.program(source))

    def test_sum_accepts_all_fixed_lengths_without_generic_source_syntax(self):
        for length in (1, 2, 3, 5, 9, 17):
            with self.subTest(length=length):
                values = ", ".join(map(str, range(1, length + 1)))
                self.checked(f"from std.array import sum\nfn main():\n    answer = sum([{values}])\n    assert answer == {length * (length + 1) // 2}\n")

    def test_boolean_reductions_have_exact_results(self):
        self.checked("""
            from std.array import all, any, count
            fn main():
                everyone = all([true, true, true, true, true])
                somebody = any([false, false, true])
                nobody = any([false])
                not_everyone = all([true, false])
                matches = count([true, false, true, false, true])
                assert everyone and somebody and not nobody and not not_everyone
                assert matches == 3
        """)

    def test_count_bounds_are_proved_for_arbitrary_array_contents(self):
        self.checked("""
            from std.array import count
            fn tally(values: bool[5]) -> int:
                ensures 0 <= result <= 5
                return count(values)
            fn main():
                print(tally([true, false, true, false, false]))
        """)

    def test_sum_result_supports_modular_postconditions(self):
        self.checked("""
            from std.array import sum
            fn total(values: int[3]) -> int:
                requires -100 <= values[0] <= 100
                requires -100 <= values[1] <= 100
                requires -100 <= values[2] <= 100
                ensures result == values[0] + values[1] + values[2]
                return sum(values)
            fn main():
                print(total([-100, 20, 80]))
        """)

    def test_sum_accepts_extreme_elements_when_every_prefix_fits(self):
        self.checked("""
            from std.array import sum
            fn main():
                answer = sum([-9223372036854775808, 9223372036854775807, 1])
                assert answer == 0
        """)

    def test_overflowing_prefix_is_rejected_even_when_final_sum_fits(self):
        for values in ("[9223372036854775807, 1, -1]", "[-9223372036854775808, -1, 1]"):
            with self.subTest(values=values), self.assertRaises(CompileError):
                self.checked(f"from std.array import sum\nfn main():\n    print(sum({values}))\n")

    def test_unconstrained_integer_array_is_not_assumed_safe_to_sum(self):
        with self.assertRaises(CompileError):
            self.checked("""
                from std.array import sum
                fn total(values: int[2]) -> int:
                    return sum(values)
                fn main():
                    print(total([1, 2]))
            """)

    def test_array_construction_is_eager_before_boolean_reduction(self):
        with self.assertRaises(CompileError):
            self.checked("""
                from std.array import all
                fn main():
                    print(all([false, 1 / 0 > 0]))
            """)

    def test_reductions_reject_wrong_element_types_arity_and_scalars(self):
        for operation, arguments in (
            ("sum", "[true, false]"), ("count", "[1, 2]"),
            ("all", "[0, 1]"), ("any", "7"),
            ("sum", ""), ("count", "[true], [false]"),
        ):
            with self.subTest(operation=operation, arguments=arguments), self.assertRaises(CompileError):
                check(self.program(f"from std.array import {operation}\nfn main():\n    print({operation}({arguments}))\n"))

    def test_reductions_require_explicit_import_and_cannot_use_internal_names(self):
        for source in (
            "fn main():\n    print(sum([1, 2]))\n",
            "fn main():\n    print(_clack_reduce_sum([1, 2]))\n",
            "fn _clack_reduce_sum(x: int) -> int:\n    return x\nfn main():\n    print(1)\n",
        ):
            with self.subTest(source=source.splitlines()[0]), self.assertRaises(CompileError):
                check(self.program(source))
        with self.assertRaises(CompileError):
            check(parse("fn main():\n    print(_clack_reduce_sum([1, 2]))\n"))

    def test_reexports_preserve_reduction_identity(self):
        (self.directory / "helpers.clack").write_text("from std.array import sum\n")
        self.checked("from helpers import sum\nfn main():\n    answer = sum([1, 2, 3, 4, 5])\n    assert answer == 15\n")

    def test_user_functions_named_sum_keep_normal_module_semantics(self):
        (self.directory / "custom.clack").write_text("fn sum(values: int[2]) -> int:\n    ensures result == 42\n    return 42\n")
        self.checked("from custom import sum\nfn main():\n    answer = sum([1, 2])\n    assert answer == 42\n")

    def test_reductions_are_not_trusted_proof_annotations(self):
        with self.assertRaises(CompileError):
            check(self.program("from std.array import sum\nfn main():\n    assert sum([1, 2]) == 3\n"))

    def test_parallel_workers_may_use_reductions_but_jobs_require_functions(self):
        self.checked("""
            from std.array import count
            fn tally(values: bool[3]) -> int:
                ensures 0 <= result <= 3
                return count(values)
            fn main():
                parallel:
                    left = tally([true, false, true])
                    right = tally([false, true, false])
                assert 0 <= left + right <= 6
        """)
        with self.assertRaises(CompileError):
            check(self.program("from std.array import sum\nfn main():\n    parallel:\n        answer = sum([1, 2, 3])\n"))

    @unittest.skipUnless(CC, "native reduction checks require a C11 compiler")
    def test_native_array_expressions_and_imported_reductions(self):
        program = self.program("""
            from std.array import sum, all, any, count
            fn values() -> int[5]:
                ensures result[0] == 1 and result[1] == 2 and result[2] == 3
                ensures result[3] == 4 and result[4] == 5
                return [1, 2, 3, 4, 5]
            fn main():
                print(sum(values()))
                print(sum([-9223372036854775808]))
                print(all([true, true, false]))
                print(all([true]))
                print(any([false, false, true]))
                print(any([false]))
                print(count([true, false, true, false, true, false, false]))
                print(count([false]))
        """)
        checked = verify(program)
        source = self.directory / "program.c"
        binary = self.directory / "program"
        source.write_text(emit_c(program, checked.local_types, checked.expr_types))
        built = subprocess.run([CC, "-std=c11", "-O3", "-Wall", "-Wextra", "-pthread", str(source), "-o", str(binary)],
                               text=True, capture_output=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout, "15\n-9223372036854775808\nfalse\ntrue\ntrue\nfalse\n3\n0\n")


if __name__ == "__main__":
    unittest.main()
