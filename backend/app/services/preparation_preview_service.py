"""Paged raw-data preview for CSV/Excel preparation sources (Slice 3, DEC-072).

Owns exactly one job: given an already-accepted `PreparationSession`
(Slices 1-2), return a bounded WINDOW of its raw rows/cells -- never the
whole dataset, never a header/data-region inference, never a type
coercion beyond what the underlying reader naturally exposes. This is
strictly an inspection surface:

    PreparationSession (raw, immutable)
            |
    preview_preparation_source() (this module)
            |
    a bounded page of raw rows -- never cached beyond one request,
    never mutates the session's own raw_bytes

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
on the first preview request (any page), so every later request already
knows when it can stop early instead of re-scanning to the true end of
the file. This is the one lightweight optimization considered
"clearly necessary" for reasonable UX here -- not a general-purpose row
index, which the task explicitly said not to build prematurely.

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
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook

from app.domain.preparation_session import FORMAT_CSV, FORMAT_EXCEL, PreparationSession
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
class PreviewRow:
    """One raw row -- `row_number` is 1-based and matches the source's
    own row position (CSV: `csv.reader`'s own enumeration; Excel:
    the worksheet's own row index) -- never renumbered/reindexed as if a
    header had been removed. `cells` is exactly what the reader
    produced: CSV cells are always `str` (an empty string for a blank
    field); Excel cells keep their native JSON-safe type (`str`/`float`/
    `int`/`bool`/`None` for blank, with `datetime`/`date`/`time` values
    converted to their ISO-8601 string form purely for JSON transport --
    never reformatted/reinterpreted otherwise)."""

    row_number: int
    cells: list[Any]


@dataclass(slots=True)
class PreviewResult:
    """See this module's own docstring for the CSV/Excel strategies that
    produce this. `selected_worksheet_index` is `None` for CSV (no
    worksheet concept at all -- never fabricated)."""

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


def _preview_csv(session: PreparationSession, *, offset: int, limit: int) -> PreviewResult:
    # errors="replace" (never raises): task scope is raw structural
    # preview, not encoding detection -- an undecodable byte becomes a
    # visible replacement character rather than failing the whole
    # preview. This is a disclosed simplification, not a claim that
    # encoding detection is solved.
    text = session.raw_bytes.decode("utf-8", errors="replace")
    delimiter = _sniff_csv_delimiter(text[:_CSV_SNIFF_SAMPLE_CHARS])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

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
    worksheet_info = summary.worksheets[summary.selected_worksheet_index]

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

    return PreviewResult(
        source_id=summary.source_id,
        selected_worksheet_index=summary.selected_worksheet_index,
        offset=offset,
        limit=limit,
        returned_row_count=len(page),
        total_row_count=worksheet_info.row_count,
        total_row_count_basis=ROW_BASIS_BEST_EFFORT if worksheet_info.row_count is not None else ROW_BASIS_UNKNOWN,
        column_count=worksheet_info.column_count,
        column_count_basis=ROW_BASIS_BEST_EFFORT if worksheet_info.column_count is not None else ROW_BASIS_UNKNOWN,
        rows=page,
    )


def preview_preparation_source(
    *,
    workspace_id: str,
    source_id: str,
    offset: int,
    limit: int,
    registry: PreparationSessionRegistry,
) -> PreviewResult:
    """Return one bounded page of raw rows for a CSV or Excel
    preparation source. `offset`/`limit` are trusted here to already be
    within bounds (see this module's own docstring: enforced by the
    API's own `Query(ge=..., le=...)` constraints, matching this
    codebase's existing `point_budget` precedent) -- this function does
    not re-validate them a second time.

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
