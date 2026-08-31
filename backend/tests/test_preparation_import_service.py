"""Service-level tests for CSV/Excel preparation-source import (Slices 1-2, DEC-072).

Mirrors the "Upload tests" character of tests/test_sources_api.py's own
TestUpload class, but at the service layer, plus a set of guardrail
assertions specific to this slice's own explicit scope limits (no
DisturbanceRecord, no waveform-ready registry entry).

`import_csv_preparation_source`/`import_excel_preparation_source` are
async (matches `import_comtrade_source`'s own signature) -- driven here
via `asyncio.run()` rather than `async def test_...`, since this project
has no pytest-asyncio/anyio pytest plugin installed and no existing
precedent for testing an async service function directly (COMTRADE's
own async import service is exercised only through the synchronous
`TestClient` in tests/test_sources_api.py). See
tests/test_preparation_sources_api.py for the equivalent API-level
coverage through that same TestClient pattern.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.domain.preparation_session import FORMAT_CSV, FORMAT_EXCEL, STATUS_NEEDS_PREPARATION
from app.services.errors import (
    EmptyWorkbookError,
    InvalidFileError,
    InvalidWorksheetIndexError,
    SourceNotFoundError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
    WorkbookParseError,
    WorksheetSelectionNotApplicableError,
)
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_session_registry import PreparationSessionRegistry


def _upload(content: bytes, filename: str | None = "event.csv", content_type: str = "text/csv") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _import(**kwargs):
    return asyncio.run(import_csv_preparation_source(**kwargs))


def _import_excel(**kwargs):
    return asyncio.run(import_excel_preparation_source(**kwargs))


def _build_xlsx(sheets: dict | None = None, hidden: frozenset = frozenset()) -> bytes:
    """Build a minimal .xlsx workbook in memory -- no fixture files on
    disk, matching this project's general preference for small,
    programmatically-built test inputs over committed binary blobs where
    that's just as clear (COMTRADE's own synthetic fixtures are text-
    based .cfg/.dat, not binary, for the same reason)."""
    if sheets is None:
        sheets = {"Sheet1": [["a", "b"], [1, 2]]}
    workbook = Workbook()
    names = list(sheets.keys())
    workbook.active.title = names[0]
    for row in sheets[names[0]]:
        workbook.active.append(row)
    for name in names[1:]:
        ws = workbook.create_sheet(name)
        for row in sheets[name]:
            ws.append(row)
    for name in hidden:
        workbook[name].sheet_state = "hidden"
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def test_valid_csv_is_accepted_and_returns_expected_summary():
    registry = PreparationSessionRegistry()
    content = b"time,VA\n0.0,1.0\n0.001,2.0\n"

    summary = _import(
        workspace_id="ws-1",
        csv_upload=_upload(content, "GPTH disturbance.csv"),
        max_total_bytes=100 * 1024 * 1024,
        registry=registry,
    )

    assert summary.workspace_id == "ws-1"
    assert summary.original_filename == "GPTH disturbance.csv"
    assert summary.source_format == FORMAT_CSV
    assert summary.status == STATUS_NEEDS_PREPARATION
    assert summary.original_byte_size == len(content)
    assert summary.source_id  # non-empty, opaque id


def test_accepted_session_is_stored_in_the_registry_with_raw_bytes_preserved():
    registry = PreparationSessionRegistry()
    content = b"time,VA\n0.0,1.0\n"

    summary = _import(
        workspace_id="ws-1", csv_upload=_upload(content), max_total_bytes=1_000_000, registry=registry,
    )

    stored = registry.get("ws-1", summary.source_id)
    assert stored is not None
    assert stored.raw_bytes == content
    assert stored.summary == summary


def test_unsupported_extension_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(UnsupportedFileTypeError):
        _import(
            workspace_id="ws-1",
            csv_upload=_upload(b"not a csv", "event.txt"),
            max_total_bytes=1_000_000,
            registry=registry,
        )
    assert registry.count() == 0


def test_missing_filename_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(UnsupportedFileTypeError):
        _import(
            workspace_id="ws-1",
            csv_upload=_upload(b"a,b\n1,2\n", filename=None),
            max_total_bytes=1_000_000,
            registry=registry,
        )
    assert registry.count() == 0


def test_empty_csv_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(InvalidFileError):
        _import(
            workspace_id="ws-1", csv_upload=_upload(b"", "empty.csv"), max_total_bytes=1_000_000, registry=registry,
        )
    assert registry.count() == 0


def test_oversized_csv_is_rejected():
    registry = PreparationSessionRegistry()
    content = b"x" * 2000

    with pytest.raises(UploadTooLargeError):
        _import(
            workspace_id="ws-1", csv_upload=_upload(content, "big.csv"), max_total_bytes=1000, registry=registry,
        )
    assert registry.count() == 0


def test_two_uploads_in_the_same_workspace_get_distinct_source_ids():
    registry = PreparationSessionRegistry()

    first = _import(
        workspace_id="ws-1", csv_upload=_upload(b"a,b\n1,2\n", "a.csv"), max_total_bytes=1_000_000, registry=registry,
    )
    second = _import(
        workspace_id="ws-1", csv_upload=_upload(b"c,d\n3,4\n", "b.csv"), max_total_bytes=1_000_000, registry=registry,
    )

    assert first.source_id != second.source_id
    assert {s.summary.source_id for s in registry.list_for_workspace("ws-1")} == {
        first.source_id,
        second.source_id,
    }


# ---- CSV/Excel ingestion Slice 2 (DEC-072): Excel upload + worksheet discovery ----


class TestExcelUpload:
    def test_single_sheet_workbook_is_accepted_and_auto_selected(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Event Data": [["time", "VA"], [0.0, 1.0], [0.001, 2.0]]})

        summary = _import_excel(
            workspace_id="ws-1",
            excel_upload=_upload(content, "GPTH disturbance.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            max_total_bytes=100 * 1024 * 1024,
            registry=registry,
        )

        assert summary.workspace_id == "ws-1"
        assert summary.original_filename == "GPTH disturbance.xlsx"
        assert summary.source_format == FORMAT_EXCEL
        assert summary.status == STATUS_NEEDS_PREPARATION
        assert summary.original_byte_size == len(content)
        assert [w.name for w in summary.worksheets] == ["Event Data"]
        assert summary.worksheets[0].index == 0
        assert summary.worksheets[0].visible is True
        # Auto-selected -- exactly one worksheet, deterministic (see this
        # slice's own docstring for the exact rule).
        assert summary.selected_worksheet_index == 0

    def test_row_and_column_counts_are_populated_best_effort(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["a", "b", "c"], [1, 2, 3], [4, 5, 6]]})

        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "e.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )

        sheet = summary.worksheets[0]
        assert sheet.row_count == 3
        assert sheet.column_count == 3

    def test_multi_sheet_workbook_discovers_all_sheets_in_order_and_leaves_selection_unset(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({
            "Event Data": [["time", "VA"], [0.0, 1.0]],
            "RMS": [["time", "rms"], [0.0, 1.0]],
            "Settings": [["k", "v"]],
            "Summary": [["note"]],
        })

        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "multi.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )

        assert [w.name for w in summary.worksheets] == ["Event Data", "RMS", "Settings", "Summary"]
        assert [w.index for w in summary.worksheets] == [0, 1, 2, 3]
        # Multiple worksheets -- never auto-selected (task's own "Excel,
        # multiple worksheets" scenario: the user must choose explicitly).
        assert summary.selected_worksheet_index is None

    def test_hidden_sheet_is_discovered_with_visible_false_never_dropped(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx(
            {"Visible One": [["a"]], "Hidden One": [["b"]]},
            hidden=frozenset({"Hidden One"}),
        )

        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "h.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )

        by_name = {w.name: w for w in summary.worksheets}
        assert by_name["Visible One"].visible is True
        assert by_name["Hidden One"].visible is False
        # Hidden sheets are discovered, not silently merged/discarded --
        # and a workbook with one visible + one hidden sheet is TWO
        # worksheets total, so it is not auto-selected.
        assert summary.selected_worksheet_index is None

    def test_accepted_excel_session_is_stored_in_the_registry_with_raw_bytes_preserved(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx()

        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "e.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )

        stored = registry.get("ws-1", summary.source_id)
        assert stored is not None
        assert stored.raw_bytes == content
        assert stored.summary == summary


class TestInvalidExcelUpload:
    def test_unsupported_extension_is_rejected(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(UnsupportedFileTypeError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(_build_xlsx(), "event.xls"),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0

    def test_missing_filename_is_rejected(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(UnsupportedFileTypeError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(_build_xlsx(), filename=None),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0

    def test_empty_upload_is_rejected(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(InvalidFileError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(b"", "empty.xlsx"),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0

    def test_oversized_excel_is_rejected(self):
        registry = PreparationSessionRegistry()
        # A real .xlsx is a zip container, so even a minimal workbook has
        # real overhead (Content_Types.xml, docProps, ...) -- the limit
        # below is set well under that actual size, not under some
        # assumed-tiny value.
        content = _build_xlsx()

        with pytest.raises(UploadTooLargeError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(content, "big.xlsx"),
                max_total_bytes=len(content) - 1,
                registry=registry,
            )
        assert registry.count() == 0

    def test_corrupt_workbook_bytes_raise_workbook_parse_error(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(WorkbookParseError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(b"this is not a real workbook" * 10, "corrupt.xlsx"),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0

    def test_non_excel_bytes_renamed_xlsx_raise_workbook_parse_error(self):
        registry = PreparationSessionRegistry()
        # A real CSV's bytes, renamed .xlsx -- extension alone must never
        # be trusted; the workbook must actually open.
        csv_bytes = b"time,VA\n0.0,1.0\n"

        with pytest.raises(WorkbookParseError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(csv_bytes, "fake.xlsx"),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0

    def test_valid_zip_that_is_not_a_workbook_raises_workbook_parse_error(self):
        import zipfile

        registry = PreparationSessionRegistry()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("hello.txt", "not a workbook")

        with pytest.raises(WorkbookParseError):
            _import_excel(
                workspace_id="ws-1",
                excel_upload=_upload(buf.getvalue(), "notreally.xlsx"),
                max_total_bytes=1_000_000,
                registry=registry,
            )
        assert registry.count() == 0


class TestWorksheetSelection:
    def test_select_a_worksheet_updates_selection(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "m.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )
        assert summary.selected_worksheet_index is None

        updated = select_preparation_worksheet(
            workspace_id="ws-1", source_id=summary.source_id, worksheet_index=1, registry=registry,
        )

        assert updated.selected_worksheet_index == 1
        # The registry's own stored copy reflects the same update --
        # single source of truth, not a copy that could drift.
        assert registry.get("ws-1", summary.source_id).summary.selected_worksheet_index == 1

    def test_select_out_of_range_index_raises_invalid_worksheet_index(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "m.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )

        with pytest.raises(InvalidWorksheetIndexError):
            select_preparation_worksheet(
                workspace_id="ws-1", source_id=summary.source_id, worksheet_index=2, registry=registry,
            )
        with pytest.raises(InvalidWorksheetIndexError):
            select_preparation_worksheet(
                workspace_id="ws-1", source_id=summary.source_id, worksheet_index=-1, registry=registry,
            )

    def test_select_on_csv_source_raises_not_applicable(self):
        registry = PreparationSessionRegistry()
        summary = _import(
            workspace_id="ws-1", csv_upload=_upload(b"a,b\n1,2\n", "c.csv"), max_total_bytes=1_000_000, registry=registry,
        )

        with pytest.raises(WorksheetSelectionNotApplicableError):
            select_preparation_worksheet(
                workspace_id="ws-1", source_id=summary.source_id, worksheet_index=0, registry=registry,
            )

    def test_select_on_unknown_source_raises_source_not_found(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(SourceNotFoundError):
            select_preparation_worksheet(
                workspace_id="ws-1", source_id="does-not-exist", worksheet_index=0, registry=registry,
            )

    def test_reselecting_an_already_auto_selected_single_sheet_workbook_is_allowed(self):
        # A one-sheet workbook auto-selects index 0 -- re-confirming that
        # same selection explicitly must not be rejected merely because
        # it's already set.
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["x"]]})
        summary = _import_excel(
            workspace_id="ws-1", excel_upload=_upload(content, "one.xlsx"), max_total_bytes=1_000_000, registry=registry,
        )
        assert summary.selected_worksheet_index == 0

        updated = select_preparation_worksheet(
            workspace_id="ws-1", source_id=summary.source_id, worksheet_index=0, registry=registry,
        )
        assert updated.selected_worksheet_index == 0
