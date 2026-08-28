"""Wire shapes for the waveform time-synchronization API (Slice 1:
per-source manual alignment offsets; Slice 2: event origin, now
Time-Group-scoped; Timestamp-Based Initial Alignment and Time Groups:
`timestamp_placement_offset_s`/`effective_alignment_offset_s`/Time
Group listing).

A source's alignment state is identified by its own owning `source_id`
(the URL path parameter), mirroring `app.schemas.per_unit`'s own
source-bound shape -- no separate synchronization-state identity exists.
`t0_workspace_time` has no `source_id` of its OWN identity either (it is
still one value per TIME GROUP, never per-source) but every t0 request
below carries a `source_id` purely to RESOLVE which group's t0 is meant
-- see app.services.synchronization_service's own module docstring for
the full rationale.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.synchronization_service import SourceAlignmentView, T0View
from app.domain.time_grouping import TimeGroup


class SourceAlignmentUpdateRequest(BaseModel):
    """Request body for PUT .../synchronization/sources/{source_id}.
    Sets the MANUAL correction only -- `timestamp_placement_offset_s` is
    derived, never writable through this endpoint (task section 20)."""

    alignment_offset_s: float


class SourceAlignmentOut(BaseModel):
    """`alignment_offset_s` (kept under its original Slice 1 name for
    API continuity) is now the EFFECTIVE offset -- `timestamp_placement_offset_s
    + manual_alignment_offset_s` -- i.e. exactly the value every existing
    waveform-positioning call site already needs (task section 3's own
    composed formula). `manual_alignment_offset_s` is the value the
    Synchronize Sources UI's own editable field now reads/writes (task
    section 20: "UI may initially continue to show the manual correction
    as the editable value"). `timestamp_placement_offset_s` and
    `time_group_id` are new, purely additive provenance/grouping fields."""

    source_id: str
    time_group_id: str
    alignment_offset_s: float
    timestamp_placement_offset_s: float
    manual_alignment_offset_s: float
    is_reference: bool

    @classmethod
    def from_view(cls, view: SourceAlignmentView) -> "SourceAlignmentOut":
        return cls(
            source_id=view.source_id,
            time_group_id=view.time_group_id,
            alignment_offset_s=view.effective_alignment_offset_s,
            timestamp_placement_offset_s=view.timestamp_placement_offset_s,
            manual_alignment_offset_s=view.manual_alignment_offset_s,
            is_reference=view.is_reference,
        )


class TimeGroupOut(BaseModel):
    """One Time Group (task section 9) -- "one coherent time domain."
    `group_id`/`origin_source_id` are always the same value (see
    app.domain.time_grouping's own docstring for why); both are exposed
    so a caller never needs to know that fact to use either field
    correctly. `note` is `None` except for a `recorded_absolute` group
    that failed to temporally overlap any OTHER `recorded_absolute`
    source present in the same workspace (task section 11)."""

    group_id: str
    time_reference_type: str
    origin_source_id: str
    source_ids: list[str]
    note: str | None

    @classmethod
    def from_group(cls, group: TimeGroup) -> "TimeGroupOut":
        return cls(
            group_id=group.group_id,
            time_reference_type=group.time_reference_type,
            origin_source_id=group.origin_source_id,
            source_ids=list(group.source_ids),
            note=group.note,
        )


class T0UpdateRequest(BaseModel):
    """Request body for PUT .../synchronization/t0. `source_id`
    resolves WHICH time group's own event origin is being set (task
    section 24) -- t0 itself remains one value per coherent time domain,
    never per-source."""

    source_id: str
    t0_workspace_time: float


class T0Out(BaseModel):
    """`t0_workspace_time` is `None` exactly when no event origin has
    been selected for this time group (or it was cleared) -- never a
    fabricated `0.0` default (see `SynchronizationRegistry.get_t0()`'s
    own docstring). `time_group_id` echoes back which group this
    resolved to."""

    time_group_id: str
    t0_workspace_time: float | None

    @classmethod
    def from_view(cls, view: T0View) -> "T0Out":
        return cls(time_group_id=view.time_group_id, t0_workspace_time=view.t0_workspace_time)
