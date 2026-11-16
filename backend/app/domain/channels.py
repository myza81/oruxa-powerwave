"""Channel descriptors.

Ported near-verbatim from powerwave's app/models/channels.py (commit
3156392). Channels never carry sample data -- that lives only in
DisturbanceRecord.waveform_data, keyed by channel name.
"""

from __future__ import annotations

from dataclasses import dataclass
from app.domain.reference_side import ReferenceSide

# TYPE_CHECKING guard keeps the import lightweight for callers that do not
# use the calibration contract.  At runtime the type annotation is a string
# (from __future__ import annotations), so no circular-import risk.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.domain.physical_calibration import PhysicalCalibrationAuthority


@dataclass(slots=True)
class AnalogChannel:
    """Descriptor for one analog waveform channel (voltage, current, frequency, etc.)."""

    name: str
    unit: str
    index: int

    phase: str | None = None
    description: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    primary_ratio: float | None = None
    secondary_ratio: float | None = None
    parameter_type: str | None = None
    measurement_side: ReferenceSide = "unknown"
    # Stage 3A: optional immutable calibration authority.  None = not assessed.
    # Renaming or regrouping a channel does NOT alter this object.
    calibration_authority: PhysicalCalibrationAuthority | None = None


@dataclass(slots=True)
class DigitalChannel:
    """Descriptor for one digital/binary channel (breaker status, relay trip, etc.)."""

    name: str
    index: int

    normal_state: int = 0
    description: str | None = None
