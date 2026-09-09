"""Structural checks for the Raw Data Preview Data Quality summary +
Data Issues side panel (DEC-084, Slice 4).

Same static source-text convention every other test_frontend_*.py file
in this suite uses -- no JS execution engine is part of this repo's
test harness, so these assert markup/id/class presence and the exact
source text of the relevant functions, never runtime DOM behavior.
Browser-level behavior (open/close, actual navigation, actual
highlighting) requires manual UAT -- see this task's own final report.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestDataQualitySummary:
    def test_summary_strip_exists_above_the_table(self):
        source = _source()
        preview_card_start = source.index('id="wwDataPrepPreviewHeading"')
        table_start = source.index('id="wwDataPrepTable"')
        summary_start = source.index('id="wwDataQualitySummary"')
        assert preview_card_start < summary_start < table_start

    def test_summary_has_a_review_issues_button(self):
        source = _source()
        assert 'id="wwDataQualityReviewBtn"' in source
        assert "Review Issues" in source

    def test_summary_derives_from_the_effective_issue_summary_never_a_second_validator(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataQualitySummary()", "function wwDataPrepRenderCellIssueGroupHtml(",
        )
        assert "wwDataPrepFlatCellIssueList()" in body
        assert "No unresolved data-cell issues" in body

    def test_flat_cell_issue_list_reads_wwdataprepeffectiveissuesummary(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepFlatCellIssueList()", "function wwDataPrepGroupCellIssues(",
        )
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "cell_issues" in body


class TestDataIssuesPanelExistsAndIsPersistentCollapsible:
    def test_panel_element_exists_as_an_aside(self):
        source = _source()
        assert '<aside class="ww-data-issues-panel" id="wwDataIssuesPanel"' in source

    def test_panel_has_a_data_open_attribute_for_persistent_collapsed_state(self):
        # Persistent means present-but-collapsed (data-open="false"),
        # never removed from the DOM/never display:none entirely (task
        # section 1: "collapsed state keeps a compact visible handle").
        source = _source()
        assert 'data-open="false"' in source
        assert '.ww-data-issues-panel[data-open="false"]' in source

    def test_panel_is_a_flex_sibling_on_desktop_never_position_fixed_by_default(self):
        source = _source()
        # The persistent desktop layout rule (identified by its own
        # unique flex-basis, no @media guard) must not itself use
        # position: fixed -- only the narrow-screen override (inside the
        # existing 820px breakpoint, found separately/earlier in the
        # file since it was merged into that existing block) does.
        idx = source.index("flex: 0 0 300px")
        rule_start = source.rindex(".ww-data-issues-panel {", 0, idx)
        rule_end = source.index("}", idx)
        desktop_rule = source[rule_start:rule_end]
        assert "position: fixed" not in desktop_rule
        assert "flex: 0 0 300px" in desktop_rule

    def test_narrow_screen_override_reuses_the_existing_data_prep_820px_breakpoint(self):
        # Reuses the SAME Data-Preparation-scoped 820px block
        # `.ww-data-prep-row-cols`'s own stacked-layout rule already
        # lives in -- never a new, duplicate breakpoint just for this
        # panel (other, unrelated pages in this file may have their own
        # independent 820px block; this only asserts THIS one is shared).
        source = _source()
        data_prep_media_start = source.index(".ww-data-prep-row-cols { grid-template-columns: 1fr; }")
        media_block_start = source.rindex("@media (max-width: 820px)", 0, data_prep_media_start)
        narrow_block_end = source.index("@media (max-width: 480px)", media_block_start)
        narrow_block = source[media_block_start:narrow_block_end]
        assert ".ww-data-issues-panel" in narrow_block
        assert "position: fixed" in narrow_block

    def test_toggle_button_has_aria_expanded(self):
        source = _source()
        assert 'id="wwDataIssuesPanelToggleBtn"' in source
        assert 'aria-expanded="false"' in source

    def test_toggle_function_updates_aria_expanded(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesPanel()", "function wwDataPrepRefreshCellIssueHighlighting()",
        )
        assert 'toggleBtn.setAttribute("aria-expanded"' in body

    def test_count_badge_exists(self):
        source = _source()
        assert 'id="wwDataIssuesPanelCount"' in source


class TestCoordinateRendering:
    def test_coordinate_buttons_are_rendered_as_real_buttons(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert '<button type="button" class="ww-data-issue-coordinate"' in body
        assert "data-issue-key=" in body

    def test_coordinate_text_uses_spreadsheet_column_label_and_row_number(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepCellCoordinateText(issue)", "function wwDataPrepColumnDisplayName(",
        )
        assert "wwSpreadsheetColumnLabel(issue.column_index)" in body
        assert "issue.row_number" in body

    def test_grouping_is_by_type_then_by_column(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepGroupCellIssues(cellIssues)", "function wwDataPrepRenderDataQualitySummary(",
        )
        assert "groups.invalid" in body
        assert "groups.missing" in body
        assert "byColumn" not in body or "column_index" in body

    def test_column_order_is_source_order_never_alphabetical(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert "sort((a, b) => a - b)" in body

    def test_large_groups_are_capped_with_a_load_more_control(self):
        source = _source()
        assert "WW_DATA_ISSUES_INITIAL_VISIBLE" in source
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert "ww-data-issues-load-more" in body
        assert "data-load-more-group=" in body


class TestUnresolvedCellHighlighting:
    def test_missing_and_invalid_get_distinct_classes(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "ww-data-prep-cell-issue-missing" in body
        assert "ww-data-prep-cell-issue-invalid" in body

    def test_highlighting_uses_border_and_background_not_color_alone(self):
        source = _source()
        assert "td.ww-data-prep-cell-issue-missing" in source
        assert "td.ww-data-prep-cell-issue-invalid" in source
        missing_idx = source.index("td.ww-data-prep-cell-issue-missing")
        missing_rule_end = source.index("}", missing_idx)
        missing_rule = source[missing_idx:missing_rule_end]
        assert "background" in missing_rule
        assert "box-shadow" in missing_rule or "border" in missing_rule

    def test_unresolved_cells_get_an_aria_label(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "not yet resolved" in body


class TestExplicitNullResolvedStyling:
    def test_explicit_null_cells_get_a_distinct_class_not_ordinary_blank(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "ww-data-prep-cell-explicit-null" in body
        assert "ww-data-prep-null-badge" in body

    def test_explicit_null_detection_reads_is_explicit_null_from_modified_cells(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "modified.is_explicit_null" in body

    def test_unresolved_takes_priority_over_explicit_null_for_the_time_axis_edge_case(self):
        # DEC-084: Time Axis explicit null stays BLOCKING (Slice 1) -- if
        # a cell is somehow both, the unresolved/blocking styling must
        # win, never the resolved-looking NULL badge (task section 11:
        # "the backend explicit-null kind remains authoritative").
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        issue_check_idx = body.index("if (issue) {")
        explicit_null_check_idx = body.index("explicitNullByKey.has(key)")
        assert issue_check_idx < explicit_null_check_idx

    def test_null_badge_renders_the_literal_text_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert 'badge.textContent = "NULL"' in body


class TestTimeAxisGuardrail:
    def test_time_axis_issue_never_renders_mark_as_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert 'issue.code.startsWith("time_value_")' in body
        assert "if (!isTimeAxis) html +=" in body
        assert 'data-issue-action="mark-null"' in body

    def test_time_axis_issue_offers_fill_manually_and_revisit_time_axis(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert 'data-issue-action="fill-manually"' in body
        assert 'data-issue-action="configure-time-axis"' in body

    def test_waveform_issue_does_expose_mark_as_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert 'data-issue-action="change-role"' in body


class TestActionsReuseExistingBehavior:
    def test_mark_as_null_sends_kind_null_never_a_value(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepMarkCellNull(rowNumber, columnIndex)", "document.getElementById(\"wwDataQualityReviewBtn\")",
        )
        assert '{ kind: "null" }' in body or "{\"kind\": \"null\"}" in body or "kind: \"null\"" in body
        assert '"value"' not in body

    def test_fill_manually_reuses_wwdataprepbegincelledit(self):
        source = _source()
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesActionArea").addEventListener', "// CSV/Excel ingestion Slice 10",
        )
        assert "wwDataPrepBeginCellEdit(cell)" in body

    def test_change_role_reuses_wwdataprepsetcolumnrole_with_not_assigned(self):
        source = _source()
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesActionArea").addEventListener', "// CSV/Excel ingestion Slice 10",
        )
        assert 'wwDataPrepSetColumnRole(columnIndex, "not_assigned")' in body


class TestNavigationKeepsThePanelOpen:
    def test_select_and_jump_sets_panel_open_true(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepSelectAndJumpToCellIssue(issue)", "function wwDataPrepSelectIssueByOffset(",
        )
        assert "wwDataPrep.dataIssuesPanelOpen = true;" in body

    def test_jump_uses_source_row_number_not_visible_table_index(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepJumpToSourceCell(rowNumber, columnIndex)", "async function wwDataPrepSelectAndJumpToCellIssue(",
        )
        assert "Math.floor((rowNumber - 1) / wwDataPrep.limit) * wwDataPrep.limit" in body
        assert "wwDataPrepFetchPreview()" in body

    def test_prev_next_navigation_uses_the_same_jump_behavior(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepSelectIssueByOffset(delta)", "async function wwDataPrepMarkCellNull(",
        )
        assert "wwDataPrepSelectAndJumpToCellIssue(list[nextIndex])" in body

    def test_prev_next_buttons_exist(self):
        source = _source()
        assert 'id="wwDataIssuesPrevBtn"' in source
        assert 'id="wwDataIssuesNextBtn"' in source
        assert 'id="wwDataIssuesNavPosition"' in source


class TestSelectionAdvancesWhenResolved:
    def test_render_panel_advances_selection_when_the_current_one_is_gone(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesPanel()", "function wwDataPrepRefreshCellIssueHighlighting()",
        )
        assert "selectedIndex === -1" in body
        assert "lastSelectedCellIssueOrdinal" in body


class TestReadinessAndUndoRedoIntegration:
    def test_data_quality_and_issues_panel_refresh_alongside_the_existing_issues_render(self):
        # task section 17: reuses wwDataPrepEffectiveIssueSummary()/the
        # existing wwDataPrepRenderIssues() refresh path -- never a new
        # call site wired into Undo/Redo/Reset All themselves (those
        # already end in wwDataPrepFetchPreview() -> wwDataPrepFetchIssues()
        # -> wwDataPrepRenderIssues(), which already re-renders the
        # existing coarse issues panel).
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderIssues()", "function wwDataPrepIsIndexOnlyWithoutInterval()",
        )
        assert "wwDataPrepRenderDataQualitySummary();" in body
        assert "wwDataPrepRenderDataIssuesPanel();" in body
        assert "wwDataPrepRefreshCellIssueHighlighting();" in body

    def test_no_second_undo_redo_stack_is_introduced(self):
        source = _source()
        # The new functions in this slice never touch an undo/redo/
        # history-like array of their own.
        for name in (
            "function wwDataPrepMarkCellNull",
            "function wwDataPrepSelectAndJumpToCellIssue",
            "function wwDataPrepJumpToSourceCell",
        ):
            start = source.index(name)
            end = source.index("\n        }", start)
            body = source[start:end]
            assert "History" not in body
            assert "undoStack" not in body and "redoStack" not in body


class TestSingleCellActionAreaStillUngrouped:
    # The per-cell action area (Selected: <coordinate> -- Mark as Null /
    # Fill Manually / Change Role) predates bulk resolution (Slice 4) and
    # stays scoped to exactly one cell even now that Slice 5 adds a
    # SEPARATE, column-issue-group-level bulk control elsewhere in the
    # same panel (see TestBulkNullControls below) -- the two never merge
    # into one "select many, act once" mechanism.
    def test_coordinate_list_items_are_not_checkboxes(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert 'type="checkbox"' not in body

    def test_single_cell_action_area_never_targets_a_whole_group_or_selection(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert "selected cells" not in body.lower()
        assert "all issues" not in body.lower()


class TestBulkNullControls:
    # DEC-084 (Slice 5): safe bulk explicit-null resolution -- one
    # button per bulk-eligible (column_index, issue_code) group, gated
    # to the two Waveform-only issue codes, with a confirmation dialog
    # that always re-fetches the authoritative count before the user can
    # confirm (task sections 3-9, 15-17).
    def test_eligible_codes_are_exactly_the_two_waveform_codes(self):
        source = _source()
        assert 'const WW_BULK_NULL_ELIGIBLE_CODES = new Set(["waveform_value_missing", "waveform_value_invalid"]);' in source

    def test_bulk_button_is_rendered_per_column_group_gated_by_eligibility(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert "WW_BULK_NULL_ELIGIBLE_CODES.has(issueCode)" in body
        assert "ww-data-issues-bulk-null-btn" in body
        assert "data-bulk-null-issue-code=" in body
        assert "data-bulk-null-column-index=" in body

    def test_bulk_button_count_comes_from_the_preview_endpoint_never_cell_issues_length(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepFetchBulkNullCount(issueCode, columnIndex)", "function wwDataPrepRenderCellIssueGroupHtml(",
        )
        assert "/working/cells/bulk-null/preview" in body
        assert "eligible_count" in body

    def test_confirmation_dialog_exists_with_required_wording(self):
        source = _source()
        assert 'id="wwDataIssuesBulkNullOverlay"' in source
        assert 'id="wwDataIssuesBulkNullConfirmBtn"' in source
        assert 'id="wwDataIssuesBulkNullCancelBtn"' in source

    def test_confirm_open_refetches_the_authoritative_count_fresh(self):
        # Task section 8/16: never trust the button's own already-shown
        # count for the actual confirmation text -- a fresh preview call
        # happens every time the dialog opens.
        source = _source()
        body = _function_body(
            source, "async function openWwDataIssuesBulkNullConfirm(columnIndex, issueCode)", "function closeWwDataIssuesBulkNullConfirm()",
        )
        assert "/working/cells/bulk-null/preview" in body
        assert "Other valid cells in the same rows will not be changed." in body

    def test_apply_uses_the_dedicated_apply_endpoint_and_reports_drift(self):
        # Task section 9: staleness between the confirmation's own preview
        # and the actual apply must be reported, never silently dropped.
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyBulkNull(columnIndex, issueCode, previewCount)", "document.getElementById(\"wwDataQualityReviewBtn\")",
        )
        assert "/working/cells/bulk-null/apply" in body
        assert "no longer eligible" in body

    def test_apply_reuses_the_existing_overlay_summary_path_no_new_undo_redo_stack(self):
        # Task section 10/19: one grouped backend operation, surfaced
        # through the SAME wwDataPrepApplyOverlaySummary()/Undo/Redo
        # buttons every other working-overlay mutation already uses --
        # no bulk-specific history array of its own.
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyBulkNull(columnIndex, issueCode, previewCount)", "document.getElementById(\"wwDataQualityReviewBtn\")",
        )
        assert "wwDataPrepApplyOverlaySummary(" in body
        assert "History" not in body
        assert "undoStack" not in body and "redoStack" not in body

    def test_time_axis_issue_group_never_gets_a_bulk_button(self):
        # Backend-and-frontend guardrail (task section 5): a Time Axis
        # column's own cell_issues carry `time_value_missing`/
        # `time_value_invalid` codes, neither of which is in
        # WW_BULK_NULL_ELIGIBLE_CODES, so the same gated branch that
        # renders the button for a Waveform group silently renders
        # nothing at all for a Time Axis one.
        source = _source()
        assert '"time_value_missing"' not in source.split("const WW_BULK_NULL_ELIGIBLE_CODES")[1].split(";")[0]
        assert '"time_value_invalid"' not in source.split("const WW_BULK_NULL_ELIGIBLE_CODES")[1].split(";")[0]


class TestDataIssuesStateIsOwnAndSeparateFromAnnotations:
    def test_state_fields_exist_on_wwdataprep(self):
        source = _source()
        assert "dataIssuesPanelOpen: false," in source
        assert "selectedCellIssueKey: null," in source
        assert "dataIssuesExpandedColumnGroups: new Set()," in source

    def test_state_reset_on_workspace_open(self):
        source = _source()
        body = _function_body(
            source, "async function openDataPreparationWorkspace(sourceId)",
            "wwDataPrepRenderIssues();\n            wwDataPrepRenderStructureSummary();",
        )
        assert "wwDataPrep.dataIssuesPanelOpen = false;" in body
        assert "wwDataPrep.selectedCellIssueKey = null;" in body

    def test_never_reads_or_writes_ww_annotations(self):
        source = _source()
        for name in (
            "function wwDataPrepRenderDataIssuesPanel",
            "function wwDataPrepRenderDataQualitySummary",
            "function wwDataPrepSelectAndJumpToCellIssue",
            "function wwDataPrepRefreshCellIssueHighlighting",
        ):
            start = source.index(name)
            end = source.index("\n        }", start)
            body = source[start:end]
            assert "ww.annotations" not in body
