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
    # CSV/Excel Engineering Quantity enhancement (DEC-077): richer values
    # the Data Preparation Workspace may now write into
    # AnalogChannel.parameter_type. Each still resolves to the exact same
    # broad category the plain form already does -- "voltage angle" ->
    # VOLTAGE, same as "voltage" -- because this Tier-1 classifier only
    # ever draws the SIX broad KNOWN_CATEGORIES distinctions; a richer
    # Angle/Active-vs-Reactive distinction lives one level up, in
    # ENGINEERING QUANTITY below, never here (see that section's own
    # docstring for why the two stay deliberately separate).
    "voltage angle": VOLTAGE,
    "current angle": CURRENT,
    "active power": POWER,
    "reactive power": POWER,
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


# ---------------------------------------------------------------------------
# Engineering Quantity (DEC-077): CSV/Excel Waveform-column metadata,
# ---------------------------------------------------------------------------
#
# A richer, user-SELECTED (never guessed) taxonomy than the six broad
# KNOWN_CATEGORIES above -- e.g. distinguishing "Voltage Angle" from plain
# "Voltage", or "Active Power"/"Reactive Power" from the unified "Power"
# category. Every Engineering Quantity maps to EXACTLY ONE broad category
# via broad_engineering_type() below, so every existing engineering_type
# consumer (channel-browsing group headings, calculated-channel
# derive_engineering_type() inheritance, per-unit measurement-group
# eligibility) keeps working completely unchanged -- this module never
# forces the old broad field to carry more meaning than that code already
# expects.
#
# Deliberately still no first-class "Angle" broad category (see
# broad_engineering_type()'s own docstring): "Voltage Angle" maps to plain
# VOLTAGE, not a new family, matching the owner's own explicit instruction
# not to widen broad-family compatibility assumptions (measurement-group/
# per-unit eligibility, RMS/magnitude waveform_form assumptions) merely
# because a richer label now exists. A channel carrying an Angle quantity
# is metadata-only richer for now -- nothing downstream treats it any
# differently than a plain Voltage/Current channel of the same broad type.
ENGINEERING_QUANTITY_VOLTAGE = "Voltage"
ENGINEERING_QUANTITY_VOLTAGE_ANGLE = "Voltage Angle"
ENGINEERING_QUANTITY_CURRENT = "Current"
ENGINEERING_QUANTITY_CURRENT_ANGLE = "Current Angle"
ENGINEERING_QUANTITY_ACTIVE_POWER = "Active Power"
ENGINEERING_QUANTITY_REACTIVE_POWER = "Reactive Power"
ENGINEERING_QUANTITY_FREQUENCY = "Frequency"
ENGINEERING_QUANTITY_ROCOF = "ROCOF"
#: Same literal as the broad UNDEFINED above -- one constant, reused, never
#: two independent "undefined" strings that could silently drift apart.
ENGINEERING_QUANTITY_UNDEFINED = UNDEFINED

#: Every value classify_analog_channel()/the Data Preparation Workspace's
#: own selector may use. Deliberately closed -- no Power Factor, Energy,
#: Impedance, Digital, or Temperature (explicit non-goals; add later, when
#: actually needed, never speculatively).
KNOWN_ENGINEERING_QUANTITIES = (
    ENGINEERING_QUANTITY_VOLTAGE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_ACTIVE_POWER,
    ENGINEERING_QUANTITY_REACTIVE_POWER,
    ENGINEERING_QUANTITY_FREQUENCY,
    ENGINEERING_QUANTITY_ROCOF,
    ENGINEERING_QUANTITY_UNDEFINED,
)

_ENGINEERING_QUANTITY_TO_BROAD_TYPE: dict[str, str] = {
    ENGINEERING_QUANTITY_VOLTAGE: VOLTAGE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE: VOLTAGE,
    ENGINEERING_QUANTITY_CURRENT: CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE: CURRENT,
    ENGINEERING_QUANTITY_ACTIVE_POWER: POWER,
    ENGINEERING_QUANTITY_REACTIVE_POWER: POWER,
    ENGINEERING_QUANTITY_FREQUENCY: FREQUENCY,
    ENGINEERING_QUANTITY_ROCOF: ROCOF,
    ENGINEERING_QUANTITY_UNDEFINED: UNDEFINED,
}

#: Case-insensitive reverse lookup, keyed by lowercased quantity text ->
#: the exact canonical-cased member of KNOWN_ENGINEERING_QUANTITIES.
_NORMALIZED_TO_ENGINEERING_QUANTITY: dict[str, str] = {
    quantity.lower(): quantity for quantity in KNOWN_ENGINEERING_QUANTITIES
}

# Measured Unit enhancement (DEC-080): a SEPARATE concept from Engineering
# Quantity above -- Quantity answers "what does this signal represent"
# (Voltage, Frequency, ...), Unit answers "how is the numeric value
# expressed" (V vs kV, W vs MW, ...). Quantity never determines scale (a
# Voltage channel may genuinely be recorded in V or kV), so this is a
# SEPARATE, quantity-dependent controlled list, never a guess derived from
# the quantity alone (task section G's own explicit "no silent unit
# guessing" requirement). Blank is always a valid member -- "the system
# still cannot safely scale it" (task section F) is a legitimate, common
# state, never a readiness blocker. Deliberately closed per quantity: only
# the units actually reachable by existing PU/classifier code
# (`app.domain.per_unit.VOLTAGE_UNIT_SCALE`/`CURRENT_UNIT_SCALE` for
# Voltage/Current; the rest are metadata-only today, matching Angle's own
# "no deg<->rad conversion in this slice" non-goal) -- never a free-text
# unit system. `ENGINEERING_QUANTITY_UNDEFINED` intentionally allows only
# blank (task section R): the controlled list is quantity-dependent, so an
# unclassified column has no quantity to look the list up against.
MEASURED_UNIT_OPTIONS: dict[str, tuple[str, ...]] = {
    ENGINEERING_QUANTITY_VOLTAGE: ("", "V", "kV"),
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE: ("", "deg", "rad"),
    ENGINEERING_QUANTITY_CURRENT: ("", "A", "kA"),
    ENGINEERING_QUANTITY_CURRENT_ANGLE: ("", "deg", "rad"),
    ENGINEERING_QUANTITY_ACTIVE_POWER: ("", "W", "kW", "MW", "GW"),
    ENGINEERING_QUANTITY_REACTIVE_POWER: ("", "var", "kvar", "Mvar", "Gvar"),
    ENGINEERING_QUANTITY_FREQUENCY: ("", "Hz"),
    ENGINEERING_QUANTITY_ROCOF: ("", "Hz/s"),
    ENGINEERING_QUANTITY_UNDEFINED: ("",),
}


def measured_unit_valid_for_quantity(engineering_quantity: str, measured_unit: str) -> bool:
    """`True` iff `measured_unit` is `""` (always valid, task section F) or
    an exact, canonical-cased member of `MEASURED_UNIT_OPTIONS[engineering_
    quantity]`. An unrecognized `engineering_quantity` falls back to
    "only blank is valid" (`("",)` default), the same conservative
    behavior `ENGINEERING_QUANTITY_UNDEFINED` itself uses -- never raises,
    matching this module's own "never raise, only report" contract; the
    caller (`app.services.working_overlay_service`) turns a `False` result
    into an HTTP 400 (task section AF/AE: the backend validates the pair,
    never trusting a frontend dropdown alone)."""
    return measured_unit in MEASURED_UNIT_OPTIONS.get(engineering_quantity, ("",))


def broad_engineering_type(engineering_quantity: str) -> str:
    """Deterministic Engineering Quantity -> broad `engineering_type`
    mapping (task section C), the ONE place this compatibility rule is
    ever expressed. Unrecognized input maps to UNDEFINED, never raises --
    matching classify_analog_channel()'s own "never raise, only report
    not-confidently-known" contract."""
    return _ENGINEERING_QUANTITY_TO_BROAD_TYPE.get(engineering_quantity, UNDEFINED)


def canonical_engineering_quantity(parameter_type: str | None) -> str:
    """Return the exact `KNOWN_ENGINEERING_QUANTITIES` member `parameter_type`
    names (case-insensitively), or `UNDEFINED` if it does not name one.

    Deliberately STRICTER than classify_analog_channel()'s own Tier-1 unit
    lookup: legacy/compatibility-only parameter_type values such as "mw"/
    "mvar" (kept working for broad `engineering_type` classification, see
    `_PARAMETER_TYPE_TO_CATEGORY`) are NOT themselves one of the nine
    canonical Engineering Quantity strings, so this returns UNDEFINED for
    them -- only an EXACT (case-insensitive) canonical quantity name (as
    the Data Preparation Workspace's own selector writes) restores the
    richer value. This is why a COMTRADE channel (parameter_type always
    `None`) or a channel whose parameter_type is one of the older bare
    keys always reports `engineering_quantity = "Undefined"` even when its
    broad `engineering_type` is confidently Voltage/Current/Power -- the
    richer field is additive, never a replacement for the broad one.
    """
    if not parameter_type:
        return UNDEFINED
    return _NORMALIZED_TO_ENGINEERING_QUANTITY.get(parameter_type.strip().lower(), UNDEFINED)


#: Strict "<base label> (<suffix text>)" grammar -- the suffix must be the
#: very end of the string, in exactly one trailing parenthesized group.
#: `(.*)` is greedy, so a label with unrelated internal parentheses (task
#: section R's own "Line 1 (North)" kind of case) still only ever matches
#: the LAST parenthesized group; whether that group's text turns out to be
#: a recognized quantity is decided afterward by the canonical lookup, not
#: by this pattern.
_ENGINEERING_QUANTITY_SUFFIX_PATTERN = re.compile(r"^(.*) \(([^()]+)\)$")


def parse_engineering_quantity_suffix(label: str) -> tuple[str, str | None]:
    """Parse a strict, case-insensitive `" (<Engineering Quantity>)"`
    suffix off the END of `label` (task section Q/R). Returns
    `(base_label, matched_quantity)`: `matched_quantity` is the exact
    canonical-cased `KNOWN_ENGINEERING_QUANTITIES` member if -- and only
    if -- the parenthesized text is an EXACT (case-insensitive) match for
    one of the eight non-Undefined quantities; otherwise returns
    `(label, None)` completely UNCHANGED, deliberately conservative:

    - `"Time (s)"` never matches -- `"s"` is not a known quantity, so this
      returns `("Time (s)", None)` (task section T: never confused with
      the Configured Time header's own `(s)` suffix).
    - `"Voltage Sensor"` (no parenthesis at all) never matches.
    - `"Voltage Sensor (Voltage)"` matches: `("Voltage Sensor", "Voltage")`.
    - `"Phase A"`, `"Quality"`, ordinary text containing quantity-ish
      substrings but no exact recognized suffix, never match (task section
      AM) -- this is an exact-suffix parser, never a substring/fuzzy
      guesser (task section R).

    Never guesses, never raises.
    """
    match = _ENGINEERING_QUANTITY_SUFFIX_PATTERN.match(label)
    if not match:
        return label, None
    base, suffix_text = match.group(1), match.group(2)
    canonical = _NORMALIZED_TO_ENGINEERING_QUANTITY.get(suffix_text.strip().lower())
    if canonical is None or canonical == UNDEFINED:
        return label, None
    return base, canonical


def encode_engineering_quantity_suffix(label: str, engineering_quantity: str) -> str:
    """The exporter's own inverse of `parse_engineering_quantity_suffix()`
    (task sections N/O/P): returns `"<base label> (<Engineering
    Quantity>)"` for a known, non-Undefined quantity, or `label` UNCHANGED
    for `UNDEFINED`/an unrecognized value (task section O -- never a noisy
    literal `"(Undefined)"` suffix).

    Round-trip-stable by construction (task section P): ANY existing
    recognized suffix is stripped via `parse_engineering_quantity_suffix()`
    FIRST, so re-exporting an already-suffixed label (from a prior cleaned
    export, re-uploaded and re-exported unchanged) normalizes to exactly
    one suffix, never `"... (Voltage) (Voltage)"`.
    """
    if engineering_quantity not in KNOWN_ENGINEERING_QUANTITIES or engineering_quantity == UNDEFINED:
        return label
    base_label, _ = parse_engineering_quantity_suffix(label)
    return f"{base_label} ({engineering_quantity})"


#: Strict "<base label> (<quantity>) [<unit>]" grammar (Measured Unit
#: enhancement, DEC-080) -- the SAME anchored, end-of-string discipline as
#: `_ENGINEERING_QUANTITY_SUFFIX_PATTERN` above, extended with one more
#: trailing bracketed group. Deliberately a SEPARATE pattern rather than
#: making the quantity pattern's own trailing group optional-with-a-
#: bracket: keeping both patterns simple and independently readable was
#: judged clearer than one regex trying to express both grammars.
_ENGINEERING_QUANTITY_UNIT_SUFFIX_PATTERN = re.compile(r"^(.*) \(([^()]+)\) \[([^\[\]]+)\]$")


def _normalized_measured_unit_for_quantity(engineering_quantity: str, unit_text: str) -> str | None:
    """Case-insensitive match of `unit_text` against `MEASURED_UNIT_
    OPTIONS[engineering_quantity]`, returning the canonical-cased option
    (task section S: "parser may be case-insensitive; stored/exported
    values use canonical casing") or `None` if it names no valid unit for
    that quantity -- never guesses, never invents a new unit string."""
    normalized = unit_text.strip().lower()
    for option in MEASURED_UNIT_OPTIONS.get(engineering_quantity, ()):
        if option and option.lower() == normalized:
            return option
    return None


def parse_engineering_quantity_and_unit_suffix(label: str) -> tuple[str, str | None, str | None]:
    """Parse the combined `" (<Engineering Quantity>) [<Measured Unit>]"`
    suffix (task section S), falling back to the quantity-ONLY parser
    (`parse_engineering_quantity_suffix()`) for backward compatibility
    with existing DEC-077-only exports that carry no unit suffix at all
    (task section T) -- `measured_unit` is simply `None` in that case.
    Returns `(base_label, matched_quantity, matched_unit)`.

    Deliberately conservative when a trailing `[...]` bracket IS present
    but does not parse as a valid quantity+unit pair (an unrecognized
    quantity text, or a unit not in that quantity's own controlled list,
    e.g. task section AQ's `"Line (North) [A]"`): falls through to the
    quantity-only parser applied to the FULL original string, which
    cannot match either (it requires the string to end in `")"`, not
    `"]"`) -- so the result is `(label, None, None)`, exactly as
    `parse_engineering_quantity_suffix()` alone would already report for
    that string. Never invents a quantity or a unit from a malformed
    bracket. `"Voltage [estimated]"` (a bare bracket with no quantity
    parenthesis at all) never matches either pattern, for the same
    reason (task section X: no fuzzy label guessing).
    """
    match = _ENGINEERING_QUANTITY_UNIT_SUFFIX_PATTERN.match(label)
    if match:
        base, suffix_text, unit_text = match.group(1), match.group(2), match.group(3)
        canonical_quantity = _NORMALIZED_TO_ENGINEERING_QUANTITY.get(suffix_text.strip().lower())
        if canonical_quantity is not None and canonical_quantity != UNDEFINED:
            canonical_unit = _normalized_measured_unit_for_quantity(canonical_quantity, unit_text)
            if canonical_unit is not None:
                return base, canonical_quantity, canonical_unit
    base_label, quantity = parse_engineering_quantity_suffix(label)
    return base_label, quantity, None


def encode_engineering_quantity_and_unit_suffix(
    label: str, engineering_quantity: str, measured_unit: str | None
) -> str:
    """The exporter's own inverse of `parse_engineering_quantity_and_unit_
    suffix()` (task section P): `"<base label> (<Engineering Quantity>)
    [<Measured Unit>]"` when a valid, non-blank unit is supplied for that
    quantity; otherwise falls back to `encode_engineering_quantity_suffix()`'s
    own quantity-only form (task section Q: a blank unit never appends
    `"[]"`/`"[ ]"`), which itself returns `label` unchanged for
    `Undefined`/an unrecognized quantity (task section O).

    Round-trip-stable by construction (task sections U/V): ANY existing
    suffix -- quantity-only OR quantity+unit -- is stripped via
    `parse_engineering_quantity_and_unit_suffix()` FIRST (the ONE parser
    this function's own stripping step uses), so re-exporting an
    already-suffixed label normalizes to exactly one suffix, never a
    duplicated `"(Voltage) [kV] (Voltage) [kV]"`.
    """
    if engineering_quantity not in KNOWN_ENGINEERING_QUANTITIES or engineering_quantity == UNDEFINED:
        return label
    base_label, _, _ = parse_engineering_quantity_and_unit_suffix(label)
    if measured_unit and measured_unit_valid_for_quantity(engineering_quantity, measured_unit):
        return f"{base_label} ({engineering_quantity}) [{measured_unit}]"
    return f"{base_label} ({engineering_quantity})"
