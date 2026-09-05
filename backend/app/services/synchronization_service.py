"""Waveform time-synchronization orchestration.

Slice 1: per-source MANUAL alignment offsets. Slice 2: event origin
(`t0`), now Time-Group-scoped. Slice 3: assisted event-origin detection.
**Timestamp-Based Initial Alignment and Time Groups**: every source's
own EFFECTIVE placement is now `timestamp_placement_offset_s` (derived,
`app.domain.time_grouping`, from recorded start timestamps) +
`manual_alignment_offset_s` (Slice 1's own existing engineer correction,
`SynchronizationRegistry`, completely unchanged storage/semantics) --
see `app.domain.time_grouping`'s own module docstring for the full time
architecture and grouping rules, and
docs/project-memory/DECISIONS.md's "Timestamp-Based Initial Alignment
and Time Groups" entry for the full record.

**Governing principle: "one waveform panel = one coherent time
domain."** A workspace's sources are partitioned into Time Groups
(`app.domain.time_grouping.derive_time_groups()`, recomputed fresh on
every call from the CURRENT source set, never cached/persisted -- see
that function's own docstring for the deterministic derivation rule).
Each group has its own ORIGIN source (`group.origin_source_id`, always
the group's own current `group_id` too -- no separate hardcoded ID
scheme) -- the group's own reference/anchor, whose `timestamp_placement_offset_s`
is always `0.0` by construction and whose `manual_alignment_offset_s` is
locked to `0.0` for the exact same "the reference source's own offset is
always 0" reason Slice 1 already established, just now scoped PER GROUP
instead of per-workspace (`ReferenceSourceAlignmentError` below).

`app.domain.synchronization.reference_source_id_for_workspace()` (the
original, workspace-wide, upload-order reference rule) is intentionally
left completely untouched -- it is still correct, still tested, simply
no longer the mechanism this module uses to decide which source's
manual offset is locked to zero (that decision is now made per Time
Group, from each group's own EARLIEST recorded start timestamp instead
of upload order -- task section 4's own worked example).

`t0` (Slice 2) is now Time-Group-scoped (task section 24: "a t0 applies
to one coherent time domain... do not let setting t0 in one independent
group silently re-zero unrelated groups") -- every t0 get/set/clear call
below takes a `source_id` to resolve WHICH group's own t0 is being
addressed (`SynchronizationRegistry`'s own `(workspace_id,
time_group_key)` key shape, `time_group_key` always that group's
current `group_id`). For the common single-group workspace (task
section 25), this degenerates to exactly Slice 2's original behaviour --
one group, one t0, unchanged UX.

This module never touches waveform/cursor/digital-waveform data --
Slice 1's request/response time-shift for those endpoints, and Slice 2's
additional event-time layer on top, both happen entirely on the frontend
(convert the event/workspace-time range to source-native before calling
the EXISTING `.../waveform`/`.../cursor-values`/`.../digital-waveform`
endpoints unchanged, then shift the returned times back for display),
mirroring DEC-042's own "presentation-layer transform, not a backend
data authority" precedent for Absolute/Elapsed time-mode. The backend's
own role is authoritative storage/derivation of the scalar
offset/t0/time-group values only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.event_detection import VALID_SENSITIVITIES, EventDetectionResult, detect_event_onset
from app.domain.source import SourceMetadata
from app.domain.synchronization import alignment_offset_valid, source_time_to_workspace_time
from app.domain.time_grouping import (
    TIME_REFERENCE_TIME_OF_DAY,
    TimeGroup,
    derive_time_groups,
    time_of_day_placement_offset_s,
    timestamp_placement_offset_s,
)
from app.services.errors import (
    ChannelNotAnalogError,
    ChannelNotFoundError,
    InvalidAlignmentOffsetError,
    InvalidDetectionSensitivityError,
    InvalidT0Error,
    ReferenceSourceAlignmentError,
    SourceNotFoundError,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry


def list_time_groups(*, workspace_id: str, source_registry: WorkspaceRegistry) -> list[TimeGroup]:
    """Every current Time Group in this workspace (task section 9),
    recomputed fresh from the CURRENT source set -- see
    `app.domain.time_grouping.derive_time_groups()`'s own docstring for
    the full derivation rule. A workspace with no sources yet returns an
    empty list."""
    actives = source_registry.list_for_workspace(workspace_id)
    sources = [_metadata_tuple(active.metadata) for active in actives]
    time_of_day_reference_seconds = _time_of_day_reference_seconds(active.metadata for active in actives)
    return derive_time_groups(sources, time_of_day_reference_seconds=time_of_day_reference_seconds)


def _metadata_tuple(metadata: SourceMetadata) -> tuple[str, str, object, float, float]:
    return (metadata.source_id, metadata.timing_reference, metadata.start_time, metadata.elapsed_start_seconds, metadata.elapsed_end_seconds)


def _time_of_day_reference_seconds(metadata_iter) -> dict[str, float]:
    """Time of Day (additive): the `source_id -> seconds_since_midnight`
    lookup `derive_time_groups()` needs for its own separate Time-of-Day
    overlap pass -- built straight from `SourceMetadata.time_of_day_
    reference_seconds`, `None` entries omitted (a source with no real
    Time of Day anchor is not eligible for that pass at all, exactly
    like a `recorded_absolute` source with `start_time is None`)."""
    return {m.source_id: m.time_of_day_reference_seconds for m in metadata_iter if m.time_of_day_reference_seconds is not None}


def _group_lookup(*, workspace_id: str, source_registry: WorkspaceRegistry) -> tuple[dict[str, TimeGroup], dict[str, SourceMetadata]]:
    """The ONE place this module derives Time Groups and builds the two
    lookups every group-aware function below needs: `source_id ->
    TimeGroup` (its own current group) and `source_id -> SourceMetadata`
    (for `start_time`/`time_of_day_reference_seconds` access when
    computing `timestamp_placement_offset_s`/`time_of_day_placement_
    offset_s`). Computed once per call site, never per-source, so a
    multi-source workspace stays O(n) rather than O(n^2)."""
    actives = source_registry.list_for_workspace(workspace_id)
    metadata_by_id = {active.metadata.source_id: active.metadata for active in actives}
    groups = derive_time_groups(
        [_metadata_tuple(m) for m in metadata_by_id.values()],
        time_of_day_reference_seconds=_time_of_day_reference_seconds(metadata_by_id.values()),
    )
    group_by_source_id = {source_id: group for group in groups for source_id in group.source_ids}
    return group_by_source_id, metadata_by_id


@dataclass(slots=True)
class SourceAlignmentView:
    """One source's own alignment state, as the manual-synchronization
    UI needs to render it -- the three-part composition (task section
    3): `effective_alignment_offset_s = timestamp_placement_offset_s +
    manual_alignment_offset_s`. `time_group_id` is that source's own
    CURRENT time group's `group_id` (see `app.domain.time_grouping`'s
    own docstring for why that is always a real source_id, never a
    separate hardcoded identifier). `is_reference` means "is this
    source its OWN time group's origin" -- scoped per-group now, not
    per-workspace (see this module's own top-of-file docstring)."""

    source_id: str
    time_group_id: str
    timestamp_placement_offset_s: float
    manual_alignment_offset_s: float
    effective_alignment_offset_s: float
    is_reference: bool


def _view_for_source(
    *, source_id: str, registry: SynchronizationRegistry, workspace_id: str,
    group_by_source_id: dict[str, TimeGroup], metadata_by_id: dict[str, SourceMetadata],
) -> SourceAlignmentView:
    group = group_by_source_id[source_id]
    origin_metadata = metadata_by_id[group.origin_source_id]
    own_metadata = metadata_by_id[source_id]
    if group.time_reference_type == TIME_REFERENCE_TIME_OF_DAY:
        # Time of Day (additive): the SAME placement composition, in
        # date-neutral seconds-since-midnight coordinates -- never the
        # `datetime`-based `timestamp_placement_offset_s()` below, which
        # would be meaningless here (`start_time` is always `None` for a
        # Time of Day source -- no date is ever invented).
        placement = time_of_day_placement_offset_s(
            source_reference_seconds=own_metadata.time_of_day_reference_seconds,
            origin_reference_seconds=origin_metadata.time_of_day_reference_seconds,
        )
    else:
        placement = timestamp_placement_offset_s(source_start_time=own_metadata.start_time, origin_start_time=origin_metadata.start_time)
    manual = registry.get_offset(workspace_id, source_id)
    return SourceAlignmentView(
        source_id=source_id,
        time_group_id=group.group_id,
        timestamp_placement_offset_s=placement,
        manual_alignment_offset_s=manual,
        effective_alignment_offset_s=placement + manual,
        is_reference=(source_id == group.origin_source_id),
    )


def list_source_alignments(*, workspace_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> list[SourceAlignmentView]:
    """Every real source currently loaded in the workspace, offset or
    not -- mirrors `list_source_per_unit_configs`'s own "every loaded
    recording appears automatically" rule."""
    group_by_source_id, metadata_by_id = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    return [
        _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, group_by_source_id=group_by_source_id, metadata_by_id=metadata_by_id)
        for source_id in metadata_by_id
    ]


def get_source_alignment(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> SourceAlignmentView:
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    group_by_source_id, metadata_by_id = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, group_by_source_id=group_by_source_id, metadata_by_id=metadata_by_id)


def set_source_alignment_offset(
    *, workspace_id: str, source_id: str, alignment_offset_s: float, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry
) -> SourceAlignmentView:
    """Create-or-replace ONE source's own MANUAL correction (task
    section 2/20: this sets `manual_alignment_offset_s` only --
    `timestamp_placement_offset_s` is derived, never writable here).
    404s if `source_id` does not exist in this workspace; rejects a
    non-finite offset (`InvalidAlignmentOffsetError`); rejects a
    non-zero manual correction on the CURRENT origin/reference source OF
    ITS OWN TIME GROUP (`ReferenceSourceAlignmentError`, now group-
    scoped -- see this module's own top-of-file docstring for why) --
    setting it to exactly `0` is accepted as a harmless no-op, never
    rejected, so a client does not need to special-case "skip the
    reference row" before calling this."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    if not alignment_offset_valid(alignment_offset_s):
        raise InvalidAlignmentOffsetError("alignment_offset_s must be a finite number of seconds.")
    group_by_source_id, metadata_by_id = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    if source_id == group_by_source_id[source_id].origin_source_id and alignment_offset_s != 0.0:
        raise ReferenceSourceAlignmentError(
            "This source is its own time group's origin; its manual alignment offset is always 0 and cannot be changed directly."
        )
    if alignment_offset_s == 0.0:
        registry.reset_offset(workspace_id, source_id)
    else:
        registry.set_offset(workspace_id, source_id, alignment_offset_s)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, group_by_source_id=group_by_source_id, metadata_by_id=metadata_by_id)


def reset_source_alignment_offset(
    *, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry
) -> SourceAlignmentView:
    """`manual_alignment_offset_s -> 0` for one source (task section 21:
    "Reset source ... resets only the manual correction. Timestamp-
    derived placement remains."). 404s if `source_id` does not exist;
    idempotent for an already-unshifted source (resetting the origin
    source, whose manual correction is already always `0`, is always a
    harmless no-op, never an error). The source's own
    `timestamp_placement_offset_s` is untouched -- this returns it to
    its recorded-timestamp position, never to a plain zero shift, unless
    it had none to begin with."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    registry.reset_offset(workspace_id, source_id)
    group_by_source_id, metadata_by_id = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    return _view_for_source(source_id=source_id, registry=registry, workspace_id=workspace_id, group_by_source_id=group_by_source_id, metadata_by_id=metadata_by_id)


def reset_all_alignment_offsets(*, workspace_id: str, registry: SynchronizationRegistry) -> int:
    """Every source's own MANUAL correction in this workspace `-> 0`
    (task section 21: "Reset All ... reset all manual corrections. Do
    not delete timestamp placement."). Returns the number of sources
    that actually had a non-default manual correction cleared, for
    logging/testing, not for any success/failure branching by the
    caller (mirrors `WorkspaceRegistry.remove_workspace()`'s own
    idempotent contract). Every source's own `timestamp_placement_offset_s`
    is completely untouched -- it is derived from recorded timestamps,
    never stored, so there is nothing here that could delete it.

    **Deliberately leaves t0 untouched** (Slice 2 task section 14:
    "Synchronization reset and t=0 reset are independent... source
    offsets return to zero; t=0 should remain unchanged") --
    `registry.remove_workspace()` only ever cleared the offsets store;
    this call site is exactly why that method must never be widened to
    also clear `_t0` (see that method's own docstring)."""
    return registry.remove_workspace(workspace_id)


def remove_source_alignment(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry) -> None:
    """Source-removal lifecycle hook (Slice 1 task section 10) -- called
    from `app.api.v1.sources.delete_source`, mirroring
    `delete_source_per_unit_config`'s own call-site shape exactly.

    Deliberately does NOT touch any time group's own t0 (Slice 2 task
    section 15, Time-Group task section 23: "if the synchronization
    relationship connecting a source is removed, the architecture should
    allow it to become independent again" -- groups are recomputed
    fresh on the NEXT call, never patched retroactively here; see
    `SynchronizationRegistry.remove_source()`'s own docstring for the
    full orphaned-key consequence when the removed source happened to be
    some group's own origin)."""
    registry.remove_source(workspace_id, source_id)


def remove_workspace_synchronization_state(*, workspace_id: str, registry: SynchronizationRegistry) -> None:
    """Full workspace-lifecycle teardown hook -- called from
    `app.api.v1.workspaces.delete_workspace` ("Start New Workspace").
    Clears BOTH every source's own manual correction AND EVERY time
    group's own t0 event origin (Slice 2 task section 15 / Time-Group
    task section 41: "all timing-group state clears" on workspace
    reset). Distinct from `reset_all_alignment_offsets()` above (manual
    corrections only, "Reset All" within a still-live workspace) -- see
    that function's own docstring for why t0 must stay untouched
    there."""
    registry.remove_workspace(workspace_id)
    registry.clear_all_t0_for_workspace(workspace_id)


# ==============================================================================
# Slice 2: event origin (t0), now Time-Group-scoped (task section 24).
# ==============================================================================


@dataclass(slots=True)
class T0View:
    """One time group's own single event-origin state, as the API needs
    to render it. `t0_workspace_time` is `None` exactly when no event
    origin has been selected for THIS group (or it was cleared) --
    never a fabricated `0.0` default (see
    `SynchronizationRegistry.get_t0()`'s own docstring). `time_group_id`
    echoes back which group this view actually resolved to, so a caller
    that only supplied a `source_id` can see which group it means."""

    time_group_id: str
    t0_workspace_time: float | None


def _resolve_time_group_key(*, workspace_id: str, source_id: str, source_registry: WorkspaceRegistry) -> str:
    """The ONE place a `source_id` is resolved to "which time group's
    t0 does this address" -- every t0 get/set/clear call below goes
    through this first. 404s (`SourceNotFoundError`) for an unknown
    source_id, exactly like every other source-scoped endpoint in this
    API."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    group_by_source_id, _ = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    return group_by_source_id[source_id].group_id


def get_t0(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> T0View:
    """The event origin for WHICHEVER time group `source_id` currently
    belongs to (task section 24: t0 applies to one coherent time domain,
    never the whole workspace unconditionally)."""
    time_group_id = _resolve_time_group_key(workspace_id=workspace_id, source_id=source_id, source_registry=source_registry)
    return T0View(time_group_id=time_group_id, t0_workspace_time=registry.get_t0(workspace_id, time_group_id))


def set_t0(
    *, workspace_id: str, source_id: str, t0_workspace_time: float, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry
) -> T0View:
    """Sets the event origin for WHICHEVER time group `source_id`
    currently belongs to -- task section 24's own explicit warning: "do
    not let setting t0 in one independent group silently re-zero
    unrelated groups" -- structurally impossible here, since this only
    ever writes the ONE resolved group's own registry key. Rejects a
    non-finite value (`InvalidT0Error`) -- reuses the SAME
    finite-real-number validator alignment offsets already use
    (`app.domain.synchronization.alignment_offset_valid`).

    Deliberately does NOT touch any source's own alignment offset (task
    section 11: "these are separate concepts... do not absorb the
    alignment offset into t0"). Setting a NEW t0 while one already
    exists for this group is a plain create-or-replace, matching every
    other PUT in this codebase."""
    if not alignment_offset_valid(t0_workspace_time):
        raise InvalidT0Error("t0_workspace_time must be a finite number of seconds.")
    time_group_id = _resolve_time_group_key(workspace_id=workspace_id, source_id=source_id, source_registry=source_registry)
    registry.set_t0(workspace_id, time_group_id, t0_workspace_time)
    return T0View(time_group_id=time_group_id, t0_workspace_time=t0_workspace_time)


def clear_t0(*, workspace_id: str, source_id: str, registry: SynchronizationRegistry, source_registry: WorkspaceRegistry) -> T0View:
    """"Clear t=0" for WHICHEVER time group `source_id` currently
    belongs to (Slice 2 task section 13): removes ONLY that group's own
    event-origin reference, leaving every OTHER group's own t0 (and
    every source's own manual alignment offset, in any group) untouched
    -- deliberately NOT the same operation as `reset_all_alignment_offsets()`
    above (task section 13: "Do not make Clear t=0 equivalent to
    synchronization Reset All")."""
    time_group_id = _resolve_time_group_key(workspace_id=workspace_id, source_id=source_id, source_registry=source_registry)
    registry.clear_t0(workspace_id, time_group_id)
    return T0View(time_group_id=time_group_id, t0_workspace_time=None)


# ==============================================================================
# Slice 3 of waveform time synchronization: assisted event-origin
# detection ("Detect Event Origin").
#
# Advisory only (task section 1) -- this orchestration function ONLY ever
# returns a candidate; it never calls set_t0() itself and never touches
# any source's own alignment_offset_s. Acceptance is a SEPARATE, explicit
# frontend action that calls the existing set_t0() above unchanged (task
# section 14: "reuse the existing t0 service... do not create a second
# t0 implementation").
#
# Time-Group task section 26: operates within the selected source's own
# time group -- the candidate is composed into workspace time using that
# source's EFFECTIVE offset (timestamp placement + manual correction),
# never the manual value alone, so the previewed marker lands at the
# source's TRUE current position. Acceptance (a separate, later call)
# resolves the correct group's own t0 the SAME way every other t0 call
# does (`_resolve_time_group_key()`), via the source_id the frontend
# already carries from this same request -- never applied to an
# unrelated group.
# ==============================================================================


@dataclass(slots=True)
class DetectEventView:
    """One channel's assisted event-origin analysis, already composed
    into WORKSPACE time (task section 17/18) -- the API/frontend layer
    never needs to apply the alignment-offset composition itself.
    `candidate_workspace_time` is `None` exactly when `found` is
    `False`."""

    found: bool
    reason: str
    detector_method: str
    channel_unit: str
    nominal_frequency_hz: float
    candidate_source_time: float | None
    candidate_workspace_time: float | None
    baseline_rms: float | None
    changed_rms: float | None
    change_ratio: float | None
    direction: str | None
    quality: str | None


def _view_from_detection(
    result: EventDetectionResult, *, channel_unit: str, nominal_frequency_hz: float, effective_alignment_offset_s: float
) -> DetectEventView:
    candidate_workspace_time = (
        source_time_to_workspace_time(result.candidate_source_time, effective_alignment_offset_s)
        if result.candidate_source_time is not None
        else None
    )
    return DetectEventView(
        found=result.found,
        reason=result.reason,
        detector_method=result.detector_method,
        channel_unit=channel_unit,
        nominal_frequency_hz=nominal_frequency_hz,
        candidate_source_time=result.candidate_source_time,
        candidate_workspace_time=candidate_workspace_time,
        baseline_rms=result.baseline_rms,
        changed_rms=result.changed_rms,
        change_ratio=result.change_ratio,
        direction=result.direction,
        quality=result.quality,
    )


def detect_event_candidate(
    *,
    workspace_id: str,
    source_id: str,
    channel_name: str,
    sensitivity: str,
    search_start_time: float | None,
    search_end_time: float | None,
    source_registry: WorkspaceRegistry,
    synchronization_registry: SynchronizationRegistry,
) -> DetectEventView:
    """Run Slice 3's assisted detector against ONE engineer-selected
    analog channel (task section 5: "the engineer should explicitly
    select source; channel" -- never an automatic best-channel choice
    across a source's whole channel list, task section 32's own
    non-goal).

    404s (`source_not_found`/`channel_not_found`) or 400s
    (`channel_not_analog`/`invalid_sensitivity`/`invalid_time_range`)
    exactly like every other read-only analysis endpoint in this API
    (`.../peak-values`, `.../annotation-anchor`) -- reuses the SAME
    `ChannelNotFoundError`/`ChannelNotAnalogError` this module's sibling
    `app.services.waveform_service` already raises for the identical
    situation, never a third differently-worded error for the same
    fact.

    Operates on the selected source's own NATIVE full-resolution data
    (task section 17: "detection should operate on the selected
    source's native signal") -- `active.record.waveform_data`, the SAME
    authoritative array every other analysis endpoint in this codebase
    reads (never the reduced display envelope). The candidate this
    returns is composed into WORKSPACE time via
    `source_time_to_workspace_time()` using this source's CURRENT
    EFFECTIVE offset (timestamp placement + manual correction, Time-
    Group task section 26 -- unmodified by this function) -- so a
    later-changed manual offset, or a later change in which sources
    overlap this one's own timestamp, is naturally reflected the next
    time detection runs, never a stale cached composition.

    Never mutates any offset, t0, or the source's own record. If
    `search_start_time`/`search_end_time` are given, the analysed slice
    is boundary-inclusive clipped to them first (source-native time, the
    SAME `np.searchsorted` convention `waveform_service._peak_in_range`/
    `_clip_and_reduce` already use) -- task section 24's own optional
    narrowing; omitted, the full record is analysed."""
    if sensitivity not in VALID_SENSITIVITIES:
        raise InvalidDetectionSensitivityError(
            f"sensitivity must be one of {sorted(VALID_SENSITIVITIES)}."
        )

    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")

    channel_unit: str | None = None
    for channel in active.metadata.analog_channels:
        if channel.name == channel_name:
            channel_unit = channel.unit
            break
    if channel_unit is None:
        for channel in active.metadata.digital_channels:
            if channel.name == channel_name:
                raise ChannelNotAnalogError(
                    f"Channel '{channel_name}' is a digital channel; event detection currently "
                    "supports analog channels only."
                )
        raise ChannelNotFoundError(f"No channel named '{channel_name}' on this source.")

    waveform_data = active.record.waveform_data
    time_full = waveform_data["time"].to_numpy()
    values_full = waveform_data[channel_name].to_numpy()

    lo = 0 if search_start_time is None else int(np.searchsorted(time_full, search_start_time, side="left"))
    hi = time_full.shape[0] if search_end_time is None else int(np.searchsorted(time_full, search_end_time, side="right"))
    time_slice = time_full[lo:hi]
    values_slice = values_full[lo:hi]

    result = detect_event_onset(
        time_slice, values_slice, nominal_frequency_hz=active.metadata.nominal_frequency, sensitivity=sensitivity
    )
    group_by_source_id, metadata_by_id = _group_lookup(workspace_id=workspace_id, source_registry=source_registry)
    view = _view_for_source(source_id=source_id, registry=synchronization_registry, workspace_id=workspace_id, group_by_source_id=group_by_source_id, metadata_by_id=metadata_by_id)
    return _view_from_detection(
        result,
        channel_unit=channel_unit,
        nominal_frequency_hz=active.metadata.nominal_frequency,
        effective_alignment_offset_s=view.effective_alignment_offset_s,
    )
