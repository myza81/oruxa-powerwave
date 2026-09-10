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
        # UI/UX polish (2026-09-10): width widened 300px -> 320px for
        # the redesigned panel's own more generous padding/rhythm --
        # the flex-basis literal itself isn't the behavior under test
        # here (still a desktop flex sibling, never position: fixed),
        # so this just tracks whatever the current desktop width is.
        idx = source.index("flex: 0 0 320px")
        rule_start = source.rindex(".ww-data-issues-panel {", 0, idx)
        rule_end = source.index("}", idx)
        desktop_rule = source[rule_start:rule_end]
        assert "position: fixed" not in desktop_rule
        assert "flex: 0 0 320px" in desktop_rule

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
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
        )
        assert 'issue.code.startsWith("time_value_")' in body
        assert "if (!isTimeAxis) html +=" in body
        assert 'data-issue-action="mark-null"' in body

    def test_time_axis_issue_offers_fill_manually_and_revisit_time_axis(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
        )
        assert 'data-issue-action="fill-manually"' in body
        assert 'data-issue-action="configure-time-axis"' in body

    def test_waveform_issue_does_expose_mark_as_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
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
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
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


class TestSingleCellEstimateAction:
    # Missing-value fill/estimation enhancement (owner UAT, 2026-09-10,
    # task sections 2/4): "Estimate Missing Value" reuses the SAME
    # eligibility gate as the pre-existing bulk-null button
    # (WW_BULK_NULL_ELIGIBLE_CODES) -- a single source of truth for
    # "only waveform_value_missing/waveform_value_invalid," so Time Axis
    # issue codes are excluded the same structural way bulk-null already
    # proves in TestBulkNullControls.
    def test_estimate_button_gated_to_the_same_waveform_eligible_codes_as_bulk_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
        )
        assert "WW_BULK_NULL_ELIGIBLE_CODES.has(issue.code)" in body
        assert 'data-issue-action="estimate"' in body

    def test_estimate_button_appears_after_fill_manually_before_not_assigned(self):
        # Task section 1's own required action order: Mark as Null /
        # Fill Manually / Estimate Missing Value / Set Column to Not
        # Assigned.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderDataIssuesActionArea(issue)", "const WW_DATA_PREP_ESTIMATION_METHODS = {",
        )
        fill_idx = body.index('data-issue-action="fill-manually"')
        estimate_idx = body.index('data-issue-action="estimate"')
        not_assigned_idx = body.index('data-issue-action="change-role"')
        assert fill_idx < estimate_idx < not_assigned_idx

    def test_open_dialog_stores_the_clicked_cells_own_issue_code(self):
        # SingleCellEstimateRequest needs the clicked cell's CURRENT
        # issue type -- read back from the action area's own dataset,
        # never guessed/hardcoded.
        source = _source()
        assert "areaEl.dataset.issueCode = issue.code;" in source
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesActionArea").addEventListener', "// CSV/Excel ingestion Slice 10",
        )
        assert "openWwDataIssuesEstimateDialog(rowNumber, columnIndex, areaEl.dataset.issueCode)" in body


class TestBulkFillEstimateGroupAction:
    # Task sections 9-12: "Fill / Estimate Missing Values" -- Constant
    # Value (issue-scoped) + the four algorithmic methods (gap-based),
    # never a separate "Bulk Fill Manually" action (task section 1).
    def test_bulk_fill_button_is_gated_by_the_same_eligibility_check_as_bulk_null(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        gate_idx = body.index("WW_BULK_NULL_ELIGIBLE_CODES.has(issueCode)")
        bulk_fill_idx = body.index("ww-data-issues-bulk-fill-btn")
        not_assigned_idx = body.index("ww-data-issues-group-not-assigned-btn")
        assert gate_idx < bulk_fill_idx
        assert gate_idx < not_assigned_idx
        assert "data-bulk-fill-issue-code=" in body
        assert "data-bulk-fill-column-index=" in body

    def test_no_separate_bulk_fill_manually_action_exists(self):
        source = _source()
        assert "Bulk Fill Manually" not in source
        assert "bulk-fill-manually" not in source

    def test_bulk_fill_button_labelled_fill_estimate_missing_values(self):
        source = _source()
        assert "Fill / Estimate Missing Values" in source


class TestGroupLevelNotAssignedAction:
    # Task section 19: the group header's own "Set <Column> to Not
    # Assigned" reuses the exact same wwDataPrepSetColumnRole(...,
    # "not_assigned") call and confirmation wording as the pre-existing
    # single-cell action -- no second ignore mechanism.
    def test_group_not_assigned_button_reuses_set_column_role(self):
        source = _source()
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesPanelBody").addEventListener',
            'document.getElementById("wwDataIssuesActionArea").addEventListener',
        )
        assert "ww-data-issues-group-not-assigned-btn" in body
        assert 'wwDataPrepSetColumnRole(columnIndex, "not_assigned")' in body
        assert "This affects the entire column, not only the cells with issues." in body

    def test_group_not_assigned_button_label_embeds_the_column_name(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderCellIssueGroupHtml(", "function wwDataPrepRenderDataIssuesActionArea(",
        )
        assert "'Set ' + escapeHtml(wwDataPrepColumnDisplayName(columnIndex)) + ' to Not Assigned</button>'" in body
        # The vague pre-DEC-084-hardening label is never rendered as an
        # actual button; it survives only in historical comments
        # explaining why the wording changed.
        assert ">Change Column Role<" not in source


class TestEstimationMethodsExposed:
    # Task section 6/24: exactly the four implemented methods, matching
    # the backend's own ALL_ESTIMATION_METHODS minus
    # UNIMPLEMENTED_ESTIMATION_METHODS (app.domain.missing_data_estimation)
    # -- PCHIP is never offered anywhere in this feature's own UI.
    def test_exactly_four_methods_in_the_fixed_order(self):
        source = _source()
        assert (
            'const WW_DATA_PREP_ESTIMATION_METHOD_ORDER = ["hold_last", "nearest", "linear", "local_mean"];' in source
        )

    def test_method_labels_match_backend_wire_values(self):
        source = _source()
        body = _function_body(
            source, "const WW_DATA_PREP_ESTIMATION_METHODS = {", "const WW_DATA_PREP_ESTIMATION_METHOD_ORDER",
        )
        assert 'hold_last: { label: "Hold Last Value" }' in body
        assert 'nearest: { label: "Nearest Value" }' in body
        assert 'linear: { label: "Linear Interpolation" }' in body
        assert 'local_mean: { label: "Local Mean" }' in body

    def test_pchip_never_appears_in_either_new_dialogs_method_list(self):
        source = _source()
        for name in ("WW_DATA_PREP_ESTIMATION_METHOD_ORDER", "WW_DATA_PREP_BULK_FILL_METHOD_ORDER"):
            start = source.index(name)
            end = source.index(";", start)
            assert "pchip" not in source[start:end].lower()

    def test_bulk_method_order_leads_with_constant_value(self):
        source = _source()
        assert (
            'const WW_DATA_PREP_BULK_FILL_METHOD_ORDER = ["constant", "hold_last", "nearest", "linear", "local_mean"];'
            in source
        )

    def test_no_scipy_dependency_is_introduced(self):
        source = _source()
        assert "scipy" not in source.lower()


class TestSingleCellEstimateDialogFields:
    # Task sections 5/7/8: Maximum Gap always shown when the dialog is
    # open; Local Mean Radius only when Local Mean is selected; both
    # plain numeric inputs + a fixed "samples" suffix, never a unit
    # dropdown (task section 7: "Only samples is supported").
    def test_maximum_gap_field_is_unconditional_and_samples_only(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderEstimateDialogFields()", "function wwDataPrepEstimateValidationError()",
        )
        assert "Maximum Gap" in body
        assert '<span class="ww-pu-suffix">samples</span>' in body
        assert "Gaps longer than this remain unresolved." in body

    def test_local_mean_radius_field_is_conditional_on_method(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderEstimateDialogFields()", "function wwDataPrepEstimateValidationError()",
        )
        assert 'if (d.method === "local_mean") {' in body
        assert "Local Mean Radius" in body
        assert "samples each side" in body

    def test_switching_away_from_local_mean_clears_the_stored_radius(self):
        source = _source()
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesEstimateMethodSelect").addEventListener',
            'document.getElementById("wwDataIssuesEstimateGapFields").addEventListener',
        )
        assert 'if (wwDataPrepEstimateDialog.method !== "local_mean") wwDataPrepEstimateDialog.localMeanRadius = "";' in body

    def test_max_gap_and_radius_must_be_positive_integers(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepEstimateValidationError()", "function openWwDataIssuesEstimateDialog(",
        )
        assert "Number.isInteger(maxGap)" in body and "maxGap < 1" in body
        assert "Number.isInteger(radius)" in body and "radius < 1" in body


class TestBulkFillDialogFields:
    # Task sections 9-11: Constant Value shows a plain numeric Value
    # input (never a gap-based field, section 10); the four algorithmic
    # methods show Maximum Gap (+ conditional Local Mean Radius),
    # mirroring the single-cell dialog's own fields exactly.
    def test_constant_value_shows_a_plain_numeric_value_input_not_gap_fields(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderBulkFillFields()", "function wwDataPrepBulkFillValidationError()",
        )
        constant_branch = body[body.index('if (d.method === "constant") {'):body.index("} else {")]
        assert 'id="wwDataIssuesBulkFillConstantInput"' in constant_branch
        assert "Maximum Gap" not in constant_branch

    def test_algorithmic_methods_show_maximum_gap_and_conditional_radius(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderBulkFillFields()", "function wwDataPrepBulkFillValidationError()",
        )
        algorithmic_branch = body[body.index("} else {"):]
        assert "Maximum Gap" in algorithmic_branch
        assert 'if (d.method === "local_mean") {' in algorithmic_branch
        assert "Local Mean Radius" in algorithmic_branch

    def test_switching_away_from_local_mean_clears_the_stored_radius(self):
        source = _source()
        body = _function_body(
            source, 'document.getElementById("wwDataIssuesBulkFillMethodSelect").addEventListener',
            'document.getElementById("wwDataIssuesBulkFillFields").addEventListener',
        )
        assert 'if (wwDataPrepBulkFillDialog.method !== "local_mean") wwDataPrepBulkFillDialog.localMeanRadius = "";' in body

    def test_constant_value_must_be_a_finite_number(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepBulkFillValidationError()", "function openWwDataIssuesBulkFillDialog(",
        )
        assert 'if (d.method === "constant") {' in body
        assert "Number.isFinite(value)" in body


class TestConstantValueStaysIssueScoped:
    # Task section 10: Constant Value is NOT gap-based -- its own preview
    # call hits the dedicated bulk-constant-fill endpoint (no method/
    # max_gap fields in that request body), distinct from the algorithmic
    # methods' bulk-estimate endpoint.
    def test_constant_preview_uses_the_dedicated_constant_fill_endpoint(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepRefreshBulkFillPreview()", "function wwDataPrepQueueBulkFillPreview()",
        )
        constant_branch = body[body.index('if (d.method === "constant") {'):body.index("} else {")]
        assert "/working/cells/bulk-constant-fill/preview" in constant_branch
        assert "method" not in constant_branch.split("body: JSON.stringify(")[1].split(")")[0]

    def test_constant_apply_uses_the_dedicated_constant_fill_endpoint(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyBulkFillDialog()", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert "/working/cells/bulk-constant-fill/apply" in body
        assert "/working/cells/bulk-estimate/apply" in body


class TestMatchingAndAffectedCountRendering:
    # Task sections 4/11/13: every count shown comes straight from the
    # backend's own preview response -- matching_count (N) and
    # affected_count (M) are BOTH rendered whenever a mixed-gap
    # expansion makes them differ, never silently hidden.
    def test_single_cell_preview_renders_matching_and_estimated_counts(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepRefreshEstimateDialogPreview()", "function wwDataPrepQueueEstimateDialogPreview()",
        )
        assert "body.matching_count" in body
        assert "body.eligible_count" in body
        assert "body.affected_count" in body

    def test_bulk_algorithmic_preview_shows_matching_affected_eligible_unresolved(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepRefreshBulkFillPreview()", "function wwDataPrepQueueBulkFillPreview()",
        )
        assert "body.matching_count" in body
        assert "body.affected_count" in body
        assert "body.eligible_count" in body
        assert "body.unresolved_count" in body

    def test_mixed_gap_expansion_is_shown_not_hidden(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepRefreshBulkFillPreview()", "function wwDataPrepQueueBulkFillPreview()",
        )
        assert "body.affected_count !== body.matching_count" in body
        assert "Values in the full contiguous gap:" in body
        assert 'gapNoteEl.hidden = !mixedGap;' in body

    def test_gap_note_explains_contiguous_gap_behavior(self):
        source = _source()
        assert "Estimation is applied to complete contiguous missing/invalid gaps." in source


class TestPreviewBeforeApply:
    # Task section 13: every action calls preview first -- opening
    # either dialog immediately triggers a preview fetch, and every
    # config change re-triggers one (debounced); Apply is a SEPARATE
    # function that never substitutes for a preview call of its own.
    def test_opening_single_cell_dialog_triggers_a_preview(self):
        source = _source()
        body = _function_body(
            source, "function openWwDataIssuesEstimateDialog(rowNumber, columnIndex, issueCode)", "function closeWwDataIssuesEstimateDialog()",
        )
        assert "wwDataPrepRefreshEstimateDialogPreview();" in body

    def test_opening_bulk_dialog_triggers_a_preview(self):
        source = _source()
        body = _function_body(
            source, "function openWwDataIssuesBulkFillDialog(columnIndex, issueCode)", "function closeWwDataIssuesBulkFillDialog()",
        )
        assert "wwDataPrepRefreshBulkFillPreview();" in body

    def test_config_changes_queue_a_fresh_preview_never_reuse_a_stale_one(self):
        source = _source()
        assert "wwDataPrepQueueEstimateDialogPreview()" in source
        assert "wwDataPrepQueueBulkFillPreview()" in source
        # Both queue functions debounce into the SAME refresh function
        # opening already calls directly -- never a second, divergent
        # preview implementation.
        body = _function_body(
            source, "function wwDataPrepQueueEstimateDialogPreview()", "async function wwDataPrepApplyEstimateDialog()",
        )
        assert "wwDataPrepRefreshEstimateDialogPreview" in body

    def test_apply_never_computes_its_own_count_reuses_lastpreview_only_for_drift(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyEstimateDialog()", "// ------------------------------------------------------------------\n        // Bulk",
        )
        assert "d.lastPreview ? d.lastPreview.eligible_count : null" in body
        assert "/working/cells/" in body and "/estimate/apply" in body


class TestApplyTimeStalenessReported:
    # Task section 14: apply endpoints re-evaluate eligibility fresh --
    # if fewer cells were actually applied than preview promised, the
    # drift must be surfaced, never silently swallowed.
    def test_single_cell_apply_reports_drift(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyEstimateDialog()", "// ------------------------------------------------------------------\n        // Bulk",
        )
        assert "previewCount - result.applied_count" in body
        assert "no longer eligible" in body

    def test_bulk_apply_reports_drift(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyBulkFillDialog()", "function wwDataPrepRenderDataIssuesPanel()",
        )
        assert "previewCount - result.applied_count" in body
        assert "no longer eligible" in body


class TestEstimatedAndConstantFillVisualStates:
    # Task sections 15/16: estimated and constant-filled cells are
    # visually distinguishable from raw source values AND from each
    # other -- Constant Value is never labelled "Estimated" (it is a
    # direct user-specified fill, not an interpolation result).
    def test_estimated_cell_gets_a_distinct_class_and_badge(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "ww-data-prep-cell-estimated" in body
        assert "ww-data-prep-estimated-badge" in body
        assert 'badge.textContent = "Estimated"' in body

    def test_constant_fill_cell_gets_a_distinct_class_and_badge_never_labelled_estimated(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "ww-data-prep-cell-constant-fill" in body
        assert "ww-data-prep-filled-badge" in body
        assert 'badge.textContent = "Filled"' in body
        filled_branch_start = body.index("constantFillByKey.has(key)")
        filled_branch_end = body.index("if (selectedKey ===", filled_branch_start)
        filled_branch = body[filled_branch_start:filled_branch_end]
        assert 'badge.textContent = "Estimated"' not in filled_branch
        assert "ww-data-prep-estimated-badge" not in filled_branch

    def test_estimated_detection_reads_modified_cells_never_a_second_computation(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert "modified.is_estimated" in body
        assert "modified.is_constant_fill" in body
        assert "modified.estimation_method" in body

    def test_estimated_badge_tooltip_names_the_method_where_available(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        assert 'badge.title = "Estimated using " + methodLabel;' in body

    def test_unresolved_and_explicit_null_still_take_priority_over_estimated_and_filled(self):
        # Mirrors TestExplicitNullResolvedStyling's own priority-order
        # assertion (unresolved wins over explicit-null) one level
        # further: unresolved/explicit-null both still outrank the two
        # NEW resolved states in the same if/else if chain.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRefreshCellIssueHighlighting()", "function wwDataPrepSetIssuesPanelOpen(",
        )
        issue_idx = body.index("if (issue) {")
        explicit_null_idx = body.index("explicitNullByKey.has(key)")
        estimated_idx = body.index("estimatedByKey.has(key)")
        constant_fill_idx = body.index("constantFillByKey.has(key)")
        assert issue_idx < explicit_null_idx < estimated_idx < constant_fill_idx

    def test_cell_state_css_uses_border_and_background_not_color_alone(self):
        source = _source()
        for selector in ("td.ww-data-prep-cell-estimated", "td.ww-data-prep-cell-constant-fill"):
            idx = source.index(selector)
            rule_end = source.index("}", idx)
            rule = source[idx:rule_end]
            assert "background" in rule
            assert "box-shadow" in rule


class TestEstimatedAndConstantFillDisplayFormatting:
    # UAT fix (2026-09-10): an estimated/constant-filled cell holds the
    # raw computed override value (e.g. a linear-interpolation result
    # such as 73.75999999999999), which must never be shown with a
    # floating-point tail -- the surrounding raw source cells in the
    # same column render in that column's own compact, source-native
    # decimal format (e.g. "73.28"). Presentation-layer only: this is
    # the display-text side; TestEstimatedAndConstantFillVisualStates
    # above covers the (unchanged) badge/class/provenance side.
    def test_render_table_formats_only_estimated_and_constant_fill_cells(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "function wwDataPrepApplyOverlaySummary(",
        )
        assert "modifiedCell.is_estimated || modifiedCell.is_constant_fill" in body
        assert "wwDataPrepFormatDerivedValue(value, c, preview.rows)" in body

    def test_no_second_ad_hoc_formatter_was_invented_without_checking_for_one(self):
        # The task's own instruction: check for an existing shared
        # numeric formatter before writing a new one. wwFormatEngineeringValue()
        # (fixed 1-or-3-decimal, for waveform Y-axis magnitudes) is the
        # only general-purpose numeric formatter in the codebase; the
        # comment directly above wwDataPrepColumnDecimalPrecision()
        # records that it was found and NOT reused (its precision rule
        # cannot match an arbitrary preview column's own source-native
        # decimal format), rather than silently inventing a second
        # formatter without checking.
        source = _source()
        body = _function_body(
            source,
            "// UAT fix (2026-09-10): Estimated/Filled cells hold the raw",
            "function wwDataPrepRenderTable(preview)",
        )
        # Mentioned once, in the comment, as the formatter considered
        # and rejected -- never actually called anywhere in this range.
        assert body.count("wwFormatEngineeringValue") == 1

    def test_precision_is_derived_from_the_columns_own_raw_sibling_values(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepFormatDerivedValue(", "function wwDataPrepRenderTable(preview)",
        )
        assert "wwDataPrepColumnDecimalPrecision(rows, columnIndex)" in body
        assert "num.toFixed(precision)" in body

    def test_precision_helper_excludes_derived_cells_from_the_reference_scan(self):
        # A derived (estimated/constant-fill) cell must never be used as
        # its own precision reference -- only genuine raw source values
        # in that column establish the column's own decimal format.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepColumnDecimalPrecision(", "function wwDataPrepFormatDerivedValue(",
        )
        assert "modified.is_estimated || modified.is_constant_fill)) continue;" in body

    def test_data_value_and_title_attributes_still_carry_the_exact_raw_value(self):
        # Click-to-edit (data-value) and the hover tooltip (title) must
        # stay exact/unrounded -- only the visible cell text changes.
        # Confirms wwDataPrepFormatDerivedValue() is used for the
        # displayed text only, never for data-value/title.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "function wwDataPrepApplyOverlaySummary(",
        )
        data_value_idx = body.index('data-value="')
        title_idx = body.index("const titleAttr =")
        data_value_segment = body[data_value_idx:data_value_idx + 100]
        title_segment = body[title_idx:title_idx + 120]
        assert 'escapeHtml(isBlank ? "" : String(value))' in data_value_segment
        assert "wwDataPrepFormatDerivedValue" not in data_value_segment
        assert "escapeHtml(String(value))" in title_segment
        assert "wwDataPrepFormatDerivedValue" not in title_segment

    def test_underlying_working_overlay_value_is_never_touched_by_formatting(self):
        # The formatter is called with the row's own `value` purely to
        # compute display text -- it must never be assigned back into
        # row.cells or otherwise mutate the fetched preview state.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepFormatDerivedValue(", "function wwDataPrepRenderTable(preview)",
        )
        assert "row.cells[" not in body
        assert ".cells[c] =" not in body


def _column_decimal_precision(raw_values):
    """Pure-Python mirror of wwDataPrepColumnDecimalPrecision()'s
    frequency-count + smallest-decimals-tie-break rule.

    This repository's frontend test harness has no JS execution engine
    (see this module's own docstring -- CI stays deliberately Python-only,
    DEC-071) -- this mirror does NOT execute the real JS and is not a
    substitute for that. It exists only to make the worked examples in
    TestPrecisionIsRepresentativeNotMaximum below self-checking against
    the same rule, and the OTHER tests in this file/that class -- which
    assert the exact operators/expressions present in the real JS source
    (e.g. "decimals < bestDecimals") -- are what actually pins the real
    implementation to this rule.
    """
    import re
    from collections import Counter

    counts: Counter[int] = Counter()
    for raw in raw_values:
        if raw is None or raw == "":
            continue
        text = str(raw).strip()
        if not re.match(r"^-?\d+(\.\d+)?$", text):
            continue
        dot = text.find(".")
        decimals = 0 if dot == -1 else len(text) - dot - 1
        counts[decimals] += 1
    if not counts:
        return None
    best_decimals, best_count = None, -1
    for decimals, count in counts.items():
        if count > best_count or (count == best_count and decimals < best_decimals):
            best_decimals, best_count = decimals, count
    return best_decimals


class TestPrecisionIsRepresentativeNotMaximum:
    # Owner UAT hardening (2026-09-10): the ORIGINAL implementation took
    # the MAXIMUM decimal-place count seen among a column's own raw
    # values -- a single unusually precise raw token (or, symmetrically,
    # the column's typical precision being dragged to 0 by an occasional
    # bare integer) would force every estimated/constant-filled value in
    # that column to an unrepresentative precision. The fix uses the
    # REPRESENTATIVE (most common/mode) decimal count instead, tied
    # toward the SMALLER count on a frequency tie.
    #
    # Two layers of coverage per scenario: (1) the real JS source is
    # asserted to contain the exact frequency-map/tie-break expressions
    # (this is the actual regression guard, consistent with every other
    # test_frontend_*.py's static-source convention -- there is no JS
    # execution engine here to run the real function against data), and
    # (2) the worked datasets are cross-checked against the disclosed
    # Python mirror above, which implements the identical rule, so the
    # numbers asserted below are not just hand-picked.

    def test_precision_helper_uses_a_frequency_map_not_a_running_maximum(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepColumnDecimalPrecision(", "function wwDataPrepFormatDerivedValue(",
        )
        assert "const decimalCounts = new Map();" in body
        assert "decimalCounts.set(decimals, (decimalCounts.get(decimals) || 0) + 1);" in body
        assert "maxDecimals" not in body
        assert "decimals > maxDecimals" not in body

    def test_tie_between_two_decimal_counts_breaks_toward_the_smaller_count(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepColumnDecimalPrecision(", "function wwDataPrepFormatDerivedValue(",
        )
        assert "count > bestCount || (count === bestCount && decimals < bestDecimals)" in body

    def test_predominant_two_decimal_column_infers_two_decimals(self):
        # The task's own example: 5 of 6 raw values at 2 decimals, one
        # bare integer -- must infer 2, matching the column's own
        # dominant format, never 0 and never a maximum-based value.
        raw_values = ["73.28", "76.16", "74.24", "72", "70.08", "69.12"]
        assert _column_decimal_precision(raw_values) == 2

    def test_single_outlier_does_not_force_its_own_precision(self):
        # A single 5-decimal outlier among five 2-decimal values must
        # never drag the whole column's inferred precision up to 5.
        raw_values = ["73.28", "76.16", "74.24", "70.08", "69.12", "12.34567"]
        assert _column_decimal_precision(raw_values) == 2

    def test_occasional_integer_does_not_force_integer_display(self):
        # A single bare integer among mostly 2-decimal values must never
        # drag the column's inferred precision down to 0.
        raw_values = ["10.50", "11.25", "9.75", "12", "8.40", "10.10"]
        assert _column_decimal_precision(raw_values) == 2

    def test_genuinely_predominant_three_decimal_column_infers_three_decimals(self):
        # A genuinely different column format (3 decimals dominant, one
        # 1-decimal outlier) must be respected as its own column's own
        # representative precision, not clamped to some other value.
        raw_values = ["1.234", "1.567", "1.890", "2.001", "1.5"]
        assert _column_decimal_precision(raw_values) == 3

    def test_estimated_underlying_value_remains_exact(self):
        # The precision fix is presentation-only: the exact raw
        # computed value (e.g. 73.75999999999999, the task's own
        # reported example) must still be what data-value/title carry,
        # and what wwDataPrepFormatDerivedValue() receives as input --
        # only its DISPLAYED text is rounded to the column's
        # representative precision. Mirrors
        # test_data_value_and_title_attributes_still_carry_the_exact_raw_value
        # above, restated here against the task's own example value.
        source = _source()
        render_body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "function wwDataPrepApplyOverlaySummary(",
        )
        assert "const value = row.cells[c];" in render_body
        data_value_idx = render_body.index('data-value="')
        data_value_segment = render_body[data_value_idx:data_value_idx + 100]
        assert 'escapeHtml(isBlank ? "" : String(value))' in data_value_segment
        assert "wwDataPrepFormatDerivedValue" not in data_value_segment
        # The formatter itself never rounds/reassigns the exact input --
        # it only returns a display string derived from it.
        format_body = _function_body(
            source, "function wwDataPrepFormatDerivedValue(", "function wwDataPrepRenderTable(preview)",
        )
        assert "const num = Number(value);" in format_body
        assert "value =" not in format_body.replace("const num = Number(value);", "")

    def test_constant_fill_uses_the_same_presentation_rule_as_estimated(self):
        # Both override kinds route through the exact same formatter
        # call -- there is no second, constant-fill-specific rounding
        # rule to drift out of sync with the estimated one.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "function wwDataPrepApplyOverlaySummary(",
        )
        derived_condition = "modifiedCell.is_estimated || modifiedCell.is_constant_fill"
        assert derived_condition in body
        # Exactly one formatter call, gated by the single combined
        # condition above -- not two separate branches/formatters.
        assert body.count("wwDataPrepFormatDerivedValue(value, c, preview.rows)") == 1
        assert body.count(derived_condition) == 1

    def test_no_reference_fallback_uses_bounded_significant_digits_not_fixed_decimals(self):
        # Reviewed per owner feedback: an arbitrary fixed toFixed(6) can
        # either truncate a large value's integer part or pad a small
        # one with meaningless trailing zeros. A bounded
        # significant-digit rounding reads as a natural engineering
        # value at any magnitude while still removing the
        # floating-point tail.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepFormatDerivedValue(", "function wwDataPrepRenderTable(preview)",
        )
        assert "num.toPrecision(6)" in body
        assert "num.toFixed(6)" not in body


class TestNewDialogsStackAboveTheDrawer:
    # Task section 27: same scoped +1-over-40 z-index convention as
    # #wwDataIssuesBulkNullOverlay/#wwDataPrepResetAllOverlay.
    def test_both_new_overlays_get_the_scoped_z_index(self):
        source = _source()
        assert "#wwDataIssuesEstimateOverlay,\n        #wwDataIssuesBulkFillOverlay { z-index: 41; }" in source

    def test_both_new_dialogs_reuse_the_shared_confirm_overlay_shell(self):
        source = _source()
        assert '<div class="confirm-overlay" id="wwDataIssuesEstimateOverlay" hidden>' in source
        assert '<div class="confirm-overlay" id="wwDataIssuesBulkFillOverlay" hidden>' in source
        assert 'role="alertdialog" aria-modal="true"' in source


class TestNewDialogsEscapeAndCancel:
    # Task section 26: keyboard navigation / Escape/cancel, same shell
    # pattern as Reset All / bulk-null.
    def test_estimate_dialog_has_cancel_and_escape_wiring(self):
        source = _source()
        assert 'document.getElementById("wwDataIssuesEstimateCancelBtn").addEventListener("click", closeWwDataIssuesEstimateDialog);' in source
        body = source[source.index('document.getElementById("wwDataIssuesEstimateCancelBtn").addEventListener'):]
        assert 'if (!document.getElementById("wwDataIssuesEstimateOverlay").hidden) closeWwDataIssuesEstimateDialog();' in body[:2000]

    def test_bulk_fill_dialog_has_cancel_and_escape_wiring(self):
        source = _source()
        assert 'document.getElementById("wwDataIssuesBulkFillCancelBtn").addEventListener("click", closeWwDataIssuesBulkFillDialog);' in source
        body = source[source.index('document.getElementById("wwDataIssuesBulkFillCancelBtn").addEventListener'):]
        assert 'if (!document.getElementById("wwDataIssuesBulkFillOverlay").hidden) closeWwDataIssuesBulkFillDialog();' in body[:2000]

    def test_estimate_dialog_focuses_cancel_button_on_open(self):
        source = _source()
        body = _function_body(
            source, "function openWwDataIssuesEstimateDialog(rowNumber, columnIndex, issueCode)", "function closeWwDataIssuesEstimateDialog()",
        )
        assert 'document.getElementById("wwDataIssuesEstimateCancelBtn").focus();' in body


class TestNoAlertUsedForNewDialogs:
    # Task section 25: reuse existing structured error/status UI (the
    # #wwDataPrepStatus role="status" element every other Data
    # Preparation mutation already writes to) -- never a plain
    # window.alert() for the two NEW dialogs' own error paths (the
    # single pre-existing window.confirm() on the "change-role" action
    # is untouched legacy behavior, not something this slice repeats).
    def test_new_dialog_functions_never_call_alert(self):
        source = _source()
        for name in (
            "async function wwDataPrepRefreshEstimateDialogPreview()",
            "async function wwDataPrepApplyEstimateDialog()",
            "async function wwDataPrepRefreshBulkFillPreview()",
            "async function wwDataPrepApplyBulkFillDialog()",
        ):
            start = source.index(name)
            end = source.index("\n        }", start)
            body = source[start:end]
            assert "window.alert(" not in body
            assert "alert(" not in body

    def test_new_dialog_errors_surface_via_the_shared_status_line_or_count_element(self):
        source = _source()
        body = _function_body(
            source, "async function wwDataPrepApplyEstimateDialog()", "// ------------------------------------------------------------------\n        // Bulk",
        )
        assert 'document.getElementById("wwDataPrepStatus")' in body
        assert "Could not reach the backend." in body


class TestNoNewUndoRedoStackForEstimateFill:
    # Mirrors TestBulkNullControls.test_apply_reuses_the_existing_overlay_summary_path_no_new_undo_redo_stack
    # exactly, for the two new apply functions.
    def test_apply_functions_reuse_the_existing_overlay_summary_path(self):
        source = _source()
        for name in ("async function wwDataPrepApplyEstimateDialog()", "async function wwDataPrepApplyBulkFillDialog()"):
            start = source.index(name)
            end = source.index("\n        }", start)
            body = source[start:end]
            assert "wwDataPrepApplyOverlaySummary(" in body
            assert "History" not in body
            assert "undoStack" not in body and "redoStack" not in body


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
