"""Wire shapes for the Event Reconstruction API (DEC-123, DEC-124,
DEC-128).

Members are independently imported RECORDS addressed by `record_id` (the
record's `source_id`, one upload = one logical event) -- never by a
Waveform Time Group. Times named `*_s` are seconds (full float
precision); `start_s`/`end_s` are reconstruction time, where 0 is the
reference record's recorded start shifted by the reference's own
correction. `*_utc` values are absolute instants in UTC.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.services.event_reconstruction_service import (
    ReconstructionMemberView,
    ReconstructionRelationshipView,
    ReconstructionSourceTimingView,
    ReconstructionView,
    ReconstructionWarningView,
    RecordEligibilityView,
)


class ReconstructionRecordOut(BaseModel):
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

    @classmethod
    def from_view(cls, view: RecordEligibilityView) -> "ReconstructionRecordOut":
        return cls(
            record_id=view.record_id,
            source_ids=list(view.source_ids),
            time_reference_type=view.time_reference_type,
            eligible=view.eligible,
            reason_code=view.reason_code,
            reason_message=view.reason_message,
            start_time_utc=view.start_time_utc,
            end_time_utc=view.end_time_utc,
            duration_s=view.duration_s,
            in_reconstruction=view.in_reconstruction,
        )


class ReconstructionSourceTimingOut(BaseModel):
    """One constituent source's mapping onto the reconstruction timeline:
    `reconstruction_x_s = source_elapsed_s + total_reconstruction_offset_s`.
    `total_reconstruction_offset_s` = `within_record_offset_s` (where the
    source sits inside its record; 0 for a single-source record) +
    `reconstruction_record_offset_s` (the record's offset to the
    reference, incl. Event Reconstruction corrections). Start/end are the
    source's own extent mapped. Seconds, full float precision."""

    source_id: str
    within_record_offset_s: float
    reconstruction_record_offset_s: float
    total_reconstruction_offset_s: float
    reconstruction_start_s: float
    reconstruction_end_s: float

    @classmethod
    def from_view(cls, view: ReconstructionSourceTimingView) -> "ReconstructionSourceTimingOut":
        return cls(
            source_id=view.source_id,
            within_record_offset_s=view.within_record_offset_s,
            reconstruction_record_offset_s=view.reconstruction_record_offset_s,
            total_reconstruction_offset_s=view.total_reconstruction_offset_s,
            reconstruction_start_s=view.reconstruction_start_s,
            reconstruction_end_s=view.reconstruction_end_s,
        )


class ReconstructionMemberOut(BaseModel):
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
    # `null` whenever placements are unavailable (stale member or stale
    # reference) -- never a mapping for stale state.
    source_timings: list[ReconstructionSourceTimingOut] | None

    @classmethod
    def from_view(cls, view: ReconstructionMemberView) -> "ReconstructionMemberOut":
        return cls(
            record_id=view.record_id,
            source_ids=list(view.source_ids),
            status=view.status,
            stale_reason=view.stale_reason,
            is_reference=view.is_reference,
            correction_s=view.correction_s,
            correction_relative_to_reference_s=view.correction_relative_to_reference_s,
            recorded_placement_s=view.recorded_placement_s,
            reconstruction_offset_s=view.reconstruction_offset_s,
            start_s=view.start_s,
            end_s=view.end_s,
            recorded_start_time_utc=view.recorded_start_time_utc,
            recorded_end_time_utc=view.recorded_end_time_utc,
            source_timings=(
                [ReconstructionSourceTimingOut.from_view(t) for t in view.source_timings]
                if view.source_timings is not None else None
            ),
        )


class ReconstructionRelationshipOut(BaseModel):
    record_a_id: str
    record_b_id: str
    kind: str
    gap_s: float
    overlap_s: float

    @classmethod
    def from_view(cls, view: ReconstructionRelationshipView) -> "ReconstructionRelationshipOut":
        return cls(
            record_a_id=view.record_a_id, record_b_id=view.record_b_id, kind=view.kind,
            gap_s=view.gap_s, overlap_s=view.overlap_s,
        )


class ReconstructionWarningOut(BaseModel):
    code: str
    message: str
    before_record_id: str
    after_record_id: str
    gap_s: float
    threshold_s: float

    @classmethod
    def from_view(cls, view: ReconstructionWarningView) -> "ReconstructionWarningOut":
        return cls(
            code=view.code, message=view.message, before_record_id=view.before_record_id,
            after_record_id=view.after_record_id, gap_s=view.gap_s, threshold_s=view.threshold_s,
        )


class ReconstructionOut(BaseModel):
    """`defined: false` (with empty lists) when the workspace has no
    reconstruction yet. `status` is `ready` or `stale`; `stale` means at
    least one member record was removed. `placements_available` is
    `false` while the reference record is stale.

    `reconstruction_zero_time_utc` (additive) is the absolute instant of
    reconstruction time 0 -- the reference's recorded start plus its own
    correction -- so `absolute = reconstruction_zero_time_utc + x` for any
    reconstruction time x (Relative / Absolute time display). `null` when
    placements are unavailable."""

    defined: bool
    status: str | None
    reference_record_id: str | None
    reference_origin_start_time_utc: datetime | None
    reconstruction_zero_time_utc: datetime | None
    placements_available: bool
    large_gap_warning_threshold_s: float
    members: list[ReconstructionMemberOut]
    relationships: list[ReconstructionRelationshipOut]
    warnings: list[ReconstructionWarningOut]

    @classmethod
    def from_view(cls, view: ReconstructionView) -> "ReconstructionOut":
        return cls(
            defined=view.defined,
            status=view.status,
            reference_record_id=view.reference_record_id,
            reference_origin_start_time_utc=view.reference_origin_start_time_utc,
            reconstruction_zero_time_utc=view.reconstruction_zero_time_utc,
            placements_available=view.placements_available,
            large_gap_warning_threshold_s=view.large_gap_warning_threshold_s,
            members=[ReconstructionMemberOut.from_view(m) for m in view.members],
            relationships=[ReconstructionRelationshipOut.from_view(r) for r in view.relationships],
            warnings=[ReconstructionWarningOut.from_view(w) for w in view.warnings],
        )


class ReconstructionDefinitionRequest(BaseModel):
    """Create or replace the reconstruction from current record ids, in
    selection order."""

    record_ids: list[str]
    reference_record_id: str


class ReconstructionReferenceRequest(BaseModel):
    record_id: str


class ReconstructionCorrectionRequest(BaseModel):
    correction_s: float
