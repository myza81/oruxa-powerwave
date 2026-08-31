"""API response/request DTOs for CSV/Excel preparation sources (Slices 1-3, DEC-072).

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

Slice 3: `PreparationRowOut`/`PreparationSourcePreviewOut` are the
paged raw-preview response shape -- see
`app.services.preparation_preview_service`'s own module docstring for
the CSV/Excel strategies that produce a `PreviewResult`/`PreviewRow`
this module only re-shapes for the wire.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.preparation_session import PreparationSessionSummary, WorksheetInfo
from app.services.preparation_preview_service import PreviewResult, PreviewRow


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


class PreparationRowOut(BaseModel):
    """One raw row -- see `PreviewRow`'s own docstring for exactly what
    `cells` does and does not contain (raw values only, no header/type
    inference)."""

    row_number: int
    cells: list[Any]

    @classmethod
    def from_domain(cls, row: PreviewRow) -> "PreparationRowOut":
        return cls(row_number=row.row_number, cells=row.cells)


class PreparationSourcePreviewOut(BaseModel):
    """`GET .../preparation-sources/{source_id}/rows` (Slice 3) -- one
    bounded page of raw rows. `total_row_count`/`column_count` are
    always paired with their own `_basis` field
    (`"exact"`/`"best_effort"`/`"unknown"`) so the frontend never
    presents an approximate total as if it were authoritative -- see
    `app.services.preparation_preview_service`'s own module docstring
    for exactly which formats produce which basis."""

    source_id: str
    selected_worksheet_index: int | None = None
    offset: int
    limit: int
    returned_row_count: int
    total_row_count: int | None
    total_row_count_basis: str
    column_count: int | None
    column_count_basis: str
    rows: list[PreparationRowOut]

    @classmethod
    def from_domain(cls, result: PreviewResult) -> "PreparationSourcePreviewOut":
        return cls(
            source_id=result.source_id,
            selected_worksheet_index=result.selected_worksheet_index,
            offset=result.offset,
            limit=result.limit,
            returned_row_count=result.returned_row_count,
            total_row_count=result.total_row_count,
            total_row_count_basis=result.total_row_count_basis,
            column_count=result.column_count,
            column_count_basis=result.column_count_basis,
            rows=[PreparationRowOut.from_domain(r) for r in result.rows],
        )
