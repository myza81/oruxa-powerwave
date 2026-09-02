"""Service-level tests for Preparation Readiness Issue production (Slice 6, DEC-072).

Covers `collect_preparation_issues()`/`build_issue_summary()` -- the
conservative, informational-only issue set Slice 6 itself produces,
plus revision linkage and worksheet scoping. Pure summary-model tests
already live in tests/test_preparation_issue_domain.py.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.domain.preparation_issue import (
    ISSUE_COLUMN_ROLES_UNASSIGNED,
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_HEADER_NOT_SELECTED,
    SEVERITY_INFO,
)
from app.services.errors import SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_issue_service import build_issue_summary, collect_preparation_issues
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.working_overlay_service import (
    clear_header_row,
    set_column_role,
    set_data_region,
    set_header_row,
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


class TestCollectPreparationIssuesCsv:
    def test_fresh_upload_produces_all_three_info_issues(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\n1,2,3\n")
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        codes = {i.code for i in issues}
        assert codes == {ISSUE_HEADER_NOT_SELECTED, ISSUE_DATA_REGION_UNCONFIGURED, ISSUE_COLUMN_ROLES_UNASSIGNED}
        assert all(i.severity == SEVERITY_INFO for i in issues)

    def test_setting_header_removes_that_issue(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert ISSUE_HEADER_NOT_SELECTED not in {i.code for i in issues}

    def test_clearing_header_restores_that_issue(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        clear_header_row(workspace_id="ws-1", source_id=source_id, registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert ISSUE_HEADER_NOT_SELECTED in {i.code for i in issues}

    def test_setting_data_region_removes_that_issue(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n3,4\n")
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=1, end_row=2, registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert ISSUE_DATA_REGION_UNCONFIGURED not in {i.code for i in issues}

    def test_assigning_all_roles_removes_that_issue(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="time_axis", registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert ISSUE_COLUMN_ROLES_UNASSIGNED not in {i.code for i in issues}

    def test_partial_role_assignment_reports_exact_unassigned_count(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\n1,2,3\n")
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        role_issue = next(i for i in issues if i.code == ISSUE_COLUMN_ROLES_UNASSIGNED)
        assert role_issue.details == {"unassigned_count": 2, "total_columns": 3}

    def test_no_issues_are_ever_blocking_or_warning_in_slice_6(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert all(i.severity == SEVERITY_INFO for i in issues)

    def test_location_field_matches_the_configuration_surface(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        fields_by_code = {i.code: i.location.field for i in issues}
        assert fields_by_code[ISSUE_HEADER_NOT_SELECTED] == "header"
        assert fields_by_code[ISSUE_DATA_REGION_UNCONFIGURED] == "data_region"
        assert fields_by_code[ISSUE_COLUMN_ROLES_UNASSIGNED] == "column_roles"

    def test_every_issue_carries_a_suggested_action(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, None)

        assert all(i.suggested_action for i in issues)


class TestCollectPreparationIssuesExcel:
    def test_worksheet_scoped_location(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        session = registry.get("ws-1", source_id)

        issues = collect_preparation_issues(session, 1)

        assert all(i.location.worksheet_index == 1 for i in issues)

    def test_issues_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        session = registry.get("ws-1", source_id)

        issues_sheet_a = collect_preparation_issues(session, 0)
        issues_sheet_b = collect_preparation_issues(session, 1)

        assert ISSUE_HEADER_NOT_SELECTED not in {i.code for i in issues_sheet_a}
        assert ISSUE_HEADER_NOT_SELECTED in {i.code for i in issues_sheet_b}

    def test_unknown_column_count_skips_role_issue_without_fabricating(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["a", "b"]]})
        source_id = _add_excel(registry, content)
        session = registry.get("ws-1", source_id)
        # Force an unknown column_count to verify the role-assignment
        # issue is skipped rather than guessed.
        session.summary.worksheets[0].column_count = None

        issues = collect_preparation_issues(session, 0)

        assert ISSUE_COLUMN_ROLES_UNASSIGNED not in {i.code for i in issues}


class TestBuildIssueSummary:
    def test_summary_revision_matches_working_revision(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)

        summary = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.evaluated_revision == 1
        assert summary.current_revision == 1
        assert summary.is_stale is False

    def test_summary_counts_match_issue_list(self):
        # A totally-unconfigured source now also carries Slice 9's own
        # "no Time Axis" / "no Waveform Channel" blocking findings
        # alongside Slice 6's three original info findings.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        summary = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert summary.info_count + summary.blocking_count + summary.warning_count == len(summary.issues)
        assert summary.info_count == 3
        assert summary.blocking_count == 2
        assert summary.warning_count == 0
        assert summary.is_ready is False

    def test_unknown_source_raises_source_not_found(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(SourceNotFoundError):
            build_issue_summary(workspace_id="ws-1", source_id="nope", registry=registry)

    def test_excel_multi_sheet_without_selection_raises_worksheet_not_selected(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError):
            build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

    def test_worksheet_not_selected_is_a_runtime_error_not_an_issue(self):
        # Task's own explicit architectural rule: runtime/request
        # failures must never be represented as a PreparationIssue.
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["x"]], "B": [["y"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError) as exc_info:
            build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert exc_info.value.code == "worksheet_not_selected"
