"""Wire shapes for the Oscillation Analysis representation endpoint
(DEC-173 [APPROVED]). Metadata only -- no sample arrays."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefIn


class OscillationRepresentationRequest(BaseModel):
    input: ChannelRefIn
    #: Only `rms_magnitude` exists; the field lets later representations
    #: join without a new endpoint (unknown values are a 400).
    representation: str = "rms_magnitude"


class OscillationRepresentationOut(BaseModel):
    status: Literal["ready", "unavailable"]
    representation: str
    source_form: str | None = None
    reason_code: str | None = None
    message: str | None = None
    nominal_frequency_hz: float | None = None
    #: "recording_metadata" | "assumed_default"
    nominal_frequency_origin: str | None = None
    source_sample_count: int = 0
    source_sample_rate_hz: float | None = None
    source_start_s: float | None = None
    source_end_s: float | None = None
    # The following are present only when status == "ready".
    reporting: str | None = None
    representation_sample_rate_hz: float | None = None
    derived_sample_count: int | None = None
    window_s: float | None = None
    window_alignment: str | None = None
    group_delay_s: float | None = None
    valid_start_s: float | None = None
    valid_end_s: float | None = None
    boundary_loss_start_s: float | None = None
    boundary_loss_end_s: float | None = None
    bandwidth_half_power_hz: float | None = None
    bandwidth_limit_hz: float | None = None
