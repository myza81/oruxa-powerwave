"""OEM-neutral representation of relay settings *before* interpretation.

A `RawRelayDocument` is what a format-specific reader (PDF, Excel, CSV, XML,
OEM export -- all future slices) produces. It preserves what was found
without deciding what it means. Nothing here assumes parameter IDs, tables,
zones or even that the document is a distance-protection setting sheet.

Raw documents are ephemeral by design: they are plain in-memory values with
no persistence hook, and must never be written to the application database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceFormat(StrEnum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    XML = "xml"
    OEM_EXPORT = "oem_export"
    OTHER = "other"


@dataclass(frozen=True)
class SourceLocation:
    """Where in the source a setting was found; every field optional."""

    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    column: str | None = None
    line: int | None = None
    path: str | None = None  # e.g. an XML path


@dataclass(frozen=True)
class SettingRange:
    text: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


@dataclass(frozen=True)
class ExtractionProvenance:
    """How the extractor obtained the setting (not how it was interpreted)."""

    extractor_id: str
    extractor_version: str | None = None
    confidence: float | None = None  # extractor's own confidence, 0..1
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawSetting:
    #: Unique within the document; assigned by the extractor. Interpretation
    #: provenance points back to this, so it must be stable for a document.
    setting_id: str
    name: str | None = None
    #: Manufacturer's own code/address (e.g. "3002", "0101"); often absent.
    parameter_id: str | None = None
    section_path: tuple[str, ...] = ()
    raw_value: str | float | None = None
    #: Extractor-normalised value (e.g. numeric parse); never an
    #: engineering interpretation.
    normalized_value: str | float | bool | None = None
    unit: str | None = None
    setting_range: SettingRange | None = None
    location: SourceLocation = field(default_factory=SourceLocation)
    source_text: str | None = None
    notes: tuple[str, ...] = ()
    extraction: ExtractionProvenance | None = None


@dataclass(frozen=True)
class RawRelayDocument:
    source_format: SourceFormat
    settings: tuple[RawSetting, ...] = ()
    #: Free-text clues for relay identification (title block, order code,
    #: firmware banner...). Evidence only -- never a verdict.
    identification_hints: tuple[str, ...] = ()
    extractor_id: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [s.setting_id for s in self.settings]
        if len(set(ids)) != len(ids):
            raise ValueError("RawRelayDocument setting_id values must be unique")

    def by_id(self, setting_id: str) -> RawSetting | None:
        return next((s for s in self.settings if s.setting_id == setting_id), None)

    def by_parameter_id(self, parameter_id: str) -> tuple[RawSetting, ...]:
        return tuple(s for s in self.settings if s.parameter_id == parameter_id)

    def in_section(self, *prefix: str) -> tuple[RawSetting, ...]:
        n = len(prefix)
        return tuple(s for s in self.settings if s.section_path[:n] == prefix)
