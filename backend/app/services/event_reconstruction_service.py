"""Event Reconstruction orchestration (DEC-123, DEC-124, DEC-128).

Members are independently imported RECORDS (DEC-128): one record per
workspace source (`SourceMetadata.source_id`, one upload = one logical
event). Waveform Time Groups and Synchronise Sources state are not inputs
at all -- two records whose recorded times overlap, even identically,
stay two members, and nothing here reads or writes
`SynchronizationRegistry`. See app.domain.event_reconstruction for the
timing model. Analysis state lives in `EventReconstructionRegistry`;
source data is never touched.

Current vs stale is derived on every read: a stored member is `current`
while its record exists in the workspace, otherwise `stale`. A stale
member keeps its stored correction frozen and unapplied and exposes no
placement or source timing; the engineer resolves it by redefining the
reconstruction without it. If the reference record is stale, no
placement is reported at all -- the reference is never re-picked
automatically (DEC-059: ambiguous analysis state does not silently
migrate).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from app.domain.event_reconstruction import (
    REASON_NO_ABSOLUTE_TIME_REFERENCE,
    EventReconstructionDefinition,
    ReconstructionAnnotation,
    ReconstructionEligibility,
    ReconstructionMember,
    annotation_time_valid,
    classify_interval_relationship,
    correction_valid,
    large_gaps,
    normalized_annotation_text,
    reconstruction_eligibility,
    reconstruction_frame_shift_s,
    reconstruction_offset_s,
    reconstruction_zero_instant,
    recorded_placement_s,
    total_reconstruction_offset_s,
)
from app.domain.time_grouping import normalize_absolute_datetime, time_reference_type_for_source
from app.services.errors import (
    DuplicateReconstructionMemberError,
    InvalidReconstructionAnnotationError,
    InvalidReconstructionCorrectionError,
    ReconstructionAnnotationNotFoundError,
    InvalidReconstructionDefinitionError,
    ReconstructionMemberNotFoundError,
    ReconstructionMemberStaleError,
    ReconstructionNotDefinedError,
    ReconstructionReferenceNotMemberError,
    RecordNotEligibleError,
    SourceNotFoundError,
)
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.workspace_registry import WorkspaceRegistry

MEMBER_STATUS_CURRENT = "current"
MEMBER_STATUS_STALE = "stale"
#: The member's record no longer exists in the workspace.
STALE_REASON_RECORD_REMOVED = "record_removed"

RECONSTRUCTION_STATUS_READY = "ready"
RECONSTRUCTION_STATUS_STALE = "stale"

WARNING_LARGE_GAP = "large_gap"


@dataclass(slots=True)
class _SourceTiming:
    """One constituent source of a record: its own native elapsed extent
    and where it sits inside the record (0 for a single-source record)."""

    source_id: str
    within_record_offset_s: float
    elapsed_start_s: float
    elapsed_end_s: float


@dataclass(slots=True)
class _RecordTiming:
    """One record as Event Reconstruction sees it. Extents are in the
    record's own time; `origin_start` is its recorded start as a
    comparable instant, for eligible records only."""

    record_id: str
    source_ids: list[str]
    time_reference_type: str
    eligibility: ReconstructionEligibility
    origin_start: datetime | None
    extent_start_s: float
    extent_end_s: float
    sources: list[_SourceTiming]


def _record_timings(*, workspace_id: str, source_registry: WorkspaceRegistry) -> list[_RecordTiming]:
    """Every record in the workspace, eligible ones by recorded start
    (then id), then the ineligible ones by id."""
    timings: list[_RecordTiming] = []
    for active in source_registry.list_for_workspace(workspace_id):
        metadata = active.metadata
        time_reference_type = time_reference_type_for_source(metadata.timing_reference)
        eligibility = reconstruction_eligibility(time_reference_type)
        origin_start = None
        if eligibility.eligible:
            if metadata.start_time is None:
                # Never fabricate an anchor for an "absolute" record
                # without a recorded start.
                eligibility = ReconstructionEligibility(
                    eligible=False, reason_code=REASON_NO_ABSOLUTE_TIME_REFERENCE,
                    reason_message="This record has no recorded absolute start.",
                )
            else:
                origin_start = normalize_absolute_datetime(metadata.start_time)
        source = _SourceTiming(
            source_id=metadata.source_id, within_record_offset_s=0.0,
            elapsed_start_s=metadata.elapsed_start_seconds, elapsed_end_s=metadata.elapsed_end_seconds,
        )
        timings.append(
            _RecordTiming(
                record_id=metadata.source_id,
                source_ids=[metadata.source_id],
                time_reference_type=time_reference_type,
                eligibility=eligibility,
                origin_start=origin_start,
                extent_start_s=source.elapsed_start_s + source.within_record_offset_s,
                extent_end_s=source.elapsed_end_s + source.within_record_offset_s,
                sources=[source],
            )
        )
    timings.sort(key=lambda t: (t.origin_start is None, t.origin_start or datetime.min.replace(tzinfo=timezone.utc), t.record_id))
    return timings


def _utc(origin_start: datetime, offset_s: float) -> datetime:
    return (origin_start + timedelta(seconds=offset_s)).astimezone(timezone.utc)


# ==============================================================================
# Views
# ==============================================================================


@dataclass(slots=True)
class RecordEligibilityView:
    """One workspace record with its Event Reconstruction eligibility.
    `start_time_utc`/`end_time_utc` are its recorded absolute extent --
    `None` for an ineligible record, which has no absolute anchor.
    `duration_s` is always available."""

    record_id: str
    source_ids: list[str]
    time_reference_type: str
    eligible: bool
    reason_code: str | None
    reason_message: str | None
    start_time_utc: datetime | None
    end_time_utc: datetime | None
    duration_s: float
    in_reconstruction: bool


@dataclass(slots=True)
class ReconstructionSourceTimingView:
    """How ONE constituent source maps onto the reconstruction timeline.
    The frontend uses `total_reconstruction_offset_s` alone:

        reconstruction_x_s = source_elapsed_s + total_reconstruction_offset_s

    - `within_record_offset_s`: where the source sits inside its record
      (0 for a single-source record).
    - `reconstruction_record_offset_s`: its record's offset to the
      reference (recorded-start difference + Event Reconstruction
      corrections) -- the member's `reconstruction_offset_s`.
    - `total_reconstruction_offset_s`: the sum of the two.
    - `reconstruction_start_s`/`reconstruction_end_s`: the source's own
      native elapsed extent mapped onto the reconstruction timeline.
    Calculated channels use the entry of their timing-parent source."""

    source_id: str
    within_record_offset_s: float
    reconstruction_record_offset_s: float
    total_reconstruction_offset_s: float
    reconstruction_start_s: float
    reconstruction_end_s: float


@dataclass(slots=True)
class ReconstructionMemberView:
    """One member record. Placement fields (`recorded_placement_s`,
    `reconstruction_offset_s`, `start_s`, `end_s`, in reconstruction time)
    and `source_timings` are `None` when the member is stale or the
    reference is stale -- no usable mapping is ever exposed for stale
    state. `correction_relative_to_reference_s` is `correction_s` minus
    the reference's stored correction."""

    record_id: str
    source_ids: list[str]
    status: str
    stale_reason: str | None
    is_reference: bool
    correction_s: float
    correction_relative_to_reference_s: float
    recorded_placement_s: float | None
    reconstruction_offset_s: float | None
    start_s: float | None
    end_s: float | None
    recorded_start_time_utc: datetime | None
    recorded_end_time_utc: datetime | None
    source_timings: list[ReconstructionSourceTimingView] | None


@dataclass(slots=True)
class ReconstructionRelationshipView:
    record_a_id: str
    record_b_id: str
    kind: str
    gap_s: float
    overlap_s: float


@dataclass(slots=True)
class ReconstructionWarningView:
    """Advisory only -- a warning never makes the reconstruction invalid."""

    code: str
    message: str
    before_record_id: str
    after_record_id: str
    gap_s: float
    threshold_s: float


@dataclass(slots=True)
class ReconstructionAnnotationView:
    annotation_id: str
    reconstruction_time_s: float
    text: str


@dataclass(slots=True)
class ReconstructionView:
    """The workspace's reconstruction as the API reports it. `defined` is
    `False` (and everything else empty) when none exists -- "not defined
    yet" is a normal state, not an error, for a read."""

    defined: bool
    status: str | None
    reference_record_id: str | None
    reference_origin_start_time_utc: datetime | None
    # Absolute instant of reconstruction time 0 (reference recorded start +
    # reference correction); `None` whenever placements are unavailable.
    reconstruction_zero_time_utc: datetime | None
    placements_available: bool
    large_gap_warning_threshold_s: float
    members: list[ReconstructionMemberView] = field(default_factory=list)
    # The reconstruction's own annotations (DEC-136), by time then id, in
    # the current reconstruction frame.
    annotations: list[ReconstructionAnnotationView] = field(default_factory=list)
    relationships: list[ReconstructionRelationshipView] = field(default_factory=list)
    warnings: list[ReconstructionWarningView] = field(default_factory=list)


def _build_view(
    definition: EventReconstructionDefinition, timings: list[_RecordTiming], threshold_s: float
) -> ReconstructionView:
    by_record = {t.record_id: t for t in timings if t.eligibility.eligible}
    reference = definition.member(definition.reference_record_id)
    reference_timing = by_record.get(reference.record_id)
    placements_available = reference_timing is not None

    member_views: list[ReconstructionMemberView] = []
    placed: list[tuple[str, float, float]] = []
    for member in definition.members:
        timing = by_record.get(member.record_id)
        status = MEMBER_STATUS_CURRENT if timing is not None else MEMBER_STATUS_STALE
        stale_reason = None if timing is not None else STALE_REASON_RECORD_REMOVED

        placement = offset = start = end = source_timings = None
        if timing is not None and placements_available:
            placement = recorded_placement_s(record_origin_start=timing.origin_start, reference_origin_start=reference_timing.origin_start)
            offset = reconstruction_offset_s(
                recorded_placement_s=placement, correction_s=member.correction_s, reference_correction_s=reference.correction_s
            )
            start, end = timing.extent_start_s + offset, timing.extent_end_s + offset
            placed.append((member.record_id, start, end))
            source_timings = []
            for src in timing.sources:
                total = total_reconstruction_offset_s(within_record_offset_s=src.within_record_offset_s, reconstruction_record_offset_s=offset)
                source_timings.append(
                    ReconstructionSourceTimingView(
                        source_id=src.source_id,
                        within_record_offset_s=src.within_record_offset_s,
                        reconstruction_record_offset_s=offset,
                        total_reconstruction_offset_s=total,
                        reconstruction_start_s=src.elapsed_start_s + total,
                        reconstruction_end_s=src.elapsed_end_s + total,
                    )
                )

        member_views.append(
            ReconstructionMemberView(
                record_id=member.record_id,
                source_ids=list(member.source_ids),
                status=status,
                stale_reason=stale_reason,
                is_reference=member.record_id == reference.record_id,
                correction_s=member.correction_s,
                correction_relative_to_reference_s=member.correction_s - reference.correction_s,
                recorded_placement_s=placement,
                reconstruction_offset_s=offset,
                start_s=start,
                end_s=end,
                recorded_start_time_utc=_utc(timing.origin_start, timing.extent_start_s) if timing is not None else None,
                recorded_end_time_utc=_utc(timing.origin_start, timing.extent_end_s) if timing is not None else None,
                source_timings=source_timings,
            )
        )

    relationships = []
    for index, (a_id, a_start, a_end) in enumerate(placed):
        for b_id, b_start, b_end in placed[index + 1 :]:
            relation = classify_interval_relationship(a_start, a_end, b_start, b_end)
            relationships.append(
                ReconstructionRelationshipView(
                    record_a_id=a_id, record_b_id=b_id, kind=relation.kind, gap_s=relation.gap_s, overlap_s=relation.overlap_s
                )
            )

    warnings = [
        ReconstructionWarningView(
            code=WARNING_LARGE_GAP,
            message=(
                f"Records are {gap.gap_s:.3f} s apart on the reconstruction timeline (warning threshold "
                f"{gap.threshold_s:g} s). Check the event selection, recorder clocks and timezones."
            ),
            before_record_id=gap.before_key,
            after_record_id=gap.after_key,
            gap_s=gap.gap_s,
            threshold_s=gap.threshold_s,
        )
        for gap in large_gaps(placed, threshold_s=threshold_s)
    ]

    all_current = all(view.status == MEMBER_STATUS_CURRENT for view in member_views)
    return ReconstructionView(
        defined=True,
        status=RECONSTRUCTION_STATUS_READY if all_current else RECONSTRUCTION_STATUS_STALE,
        reference_record_id=reference.record_id,
        reference_origin_start_time_utc=reference_timing.origin_start.astimezone(timezone.utc) if placements_available else None,
        reconstruction_zero_time_utc=(
            reconstruction_zero_instant(
                reference_origin_start=reference_timing.origin_start, reference_correction_s=reference.correction_s
            ).astimezone(timezone.utc)
            if placements_available else None
        ),
        placements_available=placements_available,
        large_gap_warning_threshold_s=threshold_s,
        members=member_views,
        relationships=relationships,
        warnings=warnings,
        annotations=[
            ReconstructionAnnotationView(
                annotation_id=a.annotation_id, reconstruction_time_s=a.reconstruction_time_s, text=a.text
            )
            for a in sorted(definition.annotations, key=lambda a: (a.reconstruction_time_s, a.annotation_id))
        ],
    )


def _undefined_view(threshold_s: float) -> ReconstructionView:
    return ReconstructionView(
        defined=False, status=None, reference_record_id=None, reference_origin_start_time_utc=None,
        reconstruction_zero_time_utc=None,
        placements_available=False, large_gap_warning_threshold_s=threshold_s,
    )


# ==============================================================================
# Reads
# ==============================================================================


def list_reconstruction_records(
    *, workspace_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
) -> list[RecordEligibilityView]:
    """Every workspace record with its V1 eligibility -- eligible ones by
    recorded start, then the ineligible ones. Recomputed fresh."""
    definition = registry.get(workspace_id)
    member_ids = {m.record_id for m in definition.members} if definition is not None else set()
    views = []
    for timing in _record_timings(workspace_id=workspace_id, source_registry=source_registry):
        absolute = timing.origin_start is not None
        views.append(
            RecordEligibilityView(
                record_id=timing.record_id,
                source_ids=list(timing.source_ids),
                time_reference_type=timing.time_reference_type,
                eligible=timing.eligibility.eligible,
                reason_code=timing.eligibility.reason_code,
                reason_message=timing.eligibility.reason_message,
                start_time_utc=_utc(timing.origin_start, timing.extent_start_s) if absolute else None,
                end_time_utc=_utc(timing.origin_start, timing.extent_end_s) if absolute else None,
                duration_s=timing.extent_end_s - timing.extent_start_s,
                in_reconstruction=timing.record_id in member_ids,
            )
        )
    return views


def get_reconstruction(
    *, workspace_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    large_gap_threshold_s: float,
) -> ReconstructionView:
    definition = registry.get(workspace_id)
    if definition is None:
        return _undefined_view(large_gap_threshold_s)
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    return _build_view(definition, timings, large_gap_threshold_s)


# ==============================================================================
# Writes -- every write goes to EventReconstructionRegistry only.
# ==============================================================================


def set_reconstruction_definition(
    *, workspace_id: str, record_ids: list[str], reference_record_id: str, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    """Create or replace the reconstruction from current record ids.

    A record already in the reconstruction keeps its correction; every
    other selected record starts at `0.0`. Members not selected are
    dropped, along with their corrections -- this is also how a stale
    (removed) member is cleared."""
    if not record_ids:
        raise InvalidReconstructionDefinitionError("Select at least one record for the reconstruction.")
    duplicates = sorted(rid for rid, count in Counter(record_ids).items() if count > 1)
    if duplicates:
        raise DuplicateReconstructionMemberError(f"Record '{duplicates[0]}' is selected more than once.")

    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    by_record = {t.record_id: t for t in timings}
    for record_id in record_ids:
        timing = by_record.get(record_id)
        if timing is None:
            raise SourceNotFoundError(f"No record '{record_id}' in workspace '{workspace_id}'.")
        if not timing.eligibility.eligible:
            raise RecordNotEligibleError(
                f"Record '{record_id}' cannot join an Event Reconstruction "
                f"({timing.eligibility.reason_code}): {timing.eligibility.reason_message}"
            )
    if reference_record_id not in record_ids:
        raise ReconstructionReferenceNotMemberError("The reference record must be one of the selected records.")

    existing = registry.get(workspace_id)
    previous_corrections = {m.record_id: m.correction_s for m in existing.members} if existing is not None else {}
    # A membership change keeps the reconstruction's annotations (they
    # belong to its storyline, not to a record), rebased if the frame moved.
    previous_annotations = existing.annotations if existing is not None else ()
    members = tuple(
        ReconstructionMember(
            record_id=record_id,
            source_ids=tuple(by_record[record_id].source_ids),
            correction_s=previous_corrections.get(record_id, 0.0),
        )
        for record_id in record_ids
    )
    definition = EventReconstructionDefinition(
        members=members, reference_record_id=reference_record_id, annotations=previous_annotations
    )
    if existing is not None:
        definition = _rebased(existing, definition, timings)
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def _rebased(
    before: EventReconstructionDefinition, after: EventReconstructionDefinition, timings: list[_RecordTiming]
) -> EventReconstructionDefinition:
    """`after` with its annotations moved by the reconstruction frame shift
    from `before`, so each stays on its physical instant (DEC-136)."""
    origins = {t.record_id: t.origin_start for t in timings if t.eligibility.eligible and t.origin_start is not None}
    return after.with_frame_shift(reconstruction_frame_shift_s(before=before, after=after, origin_starts=origins))


def _require_current_member(
    *, workspace_id: str, record_id: str, registry: EventReconstructionRegistry, timings: list[_RecordTiming]
) -> EventReconstructionDefinition:
    definition = registry.get(workspace_id)
    if definition is None:
        raise ReconstructionNotDefinedError(f"Workspace '{workspace_id}' has no Event Reconstruction.")
    if definition.member(record_id) is None:
        raise ReconstructionMemberNotFoundError(f"Record '{record_id}' is not in the reconstruction.")
    if not any(t.record_id == record_id and t.eligibility.eligible for t in timings):
        raise ReconstructionMemberStaleError(
            f"Record '{record_id}' is no longer in the workspace. Remove it from the reconstruction."
        )
    return definition


def set_reconstruction_reference(
    *, workspace_id: str, record_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    large_gap_threshold_s: float,
) -> ReconstructionView:
    """Make a current member record the reference. Stored corrections are
    not touched, so every record's position relative to every other is
    unchanged; only the frame they are reported in moves."""
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    definition = _require_current_member(workspace_id=workspace_id, record_id=record_id, registry=registry, timings=timings)
    definition = _rebased(definition, definition.with_reference(record_id), timings)
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def set_member_correction(
    *, workspace_id: str, record_id: str, correction_s: float, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    """Store one current member record's manual correction (seconds, full
    float precision). The reference may carry a correction too:
    corrections belong to a record's clock, not to the reference role."""
    if not correction_valid(correction_s):
        raise InvalidReconstructionCorrectionError("correction_s must be a finite number of seconds.")
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    definition = _require_current_member(workspace_id=workspace_id, record_id=record_id, registry=registry, timings=timings)
    definition = _rebased(definition, definition.with_correction(record_id, float(correction_s)), timings)
    registry.put(workspace_id, definition)
    return _build_view(definition, timings, large_gap_threshold_s)


def reset_member_correction(
    *, workspace_id: str, record_id: str, registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry,
    large_gap_threshold_s: float,
) -> ReconstructionView:
    """Correction back to `0.0`: the record returns to its recorded-
    timestamp placement."""
    return set_member_correction(
        workspace_id=workspace_id, record_id=record_id, correction_s=0.0, registry=registry,
        source_registry=source_registry, large_gap_threshold_s=large_gap_threshold_s,
    )


# ------------------------------------------------------------------------------
# Annotations (DEC-136): the reconstruction's own storyline markers -- never
# Waveform annotations, never attached to a record.
# ------------------------------------------------------------------------------


def _require_definition(workspace_id: str, registry: EventReconstructionRegistry) -> EventReconstructionDefinition:
    definition = registry.get(workspace_id)
    if definition is None:
        raise ReconstructionNotDefinedError(f"Workspace '{workspace_id}' has no Event Reconstruction.")
    return definition


def _validated_time(reconstruction_time_s: float) -> float:
    if not annotation_time_valid(reconstruction_time_s):
        raise InvalidReconstructionAnnotationError("reconstruction_time_s must be a finite number of seconds.")
    return float(reconstruction_time_s)


def _validated_text(text: str | None) -> str:
    normalized = normalized_annotation_text(text)
    if normalized is None:
        raise InvalidReconstructionAnnotationError("An annotation needs a label of 1 to 200 characters.")
    return normalized


def add_reconstruction_annotation(
    *, workspace_id: str, reconstruction_time_s: float, text: str, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, large_gap_threshold_s: float,
) -> tuple[ReconstructionView, str]:
    """Add one annotation at a reconstruction time (current frame). Returns
    the view and the new annotation's id."""
    definition = _require_definition(workspace_id, registry)
    annotation = ReconstructionAnnotation(
        annotation_id="ann-" + uuid.uuid4().hex[:12],
        reconstruction_time_s=_validated_time(reconstruction_time_s),
        text=_validated_text(text),
    )
    definition = definition.with_annotations((*definition.annotations, annotation))
    registry.put(workspace_id, definition)
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    return _build_view(definition, timings, large_gap_threshold_s), annotation.annotation_id


def update_reconstruction_annotation(
    *, workspace_id: str, annotation_id: str, reconstruction_time_s: float | None, text: str | None,
    registry: EventReconstructionRegistry, source_registry: WorkspaceRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    """Move and/or relabel one annotation; a field left `None` is kept."""
    definition = _require_definition(workspace_id, registry)
    existing = definition.annotation(annotation_id)
    if existing is None:
        raise ReconstructionAnnotationNotFoundError(f"No annotation '{annotation_id}' in the reconstruction.")
    updated = replace(
        existing,
        reconstruction_time_s=existing.reconstruction_time_s if reconstruction_time_s is None else _validated_time(reconstruction_time_s),
        text=existing.text if text is None else _validated_text(text),
    )
    definition = definition.with_annotations(updated if a.annotation_id == annotation_id else a for a in definition.annotations)
    registry.put(workspace_id, definition)
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    return _build_view(definition, timings, large_gap_threshold_s)


def delete_reconstruction_annotation(
    *, workspace_id: str, annotation_id: str, registry: EventReconstructionRegistry,
    source_registry: WorkspaceRegistry, large_gap_threshold_s: float,
) -> ReconstructionView:
    definition = _require_definition(workspace_id, registry)
    if definition.annotation(annotation_id) is None:
        raise ReconstructionAnnotationNotFoundError(f"No annotation '{annotation_id}' in the reconstruction.")
    definition = definition.with_annotations(a for a in definition.annotations if a.annotation_id != annotation_id)
    registry.put(workspace_id, definition)
    timings = _record_timings(workspace_id=workspace_id, source_registry=source_registry)
    return _build_view(definition, timings, large_gap_threshold_s)


def clear_reconstruction(*, workspace_id: str, registry: EventReconstructionRegistry) -> None:
    """Remove the workspace's reconstruction. Idempotent."""
    registry.remove_workspace(workspace_id)


def remove_workspace_event_reconstruction_state(*, workspace_id: str, registry: EventReconstructionRegistry) -> None:
    """Workspace-teardown hook ("Start New Workspace"), called from
    app.api.v1.workspaces.delete_workspace. Source removal deliberately
    has no hook: the affected member simply reads as stale."""
    registry.remove_workspace(workspace_id)
