"""Deterministic Automatic Engineering Context (bay) Detection (Analysis
Guardrail Slice 1; see docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md,
"Engineering Context detection").

Pure, framework-free grouping over shared
`app.domain.channel_engineering_identity` results (already-classified
`engineering_type`, optional unit evidence, optional structured source
phase metadata, and deterministic channel-name role grammar) -- the same
deliberate restraint
`app.domain.measurement_group_detection` already established for
Measurement Groups: never a probabilistic classifier, never waveform-
magnitude analysis.

**How this differs from `measurement_group_detection`**: that module
clusters channels sharing one `(base_name, kind)` -- Voltage and Current
clusters are built and returned completely independently, by design (it
answers "which channels form one measurement BANK of a single kind").
This module asks a different, cross-kind question -- "which channels,
Voltage AND Current together, represent one physical piece of EQUIPMENT"
-- so it clusters compatible shared identity `context_hint` values into
ONE candidate context: `ALPHA1_VA`/`ALPHA1_IA`, `VR JMHE NO1`/
`IR JMHE NO1`, and `UR JMHE NO1 (kV)`/`IR JMHE NO1 (kA)` all share the
same bay hint. Measurement Group detection still groups by
`(context_hint, kind)`, so the grouping semantics remain separate.

**Single-source only.** This function's own input is one source's own
channel list, exactly like `measurement_group_detection`'s entry point --
it NEVER attempts cross-source bay merging. This is a deliberate Slice 1
scope choice (owner instruction: "Be conservative about automatically
merging across sources... do not silently merge bays across files purely
because prefixes match"): the safest way to guarantee that is to never
let the automatic detector look at more than one source's channels at
once. A multi-source `EngineeringContext` is fully representable by the
domain model (`app.domain.engineering_context`) and constructible through
`app.services.engineering_context_service.update_context_membership()`
-- just never produced automatically by this module.

A detected candidate is always `STATUS_SUGGESTED` or `STATUS_NEEDS_REVIEW`
-- **never `STATUS_CONFIRMED`/`STATUS_MANUAL`**, matching
`measurement_group_detection`'s own reserved-for-an-engineer's-own-action
rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.channel_engineering_identity import (
    ChannelEngineeringIdentityInput,
    identity_evidence_letters,
    resolve_channel_engineering_identity,
)
from app.domain.measurement_group import (
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
)
from app.domain.phase_identity import (
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_UNKNOWN,
    infer_phase_convention,
    normalize_phase_token,
)

_ROOTLESS_CONTEXT_KEY = "__rootless_default_context__"
_ROOTLESS_CONTEXT_DISPLAY_NAME = "Default Context"


@dataclass(frozen=True, slots=True)
class ChannelForDetection:
    """One source channel's own detection input. `phase_label` is the
    channel's OWN structured source metadata (e.g.
    `AnalogChannelSummary.phase`, COMTRADE's raw `ph` field) -- optional,
    and used as phase evidence ONLY when it independently normalizes to a
    recognized token (see module docstring's precedence rule); never
    trusted blindly."""

    name: str
    engineering_type: str
    phase_label: str | None = None
    unit: str | None = None


@dataclass(slots=True)
class DetectedContextMember:
    channel_name: str
    engineering_type: str
    phase: str
    phase_source: str
    original_phase_label: str | None


@dataclass(slots=True)
class DetectedContext:
    display_name: str
    status: str
    members: list[DetectedContextMember] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _Matched:
    name: str
    engineering_type: str
    raw_token: str  # normalization-ready form: bare letter for single/neutral (neutral's own trailing "N" already stripped), the 2-char pair, or "L1"/"L2"/"L3"
    token_kind: str  # "single" | "neutral" | "pair" | "l123"
    phase_source: str
    original_label: str
    # The token parsed from the channel NAME, kept even when structured
    # metadata supplied the phase (see _names_agree_with_structured_phases()).
    name_raw_token: str
    name_token_kind: str
    name_original_label: str
    issues: list[str] = field(default_factory=list)


def _display_name(root: str) -> str:
    if root == _ROOTLESS_CONTEXT_KEY:
        return _ROOTLESS_CONTEXT_DISPLAY_NAME
    trimmed = root.rstrip("_- ").strip()
    return trimmed if trimmed else "Engineering Context"


def _names_agree_with_structured_phases(matched: list[_Matched], phases: list[str], name_convention: str | None) -> bool:
    """`original_phase_label` is the ENGINEER-FACING label (DEC-118 derives
    the display convention from it). Structured metadata may supply the
    PHASE -- e.g. a COMTRADE `ph` of "A" on a channel named "KPDN2 VR" --
    but the engineer reads the name's own "R". The names become the
    display labels only when, read under their own inferred convention,
    they resolve to the SAME canonical phase as the metadata for EVERY
    structured member of the cluster. Any disagreement, or names that
    establish no convention on their own (a lone "B"), keeps the metadata
    labels exactly as before. Never changes `phase`."""
    structured = [(m, phase) for m, phase in zip(matched, phases)
                  if m.phase_source == PHASE_SOURCE_STRUCTURED_METADATA and phase != PHASE_UNKNOWN]
    return bool(structured) and all(normalize_phase_token(m.name_raw_token, name_convention) == phase for m, phase in structured)


def detect_engineering_contexts(channels: list[ChannelForDetection]) -> list[DetectedContext]:
    """The one deterministic detection entry point. `channels` is one
    source's own channel list, in source order. Non-Voltage/Current
    channels, and any channel with no deterministic engineering role in
    its OWN NAME (structured metadata alone is never enough to place a
    channel into a cluster -- clustering is always name-derived, only the
    resulting PHASE VALUE may come from metadata), are silently excluded
    -- never forced into a context.

    Within one root cluster: a convention (A/B/C, R/Y/B, or L1/L2/L3) is
    inferred once from the combined evidence of every member's own
    resolved token (`app.domain.phase_identity.infer_phase_convention`);
    every member's canonical phase is then normalized under that one
    shared convention. `STATUS_NEEDS_REVIEW` (never silently resolved) is
    used whenever: (a) any member's own phase could not be confidently
    normalized (no convention evidence, e.g. a lone ambiguous "B"), (b)
    two or more members resolved to the exact same (engineering_type,
    canonical phase) pair, or (c) identity evidence conflicts (for
    example a Voltage-looking `UR` role on a Current/kA channel).
    Otherwise `STATUS_SUGGESTED`.

    Deterministic iteration/output order (insertion order of the input
    list), never randomized.
    """
    clusters: dict[str, list[_Matched]] = {}
    for ch in channels:
        identity = resolve_channel_engineering_identity(
            ChannelEngineeringIdentityInput(
                name=ch.name,
                engineering_type=ch.engineering_type,
                phase_label=ch.phase_label,
                unit=ch.unit,
            )
        )
        if identity.kind is None or not identity.has_role:
            continue
        root = identity.context_hint or _ROOTLESS_CONTEXT_KEY

        clusters.setdefault(root, []).append(
            _Matched(
                name=ch.name,
                engineering_type=ch.engineering_type,
                raw_token=identity.phase_raw_token or "",
                token_kind=identity.phase_token_kind or "",
                phase_source=identity.phase_source or PHASE_SOURCE_DETECTED_FROM_NAME,
                original_label=identity.original_phase_label or "",
                name_raw_token=identity.name_raw_token or "",
                name_token_kind=identity.name_token_kind or "",
                name_original_label=identity.name_original_label or "",
                issues=list(identity.issues),
            )
        )

    detected: list[DetectedContext] = []
    for root, matched in clusters.items():
        evidence_letters = [
            letter for m in matched for letter in identity_evidence_letters(m.raw_token, m.token_kind)
        ]
        convention = infer_phase_convention(evidence_letters)
        # The names' own convention, inferred from the names alone (the
        # same no-guessing rule: a lone "B" establishes nothing).
        name_convention = infer_phase_convention(
            [letter for m in matched for letter in identity_evidence_letters(m.name_raw_token, m.name_token_kind)]
        )

        phases = [normalize_phase_token(m.raw_token, convention) for m in matched]
        names_agree = _names_agree_with_structured_phases(matched, phases, name_convention)

        members: list[DetectedContextMember] = []
        for m, canonical_phase in zip(matched, phases):
            label = m.name_original_label if names_agree and m.phase_source == PHASE_SOURCE_STRUCTURED_METADATA else m.original_label
            members.append(
                DetectedContextMember(
                    channel_name=m.name,
                    engineering_type=m.engineering_type,
                    phase=canonical_phase,
                    phase_source=m.phase_source,
                    original_phase_label=label,
                )
            )

        has_unresolved_phase = any(mem.phase == PHASE_UNKNOWN for mem in members)
        has_identity_conflict = any(m.issues for m in matched)
        seen_roles: set[tuple[str, str]] = set()
        has_duplicate_role = False
        for mem in members:
            if mem.phase == PHASE_UNKNOWN:
                continue
            role = (mem.engineering_type, mem.phase)
            if role in seen_roles:
                has_duplicate_role = True
            seen_roles.add(role)

        status = STATUS_NEEDS_REVIEW if (has_unresolved_phase or has_duplicate_role or has_identity_conflict) else STATUS_SUGGESTED
        channel_names = [mem.channel_name for mem in members]
        detected.append(
            DetectedContext(
                display_name=_display_name(root),
                status=status,
                members=members,
                evidence=list(channel_names),
            )
        )
    return detected
