"""Deterministic Automatic Measurement-Group Detection (Slice 2 of
DEC-050's measurement-group-aware Per-Unit redesign; see
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md section 15,
"Automatic grouping principle" / "Grouping lifecycle").

Pure, framework-free grouping over shared
`app.domain.channel_engineering_identity` results (already-classified
`engineering_type`, optional unit evidence, and deterministic
channel-name role grammar) -- never a probabilistic classifier, never
waveform-magnitude analysis, mirroring the same deliberate
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

from app.domain.channel_engineering_identity import (
    ChannelEngineeringIdentityInput,
    REPRESENTATION_PAIR,
    resolve_channel_engineering_identity,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    kind_for_engineering_type,
)

_PAIR_TOKEN_KIND = "pair"

_KIND_DISPLAY_SUFFIX = {KIND_VOLTAGE: "VOLTAGE", KIND_CURRENT: "CURRENT"}


@dataclass(slots=True)
class _MatchedChannel:
    name: str
    phase_token: str
    token_kind: str  # "single" | "neutral" | "pair"
    has_identity_conflict: bool = False


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


def _display_name(context_hint: str | None, kind: str) -> str:
    """A simple, cosmetic heuristic label -- never identity (canonical
    document section 8), freely renamable later once a UI exists
    (Slice 6; section 8 also explicitly says not to build renaming
    logic yet, so this is intentionally minimal). Appends the kind's own
    display suffix to the shared identity context hint."""
    trimmed = (context_hint or "").rstrip("_- ").strip()
    suffix = _KIND_DISPLAY_SUFFIX[kind]
    return f"{trimmed} {suffix}" if trimmed else suffix


def detect_measurement_groups(channels: list[tuple[str, str] | tuple[str, str, str | None]]) -> list[DetectedGroup]:
    """The one deterministic detection entry point. `channels` is a
    source's own `(channel_name, engineering_type[, unit])` tuples, in
    source order -- callers pass `[(ch.name, ch.engineering_type,
    ch.unit) for ch in active.metadata.analog_channels]` (see
    `measurement_group_service.generate_suggested_groups_for_source()`).

    Non-Voltage/Current channels, and any channel with no deterministic
    engineering role in its name, are silently excluded from clustering
    (never forced into a group). Channels sharing one `(context_hint,
    kind)` cluster are `STATUS_SUGGESTED` when every member's own phase
    token is unique within the cluster and every member's representation
    (phase-to-reference vs. phase-to-phase) agrees; `STATUS_NEEDS_REVIEW`
    otherwise -- contradictory automatic evidence must never silently
    pick a winner. Iteration and output order are both deterministic
    (insertion order of the input list), never randomized.
    """
    clusters: dict[tuple[str | None, str], list[_MatchedChannel]] = {}
    for channel in channels:
        channel_name, engineering_type = channel[0], channel[1]
        unit = channel[2] if len(channel) > 2 else None
        kind = kind_for_engineering_type(engineering_type)
        if kind is None:
            continue
        identity = resolve_channel_engineering_identity(
            ChannelEngineeringIdentityInput(name=channel_name, engineering_type=engineering_type, unit=unit)
        )
        if not identity.has_role or identity.kind != kind:
            continue
        clusters.setdefault((identity.context_hint, kind), []).append(
            _MatchedChannel(
                name=channel_name,
                phase_token=identity.name_raw_token or "",
                token_kind=identity.name_token_kind or "",
                has_identity_conflict=identity.has_conflict,
            )
        )

    detected: list[DetectedGroup] = []
    for (context_hint, kind), members in clusters.items():
        phase_tokens = [member.phase_token for member in members]
        has_duplicate_phase = len(phase_tokens) != len(set(phase_tokens))
        representations = {
            REPRESENTATION_PAIR if member.token_kind == _PAIR_TOKEN_KIND else "reference" for member in members
        }
        has_mixed_representation = len(representations) > 1
        has_identity_conflict = any(member.has_identity_conflict for member in members)
        status = STATUS_NEEDS_REVIEW if (has_duplicate_phase or has_mixed_representation or has_identity_conflict) else STATUS_SUGGESTED
        channel_names = [member.name for member in members]
        detected.append(
            DetectedGroup(
                kind=kind,
                display_name=_display_name(context_hint, kind),
                channel_names=channel_names,
                status=status,
                evidence=list(channel_names),
            )
        )
    return detected
