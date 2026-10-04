"""Static structural regression checks for the Event Reconstruction
frontend: the Slice 0 shell (page, left panel, waveform workspace shell,
toolbar), the Slice 2 selection workflow wired to the Event
Reconstruction API (records as independent members, DEC-128), and the
boundaries both must keep with the shared Waveform engine."""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
THEME_CSS = Path(__file__).resolve().parents[2] / "frontend" / "theme.css"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _between(source: str, start_token: str, end_token: str) -> str:
    start = source.index(start_token)
    end = source.index(end_token, start)
    return source[start:end]


def _nav_list(source: str) -> str:
    return _between(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')


def _er_page(source: str) -> str:
    return _between(source, '<section id="pageEventReconstruction"', "<!-- Recordings page (Phase 3B)")


def _er_module(source: str) -> str:
    """The Event Reconstruction JS module, with `//` comments removed so
    checks see code only (its comments name the Waveform functions it
    deliberately avoids)."""
    module = _between(source, "// Event Reconstruction (DEC-123 Slice 0 shell; DEC-125 Slice 2", "// Phase 3B: Recordings page (section 5/8/9)")
    return "\n".join(line.split("//", 1)[0] for line in module.splitlines())


def _workspace_row(source: str) -> str:
    return _between(source, '<div id="workspaceRow" hidden>', '<section id="pageEventReconstruction"')


class TestEventReconstructionNavigation:
    def test_menu_entry_exists_with_label(self):
        nav = _nav_list(_source())
        assert 'id="mainNavEventReconstructionBtn"' in nav
        assert 'title="Event Reconstruction"' in nav
        assert '<span class="shell-nav-label">Event Reconstruction</span>' in nav

    def test_menu_entry_is_immediately_after_waveform(self):
        nav = _nav_list(_source())
        ids = re.findall(r'class="shell-nav-item" id="(mainNav\w+Btn)"', nav)
        waveform_index = ids.index("mainNavWaveformBtn")
        assert ids[waveform_index + 1] == "mainNavEventReconstructionBtn"

    def test_full_main_nav_order(self):
        nav = _nav_list(_source())
        ids = re.findall(r'class="shell-nav-item" id="(mainNav\w+Btn)"', nav)
        assert ids == [
            "mainNavRecordingsBtn",
            "mainNavWaveformBtn",
            "mainNavEventReconstructionBtn",
            "mainNavTableBtn",
            "mainNavCalculatedChannelsBtn",
            "mainNavAnalysisBtn",
            "mainNavComplianceBtn",
            "mainNavCalculatorBtn",
        ]

    def test_shell_set_current_page_handles_event_reconstruction(self):
        source = _source()
        body = _between(source, "function shellSetCurrentPage(page) {", "function shellSetSidebarDrawerOpen(open)")
        assert 'page !== "event-reconstruction"' in body
        assert 'document.getElementById("pageEventReconstruction").hidden = page !== "event-reconstruction";' in body
        assert 'setShellNavCurrent("mainNavEventReconstructionBtn", page === "event-reconstruction");' in body
        assert 'if (page === "event-reconstruction") {\n                wwErOnPageEntered();' in body
        assert (
            'document.getElementById("mainNavEventReconstructionBtn").addEventListener'
            '("click", () => shellSetCurrentPage("event-reconstruction"));'
        ) in source

    def test_every_existing_page_is_still_switched(self):
        body = _between(_source(), "function shellSetCurrentPage(page) {", "function shellSetSidebarDrawerOpen(open)")
        for element_id, page in (
            ("workspaceRow", "waveform"),
            ("pageRecordings", "recordings"),
            ("pageCalculatedChannels", "calculated-channels"),
            ("pageDataPreparation", "data-preparation"),
            ("pageAnalysis", "analysis"),
            ("pageCompliance", "compliance"),
            ("pageCalculator", "calculator"),
        ):
            assert f'document.getElementById("{element_id}").hidden = page !== "{page}";' in body


class TestEventReconstructionPageShell:
    def test_page_is_a_hidden_sibling_of_the_waveform_workspace_row(self):
        source = _source()
        assert '<section id="pageEventReconstruction" aria-label="Event Reconstruction" hidden>' in source
        # Never nested inside the Waveform workspace row.
        assert "pageEventReconstruction" not in _workspace_row(source)

    def test_left_panel_has_reconstruction_and_record_sections(self):
        page = _er_page(_source())
        assert '<aside id="wwErSidebar" aria-label="Event Reconstruction records">' in page
        assert 'id="wwErDefinitionHeading">Reconstruction <span id="wwErMemberCountBadge" class="count-badge">(0)</span></h2>' in page
        for element_id in ("wwErNotices", "wwErMembersPanel", "wwErClearBtn", "wwErStatus", "wwErRecordsPanel"):
            assert f'id="{element_id}"' in page
        assert 'id="wwErRecordsHeading">Records <span id="wwErRecordsCountBadge" class="count-badge">(0)</span></h2>' in page
        assert "wwErGroups" not in page and "Time Groups" not in page
        assert 'class="shell-split-handle" id="wwErSplitHandle"' in page
        assert 'id="wwErSidebarBackdrop"' in page

    def test_main_waveform_workspace_shell_exists(self):
        page = _er_page(_source())
        assert 'id="wwErMain"' in page
        assert '<div class="ww-toolbar" id="wwErToolbar">' in page
        assert 'id="wwErViewArea"' in page
        assert 'class="ww-er-canvas" id="wwErCanvas"' in page
        assert '<div class="ww-tg-panels" id="wwErPanels"></div>' in page
        assert 'id="wwErEmptyState"' in page
        assert "not available yet." not in _between(page, 'id="wwErEmptyState"', "</p>")

    def test_waveform_keeps_the_only_main_element(self):
        page = _er_page(_source())
        assert "<main" not in page

    def test_standard_interaction_controls_exist(self):
        """DEC-141: every general waveform tool is now a compact icon
        button in the global header, not a text button. DEC-144: Box Zoom
        is retired (no drag-mode toggle at all -- Pan is the only
        plot-area mode); Reset Time View is renamed Autoscale X."""
        page = _er_page(_source())
        assert 'id="wwErDragModeZoomBtn"' not in page and 'id="wwErDragModePanBtn"' not in page
        assert 'id="wwErZoomInBtn" title="Zoom In — Time Axis" aria-label="Zoom In — Time Axis" disabled>' in page
        assert 'id="wwErZoomOutBtn" title="Zoom Out — Time Axis" aria-label="Zoom Out — Time Axis" disabled>' in page
        assert 'id="wwErResetViewBtn" title="Autoscale X" aria-label="Autoscale X" disabled>' in page
        assert ">Zoom In</button>" not in page and ">Zoom Out</button>" not in page
        assert ">Reset Time View</button>" not in page and 'title="Reset Time View"' not in page

    def test_controls_reuse_waveform_toolbar_markup_classes(self):
        """DEC-141: every one of these controls now lives in the global
        header (#wwErToolbar); the Reconstruction Timeline canvas no
        longer has its own copy (#wwErCanvasToolbar is gone). DEC-144:
        there is no drag-mode toggle at all any more (Box Zoom retired)."""
        page = _er_page(_source())
        assert 'id="wwErDragModeToggle"' not in page
        assert '<div class="ww-split-btn" id="wwErAnnotateSplit">' in page  # the one remaining split-btn family
        assert 'class="ww-icon-btn ww-tg-reset-view-btn" id="wwErResetViewBtn"' in page
        assert 'id="wwErCanvasToolbar"' not in page
        assert 'class="ww-tg-toolbar"' not in _between(page, '<section class="ww-er-canvas"', "</section>")

    def test_shares_waveform_layout_css(self):
        # The ER selector is listed first so each original Waveform
        # selector still directly precedes its own `{` (existing Waveform
        # CSS guard tests match that exact shape).
        source = _source()
        assert "#pageEventReconstruction,\n        #workspaceRow {" in source
        assert "#wwErSidebar,\n        #workspaceSidebar {" in source
        assert "#wwErMain,\n        #mainWorkspace {" in source
        assert "#wwErViewArea,\n        #activeViewArea {" in source
        assert "#pageEventReconstruction.shell-sidebar-open #wwErSidebar,\n            #workspaceRow.shell-sidebar-open #workspaceSidebar { transform: translateX(0); }" in source
        assert "#wwErSidebar {\n    scrollbar-color: var(--scrollbar-thumb) var(--bg);\n}" in THEME_CSS.read_text(encoding="utf-8")


class TestEventReconstructionKeepsWaveformBoundaries:
    def test_canvas_never_uses_the_waveform_time_group_canvas_class(self):
        # Waveform iterates `.ww-time-group-canvas` document-wide; the
        # shell must never be picked up as a Waveform Time Group.
        assert "ww-time-group-canvas" not in _er_page(_source())

    def test_module_never_touches_waveform_engine_state_or_interactions(self):
        module = _er_module(_source())
        assert not re.search(r"\bww\.", module)
        for forbidden in ("wwStepZoomX(", "wwStepZoomY(", "wwResetOneTimeGroupView(", "wwWireTimeGroupToolbar("):
            assert forbidden not in module

    def test_drag_mode_is_pan_only_and_never_toggled(self):
        """DEC-144: Box Zoom is retired -- there is no wwErSetDragMode()
        left to call (or exist) since there is no longer a mode to
        switch TO. wwErState.dragMode stays the fixed "pan" it is
        initialised to; Plotly's own dragmode layout property reads it
        via wwErPanelLayout(), not a runtime setter."""
        source = _source()
        assert "wwErSetDragMode" not in source and "wwErApplyDragMode" not in source
        assert 'dragMode: "pan",' in _between(source, "const wwErState = {", "\n        };")

    def test_no_event_reconstruction_channel_presentation_store(self):
        source = _source()
        module = _er_module(source)
        state = _between(source, "const wwErState = {", "};")
        keys = re.findall(r"^ {12}(\w+):", state.split("{", 1)[1], re.MULTILINE)
        # Workspace state, the last API responses and (Slice 3C) the
        # renderer's own plot state only.
        assert keys == [
            "dragMode", "timeDisplay", "unitMode", "perUnit", "sources", "records", "definition",
            "channelsBySource", "calculatedChannels", "selectedChannels", "activeRecordId", "annotationUi", "loadSeq", "busy", "plot",
        ]
        plot_keys = re.findall(r"^ {16}(\w+):", state.split("plot: {", 1)[1], re.MULTILINE)
        assert plot_keys == [
            "viewMode", "axisStates", "panels", "viewport", "fitAll", "atFitAll", "origin", "relayoutTimer",
            "cursors", "cursorRequests", "cursorValuesTimer", "activeAxisKey", "activeAxisQuantity",
        ]
        for forbidden in ("PresentationOverrides", "channelColors", "ColorOverride", "DisplayName =", "localStorage"):
            assert forbidden not in module
        # The only ER-owned persisted value is the left panel width; the
        # rest are renderer constants.
        assert re.findall(r"const (?:WW_ER_|wwEr)\w+", module) == [
            "const WW_ER_SIDEBAR_WIDTH_STORAGE_KEY", "const wwErState", "const WW_ER_PANEL_HEIGHT",
            "const WW_ER_COMBINED_PANEL_HEIGHT", "const WW_ER_COMBINED_AXIS_ADVISORY",
            "const WW_ER_Y_AXIS_TITLE_FONT_SIZE", "const WW_ER_SECONDS_PER_DAY", "const WW_ER_ABSOLUTE_TICK_STEPS",
            "const WW_ER_MONTHS", "const WW_ER_UNKNOWN_QUANTITY_LABEL", "const WW_ER_PU_UNAVAILABLE_CELL", "const WW_ER_PU_UNAVAILABLE_CELL_TITLE", "const WW_ER_ORIGIN_MAX_SPANS", "const WW_ER_RELAYOUT_DEBOUNCE_MS", "const WW_ER_TIME_AXIS_TITLE",
            "const WW_ER_OUTLIER_GAP_FRACTION", "const WW_ER_SPAN_UNITS",
        ]

    def test_left_panel_never_reuses_waveform_channel_tree_or_sync_state(self):
        module = _er_module(_source())
        for forbidden in (
            "renderAnalogGroup", "renderDigitalGroup", "channel-row--toggle", "wwSourceSyncBadgeHtml",
            "/synchronization", "wwOpenSyncModal", "source-recording-sync-badge",
        ):
            assert forbidden not in module

    def test_panels_live_only_in_the_event_reconstruction_canvas(self):
        module = _er_module(_source())
        # Slice 3C plots into #wwErPanels only, never a Time Group canvas
        # or Waveform's panel registry/pipeline.
        assert 'document.getElementById("wwErPanels")' in module
        for forbidden in ("ww-time-group-canvas", "wwEnsureTimeGroupCanvasDom", "wwCreatePanelDom(", "wwInitPanelPlot(",
                          "wwLoadChannelRange(", "wwApplyAndFetchGroupViewport(", "wwWirePanelRelayout(", "#wwTimeGroupCanvases"):
            assert forbidden not in module

    def test_page_entry_and_refresh_read_only_existing_lists(self):
        source = _source()
        entered = _between(source, "async function wwErOnPageEntered() {", "\n        }\n")
        assert "await wwErRefresh();" in entered
        refresh = _between(source, "async function wwErRefresh() {", "async function wwErOnPageEntered()")
        assert 'fetchSourcesList(), wwErFetchJson("/records"), wwErFetchJson("/definition"),' in refresh
        assert "if (seq !== wwErState.loadSeq) return;" in refresh

    def test_waveform_toolbar_controls_keep_their_slice_0_status(self):
        page = _er_page(_source())
        for element_id in ("wwErZoomInBtn", "wwErZoomOutBtn", "wwErResetViewBtn"):
            assert re.search(rf'id="{element_id}"[^>]*disabled', page)

    def test_sidebar_drawer_targets_the_current_page_row(self):
        source = _source()
        helper = _between(source, "function shellSidebarDrawerRowEl() {", "\n        }\n")
        assert 'shell.currentPage === "event-reconstruction" ? "pageEventReconstruction" : "workspaceRow"' in helper
        assert 'document.getElementById("wwErSidebarBackdrop").addEventListener("click", () => shellSetSidebarDrawerOpen(false));' in source


class TestEventReconstructionSelectionWorkflow:
    """Slice 2 (DEC-125, DEC-128): the left panel is driven by the Event
    Reconstruction API only."""

    def test_api_base_is_the_event_reconstruction_router(self):
        url = _between(_source(), "function wwErApiUrl(path) {", "\n        }\n")
        assert '"/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/event-reconstruction" + path' in url

    def test_every_write_is_one_of_the_api_endpoints(self):
        module = _er_module(_source())
        writes = re.findall(r'wwErMutate\("(\w+)", "([^"]+)"', module)
        assert sorted(set(writes)) == sorted({
            ("PUT", "/definition"),
            ("PUT", "/definition/reference"),
            ("DELETE", "/definition"),
            ("POST", "/definition/annotations"),  # DEC-136
            ("PUT", "/definition/annotations/"),
            ("DELETE", "/definition/annotations/"),
        })
        path = _between(_source(), "function wwErCorrectionPath(recordId) {", "\n        }\n")
        assert 'return "/definition/records/" + encodeURIComponent(recordId) + "/correction";' in path
        assert re.findall(r'wwErMutate\("(\w+)", wwErCorrectionPath\(recordId\)', module) == ["PUT", "DELETE"]
        assert module.count('"/correction"') == 1

    def test_records_are_sorted_chronologically_with_ineligible_after(self):
        sort = _between(_source(), "function wwErSortedRecords() {", "function wwErMembershipBlockedReason()")
        assert "Date.parse(a.start_time_utc) - Date.parse(b.start_time_utc)" in sort
        assert "filter((r) => r.eligible)" in sort and "filter((r) => !r.eligible)" in sort

    def test_ineligible_records_show_the_backend_reason_and_no_add_action(self):
        row = _between(_source(), "function wwErRecordRowHtml(record) {", "function wwErRender()")
        assert "record.reason_message" in row
        assert 'data-reason-code="' in row
        assert '\'<span class="ww-er-badge">Not eligible</span>\'' in row
        add = row.index('wwErActionButton("add-record"')
        assert row.rfind("record.eligible", 0, add) != -1

    def test_membership_changes_never_drop_stale_members_implicitly(self):
        source = _source()
        blocked = _between(source, "function wwErMembershipBlockedReason() {", "// ---- Formatting ----")
        assert "Choose a current member as reference first." in blocked
        assert "Remove the stale members first." in blocked
        for name, nxt in (("function wwErAddRecord(recordId) {", "function wwErRemoveMember(recordId)"),
                          ("function wwErRemoveMember(recordId) {", "function wwErRemoveStale()")):
            assert "wwErMembershipBlockedReason()" in _between(source, name, nxt)

    def test_stale_corrections_are_shown_but_never_transferred(self):
        source = _source()
        module = _er_module(source)
        # A removed record has no successor: no re-confirmation, no
        # candidate records, no carried-over corrections.
        for forbidden in ("Reconfirm", "reconfirm", "candidate_group_ids", "previousCorrections"):
            assert forbidden not in module
        remove_stale = _between(source, "function wwErRemoveStale() {", "function wwErMakeReference(recordId)")
        assert "wwErPutDefinition(wwErCurrentMembers().map((m) => m.record_id), reference.record_id)" in remove_stale
        assert "correction_s" not in remove_stale
        member_row = _between(source, "function wwErMemberRowHtml(member) {", "function wwErRecordRowHtml(record)")
        assert "(kept, not applied)" in member_row

    def test_corrections_use_the_existing_millisecond_conversion_point(self):
        module = _er_module(_source())
        assert "correction_s: wwSyncMsToOffsetSeconds(ms)" in module
        assert "wwSyncOffsetToMsDisplay(correctionS)" in module

    def test_reference_is_only_changed_by_explicit_api_call(self):
        module = _er_module(_source())
        assert 'wwErMutate("PUT", "/definition/reference", { record_id: recordId })' in module
        assert module.count("/definition/reference") == 1

    def test_clear_uses_a_confirmation_overlay(self):
        source = _source()
        assert '<div class="confirm-overlay" id="wwErClearConfirmOverlay" hidden>' in source
        assert 'id="wwErClearConfirmBtn">Clear reconstruction</button>' in source
        assert 'document.getElementById("wwErClearBtn").addEventListener("click", wwErOpenClearConfirm);' in source

    def test_workspace_changes_trigger_a_refresh_only_when_the_page_is_current(self):
        source = _source()
        notify = _between(source, "function wwErNotifyWorkspaceChanged() {", "\n        }\n")
        assert 'if (shell.currentPage === "event-reconstruction") wwErRefresh();' in notify
        assert "wwErNotifyWorkspaceChanged();" in _between(source, "async function refreshAllSourceViews() {", "async function refreshSourceList()")
        # Records never depend on Synchronise Sources (DEC-128), so a
        # sync change is not an Event Reconstruction trigger.
        assert "wwErNotifyWorkspaceChanged();" not in _between(
            source, "async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId) {", "function wwRefreshSourceSyncBadges()"
        )

    def test_large_gap_warning_comes_from_the_backend_response(self):
        notices = _between(_source(), "function wwErNoticesHtml() {", "function wwErMemberRowHtml(member)")
        assert "wwErState.definition.warnings" in notices
        # The backend's own threshold DECISION (whether a gap triggers this
        # warning at all) and its two raw numbers (gap_s/threshold_s) are
        # unchanged and still authoritative; the human-friendly TEXT is
        # built client-side from those numbers (style: improve event
        # reconstruction large-gap time formatting) -- the backend's own
        # pre-rendered raw-seconds `.message` string is no longer shown.
        assert "warning.gap_s" in notices and "warning.threshold_s" in notices
        assert "wwErFormatSpan(warning.gap_s)" in notices
        assert "wwErFormatSpan(warning.threshold_s)" in notices
        assert "warning.message" not in notices
        assert "3600" not in _er_module(_source())


class TestEventReconstructionChannelBrowser:
    """Slice 2A: the member channel tree mirrors the Waveform tree, inherits
    presentation read-only, and keeps its own selection state."""

    def test_waveform_and_event_reconstruction_share_one_grouping_rule(self):
        source = _source()
        analog = _between(source, "function renderAnalogGroup(channels, source, timebase) {", "const DIGITAL_GROUP_LABELS")
        digital = _between(source, "function renderDigitalGroup(channels, source, timebase) {", "function renderChannelTable(")
        calculated = _between(source, "function wwRenderCalculatedChannelsSidebarSection() {", "// Phase 5A-UAT (extended Phase 5A-UAT6)")
        tree = _between(source, "function wwErSourceTreeHtml(member, sourceId, open) {", "function wwErMemberTreeHtml(member)")
        assert "wwGroupChannelsByEngineeringType(channels)" in analog
        assert "wwGroupDigitalChannelsByClassification(channels)" in digital
        assert "wwGroupChannelsByEngineeringType(channels)" in calculated
        assert "wwGroupChannelsByEngineeringType(analog)" in tree
        assert "wwGroupChannelsByEngineeringType(calculated)" in tree
        # No second grouping implementation anywhere in Event Reconstruction:
        # the tree uses Waveform's helper; the Grouped View's panels use the
        # backend's display axis and only Waveform's ANALOG_GROUP_ORDER for
        # their order (DEC-131).
        module = _er_module(source)
        assert module.count("ANALOG_GROUP_ORDER") == 2
        groups = _between(source, "function wwErPlotGroups(items) {", "\n        }\n")
        assert groups.count("ANALOG_GROUP_ORDER") == 2

    def test_tree_reuses_waveform_tree_markup_and_name_cells(self):
        tree = _between(_source(), "function wwErSourceTreeHtml(member, sourceId, open) {", "function wwErMemberTreeHtml(member)")
        assert 'class="source-recording"' in tree
        assert "renderChannelTable(" in tree
        assert "analogChannelNameCellHtml({ source_id: sourceId }, c)" in tree
        assert "analogChannelNameCellHtml({ source_id: c.id }, c)" in tree
        assert '"Analog Channels"' in tree and '"Calculated Channels"' in tree
        helpers = _between(_source(), "function wwErChannelGroupHtml(", "function wwErSourceTreeHtml(")
        assert 'class="channel-group"' in helpers and 'class="channel-subgroup" open' in helpers

    def test_calculated_channels_sit_under_their_timing_parent(self):
        tree = _between(_source(), "function wwErSourceTreeHtml(member, sourceId, open) {", "function wwErMemberTreeHtml(member)")
        assert "wwErState.calculatedChannels.filter((c) => c.reference_source_id === sourceId)" in tree
        assert 'wwErChannelRowAttrs(member.record_id, "calculated", c.id, c.name, c.reference_source_id)' in tree

    def test_presentation_is_read_only(self):
        module = _er_module(_source())
        for forbidden in (
            "wwSetChannelDisplayName", "wwResetChannelDisplayName", "wwSetChannelColorOverride",
            "wwResetChannelColorOverride", "wwOpenChannelContextMenu", "contextmenu", 'type="color"',
            "Rename", "Change colour", "wwCreateCalculatedChannel", "wwDeleteCalculatedChannel",
        ):
            assert forbidden not in module
        assert "wwChannelDisplayName(row.dataset.erSourceId, row.dataset.erChannelName)" in module
        # The only direct POSTs are read-only queries -- cursor values
        # (Slice 3E) and, for annotations (DEC-137), Waveform's sample-anchor
        # and peak-value endpoints: nothing is created, renamed or recoloured
        # from here (annotation writes go through wwErMutate()).
        assert module.count('method: "POST"') == 3
        values = _between(_source(), "async function wwErRefreshCursorValues() {", "\n        }\n\n")
        assert 'method: "POST"' in values
        assert '"/calculated-channels/cursor-values"' in values and '"/cursor-values"' in values

    def test_rows_never_use_waveform_row_classes_or_attributes(self):
        attrs = _between(_source(), "function wwErChannelRowAttrs(", "function wwErChannelGroupHtml(")
        assert 'class="ww-er-channel-row ww-er-channel-row--unselected"' in attrs
        for forbidden in ("channel-row--toggle", "channel-row--hidden", "data-channel-kind", "data-source-id", "data-channel-name"):
            assert forbidden not in attrs
        module = _er_module(_source())
        assert "group-toggle-btn\"" not in module.replace("ww-er-group-toggle-btn", "")
        assert "#channelGroups" not in module

    def test_selection_is_event_reconstruction_state_only(self):
        source = _source()
        set_row = _between(source, "function wwErSetRowSelected(row, selected) {", "function wwErToggleChannelRow(row)")
        assert "wwErState.selectedChannels[key] = {" in set_row
        assert "delete wwErState.selectedChannels[key];" in set_row
        plotting = _between(source, "function wwErSelectedChannelsForPlotting() {", "function wwErMemberRowHtml(member)")
        assert "wwErCurrentMembers()" in plotting
        assert "current.has(selection.recordId)" in plotting
        assert "recordId: row.dataset.erRecordId," in set_row

    def test_stale_members_get_no_channel_tree(self):
        row = _between(_source(), "function wwErMemberRowHtml(member) {", "function wwErRecordRowHtml(record)")
        current_branch, stale_branch = row.split("} else {", 1)
        assert "wwErMemberTreeHtml(member)" in current_branch
        assert "wwErMemberTreeHtml" not in stale_branch.split("return '<div", 1)[0]
        assert "Channel selection is unavailable for a removed record." in stale_branch

    def test_expand_state_is_local_to_event_reconstruction(self):
        render = _between(_source(), "function wwErRender() {", "function wwErHandleAction(button)")
        assert 'membersPanel.querySelectorAll("details[data-er-expand-key]")' in render
        assert "wwCaptureChannelTreeExpandState" not in render and "wwRestoreChannelTreeExpandState" not in render

    def test_group_toggle_does_not_toggle_its_details(self):
        source = _source()
        wiring = _between(source, 'document.getElementById("wwErSidebar").addEventListener("click", (event) => {', 'document.getElementById("wwErClearBtn")')
        assert 'button.dataset.erAction === "toggle-channel-group"' in wiring
        assert "event.preventDefault();" in wiring and "event.stopPropagation();" in wiring

    def test_row_and_group_toggle_styles_are_shared_with_waveform(self):
        source = _source()
        assert ".ww-er-channel-row,\n        .channel-row--toggle { cursor: pointer; }" in source
        assert ".ww-er-channel-row--unselected,\n        .channel-row--hidden { opacity: 0.25; }" in source
        assert ".ww-er-group-toggle-btn,\n        .group-toggle-btn {" in source


class TestEventReconstructionIsAnalogOnly:
    """DEC-127: Event Reconstruction accepts native and calculated analog
    channels only; Waveform's digital behaviour is unchanged."""

    def test_tree_has_no_digital_channels(self):
        source = _source()
        tree = _between(source, "function wwErSourceTreeHtml(member, sourceId, open) {", "function wwErMemberTreeHtml(member)")
        for forbidden in ("digital_channels", "Digital Channels", "wwGroupDigitalChannelsByClassification", "DIGITAL_GROUP_LABELS", '"digital"'):
            assert forbidden not in tree
        assert "wwErDigitalNameCellHtml" not in source

    def test_only_analog_and_calculated_kinds_are_accepted(self):
        source = _source()
        kinds = _between(source, "function wwErIsReconstructionChannelKind(kind) {", "function wwErChannelSelectionKey(")
        assert 'return kind === "analog" || kind === "calculated";' in kinds
        set_row = _between(source, "function wwErSetRowSelected(row, selected) {", "function wwErToggleChannelRow(row)")
        assert "if (selected && wwErIsReconstructionChannelKind(row.dataset.erKind)) {" in set_row
        plotting = _between(source, "function wwErSelectedChannelsForPlotting() {", "function wwErMemberRowHtml(member)")
        assert "wwErIsReconstructionChannelKind(selection.kind)" in plotting
        refresh = _between(source, "async function wwErRefresh() {", "async function wwErOnPageEntered()")
        assert "!wwErIsReconstructionChannelKind(selection.kind)" in refresh

    def test_waveform_digital_browser_is_unchanged(self):
        source = _source()
        digital = _between(source, "function renderDigitalGroup(channels, source, timebase) {", "function renderChannelTable(")
        assert "wwGroupDigitalChannelsByClassification(channels)" in digital
        assert "digitalChannelNameCellHtml(source.source_id, c)" in digital
        assert "digitalChannelRowAttrs(source, c, timebase)" in digital


class TestEventReconstructionTimeMapping:
    """Slice 3B: one authoritative frontend mapping, fed by the backend's
    total_reconstruction_offset_s; nothing plots yet."""

    def test_mapping_pair_reuses_the_shared_offset_helpers(self):
        source = _source()
        forward = _between(source, "function wwErSourceElapsedToReconstructionTime(elapsedSeconds, totalOffsetS) {", "\n        }\n")
        inverse = _between(source, "function wwErReconstructionTimeToSourceElapsed(reconstructionSeconds, totalOffsetS) {", "\n        }\n")
        assert "return wwSourceElapsedToViewportTime(elapsedSeconds, totalOffsetS);" in forward
        assert "return wwViewportTimeToSourceElapsed(reconstructionSeconds, totalOffsetS);" in inverse

    def test_source_timing_reads_backend_totals_for_current_members_only(self):
        timing = _between(_source(), "function wwErSourceTiming(displaySourceId) {", "\n        }\n")
        assert "const timingSourceId = calculated ? calculated.reference_source_id : displaySourceId;" in timing
        assert "for (const member of wwErCurrentMembers()) {" in timing
        assert "member.source_timings || []" in timing
        assert "totalOffsetS: timing.total_reconstruction_offset_s," in timing
        # No second timing model: no origin/placement arithmetic in the frontend.
        for forbidden in ("start_time_utc", "recorded_placement_s", "within_record_offset_s +", "correction_s"):
            assert forbidden not in timing
        assert "recordId: member.record_id," in timing

    def test_mapping_arithmetic_is_not_repeated_elsewhere_in_the_module(self):
        module = _er_module(_source())
        assert module.count("total_reconstruction_offset_s") == 1


class TestEventReconstructionRecordModel:
    """DEC-128: every member is an independently imported record; the
    frontend never consumes Waveform Time Groups for Event Reconstruction."""

    def test_module_never_reads_time_groups_or_group_identities(self):
        module = _er_module(_source())
        for forbidden in (
            "/time-groups", "timeGroups", "group_id", "group_ids", "member_id", "memberId",
            "membership_fingerprint", "current_group_id", "Time Group", "wwErGroup",
        ):
            assert forbidden not in module

    def test_rows_and_actions_are_keyed_by_record_id(self):
        source = _source()
        row = _between(source, "function wwErRecordRowHtml(record) {", "function wwErRender()")
        assert "' data-record-id=\"' + escapeHtml(record.record_id) + '\"" in row
        assert 'ww-er-record-row' in row
        member_row = _between(source, "function wwErMemberRowHtml(member) {", "function wwErRecordRowHtml(record)")
        assert "const idAttr = ' data-record-id=\"' + escapeHtml(member.record_id) + '\"';" in member_row
        actions = _between(source, "function wwErHandleAction(button) {", "function wwErOpenClearConfirm()")
        assert "const recordId = button.dataset.recordId;" in actions
        assert 'case "add-record": return wwErAddRecord(recordId);' in actions
        assert "wwErSetCorrection(event.target.dataset.recordId, event.target);" in source

    def test_channel_tree_is_per_record(self):
        source = _source()
        assert 'const base = "record:" + member.record_id + ":source:" + sourceId;' in source
        assert 'data-er-expand-key="record:\' + escapeHtml(member.record_id)' in source
        assert "' data-er-record-id=\"' + escapeHtml(recordId) + '\"' +" in source
        assert "function wwErChannelSelectionKey(recordId, sourceId, channelName) {" in source

    def test_canvas_counts_records(self):
        chrome = _between(_source(), "function wwErSyncPlotChrome() {", "function wwErPlottedRecordIntervals()")
        assert '" record selected" : " records selected"' in chrome
        assert '" channel" : " channels"' in chrome and '" panel" : " panels"' in chrome


class TestEventReconstructionPlotting:
    """Slice 3C (DEC-127 Option B): Event Reconstruction's own renderer over
    the shared helpers -- analog only, engineering units, the Slice 3B
    mapping and one numerical plotting origin."""

    def test_render_uses_the_shared_helpers(self):
        module = _er_module(_source())
        for helper in ("wwFetchWaveformRange(request)", "wwAnalogLineTrace({", "wwAnalogPanelLayout(wwThemeColors(), {",
                       "wwPanelMarkupHtml(\"\")", "wwPointBudgetForPlotWidth(wwPlotWidthForChart(panel.chartEl))",
                       "wwClampPanWindowToBounds(fitAll, start, end)", "wwClampRangeToBounds(fitAll, start, end)",
                       "wwTickValuesForRange(viewport.start, viewport.end, 7)"):
            assert helper in module
        # No second fetch, abort or reduction implementation.
        for forbidden in ("/waveform", "new AbortController", "point_budget", "envelope("):
            assert forbidden not in module
        # The renderer's only direct requests are the cursor-values query
        # and the annotation anchor / peak-value queries (DEC-137); waveform
        # data only ever comes through wwFetchWaveformRange().
        plotting = _between(_source(), "// ---- Slice 3C: the reconstruction renderer", "function wwErMemberRowHtml(member)")
        assert plotting.count("await fetch(") == 3
        annotations = _between(_source(), "// ---- Event Reconstruction annotations (DEC-136, DEC-137) ----", "// ---- Slice 3E: global A/B cursors (DEC-130) ----")
        assert annotations.count("await fetch(") == 2
        assert "/waveform" not in annotations
        assert "await fetch(url, { method: \"POST\"" in _between(_source(), "async function wwErRefreshCursorValues() {", "\n        }\n\n")

    def test_fetch_is_engineering_units_with_the_slice_3b_mapping_only(self):
        source = _source()
        request = _between(source, "function wwErFetchRequestFor(trace, timing, viewport, pointBudget) {", "\n        }\n")
        # DEC-138: the trace's own unit_mode ("per_unit" only for a channel
        # whose resolution is "configured"); the backend converts.
        assert "unitMode: trace.unitMode," in request
        assert "timeOffsetS: 0," in request
        assert "wwErReconstructionTimeToSourceElapsed(viewport.start, timing.totalOffsetS)" in request
        assert "wwErReconstructionTimeToSourceElapsed(viewport.end, timing.totalOffsetS)" in request
        assert "if (timing.endS < viewport.start || timing.startS > viewport.end) return null;" in request
        load = _between(source, "async function wwErLoadTrace(trace) {", "function wwErPlottedTraces()")
        assert "body.time.map((t) => wwErSourceElapsedToReconstructionTime(t, timing.totalOffsetS))" in load
        assert "if (result.superseded || trace.removed) return;" in load
        module = _er_module(source)
        for forbidden in ("unitMode: ww", "ww.unitMode", "wwAlignmentOffset", "effective_alignment", "alignment_offset_s", "digital-waveform",
                          "wwRebuildDigitalChart", "start_time_utc +", "Date.parse(timing"):
            assert forbidden not in module

    def test_one_plotting_origin_for_every_panel(self):
        source = _source()
        to_x = _between(source, "function wwErReconstructionToPlotX(reconstructionSeconds, origin) {", "\n        }\n")
        assert "return reconstructionSeconds - origin;" in to_x
        from_x = _between(source, "function wwErPlotXToReconstruction(plotX, origin) {", "\n        }\n")
        assert "return Number(plotX) + origin;" in from_x
        module = _er_module(source)
        # Every Plotly-facing x goes through the one converter, with the
        # canvas-wide origin.
        assert module.count("- origin") == 1
        assert "wwErState.plot.origin" in module
        assert "panel.origin" not in module
        ticks = _between(source, "function wwErTimeAxisTicks(viewport, origin) {", "\n        }\n")
        assert "tickvals: values.map((value) => wwErReconstructionToPlotX(value, origin))" in ticks
        assert "ticktext: values.map((value) => wwErFormatReconstructionSeconds(value, decimals))" in ticks

    def test_relayout_drives_one_common_viewport(self):
        source = _source()
        wire = _between(source, "function wwErWirePanelRelayout(panel) {", "function wwErRequestViewport(start, end)")
        assert "wwErPlotXToReconstruction(x0, plot.origin)" in wire
        assert 'if (eventData["xaxis.autorange"] === true) wwErResetView();' in wire
        apply = _between(source, "function wwErApplyViewport(viewport) {", "function wwErSyncPanelStatus(panel)")
        assert "for (const panel of plot.panels)" in apply
        assert "Plotly.relayout(panel.chartEl, wwErTimeAxisRelayout(viewport, origin));" in apply
        assert 'doubleClick: "autosize"' in source
        request = _between(source, "function wwErRequestViewport(start, end) {", "function wwErResetView()")
        assert "wwErClampViewport(plot.fitAll, start, end, wwErState.dragMode)" in request

    def test_selection_reaches_the_renderer(self):
        source = _source()
        assert "wwErRenderPlot();" in _between(source, "function wwErToggleChannelRow(row) {", "function wwErToggleChannelGroup(button)")
        assert "wwErRenderPlot();" in _between(source, "function wwErToggleChannelGroup(button) {", "function wwErSyncChannelSelectionDom()")
        assert "wwErRenderPlot();" in _between(source, "function wwErRender() {", "function wwErHandleAction(button)")

    def test_panels_follow_the_browser_order(self):
        items = _between(_source(), "function wwErPlotItems() {", "function wwErPlotGroups(items)")
        assert "for (const member of wwErCurrentMembers())" in items
        assert "wwGroupChannelsByEngineeringType((data && data.analog_channels) || [])" in items
        assert "wwGroupChannelsByEngineeringType(calculated)" in items
        assert "wwErSelectedChannelsForPlotting()" in items
        assert "wwErSourceTiming(item.sourceId)" in items
        for forbidden in ("sampling_rate", "duration", "sample_count"):
            assert forbidden not in items

    def test_presentation_is_resolved_from_waveform_on_every_render(self):
        source = _source()
        trace = _between(source, "function wwErBuildTrace(trace) {", "function wwErLegendChipHtml(trace)")
        assert "color: wwColorForChannel(trace.sourceId, trace.channelName)," in trace
        assert "name: wwChannelDisplayNamePlotly(trace.sourceId, trace.channelName)," in trace
        refresh = _between(source, "function wwErRefreshPanelPresentation(panel) {", "function wwErPanelLayout(panel)")
        assert '"line.color": panel.traces.map((t) => wwColorForChannel(t.sourceId, t.channelName))' in refresh
        label = _between(source, "function wwErTraceLabelHtml(trace) {", "\n        }\n")
        assert "wwRichLabelHtml(" in label and "wwChannelDisplayNameHtml(trace.sourceId, trace.channelName)" in label
        legend = _between(source, "function wwErLegendChipHtml(trace) {", "function wwErCreateTrace(item)")
        assert "wwColorForChannel(trace.sourceId, trace.channelName)" in legend
        for forbidden in ("ww-legend-remove", "wwRemoveChannelByKey"):
            assert forbidden not in legend

    def test_own_theme_and_resize_hooks_without_touching_waveform_ones(self):
        source = _source()
        assert 'document.addEventListener("powerwave:theme-change", wwErApplyTheme);' in source
        assert "onResize: wwErResizePlots," in source
        for waveform_fn in ("function wwApplyTheme() {", "function wwResizeAllVisiblePlots("):
            body = source[source.index(waveform_fn) : source.index("\n        }\n", source.index(waveform_fn))]
            assert "wwEr" not in body

    def test_y_step_zoom_targets_the_active_axis(self):
        """DEC-142: Event Reconstruction's Y Zoom In/Out act on the
        explicit active Y-axis target. The buttons carry the SAME
        registry icons as Waveform's own Y-targeted zoom, start disabled
        in markup (dynamically re-enabled once a target exists,
        wwErSyncToolbar()) and are now wired to wwErStepZoomY(), which
        uses the SAME step factors/midpoint math as Waveform's own
        wwStepZoomY() -- parity, not a new factor."""
        source = _source()
        page = _er_page(source)
        for control in ("wwErZoomYInBtn", "wwErZoomYOutBtn"):
            assert re.search(r'id="' + control + r'"[^>]*\bdisabled\b', page)
        assert 'getElementById("wwErZoomYInBtn").addEventListener("click", () => wwErStepZoomY("in"));' in source
        assert 'getElementById("wwErZoomYOutBtn").addEventListener("click", () => wwErStepZoomY("out"));' in source
        assert _icon_key(_element(page, "wwErZoomYInBtn", "button")) == "ZOOM_Y_IN"
        assert _icon_key(_element(page, "wwErZoomYOutBtn", "button")) == "ZOOM_Y_OUT"
        module = _er_module(source)
        step = _between(module, "function wwErStepZoomY(direction) {", "function wwErSyncActiveAxisReadout(")
        assert "wwErActiveAxisEntry()" in step
        assert "WW_ZOOM_STEP_IN_FACTOR" in step and "WW_ZOOM_STEP_OUT_FACTOR" in step and "WW_MIN_Y_SPAN" in step
        assert "center - newSpan / 2" in step and "center + newSpan / 2" in step
        assert "entry.axis.manual = true;" in step


class TestEventReconstructionTimelineNavigation:
    """Slice 3D (DEC-129), Pan-only since DEC-144 (Box Zoom retired):
    X-only Pan, staged Zoom In/Out clamped to Fit All, Autoscale X = Fit
    All + autoscale Y (button and double-click), Autoscale Y on every
    panel, viewport rebasing, and the Fit All span notice -- all in
    reconstruction time."""

    def test_pan_is_x_only(self):
        source = _source()
        # Every Y axis can be dragged on its own scale (DEC-134), so none is
        # fixedrange in the layout; a drag that starts in the plot area (or
        # its corners) sees every Y axis as fixed for that drag only.
        layout = _between(source, "function wwErPanelLayout(panel) {", "function wwErInitPanelPlot(panel)")
        assert "panel.axes.forEach((axis, index) => {" in layout
        assert "fixedrange: false," in layout and "fixedrange: true" not in layout
        guard = _between(source, "function wwErKeepPlotAreaDragXOnly(panel, event) {", "async function wwErRelayoutY(panel, update)")
        assert 'if (!event.target.closest(".nsewdrag, .nwdrag, .nedrag, .swdrag, .sedrag")) return;' in guard
        assert "for (const key of keys) fullLayout[key].fixedrange = true;" in guard
        assert 'window.addEventListener("mouseup", restore);' in guard
        # DEC-142: the same pointerdown also resolves the active Y-axis
        # target (wwErActivateAxisFromDragEvent()) -- a different
        # selector (.nsdrag/.ndrag/.sdrag, the axis's own scale, never
        # this guard's plot-area corner classes), so the two coexist on
        # one listener without either one changing the other's scope.
        pointerdown = _between(source, 'panel.chartEl.addEventListener("pointerdown", (event) => {', "wwErWirePanelRelayout(panel);")
        assert "wwErKeepPlotAreaDragXOnly(panel, event);" in pointerdown
        assert "wwErActivateAxisFromDragEvent(panel, event);" in pointerdown
        # DEC-144: the same pointerdown also drives Pan's own grab/grabbing
        # cursor feedback -- a third, independent concern on the one
        # listener.
        assert "wwWirePlotAreaGrabCursor(event);" in pointerdown
        assert "layout[axis.placement.layoutKey] = yaxis;" in layout
        init = _between(source, "function wwErInitPanelPlot(panel) {", "function wwErWirePanelRelayout(panel)")
        assert "wwErPanelLayout(panel)" in init

    def test_toolbar_is_wired_to_event_reconstruction_functions_only(self):
        source = _source()
        assert 'document.getElementById("wwErZoomInBtn").addEventListener("click", () => wwErStepZoomX("in"));' in source
        assert 'document.getElementById("wwErZoomOutBtn").addEventListener("click", () => wwErStepZoomX("out"));' in source
        assert 'document.getElementById("wwErResetViewBtn").addEventListener("click", wwErResetView);' in source
        assert 'document.getElementById("wwErAutoscaleYBtn").addEventListener("click", wwErAutoscaleY);' in source
        page = _er_page(source)
        assert '<button type="button" class="ww-icon-btn ww-tg-autoscale-btn" id="wwErAutoscaleYBtn"' in page
        module = _er_module(source)
        for waveform_fn in ("wwStepZoomX(", "wwResetTimeView(", "wwAutoscaleY(", "wwAutoscaleYForGroup(", "wwPerformZoomStep("):
            assert waveform_fn not in module

    def test_staged_zoom_uses_the_shared_step_and_fit_all_bounds(self):
        source = _source()
        step = _between(source, "function wwErZoomStepRange(viewport, fitAll, direction) {", "\n        }\n")
        assert "wwStepZoomXRange(viewport, direction)" in step
        assert "wwClampPanWindowToBounds(fitAll, stepped.start, stepped.end)" in step
        assert "wwClampRangeToBounds(fitAll, stepped.start, stepped.end)" in step
        zoom = _between(source, "function wwErStepZoomX(direction) {", "\n        }\n")
        assert "wwErZoomStepRange(plot.viewport, plot.fitAll, direction)" in zoom
        assert "if (!next || wwErSameRange(next, plot.viewport)) return;" in zoom
        assert "wwErApplyViewport(next);" in zoom
        # Toolbar actions never read Plotly's (origin-relative) ranges.
        assert "layout.xaxis.range" not in _er_module(source)

    def test_reset_is_one_path_for_button_and_double_click(self):
        source = _source()
        reset = _between(source, "function wwErResetView() {", "\n        }\n")
        assert "axis.autoscaleYPending = true;" in reset and "for (const axis of panel.axes) {" in reset
        assert "wwErApplyViewport(plot.fitAll);" in reset
        assert "wwErRequestFitAll" not in source

    def test_autoscale_y_uses_plotly_autorange_then_keeps_the_range(self):
        source = _source()
        apply = _between(source, "async function wwErApplyPendingAutoscaleY(panel) {", "\n        }\n")
        assert 'autorange[axis.placement.layoutKey + ".autorange"] = true;' in apply
        assert "await wwErRelayoutY(panel, autorange);" in apply
        assert "if (!hasData) return;" in apply  # an empty axis stays pending
        assert "axis.range = panel.chartEl._fullLayout[axis.placement.layoutKey].range.slice();" in apply
        assert 'fixed[axis.placement.layoutKey + ".autorange"] = false;' in apply
        autoscale = _between(source, "function wwErAutoscaleY() {", "\n        }\n")
        assert "for (const panel of wwErState.plot.panels)" in autoscale
        assert "wwErApplyViewport" not in autoscale

    def test_viewport_rebasing_keeps_the_physical_segment(self):
        source = _source()
        shift = _between(source, "function wwErReferenceFrameShift(previous, next) {", "\n        }\n")
        assert "return before.reconstruction_offset_s + (after.correction_s - before.correction_s);" in shift
        rebase = _between(source, "function wwErRebaseViewport(previous, next) {", "\n        }\n")
        assert "if (!plot.viewport || plot.atFitAll) return;" in rebase
        assert "plot.viewport = { start: plot.viewport.start - shift, end: plot.viewport.end - shift };" in rebase
        refresh = _between(source, "async function wwErRefresh() {", "async function wwErOnPageEntered()")
        assert refresh.index("wwErRebaseViewport(wwErState.definition, definition);") < refresh.index("wwErState.definition = definition;")

    def test_span_notice_is_advisory_and_uses_the_configured_threshold(self):
        source = _source()
        assert "const WW_ER_OUTLIER_GAP_FRACTION = 0.9;" in source
        check = _between(source, "function wwErFitAllOutlier(intervals, thresholdS) {", "\n        }\n")
        assert "best.gapS < thresholdS || best.gapS < WW_ER_OUTLIER_GAP_FRACTION * spanS" in check
        notice = _between(source, "function wwErSyncSpanNotice() {", "\n        }\n")
        assert "wwErState.definition.large_gap_warning_threshold_s" in notice
        assert 'id="wwErSpanNotice"' in _er_page(source)
        module = _er_module(source)
        assert "3600" not in module and "86400" not in module

    def test_span_formatting_is_human_friendly_never_raw_seconds_for_a_large_gap(self):
        """UX refinement: the large-gap notice's own span/gap durations
        read in the smallest unit that is natural for their size -- a
        reader should not have to mentally divide a 5-digit second count.
        Display only; the threshold/outlier LOGIC above is untouched."""
        source = _source()
        fmt = _between(source, "function wwErFormatSpan(seconds) {", "\n        }\n")
        assert "const unit = WW_ER_SPAN_UNITS.find((u) => seconds < u.threshold);" in fmt
        assert "Number((seconds / unit.divisor).toFixed(unit.decimals));" in fmt
        # Every threshold/divisor is built from units, never a bare literal
        # (the module-wide "3600"/"86400" guard above already enforces the
        # two Waveform-precedent magic numbers specifically).
        units = _between(source, "const WW_ER_SPAN_UNITS = (() => {", "\n        })();")
        assert "WW_ER_SECONDS_PER_DAY" in units
        assert "2592000" not in units and "604800" not in units and "31536000" not in units
        module = _er_module(source)
        assert "2592000" not in module

class TestEventReconstructionCursors:
    """Slice 3E (DEC-130): global A/B cursors in reconstruction time, drawn
    on every panel, nearest-real-sample values, rebasing with the
    reconstruction zero -- never Waveform's cursor state."""

    def test_cursor_state_is_reconstruction_time_and_event_reconstruction_owned(self):
        source = _source()
        state = _between(source, "const wwErState = {", "};")
        assert "cursors: { enabled: false, a: { time: null, visible: true }, b: { time: null, visible: true } }," in state
        module = _er_module(source)
        for waveform in ("timeGroupCursorState", "wwToggleMeasurementCursors(", "wwSetMeasurementCursorVisible(",
                         "wwFetchCursorValuesForSource(", "wwUpdateCursorOverlayForGroup(", "wwCurValueText(", "#viewWaveform",
                         "wwCursorTimeToPixelX(", "wwCursorPixelXToTime("):
            assert waveform not in module

    def test_cursor_geometry_uses_the_shared_helpers_and_never_the_origin(self):
        source = _source()
        draw = _between(source, "function wwErDrawPanelCursors(panel) {", "function wwErWirePanelCursorDrag(panel)")
        assert "wwPlotMetricsForChart(panel.chartEl)" in draw
        assert "wwTimeToPageX(plot.viewport, metrics, time)" in draw
        assert "origin" not in draw
        drag = _between(source, "function wwErWirePanelCursorDrag(panel) {", "function wwErScheduleCursorValues()")
        assert "wwPageXToTime(wwErState.plot.viewport, metrics, event.clientX)" in drag
        assert "origin" not in drag
        assert "wwErClampCursorTime(plot.fitAll, time)" in _between(source, "function wwErSetCursorTime(kind, time,", "\n        }\n")

    def test_values_are_the_backend_nearest_sample_at_native_time(self):
        values = _between(_source(), "async function wwErRefreshCursorValues() {", "\n        }\n\n")
        assert "wwErReconstructionTimeToSourceElapsed(shown.a, offset)" in values
        assert "wwErReconstructionTimeToSourceElapsed(shown.b, offset)" in values
        assert "unit_mode: group.unitMode" in values
        assert "if (!current || current.seq !== seq) return; // superseded" in values
        for forbidden in ("interpolat", "Math.round(", "sampling_rate"):
            assert forbidden not in values
        text = _between(_source(), "function wwErCursorValueText(entry, kind) {", "\n        }\n")
        assert 'if (point.noSample) return "No sample";' in text
        assert "wwFormatEngineeringValue(point.value)" in text

    def test_cursors_rebase_with_the_reconstruction_zero(self):
        rebase = _between(_source(), "function wwErRebaseViewport(previous, next) {", "\n        }\n")
        assert rebase.index("if (Number.isFinite(cursor.time)) cursor.time -= shift;") < rebase.index("if (!plot.viewport || plot.atFitAll) return;")

    def test_controls_and_readout_are_event_reconstruction_ids(self):
        source = _source()
        page = _er_page(source)
        assert 'id="wwErCursorModeBtn"' in page and 'id="wwErCursorReadout"' in page
        for element_id in ("wwErCursorReadoutA", "wwErCursorReadoutB", "wwErCursorReadoutDelta", "wwErCursorCloseA", "wwErCursorCloseB"):
            assert 'id="' + element_id + '"' in page
        assert 'document.getElementById("wwErCursorModeBtn").addEventListener("click", wwErToggleCursors);' in source
        create = _between(source, "function wwErCreatePanel(spec) {", "function wwErDestroyPanel(panel)")
        assert 'data-er-cursor-line="' in create and 'data-er-cursor-drag="' in create
        assert 'data-cursor-line="' not in create  # never Waveform's cursor hooks


class TestEventReconstructionGroupedView:
    """DEC-131: the Grouped Measurement View -- one panel per backend display
    axis (engineering quantity + normalized unit), shared across records and
    by native and calculated channels; every trace keeps its own fetch and
    timing; per-channel cursor values live in the channel tree."""

    def test_grouping_uses_the_backend_display_axis_only(self):
        source = _source()
        axis = _between(source, "function wwErChannelAxis(item, perUnit = false) {", "\n        }\n")
        # The backend's display axis -- or, shown in Per Unit, its
        # per_unit_display_axis (DEC-138).
        assert 'const prefix = perUnit ? "per_unit_display_axis_" : "display_axis_";' in axis
        assert 'key: channel[prefix + "key"] === undefined ? null : channel[prefix + "key"],' in axis
        assert 'unit: channel[prefix + "unit"] || "",' in axis
        groups = _between(source, "function wwErPlotGroups(items) {", "\n        }\n")
        assert "const key = wwErAxisGroupKey(item, item.axis);" in groups
        group_key = _between(source, "function wwErAxisGroupKey(item, axis) {", "\n        }\n")
        assert 'return axis.key !== null ? "axis:" + axis.key : "solo:" + item.key;' in group_key
        # Never a rule over channel names or unit strings in the frontend.
        for body in (axis, groups):
            for forbidden in (".test(", ".match(", "toLowerCase", "toUpperCase", "indexOf(\"k", "channelName.", "name.includes"):
                assert forbidden not in body
        title = _between(source, "function wwErAxisTitle(axis, traces) {", "\n        }\n")
        assert 'const title = (axis.quantity || WW_ER_UNKNOWN_QUANTITY_LABEL) + (axis.unit ? " (" + axis.unit + ")" : "");' in title
        # An unknown-quantity axis with one channel is named after it, with
        # the Waveform-owned display name -- display only.
        assert "if (!axis.unknown || !traces || traces.length !== 1) return title;" in title
        assert 'return title + " — " + wwChannelDisplayName(traces[0].sourceId, traces[0].channelName);' in title
        assert "unknown: !quantity || quantity === WW_ER_UNKNOWN_QUANTITY_LABEL," in axis
        # The title quantity is the backend's; never a classification
        # sentinel or broad type copied in by the frontend.
        assert 'const quantity = channel[prefix + "quantity"];' in axis and "quantity: quantity || null," in axis
        assert 'quantity: "Undefined"' not in axis
        assert "display_axis_quantity || channel.engineering_type" not in axis
        # One title helper: no other place in the module builds a title
        # from an axis quantity.
        module = _er_module(source)
        # DEC-142: the active Y-axis target re-targets across an
        # Engineering <-> Per Unit switch by physical quantity (never a
        # title string) -- three legitimate reads outside wwErAxisTitle
        # itself (wwErSetActiveAxisTarget, wwErReconcileActiveAxisTarget,
        # wwErRemapActiveAxisTargetForUnitMode). wwErAxisTitle is still
        # the only place that builds a TITLE from one.
        active_target = _between(module, "function wwErLiveAxisEntries() {", "function wwErSyncActiveAxisVisual() {")
        assert active_target.count(".axis.quantity") == 3
        assert module.count(".quantity") == title.count(".quantity") + active_target.count(".axis.quantity")
        for use in ("text: panel.combined ? wwErAxisTitle(axis.axis, wwErAxisTraces(panel, index))", "const title = wwErAxisTitle(panel.axes[0].axis, panel.traces);",
                    "const title = wwErAxisTitle(axis.axis, wwErAxisTraces(panel, index));"):
            assert use in module

    def test_each_trace_fetches_and_maps_independently(self):
        source = _source()
        create = _between(source, "function wwErCreatePanel(spec) {", "function wwErDestroyPanel(panel)")
        assert "abortController" not in create and "requestSeq" not in create  # fetch state is per trace
        trace = _between(source, "function wwErCreateTrace(item) {", "function wwErDestroyTrace(trace)")
        assert "abortController: null," in trace and "requestSeq: 0," in trace and "timing: item.timing," in trace
        apply = _between(source, "function wwErApplyViewport(viewport) {", "function wwErSyncPanelStatus(panel)")
        assert "for (const trace of wwErPlottedTraces()) wwErLoadTrace(trace);" in apply
        load = _between(source, "async function wwErLoadTrace(trace) {", "function wwErPlottedTraces()")
        assert "wwErFetchRequestFor(trace, timing, viewport, pointBudget)" in load
        assert "trace.error = result.error ? wwFriendlyError(" in load  # one trace fails, the rest plot

    def test_autoscale_covers_every_trace_of_a_panel(self):
        source = _source()
        has_data = _between(source, "function wwErAxisHasData(panel, axisIndex) {", "\n        }\n")
        assert "panel.traces.some((trace) => trace.axisIndex === axisIndex && trace.values.some((value) => Number.isFinite(value)))" in has_data
        apply = _between(source, "async function wwErApplyPendingAutoscaleY(panel) {", "\n        }\n")
        assert "panel.traces.some((t) => t.loading)" in apply
        render = _between(source, "function wwErRenderPlot() {", "function wwErSetViewMode(mode)")
        # A channel joined or left an axis: that axis re-autoscales.
        assert "const pending = !manual && (!previous || previous.autoscaleYPending || previous.traceKeys !== traceKeys);" in render

    def test_cursor_values_live_in_the_channel_tree_not_the_panels(self):
        source = _source()
        tree = _between(source, "function wwErSourceTreeHtml(member, sourceId, open) {", "function wwErMemberTreeHtml(member)")
        assert tree.count("...wwErTreeCursorColumns(") == 2
        columns = _between(source, "function wwErTreeCursorColumns(keyFor) {", "\n        }\n")
        for label in ('"Cur A"', '"Cur B"', '"Δ"'):
            assert label in columns
        assert columns.count('className: "cur-value-col"') == 3
        module = _er_module(source)
        for gone in ("cursorValuesEl", "wwErRenderPanelCursorValues", "ww-er-panel-cursor-values"):
            assert gone not in module
        assert "wwErSyncTreeCursorValues();" in _between(source, "function wwErSyncCursorReadout() {", "\n        }\n")

    def test_view_mode_defaults_to_grouped(self):
        source = _source()
        page = _er_page(source)
        assert '<button type="button" id="wwErViewGroupedBtn" aria-pressed="true"' in page
        assert 'viewMode: "grouped",' in _between(source, "const wwErState = {", "};")

    def test_waveform_grouping_is_untouched(self):
        source = _source()
        for waveform_fn in ("function wwPanelGroupKeyFor(channel) {", "function wwPanelLabelFor(channel) {"):
            body = source[source.index(waveform_fn) : source.index("\n        }\n", source.index(waveform_fn))]
            assert "wwEr" not in body and "display_axis" not in body


class TestEventReconstructionCombinedView:
    """DEC-132: the Combined Multi-Axis View -- every selected channel in one
    panel, one Plotly Y axis per backend display axis (the Grouped View's
    own grouping), deterministic left/right placement with Plotly-sized
    margins, per-axis autoscale, X-only navigation, one cursor overlay;
    switching modes is presentation only and reuses fetched data."""

    def test_both_modes_use_the_one_display_axis_grouping(self):
        source = _source()
        render = _between(source, "function wwErRenderPlot() {", "function wwErSetViewMode(mode)")
        assert "const groups = wwErPlotGroups(plotted);" in render and "const specs = wwErViewPanels(groups, plot.viewMode);" in render
        view = _between(source, "function wwErViewPanels(groups, viewMode) {", "\n        }\n")
        assert 'if (viewMode === "combined") return groups.length ? [{ key: "combined", combined: true, axes: groups }] : [];' in view
        assert "return groups.map((group) => ({ key: group.key, combined: false, axes: [group] }));" in view
        # Never a second grouping or a conversion between units.
        module = _er_module(source)
        for forbidden in ("1000 *", "* 1000", "/ 1000", "toLowerCase()", "unitScale"):
            assert forbidden not in _between(source, "function wwErViewPanels(groups, viewMode) {", "function wwErTraceLabelHtml(trace)")
        assert module.count("function wwErPlotGroups(") == 1

    def test_axis_placement_is_deterministic_and_plotly_sized(self):
        placement = _between(_source(), "function wwErYAxisPlacement(index) {", "\n        }\n")
        assert 'const side = index % 2 === 0 ? "left" : "right";' in placement
        assert 'if (index === 1) return { ref, layoutKey, spec: { side, overlaying: "y", anchor: "x" } };' in placement
        assert 'spec: { side, overlaying: "y", anchor: "free", position: side === "left" ? 0 : 1, autoshift: true } };' in placement
        layout = _between(_source(), "function wwErPanelLayout(panel) {", "function wwErInitPanelPlot(panel)")
        assert "yaxis.automargin = true;" in layout
        assert "if (index > 0) yaxis.showgrid = false;" in layout
        # No pixel spacing, no cap on the axis count.
        for forbidden in (" shift:", "margin.l", "margin.r", "domain:", "Math.min(", "slice(0,"):
            assert forbidden not in placement + layout

    def test_empty_axis_keeps_its_title_and_shows_no_invented_values(self):
        source = _source()
        layout = _between(source, "function wwErPanelLayout(panel) {", "function wwErInitPanelPlot(panel)")
        assert "text: panel.combined ? wwErAxisTitle(axis.axis, wwErAxisTraces(panel, index)) : (axis.axis.unit || \"\")," in layout
        assert "font: { size: WW_ER_Y_AXIS_TITLE_FONT_SIZE }," in layout
        assert "yaxis.showticklabels = !axis.autoscaleYPending || wwErAxisHasData(panel, index);" in layout
        apply = _between(source, "async function wwErApplyPendingAutoscaleY(panel) {", "\n        }\n")
        assert 'if (panel.combined) fixed[axis.placement.layoutKey + ".showticklabels"] = hasData;' in apply

    def test_traces_carry_their_axis_and_move_between_panels(self):
        source = _source()
        build = _between(source, "function wwErBuildTrace(trace) {", "function wwErLegendChipHtml(trace)")
        assert "yaxis: trace.yRef," in build
        render = _between(source, "function wwErRenderPlot() {", "function wwErSetViewMode(mode)")
        assert "const trace = traces.get(item.key) || wwErCreateTrace(item);" in render
        assert "trace.panel = panel;" in render and "trace.axisIndex = index;" in render and "trace.yRef = placement.ref;" in render
        destroy = _between(source, "function wwErDestroyPanel(panel) {", "\n        }\n")
        assert "wwErDestroyTrace" not in destroy  # traces outlive a panel
        load = _between(source, "async function wwErLoadTrace(trace) {", "function wwErPlottedTraces()")
        assert "const current = trace.panel;" in load  # results go to the trace's panel now
        assert 'const served = !request || trace.representation === "full_resolution" || trace.loadedBudget >= pointBudget;' in load
        assert "if (loadKey === trace.loadedKey && served) return;" in load
        # A pending axis scales only once every trace that needs data has
        # started loading (a channel joining an axis is never left out).
        assert "wwErApplyPendingAutoscaleY" not in load.split("await wwFetchWaveformRange(request)")[0]
        apply = _between(source, "function wwErApplyViewport(viewport) {", "function wwErSyncPanelStatus(panel)")
        assert apply.index("wwErLoadTrace(trace);") < apply.index("for (const panel of plot.panels) wwErApplyPendingAutoscaleY(panel);")

    def test_mode_switch_is_presentation_only(self):
        source = _source()
        switch = _between(source, "function wwErSetViewMode(mode) {", "\n        }\n")
        assert "plot.viewMode = mode;" in switch and "wwErRenderPlot();" in switch
        for forbidden in ("viewport", "fitAll", "cursors", "dragMode", "selectedChannels", "Definition", "reference", "fetch("):
            assert forbidden not in switch
        assert 'document.getElementById("wwErViewGroupedBtn").addEventListener("click", () => wwErSetViewMode("grouped"));' in source
        assert 'document.getElementById("wwErViewCombinedBtn").addEventListener("click", () => wwErSetViewMode("combined"));' in source
        page = _er_page(source)
        assert not re.search(r'id="wwErViewCombinedBtn"[^>]*\bdisabled\b', page)

    def test_combined_panel_height_and_advisory_notice(self):
        source = _source()
        assert "const WW_ER_COMBINED_PANEL_HEIGHT = 420;" in source
        assert "const WW_ER_COMBINED_AXIS_ADVISORY = 4;" in source
        create = _between(source, "function wwErCreatePanel(spec) {", "function wwErDestroyPanel(panel)")
        assert 'panel.chartEl.style.height = (spec.combined ? WW_ER_COMBINED_PANEL_HEIGHT : WW_ER_PANEL_HEIGHT) + "px";' in create
        assert ".ww-resize-handle\").remove();" in create  # still no resize grip
        notice = _between(source, "function wwErSyncAxisNotice() {", "\n        }\n")
        assert "if (axes <= WW_ER_COMBINED_AXIS_ADVISORY) {" in notice
        assert 'id="wwErAxisNotice"' in _er_page(source)

    def test_legend_is_per_trace_organised_by_axis(self):
        legend = _between(_source(), "function wwErRenderPanelLegend(panel) {", "function wwErCreateTrace(item)")
        assert "panel.traces.filter((trace) => trace.axisIndex === index).map(wwErLegendChipHtml)" in legend
        assert "const title = wwErAxisTitle(axis.axis, wwErAxisTraces(panel, index));" in legend
        assert "escapeHtml(title)" in legend
        for forbidden in ("dash", "dot"):
            assert forbidden not in _between(_source(), "function wwErBuildTrace(trace) {", "function wwErLegendChipHtml(trace)")

    def test_waveform_layout_helpers_are_untouched(self):
        source = _source()
        layout = source[source.index("function wwAnalogPanelLayout(") : source.index("\n        }\n", source.index("function wwAnalogPanelLayout("))]
        for forbidden in ("autoshift", "overlaying", "wwEr"):
            assert forbidden not in layout


class TestEventReconstructionFitRecord:
    """Mixed-duration navigation -- Fit Record: an explicit active navigation
    record (a record identity, distinct from the reference), whose backend
    reconstruction extent becomes the common X viewport; X only."""

    def test_active_record_is_an_identity_separate_from_the_reference(self):
        source = _source()
        state = _between(source, "const wwErState = {", "};")
        assert "activeRecordId: null," in state
        sync = _between(source, "function wwErSyncActiveRecord(wasDefined) {", "\n        }\n")
        # Initialised once (reference record) when a reconstruction appears;
        # cleared when its record leaves; never replaced by another record.
        assert "if (!wasDefined) {" in sync and "wwErState.activeRecordId = reference ? reference.record_id : null;" in sync
        assert "if (id !== null && !wwErMembers().some((m) => m.record_id === id)) wwErState.activeRecordId = null;" in sync
        refresh = _between(source, "async function wwErRefresh() {", "async function wwErOnPageEntered()")
        assert "wwErSyncActiveRecord(wasDefined);" in refresh
        setter = _between(source, "function wwErSetActiveRecord(recordId) {", "\n        }\n")
        for forbidden in ("is_reference", "make-reference", "selectedChannels", "correction", "PUT", "wwErRenderPlot", "viewport"):
            assert forbidden not in setter
        # Neither the reference action nor channel selection touches it.
        module = _er_module(source)
        assert module.count("wwState.activeRecordId") == 0
        assert module.count("activeRecordId =") == 4  # init/clear (3 in sync) + explicit selection
        toggle = _between(source, "function wwErToggleChannelRow(row) {", "\n        }\n")
        assert "activeRecordId" not in toggle

    def test_record_header_is_the_selection_target(self):
        source = _source()
        row = _between(source, "function wwErMemberRowHtml(member) {", "function wwErRecordRowHtml(record)")
        assert "' data-er-activate-record role=\"button\" tabindex=\"0\" aria-pressed=\"' + active + '\"'" in row
        assert '" ww-er-member-row--active"' in row and "ww-er-active-marker" in row
        assert "ww-er-badge--reference" in row  # the reference keeps its own, different marker
        click = source[source.index('document.getElementById("wwErSidebar").addEventListener("click"'):]
        assert click.index('closest("[data-er-activate-record]")') < click.index('closest("button[data-er-action]")')

    def test_fit_uses_the_backend_record_extent_only(self):
        source = _source()
        target = _between(source, "function wwErFitRecordTarget() {", "function wwErFitRecord()")
        assert "return { range: { start: member.start_s, end: member.end_s }, name, reason: null };" in target
        for forbidden in ("sample_count", "sampling_rate", "reconstructionTime", "values", "duration_s", ".timing."):
            assert forbidden not in target
        fit = _between(source, "function wwErFitRecord() {", "\n        }\n")
        assert 'wwErClampViewport(plot.fitAll, target.range.start, target.range.end, "zoom")' in fit
        assert "wwErApplyViewport(next);" in fit
        # X only: no Y autoscale, no cursor or timing change.
        for forbidden in ("autoscaleYPending", "cursors", "wwErAutoscaleY", "definition", "fetch("):
            assert forbidden not in fit

    def test_toolbar_button(self):
        source = _source()
        page = _er_page(source)
        # DEC-137: an Event Reconstruction-specific tool -> the shared
        # compact icon button with its own icon and an accessible name.
        assert '<button type="button" class="ww-icon-btn ww-er-fit-record-btn" id="wwErFitRecordBtn" title="Fit selected record" aria-label="Fit selected record" disabled>' in page
        assert ">Fit Record</button>" not in page
        assert 'document.getElementById("wwErFitRecordBtn").addEventListener("click", wwErFitRecord);' in source
        toolbar = _between(source, "function wwErSyncToolbar() {", "\n        }\n")
        assert "fitBtn.disabled = !fit.range;" in toolbar


class TestEventReconstructionYAxisDragZoom:
    """DEC-134: individual Y-axis drag zoom -- Plotly's native drag on one
    axis's own scale; a dragged range is that axis's manual range, keyed by
    display-axis key, per view mode, kept through X navigation until
    Autoscale Y / Reset."""

    def test_user_axis_changes_touch_only_the_named_axis(self):
        source = _source()
        apply = _between(source, "function wwErApplyUserAxisChange(panel, eventData) {", "function wwErKeepPlotAreaDragXOnly(panel, event)")
        assert 'let y0 = eventData[key + ".range[0]"];' in apply
        assert "axis.manual = true;" in apply and "axis.range = [Number(y0), Number(y1)];" in apply
        assert 'eventData[key + ".autorange"] === true' in apply  # double-click: that axis only
        for forbidden in ("viewport", "cursors", "wwErApplyViewport", "xaxis", "definition"):
            assert forbidden not in apply
        relayout = _between(source, "function wwErWirePanelRelayout(panel) {", "function wwErApplyUserAxisChange(panel, eventData)")
        assert "if (!panel.internalYRelayouts) wwErApplyUserAxisChange(panel, eventData);" in relayout
        # Our own Y relayouts are never read back as a user's drag.
        pending = _between(source, "async function wwErApplyPendingAutoscaleY(panel) {", "\n        }\n")
        assert "await wwErRelayoutY(panel, autorange);" in pending and "await wwErRelayoutY(panel, fixed);" in pending
        assert "Plotly.relayout" not in pending

    def test_state_is_keyed_by_display_axis_per_view_mode(self):
        source = _source()
        state = _between(source, "const wwErState = {", "};")
        # Per view mode AND unit mode (DEC-138): "<viewMode>|<unitMode>".
        assert "axisStates: {}," in state
        store = _between(source, "function wwErAxisStore(viewMode, unitMode) {", "\n        }\n")
        assert 'const key = viewMode + "|" + unitMode;' in store
        render = _between(source, "function wwErRenderPlot() {", "function wwErSetViewMode(mode)")
        assert "const axisStore = wwErAxisStore(plot.viewMode, wwErState.unitMode);" in render
        assert "const previous = axisStore.get(group.key);" in render  # never "y2"
        assert "axisStore.set(group.key, entry);" in render
        assert "if (!liveAxes.has(key)) store.delete(key);" in render
        # A manual range survives a channel joining or leaving its axis.
        assert "const manual = !!previous && previous.manual;" in render

    def test_autoscale_and_reset_clear_manual_ranges(self):
        source = _source()
        autoscale = _between(source, "function wwErAutoscaleY() {", "function wwErAxisHasData(panel, axisIndex)")
        assert "axis.manual = false;" in autoscale and "axis.autoscaleYPending = true;" in autoscale
        reset = _between(source, "function wwErResetView() {", "\n        }\n")
        assert "axis.manual = false;" in reset
        # The other view mode's Y in the CURRENT unit mode only (DEC-138).
        assert 'wwErAxisStore(plot.viewMode === "combined" ? "grouped" : "combined", wwErState.unitMode).clear();' in reset
        assert "wwErApplyViewport(plot.fitAll);" in reset
        fit = _between(source, "function wwErFitRecord() {", "\n        }\n")
        assert "manual" not in fit and "autoscaleYPending" not in fit  # Fit Record is X only


class TestEventReconstructionTimeDisplay:
    """DEC-135: Relative / Absolute time display -- labels only; reconstruction
    seconds stay the internal coordinate; Absolute = the backend's
    reconstruction_zero_time_utc + r, in the display timezone (DEC-122),
    precision-safe."""

    def test_default_relative_and_backend_anchor(self):
        source = _source()
        assert 'timeDisplay: "relative",' in _between(source, "const wwErState = {", "};")
        zero = _between(source, "function wwErAbsoluteZero() {", "\n        }\n")
        assert "wwErState.definition.reconstruction_zero_time_utc" in zero
        instant = _between(source, "function wwErAbsoluteInstant(zero, r) {", "\n        }\n")
        assert "const t = zero.fraction + r;" in instant and "epochSecond: zero.epochSecond + whole" in instant

    def test_calendar_from_the_display_timezone_whole_seconds_only(self):
        source = _source()
        clock = _between(source, "function wwErWallClock(epochSecond) {", "\n        }\n")
        assert "wwDisplayWallClockFormatter().formatToParts(new Date(epochSecond * 1000))" in clock
        block = _between(source, "// ---- Relative / Absolute time display (DEC-135) ----", "function wwErTimeAxisRelayout(viewport, origin)")
        for forbidden in ("getHours", "getMinutes", "toLocale", "getTimezoneOffset", "Date.now", "new Date(epochSecond * 1000 +"):
            assert forbidden not in block

    def test_switching_is_presentation_only(self):
        source = _source()
        switch = _between(source, "function wwErSetTimeDisplay(mode) {", "function wwErSyncTimeDisplayButtons()")
        assert "Plotly.relayout(panel.chartEl, wwErTimeAxisRelayout(plot.viewport, plot.origin));" in switch
        for forbidden in ("wwErLoadTrace", "wwErRefreshCursorValues", "wwErApplyViewport", "fetch(", "viewport =", "cursors", "autoscaleYPending", "wwErRefresh("):
            assert forbidden not in switch
        # Trace x stays origin-relative reconstruction time; customdata numeric.
        build = _between(source, "function wwErBuildTrace(trace) {", "function wwErLegendChipHtml(trace)")
        assert "x: trace.reconstructionTime.map((r) => wwErReconstructionToPlotX(r, origin))," in build
        assert "customdata: trace.reconstructionTime," in build and "text: wwErHoverTexts(trace)," in build

    def test_cursor_delta_stays_a_duration(self):
        source = _source()
        readout = _between(source, "function wwErSyncCursorReadout() {", "\n        }\n")
        assert "wwErFormatCursorDelta(shown.b - shown.a)" in readout
        label = _between(source, "function wwErCursorTimeLabel(seconds) {", "\n        }\n")
        assert "wwErFormatAbsoluteClock(wwErAbsoluteInstant(zero, seconds), 6)" in label


def _er_annotations(source: str) -> str:
    return _between(source, "// ---- Event Reconstruction annotations (DEC-136, DEC-137) ----", "// ---- Slice 3E: global A/B cursors (DEC-130) ----")


def _element(source: str, element_id: str, tag: str) -> str:
    """The element with `id` through its matching close tag (no nesting of
    the same tag inside)."""
    start = source.index(f'id="{element_id}"')
    start = source.rindex(f"<{tag}", 0, start)
    return source[start:source.index(f"</{tag}>", start) + len(f"</{tag}>")]


def _svgs(markup: str) -> list[str]:
    out, at = [], 0
    while (i := markup.find("<svg", at)) != -1:
        j = markup.index("</svg>", i) + len("</svg>")
        out.append(markup[i:j])
        at = j
    return out


class TestEventReconstructionAnnotations:
    """DEC-136 as amended by DEC-137: the SAME four annotation tools as
    Waveform (Text Note, Callout, Maximum Peak, Minimum Peak) and an
    Annotations manager, over Event Reconstruction's OWN backend-owned
    state (`definition.annotations`) -- never Waveform's annotation state,
    never Time Groups; shared presentation helpers, page adapters."""

    def test_state_is_the_backend_definition_never_waveform(self):
        source = _source()
        annotations = _between(source, "function wwErAnnotations() {", "\n        }\n")
        assert "wwErState.definition.annotations" in annotations
        block = _er_annotations(source)
        for forbidden in ("ww.annotations", "ww.annotation", "wwCreateAnnotation(", "wwUpdateAnnotation(", "wwDeleteAnnotation(",
                          "wwRenderAnnotations(", "wwSelectAnnotation(", "timeGroup", "TimeGroup", "#wwAnnotationOverlay",
                          'getElementById("wwAnnotation', 'getElementById("wwCalloutConnectorLayer")', "data-annotation-id=\""):
            assert forbidden not in block, forbidden
        # And Waveform's annotation code never reads Event Reconstruction state.
        waveform = _between(source, "function wwCreateAnnotation(type, region, position, data) {", "function wwAnnotationCategoryLabel(annotation)")
        assert "wwEr" not in waveform

    def test_the_four_waveform_types_and_the_shared_presentation(self):
        block = _er_annotations(_source())
        # The same box markup, connector geometry and texts as Waveform.
        for shared in ("wwCalloutBodyHtml()", "wwPeakBodyHtml(annotation.type)", "wwAnnotationNoteBodyHtml()",
                       "wwUpdateCalloutConnectorGeometry(", "wwHideCalloutConnector(connectors, id)",
                       "wwAnnotationCategoryLabel(shape)", "wwAnnotationSummary(shape)",
                       "wwPeakValueLineText(wwErAsWaveformAnnotation(annotation))", "wwAnnotationPlacementGuidance(type)",
                       'el.className = "ww-annotation ww-annotation--" + annotation.type;'):
            assert shared in block, shared
        # Every write is Event Reconstruction's own API.
        assert 'wwErMutate("POST", "/definition/annotations", body)' in block
        assert 'wwErMutate("PUT", "/definition/annotations/" + encodeURIComponent(id), patch)' in block
        assert 'wwErMutate("DELETE", "/definition/annotations/" + encodeURIComponent(id))' in block
        for body in ('type: "text_note", reconstruction_time_s:', 'type: "callout", channel: wwErAnnotationChannelOf(trace), anchor: resolved.anchor',
                     "{ type, channel: wwErAnnotationChannelOf(trace) }"):
            assert body in block, body
        # Boxes are told apart from Waveform's by their own attribute.
        assert "el.dataset.erAnnotationId = id;" in block

    def test_channel_attached_annotations_use_the_clicked_trace_and_its_axis(self):
        source = _source()
        click = _between(source, "function wwErAnnotationTraceClick(panel, eventData) {", "function wwErAnnotationChannelOf(trace)")
        assert "panel.traces.find((t) => t.key === (point.data && point.data.meta))" in click
        assert 'panel.chartEl.on("plotly_click", (eventData) => wwErAnnotationTraceClick(panel, eventData));' in source
        match = _between(source, "function wwErAnnotationTrace(annotation) {", "\n        }\n")
        assert "t.recordId === channel.record_id" in match and "t.sourceId === channel.source_id" in match
        assert "t.channelName === channel.channel_name" in match
        # Y from the trace's OWN axis (Grouped panel or its Combined axis).
        y = _between(source, "function wwErTraceValueToY(trace, value, wrapRect) {", "\n        }\n")
        assert "panel.axes[trace.axisIndex]" in y and "fl[axis.placement.layoutKey]" in y

    def test_timing_model(self):
        source = _source()
        time = _between(source, "function wwErAnnotationTime(annotation) {", "\n        }\n")
        # Text Note: reconstruction-level (the backend rebases it).
        assert 'if (annotation.type === "text_note") return annotation.reconstruction_time_s;' in time
        # Callout / Peak: the record's CURRENT offset -> follow corrections.
        assert "wwErSourceElapsedToReconstructionTime(annotation.anchor.source_elapsed_s, timing.totalOffsetS)" in time
        assert "wwErSourceElapsedToReconstructionTime(peak.sourceElapsed, timing.totalOffsetS)" in time
        timing = _between(source, "function wwErAnnotationTiming(annotation) {", "\n        }\n")
        assert "timing.recordId === annotation.channel.record_id" in timing

    def test_anchor_and_peaks_use_waveforms_endpoints_in_source_time(self):
        source = _source()
        anchor = _between(source, "async function wwErResolveAnchor(trace, reconstructionTime) {", "function wwErRefreshCalloutValues()")
        assert "wwErReconstructionTimeToSourceElapsed(r, timing.totalOffsetS)" in anchor
        # The stored anchor is always in engineering units (DEC-138).
        assert 'wwErRequestAnchor(trace.kind, trace.sourceId, trace.channelName, native, "engineering")' in anchor
        request = _between(source, "async function wwErRequestAnchor(kind, sourceId, channelName, nativeTime, unitMode) {", "async function wwErResolveAnchor(")
        assert '"/annotation-anchor"' in request and "unit_mode: unitMode" in request
        peaks = _between(source, "async function wwErMeasurePeaks(sourceId, calculated, items, unitMode = \"engineering\") {", "function wwErPeakResult(result, displayKey, unitMode)")
        assert '"/calculated-channels/peak-values"' in peaks and '"/peak-values"' in peaks
        assert "Math.max(viewport.start, timing.startS)" in peaks and "Math.min(viewport.end, timing.endS)" in peaks
        # Live recalculation on every viewport change, stale responses dropped.
        assert "wwErRefreshAnnotationValues();\n            wwErSyncToolbar();" in _between(source, "function wwErApplyViewport(", "\n        }\n")
        recalc = _between(source, "function wwErRecalculatePeaks() {", "function wwState_isCalculatedErSource(sourceId)")
        assert "if (!current || current.seq !== seq) return;" in recalc

    def test_manager_lists_event_reconstruction_annotations_only(self):
        source = _source()
        page = _er_page(source)
        drawer = _between(page, '<div class="ww-annotation-drawer" id="wwErAnnotationDrawer"', "No annotations yet.")
        assert 'id="wwErAnnotationListBody"' in drawer and 'id="wwErAnnotationDrawerCloseBtn"' in drawer
        listing = _between(source, "function wwErRenderAnnotationList() {", "function wwErSetAnnotationDrawerOpen(open)")
        assert "wwErAnnotations().slice().sort((a, b) => b.sequence - a.sequence)" in listing
        assert 'deleteBtn.title = "Delete annotation";' in listing
        assert "wwErDeleteAnnotation(annotation.annotation_id)" in listing
        assert "wwErSelectAnnotationAndReveal(annotation.annotation_id)" in listing
        assert 'meta.textContent = wwErAnnotationMetaLine(annotation);' in listing

    def test_time_text_uses_the_one_time_display_helper(self):
        source = _source()
        text = _between(source, "function wwErAnnotationTimeText(seconds) {", "\n        }\n")
        assert "wwErCursorTimeLabel(seconds)" in text
        switch = _between(source, "function wwErSetTimeDisplay(mode) {", "function wwErSyncTimeDisplayButtons()")
        assert "wwErRenderAnnotations();" in switch and "wwErRenderAnnotationList();" in switch
        # Every cursor redraw path also re-places the annotations.
        assert "wwErScheduleAnnotationRender();" in _between(source, "function wwErDrawPanelCursors(panel) {", "const layer = panel.cursorLayerEl;")

    def test_the_simplified_marker_ux_is_gone(self):
        source = _source()
        for gone in ("wwErAnnotationEditor", "wwErAnnotationHint", "ww-er-annotation-marker", "ww-er-annotation-label",
                     "ww-er-annotate-btn", "wwErDrawPanelAnnotations", "wwErToggleAnnotationPlacement", ">Annotate</button>"):
            assert gone not in source, gone


def _div_by_id(source: str, element_id: str) -> str:
    """A `<div id="...">`, up to its own first `</div>` -- only valid for
    a div with no nested div, which every control wrapper used below is."""
    i = source.index(f'id="{element_id}"')
    start = source.rindex("<div", 0, i)
    end = source.index("</div>", start) + len("</div>")
    return source[start:end]


def _div_matching_by_id(source: str, element_id: str) -> str:
    """A `<div id="...">`, up to its own true matching `</div>` (nesting
    depth tracked), for a wrapper that DOES contain further divs."""
    i = source.index(f'id="{element_id}"')
    start = source.rindex("<div", 0, i)
    depth, j = 0, start
    while True:
        next_open = source.find("<div", j + 1)
        next_close = source.find("</div>", j + 1)
        if depth == 0 and next_close < next_open:
            return source[start:next_close + len("</div>")]
        if next_open != -1 and (next_close == -1 or next_open < next_close):
            depth += 1
            j = next_open
        else:
            depth -= 1
            j = next_close


def _icon_registry(source: str) -> dict:
    """`WW_TOOL_ICONS` parsed into {KEY: svg_markup} -- the ONE place every
    `data-ww-icon="KEY"` placeholder's actual rendered markup comes from
    (DEC-140). Parsed from the real source, never retyped, so a future
    edit to the registry is what these tests see too."""
    import ast
    body = _between(source, "const WW_TOOL_ICONS = {", "\n        };")
    entries = {}
    for line in body.split("\n"):
        line = line.strip().rstrip(",")
        if not line.startswith("//") and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            if key.isidentifier() and key.isupper():
                entries[key] = ast.literal_eval(value.strip())
    assert entries, "WW_TOOL_ICONS parsed empty -- check the anchors above"
    return entries


def _icon_key(markup: str) -> str:
    i = markup.index('data-ww-icon="') + len('data-ww-icon="')
    return markup[i:markup.index('"', i)]


class TestPowerwaveIconSystem:
    """DEC-140: the global Powerwave Waveform Tool Icon System. One
    registry is the canonical source for every common-tool icon; a
    control's markup names which registry entry it wants
    (`data-ww-icon="KEY"`) rather than carrying its own copy, so "two
    pages use the same icon" is a structural fact (one shared string),
    never a coincidence two separately-typed `<svg>` blocks happen to
    agree. wwApplyToolIcons() fills every placeholder from the registry,
    once at init (so there is no flash of an empty icon) and again, scoped,
    for any canvas built later."""

    def test_every_data_ww_icon_placeholder_resolves_to_one_registry_entry(self):
        source = _source()
        registry = _icon_registry(source)
        used = set()
        for match in __import__("re").finditer(r'data-ww-icon="([A-Z_]+)"', source):
            assert match.group(1) in registry, match.group(1)
            used.add(match.group(1))
        assert len(used) >= 15  # every family this slice wires, not a token few

    def test_every_remaining_inline_registry_icon_follows_the_global_geometry_contract(self):
        """Section 6's own goal (one stroke weight, round caps/joins,
        inherited colour) is already the file's ONE shared `.ww-icon svg`
        rule -- at this file's own native 18-unit grammar, not Lucide's
        native 24-unit one (see the registry's own comment for why pasting
        Lucide markup unmodified would visibly mismatch weight under that
        rule). DEC-143: most entries are now owner-supplied asset PATHS,
        exempt from this rule by design (they are masked, not stroked --
        see .ww-icon-asset's own comment); only a REMAINING inline <svg>
        entry (no owner asset exists for it yet) must still be the house
        18x18, so no icon silently breaks that shared rule."""
        source = _source()
        assert '.ww-icon svg {' in source
        shared_rule = _between(source, ".ww-icon svg {", "\n        }\n")
        for prop in ("stroke: currentColor", "fill: none", "stroke-width: 1.5", "stroke-linecap: round", "stroke-linejoin: round"):
            assert prop in shared_rule, prop
        inline = {k: v for k, v in _icon_registry(source).items() if v.startswith("<")}
        assert len(inline) >= 5  # CARET_DOWN/4 annotation-type icons
        for key, markup in inline.items():
            assert 'viewBox="0 0 18 18"' in markup, key

    def test_same_function_same_registry_key_waveform_and_er(self):
        """Section 1/22: the literal proof that Waveform and Event
        Reconstruction reference the SAME icon for the same function --
        not that their markup happens to match, but that they name the
        identical registry key."""
        source = _source()
        page = _er_page(source)
        pairs = [
            ("wwAnnotateBtn", "wwErAnnotateBtn", "ANNOTATE"),
            ("wwAnnotationListBtn", "wwErAnnotationListBtn", "ANNOTATIONS"),
            ("timeModeElapsedBtn", "wwErTimeElapsedBtn", "TIME_ELAPSED"),
            ("timeModeAbsoluteBtn", "wwErTimeAbsoluteBtn", "TIME_ABSOLUTE"),
            ("layoutModeGroupedBtn", "wwErViewGroupedBtn", "VIEW_GROUPED"),
        ]
        for wf_id, er_id, key in pairs:
            assert _icon_key(_element(source, wf_id, "button")) == key, wf_id
            assert _icon_key(_element(page, er_id, "button")) == key, er_id
        # Waveform's Relative Time (disabled stub) and Event
        # Reconstruction's own Relative Time (enabled) also share one key.
        assert _icon_key(_element(source, "timeModeRelativeBtn", "button")) == "TIME_RELATIVE"
        assert _icon_key(_element(page, "wwErTimeRelativeBtn", "button")) == "TIME_RELATIVE"
        # The A/B cursors icon used by every Time Group canvas and Event
        # Reconstruction's own canvas.
        canvas = _between(source, "function wwCreateTimeGroupCanvasDom(", "\n        }\n")
        assert 'data-ww-icon="CURSORS_AB"' in canvas
        assert _icon_key(_element(page, "wwErCursorModeBtn", "button")) == "CURSORS_AB"
        # DEC-141: Autoscale X (DEC-144: renamed from Reset Time View) /
        # Autoscale Y / Fit Selected Record all now reference the same
        # registry key on both pages (Waveform's own Fit Selected Record
        # is its new, permanently-disabled stub -- it has no "active
        # record" concept of its own).
        for key in ("AUTOSCALE_X", "AUTOSCALE_Y", "FIT_SELECTED_RECORD"):
            assert canvas.count(f'data-ww-icon="{key}"') == 1, key
            assert page.count(f'data-ww-icon="{key}"') == 1, key
        # DEC-141: the Zoom In/Out MAIN action -- Waveform's own dynamic
        # X/Y choice (ZOOM_X_IN/_OUT by default, swapped to ZOOM_Y_IN/_OUT
        # by wwSyncTimeGroupZoomControls()) and Event Reconstruction's own
        # static, always-X (it has no axis choice to make).
        for key in ("ZOOM_X_IN", "ZOOM_X_OUT"):
            assert f'data-ww-icon="{key}"' in canvas, key
        assert _icon_key(_element(page, "wwErZoomInBtn", "button")) == "ZOOM_X_IN"
        assert _icon_key(_element(page, "wwErZoomOutBtn", "button")) == "ZOOM_X_OUT"
        # DEC-141: the Y-axis Scale family's own dedicated Zoom In/Out --
        # Event Reconstruction's own (permanently disabled: no active-Y-
        # axis-target concept) use the SAME ZOOM_Y_IN/_OUT composites
        # Waveform's dynamic swap uses, never a separate definition.
        assert _icon_key(_element(page, "wwErZoomYInBtn", "button")) == "ZOOM_Y_IN"
        assert _icon_key(_element(page, "wwErZoomYOutBtn", "button")) == "ZOOM_Y_OUT"
        # The zoom-axis caret: Waveform's dynamic template only now --
        # Event Reconstruction retired its own (always-disabled, never
        # wired) copy once it gained dedicated Y buttons (DEC-141).
        assert canvas.count('data-ww-icon="CARET_DOWN"') == 2
        assert "wwErZoomInAxisBtn" not in page and "wwErZoomOutAxisBtn" not in page
        # The four annotation-type menu items, both menus.
        for kind, key in (("text_note", "ANNOTATION_TEXT_NOTE"), ("callout", "ANNOTATION_CALLOUT"),
                          ("peak_max", "ANNOTATION_PEAK_MAX"), ("peak_min", "ANNOTATION_PEAK_MIN")):
            assert source.count(f'data-annotation-type="{kind}"') == 2
            assert page.count(f'data-ww-icon="{key}"') == 1 and source.count(f'data-ww-icon="{key}"') == 2

    def test_view_grouped_and_combined_are_both_owner_supplied_unrelated_files(self):
        """Section 2/8 (DEC-140): VIEW_COMBINED was ORIGINALLY a composite
        built from VIEW_GROUPED's own inline shape. DEC-143 resolved
        VIEW_GROUPED's own icon gap with an owner-supplied asset
        (grouped_view.svg) -- both are now independent owner files with
        no shape relationship expected or enforced between them."""
        registry = _icon_registry(_source())
        assert registry["VIEW_GROUPED"] == "assets/icons/waveform/grouped_view.svg"
        assert not registry["VIEW_COMBINED"].startswith("<")
        assert registry["VIEW_GROUPED"] != registry["VIEW_COMBINED"]

    def test_unit_mode_now_uses_owner_supplied_icons_not_text(self):
        """DEC-143 supersedes DEC-140's §13 finding ("no unambiguous icon
        metaphor exists for Engineering/Per Unit, keep text") -- the
        owner has since supplied dedicated engineering_unit.svg/
        per_unit.svg and explicitly instructed removing the former
        "Units" label and ENG/PU text buttons. Both are now individual
        icon buttons (never a joined/segmented pair -- the owner's own
        separate "global tool button geometry" correction), same
        .ww-icon-btn-equivalent markup pattern as every other family."""
        registry = _icon_registry(_source())
        assert registry["UNIT_ENGINEERING"] == "assets/icons/waveform/engineering_unit.svg"
        assert registry["UNIT_PER_UNIT"] == "assets/icons/waveform/per_unit.svg"
        page = _er_page(_source())
        assert "Units</span>" not in page and 'id="wwErUnitModeLabel"' not in page
        eng = _element(page, "wwErUnitEngineeringBtn", "button")
        pu = _element(page, "wwErUnitPerUnitBtn", "button")
        assert ">ENG<" not in eng and ">PU<" not in pu
        assert _icon_key(eng) == "UNIT_ENGINEERING"
        assert _icon_key(pu) == "UNIT_PER_UNIT"
        assert 'title="Engineering Units"' in eng and 'title="Per Unit"' in pu
        # Individual buttons, not a joined pill: no .ww-er-view-mode (the
        # one exception class DEC-143 retired once Unit Mode joined every
        # other family's treatment).
        toggle = _between(page, 'id="wwErUnitModeToggle"', ">")
        assert "ww-er-view-mode" not in toggle

    def test_zoom_xy_composites_are_registered_and_now_wired(self):
        """DEC-141 (amending DEC-140's own deferral): the ZOOM_X/Y_IN/OUT
        composites are now live -- Waveform's Zoom In/Out own MAIN action
        icon (dynamically swapped with its existing X/Y choice, never
        changing the choice/interaction logic itself) and Event
        Reconstruction's consolidated Time Navigation (X, live) and
        Y-axis Scale (Y, permanently disabled -- no target concept yet)
        families. Still never a second definition per key."""
        source = _source()
        registry = _icon_registry(source)
        for key in ("ZOOM_X_IN", "ZOOM_X_OUT", "ZOOM_Y_IN", "ZOOM_Y_OUT"):
            assert key in registry
            assert source.count(f'data-ww-icon="{key}"') >= 1, key
        sync = _between(source, "function wwSyncTimeGroupZoomControls(groupId) {", "\n        }\n")
        assert 'const iconKey = "ZOOM_" + axis.toUpperCase() + "_" + (action === "in" ? "IN" : "OUT");' in sync
        assert "if (iconSpan.dataset.wwIcon !== iconKey) wwSetToolIcon(iconSpan, iconKey);" in sync


class TestEventReconstructionToolConsistency:
    """DEC-137/DEC-139/DEC-140: common tools across Powerwave pages share
    iconography, tooltip wording, compact button styling and interaction
    language (the icon/component, not just its presence); page state and
    workflow stay independently owned. Every assertion below compares
    against the ACTUAL Waveform markup read from the same source -- never
    an assumed/expected string -- so a future Waveform edit that drifts
    from this file would fail these tests rather than go unnoticed."""

    def test_no_drag_mode_toggle_remains_on_either_page(self):
        """DEC-144: Box Zoom is retired -- there is no "drag mode" to
        select any more (Pan is the only plot-area interaction mode), so
        neither page has a dragModeToggle/wwErDragModeToggle control."""
        source = _source()
        page = _er_page(source)
        for forbidden in ('id="dragModeToggle"', 'id="dragModeZoomBtn"', 'id="dragModePanBtn"',
                           'id="wwErDragModeToggle"', 'id="wwErDragModeZoomBtn"', 'id="wwErDragModePanBtn"'):
            assert forbidden not in source, forbidden
        assert 'title="Box Zoom"' not in source and 'title="Box Zoom"' not in page

    def test_annotate_and_annotations_controls_are_waveforms(self):
        source = _source()
        page = _er_page(source)
        wf_split = _between(source, '<div class="ww-split-btn" id="wwAnnotateSplit">', 'id="wwAnnotationListBtn"')
        er_split = _between(page, '<div class="ww-split-btn" id="wwErAnnotateSplit">', 'id="wwErAnnotationListBtn"')
        for same in ('title="Annotate" aria-label="Annotate"', 'aria-label="Annotation type"', "Text Note", "Callout",
                     "Maximum Peak (+Peak)", "Minimum Peak (-Peak)"):
            assert same in er_split and same in wf_split, same
        for kind in ("text_note", "callout", "peak_max", "peak_min"):
            assert f'data-annotation-type="{kind}"' in er_split
        wf_list = _element(source, "wwAnnotationListBtn", "button")
        er_list = _element(page, "wwErAnnotationListBtn", "button")
        assert 'title="Annotations" aria-label="Annotations"' in er_list and 'title="Annotations" aria-label="Annotations"' in wf_list
        assert 'class="ww-annotation-count-badge" id="wwErAnnotationCountBadge"' in er_list
        # Inside Event Reconstruction's own global toolbar, in the
        # Analysis family (DEC-141): Cursors, Annotate, Annotations.
        toolbar = _between(page, '<div class="ww-toolbar" id="wwErToolbar">', 'id="wwErAnnotationGuidance"')
        assert 'id="wwErAnnotateSplit"' in toolbar and 'id="wwErAnnotationListBtn"' in toolbar
        assert toolbar.index('id="wwErCursorModeBtn"') < toolbar.index('id="wwErAnnotateSplit"')

    def test_equivalent_canvas_tools_reuse_waveforms_classes_and_exact_tooltips(self):
        """Section 1/9/18: not just the tooltip string -- the same compact
        button CLASS every one of these controls carries (DEC-141: Event
        Reconstruction's own copies are now `.ww-icon-btn`, consolidated
        into the global header, since the owner's own explicit "do not
        leave Reset/Autoscale/Zoom as a large text button" instruction for
        THIS page -- Waveform's own canvas-toolbar precedent, DEC-139, is
        unaffected), and the canonical "Time Axis"/"Selected Y Axis"
        wording (DEC-140) in place of the old generic "X axis"/"Y axis"."""
        source = _source()
        page = _er_page(source)
        canvas = _between(source, "function wwCreateTimeGroupCanvasDom(", "\n        }\n")
        for shared_class in ("ww-tg-reset-view-btn", "ww-tg-autoscale-btn", "ww-tg-cursor-mode-btn"):
            assert shared_class in canvas, shared_class
            assert shared_class in page, shared_class
        assert 'class="ww-icon-btn" id="wwErZoomInBtn"' in page
        assert 'class="ww-icon-btn" id="wwErZoomOutBtn"' in page
        assert 'class="ww-icon-btn ww-tg-reset-view-btn" id="wwErResetViewBtn"' in page
        assert 'class="ww-icon-btn ww-tg-autoscale-btn" id="wwErAutoscaleYBtn"' in page
        assert 'class="ww-icon-btn ww-tg-cursor-mode-btn" id="wwErCursorModeBtn"' in page
        for markup in (
            'id="wwErZoomInBtn" title="Zoom In — Time Axis" aria-label="Zoom In — Time Axis"',
            'id="wwErZoomOutBtn" title="Zoom Out — Time Axis" aria-label="Zoom Out — Time Axis"',
            'id="wwErResetViewBtn" title="Autoscale X" aria-label="Autoscale X" disabled>',
            'id="wwErAutoscaleYBtn" title="Autoscale Y" aria-label="Autoscale Y" disabled>',
        ):
            assert markup in page, markup
        for base in ("Zoom In — Time Axis", "Zoom Out — Time Axis", "Choose Zoom In axis", "Choose Zoom Out axis"):
            assert base in canvas
        for old in ("never beyond Fit All", "Fit All and autoscale Y on every panel", "Autoscale Y on every panel",
                    "Event Reconstruction zooms the time axis only", "— X axis", "— Y axis"):
            assert old not in page, old

    def test_ab_cursors_icon_is_byte_identical_to_waveform(self):
        source = _source()
        page = _er_page(source)
        canvas = _between(source, "function wwCreateTimeGroupCanvasDom(", "\n        }\n")
        assert 'data-ww-icon="CURSORS_AB"' in canvas
        er_cursor = _element(page, "wwErCursorModeBtn", "button")
        assert _icon_key(er_cursor) == "CURSORS_AB"
        assert 'class="ww-icon-btn ww-tg-cursor-mode-btn"' in er_cursor
        assert 'title="A/B Time Cursors" aria-label="A/B Time Cursors"' in er_cursor

    def test_event_reconstruction_specific_tools_get_their_own_icon_same_compact_design(self):
        """DEC-141: Fit Selected Record now sits in the global header's
        Fit/Reset family (no page-specific canvas toolbar left at all),
        and its own icon is a registry entry (FIT_SELECTED_RECORD) --
        Waveform's own new disabled stub reuses the identical key."""
        source = _source()
        page = _er_page(source)
        fit = _element(page, "wwErFitRecordBtn", "button")
        assert 'class="ww-icon-btn ww-er-fit-record-btn"' in fit and 'aria-label="Fit selected record"' in fit
        assert _icon_key(fit) == "FIT_SELECTED_RECORD"
        canvas = _between(source, "function wwCreateTimeGroupCanvasDom(", "\n        }\n")
        assert 'class="ww-icon-btn ww-tg-fit-record-btn"' in canvas
        assert 'title="Fit selected record — unavailable in Waveform"' in canvas
        # Within the header: Fit Selected Record precedes the paired
        # Autoscale X/Y group (section 8's own order).
        toolbar = _between(page, '<div class="ww-toolbar" id="wwErToolbar">', 'id="wwErAnnotationGuidance"')
        assert toolbar.index('id="wwErFitRecordBtn"') < toolbar.index('id="wwErResetViewBtn"')

    def test_autoscale_x_and_y_are_paired_adjacent_individual_buttons(self):
        """DEC-145 (owner correction): Autoscale X and Autoscale Y are a
        paired axis-scaling function and sit adjacent in their own group
        -- [Autoscale X][Autoscale Y], nothing else between them, each
        its own individual button (never a joined/segmented pair)."""
        page = _er_page(_source())
        x_btn = _element(page, "wwErResetViewBtn", "button")
        x_end = page.index(x_btn) + len(x_btn)
        y_start = page.index('<button type="button" class="ww-icon-btn ww-tg-autoscale-btn" id="wwErAutoscaleYBtn"')
        gap = page[x_end:y_start]
        assert "<button" not in gap  # no other control in between
        assert "theme-toggle" not in gap and "ww-icon-group" not in gap  # not a segmented pair
        y_btn = _element(page, "wwErAutoscaleYBtn", "button")
        assert 'title="Autoscale X"' in x_btn and 'title="Autoscale Y"' in y_btn
        assert _icon_key(x_btn) == "AUTOSCALE_X" and _icon_key(y_btn) == "AUTOSCALE_Y"

    def test_unit_mode_is_now_an_icon_family_like_every_other(self):
        """DEC-143 supersedes section 11/13's own DEC-140-era hedge: Unit
        Mode is now an icon family exactly like Time Display/View Mode --
        individual compact buttons (no joined .ww-er-view-mode pill), the
        owner-supplied engineering_unit.svg/per_unit.svg, and no leftover
        ENG/PU/"Units" text. See TestPowerwaveIconSystem's own dedicated
        test for the full reasoning."""
        page = _er_page(_source())
        for button, key in (("wwErUnitEngineeringBtn", "UNIT_ENGINEERING"), ("wwErUnitPerUnitBtn", "UNIT_PER_UNIT")):
            element = _element(page, button, "button")
            assert ">ENG<" not in element and ">PU<" not in element
            assert _icon_key(element) == key
        group = _element(page, "wwErUnitModeToggle", "div")
        assert 'class="theme-toggle ww-icon-group"' in group
        assert "ww-er-view-mode" not in group

    def test_disabled_state_uses_the_shared_rule_no_er_specific_override(self):
        """Section 15D/16: no page-scoped CSS rule weakens or replaces the
        shared disabled treatment every compact tool -- icon-button or
        icon-group member alike -- already uses."""
        source = _source()
        assert ".ww-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; background: transparent; }" in source
        # Owner correction (individual-button geometry): a disabled icon-
        # group member now shares .ww-toolbar .ww-icon-btn's own exact
        # disabled treatment (opacity 0.42) rather than a group-specific
        # 0.5 rule -- see .ww-toolbar .theme-toggle.ww-icon-group
        # button:disabled's own definition.
        assert ".ww-toolbar .theme-toggle.ww-icon-group button:disabled {" in source
        group_disabled = _between(source, ".ww-toolbar .theme-toggle.ww-icon-group button:disabled {", "\n        }\n")
        assert "opacity: 0.42;" in group_disabled
        page = _er_page(source)
        for button_id in ("wwErZoomInBtn", "wwErZoomOutBtn", "wwErResetViewBtn", "wwErAutoscaleYBtn", "wwErCursorModeBtn",
                          "wwErFitRecordBtn", "wwErTimeElapsedBtn"):
            assert "disabled" in _element(page, button_id, "button")
        assert "disabled" in _element(source, "timeModeRelativeBtn", "button")
        for forbidden in (".ww-er-fit-record-btn:disabled", "#wwErCanvasToolbar .ww-icon-btn:disabled", "#wwErToolbar .secondary:disabled"):
            assert forbidden not in source, forbidden

    def test_waveform_toolbar_is_unchanged(self):
        source = _source()
        assert '<button type="button" class="ww-icon-btn" id="wwAnnotateBtn" aria-haspopup="menu" aria-expanded="false" aria-pressed="false" title="Annotate" aria-label="Annotate">' in source
        assert '<button class="ww-icon-btn" type="button" id="wwAnnotationListBtn" aria-pressed="false" aria-expanded="false" title="Annotations" aria-label="Annotations">' in source
        canvas = _between(source, "function wwCreateTimeGroupCanvasDom(", "\n        }\n")
        for wording in ("Autoscale X for this Time Group", "Autoscale Y for this Time Group",
                        "Choose Zoom In axis", "A/B Time Cursors for this Time Group"):
            assert wording in canvas, wording
        # Section 18's new wording lands on BOTH pages via the one shared
        # sync function (the owner's own worked example: "Zoom In — Time
        # Axis" if the ER function is the same) -- Waveform's zoom
        # behaviour/markup structure is otherwise untouched.
        assert "ww-toolbar-sep" not in canvas

    def test_shared_toolbar_primitives_never_introduce_shared_state(self):
        """Section 12/19/24: the same icon/component, ER's own handler and
        state -- never a read of Waveform's own `ww` drag mode, time mode,
        view mode, cursor state or annotation state. DEC-144: there is no
        wwErSetDragMode()/wwSetDragMode() left at all (Box Zoom retired,
        nothing to toggle) -- wwErState.dragMode is set once, at
        initialisation, to the fixed "pan"."""
        module = _er_module(_source())
        for forbidden in (
            "ww.dragMode", "ww.panels", "ww.timeGroupCursorState", "ww.annotationPlacementType", "ww.annotations",
            "ww.timeMode", "ww.layoutMode", "wwSyncTimeGroupZoomControls", "wwCreateTimeGroupCanvasDom",
            "wwSetTimeMode(", "wwSetLayoutMode(", "wwToggleTimeGroupCursors",
        ):
            assert forbidden not in module, forbidden
        source = _source()
        assert "wwSetDragMode" not in source and "wwErSetDragMode" not in source


class TestGlobalTimeDisplayFamily:
    """DEC-140 section 9/10/16/23/24: one coherent 3-icon Time Display
    family (Elapsed/Relative/Absolute) on every waveform-capable page.
    Each page enables only the modes it genuinely supports; the rest stay
    visible, disabled, with a tooltip explaining why -- never hidden."""

    def test_order_and_icons_match_on_both_pages(self):
        source = _source()
        page = _er_page(source)
        wf_group = _div_by_id(source, "timeModeToggle")
        er_group = _div_by_id(page, "wwErTimeDisplayToggle")
        wf_order = sorted(("timeModeElapsedBtn", "timeModeRelativeBtn", "timeModeAbsoluteBtn"), key=lambda i: wf_group.index(f'id="{i}"'))
        assert wf_order == ["timeModeElapsedBtn", "timeModeRelativeBtn", "timeModeAbsoluteBtn"]
        assert __import__("re").findall(r'id="(wwErTime\w+Btn)"', er_group) == ["wwErTimeElapsedBtn", "wwErTimeRelativeBtn", "wwErTimeAbsoluteBtn"]
        assert _icon_key(_element(wf_group, "timeModeElapsedBtn", "button")) == "TIME_ELAPSED"
        assert _icon_key(_element(wf_group, "timeModeRelativeBtn", "button")) == "TIME_RELATIVE"
        assert _icon_key(_element(wf_group, "timeModeAbsoluteBtn", "button")) == "TIME_ABSOLUTE"
        assert _icon_key(_element(er_group, "wwErTimeElapsedBtn", "button")) == "TIME_ELAPSED"
        assert _icon_key(_element(er_group, "wwErTimeRelativeBtn", "button")) == "TIME_RELATIVE"
        assert _icon_key(_element(er_group, "wwErTimeAbsoluteBtn", "button")) == "TIME_ABSOLUTE"

    def test_capability_matrix(self):
        """Section 15's own matrix: Waveform Elapsed=ON/Relative=OFF/
        Absolute=ON; Event Reconstruction Elapsed=OFF/Relative=ON/
        Absolute=ON."""
        source = _source()
        page = _er_page(source)
        assert "disabled" not in _element(source, "timeModeElapsedBtn", "button")
        wf_relative = _element(source, "timeModeRelativeBtn", "button")
        assert "disabled" in wf_relative
        assert "disabled" not in _element(source, "timeModeAbsoluteBtn", "button")
        er_elapsed = _element(page, "wwErTimeElapsedBtn", "button")
        assert "disabled" in er_elapsed
        assert "disabled" not in _element(page, "wwErTimeRelativeBtn", "button")
        assert "disabled" not in _element(page, "wwErTimeAbsoluteBtn", "button")

    def test_disabled_tooltips_explain_why_section_16(self):
        source = _source()
        page = _er_page(source)
        assert 'title="Relative Time — unavailable in Waveform" aria-label="Relative Time — unavailable in Waveform"' in source
        assert 'title="Elapsed Time — unavailable in Event Reconstruction" aria-label="Elapsed Time — unavailable in Event Reconstruction"' in page

    def test_tooltip_wording_is_identical_across_pages_for_the_same_mode(self):
        """Section 18: same semantic tool, same tooltip -- the disabled
        reason clause is the only thing that may differ (it names the
        page), the base mode name never does."""
        source = _source()
        page = _er_page(source)
        assert 'title="Absolute Time" aria-label="Absolute Time"' in source
        assert 'title="Absolute Time" aria-label="Absolute Time"' in page
        assert 'title="Relative Time"' in page and "aria-label=\"Relative Time\"" in page
        assert 'title="Elapsed Time" aria-label="Elapsed Time"' in source


class TestGlobalViewModeFamily:
    """DEC-140 section 11/12/14/23: Grouped/Combined use one shared icon
    family. Event Reconstruction has no Custom Layout or Split View
    concept (neither per-channel custom grouping nor a table to split
    with) -- no stub buttons are invented for capabilities it never had
    (section 12/21's own "do not invent functionality")."""

    def test_grouped_combined_are_icon_buttons_on_both_pages(self):
        page = _er_page(_source())
        for button in ("wwErViewGroupedBtn", "wwErViewCombinedBtn"):
            element = _element(page, button, "button")
            assert "data-ww-icon" in element and "<svg" not in element

    def test_er_shows_the_full_view_mode_family_separate_custom_split_disabled(self):
        """DEC-141 (reversing DEC-140's own prior "no invented stubs"
        reasoning for View Mode specifically, per the owner's explicit,
        UAT-informed "do not omit unsupported global slots" instruction):
        Separate/Custom/Split now exist on Event Reconstruction too,
        permanently disabled, each with a tooltip naming the page."""
        source = _source()
        page = _er_page(source)
        group = _element(page, "wwErViewModeToggle", "div")
        ids = __import__("re").findall(r'id="(wwErView\w+Btn)"', group)
        assert ids == ["wwErViewGroupedBtn", "wwErViewCombinedBtn", "wwErViewSeparateBtn", "wwErViewCustomBtn", "wwErViewSplitBtn"]
        for button_id, key in (("wwErViewSeparateBtn", "VIEW_SEPARATE"), ("wwErViewCustomBtn", "VIEW_CUSTOM"), ("wwErViewSplitBtn", "VIEW_SPLIT")):
            element = _element(page, button_id, "button")
            assert "disabled" in element
            assert _icon_key(element) == key
            assert "unavailable in Event Reconstruction" in element
        # The SAME registry keys as Waveform's own existing icons -- never
        # a second definition.
        assert _icon_key(_element(source, "layoutModeSeparateBtn", "button")) == "VIEW_SEPARATE"
        assert _icon_key(_element(source, "layoutModeCustomBtn", "button")) == "VIEW_CUSTOM"
        assert _icon_key(_element(source, "wwSplitViewBtn", "button")) == "VIEW_SPLIT"


class TestEventReconstructionPerUnitDisplay:
    """DEC-138: Waveform owns per-unit configuration; Event Reconstruction
    consumes the backend's RESOLVED per-unit result and only switches its
    display between Engineering and Per Unit."""

    def test_unit_selector_uses_waveforms_wording_as_a_labelled_mode_selector(self):
        """DEC-143: Event Reconstruction's own ENG/PU switch is now two
        icon buttons (owner-supplied engineering_unit.svg/per_unit.svg),
        not text -- but the ARIA wording ("Unit Mode", "Engineering
        Units", "Per Unit") is unchanged, still Waveform's own words, via
        title/aria-label rather than visible text content."""
        source = _source()
        page = _er_page(source)
        toggle = _between(page, '<div class="theme-toggle ww-icon-group" id="wwErUnitModeToggle"', "</div>")
        assert 'role="group" aria-label="Unit Mode"' in toggle
        assert 'id="wwErUnitEngineeringBtn" aria-pressed="true" title="Engineering Units" aria-label="Engineering Units"' in toggle
        assert 'id="wwErUnitPerUnitBtn" aria-pressed="false" title="Per Unit" aria-label="Per Unit"' in toggle
        assert ">Units</span>" not in page  # the former text label is gone
        # Waveform's own words for the same switch.
        assert 'title="Unit Mode" aria-label="Unit Mode"' in source
        for words in ("Engineering Units", "Per Unit"):
            assert words in _between(source, '<div class="ww-split-menu" id="wwUnitModeMenu"', "</div>")
        assert 'textContent = ww.unitMode === "per_unit" ? "PU" : "ENG";' in source
        # Default Engineering.
        assert 'unitMode: "engineering",' in _between(source, "const wwErState = {", "};")

    def test_no_per_unit_configuration_in_event_reconstruction(self):
        source = _source()
        page = _er_page(source)
        for forbidden in ("Per-Unit Settings</button>", "wwOpenPerUnitSettingsBtn", "Manage Per-Unit", "Measurement Group", "nominal_voltage_ll_kv",
                          'type="number"', "Line-to-Ground", "line_to_ground"):
            assert forbidden not in page, forbidden
        module = _er_module(source)
        # Never a write to (or a read of the editors of) per-unit settings.
        for forbidden in ("/per-unit/sources", "/measurement-groups", "voltage-config", "current-config", "wwOpenPerUnit",
                          "wwApplyUnitMode", "ww.unitMode", "ww.perUnit", "wwSavePerUnit"):
            assert forbidden not in module, forbidden
        # The settings writes that exist stay Waveform's.
        assert "voltage-config" in source

    def test_resolution_is_the_backends_and_values_are_never_converted_here(self):
        source = _source()
        fetch = _between(source, "async function wwErFetchPerUnitResolution(kind, sourceId, channelName) {", "\n        }\n")
        assert "wwFetchChannelPerUnitResolution(sourceId, channelName)" in fetch
        assert '"/per-unit-resolution"' in fetch
        display = _between(source, "function wwErChannelUnitDisplay(kind, sourceId, channelName, unitMode = wwErState.unitMode) {", "\n        }\n")
        assert 'if (resolution.status === "configured") return { state: "per_unit", unitMode: "per_unit"' in display
        assert 'if (resolution.status === "not_applicable") return { state: "engineering", unitMode: "engineering"' in display
        assert 'return { state: "unavailable", unitMode: null' in display
        module = _er_module(source)
        # No base is derived and no value converted in the frontend.
        for forbidden in ("Math.sqrt", "SQRT", "1.732", "effective_base_amount", "nominal_base_kv", "/ base", "* base"):
            assert forbidden not in module, forbidden

    def test_unavailable_channels_stay_selected_never_plotted_never_valued(self):
        source = _source()
        items = _between(source, "function wwErPlotItems() {", "// ---- Per-Unit Display (DEC-138) ----")
        assert 'plottable: display.state === "engineering" || display.state === "per_unit",' in items
        render = _between(source, "function wwErRenderPlot() {", "function wwErSetViewMode(mode)")
        assert "const plotted = items.filter((item) => item.plottable);" in render
        assert "const fitAll = wwErFitAllRange(items.map((item) => item.timing));" in render
        tree = _between(source, "function wwErTreeCursorText(key, kind) {", "\n        }\n")
        assert 'return kind === "delta" ? "—" : WW_ER_PU_UNAVAILABLE_CELL;' in tree
        assert 'if (entry.puUnavailable) return WW_ER_PU_UNAVAILABLE_CELL;' in _between(source, "function wwErCursorValueText(entry, kind) {", "\n        }\n")
        load = _between(source, "async function wwErLoadTrace(trace) {", "function wwErPlottedTraces()")
        assert 'if (trace.unitMode === "per_unit" && body.per_unit_status !== "configured") {' in load
        # Engineering values never land on a pu axis: a unit switch starts
        # the trace empty unless that display's own data is kept.
        assign = _between(source, "function wwErAssignTraceUnit(trace, item) {", "\n        }\n")
        assert "reconstructionTime: [], values: []," in assign and "trace.unitCache[key]" in assign

    def test_the_switch_is_display_only(self):
        source = _source()
        switch = _between(source, "function wwErSetUnitMode(mode) {", "\n        }\n")
        for forbidden in ("viewport", "cursors", "definition", "selectedChannels", "activeRecordId", "timeDisplay", "viewMode", "wwErMutate", "fetch("):
            assert forbidden not in switch, forbidden
        assert "wwErRenderPlot();" in switch

    def test_waveform_unit_mode_is_untouched(self):
        source = _source()
        waveform = _between(source, "function wwPanelGroupKeyFor(", "function wwTimeGroupLabelSuffix(")
        assert "wwEr" not in waveform
        assert 'if (channel.perUnitStatus === "base_required") return baseKey + ":base_required";' in waveform


class TestPowerwaveIconAssets:
    """DEC-143: Powerwave icons are owner-approved local SVG assets under
    frontend/assets/icons/**, referenced by the semantic registry through
    a path rather than duplicated inline markup. Static guards proving
    the asset structure, the manifest, and the registry/markup's use of
    it -- independent of (and in addition to) TestPowerwaveIconSystem's
    own DEC-140-era checks, most of which still hold for the handful of
    entries with no owner asset yet."""

    ICONS_DIR = FRONTEND.parent / "assets" / "icons"
    BRANDING_DIR = FRONTEND.parent / "assets" / "branding"

    def test_asset_folder_structure_exists(self):
        for sub in ("common", "navigation", "waveform"):
            d = self.ICONS_DIR / sub
            assert d.is_dir(), d
        assert self.BRANDING_DIR.is_dir()
        assert (self.ICONS_DIR / "README.md").is_file()
        assert (self.ICONS_DIR / "manifest.json").is_file()
        assert (self.BRANDING_DIR / "README.md").is_file()

    def test_manifest_entries_all_resolve_to_a_real_file_or_are_explicit_gaps(self):
        import json
        manifest = json.loads((self.ICONS_DIR / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest) >= 25
        for key, entry in manifest.items():
            if entry["source"] == "inline-fallback":
                assert entry["file"] is None, key  # an explicit, reported gap -- not a broken path
                continue
            assert entry["source"] == "owner-supplied", key
            path = self.ICONS_DIR / entry["file"]
            assert path.is_file(), f"{key}: {path}"
            assert path.suffix == ".svg", key

    def test_registry_matches_the_manifest(self):
        """Every manifest entry with a file is the SAME path the registry
        itself resolves that key to -- the manifest is a true record of
        what ships, not a separate, driftable catalogue."""
        import json
        manifest = json.loads((self.ICONS_DIR / "manifest.json").read_text(encoding="utf-8"))
        registry = _icon_registry(_source())
        for key, entry in manifest.items():
            assert key in registry, key
            if entry["file"] is None:
                assert registry[key].startswith("<"), key
            else:
                assert registry[key] == "assets/icons/" + entry["file"], key

    def test_migrated_entries_are_asset_paths_not_inline_markup(self):
        """Section 19's own guard: a migrated entry is a path, never SVG
        markup -- the opposite of the handful of still-inline (no owner
        asset yet) entries TestPowerwaveIconSystem's geometry test covers."""
        registry = _icon_registry(_source())
        migrated = ("ANNOTATIONS", "ANNOTATE", "SEARCH", "PAN",
                    "ZOOM_X_IN", "ZOOM_X_OUT", "ZOOM_Y_IN", "ZOOM_Y_OUT",
                    "TIME_ELAPSED", "TIME_RELATIVE", "TIME_ABSOLUTE", "UNIT_ENGINEERING", "UNIT_PER_UNIT",
                    "VIEW_SEPARATE", "VIEW_CUSTOM", "VIEW_COMBINED", "VIEW_SPLIT", "VIEW_GROUPED",
                    "CURSORS_AB", "AUTOSCALE_X", "AUTOSCALE_Y", "FIT_SELECTED_RECORD")
        for key in migrated:
            value = registry[key]
            assert not value.startswith("<"), key
            assert not value.startswith("http://") and not value.startswith("https://") and not value.startswith("//"), key
            assert value.startswith("assets/icons/"), key
            assert (self.ICONS_DIR.parent.parent / value).is_file(), key

    def test_axis_specific_zoom_keys_each_have_their_own_distinct_file(self):
        """DEC-146: a follow-up owner delivery gave each axis-specific
        zoom key its own dedicated icon, superseding the former
        ZOOM_IN/ZOOM_OUT-aliasing scheme (section 7's 'do not invent
        compound icons' placeholder) -- the four keys must now resolve
        to four DIFFERENT files, never collapse back to a shared pair."""
        registry = _icon_registry(_source())
        values = {registry["ZOOM_X_IN"], registry["ZOOM_X_OUT"], registry["ZOOM_Y_IN"], registry["ZOOM_Y_OUT"]}
        assert len(values) == 4
        assert "ZOOM_IN" not in registry and "ZOOM_OUT" not in registry
        assert "ZOOM_HORIZONTAL" not in registry and "ZOOM_VERTICAL" not in registry

    def test_no_remote_icon_urls(self):
        source = _source()
        registry = _icon_registry(source)
        for key, value in registry.items():
            assert "http://" not in value and "https://" not in value, key
        # No CDN/remote <link> or <script> feeds an icon anywhere in the
        # file's own icon machinery.
        icon_region = _between(source, "const WW_TOOL_ICONS = {", "function wwApplyToolIcons(")
        assert "cdn." not in icon_region and "googleapis" not in icon_region

    def test_owner_supplied_icons_are_never_also_duplicated_inline(self):
        """A migrated key's old inline <svg> definition is gone -- asset
        and inline fallback never coexist for the same key (section 17:
        "do not keep asset + inline fallback unless there is a proven
        technical necessity", and none is claimed here)."""
        registry = _icon_registry(_source())
        for key, value in registry.items():
            if not value.startswith("<"):
                continue
            # The few still-inline keys are exactly the reported gaps --
            # never one that also has a manifest/asset entry.
            import json
            manifest = json.loads((self.ICONS_DIR / "manifest.json").read_text(encoding="utf-8"))
            assert manifest[key]["source"] == "inline-fallback", key

    def test_no_new_inline_svg_blocks_for_migrated_controls(self):
        """Section 19's own guard: a migrated control's markup carries
        `data-ww-icon`, never a hand-written `<svg>` of its own -- the
        nav icons (DEC-143) and every pre-existing toolbar control alike."""
        source = _source()
        for btn_id in ("mainNavRecordingsBtn", "mainNavWaveformBtn", "mainNavEventReconstructionBtn",
                       "mainNavTableBtn", "mainNavCalculatedChannelsBtn", "mainNavAnalysisBtn",
                       "mainNavComplianceBtn", "mainNavCalculatorBtn"):
            element = _element(source, btn_id, "button")
            assert "<svg" not in element, btn_id
            assert 'data-ww-icon="PAGE_' in element, btn_id
        # Settings keeps its own inline icon -- no owner asset supplied
        # for it; the one deliberate exception among nav items.
        settings = _element(source, "mainNavSettingsBtn", "button")
        assert "<svg" in settings and "data-ww-icon" not in settings

    def test_asset_rendering_uses_css_mask_not_img_or_fetch_inject(self):
        """Section 11's own technique decision: the supplied files are not
        colour-uniform (some stroke="currentColor", most a hardcoded
        fill/stroke), so a plain <img> would show the wrong fixed colour
        in at least one theme, and fetch+inject would have to parse/strip
        each file's own colour to theme it (editing the artwork in
        spirit). A CSS mask reads only the silhouette and paints it with
        the control's own currentColor -- correct for every file, in
        both themes, without touching any artwork."""
        source = _source()
        assert ".ww-icon-asset {" in source
        mask_rule = _between(source, ".ww-icon-asset {", "\n        }\n")
        assert "background-color: currentColor" in mask_rule
        assert "mask-image" not in mask_rule  # the per-icon mask-image is set inline by wwSetToolIcon(), not hardcoded here
        assert "mask-size: contain" in mask_rule
        set_icon = _between(source, "function wwSetToolIcon(el, key) {", "\n        }\n")
        assert 'el.style.maskImage = \'url("\' + value + \'")\';' in set_icon
        assert 'el.style.webkitMaskImage = \'url("\' + value + \'")\';' in set_icon
        assert "new Image(" not in set_icon and "<img" not in set_icon
        assert "await fetch(" not in set_icon and ".then(" not in set_icon

    def test_dockerfile_ships_the_assets_folder(self):
        """A packaging guard, not a frontend-source one: WW_TOOL_ICONS
        references assets/icons/** by relative path at runtime, so the
        production image must actually contain it -- the Dockerfile's
        existing COPY list (vendor/, config.js, ...) does not do this
        automatically; nothing else in it would either."""
        dockerfile = (FRONTEND.parent / "Dockerfile").read_text(encoding="utf-8")
        assert "COPY assets /usr/share/nginx/html/assets" in dockerfile
