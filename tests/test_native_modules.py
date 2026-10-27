"""Text values and the explicit, main-only boundary to trusted native C."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from clack.frontend import CompileError, parse
from clack.modules import load_program
from clack.verifier import verify


ROOT = Path(__file__).resolve().parents[1]
CC = shutil.which("cc")
BINDINGS = '''native "terminal.c"
extern fn answer(label: text, value: int) -> int = "clack_test_answer"
extern fn say(label: text) -> unit = "clack_test_say"
extern fn flip(value: bool) -> bool = "clack_test_flip"
'''
PROVIDER = '''#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
int64_t clack_test_answer(const char *label, int64_t value) {
    (void)label; return value;
}
void clack_test_say(const char *label) { puts(label); }
bool clack_test_flip(bool value) { return !value; }
'''


class NativeModuleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-native-module-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.write("bindings.clack", BINDINGS)
        self.native_source = self.write("terminal.c", PROVIDER)

    def write(self, name, source):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        return path

    def checked(self, source):
        path = self.write("main.clack", source)
        program = load_program(path)
        return program, verify(program)

    def rejected(self, source):
        with self.assertRaises(CompileError):
            self.checked(source)

    def cli(self, command, path, *arguments):
        return subprocess.run([sys.executable, "-m", "clack", command, str(path), *map(str, arguments)],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)

    def test_text_literals_and_pure_passthrough_records_are_typed(self):
        self.checked('''
            type Label:
                value: text
            fn identity(value: text) -> text:
                return value
            fn wrap(value: text) -> Label:
                return Label(value)
            fn main():
                original = identity("hello")
                copied = wrap(original)
                print(copied.value)
        ''')

    def test_text_rejects_unsupported_operations(self):
        for expression in ('"a" + "b"', '"a" < "b"', '["a", "b"]', '"hello"[0]'):
            with self.subTest(expression=expression):
                self.rejected(f"fn main():\n    value = {expression}\n    print(value)\n")

    def test_literals_accept_json_escapes_and_reject_nul_and_other_styles(self):
        text = 'line\nquote" backslash\\ café ▣'
        verify(parse("fn main():\n    print(" + json.dumps(text, ensure_ascii=False) + ")\n"))
        for literal in ('"bad\\u0000value"', '"\\ud800"', "'single'", '"""triple"""', 'f"interpolated"', '"\\x41"'):
            with self.subTest(literal=literal):
                with self.assertRaises(CompileError):
                    parse(f"fn main():\n    print({literal})\n")

    def test_native_file_is_resolved_relative_to_its_module(self):
        self.write("nested/terminal.c", PROVIDER)
        self.write("nested/bindings.clack", BINDINGS)
        program, _ = self.checked('''
            from nested.bindings import answer
            fn main():
                value = answer("from nested module", 7)
                print(value)
        ''')
        self.assertEqual(program.native_sources, [str(self.directory / "nested/terminal.c")])

    def test_transitive_native_inputs_are_deduplicated(self):
        self.write("left.clack", "from bindings import answer\n")
        self.write("right.clack", "from bindings import flip\n")
        program, _ = self.checked('''
            from left import answer
            from right import flip
            fn main():
                value = answer("shared provider", 7)
                other = flip(false)
                print(value)
                print(other)
        ''')
        self.assertEqual(program.native_sources, [str(self.native_source)])

    def test_missing_absolute_parent_and_non_c_sources_are_rejected(self):
        self.write("terminal.py", "# not native C\n")
        for name in ('missing.c', '../terminal.c', str(self.native_source), 'terminal.py'):
            with self.subTest(name=name):
                source = f"native {json.dumps(name)}\nfn main():\n    print(0)\n"
                self.rejected(source)
        self.write("nested/escape.clack", BINDINGS.replace('"terminal.c"', '"../terminal.c"'))
        self.rejected('from nested.escape import answer\nfn main():\n    value = answer("escape", 7)\n    print(value)\n')

    def test_native_calls_are_not_allowed_in_verified_helpers(self):
        self.rejected('''
            from bindings import answer
            fn helper() -> int:
                return answer("effect", 7)
            fn main():
                print(helper())
        ''')

    def test_native_calls_cannot_hide_in_expressions_or_conditions(self):
        for body in ('print(answer("effect", 7))', 'value = answer("effect", 7) + 1',
                     'if answer("effect", 7) == 7:\n        print(1)',
                     'assert answer("effect", 7) == 7'):
            with self.subTest(body=body):
                self.rejected('from bindings import answer\nfn main():\n    ' + body + '\n')

    def test_native_arguments_cannot_have_nested_native_effects(self):
        self.rejected('''
            from bindings import answer
            fn main():
                value = answer("outer", answer("inner", 7))
                print(value)
        ''')

    def test_native_calls_cannot_be_parallel_jobs(self):
        self.rejected('''
            from bindings import answer
            fn main():
                parallel:
                    value = answer("effect", 7)
                print(value)
        ''')

    def test_foreign_results_have_no_assumed_functional_contract(self):
        self.rejected('''
            from bindings import answer
            fn main():
                value = answer("C happens to return 7", 7)
                assert value == 7
        ''')
        self.checked('''
            from bindings import answer
            fn main():
                value = answer("guarded result", 7)
                if value == 7:
                    assert value == 7
                print(value)
        ''')

    def test_foreign_result_range_does_not_allow_overflow(self):
        self.rejected('''
            from bindings import answer
            fn main():
                value = answer("unknown int", 7)
                print(value + 1)
        ''')

    def test_foreign_abi_rejects_composites_and_text_returns(self):
        declarations = [
            'extern fn invalid(values: int[2]) -> int = "clack_test_invalid"',
            'extern fn invalid() -> text = "clack_test_invalid"',
            'extern fn invalid() -> int[2] = "clack_test_invalid"',
            'extern fn invalid() -> int = "not-a-C-identifier"',
            'extern fn invalid() -> int = "bad\\u0000symbol"',
            'extern fn invalid() -> int = "clack_for_1_start"',
        ]
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                self.rejected('native "terminal.c"\n' + declaration + '\nfn main():\n    print(0)\n')

    def test_main_cannot_be_an_external_function(self):
        self.rejected('native "terminal.c"\nextern fn main() -> unit = "clack_test_main"\n')

    def test_conflicting_native_signatures_are_rejected(self):
        self.rejected('''
            native "terminal.c"
            extern fn first(value: int) -> int = "clack_test_shared"
            extern fn second(value: bool) -> int = "clack_test_shared"
            fn main():
                print(0)
        ''')

    @unittest.skipUnless(CC, "native execution needs a C11 compiler")
    def test_native_utf8_text_boolean_integer_and_unit_calls_execute(self):
        source = self.write("main.clack", '''
            from bindings import answer, say, flip
            type Label:
                value: text
            fn identity(value: text) -> text:
                return value
            fn main():
                label = Label(identity("café ▣"))
                say(label.value)
                value = answer("number", -9223372036854775808)
                flag = flip(false)
                print(value)
                print(flag)
                print("quote: \\" backslash: \\\\ end")
        ''')
        result = self.cli("run", source, "--cc", CC)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'café ▣\n-9223372036854775808\ntrue\nquote: " backslash: \\ end\n')

    def test_cli_discloses_native_boundary_and_preserves_native_source(self):
        source = self.write("main.clack", '''
            from bindings import answer
            fn main():
                value = answer("source", 7)
                print(value)
        ''')
        result = self.cli("check", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("outside verification", result.stdout.lower())
        original = self.native_source.read_bytes()
        for command in ("build", "emit-c"):
            with self.subTest(command=command):
                result = self.cli(command, source, "-o", self.native_source)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(self.native_source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
