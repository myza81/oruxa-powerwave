"""Service-level tests for paged raw-data preview (Slice 3, DEC-072).

`preview_preparation_source` is a plain synchronous function (unlike the
upload services, which are async to match FastAPI's `UploadFile`
handling) -- no `asyncio.run()` wrapper needed here.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.services.errors import SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_preview_service import (
    ROW_BASIS_BEST_EFFORT,
    ROW_BASIS_EXACT,
    preview_preparation_source,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.working_overlay_service import (
    edit_cell,
    reset_all_working_changes,
    reset_cell,
    set_column_ignored,
    set_row_excluded,
)


def _upload(content: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


def _add_csv(registry: PreparationSessionRegistry, content: bytes, workspace_id: str = "ws-1", filename: str = "e.csv") -> str:
    summary = asyncio.run(
        import_csv_preparation_source(
            workspace_id=workspace_id, csv_upload=_upload(content, filename, "text/csv"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


def _build_xlsx(sheets: dict | None = None, hidden: frozenset = frozenset(), formulas: dict | None = None) -> bytes:
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
    if formulas:
        for cell_ref, formula in formulas.items():
            workbook.active[cell_ref] = formula
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _add_excel(registry: PreparationSessionRegistry, content: bytes, workspace_id: str = "ws-1", filename: str = "e.xlsx") -> str:
    summary = asyncio.run(
        import_excel_preparation_source(
            workspace_id=workspace_id,
            excel_upload=_upload(content, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


# ---- CSV preview ----


class TestCsvPreview:
    def test_first_page(self):
        registry = PreparationSessionRegistry()
        content = "\n".join(f"{i},v{i}" for i in range(1, 11)).encode()
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=5, registry=registry)

        assert result.offset == 0
        assert result.limit == 5
        assert result.returned_row_count == 5
        assert [r.row_number for r in result.rows] == [1, 2, 3, 4, 5]
        assert result.rows[0].cells == ["1", "v1"]
        assert result.total_row_count == 10
        assert result.total_row_count_basis == ROW_BASIS_EXACT
        assert result.column_count == 2
        assert result.column_count_basis == ROW_BASIS_EXACT
        assert result.selected_worksheet_index is None

    def test_later_page(self):
        registry = PreparationSessionRegistry()
        content = "\n".join(f"{i},v{i}" for i in range(1, 11)).encode()
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=5, limit=5, registry=registry)

        assert [r.row_number for r in result.rows] == [6, 7, 8, 9, 10]
        assert result.rows[0].cells == ["6", "v6"]
        assert result.total_row_count == 10

    def test_partial_final_page(self):
        registry = PreparationSessionRegistry()
        content = "\n".join(f"{i},v{i}" for i in range(1, 11)).encode()  # 10 rows
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=8, limit=5, registry=registry)

        # Only rows 9-10 exist beyond offset 8.
        assert [r.row_number for r in result.rows] == [9, 10]
        assert result.returned_row_count == 2
        assert result.total_row_count == 10

    def test_offset_past_end_returns_empty_page_not_an_error(self):
        registry = PreparationSessionRegistry()
        content = b"a,b\n1,2\n"  # 2 rows total
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=100, limit=10, registry=registry)

        assert result.rows == []
        assert result.returned_row_count == 0
        assert result.total_row_count == 2

    def test_blank_cells_preserved(self):
        registry = PreparationSessionRegistry()
        content = b"a,,c\n,,\n"
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "", "c"]
        assert result.rows[1].cells == ["", "", ""]

    def test_blank_rows_preserved_with_row_number(self):
        registry = PreparationSessionRegistry()
        content = b"a,b\n\n1,2\n"
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert [r.row_number for r in result.rows] == [1, 2, 3]
        assert result.rows[1].cells == []  # the blank row itself
        assert result.rows[2].cells == ["1", "2"]

    def test_many_columns(self):
        registry = PreparationSessionRegistry()
        wide_row = ",".join(str(i) for i in range(50))
        content = (wide_row + "\n").encode()
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.column_count == 50
        assert len(result.rows[0].cells) == 50

    def test_first_row_is_not_treated_as_a_header(self):
        registry = PreparationSessionRegistry()
        content = b"time,VA\n0.0,1.0\n"
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        # Row 1 (the would-be "header") is returned as an ordinary raw
        # row, not consumed/skipped/relabeled.
        assert result.rows[0].row_number == 1
        assert result.rows[0].cells == ["time", "VA"]

    def test_deleted_source_cannot_preview(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        registry.remove("ws-1", source_id)

        with pytest.raises(SourceNotFoundError):
            preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

    def test_unknown_source_raises_source_not_found(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(SourceNotFoundError):
            preview_preparation_source(workspace_id="ws-1", source_id="does-not-exist", offset=0, limit=10, registry=registry)

    def test_totals_are_cached_after_first_preview_and_reused(self):
        registry = PreparationSessionRegistry()
        content = "\n".join(f"{i},v{i}" for i in range(1, 11)).encode()
        source_id = _add_csv(registry, content)

        preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=3, registry=registry)
        session = registry.get("ws-1", source_id)
        assert session.cached_row_count == 10
        assert session.cached_column_count == 2

        # A later page still reports the same correct total without
        # needing to re-derive it from scratch (implementation detail,
        # but observable via the correct total on a page that itself
        # doesn't reach the end of the file).
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=3, limit=2, registry=registry)
        assert result.total_row_count == 10


class TestCsvStructure:
    def test_comma_delimited(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\n1,2,3\n")

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "b", "c"]

    def test_quoted_commas_are_not_split(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b'a,"b,c",d\n1,2,3\n')

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "b,c", "d"]

    def test_semicolon_delimiter_is_sniffed(self):
        registry = PreparationSessionRegistry()
        content = b"a;b;c\n1;2;3\n4;5;6\n"
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "b", "c"]
        assert result.column_count == 3

    def test_ambiguous_single_column_falls_back_to_comma_default(self):
        # No real delimiter present anywhere -- sniffing must fail
        # cleanly and fall back to the safe default, never guess a
        # nonsense delimiter from the data itself.
        registry = PreparationSessionRegistry()
        content = b"onlyonecolumn\nanothervalue\n"
        source_id = _add_csv(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["onlyonecolumn"]
        assert result.rows[1].cells == ["anothervalue"]

    def test_no_trailing_newline_still_reads_the_last_row(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2")  # no trailing \n

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert [r.cells for r in result.rows] == [["a", "b"], ["1", "2"]]


# ---- Excel preview ----


class TestExcelPreview:
    def test_one_sheet_workbook_preview(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["time", "VA"], [0.0, 1.0], [0.001, 2.0]]})
        source_id = _add_excel(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.selected_worksheet_index == 0  # auto-selected, Slice 2
        assert [r.row_number for r in result.rows] == [1, 2, 3]
        assert result.rows[0].cells == ["time", "VA"]
        assert result.total_row_count == 3
        assert result.total_row_count_basis == ROW_BASIS_BEST_EFFORT
        assert result.column_count == 2

    def test_multi_sheet_requires_selection_first(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError):
            preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

    def test_multi_sheet_preview_after_explicit_selection(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Event Data": [["e1"]], "RMS": [["r1"], ["r2"]]})
        source_id = _add_excel(registry, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.selected_worksheet_index == 1
        assert [r.cells for r in result.rows] == [["r1"], ["r2"]]

    def test_switching_worksheet_changes_the_preview(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["from-a"]], "B": [["from-b"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        result_a = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert result_a.rows[0].cells == ["from-a"]

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_b = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert result_b.rows[0].cells == ["from-b"]

    def test_hidden_sheet_can_still_be_previewed_once_selected(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Visible": [["v"]], "Hidden": [["h"]]}, hidden=frozenset({"Hidden"}))
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["h"]

    def test_blank_cells_are_none(self):
        registry = PreparationSessionRegistry()
        workbook = Workbook()
        workbook.active.append(["a", None, "c"])
        buf = io.BytesIO()
        workbook.save(buf)
        source_id = _add_excel(registry, buf.getvalue())

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", None, "c"]

    def test_formula_cell_shows_stored_formula_text(self):
        registry = PreparationSessionRegistry()
        workbook = Workbook()
        ws = workbook.active
        ws["A1"] = 5
        ws["A2"] = "=A1+1"
        buf = io.BytesIO()
        workbook.save(buf)
        source_id = _add_excel(registry, buf.getvalue())

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == [5]
        assert result.rows[1].cells == ["=A1+1"]

    def test_partial_final_page(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [[i] for i in range(1, 6)]})  # 5 rows
        source_id = _add_excel(registry, content)

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=3, limit=10, registry=registry)

        assert [r.row_number for r in result.rows] == [4, 5]

    def test_worksheet_resources_are_released_after_preview(self):
        # No direct handle-leak assertion possible from outside openpyxl,
        # but this confirms repeated previews against the same session
        # never fail/hang, consistent with the workbook being reopened
        # and closed cleanly every call (see the service's own docstring).
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["x"]]})
        source_id = _add_excel(registry, content)

        for _ in range(5):
            preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)


# ---- CSV/Excel ingestion Slice 4 (DEC-072): working overlay merged into preview ----


class TestWorkingOverlayInCsvPreview:
    def test_edited_cell_shows_the_working_value(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=0, value="EDITED", registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[1].cells == ["EDITED", "2"]

    def test_edited_cell_reports_provenance_via_modified_cells(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=0, value="EDITED", registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        edited_row = result.rows[1]
        assert len(edited_row.modified_cells) == 1
        assert edited_row.modified_cells[0].column_index == 0
        assert edited_row.modified_cells[0].raw_value == "1"

    def test_unmodified_rows_have_no_modified_cells(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=0, value="EDITED", registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].modified_cells == []

    def test_cleared_cell_shows_none(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=1, value=None, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", None]

    def test_reset_cell_restores_the_raw_value_in_preview(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        reset_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "b"]
        assert result.rows[0].modified_cells == []

    def test_editing_a_blank_cell_beyond_a_ragged_rows_own_width_is_supported(self):
        # Row 2 only has one column ("x") -- editing column_index=2 on it
        # must pad ONLY this row, not silently widen every other row.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\nx\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=2, value="NEW", registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[1].cells == ["x", None, "NEW"]
        assert result.rows[0].cells == ["a", "b", "c"]  # untouched row keeps its own original width

    def test_excluded_row_is_flagged_but_never_removed_or_renumbered(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n5,6\n")  # rows 1-4

        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=3, excluded=True, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert [r.row_number for r in result.rows] == [1, 2, 3, 4]
        assert [r.excluded for r in result.rows] == [False, False, True, False]
        assert result.rows[2].cells == ["3", "4"]  # excluded row's own data is unchanged

    def test_ignored_column_is_reported_page_independently(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\n1,2,3\n")  # row 1: a,b,c / row 2: 1,2,3

        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=True, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.ignored_columns == [1]
        # Ignoring a column never removes it from the returned cells --
        # it is a display/consumption hint, not a structural deletion.
        assert result.rows[1].cells == ["1", "2", "3"]

    def test_working_revision_reflects_the_overlays_own_revision_counter(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        before = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert before.working_revision == 0

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        after = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert after.working_revision == 1

    def test_reset_all_restores_the_full_raw_preview(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")  # 3 rows

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=True, registry=registry)
        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=True, registry=registry)

        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["a", "b"]
        assert [r.excluded for r in result.rows] == [False, False, False]
        assert result.ignored_columns == []

    def test_no_overlay_activity_skips_overlay_processing_entirely(self):
        # A freshly uploaded/unedited source's preview must look byte-
        # for-byte identical to Slice 3's own raw preview (regression
        # guard for the "common case" early-return in
        # _apply_working_overlay).
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].excluded is False
        assert result.rows[0].modified_cells == []
        assert result.ignored_columns == []
        assert result.working_revision == 0

    def test_raw_bytes_are_never_mutated_by_an_edit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        session = registry.get("ws-1", source_id)
        original_raw_bytes = session.raw_bytes

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)

        assert session.raw_bytes == original_raw_bytes
        assert session.raw_bytes is original_raw_bytes


class TestWorkingOverlayInExcelPreview:
    def test_edit_on_selected_worksheet_shows_in_preview(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="EDITED", registry=registry)
        result = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)

        assert result.rows[0].cells == ["EDITED"]

    def test_edits_do_not_leak_across_worksheets_in_preview(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="from-a", registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_b = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert result_b.rows[0].cells == ["y"]  # untouched -- the edit targeted worksheet 0 only

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        result_a = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert result_a.rows[0].cells == ["from-a"]

