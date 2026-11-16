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

#: Explicit format-variant identifier for the BEN32 BEN5K Legacy record class.
#: Stored in RecordingMetadata.format_variant when a BEN5K record is normalised.
#: Used by services that need to identify BEN5K legacy records independently of
#: timestamp-authority properties (time_basis is a separate, independent concept).
FORMAT_VARIANT_BEN5K_LEGACY = "BEN5K_LEGACY"


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
    # Stage 3B-2A (DEC-213): explicit format variant, set by providers that emit
    # a known sub-format. None for COMTRADE, CSV/Excel and legacy BEN32 SubBen.
    # Must NOT be derived from timestamp-authority properties (time_basis is
    # independent) or from channel names. Currently: FORMAT_VARIANT_BEN5K_LEGACY
    # for BEN32 BEN5K Legacy records; None for every other provider.
    format_variant: str | None = None
