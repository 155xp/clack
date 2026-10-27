"""Array construction and extrema keep explicit imports and static shapes."""

from pathlib import Path
import tempfile
import textwrap
import unittest

from clack.frontend import CompileError, parse
from clack.modules import load_program
from clack.typecheck import check
from clack.verifier import verify


class ArrayOperatorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="clack-array-operators-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def program(self, source):
        path = self.root / "main.clack"
        path.write_text(textwrap.dedent(source).lstrip("\n"))
        return load_program(path)

    def checked(self, source):
        return verify(self.program(source))

    def test_fill_infers_int_and_bool_shapes_without_expanding_the_source(self):
        source = """
            from std.array import fill
            fn main():
                numbers = fill(-7, 1000)
                flags = fill(true, 17)
                assert len(numbers) == 1000 and numbers[999] == -7
                assert len(flags) == 17 and flags[16]
        """
        checked = self.checked(source)
        self.assertEqual(checked.local_types["main"]["numbers"], "int[1000]")
        self.assertEqual(checked.local_types["main"]["flags"], "bool[17]")

    def test_fill_counts_are_positive_bounded_integer_literals(self):
        for count in ("0", "-1", "+3", "1000001", "1 + 2", "n", "true", '"3"'):
            with self.subTest(count=count), self.assertRaisesRegex(CompileError, "fill length must be an integer literal"):
                check(self.program(f"from std.array import fill\nfn main():\n    n = 3\n    values = fill(0, {count})\n"))

    def test_fill_rejects_wrong_arity_and_unsupported_element_types(self):
        for arguments in ("", "0", "0, 3, 4", '"text", 3', "[1], 3", "Point(1), 3"):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(CompileError, "fill needs an int or bool"):
                check(self.program('from std.array import fill\ntype Point:\n    x: int\nfn main():\n    values = fill(' + arguments + ')\n'))

    def test_fill_values_must_be_safe_even_when_only_length_is_used(self):
        for value in ("1 / 0", "9223372036854775808"):
            with self.subTest(value=value), self.assertRaises(CompileError):
                self.checked(f"from std.array import fill\nfn main():\n    print(len(fill({value}, 10)))\n")

    def test_filled_arrays_are_independent_values(self):
        self.checked("""
            from std.array import fill
            fn main():
                original = fill(7, 3)
                copied = original
                copied[0] = 99
                assert original[0] == 7 and copied[0] == 99
                flags = fill(false, 2)
                other = flags
                other[1] = true
                assert not flags[1] and other[1]
        """)

    def test_extrema_are_exact_for_unrestricted_signed_inputs(self):
        self.checked("""
            from std.array import minimum, maximum
            fn lowest(values: int[3]) -> int:
                ensures result <= values[0] and result <= values[1] and result <= values[2]
                ensures result == values[0] or result == values[1] or result == values[2]
                return minimum(values)
            fn highest(values: int[3]) -> int:
                ensures result >= values[0] and result >= values[1] and result >= values[2]
                ensures result == values[0] or result == values[1] or result == values[2]
                return maximum(values)
            fn main():
                low = lowest([-9223372036854775808, 0, 9223372036854775807])
                high = highest([-9223372036854775808, 0, 9223372036854775807])
                assert low == -9223372036854775808 and high == 9223372036854775807
        """)

    def test_extrema_reject_wrong_arity_scalar_and_bool_arrays(self):
        for operation in ("minimum", "maximum"):
            for arguments in ("", "3", "[true, false]", "[1], [2]"):
                with self.subTest(operation=operation, arguments=arguments), self.assertRaisesRegex(CompileError, "needs exactly one fixed int array"):
                    check(self.program(f"from std.array import {operation}\nfn main():\n    value = {operation}({arguments})\n"))

    def test_new_operators_require_imports_and_cannot_be_forged(self):
        for name, arguments in (("fill", "0, 3"), ("minimum", "[1, 2]"), ("maximum", "[1, 2]")):
            for spelling in (name, "_clack_reduce_" + name):
                with self.subTest(name=spelling), self.assertRaises(CompileError):
                    check(self.program(f"fn main():\n    value = {spelling}({arguments})\n"))
        forged = parse("fn main():\n    value = _clack_reduce_fill(0, 3)\n")
        with self.assertRaisesRegex(CompileError, "explicit import"):
            check(forged)

    def test_reexports_preserve_new_operators_and_custom_names_stay_separate(self):
        (self.root / "facade.clack").write_text("from std.array import fill, minimum, maximum\n")
        self.checked("""
            from facade import fill, minimum, maximum
            fn main():
                values = fill(3, 5)
                low = minimum(values)
                high = maximum(values)
                assert low == 3 and high == 3
        """)
        (self.root / "custom.clack").write_text("fn minimum(value: int) -> int:\n    ensures result == value\n    return value\n")
        self.checked("from custom import minimum\nfn main():\n    value = minimum(42)\n    assert value == 42\n")

    def test_operators_cannot_appear_in_proofs_or_direct_parallel_jobs(self):
        for statement in ("assert minimum([1, 2]) == 1", "assert len(fill(0, 3)) == 3", "parallel:\n        value = maximum([1, 2])"):
            with self.subTest(statement=statement), self.assertRaises(CompileError):
                check(self.program("from std.array import fill, minimum, maximum\nfn main():\n    " + statement + "\n"))

    def test_filled_shapes_are_checked_at_function_boundaries(self):
        source = """
            from std.array import fill, minimum
            fn first(values: int[3]) -> int:
                return minimum(values)
            fn main():
                value = first(fill(7, 4))
                print(value)
        """
        with self.assertRaisesRegex(CompileError, r"needs int\[3\], got int\[4\]"):
            self.checked(source)
        self.checked(source.replace("fill(7, 4)", "fill(7, 3)"))


if __name__ == "__main__":
    unittest.main()
