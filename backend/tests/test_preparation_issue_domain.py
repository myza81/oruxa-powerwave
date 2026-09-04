"""Domain-level tests for the Preparation Readiness Issue model (Slice 6, DEC-072).

Pure data-structure tests -- no registry, no CSV/Excel I/O, no HTTP.
"""

from __future__ import annotations

from app.domain.preparation_issue import (
    ISSUE_DATA_REGION_UNCONFIGURED,
    ISSUE_HEADER_NOT_SELECTED,
    KNOWN_ISSUE_CODES,
    KNOWN_SEVERITIES,
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    IssueLocation,
    PreparationIssue,
    summarize_issues,
)


class TestSeverityModel:
    def test_three_known_severities(self):
        assert KNOWN_SEVERITIES == (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO)

    def test_known_issue_codes_are_stable_strings(self):
        assert ISSUE_HEADER_NOT_SELECTED in KNOWN_ISSUE_CODES
        assert ISSUE_DATA_REGION_UNCONFIGURED in KNOWN_ISSUE_CODES
        assert all(isinstance(code, str) and code for code in KNOWN_ISSUE_CODES)

    def test_column_roles_unassigned_is_retired(self):
        # UAT fix (2026-09-04): `not_assigned` is now a normal,
        # intentional final state -- not incomplete configuration -- so
        # this code no longer exists at all.
        assert "column_roles_unassigned" not in KNOWN_ISSUE_CODES


class TestIssueConstruction:
    def test_minimal_issue_has_no_location_or_extras(self):
        issue = PreparationIssue(severity=SEVERITY_INFO, code=ISSUE_HEADER_NOT_SELECTED, message="No header selected.")

        assert issue.location is None
        assert issue.suggested_action is None
        assert issue.details is None

    def test_dataset_level_location_is_all_none(self):
        location = IssueLocation()

        assert location.worksheet_index is None
        assert location.row_number is None
        assert location.column_index is None
        assert location.field is None

    def test_field_level_location(self):
        location = IssueLocation(worksheet_index=None, field="header")

        assert location.field == "header"
        assert location.row_number is None

    def test_cell_level_location(self):
        location = IssueLocation(worksheet_index=0, row_number=125, column_index=2)

        assert location.worksheet_index == 0
        assert location.row_number == 125
        assert location.column_index == 2

    def test_row_only_location(self):
        location = IssueLocation(row_number=10)

        assert location.row_number == 10
        assert location.column_index is None

    def test_column_only_location(self):
        location = IssueLocation(column_index=3)

        assert location.column_index == 3
        assert location.row_number is None

    def test_worksheet_scoped_location(self):
        location = IssueLocation(worksheet_index=1, field="column_roles")

        assert location.worksheet_index == 1
        assert location.field == "column_roles"

    def test_suggested_action_is_advisory_text(self):
        issue = PreparationIssue(
            severity=SEVERITY_INFO, code=ISSUE_HEADER_NOT_SELECTED, message="msg",
            suggested_action="Select a header row.",
        )

        assert issue.suggested_action == "Select a header row."

    def test_details_carries_small_structured_data(self):
        issue = PreparationIssue(
            severity=SEVERITY_INFO, code=ISSUE_HEADER_NOT_SELECTED, message="msg",
            details={"unassigned_count": 4, "total_columns": 6},
        )

        assert issue.details == {"unassigned_count": 4, "total_columns": 6}


class TestIssueSummary:
    def test_empty_issue_list(self):
        summary = summarize_issues(source_id="s1", revision=0, issues=[])

        assert summary.blocking_count == 0
        assert summary.warning_count == 0
        assert summary.info_count == 0
        assert summary.issues == []

    def test_one_issue_per_severity(self):
        issues = [
            PreparationIssue(severity=SEVERITY_BLOCKING, code="x", message="a"),
            PreparationIssue(severity=SEVERITY_WARNING, code="y", message="b"),
            PreparationIssue(severity=SEVERITY_INFO, code="z", message="c"),
        ]

        summary = summarize_issues(source_id="s1", revision=3, issues=issues)

        assert summary.blocking_count == 1
        assert summary.warning_count == 1
        assert summary.info_count == 1
        assert len(summary.issues) == 3

    def test_mixed_issues_exact_counts(self):
        issues = [
            PreparationIssue(severity=SEVERITY_INFO, code="a", message="1"),
            PreparationIssue(severity=SEVERITY_INFO, code="b", message="2"),
            PreparationIssue(severity=SEVERITY_WARNING, code="c", message="3"),
        ]

        summary = summarize_issues(source_id="s1", revision=5, issues=issues)

        assert summary.info_count == 2
        assert summary.warning_count == 1
        assert summary.blocking_count == 0

    def test_evaluated_and_current_revision_match_input(self):
        summary = summarize_issues(source_id="s1", revision=17, issues=[])

        assert summary.evaluated_revision == 17
        assert summary.current_revision == 17

    def test_is_stale_is_always_false_for_live_derivation(self):
        summary = summarize_issues(source_id="s1", revision=1, issues=[])

        assert summary.is_stale is False

    def test_source_id_is_preserved(self):
        summary = summarize_issues(source_id="abc-123", revision=0, issues=[])

        assert summary.source_id == "abc-123"
