"""Event Reconstruction orchestration (DEC-123/DEC-124).

Consumes the workspace's existing Time Groups
(`synchronization_service.list_time_groups()`) and each source's existing
effective placement (`synchronization_service.list_source_alignments()`)
strictly read-only, and keeps its own analysis state in
`EventReconstructionRegistry`. It never writes `SynchronizationRegistry`,
never changes Time Group membership, and never touches source data. See
app.domain.event_reconstruction for the timing model and member
identity.

Current vs stale is derived on every read: a stored member is `current`
when a Time Group with exactly its membership fingerprint exists now,
otherwise `stale`. A stale member keeps its stored correction frozen and
unapplied; it is resolved only by the engineer re-confirming the
reconstruction (`set_reconstruction_definition()`), never by silently
re-binding to a differently composed group. If the reference member is
stale, no placement is reported at all -- the reference is never
re-picked automatically (DEC-059: ambiguous analysis state does not
silently migrate).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.domain.event_reconstruction import (
    REASON_NO_ABSOLUTE_TIME_REFERENCE,
    EventReconstructionDefinition,
    ReconstructionEligibility,
    ReconstructionMember,
    classify_interval_relationship,
    correction_valid,
    large_gaps,
    membership_fingerprint,
    reconstruction_eligibility,
    reconstruction_offset_s,
    recorded_placement_s,
)
from app.domain.time_grouping import TimeGroup, normalize_absolute_datetime
from app.services.errors import (
    DuplicateReconstructionMemberError,
    InvalidReconstructionCorrectionError,
    InvalidReconstructionDefinitionError,
    ReconstructionMemberNotFoundError,
    ReconstructionMemberStaleError,
    ReconstructionNotDefinedError,
    ReconstructionReferenceNotMemberError,
    TimeGroupNotEligibleError,
    TimeGroupNotFoundError,
)
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import list_source_alignments, list_time_groups
from app.services.workspace_registry import WorkspaceRegistry

MEMBER_STATUS_CURRENT = "current"
MEMBER_STATUS_STALE = "stale"
#: Some of the member's sources now sit in a differently composed group
#: (a merge, a split, or another source added/removed).
STALE_REASON_MEMBERSHIP_CHANGED = "membership_changed"
#: None of the member's sources exist in the workspace any more.
STALE_REASON_SOURCES_REMOVED = "sources_removed"

RECONSTRUCTION_STATUS_READY = "ready"
RECONSTRUCTION_STATUS_STALE = "stale"

WARNING_LARGE_GAP = "large_gap"


@dataclass(slots=True)
class _GroupTiming:
    """One current Time Group as Event Reconstruction sees it. Extents are
    in the group's own time (existing effective within-group placement
    applied); `origin_start` is the origin source's recorded start as a
    comparable instant, for eligible groups only."""

    group: TimeGroup
    fingerprint: str
    eligibility: ReconstructionEligibility
    origin_start: datetime | None
    extent_start_s: float
    extent_end_s: float


def _group_timings(
    *, workspace_id: str, source_registry: WorkspaceRegistry, synchronization_registry: SynchronizationRegistry
) -> list[_GroupTiming]:
    groups = list_time_groups(workspace_id=workspace_id, source_registry=source_registry)
    effective = {
        view.source_id: view.effective_alignment_offset_s
        for view in list_source_alignments(
            workspace_id=workspace_id, registry=synchronization_registry, source_registry=source_registry
        )
    }
    metadata_by_id = {active.metadata.source_id: active.metadata for active in source_registry.list_for_workspace(workspace_id)}

    timings: list[_GroupTiming] = []
    for group in groups:
        members = [metadata_by_id[sid] for sid in group.source_ids if sid in metadata_by_id]
        if not members:
            continue
        starts = [m.elapsed_start_seconds + effective.get(m.source_id, 0.0) for m in members]
        ends = [m.elapsed_end_seconds + effective.get(m.source_id, 0.0) for m in members]
        eligibility = reconstruction_eligibility(group.time_reference_type)
        origin = metadata_by_id.get(group.origin_source_id)
        origin_start = None
        if eligibility.eligible:
            if origin is None or origin.start_time is None:
                # Unreachable through derive_time_groups() (an absolute
                # source without a start is demoted to elapsed-only), but
                # never fabricate an anchor if it ever happens.
                eligibility = ReconstructionEligibility(
                    eligible=False, reason_code=REASON_NO_ABSOLUTE_TIME_REFERENCE,
                    reason_message="This Time Group's origin has no recorded absolute start.",
                )
            else:
                origin_start = normalize_absolute_datetime(origin.start_time)
        timings.append(
            _GroupTiming(
                group=group, fingerprint=membership_fingerprint(group.source_ids), eligibility=eligibility,
                origin_start=origin_start, extent_start_s=min(starts), extent_end_s=max(ends),
            )
        )
    return timings


def _utc(origin_start: datetime, offset_s: float) -> datetime:
    return (origin_start + timedelta(seconds=offset_s)).astimezone(timezone.utc)


# ==============================================================================
# Views
# ==============================================================================


@dataclass(slots=True)
class TimeGroupEligibilityView:
    """One current Time Group with its Event Reconstruction eligibility.
    `start_time_utc`/`end_time_utc` are its recorded absolute extent
    (existing effective within-group placement applied, no Event
    Reconstruction correction) -- `None` for an ineligible group, which
    has no absolute anchor. `duration_s` is always available."""

    group_id: str
    time_reference_type: str
    origin_source_id: str
    source_ids: list[str]
    membership_fingerprint: str
    eligible: bool
    reason_code: str | None
    reason_message: str | None
    start_time_utc: datetime | None
    end_time_utc: datetime | None
    duration_s: float
    note: str | None
    reconstruction_member_id: str | None


@dataclass(slots=True)
class ReconstructionMemberView:
    """One member. Placement fields (`recorded_placement_s`,
    `reconstruction_offset_s`, `start_s`, `end_s`, in reconstruction time)
    are `None` when the member is stale or the reference is stale.
    `correction_relative_to_reference_s` is `correction_s` minus the
    reference's stored correction."""

    member_id: str
    source_ids: list[str]
    confirmed_group_id: str
    current_group_id: str | None
    status: str
    stale_reason: str | None
    candidate_group_ids: list[str]
    is_reference: bool
    correction_s: float
    correction_relative_to_reference_s: float
    recorded_placement_s: float | None
    reconstruction_offset_s: float | None
    start_s: float | None
    end_s: float | None
    recorded_start_time_utc: datetime | None
    recorded_end_time_utc: datetime | None


@dataclass(slots=True)
class ReconstructionRelationshipView:
    member_a_id: str
    member_b_id: str
    kind: str
    gap_s: float
    overlap_s: float


@dataclass(slots=True)
class ReconstructionWarningView:
    """Advisory only -- a warning never makes the reconstruction invalid."""

    code: str
    message: str
    before_member_id: str
    after_member_id: str
    gap_s: float
    threshold_s: float


@dataclass(slots=True)
class ReconstructionView:
    """The workspace's reconstruction as the API reports it. `defined` is
    `False` (and everything else empty) when none exists -- "not defined
    yet" is a normal state, not an error, for a read."""

    defined: bool
    status: str | None
    reference_member_id: str | None
    reference_origin_start_time_utc: datetime | None
    placements_available: bool
    large_gap_warning_threshold_s: float
    members: list[ReconstructionMemberView] = field(default_factory=list)
    relationships: list[ReconstructionRelationshipView] = field(default_factory=list)
    warnings: list[ReconstructionWarningView] = field(default_factory=list)


def _build_view(
    definition: EventReconstructionDefinition, timings: list[_GroupTiming], threshold_s: float
) -> ReconstructionView:
    by_fingerprint = {t.fingerprint: t for t in timings if t.eligibility.eligible}
    group_id_by_source = {sid: t.group.group_id for t in timings for sid in t.group.source_ids}
    reference = definition.member(definition.reference_member_id)
    reference_timing = by_fingerprint.get(reference.member_id)
    placements_available = reference_timing is not None

    member_views: list[ReconstructionMemberView] = []
    placed: list[tuple[str, float, float]] = []
    for member in definition.members:
        timing = by_fingerprint.get(member.member_id)
        if timing is not None:
            status, stale_reason, candidates = MEMBER_STATUS_CURRENT, None, []
        else:
            candidates = sorted({group_id_by_source[sid] for sid in member.source_ids if sid in group_id_by_source})
            status = MEMBER_STATUS_STALE
            stale_reason = STALE_REASON_MEMBERSHIP_CHANGED if candidates else STALE_REASON_SOURCES_REMOVED

        placement = offset = start = end = None
        if timing is not None and placements_available:
            placement = recorded_placement_s(group_origin_start=timing.origin_start, reference_origin_start=reference_timing.origin_start)
            offset = reconstruction_offset_s(
                recorded_placement_s=placement, correction_s=member.correction_s, reference_correction_s=reference.correction_s
            )
            start, end = timing.extent_start_s + offset, timing.extent_end_s + offset
            placed.append((member.member_id, start, end))

        member_views.append(
            ReconstructionMemberView(
                member_id=member.member_id,
                source_ids=list(member.source_ids),
                confirmed_group_id=member.confirmed_group_id,
                current_group_id=timing.group.group_id if timing is not None else None,
                status=status,
                stale_reason=stale_reason,
                candidate_group_ids=candidates,
                is_reference=member.member_id == reference.member_id,
                correction_s=member.correction_s,
                correction_relative_to_reference_s=member.correction_s - reference.correction_s,
                recorded_placement_s=placement,
                reconstruction_offset_s=offset,
                start_s=start,
                end_s=end,
                recorded_start_time_utc=_utc(timing.origin_start, timing.extent_start_s) if timing is not None else None,
                recorded_end_time_utc=_utc(timing.origin_start, timing.extent_end_s) if timing is not None else None,
            )
        )

    relationships = []
    for index, (a_id, a_start, a_end) in enumerate(placed):
        for b_id, b_start, b_end in placed[index + 1 :]:
            relation = classify_interval_relationship(a_start, a_end, b_start, b_end)
            relationships.append(
                ReconstructionRelationshipView(
                    member_a_id=a_id, member_b_id=b_id, kind=relation.kind, gap_s=relation.gap_s, overlap_s=relation.overlap_s
                )
            )

    warnings = [
        ReconstructionWarningView(
            code=WARNING_LARGE_GAP,
            message=(
                f"Records are {gap.gap_s:.3f} s apart on the reconstruction timeline (warning threshold "
                f"{gap.threshold_s:g} s). Check the event selection, recorder clocks and timezones."
            ),
            before_member_id=gap.before_key,
            after_member_id=gap.after_key,
            gap_s=gap.gap_s,
            threshold_s=gap.threshold_s,
        )
        for gap in large_gaps(placed, threshold_s=threshold_s)
    ]

    all_current = all(view.status == MEMBER_STATUS_CURRENT for view in member_views)
    return ReconstructionView(
        defined=True,
        status=RECONSTRUCTION_STATUS_READY if all_current else RECONSTRUCTION_STATUS_STALE,
        reference_member_id=reference.member_id,
        reference_origin_start_time_utc=reference_timing.origin_start.astimezone(timezone.utc) if placements_available else None,
        placements_available=placements_available,
        large_gap_warning_threshold_s=threshold_s,
        members=member_views,
        relationships=relationships,
        warnings=warnings,
    )


def _undefined_view(threshold_s: float) -> ReconstructionView:
    return ReconstructionView(
        defined=False, status=None, reference_member_id=None, reference_origin_start_time_utc=None,
        placements_available=False, large_gap_warning_threshold_s=threshold_s,
    )


# ==============================================================================
# Reads
# ==============================================================================


def list_reconstruction_time_groups(
    *, workspace_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    synchronization_registry: SynchronizationRegistry,
) -> list[TimeGroupEligibilityView]:
    """Every current Time Group with its V1 eligibility, in the existing
    Time Group order. Recomputed fresh, like `list_time_groups()`."""
    definition = registry.get(workspace_id)
    member_ids = {m.member_id for m in definition.members} if definition is not None else set()
    views = []
    for timing in _group_timings(
        workspace_id=workspace_id, source_registry=source_registry, synchronization_registry=synchronization_registry
    ):
        absolute = timing.origin_start is not None
        views.append(
            TimeGroupEligibilityView(
                group_id=timing.group.group_id,
                time_reference_type=timing.group.time_reference_type,
                origin_source_id=timing.group.origin_source_id,
                source_ids=list(timing.group.source_ids),
                membership_fingerprint=timing.fingerprint,
                eligible=timing.eligibility.eligible,
                reason_code=timing.eligibility.reason_code,
                reason_message=timing.eligibility.reason_message,
                start_time_utc=_utc(timing.origin_start, timing.extent_start_s) if absolute else None,
                end_time_utc=_utc(timing.origin_start, timing.extent_end_s) if absolute else None,
                duration_s=timing.extent_end_s - timing.extent_start_s,
                note=timing.group.note,
                reconstruction_member_id=timing.fingerprint if timing.fingerprint in member_ids else None,
            )
        )
    return views


def get_reconstruction(
    *, workspace_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    synchronization_registry: SynchronizationRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    definition = registry.get(workspace_id)
    if definition is None:
        return _undefined_view(large_gap_threshold_s)
    timings = _group_timings(workspace_id=workspace_id, source_registry=source_registry, synchronization_registry=synchronization_registry)
    return _build_view(definition, timings, large_gap_threshold_s)


# ==============================================================================
# Writes -- every write goes to EventReconstructionRegistry only.
# ==============================================================================


def set_reconstruction_definition(
    *, workspace_id: str, group_ids: list[str], reference_group_id: str, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, synchronization_registry: SynchronizationRegistry,
    large_gap_threshold_s: float,
) -> ReconstructionView:
    """Create or replace the reconstruction from current Time Group ids.

    This is also how a stale reconstruction is re-confirmed. A member
    whose membership fingerprint matches an existing member keeps that
    member's correction; every other selected group starts at `0.0`.
    Members not selected are dropped, along with their corrections. A
    stale member can never be "kept": its fingerprint matches no current
    group, so re-selecting the group its sources now belong to starts a
    fresh member -- the old correction is never transferred."""
    if not group_ids:
        raise InvalidReconstructionDefinitionError("Select at least one Time Group for the reconstruction.")
    duplicates = sorted(gid for gid, count in Counter(group_ids).items() if count > 1)
    if duplicates:
        raise DuplicateReconstructionMemberError(f"Time Group '{duplicates[0]}' is selected more than once.")

    timings = _group_timings(workspace_id=workspace_id, source_registry=source_registry, synchronization_registry=synchronization_registry)
    by_group_id = {t.group.group_id: t for t in timings}
    for group_id in group_ids:
        timing = by_group_id.get(group_id)
        if timing is None:
            raise TimeGroupNotFoundError(f"No current Time Group '{group_id}' in workspace '{workspace_id}'.")
        if not timing.eligibility.eligible:
            raise TimeGroupNotEligibleError(
                f"Time Group '{group_id}' cannot join an Event Reconstruction "
                f"({timing.eligibility.reason_code}): {timing.eligibility.reason_message}"
            )
    if reference_group_id not in group_ids:
        raise ReconstructionReferenceNotMemberError("The reference Time Group must be one of the selected Time Groups.")

    existing = registry.get(workspace_id)
    previous_corrections = {m.member_id: m.correction_s for m in existing.members} if existing is not None else {}
    members = tuple(
        ReconstructionMember(
            member_id=by_group_id[group_id].fingerprint,
            source_ids=tuple(sorted(by_group_id[group_id].group.source_ids)),
            confirmed_group_id=group_id,
            correction_s=previous_corrections.get(by_group_id[group_id].fingerprint, 0.0),
        )
        for group_id in group_ids
    )
    definition = EventReconstructionDefinition(members=members, reference_member_id=by_group_id[reference_group_id].fingerprint)
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def _require_current_member(
    *, workspace_id: str, member_id: str, registry: EventReconstructionRegistry, timings: list[_GroupTiming]
) -> EventReconstructionDefinition:
    definition = registry.get(workspace_id)
    if definition is None:
        raise ReconstructionNotDefinedError(f"Workspace '{workspace_id}' has no Event Reconstruction.")
    if definition.member(member_id) is None:
        raise ReconstructionMemberNotFoundError(f"No reconstruction member '{member_id}'.")
    if not any(t.fingerprint == member_id and t.eligibility.eligible for t in timings):
        raise ReconstructionMemberStaleError(
            f"Reconstruction member '{member_id}' no longer matches a current Time Group. "
            "Re-confirm the reconstruction before changing it."
        )
    return definition


def set_reconstruction_reference(
    *, workspace_id: str, member_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    synchronization_registry: SynchronizationRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    """Make a current member the reference. Stored corrections are not
    touched, so every member's position relative to every other member is
    unchanged; only the frame they are reported in moves."""
    timings = _group_timings(workspace_id=workspace_id, source_registry=source_registry, synchronization_registry=synchronization_registry)
    definition = _require_current_member(workspace_id=workspace_id, member_id=member_id, registry=registry, timings=timings)
    definition = definition.with_reference(member_id)
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def set_member_correction(
    *, workspace_id: str, member_id: str, correction_s: float, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, synchronization_registry: SynchronizationRegistry,
    large_gap_threshold_s: float,
) -> ReconstructionView:
    """Store one current member's manual correction (seconds, full float
    precision). The reference may carry a correction too: corrections
    belong to a group's clock, not to the reference role."""
    if not correction_valid(correction_s):
        raise InvalidReconstructionCorrectionError("correction_s must be a finite number of seconds.")
    timings = _group_timings(workspace_id=workspace_id, source_registry=source_registry, synchronization_registry=synchronization_registry)
    definition = _require_current_member(workspace_id=workspace_id, member_id=member_id, registry=registry, timings=timings)
    definition = definition.with_correction(member_id, float(correction_s))
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def reset_member_correction(
    *, workspace_id: str, member_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    synchronization_registry: SynchronizationRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    """Correction back to `0.0`: the member returns to its recorded-
    timestamp placement."""
    return set_member_correction(
        workspace_id=workspace_id, member_id=member_id, correction_s=0.0, registry=registry,
        source_registry=source_registry, synchronization_registry=synchronization_registry,
        large_gap_threshold_s=large_gap_threshold_s,
    )


def clear_reconstruction(*, workspace_id: str, registry: EventReconstructionRegistry) -> None:
    """Remove the workspace's reconstruction. Idempotent."""
    registry.remove_workspace(workspace_id)


def remove_workspace_event_reconstruction_state(*, workspace_id: str, registry: EventReconstructionRegistry) -> None:
    """Workspace-teardown hook ("Start New Workspace"), called from
    app.api.v1.workspaces.delete_workspace. Source removal deliberately
    has no hook: the affected member simply reads as stale."""
    registry.remove_workspace(workspace_id)
