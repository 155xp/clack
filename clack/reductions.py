"""Typed array reductions supplied by the compiler through ``std.array``.

These operators accept every supported nonempty fixed length. Their arithmetic
and bounds are modeled by the verifier; the native backend emits ordinary loops.
Internal spellings are reserved, so source programs access them through imports.
"""

from dataclasses import dataclass


PREFIX = "_clack_reduce_"


@dataclass(frozen=True)
class Reduction:
    name: str
    element: str
    result: str


REDUCTIONS = {
    PREFIX + name: Reduction(name, element, result)
    for name, element, result in (
        ("sum", "int", "int"),
        ("all", "bool", "bool"),
        ("any", "bool", "bool"),
        ("count", "bool", "int"),
    )
}
EXPORTS = {operation.name: name for name, operation in REDUCTIONS.items()}
