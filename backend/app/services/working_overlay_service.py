"""Working Dataset overlay orchestration (CSV/Excel ingestion Slice 4, DEC-072).

The HTTP-mappable layer over `app.domain.working_overlay`'s own pure
data structures/mutation functions -- this module owns exactly the
things that module deliberately does not:

    resolve (workspace_id, source_id) -> PreparationSession (registry)
            |
    resolve which worksheet's coordinate space applies (None for CSV;
    the selected worksheet for Excel -- never guessed)
            |
    validate the request against THIS source's own known dimensions
    (structural row_number>=1 / column_index>=0 bounds are already
    enforced by the API's own Path(ge=...) constraints -- see
    app.api.v1.preparation_sources, matching that router's existing
    Query(ge=0)/Query(gt=0, le=...) precedent for offset/limit; this
    module only ever checks the UPPER bound, which depends on this
    one source's own dimensions and so cannot live in a static Path
    constraint)
            |
    app.domain.working_overlay's own pure mutation functions
            |
    WorkingOverlaySummary (also reused by GET .../preparation-sources/{id})

Never reads or writes `raw_bytes`, never touches a `DisturbanceRecord`,
never interprets a cell value's engineering meaning -- see
`app.domain.working_overlay`'s own module docstring for why a working
value is always a plain string.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import working_overlay as overlay_domain
from app.domain.preparation_session import PreparationSession
from app.services.errors import (
    InvalidWorkingCellValueError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    WorksheetNotSelectedError,
)
from app.services.preparation_preview_service import ensure_csv_totals_cached
from app.services.preparation_session_registry import PreparationSessionRegistry


@dataclass(slots=True)
class WorkingOverlaySummary:
    """A cheap, O(1)-ish snapshot of one session's own working overlay --
    never the overlay's full content (that is what the preview endpoint
    is for). `edited_cell_count` counts BOTH edits and explicit clears
    (both live in `WorkingOverlay.cell_overrides`, see that dataclass's
    own docstring) -- this summary does not distinguish the two kinds,
    only how many cells currently differ from raw."""

    working_revision: int
    edited_cell_count: int
    excluded_row_count: int
    ignored_column_count: int
    can_undo: bool
    can_redo: bool


def summarize_working_overlay(session: PreparationSession) -> WorkingOverlaySummary:
    """Shared by every mutation function below AND by
    `GET .../preparation-sources/{source_id}` (Slice 4 extends that
    existing endpoint's own response with this same summary), so there
    is exactly one place that defines what these counters mean."""
    overlay = session.working_overlay
    return WorkingOverlaySummary(
        working_revision=overlay.revision,
        edited_cell_count=len(overlay.cell_overrides),
        excluded_row_count=len(overlay.excluded_rows),
        ignored_column_count=len(overlay.ignored_columns),
        can_undo=bool(overlay.history),
        can_redo=bool(overlay.redo_stack),
    )


def _resolve_session(*, workspace_id: str, source_id: str, registry: PreparationSessionRegistry) -> PreparationSession:
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")
    return session


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    """`None` for CSV (no worksheet dimension at all). For Excel, the
    currently selected worksheet -- never guessed: raises
    `WorksheetNotSelectedError` for a multi-sheet workbook with no
    selection yet, exactly mirroring
    `preparation_preview_service._preview_excel`'s own rule, so a
    working edit is always made against the same coordinate space the
    preview itself is currently showing."""
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before editing its working dataset."
        )
    return session.summary.selected_worksheet_index


def _row_total(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_row_count
    return session.summary.worksheets[worksheet_index].row_count


def _column_total(session: PreparationSession, worksheet_index: int | None) -> int | None:
    if worksheet_index is None:
        ensure_csv_totals_cached(session)
        return session.cached_column_count
    return session.summary.worksheets[worksheet_index].column_count


def _check_row_bound(session: PreparationSession, worksheet_index: int | None, row_number: int) -> None:
    total = _row_total(session, worksheet_index)
    # A `None` total (Excel worksheet with no cheap dimension hint, see
    # WorksheetInfo's own docstring) is never fabricated into a false
    # bound -- only a KNOWN total is ever enforced.
    if total is not None and row_number > total:
        raise InvalidWorkingCoordinateError(
            f"row_number {row_number} is beyond this source's own {total} known rows."
        )


def _check_column_bound(session: PreparationSession, worksheet_index: int | None, column_index: int) -> None:
    total = _column_total(session, worksheet_index)
    if total is not None and column_index >= total:
        raise InvalidWorkingCoordinateError(
            f"column_index {column_index} is beyond this source's own {total} known columns."
        )


def edit_cell(
    *,
    workspace_id: str,
    source_id: str,
    row_number: int,
    column_index: int,
    value: str | None,
    registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Set (or clear, when `value is None`) one cell's working value --
    see `app.domain.working_overlay.CellOverride`'s own docstring for
    why these stay distinct kinds despite rendering identically today."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    _check_column_bound(session, worksheet_index, column_index)
    if value is not None and len(value) > overlay_domain.MAX_CELL_VALUE_LENGTH:
        raise InvalidWorkingCellValueError(
            f"Cell working value exceeds the maximum length of "
            f"{overlay_domain.MAX_CELL_VALUE_LENGTH} characters."
        )
    key = overlay_domain.cell_key(worksheet_index, row_number, column_index)
    overlay_domain.set_cell_value(session.working_overlay, key, value)
    return summarize_working_overlay(session)


def reset_cell(
    *, workspace_id: str, source_id: str, row_number: int, column_index: int, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Remove one cell's override entirely (a safe no-op if it had
    none) -- the working value reverts to the raw value exactly."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    key = overlay_domain.cell_key(worksheet_index, row_number, column_index)
    overlay_domain.reset_cell(session.working_overlay, key)
    return summarize_working_overlay(session)


def set_row_excluded(
    *, workspace_id: str, source_id: str, row_number: int, excluded: bool, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Mark (or unmark) one row as excluded from the working view.
    Never renumbers surrounding rows -- see
    `app.domain.working_overlay`'s own module docstring."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_row_bound(session, worksheet_index, row_number)
    key = overlay_domain.row_key(worksheet_index, row_number)
    overlay_domain.set_row_excluded(session.working_overlay, key, excluded)
    return summarize_working_overlay(session)


def set_column_ignored(
    *, workspace_id: str, source_id: str, column_index: int, ignored: bool, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Mark (or unmark) one column as ignored in the working view."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    _check_column_bound(session, worksheet_index, column_index)
    key = overlay_domain.column_key(worksheet_index, column_index)
    overlay_domain.set_column_ignored(session.working_overlay, key, ignored)
    return summarize_working_overlay(session)


def reset_all_working_changes(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Clear every cell override, row exclusion, and column ignore for
    this source in one step -- still undoable (see
    `app.domain.working_overlay.reset_all`'s own docstring for why this
    stays bounded by edit count, not dataset size)."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.reset_all(session.working_overlay)
    return summarize_working_overlay(session)


def undo_working_change(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Revert the most recent working-dataset operation, of any kind
    (cell/row/column/reset-all). A safe no-op when there is nothing to
    undo -- never an error, since a disabled Undo button racing a click
    is a normal UI state, not a client mistake."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.undo(session.working_overlay)
    return summarize_working_overlay(session)


def redo_working_change(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> WorkingOverlaySummary:
    """Reapply the most recently undone operation. A safe no-op when
    there is nothing to redo."""
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    overlay_domain.redo(session.working_overlay)
    return summarize_working_overlay(session)
