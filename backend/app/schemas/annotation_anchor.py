"""Wire shape for the Callout annotation anchor-resolution endpoint
(Phase 4F, DEC-045).

A single-purpose endpoint -- resolves ONE authoritative full-resolution
sample identity/value for a Callout annotation at creation time. This is
NOT a persistent annotation backend: the frontend's own `ww.annotations`
remains the sole state authority for the Callout afterward (DEC-044/
DEC-045); this endpoint only ever answers "what is the nearest real
sample to this approximate time, on this channel."
"""

from __future__ import annotations

from pydantic import BaseModel

from app.services.waveform_service import AnnotationAnchorResult


class AnnotationAnchorRequest(BaseModel):
    """Request body for POST .../annotation-anchor.

    `channel_name` is an analog channel name as returned by GET
    .../channels (a digital channel name raises `channel_not_analog` --
    digital Callouts are out of scope this phase). `approximate_elapsed_seconds`
    is the engineer's clicked X position, elapsed seconds on this
    source's own native time axis (the same coordinate system every other
    time-based request in this API already uses) -- resolved server-side
    to the nearest ACTUAL recorded sample, never used as the anchor's own
    engineering time.
    """

    channel_name: str
    approximate_elapsed_seconds: float
    # Phase 5C (DEC-049): "engineering" (default) or "per_unit".
    unit_mode: str = "engineering"


class AnnotationAnchorOut(BaseModel):
    """The resolved, authoritative anchor -- a real recorded sample, never
    an interpolated or approximate value."""

    source_id: str
    channel_name: str
    unit: str
    sample_index: int
    elapsed_seconds: float
    value: float
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: AnnotationAnchorResult) -> "AnnotationAnchorOut":
        return cls(
            source_id=result.source_id,
            channel_name=result.channel_name,
            unit=result.unit,
            sample_index=result.sample_index,
            elapsed_seconds=result.elapsed_seconds,
            value=result.value,
            per_unit_status=result.per_unit_status,
        )
