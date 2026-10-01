"""Recording-level metadata.

Ported near-verbatim from powerwave's app/models/metadata.py (commit 3156392).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Conventional power-system nominal frequency used when a source format
#: does not declare one (CSV/Excel conversion, BEN import). A default,
#: never a detected value -- importers record it as assumed in the
#: source's provenance (``nominal_frequency_assumed``). Malaysia's grid
#: is 50 Hz.
DEFAULT_NOMINAL_FREQUENCY_HZ = 50.0


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
