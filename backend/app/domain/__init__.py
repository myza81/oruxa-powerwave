"""Domain layer: pure data contracts with zero framework dependencies.

Ported from powerwave's app/models/ (see docs/project-memory/MIGRATION_PLAN.md
Phase 0 reuse mapping). Nothing in this package may import Pydantic, FastAPI,
or any other web-framework type -- that conversion happens in app.schemas.
"""

from app.domain.channels import AnalogChannel, DigitalChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import DisturbanceInformation, SamplingInformation, TimingInformation

__all__ = [
    "AnalogChannel",
    "AnalogChannelSummary",
    "DigitalChannel",
    "DigitalChannelSummary",
    "DisturbanceRecord",
    "RecordingMetadata",
    "SamplingInformation",
    "SourceMetadata",
    "TimingInformation",
    "DisturbanceInformation",
]
