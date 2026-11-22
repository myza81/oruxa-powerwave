"""D5A-2B2A / D5A-UI-002: the shared effective measurement-side authority (service layer).

`resolve_effective_measurement_side()` is the ONE place a recorded channel's Primary/Secondary side is
decided. Every consumer (Per-Unit, Overcurrent, Impedance, Distance, phasor/power) must call it, or
`resolve_consumed_side()` for the set of channels a calculation consumes, instead of interpreting a
recording's P/S marker or a request parameter itself. It is stateless: nothing is cached, so a change at
Recording or Group level is visible to every consumer on its next call.

Ownership model -- no name parsing anywhere:
  * a channel belongs to exactly ONE source (its `ChannelRef`);
  * a channel belongs to at most ONE Measurement Group (registry invariant), and a group belongs to exactly ONE
    source and is either a Voltage or a Current group;
  * the Level 2 setting belongs to that Measurement Group -- the same unit that owns the CT/VT ratio -- so a bay's
    Voltage group and Current group are independent, and Engineering Context membership plays no part;
  * a channel in no group follows its recording.

The group's side never changes a ratio and no ratio changes a side; the CT/VT conversion itself stays with the
existing CT/VT authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, MeasurementGroup, kind_for_engineering_type
from app.domain.measurement_side_config import (
    AUTH_NOT_APPLICABLE,
    AUTH_UNRESOLVED,
    DIAG_CALCULATED_CHANNEL,
    DIAG_CHANNEL_NOT_FOUND,
    DIAG_CHANNEL_NOT_MEASUREMENT,
    DIAG_CONSUMED_MIXED,
    DIAG_CONSUMED_VI_DIFFER,
    DIAG_CONSUMED_UNRESOLVED,
    DIAG_GROUP_NO_MEMBERS,
    DIAG_SOURCE_NOT_FOUND,
    QUANTITY_CURRENT,
    QUANTITY_VOLTAGE,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SIDE_UNKNOWN,
    STATUS_RESOLVED,
    ChannelSideEvidence,
    ChannelSideResolution,
    GroupSideState,
    RecordingSideState,
    SideDiagnostic,
    SideSetResolution,
    derive_recording_side,
    group_override_is_redundant,
    normalise_declared_side,
    recording_correction_to_store,
    resolve_channel_side,
    resolve_recording_state,
    resolve_side_set,
)
from app.domain.source import ActiveSource
from app.services.errors import (
    GroupHasNoMeasurementChannelsError,
    MeasurementGroupNotFoundError,
    SourceNotFoundError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_side_registry import GroupSideOverride, MeasurementSideRegistry, RecordingSideCorrection
from app.services.workspace_registry import WorkspaceRegistry

NOTE_MAX_LENGTH = 500
_QUANTITY_BY_KIND = {KIND_VOLTAGE: QUANTITY_VOLTAGE, KIND_CURRENT: QUANTITY_CURRENT}


@dataclass(frozen=True, slots=True)
class SideAuthority:
    """The registries the shared resolver reads. Build once per request with `from_app_state`."""

    source_registry: WorkspaceRegistry
    group_registry: MeasurementGroupRegistry
    side_registry: MeasurementSideRegistry

    @classmethod
    def from_app_state(cls, state) -> "SideAuthority":
        return cls(
            source_registry=state.workspace_registry, group_registry=state.measurement_group_registry,
            side_registry=state.measurement_side_registry,
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


def _group_state(workspace_id: str, ref: ChannelRef, deps: SideAuthority) -> GroupSideState:
    group_id = deps.group_registry.group_for_channel(workspace_id, ref)
    if group_id is None:
        return GroupSideState()
    override = deps.side_registry.get_group(workspace_id, ref.source_id, group_id)
    return GroupSideState(group_id, override.side if override else None)


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
        state, _group_state(workspace_id, ref, deps),
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
    side (or each quantity is uniform: Primary voltage with Secondary current). Different sides within a quantity,
    or any unresolved channel, are reported (never merged or guessed) so the consumer blocks.

    This answers the SIDE only. Whether a CT/VT ratio may be applied to a consumed channel is the consuming slice's
    own check of that channel's Measurement Group (matching sides alone do not establish shared conversion authority)."""
    resolutions = [resolve_effective_side_for_ref(workspace_id, r, deps=deps) for r in refs]
    return resolve_side_set(resolutions, mixed_code=DIAG_CONSUMED_MIXED, vi_code=DIAG_CONSUMED_VI_DIFFER,
                            unresolved_code=DIAG_CONSUMED_UNRESOLVED)


# --------------------------------------------------------------------------- views


@dataclass(frozen=True, slots=True)
class RecordingSideView:
    source_id: str
    state: RecordingSideState
    correction: RecordingSideCorrection | None
    channels: tuple[ChannelSideResolution, ...]
    group_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroupSideView:
    """One Voltage or Current Measurement Group of one recording: the unit a Level 2 setting belongs to."""

    group_id: str
    source_id: str
    kind: str
    display_name: str
    override: GroupSideOverride | None
    #: The side the group's channels would have WITHOUT its override (null when that is not one side).
    inherited_side: str | None
    recording_side: str | None
    resolution: SideSetResolution
    channels: tuple[ChannelSideResolution, ...]
    diagnostics: tuple[SideDiagnostic, ...]


def _require_source(workspace_id: str, source_id: str, deps: SideAuthority) -> ActiveSource:
    active = deps.source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in this workspace.")
    return active


def _require_group(workspace_id: str, source_id: str, group_id: str, deps: SideAuthority) -> MeasurementGroup:
    group = deps.group_registry.get(workspace_id, group_id)
    if group is None or group.source_id != source_id:
        raise MeasurementGroupNotFoundError(f"No measurement group '{group_id}' in this source.")
    return group


def build_recording_view(workspace_id: str, source_id: str, *, deps: SideAuthority) -> RecordingSideView:
    active = _require_source(workspace_id, source_id, deps)
    state, evidence = _recording_state(workspace_id, source_id, active, deps)
    channels: list[ChannelSideResolution] = []
    group_ids: dict[str, None] = {}
    for item in evidence:
        ref = ChannelRef(kind="source", source_id=source_id, channel_name=item.channel_name)
        group = _group_state(workspace_id, ref, deps)
        if group.group_id:
            group_ids[group.group_id] = None
        channels.append(resolve_channel_side(item, state, group))
    return RecordingSideView(source_id, state, deps.side_registry.get_recording(workspace_id, source_id),
                             tuple(channels), tuple(group_ids))


def _group_evidence(group: MeasurementGroup, active: ActiveSource) -> list[ChannelSideEvidence]:
    """The original declarations of the Voltage/Current channels of this group that exist in its recording."""
    by_name = {c.name: c for c in active.metadata.analog_channels}
    out: list[ChannelSideEvidence] = []
    for ref in group.channel_refs:
        channel = by_name.get(ref.channel_name) if ref.kind == "source" and ref.source_id == group.source_id else None
        quantity = _quantity_of(channel.engineering_type) if channel is not None else None
        if channel is not None and quantity is not None:
            out.append(ChannelSideEvidence(channel.name, quantity, normalise_declared_side(channel.measurement_side),
                                           group.source_id))
    return out


def build_group_view(workspace_id: str, source_id: str, group_id: str, *, deps: SideAuthority) -> GroupSideView:
    """One Measurement Group. Raises when the group is not in that recording."""
    group = _require_group(workspace_id, source_id, group_id, deps)
    active = _require_source(workspace_id, source_id, deps)
    recording_state, _evidence = _recording_state(workspace_id, source_id, active, deps)
    stored = deps.side_registry.get_group(workspace_id, source_id, group_id)
    evidence = _group_evidence(group, active)
    channels = [resolve_channel_side(e, recording_state, GroupSideState(group_id, stored.side if stored else None))
                for e in evidence]
    without = [resolve_channel_side(e, recording_state, GroupSideState(group_id, None)) for e in evidence]
    resolution = resolve_side_set(channels)
    inherited = resolve_side_set(without)
    diagnostics = list(resolution.diagnostics)
    if not evidence:
        diagnostics.append(SideDiagnostic(DIAG_GROUP_NO_MEMBERS, SEVERITY_INFO,
                                          "This group has no recorded voltage or current channel."))
    return GroupSideView(
        group_id=group.id, source_id=source_id, kind=group.kind, display_name=group.display_name, override=stored,
        inherited_side=inherited.side if inherited.status == STATUS_RESOLVED else None,
        recording_side=recording_state.effective_side, resolution=resolution, channels=tuple(channels),
        diagnostics=tuple(diagnostics),
    )


def build_workspace_views(workspace_id: str, *, deps: SideAuthority) -> tuple[list[RecordingSideView], list[GroupSideView]]:
    """Every recording, and every Measurement Group of those recordings."""
    sources = deps.source_registry.list_for_workspace(workspace_id)
    recordings = [build_recording_view(workspace_id, a.metadata.source_id, deps=deps) for a in sources]
    known = {a.metadata.source_id for a in sources}
    groups = [build_group_view(workspace_id, g.source_id, g.id, deps=deps)
              for g in deps.group_registry.list_for_workspace(workspace_id) if g.source_id in known]
    return recordings, groups


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


def set_group_side(workspace_id: str, source_id: str, group_id: str, side: str, *, deps: SideAuthority) -> GroupSideView:
    """Level 2 override for ONE Measurement Group of one recording. Selecting the side the group already has without
    an override -- on reliable evidence for every channel -- clears the override (it follows Level 1 again). Any other
    selection is kept, so a contradiction between the engineer and the recording's declarations is never lost. The
    other group of the same bay, and every other recording, are untouched."""
    group = _require_group(workspace_id, source_id, group_id, deps)
    active = _require_source(workspace_id, source_id, deps)
    evidence = _group_evidence(group, active)
    if not evidence:
        raise GroupHasNoMeasurementChannelsError("This group has no recorded voltage or current channel in this recording.")
    recording_state, _e = _recording_state(workspace_id, source_id, active, deps)
    without = [resolve_channel_side(e, recording_state, GroupSideState(group_id, None)) for e in evidence]
    if group_override_is_redundant(side, without):
        deps.side_registry.clear_group(workspace_id, source_id, group_id)
    else:
        deps.side_registry.set_group(workspace_id, source_id, group_id, GroupSideOverride(side, datetime.now(timezone.utc)))
    return build_group_view(workspace_id, source_id, group_id, deps=deps)


# --------------------------------------------------------------------------- lifecycle


def prune_orphan_group_overrides(workspace_id: str, *, side_registry: MeasurementSideRegistry,
                                 group_registry: MeasurementGroupRegistry) -> list[tuple[str, str]]:
    """Drop a group override whose Measurement Group no longer exists (deleted, or its recording was removed). A group
    that merely changed members keeps its identity and its override."""
    removed: list[tuple[str, str]] = []
    for source_id, group_id in side_registry.group_keys(workspace_id):
        group = group_registry.get(workspace_id, group_id)
        if group is None or group.source_id != source_id:
            side_registry.clear_group(workspace_id, source_id, group_id)
            removed.append((source_id, group_id))
    return removed
