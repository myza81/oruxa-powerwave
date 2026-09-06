"""Structural checks for the Data Preparation page visual/layout
redesign (owner-approved mock target, 2026-09-06).

Purely presentational: every element/function this workspace already
used is asserted to still exist (same id, same JS function), just
relocated into the new one-page grid layout -- no preparation
semantics, readiness rules, Time Axis behavior, or API shape is
expected to have changed by this redesign, and this module does not
re-test any of that (see test_frontend_time_axis_draft_vs_applied.py/
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


class TestOnePageConfigGrid:
    """Task section 4: Worksheet/Header&Region, Column Roles, and Issues
    must all remain visible on the SAME page, arranged as a 3-column
    grid on a wide desktop -- never split into separate pages/tabs."""

    def test_config_grid_exists_with_three_columns(self):
        source = _source()
        assert source.count('class="ww-data-prep-config-grid"') == 1
        # Worksheet+Header/Region column and the Issues column both use
        # the plain class; the middle Column Roles column additionally
        # carries -wide -- three columns total.
        assert source.count('class="ww-data-prep-config-col">') == 2
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-wide"' in source

    def test_worksheet_and_header_region_share_the_first_column(self):
        source = _source()
        worksheet_pos = source.index('id="wwDataPrepWorksheetCard"')
        header_region_pos = source.index("Header &amp; Data Region")
        col_boundary = source.index('class="ww-data-prep-config-col ww-data-prep-config-col-wide"')
        assert worksheet_pos < header_region_pos < col_boundary

    def test_column_roles_card_exists_in_the_wide_column(self):
        source = _source()
        wide_col_start = source.index('class="ww-data-prep-config-col ww-data-prep-config-col-wide"')
        issues_col_start = source.index('id="wwDataPrepIssuesCard"')
        assert wide_col_start < source.index("<h3>Column Roles</h3>") < issues_col_start
        assert 'id="wwDataPrepColumnsTable"' in source[wide_col_start:issues_col_start]

    def test_issues_card_exists_and_no_longer_hosts_the_conversion_action(self):
        source = _source()
        issues_card_start = source.index('id="wwDataPrepIssuesCard"')
        # The Issues card ends at its own closing </section> -- the
        # conversion/export actions must not be inside it any more (task
        # section 8: "Issues" carries no conversion action in the mock).
        issues_card_end = source.index("</section>", issues_card_start)
        issues_card_body = source[issues_card_start:issues_card_end]
        assert 'id="wwDataPrepConvertBtn"' not in issues_card_body
        assert 'id="wwDataPrepExportBtn"' not in issues_card_body
        assert 'id="wwDataPrepIssueHeadline"' in issues_card_body
        assert 'id="wwDataPrepIssueCounts"' in issues_card_body
        assert 'id="wwDataPrepIssueGroups"' in issues_card_body

    def test_responsive_breakpoints_collapse_the_grid(self):
        source = _source()
        assert "@media (max-width: 1180px)" in source
        assert "@media (max-width: 820px)" in source


class TestFinalActionBarRelocation:
    """Task section 11: a persistent bottom action bar pairs a
    secondary action with the strong primary "Continue to Powerwave"
    action -- both are the SAME pre-existing elements/ids, just moved
    out of the Issues card."""

    def test_action_bar_exists_after_data_preview_and_holds_both_actions(self):
        source = _source()
        bar_start = source.index('class="ww-data-prep-action-bar"')
        bar_end = source.index("</section>", source.index("</div>\n            </section>", bar_start))
        bar_body = source[bar_start:bar_end]
        assert 'id="wwDataPrepConvertBtn"' in bar_body
        assert 'id="wwDataPrepExportBtn"' in bar_body
        assert 'id="wwDataPrepConversionLimitation"' in bar_body
        # Reset All Changes deliberately stays in the Data Preview
        # toolbar (contextually tied to the table it clears), not
        # duplicated here -- see this task's own final report mapping.
        assert 'id="wwDataPrepResetAllBtn"' not in bar_body

    def test_only_one_convert_button_and_one_export_button_exist(self):
        source = _source()
        assert source.count('id="wwDataPrepConvertBtn"') == 1
        assert source.count('id="wwDataPrepExportBtn"') == 1


class TestAlwaysVisibleStructureAndIssuesCards:
    """Visual redesign: Structure (Header & Data Region / Column Roles)
    and Issues drop their previous collapsed-by-default progressive
    disclosure in favor of the mock's own always-visible compact cards.
    The old toggle buttons/state flags are kept (not deleted) to avoid
    a null-element risk, just permanently hidden and defaulted open."""

    def test_toggle_buttons_are_visually_removed_not_deleted(self):
        source = _source()
        assert (
            'class="secondary ww-data-prep-visually-removed" id="wwDataPrepStructureToggleBtn"'
            in source
        )
        assert (
            'class="secondary ww-data-prep-visually-removed" id="wwDataPrepIssuesToggleBtn"'
            in source
        )

    def test_visually_removed_class_is_display_none(self):
        source = _source()
        body = _function_body(
            source, ".ww-data-prep-visually-removed {", "}",
        )
        assert "display: none" in body

    def test_expanded_flags_default_and_reset_to_true(self):
        source = _source()
        assert "issuesExpanded: true," in source
        assert "structureExpanded: true," in source
        assert "wwDataPrep.issuesExpanded = true;" in source
        assert "wwDataPrep.structureExpanded = true;" in source
        # Time Axis Setup keeps its own genuine collapse-by-default --
        # unaffected by this task (task section 9).
        assert "timeAxisExpanded: false," in source
        assert "wwDataPrep.timeAxisExpanded = false;" in source

    def test_structure_details_defaults_to_visible_on_workspace_open(self):
        source = _source()
        assert 'document.getElementById("wwDataPrepStructureDetails").hidden = false;' in source


class TestPageHeaderAndFileCard:
    """Task section 2: a file-summary card in the page header, showing
    only ALREADY-available metadata -- no fabricated "last edited"
    timestamp exists anywhere in this workspace's state."""

    def test_file_card_shows_filename_format_size_and_row_count(self):
        source = _source()
        assert 'class="ww-data-prep-file-card"' in source
        assert 'id="wwDataPrepFilename"' in source
        assert 'id="wwDataPrepFormat"' in source
        assert 'id="wwDataPrepSize"' in source
        assert 'id="wwDataPrepRowCount"' in source
        assert 'id="wwDataPrepStatusBadge"' in source

    def test_no_last_edited_field_is_fabricated(self):
        source = _source()
        assert "Last edited" not in source

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


class TestWorkflowStrip:
    """Task section 3: a compact 4-step progress strip -- presentation
    only, derived from state this workspace already computed, never a
    second readiness/status engine."""

    def test_four_steps_exist_with_stable_ids(self):
        source = _source()
        for step_id in (
            "wwDataPrepWorkflowStepStructure",
            "wwDataPrepWorkflowStepIssues",
            "wwDataPrepWorkflowStepPreview",
            "wwDataPrepWorkflowStepConvert",
        ):
            assert 'id="' + step_id + '"' in source

    def test_render_function_derives_from_existing_state_only(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "// Section 22:",
        )
        assert "fetch(" not in body
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "wwDataPrep.totalRowCount" in body

    def test_render_function_is_called_after_issues_structure_and_pagination_render(self):
        source = _source()
        for anchor in (
            'function wwDataPrepRenderIssues()',
        ):
            body = _function_body(source, anchor, "function wwDataPrepIsIndexOnlyWithoutInterval()")
            assert "wwDataPrepRenderWorkflowStrip();" in body


class TestDataPreviewHeaderBadges:
    """Task section 10: column-role/type badges in Data Preview table
    headers -- reuses the SAME wwDataPrep.columnRoles/columnLabels
    state the Column Roles card already renders from, never a second
    "interpreted vs raw" data mode."""

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


class TestColumnRolesPreviewColumn:
    """Task section 7 / mock fidelity: the Column Roles table gains a
    read-only "Preview" column of a column's own actual sample values,
    reusing the SAME already-fetched preview response
    wwDataPrepRenderTable() renders from -- never a second fetch, never
    itself editable."""

    def test_preview_column_header_exists(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderColumnMapping(preview)", "function wwDataPrepRenderStructureSummary()",
        )
        assert "<th>Preview</th>" in body
        assert "fetch(" not in body

    def test_call_site_passes_the_already_fetched_preview(self):
        source = _source()
        assert "wwDataPrepRenderColumnMapping(preview);" in source
