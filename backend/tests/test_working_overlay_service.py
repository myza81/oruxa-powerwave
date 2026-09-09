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

from app.domain.working_overlay import (
    OVERRIDE_KIND_CLEAR,
    OVERRIDE_KIND_EDIT,
    OVERRIDE_KIND_NULL,
    cell_key,
    column_key,
)
from app.domain.preparation_issue import ISSUE_TIME_VALUE_MISSING, ISSUE_WAVEFORM_VALUE_INVALID, ISSUE_WAVEFORM_VALUE_MISSING
from app.services.errors import (
    InvalidBulkNullIssueCodeError,
    InvalidColumnRoleError,
    InvalidDataRegionError,
    InvalidEngineeringQuantityError,
    InvalidMeasuredUnitError,
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
    apply_bulk_mark_null,
    clear_header_row,
    edit_cell,
    preview_bulk_mark_null,
    redo_working_change,
    reset_all_working_changes,
    reset_cell,
    reset_column_engineering_quantity,
    reset_column_measured_unit,
    reset_column_role,
    reset_data_region,
    set_column_engineering_quantity,
    set_column_measured_unit,
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


class TestEditCellExplicitNull:
    """DEC-084 (Slice 1): `kind="null"` is the one unambiguous way a
    caller requests the explicit-null override -- distinct from
    `value=None` (clear) at both the request-schema and domain layers."""

    def test_kind_null_with_value_omitted_is_accepted(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")

        summary = edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value=None, kind=OVERRIDE_KIND_NULL, registry=registry,
        )

        assert summary.edited_cell_count == 1
        session = registry.get("ws-1", source_id)
        override = session.working_overlay.cell_overrides[cell_key(None, 1, 0)]
        assert override.kind == OVERRIDE_KIND_NULL
        assert override.value is None

    def test_kind_null_with_value_explicitly_none_is_accepted(self):
        # `value=None` is indistinguishable from "omitted" once it
        # reaches this function (both are the Python `None` default) --
        # this test exists to prove that shape is accepted, not merely
        # untested.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value=None, kind=OVERRIDE_KIND_NULL, registry=registry,
        )

        assert summary.edited_cell_count == 1
        session = registry.get("ws-1", source_id)
        override = session.working_overlay.cell_overrides[cell_key(None, 1, 0)]
        assert override.kind == OVERRIDE_KIND_NULL
        assert override.value is None

    def test_kind_null_with_a_non_null_value_is_rejected(self):
        # DEC-084's own data-integrity guardrail: the application must
        # never silently reinterpret or discard supplied data. A client
        # sending both an explicit-null operation AND a real value has a
        # bug -- it must fail visibly, not silently lose the value.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCellValueError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
                value="123.45", kind=OVERRIDE_KIND_NULL, registry=registry,
            )

    def test_kind_null_with_a_non_null_value_does_not_mutate_the_overlay(self):
        # The rejected request must be a true no-op -- no override
        # written, no history entry recorded -- never a partial/silent
        # application of either the null or the value.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCellValueError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
                value="123.45", kind=OVERRIDE_KIND_NULL, registry=registry,
            )

        session = registry.get("ws-1", source_id)
        assert cell_key(None, 1, 0) not in session.working_overlay.cell_overrides
        assert session.working_overlay.revision == 0

    def test_kind_null_with_empty_string_value_is_rejected(self):
        # An empty string is still a REAL, non-null value -- it must be
        # rejected exactly like any other non-null value, never treated
        # as equivalent to omitted/None.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCellValueError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
                value="", kind=OVERRIDE_KIND_NULL, registry=registry,
            )

    def test_kind_omitted_with_value_none_is_still_a_plain_clear(self):
        # Backward compatibility: the legacy request shape (no `kind` at
        # all) must keep producing a CLEAR, never a null, so existing
        # callers are completely unaffected by this addition.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value=None, registry=registry,
        )

        session = registry.get("ws-1", source_id)
        override = session.working_overlay.cell_overrides[cell_key(None, 1, 0)]
        assert override.kind == OVERRIDE_KIND_CLEAR

    def test_kind_omitted_with_a_string_value_is_still_a_plain_edit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value="42", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        override = session.working_overlay.cell_overrides[cell_key(None, 1, 0)]
        assert override.kind == OVERRIDE_KIND_EDIT
        assert override.value == "42"

    def test_an_unrecognized_kind_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCellValueError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
                value=None, kind="bogus", registry=registry,
            )

    def test_kind_null_still_enforces_row_bounds(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            edit_cell(
                workspace_id="ws-1", source_id=source_id, row_number=99, column_index=0,
                value=None, kind=OVERRIDE_KIND_NULL, registry=registry,
            )

    def test_kind_null_overwrites_a_previous_edit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="42", registry=registry)

        edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0,
            value=None, kind=OVERRIDE_KIND_NULL, registry=registry,
        )

        session = registry.get("ws-1", source_id)
        override = session.working_overlay.cell_overrides[cell_key(None, 1, 0)]
        assert override.kind == OVERRIDE_KIND_NULL


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


class TestResetAllAndUndoRedo:
    def test_reset_all_clears_every_kind_of_change(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="X", registry=registry)
        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=True, registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=3, registry=registry)

        summary = reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.edited_cell_count == 0
        assert summary.excluded_row_count == 0
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
    def test_assign_and_read_back(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        set_column_role(
            workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert session.working_overlay.column_roles[column_key(None, 1)] == "waveform"

    def test_legacy_roles_are_rejected(self):
        # UAT fix (2026-09-04): `unknown`/`metadata`/`quality_status`/
        # `ignore` are retired -- only `not_assigned`/`time_axis`/
        # `waveform` remain valid.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        for legacy_role in ("unknown", "metadata", "quality_status", "ignore"):
            with pytest.raises(InvalidColumnRoleError):
                set_column_role(
                    workspace_id="ws-1", source_id=source_id, column_index=0, role=legacy_role, registry=registry,
                )

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
            set_column_role(workspace_id="ws-1", source_id=source_id, column_index=99, role="waveform", registry=registry)

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

        session = registry.get("ws-1", source_id)
        from app.domain.working_overlay import column_key
        assert column_key(1, 0) not in session.working_overlay.column_roles
        assert session.working_overlay.column_roles[column_key(0, 0)] == "waveform"


class TestColumnEngineeringQuantity:
    """DEC-077: direct PUT/DELETE-equivalent service calls, independent
    of any suffix-restoration behavior (covered separately below)."""

    def test_assign_and_read_back(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            engineering_quantity="Voltage", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 1)] == "Voltage"

    def test_invalid_quantity_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidEngineeringQuantityError):
            set_column_engineering_quantity(
                workspace_id="ws-1", source_id=source_id, column_index=0,
                engineering_quantity="Power Factor", registry=registry,
            )

    def test_lowercase_is_rejected_exact_casing_only(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidEngineeringQuantityError):
            set_column_engineering_quantity(
                workspace_id="ws-1", source_id=source_id, column_index=0,
                engineering_quantity="voltage", registry=registry,
            )

    def test_column_beyond_known_bounds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_column_engineering_quantity(
                workspace_id="ws-1", source_id=source_id, column_index=99,
                engineering_quantity="Voltage", registry=registry,
            )

    def test_reset_column_engineering_quantity(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            engineering_quantity="Current", registry=registry,
        )

        reset_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1, registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert column_key(None, 1) not in session.working_overlay.column_engineering_quantities

    def test_role_changing_away_from_waveform_preserves_stored_quantity(self):
        # DEC-077 task section J's chosen behavior, verified end-to-end
        # through the service layer this time (not just the pure domain
        # function) -- "ignored," not cleared.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="not_assigned", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 0)] == "Voltage"


class TestEngineeringQuantitySuffixRestoration:
    """DEC-077 task section S: assigning ROLE_WAVEFORM to a column whose
    current WORKING label carries a recognized suffix restores the
    Engineering Quantity automatically -- the ONE place this fires."""

    def test_assigning_waveform_restores_quantity_from_labeled_header(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n2.0,0.02\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 0)] == "Voltage"

    def test_no_header_configured_means_label_is_a_plain_letter_never_matches(self):
        # Without a header row selected, the column's own "label" is just
        # its neutral spreadsheet letter ("A") -- never mistaken for a
        # suffix.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n")

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_engineering_quantities

    def test_ordinary_label_without_suffix_does_not_restore_anything(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"Voltage Sensor,Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_engineering_quantities

    def test_role_never_auto_assigned_merely_because_a_label_looks_self_describing(self):
        # Only the QUANTITY is restored; ROLE_WAVEFORM must still be an
        # explicit user action (task section S: "do not silently broaden
        # auto-role detection").
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_roles

    def test_does_not_overwrite_an_explicit_prior_quantity(self):
        # Assign Waveform, override the auto-suggestion, remove the role,
        # re-assign Waveform -- the user's own explicit override must
        # survive, never silently re-suggested over.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Current", registry=registry,
        )
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 0)] == "Current"

    def test_assigning_time_axis_role_never_restores_a_quantity(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_engineering_quantities


class TestColumnMeasuredUnit:
    """Measured Unit enhancement (DEC-080): direct PUT/DELETE-equivalent
    service calls, mirroring TestColumnEngineeringQuantity's own
    structure."""

    def test_assign_and_read_back(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            engineering_quantity="Voltage", registry=registry,
        )

        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=1, measured_unit="kV", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_measured_units[column_key(None, 1)] == "kV"

    def test_blank_is_always_accepted(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=1, measured_unit="", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert column_key(None, 1) not in session.working_overlay.column_measured_units

    def test_invalid_pair_is_rejected(self):
        """Task section AE/AF: backend validates the quantity/unit pair
        itself -- MW is not valid for Voltage."""
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )

        with pytest.raises(InvalidMeasuredUnitError):
            set_column_measured_unit(
                workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="MW", registry=registry,
            )

    def test_active_power_rejects_reactive_power_unit(self):
        """Task section AE: backend must not allow a Reactive Power unit
        for an Active Power quantity, regardless of frontend filtering."""
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Active Power", registry=registry,
        )

        with pytest.raises(InvalidMeasuredUnitError):
            set_column_measured_unit(
                workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="Mvar", registry=registry,
            )

    def test_undefined_quantity_rejects_a_non_blank_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidMeasuredUnitError):
            set_column_measured_unit(
                workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="V", registry=registry,
            )

    def test_column_beyond_known_bounds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_column_measured_unit(
                workspace_id="ws-1", source_id=source_id, column_index=99, measured_unit="kV", registry=registry,
            )

    def test_reset_column_measured_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            engineering_quantity="Current", registry=registry,
        )
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=1, measured_unit="kA", registry=registry,
        )

        reset_column_measured_unit(workspace_id="ws-1", source_id=source_id, column_index=1, registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 1) not in session.working_overlay.column_measured_units

    def test_role_changing_away_from_waveform_preserves_stored_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="kV", registry=registry,
        )

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="not_assigned", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_measured_units[column_key(None, 0)] == "kV"


class TestQuantityChangeClearsIncompatibleUnit:
    """Task section J: changing Engineering Quantity must never silently
    convert an existing unit -- an incompatible one is cleared to blank."""

    def test_changing_quantity_clears_an_incompatible_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="kV", registry=registry,
        )

        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Frequency", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_measured_units

    def test_changing_quantity_keeps_a_still_compatible_unit(self):
        """Voltage -> Voltage Angle both share no common unit here, but a
        genuinely shared value (blank) is left untouched, and switching
        between the two Voltage-family quantities to an incompatible one
        clears it -- this test locks in that a compatible transition
        (Voltage -> Voltage, i.e. no real change) never clears a valid
        unit."""
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="kV", registry=registry,
        )

        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_measured_units[column_key(None, 0)] == "kV"

    def test_resetting_quantity_to_undefined_clears_an_existing_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=0,
            engineering_quantity="Voltage", registry=registry,
        )
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="kV", registry=registry,
        )

        reset_column_engineering_quantity(workspace_id="ws-1", source_id=source_id, column_index=0, registry=registry)

        session = registry.get("ws-1", source_id)
        assert column_key(None, 0) not in session.working_overlay.column_measured_units


class TestEngineeringQuantityAndUnitSuffixRestoration:
    """Measured Unit enhancement (DEC-080), task section S: assigning
    ROLE_WAVEFORM to a column whose current WORKING label carries a
    recognized quantity+unit suffix restores BOTH automatically."""

    def test_assigning_waveform_restores_quantity_and_unit_from_labeled_header(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage) [kV],Time\n1.0,0.0\n2.0,0.02\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 0)] == "Voltage"
        assert session.working_overlay.column_measured_units[column_key(None, 0)] == "kV"

    def test_quantity_only_suffix_still_restores_quantity_alone(self):
        """Backward compatibility with a DEC-077-only export (task
        section T/AR) -- no unit is restored because none was ever
        encoded."""
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage),Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.column_engineering_quantities[column_key(None, 0)] == "Voltage"
        assert column_key(None, 0) not in session.working_overlay.column_measured_units

    def test_does_not_overwrite_an_explicit_prior_unit(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"CBDK_V1 Magnitude (Voltage) [kV],Time\n1.0,0.0\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        set_column_measured_unit(
            workspace_id="ws-1", source_id=source_id, column_index=0, measured_unit="V", registry=registry,
        )
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        # The quantity was already explicit from the FIRST waveform
        # assignment, so the auto-suggest block never fires again at all
        # on this second round trip -- the user's own "V" override survives.
        assert session.working_overlay.column_measured_units[column_key(None, 0)] == "V"


def _bulk_source(registry: PreparationSessionRegistry, *, rows: int = 5, blank_at: tuple = (), invalid_at: tuple = ()) -> str:
    """A minimal CSV with column 0 = Time Axis (always valid), column 1
    = Waveform -- `blank_at`/`invalid_at` are 1-based row numbers to
    seed as an empty/invalid raw waveform value."""
    lines = []
    for i in range(1, rows + 1):
        value = "" if i in blank_at else ("ERR" if i in invalid_at else f"{i}.0")
        lines.append(f"2026-08-31 13:00:{i:02d},{value}")
    source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
    set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)
    set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)
    return source_id


class TestPreviewBulkMarkNull:
    def test_returns_the_authoritative_eligible_count_with_no_mutation(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6))
        session = registry.get("ws-1", source_id)
        revision_before = session.working_overlay.revision

        result = preview_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 3
        assert session.working_overlay.cell_overrides == {}  # no mutation
        assert session.working_overlay.revision == revision_before  # no history entry either

    def test_invalid_scope_returns_the_invalid_count(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, invalid_at=(3, 5))

        result = preview_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_INVALID, registry=registry,
        )

        assert result.eligible_count == 2

    def test_not_assigned_column_returns_zero_eligible_never_an_error(self):
        registry = PreparationSessionRegistry()
        lines = ["2026-08-31 13:00:00,1.0,"]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)
        # column_index=2 stays not_assigned

        result = preview_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=2,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 0

    def test_out_of_range_column_raises_invalid_working_coordinate(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=3)

        with pytest.raises(InvalidWorkingCoordinateError):
            preview_bulk_mark_null(
                workspace_id="ws-1", source_id=source_id, column_index=99,
                issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
            )

    def test_time_axis_issue_code_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=3)

        with pytest.raises(InvalidBulkNullIssueCodeError):
            preview_bulk_mark_null(
                workspace_id="ws-1", source_id=source_id, column_index=0,
                issue_code=ISSUE_TIME_VALUE_MISSING, registry=registry,
            )


class TestApplyBulkMarkNull:
    def test_marks_every_currently_eligible_cell(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6))

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 3
        assert result.applied_count == 3
        assert result.overlay.can_undo is True
        session = registry.get("ws-1", source_id)
        for row_number in (2, 4, 6):
            assert session.working_overlay.cell_overrides[cell_key(None, row_number, 1)].kind == OVERRIDE_KIND_NULL

    def test_creates_exactly_one_undoable_operation(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=20, blank_at=tuple(range(1, 21)))

        apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        session = registry.get("ws-1", source_id)
        # 2 set_column_role ops (Time Axis + Waveform) + 1 bulk op.
        assert len(session.working_overlay.history) == 3
        assert session.working_overlay.history[-1].kind == "bulk_cell"

    def test_undo_restores_the_whole_group_in_one_press(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6))
        apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        summary = undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.can_redo is True
        session = registry.get("ws-1", source_id)
        for row_number in (2, 4, 6):
            assert cell_key(None, row_number, 1) not in session.working_overlay.cell_overrides

    def test_redo_reapplies_the_full_group(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6))
        apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )
        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        session = registry.get("ws-1", source_id)
        for row_number in (2, 4, 6):
            assert session.working_overlay.cell_overrides[cell_key(None, row_number, 1)].kind == OVERRIDE_KIND_NULL

    def test_reset_all_restores_original_source_state(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6))
        apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.working_overlay.cell_overrides == {}

    def test_staleness_manually_repaired_cells_are_not_overwritten(self):
        # Task section 13/33's own exact scenario: preview says N,
        # then the user manually fixes some of those cells before the
        # SAME bulk scope is applied -- apply must re-evaluate current
        # eligibility, never trust the earlier preview.
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4, 6, 8))
        preview = preview_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )
        assert preview.eligible_count == 4
        # The user manually repairs two of the four blank cells in between.
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=2, column_index=1, value="22.0", registry=registry)
        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=4, column_index=1, value="44.0", registry=registry)

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 2  # re-evaluated fresh, not the stale 4
        assert result.applied_count == 2
        session = registry.get("ws-1", source_id)
        # The manually repaired cells keep their real, entered values --
        # never converted to null by the stale bulk request.
        assert session.working_overlay.cell_overrides[cell_key(None, 2, 1)].kind == OVERRIDE_KIND_EDIT
        assert session.working_overlay.cell_overrides[cell_key(None, 2, 1)].value == "22.0"
        assert session.working_overlay.cell_overrides[cell_key(None, 4, 1)].kind == OVERRIDE_KIND_EDIT
        assert session.working_overlay.cell_overrides[cell_key(None, 4, 1)].value == "44.0"
        # The two still-blank cells DID get nulled.
        assert session.working_overlay.cell_overrides[cell_key(None, 6, 1)].kind == OVERRIDE_KIND_NULL
        assert session.working_overlay.cell_overrides[cell_key(None, 8, 1)].kind == OVERRIDE_KIND_NULL

    def test_already_explicit_null_cells_are_not_recounted_or_reapplied(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=10, blank_at=(2, 4))
        edit_cell(
            workspace_id="ws-1", source_id=source_id, row_number=2, column_index=1,
            value=None, kind="null", registry=registry,
        )

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 1  # only row 4 -- row 2 already resolved
        assert result.applied_count == 1

    def test_not_assigned_column_applies_nothing_returns_zero_no_error(self):
        registry = PreparationSessionRegistry()
        lines = ["2026-08-31 13:00:00,1.0,"]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=2,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.applied_count == 0
        session = registry.get("ws-1", source_id)
        assert session.working_overlay.cell_overrides == {}

    def test_no_eligible_cells_is_a_normal_zero_response_not_an_error(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=5)  # every cell already valid

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.eligible_count == 0
        assert result.applied_count == 0

    def test_valid_sibling_channel_in_the_same_row_stays_untouched(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{'' if i == 2 else f'{i}.0'},{i}.5" for i in range(1, 6)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="time_axis", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=2, role="waveform", registry=registry)

        apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        session = registry.get("ws-1", source_id)
        assert cell_key(None, 2, 1) in session.working_overlay.cell_overrides
        assert cell_key(None, 2, 2) not in session.working_overlay.cell_overrides  # sibling column untouched

    def test_large_batch_50000_cells_stays_a_single_operation(self):
        registry = PreparationSessionRegistry()
        source_id = _bulk_source(registry, rows=50_000, blank_at=tuple(range(1, 50_001)))

        result = apply_bulk_mark_null(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            issue_code=ISSUE_WAVEFORM_VALUE_MISSING, registry=registry,
        )

        assert result.applied_count == 50_000
        session = registry.get("ws-1", source_id)
        assert session.working_overlay.history[-1].kind == "bulk_cell"
        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert session.working_overlay.cell_overrides == {}
