"""Proof-optimization regressions: faster checks must preserve the proof model."""

import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import z3

from clack.codegen import _Emitter, emit_c
from clack.frontend import CompileError, parse
from clack.modules import load_program
from clack.verifier import verify


class ProofOptimizationSafety(unittest.TestCase):
    def program(self, source):
        source = textwrap.dedent(source).strip() + "\n"
        if "fn main(" not in source:
            source += "fn main():\n    print(0)\n"
        return parse(source)

    def test_constant_false_goal_can_hold_on_an_unreachable_path(self):
        verify(self.program("""
            fn main():
                if false:
                    print(9223372036854775808)
                    print(1 / 0)
                else:
                    print(42)
        """))

    def test_constant_simplification_preserves_short_circuit_safety(self):
        verify(self.program("fn main():\n    print(true or 1 / 0 == 0)"))
        for expression in ("9223372036854775808", "false or 1 / 0 == 0"):
            with self.subTest(expression=expression):
                program = self.program(f"fn main():\n    print({expression})")
                with self.assertRaises(CompileError):
                    verify(program)

    def test_an_unsatisfiable_previous_query_cannot_prove_another_function(self):
        program = self.program("""
            fn constant() -> int:
                ensures result == 0
                return 0

            fn wrong(x: int) -> int:
                ensures result >= 0
                return x
        """)
        with self.assertRaisesRegex(CompileError, "postcondition of wrong"):
            verify(program)

    def test_solver_facts_do_not_leak_between_branches(self):
        program = self.program("""
            fn wrong(x: int) -> int:
                ensures result >= 0
                if x >= 0:
                    return x
                return x
        """)
        with self.assertRaisesRegex(CompileError, "counterexample"):
            verify(program)

    def test_independent_verifications_do_not_share_assumptions(self):
        verify(self.program("""
            fn bounded(x: int) -> int:
                requires x >= 0
                ensures result >= 0
                return x
        """))
        unsafe = self.program("""
            fn unbounded(x: int) -> int:
                ensures result >= 0
                return x
        """)
        with self.assertRaises(CompileError):
            verify(unsafe)

    def test_join_preserves_scalar_choices_and_callee_summary_facts(self):
        verify(self.program("""
            fn first() -> int:
                ensures result == 11
                return 11

            fn second() -> int:
                ensures result == 22
                return 22

            fn choose(flag: bool) -> int:
                ensures (flag and result == 11) or (not flag and result == 22)
                if flag:
                    chosen = first()
                else:
                    chosen = second()
                return chosen
        """))

    def test_join_preserves_record_and_array_update_alternatives(self):
        verify(self.program("""
            type Box:
                values: int[2]
                tag: int

            fn choose(flag: bool) -> Box:
                ensures (flag and result.values[0] == 9 and result.values[1] == 2 and result.tag == 1) or (not flag and result.values[0] == 1 and result.values[1] == 8 and result.tag == 2)
                values = [1, 2]
                if flag:
                    values[0] = 9
                    box = Box(values, 1)
                else:
                    values[1] = 8
                    box = Box(values, 2)
                return box
        """))

    def test_join_cannot_define_a_local_missing_from_one_branch(self):
        program = self.program("""
            fn missing(flag: bool) -> int:
                if flag:
                    value = 7
                else:
                    other = 8
                return value
        """)
        with self.assertRaisesRegex(CompileError, "not defined on every path"):
            verify(program)

    def test_returned_branch_is_checked_and_excluded_from_continuation(self):
        verify(self.program("""
            fn choose(flag: bool) -> int:
                ensures (flag and result == 0) or (not flag and result == 7)
                if flag:
                    return 0
                else:
                    value = 7
                return value
        """))
        wrong = self.program("""
            fn choose(flag: bool) -> int:
                ensures result == 1
                if flag:
                    return 2
                else:
                    value = 1
                return value
        """)
        with self.assertRaisesRegex(CompileError, "postcondition of choose"):
            verify(wrong)

    def test_join_discards_an_impossible_alternative_value(self):
        verify(self.program("""
            fn choose(flag: bool) -> int:
                ensures result == 7
                if flag and not flag:
                    value = 9223372036854775808
                else:
                    value = 7
                return value
        """))

    def test_unknown_symbolic_obligation_is_rejected(self):
        program = self.program("""
            fn nonnegative(x: int) -> int:
                ensures result >= 0
                if x < 0:
                    return 0
                return x
        """)
        with patch("clack.verifier.z3.Solver") as constructor:
            constructor.return_value.check.return_value = z3.unknown
            constructor.return_value.reason_unknown.return_value = "forced unknown"
            with self.assertRaisesRegex(CompileError, "forced unknown"):
                verify(program)

    def test_exported_constant_and_symbolic_queries_replay(self):
        program = self.program("""
            fn nonnegative(x: int) -> int:
                ensures result >= 0
                if x < 0:
                    return 0
                return x

            fn main():
                print(nonnegative(-7))
        """)
        with tempfile.TemporaryDirectory(prefix="clack-proof-replay-") as directory:
            result = verify(program, proof_dir=directory)
            rows = json.loads((Path(directory) / "obligations.json").read_text())
            self.assertEqual(rows, result.obligations)
            self.assertTrue(rows)
            for row in rows:
                with self.subTest(obligation=row["id"]):
                    solver = z3.Solver()
                    solver.from_file(str(Path(directory) / row["query"]))
                    self.assertEqual(row["status"], "unsat")
                    self.assertEqual(solver.check(), z3.unsat)

    def test_failed_query_keeps_a_replayable_counterexample(self):
        program = self.program("""
            fn wrong(x: int) -> int:
                ensures result > x
                return x
        """)
        with tempfile.TemporaryDirectory(prefix="clack-failed-proof-") as directory:
            with self.assertRaisesRegex(CompileError, "counterexample"):
                verify(program, proof_dir=directory)
            rows = json.loads((Path(directory) / "obligations.json").read_text())
            self.assertEqual(rows[-1]["status"], "sat")
            solver = z3.Solver()
            solver.from_file(str(Path(directory) / rows[-1]["query"]))
            self.assertEqual(solver.check(), z3.sat)

    def test_nested_reductions_do_not_expand_emitter_work_exponentially(self):
        source = "1"
        for _ in range(18):
            source = f"sum([{source}])"
        with tempfile.TemporaryDirectory(prefix="clack-nested-reductions-") as directory:
            path = Path(directory) / "main.clack"
            path.write_text(f"from std.array import sum\nfn main():\n    print({source})\n")
            program = load_program(path)
            checked = verify(program)
        original = _Emitter.expression
        visits = 0

        def bounded(emitter, expression):
            nonlocal visits
            visits += 1
            if visits > 500:
                raise AssertionError("small nested expressions must not cause exponential emitter work")
            return original(emitter, expression)

        with patch.object(_Emitter, "expression", bounded):
            emit_c(program, checked.local_types, checked.expr_types)


if __name__ == "__main__":
    unittest.main()
