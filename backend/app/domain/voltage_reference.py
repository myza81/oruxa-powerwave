"""Automatic Voltage Reference detection (Phase 5C-UAT, DEC-049 addendum).

Owner UAT on the original profile-based Per-Unit workflow found it too
complex; this module is the new piece that replaces the old "Voltage
Basis" dropdown-only field with a deterministic, explainable, naming-
based detector -- never a probabilistic classifier, never waveform-
magnitude analysis (explicitly deferred, per the owner's own spec:
"Do not infer voltage reference solely from instantaneous magnitude
yet").

`detect_voltage_reference()` inspects a source's own Voltage-classified
analog channel NAMES only (the trusted, always-available signal every
COMTRADE/future-provider channel already carries) and returns one of:

- A confident `LINE_TO_GROUND`/`LINE_TO_LINE` result, with the channel
  names that produced that evidence (surfaced verbatim in the UI as
  "Detected from VR, VY, VB").
- `None` (no confident result) when the evidence is absent or
  contradictory -- NEVER silently guessed. Section 7: "If the algorithm
  cannot determine the reference with sufficient confidence, do NOT
  silently invent one."

Deliberately conservative and simple (section 6/7's own explicit
instruction): a fixed, ordered set of phase-naming patterns, not a
scored/probabilistic model. A bare phase LETTER (R/Y/B or A/B/C) is
treated as line-to-ground evidence (a single-phase-to-reference
measurement); a phase-PAIR (RY/YB/BR or AB/BC/CA, in either character
order) is treated as line-to-line evidence -- checked in that priority
order specifically so a name like "VRY" is never mis-read as a bare "R"
reading with a trailing "Y" (the owner's own explicit warning: "R/Y/B
present is useful evidence, but it must NOT automatically mean
Line-to-Ground when the names clearly indicate combinations such as
VRY/VYB/VBR").

**DEC-050 Slice 3 correction (2026-08-24)**: the original implementation
only ever recognized phase evidence when the ENTIRE channel name was
"V" + a bare token (e.g. exactly "VR", "VRY", "VBUS") -- it had no way
to see phase evidence in a longer, location-prefixed name like "NORTH
BUS VA", so the generic `_LL_EXPLICIT_SUBSTRINGS` ("BUS"/"LL") fallback
was the ONLY thing that ever matched such a name, incorrectly returning
Line-to-Line even though "VA" at the end is strong, explicit
Line-to-Ground evidence. Per
PER_UNIT_MEASUREMENT_MODEL.md's own corrected principle -- "explicit
electrical representation outranks generic location/equipment
vocabulary" -- `_classify_one_channel_name()` now looks for an explicit
"V" + phase-token pattern anywhere a real word boundary precedes it
(name start, or a non-alphanumeric separator -- never fused into an
unrelated word like "AVR", which must keep resolving to `None`, exactly
as before this fix), and only falls back to the generic BUS/LL
substring check when no such explicit suffix is found at all. Every
pre-existing test in test_voltage_reference.py still passes unchanged
-- this is a strictly additive detection capability, not a
re-interpretation of any name this module already classified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LINE_TO_GROUND = "line_to_ground"
LINE_TO_LINE = "line_to_line"
KNOWN_VOLTAGE_REFERENCES = (LINE_TO_GROUND, LINE_TO_LINE)

REASON_DETECTED = "detected_from_names"
REASON_NO_PATTERN = "no_recognizable_pattern"
REASON_CONFLICTING = "conflicting_evidence"
REASON_MANUAL_OVERRIDE = "manual_override"
REASON_NO_CHANNELS = "no_voltage_channels"

#: Phase-to-phase pairs, both character orders, covering both the R/Y/B
#: (common in Asia-Pacific/UK-derived conventions) and A/B/C naming
#: schemes -- e.g. "VRY"/"VYR" both read as the same R-Y phase-to-phase
#: measurement.
_LL_PAIR_TOKENS = frozenset({"RY", "YR", "YB", "BY", "BR", "RB", "AB", "BA", "BC", "CB", "CA", "AC"})
#: Bare phase-to-neutral/ground tokens with an explicit trailing "N" --
#: e.g. "VRN", "VAN" -- the strongest possible line-to-ground evidence
#: (an explicit neutral reference named in the channel itself).
_LG_NEUTRAL_TOKENS = frozenset({"RN", "YN", "BN", "AN", "CN"})
#: A single bare phase letter -- e.g. "VR", "VA" -- read as a
#: single-phase-to-reference (line-to-ground) measurement.
_LG_SINGLE_TOKENS = frozenset({"R", "Y", "B", "A", "C"})
#: Explicit line-to-line/bus vocabulary that can appear anywhere in the
#: name, not just as a trailing phase token -- "VLL", "VBUS", "BUS
#: VOLTAGE" are all common vendor conventions for an already-phase-to-
#: phase measurement.
_LL_EXPLICIT_SUBSTRINGS = ("BUS", "LL")


@dataclass(slots=True)
class VoltageReferenceDetection:
    """One source's own effective voltage reference -- the result the
    setup UI renders directly ("Auto: Line-to-Ground / Detected from VR,
    VY, VB", or "Could not determine automatically")."""

    reference: str | None
    evidence_names: list[str] = field(default_factory=list)
    reason: str = REASON_NO_PATTERN


def _ends_with_v_token(upper: str, token: str) -> bool:
    """True if `upper` ends in "V" + `token`, with that "V" starting its
    own word -- either the whole name IS "V" + token (e.g. "VR"), or the
    character immediately before the "V" is a non-alphanumeric separator
    (space/hyphen/underscore/etc.), e.g. "NORTH BUS VA", "275KV-BUS_VRY".
    This is what lets a longer, location-prefixed name still carry
    recognizable explicit phase evidence. The word-boundary requirement
    is deliberate: it is what keeps a name like "AVR" (Automatic Voltage
    Regulator -- a real power-system abbreviation, "V" fused into the
    middle of an unrelated word) from being misread as phase-R evidence
    -- explicit evidence must be a genuine, separated phase token, not a
    coincidental letter run inside a different word."""
    suffix = "V" + token
    if not upper.endswith(suffix):
        return False
    prefix_len = len(upper) - len(suffix)
    if prefix_len == 0:
        return True
    return not upper[prefix_len - 1].isalnum()


def _classify_one_channel_name(channel_name: str) -> str | None:
    """Returns LINE_TO_LINE/LINE_TO_GROUND for one channel name, or
    `None` if it carries no recognizable phase-naming evidence at all.

    Priority order, per PER_UNIT_MEASUREMENT_MODEL.md's own corrected
    principle -- "explicit electrical representation outranks generic
    location/equipment vocabulary": an explicit phase token (bare, e.g.
    a channel literally named just "RY" or "AN", OR as a word-bounded
    "V" + token suffix of a longer name, e.g. "NORTH BUS VA") is checked
    FIRST, in pair > neutral > single sub-priority so a pair is never
    mis-read via its own trailing single letter -- and ONLY when no such
    explicit token is found anywhere does the generic "BUS"/"LL"
    vocabulary fallback apply. A name like "NORTH BUS VA" therefore
    resolves via its own explicit "VA" evidence to Line-to-Ground, never
    falling through to the generic "BUS" reading; a name with no phase
    letter at all, like plain "BUS VOLTAGE" or "VBUS", still correctly
    falls through to that same generic reading, unchanged from before
    this correction."""
    upper = channel_name.strip().upper()

    def matches(token: str) -> bool:
        return upper == token or _ends_with_v_token(upper, token)

    for token in _LL_PAIR_TOKENS:
        if matches(token):
            return LINE_TO_LINE
    for token in _LG_NEUTRAL_TOKENS:
        if matches(token):
            return LINE_TO_GROUND
    for token in _LG_SINGLE_TOKENS:
        if matches(token):
            return LINE_TO_GROUND
    if any(marker in upper for marker in _LL_EXPLICIT_SUBSTRINGS):
        return LINE_TO_LINE
    return None


def detect_voltage_reference(voltage_channel_names: list[str]) -> VoltageReferenceDetection:
    """The one, deterministic detection authority (section 6/7): scans
    every Voltage-classified channel name belonging to one source,
    classifies each independently, and returns a confident result only
    when every channel that DID carry evidence agrees -- a source mixing
    "VRY" (line-to-line) with "VA" (line-to-ground) is conflicting, never
    silently resolved to whichever pattern happened to match first."""
    if not voltage_channel_names:
        return VoltageReferenceDetection(reference=None, evidence_names=[], reason=REASON_NO_CHANNELS)

    line_to_line_evidence: list[str] = []
    line_to_ground_evidence: list[str] = []
    for name in voltage_channel_names:
        classification = _classify_one_channel_name(name)
        if classification == LINE_TO_LINE:
            line_to_line_evidence.append(name)
        elif classification == LINE_TO_GROUND:
            line_to_ground_evidence.append(name)

    if line_to_line_evidence and line_to_ground_evidence:
        return VoltageReferenceDetection(
            reference=None, evidence_names=line_to_line_evidence + line_to_ground_evidence, reason=REASON_CONFLICTING
        )
    if line_to_line_evidence:
        return VoltageReferenceDetection(reference=LINE_TO_LINE, evidence_names=line_to_line_evidence, reason=REASON_DETECTED)
    if line_to_ground_evidence:
        return VoltageReferenceDetection(reference=LINE_TO_GROUND, evidence_names=line_to_ground_evidence, reason=REASON_DETECTED)
    return VoltageReferenceDetection(reference=None, evidence_names=[], reason=REASON_NO_PATTERN)
