"""Parser acceptance and diagnostics for the public language surface."""

import textwrap
import unittest

from clack.frontend import (
    ArrayLit,
    Assign,
    Binary,
    BoolLit,
    Call,
    CompileError,
    Field,
    If,
    Index,
    IndexAssign,
    IntLit,
    Name,
    Parallel,
    Unary,
    While,
    parse,
)


class FrontendTests(unittest.TestCase):
    def program(self, source):
        return parse(textwrap.dedent(source).lstrip("\n"))

    def expression(self, source):
        return parse(f"fn main():\n    x = {source}\n").functions[0].body[0].value

    def assert_rejected(self, source, message, line=None):
        with self.assertRaisesRegex(CompileError, message) as raised:
            self.program(source)
        if line is not None:
            self.assertEqual(raised.exception.line, line)
        self.assertGreaterEqual(raised.exception.column, 1)

    def test_comments_and_blank_lines_preserve_source_locations(self):
        program = parse(
            "# arbitrary text: import os; __import__('os')\n"
            "\n"
            "fn main(): # entry point\n"
            "    # a comment with unmatched brackets: (((\n"
            "    x = 4 # inline comment\n"
            "\n"
            "    print(x)\n"
        )
        self.assertEqual(program.functions[0].line, 3)
        self.assertEqual([stmt.line for stmt in program.functions[0].body], [5, 7])

    def test_arithmetic_comparison_and_boolean_precedence(self):
        value = self.expression("not 1 + 2 * 3 < 8 and true or false")
        self.assertEqual(value.op, "or")
        self.assertEqual(value.right, BoolLit(line=2, value=False))
        conjunction = value.left
        self.assertEqual(conjunction.op, "and")
        self.assertEqual(conjunction.left.op, "not")
        comparison = conjunction.left.operand
        self.assertEqual(comparison.op, "<")
        self.assertEqual(comparison.left.op, "+")
        self.assertEqual(comparison.left.right.op, "*")

    def test_unary_and_parentheses_precedence(self):
        value = self.expression("-(1 + 2) * 3 - 4 / 2 % 2")
        self.assertEqual(value.op, "-")
        self.assertEqual(value.left.op, "*")
        self.assertIsInstance(value.left.left, Unary)
        self.assertEqual(value.left.left.operand.op, "+")
        self.assertEqual(value.right.op, "%")
        self.assertEqual(value.right.left.op, "/")

    def test_chained_comparison_means_both_comparisons(self):
        value = self.expression("0 <= n < 10")
        self.assertIsInstance(value, Binary)
        self.assertEqual(value.op, "and")
        self.assertEqual(value.left.op, "<=")
        self.assertEqual(value.right.op, "<")
        self.assertEqual(value.left.right, Name(line=2, name="n"))
        self.assertEqual(value.right.left, Name(line=2, name="n"))

    def test_function_contracts_and_loop_annotations(self):
        program = self.program("""
            fn count(n: int) -> int:
                requires n >= 0
                ensures result == n
                i = 0
                while i < n:
                    invariant 0 <= i
                    invariant i <= n
                    decreases n - i
                    i = i + 1
                return i
        """)
        function = program.functions[0]
        self.assertEqual(function.params, [("n", "int")])
        self.assertEqual(len(function.requires), 1)
        self.assertEqual(len(function.ensures), 1)
        loop = function.body[1]
        self.assertIsInstance(loop, While)
        self.assertEqual(len(loop.invariants), 2)
        self.assertEqual(loop.decreases.op, "-")

    def test_record_arrays_and_parallel_bindings(self):
        program = self.program("""
            type Point:
                x: int
                flags: bool[2]

            fn translate(p: Point, values: int[3]) -> Point:
                return Point(p.x + values[0], p.flags)

            fn main():
                p = Point(1, [true, false])
                values = [1, 2, 3]
                values[0] = p.x
                parallel:
                    left = translate(p, values)
                    right = translate(p, [4, 5, 6])
                print(left.x)
        """)
        self.assertEqual(program.records[0].fields, [("x", "int"), ("flags", "bool[2]")])
        function = program.functions[0]
        self.assertEqual(function.params, [("p", "Point"), ("values", "int[3]")])
        self.assertEqual(function.return_type, "Point")
        body = program.functions[1].body
        self.assertIsInstance(body[1].value, ArrayLit)
        self.assertIsInstance(body[2], IndexAssign)
        self.assertIsInstance(body[2].value, Field)
        self.assertIsInstance(body[3], Parallel)
        self.assertEqual([binding.name for binding in body[3].bindings], ["left", "right"])
        self.assertTrue(all(isinstance(binding.value, Call) for binding in body[3].bindings))

    def test_postfix_access_and_multiline_arguments(self):
        value = self.expression("Point(1, 2).x")
        self.assertIsInstance(value, Field)
        self.assertIsInstance(value.value, Call)
        program = parse("fn main():\n    x = f(\n        [1, 2, 3],\n        true,\n    )")
        value = program.functions[0].body[0].value
        self.assertEqual(value.name, "f")
        self.assertEqual(len(value.args), 2)
        self.assertIsInstance(self.expression("values[i + 1]"), Index)

    def test_elif_binds_to_the_matching_if(self):
        program = self.program("""
            fn main():
                if true:
                    print(1)
                elif false:
                    print(2)
                else:
                    print(3)
        """)
        branch = program.functions[0].body[0]
        self.assertIsInstance(branch, If)
        self.assertIsInstance(branch.else_body[0], If)
        self.assertEqual(len(branch.else_body[0].else_body), 1)

    def test_spaces_are_flexible_but_tabs_and_bad_dedents_reject(self):
        self.assertEqual(len(parse("fn main():\n  print(1)\n").functions), 1)
        self.assert_rejected("fn main():\n\tprint(1)\n", "spaces for indentation", line=2)
        self.assert_rejected("fn main():\n    print(1)\n  print(2)\n", "inconsistent indentation", line=3)

    def test_annotations_cannot_be_misplaced_or_incomplete(self):
        cases = [
            ("fn main():\n    x = 1\n    requires true\n", "contracts must appear", 3),
            ("fn main():\n    invariant true\n", "loop annotations", 2),
            ("fn main():\n    while true:\n        print(1)\n", "must start with 'invariant", 2),
            ("fn main():\n    while true:\n        invariant true\n        print(1)\n", "needs 'decreases", 4),
            ("fn main():\n    while true:\n        invariant true\n        decreases 1\n        decreases 0\n", "loop annotations", 5),
        ]
        for source, message, line in cases:
            with self.subTest(source=source):
                self.assert_rejected(source, message, line)

    def test_parallel_blocks_require_named_calls(self):
        for body in ["print(1)", "x = 1", "values[0] = f()"]:
            with self.subTest(body=body):
                self.assert_rejected(f"fn main():\n    parallel:\n        {body}\n", "only 'name = function")

    def test_immutable_record_fields_and_invalid_assignment_targets(self):
        self.assert_rejected("fn main():\n    p.x = 2\n", "record fields are immutable", 2)
        self.assert_rejected("fn main():\n    a[0][0] = 2\n", "assignment needs", 2)
        self.assert_rejected("fn main():\n    1 = 2\n", "assignment needs", 2)

    def test_unsupported_host_language_and_injection_syntax_is_rejected(self):
        cases = [
            ("import os\n", "top level declarations"),
            ("fn main():\n    x = __import__('os')\n", "strings are not supported"),
            ("fn main():\n    x = 1; print(2)\n", "unsupported operator"),
            ("fn main():\n    x = `touch /tmp/unwanted`\n", "unsupported operator"),
            ("fn main():\n    x = 1.5\n", "decimal integer literals"),
            ("fn main():\n    x = 0xff\n", "decimal integer literals"),
            ("fn main():\n    x = lambda y: y\n", "expected end of line"),
        ]
        for source, message in cases:
            with self.subTest(source=source):
                self.assert_rejected(source, message)

    def test_incomplete_delimiters_and_missing_blocks_report_compile_errors(self):
        for source in ["fn main():\n    x = (1 + 2\n", "fn main():\nprint(1)\n", "fn main()\n    print(1)\n"]:
            with self.subTest(source=source):
                with self.assertRaises(CompileError):
                    parse(source)

    def test_empty_arrays_and_invalid_fixed_lengths_reject(self):
        self.assert_rejected("fn main():\n    x = []\n", "at least one element", 2)
        self.assert_rejected("fn f(x: int[0]) -> int:\n    return 0\n", "positive length", 1)
        self.assert_rejected("fn f(x: int[-1]) -> int:\n    return 0\n", "fixed array length", 1)
        self.assert_rejected("fn f(x: int[" + "1" * 5000 + "]) -> int:\n    return 0\n", "too large to read", 1)

    def test_return_annotation_required_except_for_main(self):
        self.assertEqual(parse("fn main():\n    return\n").functions[0].return_type, "unit")
        self.assert_rejected("fn add(a: int):\n    return a\n", "function results need", 1)
        self.assert_rejected("# just a comment\n", "needs at least one function")


if __name__ == "__main__":
    unittest.main()
