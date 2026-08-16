"""API response/error DTOs for the Phase 1 COMTRADE source/channel API.

Deliberately excludes any waveform/sample array field -- see
docs/project-memory/MIGRATION_PLAN.md Sec 8 (API response size discipline).
Converts explicitly from app.domain.source.SourceMetadata rather than
relying on blanket from_attributes mapping, since the wire shape nests
timing/sampling information under "timebase" while the domain object keeps
those fields flat.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.source import SourceMetadata


class AnalogChannelOut(BaseModel):
    """Full analog channel record, including engineering fields (scale/offset)
    that the Phase 1 frontend's primary browsing table deliberately does not
    display (UAT feedback: little browsing value) but which stay in the API
    and domain model -- see
    docs/project-memory/MIGRATION_PLAN.md's Phase 1 refinement record.
    `engineering_type` is computed once, backend-side (app.domain.channel_classification),
    never re-derived client-side.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    index: int
    unit: str
    engineering_type: str
    phase: str | None = None
    scale: float
    offset: float
    primary_ratio: float | None = None
    secondary_ratio: float | None = None


class DigitalChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    index: int
    normal_state: int


class TimebaseOut(BaseModel):
    timing_reference: str
    start_time: datetime | None
    trigger_time: datetime | None
    sample_count: int
    duration_seconds: float
    sampling_rates: list[float]
    samples_per_rate: list[int]


class SourceSummaryOut(BaseModel):
    """Identity/status summary -- the shape returned by upload, list, and get-one.

    Phase 3B: `duration_seconds`/`sample_count` were added here (purely
    additive -- both already existed on `SourceMetadata`/`ActiveSource`,
    computed once at import time; no new storage, no new computation, no
    change to any existing field) so the Recordings page's list table can
    show a real Duration column without an extra per-row `.../channels`
    request for every listed recording.
    """

    source_id: str
    workspace_id: str
    provider_type: str
    original_filenames: list[str]
    status: str = "ready"
    created_at: datetime
    station_name: str
    recorder_name: str
    nominal_frequency: float
    analog_channel_count: int
    digital_channel_count: int
    duration_seconds: float
    sample_count: int

    @classmethod
    def from_domain(cls, source: SourceMetadata) -> "SourceSummaryOut":
        return cls(
            source_id=source.source_id,
            workspace_id=source.workspace_id,
            provider_type=source.provider_type,
            original_filenames=list(source.original_filenames),
            created_at=source.created_at,
            station_name=source.station_name,
            recorder_name=source.recorder_name,
            nominal_frequency=source.nominal_frequency,
            analog_channel_count=len(source.analog_channels),
            digital_channel_count=len(source.digital_channels),
            duration_seconds=source.duration_seconds,
            sample_count=source.sample_count,
        )


class SourceChannelsOut(BaseModel):
    """The Phase 1 payload: one source's summary + timebase + full channel list."""

    source: SourceSummaryOut
    timebase: TimebaseOut
    analog_channels: list[AnalogChannelOut]
    digital_channels: list[DigitalChannelOut]

    @classmethod
    def from_domain(cls, source: SourceMetadata) -> "SourceChannelsOut":
        return cls(
            source=SourceSummaryOut.from_domain(source),
            timebase=TimebaseOut(
                timing_reference=source.timing_reference,
                start_time=source.start_time,
                trigger_time=source.trigger_time,
                sample_count=source.sample_count,
                duration_seconds=source.duration_seconds,
                sampling_rates=list(source.sampling_rates),
                samples_per_rate=list(source.samples_per_rate),
            ),
            analog_channels=[
                AnalogChannelOut.model_validate(ch) for ch in source.analog_channels
            ],
            digital_channels=[
                DigitalChannelOut.model_validate(ch) for ch in source.digital_channels
            ],
        )


class ErrorOut(BaseModel):
    """User-safe structured error. Never carries a raw traceback -- see
    docs/project-memory/MIGRATION_PLAN.md Sec 9 and app.services.errors.
    """

    code: str
    message: str
