"""Typed array operators supplied by the compiler through ``std.array``.

These operators accept every supported nonempty fixed length. Their arithmetic
and bounds are modeled by the verifier; the native backend emits ordinary loops.
Internal spellings are reserved, so source programs access them through imports.
"""

from dataclasses import dataclass


PREFIX = "_clack_reduce_"


@dataclass(frozen=True)
class ArrayOperation:
    name: str
    element: str | None
    result: str | None


OPERATIONS = {
    PREFIX + name: ArrayOperation(name, element, result)
    for name, element, result in (
        ("sum", "int", "int"),
        ("all", "bool", "bool"),
        ("any", "bool", "bool"),
        ("count", "bool", "int"),
        ("minimum", "int", "int"),
        ("maximum", "int", "int"),
        ("fill", None, None),
    )
}
EXPORTS = {operation.name: name for name, operation in OPERATIONS.items()}
