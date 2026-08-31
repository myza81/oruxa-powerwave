"""Paged raw-data preview for CSV/Excel preparation sources (Slices 3-4, DEC-072).

Owns exactly one job: given an already-accepted `PreparationSession`
(Slices 1-2), return a bounded WINDOW of its rows/cells -- never the
whole dataset, never a header/data-region inference, never a type
coercion beyond what the underlying reader naturally exposes. This is
strictly an inspection surface:

    PreparationSession (raw, immutable)
            |
    preview_preparation_source() (this module)
            |
    raw page  +  Slice 4's own WorkingOverlay, applied at read time
            |
    a bounded page of WORKING rows -- never cached beyond one request,
    never mutates the session's own raw_bytes OR its working_overlay

No `DisturbanceRecord` is read or produced here. Nothing in this module
assumes a header row, infers column roles, or interprets timestamps --
see this feature's own explicit non-goals in
docs/project-memory/CSV_EXCEL_INGESTION_ARCHITECTURE.md.

CSV strategy (task's own "avoid parsing the entire CSV into a full
DataFrame just to return 200 rows"): the raw bytes are decoded once per
request and streamed through `csv.reader` -- never `pandas.read_csv`.
Because the in-memory bytes have no index, reaching row N still means
iterating from row 0 (task's own "acceptable initially if documented and
bounded" allowance) -- but the exact row/column TOTALS only need to be
computed once per session: `PreparationSession.cached_row_count`/
`cached_column_count` (see that dataclass's own docstring) are memoized
on the first preview request (any page) via `ensure_csv_totals_cached()`
-- Slice 4's own coordinate-bounds validation
(`app.services.working_overlay_service`) reuses this exact same function
rather than a second scan implementation.

Excel strategy: reuses `openpyxl`'s `read_only=True` streaming mode
(same choice as Slice 2's own worksheet discovery), reopening the
workbook fresh per request (never held open across requests -- see
Slice 2's own precedent) and using `Worksheet.iter_rows(min_row=,
max_row=, values_only=True)` to avoid materializing rows outside the
requested window. `data_only=False` is used deliberately (opposite of
Slice 2's discovery, which never reads cell values at all) so a formula
cell's STORED FORMULA TEXT is what gets displayed -- never a cached or
recalculated value, and never a live spreadsheet recalculation (task's
own explicit "do not attempt spreadsheet recalculation"). Excel's own
row/column totals are never re-scanned here at all -- they already exist
on the selected `WorksheetInfo` from Slice 2's own upload-time discovery
(best-effort, exactly as already documented there).

Slice 4 overlay application (`_apply_working_overlay`): a post-
processing step run on the already-fetched raw page, AFTER either
format's own raw-reading logic above -- it never touches how rows are
read, only what gets returned. For each row in the page: any cell
override at `(worksheet_index, row.row_number, column_index)` replaces
that cell's displayed value (the row's own `cells` list is extended
with `None` -- "raw blank" -- only as far as needed to show an override
targeting a column beyond that specific row's own raw width, e.g. a
short/ragged CSV row; every OTHER row's own length is left exactly as
the raw reader produced it). The row's own `excluded` flag and the
page-level `ignored_columns` list are looked up the same way. Overrides
are pre-filtered by worksheet ONCE per preview call (`_overrides_for_worksheet`),
not re-scanned per row, so this stays proportional to (page size +
total edit count for this worksheet), never to the raw dataset's size.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook

from app.domain.preparation_session import FORMAT_CSV, FORMAT_EXCEL, PreparationSession
from app.domain.working_overlay import OVERRIDE_KIND_CLEAR, WorkingOverlay
from app.services.errors import SourceNotFoundError, WorkbookParseError, WorksheetNotSelectedError
from app.services.preparation_session_registry import PreparationSessionRegistry

#: Task's own suggested default; a bounded maximum enforced server-side
#: regardless of what a caller requests (see this module's own docstring
#: note on why offset/limit validation itself lives at the API's
#: `Query(...)` layer, not here).
PREVIEW_DEFAULT_LIMIT = 200
PREVIEW_MAX_LIMIT = 1000

#: How a reported row/column total was obtained -- task's own explicit
#: "clearly document whether they are: exact / best effort / unknown"
#: requirement. CSV counts are ALWAYS "exact" here (a real scan of the
#: actual in-memory bytes, not a sample or estimate); Excel counts
#: inherit Slice 2's own "best_effort" (from `max_row`/`max_column`) or
#: "unknown" (when the workbook's own XML didn't expose a dimension hint
#: at all, see `WorksheetInfo`'s own docstring).
ROW_BASIS_EXACT = "exact"
ROW_BASIS_BEST_EFFORT = "best_effort"
ROW_BASIS_UNKNOWN = "unknown"

#: A conservative, small allowlist for CSV delimiter sniffing -- task's
#: own "do not treat delimiter selection as an engineering interpretation"
#: guardrail. Restricting `csv.Sniffer` to only these candidates (rather
#: than letting it guess freely) is a real, verified fix for a genuine
#: failure mode: an unrestricted sniff on single-column data can return
#: a nonsense "delimiter" (a letter from the data itself) instead of
#: failing cleanly -- verified directly against this exact case before
#: choosing this approach.
_CSV_CANDIDATE_DELIMITERS = ",;\t|"
_CSV_DEFAULT_DELIMITER = ","
_CSV_SNIFF_SAMPLE_CHARS = 8192


@dataclass(slots=True)
class ModifiedCell:
    """One cell within a `PreviewRow` that currently has an active
    working override -- sparse by construction (task's own "do not
    multiply payload size unnecessarily for every unchanged cell"):
    only cells that actually differ from the raw source appear here.
    `raw_value` is the ORIGINAL value at this position, in its native
    type, preserved for provenance/hover/reset display -- never the
    working value (that already lives in the row's own `cells`)."""

    column_index: int
    raw_value: Any


@dataclass(slots=True)
class PreviewRow:
    """One row, as WORKING values (raw with Slice 4's overlay applied).
    `row_number` is 1-based and matches the source's own row position
    (CSV: `csv.reader`'s own enumeration; Excel: the worksheet's own row
    index) -- never renumbered/reindexed, including when `excluded` is
    `True` (task's own explicit "provenance" requirement: exclusion is a
    flag, never a removal or a renumbering). `cells` is the DISPLAYED
    (working) value at each position: CSV cells are `str` unless
    overridden; Excel cells keep their native JSON-safe type unless
    overridden, with `datetime`/`date`/`time` raw values converted to
    ISO-8601 strings purely for JSON transport. `modified_cells` lists
    only the cells in THIS row with an active override, each carrying
    the raw value alongside for provenance -- see `ModifiedCell`'s own
    docstring."""

    row_number: int
    cells: list[Any]
    excluded: bool = False
    modified_cells: list[ModifiedCell] = field(default_factory=list)


@dataclass(slots=True)
class PreviewResult:
    """See this module's own docstring for the CSV/Excel strategies that
    produce this. `selected_worksheet_index` is `None` for CSV (no
    worksheet concept at all -- never fabricated). `ignored_columns`
    lists column indices ignored for the CURRENT worksheet (or for CSV,
    the source as a whole) -- page-independent, same set on every page.
    `working_revision` is `WorkingOverlay.revision` at the moment this
    page was read, for the frontend's own stale-page/refresh bookkeeping
    (task's own "lightweight revision counter... stale-page detection")."""

    source_id: str
    selected_worksheet_index: int | None
    offset: int
    limit: int
    returned_row_count: int
    total_row_count: int | None
    total_row_count_basis: str
    column_count: int | None
    column_count_basis: str
    rows: list[PreviewRow]
    ignored_columns: list[int] = field(default_factory=list)
    working_revision: int = 0


def _sniff_csv_delimiter(sample: str) -> str:
    """Bounded, conservative dialect sniffing -- never a full-file scan
    just to pick a delimiter, and never treated as an "engineering
    interpretation" (task's own wording): a wrong guess only affects how
    this ONE preview splits cells, never anything downstream, and later
    slices (header/column mapping) start from a clean slate regardless.
    """
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_CSV_CANDIDATE_DELIMITERS)
        return dialect.delimiter
    except csv.Error:
        return _CSV_DEFAULT_DELIMITER


def _open_csv_reader(session: PreparationSession) -> csv.reader:
    # errors="replace" (never raises): task scope is raw structural
    # preview, not encoding detection -- an undecodable byte becomes a
    # visible replacement character rather than failing the whole
    # preview. This is a disclosed simplification, not a claim that
    # encoding detection is solved.
    text = session.raw_bytes.decode("utf-8", errors="replace")
    delimiter = _sniff_csv_delimiter(text[:_CSV_SNIFF_SAMPLE_CHARS])
    return csv.reader(io.StringIO(text), delimiter=delimiter)


def ensure_csv_totals_cached(session: PreparationSession) -> None:
    """Populate `session.cached_row_count`/`cached_column_count` via one
    full pass over the in-memory text, if not already cached. Shared by
    `_preview_csv()` (below) and `app.services.working_overlay_service`'s
    own coordinate-bounds validation, so there is exactly one CSV
    row/column-counting implementation, never two that could disagree.
    A no-op (zero cost) once already cached."""
    if session.cached_row_count is not None:
        return
    reader = _open_csv_reader(session)
    row_count = 0
    max_columns = 0
    for row_number, row in enumerate(reader, start=1):
        row_count = row_number
        if len(row) > max_columns:
            max_columns = len(row)
    session.cached_row_count = row_count
    session.cached_column_count = max_columns


def _preview_csv(session: PreparationSession, *, offset: int, limit: int) -> PreviewResult:
    reader = _open_csv_reader(session)

    cached_total = session.cached_row_count
    stop_after = offset + limit  # 1-based inclusive row_number

    page: list[PreviewRow] = []
    row_count = 0
    max_columns = 0

    for row_number, row in enumerate(reader, start=1):
        row_count = row_number
        if len(row) > max_columns:
            max_columns = len(row)
        if offset < row_number <= stop_after:
            page.append(PreviewRow(row_number=row_number, cells=list(row)))
        if cached_total is not None and row_number >= stop_after:
            # Totals are already known from a prior request -- no need
            # to keep scanning once this page is fully collected.
            row_count = cached_total
            max_columns = session.cached_column_count or 0
            break
    else:
        # Loop reached the true end of the file (either cached_total was
        # None, so a full scan was required anyway, or the requested
        # page extends past the last row) -- row_count/max_columns are
        # now the real totals; memoize them for every future request
        # against this same session, regardless of which page they ask
        # for next.
        session.cached_row_count = row_count
        session.cached_column_count = max_columns

    total_row_count = session.cached_row_count if session.cached_row_count is not None else row_count
    column_count = session.cached_column_count if session.cached_column_count is not None else max_columns

    _apply_working_overlay(session, worksheet_index=None, rows=page)

    return PreviewResult(
        source_id=session.summary.source_id,
        selected_worksheet_index=None,
        offset=offset,
        limit=limit,
        returned_row_count=len(page),
        total_row_count=total_row_count,
        total_row_count_basis=ROW_BASIS_EXACT,
        column_count=column_count,
        column_count_basis=ROW_BASIS_EXACT,
        rows=page,
        ignored_columns=_ignored_columns_for_worksheet(session.working_overlay, None),
        working_revision=session.working_overlay.revision,
    )


def _json_safe_excel_cell(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    return value


def _preview_excel(session: PreparationSession, *, offset: int, limit: int) -> PreviewResult:
    summary = session.summary
    if summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before requesting a preview."
        )
    worksheet_index = summary.selected_worksheet_index
    worksheet_info = summary.worksheets[worksheet_index]

    try:
        workbook = load_workbook(io.BytesIO(session.raw_bytes), read_only=True, data_only=False)
    except Exception as exc:
        raise WorkbookParseError(f"Could not re-open the Excel workbook for preview: {exc}") from exc

    try:
        worksheet = workbook[worksheet_info.name]
        min_row = offset + 1
        max_row = offset + limit
        page: list[PreviewRow] = []
        for row_number, row_values in enumerate(
            worksheet.iter_rows(min_row=min_row, max_row=max_row, values_only=True), start=min_row
        ):
            page.append(
                PreviewRow(
                    row_number=row_number,
                    cells=[_json_safe_excel_cell(v) for v in row_values],
                )
            )
    finally:
        # Never held open across requests -- released before this
        # function returns, whether it succeeded or raised.
        workbook.close()

    _apply_working_overlay(session, worksheet_index=worksheet_index, rows=page)

    return PreviewResult(
        source_id=summary.source_id,
        selected_worksheet_index=worksheet_index,
        offset=offset,
        limit=limit,
        returned_row_count=len(page),
        total_row_count=worksheet_info.row_count,
        total_row_count_basis=ROW_BASIS_BEST_EFFORT if worksheet_info.row_count is not None else ROW_BASIS_UNKNOWN,
        column_count=worksheet_info.column_count,
        column_count_basis=ROW_BASIS_BEST_EFFORT if worksheet_info.column_count is not None else ROW_BASIS_UNKNOWN,
        rows=page,
        ignored_columns=_ignored_columns_for_worksheet(session.working_overlay, worksheet_index),
        working_revision=session.working_overlay.revision,
    )


def _overrides_for_worksheet(overlay: WorkingOverlay, worksheet_index: int | None) -> dict[int, dict[int, Any]]:
    """Pre-filter the WHOLE overlay's cell overrides down to just this
    worksheet, grouped by row -- done ONCE per preview call (not once
    per row), so applying overrides to a page stays O(page size +
    this-worksheet's own edit count), never O(page size x total edit
    count)."""
    by_row: dict[int, dict[int, Any]] = {}
    for (ws, row_number, column_index), override in overlay.cell_overrides.items():
        if ws != worksheet_index:
            continue
        by_row.setdefault(row_number, {})[column_index] = override
    return by_row


def _excluded_rows_for_worksheet(overlay: WorkingOverlay, worksheet_index: int | None) -> set[int]:
    return {row_number for (ws, row_number) in overlay.excluded_rows if ws == worksheet_index}


def _ignored_columns_for_worksheet(overlay: WorkingOverlay, worksheet_index: int | None) -> list[int]:
    return sorted(column_index for (ws, column_index) in overlay.ignored_columns if ws == worksheet_index)


def _apply_working_overlay(session: PreparationSession, *, worksheet_index: int | None, rows: list[PreviewRow]) -> None:
    """Mutate `rows` (already-fetched RAW rows) in place into their
    WORKING form -- see this module's own docstring for the exact
    strategy. Never touches `session.raw_bytes` or the overlay itself
    (read-only with respect to `session.working_overlay`)."""
    overlay = session.working_overlay
    if not overlay.cell_overrides and not overlay.excluded_rows:
        return  # common case (no edits yet at all) -- skip the filtering work entirely

    overrides_by_row = _overrides_for_worksheet(overlay, worksheet_index)
    excluded_row_numbers = _excluded_rows_for_worksheet(overlay, worksheet_index)

    for row in rows:
        row.excluded = row.row_number in excluded_row_numbers
        row_overrides = overrides_by_row.get(row.row_number)
        if not row_overrides:
            continue
        # Extend this ONE row's own cells with raw-blank (None) padding
        # only as far as needed to show an override targeting a column
        # beyond its own raw width (a short/ragged row) -- every other
        # row's own length is left exactly as the raw reader produced it
        # (task's own "editing a blank raw cell must be supported"
        # requirement, without silently padding every unmodified row).
        needed_len = max(len(row.cells), max(row_overrides) + 1)
        if needed_len > len(row.cells):
            row.cells = row.cells + [None] * (needed_len - len(row.cells))
        modified: list[ModifiedCell] = []
        for column_index in sorted(row_overrides):
            override = row_overrides[column_index]
            raw_value = row.cells[column_index]
            row.cells[column_index] = None if override.kind == OVERRIDE_KIND_CLEAR else override.value
            modified.append(ModifiedCell(column_index=column_index, raw_value=raw_value))
        row.modified_cells = modified


def preview_preparation_source(
    *,
    workspace_id: str,
    source_id: str,
    offset: int,
    limit: int,
    registry: PreparationSessionRegistry,
) -> PreviewResult:
    """Return one bounded page of WORKING rows (raw + Slice 4's overlay
    applied) for a CSV or Excel preparation source. `offset`/`limit` are
    trusted here to already be within bounds (see this module's own
    docstring: enforced by the API's own `Query(ge=..., le=...)`
    constraints, matching this codebase's existing `point_budget`
    precedent) -- this function does not re-validate them a second time.

    Raises `SourceNotFoundError` if no such preparation session exists,
    `WorksheetNotSelectedError` for an Excel source with no worksheet
    chosen yet, or `WorkbookParseError` if the stored workbook bytes
    fail to re-open (should not happen in practice -- defensive only).
    """
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(
            f"No preparation source '{source_id}' in workspace '{workspace_id}'."
        )

    if session.summary.source_format == FORMAT_CSV:
        return _preview_csv(session, offset=offset, limit=limit)
    # FORMAT_EXCEL is the only other known format (see
    # app.domain.preparation_session.KNOWN_PREPARATION_FORMATS) --
    # nothing else can have reached this registry.
    return _preview_excel(session, offset=offset, limit=limit)
