"""Contracts and native results for the optional Clack statistics library."""

import random
from fractions import Fraction
from pathlib import Path
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
IMPORTS = "from stats import Summary, summarize4, mean4, variance4, span, sum_squares4\n"


class StatsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-stats-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        shutil.copyfile(ROOT / "stats.clack", self.directory / "stats.clack")

    def checked(self, body):
        source = self.directory / "main.clack"
        source.write_text(IMPORTS + "\nfn main():\n" + body, encoding="utf-8")
        program = load_program(source)
        return program, verify(program)

    def test_demo_and_every_loaded_function_are_verified(self):
        program = load_program(ROOT / "demo.clack")
        checked = verify(program)
        names = {entry["function"] for entry in checked.obligations}
        self.assertTrue({"stats.summarize4", "stats.mean4", "stats.variance4", "stats.span", "stats.sum_squares4"} <= names)

    def test_summary_contract_gives_exact_totals_and_extrema(self):
        self.checked("""    values = [3, 7, -2, 8]
    summary = summarize4(values)
    assert summary.total == 16
    assert summary.minimum == -2
    assert summary.maximum == 8
    width = span(summary)
    assert width == 10
""")

    def test_mean_preserves_fraction_instead_of_truncating(self):
        self.checked("""    positive = mean4([0, 0, 0, 1])
    negative = mean4([-1, -2, -3, -4])
    assert positive.numerator == 1 and positive.denominator == 4
    assert negative.numerator == -10 and negative.denominator == 4
""")

    def test_population_variance_preserves_fraction_and_zero(self):
        self.checked("""    fractional = variance4([0, 0, 0, 1])
    constant = variance4([-7, -7, -7, -7])
    assert fractional.numerator == 3 and fractional.denominator == 16
    assert constant.numerator == 0 and constant.denominator == 16
""")

    def test_boundary_values_and_zero_spread(self):
        self.checked("""    extremes = summarize4([-1000000, 1000000, -1000000, 1000000])
    width = span(extremes)
    squares = sum_squares4([-1000000, 1000000, -1000000, 1000000])
    assert extremes.total == 0 and width == 2000000
    assert squares == 4000000000000
    identical = summarize4([-7, -7, -7, -7])
    zero = span(identical)
    assert zero == 0
""")

    def test_out_of_domain_inputs_are_rejected(self):
        for function in ("summarize4", "mean4", "variance4", "sum_squares4"):
            for value in (-1000001, 1000001):
                with self.subTest(function=function, value=value), self.assertRaises(CompileError):
                    self.checked(f"    value = {function}([{value}, 0, 0, 0])\n")

    def test_span_requires_ordered_bounded_extrema(self):
        for minimum, maximum in ((7, 3), (-1000001, 0), (0, 1000001)):
            with self.subTest(minimum=minimum, maximum=maximum), self.assertRaises(CompileError):
                self.checked(f"    print(span(Summary(0, {minimum}, {maximum})))\n")

    def test_array_length_is_checked(self):
        with self.assertRaises(CompileError):
            self.checked("    value = summarize4([1, 2, 3])\n")

    @unittest.skipUnless(CC, "native checks require a C11 compiler")
    def test_native_outputs_match_independent_python_references(self):
        rng = random.Random(1729)
        cases = [[0, 0, 0, 0], [4, 4, 4, 4], [-1, -3, -8, -12],
                 [-1000000, 1000000, -1000000, 1000000]]
        cases += [[rng.randint(-1000000, 1000000) for _ in range(4)] for _ in range(12)]
        body = []
        expected = []
        for values in cases:
            body.extend([f"    values = {values}", "    summary = summarize4(values)", "    average = mean4(values)",
                         "    print(summary.total)", "    print(summary.minimum)", "    print(summary.maximum)",
                         "    print(average.numerator)", "    print(average.denominator)",
                         "    print(span(summary))", "    print(sum_squares4(values))"])
            expected.extend([sum(values), min(values), max(values), sum(values), 4,
                             max(values) - min(values), sum(value * value for value in values)])
        program, checked = self.checked("\n".join(body) + "\n")
        source = self.directory / "main.c"
        binary = self.directory / "main"
        source.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        compiled = subprocess.run([CC, "-std=c11", "-O3", "-pthread", str(source), "-o", str(binary)],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "".join(f"{value}\n" for value in expected))

    @unittest.skipUnless(CC, "native checks require a C11 compiler")
    def test_population_variance_matches_independent_fraction_reference(self):
        rng = random.Random(2451)
        cases = [[0, 0, 0, 0], [0, 0, 0, 1], [-7, -7, -7, -7],
                 [-1000000, 1000000, -1000000, 1000000]]
        cases += [[rng.randint(-1000000, 1000000) for _ in range(4)] for _ in range(12)]
        body = []
        expected = []
        for values in cases:
            body.extend([f"    variance = variance4({values})", "    print(variance.numerator)", "    print(variance.denominator)"])
            average = Fraction(sum(values), 4)
            expected.append(sum((Fraction(value) - average) ** 2 for value in values) / 4)
        program, checked = self.checked("\n".join(body) + "\n")
        source = self.directory / "variance.c"
        binary = self.directory / "variance"
        source.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        compiled = subprocess.run([CC, "-std=c11", "-O3", "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(source), "-o", str(binary)],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        numbers = [int(value) for value in result.stdout.splitlines()]
        self.assertEqual(numbers[1::2], [16] * len(cases))
        self.assertEqual([Fraction(numerator, denominator) for numerator, denominator in zip(numbers[::2], numbers[1::2])], expected)


if __name__ == "__main__":
    unittest.main()
