"""Structural checks for the Data Preparation page visual/layout
redesign (owner-approved mock target, 2026-09-06) and its subsequent
layout-architecture revisions (4-row pass, approved 5-row pass, 6-row
experiment, then the approved 7-row layout, all 2026-09-06).

Purely presentational: every element/function this workspace already
used is asserted to still exist (same id, same JS function), just
relocated into the current row/grid layout -- no preparation
semantics, readiness rules, Time Axis behavior, or API shape is
expected to have changed by any of these layout tasks, and this module
does not re-test any of that (see test_frontend_time_axis_draft_vs_applied.py/
test_frontend_time_axis_advanced_options.py/
test_frontend_recording_time_identity.py for that coverage, unaffected
by this task).

Same static source-text convention every other test_frontend_*.py file
in this suite uses -- no JS execution engine is part of this repo's
test harness.
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


class TestRowFiveMainConfiguration:
    """Approved 7-row layout (2026-09-06): Row 5 is now the main
    configuration workspace at the owner-requested 1:3:1 ratio:
    Header & Data Region | Column Roles | Time Axis Setup. Worksheet
    selection and Issues/Readiness both have their own rows."""

    def test_row_5_is_the_main_configuration_grid(self):
        source = _source()
        assert 'class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"' in source

    def test_row_5_contains_header_roles_and_time_axis_only(self):
        source = _source()
        row5_start = source.index('class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"')
        row5_end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        row5_body = source[row5_start:row5_end]
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-region"' in row5_body
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-wide"' in row5_body
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-time"' in row5_body
        assert "Header &amp; Data Region" in row5_body
        assert 'id="wwDataPrepColumnsTable"' in row5_body
        assert 'id="wwDataPrepTimeAxisPanel"' in row5_body
        assert 'id="wwDataPrepWorksheetCard"' not in row5_body
        assert 'id="wwDataPrepIssuesCard"' not in row5_body

    def test_worksheet_has_its_own_row_4_before_main_configuration(self):
        source = _source()
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4"')
        row5_start = source.index('class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"')
        row4_body = source[row4_start:row5_start]
        assert 'id="wwDataPrepWorksheetCard"' in row4_body
        assert 'id="wwDataPrepWorksheetSelect"' in row4_body
        assert 'id="wwDataPrepWorksheetTabs"' in row4_body
        assert "Header &amp; Data Region" not in row4_body

    def test_worksheet_tabs_are_a_presentation_layer_over_the_existing_selector(self):
        source = _source()
        render_body = _function_body(source, "function wwDataPrepRenderWorksheetSelector()", "function wwDataPrepRenderTable")
        assert 'const tabs = document.getElementById("wwDataPrepWorksheetTabs");' in render_body
        assert 'class="ww-data-prep-worksheet-tab"' in render_body
        assert 'role="tab"' in render_body
        assert 'aria-selected="' in render_body

        click_body = _function_body(
            source,
            'document.getElementById("wwDataPrepWorksheetTabs").addEventListener("click"',
            'document.getElementById("wwDataPrepBackBtn").addEventListener("click"',
        )
        assert 'const select = document.getElementById("wwDataPrepWorksheetSelect");' in click_body
        assert "select.value = tab.dataset.worksheetIndex;" in click_body
        assert 'select.dispatchEvent(new Event("change", { bubbles: true }));' in click_body

    def test_column_roles_card_exists_in_the_wide_middle_column(self):
        source = _source()
        wide_col_start = source.index('class="ww-data-prep-config-col ww-data-prep-config-col-wide"')
        row5_end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        assert wide_col_start < source.index("<h3>Column Roles ") < row5_end
        assert 'id="wwDataPrepColumnsTable"' in source[wide_col_start:row5_end]

    def test_row_5_grid_ratio_is_1_3_1(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-row-5-grid {", "}")
        assert "display: grid" in body
        assert "minmax(0, 1fr) minmax(0, 3fr) minmax(0, 1fr)" in body
        assert 'grid-template-areas: "region roles time";' in body

    def test_row_5_keeps_1_3_1_until_mobile_stack(self):
        source = _source()
        media_1180 = _function_body(source, "@media (max-width: 1180px) {", "@media (max-width: 820px) {")
        assert ".ww-data-prep-row-5-grid" not in media_1180
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert ".ww-data-prep-row-5-grid" in media_820
        assert "grid-template-columns: 1fr;" in media_820
        assert 'grid-template-areas:' in media_820
        assert '"region"' in media_820
        assert '"roles"' in media_820
        assert '"time"' in media_820
        assert '"region time"' not in source
        assert '"roles roles"' not in source

    def test_phone_widths_keep_first_role_dropdown_reachable(self):
        source = _source()
        media_480 = _function_body(source, "@media (max-width: 480px) {", "/* Header row:")
        assert "td.ww-data-prep-label-cell { min-width: 112px; }" in media_480
        assert ".ww-data-prep-role-select { min-width: 104px; }" in media_480
        assert ".ww-data-prep-engineering-quantity-select { min-width: 120px; }" in media_480


class TestRowTwoIssuesReadiness:
    """Approved 7-row layout (2026-09-06): Issues/Readiness is now its
    own Row 2, collapsed by default with the existing status summary
    always visible and the detailed issue groups revealed by the
    existing toggle."""

    def test_row_2_is_issues_and_readiness(self):
        source = _source()
        assert 'class="ww-data-prep-row ww-data-prep-row-2"' in source
        row2_start = source.index('class="ww-data-prep-row ww-data-prep-row-2"')
        row3_start = source.index('class="ww-data-prep-row ww-data-prep-row-3 ww-data-prep-workflow-strip"', row2_start)
        row2_body = source[row2_start:row3_start]
        assert 'id="wwDataPrepIssuesCard"' in row2_body
        assert 'id="wwDataPrepIssueStatus"' in row2_body
        assert 'id="wwDataPrepIssueGroups" hidden' in row2_body
        assert 'id="wwDataPrepTimeAxisPanel"' not in row2_body
        assert 'id="wwDataPrepConversionAction"' not in row2_body

    def test_issues_card_exists_exactly_once_and_no_longer_hosts_the_conversion_action(self):
        source = _source()
        issues_card_start = source.index('id="wwDataPrepIssuesCard"')
        issues_card_end = source.index("</section>", issues_card_start)
        issues_card_body = source[issues_card_start:issues_card_end]
        assert 'id="wwDataPrepConvertBtn"' not in issues_card_body
        assert 'id="wwDataPrepExportBtn"' not in issues_card_body
        assert 'id="wwDataPrepIssueHeadline"' in issues_card_body
        assert 'id="wwDataPrepIssueCounts"' in issues_card_body
        assert 'id="wwDataPrepIssueGroups"' in issues_card_body


class TestRowTwoIssuesReadinessRedesign:
    """Row 2 refinement (2026-09-06): Issues/Readiness gets the SAME
    unified status card (icon + strong headline + one compact detail
    line, subtle background wash) Time Axis Setup's own status card
    already established -- presentation only,
    the exact same wwDataPrepEffectiveIssueSummary()/is_ready/counts the
    old pill-badge layout already read, never a second readiness
    computation."""

    def _issues_card_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepIssuesCard"')
        end = source.index("</section>", start)
        return source[start:end]

    def test_card_title_is_issues_and_readiness(self):
        source = _source()
        body = self._issues_card_body(source)
        assert "<h3>Issues &amp; Readiness</h3>" in body

    def test_old_subtitle_paragraph_is_gone(self):
        source = _source()
        body = self._issues_card_body(source)
        assert "Reports whether the current preparation is ready to convert" not in body

    def test_status_card_wraps_headline_and_counts_with_an_icon(self):
        source = _source()
        body = self._issues_card_body(source)
        status_start = body.index('id="wwDataPrepIssueStatus"')
        status_end = body.index("</div>", body.index('id="wwDataPrepIssueCounts"'))
        status_body = body[status_start:status_end]
        assert 'id="wwDataPrepIssueStatusIcon"' in status_body
        assert 'id="wwDataPrepIssueHeadline"' in status_body
        assert 'id="wwDataPrepIssueCounts"' in status_body

    def test_status_card_reuses_the_same_wash_technique_as_time_axis_setup(self):
        source = _source()
        assert '.ww-data-prep-issue-status[data-state="valid"] .ww-data-prep-issue-status-mark { background: var(--ok-wash); color: var(--ok); }' in source
        assert (
            '.ww-data-prep-issue-status[data-state="attention"] .ww-data-prep-issue-status-mark { background: color-mix(in srgb, var(--warn) 14%, transparent); color: var(--warn); }'
            in source
        )

    def test_pill_badge_system_is_removed(self):
        source = _source()
        assert "ww-data-prep-count-badge" not in source

    def test_headline_wording_matches_the_approved_copy(self):
        source = _source()
        assert 'headlineEl.textContent = summary.is_ready ? "Ready to convert" : "Needs attention";' in source

    def test_counts_are_one_joined_compact_line_not_a_second_no_issues_text(self):
        source = _source()
        body = _function_body(source, "function wwDataPrepRenderIssues() {", "function wwDataPrepIsIndexOnlyWithoutInterval")
        assert 'countsEl.textContent = countParts.length ? countParts.join(" · ") : "No blocking issues remain.";' in body
        # The old generic "No issues found." fallback paragraph in the
        # groups list is gone -- the status card above already says so.
        assert "No issues found." not in body

    def test_issue_rows_carry_a_severity_icon(self):
        source = _source()
        body = _function_body(source, "function wwDataPrepRenderIssues() {", "function wwDataPrepIsIndexOnlyWithoutInterval")
        assert "ww-data-prep-issue-item-icon" in body

    def test_view_issues_toggle_and_groups_expand_state_are_collapsed_by_default(self):
        source = _source()
        assert 'class="secondary ww-data-prep-issues-chevron-btn" id="wwDataPrepIssuesToggleBtn"' in source
        assert 'class="secondary ww-data-prep-visually-removed" id="wwDataPrepIssuesToggleBtn"' not in source
        assert "issuesExpanded: false," in source
        assert "wwDataPrep.issuesExpanded = false;" in source
        assert 'id="wwDataPrepIssueGroups" hidden' in source
        assert "wwDataPrep.issuesExpanded ? \"Hide Issues\" : \"View Issues\"" in source
        assert 'toggleBtn.setAttribute("aria-expanded", wwDataPrep.issuesExpanded ? "true" : "false");' in source

    def test_issues_toggle_hidden_attribute_still_wins_over_button_display_rule(self):
        source = _source()
        assert "#wwDataPrepIssuesToggleBtn[hidden] { display: none; }" in source

    def test_old_full_width_action_bar_class_is_retired(self):
        source = _source()
        assert 'class="ww-data-prep-action-bar"' not in source


class TestIssueListSimplification:
    """Issue-list simplification (2026-09-06): each issue row is now
    exactly icon + issue statement + muted suggested action -- the old
    "Go to worksheet"/"Go to row" links (and their now-dead navigation
    helpers/click listener) are removed outright, with no replacement
    navigation control. Grouping (BLOCKING/WARNING/INFO), which issues
    fall into which group, and every count/readiness computation are
    completely unchanged -- presentation only."""

    def test_goto_links_and_their_dead_code_are_fully_removed(self):
        source = _source()
        assert ">Go to worksheet<" not in source
        assert ">Go to row<" not in source
        assert "ww-data-prep-issue-goto-btn" not in source
        assert "function wwDataPrepGoToIssueWorksheet(" not in source
        assert "function wwDataPrepGoToIssueRow(" not in source

    def test_issue_row_is_icon_plus_message_plus_action(self):
        source = _source()
        body = _function_body(source, "function wwDataPrepRenderIssues() {", "function wwDataPrepIsIndexOnlyWithoutInterval")
        assert "ww-data-prep-issue-item-icon" in body
        assert "ww-data-prep-issue-item-message" in body
        assert "ww-data-prep-issue-item-action" in body
        # The suggested action is still the SAME field, just a
        # dedicated element instead of a trailing ` — text` span.
        assert "issue.suggested_action" in body

    def test_message_is_visually_stronger_than_the_muted_action(self):
        source = _source()
        message_rule = _function_body(source, ".ww-data-prep-issue-item-message {", "}")
        action_rule = _function_body(source, ".ww-data-prep-issue-item-action {", "}")
        assert "font-weight: 600" in message_rule
        assert "color: var(--text-dim)" in action_rule
        # Explicitly not italic -- the shared .hint class this used to
        # reuse is italic by default; task's own "avoid excessive
        # italics" rule.
        assert "font-style: normal" in action_rule

    def test_severity_grouping_and_labels_are_unchanged(self):
        source = _source()
        assert 'WW_DATA_PREP_SEVERITY_LABELS = { blocking: "Blocking", warning: "Warnings", info: "Info" };' in source
        body = _function_body(source, "function wwDataPrepRenderIssues() {", "function wwDataPrepIsIndexOnlyWithoutInterval")
        assert 'for (const severity of ["blocking", "warning", "info"])' in body

    def test_icon_column_has_a_consistent_fixed_width(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-issue-item-icon {", "}")
        assert "flex: 0 0 16px" in rule


class TestRowSevenFinalActions:
    """Approved 7-row layout (2026-09-06): Final Actions now lives
    alone on Row 7 -- the SAME Export/Proceed elements, re-parented
    only, capped to a compact content width rather than stretched
    full-bleed."""

    def test_row_7_exists_and_holds_only_final_actions(self):
        source = _source()
        assert 'class="ww-data-prep-row ww-data-prep-row-7"' in source
        row7_start = source.index('class="ww-data-prep-row ww-data-prep-row-7"')
        row7_end = source.index("<!-- /ww-data-prep-row-7 -->")
        row7_body = source[row7_start:row7_end]
        assert 'class="ww-data-prep-config-col ww-data-prep-final-actions"' in row7_body
        assert 'id="wwDataPrepIssuesCard"' not in row7_body

    def test_final_actions_slot_holds_export_and_convert(self):
        source = _source()
        final_actions_start = source.index('class="ww-data-prep-config-col ww-data-prep-final-actions"')
        final_actions_end = source.index("<!-- /ww-data-prep-row-7 -->", final_actions_start)
        final_actions_body = source[final_actions_start:final_actions_end]
        assert 'id="wwDataPrepExportBtn"' in final_actions_body
        assert 'id="wwDataPrepConvertBtn"' in final_actions_body
        assert "Proceed to Powerwave" in final_actions_body

    def test_only_one_convert_button_and_one_export_button_exist(self):
        source = _source()
        assert source.count('id="wwDataPrepConvertBtn"') == 1
        assert source.count('id="wwDataPrepExportBtn"') == 1

    def test_reset_all_changes_is_not_in_row_7(self):
        source = _source()
        row7_start = source.index('class="ww-data-prep-row ww-data-prep-row-7"')
        row7_end = source.index("<!-- /ww-data-prep-row-7 -->", row7_start)
        assert 'id="wwDataPrepResetAllBtn"' not in source[row7_start:row7_end]

    def test_final_actions_has_a_compact_max_width_not_full_bleed(self):
        # `.ww-data-prep-action-bar-primary`'s own `align-items: stretch`
        # would otherwise stretch "Proceed to Powerwave" across the
        # entire page now that this card is alone on a full-width row.
        source = _source()
        body = _function_body(source, ".ww-data-prep-final-actions {", "}")
        assert "justify-content: flex-end" in body
        assert "width: auto" in body

    def test_old_full_width_action_bar_class_is_retired(self):
        source = _source()
        assert 'class="ww-data-prep-action-bar"' not in source


class TestRowSixDataPreviewKeepsResetAllChanges:
    """Row 6 Data Preview is unchanged by this task -- Reset All Changes
    explicitly stays here, per the original task's own explicit rule,
    contextually tied to the table/toolbar it clears."""

    def test_data_preview_is_full_width_row_6(self):
        source = _source()
        assert (
            'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-preview-card ww-data-prep-row ww-data-prep-row-6"'
            in source
        )

    def test_reset_all_changes_is_inside_row_6(self):
        source = _source()
        row6_start = source.index(
            'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-preview-card ww-data-prep-row ww-data-prep-row-6"'
        )
        row7_start = source.index('class="ww-data-prep-row ww-data-prep-row-7"')
        row6_body = source[row6_start:row7_start]
        assert 'id="wwDataPrepResetAllBtn"' in row6_body
        assert 'id="wwDataPrepUndoBtn"' in row6_body
        assert 'id="wwDataPrepRedoBtn"' in row6_body

    def test_only_one_reset_all_button_exists(self):
        source = _source()
        assert source.count('id="wwDataPrepResetAllBtn"') == 1


class TestStructureOpenAndIssuesCollapsible:
    """7-row redesign: Structure keeps the previous always-visible
    compact-card treatment, while Issues/Readiness returns to a
    user-openable collapsed-by-default Row 2."""

    def test_structure_toggle_is_visually_removed_but_issues_toggle_is_visible(self):
        source = _source()
        assert (
            'class="secondary ww-data-prep-visually-removed" id="wwDataPrepStructureToggleBtn"'
            in source
        )
        assert 'class="secondary ww-data-prep-issues-chevron-btn" id="wwDataPrepIssuesToggleBtn"' in source
        assert 'class="secondary ww-data-prep-visually-removed" id="wwDataPrepIssuesToggleBtn"' not in source

    def test_visually_removed_class_is_display_none(self):
        source = _source()
        body = _function_body(
            source, ".ww-data-prep-visually-removed {", "}",
        )
        assert "display: none" in body

    def test_expanded_flags_match_structure_open_and_issues_collapsed(self):
        source = _source()
        assert "issuesExpanded: false," in source
        assert "structureExpanded: true," in source
        assert "wwDataPrep.issuesExpanded = false;" in source
        assert "wwDataPrep.structureExpanded = true;" in source
        # UAT fix (2026-09-06): Time Axis Setup's own equivalent flag was
        # removed outright (its "Hide"/"Configure" toggle no longer
        # exists) -- see TestTimeAxisSetupHideButtonRemoval for the
        # dedicated coverage of that removal. Checks the actual CODE
        # patterns (a declaration/assignment), not the bare word, since
        # explanatory comments elsewhere legitimately still name the
        # retired flag for historical context.
        assert "timeAxisExpanded:" not in source
        assert ".timeAxisExpanded =" not in source
        assert "wwDataPrep.timeAxisExpanded" not in source

    def test_structure_details_defaults_to_visible_on_workspace_open(self):
        source = _source()
        assert 'document.getElementById("wwDataPrepStructureDetails").hidden = false;' in source


class TestPageHeaderAndFileCard:
    """Row 1 visual redesign (2026-09-06): the approved order is now
    title block (visual anchor, primary width) -> back navigation
    (compact) -> file details (a card with a prominent icon, filename/
    format-size-rows on the left, a stacked Uploaded/Status metadata
    list on the right) -- only ALREADY-available metadata, no
    fabricated "last edited" or "start time" field exists anywhere in
    this workspace's state (Start time was investigated and found not
    to exist for an unconverted preparation source -- see the task's
    own final report)."""

    def test_row_1_has_three_slots_title_back_file_in_that_order(self):
        source = _source()
        row1_start = source.index('class="ww-data-prep-row ww-data-prep-row-1"')
        row2_start = source.index('class="ww-data-prep-row ww-data-prep-row-2"', row1_start)
        row1_body = source[row1_start:row2_start]
        assert 'class="ww-data-prep-page-header-titles"' in row1_body
        assert 'class="ww-data-prep-page-header-back"' in row1_body
        assert 'class="ww-data-prep-file-card"' in row1_body
        titles_pos = row1_body.index('class="ww-data-prep-page-header-titles"')
        back_pos = row1_body.index('class="ww-data-prep-page-header-back"')
        file_pos = row1_body.index('class="ww-data-prep-file-card"')
        assert titles_pos < back_pos < file_pos

    def test_back_button_is_its_own_slot_separate_from_title(self):
        source = _source()
        titles_start = source.index('class="ww-data-prep-page-header-titles"')
        back_slot_start = source.index('class="ww-data-prep-page-header-back"')
        titles_slot_body = source[titles_start:back_slot_start]
        assert 'id="wwDataPrepBackBtn"' not in titles_slot_body
        back_slot_end = source.index('class="ww-data-prep-file-card"')
        back_slot_body = source[back_slot_start:back_slot_end]
        assert 'id="wwDataPrepBackBtn"' in back_slot_body

    def test_row_1_uses_its_own_dedicated_grid_not_the_shared_equal_columns_one(self):
        source = _source()
        assert 'class="ww-data-prep-row ww-data-prep-row-1"' in source
        assert 'class="ww-data-prep-row ww-data-prep-row-1 ww-data-prep-row-cols"' not in source
        body = _function_body(source, ".ww-data-prep-row-1 {", "}")
        assert "display: grid" in body
        assert "minmax(0, 1.6fr) auto minmax(260px, 1fr)" in body

    def test_status_badge_and_dot_live_inside_the_file_details_slot(self):
        source = _source()
        file_card_start = source.index('class="ww-data-prep-file-card"')
        row1_end = source.index('class="ww-data-prep-row ww-data-prep-row-2"', file_card_start)
        file_card_body = source[file_card_start:row1_end]
        assert 'id="wwDataPrepStatusBadge"' in file_card_body
        assert 'id="wwDataPrepStatusDot"' in file_card_body
        assert 'class="ww-data-prep-status-slot"' not in source

    def test_status_dot_reuses_the_existing_dot_ok_convention(self):
        source = _source()
        assert 'class="dot" id="wwDataPrepStatusDot"' in source
        body = _function_body(
            source, "function wwDataPrepRenderMeta()", "function wwDataPrepRenderFileCardRowCount()",
        )
        assert 'wwDataPrep.status === "ready"' in body
        assert '"dot" + (' in body

    def test_uploaded_row_hides_as_a_whole_unit_not_just_the_value(self):
        source = _source()
        assert 'id="wwDataPrepUploadedRow" hidden' in source
        body = _function_body(
            source, "function wwDataPrepRenderMeta()", "function wwDataPrepRenderFileCardRowCount()",
        )
        assert 'document.getElementById("wwDataPrepUploadedRow")' in body
        assert "uploadedRow.hidden = false;" in body
        assert "uploadedRow.hidden = true;" in body

    def test_file_card_shows_filename_format_size_and_row_count(self):
        source = _source()
        assert 'class="ww-data-prep-file-card"' in source
        assert 'id="wwDataPrepFilename"' in source
        assert 'id="wwDataPrepFormat"' in source
        assert 'id="wwDataPrepSize"' in source
        assert 'id="wwDataPrepRowCount"' in source
        assert 'id="wwDataPrepStatusBadge"' in source

    def test_no_last_edited_or_start_time_field_is_fabricated(self):
        source = _source()
        assert "Last edited" not in source
        # No rendered "Start time" label anywhere in Row 1's own markup
        # (an explanatory HTML comment may still mention the words while
        # documenting why it's absent -- checked as actual tag content,
        # not a bare substring, so that comment doesn't false-positive
        # this check) -- only investigated/reported as unavailable, per
        # the task's own explicit "do not fabricate" instruction.
        row1_start = source.index('class="ww-data-prep-row ww-data-prep-row-1"')
        row2_start = source.index('class="ww-data-prep-row ww-data-prep-row-2"', row1_start)
        row1_body = source[row1_start:row2_start]
        assert ">Start time<" not in row1_body
        assert ">Start Time<" not in row1_body

    def test_uploaded_date_reuses_created_at_and_the_existing_formatter(self):
        source = _source()
        assert "wwDataPrep.createdAt = summary.created_at" in source
        body = _function_body(
            source, "function wwDataPrepRenderMeta()", "function wwDataPrepRenderFileCardRowCount()",
        )
        assert "formatImportedAt(wwDataPrep.createdAt)" in body

    def test_row_count_reflects_the_same_total_row_count_the_pager_uses(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderFileCardRowCount()", "function wwDataPrepRenderWorksheetSelector()",
        )
        assert "wwDataPrep.totalRowCount" in body

    def test_back_button_keeps_its_id_and_click_wiring(self):
        source = _source()
        assert 'id="wwDataPrepBackBtn"' in source
        assert source.count('id="wwDataPrepBackBtn"') == 1

    def test_file_card_icon_is_larger_than_the_old_inline_size(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-file-card-icon {", "}")
        assert "width: 44px" in body
        assert "height: 44px" in body

    def test_row_1_has_its_own_responsive_collapse_reusing_shared_breakpoints(self):
        source = _source()
        assert ".ww-data-prep-row-1 { grid-template-columns: 1fr auto; }" in source
        assert ".ww-data-prep-row-1 { grid-template-columns: 1fr; }" in source
        # Both declared inside the pre-existing shared breakpoint blocks
        # (1180px/820px), never a brand-new media query value.
        media_1180 = _function_body(source, "@media (max-width: 1180px) {", "@media (max-width: 820px) {")
        assert ".ww-data-prep-row-1 { grid-template-columns: 1fr auto; }" in media_1180


class TestWorkflowStrip:
    """Row 3 redesign (2026-09-06): a connected 4-step line-and-circle
    progress strip with title+helper text and checkmark-on-completed
    circles. Legacy chevrons stay in the DOM but are hidden presentation
    nodes; state remains derived from existing workspace state, never a
    second readiness/status engine. State priority: exactly one step is
    ever active/attention; every later step is forced "pending" regardless
    of its own individual signal."""

    def test_four_steps_exist_with_stable_ids(self):
        source = _source()
        for step_id in (
            "wwDataPrepWorkflowStepStructure",
            "wwDataPrepWorkflowStepIssues",
            "wwDataPrepWorkflowStepPreview",
            "wwDataPrepWorkflowStepConvert",
        ):
            assert 'id="' + step_id + '"' in source

    def test_row_3_is_the_workflow_strip(self):
        source = _source()
        assert (
            'class="ww-data-prep-row ww-data-prep-row-3 ww-data-prep-workflow-strip" id="wwDataPrepWorkflowStrip"'
            in source
        )

    def test_strip_uses_list_semantics_not_a_clickable_stepper(self):
        source = _source()
        strip_start = source.index('id="wwDataPrepWorkflowStrip"')
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4"', strip_start)
        strip_body = source[strip_start:row4_start]
        assert 'id="wwDataPrepWorkflowStrip" role="list"' in source
        assert strip_body.count('role="listitem"') == 4
        assert "addEventListener" not in strip_body
        assert "<button" not in strip_body

    def test_each_step_has_a_title_and_a_helper_line_with_approved_wording(self):
        source = _source()
        expected = [
            ("Configure Structure", "Define header, data region and column roles"),
            ("Review Issues", "Check and resolve any detected issues"),
            ("Preview Data", "Verify the data looks correct"),
            ("Convert", "Save and add to Recording Events"),
        ]
        for title, helper in expected:
            assert '<span class="ww-data-prep-workflow-step-title">' + title + "</span>" in source
            assert '<span class="ww-data-prep-workflow-step-helper">' + helper + "</span>" in source

    def test_each_step_has_a_digit_and_a_hidden_checkmark_for_completed(self):
        source = _source()
        assert source.count('class="ww-data-prep-workflow-step-num-digit"') == 4
        assert source.count('class="ww-data-prep-workflow-step-num-check" aria-hidden="true"') == 4
        body = _function_body(source, ".ww-data-prep-workflow-step-num-check {", "}")
        assert "display: none" in body
        done_body = _function_body(
            source,
            '.ww-data-prep-workflow-step[data-state="done"] .ww-data-prep-workflow-step-num-digit',
            "}",
        )
        assert "display: none" in done_body

    def test_three_chevron_separators_exist_between_the_four_steps(self):
        source = _source()
        strip_start = source.index('id="wwDataPrepWorkflowStrip"')
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4"', strip_start)
        strip_body = source[strip_start:row4_start]
        assert strip_body.count('class="ww-data-prep-workflow-chevron" aria-hidden="true"') == 3

    def test_chevrons_remain_nonsemantic_and_hidden_in_the_mock_like_strip(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-workflow-chevron {", "}")
        assert "display: none" in body

    def test_outer_container_is_a_mock_like_line_and_circle_grid(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-workflow-strip {", "}")
        assert "display: grid" in body
        assert "repeat(4, minmax(0, 1fr))" in body
        assert "background: transparent" in body
        assert "overflow: visible" in body
        connector = _function_body(source, ".ww-data-prep-workflow-strip::before {", "}")
        assert 'content: ""' in connector
        assert "height: 2px" in connector
        assert "background: var(--panel-border)" in connector

    def test_active_and_done_states_style_the_circles_not_the_whole_cell(self):
        source = _source()
        assert '.ww-data-prep-workflow-step[data-state="active"] { background: transparent; }' in source
        assert '.ww-data-prep-workflow-step[data-state="done"] { background: transparent; }' in source
        assert (
            '.ww-data-prep-workflow-step[data-state="active"] .ww-data-prep-workflow-step-num { background: var(--accent); border-color: var(--accent); color: #fff; }'
            in source
        )
        assert (
            '.ww-data-prep-workflow-step[data-state="done"] .ww-data-prep-workflow-step-num { background: var(--accent); border-color: var(--accent); color: #fff; }'
            in source
        )

    def test_attention_uses_the_existing_warning_token_on_the_circle(self):
        source = _source()
        assert (
            '.ww-data-prep-workflow-step[data-state="attention"] .ww-data-prep-workflow-step-num { background: var(--warn); border-color: var(--warn); color: #fff; }'
            in source
        )

    def test_render_function_derives_from_existing_state_only(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "// Section 22:",
        )
        assert "fetch(" not in body
        assert "wwDataPrepEffectiveIssueSummary()" in body
        # Step 3/4 both key off the SAME existing Continue-to-Powerwave
        # visibility signal -- no invented "user confirmed preview" flag.
        assert 'document.getElementById("wwDataPrepConversionAction").hidden' in body

    def test_render_function_is_called_after_issues_structure_and_pagination_render(self):
        source = _source()
        for anchor in (
            'function wwDataPrepRenderIssues()',
        ):
            body = _function_body(source, anchor, "function wwDataPrepIsIndexOnlyWithoutInterval()")
            assert "wwDataPrepRenderWorkflowStrip();" in body

    def test_earlier_incomplete_step_forces_every_later_step_to_pending(self):
        # The core state-model fix: an incomplete Step 1 must not let
        # Step 2 independently compute "attention" merely because the
        # SAME missing configuration also produces a blocking issue.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "\n\n        // Section 22:",
        )
        assert "if (!structureDone) {" in body
        assert 'issuesState = previewState = convertState = "pending";' in body
        assert 'previewState = convertState = "pending";' in body

    def test_convert_step_never_reaches_a_done_state(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "\n\n        // Section 22:",
        )
        assert 'convertState = "done"' not in body

    def test_active_step_gets_aria_current(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "\n\n        // Section 22:",
        )
        assert 'el.setAttribute("aria-current", "step");' in body
        assert 'el.removeAttribute("aria-current");' in body

    def test_small_screen_hides_helper_text_but_keeps_titles(self):
        # Owner-explicit preference: retain step TITLES for as long as
        # reasonably possible on small screens -- numbers alone provide
        # weak workflow context. Only the helper description is hidden.
        source = _source()
        media_820 = _function_body(source, "@media (max-width: 820px) {", "@media (max-width: 640px) {")
        assert ".ww-data-prep-workflow-step-helper { display: none; }" in media_820
        assert ".ww-data-prep-workflow-step-title { display: none; }" not in media_820
        assert "wwDataPrepWorkflowStepStructure" not in media_820


class TestDataPreviewHeaderBadges:
    """Column-role/type badges in Data Preview table headers -- reuses
    the SAME wwDataPrep.columnRoles/columnLabels state the Column Roles
    card already renders from, never a second "interpreted vs raw" data
    mode."""

    def test_role_badge_helper_exists_and_covers_time_axis_and_waveform(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "preview.rows.forEach(",
        )
        assert 'data-role="time_axis"' in body
        assert 'data-role="waveform"' in body

    def test_derived_time_column_badge_uses_the_actual_interpreter_label(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview)", "preview.rows.forEach(",
        )
        assert "WW_DATA_PREP_INTERPRETER_LABELS[wwDataPrep.timeAxisSummary" in body


class TestColumnRolesRow3BRedesign:
    """Row 3B redesign (2026-09-06): the old read-only "Preview" column
    (a duplicate sample of each column's own values, already shown for
    real in Row 4's Data Preview) is removed entirely, and the old
    permanent explanatory paragraph is replaced by an info-tip tooltip
    beside the title, reusing the SAME shared .ww-info-tip-trigger/
    wwInfoTipShow()/wwInfoTipHide() mechanism Row 3A already
    established -- never a second tooltip system. Table structure is
    now exactly: Column / Label / Role / Engineering Quantity /
    Measured Unit."""

    def test_preview_column_is_gone(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderColumnMapping()", "function wwDataPrepRenderStructureSummary()",
        )
        assert "<th>Preview</th>" not in body
        assert "ww-data-prep-column-preview-cell" not in body
        assert "fetch(" not in body

    def test_render_function_no_longer_takes_a_preview_argument(self):
        source = _source()
        assert "function wwDataPrepRenderColumnMapping()" in source
        assert "function wwDataPrepRenderColumnMapping(preview)" not in source

    def test_call_site_passes_no_argument(self):
        source = _source()
        assert "wwDataPrepRenderColumnMapping();" in source
        assert "wwDataPrepRenderColumnMapping(preview);" not in source

    def test_table_header_is_five_columns_in_the_new_order(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderColumnMapping()", "function wwDataPrepRenderStructureSummary()",
        )
        header_start = body.index("<thead>")
        header_end = body.index("</thead>")
        header = body[header_start:header_end]
        assert header.index("<th>Col.</th>") < header.index("<th>Label</th>") < header.index(
            "<th>Role</th>"
        ) < header.index("<th>Engineering Quantity</th>") < header.index("<th>Measured Unit</th>")

    def test_dead_preview_cell_css_rule_is_removed(self):
        source = _source()
        assert "ww-data-prep-column-preview-cell" not in source

    def test_old_permanent_helper_paragraph_is_gone_from_the_card(self):
        source = _source()
        card_start = source.index("<h3>Column Roles ")
        h3_end = source.index("</h3>", card_start)
        card_end = source.index('id="wwDataPrepColumnsTable"', card_start)
        card_body = source[h3_end:card_end]
        # The guidance text now lives ONLY inside the tooltip's
        # data-tooltip-text attribute (checked up to the closing
        # </h3>) -- nothing after the title, before the table, should
        # be a permanent visible paragraph repeating it.
        assert "defines the X-axis" not in card_body
        assert "ww-data-prep-card-subtitle" not in card_body

    def test_title_carries_the_shared_info_tip_trigger(self):
        source = _source()
        card_start = source.index("<h3>Column Roles ")
        card_end = source.index('id="wwDataPrepColumnsTable"', card_start)
        card_head = source[card_start:card_end]
        assert "ww-info-tip-trigger" in card_head
        assert "data-tooltip-text=" in card_head

    def test_tooltip_text_covers_all_three_roles(self):
        source = _source()
        card_start = source.index("<h3>Column Roles ")
        card_end = source.index('id="wwDataPrepColumnsTable"', card_start)
        card_head = source[card_start:card_end]
        tooltip_start = card_head.index('data-tooltip-text="') + len('data-tooltip-text="')
        tooltip_end = card_head.index('"', tooltip_start)
        tooltip_text = card_head[tooltip_start:tooltip_end]
        assert "Time Axis" in tooltip_text and "X-axis" in tooltip_text
        assert "Waveform" in tooltip_text and "Y-axis" in tooltip_text
        assert "Not Assigned" in tooltip_text and "excluded from the cleaned export" in tooltip_text

    def test_no_second_tooltip_implementation_is_introduced(self):
        source = _source()
        # Reuses the exact same portal/show/hide functions Row 3A's
        # tooltip already relies on -- exactly one of each must exist.
        assert source.count("function wwInfoTipShow(") == 1
        assert source.count("function wwInfoTipHide(") == 1
        assert source.count('id="wwInfoTipPortal"') == 1


class TestColumnRolesLabelColumnStaysReadable:
    """Owner correction (2026-09-06): the Label/Source Header column is
    real engineering data and must never be silently truncated. It
    renders in full, wraps rather than clips, carries a native `title`
    tooltip as a fallback, and gets the largest width share of the five
    columns so the other (select-driven) columns have to stay
    compact, not the other way around."""

    def _render_body(self, source: str) -> str:
        return _function_body(
            source, "function wwDataPrepRenderColumnMapping()", "function wwDataPrepRenderStructureSummary()",
        )

    def test_label_cell_renders_the_full_escaped_value_with_a_title_attribute(self):
        source = _source()
        body = self._render_body(source)
        assert 'class="ww-data-prep-label-cell"' in body
        assert "title=\"" in body
        # The exact same escaped value backs both the visible text and
        # the title attribute -- never a shortened/summarized copy.
        assert "labelEscaped" in body
        assert body.count("labelEscaped") >= 2

    def test_label_cell_has_no_ellipsis_or_line_clamp_truncation(self):
        source = _source()
        body = self._render_body(source)
        assert "text-overflow" not in body
        rule_start = source.index(".ww-data-prep-label-cell {")
        rule_end = source.index("}", rule_start)
        rule = source[rule_start:rule_end]
        assert "-webkit-line-clamp" not in rule
        assert "overflow-wrap: anywhere" in rule

    def test_label_column_has_the_largest_percentage_width(self):
        source = _source()
        import re

        widths = {}
        for n in range(1, 6):
            m = re.search(
                r'\.ww-data-prep-columns-table th:nth-child\(' + str(n) + r'\),'
                r' \.ww-data-prep-columns-table td:nth-child\(' + str(n) + r'\) \{ width: (\d+)%',
                source,
            )
            assert m, f"expected an nth-child({n}) width rule"
            widths[n] = int(m.group(1))
        # Label is column 2 -- it must be the single widest column.
        assert widths[2] == max(widths.values())
        assert sum(widths.values()) == 100

    def test_role_engineering_quantity_measured_unit_selects_still_have_min_width_floors(self):
        source = _source()
        assert ".ww-data-prep-role-select { min-width:" in source
        assert ".ww-data-prep-engineering-quantity-select { min-width:" in source
        assert ".ww-data-prep-measured-unit-select { min-width:" in source

    def test_label_cell_has_its_own_min_width_floor_to_avoid_character_by_character_wrap(self):
        source = _source()
        rule_start = source.index("td.ww-data-prep-label-cell {")
        rule_end = source.index("min-width:", rule_start)
        # A comment may sit between the selector and the declarations
        # (and may itself contain a brace-punctuated example) -- assert
        # the declaration is reasonably close to the selector rather
        # than naively matching the first "}", which could belong to
        # an example inside such a comment.
        assert rule_end - rule_start < 700

    def test_first_column_header_is_the_compact_col_abbreviation(self):
        source = _source()
        body = self._render_body(source)
        assert "<th>Col.</th>" in body
        assert "<th>Column</th>" not in body


class TestTimeAxisSetupRow3CRedesign:
    """Row 3C redesign (2026-09-06): visual/layout only -- the existing
    collapse-by-default "Configure" toggle, every id, every render
    function, and every DEC-082/DEC-083 behavior are unchanged. Only
    checks: the permanent helper paragraph moved into the SAME shared
    info-tip tooltip system Row 3A/3B already use, Time format/Time
    column now share a responsive side-by-side row, and Save is now
    the visually primary action (Clear stays secondary)."""

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        return source[start:end]

    def test_permanent_helper_paragraph_is_gone_replaced_by_a_tooltip(self):
        source = _source()
        panel = self._panel_body(source)
        header_end = panel.index("</h3>")
        # Nothing between the title and the status card repeats the old
        # permanent paragraph -- its guidance now lives ONLY in the
        # tooltip's own data-tooltip-text attribute (checked up to and
        # including the closing </h3>, where that attribute lives).
        assert "Powerwave never guesses a date order" not in panel[header_end:panel.index('id="wwDataPrepTimeAxisValidity"')]
        assert 'data-tooltip-text="Configure how Powerwave should interpret' in panel[:header_end]

    def test_title_carries_the_shared_info_tip_trigger(self):
        source = _source()
        panel = self._panel_body(source)
        header = panel[: panel.index("</h3>")]
        assert "ww-info-tip-trigger" in header

    def test_time_format_and_time_column_share_a_responsive_row(self):
        source = _source()
        panel = self._panel_body(source)
        row_start = panel.index('class="ww-data-prep-structure-row ww-data-prep-time-axis-format-row"')
        interpreter_pos = panel.index('id="wwDataPrepTimeAxisInterpreterSelect"')
        column_field_pos = panel.index('id="wwDataPrepTimeAxisColumnField"')
        assert row_start < interpreter_pos < column_field_pos

    def test_save_is_primary_and_clear_stays_secondary(self):
        source = _source()
        panel = self._panel_body(source)
        save_start = panel.index('id="wwDataPrepTimeAxisSaveBtn"')
        save_tag_start = panel.rindex("<button", 0, save_start)
        save_tag = panel[save_tag_start:save_start]
        assert 'class="secondary"' not in save_tag
        clear_start = panel.index('id="wwDataPrepTimeAxisClearBtn"')
        clear_tag_start = panel.rindex("<button", 0, clear_start)
        clear_tag = panel[clear_tag_start:clear_start]
        assert 'class="secondary"' in clear_tag

    def test_advanced_options_and_advanced_details_stay_distinct(self):
        source = _source()
        panel = self._panel_body(source)
        assert 'id="wwDataPrepTimeAxisAdvancedOptions"' in panel
        assert 'id="wwDataPrepTimeAxisAdvanced"' in panel
        assert panel.index('id="wwDataPrepTimeAxisAdvancedOptions"') != panel.index('id="wwDataPrepTimeAxisAdvanced"')

    def test_configure_toggle_and_collapse_behavior_are_unchanged(self):
        # Superseded by TestTimeAxisSetupHideButtonRemoval below (a
        # follow-up UAT fix removed this toggle entirely) -- kept as a
        # negative check so a regression re-adding it is still caught.
        source = _source()
        assert 'id="wwDataPrepTimeAxisToggleBtn"' not in source

    def test_time_format_field_has_a_readable_min_width_floor(self):
        # UAT fix (2026-09-06): the two longest interpreter labels
        # ("Sample Number / Index", "Date + Time (2 columns)") must
        # stay fully readable rather than ellipsis-truncated -- the
        # field's own min-width (not just the select's) is what the
        # row's flex-wrap decision actually sizes against.
        source = _source()
        assert 'class="field ww-data-prep-structure-field ww-data-prep-time-axis-format-field"' in source
        rule_start = source.index(
            ".ww-data-prep-time-axis-format-row > .ww-data-prep-structure-field.ww-data-prep-time-axis-format-field {"
        )
        rule_end = source.index("}", rule_start)
        rule = source[rule_start:rule_end]
        assert "min-width: 200px" in rule

    def test_interpreter_select_title_is_kept_in_sync_with_its_selected_label(self):
        source = _source()
        assert 'interpreterSelect.title = selectedOption ? selectedOption.textContent : "";' in source


class TestTimeAxisSetupHideButtonRemoval:
    """UAT fix (2026-09-06): the "Hide"/"Configure" collapse interaction
    is retired -- Time Axis Setup stays permanently visible, matching
    Row 3A's own always-visible card treatment. Advanced options and
    Advanced details each keep their own independent <details> collapse
    unchanged. `wwDataPrep.timeAxisExpanded` (truly dead once nothing
    ever reads or writes it any more) is removed outright."""

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        return source[start:end]

    def test_hide_configure_toggle_button_is_gone(self):
        source = _source()
        assert 'id="wwDataPrepTimeAxisToggleBtn"' not in source

    def test_details_wrapper_has_no_hidden_attribute_and_is_never_hidden_by_script(self):
        source = _source()
        assert '<div id="wwDataPrepTimeAxisDetails">' in source
        assert '<div id="wwDataPrepTimeAxisDetails" hidden>' not in source
        assert '"wwDataPrepTimeAxisDetails").hidden' not in source

    def test_time_axis_expanded_flag_is_fully_removed(self):
        # Checks the actual CODE patterns, not the bare word -- this
        # class's own docstring, and other comments, legitimately still
        # name the retired flag for historical context.
        source = _source()
        assert "timeAxisExpanded:" not in source
        assert ".timeAxisExpanded =" not in source
        assert "wwDataPrep.timeAxisExpanded" not in source

    def test_configure_time_axis_cta_still_scrolls_the_panel_into_view(self):
        # The SEPARATE "Configure Time Axis" call-to-action (Row 5's
        # Sample-Index-without-interval limitation notice) still exists
        # and still jumps focus to the panel -- only the now-dead
        # expand/relabel lines it used to also perform are gone.
        source = _source()
        assert "function wwDataPrepConfigureTimeAxis() {" in source
        body = _function_body(source, "function wwDataPrepConfigureTimeAxis() {", "}")
        assert 'getElementById("wwDataPrepTimeAxisPanel").scrollIntoView(' in body
        assert "timeAxisExpanded" not in body

    def test_advanced_options_and_advanced_details_keep_their_own_collapse(self):
        source = _source()
        panel = self._panel_body(source)
        assert '<details class="ww-data-prep-time-axis-advanced-options" id="wwDataPrepTimeAxisAdvancedOptions">' in panel
        assert '<details class="ww-data-prep-time-axis-advanced" id="wwDataPrepTimeAxisAdvanced">' in panel


class TestTimeAxisSetupStatusCardAndDetectSpacing:
    """UAT fix (2026-09-06): the old bare "TIME FORMAT"/"TIME COLUMN"
    metadata pair is visually retired (still populated, computation
    reused rather than duplicated) in favor of one compact status card
    -- icon + adaptive headline + one detail line -- and Detect gets a
    dedicated margin so it no longer sits flush against whichever
    conditional field precedes it."""

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        return source[start:end]

    def test_old_summary_dl_is_visually_removed_but_still_populated(self):
        source = _source()
        panel = self._panel_body(source)
        assert 'class="ww-data-prep-structure-summary ww-data-prep-visually-removed" id="wwDataPrepTimeAxisSummary"' in panel
        assert 'id="wwDataPrepTimeAxisSummaryInterpretation"' in panel
        assert 'id="wwDataPrepTimeAxisSummaryColumns"' in panel

    def test_validity_detail_is_now_nested_inside_the_status_card(self):
        source = _source()
        panel = self._panel_body(source)
        card_start = panel.index('id="wwDataPrepTimeAxisValidity"')
        card_end = panel.index("</div>", panel.index('id="wwDataPrepTimeAxisValidityDetail"'))
        card_body = panel[card_start:card_end]
        assert 'id="wwDataPrepTimeAxisValidityIcon"' in card_body
        assert 'id="wwDataPrepTimeAxisValidityText"' in card_body
        assert 'id="wwDataPrepTimeAxisValidityDetail"' in card_body

    def test_status_card_has_a_subtle_background_wash_per_state(self):
        source = _source()
        assert '.ww-data-prep-time-axis-validity[data-state="valid"] { background: var(--ok-wash); }' in source
        assert (
            '.ww-data-prep-time-axis-validity[data-state="unconfigured"] { background: color-mix(in srgb, var(--warn) 12%, transparent); }'
            in source
        )

    def test_unconfigured_and_configured_wording_matches_the_approved_copy(self):
        source = _source()
        assert 'textEl.textContent = "Time axis not configured";' in source
        assert 'detailEl.textContent = "Select a time format and time column to continue.";' in source
        assert 'textEl.textContent = attention ? "Time axis needs attention" : "Time axis configured";' in source

    def test_configured_detail_line_reuses_the_summary_text_not_row_count(self):
        source = _source()
        body = _function_body(source, "function wwDataPrepRenderTimeAxisValidity() {", "function wwDataPrepRenderTimeAxisAdvancedDetails(")
        assert 'getElementById("wwDataPrepTimeAxisSummaryInterpretation")' in body
        assert 'getElementById("wwDataPrepTimeAxisSummaryColumns")' in body
        assert '" rows"' not in body
        assert "approximately " not in body

    def test_detect_button_row_has_its_own_top_margin(self):
        source = _source()
        panel = self._panel_body(source)
        assert 'class="ww-data-prep-structure-controls ww-data-prep-time-axis-detect-row"' in panel
        rule_start = source.index(".ww-data-prep-time-axis-detect-row {")
        rule_end = source.index("}", rule_start)
        assert "margin-top: 14px" in source[rule_start:rule_end]


class TestSevenRowLayoutFoundation:
    """Approved 7-row layout (2026-09-06): the page is organized into
    exactly seven semantic horizontal rows. Row 5 owns the only active
    configuration grid and uses a responsive 1:3:1 wide-desktop layout."""

    def test_exactly_seven_rows_exist(self):
        source = _source()
        # Each row's class is applied to exactly one element -- checked
        # via each row's own distinctive class-attribute string rather
        # than a bare substring count (which would also match e.g. a
        # "/ww-data-prep-row-N -->" closing comment).
        assert source.count('class="ww-data-prep-row ww-data-prep-row-1"') == 1
        assert source.count('class="ww-data-prep-row ww-data-prep-row-2"') == 1
        assert (
            source.count(
                'class="ww-data-prep-row ww-data-prep-row-3 ww-data-prep-workflow-strip" id="wwDataPrepWorkflowStrip"'
            )
            == 1
        )
        assert source.count('class="ww-data-prep-row ww-data-prep-row-4"') == 1
        assert source.count('class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"') == 1
        assert (
            source.count(
                'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-preview-card ww-data-prep-row ww-data-prep-row-6"'
            )
            == 1
        )
        assert source.count('class="ww-data-prep-row ww-data-prep-row-7"') == 1

    def test_row_5_grid_class_is_defined_once(self):
        source = _source()
        assert source.count(".ww-data-prep-row-5-grid {\n            display: grid;") == 1

    def test_old_shared_grid_classes_are_kept_but_unused(self):
        # .ww-data-prep-row-cols/-cols-2 are deliberately NOT deleted
        # (reusable utilities, explicit layout-experiment framing that
        # invites further iteration) but no row's own class list
        # references them any more.
        source = _source()
        assert ".ww-data-prep-row-cols {" in source
        assert ".ww-data-prep-row-cols-2 {" in source
        assert 'class="ww-data-prep-row ww-data-prep-row-3 ww-data-prep-row-cols ww-data-prep-config-grid"' not in source
        assert 'class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-cols-2"' not in source
        # The old fixed 1:1.5:1 override this class used to pair with is
        # gone entirely -- superseded by .ww-data-prep-row-5-grid.
        assert ".ww-data-prep-config-grid {" not in source

    def test_grid_children_get_min_width_zero(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-row-5-grid {", "/* Not currently used")
        assert ".ww-data-prep-row-5-grid > * { min-width: 0; }" in body

    def test_rows_do_not_flex_shrink_under_following_rows(self):
        source = _source()
        assert ".ww-data-prep-row { flex-shrink: 0; }" in source

    def test_no_orphaned_time_axis_comment_before_data_preview(self):
        # A stale comment describing the Time-Axis-interpretation panel
        # used to sit directly before Data Preview after the section
        # itself was relocated during an earlier layout pass -- must not
        # reappear.
        source = _source()
        row6_start = source.index(
            'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-preview-card ww-data-prep-row ww-data-prep-row-6"'
        )
        preceding = source[max(0, row6_start - 800):row6_start]
        assert "Time-Axis interpretation FRAMEWORK" not in preceding
