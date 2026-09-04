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

Slice 4: `PreparationRowOut` gains `excluded`/`modified_cells`.
`WorkingOverlaySummaryOut` is the small counter block shared between
`PreparationSessionSummaryOut` (so the sources list/detail views can
show "N cells edited" without a separate request) and every working-
overlay mutation endpoint's own response. The request bodies
(`CellWorkingValueRequest`/`RowExclusionRequest`) are deliberately tiny
and format-agnostic -- worksheet identity is resolved server-side
(Slice 4's own "backend is authoritative" requirement), never accepted
from the client.

Slice 5 extends the same shapes with header/data-region/column-role
state: `WorkingOverlaySummaryOut` gains `header_row_number`/
`data_start_row`/`data_end_row`; `PreparationRowOut` gains `is_header`/
`in_active_region`; `PreparationSourcePreviewOut` gains the same three
plus `column_labels`/`column_roles`. New request bodies
(`HeaderRowRequest`/`DataRegionRequest`/`ColumnRoleRequest`) follow the
same "tiny, format-agnostic, backend resolves worksheet identity"
convention.

A later owner-UAT refinement adds `data_end_mode` alongside
`data_end_row` on `WorkingOverlaySummaryOut`/`PreparationSourcePreviewOut`,
and an `end_mode` field (defaulting to `"specific"`, preserving the
original request shape) on `DataRegionRequest` -- see
`app.domain.working_overlay.DataRegion`'s own docstring for the
`source_end`/`specific` distinction this mirrors.

UAT fix (2026-09-04): `WorkingOverlaySummaryOut.ignored_column_count`
and `PreparationSourcePreviewOut.ignored_columns` are retired, and
`ColumnIgnoreRequest`/`PUT .../working/columns/{column_index}` (Slice
4's own legacy boolean ignore/unignore endpoint) is removed entirely --
see `app.domain.working_overlay`'s own module docstring for the
three-role column-model simplification that makes all three redundant
(`column_roles`, already on the wire, carries the same information for
every column, not just previously-"ignored" ones; "ignore" is no longer
a distinct action from simply never assigning a role).

UAT enhancement (2026-09-04, DEC-075): `PreparationSourcePreviewOut`
gains an additive `configured_time: ConfiguredTimePreviewOut | None`
field -- a VIRTUAL, derived, read-only preview of the RESOLVED Time
Axis for this page's own rows (see that schema's own docstring), never
a real source column. Populated by the API route itself, not by
`from_domain()` here (see `PreparationSourcePreviewOut`'s own
docstring for why).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.preparation_session import PreparationSessionSummary, WorksheetInfo
from app.domain.working_overlay import END_MODE_SPECIFIC
from app.services.preparation_preview_service import ModifiedCell, PreviewResult, PreviewRow
from app.services.working_overlay_service import WorkingOverlaySummary


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


class WorkingOverlaySummaryOut(BaseModel):
    """Cheap counters describing one source's own Working Dataset overlay
    -- never the overlay's full content (see
    `app.services.working_overlay_service.WorkingOverlaySummary`'s own
    docstring). Defaults to all-zero/`False`, which is exactly correct
    for a freshly uploaded source (no edits made yet)."""

    model_config = ConfigDict(from_attributes=True)

    working_revision: int = 0
    edited_cell_count: int = 0
    excluded_row_count: int = 0
    can_undo: bool = False
    can_redo: bool = False
    header_row_number: int | None = None
    data_start_row: int | None = None
    data_end_mode: str | None = None
    data_end_row: int | None = None

    @classmethod
    def from_domain(cls, summary: WorkingOverlaySummary) -> "WorkingOverlaySummaryOut":
        return cls(
            working_revision=summary.working_revision,
            edited_cell_count=summary.edited_cell_count,
            excluded_row_count=summary.excluded_row_count,
            can_undo=summary.can_undo,
            can_redo=summary.can_redo,
            header_row_number=summary.header_row_number,
            data_start_row=summary.data_start_row,
            data_end_mode=summary.data_end_mode,
            data_end_row=summary.data_end_row,
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
    working_overlay: WorkingOverlaySummaryOut = Field(default_factory=WorkingOverlaySummaryOut)

    @classmethod
    def from_domain(
        cls,
        summary: PreparationSessionSummary,
        working_overlay_summary: WorkingOverlaySummary | None = None,
    ) -> "PreparationSessionSummaryOut":
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
            working_overlay=(
                WorkingOverlaySummaryOut.from_domain(working_overlay_summary)
                if working_overlay_summary is not None
                else WorkingOverlaySummaryOut()
            ),
        )


class WorksheetSelectionRequest(BaseModel):
    """Body of `PATCH .../preparation-sources/{source_id}` (Slice 2) --
    stores only the stable worksheet index already discovered at upload
    time, never a header row/data region/column mapping (later slices'
    own scope)."""

    selected_worksheet_index: int


class ModifiedCellOut(BaseModel):
    """One cell within a `PreparationRowOut` that currently has an
    active working override -- see `ModifiedCell`'s own docstring.
    `raw_value` is the ORIGINAL value, kept for provenance/hover/reset
    display, never the working value (that already lives in the row's
    own `cells`)."""

    column_index: int
    raw_value: Any

    @classmethod
    def from_domain(cls, cell: ModifiedCell) -> "ModifiedCellOut":
        return cls(column_index=cell.column_index, raw_value=cell.raw_value)


class PreparationRowOut(BaseModel):
    """One WORKING row (raw with Slice 4's overlay applied) -- see
    `PreviewRow`'s own docstring for exactly what `cells` does and does
    not contain. `excluded` and `modified_cells` are both sparse,
    provenance-preserving flags added in Slice 4 -- `row_number` is
    never renumbered because of either."""

    row_number: int
    cells: list[Any]
    excluded: bool = False
    modified_cells: list[ModifiedCellOut] = Field(default_factory=list)
    is_header: bool = False
    in_active_region: bool = True

    @classmethod
    def from_domain(cls, row: PreviewRow) -> "PreparationRowOut":
        return cls(
            row_number=row.row_number,
            cells=row.cells,
            excluded=row.excluded,
            modified_cells=[ModifiedCellOut.from_domain(c) for c in row.modified_cells],
            is_header=row.is_header,
            in_active_region=row.in_active_region,
        )


class ConfiguredTimePreviewOut(BaseModel):
    """UAT enhancement (2026-09-04, DEC-075): the RESOLVED/CONFIGURED
    Time Axis, standardized exactly like cleaned export's own Time
    column, for exactly this page's own rows -- a VIRTUAL, derived,
    read-only preview field, never a real source column (never counted
    in `column_count`, never assigned an index, never editable). `None`
    on `PreparationSourcePreviewOut.configured_time` (the field this
    schema fills) means the current Time Axis is not resolved enough to
    derive one yet -- the frontend shows no derived column at all
    rather than an empty one. `values` is exactly `len(rows)` long, in
    the SAME order, with `None` for any row that itself has no
    configured value (excluded, the header row, outside the active
    region, or an unparseable cell) -- see
    `app.services.time_axis_service.build_configured_time_values`'s own
    docstring for the full semantics, in particular the critical
    "always anchored to the true first active row, never this page's
    own first row" guardrail."""

    column_name: str
    family: str
    values: list[str | None] = Field(default_factory=list)


class PreparationSourcePreviewOut(BaseModel):
    """`GET .../preparation-sources/{source_id}/rows` -- one bounded page
    of the WORKING view by default (Slice 4: raw + the source's own
    working overlay applied at read time -- see
    `app.services.preparation_preview_service`'s own module docstring
    for the exact merge strategy). `total_row_count`/`column_count` are
    always paired with their own `_basis` field
    (`"exact"`/`"best_effort"`/`"unknown"`) so the frontend never
    presents an approximate total as if it were authoritative.
    `working_revision` is page-independent (same on every page of the
    same source) -- lets the frontend detect a page fetched before a
    since-applied edit.

    `configured_time` (2026-09-04, DEC-075) is populated by the API
    route itself (`app.api.v1.preparation_sources.
    get_preparation_source_rows`), never by `from_domain()` here --
    computing it requires the separate Time-Axis service layer
    (`app.services.time_axis_service`), which this schema module
    deliberately does not import (mirroring `PreviewResult`'s own
    "never interprets timestamps" boundary -- see that module's own
    docstring)."""

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
    working_revision: int = 0
    header_row_number: int | None = None
    data_start_row: int | None = None
    data_end_mode: str | None = None
    data_end_row: int | None = None
    column_labels: list[str] = Field(default_factory=list)
    column_roles: list[str] = Field(default_factory=list)
    configured_time: ConfiguredTimePreviewOut | None = None

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
            working_revision=result.working_revision,
            header_row_number=result.header_row_number,
            data_start_row=result.data_start_row,
            data_end_mode=result.data_end_mode,
            data_end_row=result.data_end_row,
            column_labels=result.column_labels,
            column_roles=result.column_roles,
        )


class CellWorkingValueRequest(BaseModel):
    """Body of `PUT .../working/cells/{row_number}/{column_index}`.
    `value=None` means an explicit CLEAR; any string (including `""`)
    means an EDIT to that exact string -- see
    `app.domain.working_overlay.CellOverride`'s own docstring for why
    these stay distinct kinds."""

    value: str | None = None


class RowExclusionRequest(BaseModel):
    """Body of `PUT .../working/rows/{row_number}`."""

    excluded: bool


class HeaderRowRequest(BaseModel):
    """Body of `PUT .../working/header` (Slice 5)."""

    row_number: int


class DataRegionRequest(BaseModel):
    """Body of `PUT .../working/data-region` (Slice 5; `end_mode` added
    by a later owner-UAT refinement -- manually finding the true last
    row of a large source was "unnecessarily burdensome"). `end_mode`
    defaults to `"specific"` so the ORIGINAL Slice 5 request shape
    (`{"start_row": ..., "end_row": ...}`, no `end_mode` at all) keeps
    working completely unchanged -- a real backward-compatibility
    guarantee. For `end_mode="source_end"`, `end_row` is ignored
    (never stored -- see `app.domain.working_overlay.DataRegion`'s own
    docstring for why a floating end is never resolved into a stored
    guess); omit it or leave it `null`. For `end_mode="specific"`
    (explicit or defaulted), `end_row` is required and
    `start_row <= end_row` is enforced server-side
    (`InvalidDataRegionError` otherwise)."""

    start_row: int
    end_row: int | None = None
    end_mode: str = END_MODE_SPECIFIC


class ColumnRoleRequest(BaseModel):
    """Body of `PUT .../working/columns/{column_index}/role` (Slice 5).
    `role` must be one of `app.domain.working_overlay.KNOWN_COLUMN_ROLES`
    -- never a free-text field."""

    role: str
