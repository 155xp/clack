"""Counted loops retain strict proofs while inferring index safety/termination."""

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

import z3

from clack.frontend import CompileError, For, parse
from clack.modules import load_program
from clack.verifier import verify


class CountedLoopTests(unittest.TestCase):
    def program(self, source):
        return parse(textwrap.dedent(source).lstrip("\n"))

    def checked(self, source, **options):
        return verify(self.program(source), **options)

    def rejected(self, source, message):
        with self.assertRaisesRegex(CompileError, message):
            self.checked(source)

    def test_range_forms_and_endpoint_types(self):
        program = self.program("""
            fn main():
                for i in range(3):
                    print(i)
                for i in range(-3, 0):
                    print(i)
        """)
        first, second = program.functions[0].body
        self.assertIsInstance(first, For)
        self.assertEqual(first.start.value, 0)
        self.assertEqual(first.stop.value, 3)
        self.assertEqual(second.start.operand.value, 3)
        verify(program)
        for bounds in ["true", "false, 3", '0, "end"']:
            with self.subTest(bounds=bounds):
                self.rejected(f"fn main():\n    for i in range({bounds}):\n        print(i)\n", "range.*needs int")

    def test_only_one_or_two_range_arguments_are_supported(self):
        for bounds in ["", "1, 2, 3", "1,", "0, 1, -1"]:
            with self.subTest(bounds=bounds), self.assertRaises(CompileError):
                self.program(f"fn main():\n    for i in range({bounds}):\n        print(i)\n")

    def test_index_is_immutable_even_in_nested_branches_and_parallel_bindings(self):
        for body in ["i = 3", "if true:\n            i = 3", "parallel:\n            i = value()"]:
            with self.subTest(body=body):
                self.rejected("fn value() -> int:\n    return 3\nfn main():\n    for i in range(4):\n        " + body + "\n", "for index 'i' is immutable")

    def test_index_cannot_shadow_an_active_local_or_parameter(self):
        self.rejected("""
            fn main():
                i = 5
                for i in range(3):
                    print(i)
        """, "shadow an existing binding")
        self.rejected("""
            fn work(i: int) -> int:
                for i in range(3):
                    value = i
                return i
            fn main():
                print(0)
        """, "shadow an existing binding")

    def test_body_bindings_and_index_are_unavailable_after_loop(self):
        for name in ["i", "inside"]:
            with self.subTest(name=name):
                self.rejected("fn main():\n    for i in range(3):\n        inside = i\n    print(" + name + ")\n", "not defined on every path")

    def test_automatic_index_facts_prove_array_access_without_annotations(self):
        self.checked("""
            fn main():
                values = [7, 8, 9]
                for i in range(len(values)):
                    print(values[i])
        """)
        self.rejected("""
            fn main():
                values = [7, 8, 9]
                for i in range(4):
                    print(values[i])
        """, "array index is in bounds")

    def test_relational_invariant_proves_counter_result(self):
        source = """
            fn count(n: int) -> int:
                requires 0 <= n <= 1000000
                ensures result == n
                total = 0
                for i in range(n):
                    invariant total == i
                    total = total + 1
                return total
            fn main():
                print(count(4))
        """
        self.checked(source)
        self.rejected(source.replace("total == i", "total == i + 1"), "invariant holds on entry")
        self.rejected(source.replace("total = total + 1", "total = total + 2"), "invariant is preserved")

    def test_missing_invariant_does_not_preserve_stale_outer_values(self):
        self.rejected("""
            fn main():
                total = 0
                for i in range(3):
                    total = total + 1
                print(total)
        """, "signed 64-bit range")

    def test_empty_and_inverted_ranges_do_not_execute_unsafe_bodies(self):
        self.checked("""
            fn main():
                for i in range(0):
                    bad = 1 / 0
                for i in range(9223372036854775807, -9223372036854775808):
                    bad = 1 / 0
                print(0)
        """)
        # Type checking still visits unreachable bodies.
        self.rejected("fn main():\n    for i in range(0):\n        bad = true + 1\n", "needs int")

    def test_endpoint_expressions_cannot_hide_unsafe_arithmetic(self):
        self.rejected("fn main():\n    for i in range(1 / 0):\n        print(i)\n", "nonzero divisor")
        self.rejected("fn main():\n    for i in range(9223372036854775807 + 1):\n        print(i)\n", "signed 64-bit range")

    def test_nested_for_and_while_loops_havoc_mutated_outer_values(self):
        self.rejected("""
            fn main():
                total = 0
                j = 0
                while j < 2:
                    invariant 0 <= j <= 2
                    invariant total == 0
                    decreases 2 - j
                    for i in range(1):
                        total = 1
                    j = j + 1
                print(total)
        """, "invariant is preserved")
        self.checked("""
            fn main():
                for i in range(3):
                    for j in range(i):
                        assert 0 <= j < i
                        print(j)
        """)

    def test_early_return_checks_contracts_on_each_path(self):
        source = """
            fn choose(n: int) -> int:
                requires n >= 0
                ensures result == 0
                for i in range(n):
                    return 0
                return 0
            fn main():
                print(choose(1))
        """
        self.checked(source)
        self.rejected(source.replace("return 0", "return 1", 1), "postcondition")

    def test_imported_counted_loop_and_diagnostic_source_map(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "numbers.clack").write_text("fn first(n: int) -> int:\n    for i in range(n):\n        return i\n    return 0\n")
            (root / "main.clack").write_text("from numbers import first\nfn main():\n    print(first(3))\n")
            verify(load_program(root / "main.clack"))
            library = root / "numbers.clack"
            library.write_text(library.read_text().replace("return i", "return i + 9223372036854775807"))
            program = load_program(root / "main.clack")
            with self.assertRaisesRegex(CompileError, "signed 64-bit range") as raised:
                verify(program)
            self.assertEqual(program.locations[raised.exception.line], (str(library), 3))

    def test_counted_loop_obligations_replay_in_fresh_solvers(self):
        with tempfile.TemporaryDirectory() as directory:
            self.checked("""
                fn main():
                    for i in range(-9223372036854775808, 9223372036854775807):
                        assert i < 9223372036854775807
                        print(i)
            """, proof_dir=directory)
            rows = json.loads((Path(directory) / "obligations.json").read_text())
            for row in rows:
                solver = z3.Solver()
                solver.from_file(str(Path(directory) / row["query"]))
                self.assertEqual(solver.check(), z3.unsat, row)


if __name__ == "__main__":
    unittest.main()
