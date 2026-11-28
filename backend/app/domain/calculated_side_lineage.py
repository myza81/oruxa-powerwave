"""PU-MIG S3: the measurement side of a calculated Voltage result, from the leaves it is calculated from.

A calculated channel carries no side of its own (calculated channels are not Measurement Group members). Its samples are an engineering-unit
arithmetic of recorded leaves (arithmetic is always done in engineering units, before any per-unit normalisation), so the side of the result is
the side of its leaves -- and only when every leaf says the same thing:

    every leaf strict-usable on ONE side        -> that side (conversion of a base onto it is the S1 resolver's job)
    any leaf not strict-usable                  -> not strict: the historical Unverified result is kept (decision D-1, option R+)
    strict leaves on DIFFERENT sides            -> refused: `voltage_mixed_side` (the existing vocabulary of the recorded consumers)

`multiply_constant` keeps the side (the constant is the engineer's scale), as do reverse polarity, absolute value and RMS, so a unary chain
needs no operation-specific rule: the leaf set is the transitive set of source channels. A multi-input result (`line_to_line_voltage` reads
two phase leaves) uses the same rule. This module chooses no base, reads no ratio, does no arithmetic and holds no registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.domain.side_denominator import (
    PROBLEM_CALCULATED,
    PROBLEM_GROUP_CONFLICT,
    PROBLEM_INFERRED,
    PROBLEM_UNRESOLVED,
    SIDE_PRIMARY,
    SIDE_SECONDARY,
    SampleSide,
)

#: The existing production code for "the consumed Voltage channels are on different measurement sides"
#: (`app.domain.side_conversion.REASON_VOLTAGE_MIXED_SIDE`); reused, not invented (decision N-2).
REASON_LEAF_SIDES_DIFFER = "voltage_mixed_side"

#: Which problem a non-strict result reports when several leaves have one: the first of these present (deterministic).
_PROBLEM_ORDER = (PROBLEM_CALCULATED, PROBLEM_UNRESOLVED, PROBLEM_INFERRED, PROBLEM_GROUP_CONFLICT)


@dataclass(frozen=True, slots=True)
class CalculatedSide:
    """`sample` is the lineage side (strict or not). `refusal` is set, and `sample` is None, when strict leaves disagree."""

    sample: SampleSide | None
    refusal: str | None = None


def resolve_calculated_side(leaves: Sequence[SampleSide]) -> CalculatedSide:
    """The side of a calculated result from the sides of its transitive source leaves. Pure; never raises for a well-formed leaf."""
    if not leaves:
        return CalculatedSide(SampleSide(side=None, problem=PROBLEM_UNRESOLVED, authority=None))
    problems = {leaf.problem for leaf in leaves if leaf.problem is not None}
    if problems:
        problem = next(p for p in _PROBLEM_ORDER if p in problems)
        return CalculatedSide(SampleSide(side=None, problem=problem, authority=None))
    sides = {leaf.side for leaf in leaves}
    if sides - {SIDE_PRIMARY, SIDE_SECONDARY}:
        return CalculatedSide(SampleSide(side=None, problem=PROBLEM_UNRESOLVED, authority=None))
    if len(sides) > 1:
        return CalculatedSide(None, REASON_LEAF_SIDES_DIFFER)
    authorities = {leaf.authority for leaf in leaves}
    return CalculatedSide(SampleSide(
        side=next(iter(sides)), problem=None, authority=next(iter(authorities)) if len(authorities) == 1 else "mixed",
    ))
