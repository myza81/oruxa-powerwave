"""Unit vocabulary shared by the canonical registry, the catalog validator and the matcher.

Units are plain strings. A *canonical* unit is what the canonical model carries (ohm, A, V,
s, deg, or dimensionless ``""``). A *source* unit is what the relay's setting is stated in; the
catalog declares it and, when it differs, the matcher converts with an entry from `CONVERSIONS`.
Nothing is ever converted that the table does not list (no "guess the scale"), and a printed
unit text is only compared, never trusted to select a conversion.
"""

from __future__ import annotations

import math

#: Every unit the catalog may name. ``""`` is dimensionless (a factor, a flag, a label).
UNITS: frozenset[str] = frozenset({"", "ohm", "mohm", "s", "ms", "A", "kA", "V", "kV", "deg", "rad"})

#: Printed unit text (case-folded) accepted for a unit.
_PRINTED: dict[str, frozenset[str]] = {
    "": frozenset({""}),
    "ohm": frozenset({"ohm", "ohms", "ω", "Ω".casefold()}),
    "mohm": frozenset({"mohm", "mω"}),
    "s": frozenset({"s", "sec"}),
    "ms": frozenset({"ms"}),
    "A": frozenset({"a", "amp"}),
    "kA": frozenset({"ka"}),
    "V": frozenset({"v"}),
    "kV": frozenset({"kv"}),
    "deg": frozenset({"deg", "°"}),
    "rad": frozenset({"rad"}),
}

#: (from, to) -> multiplicative factor. Exact, documented relationships only.
CONVERSIONS: dict[tuple[str, str], float] = {
    ("kV", "V"): 1000.0,
    ("V", "kV"): 0.001,
    ("kA", "A"): 1000.0,
    ("A", "kA"): 0.001,
    ("ms", "s"): 0.001,
    ("s", "ms"): 1000.0,
    ("mohm", "ohm"): 0.001,
    ("ohm", "mohm"): 1000.0,
    ("deg", "rad"): math.pi / 180.0,
    ("rad", "deg"): 180.0 / math.pi,
}


def is_known_unit(unit: str) -> bool:
    return unit in UNITS


def printed_aliases(unit: str) -> frozenset[str]:
    """The printed texts (case-folded) that mean ``unit``."""
    return _PRINTED.get(unit, frozenset())


def printed_matches(unit: str, printed: str) -> bool:
    return printed.strip().rstrip(".").casefold() in printed_aliases(unit)


def conversion_factor(source: str, target: str) -> float | None:
    """The factor taking a ``source``-unit value to ``target`` (1.0 when equal), or ``None``
    when the table has no such conversion."""
    if source == target:
        return 1.0
    return CONVERSIONS.get((source, target))
