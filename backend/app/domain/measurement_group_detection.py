"""Deterministic Automatic Measurement-Group Detection (Slice 2 of
DEC-050's measurement-group-aware Per-Unit redesign; see
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md section 15,
"Automatic grouping principle" / "Grouping lifecycle").

Pure, framework-free pattern matching over channel NAMES + already-
classified `engineering_type` only -- never a probabilistic classifier,
never waveform-magnitude analysis, mirroring the same deliberate
restraint `app.domain.voltage_reference`'s own detector already
established. **This module is deliberately independent of
`voltage_reference.py`, and never imports from it**: that module
answers "is a voltage group's own measurement reference phase-to-
ground or phase-to-line" (Slice 3 scope, used only to derive Ibase);
this module answers a different, earlier question -- "which channels,
together, represent one measurement context at all" (grouping). Slice
2 never determines or stores a voltage reference; it only clusters
channel names.

The one entry point, `detect_measurement_groups()`, takes a source's
own `(channel_name, engineering_type)` pairs and returns candidate
`DetectedGroup` records -- pure evidence, never a `MeasurementGroup`
and never persisted by this module (persistence, source-existence
validation, and the create-only-through-`create_group()` requirement
all live in `app.services.measurement_group_service.
generate_suggested_groups_for_source()`, which is the only caller of
this function that is expected to exist).

A detected cluster is always `STATUS_SUGGESTED` or `STATUS_NEEDS_REVIEW`
-- **never `STATUS_CONFIRMED`**, which canonical document section 15's
own grouping lifecycle reserves exclusively for an engineer's own
review/save action; nothing automatic may ever reach it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    kind_for_engineering_type,
)

#: Phase-suffix vocabulary for GROUPING purposes only -- deliberately a
#: separate, locally-owned copy, not imported from
#: `app.domain.voltage_reference`'s own token sets (see module
#: docstring: same underlying phase-naming conventions, different
#: question being asked of them). Pair tokens (phase-to-phase) are only
#: ever meaningful for Voltage channels -- Current has no line-to-line
#: concept, so `_strip_phase_suffix()` never checks them for a Current
#: channel.
_PAIR_TOKENS = frozenset({"RY", "YR", "YB", "BY", "BR", "RB", "AB", "BA", "BC", "CB", "CA", "AC"})
_NEUTRAL_TOKENS = frozenset({"RN", "YN", "BN", "AN", "CN"})
_SINGLE_TOKENS = frozenset({"R", "Y", "B", "A", "C"})

#: Coarse representation bucket used only to decide whether a cluster's
#: OWN evidence is internally consistent -- a single-letter ("R") and an
#: explicit-neutral ("RN") suffix are both phase-to-*reference* evidence
#: and never conflict with each other; a pair suffix ("RY") is
#: phase-to-*phase* evidence. Mixing the two representations within one
#: cluster is the grouping-level analogue of `voltage_reference.py`'s
#: own "LL evidence and LG evidence both present" conflict -- flagged
#: `STATUS_NEEDS_REVIEW`, never silently resolved one way.
_REFERENCE_TOKEN_KINDS = frozenset({"single", "neutral"})
_PAIR_TOKEN_KIND = "pair"

_KIND_DISPLAY_SUFFIX = {KIND_VOLTAGE: "VOLTAGE", KIND_CURRENT: "CURRENT"}
_KIND_PREFIX_LETTER = {KIND_VOLTAGE: "V", KIND_CURRENT: "I"}


@dataclass(slots=True)
class _MatchedChannel:
    name: str
    phase_token: str
    token_kind: str  # "single" | "neutral" | "pair"


@dataclass(slots=True)
class DetectedGroup:
    """One candidate measurement group discovered by
    `detect_measurement_groups()`. `status` is always `STATUS_SUGGESTED`
    (internally consistent phase evidence) or `STATUS_NEEDS_REVIEW`
    (an internal conflict was found) -- never `STATUS_CONFIRMED`.
    `evidence` lists the exact channel names that produced this
    cluster, in source order, mirroring
    `VoltageReferenceDetection.evidence_names`'s own transparency
    convention."""

    kind: str
    display_name: str
    channel_names: list[str]
    status: str
    evidence: list[str] = field(default_factory=list)


def _strip_phase_suffix(channel_name: str, kind: str) -> tuple[str, str, str] | None:
    """Returns `(base_name, phase_token, token_kind)` for a recognized
    trailing phase suffix, else `None` (channel excluded from automatic
    detection entirely -- never forced into a bogus single-channel
    group; canonical document section 15's own "productivity feature,
    not final authority" framing). Longer (2-character) tokens are
    checked before the 1-character single-phase tokens so a name like
    "VRY" is never mis-read as a bare "Y" reading with a stray leading
    "VR" -- the same ordering discipline
    `voltage_reference._classify_one_channel_name()` uses, deliberately
    reimplemented here rather than imported (see module docstring).
    Requires at least one character of the name to remain after
    stripping, so a channel literally named just "R" (no distinguishing
    prefix at all) is left ungrouped rather than clustered under an
    empty, meaningless base name."""
    upper = channel_name.strip().upper()
    if not upper:
        return None
    if kind == KIND_VOLTAGE:
        for token in _PAIR_TOKENS:
            if len(upper) > len(token) and upper.endswith(token):
                return upper[: -len(token)], token, "pair"
    for token in _NEUTRAL_TOKENS:
        if len(upper) > len(token) and upper.endswith(token):
            return upper[: -len(token)], token, "neutral"
    for token in _SINGLE_TOKENS:
        if len(upper) > len(token) and upper.endswith(token):
            return upper[:-1], token, "single"
    return None


def _display_name(base_name: str, kind: str) -> str:
    """A simple, cosmetic heuristic label -- never identity (canonical
    document section 8), freely renamable later once a UI exists
    (Slice 6; section 8 also explicitly says not to build renaming
    logic yet, so this is intentionally minimal). Drops one redundant
    trailing type-marker letter ("V"/"I") if the stripped base name
    happens to end with it (e.g. "IBT1 HV I" -> "IBT1 HV"), then
    appends the kind's own display suffix."""
    trimmed = base_name.rstrip()
    prefix_letter = _KIND_PREFIX_LETTER[kind]
    if trimmed.endswith(prefix_letter):
        trimmed = trimmed[:-1].rstrip()
    trimmed = trimmed.rstrip("_- ").strip()
    suffix = _KIND_DISPLAY_SUFFIX[kind]
    return f"{trimmed} {suffix}" if trimmed else suffix


def detect_measurement_groups(channels: list[tuple[str, str]]) -> list[DetectedGroup]:
    """The one deterministic detection entry point. `channels` is a
    source's own `(channel_name, engineering_type)` pairs, in source
    order -- callers pass `[(ch.name, ch.engineering_type) for ch in
    active.metadata.analog_channels]` (see
    `measurement_group_service.generate_suggested_groups_for_source()`).

    Non-Voltage/Current channels, and any channel with no recognizable
    phase suffix, are silently excluded from clustering (never forced
    into a group). Channels sharing one `(base_name, kind)` cluster are
    `STATUS_SUGGESTED` when every member's own phase token is unique
    within the cluster and every member's representation (phase-to-
    reference vs. phase-to-phase) agrees; `STATUS_NEEDS_REVIEW`
    otherwise -- contradictory automatic evidence must never silently
    pick a winner. Iteration and output order are both deterministic
    (insertion order of the input list), never randomized.
    """
    clusters: dict[tuple[str, str], list[_MatchedChannel]] = {}
    for channel_name, engineering_type in channels:
        kind = kind_for_engineering_type(engineering_type)
        if kind is None:
            continue
        stripped = _strip_phase_suffix(channel_name, kind)
        if stripped is None:
            continue
        base_name, phase_token, token_kind = stripped
        clusters.setdefault((base_name, kind), []).append(
            _MatchedChannel(name=channel_name, phase_token=phase_token, token_kind=token_kind)
        )

    detected: list[DetectedGroup] = []
    for (base_name, kind), members in clusters.items():
        phase_tokens = [member.phase_token for member in members]
        has_duplicate_phase = len(phase_tokens) != len(set(phase_tokens))
        representations = {
            _PAIR_TOKEN_KIND if member.token_kind == _PAIR_TOKEN_KIND else "reference" for member in members
        }
        has_mixed_representation = len(representations) > 1
        status = STATUS_NEEDS_REVIEW if (has_duplicate_phase or has_mixed_representation) else STATUS_SUGGESTED
        channel_names = [member.name for member in members]
        detected.append(
            DetectedGroup(
                kind=kind,
                display_name=_display_name(base_name, kind),
                channel_names=channel_names,
                status=status,
                evidence=list(channel_names),
            )
        )
    return detected
