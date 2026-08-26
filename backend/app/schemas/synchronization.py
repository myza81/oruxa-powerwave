"""Wire shapes for the waveform time-synchronization API (Slice 1:
per-source alignment offsets; Slice 2: one workspace-wide event origin).

A source's alignment offset is identified by its own owning `source_id`
(the URL path parameter), mirroring `app.schemas.per_unit`'s own
source-bound shape -- no separate synchronization-state identity exists.
Slice 2's `t0_workspace_time`, by contrast, has no `source_id` at all --
it is a single workspace-wide value (see app.domain.synchronization's
own module docstring for why).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.synchronization_service import SourceAlignmentView, T0View


class SourceAlignmentUpdateRequest(BaseModel):
    """Request body for PUT .../synchronization/sources/{source_id}."""

    alignment_offset_s: float


class SourceAlignmentOut(BaseModel):
    source_id: str
    alignment_offset_s: float
    is_reference: bool

    @classmethod
    def from_view(cls, view: SourceAlignmentView) -> "SourceAlignmentOut":
        return cls(
            source_id=view.source_id,
            alignment_offset_s=view.alignment_offset_s,
            is_reference=view.is_reference,
        )


class T0UpdateRequest(BaseModel):
    """Request body for PUT .../synchronization/t0."""

    t0_workspace_time: float


class T0Out(BaseModel):
    """`t0_workspace_time` is `None` exactly when no event origin has
    been selected (or it was cleared) -- never a fabricated `0.0`
    default (see `SynchronizationRegistry.get_t0()`'s own docstring)."""

    t0_workspace_time: float | None

    @classmethod
    def from_view(cls, view: T0View) -> "T0Out":
        return cls(t0_workspace_time=view.t0_workspace_time)
