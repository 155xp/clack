"""Adversarial sequences of proof goals must remain independent."""

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

import z3

from clack.frontend import CompileError, parse
from clack.verifier import verify


class SolverScopeTests(unittest.TestCase):
    def program(self, source):
        return parse(textwrap.dedent(source).strip() + "\nfn main():\n    print(0)\n")

    def test_later_counterexample_survives_many_successful_queries(self):
        source = "fn wrong(x: int) -> int:\n    requires -100 <= x <= 100\n    y = x\n"
        source += "    y = y + 1\n" * 64
        source += "    assert x >= 0\n    return y\n"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CompileError, "assertion.*|counterexample"):
                verify(self.program(source), proof_dir=directory)
            rows = json.loads((Path(directory) / "obligations.json").read_text())
            self.assertGreater(len(rows), 100)
            self.assertTrue(all(row["status"] == "unsat" for row in rows[:-1]))
            self.assertEqual(rows[-1]["status"], "sat")
            # Old, contradictory negated goals must not pollute this query.
            solver = z3.Solver()
            solver.from_file(str(Path(directory) / rows[-1]["query"]))
            self.assertEqual(solver.check(), z3.sat)

    def test_unreachable_division_does_not_make_later_overflow_safe(self):
        program = self.program("""
            fn wrong(x: int) -> int:
                if false:
                    discarded = 1 / 0
                return x + 1
        """)
        with self.assertRaisesRegex(CompileError, "signed 64-bit range"):
            verify(program)

    def test_loop_havoc_is_not_constrained_by_a_previous_iteration_query(self):
        program = self.program("""
            fn wrong(n: int) -> int:
                requires 0 <= n <= 10
                i = 0
                value = 0
                while i < n:
                    invariant 0 <= i <= n
                    invariant 0 <= value <= 10
                    decreases n - i
                    value = value + 1
                    i = i + 1
                return value
        """)
        # The weak invariant does not relate value to i. At an arbitrary loop
        # head value can already be 10 even when the guard is true.
        with self.assertRaisesRegex(CompileError, "invariant is preserved"):
            verify(program)

    def test_large_valid_sequence_exports_each_query_independently(self):
        source = "fn bounded(x: int) -> int:\n    requires -100 <= x <= 100\n"
        source += "    ensures result == x + 32\n    value = x\n"
        source += "    value = value + 1\n" * 32
        source += "    return value\n"
        with tempfile.TemporaryDirectory() as directory:
            result = verify(self.program(source), proof_dir=directory)
            for row in result.obligations:
                solver = z3.Solver()
                solver.from_file(str(Path(directory) / row["query"]))
                self.assertEqual(solver.check(), z3.unsat, row)


if __name__ == "__main__":
    unittest.main()
