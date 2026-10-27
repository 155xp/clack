"""Byte-model properties for mixed Unicode and escape-looking source text."""

import json
import random
import unittest

from clack.frontend import parse
from clack.verifier import verify


class TextEncodingTests(unittest.TestCase):
    def test_unicode_bytes_cannot_alias_their_ascii_escape_spellings(self):
        cases = ["", "\\", '"', "é😀", chr(0x30000), chr(0x10FFFF),
                 r"\u{5c}u{c3}", r"\u{5c}\u{0}", r"\u{}", r"\u{110000}"]
        rng = random.Random(619)
        for _ in range(64):
            points = [rng.randrange(1, 0x110000) for _ in range(rng.randrange(1, 12))]
            value = "".join(chr(point) for point in points if not 0xD800 <= point <= 0xDFFF)
            cases.append(value + r"\u{c3}\u{a9}")
        source = "fn main():\n"
        for value in cases:
            encoded = value.encode("utf-8")
            spelling = "".join(r"\u{%x}" % byte for byte in encoded)
            left, right = json.dumps(value), json.dumps(spelling)
            operator = "==" if value == spelling else "!="
            source += f"    assert len({left}) == {len(encoded)}\n"
            source += f"    assert {left} {operator} {right}\n"
        verify(parse(source))


if __name__ == "__main__":
    unittest.main()
