"""Analog channel engineering-type classification.

Reusable domain knowledge, not a UI display trick -- lives here (not in the
frontend) so it has exactly one implementation, usable by future channel
filtering, waveform channel selection, calculated signals, and analysis
tools, not just the Phase 1 channel-browsing UI (see
docs/project-memory/MIGRATION_PLAN.md's Phase 1 refinement record).

Classification is deliberately conservative: an analog channel that cannot
be confidently classified is `UNDEFINED`, never guessed. Three tiers, in
order:

1. Explicit metadata (`AnalogChannel.parameter_type`) -- the values powerwave's
   own Import Wizard already assigns (`app/import_wizard/column_mapping.py`
   `ParameterType`). COMTRADE (Phase 1's only provider) never sets this
   field, so this tier is currently dormant in production but is real,
   tested code -- not a placeholder -- ready for Phase 1.5's CSV/Excel
   providers, which do set it.
2. Reliable unit semantics -- COMTRADE always provides a `unit` string
   (from the CFG's declared engineering unit), which is the one signal
   available for every Phase 1 analog channel today. Matched against a
   fixed set of recognized base units, tolerant of a metric prefix
   (k/m/M/G/µ/u) and case, but nothing looser than that.
3. Channel naming patterns -- deliberately NOT implemented. No naming
   pattern was judged "sufficiently deterministic" (the project's own
   bar for this tier): e.g. a channel literally named "VA" is genuinely
   ambiguous between "voltage, phase A" and the unit "VA" (apparent
   power) -- exactly the kind of vague string match this classifier must
   not guess through. If a genuinely unambiguous naming convention is
   identified later, it belongs here as tier 3, not duplicated in the UI.

Real/reactive/apparent power (W / VAR / VA and their prefixed forms) are
grouped under one `Power` category for Phase 1 -- the task that requested
this classifier gave Voltage/Current/Frequency/Power as the target
categories; splitting Power into Active/Reactive/Apparent is a reasonable
future refinement, not requested now.
"""

from __future__ import annotations

import re

UNDEFINED = "Undefined"
VOLTAGE = "Voltage"
CURRENT = "Current"
FREQUENCY = "Frequency"
ROCOF = "ROCOF"
POWER = "Power"

# All categories this module can ever return -- useful for tests and for
# any future UI that wants to render a stable, ordered group list rather
# than deriving it from whatever happens to appear in one file.
KNOWN_CATEGORIES = (VOLTAGE, CURRENT, POWER, FREQUENCY, ROCOF, UNDEFINED)

# Tier 1: powerwave's own ParameterType values (app/import_wizard/column_mapping.py).
# "digital", "timestamp" cannot apply to an analog channel and are treated
# as unrecognized (fall through) rather than mapped to something
# arbitrary. "unknown" maps explicitly to UNDEFINED -- that is exactly
# what it means, not a coincidental fallthrough.
_PARAMETER_TYPE_TO_CATEGORY: dict[str, str] = {
    "voltage": VOLTAGE,
    "current": CURRENT,
    "mw": POWER,
    "mvar": POWER,
    "frequency": FREQUENCY,
    "rocof": ROCOF,
    "unknown": UNDEFINED,
}

# Tier 2: base engineering unit, after stripping an optional single-letter
# metric prefix. The prefix is intentionally not decoded into a multiplier
# here (that's what AnalogChannel.scale/offset are for) -- this only needs
# to recognize the unit *family* for classification purposes, so "m" being
# ambiguous between milli- and Mega- (case-folded) doesn't matter.
_UNIT_PATTERN = re.compile(r"^[kmgµu]?(hz|var|va|v|a|w)$", re.IGNORECASE)
_BASE_UNIT_TO_CATEGORY: dict[str, str] = {
    "v": VOLTAGE,
    "a": CURRENT,
    "hz": FREQUENCY,
    "w": POWER,
    "var": POWER,
    "va": POWER,
}


def classify_analog_channel(*, parameter_type: str | None, unit: str | None) -> str:
    """Return one of KNOWN_CATEGORIES for an analog channel.

    Never raises. Returns UNDEFINED whenever neither signal confidently
    resolves to a known category -- callers must not treat UNDEFINED as an
    error, only as "type not confidently known."
    """
    if parameter_type:
        category = _PARAMETER_TYPE_TO_CATEGORY.get(parameter_type.strip().lower())
        if category:
            return category

    if unit:
        match = _UNIT_PATTERN.match(unit.strip())
        if match:
            return _BASE_UNIT_TO_CATEGORY[match.group(1).lower()]

    return UNDEFINED
