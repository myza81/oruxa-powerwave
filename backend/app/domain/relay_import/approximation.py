"""Engine approximations (DEC-198): the generic, relay-neutral representation of a known engine
limitation that may be drawn approximately instead of exactly.

An approximation is allowed only when the relay's own behaviour is established (by a verified
catalog mapping or documented derivation) and the current engine cannot represent it exactly.
It never stands in for a missing or unverified value. A rule is identified by ``rule_id`` and
``rule_version`` and is classified by what it does to the drawn region:

* ``conservative`` -- the drawn / modelled region lies wholly within the verified relay behaviour;
* ``bounded`` -- the region may differ in either direction, but a verified error envelope exists
  and is shown to the user;
* ``unbounded`` -- the effect, or its direction, is not established. Never applied automatically:
  a value that would need it stays blocking.

A rule names canonical fields and geometry, never a manufacturer, family or model: an OEM catalog
may later *opt into* a rule after it has established the relay semantics, but the rule itself is
the same for every relay. **No rule is approved yet** (`APPROVED_RULES` is empty), so no import is
approximated and nothing reaches the "Ready -- approximate plot" state until the owner approves a
rule. This module holds no geometry: computing an approximated value is the job of the rule's
future implementation, which must record an `ApproximationRecord` on the value it writes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "APPROVED_RULES",
    "ApproximationClass",
    "ApproximationRecord",
    "ApproximationRule",
    "ErrorEnvelope",
    "approved_rule",
    "rule_problems",
]


class ApproximationClass(StrEnum):
    CONSERVATIVE = "conservative"
    BOUNDED = "bounded"
    UNBOUNDED = "unbounded"

    @property
    def permits_automatic_apply(self) -> bool:
        """Only a conservative or a bounded approximation may be applied without the user."""
        return self is not ApproximationClass.UNBOUNDED


@dataclass(frozen=True)
class ErrorEnvelope:
    """How far the drawn region may differ from the relay's, as established for the rule.

    ``description`` is the user-facing sentence (e.g. "up to 0.47 × X at the upper-left corner").
    ``max_deviation_ohm`` is an absolute bound and ``max_relative_deviation`` a bound relative to
    the reach the rule names; either may be absent when the description states the bound."""

    description: str
    max_deviation_ohm: float | None = None
    max_relative_deviation: float | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("an error envelope needs a description")
        for value in (self.max_deviation_ohm, self.max_relative_deviation):
            if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value < 0):
                raise ValueError("an error envelope bound must be a finite, non-negative number")


_RULE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RULE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _envelope_problems(classification: ApproximationClass, envelope: ErrorEnvelope | None) -> list[str]:
    if classification is ApproximationClass.BOUNDED and envelope is None:
        return ["a bounded approximation needs a verified error envelope"]
    return []


@dataclass(frozen=True)
class ApproximationRule:
    """A relay-neutral approximation the engine may use for one canonical / geometry field."""

    rule_id: str
    rule_version: str
    #: The canonical field (registry id, e.g. ``distance.zone.r_left``) or geometry feature it affects.
    field: str
    classification: ApproximationClass
    #: What is drawn instead of the relay's behaviour, in user-facing words.
    description: str
    envelope: ErrorEnvelope | None = None


def rule_problems(rule: ApproximationRule) -> list[str]:
    """Every reason ``rule`` is not a valid rule (empty when it is)."""
    problems = []
    if not _RULE_ID.match(rule.rule_id):
        problems.append("rule_id must be lower-case kebab-case")
    if not _RULE_VERSION.match(rule.rule_version):
        problems.append("rule_version must be MAJOR.MINOR.PATCH")
    if not rule.field.strip():
        problems.append("a rule must name the field it affects")
    if not rule.description.strip():
        problems.append("a rule needs a description")
    problems += _envelope_problems(rule.classification, rule.envelope)
    return problems


@dataclass(frozen=True)
class ApproximationRecord:
    """The provenance of one approximated canonical value: which rule produced it and what it
    means for the result. Carried on the value's `Provenance` (origin ``engine_approximation``),
    counted by readiness (``ready_approximate``) and returned with an Apply."""

    rule_id: str
    rule_version: str
    #: The canonical path of the approximated value (e.g. ``zones[Z1].resistive_reach.reverse``).
    field: str
    classification: ApproximationClass
    description: str
    envelope: ErrorEnvelope | None = None
    #: The zone the value belongs to (``None`` for a document-level value).
    zone_id: str | None = None

    def __post_init__(self) -> None:
        if not self.classification.permits_automatic_apply:
            raise ValueError("an unbounded approximation is never applied automatically")
        problems = _envelope_problems(self.classification, self.envelope)
        if problems:
            raise ValueError(problems[0])
        if not (self.rule_id and self.rule_version and self.field and self.description.strip()):
            raise ValueError("an approximation record needs a rule id, version, field and description")


#: The approximation rules the owner has approved for automatic use. Empty until a rule is
#: explicitly approved (DEC-198): nothing is approximated today.
APPROVED_RULES: tuple[ApproximationRule, ...] = ()


def approved_rule(rule_id: str, rule_version: str, rules: tuple[ApproximationRule, ...] = APPROVED_RULES) -> ApproximationRule | None:
    """The approved rule with this id and version that may be applied automatically, else ``None``."""
    return next(
        (r for r in rules if r.rule_id == rule_id and r.rule_version == rule_version
         and r.classification.permits_automatic_apply and not rule_problems(r)),
        None,
    )
