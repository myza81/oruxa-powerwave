"""Shared engineering-unit domain layer (owner UAT hardening,
2026-09-12) -- see docs/project-memory/ENGINEERING_UNITS.md.

Triggered by a real Overcurrent UAT defect: a 2.4 kA primary current
through a 1200:1 CT was reported as 0.002 A relay-equivalent instead of
the correct 2.0 A, because `app.domain.overcurrent.
convert_to_relay_secondary()` multiplied the raw *numeric* value (2.4)
by the CT ratio without ever converting the channel's own declared
"kA" unit to amperes first. A unit-safety audit across every backend
calculation path that consumes a unit-bearing engineering value (see
this project's own implementation report for the full findings) found
this was the ONLY confirmed bug of this class in the codebase -- every
other unit-bearing arithmetic path either already normalizes correctly
(`app.domain.per_unit`'s own `VOLTAGE_UNIT_SCALE`/`CURRENT_UNIT_SCALE`,
duplicated a further two ways in `voltage_group_config.py`/
`current_group_config.py`) or never performs cross-unit arithmetic at
all (Phasor, Related Waveforms, the raw waveform/table display path).

This module is the ONE authoritative place for:

    unit parsing            (parse_engineering_unit())
    unit normalization      (the quantity-aware alias table below)
    canonical-unit lookup   (CANONICAL_CALCULATION_UNIT)
    scalar conversion       (convert_value_to_canonical())
    array conversion        (convert_array_to_canonical())

so a future analyzer (Distance: V/I -> ohm; Differential: multiple
current sources normalized to A before comparison; Power: V x I using
canonical units before deriving W/VA/var) never needs to invent its own
unit-scale dictionary the way Overcurrent's own bug shows can go wrong.

## Canonical calculation units

Internal calculation always happens in ONE canonical unit per
Engineering Quantity (`CANONICAL_CALCULATION_UNIT` below) -- the
DISPLAY/source unit is completely independent and is never forced to
change (a 2.4 kA measurement may still be SHOWN as "2.4 kA"; only the
number handed to arithmetic that assumes amperes is normalized first).

## Prefix/case policy -- a deliberate power-system engineering alias
table, never generic SI parsing

Real event files frequently carry inconsistent casing ("KA", "ka",
"KV", "mw", "MVAR", "mva", ...). A bare `raw_unit.lower()` before a
scale lookup would be unsafe in general SI (a lowercase "m" prefix is
genuinely ambiguous between milli and mega), but in THIS domain --
power-system protection/measurement values -- milli-scale current/
voltage/power readings never occur in practice, so this module commits
to one explicit, closed alias table per Engineering Quantity where a
lowercase "m"/"M"/"g"/"G" prefix always means mega/giga, never milli,
exactly matching real files this project has seen (see the module-level
`_ALIASES` table). Any raw unit string NOT in that table -- including a
genuinely novel prefix this table does not yet cover -- is never
guessed at: `parse_engineering_unit()` returns `NORMALIZATION_UNSUPPORTED`
(or, for a future quantity where a prefix's meaning cannot be safely
committed to one interpretation, `NORMALIZATION_AMBIGUOUS`), never a
silent assumption of scale 1.0 or of any particular base unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_ACTIVE_POWER,
    ENGINEERING_QUANTITY_APPARENT_POWER,
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_FREQUENCY,
    ENGINEERING_QUANTITY_REACTIVE_POWER,
    ENGINEERING_QUANTITY_ROCOF,
    ENGINEERING_QUANTITY_VOLTAGE,
)

# ---------------------------------------------------------------------------
# Normalization status vocabulary
# ---------------------------------------------------------------------------

#: `raw_unit` (after only whitespace-stripping, no case change) is
#: already exactly the canonical-cased unit string for this quantity --
#: no correction was needed.
NORMALIZATION_EXACT = "exact"
#: `raw_unit` matched a known alias (a case variant, or a differently-
#: cased prefix) and was normalized to the canonical-cased form.
NORMALIZATION_ALIAS = "normalized_alias"
#: `raw_unit` is blank, or does not match any known alias for this
#: quantity -- never guessed; the caller must treat this as an explicit
#: needs_configuration/ineligible state, never assume a default unit.
NORMALIZATION_UNSUPPORTED = "unsupported"
#: Reserved for a future quantity/prefix combination this table
#: deliberately declines to resolve one way (see module docstring) --
#: no current entry in `_ALIASES` produces this status, since every
#: alias this module DOES recognize has already committed to one
#: explicit interpretation. Kept as a distinct status (rather than
#: folding it into UNSUPPORTED) so a future addition to this table can
#: use it without a call-site contract change.
NORMALIZATION_AMBIGUOUS = "ambiguous"

KNOWN_NORMALIZATION_STATUSES = (
    NORMALIZATION_EXACT, NORMALIZATION_ALIAS, NORMALIZATION_UNSUPPORTED, NORMALIZATION_AMBIGUOUS,
)

# ---------------------------------------------------------------------------
# Canonical calculation unit per Engineering Quantity
# ---------------------------------------------------------------------------

CANONICAL_CALCULATION_UNIT: dict[str, str] = {
    ENGINEERING_QUANTITY_VOLTAGE: "V",
    ENGINEERING_QUANTITY_CURRENT: "A",
    ENGINEERING_QUANTITY_ACTIVE_POWER: "W",
    ENGINEERING_QUANTITY_REACTIVE_POWER: "var",
    ENGINEERING_QUANTITY_APPARENT_POWER: "VA",
    ENGINEERING_QUANTITY_FREQUENCY: "Hz",
    ENGINEERING_QUANTITY_ROCOF: "Hz/s",
}

# ---------------------------------------------------------------------------
# Quantity-aware alias table: raw spelling -> (canonical-cased unit,
# scale to CANONICAL_CALCULATION_UNIT). Deliberately closed and
# per-quantity -- never a generic case-folded SI parser (see module
# docstring). Every raw spelling this project has actually observed in
# real event files/settings forms is listed explicitly; nothing is
# derived by pattern.
# ---------------------------------------------------------------------------

_ALIASES: dict[str, dict[str, tuple[str, float]]] = {
    ENGINEERING_QUANTITY_CURRENT: {
        "A": ("A", 1.0), "a": ("A", 1.0),
        "kA": ("kA", 1_000.0), "KA": ("kA", 1_000.0), "ka": ("kA", 1_000.0),
    },
    ENGINEERING_QUANTITY_VOLTAGE: {
        "V": ("V", 1.0), "v": ("V", 1.0),
        "kV": ("kV", 1_000.0), "KV": ("kV", 1_000.0), "kv": ("kV", 1_000.0),
        "MV": ("MV", 1_000_000.0), "Mv": ("MV", 1_000_000.0), "mv": ("MV", 1_000_000.0),
    },
    ENGINEERING_QUANTITY_ACTIVE_POWER: {
        "W": ("W", 1.0), "w": ("W", 1.0),
        "kW": ("kW", 1_000.0), "KW": ("kW", 1_000.0), "kw": ("kW", 1_000.0),
        "MW": ("MW", 1_000_000.0), "Mw": ("MW", 1_000_000.0), "mw": ("MW", 1_000_000.0),
        "GW": ("GW", 1_000_000_000.0), "Gw": ("GW", 1_000_000_000.0), "gw": ("GW", 1_000_000_000.0),
    },
    #: Common spelling aliases (VAR/kVAR/KVAR/...) are all accepted and
    #: converted to the one canonical spelling ("var"/"kvar"/"Mvar"/
    #: "Gvar" -- lowercase "var", matching MEASURED_UNIT_OPTIONS'
    #: own existing canonical spelling in channel_classification.py).
    ENGINEERING_QUANTITY_REACTIVE_POWER: {
        "var": ("var", 1.0), "VAR": ("var", 1.0), "Var": ("var", 1.0),
        "kvar": ("kvar", 1_000.0), "kVAR": ("kvar", 1_000.0), "KVAR": ("kvar", 1_000.0),
        "Mvar": ("Mvar", 1_000_000.0), "MVAR": ("Mvar", 1_000_000.0), "mvar": ("Mvar", 1_000_000.0),
        "Gvar": ("Gvar", 1_000_000_000.0), "GVAR": ("Gvar", 1_000_000_000.0), "gvar": ("Gvar", 1_000_000_000.0),
    },
    ENGINEERING_QUANTITY_APPARENT_POWER: {
        "VA": ("VA", 1.0), "va": ("VA", 1.0),
        "kVA": ("kVA", 1_000.0), "KVA": ("kVA", 1_000.0), "kva": ("kVA", 1_000.0),
        "MVA": ("MVA", 1_000_000.0), "Mva": ("MVA", 1_000_000.0), "mva": ("MVA", 1_000_000.0),
        "GVA": ("GVA", 1_000_000_000.0), "Gva": ("GVA", 1_000_000_000.0), "gva": ("GVA", 1_000_000_000.0),
    },
    ENGINEERING_QUANTITY_FREQUENCY: {
        "Hz": ("Hz", 1.0), "hz": ("Hz", 1.0), "HZ": ("Hz", 1.0),
    },
    ENGINEERING_QUANTITY_ROCOF: {
        "Hz/s": ("Hz/s", 1.0),
    },
}


@dataclass(frozen=True, slots=True)
class ParsedEngineeringUnit:
    """The result of `parse_engineering_unit()` -- always returned
    (never raises, never `None`); `normalization_status` is what a
    caller checks first. `canonical_unit`/`scale_to_canonical` are only
    populated when the raw unit was actually resolved (`exact` or
    `normalized_alias`) -- both are `None` for `unsupported`/
    `ambiguous`, so a caller can never accidentally use a scale that
    was never actually established."""

    engineering_quantity: str
    raw_unit: str | None
    canonical_unit: str | None
    canonical_calculation_unit: str | None
    scale_to_canonical: float | None
    normalization_status: str


def parse_engineering_unit(engineering_quantity: str, raw_unit: str | None) -> ParsedEngineeringUnit:
    """The one quantity-aware parsing entry point. Never raises, never
    guesses -- an unrecognized `engineering_quantity`, a blank/`None`
    `raw_unit`, or a `raw_unit` outside this quantity's own closed alias
    table all return `normalization_status=NORMALIZATION_UNSUPPORTED`
    with `canonical_unit`/`scale_to_canonical` left `None`."""
    canonical_calculation_unit = CANONICAL_CALCULATION_UNIT.get(engineering_quantity)
    if canonical_calculation_unit is None or raw_unit is None or not raw_unit.strip():
        return ParsedEngineeringUnit(
            engineering_quantity=engineering_quantity, raw_unit=raw_unit,
            canonical_unit=None, canonical_calculation_unit=canonical_calculation_unit,
            scale_to_canonical=None, normalization_status=NORMALIZATION_UNSUPPORTED,
        )
    stripped = raw_unit.strip()
    match = _ALIASES.get(engineering_quantity, {}).get(stripped)
    if match is None:
        return ParsedEngineeringUnit(
            engineering_quantity=engineering_quantity, raw_unit=raw_unit,
            canonical_unit=None, canonical_calculation_unit=canonical_calculation_unit,
            scale_to_canonical=None, normalization_status=NORMALIZATION_UNSUPPORTED,
        )
    canonical_unit, scale = match
    status = NORMALIZATION_EXACT if canonical_unit == stripped else NORMALIZATION_ALIAS
    return ParsedEngineeringUnit(
        engineering_quantity=engineering_quantity, raw_unit=raw_unit,
        canonical_unit=canonical_unit, canonical_calculation_unit=canonical_calculation_unit,
        scale_to_canonical=scale, normalization_status=status,
    )


def scale_to_canonical(engineering_quantity: str, raw_unit: str | None) -> float | None:
    """Convenience: just the multiplier (raw_unit's own value x this =
    the canonical-calculation-unit value), or `None` if `raw_unit`
    could not be resolved for this quantity."""
    parsed = parse_engineering_unit(engineering_quantity, raw_unit)
    if parsed.normalization_status in (NORMALIZATION_UNSUPPORTED, NORMALIZATION_AMBIGUOUS):
        return None
    return parsed.scale_to_canonical


def convert_value_to_canonical(value: float | None, engineering_quantity: str, raw_unit: str | None) -> float | None:
    """Scalar conversion to the quantity's own canonical calculation
    unit. Returns `None` (never guesses, never silently assumes scale
    1.0) when `value` is missing/non-finite or `raw_unit` cannot be
    resolved -- the caller must treat that as an explicit needs-
    configuration state."""
    if value is None or not math.isfinite(value):
        return None
    scale = scale_to_canonical(engineering_quantity, raw_unit)
    if scale is None:
        return None
    return value * scale


def convert_array_to_canonical(
    values: np.ndarray, engineering_quantity: str, raw_unit: str | None,
) -> np.ndarray | None:
    """Array counterpart of `convert_value_to_canonical()` -- same
    unit-resolution rule, vectorized. Never mutates `values` (a fresh
    array is always returned); a non-finite (NaN) input sample stays
    non-finite after conversion, never coerced. Returns `None` under the
    exact same "raw_unit could not be resolved" condition the scalar
    form does -- the caller must not silently fall back to treating the
    array as already-canonical."""
    scale = scale_to_canonical(engineering_quantity, raw_unit)
    if scale is None:
        return None
    return values.astype(np.float64, copy=True) * scale
