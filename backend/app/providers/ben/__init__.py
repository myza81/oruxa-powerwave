"""Native BEN (BEN32 SubBen) disturbance-record support.

    BEN bytes -> parse_ben() -> BenRecord -> to_disturbance_record() -> DisturbanceRecord

Modules:
    layout     -- every structural constant of the validated SubBen layout
    reader     -- bounds-checked byte/section/string-table primitives
    parser     -- header, sections, descriptors, sample layout, payload checks
    model      -- BenRecord and its channel/header types (lossless, native)
    normalize  -- BenRecord -> DisturbanceRecord
    provider   -- BaseProvider adapter (not registered for upload yet)
    errors     -- BEN-specific ProviderLoadError subclasses

See docs/project-memory/BEN_FORMAT.md for what is proven, what is
inferred and what is still unknown about the format.
"""

from app.providers.ben.errors import (
    BenFormatError,
    BenNotRecognizedError,
    BenStructureError,
    BenTruncatedError,
    BenUnsupportedVariantError,
)
from app.providers.ben.model import (
    BenChannelKind,
    BenDiagnostic,
    BenDigitalChannel,
    BenDigitalSource,
    BenHeader,
    BenRecord,
    BenRecordClass,
    BenSampleSlot,
    BenTriggerTime,
    BenValueChannel,
)
from app.providers.ben.normalize import to_disturbance_record
from app.providers.ben.parser import parse_ben, parse_ben_file
from app.providers.ben.provider import BenProvider

__all__ = [
    "BenChannelKind",
    "BenDiagnostic",
    "BenDigitalChannel",
    "BenDigitalSource",
    "BenFormatError",
    "BenHeader",
    "BenNotRecognizedError",
    "BenProvider",
    "BenRecord",
    "BenRecordClass",
    "BenSampleSlot",
    "BenStructureError",
    "BenTriggerTime",
    "BenTruncatedError",
    "BenUnsupportedVariantError",
    "BenValueChannel",
    "parse_ben",
    "parse_ben_file",
    "to_disturbance_record",
]
