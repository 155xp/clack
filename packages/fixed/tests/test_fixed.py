"""Fixed-point contracts and native arithmetic against exact integer references."""

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
IMPORTS = "from fixed import Fixed, from_int, to_int, from_ratio, add, subtract, multiply, divide\n"
MIN_INT, MAX_INT = -(1 << 63), (1 << 63) - 1


def trunc(numerator, denominator):
    magnitude = abs(numerator) // abs(denominator)
    return -magnitude if (numerator < 0) != (denominator < 0) else magnitude


class FixedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-fixed-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copyfile(ROOT / "fixed.clack", self.root / "fixed.clack")

    def checked(self, body, declarations=""):
        path = self.root / "main.clack"
        path.write_text(IMPORTS + declarations + "\nfn main():\n" + body, encoding="utf-8")
        program = load_program(path)
        return program, verify(program)

    def native(self, body):
        program, checked = self.checked(body)
        path, binary = self.root / "program.c", self.root / "program"
        path.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        built = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-Wall", "-Wextra", "-Werror", "-O3", "-pthread", "-fsanitize=undefined", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [int(line) for line in result.stdout.splitlines()]

    def test_contracts_compose_at_the_documented_scale(self):
        self.checked("""    left = from_ratio(3, 2)
    right = from_int(2)
    product = multiply(left, right)
    quotient = divide(product, right)
    difference = subtract(product, left)
    total = add(left, difference)
    assert product.raw == 3000 and quotient.raw == 1500
    assert difference.raw == 1500 and total.raw == 3000
    rounded = to_int(Fixed(-1999))
    assert rounded == -1
""")

    def test_zero_divisors_are_rejected(self):
        for expression in ("from_ratio(1, 0)", "divide(Fixed(1), Fixed(0))"):
            with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, "precondition"):
                self.checked("    result_value = " + expression + "\n    print(result_value.raw)\n")

    def test_operation_domains_reject_large_raw_values(self):
        for expression in ("from_int(1000000000001)", "from_ratio(-1000000000001, 1)",
                           "add(Fixed(1000000000000001), Fixed(0))",
                           "subtract(Fixed(0), Fixed(-1000000000000001))",
                           "multiply(Fixed(1000000001), Fixed(1))",
                           "divide(Fixed(-1000000000001), Fixed(1))"):
            with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, "precondition"):
                self.checked("    result_value = " + expression + "\n    print(result_value.raw)\n")

    def test_nominal_fixed_values_do_not_silently_accept_plain_integers(self):
        with self.assertRaisesRegex(CompileError, "argument"):
            self.checked("    result_value = multiply(1500, Fixed(2000))\n    print(result_value.raw)\n")

    def test_an_incorrect_rounding_postcondition_is_rejected(self):
        declaration = "fn wrong() -> int:\n    ensures result == -2\n    return to_int(Fixed(-1999))\n"
        with self.assertRaisesRegex(CompileError, "postcondition"):
            self.checked("    print(0)\n", declaration)

    @unittest.skipUnless(CC, "native tests need a C11 compiler")
    def test_native_arithmetic_matches_exact_truncation_reference(self):
        rng = random.Random(707)
        pairs = [(0, 1), (1, -3), (-1, 3), (-1999, -7), (10**9, -(10**9))]
        pairs += [(rng.randint(-10**8, 10**8), rng.choice((-1, 1)) * rng.randint(1, 10**8)) for _ in range(20)]
        body, expected = "", []
        for left, right in pairs:
            for operation, reference in (
                ("add", left + right), ("subtract", left - right),
                ("multiply", trunc(left * right, 1000)),
                ("divide", trunc(left * 1000, right)),
            ):
                body += f"    print({operation}(Fixed({left}), Fixed({right})).raw)\n"
                expected.append(reference)
            body += f"    print(from_ratio({left}, {right}).raw)\n"
            expected.append(trunc(left * 1000, right))
        for value in (MIN_INT, MAX_INT, -1999, -1, 0, 1, 1999):
            body += f"    print(to_int(Fixed({value})))\n"
            expected.append(trunc(value, 1000))
        for value in (-10**12, -3, 0, 7, 10**12):
            body += f"    print(from_int({value}).raw)\n"
            expected.append(value * 1000)
        self.assertEqual(self.native(body), expected)

    @unittest.skipUnless(CC, "native tests need a C11 compiler")
    def test_division_handles_extreme_denominators_and_largest_domains(self):
        body, expected = "", []
        for numerator in (-10**12, 0, 10**12):
            for denominator in (MIN_INT, MAX_INT, -1, 1):
                body += f"    print(from_ratio({numerator}, {denominator}).raw)\n"
                body += f"    print(divide(Fixed({numerator}), Fixed({denominator})).raw)\n"
                expected.extend([trunc(numerator * 1000, denominator)] * 2)
        body += "    print(add(Fixed(1000000000000000), Fixed(1000000000000000)).raw)\n"
        body += "    print(subtract(Fixed(-1000000000000000), Fixed(1000000000000000)).raw)\n"
        expected.extend([2 * 10**15, -2 * 10**15])
        self.assertEqual(self.native(body), expected)


if __name__ == "__main__":
    unittest.main()
