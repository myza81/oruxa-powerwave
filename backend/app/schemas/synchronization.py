"""Wire shapes for the Slice 1 waveform time-synchronization API.

A source's alignment offset is identified by its own owning `source_id`
(the URL path parameter), mirroring `app.schemas.per_unit`'s own
source-bound shape -- no separate synchronization-state identity exists.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.synchronization_service import SourceAlignmentView


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
