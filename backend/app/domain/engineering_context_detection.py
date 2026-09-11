"""Deterministic Automatic Engineering Context (bay) Detection (Analysis
Guardrail Slice 1; see docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md,
"Engineering Context detection").

Pure, framework-free pattern matching over channel NAMES + already-
classified `engineering_type` (+ optional structured source phase
metadata) -- the exact same deliberate restraint
`app.domain.measurement_group_detection` already established for
Measurement Groups: never a probabilistic classifier, never waveform-
magnitude analysis.

**How this differs from `measurement_group_detection`**: that module
clusters channels sharing one `(base_name, kind)` -- Voltage and Current
clusters are built and returned completely independently, by design (it
answers "which channels form one measurement BANK of a single kind").
This module asks a different, cross-kind question -- "which channels,
Voltage AND Current together, represent one physical piece of EQUIPMENT"
-- so it strips one further trailing letter (the kind marker "V"/"I")
off the same phase-stripped base name to compute a shared ROOT, and
clusters `ALPHA1_VA`/`ALPHA1_VB`/`ALPHA1_VC`/`ALPHA1_IA`/`ALPHA1_IB`/
`ALPHA1_IC` into ONE candidate context keyed only by that root
(`ALPHA1_`), never by `(root, kind)`.

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

from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    kind_for_engineering_type,
)
from app.domain.phase_identity import (
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_UNKNOWN,
    infer_phase_convention,
    normalize_phase_token,
)

#: Locally-owned phase-suffix vocabulary -- deliberately a SEPARATE copy
#: from `measurement_group_detection`'s own (see that module's own
#: docstring for why each module owns its own copy rather than sharing
#: one), extended with the L1/L2/L3 convention this new module also
#: needs to recognize (Measurement Group detection never needed it, since
#: it never normalizes to a canonical A/B/C phase -- it only clusters by
#: raw suffix token).
_PAIR_TOKENS = frozenset({"RY", "YR", "YB", "BY", "BR", "RB", "AB", "BA", "BC", "CB", "CA", "AC"})
_NEUTRAL_TOKENS = frozenset({"RN", "YN", "BN", "AN", "CN"})
_SINGLE_TOKENS = frozenset({"R", "Y", "B", "A", "C"})
_L123_TOKENS = frozenset({"L1", "L2", "L3"})

_KIND_PREFIX_LETTER = {KIND_VOLTAGE: "V", KIND_CURRENT: "I"}
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


def _strip_phase_suffix(channel_name: str, kind: str) -> tuple[str, str, str, str] | None:
    """Returns `(base_name, raw_token, token_kind, original_label)` for a
    recognized trailing phase suffix parsed from the NAME itself, else
    `None`. `raw_token` is already normalization-ready (neutral's
    trailing "N" stripped to its bare letter); `original_label` preserves
    the exact original-case substring matched, for display. Longer
    tokens are checked before shorter ones for the same reason
    `measurement_group_detection._strip_phase_suffix` checks 2-character
    tokens first -- a name like "VRY" must never be mis-read as a bare
    "Y" reading with a stray leading "VR"."""
    stripped_input = channel_name.strip()
    upper = stripped_input.upper()
    if not upper:
        return None
    if kind == KIND_VOLTAGE:
        for token in _PAIR_TOKENS:
            if len(upper) > len(token) and upper.endswith(token):
                original = stripped_input[-len(token):]
                return upper[: -len(token)], token, "pair", original
    for token in _L123_TOKENS:
        if len(upper) > len(token) and upper.endswith(token):
            original = stripped_input[-len(token):]
            return upper[: -len(token)], token, "l123", original
    for token in _NEUTRAL_TOKENS:
        if len(upper) > len(token) and upper.endswith(token):
            original = stripped_input[-len(token):]
            return upper[: -len(token)], token[:-1], "neutral", original
    for token in _SINGLE_TOKENS:
        if len(upper) > len(token) and upper.endswith(token):
            original = stripped_input[-1:]
            return upper[:-1], token, "single", original
    return None


def _match_structured_label(phase_label: str | None, kind: str) -> tuple[str, str] | None:
    """Attempts to recognize `phase_label` (structured source metadata,
    e.g. a COMTRADE `ph` field) directly as a phase token, independent of
    any channel name. Returns `(raw_token, token_kind)` (same
    normalization-ready shape `_strip_phase_suffix` returns) if
    recognized, else `None` -- never guesses at a value this module does
    not recognize."""
    if not phase_label or not phase_label.strip():
        return None
    upper = phase_label.strip().upper()
    if upper in _L123_TOKENS:
        return upper, "l123"
    if upper in _SINGLE_TOKENS:
        return upper, "single"
    if upper in _NEUTRAL_TOKENS:
        return upper[:-1], "neutral"
    if kind == KIND_VOLTAGE and upper in _PAIR_TOKENS:
        return upper, "pair"
    return None


def _root_name(base_name: str, kind: str) -> str | None:
    """Strips the ONE trailing kind-marker letter ("V"/"I") a
    phase-stripped base name ends with, to get the cross-kind clustering
    key. Returns `None` (channel excluded from context detection
    entirely) if the base name does not end with its own kind's marker
    letter, or if nothing would remain -- there is no reliable bay
    prefix to cluster on in either case, and this module never forces a
    channel into a bogus/empty-rooted context."""
    letter = _KIND_PREFIX_LETTER[kind]
    if not base_name.endswith(letter):
        return None
    root = base_name[:-1]
    return root or None


def _rootless_context_key(base_name: str, kind: str) -> str | None:
    """Returns the one source-local fallback key for bare role names.

    This is deliberately narrower than "_root_name returned None": only a
    phase-stripped base that is exactly the kind marker ("V" or "I") is a
    bare engineering role such as VA/VB/VC or IA/IB/IC. Other unrooted or
    malformed names remain excluded.
    """
    return _ROOTLESS_CONTEXT_KEY if base_name == _KIND_PREFIX_LETTER[kind] else None


def _evidence_letters(raw_token: str, token_kind: str) -> list[str]:
    if token_kind == "pair":
        return [raw_token[0], raw_token[1]]
    return [raw_token]


def _display_name(root: str) -> str:
    if root == _ROOTLESS_CONTEXT_KEY:
        return _ROOTLESS_CONTEXT_DISPLAY_NAME
    trimmed = root.rstrip("_- ").strip()
    return trimmed if trimmed else "Engineering Context"


def detect_engineering_contexts(channels: list[ChannelForDetection]) -> list[DetectedContext]:
    """The one deterministic detection entry point. `channels` is one
    source's own channel list, in source order. Non-Voltage/Current
    channels, and any channel with no recognizable phase suffix in its
    OWN NAME (structured metadata alone is never enough to place a
    channel into a cluster -- see module docstring: clustering is always
    name-derived, only the resulting PHASE VALUE may come from metadata),
    are silently excluded -- never forced into a context.

    Within one root cluster: a convention (A/B/C, R/Y/B, or L1/L2/L3) is
    inferred once from the combined evidence of every member's own
    resolved token (`app.domain.phase_identity.infer_phase_convention`);
    every member's canonical phase is then normalized under that one
    shared convention. `STATUS_NEEDS_REVIEW` (never silently resolved) is
    used whenever: (a) any member's own phase could not be confidently
    normalized (no convention evidence, e.g. a lone ambiguous "B"), or
    (b) two or more members resolved to the exact same
    (engineering_type, canonical phase) pair -- a suspicious duplicate,
    the cross-kind analogue of `measurement_group_detection`'s own
    duplicate-phase-token guard. Otherwise `STATUS_SUGGESTED`.

    Deterministic iteration/output order (insertion order of the input
    list), never randomized.
    """
    clusters: dict[str, list[_Matched]] = {}
    for ch in channels:
        kind = kind_for_engineering_type(ch.engineering_type)
        if kind is None:
            continue
        stripped = _strip_phase_suffix(ch.name, kind)
        if stripped is None:
            continue
        base_name, name_raw_token, name_token_kind, name_original_label = stripped
        root = _root_name(base_name, kind)
        if root is None:
            root = _rootless_context_key(base_name, kind)
            if root is None:
                continue

        structured = _match_structured_label(ch.phase_label, kind)
        if structured is not None:
            raw_token, token_kind = structured
            phase_source = PHASE_SOURCE_STRUCTURED_METADATA
            original_label = ch.phase_label.strip() if ch.phase_label else ""
        else:
            raw_token, token_kind = name_raw_token, name_token_kind
            phase_source = PHASE_SOURCE_DETECTED_FROM_NAME
            original_label = name_original_label

        clusters.setdefault(root, []).append(
            _Matched(
                name=ch.name,
                engineering_type=ch.engineering_type,
                raw_token=raw_token,
                token_kind=token_kind,
                phase_source=phase_source,
                original_label=original_label,
            )
        )

    detected: list[DetectedContext] = []
    for root, matched in clusters.items():
        evidence_letters = [
            letter for m in matched for letter in _evidence_letters(m.raw_token, m.token_kind)
        ]
        convention = infer_phase_convention(evidence_letters)

        members: list[DetectedContextMember] = []
        for m in matched:
            canonical_phase = normalize_phase_token(m.raw_token, convention)
            members.append(
                DetectedContextMember(
                    channel_name=m.name,
                    engineering_type=m.engineering_type,
                    phase=canonical_phase,
                    phase_source=m.phase_source,
                    original_phase_label=m.original_label,
                )
            )

        has_unresolved_phase = any(mem.phase == PHASE_UNKNOWN for mem in members)
        seen_roles: set[tuple[str, str]] = set()
        has_duplicate_role = False
        for mem in members:
            if mem.phase == PHASE_UNKNOWN:
                continue
            role = (mem.engineering_type, mem.phase)
            if role in seen_roles:
                has_duplicate_role = True
            seen_roles.add(role)

        status = STATUS_NEEDS_REVIEW if (has_unresolved_phase or has_duplicate_role) else STATUS_SUGGESTED
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
