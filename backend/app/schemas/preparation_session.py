"""API response/request DTOs for CSV/Excel preparation sources (Slices 1-2, DEC-072).

Deliberately excludes the raw file bytes, mirroring
`app.schemas.source`'s own "never return the heavy payload" convention.
`file_format` is uppercased/title-cased at the domain layer already
(`"CSV"`, `"Excel"`), matching `SourceSummaryOut.provider_type`'s
existing `"COMTRADE"` convention exactly -- the Recording Events table's
File Format column reads both through the same display path on the
frontend.

Slice 2: `worksheets`/`selected_worksheet_index` are additive fields on
`PreparationSessionSummaryOut` -- an empty list/`None` for CSV, exactly
mirroring the domain layer's own shape (no fake single-sheet metadata
invented for CSV just to keep the wire shape uniform).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.preparation_session import PreparationSessionSummary, WorksheetInfo


class WorksheetInfoOut(BaseModel):
    """One worksheet's discovered structural identity only -- never cell
    values, a header row, or a data region (those are later slices'
    concepts)."""

    model_config = ConfigDict(from_attributes=True)

    index: int
    name: str
    visible: bool
    row_count: int | None = None
    column_count: int | None = None

    @classmethod
    def from_domain(cls, worksheet: WorksheetInfo) -> "WorksheetInfoOut":
        return cls(
            index=worksheet.index,
            name=worksheet.name,
            visible=worksheet.visible,
            row_count=worksheet.row_count,
            column_count=worksheet.column_count,
        )


class PreparationSessionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    workspace_id: str
    file_format: str
    original_filename: str
    file_size_bytes: int
    status: str
    created_at: datetime
    worksheets: list[WorksheetInfoOut] = Field(default_factory=list)
    selected_worksheet_index: int | None = None

    @classmethod
    def from_domain(cls, summary: PreparationSessionSummary) -> "PreparationSessionSummaryOut":
        return cls(
            source_id=summary.source_id,
            workspace_id=summary.workspace_id,
            file_format=summary.source_format,
            original_filename=summary.original_filename,
            file_size_bytes=summary.original_byte_size,
            status=summary.status,
            created_at=summary.created_at,
            worksheets=[WorksheetInfoOut.from_domain(w) for w in summary.worksheets],
            selected_worksheet_index=summary.selected_worksheet_index,
        )


class WorksheetSelectionRequest(BaseModel):
    """Body of `PATCH .../preparation-sources/{source_id}` (Slice 2) --
    stores only the stable worksheet index already discovered at upload
    time, never a header row/data region/column mapping (later slices'
    own scope)."""

    selected_worksheet_index: int
