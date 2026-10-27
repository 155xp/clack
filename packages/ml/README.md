# Small ML models in Clack

This optional source package provides a four-feature integer perceptron with online training, exact linear scores, squared distances, and two-centroid classification. It compiles to native C through the ordinary Clack compiler. It adds no compiler code or runtime dependency.

Run the complete training example from the Clack repository:

```sh
.venv/bin/python -m clack check packages/ml/demo.clack
.venv/bin/python -m clack run packages/ml/demo.clack
```

The example trains an OR classifier for eight deterministic passes over four examples, then prints:

```text
false
true
true
true
true
```

The first four lines classify `[0, 0]`, `[0, 1]`, `[1, 0]`, and `[1, 1]`, with two unused features set to zero. The final line demonstrates nearest-centroid classification. The successful training result is tested for this dataset; it is not a general convergence guarantee.

## Use a model

Place an application beside the repository's `packages` directory:

```clack
from packages.ml.ml import Linear4, score4, predict4

fn main():
    model = Linear4([2, -1, 0, 0], -1)
    features = [3, 1, 0, 0]
    print(score4(model, features))
    print(predict4(model, features))
```

This prints `4` and `true`. A standalone application can instead copy this directory to `ml/` and import `from ml.ml import ...`. Imports resolve relative to the file containing them. The supplied `demo.clack`, which lives inside this directory, imports the neighboring `ml.clack` as `from ml import ...`.

All numbers are plain integers. There is no hidden decimal scale, floating-point rounding, tensor allocation, or Python execution in the resulting program. Choose consistent units when encoding features, weights, and bias.

## API

Source: [ml.clack](ml.clack). Model fields are immutable values; training returns a new model.

| Name | Signature | Meaning |
| --- | --- | --- |
| `Linear4` | `(weights: int[4], bias: int)` | Four weights and one bias |
| `zero4` | `() -> Linear4` | Zero weights and bias |
| `score4` | `(model: Linear4, features: int[4]) -> int` | `sum(weight[i] * feature[i]) + bias` |
| `predict4` | `(model: Linear4, features: int[4]) -> bool` | True exactly when the score is nonnegative |
| `perceptron_step4` | `(model: Linear4, features: int[4], label: bool, rate: int) -> Linear4` | One bounded online training update |
| `bounded_add` | `(value: int, delta: int) -> int` | Addition clipped to the weight/bias domain |
| `squared_distance4` | `(left: int[4], right: int[4]) -> int` | Sum of four squared coordinate differences |
| `nearest_centroid4` | `(features: int[4], negative: int[4], positive: int[4]) -> bool` | Whether the positive centroid is at least as close as the negative one |

For `score4`, `predict4`, and `perceptron_step4`, every weight and the bias must be between `-1000000` and `1000000`, inclusive. Each feature must be between `-1000` and `1000`. Scores stay within `-4001000000` through `4001000000`. Training rates are integer values from `1` through `1000`.

For distance and centroid functions, each coordinate may range from `-1000000` through `1000000`. Squared distances lie between zero and `16000000000000`. A centroid tie selects `true`, the positive class. `bounded_add` accepts both operands from `-1000000` through `1000000`.

## Train incrementally

Each step first computes the current prediction. If it matches the supplied label, every model field remains unchanged. Otherwise, let `d` equal `rate` for a true label and `-rate` for a false label:

```text
new_weight[i] = clip(old_weight[i] + d * feature[i])
new_bias      = clip(old_bias + d)
clip(v)      = max(-1000000, min(1000000, v))
```

Clipping keeps subsequent updates inside the supported model domain. It also changes the unconstrained perceptron algorithm; a large rate can saturate weights, and arbitrary data need not be linearly separable. The package does not promise convergence or accuracy on an unknown dataset.

The [training demo](demo.clack) initializes `zero4()`, presents all four labeled OR examples repeatedly, and uses loop invariants to carry the model's bounds between passes. A model can be used by ordinary pure workers in `parallel:` blocks; independent models and returned values retain Clack's normal copy semantics.

## What is proved and tested

The compiler verifies every loaded source function. Contracts specify exact scores, exact threshold decisions, exact squared distances, exact nearest-centroid decisions, and exact saturating scalar addition. Training proves that all returned model fields remain in range and that an already-correct prediction leaves the model unchanged. It proves the update arithmetic safe. The training function's postconditions do not encode every clipped update formula, and they do not establish convergence or statistical accuracy.

[Tests](tests/test_ml.py) compare native training updates against independent Python integer references, including saturation, signed boundaries, seeded samples, and centroid ties. The OR training example runs as a native executable. Native tests use strict C11 and undefined-behavior sanitization.

```sh
.venv/bin/python -m unittest discover -s packages/ml/tests -v
```

## Notes for coding agents

- Read the function preconditions in `ml.clack` before generating a call. Record construction alone does not prove that its fields satisfy the numeric domains.
- Use four integer features; pad unused coordinates with zero. Do not invent a generic `Linear[N]` type, floating-point literals, automatic differentiation, tensor APIs, or dataset loaders.
- Preserve the documented nonnegative-score and positive-centroid tie rules in reference implementations.
- Carry all five model bounds as loop invariants when repeatedly assigning trained models, as shown in `demo.clack`.
- Keep real-valued preprocessing outside this integer package or explicitly choose a documented encoding. Increasing a bound requires re-verifying arithmetic and updating the contract and tests together.

This is a small foundation for integer classification and educational models. Larger shapes, floating-point numerical algorithms, GPU execution, automatic differentiation, and training/data pipelines need separate implementations.

MIT licensed; see [LICENSE](LICENSE).
