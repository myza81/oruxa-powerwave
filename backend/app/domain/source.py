"""Lightweight, ephemeral source/channel metadata.

These types are what actually gets held in memory across requests (see
app.services.workspace_registry) -- never the full DisturbanceRecord or its
waveform_data DataFrame. Building these immediately after parsing and then
letting the DisturbanceRecord go out of scope is what keeps Phase 1 free of
retained waveform arrays (see docs/project-memory/MIGRATION_PLAN.md Sec 12
"Record aliasing risk" and Sec 13 "Full-resolution data ownership").

Zero framework dependencies, per the domain/ layer contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class AnalogChannelSummary:
    name: str
    index: int
    unit: str
    phase: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    primary_ratio: float | None = None
    secondary_ratio: float | None = None


@dataclass(slots=True)
class DigitalChannelSummary:
    name: str
    index: int
    normal_state: int = 0


@dataclass(slots=True)
class SourceMetadata:
    """Everything the Phase 1 API needs to answer channel-list requests.

    Deliberately excludes waveform_data / any sample array -- see the module
    docstring. This is the object the in-memory WorkspaceRegistry stores.
    """

    source_id: str
    workspace_id: str
    provider_type: str
    original_filenames: tuple[str, ...]
    created_at: datetime

    station_name: str
    recorder_name: str
    nominal_frequency: float

    timing_reference: str
    start_time: datetime | None
    trigger_time: datetime | None

    sample_count: int
    duration_seconds: float
    sampling_rates: tuple[float, ...]
    samples_per_rate: tuple[int, ...]

    analog_channels: list[AnalogChannelSummary] = field(default_factory=list)
    digital_channels: list[DigitalChannelSummary] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
