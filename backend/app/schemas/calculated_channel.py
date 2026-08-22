"""Wire shapes for the Phase 5A Calculated Channels API (DEC-047).

JSON-first, same convention as app.schemas.waveform -- no binary format.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import numpy as np
from pydantic import BaseModel, model_validator

from app.services.calculated_channel_service import (
    CalculatedAnnotationAnchorResult,
    CalculatedCursorValues,
    CalculatedPeakResult,
    CalculatedWaveformRangeResult,
    RmsEligibility,
)
from app.domain.calculated_channel import CalculatedChannel, ChannelRef


def _sanitize_float_list(values) -> list[float | None]:
    """Phase 5B: NaN -> `null`, everything else unchanged. See
    app.services.calculated_channel_service._finite_or_none's own
    docstring for why this sanitization exists and why it is applied at
    this calculated-channel-only serialization boundary."""
    return [float(v) if np.isfinite(v) else None for v in values]


class ChannelRefIn(BaseModel):
    """Wire shape of app.domain.calculated_channel.ChannelRef -- section 57's
    one structured reference, never a parsed string prefix."""

    kind: Literal["source", "calculated"]
    source_id: str | None = None
    channel_name: str | None = None
    calculated_channel_id: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> "ChannelRefIn":
        if self.kind == "source" and (not self.source_id or not self.channel_name):
            raise ValueError("A 'source' input requires both source_id and channel_name.")
        if self.kind == "calculated" and not self.calculated_channel_id:
            raise ValueError("A 'calculated' input requires calculated_channel_id.")
        return self

    def to_domain(self) -> ChannelRef:
        return ChannelRef(
            kind=self.kind,
            source_id=self.source_id,
            channel_name=self.channel_name,
            calculated_channel_id=self.calculated_channel_id,
        )


class ChannelRefOut(BaseModel):
    kind: str
    source_id: str | None = None
    channel_name: str | None = None
    calculated_channel_id: str | None = None

    @classmethod
    def from_domain(cls, ref: ChannelRef) -> "ChannelRefOut":
        return cls(
            kind=ref.kind, source_id=ref.source_id,
            channel_name=ref.channel_name, calculated_channel_id=ref.calculated_channel_id,
        )


class CalculatedChannelCreateRequest(BaseModel):
    """Request body for POST .../calculated-channels.

    `parameters` is operation-specific -- `multiply_constant` reads
    `{"constant": <finite number>}`; `rms` (Phase 5B) reads
    `{"nominal_frequency_hz": <finite number>}`; every other operation
    ignores it. Section 74: no free-form formula text anywhere in this
    shape.

    `override` (Phase 5B, DEC-048) only matters for `rms`: the engineer's
    explicit "Calculate anyway" acknowledgement when RMS eligibility is
    not `suitable`. A strongly-typed top-level field, deliberately not
    buried inside the loosely-typed `parameters` dict -- it is a
    cross-cutting safety flag the backend must independently validate,
    never a math parameter. Ignored (never trusted as an eligibility
    result itself) for every other operation.
    """

    name: str
    operation: Literal["reverse_polarity", "absolute_value", "multiply_constant", "addition", "subtraction", "rms"]
    inputs: list[ChannelRefIn]
    parameters: dict = {}
    override: bool = False


class RmsEligibilityRequest(BaseModel):
    """Request body for POST .../calculated-channels/rms-eligibility --
    a stateless, side-effect-free pre-check the Signal Builder calls on
    every input/nominal-frequency change, independent of Create (section
    44)."""

    input: ChannelRefIn
    nominal_frequency_hz: float


class RmsEligibilityResponse(BaseModel):
    status: Literal["suitable", "likely_already_rms_or_magnitude", "uncertain"]
    reason: str
    override_required: bool

    @classmethod
    def from_result(cls, result: RmsEligibility) -> "RmsEligibilityResponse":
        return cls(status=result.status, reason=result.reason, override_required=result.override_required)


class CalculatedChannelOut(BaseModel):
    """One calculated channel's definition + metadata -- never its full
    sample arrays (mirrors SourceSummaryOut's own "metadata only" shape;
    waveform data is served separately, on demand, exactly like a real
    source channel)."""

    id: str
    workspace_id: str
    name: str
    unit: str
    operation: str
    inputs: list[ChannelRefOut]
    parameters: dict
    dependency_ids: list[str]
    reference_source_id: str
    sample_count: int
    created_at: datetime
    # Phase 5A-UAT4 (DEC-047 clarification): additive field -- the
    # inherited engineering classification (app.domain.
    # channel_classification.KNOWN_CATEGORIES), used by the Waveform
    # sidebar to subgroup Calculated Channels the same way Analog
    # Channels are subgrouped. Every pre-existing field/consumer is
    # unchanged.
    engineering_type: str
    # Phase 5B (DEC-048): additive field -- this channel's own
    # waveform-form classification (app.domain.channel_classification.
    # KNOWN_WAVEFORM_FORMS), computed once at creation by
    # derive_waveform_form(). An RMS channel is always "rms" here (owner
    # section 10: "the waveform form should be identifiable as RMS").
    # Every pre-existing field/consumer is unchanged.
    waveform_form: str

    @classmethod
    def from_domain(cls, channel: CalculatedChannel) -> "CalculatedChannelOut":
        return cls(
            id=channel.id,
            workspace_id=channel.workspace_id,
            name=channel.name,
            unit=channel.unit,
            operation=channel.operation,
            inputs=[ChannelRefOut.from_domain(ref) for ref in channel.inputs],
            parameters=channel.parameters,
            dependency_ids=channel.dependency_ids,
            reference_source_id=channel.reference_source_id,
            sample_count=int(channel.time.shape[0]),
            created_at=channel.created_at,
            engineering_type=channel.engineering_type,
            waveform_form=channel.waveform_form,
        )


class CalculatedWaveformRangeOut(BaseModel):
    calculated_channel_id: str
    name: str
    unit: str
    start_time: float
    end_time: float
    original_sample_count: int
    returned_point_count: int
    representation: str
    # Phase 5B: `float | None` (was `list[float]`) -- an RMS channel's
    # leading warm-up region is routine, guaranteed NaN in the underlying
    # numpy array; `null` is what reaches JSON instead (see
    # _sanitize_float_list's own docstring). Widening only -- every
    # pre-existing operation never produces NaN, so this is a no-op for
    # them.
    time: list[float | None]
    values: list[float | None]
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: CalculatedWaveformRangeResult) -> "CalculatedWaveformRangeOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id,
            name=result.name,
            unit=result.unit,
            start_time=result.start_time,
            end_time=result.end_time,
            original_sample_count=result.original_sample_count,
            returned_point_count=len(result.time),
            representation=result.representation,
            time=_sanitize_float_list(result.time),
            values=_sanitize_float_list(result.values),
            per_unit_status=result.per_unit_status,
        )


class CalculatedCursorValuesRequest(BaseModel):
    calculated_channel_ids: list[str]
    cursor_a_time: float | None = None
    cursor_b_time: float | None = None
    # Phase 5C (DEC-049): "engineering" (default) or "per_unit".
    unit_mode: str = "engineering"


class CalculatedCursorValuesItemOut(BaseModel):
    calculated_channel_id: str
    name: str
    unit: str
    a_value: float | None
    b_value: float | None
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: CalculatedCursorValues) -> "CalculatedCursorValuesItemOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, name=result.name,
            unit=result.unit, a_value=result.a_value, b_value=result.b_value,
            per_unit_status=result.per_unit_status,
        )


class CalculatedCursorValuesOut(BaseModel):
    channels: list[CalculatedCursorValuesItemOut]


class CalculatedPeakRequestItem(BaseModel):
    calculated_channel_id: str
    mode: Literal["max", "min"]


class CalculatedPeakBatchRequest(BaseModel):
    requests: list[CalculatedPeakRequestItem]
    start_time: float
    end_time: float
    # Phase 5C (DEC-049): "engineering" (default) or "per_unit".
    unit_mode: str = "engineering"


class CalculatedPeakResultOut(BaseModel):
    calculated_channel_id: str
    mode: str
    available: bool
    sample_index: int | None
    elapsed_seconds: float | None
    value: float | None
    unit: str | None
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: CalculatedPeakResult) -> "CalculatedPeakResultOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, mode=result.mode,
            available=result.available, sample_index=result.sample_index,
            elapsed_seconds=result.elapsed_seconds, value=result.value, unit=result.unit,
            per_unit_status=result.per_unit_status,
        )


class CalculatedPeakBatchOut(BaseModel):
    start_time: float
    end_time: float
    results: list[CalculatedPeakResultOut]


class CalculatedAnnotationAnchorRequest(BaseModel):
    approximate_elapsed_seconds: float
    # Phase 5C (DEC-049): "engineering" (default) or "per_unit".
    unit_mode: str = "engineering"


class CalculatedAnnotationAnchorOut(BaseModel):
    calculated_channel_id: str
    unit: str
    sample_index: int
    elapsed_seconds: float
    # Phase 5B: `float | None` (was `float`) -- see
    # CalculatedAnnotationAnchorResult's own docstring; the anchor itself
    # is always valid, only the displayed value can be unavailable
    # (an RMS channel's warm-up region).
    value: float | None
    per_unit_status: str | None = None

    @classmethod
    def from_result(cls, result: CalculatedAnnotationAnchorResult) -> "CalculatedAnnotationAnchorOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, unit=result.unit,
            sample_index=result.sample_index, elapsed_seconds=result.elapsed_seconds, value=result.value,
            per_unit_status=result.per_unit_status,
        )
