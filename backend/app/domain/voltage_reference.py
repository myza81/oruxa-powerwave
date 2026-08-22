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


def _phase_token(channel_name: str) -> str:
    """Strips a single leading "V" (the near-universal Voltage-channel
    naming prefix -- "VR", "VAB", "VBUS") before pattern matching, so the
    patterns themselves stay in terms of the bare phase designator. A
    name that doesn't start with "V" (e.g. a raw "BUS VOLTAGE" label) is
    matched as-is -- the explicit-substring check below still finds
    "BUS" regardless."""
    upper = channel_name.strip().upper()
    if upper.startswith("V") and len(upper) > 1:
        return upper[1:]
    return upper


def _classify_one_channel_name(channel_name: str) -> str | None:
    """Returns LINE_TO_LINE/LINE_TO_GROUND for one channel name, or
    `None` if it carries no recognizable phase-naming evidence at all.
    Checked in priority order: phase-PAIR tokens and explicit LL
    vocabulary before any single-phase-letter reading, so a pair name is
    never mis-read via its own leading letter alone."""
    upper = channel_name.strip().upper()
    token = _phase_token(upper)
    if token in _LL_PAIR_TOKENS:
        return LINE_TO_LINE
    if any(marker in upper for marker in _LL_EXPLICIT_SUBSTRINGS):
        return LINE_TO_LINE
    if token in _LG_NEUTRAL_TOKENS:
        return LINE_TO_GROUND
    if token in _LG_SINGLE_TOKENS:
        return LINE_TO_GROUND
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
