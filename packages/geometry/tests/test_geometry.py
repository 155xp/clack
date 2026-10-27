"""Check library contracts, integer boundaries, and native geometry results."""

from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from clack.frontend import CompileError
from clack.modules import load_program
from clack.verifier import verify


ROOT = Path(__file__).resolve().parents[1]
IMPORT = "from geometry import Point, Rect, translate, squared_distance, contains, intersects, area, bounding_rect\n"


class GeometryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-geometry-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        shutil.copyfile(ROOT / "geometry.clack", self.directory / "geometry.clack")

    def checked(self, statements):
        source = IMPORT + "fn main():\n" + "\n".join("    " + line for line in statements.splitlines()) + "\n"
        path = self.directory / "app.clack"
        path.write_text(source, encoding="utf-8")
        return verify(load_program(path))

    def test_translation_and_distance_have_exact_results(self):
        self.checked("""a = Point(3, 4)
b = translate(a, -6, -8)
assert b.x == -3 and b.y == -4
distance = squared_distance(a, b)
assert distance == 100
print(distance)""")

    def test_distance_at_supported_extremes_fits_i64(self):
        self.checked("""distance = squared_distance(Point(-1000000, -1000000), Point(1000000, 1000000))
assert distance == 8000000000000
moved = translate(Point(1000000, -1000000), 1000000, -1000000)
assert moved.x == 2000000 and moved.y == -2000000
print(distance)""")

    def test_containment_includes_every_boundary(self):
        self.checked("""rect = Rect(-5, -3, 7, 11)
a = contains(rect, Point(-5, -3))
b = contains(rect, Point(7, 11))
c = contains(rect, Point(7, 12))
assert a and b and not c
print(a)""")

    def test_shared_edge_and_corner_count_as_intersection(self):
        self.checked("""a = Rect(0, 0, 3, 4)
edge = intersects(a, Rect(3, 1, 8, 2))
corner = intersects(a, Rect(3, 4, 8, 9))
separate = intersects(a, Rect(4, 4, 8, 9))
assert edge and corner and not separate
print(edge)""")

    def test_area_and_degenerate_rectangles(self):
        self.checked("""large = area(Rect(-1000000, -1000000, 1000000, 1000000))
line = area(Rect(3, 2, 3, 8))
point = contains(Rect(3, 2, 3, 2), Point(3, 2))
assert large == 4000000000000 and line == 0 and point
print(large)""")

    def test_bounding_rect_accepts_full_integer_coordinates(self):
        self.checked("""bounds = bounding_rect(Point(-9223372036854775808, 9223372036854775807), Point(9223372036854775807, -9223372036854775808))
assert bounds.left == -9223372036854775808
assert bounds.top == -9223372036854775808
assert bounds.right == 9223372036854775807
assert bounds.bottom == 9223372036854775807
print(bounds.left)""")

    def test_invalid_rectangles_and_unbounded_arithmetic_are_rejected(self):
        invalid = [
            "print(area(Rect(2, 0, 1, 4)))",
            "print(contains(Rect(0, 8, 4, 2), Point(1, 1)))",
            "print(intersects(Rect(3, 0, 1, 2), Rect(0, 0, 4, 4)))",
            "print(squared_distance(Point(1000001, 0), Point(0, 0)))",
            "p = translate(Point(0, 0), 1000001, 0)\nprint(p.x)",
        ]
        for statements in invalid:
            with self.subTest(statements=statements), self.assertRaises(CompileError):
                self.checked(statements)

    @unittest.skipUnless(shutil.which("cc"), "native demo needs a C11 compiler")
    def test_native_demo_output(self):
        result = subprocess.run([sys.executable, "-m", "clack", "run", str(ROOT / "demo.clack")],
                                cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "25\n12\ntrue\ntrue\n")

    @unittest.skipUnless(shutil.which("cc"), "native samples need a C11 compiler")
    def test_native_samples_match_independent_python_geometry(self):
        rng = random.Random(42)
        lines, expected = [IMPORT, "fn main():"], []
        for index in range(12):
            ax, ay, bx, by = [rng.randint(-1000, 1000) for _ in range(4)]
            dx, dy = rng.randint(-100, 100), rng.randint(-100, 100)
            left, right = sorted((ax, bx))
            top, bottom = sorted((ay, by))
            px, py = rng.randint(-1000, 1000), rng.randint(-1000, 1000)
            lines += [
                f"    p{index} = translate(Point({ax}, {ay}), {dx}, {dy})",
                f"    print(p{index}.x)",
                f"    print(p{index}.y)",
                f"    print(squared_distance(Point({ax}, {ay}), Point({bx}, {by})))",
                f"    print(area(Rect({left}, {top}, {right}, {bottom})))",
                f"    print(contains(Rect({left}, {top}, {right}, {bottom}), Point({px}, {py})))",
                f"    print(intersects(Rect({left}, {top}, {right}, {bottom}), Rect({px}, {py}, {px+7}, {py+11})))",
            ]
            expected += [str(ax + dx), str(ay + dy), str((ax - bx) ** 2 + (ay - by) ** 2),
                         str((right - left) * (bottom - top)),
                         str(left <= px <= right and top <= py <= bottom).lower(),
                         str(left <= px + 7 and px <= right and top <= py + 11 and py <= bottom).lower()]
        app = self.directory / "samples.clack"
        app.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run([sys.executable, "-m", "clack", "run", str(app)], cwd=self.directory,
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), expected)


if __name__ == "__main__":
    unittest.main()
