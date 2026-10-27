"""Verify model contracts and compare native learning with Python integers."""

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
IMPORTS = "from ml import Linear4, zero4, score4, predict4, bounded_add, perceptron_step4, squared_distance4, nearest_centroid4\n"


def array(values):
    return "[" + ", ".join(map(str, values)) + "]"


def clip(value):
    return max(-1000000, min(1000000, value))


def reference_step(weights, bias, features, label, rate):
    correct = (sum(w * x for w, x in zip(weights, features)) + bias >= 0) == label
    if correct:
        return list(weights), bias
    change = rate if label else -rate
    return [clip(w + change * x) for w, x in zip(weights, features)], clip(bias + change)


class MLTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clack-ml-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        shutil.copyfile(ROOT / "ml.clack", self.directory / "ml.clack")

    def checked(self, body, declarations=""):
        path = self.directory / "main.clack"
        path.write_text(IMPORTS + declarations + "\nfn main():\n" + body, encoding="utf-8")
        program = load_program(path)
        return program, verify(program)

    def native(self, body):
        program, checked = self.checked(body)
        source, binary = self.directory / "program.c", self.directory / "program"
        source.write_text(emit_c(program, checked.local_types, checked.expr_types), encoding="utf-8")
        built = subprocess.run([CC, "-std=c11", "-pedantic-errors", "-O3", "-Wall", "-Wextra", "-Werror", "-pthread", "-fsanitize=undefined", str(source), "-o", str(binary)], text=True, capture_output=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_zero_scores_predictions_and_exact_distance_contracts_compose(self):
        self.checked("""    model = zero4()
    value = score4(model, [1000, -1000, 0, 1])
    answer = predict4(model, [1000, -1000, 0, 1])
    distance = squared_distance4([1, 2, 3, 4], [4, 3, 2, 1])
    chosen = nearest_centroid4([0, 0, 0, 0], [-1, 0, 0, 0], [1, 0, 0, 0])
    assert value == 0 and answer
    assert distance == 20 and chosen
""")

    def test_correct_prediction_preserves_every_model_field(self):
        self.checked("""    original = Linear4([1000000, -1000000, 7, -8], 1000000)
    learned = perceptron_step4(original, [0, 0, 0, 0], true, 1000)
    assert learned.weights[0] == original.weights[0]
    assert learned.weights[1] == original.weights[1]
    assert learned.weights[2] == original.weights[2]
    assert learned.weights[3] == original.weights[3]
    assert learned.bias == original.bias
""")

    def test_saturated_add_has_an_exact_public_contract(self):
        self.checked("""    low = bounded_add(-1000000, -1000000)
    high = bounded_add(1000000, 1000000)
    inside = bounded_add(-10, 17)
    assert low == -1000000 and high == 1000000 and inside == 7
""")

    def test_parameter_domains_and_array_shapes_are_enforced(self):
        invalid = [
            "    print(score4(Linear4([1000001, 0, 0, 0], 0), [0, 0, 0, 0]))\n",
            "    print(score4(Linear4([0, 0, 0, 0], -1000001), [0, 0, 0, 0]))\n",
            "    print(predict4(Linear4([0, 0, 0, 0], 0), [1001, 0, 0, 0]))\n",
            "    model = perceptron_step4(Linear4([0, 0, 0, 0], 0), [0, 0, 0, 0], false, 0)\n    print(model.bias)\n",
            "    model = perceptron_step4(Linear4([0, 0, 0, 0], 0), [0, 0, 0, 0], false, 1001)\n    print(model.bias)\n",
            "    print(squared_distance4([1000001, 0, 0, 0], [0, 0, 0, 0]))\n",
            "    print(nearest_centroid4([0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, -1000001]))\n",
            "    print(predict4(Linear4([0, 0, 0, 0], 0), [0, 0]))\n",
        ]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(CompileError):
                self.checked(body)

    @unittest.skipUnless(CC, "native comparisons need a C11 compiler")
    def test_native_model_updates_match_independent_reference(self):
        rng = random.Random(194)
        cases = [
            ([0, 0, 0, 0], 0, [0, 0, 0, 0], False, 1),
            ([1000000, -1000000, 0, 0], 1000000, [-1000, 1000, 1000, -1000], True, 1000),
            ([-1000000, 1000000, 0, 0], -1000000, [-1000, 1000, -1000, 1000], False, 1000),
            ([1000000, -1000000, -1000000, -1000000], -1000000, [1000] * 4, True, 1000),
            ([1000000] * 4, -1000000, [1000] * 4, False, 1000),
            ([-1000000] * 4, 1000000, [1000] * 4, True, 1000),
        ]
        cases += [([rng.randint(-1000000, 1000000) for _ in range(4)], rng.randint(-1000000, 1000000),
                   [rng.randint(-1000, 1000) for _ in range(4)], bool(rng.randrange(2)), rng.randint(1, 1000)) for _ in range(16)]
        lines, expected = [], []
        for index, (weights, bias, features, label, rate) in enumerate(cases):
            score = sum(w * x for w, x in zip(weights, features)) + bias
            learned_weights, learned_bias = reference_step(weights, bias, features, label, rate)
            lines += [f"    original{index} = Linear4({array(weights)}, {bias})",
                      f"    print(score4(original{index}, {array(features)}))",
                      f"    print(predict4(original{index}, {array(features)}))",
                      f"    learned{index} = perceptron_step4(original{index}, {array(features)}, {str(label).lower()}, {rate})"]
            expected += [str(score), str(score >= 0).lower()]
            for field in range(4):
                lines.append(f"    print(learned{index}.weights[{field}])")
            lines += [f"    print(learned{index}.bias)", f"    print(original{index}.bias)"]
            expected += list(map(str, learned_weights)) + [str(learned_bias), str(bias)]
        self.assertEqual(self.native("\n".join(lines) + "\n"), expected)

    @unittest.skipUnless(CC, "native comparisons need a C11 compiler")
    def test_native_distances_and_centroid_ties_match_reference(self):
        rng = random.Random(513)
        cases = [([0] * 4, [-1] * 4, [1] * 4),
                 ([-1000000] * 4, [1000000] * 4, [-1000000] * 4)]
        cases += [([rng.randint(-1000000, 1000000) for _ in range(4)],
                   [rng.randint(-1000000, 1000000) for _ in range(4)],
                   [rng.randint(-1000000, 1000000) for _ in range(4)]) for _ in range(12)]
        lines, expected = [], []
        for features, negative, positive in cases:
            low = sum((a - b) ** 2 for a, b in zip(features, negative))
            high = sum((a - b) ** 2 for a, b in zip(features, positive))
            lines += [f"    print(squared_distance4({array(features)}, {array(negative)}))",
                      f"    print(nearest_centroid4({array(features)}, {array(negative)}, {array(positive)}))"]
            expected += [str(low), str(high <= low).lower()]
        self.assertEqual(self.native("\n".join(lines) + "\n"), expected)

    @unittest.skipUnless(CC, "native training needs a C11 compiler")
    def test_training_demo_learns_or_classification(self):
        body = (ROOT / "demo.clack").read_text().split("fn main():\n", 1)[1]
        self.assertEqual(self.native(body), ["false", "true", "true", "true", "true"])

    @unittest.skipUnless(CC, "native training needs a C11 compiler")
    def test_nonseparable_xor_training_stays_bounded_without_promising_accuracy(self):
        data = [([0, 0, 0, 0], False), ([0, 1, 0, 0], True),
                ([1, 0, 0, 0], True), ([1, 1, 0, 0], False)]
        weights, bias = [0] * 4, 0
        for _ in range(16):
            for features, label in data:
                weights, bias = reference_step(weights, bias, features, label, 1)
        expected = [str(sum(w * x for w, x in zip(weights, features)) + bias >= 0).lower()
                    for features, _ in data]
        self.assertNotEqual(expected, [str(label).lower() for _, label in data])
        body = """    model = zero4()
    for epoch in range(16):
        invariant -1000000 <= model.weights[0] <= 1000000
        invariant -1000000 <= model.weights[1] <= 1000000
        invariant -1000000 <= model.weights[2] <= 1000000
        invariant -1000000 <= model.weights[3] <= 1000000
        invariant -1000000 <= model.bias <= 1000000
"""
        for features, label in data:
            body += f"        model = perceptron_step4(model, {array(features)}, {str(label).lower()}, 1)\n"
        for features, _ in data:
            body += f"    print(predict4(model, {array(features)}))\n"
        self.assertEqual(self.native(body), expected)


if __name__ == "__main__":
    unittest.main()
