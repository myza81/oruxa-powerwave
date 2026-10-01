"""Wire shapes for the Event Reconstruction API (DEC-123/DEC-124).

Members are addressed by `member_id` (their Time Group membership
fingerprint), never by `group_id`, because a Time Group's id can change
when sources are added or removed. Times named `*_s` are seconds (full
float precision); `start_s`/`end_s` are reconstruction time, where 0 is
the reference group's recorded origin instant shifted by the reference's
own correction. `*_utc` values are absolute instants in UTC.
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
    TimeGroupEligibilityView,
)


class ReconstructionTimeGroupOut(BaseModel):
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

    @classmethod
    def from_view(cls, view: TimeGroupEligibilityView) -> "ReconstructionTimeGroupOut":
        return cls(
            group_id=view.group_id,
            time_reference_type=view.time_reference_type,
            origin_source_id=view.origin_source_id,
            source_ids=list(view.source_ids),
            membership_fingerprint=view.membership_fingerprint,
            eligible=view.eligible,
            reason_code=view.reason_code,
            reason_message=view.reason_message,
            start_time_utc=view.start_time_utc,
            end_time_utc=view.end_time_utc,
            duration_s=view.duration_s,
            note=view.note,
            reconstruction_member_id=view.reconstruction_member_id,
        )


class ReconstructionSourceTimingOut(BaseModel):
    """Slice 3B: one member source's mapping onto the reconstruction
    timeline -- `reconstruction_x_s = source_elapsed_s +
    total_reconstruction_offset_s`. `total_reconstruction_offset_s` =
    `within_group_offset_s` (existing effective placement in its Time
    Group, incl. Synchronise Sources) + `reconstruction_group_offset_s`
    (the member's offset to the reference, incl. Event Reconstruction
    corrections). Start/end are the source's own extent mapped. Seconds,
    full float precision."""

    source_id: str
    within_group_offset_s: float
    reconstruction_group_offset_s: float
    total_reconstruction_offset_s: float
    reconstruction_start_s: float
    reconstruction_end_s: float

    @classmethod
    def from_view(cls, view: ReconstructionSourceTimingView) -> "ReconstructionSourceTimingOut":
        return cls(
            source_id=view.source_id,
            within_group_offset_s=view.within_group_offset_s,
            reconstruction_group_offset_s=view.reconstruction_group_offset_s,
            total_reconstruction_offset_s=view.total_reconstruction_offset_s,
            reconstruction_start_s=view.reconstruction_start_s,
            reconstruction_end_s=view.reconstruction_end_s,
        )


class ReconstructionMemberOut(BaseModel):
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
    # Slice 3B, additive: `null` whenever placements are unavailable (stale
    # member or stale reference) -- never a mapping for stale state.
    source_timings: list[ReconstructionSourceTimingOut] | None

    @classmethod
    def from_view(cls, view: ReconstructionMemberView) -> "ReconstructionMemberOut":
        return cls(
            member_id=view.member_id,
            source_ids=list(view.source_ids),
            confirmed_group_id=view.confirmed_group_id,
            current_group_id=view.current_group_id,
            status=view.status,
            stale_reason=view.stale_reason,
            candidate_group_ids=list(view.candidate_group_ids),
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
    member_a_id: str
    member_b_id: str
    kind: str
    gap_s: float
    overlap_s: float

    @classmethod
    def from_view(cls, view: ReconstructionRelationshipView) -> "ReconstructionRelationshipOut":
        return cls(
            member_a_id=view.member_a_id, member_b_id=view.member_b_id, kind=view.kind,
            gap_s=view.gap_s, overlap_s=view.overlap_s,
        )


class ReconstructionWarningOut(BaseModel):
    code: str
    message: str
    before_member_id: str
    after_member_id: str
    gap_s: float
    threshold_s: float

    @classmethod
    def from_view(cls, view: ReconstructionWarningView) -> "ReconstructionWarningOut":
        return cls(
            code=view.code, message=view.message, before_member_id=view.before_member_id,
            after_member_id=view.after_member_id, gap_s=view.gap_s, threshold_s=view.threshold_s,
        )


class ReconstructionOut(BaseModel):
    """`defined: false` (with empty lists) when the workspace has no
    reconstruction yet. `status` is `ready` or `stale`; `stale` means at
    least one member must be re-confirmed. `placements_available` is
    `false` while the reference member is stale."""

    defined: bool
    status: str | None
    reference_member_id: str | None
    reference_origin_start_time_utc: datetime | None
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
            reference_member_id=view.reference_member_id,
            reference_origin_start_time_utc=view.reference_origin_start_time_utc,
            placements_available=view.placements_available,
            large_gap_warning_threshold_s=view.large_gap_warning_threshold_s,
            members=[ReconstructionMemberOut.from_view(m) for m in view.members],
            relationships=[ReconstructionRelationshipOut.from_view(r) for r in view.relationships],
            warnings=[ReconstructionWarningOut.from_view(w) for w in view.warnings],
        )


class ReconstructionDefinitionRequest(BaseModel):
    """Create or replace (and re-confirm) the reconstruction from current
    Time Group ids, in selection order."""

    group_ids: list[str]
    reference_group_id: str


class ReconstructionReferenceRequest(BaseModel):
    member_id: str


class ReconstructionCorrectionRequest(BaseModel):
    correction_s: float
