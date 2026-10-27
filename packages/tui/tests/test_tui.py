"""Run native widgets and test real POSIX terminals; Python is only the test driver."""

from pathlib import Path
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CC = shutil.which("cc")


@unittest.skipUnless(CC and os.name == "posix", "a POSIX terminal and C11 compiler are required")
class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="clack-tui-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        for name in ("tui.clack", "terminal.c"):
            shutil.copy2(ROOT / name, cls.directory / name)
        cls.count = 0
        cls.demo, cls.demo_source = cls.build((ROOT / "demo.clack").read_text())
        cls.menu, _ = cls.build('from tui import menu3\nfn main():\n    selected = menu3("Choose", "One", "Two", "Three")\n    print(selected)\n')

    @classmethod
    def build(cls, source):
        cls.count += 1
        file = cls.directory / f"program{cls.count}.clack"
        binary = cls.directory / f"program{cls.count}"
        file.write_text(source, encoding="utf-8")
        result = subprocess.run([sys.executable, "-m", "clack", "build", str(file), "-o", str(binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary, file

    def plain(self, binary, **environment):
        env = os.environ.copy()
        env.update(environment)
        result = subprocess.run([str(binary)], capture_output=True, timeout=5, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout.decode("utf-8", errors="strict")

    def terminal(self, binary, keys=b"", send_signal=None, columns=80, resize=None, **environment):
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, columns, 0, 0))
        env = os.environ.copy()
        env.update({"TERM": "xterm-256color", "LC_ALL": "C.UTF-8", **environment})
        process = subprocess.Popen([str(binary)], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        output = bytearray()
        deadline = time.monotonic() + 7
        try:
            while b"q quit" not in output and process.poll() is None:
                if time.monotonic() > deadline:
                    self.fail("terminal did not display its first frame")
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 65536))
            if resize:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, resize, 0, 0))
                border = b"+" + b"-" * (resize - 2) + b"+\r\n"
                while border not in output:
                    if time.monotonic() > deadline:
                        self.fail("terminal did not render its resized frame")
                    if select.select([master], [], [], 0.1)[0]:
                        output.extend(os.read(master, 65536))
            if send_signal:
                process.send_signal(send_signal)
            else:
                os.write(master, keys)
            while process.poll() is None:
                if time.monotonic() > deadline:
                    self.fail("terminal input did not complete")
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 65536))
            while select.select([master], [], [], 0.05)[0]:
                output.extend(os.read(master, 65536))
            self.assertEqual(process.returncode, 0, output.decode(errors="replace"))
            self.assertEqual(termios.tcgetattr(slave), original, "raw terminal attributes must be restored")
            self.assertIn(b"\x1b[?25h\x1b[?1049l", output, "cursor and original screen must be restored")
            return output.decode("utf-8", errors="strict")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            os.close(master)
            os.close(slave)

    def test_piped_dashboard_is_plain_and_does_not_wait_for_input(self):
        output = self.plain(self.demo)
        self.assertIn("Clack build dashboard", output)
        self.assertIn("C11 / native", output)
        self.assertIn("70%", output)
        self.assertNotIn("\x1b", output)
        self.assertTrue(output.endswith("0\n"))

    def test_keyboard_and_arrow_selection_restore_terminal(self):
        for keys in (b"j\r", b"\x1b[B\r"):
            with self.subTest(keys=keys):
                output = self.terminal(self.demo, keys)
                self.assertTrue(output.endswith("2\r\n"), output)

    def test_cancellation_restores_terminal(self):
        for keys in (b"q", b"\x1b"):
            with self.subTest(keys=keys):
                output = self.terminal(self.demo, keys)
                self.assertTrue(output.endswith("0\r\n"), output)

    def test_signal_cleanup_restores_terminal(self):
        for number in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=number):
                self.terminal(self.demo, send_signal=number)

    def test_no_color_and_ascii_modes_keep_keyboard_controls(self):
        output = self.terminal(self.demo, b"\r", NO_COLOR="1", CLACK_TUI_ASCII="1")
        self.assertNotIn("\x1b[7m", output)
        self.assertNotIn("\x1b[1;32m", output)
        self.assertIn("+---", output)
        self.assertTrue(output.endswith("1\r\n"))

    def test_dumb_terminal_never_enters_raw_mode(self):
        output = self.plain(self.demo, TERM="dumb")
        self.assertNotIn("\x1b", output)
        self.assertTrue(output.endswith("0\n"))

    def test_terminal_resize_renders_a_narrower_frame(self):
        output = self.terminal(self.demo, b"\r", resize=40, CLACK_TUI_ASCII="1")
        self.assertIn("+" + "-" * 38 + "+\r\n", output)
        self.assertTrue(output.endswith("1\r\n"))

    def test_control_text_is_sanitized_and_long_utf8_is_not_split(self):
        text = "é" * 200
        binary, _ = self.build('from tui import begin, label, run\nfn main():\n    begin("Unicode")\n'
                               '    label("safe\\u001b[31m\\nnext\\tvalue %s %n")\n'
                               f'    label("{text}")\n    selected = run()\n    print(selected)\n')
        output = self.plain(binary, LC_ALL="C.UTF-8")
        self.assertIn("safe [31m next value %s %n", output)
        self.assertIn("é", output)
        self.assertNotIn("\x1b", output)

    def test_progress_extremes_and_bounded_scene_storage(self):
        source = ('from tui import begin, label, progress, option, run\nfn main():\n    begin("Limits")\n'
                  '    progress("unknown", 9223372036854775807, 0)\n'
                  '    progress("negative", -9223372036854775808, 10)\n'
                  '    progress("full", 9223372036854775807, 1)\n'
                  '    option(0, "hidden-zero")\n    option(-1, "hidden-negative")\n')
        source += "".join(f'    label("entry-{i}")\n' for i in range(140))
        source += '    selected = run()\n    print(selected)\n'
        binary, _ = self.build(source)
        output = self.plain(binary)
        self.assertIn("100%", output)
        self.assertIn("0%", output)
        self.assertIn("entry-124", output)
        self.assertNotIn("entry-125", output)
        self.assertNotIn("hidden-zero", output)
        self.assertNotIn("hidden-negative", output)

    def test_one_call_menu_wraps_and_returns_the_selected_id(self):
        output = self.terminal(self.menu, b"k\r")
        self.assertTrue(output.endswith("3\r\n"), output)

    def test_native_provider_passes_strict_c11_and_undefined_behavior_checks(self):
        generated = self.directory / "strict.c"
        result = subprocess.run([sys.executable, "-m", "clack", "emit-c", str(self.demo_source), "-o", str(generated)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        binary = self.directory / "strict"
        result = subprocess.run([CC, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic-errors",
                                 "-fsanitize=undefined", "-fno-sanitize-recover=all", str(generated),
                                 str(ROOT / "terminal.c"), "-o", str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Clack build dashboard", self.plain(binary))


if __name__ == "__main__":
    unittest.main()
