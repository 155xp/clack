"""Content equality and UTF-8 byte lengths agree with strict native C."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from clack.codegen import emit_c
from clack.frontend import parse
from clack.verifier import verify


CC = shutil.which("cc")


@unittest.skipUnless(CC, "native text tests need a C11 compiler")
class TextNativeTests(unittest.TestCase):
    def native(self, source, instrument=False):
        program = parse(textwrap.dedent(source).lstrip("\n"))
        checked = verify(program)
        generated = emit_c(program, checked.local_types, checked.expr_types)
        if instrument:
            generated = generated.replace("#include <string.h>\n", "#include <string.h>\n#include <assert.h>\nstatic int test_calls;\n")
            marker = "static const char * clack_fn_source(void) {"
            self.assertIn(marker, generated)
            generated = generated.replace(marker, marker + "\n    ++test_calls;")
            generated = generated.replace("    clack_fn_main();", "    clack_fn_main();\n    assert(test_calls == 4);")
        with tempfile.TemporaryDirectory(prefix="clack-text-native-") as directory:
            root = Path(directory)
            path, binary = root / "program.c", root / "program"
            path.write_text(generated, encoding="utf-8")
            compiled = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-Wall", "-Wextra", "-Werror", "-O3", "-pthread", "-fsanitize=undefined", str(path), "-o", str(binary)], text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            return executed.stdout

    def test_ascii_equality_uses_contents_and_handles_empty_and_prefix_strings(self):
        output = self.native('''
            fn main():
                print("hello" == "hello")
                print("hello" != "world")
                print("" == "")
                print("hello" == "hell")
                print("" != "a")
                print(len(""))
        ''')
        self.assertEqual(output, "true\ntrue\ntrue\nfalse\ntrue\n0\n")

    def test_unicode_byte_lengths_and_equality_cover_the_full_unicode_range(self):
        values = ["", "ASCII", "é", "e\u0301", "😀", "\U00030000", "\U0010ffff", "literal \\u{3}", 'quote " slash \\ newline\n']
        source = "fn main():\n"
        expected = []
        for value in values:
            raw = json.dumps(value, ensure_ascii=False)
            escaped = json.dumps(value, ensure_ascii=True)
            source += f"    print(len({raw}))\n    print({raw} == {escaped})\n"
            expected.extend([str(len(value.encode("utf-8"))), "true"])
        self.assertEqual(self.native(source), "\n".join(expected) + "\n")

    def test_equality_does_not_normalize_or_case_fold(self):
        output = self.native('''
            fn main():
                print("é" == "e\\u0301")
                print("Clack" == "clack")
                print("é" != "e\\u0301")
        ''')
        self.assertEqual(output, "false\nfalse\ntrue\n")

    def test_literal_backslash_u_braces_cannot_alias_unicode_content(self):
        source = "fn main():\n"
        for actual, escaped in (("é", "\\u{c3}\\u{a9}"), ("\U00030000", "\\u{30000}")):
            source += f"    print({json.dumps(actual, ensure_ascii=False)} == {json.dumps(escaped)})\n"
        self.assertEqual(self.native(source), "false\nfalse\n")

    def test_text_comparisons_and_length_accept_function_results_and_record_fields(self):
        output = self.native('''
            type Label:
                text_value: text
            fn identity(value: text) -> text:
                ensures result == value
                ensures len(result) == len(value)
                return value
            fn choose(flag: bool) -> text:
                ensures result == "yes" or result == "no"
                if flag:
                    return "yes"
                return "no"
            fn main():
                label = Label(identity("café"))
                print(label.text_value == "café")
                print(len(label.text_value))
                print(choose(true) == "yes")
                print(choose(false) != "yes")
        ''')
        self.assertEqual(output, "true\n5\ntrue\ntrue\n")

    def test_text_values_remain_safe_across_parallel_worker_returns(self):
        output = self.native('''
            fn identity(value: text) -> text:
                ensures result == value
                return value
            fn main():
                parallel:
                    left = identity("é")
                    right = identity("😀")
                print(left == "é")
                print(right == "😀")
                print(len(left))
                print(len(right))
        ''')
        self.assertEqual(output, "true\ntrue\n2\n4\n")

    def test_each_operand_and_length_argument_is_evaluated_once(self):
        output = self.native('''
            fn source() -> text:
                ensures result == "once"
                return "once"
            fn main():
                print(len(source()))
                print(source() == "once")
                print(source() == source())
        ''', instrument=True)
        self.assertEqual(output, "4\ntrue\ntrue\n")

    def test_array_length_keeps_its_existing_static_semantics(self):
        output = self.native('''
            fn main():
                values = [1, 2, 3]
                print(len(values))
                print(len("abc"))
                print("abc" == "abc" and len(values) == len("abc"))
                print(values[0])
        ''')
        self.assertEqual(output, "3\n3\ntrue\n1\n")


if __name__ == "__main__":
    unittest.main()
