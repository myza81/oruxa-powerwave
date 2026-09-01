"""Service-level tests for Working Dataset overlay orchestration (Slices 4-5, DEC-072).

Covers bounds validation, worksheet resolution, and the shared
`WorkingOverlaySummary` -- the pure mutation semantics themselves are
already covered by tests/test_working_overlay_domain.py.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.services.errors import (
    InvalidColumnRoleError,
    InvalidDataRegionError,
    InvalidWorkingCellValueError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    WorksheetNotSelectedError,
)
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
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


def _build_xlsx(sheets: dict | None = None) -> bytes:
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


class TestEditCellCsv:
    def test_edit_within_bounds_succeeds(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry,
        )

        assert summary.edited_cell_count == 1
        assert summary.working_revision == 1
        assert summary.can_undo is True
        assert summary.can_redo is False

    def test_edit_beyond_known_row_total_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=99, column_index=0,
                value="X", registry=registry,
            )

    def test_edit_beyond_known_column_total_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=99,
                value="X", registry=registry,
            )

    def test_first_edit_triggers_a_full_scan_to_learn_totals(self):
        # The CSV has no separate index -- totals must be known before
        # bounds can be enforced at all, reusing the exact same scan
        # preview already uses (ensure_csv_totals_cached).
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=1, value="X", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.cached_row_count == 3
        assert session.cached_column_count == 2

    def test_oversized_value_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCellValueError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
                value="x" * 10_001, registry=registry,
            )

    def test_clear_value_none_is_never_length_checked(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value=None, registry=registry,
        )

        assert summary.edited_cell_count == 1

    def test_unknown_source_raises_source_not_found(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(SourceNotFoundError):
            edit_cell(
                workspace_id="ws-1", source_id="nope", row_number=1, column_index=0,
                value="x", registry=registry,
            )


class TestEditCellExcel:
    def test_edit_requires_worksheet_selection_first(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError):
            edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="z", registry=registry)

    def test_edit_after_selection_succeeds(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)

        summary = edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="z", registry=registry)

        assert summary.edited_cell_count == 1

    def test_edits_on_different_worksheets_are_isolated(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="from-a", registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="from-b", registry=registry)

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import cell_key
        assert session.working_overlay.cell_overrides[cell_key(0, 1, 0)].value == "from-a"
        assert session.working_overlay.cell_overrides[cell_key(1, 1, 0)].value == "from-b"

    def test_edit_beyond_known_row_total_is_rejected(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["a"], ["b"]]})  # 2 rows
        source_id = _add_excel(registry, content)

        with pytest.raises(InvalidWorkingCoordinateError):
            edit_cell(workspace_id="ws-1", source_id=source_id, row_number=99, column_index=0, value="z", registry=registry)


class TestResetCell:
    def test_reset_removes_the_override(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)

        summary = reset_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, registry=registry)

        assert summary.edited_cell_count == 0

    def test_reset_with_no_override_is_a_safe_no_op(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = reset_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, registry=registry)

        assert summary.edited_cell_count == 0


class TestRowExclusion:
    def test_exclude_and_include(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=True, registry=registry)
        assert summary.excluded_row_count == 1

        summary = set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=False, registry=registry)
        assert summary.excluded_row_count == 0

    def test_exclude_beyond_known_row_total_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=99, excluded=True, registry=registry)


class TestColumnIgnore:
    def test_ignore_and_unignore(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=True, registry=registry)
        assert summary.ignored_column_count == 1

        summary = set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=False, registry=registry)
        assert summary.ignored_column_count == 0

    def test_ignore_beyond_known_column_total_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=99, ignored=True, registry=registry)


class TestResetAllAndUndoRedo:
    def test_reset_all_clears_every_kind_of_change(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=True, registry=registry)
        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=True, registry=registry)
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=3, registry=registry)

        summary = reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.edited_cell_count == 0
        assert summary.excluded_row_count == 0
        assert summary.ignored_column_count == 0
        assert summary.header_row_number is None
        assert summary.data_start_row is None
        assert summary.data_end_row is None
        assert summary.can_undo is True  # reset_all itself remains undoable

    def test_reset_all_works_even_without_a_selected_worksheet(self):
        # Reset All is session-wide -- it must not require a worksheet
        # selection the way cell/row/column/header/region edits do.
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        summary = reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.edited_cell_count == 0

    def test_undo_after_reset_all_restores_header_and_region(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=3, registry=registry)
        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        summary = undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.header_row_number == 1
        assert summary.data_start_row == 2
        assert summary.data_end_row == 3

    def test_undo_after_reset_all_restores_everything(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        summary = undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.edited_cell_count == 1

    def test_undo_then_redo_cell_edit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)

        summary = undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.edited_cell_count == 0
        assert summary.can_redo is True

        summary = redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.edited_cell_count == 1

    def test_undo_with_no_history_is_a_safe_no_op(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.can_undo is False


class TestWorkingOverlaySummary:
    def test_freshly_uploaded_source_has_an_empty_summary(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        session = registry.get("ws-1", source_id)

        summary = summarize_working_overlay(session)

        assert summary.working_revision == 0
        assert summary.edited_cell_count == 0
        assert summary.excluded_row_count == 0
        assert summary.ignored_column_count == 0
        assert summary.can_undo is False
        assert summary.can_redo is False
        assert summary.header_row_number is None
        assert summary.data_start_row is None
        assert summary.data_end_row is None


class TestHeaderRow:
    def test_set_and_read_back_via_summary(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\nc,d\n1,2\n")

        summary = set_header_row(workspace_id="ws-1", source_id=source_id, row_number=2, registry=registry)

        assert summary.header_row_number == 2

    def test_clear_header_row(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\nc,d\n1,2\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=2, registry=registry)

        summary = clear_header_row(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.header_row_number is None

    def test_header_row_beyond_known_bounds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_header_row(workspace_id="ws-1", source_id=source_id, row_number=999, registry=registry)

    def test_header_row_excel_requires_worksheet_selection(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError):
            set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

    def test_header_row_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["h-a"], ["1"]], "B": [["h-b"], ["2"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        summary_b = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=1)

        assert summary_b.header_row_number is None  # sheet B starts unconfigured

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        summary_a = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=0)
        assert summary_a.header_row_number == 1  # sheet A's own configuration remains intact


class TestDataRegion:
    def test_set_and_read_back_via_summary(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n5,6\n")

        summary = set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=3, registry=registry)

        assert summary.data_start_row == 2
        assert summary.data_end_row == 3

    def test_reset_data_region(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_row=2, registry=registry)

        summary = reset_data_region(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.data_start_row is None
        assert summary.data_end_row is None

    def test_start_greater_than_end_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        with pytest.raises(InvalidDataRegionError):
            set_data_region(workspace_id="ws-1", source_id=source_id, start_row=3, end_row=1, registry=registry)

    def test_start_equal_to_end_is_accepted(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=2, registry=registry)

        assert summary.data_start_row == 2
        assert summary.data_end_row == 2

    def test_end_beyond_known_bounds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_row=999, registry=registry)

    def test_region_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["1"], ["2"], ["3"]], "B": [["4"], ["5"], ["6"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_row=2, registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        summary_b = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=1)
        assert summary_b.data_start_row is None


class TestDataRegionEndMode:
    """Owner-UAT refinement: an explicit `end_mode`, defaulting to
    `"specific"` so every pre-refinement call site above keeps working
    unchanged (see TestDataRegion, which never passes `end_mode` at
    all)."""

    def test_default_end_mode_is_specific(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=3, registry=registry)

        assert summary.data_end_mode == "specific"
        assert summary.data_end_row == 3

    def test_source_end_mode_stores_no_numeric_end_row(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n5,6\n")

        summary = set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_mode="source_end", registry=registry)

        assert summary.data_start_row == 2
        assert summary.data_end_mode == "source_end"
        assert summary.data_end_row is None

    def test_source_end_mode_ignores_a_stray_end_row_value(self):
        # end_row is never stored for source_end -- even if a client
        # sends one anyway, it must not leak into the domain model.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = set_data_region(
            workspace_id="ws-1", source_id=source_id, start_row=1, end_row=999, end_mode="source_end", registry=registry,
        )

        assert summary.data_end_row is None

    def test_specific_mode_without_end_row_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidDataRegionError):
            set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_mode="specific", registry=registry)

    def test_invalid_end_mode_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidDataRegionError):
            set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_mode="last_page", registry=registry)

    def test_source_end_mode_start_row_still_bounds_checked(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_data_region(workspace_id="ws-1", source_id=source_id, start_row=999, end_mode="source_end", registry=registry)

    def test_source_end_mode_never_requires_a_full_extra_scan_beyond_existing_totals_cache(self):
        # No new scan mechanism was introduced for this refinement --
        # source_end mode reuses whatever CSV total-count caching
        # already existed (ensure_csv_totals_cached, via _check_row_bound
        # for start_row) rather than deriving a separate resolved bound
        # at mutation time.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_mode="source_end", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.cached_row_count == 3  # populated by the existing start_row bound check, nothing extra

    def test_excel_source_end_mode_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["1"], ["2"]], "B": [["3"], ["4"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_mode="source_end", registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        summary_b = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=1)
        assert summary_b.data_end_mode is None

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        summary_a = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=0)
        assert summary_a.data_end_mode == "source_end"


class TestColumnRole:
    def test_assign_and_read_back_ignored_count(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = set_column_role(
            workspace_id="ws-1", source_id=source_id, column_index=1, role="ignore", registry=registry,
        )

        assert summary.ignored_column_count == 1

    def test_reset_column_role(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        reset_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, registry=registry)

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert column_key(None, 1) not in session.working_overlay.column_roles

    def test_invalid_role_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidColumnRoleError):
            set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="voltage", registry=registry)

    def test_column_beyond_known_bounds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_column_role(workspace_id="ws-1", source_id=source_id, column_index=99, role="metadata", registry=registry)

    def test_multiple_time_axis_columns_allowed(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="time_axis", registry=registry)

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert session.working_overlay.column_roles[column_key(None, 0)] == "time_axis"
        assert session.working_overlay.column_roles[column_key(None, 1)] == "time_axis"

    def test_role_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["1"]], "B": [["2"]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        summary_b = summarize_working_overlay(registry.get("ws-1", source_id), worksheet_index=1)
        assert summary_b.ignored_column_count == 0

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert column_key(1, 0) not in session.working_overlay.column_roles
        assert session.working_overlay.column_roles[column_key(0, 0)] == "waveform"

    def test_legacy_ignore_endpoint_still_works_as_an_alias(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=True, registry=registry)
        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import ROLE_IGNORE, column_key
        assert session.working_overlay.column_roles[column_key(None, 1)] == ROLE_IGNORE

        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=False, registry=registry)
        assert column_key(None, 1) not in session.working_overlay.column_roles

    def test_legacy_unignore_does_not_disturb_a_different_explicit_role(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        # Calling the legacy "unignore" on a column that was never
        # ignored (it has a different explicit role) must not silently
        # reclassify it.
        set_column_ignored(workspace_id="ws-1", source_id=source_id, column_index=1, ignored=False, registry=registry)

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert session.working_overlay.column_roles[column_key(None, 1)] == "waveform"
