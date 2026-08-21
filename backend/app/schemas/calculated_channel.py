"""Wire shapes for the Phase 5A Calculated Channels API (DEC-047).

JSON-first, same convention as app.schemas.waveform -- no binary format.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from app.services.calculated_channel_service import (
    CalculatedAnnotationAnchorResult,
    CalculatedCursorValues,
    CalculatedPeakResult,
    CalculatedWaveformRangeResult,
)
from app.domain.calculated_channel import CalculatedChannel, ChannelRef


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

    `parameters` is operation-specific -- only `multiply_constant` reads
    it (`{"constant": <finite number>}`); every other operation ignores
    it. Section 74: no free-form formula text anywhere in this shape.
    """

    name: str
    operation: Literal["reverse_polarity", "absolute_value", "multiply_constant", "addition", "subtraction"]
    inputs: list[ChannelRefIn]
    parameters: dict = {}


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
    time: list[float]
    values: list[float]

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
            time=result.time.tolist(),
            values=result.values.tolist(),
        )


class CalculatedCursorValuesRequest(BaseModel):
    calculated_channel_ids: list[str]
    cursor_a_time: float | None = None
    cursor_b_time: float | None = None


class CalculatedCursorValuesItemOut(BaseModel):
    calculated_channel_id: str
    name: str
    unit: str
    a_value: float | None
    b_value: float | None

    @classmethod
    def from_result(cls, result: CalculatedCursorValues) -> "CalculatedCursorValuesItemOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, name=result.name,
            unit=result.unit, a_value=result.a_value, b_value=result.b_value,
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


class CalculatedPeakResultOut(BaseModel):
    calculated_channel_id: str
    mode: str
    available: bool
    sample_index: int | None
    elapsed_seconds: float | None
    value: float | None
    unit: str | None

    @classmethod
    def from_result(cls, result: CalculatedPeakResult) -> "CalculatedPeakResultOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, mode=result.mode,
            available=result.available, sample_index=result.sample_index,
            elapsed_seconds=result.elapsed_seconds, value=result.value, unit=result.unit,
        )


class CalculatedPeakBatchOut(BaseModel):
    start_time: float
    end_time: float
    results: list[CalculatedPeakResultOut]


class CalculatedAnnotationAnchorRequest(BaseModel):
    approximate_elapsed_seconds: float


class CalculatedAnnotationAnchorOut(BaseModel):
    calculated_channel_id: str
    unit: str
    sample_index: int
    elapsed_seconds: float
    value: float

    @classmethod
    def from_result(cls, result: CalculatedAnnotationAnchorResult) -> "CalculatedAnnotationAnchorOut":
        return cls(
            calculated_channel_id=result.calculated_channel_id, unit=result.unit,
            sample_index=result.sample_index, elapsed_seconds=result.elapsed_seconds, value=result.value,
        )
