"""Source-library contracts, isolated module scopes, and native imports."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import CompileError, parse
from clack.verifier import verify


ROOT = Path(__file__).resolve().parents[1]
CC = shutil.which("cc")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-library-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def write(self, name, source):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        return path

    def load(self, source):
        from clack.modules import load_program
        return load_program(self.write("main.clack", source))

    def checked(self, source):
        return verify(self.load(source))

    def rejected(self, source):
        with self.assertRaises(CompileError):
            self.checked(source)

    def test_math_helpers_accept_full_domain_where_representable(self):
        self.checked("""
            from std.math import min, max, abs, clamp

            fn main():
                low = min(-9223372036854775808, 9223372036854775807)
                high = max(-9223372036854775808, 9223372036854775807)
                positive = abs(-9223372036854775807)
                bounded = clamp(150, 0, 100)
                assert low == -9223372036854775808
                assert high == 9223372036854775807
                assert positive == 9223372036854775807
                assert bounded == 100
                print(bounded)
        """)

    def test_abs_rejects_unrepresentable_positive_result(self):
        self.rejected("""
            from std.math import abs
            fn main():
                print(abs(-9223372036854775808))
        """)

    def test_clamp_rejects_reversed_bounds(self):
        self.rejected("""
            from std.math import clamp
            fn main():
                print(clamp(5, 10, 0))
        """)

    def test_array_sums_and_boolean_helpers_have_exact_summaries(self):
        self.checked("""
            from std.array import sum2, sum3, sum4, sum8, all4, any4
            fn main():
                two = sum2([1, 2])
                three = sum3([-1, 2, 3])
                four = sum4([1, 2, 3, 4])
                eight = sum8([1, 2, 3, 4, 5, 6, 7, 8])
                all = all4([true, true, true, true])
                any = any4([false, false, true, false])
                assert two == 3
                assert three == 4
                assert four == 10
                assert eight == 36
                assert all and any
                print(eight)
        """)

    def test_sum_accepts_extreme_elements_when_each_prefix_fits(self):
        self.checked("""
            from std.array import sum4
            fn main():
                answer = sum4([9223372036854775807, -9223372036854775807, -9223372036854775808, 9223372036854775807])
                assert answer == -1
                print(answer)
        """)

    def test_sum_rejects_overflow_even_if_final_math_sum_fits(self):
        for values in ("[9223372036854775807, 1, -1, 0]", "[-9223372036854775808, -1, 1, 0]"):
            with self.subTest(values=values):
                self.rejected(f"from std.array import sum4\nfn main():\n    print(sum4({values}))\n")

    def test_sum_array_length_is_checked(self):
        self.rejected("""
            from std.array import sum4
            fn main():
                print(sum4([1, 2, 3]))
        """)

    def test_imports_are_available_to_parallel_jobs(self):
        self.checked("""
            from std.array import sum4
            fn main():
                parallel:
                    left = sum4([1, 2, 3, 4])
                    right = sum4([10, 20, 30, 40])
                assert left + right == 110
                print(left + right)
        """)

    def test_local_helpers_have_separate_module_scopes(self):
        self.write("left.clack", """
            fn helper(x: int) -> int:
                ensures result == x
                return x
            fn left(x: int) -> int:
                ensures result == x
                return helper(x)
        """)
        self.write("right.clack", """
            fn helper(x: int) -> int:
                ensures result == 7
                return 7
            fn right(x: int) -> int:
                ensures result == 7
                return helper(x)
        """)
        self.checked("""
            from left import left
            from right import right
            fn main():
                first = left(10)
                second = right(10)
                assert first == 10 and second == 7
                print(first)
        """)

    def test_unimported_helper_is_not_visible_in_entry_scope(self):
        self.write("helpers.clack", """
            fn hidden() -> int:
                return 9
            fn exposed() -> int:
                return hidden()
        """)
        self.rejected("""
            from helpers import exposed
            fn main():
                print(hidden())
        """)

    def test_transitive_imports_share_one_loaded_module(self):
        self.write("base.clack", """
            fn identity(x: int) -> int:
                ensures result == x
                return x
        """)
        for module in ("left", "right"):
            self.write(f"{module}.clack", f"""
                from base import identity
                fn {module}(x: int) -> int:
                    ensures result == x
                    return identity(x)
            """)
        program = self.load("""
            from left import left
            from right import right
            fn main():
                first = left(12)
                second = right(8)
                print(first)
                print(second)
        """)
        self.assertEqual(len(program.functions), 4)
        verify(program)

    def test_record_types_and_private_dependencies_are_linked(self):
        self.write("shapes.clack", """
            type Point:
                x: int
                y: int
            type Box:
                point: Point
            fn make(x: int) -> Box:
                ensures result.point.x == x
                return Box(Point(x, 0))
        """)
        self.checked("""
            from shapes import Box, make
            type Point:
                value: bool
            fn main():
                box = make(17)
                assert box.point.x == 17
                print(box.point.x)
        """)

    def test_import_only_module_can_reexport_a_declaration(self):
        self.write("helpers.clack", "from std.math import min\n")
        self.checked("""
            from helpers import min
            fn main():
                answer = min(2, 3)
                assert answer == 2
                print(answer)
        """)

    def test_dotted_module_path_resolves_local_source(self):
        self.write("models/value.clack", """
            fn value() -> int:
                ensures result == 42
                return 42
        """)
        self.checked("""
            from models.value import value
            fn main():
                answer = value()
                assert answer == 42
                print(answer)
        """)

    def test_std_namespace_cannot_be_shadowed_by_local_files(self):
        self.write("std/math.clack", "fn min(a: int, b: int) -> int:\n    return 999\n")
        self.checked("""
            from std.math import min
            fn main():
                answer = min(7, 9)
                assert answer == 7
                print(answer)
        """)

    def test_missing_modules_symbols_and_collisions_are_rejected(self):
        self.write("helpers.clack", "fn identity(x: int) -> int:\n    return x\n")
        for source in (
            "from missing import value\nfn main():\n    print(0)\n",
            "from helpers import missing\nfn main():\n    print(0)\n",
            "from helpers import identity\nfrom helpers import identity\nfn main():\n    print(0)\n",
            "from helpers import identity\nfn identity(x: int) -> int:\n    return x\nfn main():\n    print(0)\n",
        ):
            with self.subTest(source=source.splitlines()[0]):
                self.rejected(source)

    def test_import_cycles_are_rejected(self):
        self.write("left.clack", "from right import right\nfn left() -> int:\n    return 1\n")
        self.write("right.clack", "from left import left\nfn right() -> int:\n    return 2\n")
        self.rejected("from left import left\nfn main():\n    print(left())\n")

    def test_library_main_is_rejected(self):
        self.write("helpers.clack", "fn helper() -> int:\n    return 1\nfn main():\n    print(2)\n")
        self.rejected("from helpers import helper\nfn main():\n    print(helper())\n")

    def test_unused_library_functions_are_also_verified(self):
        self.write("helpers.clack", """
            fn safe() -> int:
                return 1
            fn wrong(x: int) -> int:
                ensures result == x + 1
                return x
        """)
        self.rejected("from helpers import safe\nfn main():\n    print(safe())\n")

    def test_cli_reports_the_actual_library_source_on_proof_failure(self):
        library = self.write("helpers.clack", """
            fn wrong(x: int) -> int:
                ensures result == x + 1
                return x
        """)
        main = self.write("main.clack", "from helpers import wrong\nfn main():\n    print(wrong(2))\n")
        result = subprocess.run([sys.executable, "-m", "clack", "check", str(main)], cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(library), result.stderr)
        self.assertIn("return x", result.stderr)

    def test_unresolved_imports_cannot_be_silently_ignored(self):
        program = parse("from std.math import min\nfn main():\n    print(1)\n")
        with self.assertRaisesRegex(CompileError, "unresolved imports"):
            verify(program)

    def test_proof_exports_identify_original_library_locations(self):
        library = self.write("helpers.clack", """
            fn identity(x: int) -> int:
                ensures result == x
                return x
        """)
        program = self.load("from helpers import identity\nfn main():\n    print(identity(7))\n")
        directory = self.directory / "proofs"
        verify(program, proof_dir=directory)
        obligations = json.loads((directory / "obligations.json").read_text(encoding="utf-8"))
        imported = [entry for entry in obligations if entry["function"] == "helpers.identity"]
        self.assertTrue(imported)
        for entry in imported:
            self.assertEqual(entry["source"], str(library))
            self.assertIn(entry["line"], (1, 2, 3))
            self.assertNotIn("_clack_module_", entry["claim"])

    def test_build_outputs_cannot_overwrite_an_imported_source(self):
        library = self.write("helpers.clack", "fn identity(x: int) -> int:\n    return x\n")
        original = library.read_bytes()
        main = self.write("main.clack", "from helpers import identity\nfn main():\n    print(identity(7))\n")
        for command in ("build", "emit-c"):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, "-m", "clack", command, str(main), "-o", str(library)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertIn("including imported libraries", result.stderr)
                self.assertEqual(library.read_bytes(), original)

    @unittest.skipUnless(CC, "native imports need a C11 compiler")
    def test_native_program_combines_standard_and_local_libraries(self):
        self.write("helpers.clack", """
            from std.math import clamp
            fn bounded(x: int) -> int:
                ensures 0 <= result <= 100
                return clamp(x, 0, 100)
        """)
        program = self.load("""
            from helpers import bounded
            from std.array import sum4
            fn main():
                parallel:
                    total = sum4([10, 20, 30, 40])
                    capped = bounded(150)
                print(total)
                print(capped)
        """)
        checked = verify(program)
        c_file = self.directory / "program.c"
        binary = self.directory / "program"
        c_file.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        compile_result = subprocess.run([CC, "-std=c11", "-O3", "-pthread", str(c_file), "-o", str(binary)],
                                        capture_output=True, text=True, timeout=30)
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "100\n100\n")


if __name__ == "__main__":
    unittest.main()
