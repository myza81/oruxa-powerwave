"""Stateless V-I pair resolution for single-phase power calculated channels.

Given a flat list of source channels, this module identifies candidate
voltage-current measurement pairs for Active/Reactive/Apparent Power
creation (DEC-202).  It uses the same deterministic channel-name role
grammar that ``channel_engineering_identity`` and
``measurement_group_detection`` already rely on — no new name-parsing
grammar is introduced.

Entry point: ``find_vi_pairs()``.

Automatic pairing (``MatchedVIPair``) requires all five conditions:

1. Exactly one Voltage candidate at a (context_hint, phase_token) key.
2. Exactly one Current candidate at the same key.
3. Both channels come from the **same** recording source.
4. Neither channel has an engineering-identity conflict.
5. The voltage channel is not phase-to-phase (line-to-line voltages, whose
   ``name_token_kind == ROLE_TOKEN_KIND_PAIR``, are excluded from single-
   phase pairing per the approved architecture).

Any (context_hint, phase_token) key that has both a voltage and a current
but fails one or more of those conditions yields a ``VIPairCandidate``
requiring explicit user confirmation.

Channels with no recognisable engineering role in their name, and channels
whose ``engineering_type`` is not Voltage or Current, are silently omitted
from the resolver's output — they remain fully available for manual
selection through the existing ``wwCcPowerVoltageSelect`` /
``wwCcPowerCurrentSelect`` dropdowns (Phase A).

Output order is deterministic: automatic pairs first, sorted by
(context_hint, phase_token, source_id, voltage_channel_name); candidates
sorted by the same key.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.domain.channel_engineering_identity import (
    ChannelEngineeringIdentityInput,
    ROLE_TOKEN_KIND_PAIR,
    resolve_channel_engineering_identity,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.domain.voltage_reference import detect_voltage_reference

# Reason codes for candidates_needing_confirmation.  Listed in priority
# order — when multiple reasons apply to a single key, the first one in
# this sequence is reported.
REASON_CONFLICT = "conflict"           # identity conflict on at least one channel
REASON_MULTIPLE_VOLTAGE = "multiple_voltage"  # more than one Voltage at the key
REASON_MULTIPLE_CURRENT = "multiple_current"  # more than one Current at the key
REASON_CROSS_SOURCE = "cross_source"   # V and I come from different sources

_REASON_PRIORITY = (
    REASON_CONFLICT,
    REASON_MULTIPLE_VOLTAGE,
    REASON_MULTIPLE_CURRENT,
    REASON_CROSS_SOURCE,
)


@dataclass(frozen=True, slots=True)
class ChannelPairingInput:
    """One channel offered to the resolver.

    ``source_id`` is the stable recording-source identifier (never
    assumed to be globally unique by channel name alone).  ``engineering_type``
    must already be the resolved broad type string (e.g. ``"Voltage"``,
    ``"Current"``) from ``channel_classification``.
    """

    source_id: str
    channel_name: str
    engineering_type: str
    unit: str | None = None
    phase_label: str | None = None


@dataclass(frozen=True, slots=True)
class VIChannelRef:
    """Stable reference to one channel within a specific source."""

    source_id: str
    channel_name: str


@dataclass(frozen=True, slots=True)
class MatchedVIPair:
    """A deterministic automatic V-I pair — no confirmation needed.

    ``phase_token_kind`` is taken from the voltage channel's own token
    (``"single"`` for V_A/V_R, ``"neutral"`` for V_AN/V_RN,
    ``"l123"`` for V_L1).  Current channels are always ``"single"`` or
    ``"l123"`` (line-to-line current is structurally excluded by
    ``_parse_role_text``).
    """

    source_id: str
    voltage_channel_name: str
    current_channel_name: str
    context_hint: str | None
    phase_token: str
    phase_token_kind: str


@dataclass(frozen=True, slots=True)
class VIPairCandidate:
    """A V-I pairing candidate whose ambiguity requires user confirmation.

    ``voltage_refs`` and ``current_refs`` are the full sets of matching
    candidates so the frontend can present all options.  ``reason``
    names the primary disqualifier from automatic pairing (see REASON_*
    constants).
    """

    context_hint: str | None
    phase_token: str
    voltage_refs: tuple[VIChannelRef, ...]
    current_refs: tuple[VIChannelRef, ...]
    reason: str


@dataclass
class VIPairResolution:
    """Resolver output.

    ``automatic_pairs`` — zero or more pairs that meet all automatic-
    pairing criteria; safe to pre-fill without prompting the engineer.

    ``candidates_needing_confirmation`` — pairs that were found but
    could not be automatically confirmed; the frontend must present
    these for explicit selection before creating a power channel.
    """

    automatic_pairs: list[MatchedVIPair] = field(default_factory=list)
    candidates_needing_confirmation: list[VIPairCandidate] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _ResolvedChannel:
    source_id: str
    channel_name: str
    kind: str        # KIND_VOLTAGE | KIND_CURRENT
    context_hint: str | None
    phase_token: str
    phase_token_kind: str
    has_conflict: bool


def _sort_key(context_hint: str | None, phase_token: str, source_id: str, name: str) -> tuple:
    return (context_hint or "", phase_token, source_id, name)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def find_vi_pairs(channels: list[ChannelPairingInput]) -> VIPairResolution:
    """Identify automatic and candidate V-I pairs from *channels*.

    The function is O(N) in the number of input channels (one identity
    resolution per channel, one hash-map grouping pass).  It is safe to
    call with large lists; the identity resolver itself does only string
    operations, no I/O or regex compilation at call time.

    Channels without a recognisable role token, and channels whose
    ``engineering_type`` is neither Voltage nor Current, are silently
    ignored and remain available for manual selection.
    """
    # Step 1 — resolve engineering identity for every channel.
    resolved: list[_ResolvedChannel] = []
    for ch in channels:
        identity = resolve_channel_engineering_identity(
            ChannelEngineeringIdentityInput(
                name=ch.channel_name,
                engineering_type=ch.engineering_type,
                unit=ch.unit,
                phase_label=ch.phase_label,
            )
        )
        # Only Voltage / Current with a recognised role participate.
        if identity.kind not in (KIND_VOLTAGE, KIND_CURRENT):
            continue
        if not identity.has_role:
            continue
        # Exclude line-to-line voltages (PAIR token kind) from single-phase
        # pairing (approved architecture, requirement 12).
        if identity.kind == KIND_VOLTAGE and identity.name_token_kind == ROLE_TOKEN_KIND_PAIR:
            continue
        resolved.append(
            _ResolvedChannel(
                source_id=ch.source_id,
                channel_name=ch.channel_name,
                kind=identity.kind,
                context_hint=identity.context_hint,
                phase_token=identity.name_raw_token or "",
                phase_token_kind=identity.name_token_kind or "",
                has_conflict=identity.has_conflict,
            )
        )

    # Step 2 — bucket by (context_hint, phase_token) for each kind.
    PairKey = tuple  # (context_hint, phase_token)
    voltage_buckets: dict[PairKey, list[_ResolvedChannel]] = {}
    current_buckets: dict[PairKey, list[_ResolvedChannel]] = {}

    for rc in resolved:
        key: PairKey = (rc.context_hint, rc.phase_token)
        if rc.kind == KIND_VOLTAGE:
            voltage_buckets.setdefault(key, []).append(rc)
        else:
            current_buckets.setdefault(key, []).append(rc)

    # Step 3 — classify each key that appears in both buckets.
    automatic_pairs: list[MatchedVIPair] = []
    candidates: list[VIPairCandidate] = []

    all_keys = set(voltage_buckets) & set(current_buckets)
    for key in sorted(all_keys, key=lambda k: (k[0] or "", k[1])):
        context_hint, phase_token = key
        vs = voltage_buckets[key]
        is_ = current_buckets[key]

        # Determine whether all five automatic-pairing conditions hold.
        has_conflict = any(rc.has_conflict for rc in vs + is_)
        multi_v = len(vs) > 1
        multi_i = len(is_) > 1
        cross_src = (
            not multi_v
            and not multi_i
            and vs[0].source_id != is_[0].source_id
        )
        is_automatic = (
            not has_conflict
            and not multi_v
            and not multi_i
            and not cross_src
        )

        if is_automatic:
            v, i = vs[0], is_[0]
            automatic_pairs.append(
                MatchedVIPair(
                    source_id=v.source_id,
                    voltage_channel_name=v.channel_name,
                    current_channel_name=i.channel_name,
                    context_hint=context_hint,
                    phase_token=phase_token,
                    phase_token_kind=v.phase_token_kind,
                )
            )
        else:
            # Determine primary reason (priority order).
            if has_conflict:
                reason = REASON_CONFLICT
            elif multi_v:
                reason = REASON_MULTIPLE_VOLTAGE
            elif multi_i:
                reason = REASON_MULTIPLE_CURRENT
            else:
                reason = REASON_CROSS_SOURCE

            # OD-4 (DEC-206): all ambiguous candidates require a reliable
            # equipment-context identifier. Without one, the ambiguity cannot
            # be resolved from context alone, and the channels remain accessible
            # only through the Phase A manual-selection fallback.
            if context_hint is None:
                continue

            v_refs = tuple(
                VIChannelRef(source_id=rc.source_id, channel_name=rc.channel_name)
                for rc in sorted(vs, key=lambda rc: (rc.source_id, rc.channel_name))
            )
            i_refs = tuple(
                VIChannelRef(source_id=rc.source_id, channel_name=rc.channel_name)
                for rc in sorted(is_, key=lambda rc: (rc.source_id, rc.channel_name))
            )
            candidates.append(
                VIPairCandidate(
                    context_hint=context_hint,
                    phase_token=phase_token,
                    voltage_refs=v_refs,
                    current_refs=i_refs,
                    reason=reason,
                )
            )

    # Step 4 — stable sort within each output list.
    automatic_pairs.sort(
        key=lambda p: _sort_key(p.context_hint, p.phase_token, p.source_id, p.voltage_channel_name)
    )
    candidates.sort(
        key=lambda c: _sort_key(
            c.context_hint, c.phase_token,
            c.voltage_refs[0].source_id if c.voltage_refs else "",
            c.voltage_refs[0].channel_name if c.voltage_refs else "",
        )
    )

    return VIPairResolution(
        automatic_pairs=automatic_pairs,
        candidates_needing_confirmation=candidates,
    )


# ---------------------------------------------------------------------------
# Three-phase V-I set resolution (Phase E-1, DEC-208)
# ---------------------------------------------------------------------------

THREE_PHASE_CONV_RYB  = "RYB"
THREE_PHASE_CONV_ABC  = "ABC"
THREE_PHASE_CONV_L123 = "L123"

INCOMPLETE_REASON_MISSING_PHASES       = "missing_phases"
INCOMPLETE_REASON_PHASES_NEED_CONFIRM  = "phases_need_confirmation"
INCOMPLETE_REASON_AMBIGUOUS_CONVENTION = "ambiguous_convention"

MISSING_REASON_NOT_FOUND          = "not_found"
MISSING_REASON_NEEDS_CONFIRMATION = "needs_confirmation"

# Phase tokens that exclusively indicate a specific convention.
# The "B" token is shared between RYB and ABC — it is deliberately absent
# from all exclusive sets so a B-only group is treated as ambiguous.
_RYB_EXCLUSIVE  = frozenset({"R", "Y"})
_ABC_EXCLUSIVE  = frozenset({"A", "C"})
_L123_EXCLUSIVE = frozenset({"L1", "L2", "L3"})

# All three tokens required for a complete set, in fixed phase order.
_REQUIRED: dict[str, tuple[str, str, str]] = {
    THREE_PHASE_CONV_RYB:  ("R", "Y", "B"),
    THREE_PHASE_CONV_ABC:  ("A", "B", "C"),
    THREE_PHASE_CONV_L123: ("L1", "L2", "L3"),
}

# Exclusive tokens of OTHER conventions; any of these block a confident
# complete-set extraction (mixed-convention group → ambiguous).
_BLOCKERS: dict[str, frozenset[str]] = {
    THREE_PHASE_CONV_RYB:  _ABC_EXCLUSIVE | _L123_EXCLUSIVE,
    THREE_PHASE_CONV_ABC:  _RYB_EXCLUSIVE | _L123_EXCLUSIVE,
    THREE_PHASE_CONV_L123: _RYB_EXCLUSIVE | _ABC_EXCLUSIVE,
}


@dataclass(frozen=True, slots=True)
class MissingPhaseInfo:
    """Why one expected phase token is absent from a three-phase group."""

    phase_token: str
    reason: str  # MISSING_REASON_*


@dataclass(frozen=True, slots=True)
class ThreePhaseAutomaticSet:
    """A complete, deterministically matched three-phase V-I measurement set."""

    set_id: str
    source_id: str
    context_hint: str | None
    phase_convention: str               # THREE_PHASE_CONV_*
    phase_1: MatchedVIPair              # R | A | L1
    phase_2: MatchedVIPair              # Y | B | L2
    phase_3: MatchedVIPair              # B | C | L3
    voltage_reference: str | None       # LINE_TO_GROUND / LINE_TO_LINE / None
    voltage_reference_reason: str
    voltage_reference_evidence_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThreePhaseIncompleteSet:
    """Partial or ambiguous three-phase group — not yet actionable."""

    source_id: str
    context_hint: str | None
    phase_convention: str | None        # None when ambiguous
    incomplete_reason: str              # INCOMPLETE_REASON_*
    present_pairs: tuple[MatchedVIPair, ...]
    missing_phases: tuple[MissingPhaseInfo, ...]


@dataclass
class ThreePhaseVISetResolution:
    """Output of find_three_phase_vi_sets()."""

    complete_sets: list[ThreePhaseAutomaticSet]
    incomplete_sets: list[ThreePhaseIncompleteSet]
    single_phase_pairs: VIPairResolution


def _make_set_id(context_hint: str | None, source_id: str, convention: str) -> str:
    key = f"{context_hint or ''}:{source_id}:{convention}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"3ph:{digest}"


def _infer_convention(tokens: frozenset[str]) -> str | None:
    """Return the convention inferred from exclusive token evidence, or None if ambiguous."""
    indicators: list[str] = []
    if _RYB_EXCLUSIVE & tokens:
        indicators.append(THREE_PHASE_CONV_RYB)
    if _ABC_EXCLUSIVE & tokens:
        indicators.append(THREE_PHASE_CONV_ABC)
    if _L123_EXCLUSIVE & tokens:
        indicators.append(THREE_PHASE_CONV_L123)
    return indicators[0] if len(indicators) == 1 else None


def _build_missing_phases(
    context_hint: str | None,
    source_id: str,
    missing_tokens: frozenset[str],
    candidate_index: dict[tuple, list[VIPairCandidate]],
) -> list[MissingPhaseInfo]:
    """Build per-phase missing info, checking source-specific candidate presence."""
    result = []
    for token in sorted(missing_tokens):
        key = (context_hint, token)
        candidates = candidate_index.get(key, [])
        has_source_candidate = any(
            any(vr.source_id == source_id for vr in c.voltage_refs)
            and any(cr.source_id == source_id for cr in c.current_refs)
            for c in candidates
        )
        reason = (
            MISSING_REASON_NEEDS_CONFIRMATION
            if has_source_candidate
            else MISSING_REASON_NOT_FOUND
        )
        result.append(MissingPhaseInfo(phase_token=token, reason=reason))
    return result


def _incomplete_reason_code(missing_phases: list[MissingPhaseInfo]) -> str:
    if any(mp.reason == MISSING_REASON_NEEDS_CONFIRMATION for mp in missing_phases):
        return INCOMPLETE_REASON_PHASES_NEED_CONFIRM
    return INCOMPLETE_REASON_MISSING_PHASES


def find_three_phase_vi_sets(
    channels: list[ChannelPairingInput],
) -> ThreePhaseVISetResolution:
    """Identify complete and incomplete three-phase V-I measurement sets.

    Calls find_vi_pairs() for single-phase resolution, then groups the
    automatic pairs by (context_hint, source_id).  Null-context groups
    are included when all pairs are individually auto-resolved from the
    same source (DEC-206 null-context exclusion applies only to
    candidates, not automatic pairs).

    The single_phase_pairs field carries the unmodified VIPairResolution
    — existing single-phase behaviour is entirely preserved.
    """
    pair_resolution = find_vi_pairs(channels)

    # Build candidate index keyed by (context_hint, phase_token) — O(N) once,
    # O(1) per missing-phase lookup with source_id filtering.
    candidate_index: dict[tuple, list[VIPairCandidate]] = {}
    for cand in pair_resolution.candidates_needing_confirmation:
        k = (cand.context_hint, cand.phase_token)
        candidate_index.setdefault(k, []).append(cand)

    # Group automatic pairs by (context_hint, source_id).
    groups: dict[tuple, list[MatchedVIPair]] = {}
    for pair in pair_resolution.automatic_pairs:
        gk = (pair.context_hint, pair.source_id)
        groups.setdefault(gk, []).append(pair)

    complete_sets: list[ThreePhaseAutomaticSet] = []
    incomplete_sets: list[ThreePhaseIncompleteSet] = []

    for (context_hint, source_id), group_pairs in groups.items():
        tokens: frozenset[str] = frozenset(p.phase_token for p in group_pairs)
        pair_by_token: dict[str, MatchedVIPair] = {p.phase_token: p for p in group_pairs}

        extracted_conv: str | None = None

        if len(group_pairs) >= 3:
            for conv, (t1, t2, t3) in _REQUIRED.items():
                required = frozenset((t1, t2, t3))
                if required <= tokens and not (_BLOCKERS[conv] & tokens):
                    ph1, ph2, ph3 = pair_by_token[t1], pair_by_token[t2], pair_by_token[t3]
                    det = detect_voltage_reference([
                        ph1.voltage_channel_name,
                        ph2.voltage_channel_name,
                        ph3.voltage_channel_name,
                    ])
                    complete_sets.append(ThreePhaseAutomaticSet(
                        set_id=_make_set_id(context_hint, source_id, conv),
                        source_id=source_id,
                        context_hint=context_hint,
                        phase_convention=conv,
                        phase_1=ph1,
                        phase_2=ph2,
                        phase_3=ph3,
                        voltage_reference=det.reference,
                        voltage_reference_reason=det.reason,
                        voltage_reference_evidence_names=tuple(det.evidence_names),
                    ))
                    extracted_conv = conv
                    break  # At most one convention satisfies both conditions.

        if extracted_conv is not None:
            # Extra pairs beyond the 3-phase set remain in single_phase_pairs only.
            continue

        # Incomplete set — determine convention and missing-phase details.
        conv = _infer_convention(tokens)
        if conv is not None:
            required_set: frozenset[str] = frozenset(_REQUIRED[conv])
            missing = _build_missing_phases(
                context_hint, source_id,
                required_set - tokens,
                candidate_index,
            )
            reason = _incomplete_reason_code(missing)
            incomplete_sets.append(ThreePhaseIncompleteSet(
                source_id=source_id,
                context_hint=context_hint,
                phase_convention=conv,
                incomplete_reason=reason,
                present_pairs=tuple(sorted(group_pairs, key=lambda p: p.phase_token)),
                missing_phases=tuple(missing),
            ))
        else:
            incomplete_sets.append(ThreePhaseIncompleteSet(
                source_id=source_id,
                context_hint=context_hint,
                phase_convention=None,
                incomplete_reason=INCOMPLETE_REASON_AMBIGUOUS_CONVENTION,
                present_pairs=tuple(sorted(group_pairs, key=lambda p: p.phase_token)),
                missing_phases=(),
            ))

    complete_sets.sort(key=lambda s: (s.context_hint or "", s.source_id, s.phase_convention))
    incomplete_sets.sort(key=lambda s: (s.context_hint or "", s.source_id, s.phase_convention or ""))

    return ThreePhaseVISetResolution(
        complete_sets=complete_sets,
        incomplete_sets=incomplete_sets,
        single_phase_pairs=pair_resolution,
    )
