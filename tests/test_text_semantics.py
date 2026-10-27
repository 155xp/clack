"""UTF-8 byte lengths, exact text equality, and modular text contracts."""

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

import z3

from clack.frontend import CompileError, parse
from clack.typecheck import check
from clack.verifier import verify


def literal(value):
    return json.dumps(value, ensure_ascii=True)


class TextSemanticsTests(unittest.TestCase):
    def program(self, source):
        return parse(textwrap.dedent(source).lstrip("\n"))

    def checked(self, source, **options):
        return verify(self.program(source), **options)

    def test_lengths_count_utf8_bytes_for_latin1_controls_and_supplementary_unicode(self):
        # Include every non-NUL Latin-1 character, plus codepoints above Z3's
        # direct string alphabet and multicodepoint text presentations.
        cases = ["", *map(chr, range(1, 256)), chr(0x2FFFF), chr(0x30000), chr(0x10FFFF), "e\u0301", "👩\u200d💻"]
        source = "fn main():\n"
        for value in cases:
            source += f"    assert len({literal(value)}) == {len(value.encode('utf-8'))}\n"
        verify(parse(source))

    def test_unicode_cannot_alias_literal_backslash_escape_sequences(self):
        pairs = [
            ("é", "\\u{e9}"),
            ("é", "\\u{c3}\\u{a9}"),
            (chr(0x30000), "\\u{30000}"),
            (chr(0x10FFFF), "\\u{10ffff}"),
            ("\\", "\\u{5c}"),
            ("\\u{c3}", "\\u{5c}u{c3}"),
            ("\n", "\\n"),
        ]
        source = "fn main():\n"
        for left, right in pairs:
            source += f"    assert {literal(left)} != {literal(right)}\n"
        verify(parse(source))

    def test_equality_is_exact_and_does_not_normalize_unicode(self):
        self.checked('''
            fn main():
                assert "" == ""
                assert "Clack" == "Clack"
                assert "Clack" != "clack"
                assert "é" != "e\u0301"
                assert "😀" == "\U0001f600"
        ''')

    def test_text_functions_can_state_exact_content_and_byte_length_contracts(self):
        self.checked('''
            fn identity(value: text) -> text:
                ensures result == value
                ensures len(result) == len(value)
                return value
            fn byte_size(value: text) -> int:
                ensures result == len(value)
                return len(value)
            fn main():
                copied = identity("é😀")
                assert copied == "é😀"
                size = byte_size(copied)
                assert size == 6
        ''')

    def test_arbitrary_text_lengths_are_signed_integer_values(self):
        self.checked('''
            fn bounded(value: text) -> int:
                ensures 0 <= result <= 9223372036854775807
                return len(value)
            fn guarded(value: text) -> int:
                requires len(value) < 9223372036854775807
                ensures result == len(value) + 1
                return len(value) + 1
            fn main():
                print(bounded("abc"))
                print(guarded("é"))
        ''')
        with self.assertRaisesRegex(CompileError, "signed 64-bit range"):
            self.checked('''
                fn unguarded(value: text) -> int:
                    return len(value) + 9223372036854775807
                fn main():
                    print(unguarded("abc"))
            ''')

    def test_text_inside_records_retains_modular_equality_and_length_facts(self):
        self.checked('''
            type Label:
                name: text
            fn copy(value: Label) -> Label:
                ensures result.name == value.name
                ensures len(result.name) == len(value.name)
                return value
            fn main():
                value = copy(Label("é"))
                assert value.name == "é" and len(value.name) == 2
        ''')

    def test_returned_and_loop_havoc_texts_keep_length_bounds(self):
        self.checked('''
            fn choose(flag: bool) -> text:
                if flag:
                    return "a"
                return "bb"
            fn main():
                value = choose(true)
                assert 0 <= len(value) <= 9223372036854775807
                for i in range(3):
                    value = "😀"
                assert 0 <= len(value) <= 9223372036854775807
        ''')

    def test_false_text_postconditions_are_rejected(self):
        with self.assertRaisesRegex(CompileError, "postcondition"):
            self.checked('''
                fn wrong(value: text) -> text:
                    ensures result == value
                    return "fixed"
                fn main():
                    value = wrong("other")
                    print(value)
            ''')

    def test_text_operators_reject_mismatched_types_and_unsupported_operations(self):
        for expression, message in (
            ('"a" == 1', "equality compares matching"),
            ('true != "true"', "equality compares matching"),
            ('len()', "len needs exactly one"),
            ('len(true)', "len needs exactly one"),
            ('len(7)', "len needs exactly one"),
            ('len("a", "b")', "len needs exactly one"),
            ('"a" < "b"', "needs int"),
            ('"a" + "b"', "needs int"),
            ('"abc"[0]', "expected a fixed array"),
        ):
            with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, message):
                check(parse("fn main():\n    value = " + expression + "\n"))

    def test_unicode_success_and_failure_queries_replay_in_fresh_solvers(self):
        lookalike = literal("\\u{c3}\\u{a9}")
        good = f'fn main():\n    assert len("é😀") == 6\n    assert "é" != {lookalike}\n'
        bad = f'fn main():\n    assert "é" == {lookalike}\n'
        with tempfile.TemporaryDirectory(prefix="clack-text-replay-") as directory:
            for name, source, wanted in (("good", good, z3.unsat), ("bad", bad, z3.sat)):
                path = Path(directory) / name
                if wanted == z3.sat:
                    with self.assertRaisesRegex(CompileError, "assertion"):
                        verify(parse(source), proof_dir=path)
                else:
                    verify(parse(source), proof_dir=path)
                rows = json.loads((path / "obligations.json").read_text())
                for row in rows:
                    solver = z3.Solver()
                    solver.from_file(str(path / row["query"]))
                    self.assertEqual(solver.check(), wanted, row)


if __name__ == "__main__":
    unittest.main()
