"""D5A-2B2A: the shared effective measurement-side authority (service layer).

`resolve_effective_measurement_side()` is the ONE place a recorded channel's Primary/Secondary side is
decided. Every consumer (Per-Unit, Overcurrent, Impedance, Distance, phasor/power) must call it, or
`resolve_consumed_side()` for the set of channels a calculation consumes, instead of interpreting a
recording's P/S marker or a request parameter itself. It is stateless: nothing is cached, so a change at
Recording or bay level is visible to every consumer on its next call.

Ownership model -- no name parsing anywhere:
  * a channel belongs to exactly ONE source (its `ChannelRef`);
  * a channel belongs to at most ONE bay: the Engineering Context that lists it (registry invariant);
  * a bay setting applies only when that context's membership is `confirmed` or `manual`; a `suggested` /
    `needs_review` context is ambiguous ownership, so the channel simply follows its recording;
  * a channel in no bay follows its recording.

The CT/VT group a channel belongs to is reported alongside (read from the Measurement Group registry) but
never changes the side; the ratio itself stays with the existing CT/VT authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import EngineeringContext
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, kind_for_engineering_type
from app.domain.measurement_side_config import (
    AUTH_NOT_APPLICABLE,
    AUTH_UNRESOLVED,
    DIAG_BAY_INHERITANCE_AMBIGUOUS,
    DIAG_BAY_MEMBERSHIP_UNCONFIRMED,
    DIAG_BAY_NO_MEASUREMENT_MEMBERS,
    DIAG_BAY_OVERRIDE_INACTIVE,
    DIAG_CALCULATED_CHANNEL,
    DIAG_CHANNEL_NOT_FOUND,
    DIAG_CHANNEL_NOT_MEASUREMENT,
    DIAG_CONSUMED_MIXED,
    DIAG_CONSUMED_UNRESOLVED,
    DIAG_SOURCE_NOT_FOUND,
    MEMBERSHIP_CONFIRMED,
    MEMBERSHIP_NONE,
    MEMBERSHIP_UNCONFIRMED,
    QUANTITY_CURRENT,
    QUANTITY_VOLTAGE,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SIDE_UNKNOWN,
    BaySideState,
    ChannelSideEvidence,
    ChannelSideResolution,
    RecordingSideState,
    SideDiagnostic,
    SideSetResolution,
    bay_override_to_store,
    derive_recording_side,
    normalise_declared_side,
    recording_correction_to_store,
    resolve_channel_side,
    resolve_recording_state,
    resolve_side_set,
)
from app.domain.source import ActiveSource
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import (
    BayHasNoMeasurementChannelsError,
    BayMembershipUnconfirmedError,
    EngineeringContextNotFoundError,
    SourceNotFoundError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_side_registry import BaySideOverride, MeasurementSideRegistry, RecordingSideCorrection
from app.services.workspace_registry import WorkspaceRegistry

NOTE_MAX_LENGTH = 500
_CONFIRMED_CONTEXT_STATUSES = ("confirmed", "manual")
_QUANTITY_BY_KIND = {KIND_VOLTAGE: QUANTITY_VOLTAGE, KIND_CURRENT: QUANTITY_CURRENT}


@dataclass(frozen=True, slots=True)
class SideAuthority:
    """The registries the shared resolver reads. Build once per request with `from_app_state`."""

    source_registry: WorkspaceRegistry
    context_registry: EngineeringContextRegistry
    group_registry: MeasurementGroupRegistry
    side_registry: MeasurementSideRegistry

    @classmethod
    def from_app_state(cls, state) -> "SideAuthority":
        return cls(
            source_registry=state.workspace_registry, context_registry=state.engineering_context_registry,
            group_registry=state.measurement_group_registry, side_registry=state.measurement_side_registry,
        )


# --------------------------------------------------------------------------- evidence & state


def _quantity_of(engineering_type: str) -> str | None:
    kind = kind_for_engineering_type(engineering_type)
    return _QUANTITY_BY_KIND.get(kind) if kind else None


def source_side_evidence(active: ActiveSource) -> list[ChannelSideEvidence]:
    """The recording's ORIGINAL per-channel declarations for its Voltage/Current channels."""
    out: list[ChannelSideEvidence] = []
    for channel in active.metadata.analog_channels:
        quantity = _quantity_of(channel.engineering_type)
        if quantity is not None:
            out.append(ChannelSideEvidence(channel.name, quantity, normalise_declared_side(channel.measurement_side),
                                           active.metadata.source_id))
    return out


def _recording_state(workspace_id: str, source_id: str, active: ActiveSource,
                     deps: SideAuthority) -> tuple[RecordingSideState, list[ChannelSideEvidence]]:
    evidence = source_side_evidence(active)
    correction = deps.side_registry.get_recording(workspace_id, source_id)
    state = resolve_recording_state(
        derive_recording_side(evidence), correction.side if correction else None, evidence,
    )
    return state, evidence


def _membership(context: EngineeringContext | None) -> str:
    if context is None:
        return MEMBERSHIP_NONE
    return MEMBERSHIP_CONFIRMED if context.status in _CONFIRMED_CONTEXT_STATUSES else MEMBERSHIP_UNCONFIRMED


def _bay_state(workspace_id: str, ref: ChannelRef, deps: SideAuthority,
               contexts: dict[str, EngineeringContext | None] | None = None) -> BaySideState:
    context_id = deps.context_registry.context_for_channel(workspace_id, ref)
    if context_id is None:
        return BaySideState()
    if contexts is not None and context_id in contexts:
        context = contexts[context_id]
    else:
        context = deps.context_registry.get(workspace_id, context_id)
        if contexts is not None:
            contexts[context_id] = context
    override = deps.side_registry.get_bay(workspace_id, context_id)
    return BaySideState(context_id, _membership(context), override.side if override else None)


# --------------------------------------------------------------------------- the shared resolver


def _unresolved(ref_name: str | None, code: str, message: str, authority: str = AUTH_UNRESOLVED,
                quantity: str | None = None, source_id: str | None = None) -> ChannelSideResolution:
    return ChannelSideResolution(
        channel_name=ref_name, quantity=quantity, side=SIDE_UNKNOWN, authority=authority, declared_side=SIDE_UNKNOWN,
        recording_side=None, recording_authority=AUTH_UNRESOLVED,
        diagnostics=(SideDiagnostic(code, SEVERITY_WARNING, message),), source_id=source_id,
    )


def resolve_effective_measurement_side(
    workspace_id: str, source_id: str, channel_name: str, *, deps: SideAuthority,
) -> ChannelSideResolution:
    """Effective side, authority/provenance and diagnostics for one recorded channel.

    Never raises and never guesses: an unknown source/channel, a non-Voltage/Current channel or missing
    evidence yields `side == "unknown"` with a diagnostic, so a consumer can block on `not usable`."""
    active = deps.source_registry.get(workspace_id, source_id)
    if active is None:
        return _unresolved(channel_name, DIAG_SOURCE_NOT_FOUND, "The recording is not in this workspace.")
    channel = next((c for c in active.metadata.analog_channels if c.name == channel_name), None)
    if channel is None:
        return _unresolved(channel_name, DIAG_CHANNEL_NOT_FOUND, "The channel is not in this recording.")
    quantity = _quantity_of(channel.engineering_type)
    if quantity is None:
        return _unresolved(channel_name, DIAG_CHANNEL_NOT_MEASUREMENT,
                           "Only voltage and current channels have a measurement side.", AUTH_NOT_APPLICABLE)
    state, _evidence = _recording_state(workspace_id, source_id, active, deps)
    ref = ChannelRef(kind="source", source_id=source_id, channel_name=channel_name)
    return resolve_channel_side(
        ChannelSideEvidence(channel_name, quantity, normalise_declared_side(channel.measurement_side), source_id),
        state, _bay_state(workspace_id, ref, deps),
    )


def resolve_effective_side_for_ref(workspace_id: str, ref: ChannelRef, *, deps: SideAuthority) -> ChannelSideResolution:
    """`ChannelRef` form of the shared resolver. A calculated channel is not interpreted here: its side
    follows its inputs, which belongs to the consumer-migration slices, so it is reported unresolved."""
    if ref.kind != "source":
        return _unresolved(None, DIAG_CALCULATED_CHANNEL,
                           "A calculated channel's side is derived from its inputs and is not resolved here.")
    return resolve_effective_measurement_side(workspace_id, ref.source_id, ref.channel_name, deps=deps)


def resolve_consumed_side(workspace_id: str, refs: Iterable[ChannelRef], *, deps: SideAuthority) -> SideSetResolution:
    """The side of the channels one calculation consumes: usable only when every channel resolves to the SAME
    side. Different sides, or any unresolved channel, are reported (never merged or guessed) so the consumer
    blocks."""
    resolutions = [resolve_effective_side_for_ref(workspace_id, r, deps=deps) for r in refs]
    return resolve_side_set(resolutions, mixed_code=DIAG_CONSUMED_MIXED, vi_code=DIAG_CONSUMED_MIXED,
                            unresolved_code=DIAG_CONSUMED_UNRESOLVED)


# --------------------------------------------------------------------------- views


@dataclass(frozen=True, slots=True)
class RecordingSideView:
    source_id: str
    state: RecordingSideState
    correction: RecordingSideCorrection | None
    channels: tuple[ChannelSideResolution, ...]
    bay_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BaySideView:
    context_id: str
    display_name: str
    context_status: str
    membership: str
    override: BaySideOverride | None
    override_active: bool
    inherited_recording_side: str | None
    resolution: SideSetResolution
    source_ids: tuple[str, ...]
    voltage_group_ids: tuple[str, ...]
    current_group_ids: tuple[str, ...]
    channels: tuple[ChannelSideResolution, ...]
    diagnostics: tuple[SideDiagnostic, ...]


def _require_source(workspace_id: str, source_id: str, deps: SideAuthority) -> ActiveSource:
    active = deps.source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in this workspace.")
    return active


def _require_context(workspace_id: str, context_id: str, deps: SideAuthority) -> EngineeringContext:
    context = deps.context_registry.get(workspace_id, context_id)
    if context is None:
        raise EngineeringContextNotFoundError(
            f"No Engineering Context '{context_id}' in workspace '{workspace_id}'.")
    return context


def build_recording_view(workspace_id: str, source_id: str, *, deps: SideAuthority) -> RecordingSideView:
    active = _require_source(workspace_id, source_id, deps)
    state, evidence = _recording_state(workspace_id, source_id, active, deps)
    contexts: dict[str, EngineeringContext | None] = {}
    channels: list[ChannelSideResolution] = []
    bay_ids: dict[str, None] = {}
    for item in evidence:
        ref = ChannelRef(kind="source", source_id=source_id, channel_name=item.channel_name)
        bay = _bay_state(workspace_id, ref, deps, contexts)
        if bay.context_id:
            bay_ids[bay.context_id] = None
        channels.append(resolve_channel_side(item, state, bay))
    return RecordingSideView(source_id, state, deps.side_registry.get_recording(workspace_id, source_id),
                             tuple(channels), tuple(bay_ids))


def _bay_members(context: EngineeringContext, workspace_id: str, deps: SideAuthority):
    """(ref, active source, evidence) for each Voltage/Current SOURCE member whose recording exists."""
    out = []
    for member in context.members:
        ref = member.channel_ref
        if ref.kind != "source":
            continue
        active = deps.source_registry.get(workspace_id, ref.source_id)
        if active is None:
            continue
        channel = next((c for c in active.metadata.analog_channels if c.name == ref.channel_name), None)
        quantity = _quantity_of(channel.engineering_type) if channel is not None else None
        if channel is not None and quantity is not None:
            out.append((ref, active,
                        ChannelSideEvidence(ref.channel_name, quantity, normalise_declared_side(channel.measurement_side),
                                            ref.source_id)))
    return out


def _inherited_recording_side(workspace_id: str, members, deps: SideAuthority) -> tuple[str | None, bool]:
    """(the single Level 1 value every source of the bay shares or None, whether sources disagree/unresolved)."""
    sides: dict[str, str | None] = {}
    for ref, active, _evidence in members:
        if ref.source_id not in sides:
            sides[ref.source_id] = _recording_state(workspace_id, ref.source_id, active, deps)[0].effective_side
    values = set(sides.values())
    if len(values) == 1 and None not in values:
        return next(iter(values)), False
    return None, len(sides) > 1


def build_bay_view(workspace_id: str, context_id: str, *, deps: SideAuthority) -> BaySideView:
    context = _require_context(workspace_id, context_id, deps)
    members = _bay_members(context, workspace_id, deps)
    membership = _membership(context)
    stored = deps.side_registry.get_bay(workspace_id, context_id)
    recording_states: dict[str, RecordingSideState] = {}
    channels: list[ChannelSideResolution] = []
    voltage_groups: dict[str, None] = {}
    current_groups: dict[str, None] = {}
    for ref, active, evidence in members:
        if ref.source_id not in recording_states:
            recording_states[ref.source_id] = _recording_state(workspace_id, ref.source_id, active, deps)[0]
        bay = BaySideState(context_id, membership, stored.side if stored else None)
        channels.append(resolve_channel_side(evidence, recording_states[ref.source_id], bay))
        group_id = deps.group_registry.group_for_channel(workspace_id, ref)
        if group_id is not None:
            group = deps.group_registry.get(workspace_id, group_id)
            if group is not None:
                (voltage_groups if group.kind == KIND_VOLTAGE else current_groups)[group.id] = None
    inherited, disagree = _inherited_recording_side(workspace_id, members, deps)
    resolution = resolve_side_set(channels)
    diags: list[SideDiagnostic] = list(resolution.diagnostics)
    if not members:
        diags.append(SideDiagnostic(DIAG_BAY_NO_MEASUREMENT_MEMBERS, SEVERITY_INFO,
                                    "This bay has no recorded voltage or current channel."))
    if membership == MEMBERSHIP_UNCONFIRMED:
        if not any(d.code == DIAG_BAY_MEMBERSHIP_UNCONFIRMED for d in diags):
            diags.append(SideDiagnostic(DIAG_BAY_MEMBERSHIP_UNCONFIRMED, SEVERITY_WARNING,
                                        "The bay's membership is suggested or needs review; no bay setting applies.",
                                        {"engineering_context_id": context_id}))
        if stored is not None:
            diags.append(SideDiagnostic(DIAG_BAY_OVERRIDE_INACTIVE, SEVERITY_WARNING,
                                        "A stored bay setting is inactive until the bay's membership is confirmed.",
                                        {"bay_side": stored.side}))
    if disagree and stored is None:
        diags.append(SideDiagnostic(DIAG_BAY_INHERITANCE_AMBIGUOUS, SEVERITY_INFO,
                                    "The bay's recordings do not share one recording-level side."))
    return BaySideView(
        context_id=context_id, display_name=context.display_name, context_status=context.status,
        membership=membership, override=stored, override_active=stored is not None and membership == MEMBERSHIP_CONFIRMED,
        inherited_recording_side=inherited, resolution=resolution,
        source_ids=tuple(dict.fromkeys(ref.source_id for ref, _a, _e in members)),
        voltage_group_ids=tuple(voltage_groups), current_group_ids=tuple(current_groups),
        channels=tuple(channels), diagnostics=tuple(diags),
    )


def build_workspace_views(workspace_id: str, *, deps: SideAuthority) -> tuple[list[RecordingSideView], list[BaySideView]]:
    sources = deps.source_registry.list_for_workspace(workspace_id)
    recordings = [build_recording_view(workspace_id, a.metadata.source_id, deps=deps) for a in sources]
    bays = [build_bay_view(workspace_id, c.id, deps=deps) for c in deps.context_registry.list_for_workspace(workspace_id)]
    return recordings, bays


# --------------------------------------------------------------------------- mutations


def set_recording_side(workspace_id: str, source_id: str, side: str | None, note: str | None, *,
                       deps: SideAuthority) -> RecordingSideView:
    """Level 1 correction. `None` follows the recording; the value the recording already declares
    consistently also follows it (nothing redundant is stored). The recording's evidence is never touched."""
    active = _require_source(workspace_id, source_id, deps)
    if note is not None and len(note) > NOTE_MAX_LENGTH:
        raise ValueError(f"The note must be at most {NOTE_MAX_LENGTH} characters.")
    keep = recording_correction_to_store(side, derive_recording_side(source_side_evidence(active)))
    if keep is None:
        deps.side_registry.clear_recording(workspace_id, source_id)
    else:
        deps.side_registry.set_recording(
            workspace_id, source_id,
            RecordingSideCorrection(keep, (note or "").strip() or None, datetime.now(timezone.utc)))
    return build_recording_view(workspace_id, source_id, deps=deps)


def set_bay_side(workspace_id: str, context_id: str, side: str, *, deps: SideAuthority) -> BaySideView:
    """Level 2 override. Selecting the side the bay already inherits from Level 1 clears the override."""
    context = _require_context(workspace_id, context_id, deps)
    if _membership(context) != MEMBERSHIP_CONFIRMED:
        raise BayMembershipUnconfirmedError(
            "This bay's membership is only suggested or needs review; confirm it before setting its side.")
    members = _bay_members(context, workspace_id, deps)
    if not members:
        raise BayHasNoMeasurementChannelsError("This bay has no recorded voltage or current channel.")
    inherited, _disagree = _inherited_recording_side(workspace_id, members, deps)
    keep = bay_override_to_store(side, inherited)
    if keep is None:
        deps.side_registry.clear_bay(workspace_id, context_id)
    else:
        deps.side_registry.set_bay(workspace_id, context_id, BaySideOverride(keep, datetime.now(timezone.utc)))
    return build_bay_view(workspace_id, context_id, deps=deps)


# --------------------------------------------------------------------------- lifecycle


def remove_recording_side_state(workspace_id: str, source_id: str, *, deps_registry: MeasurementSideRegistry) -> None:
    deps_registry.remove_source(workspace_id, source_id)


def prune_orphan_bay_overrides(workspace_id: str, *, side_registry: MeasurementSideRegistry,
                               context_registry: EngineeringContextRegistry) -> list[str]:
    """Drop a bay override whose Engineering Context no longer exists (deleted, or emptied by a source removal)."""
    removed = []
    for context_id in side_registry.bay_context_ids(workspace_id):
        if context_registry.get(workspace_id, context_id) is None:
            side_registry.clear_bay(workspace_id, context_id)
            removed.append(context_id)
    return removed
