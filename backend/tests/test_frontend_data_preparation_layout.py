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
    """Row 5 revision (2026-09-07): Row 5 is now Header & Data Region |
    Column Roles ONLY, at a 1:3 ratio -- Time Axis Setup moved out to
    its own full-width row directly below (see
    TestRowFiveTimeAxisOwnRow) so its interpreter preview table could
    get a controls/preview split instead of a cramped third column.
    Worksheet selection and Issues/Readiness both still have their own
    rows, unaffected by this revision."""

    def test_row_5_is_the_main_configuration_grid(self):
        source = _source()
        assert 'class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"' in source

    def test_row_5_contains_header_and_roles_only_not_time_axis(self):
        source = _source()
        row5_start = source.index('class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"')
        row5_end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        row5_body = source[row5_start:row5_end]
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-region"' in row5_body
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-wide"' in row5_body
        assert "Header &amp; Data Region" in row5_body
        assert 'id="wwDataPrepColumnsTable"' in row5_body
        # Time Axis Setup no longer lives in Row 5 -- it is now its own
        # full-width row (see TestRowFiveTimeAxisOwnRow below).
        assert 'class="ww-data-prep-config-col ww-data-prep-config-col-time"' not in row5_body
        assert 'id="wwDataPrepTimeAxisPanel"' not in row5_body
        assert 'id="wwDataPrepWorksheetCard"' not in row5_body
        assert 'id="wwDataPrepIssuesCard"' not in row5_body

    def test_worksheet_has_its_own_row_4_before_main_configuration(self):
        source = _source()
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4" id="wwDataPrepWorksheetRow"')
        row5_start = source.index('class="ww-data-prep-row ww-data-prep-row-5 ww-data-prep-row-5-grid"')
        row4_body = source[row4_start:row5_start]
        assert 'id="wwDataPrepWorksheetCard"' in row4_body
        assert 'id="wwDataPrepWorksheetSelect"' in row4_body
        assert 'id="wwDataPrepWorksheetTabs"' in row4_body
        assert "Header &amp; Data Region" not in row4_body

    def test_csv_hides_the_entire_worksheet_row_not_inner_text(self):
        source = _source()
        render_body = _function_body(source, "function wwDataPrepRenderWorksheetSelector()", "function wwDataPrepRenderTable")

        assert 'id="wwDataPrepWorksheetCsvHint"' not in source
        assert "Not applicable -- this is a CSV file." not in source
        assert "#wwDataPrepWorksheetRow[hidden] { display: none; }" in source

        # The existing source/file-format state remains the only branch:
        # non-Excel hides the row itself, clears stale tabs, and returns
        # before the Excel select/tab rendering path.
        assert 'const row = document.getElementById("wwDataPrepWorksheetRow");' in render_body
        non_excel_branch = render_body[render_body.index('if (wwDataPrep.format !== "Excel") {'):render_body.index("return;", render_body.index('if (wwDataPrep.format !== "Excel") {'))]
        assert "if (row) row.hidden = true;" in non_excel_branch
        assert "field.hidden = true;" in non_excel_branch
        assert 'if (tabs) tabs.innerHTML = "";' in non_excel_branch
        assert "source_format" not in render_body
        assert "file_format" not in render_body

    def test_excel_shows_the_same_outer_row_before_rendering_tabs(self):
        source = _source()
        render_body = _function_body(source, "function wwDataPrepRenderWorksheetSelector()", "function wwDataPrepRenderTable")

        assert "if (row) row.hidden = false;" in render_body
        assert "field.hidden = false;" in render_body
        assert "select.innerHTML = wwDataPrep.worksheets.map((sheet) =>" in render_body
        assert "wwDataPrepWorksheetTabsHtml(wwDataPrep.worksheets, wwDataPrep.selectedWorksheetIndex)" in render_body
        assert render_body.index("if (row) row.hidden = false;") < render_body.index(
            "select.innerHTML = wwDataPrep.worksheets.map((sheet) =>"
        )

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

    def test_worksheet_tab_no_op_guard_reads_app_state_not_the_native_select(self):
        """P1 regression (2026-09-07): on a fresh Excel source the app has
        no worksheet selected (wwDataPrep.selectedWorksheetIndex === null)
        while the native <select> still reports its default first option
        ("0"). Guarding on select.value therefore treated a click on the
        FIRST worksheet tab as a no-op, so no change event was dispatched,
        no PATCH fired, and the preview never rendered. The guard must read
        application state, and must still no-op when that state already
        holds the clicked worksheet."""
        source = _source()
        click_body = _function_body(
            source,
            'document.getElementById("wwDataPrepWorksheetTabs").addEventListener("click"',
            'document.getElementById("wwDataPrepBackBtn").addEventListener("click"',
        )

        # The regressing guard must be gone -- select.value is never the
        # source of truth for what is currently selected.
        assert "if (select.value === tab.dataset.worksheetIndex) return;" not in click_body
        assert "select.value ===" not in click_body

        # The guard reads the single existing worksheet state (no second
        # worksheet state is introduced) and compares it as a string.
        assert "const selectedIndex = wwDataPrep.selectedWorksheetIndex;" in click_body
        assert "selectedIndex != null" in click_body
        assert 'String(selectedIndex) === tab.dataset.worksheetIndex' in click_body

        # A fresh source (null state) must fall through to the dispatch path.
        guard_end = click_body.index("selectedIndex != null")
        assert click_body.index("select.value = tab.dataset.worksheetIndex;") > guard_end
        assert click_body.index('select.dispatchEvent(new Event("change", { bubbles: true }));') > guard_end


class TestWorksheetRowRedesign:
    """Worksheet row redesign (2026-09-07 UAT): an Excel identity block
    (icon + "Worksheet"/"Excel file") + divider + rounded worksheet-tab
    buttons + a "More sheets" overflow, kept deliberately compact per
    explicit owner direction. Presentational only -- the SAME
    #wwDataPrepWorksheetSelect + dispatchEvent("change") mechanism and
    the SAME delegated click listener on #wwDataPrepWorksheetTabs
    (data-worksheet-index + .closest()) select worksheets exactly as
    before; only what renders/how it looks changed."""

    def _click_body(self, source: str) -> str:
        return _function_body(
            source,
            'document.getElementById("wwDataPrepWorksheetTabs").addEventListener("click"',
            'document.getElementById("wwDataPrepBackBtn").addEventListener("click"',
        )

    def test_identity_block_and_divider_exist_inside_the_excel_only_field(self):
        source = _source()
        field_start = source.index('id="wwDataPrepWorksheetField"')
        field_end = source.index("</div>\n                    </div>", field_start)
        field_body = source[field_start:field_end]
        assert 'class="ww-data-prep-worksheet-identity"' in field_body
        assert 'class="ww-data-prep-worksheet-identity-icon"' in field_body
        assert ">Worksheet<" in field_body
        assert ">Excel file<" in field_body
        assert 'class="ww-data-prep-worksheet-divider"' in field_body
        # The identity block/divider come before the select/tabs, and
        # all of it is still inside the SAME hidden/shown Excel-only unit.
        select_pos = field_body.index('id="wwDataPrepWorksheetSelect"')
        assert field_body.index('class="ww-data-prep-worksheet-identity"') < select_pos

    def test_old_permanently_hidden_heading_was_removed(self):
        # Verified unused before removal -- no id, no JS reference, only
        # ever `display: none`. Replaced by the identity block above.
        source = _source()
        assert "<h3>Worksheet <span" not in source
        assert "ww-data-prep-worksheet-subtitle" not in source
        assert ".ww-data-prep-worksheet-row h3 { display: none; }" not in source

    def test_tabs_are_rounded_pill_buttons_not_the_old_flat_underline_style(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-worksheet-tab {", "}")
        assert "border-radius: var(--radius);" in rule
        assert "border: 1px solid var(--panel-border);" in rule
        assert "border-bottom: 3px solid transparent;" not in rule
        assert "border-radius: 0;" not in rule

    def test_active_tab_gets_accent_styling_distinct_from_inactive(self):
        source = _source()
        rule = _function_body(source, '.ww-data-prep-worksheet-tab[aria-selected="true"] {', "}")
        assert "color: var(--accent);" in rule
        assert "border-color: var(--accent);" in rule
        assert "background: var(--accent-wash-soft);" in rule

    def test_tab_has_focus_visible_state(self):
        source = _source()
        assert ".ww-data-prep-worksheet-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }" in source

    def test_long_names_truncate_with_a_native_tooltip(self):
        source = _source()
        assert "max-width: 160px;" in _function_body(source, ".ww-data-prep-worksheet-tab {", "}")
        label_rule = _function_body(source, ".ww-data-prep-worksheet-tab-label {", "}")
        assert "overflow: hidden;" in label_rule
        assert "text-overflow: ellipsis;" in label_rule
        assert "white-space: nowrap;" in label_rule
        tab_html_fn = _function_body(
            source, "function wwDataPrepWorksheetTabHtml(sheet, selectedIndex) {", "}"
        )
        assert "title=" in tab_html_fn

    def test_native_select_stays_visually_hidden_and_still_the_source_of_truth(self):
        # Unchanged mechanism -- the native select is still what tab
        # clicks route through via .value + dispatchEvent("change").
        source = _source()
        rule = _function_body(source, "#wwDataPrepWorksheetSelect {", "}")
        assert "position: absolute;" in rule
        assert "clip: rect(0 0 0 0);" in rule
        click_body = self._click_body(source)
        assert 'const select = document.getElementById("wwDataPrepWorksheetSelect");' in click_body
        assert "select.value = tab.dataset.worksheetIndex;" in click_body

    def test_active_sheet_gets_a_grid_icon_inactive_sheets_do_not(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepWorksheetTabHtml(sheet, selectedIndex) {",
            "function wwDataPrepRenderTable(preview) {",
        )
        assert "const isActive = sheet.index === selectedIndex;" in body
        assert "isActive\n                ? " in body or "isActive ?" in body

    def test_overflow_keeps_the_selected_sheet_inline_never_hidden(self):
        # "Obvious at a glance" -- reopening a source whose selected
        # worksheet falls outside the first N by position must not hide
        # it inside an unopened "More sheets" dropdown.
        source = _source()
        assert "const WW_DATA_PREP_WORKSHEET_MAX_INLINE = 4;" in source
        body = _function_body(
            source,
            "function wwDataPrepWorksheetTabsHtml(worksheets, selectedIndex) {",
            "function wwDataPrepWorksheetTabHtml(sheet, selectedIndex) {",
        )
        assert "worksheets.length > WW_DATA_PREP_WORKSHEET_MAX_INLINE" in body
        assert "const selectedPos = worksheets.findIndex((s) => s.index === selectedIndex);" in body
        assert "if (selectedPos >= WW_DATA_PREP_WORKSHEET_MAX_INLINE) {" in body

    def test_more_sheets_only_renders_when_overflow_exists(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepWorksheetTabsHtml(worksheets, selectedIndex) {",
            "function wwDataPrepWorksheetTabHtml(sheet, selectedIndex) {",
        )
        assert "if (overflowSheets.length) {" in body
        assert 'class="ww-data-prep-worksheet-more"' in body
        assert ">More sheets<" in body

    def test_overflow_buttons_reuse_the_exact_same_tab_markup_and_selection_path(self):
        # No second selection path for overflowed sheets -- they are
        # plain .ww-data-prep-worksheet-tab elements with the same
        # data-worksheet-index attribute the ONE delegated click
        # listener already reads, just nested inside the dropdown body.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepWorksheetTabsHtml(worksheets, selectedIndex) {",
            "function wwDataPrepWorksheetTabHtml(sheet, selectedIndex) {",
        )
        assert "overflowSheets.map((sheet) => wwDataPrepWorksheetTabHtml(sheet, selectedIndex))" in body
        assert 'class="ww-data-prep-worksheet-more-body"' in body

    def test_more_sheets_trigger_is_excluded_from_the_selection_click_handler(self):
        # Regression guard: the "More sheets" <summary> shares
        # .ww-data-prep-worksheet-tab for consistent sizing but carries
        # no data-worksheet-index -- without this guard, clicking it
        # would dispatch a bogus "change" with an undefined value.
        source = _source()
        click_body = self._click_body(source)
        assert "if (!tab || tab.dataset.worksheetIndex === undefined) return;" in click_body
        assert 'class="ww-data-prep-worksheet-tab ww-data-prep-worksheet-tab-more"' in source
        # The trigger's own markup never sets data-worksheet-index.
        more_summary = _function_body(source, '<summary class="ww-data-prep-worksheet-tab ww-data-prep-worksheet-tab-more">', "</summary>")
        assert "data-worksheet-index" not in more_summary

    def test_selecting_from_the_overflow_dropdown_closes_it(self):
        source = _source()
        click_body = self._click_body(source)
        assert 'tab.closest(".ww-data-prep-worksheet-more")' in click_body
        assert "openDetails.open = false;" in click_body

    def test_column_roles_card_exists_in_the_wide_column(self):
        source = _source()
        wide_col_start = source.index('class="ww-data-prep-config-col ww-data-prep-config-col-wide"')
        row5_end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        assert wide_col_start < source.index("<h3>Column Roles ") < row5_end
        assert 'id="wwDataPrepColumnsTable"' in source[wide_col_start:row5_end]

    def test_row_5_grid_ratio_is_1_3(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-row-5-grid {", "}")
        assert "display: grid" in body
        assert "minmax(0, 1fr) minmax(0, 3fr)" in body
        assert "minmax(0, 1fr) minmax(0, 3fr) minmax(0, 1fr)" not in body
        assert 'grid-template-areas: "region roles";' in body

    def test_row_5_keeps_1_3_until_mobile_stack(self):
        source = _source()
        media_1180 = _function_body(source, "@media (max-width: 1180px) {", "@media (max-width: 820px) {")
        assert ".ww-data-prep-row-5-grid" not in media_1180
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert ".ww-data-prep-row-5-grid" in media_820
        assert "grid-template-columns: 1fr;" in media_820
        assert 'grid-template-areas:' in media_820
        assert '"region"' in media_820
        assert '"roles"' in media_820
        # Time Axis Setup is no longer part of Row 5's grid at all (own
        # full-width row now) -- its old stacked area must not reappear.
        assert '"time"' not in media_820
        assert '"region time"' not in source
        assert '"roles roles"' not in source

    def test_phone_widths_keep_first_role_dropdown_reachable(self):
        source = _source()
        media_480 = _function_body(source, "@media (max-width: 480px) {", "/* Header row:")
        assert "td.ww-data-prep-label-cell { min-width: 112px; }" in media_480
        assert ".ww-data-prep-role-select { min-width: 104px; }" in media_480
        assert ".ww-data-prep-engineering-quantity-select { min-width: 120px; }" in media_480


class TestRowFiveAHeaderDataRegionRedesign:
    """Row 5A redesign (2026-09-07): Header & Data Region gets the SAME
    numbered-step-badge + title + description header Column Roles' own
    Row 5B redesign already established (reusing the SAME generic
    .ww-data-prep-panel-step-badge class, never a second badge style),
    plus a new light-blue instructional info box. Presentational only --
    every existing #wwDataPrep* id, event handler, and backend contract
    for Header row / Data start-end row / Set Region / Reset Region is
    unchanged; Column Roles' own markup/CSS is untouched by this task."""

    def _card_body(self, source: str) -> str:
        start = source.index('<h3>Header &amp; Data Region</h3>')
        start = source.rindex("<section", 0, start)
        end = source.index("</section>", start)
        return source[start:end]

    def test_numbered_step_badge_reads_1_and_reuses_the_shared_badge_class(self):
        source = _source()
        card = self._card_body(source)
        assert 'class="ww-data-prep-panel-step-badge"' in card
        badge_start = card.index('class="ww-data-prep-panel-step-badge"')
        badge_end = card.index("</span>", badge_start)
        assert card[badge_start:badge_end].endswith(">1")
        # No second badge style introduced -- same class Column Roles
        # already uses, defined exactly once in the whole stylesheet.
        assert source.count(".ww-data-prep-panel-step-badge {") == 1

    def test_title_and_description_match_the_approved_copy(self):
        source = _source()
        card = self._card_body(source)
        assert "<h3>Header &amp; Data Region</h3>" in card
        assert (
            'class="hint ww-data-prep-region-desc">Specify where the header row '
            "is and which rows contain the data.</p>" in card
        )

    def test_info_box_shows_the_exact_required_message_with_an_icon(self):
        source = _source()
        card = self._card_body(source)
        assert 'class="ww-data-prep-region-info-box"' in card
        assert 'class="ww-data-prep-region-info-icon"' in card
        assert "<svg" in card[card.index('class="ww-data-prep-region-info-icon"'):]
        assert (
            'class="ww-data-prep-region-info-text">Preview and column detection '
            "will use the selected header and data region.</p>" in card
        )

    def test_info_box_uses_existing_accent_wash_token_not_a_new_color(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-region-info-box {", "}")
        assert "background: var(--accent-wash-soft);" in rule
        assert "border-radius: var(--radius);" in rule

    def test_panel_header_wrapper_still_has_exactly_two_top_level_children(self):
        # .ww-data-prep-panel-header is SHARED with Time Axis Setup's own
        # header -- its own flex/space-between rule must not need
        # changing, so this redesign nests the badge+title+description
        # group as ONE new wrapper (content block) alongside the
        # existing (visually-removed) Configure button, never a third
        # top-level flex child.
        source = _source()
        card = self._card_body(source)
        header_start = card.index('class="ww-data-prep-panel-header"')
        header_end = card.index("</div>", card.index('id="wwDataPrepStructureToggleBtn"'))
        header_body = card[header_start:header_end]
        assert 'class="ww-data-prep-region-header"' in header_body
        assert 'id="wwDataPrepStructureToggleBtn"' in header_body

    def test_existing_ids_and_fields_are_all_preserved(self):
        source = _source()
        card = self._card_body(source)
        for element_id in (
            "wwDataPrepStructureToggleBtn",
            "wwDataPrepStructureSummary",
            "wwDataPrepStructureDetails",
            "wwDataPrepHeaderInput",
            "wwDataPrepClearHeaderBtn",
            "wwDataPrepRegionStartInput",
            "wwDataPrepRegionEndInput",
            "wwDataPrepSetRegionBtn",
            "wwDataPrepResetRegionBtn",
        ):
            assert 'id="' + element_id + '"' in card

    def test_data_end_row_helper_text_is_preserved(self):
        source = _source()
        card = self._card_body(source)
        assert "Leave empty for last row" in card

    def test_existing_tooltips_are_preserved_unchanged(self):
        source = _source()
        card = self._card_body(source)
        assert 'data-tooltip-text="The row number containing column headers.' in card
        assert 'data-tooltip-text="The first row of actual data' in card
        assert 'data-tooltip-text="The last row of actual data' in card

    def test_no_javascript_or_backend_contract_functions_were_touched(self):
        # This task is presentational only -- the region-mutation
        # functions/listeners must still exist, unchanged in name/shape.
        source = _source()
        assert "function wwDataPrepApplyHeaderInputIfChanged(" in source
        assert 'document.getElementById("wwDataPrepSetRegionBtn").addEventListener("click"' in source
        assert 'document.getElementById("wwDataPrepClearHeaderBtn")' in source
        assert 'document.getElementById("wwDataPrepResetRegionBtn")' in source


class TestRowFiveHeightAlignmentAndScroll:
    """Height AUTHORITY correction (2026-09-07, second follow-up UAT
    fix): Header & Data Region is the height authority for this row --
    Column Roles must never contribute its own table content height to
    sizing the shared grid row, at any column count. Two earlier
    attempts (a fixed wrap max-height, then a fixed card max-height)
    both guessed a pixel number meant to approximate Header & Data
    Region's height; this correction removes that guesswork entirely.

    `contain: size` on .ww-data-prep-column-roles-card makes this
    card's own content invisible to the grid's row-sizing calculation
    (its content contribution is treated as zero, at any row count), so
    align-items: stretch + flex: 1 1 auto (shared with Header & Data
    Region's own card) size this card to EXACTLY the row height Header
    & Data Region's natural content determines -- no guessed number
    anywhere on desktop/tablet.

    Third follow-up UAT fix (same day): once the SAME 820px breakpoint
    that already stacks row-5-grid into two independent rows fires,
    Header & Data Region and Column Roles no longer share a row for
    `contain: size` to borrow a height from, so containment is reset
    off and the card instead gets a fixed, independent `height: 340px`
    (not a viewport-relative max-height -- that earlier attempt could
    still read as unusably short on a short/landscape viewport, since
    vh tracks viewport height, not the width this breakpoint keys on).
    340px is the ONE deliberate, explicitly-acknowledged fixed pixel
    value in this whole mechanism, used only below this one breakpoint
    where there is no sibling row height left to borrow instead."""

    def test_row_5_grid_stretches_its_two_cards_to_equal_height(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-row-5-grid {", "}")
        assert "align-items: stretch;" in rule
        assert "align-items: start;" not in rule

    def test_cards_inside_row_5_grid_grow_to_fill_the_stretched_row(self):
        source = _source()
        assert ".ww-data-prep-row-5-grid .ww-data-prep-card { overflow-x: auto; flex: 1 1 auto; }" in source

    def test_column_roles_card_carries_its_own_scoping_class(self):
        source = _source()
        assert 'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-column-roles-card"' in source
        assert "<h3>Column Roles " in source
        card_pos = source.index('class="panel ww-cc-panel ww-data-prep-card ww-data-prep-column-roles-card"')
        card_end = source.index("</section>", card_pos)
        assert card_pos < source.index("<h3>Column Roles ") < card_end

    def test_column_roles_card_uses_size_containment_not_a_guessed_max_height(self):
        # The critical behavior: Column Roles' own content must not
        # control the parent row height -- achieved via `contain: size`
        # (zeroes this card's content contribution to the grid's
        # row-sizing calculation), never a hard-coded pixel guess.
        source = _source()
        rule = _function_body(source, ".ww-data-prep-column-roles-card {", "}")
        assert "display: flex;" in rule
        assert "flex-direction: column;" in rule
        assert "contain: size;" in rule
        assert "max-height:" not in rule
        assert "px" not in rule

    def test_column_roles_wrap_fills_whatever_height_the_card_receives(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-column-roles-wrap {", "}")
        assert "max-height:" not in rule
        assert "px" not in rule
        assert "flex: 1 1 0;" in rule
        assert "min-height: 0;" in rule
        assert "overflow-y: auto;" in rule
        assert "overflow-x: auto;" in rule

    def test_column_roles_card_resets_containment_and_gets_a_fixed_height_when_stacked(self):
        # No sibling row to borrow a height from once stacked -- this is
        # the ONE place a fixed pixel height is deliberately used, and
        # containment must be turned back off so the card can use it
        # instead of being zeroed with nothing to stretch it against.
        # Reuses the EXISTING shared 820px breakpoint (the same one
        # row-5-grid itself stacks at) rather than a new/separate one.
        source = _source()
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert ".ww-data-prep-column-roles-card { contain: none; height: 340px; max-height: none; }" in media_820

    def test_column_roles_wrap_behavior_is_restated_inside_the_820px_block(self):
        # Not a NEW rule (the unconditional desktop rule already covers
        # this unchanged) -- just restated in the same 820px block as
        # the card override above so the full small-screen behavior
        # reads in one place, per this task's own request.
        source = _source()
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert (
            ".ww-data-prep-column-roles-wrap { flex: 1 1 0; min-height: 0; overflow-y: auto; overflow-x: auto; }"
            in media_820
        )

    def test_desktop_mechanism_uses_no_guessed_pixel_height(self):
        # The desktop/tablet mechanism (contain: size + stretch) uses no
        # guessed number at all -- regression guard against
        # reintroducing one there (two prior attempts each did). 340px
        # at the stacked breakpoint (previous test) is the one
        # deliberate, explicitly-acknowledged exception, not a silent
        # regression back to guessing.
        source = _source()
        card_rule = _function_body(source, ".ww-data-prep-column-roles-card {", "}")
        wrap_rule = _function_body(source, ".ww-data-prep-column-roles-wrap {", "}")
        assert "px" not in card_rule
        assert "px" not in wrap_rule

    def test_column_roles_table_header_is_sticky_via_the_shared_base_class(self):
        # No NEW sticky rule is added for Column Roles -- its <table>
        # already carries the shared .ww-data-prep-table base class,
        # whose own `thead th` rule already sets position: sticky/top:0/
        # an opaque background. That rule simply had no visible effect
        # here before, since sticky only does anything inside an actual
        # scrolling container.
        source = _source()
        assert 'class="ww-data-prep-table ww-data-prep-columns-table" id="wwDataPrepColumnsTable"' in source
        rule = _function_body(source, ".ww-data-prep-table thead th {", "}")
        assert "position: sticky;" in rule
        assert "top: 0;" in rule
        assert "z-index:" in rule
        assert "background: var(--panel);" in rule

    def test_no_duplicate_sticky_rule_was_added_for_columns_table_th(self):
        # The fix is making the EXISTING sticky rule take effect (via
        # the new max-height/overflow above), not adding a second,
        # redundant position: sticky declaration scoped to
        # .ww-data-prep-columns-table specifically.
        source = _source()
        rule = _function_body(source, "#pageDataPreparation .ww-data-prep-columns-table th {", "}")
        assert "position: sticky" not in rule


class TestRowFiveBColumnRolesRedesign:
    """Row 5B redesign (2026-09-07): Column Roles' own visual redesign
    (numbered step badge + title + description header, striped/
    lighter-bordered table, and a UI-only footer with column count +
    rows-per-page pager) matching an approved mock. Presentational plus
    a purely client-side display-slice pagination over already-loaded
    columns -- no role/EQ/MU semantics, tooltip, or backend contract
    changed. Scoped to Column Roles only; no other row/card in this
    task."""

    def _card_body(self, source: str) -> str:
        start = source.index('class="panel ww-cc-panel ww-data-prep-card ww-data-prep-column-roles-card"')
        end = source.index("</section>", start)
        return source[start:end]

    def test_numbered_step_badge_reads_2_and_is_not_the_workflow_steps_stateful_class(self):
        source = _source()
        card = self._card_body(source)
        assert 'class="ww-data-prep-panel-step-badge"' in card
        badge_start = card.index('class="ww-data-prep-panel-step-badge"')
        badge_end = card.index("</span>", badge_start)
        assert card[badge_start:badge_end].endswith(">2")
        # NOT the workflow strip's own stateful step-number class -- that
        # one is neutral-gray by default and only turns accent-colored
        # via a data-state="active" a workflow step sets on itself; this
        # is a static section badge, always accent-colored. (Checked as
        # an actual class="..." usage, not a bare substring -- this
        # test's own explanatory HTML comment above the badge legitimately
        # names that other class in prose.)
        assert 'class="ww-data-prep-workflow-step-num"' not in card

    def test_step_badge_is_permanently_accent_colored_not_state_dependent(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-panel-step-badge {", "}")
        assert "background: var(--accent);" in rule
        assert "color: #fff;" in rule
        assert "data-state" not in rule

    def test_title_and_description_match_the_approved_copy(self):
        source = _source()
        card = self._card_body(source)
        assert "<h3>Column Roles " in card
        assert (
            'class="hint ww-data-prep-column-roles-desc">Assign a role for each column '
            "and set engineering quantity and unit where applicable.</p>" in card
        )

    def test_existing_tooltip_is_preserved_unchanged(self):
        source = _source()
        card = self._card_body(source)
        assert 'data-tooltip-text="Time Axis — Defines the X-axis.' in card
        assert "Waveform — Creates a Y-axis channel." in card
        assert "ww-info-tip-trigger" in card

    def test_no_search_box_is_present(self):
        source = _source()
        card = self._card_body(source)
        assert "Search columns" not in card
        assert "wwDataPrepColumnSearch" not in card
        assert "<input" not in card

    def test_table_rows_are_striped_with_horizontal_and_light_vertical_borders(self):
        # Scoped to .ww-data-prep-columns-table specifically (its only
        # consumer is this table) -- the shared .ww-data-prep-table base
        # class (Data Preview, Time Axis preview) keeps its own full
        # grid-line borders, unaffected.
        source = _source()
        border_rule = _function_body(
            source,
            ".ww-data-prep-columns-table th,\n        .ww-data-prep-columns-table td {",
            "}",
        )
        assert "border: none;" in border_rule
        assert "border-bottom: 1px solid var(--panel-border);" in border_rule
        assert ".ww-data-prep-columns-table tbody tr:nth-child(even) td { background: var(--surface-tint); }" in source
        base_table_rule = _function_body(source, ".ww-data-prep-table th, .ww-data-prep-table td {", "}")
        assert "border: 1px solid var(--panel-border);" in base_table_rule

    def test_light_vertical_separator_between_columns_skips_the_last_column(self):
        # Refinement (2026-09-07, same day): a subtle vertical divider
        # between columns, reintroduced WITHOUT reverting the row-only
        # horizontal-border rule above (a second, additive rule rather
        # than a duplicated/rewritten border block) -- and never on the
        # last column, which would otherwise double up against the
        # table's own outer edge.
        source = _source()
        rule = _function_body(
            source,
            ".ww-data-prep-columns-table th:not(:last-child),\n        .ww-data-prep-columns-table td:not(:last-child) {",
            "}",
        )
        assert "border-right: 1px solid var(--panel-border);" in rule
        # Scoped to Column Roles only -- the shared .ww-data-prep-table
        # base class (Data Preview, Time Axis preview) must not gain a
        # vertical divider from this change.
        base_table_rule = _function_body(source, ".ww-data-prep-table th, .ww-data-prep-table td {", "}")
        assert "border-right" not in base_table_rule

    def test_footer_shows_column_count_and_pager_matching_the_mock(self):
        source = _source()
        card = self._card_body(source)
        assert 'class="ww-data-prep-columns-footer"' in card
        assert 'id="wwDataPrepColumnsCount"' in card
        assert 'id="wwDataPrepColumnsPageSizeSelect"' in card
        assert 'id="wwDataPrepColumnsRangeLabel"' in card
        assert 'id="wwDataPrepColumnsPrevBtn"' in card
        assert 'id="wwDataPrepColumnsNextBtn"' in card
        footer_start = card.index('class="ww-data-prep-columns-footer"')
        table_wrap_end = card.index("</div>", card.index('class="ww-data-prep-table-wrap ww-data-prep-column-roles-wrap"'))
        assert footer_start > table_wrap_end

    def test_pagination_is_a_ui_only_slice_never_a_second_fetch(self):
        # No backend column-page endpoint exists or is called -- this is
        # purely a display slice over columnCount/columnLabels/
        # columnRoles/etc., which are already fully loaded by the SAME
        # preview fetch Column Roles already reads.
        source = _source()
        clamp_body = _function_body(source, "function wwDataPrepClampColumnsPage() {", "}")
        assert "fetch(" not in clamp_body
        footer_body = _function_body(source, "function wwDataPrepRenderColumnsFooter(", "}\n\n        function wwDataPrepRenderColumnMapping")
        assert "fetch(" not in footer_body
        mapping_body = _function_body(source, "function wwDataPrepRenderColumnMapping() {", "function wwDataPrepSummarizeColumnRoles(")
        assert "fetch(" not in mapping_body

    def test_page_clamps_into_valid_range_both_directions(self):
        source = _source()
        body = _function_body(source, "function wwDataPrepClampColumnsPage() {", "}")
        assert "const totalPages = Math.max(1, Math.ceil(columnCount / pageSize));" in body
        assert "if (wwDataPrep.columnsPage > totalPages) wwDataPrep.columnsPage = totalPages;" in body
        assert "if (wwDataPrep.columnsPage < 1) wwDataPrep.columnsPage = 1;" in body

    def test_data_col_attribute_still_uses_the_true_absolute_column_index(self):
        # Pagination must be a display slice ONLY -- role/EQ/MU change
        # handlers read data-col directly, so it must never become a
        # page-relative index, only ever the real column position.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderColumnMapping() {", "function wwDataPrepSummarizeColumnRoles("
        )
        assert "for (let c = startIndex; c < endIndex; c++) {" in body
        assert 'data-col="\' + c + \'"' in body
        assert "for (let c = 0; c < columnCount; c++) {" not in body

    def test_page_size_change_resets_to_page_one(self):
        source = _source()
        body = _function_body(
            source,
            'document.getElementById("wwDataPrepColumnsPageSizeSelect").addEventListener("change"',
            "});",
        )
        assert "wwDataPrep.columnsPage = 1;" in body
        assert "wwDataPrepRenderColumnMapping();" in body

    def test_prev_and_next_buttons_move_the_page_and_rerender(self):
        source = _source()
        prev_body = _function_body(
            source, 'document.getElementById("wwDataPrepColumnsPrevBtn").addEventListener("click"', "});"
        )
        assert "wwDataPrep.columnsPage -= 1;" in prev_body
        assert "wwDataPrepRenderColumnMapping();" in prev_body
        next_body = _function_body(
            source, 'document.getElementById("wwDataPrepColumnsNextBtn").addEventListener("click"', "});"
        )
        assert "wwDataPrep.columnsPage += 1;" in next_body
        assert "wwDataPrepRenderColumnMapping();" in next_body

    def test_opening_a_new_source_resets_columns_page_but_not_page_size(self):
        source = _source()
        body = _function_body(
            source,
            "async function openDataPreparationWorkspace(sourceId) {",
            "function wwDataPrepRenderWorkflowStrip() {",
        )
        assert "wwDataPrep.columnsPage = 1;" in body
        assert "wwDataPrep.columnsPageSize = " not in body

    def test_role_eq_mu_change_handler_is_unchanged(self):
        # This redesign must not touch the existing role/EQ/MU logic --
        # same delegated "change" listener, same three handler calls.
        source = _source()
        body = _function_body(
            source,
            'document.getElementById("wwDataPrepColumnsTable").addEventListener("change"',
            "});",
        )
        assert "wwDataPrepSetColumnRole(parseInt(roleSelect.dataset.col, 10), roleSelect.value);" in body
        assert (
            "wwDataPrepSetColumnEngineeringQuantity(parseInt(quantitySelect.dataset.col, 10), quantitySelect.value);"
            in body
        )
        assert "wwDataPrepSetColumnMeasuredUnit(parseInt(unitSelect.dataset.col, 10), unitSelect.value);" in body


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
    alone on Row 7 -- the SAME Export/Powerwave elements, re-parented
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
        assert "Go to Powerwave" in final_actions_body

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
        # would otherwise stretch "Go to Powerwave" across the
        # entire page now that this card is alone on a full-width row.
        source = _source()
        body = _function_body(source, ".ww-data-prep-final-actions {", "}")
        assert "justify-content: flex-end" in body
        assert "width: auto" in body

    def test_old_full_width_action_bar_class_is_retired(self):
        source = _source()
        assert 'class="ww-data-prep-action-bar"' not in source


class TestRowSixDataPreviewKeepsResetAllChanges:
    """Row 6 Data Preview polish keeps Reset All Changes contextually tied
    to the table/toolbar it clears."""

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


class TestRawDataPreviewPolish:
    """Raw Data Preview visual polish (2026-09-08): scoped CSS only, with
    no preview data, edit, scrolling, role-badge, or pagination behavior
    changes."""

    def _preview_css(self, source: str) -> str:
        return source[
            source.index("/* ---- Data Preview: compact polished engineering table ----"):
            source.index("/* ---- Row 7: Final Actions ----")
        ]

    def test_preview_card_gets_scoped_spacing_and_title_hierarchy(self):
        source = _source()
        css = self._preview_css(source)
        assert "#pageDataPreparation .ww-data-prep-preview-card {" in css
        assert "padding: 15px 16px 14px;" in css
        assert "#pageDataPreparation .ww-data-prep-preview-card h3" in css
        assert "font-size: 0.9rem;" in css
        assert "#wwDataPrepPreviewHint" in css
        assert "font-size: 0.72rem;" in css
        assert "font-style: normal;" in css

    def test_toolbar_buttons_are_scoped_and_keep_existing_ids(self):
        source = _source()
        css = self._preview_css(source)
        assert 'id="wwDataPrepUndoBtn"' in source
        assert 'id="wwDataPrepRedoBtn"' in source
        assert 'id="wwDataPrepResetAllBtn"' in source
        assert ".ww-data-prep-preview-card .ww-data-prep-toolbar-actions .secondary" in css
        assert "min-height: 30px;" in css
        assert "padding: 7px 12px;" in css
        assert ":disabled" in css

    def test_preview_table_uses_soft_borders_readable_padding_and_stripes(self):
        source = _source()
        css = self._preview_css(source)
        assert ".ww-data-prep-preview-card .ww-data-prep-table-wrap" in css
        assert "overflow: auto" not in css
        assert "max-height: 58vh;" in css
        assert "font-size: 0.74rem;" in css
        assert "line-height: 1.35;" in css
        assert "padding: 5px 10px;" in css
        assert "color-mix(in srgb, var(--panel-border)" in css
        assert "tbody tr:nth-child(even):not(.ww-data-prep-row-is-header):not(.ww-data-prep-row-excluded)" in css
        assert "td:not(.ww-data-prep-cell-modified):not(.ww-data-prep-configured-time-cell)" in css
        assert ".ww-data-prep-preview-card .ww-data-prep-table td.ww-data-prep-cell:hover" in css

    def test_pagination_keeps_existing_controls_with_compact_scoped_styling(self):
        source = _source()
        css = self._preview_css(source)
        for control_id in (
            "wwDataPrepFirstBtn",
            "wwDataPrepPrevBtn",
            "wwDataPrepPageInput",
            "wwDataPrepNextBtn",
            "wwDataPrepLastBtn",
        ):
            assert 'id="' + control_id + '"' in source
        assert ".ww-data-prep-preview-card .ww-data-prep-pagination" in css
        assert "margin-top: 11px;" in css
        assert ".ww-data-prep-preview-card .ww-data-prep-pager" in css
        assert "flex-wrap: wrap;" in css
        assert ".ww-data-prep-preview-card .ww-data-prep-page-input" in css

    def test_column_header_label_format_is_preserved_pending_owner_decision(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTable(preview) {", "function wwDataPrepApplyOverlaySummary",
        )
        assert "wwSpreadsheetColumnLabel(c)" in body
        assert 'const label = wwDataPrep.columnLabels && wwDataPrep.columnLabels[c];' in body
        assert "label ?" in body
        assert "escapeHtml(label)" in body
        assert "roleBadge(role)" in body

    def test_final_action_buttons_are_polished_without_changing_handlers_or_ids(self):
        source = _source()
        final_start = source.index("/* ---- Row 7: Final Actions ----")
        final_css = source[
            final_start:
            source.index(".ww-cc-subtitle", final_start)
        ]
        assert 'id="wwDataPrepExportBtn"' in source
        assert 'id="wwDataPrepConvertBtn"' in source
        assert ".ww-data-prep-final-actions #wwDataPrepExportBtn" in final_css
        assert ".ww-data-prep-final-actions #wwDataPrepConvertBtn" in final_css
        assert "min-height: 42px;" in final_css
        assert "font-weight: 700;" in final_css
        assert 'document.getElementById("wwDataPrepExportBtn").addEventListener("click", () => { wwDataPrepExport(false); });' in source
        assert 'document.getElementById("wwDataPrepConvertBtn").addEventListener("click", () => { wwDataPrepConvert(); });' in source


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
        assert "minmax(0, 1fr) auto minmax(260px, 1fr)" in body

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
    """Row 3 status redesign (2026-09-08): a connected 4-segment
    configuration-status strip with title+helper text, status-aware
    circles, and visible chevron separators. State remains derived from
    existing workspace state, never a second readiness/status engine."""

    def test_four_status_segments_exist_with_stable_ids(self):
        source = _source()
        for segment_id in (
            "wwDataPrepWorkflowSegmentStructure",
            "wwDataPrepWorkflowSegmentRoles",
            "wwDataPrepWorkflowSegmentTimeAxis",
            "wwDataPrepWorkflowSegmentReady",
        ):
            assert 'id="' + segment_id + '"' in source

    def test_row_3_keeps_the_connected_status_strip_container(self):
        source = _source()
        assert (
            'class="ww-data-prep-row ww-data-prep-row-3 ww-data-prep-workflow-strip" id="wwDataPrepWorkflowStrip"'
            in source
        )

    def test_strip_uses_list_semantics_not_a_clickable_stepper_or_wizard_current_step(self):
        source = _source()
        strip_start = source.index('id="wwDataPrepWorkflowStrip"')
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4"', strip_start)
        strip_body = source[strip_start:row4_start]
        assert 'id="wwDataPrepWorkflowStrip" role="list"' in source
        assert strip_body.count('role="listitem"') == 4
        assert "addEventListener" not in strip_body
        assert "<button" not in strip_body
        assert 'aria-current="step"' not in strip_body

    def test_each_step_has_a_title_and_a_helper_line_with_approved_wording(self):
        source = _source()
        expected = [
            ("Header &amp; Data Region", "Configure structure"),
            ("Column Roles", "Assign required roles"),
            ("Time Axis Setup", "Configure time axis"),
            ("Ready to Convert", "Resolve blocking issues"),
        ]
        for title, helper in expected:
            assert '<span class="ww-data-prep-workflow-step-title">' + title + "</span>" in source
            assert '<span class="ww-data-prep-workflow-step-helper">' + helper + "</span>" in source

    def test_each_segment_has_digit_and_checkmark_markers_only(self):
        source = _source()
        assert source.count('class="ww-data-prep-workflow-step-num-digit"') == 4
        assert source.count('class="ww-data-prep-workflow-step-num-check" aria-hidden="true"') == 4
        assert "ww-data-prep-workflow-step-num-warning" not in source
        body = _function_body(source, ".ww-data-prep-workflow-step-num-check", "}")
        assert "display: none" in body
        complete_body = _function_body(
            source,
            '.ww-data-prep-workflow-step[data-state="complete"] .ww-data-prep-workflow-step-num-digit',
            "}",
        )
        assert "display: none" in complete_body

    def test_three_chevron_separators_exist_between_the_four_steps(self):
        source = _source()
        strip_start = source.index('id="wwDataPrepWorkflowStrip"')
        row4_start = source.index('class="ww-data-prep-row ww-data-prep-row-4"', strip_start)
        strip_body = source[strip_start:row4_start]
        assert strip_body.count('class="ww-data-prep-workflow-chevron" aria-hidden="true"') == 3

    def test_chevrons_remain_nonsemantic_and_visible_as_separators(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-workflow-chevron {", "}")
        assert "display: flex" in body
        assert 'aria-hidden="true"' in source
        assert "border-left: 1px solid rgba(148, 163, 184, 0.16)" in body

    def test_outer_container_is_a_connected_segmented_grid(self):
        source = _source()
        body = _function_body(source, ".ww-data-prep-workflow-strip {", "}")
        assert "display: grid" in body
        assert "minmax(0, 1fr) 22px minmax(0, 1fr) 22px minmax(0, 1fr) 22px minmax(0, 1fr)" in body
        assert "background: var(--panel)" in body
        assert "border: 1px solid var(--panel-border)" in body
        assert "overflow: hidden" in body
        connector = _function_body(source, ".ww-data-prep-workflow-strip::before {", "}")
        assert "content: none" in connector

    def test_incomplete_and_complete_states_style_the_whole_segment_and_circles(self):
        source = _source()
        assert '.ww-data-prep-workflow-step[data-state="incomplete"] { background: var(--accent-wash-soft); }' in source
        assert (
            '.ww-data-prep-workflow-step[data-state="complete"] { background: color-mix(in srgb, var(--ok) 7%, var(--panel)); }'
            in source
        )
        assert (
            '.ww-data-prep-workflow-step[data-state="incomplete"] .ww-data-prep-workflow-step-num { background: var(--accent); border-color: var(--accent); color: #fff; }'
            in source
        )
        assert (
            '.ww-data-prep-workflow-step[data-state="complete"] .ww-data-prep-workflow-step-num { background: var(--ok); border-color: var(--ok); color: #fff; }'
            in source
        )

    def test_row_3_uses_only_blue_green_and_neutral_state_colors(self):
        source = _source()
        row3_css = source[
            source.index("/* ---- Row 3 redesign: connected configuration-status strip ----"):
            source.index("/* ---- Row 5 shared column-wrapper ----")
        ]
        assert 'data-state="attention"' not in row3_css
        assert "var(--warn)" not in row3_css
        assert '.ww-data-prep-workflow-step[data-state="incomplete"] { background: var(--accent-wash-soft); }' in row3_css
        assert (
            '.ww-data-prep-workflow-step[data-state="complete"] { background: color-mix(in srgb, var(--ok) 7%, var(--panel)); }'
            in row3_css
        )

    def test_status_derivation_reads_existing_state_only(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepStatusSegmentStates()", "function wwDataPrepRenderWorkflowStrip()",
        )
        assert "fetch(" not in body
        assert "wwDataPrepEffectiveIssueSummary()" in body
        assert "wwDataPrepIssueCodeSet(summary)" in body
        assert 'roles.includes("time_axis")' in body
        assert 'roles.includes("waveform")' in body
        assert "wwDataPrep.timeAxisSummary && wwDataPrep.timeAxisSummary.status" in body
        assert "summary && summary.is_ready" in body
        assert 'document.getElementById("wwDataPrepConversionAction").hidden' not in body

    def test_structure_status_uses_applied_overlay_structure_not_data_region_warning(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepStatusSegmentStates()", "function wwDataPrepRenderWorkflowStrip()",
        )
        assert "const hasAppliedStructure = wwDataPrep.headerRowNumber != null || wwDataPrep.dataStartRow != null;" in body
        assert "const structureConfigured = hasAppliedStructure;" in body
        assert "wwDataPrep.headerRowNumber != null &&" not in body
        assert "wwDataPrep.dataStartRow != null" in body
        assert 'codes.has("data_region_unconfigured")' not in body

    def test_roles_segment_reflects_time_axis_and_waveform_role_state(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepStatusSegmentStates()", "function wwDataPrepRenderWorkflowStrip()",
        )
        assert 'rolesSegment = { state: "complete", helper: "Roles assigned" };' in body
        assert 'rolesSegment = { state: "incomplete", helper: "Waveform role required" };' in body
        assert 'rolesSegment = { state: "incomplete", helper: "Assign required roles" };' in body

    def test_time_axis_segment_preserves_dec_083_dirty_and_manual_states_as_blue_incomplete(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepStatusSegmentStates()", "function wwDataPrepRenderWorkflowStrip()",
        )
        assert 'codes.has("time_axis_unsaved_changes")' in body
        assert 'timeAxis = { state: "incomplete", helper: "Unsaved changes" };' in body
        assert 'helper: "Unsaved changes"' in body
        assert 'codes.has("time_axis_manual_unresolved")' in body
        assert 'timeAxisStatus === "review_required"' in body
        assert 'timeAxisStatus === "needs_attention"' in body
        assert 'timeAxis = { state: "incomplete", helper: timeAxisStatus === "review_required" ? "Review required" : "Resolve time axis" };' in body
        assert 'state: "attention"' not in body

    def test_warning_but_ready_state_uses_summary_is_ready_for_ready_segment(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepStatusSegmentStates()", "function wwDataPrepRenderWorkflowStrip()",
        )
        assert 'const ready = summary && summary.is_ready' in body
        assert '{ state: "complete", helper: "Ready" }' in body
        assert "warning_count" not in body
        assert "info_count" not in body

    def test_render_function_is_called_after_issues_structure_and_pagination_render(self):
        source = _source()
        for anchor in (
            'function wwDataPrepRenderIssues()',
        ):
            body = _function_body(source, anchor, "function wwDataPrepIsIndexOnlyWithoutInterval()")
            assert "wwDataPrepRenderWorkflowStrip();" in body

    def test_render_function_applies_accessible_status_text_to_each_segment(self):
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderWorkflowStrip()", "\n\n        // Section 22:",
        )
        assert 'el.removeAttribute("aria-current");' in body
        assert "helperEl.textContent = helper;" in body
        assert 'el.setAttribute("aria-label", title + ": " + helper);' in body
        assert "wwDataPrepWorkflowSegmentReady" in body

    def test_very_small_screen_hides_helper_text_but_keeps_titles(self):
        # Owner-explicit preference: retain step TITLES for as long as
        # reasonably possible on small screens -- numbers alone provide
        # weak workflow context. Only the helper description is hidden.
        source = _source()
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert ".ww-data-prep-workflow-step-helper { display: none; }" not in media_820
        workflow_small_screen = source[source.index("/* Very small screen (~390px and below):"):]
        media_480 = _function_body(workflow_small_screen, "@media (max-width: 480px) {", "/* ---- Data Preview:")
        assert ".ww-data-prep-workflow-step-helper { display: none; }" in media_480
        assert ".ww-data-prep-workflow-step-title { display: none; }" not in media_480
        assert "wwDataPrepWorkflowSegmentStructure" not in media_480


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
        # Row 5-time-axis (2026-09-07): the panel is now its own
        # full-width row, closed by its own dedicated comment rather
        # than Row 5's (which now ends right after Column Roles).
        end = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
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

    def test_advanced_options_and_time_details_stay_distinct(self):
        # Superseded by the Row 7 redesign (2026-09-07): the separate
        # "Advanced details" accordion (#wwDataPrepTimeAxisAdvanced) is
        # retired -- its useful fields consolidated into the new,
        # always-visible Time Details column instead (see
        # TestRowSevenTimeAxisRedesign below). Advanced Options
        # (configuration WORKFLOWS) and Time Details (read-only
        # technical facts) must still never be merged into one concept
        # -- kept as a negative check so a regression re-adding the old
        # accordion, or collapsing the two concepts together, is caught.
        source = _source()
        panel = self._panel_body(source)
        assert 'id="wwDataPrepTimeAxisAdvancedOptions"' in panel
        assert 'id="wwDataPrepTimeAxisAdvanced"' not in panel
        assert 'id="wwDataPrepTimeAxisDetailsCol"' in panel
        assert panel.index('id="wwDataPrepTimeAxisAdvancedOptions"') != panel.index('id="wwDataPrepTimeAxisDetailsCol"')

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
        # Row 5-time-axis (2026-09-07): the panel is now its own
        # full-width row, closed by its own dedicated comment rather
        # than Row 5's (which now ends right after Column Roles).
        end = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
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

    def test_advanced_options_keeps_its_own_collapse(self):
        # Superseded by the Row 7 redesign (2026-09-07): Advanced
        # details' own separate <details> collapse is retired along
        # with the accordion itself (see
        # test_advanced_options_and_time_details_stay_distinct above);
        # Advanced Options keeps its own, unchanged.
        source = _source()
        panel = self._panel_body(source)
        assert '<details class="ww-data-prep-time-axis-advanced-options" id="wwDataPrepTimeAxisAdvancedOptions">' in panel
        assert '<details class="ww-data-prep-time-axis-advanced" id="wwDataPrepTimeAxisAdvanced">' not in panel


class TestTimeAxisSetupStatusCardAndDetectSpacing:
    """UAT fix (2026-09-06): the old bare "TIME FORMAT"/"TIME COLUMN"
    metadata pair is visually retired (still populated, computation
    reused rather than duplicated) in favor of one compact status card
    -- icon + adaptive headline + one detail line -- and Detect gets a
    dedicated margin so it no longer sits flush against whichever
    conditional field precedes it."""

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        # Row 5-time-axis (2026-09-07): the panel is now its own
        # full-width row, closed by its own dedicated comment rather
        # than Row 5's (which now ends right after Column Roles).
        end = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
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
        body = _function_body(source, "function wwDataPrepRenderTimeAxisValidity() {", "function wwDataPrepRenderTimeAxisDetailsRow(")
        assert 'getElementById("wwDataPrepTimeAxisSummaryInterpretation")' in body
        assert 'getElementById("wwDataPrepTimeAxisSummaryColumns")' in body
        assert '" rows"' not in body
        assert "approximately " not in body

    def test_detect_button_row_has_its_own_top_margin(self):
        # Owner-authored spacing tweak (2026-09-07): tightened from the
        # original 14px to 5px -- still its own deliberate, non-zero gap
        # from whichever conditional field sits above it, just denser.
        source = _source()
        panel = self._panel_body(source)
        assert 'class="ww-data-prep-structure-controls ww-data-prep-time-axis-detect-row"' in panel
        rule_start = source.index(".ww-data-prep-time-axis-detect-row {")
        rule_end = source.index("}", rule_start)
        assert "margin-top: 5px" in source[rule_start:rule_end]


class TestRowSevenTimeAxisRedesign:
    """Row 7 redesign (2026-09-07): Time Axis Setup gets a numbered step
    badge + title + description header (reusing the shared
    .ww-data-prep-panel-step-badge), a right-aligned status pill/
    selected-column chip/Advanced Options, and a 3-section body (Time
    Format | Sample Preview | Time Details) replacing the old 2-section
    split. The former separate "Advanced details" accordion is retired;
    its useful fields are consolidated into the new, always-visible Time
    Details column, omitting any field that does not apply to the
    current interpreter rather than showing a "-" placeholder.
    Presentational/information-architecture only -- every existing
    #wwDataPrep* id, event handler, and backend contract is preserved or
    explicitly re-parented (never duplicated)."""

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        end = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
        return source[start:end]

    def test_numbered_step_badge_reads_3_and_reuses_the_shared_badge_class(self):
        source = _source()
        panel = self._panel_body(source)
        assert 'class="ww-data-prep-panel-step-badge"' in panel
        badge_start = panel.index('class="ww-data-prep-panel-step-badge"')
        badge_end = panel.index("</span>", badge_start)
        assert panel[badge_start:badge_end].endswith(">3")
        # No second badge style -- same class Header & Data Region/
        # Column Roles already use, defined exactly once in the sheet.
        assert source.count(".ww-data-prep-panel-step-badge {") == 1

    def test_header_description_matches_the_approved_copy(self):
        source = _source()
        panel = self._panel_body(source)
        assert (
            'class="hint ww-data-prep-time-axis-header-desc">Configure how time '
            "is interpreted from the selected column.</p>" in panel
        )

    def test_header_status_pill_is_synced_from_the_same_readiness_state(self):
        # Never a second readiness computation -- the header status
        # element is written by the SAME function that already computes
        # wwDataPrepRenderTimeAxisValidity()'s state.
        source = _source()
        panel = self._panel_body(source)
        assert 'id="wwDataPrepTimeAxisHeaderStatus"' in panel
        assert 'id="wwDataPrepTimeAxisHeaderStatusIcon"' in panel
        assert 'id="wwDataPrepTimeAxisHeaderStatusText"' in panel
        sync_body = _function_body(source, "function wwDataPrepSyncTimeAxisHeaderStatus(state, icon) {", "}")
        assert 'getElementById("wwDataPrepTimeAxisHeaderStatus")' in sync_body

    def test_selected_column_chip_was_removed_from_the_header(self):
        # UAT fix (2026-09-07): the header's selected-column pill is
        # retired -- redundant with the status badge (already shows
        # configured/unconfigured) and the Time Format section's own
        # resolved-column field. wwDataPrepRenderTimeAxisSummary()'s own
        # columnsEl/columnIndices computation (still feeding the
        # validity detail line and Time Details) is UNCHANGED -- only
        # the extra write to this now-removed chip is gone.
        source = _source()
        panel = self._panel_body(source)
        assert 'id="wwDataPrepTimeAxisHeaderColumn"' not in panel
        assert "ww-data-prep-time-axis-header-column {" not in source
        summary_body = _function_body(source, "function wwDataPrepRenderTimeAxisSummary() {", "}")
        assert "headerColumnEl" not in summary_body
        assert "columnsEl.textContent" in summary_body
        assert "None selected" in summary_body

    def test_advanced_options_moved_into_header_actions_unchanged_ids(self):
        source = _source()
        panel = self._panel_body(source)
        header_start = panel.index('class="ww-data-prep-panel-header"')
        header_end = panel.index("</div>\n                    <!--", header_start) if "</div>\n                    <!--" in panel[header_start:] else panel.index("wwDataPrepTimeAxisSummary")
        header_body = panel[header_start:header_end]
        assert 'class="ww-data-prep-time-axis-header-actions"' in header_body
        assert 'id="wwDataPrepTimeAxisAdvancedOptions"' in header_body
        assert 'id="wwDataPrepTimeAxisUseReconstructedBtn"' in header_body
        assert 'id="wwDataPrepTimeAxisUseManualBtn"' in header_body
        # Still exactly one instance of each -- moved, not duplicated.
        assert panel.count('id="wwDataPrepTimeAxisAdvancedOptions"') == 1
        assert panel.count('id="wwDataPrepTimeAxisUseReconstructedBtn"') == 1

    def test_advanced_options_force_open_and_use_buttons_are_unchanged(self):
        # No JS change to Advanced Options' own behavior from the move --
        # same force-open call, same explicit-action buttons.
        source = _source()
        assert 'document.getElementById("wwDataPrepTimeAxisAdvancedOptions").open = true;' in source
        assert 'wwDataPrepSelectAdvancedInterpreter("repeated_timestamp_precision_loss");' in source
        assert 'wwDataPrepSelectAdvancedInterpreter("manual");' in source

    def test_body_has_three_sections_at_the_approved_ratio(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-time-axis-body {", "}")
        assert "display: grid" in rule
        assert "minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 0.9fr)" in rule
        assert "align-items: stretch;" in rule

    def test_form_preview_and_details_are_the_three_direct_children_in_order(self):
        source = _source()
        panel = self._panel_body(source)
        body_start = panel.index('class="ww-data-prep-time-axis-body"')
        form_pos = panel.index('id="wwDataPrepTimeAxisForm"', body_start)
        preview_pos = panel.index('id="wwDataPrepTimeAxisPreviewCol"', body_start)
        details_pos = panel.index('id="wwDataPrepTimeAxisDetailsCol"', body_start)
        assert body_start < form_pos < preview_pos < details_pos

    def test_section_titles_match_time_format_sample_preview_time_details(self):
        source = _source()
        panel = self._panel_body(source)
        form_start = panel.index('id="wwDataPrepTimeAxisForm"')
        preview_start = panel.index('id="wwDataPrepTimeAxisPreviewCol"')
        details_start = panel.index('id="wwDataPrepTimeAxisDetailsCol"')
        assert "Time Format" in panel[form_start:preview_start]
        assert "Sample Preview" in panel[preview_start:details_start]
        assert "(first 10 rows)" in panel[preview_start:details_start]
        assert "Time Details" in panel[details_start:]

    def test_preview_table_and_form_delegated_listener_still_share_the_details_ancestor(self):
        # #wwDataPrepTimeAxisDetails's own delegated input/change listener
        # depends on #wwDataPrepTimeAxisForm's fields staying its
        # descendants -- confirm the 3-column body (and therefore the
        # form) is still nested inside #wwDataPrepTimeAxisDetails.
        source = _source()
        details_start = source.index('<div id="wwDataPrepTimeAxisDetails">')
        panel = self._panel_body(source)
        panel_end_pos = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
        details_body = source[details_start:panel_end_pos]
        assert 'id="wwDataPrepTimeAxisForm"' in details_body
        assert 'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("input"' in source
        assert 'document.getElementById("wwDataPrepTimeAxisDetails").addEventListener("change"' in source

    def test_preview_table_has_a_row_number_column_from_real_backend_data(self):
        # row_number is real data TimeAxisPreviewRowOut already returns
        # (backend/app/schemas/time_axis.py) -- not an invented column.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetectResult(detection, previewRows) {",
            "function wwDataPrepRenderTimeAxisElapsedAndIndexFields(summary) {",
        )
        assert '"<thead><tr><th>Row</th><th>Source value</th><th>Interpreted time</th></tr></thead><tbody>"' in body
        assert "cell(row.row_number)" in body
        assert '<th>Row</th><th>Date source</th><th>Time source</th><th>Interpreted time</th>' in body

    def test_heading_reflects_the_actual_10_row_render_cap(self):
        # Follow-up UAT fix (2026-09-07): the heading previously said
        # "first 5 rows" while the backend's own _TIME_AXIS_PREVIEW_LIMIT
        # (time_axis_service.py) actually returns up to 20 -- the render
        # cap below is what makes the heading's own claim true, not the
        # backend fetch itself.
        source = _source()
        panel = self._panel_body(source)
        preview_start = panel.index('id="wwDataPrepTimeAxisPreviewCol"')
        assert "(first 10 rows)" in panel[preview_start:]
        assert "(first 5 rows)" not in panel

    def test_preview_rows_are_capped_at_10_before_rendering_never_paginated(self):
        # A frontend-only render slice -- never a second/different
        # backend fetch, never pagination (this preview stays a single,
        # small confirmation sample, same as before).
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetectResult(detection, previewRows) {",
            "function wwDataPrepRenderTimeAxisElapsedAndIndexFields(summary) {",
        )
        assert "const cappedPreviewRows = previewRows.slice(0, 10);" in body
        assert "for (const row of cappedPreviewRows) {" in body
        assert "for (const row of previewRows) {" not in body
        assert "wwDataPrepColumnsPageSizeSelect" not in body
        assert "wwDataPrepColumnsPrevBtn" not in body

    def test_preview_table_and_wrap_use_full_available_width(self):
        # The base .ww-data-prep-table class sets no width at all -- a
        # plain <table> only ever shrinks to its own content, which was
        # the actual cause of the table using only part of the section's
        # width. No per-column width is set here, so the browser's own
        # default table-layout still distributes the full width across
        # Row/Source value/Interpreted time naturally.
        source = _source()
        assert ".ww-data-prep-time-axis-preview-table { width: 100%; }" in source
        wrap_rule = _function_body(source, ".ww-data-prep-time-axis-preview-col .ww-data-prep-table-wrap {", "}")
        assert "width: 100%;" in wrap_rule
        # No fixed pixel width anywhere in either rule that would stop
        # the table/wrap from expanding to fill the section.
        assert "width: 100%; flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: auto;" in source

    def test_saving_a_sample_time_axis_never_clears_the_preview_table(self):
        # Regression guard (2026-09-07): the disappearing-after-Save bug.
        # wwDataPrepRenderTimeAxisDetectResult()'s own `if (!previewRows)`
        # branch used to unconditionally wipe #wwDataPrepTimeAxisPreviewTable
        # even when `detection` (guaranteed truthy at that point -- the
        # `if (!detection)` branch above it already returned otherwise)
        # represented a real, just-saved config -- Save calls
        # wwDataPrepRenderTimeAxisForm(), which calls this with
        # (summary, null), and the table's own rows from the user's
        # prior explicit Detect must survive that call untouched.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetectResult(detection, previewRows) {",
            "function wwDataPrepRenderTimeAxisElapsedAndIndexFields(summary) {",
        )
        no_preview_rows_branch = body[body.index("if (!previewRows) {"):body.index("// Task section 7:")]
        assert 'previewTable.innerHTML = "";' not in no_preview_rows_branch
        # The truly-unconfigured case (detection itself falsy) still
        # correctly clears everything, including the table -- untouched
        # by this fix, checked separately from the branch above.
        unconfigured_branch = body[body.index("if (!detection) {"):body.index("if (!previewRows) {")]
        assert 'previewTable.innerHTML = "";' in unconfigured_branch

    def test_form_render_auto_fetches_preview_once_per_opened_source(self):
        # An already-applied sample-interpreter Time Axis gets a real
        # preview on reload without requiring a manual Detect click --
        # reuses the SAME wwDataPrepDetectTimeAxis() a manual click
        # already calls (never a second preview/detection engine), and
        # is consumed (never fires again) after the first render so it
        # does not redundantly re-fetch on every one of this page's
        # other, unrelated mutations that also re-render this form.
        source = _source()
        body = _function_body(
            source, "function wwDataPrepRenderTimeAxisForm() {", "async function wwDataPrepFetchTimeAxis() {"
        )
        assert "const shouldAutoFetchPreview = wwDataPrep.timeAxisPreviewNeedsInitialFetch;" in body
        assert "wwDataPrep.timeAxisPreviewNeedsInitialFetch = false;" in body
        assert "if (shouldAutoFetchPreview) {" in body
        assert "wwDataPrepDetectTimeAxis();" in body
        # The flag is consumed unconditionally near the top of the
        # function -- before the sample-interpreter branch that reads
        # it -- so an unconfigured first render still uses it up rather
        # than leaving it to fire later, after an intervening Save.
        assert body.index("wwDataPrep.timeAxisPreviewNeedsInitialFetch = false;") < body.index(
            "if (shouldAutoFetchPreview) {"
        )

    def test_preview_needs_initial_fetch_flag_resets_when_a_source_is_opened(self):
        source = _source()
        assert "timeAxisPreviewNeedsInitialFetch: true," in source
        body = _function_body(
            source,
            "async function openDataPreparationWorkspace(sourceId) {",
            "function wwDataPrepRenderWorkflowStrip() {",
        )
        assert "wwDataPrep.timeAxisPreviewNeedsInitialFetch = true;" in body

    def test_preview_table_is_striped_with_light_vertical_and_horizontal_borders(self):
        # Same treatment as Column Roles' own redesign, scoped to this
        # table's own class only -- Data Preview keeps its full grid.
        source = _source()
        assert 'class="ww-data-prep-table ww-data-prep-time-axis-preview-table" id="wwDataPrepTimeAxisPreviewTable"' in source
        border_rule = _function_body(
            source,
            ".ww-data-prep-time-axis-preview-table th,\n        .ww-data-prep-time-axis-preview-table td {",
            "}",
        )
        assert "border-bottom: 1px solid var(--panel-border);" in border_rule
        assert (
            ".ww-data-prep-time-axis-preview-table tbody tr:nth-child(even) td { background: var(--surface-tint); }"
            in source
        )
        base_table_rule = _function_body(source, ".ww-data-prep-table th, .ww-data-prep-table td {", "}")
        assert "border-right" not in base_table_rule

    def test_preview_table_fills_available_height_and_scrolls_internally(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-time-axis-preview-col .ww-data-prep-table-wrap {", "}")
        assert "flex: 1 1 auto;" in rule
        assert "min-height: 0;" in rule
        assert "overflow-y: auto;" in rule

    def test_preview_table_gets_a_fixed_height_when_stacked(self):
        source = _source()
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert ".ww-data-prep-time-axis-preview-col .ww-data-prep-table-wrap { flex: 0 0 auto; height: 260px; }" in media_820

    def test_time_details_column_exists_with_every_row_hidden_by_default(self):
        source = _source()
        panel = self._panel_body(source)
        details_start = panel.index('id="wwDataPrepTimeAxisDetailsCol"')
        details_section_end = panel.index('id="wwDataPrepTimeAxisStatus"', details_start)
        details_body = panel[details_start:details_section_end]
        for row_id, dd_id in (
            ("wwDataPrepTimeAxisDetailsInterpreterRow", "wwDataPrepTimeAxisAdvInterpreter"),
            ("wwDataPrepTimeAxisDetailsFamilyRow", "wwDataPrepTimeAxisAdvFamily"),
            ("wwDataPrepTimeAxisDetailsProvenanceRow", "wwDataPrepTimeAxisAdvProvenance"),
            ("wwDataPrepTimeAxisDetailsFormatRow", "wwDataPrepTimeAxisAdvFormat"),
            ("wwDataPrepTimeAxisDetailsRateRow", "wwDataPrepTimeAxisAdvRate"),
            ("wwDataPrepTimeAxisDetailsSpacingRow", "wwDataPrepTimeAxisAdvSpacing"),
            ("wwDataPrepTimeAxisDetailsConfidenceRow", "wwDataPrepTimeAxisAdvConfidence"),
            ("wwDataPrepTimeAxisDetailsStatusRow", "wwDataPrepTimeAxisAdvStatus"),
            ("wwDataPrepTimeAxisDetailsDiagnosticsRow", "wwDataPrepTimeAxisAdvDiagnostics"),
        ):
            assert ('<div id="' + row_id + '" hidden>') in details_body
            assert ('id="' + dd_id + '"') in details_body
        # No static "-" placeholder text baked into the markup -- every
        # dd starts empty, populated (or left hidden) only by JS.
        assert "—</dd>" not in details_body

    def test_validity_status_card_relocated_unchanged_to_the_bottom_of_time_details(self):
        source = _source()
        panel = self._panel_body(source)
        # Exactly one instance -- moved, not duplicated.
        assert panel.count('id="wwDataPrepTimeAxisValidity"') == 1
        details_start = panel.index('id="wwDataPrepTimeAxisDetailsCol"')
        validity_pos = panel.index('id="wwDataPrepTimeAxisValidity"')
        assert validity_pos > details_start

    def test_time_details_row_helper_hides_rows_with_no_value_never_shows_a_dash(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetailsRow(rowId, ddId, text) {",
            "}",
        )
        assert "row.hidden = !text;" in body
        assert '"—"' not in body
        assert "'—'" not in body

    def test_interpreter_row_reuses_the_shared_interpreter_label_map(self):
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetails(detection) {",
            "function wwDataPrepRenderTimeAxisFieldVisibility() {",
        )
        assert "WW_DATA_PREP_INTERPRETER_LABELS[interpreterId]" in body

    def test_sampling_rate_and_spacing_only_apply_to_sample_index_and_reconstructed_time(self):
        # Reuses the SAME interval_seconds/resolved_interval_seconds
        # fallback wwDataPrepRenderTimeAxisDetectResult()'s own summary
        # line already reads -- never a second, independently-fetched
        # interval value. Every other interpreter (Date & Time, Date +
        # Time, Time of Day, Elapsed Time, Manual) has no real interval,
        # so both rows stay hidden for them.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisDetails(detection) {",
            "function wwDataPrepRenderTimeAxisFieldVisibility() {",
        )
        assert 'detection.family === "sample_index" || detection.interpreter_id === "repeated_timestamp_precision_loss"' in body
        assert "resolved_interval_seconds != null ? detection.resolved_interval_seconds : detection.interval_seconds" in body
        assert "(1 / intervalSeconds).toFixed(3) + \" Hz\"" in body
        assert "(intervalSeconds * 1000).toFixed(3) + \" ms\"" in body

    def test_renamed_function_updated_at_all_three_call_sites(self):
        # wwDataPrepRenderTimeAxisAdvancedDetails() renamed to
        # wwDataPrepRenderTimeAxisDetails() -- same 3 call sites, no
        # stale CALL to the old name left (a few explanatory comments
        # legitimately still name it for historical context, so this
        # checks actual call syntax, not a bare substring).
        source = _source()
        assert "function wwDataPrepRenderTimeAxisDetails(detection) {" in source
        assert source.count("wwDataPrepRenderTimeAxisDetails(") >= 3
        assert "wwDataPrepRenderTimeAxisAdvancedDetails(null);" not in source
        assert "wwDataPrepRenderTimeAxisAdvancedDetails(detection);" not in source
        assert "wwDataPrepRenderTimeAxisAdvancedDetails(summary);" not in source

    def test_dead_advanced_details_accordion_css_was_removed(self):
        # Verified unused before removal (no consumer left in the DOM) --
        # regression guard against the retired accordion's own CSS
        # silently reappearing detached from any markup.
        source = _source()
        assert ".ww-data-prep-time-axis-advanced-body {" not in source
        assert ".ww-data-prep-time-axis-advanced summary {" not in source
        # The still-used Advanced Options card style is untouched.
        assert ".ww-data-prep-time-axis-advanced-option-card {" in source


class TestRowFiveTimeAxisOwnRow:
    """Time Axis Setup layout refinement (2026-09-07): Time Axis Setup
    moves out of Row 5's 1:3:1 grid into its own full-width row directly
    below Row 5, and its own internals split into a controls column
    (left) and an interpreter preview-table column (right) on wide
    screens, stacking to one column at the same 820px breakpoint Row 5
    itself stacks at. Every existing #wwDataPrep* id/function/behavior
    (DEC-082, DEC-083, Detect/Save/Clear, Advanced options/details) is
    unchanged -- this is a DOM move + restyle only."""

    def _panel_section_tag(self, source: str) -> str:
        panel_id_pos = source.index('id="wwDataPrepTimeAxisPanel"')
        tag_start = source.rindex("<section", 0, panel_id_pos)
        return source[tag_start:panel_id_pos]

    def _panel_body(self, source: str) -> str:
        start = source.index('id="wwDataPrepTimeAxisPanel"')
        end = source.index("<!-- /ww-data-prep-row-5-time-axis (Time Axis Setup) -->")
        return source[start:end]

    def test_panel_is_its_own_full_width_row_not_a_row_5_grid_child(self):
        source = _source()
        tag = self._panel_section_tag(source)
        assert "ww-data-prep-row" in tag
        assert "ww-data-prep-row-5-time-axis" in tag
        assert "ww-data-prep-config-col" not in tag
        assert "ww-data-prep-row-5-grid" not in tag

    def test_panel_sits_after_row_5_grid_and_before_row_6(self):
        source = _source()
        row5_grid_end = source.index("<!-- /ww-data-prep-row-5-grid (Row 5) -->")
        panel_pos = source.index('id="wwDataPrepTimeAxisPanel"')
        row6_pos = source.index(
            'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-preview-card ww-data-prep-row ww-data-prep-row-6"'
        )
        assert row5_grid_end < panel_pos < row6_pos

    def test_form_and_preview_column_are_wrapped_in_the_split_body(self):
        source = _source()
        panel = self._panel_body(source)
        body_start = panel.index('class="ww-data-prep-time-axis-body"')
        form_pos = panel.index('id="wwDataPrepTimeAxisForm"')
        preview_col_pos = panel.index('id="wwDataPrepTimeAxisPreviewCol"')
        assert body_start < form_pos < preview_col_pos

    def test_preview_table_moved_out_of_detect_fields_into_its_own_column(self):
        source = _source()
        panel = self._panel_body(source)
        detect_fields_start = panel.index('id="wwDataPrepTimeAxisDetectFields"')
        detect_fields_end = panel.index('id="wwDataPrepTimeAxisConfirmedField"')
        detect_fields_body = panel[detect_fields_start:detect_fields_end]
        assert 'id="wwDataPrepTimeAxisPreviewTable"' not in detect_fields_body

        preview_col_start = panel.index('id="wwDataPrepTimeAxisPreviewCol"')
        preview_col_tag_end = panel.index(">", preview_col_start)
        preview_col_tag = panel[preview_col_start:preview_col_tag_end]
        assert "hidden" in preview_col_tag
        preview_col_end = panel.index("</table>", preview_col_start)
        assert 'id="wwDataPrepTimeAxisPreviewTable"' in panel[preview_col_start:preview_col_end]

    def test_split_body_is_a_two_column_grid_on_wide_screens(self):
        source = _source()
        rule = _function_body(source, ".ww-data-prep-time-axis-body {", "}")
        assert "display: grid" in rule
        assert "grid-template-columns:" in rule

    def test_split_stacks_to_one_column_at_the_shared_820px_breakpoint(self):
        source = _source()
        media_1180 = _function_body(source, "@media (max-width: 1180px) {", "@media (max-width: 820px) {")
        assert ".ww-data-prep-time-axis-body" not in media_1180
        media_820 = _function_body(source, "@media (max-width: 820px) {", "/* Very small screen")
        assert '.ww-data-prep-time-axis-body { grid-template-columns: 1fr; }' in media_820

    def test_preview_column_visibility_mirrors_detect_fields_in_the_same_function(self):
        # Moving the table out of #wwDataPrepTimeAxisDetectFields means
        # its own `.hidden` toggle no longer covers the table -- the
        # SAME function must set an identical condition on the new
        # preview column, never a second/independent visibility rule.
        source = _source()
        body = _function_body(
            source,
            "function wwDataPrepRenderTimeAxisInterpreterFields() {",
            "document.getElementById(\"wwDataPrepTimeAxisSplitColumnsRow\")",
        )
        detect_line = 'document.getElementById("wwDataPrepTimeAxisDetectFields").hidden = isPlaceholder || !isSample;'
        preview_line = 'document.getElementById("wwDataPrepTimeAxisPreviewCol").hidden = isPlaceholder || !isSample;'
        assert detect_line in body
        assert preview_line in body
        assert body.index(detect_line) < body.index(preview_line)

    def test_preview_column_starts_hidden_matching_detect_fields_initial_state(self):
        source = _source()
        panel = self._panel_body(source)
        assert '<div id="wwDataPrepTimeAxisDetectFields" hidden>' in panel
        assert '<div class="ww-data-prep-time-axis-preview-col" id="wwDataPrepTimeAxisPreviewCol" hidden>' in panel


class TestSevenRowLayoutFoundation:
    """Approved layout (2026-09-06, revised 2026-09-07): the page is
    organized into eight semantic horizontal rows now that Time Axis
    Setup has its own full-width row (ww-data-prep-row-5-time-axis)
    between Row 5 (now a 1:3 Header & Data Region | Column Roles grid,
    down from 1:3:1) and Row 6 (Raw Data Preview, unaffected)."""

    def test_exactly_eight_rows_exist(self):
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
                'class="panel ww-cc-panel ww-data-prep-card ww-data-prep-time-axis-card ww-data-prep-row ww-data-prep-row-5-time-axis" id="wwDataPrepTimeAxisPanel"'
            )
            == 1
        )
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
