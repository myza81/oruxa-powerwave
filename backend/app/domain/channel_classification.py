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

# Phase 5B (DEC-048): waveform-form metadata -- a SEPARATE taxonomy from
# engineering_type above. engineering_type answers "what physical quantity
# is this" (Voltage/Current/...); waveform_form answers "how is this value
# recorded at each sample" (an instantaneous AC waveform vs. an already-
# RMS/magnitude quantity vs. unknown). Neither implies the other -- a
# Voltage channel may be instantaneous OR already RMS; a Frequency channel
# is virtually never a meaningful RMS input regardless of its (Frequency)
# engineering_type. This is why RMS eligibility must never be gated purely
# by engineering_type (owner requirement, section 26/27/63 of the RMS
# task) -- COMTRADE is not proof of "instantaneous" (section 12).
#
# No provider sets this away from UNKNOWN today -- COMTRADE has no such
# field, and CSV/Excel import does not exist yet (Phase 1.5, dormant, same
# as engineering_type's own tier 1). The field exists now so a future
# importer has somewhere trustworthy to write to, per the owner's explicit
# forward-compatibility requirement (section 11/28) -- this is not a
# speculative redesign, just one additive optional field, mirroring
# exactly how `engineering_type` itself was added to `CalculatedChannel`
# by a Phase 5A addendum before any UI depended on it.
WAVEFORM_FORM_UNKNOWN = "unknown"
WAVEFORM_FORM_INSTANTANEOUS = "instantaneous"
WAVEFORM_FORM_RMS = "rms"
WAVEFORM_FORM_MAGNITUDE = "magnitude"
KNOWN_WAVEFORM_FORMS = (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_UNKNOWN,
)

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


#: Calculated-channel operations whose output form is a pass-through of
#: their single input's own form, unchanged.
_WAVEFORM_FORM_PASSTHROUGH_OPERATIONS = frozenset({"reverse_polarity", "multiply_constant"})
#: Multi-input operations use the same "all-known-and-equal else unknown"
#: rule as derive_engineering_type() -- see the shared helper below.
_WAVEFORM_FORM_INHERIT_IF_UNANIMOUS_OPERATIONS = frozenset({"addition", "subtraction"})


def _unanimous_known_value(values: list[str], unknown: str) -> str:
    """Shared "all inputs share the same known value, else unknown" rule --
    used by both derive_engineering_type() (app.domain.calculated_channel)
    and derive_waveform_form() below for their respective multi-input
    branches, so the one rule has exactly one implementation."""
    if not values:
        return unknown
    first = values[0]
    if first == unknown:
        return unknown
    if all(v == first for v in values):
        return first
    return unknown


def derive_waveform_form(operation: str, input_forms: list[str]) -> str:
    """Phase 5B (DEC-048): the calculated-channel waveform-form propagation
    rule (owner section 13). Deliberately a SEPARATE function from
    derive_engineering_type() in app.domain.calculated_channel, not a
    reuse of it -- unlike engineering_type, where every Phase 5A operation
    shares one inheritance rule, waveform_form propagation genuinely
    differs PER OPERATION:

    - reverse_polarity, multiply_constant: pass through the single input's
      form unchanged (negating or scaling a waveform does not change
      whether it is instantaneous, RMS, or already a magnitude).
    - addition, subtraction: inherit only if every input shares the same
      KNOWN form, else unknown -- same conservative shape as
      derive_engineering_type(), via the shared `_unanimous_known_value()`
      helper.
    - absolute_value: always `unknown` (owner section 13: "prefer unknown
      unless there is a stronger mathematically-approved rule" -- taking
      the absolute value of an instantaneous waveform produces something
      that is no longer usefully "instantaneous" for RMS-eligibility
      purposes, e.g. it has lost its bipolarity, one of the detector's own
      indicators).
    - rms: always `rms`, unconditionally -- the output's waveform form is
      DEFINED by the operation itself, never inherited from its input
      (an RMS channel's own output is RMS by construction, regardless of
      what its input was).

    Never guesses from a channel's own (user-editable) `name`, matching
    derive_engineering_type()'s own explicit rule.
    """
    if operation == "rms":
        return WAVEFORM_FORM_RMS
    if operation == "absolute_value":
        return WAVEFORM_FORM_UNKNOWN
    if operation in _WAVEFORM_FORM_PASSTHROUGH_OPERATIONS:
        return input_forms[0] if input_forms else WAVEFORM_FORM_UNKNOWN
    if operation in _WAVEFORM_FORM_INHERIT_IF_UNANIMOUS_OPERATIONS:
        return _unanimous_known_value(input_forms, WAVEFORM_FORM_UNKNOWN)
    return WAVEFORM_FORM_UNKNOWN
