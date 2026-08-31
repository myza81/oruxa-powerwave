"""Service-level tests for Working Dataset overlay orchestration (Slice 4, DEC-072).

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
    edit_cell,
    redo_working_change,
    reset_all_working_changes,
    reset_cell,
    set_column_ignored,
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

        summary = reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.edited_cell_count == 0
        assert summary.excluded_row_count == 0
        assert summary.ignored_column_count == 0
        assert summary.can_undo is True  # reset_all itself remains undoable

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
