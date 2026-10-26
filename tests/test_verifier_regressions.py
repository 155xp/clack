"""Soundness regressions: each rejected example parses before verification.

The positive cases guard against a verifier that rejects every program; the
negative cases exercise machine arithmetic, induction, modular contracts, and
value semantics rather than implementation details of the prover.
"""

from __future__ import annotations

import textwrap
import unittest
from unittest.mock import patch

import z3

from clack.frontend import CompileError, parse
from clack.verifier import verify


class VerifierRegressions(unittest.TestCase):
    def program(self, source: str):
        source = textwrap.dedent(source).strip() + "\n"
        if "fn main(" not in source:
            source += "\nfn main():\n    print(0)\n"
        return parse(source)

    def assert_proved(self, source: str):
        return verify(self.program(source))

    def assert_rejected(self, source: str):
        # Parsing deliberately happens outside assertRaises: an accidental
        # parser rejection must not masquerade as a soundness check.
        program = self.program(source)
        with self.assertRaises(CompileError):
            verify(program)

    def test_signed_division_truncates_toward_zero(self):
        for numerator, denominator, quotient in [(-3, 2, -1), (3, -2, -1), (-3, -2, 1)]:
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assert_proved(f"""
                    fn quotient() -> int:
                        ensures result == {quotient}
                        return {numerator} / {denominator}
                """)
        self.assert_rejected("""
            fn wrong_quotient() -> int:
                ensures result == -2
                return -3 / 2
        """)

    def test_remainder_has_sign_of_dividend(self):
        self.assert_proved("""
            fn remainder() -> int:
                ensures result == -1
                return -3 % 2
        """)
        self.assert_rejected("""
            fn wrong_remainder() -> int:
                ensures result == 1
                return -3 % 2
        """)

    def test_each_executable_intermediate_must_fit_i64(self):
        for expression in ["x + 1", "x - 1", "x * 2", "-x"]:
            with self.subTest(expression=expression):
                self.assert_rejected(f"""
                    fn overflow(x: int) -> int:
                        return {expression}
                """)
        self.assert_rejected("""
            fn cancelling_overflow() -> int:
                return (9223372036854775807 + 1) - 1
        """)

    def test_minimum_integer_literal_is_representable(self):
        self.assert_proved("""
            fn minimum() -> int:
                ensures result == -9223372036854775808
                return -9223372036854775808
        """)

    def test_division_overflow_and_zero_are_rejected(self):
        for expression in ["-9223372036854775808 / -1", "-9223372036854775808 % -1", "1 / 0", "1 % 0"]:
            with self.subTest(expression=expression):
                self.assert_rejected(f"""
                    fn invalid_division() -> int:
                        return {expression}
                """)

    def test_short_circuit_guard_can_establish_division_safety(self):
        self.assert_proved("""
            fn safe(x: int) -> bool:
                return x == 0 or 10 / x > 0
        """)
        self.assert_proved("""
            fn safe(x: int) -> bool:
                return x != 0 and 10 / x > 0
        """)

    def test_short_circuit_guard_must_match_the_operation(self):
        self.assert_rejected("""
            fn unsafe(x: int) -> bool:
                return x != 0 or 10 / x > 0
        """)
        self.assert_rejected("""
            fn unsafe(x: int) -> bool:
                return x == 0 and 10 / x > 0
        """)

    def test_specification_arithmetic_is_mathematical(self):
        self.assert_proved("""
            fn identity(x: int) -> int:
                ensures result * result == x * x
                return x
        """)

    def test_proof_only_assertions_may_use_large_mathematical_integers(self):
        self.assert_proved("""
            fn main():
                assert 9223372036854775807 + 1 == 9223372036854775808
                print(0)
        """)

    def test_undefined_specification_expressions_are_rejected(self):
        self.assert_rejected("""
            fn invalid() -> int:
                ensures 0 / 0 == 0 / 0
                return 0
        """)
        self.assert_rejected("""
            fn invalid(values: int[2]) -> int:
                ensures values[2] == values[2]
                return values[0]
        """)

    def test_solver_unknown_is_never_accepted_as_a_proof(self):
        program = self.program("""
            fn main():
                print(0)
        """)
        with patch("clack.verifier.z3.Solver") as constructor:
            constructor.return_value.check.return_value = z3.unknown
            constructor.return_value.reason_unknown.return_value = "regression test"
            with self.assertRaisesRegex(CompileError, "unknown|regression test"):
                verify(program)

    def test_short_circuit_calls_retain_guarded_contract_facts(self):
        self.assert_proved("""
            fn yes() -> bool:
                ensures result
                return true

            fn combined() -> bool:
                ensures result
                return true and yes()
        """)

    def test_skipped_call_facts_cannot_make_caller_unreachable(self):
        for expression in ["false and yes()", "true or yes()"]:
            with self.subTest(expression=expression):
                self.assert_rejected(f"""
                    fn yes() -> bool:
                        ensures result
                        return true

                    fn invalid() -> int:
                        ensures result == 1
                        ignored = {expression}
                        return 0
                """)

    def test_chained_comparisons_are_conjunctions(self):
        self.assert_proved("""
            fn inside(x: int) -> bool:
                ensures result == (0 < x and x < 10)
                return 0 < x < 10
        """)

    def test_callee_preconditions_must_be_proved(self):
        self.assert_rejected("""
            fn successor(x: int) -> int:
                requires x < 9223372036854775807
                ensures result == x + 1
                return x + 1

            fn unsafe_caller(x: int) -> int:
                return successor(x)
        """)

    def test_callee_summary_supports_modular_proof(self):
        self.assert_proved("""
            fn successor(x: int) -> int:
                requires x < 9223372036854775807
                ensures result == x + 1
                return x + 1

            fn caller() -> int:
                ensures result == 4
                return successor(3)
        """)

    def test_callee_postconditions_are_not_trusted_without_verification(self):
        self.assert_rejected("""
            fn liar() -> int:
                ensures result == 1
                return 0

            fn caller() -> int:
                ensures result == 1
                return liar()
        """)

    def test_every_return_path_must_satisfy_contract(self):
        self.assert_rejected("""
            fn positive(x: int) -> int:
                ensures result > 0
                if x > 0:
                    return x
                return 0
        """)

    def test_value_functions_cannot_fall_through(self):
        self.assert_rejected("""
            fn incomplete(flag: bool) -> int:
                if flag:
                    return 1
                assert true
        """)

    def test_branch_local_cannot_escape_undefined_path(self):
        self.assert_rejected("""
            fn incomplete(flag: bool) -> int:
                if flag:
                    value = 1
                return value
        """)

    def test_branch_merge_retains_all_possible_values(self):
        self.assert_rejected("""
            fn overflow(flag: bool) -> int:
                value = 0
                if flag:
                    value = 9223372036854775807
                return value + 1
        """)

    def test_parameter_reassignment_is_forbidden(self):
        self.assert_rejected("""
            fn mutate(x: int) -> int:
                x = 0
                return x
        """)

    def test_main_cannot_assume_a_precondition(self):
        self.assert_rejected("""
            fn main():
                requires false
                assert false
                print(0)
        """)

    def test_main_is_not_callable_from_pure_functions(self):
        self.assert_rejected("""
            fn helper() -> int:
                main()
                return 0

            fn main():
                print(0)
        """)

    def test_print_is_restricted_to_main(self):
        self.assert_rejected("""
            fn impure(x: int) -> int:
                print(x)
                return x
        """)

    def test_contracts_cannot_hide_function_calls(self):
        self.assert_rejected("""
            fn identity(x: int) -> int:
                return x

            fn invalid(x: int) -> int:
                ensures identity(result) == result
                return x
        """)

    def test_direct_and_mutual_recursion_are_rejected(self):
        self.assert_rejected("""
            fn recurse(x: int) -> int:
                return recurse(x)
        """)
        self.assert_rejected("""
            fn first(x: int) -> int:
                return second(x)

            fn second(x: int) -> int:
                return first(x)
        """)

    def test_loop_invariant_must_hold_initially(self):
        self.assert_rejected("""
            fn invalid() -> int:
                value = 0
                while value < 1:
                    invariant value == 1
                    decreases 1 - value
                    value = value + 1
                return value
        """)

    def test_loop_invariant_must_be_preserved(self):
        self.assert_rejected("""
            fn invalid() -> int:
                value = 0
                while value < 3:
                    invariant 0 <= value <= 3
                    decreases 3 - value
                    value = value + 2
                return value
        """)

    def test_loop_body_is_checked_at_arbitrary_iteration(self):
        self.assert_rejected("""
            fn invalid() -> int:
                value = 0
                while value < 2:
                    invariant 0 <= value <= 2
                    decreases 2 - value
                    assert value == 0
                    value = value + 1
                return value
        """)

    def test_loop_measure_must_strictly_decrease(self):
        self.assert_rejected("""
            fn invalid() -> int:
                value = 0
                while value < 2:
                    invariant 0 <= value <= 2
                    decreases value
                    value = value + 1
                return value
        """)

    def test_loop_measure_must_be_nonnegative_when_loop_runs(self):
        self.assert_rejected("""
            fn invalid() -> int:
                value = 0
                while value < 2:
                    invariant 0 <= value <= 2
                    decreases -value
                    value = value + 1
                return value
        """)

    def test_loop_proves_a_total_result(self):
        self.assert_proved("""
            fn countdown(n: int) -> int:
                requires 0 <= n <= 1000
                ensures result == 0
                remaining = n
                while remaining > 0:
                    invariant 0 <= remaining <= n
                    decreases remaining
                    remaining = remaining - 1
                return remaining
        """)

    def test_fixed_array_bounds_are_proved(self):
        self.assert_proved("""
            fn lookup(values: int[2], index: int) -> int:
                requires 0 <= index < 2
                ensures result == values[index]
                return values[index]
        """)
        for index in ["-1", "2"]:
            with self.subTest(index=index):
                self.assert_rejected(f"""
                    fn invalid() -> int:
                        values = [10, 20]
                        return values[{index}]
                """)

    def test_index_assignment_is_also_bounds_checked(self):
        self.assert_rejected("""
            fn invalid() -> int:
                values = [10, 20]
                values[2] = 30
                return values[0]
        """)

    def test_array_assignments_copy_values(self):
        self.assert_proved("""
            fn copy() -> int:
                ensures result == 1
                original = [1, 2]
                copied = original
                copied[0] = 9
                return original[0]
        """)
        self.assert_rejected("""
            fn no_aliasing() -> int:
                original = [1, 2]
                copied = original
                copied[0] = 9
                assert original[0] == 9
                return 0
        """)

    def test_array_parameter_contents_are_immutable(self):
        self.assert_rejected("""
            fn invalid(values: int[2]) -> int:
                values[0] = 9
                return values[0]
        """)

    def test_loop_havoc_includes_array_updates(self):
        self.assert_rejected("""
            fn invalid() -> int:
                values = [0, 0]
                index = 0
                while index < 2:
                    invariant 0 <= index <= 2
                    decreases 2 - index
                    assert values[0] == 0
                    values[0] = 1
                    index = index + 1
                return 0
        """)

    def test_record_contracts_and_value_rebinding(self):
        self.assert_proved("""
            type Pair:
                left: int
                right: int

            fn make(left: int, right: int) -> Pair:
                ensures result.left == left and result.right == right
                return Pair(left, right)

            fn copy() -> int:
                ensures result == 1
                original = make(1, 2)
                copied = original
                original = Pair(3, 4)
                return copied.left
        """)

    def test_parallel_results_support_contracts(self):
        self.assert_proved("""
            fn identity(x: int) -> int:
                ensures result == x
                return x

            fn combined() -> int:
                ensures result == 5
                parallel:
                    left = identity(2)
                    right = identity(3)
                return left + right
        """)

    def test_parallel_sibling_dependencies_are_rejected(self):
        for initialization in ["", "left = 7\n    "]:
            source = (
                "fn identity(x: int) -> int:\n"
                "    ensures result == x\n"
                "    return x\n\n"
                "fn invalid() -> int:\n"
                f"    {initialization}parallel:\n"
                "        left = identity(2)\n"
                "        right = identity(left)\n"
                "    return right\n"
            )
            with self.subTest(preexisting_target=bool(initialization)):
                self.assert_rejected(source)

    def test_parallel_duplicate_destinations_are_rejected(self):
        self.assert_rejected("""
            fn identity(x: int) -> int:
                ensures result == x
                return x

            fn invalid() -> int:
                parallel:
                    value = identity(2)
                    value = identity(3)
                return value
        """)

    def test_parallel_arrays_are_input_snapshots(self):
        self.assert_proved("""
            fn first(values: int[2]) -> int:
                ensures result == values[0]
                return values[0]

            fn combined() -> int:
                ensures result == 14
                values = [7, 2]
                parallel:
                    left = first(values)
                    right = first(values)
                values[0] = 99
                return left + right
        """)

    def test_bool_and_int_do_not_coerce(self):
        self.assert_rejected("""
            fn invalid() -> int:
                return true + 1
        """)
        self.assert_rejected("""
            fn invalid() -> bool:
                return 1 == true
        """)


if __name__ == "__main__":
    unittest.main()
