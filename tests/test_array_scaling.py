"""Large constant arrays and folded literal goals retain strict proof behavior."""

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

import z3

from clack.frontend import CompileError
from clack.modules import load_program
from clack.verifier import verify


class ArrayScalingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-array-scaling-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def program(self, source):
        path = self.directory / "main.clack"
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        return load_program(path)

    def replay(self, directory, wanted):
        rows = json.loads((directory / "obligations.json").read_text())
        self.assertTrue(rows)
        for row in rows:
            solver = z3.Solver()
            solver.from_file(str(directory / row["query"]))
            self.assertEqual(solver.check(), z3.sat if row["status"] == "sat" else z3.unsat, row)
        self.assertEqual(rows[-1]["status"], wanted)

    def test_maximum_supported_fill_has_exact_contents_without_element_expansion(self):
        checked = verify(self.program("""
            from std.array import fill
            fn main():
                values = fill(-9223372036854775808, 1000000)
                flags = fill(true, 1000000)
                assert len(values) == 1000000
                assert values[0] == -9223372036854775808
                assert values[999999] == -9223372036854775808
                assert flags[999999]
        """))
        self.assertLess(len(checked.obligations), 1000)

    def test_fill_copy_and_updates_preserve_the_original_value(self):
        verify(self.program("""
            from std.array import fill
            fn main():
                original = fill(-7, 2048)
                changed = original
                changed[1024] = 9
                assert original[1024] == -7
                assert changed[1024] == 9
                assert changed[1023] == -7
        """))

    def test_symbolic_fill_result_supports_a_full_range_contract(self):
        verify(self.program("""
            from std.array import fill
            fn repeat(value: int) -> int[1000000]:
                ensures result[0] == value
                ensures result[999999] == value
                return fill(value, 1000000)
            fn main():
                values = repeat(9223372036854775807)
                assert values[0] == 9223372036854775807
                assert values[999999] == 9223372036854775807
        """))

    def test_numeral_range_checks_replay_at_both_signed_boundaries(self):
        directory = self.directory / "proofs"
        verify(self.program("""
            fn main():
                low = -9223372036854775808
                high = 9223372036854775807
                assert low < high
                assert 9223372036854775808 == high + 1
        """), proof_dir=directory)
        self.replay(directory, "unsat")

    def test_invalid_numeral_is_rejected_after_successful_goals_and_exports_sat(self):
        for value in ("9223372036854775808", "-9223372036854775809"):
            with self.subTest(value=value):
                directory = self.directory / ("negative" if value.startswith("-") else "positive")
                program = self.program("fn main():\n    value = 0\n" + "    value = 1\n" * 32 + "    print(" + value + ")\n")
                with self.assertRaisesRegex(CompileError, "signed 64-bit range"):
                    verify(program, proof_dir=directory)
                self.replay(directory, "sat")

    def test_unreachable_invalid_numeral_still_uses_its_path(self):
        directory = self.directory / "unreachable"
        verify(self.program("""
            fn main():
                if false:
                    too_large = 9223372036854775808
                    too_small = -9223372036854775809
                print(0)
        """), proof_dir=directory)
        self.replay(directory, "unsat")

    def test_symbolic_arithmetic_is_not_treated_as_a_literal(self):
        with self.assertRaisesRegex(CompileError, "signed 64-bit range"):
            verify(self.program("""
                fn overflow(value: int) -> int:
                    return value + 1
                fn main():
                    print(overflow(0))
            """))


if __name__ == "__main__":
    unittest.main()
