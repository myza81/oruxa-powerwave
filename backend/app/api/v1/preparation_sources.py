"""CSV/Excel preparation-source API (Slices 1-5, DEC-072).

A deliberately separate, smaller router from `app.api.v1.sources` -- a
preparation source is not a `SourceMetadata`/`ActiveSource` (it has no
parsed `DisturbanceRecord`, no channels, no waveform data), so it gets
its own resource path rather than being force-fitted into the existing
COMTRADE-shaped `.../sources` contract. This is also why the Workspace
Sidebar's own channel-selection source list (which reads only
`GET .../sources`) never sees a CSV/Excel preparation row at all -- a
real, structural reason a `Needs Preparation` source cannot be selected
for waveform display, not merely a UI convention (see this slice's own
guardrail: "a Needs Preparation source must never reach normal waveform
loading").

Slice 2 upload-shape decision: `POST` still accepts a single `csv_file`
field unchanged (Slice 1's own frontend/tests keep working, zero
migration forced), and now ALSO accepts an optional `excel_file` field
routed to the Excel importer -- exactly one of the two must be present
per request. This was chosen over either (a) breaking Slice 1's request
shape with a generic `file`+`format` pair, or (b) a second endpoint
family, because it mirrors this codebase's own existing convention for
a small, closed set of format-specific typed fields (see
`app.api.v1.sources.upload_comtrade_source`'s own `cfg_file`+`dat_file`
pair) rather than inventing a new upload pattern for two formats.

Only `.csv` and `.xlsx` are accepted -- legacy `.xls` is deliberately
out of scope (see `app.domain.preparation_session`'s own module
docstring).

Slice 5 adds header-row/data-region/column-role endpoints under
`.../working/header`, `.../working/data-region`, and
`.../working/columns/{column_index}/role` -- the same "backend is
authoritative, tiny format-agnostic request bodies" convention Slice 4
already established for cell/row/column-ignore editing. See
`app.services.working_overlay_service`'s own module docstring for the
orchestration/bounds-validation layer these endpoints call into.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile, status

from app.config import Settings
from app.schemas.preparation_issue import PreparationIssueSummaryOut
from app.schemas.preparation_session import (
    CellWorkingValueRequest,
    ColumnIgnoreRequest,
    ColumnRoleRequest,
    DataRegionRequest,
    HeaderRowRequest,
    PreparationSessionSummaryOut,
    PreparationSourcePreviewOut,
    RowExclusionRequest,
    WorkingOverlaySummaryOut,
    WorksheetSelectionRequest,
)
from app.schemas.source import ErrorOut
from app.services.errors import AmbiguousPreparationUploadError, ImportServiceError
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_preview_service import (
    PREVIEW_DEFAULT_LIMIT,
    PREVIEW_MAX_LIMIT,
    preview_preparation_source,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.working_overlay_service import (
    clear_header_row,
    edit_cell,
    redo_working_change,
    reset_all_working_changes,
    reset_cell,
    reset_column_role,
    reset_data_region,
    set_column_ignored,
    set_column_role,
    set_data_region,
    set_header_row,
    set_row_excluded,
    summarize_working_overlay,
    undo_working_change,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/preparation-sources", tags=["preparation-sources"]
)

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "ambiguous_preparation_upload": status.HTTP_400_BAD_REQUEST,
    "workbook_parse_error": status.HTTP_400_BAD_REQUEST,
    "empty_workbook": status.HTTP_400_BAD_REQUEST,
    "worksheet_selection_not_applicable": status.HTTP_400_BAD_REQUEST,
    "invalid_worksheet_index": status.HTTP_400_BAD_REQUEST,
    "worksheet_not_selected": status.HTTP_400_BAD_REQUEST,
    "invalid_working_coordinate": status.HTTP_400_BAD_REQUEST,
    "invalid_working_cell_value": status.HTTP_400_BAD_REQUEST,
    "invalid_data_region": status.HTTP_400_BAD_REQUEST,
    "invalid_column_role": status.HTTP_400_BAD_REQUEST,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_preparation_session_registry(request: Request) -> PreparationSessionRegistry:
    return request.app.state.preparation_session_registry


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PreparationSessionSummaryOut)
async def upload_preparation_source(
    workspace_id: str,
    csv_file: UploadFile | None = File(None, description="Raw CSV file to accept as preparation input"),
    excel_file: UploadFile | None = File(None, description="Raw .xlsx workbook to accept as preparation input"),
    settings: Settings = Depends(get_settings_dep),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSessionSummaryOut:
    """Accept exactly one of `csv_file`/`excel_file` per request -- see
    this module's own docstring for why both fields live on one
    endpoint rather than two."""
    workspace_id = _validate_workspace_id(workspace_id)

    if (csv_file is None) == (excel_file is None):
        exc = AmbiguousPreparationUploadError(
            "Exactly one of csv_file or excel_file must be provided."
        )
        raise _http_error(exc)

    try:
        if csv_file is not None:
            summary = await import_csv_preparation_source(
                workspace_id=workspace_id,
                csv_upload=csv_file,
                max_total_bytes=settings.max_event_upload_size_bytes,
                registry=registry,
            )
        else:
            summary = await import_excel_preparation_source(
                workspace_id=workspace_id,
                excel_upload=excel_file,
                max_total_bytes=settings.max_event_upload_size_bytes,
                registry=registry,
            )
    except ImportServiceError as exc:
        logger.info("Preparation-source upload rejected (%s): %s", exc.code, exc.message)
        raise _http_error(exc) from exc
    except Exception:
        logger.exception(
            "Unexpected error accepting preparation source for workspace %s", workspace_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="Upload failed unexpectedly.").model_dump(),
        )

    session = registry.get(workspace_id, summary.source_id)
    overlay_summary = summarize_working_overlay(session) if session is not None else None
    return PreparationSessionSummaryOut.from_domain(summary, overlay_summary)


@router.get("", response_model=list[PreparationSessionSummaryOut])
def list_preparation_sources(
    workspace_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> list[PreparationSessionSummaryOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    sessions = registry.list_for_workspace(workspace_id)
    return [
        PreparationSessionSummaryOut.from_domain(s.summary, summarize_working_overlay(s)) for s in sessions
    ]


@router.get("/{source_id}", response_model=PreparationSessionSummaryOut)
def get_preparation_source(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSessionSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No preparation source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return PreparationSessionSummaryOut.from_domain(session.summary, summarize_working_overlay(session))


@router.get("/{source_id}/rows", response_model=PreparationSourcePreviewOut)
def get_preparation_source_rows(
    workspace_id: str,
    source_id: str,
    offset: int = Query(
        0, ge=0,
        description="0-based row offset -- the first returned row has row_number = offset + 1.",
    ),
    limit: int = Query(
        PREVIEW_DEFAULT_LIMIT, gt=0, le=PREVIEW_MAX_LIMIT,
        description=f"Maximum rows to return, bounded server-side at {PREVIEW_MAX_LIMIT} regardless of what is requested.",
    ),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSourcePreviewOut:
    """Slice 3 (DEC-072): a bounded page of RAW rows -- never the whole
    dataset (`offset`/`limit` are enforced by the `Query(...)` constraints
    above, matching `app.api.v1.sources.get_source_waveform`'s own
    `point_budget: int = Query(..., gt=0)` precedent -- an out-of-bounds
    value is rejected by FastAPI itself before this function body ever
    runs, so no separate service-level range-validation error exists).

    No header row is assumed, no column mapping is inferred, no
    DisturbanceRecord is read or produced -- see
    app.services.preparation_preview_service's own module docstring for
    the exact CSV/Excel reading strategy.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = preview_preparation_source(
            workspace_id=workspace_id, source_id=source_id, offset=offset, limit=limit, registry=registry,
        )
    except ImportServiceError as exc:
        logger.info(
            "Preparation-source preview rejected (%s) for workspace %s source %s: %s",
            exc.code, workspace_id, source_id, exc.message,
        )
        raise _http_error(exc) from exc
    return PreparationSourcePreviewOut.from_domain(result)


@router.get("/{source_id}/issues", response_model=PreparationIssueSummaryOut)
def get_preparation_source_issues(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationIssueSummaryOut:
    """Slice 6 (DEC-072): the preparation-specific Readiness Issue
    model's own transport endpoint -- structured, informational-only
    findings about the CURRENT preparation state (see
    app.services.preparation_issue_service's own module docstring for
    exactly which ones Slice 6 itself produces). This is deliberately
    NOT the full Powerwave Readiness Validator: no time-axis parsing,
    no waveform-value validation, no `DisturbanceRecord` conversion,
    and no readiness gate anywhere in this response -- `blocking`/
    `warning` exist as a severity CAPABILITY only, never exercised by
    this slice's own issue production.

    An actual runtime/request failure (source not found, worksheet not
    selected) still raises an ordinary `ImportServiceError` subclass
    and is still mapped to an HTTP error response below -- it is never
    itself returned as a `PreparationIssue` in a 200 response.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = build_issue_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        logger.info(
            "Preparation-source issue lookup rejected (%s) for workspace %s source %s: %s",
            exc.code, workspace_id, source_id, exc.message,
        )
        raise _http_error(exc) from exc
    return PreparationIssueSummaryOut.from_domain(summary)


@router.patch("/{source_id}", response_model=PreparationSessionSummaryOut)
def patch_preparation_source(
    workspace_id: str,
    source_id: str,
    body: WorksheetSelectionRequest,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSessionSummaryOut:
    """Select the currently active worksheet for an Excel preparation
    source (Slice 2). The only PATCH-able field this slice supports --
    see `WorksheetSelectionRequest`'s own docstring for what is
    deliberately NOT modeled here yet (header row, data region, column
    mapping: later slices).
    """
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = select_preparation_worksheet(
            workspace_id=workspace_id,
            source_id=source_id,
            worksheet_index=body.selected_worksheet_index,
            registry=registry,
        )
    except ImportServiceError as exc:
        logger.info(
            "Worksheet selection rejected (%s) for workspace %s source %s: %s",
            exc.code, workspace_id, source_id, exc.message,
        )
        raise _http_error(exc) from exc
    session = registry.get(workspace_id, source_id)
    overlay_summary = summarize_working_overlay(session) if session is not None else None
    return PreparationSessionSummaryOut.from_domain(summary, overlay_summary)


def _working_error(exc: ImportServiceError) -> HTTPException:
    logger.info("Working-dataset operation rejected (%s): %s", exc.code, exc.message)
    return _http_error(exc)


@router.put("/{source_id}/working/cells/{row_number}/{column_index}", response_model=WorkingOverlaySummaryOut)
def put_working_cell(
    workspace_id: str,
    source_id: str,
    row_number: int = Path(ge=1, description="1-based row number, matching PreparationRowOut.row_number."),
    column_index: int = Path(ge=0, description="0-based column index, matching a row's own cells[] position."),
    body: CellWorkingValueRequest = CellWorkingValueRequest(),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Set (`value` a string) or clear (`value: null`) one cell's
    working value -- see `CellWorkingValueRequest`'s own docstring."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = edit_cell(
            workspace_id=workspace_id, source_id=source_id, row_number=row_number,
            column_index=column_index, value=body.value, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}/working/cells/{row_number}/{column_index}", response_model=WorkingOverlaySummaryOut)
def delete_working_cell(
    workspace_id: str,
    source_id: str,
    row_number: int = Path(ge=1),
    column_index: int = Path(ge=0),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Reset one cell to its raw value -- a safe no-op if it had no
    working override."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = reset_cell(
            workspace_id=workspace_id, source_id=source_id, row_number=row_number,
            column_index=column_index, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.put("/{source_id}/working/rows/{row_number}", response_model=WorkingOverlaySummaryOut)
def put_working_row(
    workspace_id: str,
    source_id: str,
    body: RowExclusionRequest,
    row_number: int = Path(ge=1),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Exclude/include one row from the working view -- never
    renumbers surrounding rows."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = set_row_excluded(
            workspace_id=workspace_id, source_id=source_id, row_number=row_number,
            excluded=body.excluded, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.put("/{source_id}/working/columns/{column_index}", response_model=WorkingOverlaySummaryOut)
def put_working_column(
    workspace_id: str,
    source_id: str,
    body: ColumnIgnoreRequest,
    column_index: int = Path(ge=0),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Ignore/unignore one column in the working view."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = set_column_ignored(
            workspace_id=workspace_id, source_id=source_id, column_index=column_index,
            ignored=body.ignored, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}/working", response_model=WorkingOverlaySummaryOut)
def delete_working_overlay(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Reset all working changes (cell edits/clears, row exclusions,
    column ignores) for this source in one step -- still undoable."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = reset_all_working_changes(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.post("/{source_id}/working/undo", response_model=WorkingOverlaySummaryOut)
def post_working_undo(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Revert the most recent working-dataset operation. A safe no-op
    when there is nothing to undo."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = undo_working_change(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.post("/{source_id}/working/redo", response_model=WorkingOverlaySummaryOut)
def post_working_redo(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Reapply the most recently undone operation. A safe no-op when
    there is nothing to redo."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = redo_working_change(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.put("/{source_id}/working/header", response_model=WorkingOverlaySummaryOut)
def put_working_header(
    workspace_id: str,
    source_id: str,
    body: HeaderRowRequest,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Select which raw row supplies working column labels (Slice 5,
    DEC-072). Rows 1..N remain fully preserved regardless of this
    selection -- see `app.domain.working_overlay.set_header_row`'s own
    docstring."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = set_header_row(
            workspace_id=workspace_id, source_id=source_id, row_number=body.row_number, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}/working/header", response_model=WorkingOverlaySummaryOut)
def delete_working_header(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Clear the header-row selection -- working column labels revert
    to the neutral spreadsheet-letter fallback."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = clear_header_row(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.put("/{source_id}/working/data-region", response_model=WorkingOverlaySummaryOut)
def put_working_data_region(
    workspace_id: str,
    source_id: str,
    body: DataRegionRequest,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Narrow the active working dataset to `[start_row, end_row]`
    inclusive (Slice 5, DEC-072). Rows outside this range remain fully
    preserved/inspectable -- see
    `app.domain.working_overlay.DataRegion`'s own docstring."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = set_data_region(
            workspace_id=workspace_id, source_id=source_id,
            start_row=body.start_row, end_row=body.end_row, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}/working/data-region", response_model=WorkingOverlaySummaryOut)
def delete_working_data_region(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Remove the data-region narrowing -- the entire source range
    becomes active again (the original default)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = reset_data_region(workspace_id=workspace_id, source_id=source_id, registry=registry)
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.put("/{source_id}/working/columns/{column_index}/role", response_model=WorkingOverlaySummaryOut)
def put_working_column_role(
    workspace_id: str,
    source_id: str,
    body: ColumnRoleRequest,
    column_index: int = Path(ge=0),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Assign one column's semantic role (Slice 5, DEC-072) -- one of
    `unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/
    `ignore`. Purely a stated intent, never validated/interpreted (no
    time-format parsing, no numeric-value checking) -- see
    `app.services.working_overlay_service.set_column_role`'s own
    docstring. Distinct from, but reconciled with, the legacy
    `PUT .../working/columns/{column_index}` boolean ignore endpoint
    above (both ultimately write the same `column_roles` state)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = set_column_role(
            workspace_id=workspace_id, source_id=source_id,
            column_index=column_index, role=body.role, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}/working/columns/{column_index}/role", response_model=WorkingOverlaySummaryOut)
def delete_working_column_role(
    workspace_id: str,
    source_id: str,
    column_index: int = Path(ge=0),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> WorkingOverlaySummaryOut:
    """Reset one column's role to `unknown` -- including a column
    previously set to `ignore` (task section: "If role was Ignore,
    reset should return to Unknown")."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = reset_column_role(
            workspace_id=workspace_id, source_id=source_id, column_index=column_index, registry=registry,
        )
    except ImportServiceError as exc:
        raise _working_error(exc) from exc
    return WorkingOverlaySummaryOut.from_domain(summary)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preparation_source(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> None:
    """Release one preparation session's raw bytes.

    A preparation session has no dependents in Slices 1-2 (no calculated
    channels, no measurement groups, no synchronization state can ever
    reference it -- those all require a real `SourceMetadata`/
    `ActiveSource`), so this is a plain single-registry removal, unlike
    `app.api.v1.sources.delete_source`'s own multi-registry cascade.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No preparation source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    registry.remove(workspace_id, source_id)
