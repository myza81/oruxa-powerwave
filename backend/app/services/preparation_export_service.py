"""Cleaned Data Export (CSV/Excel ingestion Slice 12, DEC-072).

**Governing principle (task's own explicit framing): "Cleaned export =
the current Working Dataset as prepared by the engineer."** Not the
untouched raw source, not the canonical `DisturbanceRecord`, not a
silently repaired dataset -- exactly what the engineer's own header/
data-region/row-exclusion/column-role/cell-edit choices currently
produce, nothing more, nothing less.

**Available regardless of Powerwave readiness** (task section A) --
this is a deliberately SEPARATE capability from Slice 10's own
canonical conversion: an engineer may use Powerwave purely to clean up
a CSV/Excel file and export the result, with no intention of ever
converting it into a waveform. `export_preparation_source()` therefore
never calls `app.services.preparation_issue_service.build_issue_
summary()` as a GATE -- only to capture a live READINESS SNAPSHOT for
the manifest (task section V: "recomputed at export time rather than
trusting stale frontend state").

**Row/column selection is a REUSE, not a re-derivation** -- the exact
same `app.services.preparation_preview_service.iterate_active_region_
rows()` single-pass streaming generator Slice 9's readiness validator
and Slice 10's own conversion service already use, filtered here to
non-excluded, non-header, in-active-region rows (identical filter to
Slice 10's own `convert_preparation_source()`). Column labels reuse
`preview_preparation_source()`'s own already-computed `column_labels`/
`column_roles` (which already encode the exact header-row-value /
neutral-spreadsheet-letter fallback task sections E/F ask for) --
this module adds only ONE new piece of logic on top: deduplicating
those labels for the columns actually being exported (task section G),
via the SAME stable-position `__{SpreadsheetLetter}` suffix strategy
Slice 10's own `_unique_channel_names()` established, generalized here
to every non-`ignore` column rather than only Waveform Channel ones.

**Time columns are never touched** (task sections M/N): a Time Axis
column exports its own CURRENT WORKING value verbatim, exactly like
every other column -- this module never calls into
`app.services.time_axis_service`'s own interpreter/preview machinery
to compute an interpreted or reconstructed value, and never adds an
extra derived-time column. Interpretation/reconstruction STATE (family/
provenance/interpreter id/unit/interval) is read once, for the
manifest's own provenance section only -- never applied to the
exported table itself.

**Read-only, by construction**: this module calls no `app.domain.
working_overlay` mutation function anywhere, and captures/re-verifies
`WorkingOverlay.revision` around the whole export (task section W) --
if a concurrent mutation is somehow observed mid-export,
`ExportRevisionChangedError` discards the whole attempt rather than
mixing rows from two different working-overlay states, mirroring Slice
10's own `ConversionRevisionChangedError` precedent exactly.

**Performance** (task section Y): one single streaming pass over
`iterate_active_region_rows()` builds the export table's rows
incrementally -- for Excel, `openpyxl.Workbook(write_only=True)` +
`worksheet.append()` writes each row directly into the underlying
zip/XML stream rather than building an in-memory cell-object graph,
matching this module's own "never build raw + working + export full
copies simultaneously" requirement. CSV uses the stdlib `csv.writer`
over an `io.StringIO`, which is already effectively O(rows) with no
second full-file materialization beyond the one `iterate_active_region_
rows()` itself already performs.

**Packaging** (task section AB): a single ZIP bundle
(`<base>_cleaned.zip`) containing the cleaned CSV/XLSX plus a sidecar
`<base>_cleaned.manifest.json` -- one download action, no separate
packaging framework (`zipfile`, stdlib only).
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook

from app.domain.preparation_session import FORMAT_CSV, PreparationSession
from app.domain.time_axis import PROVENANCE_RECONSTRUCTED
from app.domain.working_overlay import OVERRIDE_KIND_CLEAR, OVERRIDE_KIND_EDIT, ROLE_IGNORE
from app.services.errors import ExportRevisionChangedError, SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_preview_service import (
    _spreadsheet_column_label,
    iterate_active_region_rows,
    preview_preparation_source,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import get_time_axis_summary

#: Task section T's own "avoid creating a huge manifest unnecessarily"
#: allowance -- listing up to this many excluded row numbers is cheap
#: and useful; beyond it, only the count is reported (plus a truncation
#: flag), never an unbounded list. Matches `app.domain.working_overlay.
#: MAX_OPERATION_HISTORY`'s own bound for the same "generous but not
#: unlimited" reasoning.
MAX_MANIFEST_EXCLUDED_ROWS_LISTED = 200

#: Excel worksheet name constraints (task section C): at most 31
#: characters, and none of `: \ / ? * [ ]` -- Excel's own real
#: constraints, not an invented rule. A name that becomes empty after
#: sanitization (e.g. the source name was entirely invalid characters)
#: falls back to this deterministic default, matching a normal new
#: workbook's own first-sheet name.
_EXCEL_INVALID_SHEET_CHARS = re.compile(r"[:\\/?*\[\]]")
_EXCEL_MAX_SHEET_NAME_LENGTH = 31
_DEFAULT_SHEET_NAME = "Sheet1"

#: Filename sanitization (task section AC): keep only characters safe
#: in a downloaded filename across common filesystems -- alphanumerics,
#: dash, underscore, and space (collapsed to underscore); everything
#: else is dropped, never trusted from the raw uploaded filename
#: (which may contain path separators or other unsafe characters).
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]")
_MAX_BASE_FILENAME_LENGTH = 100
_DEFAULT_BASE_FILENAME = "recording"

MANIFEST_VERSION = 1


@dataclass(slots=True)
class ExportResult:
    """The finished, ready-to-return export bundle -- a single ZIP
    containing the cleaned CSV/XLSX plus its own manifest JSON. Never a
    filesystem path (task section Z: no durable storage is introduced
    by this module) -- the caller (the API route) returns `content`
    directly as an HTTP response body."""

    filename: str
    content: bytes
    media_type: str = "application/zip"


def _resolve_session(*, workspace_id: str, source_id: str, registry: PreparationSessionRegistry) -> PreparationSession:
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise SourceNotFoundError(f"No preparation source '{source_id}' in workspace '{workspace_id}'.")
    return session


def _resolve_worksheet_index(session: PreparationSession) -> int | None:
    worksheets = session.summary.worksheets
    if not worksheets:
        return None
    if session.summary.selected_worksheet_index is None:
        raise WorksheetNotSelectedError(
            "This workbook has more than one worksheet; select one with "
            "PATCH .../preparation-sources/{source_id} before exporting it."
        )
    return session.summary.selected_worksheet_index


def _sanitize_base_filename(original_filename: str) -> str:
    """`event.csv` -> `event` (task section AC's own worked example) --
    strips the original extension, keeps only filesystem-safe
    characters, collapses runs of whitespace to a single underscore,
    and falls back to a deterministic default if nothing safe survives
    (an entirely non-ASCII or entirely-symbolic original filename)."""
    stem = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
    cleaned = _UNSAFE_FILENAME_CHARS.sub("", stem).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned[:_MAX_BASE_FILENAME_LENGTH].strip("._")
    return cleaned or _DEFAULT_BASE_FILENAME


def _sanitize_sheet_name(name: str) -> str:
    """Task section C's own explicit rule: preserve the original
    selected worksheet name when practical; if it becomes invalid
    (empty, or over Excel's own 31-character limit, after stripping
    `: \\ / ? * [ ]`) apply the deterministic `Sheet1` fallback rather
    than guessing at a "close enough" alternative."""
    cleaned = _EXCEL_INVALID_SHEET_CHARS.sub("", name).strip()
    cleaned = cleaned[:_EXCEL_MAX_SHEET_NAME_LENGTH]
    return cleaned or _DEFAULT_SHEET_NAME


def _unique_export_names(column_labels: list[str], included_column_indices: list[int]) -> dict[int, str]:
    """One deterministic, unique export column name per INCLUDED column
    (task section G) -- the same strategy Slice 10's own canonical
    conversion `_unique_channel_names()` established: the FIRST included
    column to use a given label keeps it verbatim; every LATER included
    column sharing that same label gets a stable `__{SpreadsheetLetter}`
    suffix (`Voltage`, `Voltage__C`, `Voltage__D`). Deliberately scoped
    to only the columns actually being exported -- an omitted `Ignore`
    column's own label never consumes a disambiguation slot for columns
    that ARE exported. `column_labels` already carries `preview_
    preparation_source()`'s own header-row-value / neutral-fallback
    logic (task sections E/F); this function's only job is uniqueness on
    top of that, never re-deriving the label itself."""
    seen: dict[str, int] = {}
    result: dict[int, str] = {}
    for column_index in included_column_indices:
        label = (
            column_labels[column_index]
            if column_index < len(column_labels)
            else _spreadsheet_column_label(column_index)
        )
        count = seen.get(label, 0)
        seen[label] = count + 1
        result[column_index] = label if count == 0 else f"{label}__{_spreadsheet_column_label(column_index)}"
    return result


def _cell_export_value(value: Any) -> Any:
    """Task section L: a genuinely empty cell (raw `None`, or a working
    CLEAR override -- both already surface as `None` in `PreviewRow.
    cells`) exports as an empty field/cell, never the literal text
    `"None"`/`"NaN"`/`"null"`/`0`. Every other value passes through
    UNCHANGED -- this function never coerces, parses, or reinterprets a
    non-empty value (task's own explicit "do not coerce ambiguous
    non-empty text" guardrail)."""
    return "" if value is None else value


def export_preparation_source(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry,
) -> ExportResult:
    """Export the CURRENT Working Dataset of one CSV/Excel preparation
    source as a cleaned CSV or single-worksheet XLSX, bundled into one
    ZIP with a provenance manifest. Available regardless of Powerwave
    readiness (task section A) -- never gated on `is_ready`. Raises an
    `ImportServiceError` subclass (never a `PreparationIssue`) for every
    runtime failure; never mutates the preparation session, the working
    overlay, or the raw source in any way.
    """
    session = _resolve_session(workspace_id=workspace_id, source_id=source_id, registry=registry)
    worksheet_index = _resolve_worksheet_index(session)
    captured_revision = session.working_overlay.revision

    # Readiness is captured LIVE for the manifest snapshot only -- never
    # a gate (task section A/V).
    issue_summary = build_issue_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)
    time_axis_summary = get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)

    preview = preview_preparation_source(workspace_id=workspace_id, source_id=source_id, offset=0, limit=1, registry=registry)
    column_labels = preview.column_labels
    column_roles = preview.column_roles
    omitted_columns = [
        {"column_index": c, "label": column_labels[c] if c < len(column_labels) else _spreadsheet_column_label(c)}
        for c, role in enumerate(column_roles)
        if role == ROLE_IGNORE
    ]
    included_column_indices = [c for c, role in enumerate(column_roles) if role != ROLE_IGNORE]
    export_name_by_column = _unique_export_names(column_labels, included_column_indices)
    header_names = [export_name_by_column[c] for c in included_column_indices]

    exported_rows: list[list[Any]] = []
    excluded_row_numbers: list[int] = []
    for row in iterate_active_region_rows(session, worksheet_index=worksheet_index):
        if row.excluded:
            excluded_row_numbers.append(row.row_number)
        # Task section E: the header row is schema, never an exported
        # data row, even if the active data region happens to overlap
        # it (a deliberate, documented choice for that overlap case).
        if row.is_header or not row.in_active_region or row.excluded:
            continue
        exported_rows.append([_cell_export_value(row.cells[c] if c < len(row.cells) else None) for c in included_column_indices])

    # Edit/clear provenance counts (task section U) -- one cheap pass
    # over just this worksheet's own sparse overrides (proportional to
    # edit count, never to dataset size), scoped the SAME way Slice 10's
    # own `excluded_row_count` provenance field already is.
    edited_cell_count = 0
    cleared_cell_count = 0
    for (ws, _row_number, _column_index), override in session.working_overlay.cell_overrides.items():
        if ws != worksheet_index:
            continue
        if override.kind == OVERRIDE_KIND_EDIT:
            edited_cell_count += 1
        elif override.kind == OVERRIDE_KIND_CLEAR:
            cleared_cell_count += 1

    region = session.working_overlay.data_region.get(worksheet_index)
    base_name = _sanitize_base_filename(session.summary.original_filename)

    if session.summary.source_format == FORMAT_CSV:
        artifact_bytes = _build_csv_artifact(header_names, exported_rows)
        artifact_filename = f"{base_name}_cleaned.csv"
    else:
        sheet_name = _sanitize_sheet_name(session.summary.worksheets[worksheet_index].name)
        artifact_bytes = _build_xlsx_artifact(sheet_name, header_names, exported_rows)
        artifact_filename = f"{base_name}_cleaned.xlsx"

    manifest = _build_manifest(
        session=session, worksheet_index=worksheet_index, captured_revision=captured_revision,
        issue_summary=issue_summary, time_axis_summary=time_axis_summary,
        omitted_columns=omitted_columns, column_roles=column_roles,
        edited_cell_count=edited_cell_count, cleared_cell_count=cleared_cell_count,
        excluded_row_numbers=excluded_row_numbers, exported_row_count=len(exported_rows),
        artifact_filename=artifact_filename,
    )
    manifest_filename = f"{base_name}_cleaned.manifest.json"
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=False).encode("utf-8")

    # Revision race protection (task section W) -- verify nothing
    # mutated the working overlay while this export was being built,
    # mirroring Slice 10's own `ConversionRevisionChangedError`
    # precedent exactly. Export never registers/persists anything, so
    # there is no "half from one revision" state to leave behind either
    # way -- this simply refuses to hand back a bundle that may have
    # mixed two different working-overlay states.
    if session.working_overlay.revision != captured_revision:
        raise ExportRevisionChangedError(
            "This preparation source changed while the export was being built -- please retry."
        )

    zip_bytes = _build_zip(artifact_filename, artifact_bytes, manifest_filename, manifest_bytes)
    return ExportResult(filename=f"{base_name}_cleaned.zip", content=zip_bytes)


def _build_csv_artifact(header_names: list[str], rows: list[list[Any]]) -> bytes:
    """Task section AK: a normalized, deterministic CSV dialect --
    comma delimiter, UTF-8, the stdlib `csv` module's own standard
    newline handling (`\\r\\n` via `writer` default) -- never an attempt
    to preserve whatever delimiter/quoting the ORIGINAL source file
    happened to use."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header_names)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _build_xlsx_artifact(sheet_name: str, header_names: list[str], rows: list[list[Any]]) -> bytes:
    """Task section AI: a single CLEAN tabular worksheet -- no attempt
    to preserve the original workbook's styling, formulas, charts,
    macros, or merged cells, and no recalculation of any formula (task
    section AJ: the WORKING cell value, exactly as the preparation
    overlay already represents it, is written verbatim). `write_only`
    mode (task section Y) streams each row directly into the underlying
    zip/XML rather than building an in-memory cell-object graph for the
    whole sheet."""
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=sheet_name)
    worksheet.append(header_names)
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _build_manifest(
    *, session: PreparationSession, worksheet_index: int | None, captured_revision: int,
    issue_summary, time_axis_summary, omitted_columns: list[dict], column_roles: list[str],
    edited_cell_count: int, cleared_cell_count: int, excluded_row_numbers: list[int],
    exported_row_count: int, artifact_filename: str,
) -> dict[str, Any]:
    """Task section S: stable, machine-readable manifest keys only --
    never a raw Python object repr, never an attempt to recreate the
    original raw source (task section R: the raw bytes remain
    separately immutable in the `PreparationSession` itself)."""
    excluded_row_numbers = sorted(excluded_row_numbers)
    truncated = len(excluded_row_numbers) > MAX_MANIFEST_EXCLUDED_ROWS_LISTED
    listed_excluded_rows = excluded_row_numbers[:MAX_MANIFEST_EXCLUDED_ROWS_LISTED]

    worksheet_name = (
        session.summary.worksheets[worksheet_index].name if worksheet_index is not None else None
    )
    region = session.working_overlay.data_region.get(worksheet_index)

    return {
        "manifest_version": MANIFEST_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_file": artifact_filename,
        "source_format": session.summary.source_format,
        "original_filename": session.summary.original_filename,
        "worksheet_name": worksheet_name,
        "worksheet_index": worksheet_index,
        "preparation_revision": captured_revision,
        "header_row": session.working_overlay.header_row.get(worksheet_index),
        "data_region": (
            {"start_row": region.start_row, "end_mode": region.end_mode, "end_row": region.end_row}
            if region is not None else None
        ),
        "exported_row_count": exported_row_count,
        "excluded_row_count": len(excluded_row_numbers),
        "excluded_rows": listed_excluded_rows,
        "excluded_rows_truncated": truncated,
        "omitted_columns": omitted_columns,
        "column_roles": column_roles,
        "edited_cell_count": edited_cell_count,
        "cleared_cell_count": cleared_cell_count,
        "time_family": time_axis_summary.family,
        "time_provenance": time_axis_summary.provenance,
        "interpreter_id": time_axis_summary.interpreter_id,
        "time_unit": time_axis_summary.unit,
        "time_interval_seconds": time_axis_summary.interval_seconds,
        "reconstructed_timing": time_axis_summary.provenance == PROVENANCE_RECONSTRUCTED,
        "readiness": {
            "is_ready": issue_summary.is_ready,
            "blocking_count": issue_summary.blocking_count,
            "warning_count": issue_summary.warning_count,
            "info_count": issue_summary.info_count,
        },
    }


def _build_zip(artifact_filename: str, artifact_bytes: bytes, manifest_filename: str, manifest_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(artifact_filename, artifact_bytes)
        archive.writestr(manifest_filename, manifest_bytes)
    return buffer.getvalue()
