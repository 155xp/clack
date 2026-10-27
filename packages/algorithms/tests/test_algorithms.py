"""Verify contracts and compare native algorithms with independent references."""

import bisect
from collections import Counter
import itertools
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from clack.codegen import emit_c
from clack.frontend import CompileError
from clack.modules import load_program
from clack.verifier import verify


ROOT = Path(__file__).resolve().parents[1]
CC = shutil.which("cc")
IMPORTS = "from algorithms import sort4, first_index4, argmin4, lower_bound4\n"
MIN_INT, MAX_INT = -(1 << 63), (1 << 63) - 1


class AlgorithmTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-algorithms-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copyfile(ROOT / "algorithms.clack", self.root / "algorithms.clack")

    def checked(self, body, declarations=""):
        path = self.root / "main.clack"
        path.write_text(IMPORTS + declarations + "\nfn main():\n" + body, encoding="utf-8")
        program = load_program(path)
        return program, verify(program)

    def native(self, body):
        program, checked = self.checked(body)
        path, binary = self.root / "program.c", self.root / "program"
        path.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        result = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-Wall", "-Wextra", "-Werror", "-O3", "-pthread", "-fsanitize=undefined", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [int(line) for line in result.stdout.splitlines()]

    def test_sorted_contract_preserves_duplicate_multiplicity(self):
        self.checked("""    values = [2, -1, 2, 1]
    ordered = sort4(values)
    assert ordered[0] == -1 and ordered[1] == 1
    assert ordered[2] == 2 and ordered[3] == 2
    assert values[0] == 2 and values[1] == -1
""")

    def test_full_signed_range_and_first_tie_contracts(self):
        self.checked("""    values = [9223372036854775807, -9223372036854775808, -9223372036854775808, 0]
    ordered = sort4(values)
    smallest = argmin4(values)
    first = first_index4(values, -9223372036854775808)
    assert ordered[0] == -9223372036854775808
    assert ordered[3] == 9223372036854775807
    assert smallest == 1 and first == 1
""")

    def test_lower_bound_contract_composes_with_sort(self):
        self.checked("""    ordered = sort4([7, -3, 7, 1])
    before = lower_bound4(ordered, -9223372036854775808)
    middle = lower_bound4(ordered, 7)
    after = lower_bound4(ordered, 9223372036854775807)
    assert before == 0 and middle == 2 and after == 4
""")

    def test_lower_bound_rejects_unsorted_input(self):
        with self.assertRaisesRegex(CompileError, "precondition"):
            self.checked("    print(lower_bound4([0, 3, 2, 4], 2))\n")

    def test_array_shape_and_scalar_types_are_checked(self):
        for expression in ("sort4([1, 2, 3])", "argmin4([true, false, true, false])", "first_index4([1, 2, 3, 4], true)"):
            with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, "argument"):
                self.checked("    result_value = " + expression + "\n")

    def test_sort_cannot_satisfy_a_false_postcondition(self):
        declaration = "fn wrong(values: int[4]) -> int[4]:\n    ensures result[0] == values[0]\n    return sort4(values)\n"
        with self.assertRaisesRegex(CompileError, "postcondition"):
            self.checked("    print(0)\n", declaration)

    @unittest.skipUnless(CC, "native algorithms need a C11 compiler")
    def test_native_outputs_match_sort_search_and_multiset_references(self):
        rng = random.Random(619)
        cases = list(itertools.permutations([-2, 0, 1, 9]))
        cases += [(0, 0, 0, 0), (MIN_INT, MAX_INT, MIN_INT, MAX_INT), (MAX_INT, 0, MIN_INT, -1)]
        cases += [tuple(rng.randint(-5, 5) for _ in range(4)) for _ in range(12)]
        body, expected = [], []
        for number, values in enumerate(cases):
            literal = "[" + ", ".join(map(str, values)) + "]"
            target = values[number % 4] if number % 2 else rng.randint(-6, 6)
            ordered = sorted(values)
            body += [f"    values{number} = {literal}", f"    sorted{number} = sort4(values{number})"]
            body += [f"    print(sorted{number}[{index}])" for index in range(4)]
            body += [f"    print(first_index4(values{number}, {target}))", f"    print(argmin4(values{number}))", f"    print(lower_bound4(sorted{number}, {target}))"]
            expected += ordered + [values.index(target) if target in values else -1, min(range(4), key=lambda i: values[i]), bisect.bisect_left(ordered, target)]
        actual = self.native("\n".join(body) + "\n")
        self.assertEqual(actual, expected)
        for number, values in enumerate(cases):
            self.assertEqual(Counter(actual[number * 7:number * 7 + 4]), Counter(values))

    @unittest.skipUnless(CC, "native demo needs a C11 compiler")
    def test_shipped_demo_runs(self):
        body = (ROOT / "demo.clack").read_text().split("fn main():\n", 1)[1]
        self.assertEqual(self.native(body), [-3, 1, 7, 7, 0, -1, 1, 2])


if __name__ == "__main__":
    unittest.main()
