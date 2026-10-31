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

from dataclasses import dataclass, field

from app.domain.channel_engineering_identity import (
    ChannelEngineeringIdentityInput,
    ROLE_TOKEN_KIND_PAIR,
    resolve_channel_engineering_identity,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE

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
