"""Recording-level metadata.

Ported near-verbatim from powerwave's app/models/metadata.py (commit 3156392).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RecordingMetadata:
    """Recording-level identity and configuration for a disturbance record."""

    station_name: str
    recorder_name: str
    source_file: str
    provider_type: str
    nominal_frequency: float

    device_id: str | None = None
    location: str | None = None
    timezone: str | None = None
    comments: str | None = None
    timestamp_ambiguity_sample: str | None = None
