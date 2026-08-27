"""Wire shapes for Slice 3's assisted event-origin detection endpoint
(`POST .../synchronization/detect-event`).

Advisory only -- this endpoint never sets `t0` itself (see
app.services.synchronization_service.detect_event_candidate's own
docstring); accepting a candidate is a separate `PUT .../synchronization/t0`
call the frontend makes using Slice 2's existing, unmodified endpoint.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.event_detection import SENSITIVITY_NORMAL
from app.services.synchronization_service import DetectEventView


class DetectEventRequest(BaseModel):
    """`channel_name` (not `channel_id`, task section 26's own suggested
    naming) -- matches this codebase's own established convention for
    every other analog-channel-selecting request in this API
    (AnnotationAnchorRequest, PeakValueRequestItem, CursorValuesRequest
    all use `channel_name`), never a separate id scheme invented for
    this one endpoint. `search_start_time`/`search_end_time` are this
    source's own native elapsed seconds (task section 24's optional
    narrowing) -- omitted, the whole record is analysed."""

    source_id: str
    channel_name: str
    sensitivity: str = SENSITIVITY_NORMAL
    search_start_time: float | None = None
    search_end_time: float | None = None


class DetectEventOut(BaseModel):
    """`found=False` -- with every candidate/metric field `None` -- is a
    valid, expected response (task section 28), never an error."""

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

    @classmethod
    def from_view(cls, view: DetectEventView) -> "DetectEventOut":
        return cls(
            found=view.found,
            reason=view.reason,
            detector_method=view.detector_method,
            channel_unit=view.channel_unit,
            nominal_frequency_hz=view.nominal_frequency_hz,
            candidate_source_time=view.candidate_source_time,
            candidate_workspace_time=view.candidate_workspace_time,
            baseline_rms=view.baseline_rms,
            changed_rms=view.changed_rms,
            change_ratio=view.change_ratio,
            direction=view.direction,
            quality=view.quality,
        )
