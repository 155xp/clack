"""Verify source contracts and compare native results with Python integers."""

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
IMPORTS = "from matrices import Matrix2, Vec2, Vec4, identity, transpose, determinant, multiply, apply, add, dot4, squared_norm4\n"


class MatrixTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-matrix-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        shutil.copyfile(ROOT / "matrices.clack", self.directory / "matrices.clack")

    def checked(self, body, declarations=""):
        source = self.directory / "main.clack"
        source.write_text(IMPORTS + declarations + "\nfn main():\n" + body, encoding="utf-8")
        program = load_program(source)
        return program, verify(program)

    def native(self, body):
        program, checked = self.checked(body)
        source = self.directory / "program.c"
        binary = self.directory / "program"
        source.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        built = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-Wall", "-Wextra", "-Werror", "-O3", "-pthread",
                                "-fsanitize=undefined", "-fno-sanitize-recover=all", str(source), "-o", str(binary)],
                               text=True, capture_output=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [int(line) for line in result.stdout.splitlines()]

    def test_exact_algebraic_contracts_compose(self):
        self.checked("""    matrix = Matrix2(1, -2, 3, 4)
    one = identity()
    product = multiply(matrix, one)
    assert product.a == matrix.a and product.b == matrix.b
    assert product.c == matrix.c and product.d == matrix.d
    flipped = transpose(matrix)
    restored = transpose(flipped)
    assert restored.a == matrix.a and restored.b == matrix.b
    assert restored.c == matrix.c and restored.d == matrix.d
    original_det = determinant(matrix)
    flipped_det = determinant(flipped)
    assert original_det == flipped_det
    print(original_det)
""")

    def test_transpose_accepts_the_full_integer_domain(self):
        self.checked("""    value = Matrix2(-9223372036854775808, 9223372036854775807, 0, -1)
    flipped = transpose(value)
    assert flipped.a == -9223372036854775808
    assert flipped.b == 0 and flipped.c == 9223372036854775807
    assert flipped.d == -1
    print(flipped.c)
""")

    def test_inclusive_arithmetic_boundaries(self):
        self.checked("""    matrix = Matrix2(1000000, -1000000, 1000000, 1000000)
    product = multiply(matrix, matrix)
    transformed = apply(matrix, Vec2(1000000, -1000000))
    det = determinant(matrix)
    assert product.a == 0 and product.b == -2000000000000
    assert product.c == 2000000000000 and product.d == 0
    assert transformed.x == 2000000000000 and transformed.y == 0
    assert det == 2000000000000
    print(det)
""")

    def test_outside_the_documented_domain_is_rejected(self):
        bodies = [
            "    print(determinant(Matrix2(1000001, 0, 0, 1)))\n",
            "    result_matrix = multiply(Matrix2(1, 0, 0, 1), Matrix2(0, 0, 0, -1000001))\n    print(result_matrix.a)\n",
            "    result_vector = apply(Matrix2(1, 0, 0, 1), Vec2(1000001, 0))\n    print(result_vector.x)\n",
            "    result_matrix = add(Matrix2(1000001, 0, 0, 0), Matrix2(0, 0, 0, 0))\n    print(result_matrix.a)\n",
        ]
        for body in bodies:
            with self.subTest(body=body), self.assertRaisesRegex(CompileError, "precondition"):
                self.checked(body)

    def test_large_product_cannot_bypass_the_next_input_contract(self):
        with self.assertRaisesRegex(CompileError, "precondition"):
            self.checked("""    matrix = Matrix2(1000000, 1000000, 1000000, 1000000)
    large = multiply(matrix, matrix)
    print(determinant(large))
""")

    def test_record_shape_does_not_replace_nominal_type(self):
        declaration = "type Lookalike:\n    a: int\n    b: int\n    c: int\n    d: int\n"
        with self.assertRaisesRegex(CompileError, "argument"):
            self.checked("    print(determinant(Lookalike(1, 2, 3, 4)))\n", declaration)

    def test_vector_contracts_give_exact_products_and_nonnegative_norms(self):
        self.checked("""    left = Vec4(1, -2, 3, -4)
    right = Vec4(5, 6, -7, 8)
    product = dot4(left, right)
    reversed = dot4(right, left)
    energy = squared_norm4(left)
    assert product == -60 and reversed == product
    assert energy == 30
    extreme = squared_norm4(Vec4(-1000000, 1000000, -1000000, 1000000))
    assert extreme == 4000000000000
""")

    def test_vector_arithmetic_checks_every_input_component(self):
        for component in range(4):
            for outside in (-1000001, 1000001, -(1 << 63), (1 << 63) - 1):
                values = [0] * 4
                values[component] = outside
                vector = "Vec4(" + ", ".join(map(str, values)) + ")"
                for expression in (f"dot4({vector}, Vec4(0, 0, 0, 0))", f"dot4(Vec4(0, 0, 0, 0), {vector})", f"squared_norm4({vector})"):
                    with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, "precondition"):
                        self.checked(f"    print({expression})\n")

    @unittest.skipUnless(CC, "native comparisons need a C compiler")
    def test_native_results_match_independent_integer_reference(self):
        rng = random.Random(42)
        cases = [((1, 2, 3, 4), (5, 6, 7, 8), (2, 3)),
                 ((0, 0, 0, 0), (1, 0, 0, 1), (0, 0)),
                 ((1000000, -1000000, 1000000, 1000000), (-1000000, 1000000, 1000000, -1000000), (-1000000, 1000000))]
        cases += [(tuple(rng.randint(-100, 100) for _ in range(4)),
                   tuple(rng.randint(-100, 100) for _ in range(4)),
                   tuple(rng.randint(-100, 100) for _ in range(2))) for _ in range(6)]
        body, expected = [], []
        for i, (left, right, vector) in enumerate(cases):
            a, b, c, d = left
            e, f, g, h = right
            x, y = vector
            body += [f"    left{i} = Matrix2({a}, {b}, {c}, {d})",
                     f"    right{i} = Matrix2({e}, {f}, {g}, {h})",
                     f"    product{i} = multiply(left{i}, right{i})",
                     f"    vector{i} = apply(left{i}, Vec2({x}, {y}))",
                     f"    added{i} = add(left{i}, right{i})",
                     f"    print(determinant(left{i}))"]
            expected.append(a * d - b * c)
            for field in ("a", "b", "c", "d"):
                body.append(f"    print(product{i}.{field})")
            expected += [a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h]
            body += [f"    print(vector{i}.x)", f"    print(vector{i}.y)"]
            expected += [a * x + b * y, c * x + d * y]
            for field in ("a", "b", "c", "d"):
                body.append(f"    print(added{i}.{field})")
            expected += [a + e, b + f, c + g, d + h]
        self.assertEqual(self.native("\n".join(body) + "\n"), expected)

    @unittest.skipUnless(CC, "native demo needs a C compiler")
    def test_parallel_demo(self):
        source = (ROOT / "demo.clack").read_text()
        # Use the shipped source, preserving its parallel block.
        self.assertEqual(self.native(source.split("fn main():\n", 1)[1]), [19, 50, 8, 18, -2])

    @unittest.skipUnless(CC, "native comparisons need a C compiler")
    def test_native_vector_results_match_independent_integer_reference(self):
        rng = random.Random(731)
        cases = [((0, 0, 0, 0), (0, 0, 0, 0)),
                 ((1000000,) * 4, (-1000000,) * 4),
                 ((-1000000, 1000000, -1000000, 1000000), (1000000, -1000000, 1000000, -1000000))]
        cases += [(tuple(rng.randint(-1000000, 1000000) for _ in range(4)),
                   tuple(rng.randint(-1000000, 1000000) for _ in range(4))) for _ in range(12)]
        body, expected = [], []
        for index, (left, right) in enumerate(cases):
            body += [f"    left{index} = Vec4({', '.join(map(str, left))})",
                     f"    right{index} = Vec4({', '.join(map(str, right))})",
                     f"    print(dot4(left{index}, right{index}))",
                     f"    print(squared_norm4(left{index}))"]
            expected += [sum(a * b for a, b in zip(left, right)), sum(value * value for value in left)]
        self.assertEqual(self.native("\n".join(body) + "\n"), expected)

    @unittest.skipUnless(CC, "native demo needs a C compiler")
    def test_parallel_vector_demo(self):
        source = (ROOT / "vector_demo.clack").read_text()
        self.assertEqual(self.native(source.split("fn main():\n", 1)[1]), [70, 30])


if __name__ == "__main__":
    unittest.main()
