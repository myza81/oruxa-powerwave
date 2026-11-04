"""Result-owned Current normalization; never contains waveform samples."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.reference_side import ReferenceSide

CalculatedCurrentMode = Literal["automatic", "manual", "unassigned"]


@dataclass(frozen=True, slots=True)
class CalculatedCurrentConfiguration:
    mode: CalculatedCurrentMode = "automatic"
    current_base_amps: float | None = None
    base_reference_side: ReferenceSide = "unknown"
    updated_at: datetime | None = None
