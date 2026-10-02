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
        page = _er_page(_source())
        assert 'id="wwErDragModeZoomBtn" aria-pressed="true" title="Box Zoom" aria-label="Box Zoom"' in page
        assert 'id="wwErDragModePanBtn" aria-pressed="false" title="Pan" aria-label="Pan"' in page
        assert re.search(r'id="wwErZoomInBtn"[^>]*disabled>Zoom In</button>', page)
        assert re.search(r'id="wwErZoomOutBtn"[^>]*disabled>Zoom Out</button>', page)
        assert re.search(r'id="wwErResetViewBtn"[^>]*disabled>Reset Time View</button>', page)

    def test_controls_reuse_waveform_toolbar_markup_classes(self):
        page = _er_page(_source())
        assert '<div class="theme-toggle ww-icon-group" id="wwErDragModeToggle" role="group" aria-label="Drag mode">' in page
        assert '<div class="ww-split-btn ww-tg-zoom-in-split">' in page
        assert '<div class="ww-split-btn ww-tg-zoom-out-split">' in page
        assert 'class="secondary ww-tg-reset-view-btn" id="wwErResetViewBtn"' in page
        assert '<div class="ww-tg-toolbar" id="wwErCanvasToolbar">' in page

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
        for forbidden in ("wwSetDragMode(", "wwStepZoomX(", "wwStepZoomY(", "wwResetOneTimeGroupView(", "wwWireTimeGroupToolbar("):
            assert forbidden not in module

    def test_drag_mode_buttons_use_event_reconstruction_state_only(self):
        source = _source()
        assert 'document.getElementById("wwErDragModeZoomBtn").addEventListener("click", () => wwErSetDragMode("zoom"));' in source
        assert 'document.getElementById("wwErDragModePanBtn").addEventListener("click", () => wwErSetDragMode("pan"));' in source
        set_mode = _between(source, "function wwErSetDragMode(mode) {", "// ---- API ----")
        assert "wwErState.dragMode = mode;" in set_mode
        assert "Plotly" not in set_mode

    def test_no_event_reconstruction_channel_presentation_store(self):
        source = _source()
        module = _er_module(source)
        state = _between(source, "const wwErState = {", "};")
        keys = re.findall(r"^ {12}(\w+):", state.split("{", 1)[1], re.MULTILINE)
        # Workspace state, the last API responses and (Slice 3C) the
        # renderer's own plot state only.
        assert keys == [
            "dragMode", "sources", "records", "definition",
            "channelsBySource", "calculatedChannels", "selectedChannels", "loadSeq", "busy", "plot",
        ]
        plot_keys = re.findall(r"^ {16}(\w+):", state.split("plot: {", 1)[1], re.MULTILINE)
        assert plot_keys == [
            "viewMode", "panels", "viewport", "fitAll", "atFitAll", "origin", "relayoutTimer",
            "cursors", "cursorRequests", "cursorValuesTimer",
        ]
        for forbidden in ("PresentationOverrides", "channelColors", "ColorOverride", "DisplayName =", "localStorage"):
            assert forbidden not in module
        # The only ER-owned persisted value is the left panel width; the
        # rest are renderer constants.
        assert re.findall(r"const (?:WW_ER_|wwEr)\w+", module) == [
            "const WW_ER_SIDEBAR_WIDTH_STORAGE_KEY", "const wwErState", "const WW_ER_PANEL_HEIGHT",
            "const WW_ER_COMBINED_PANEL_HEIGHT", "const WW_ER_COMBINED_AXIS_ADVISORY",
            "const WW_ER_UNKNOWN_QUANTITY_LABEL", "const WW_ER_ORIGIN_MAX_SPANS", "const WW_ER_RELAYOUT_DEBOUNCE_MS", "const WW_ER_TIME_AXIS_TITLE",
            "const WW_ER_OUTLIER_GAP_FRACTION",
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
        for element_id in ("wwErZoomInBtn", "wwErZoomInAxisBtn", "wwErZoomOutBtn", "wwErZoomOutAxisBtn", "wwErResetViewBtn"):
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
        assert "warning.message" in notices
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
        # The only POST is the read-only cursor-values query (Slice 3E):
        # nothing is created, renamed or recoloured from here.
        assert module.count('method: "POST"') == 1
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
        chrome = _between(_source(), "function wwErSyncPlotChrome() {", "function wwErApplyDragMode()")
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
        # The renderer's only direct request is the cursor-values query;
        # waveform data only ever comes through wwFetchWaveformRange().
        plotting = _between(_source(), "// ---- Slice 3C: the reconstruction renderer", "function wwErMemberRowHtml(member)")
        assert plotting.count("await fetch(") == 1
        assert "await fetch(url, { method: \"POST\"" in _between(_source(), "async function wwErRefreshCursorValues() {", "\n        }\n\n")

    def test_fetch_is_engineering_units_with_the_slice_3b_mapping_only(self):
        source = _source()
        request = _between(source, "function wwErFetchRequestFor(trace, timing, viewport, pointBudget) {", "\n        }\n")
        assert 'unitMode: "engineering",' in request
        assert "timeOffsetS: 0," in request
        assert "wwErReconstructionTimeToSourceElapsed(viewport.start, timing.totalOffsetS)" in request
        assert "wwErReconstructionTimeToSourceElapsed(viewport.end, timing.totalOffsetS)" in request
        assert "if (timing.endS < viewport.start || timing.startS > viewport.end) return null;" in request
        load = _between(source, "async function wwErLoadTrace(trace) {", "function wwErPlottedTraces()")
        assert "body.time.map((t) => wwErSourceElapsedToReconstructionTime(t, timing.totalOffsetS))" in load
        assert "if (result.superseded || trace.removed) return;" in load
        module = _er_module(source)
        for forbidden in ("per_unit", "unitMode: ww", "wwAlignmentOffset", "effective_alignment", "alignment_offset_s", "digital-waveform",
                          "wwRebuildDigitalChart", "start_time_utc +", "Date.parse(timing"):
            assert forbidden not in module
        assert module.count("unitMode:") == 1

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

    def test_selection_and_drag_mode_reach_the_renderer(self):
        source = _source()
        assert "wwErRenderPlot();" in _between(source, "function wwErToggleChannelRow(row) {", "function wwErToggleChannelGroup(button)")
        assert "wwErRenderPlot();" in _between(source, "function wwErToggleChannelGroup(button) {", "function wwErSyncChannelSelectionDom()")
        assert "wwErRenderPlot();" in _between(source, "function wwErRender() {", "function wwErHandleAction(button)")
        assert "wwErApplyDragMode();" in _between(source, "function wwErSetDragMode(mode) {", "// ---- API ----")
        drag = _between(source, "function wwErApplyDragMode() {", "\n        }\n")
        assert "for (const panel of wwErState.plot.panels)" in drag

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

    def test_y_step_zoom_stays_out(self):
        source = _source()
        page = _er_page(source)
        # Slice 3D zooms X only: the axis menus stay disabled and unwired.
        for control in ("wwErZoomInAxisBtn", "wwErZoomOutAxisBtn"):
            assert re.search(r'id="' + control + r'"[^>]*\bdisabled\b', page)
            assert 'getElementById("' + control + '").addEventListener' not in source
        module = _er_module(source)
        for forbidden in ("wwStepZoomY(", "yaxis.range\": [center"):
            assert forbidden not in module


class TestEventReconstructionTimelineNavigation:
    """Slice 3D (DEC-129): X-only Box Zoom/Pan, staged Zoom In/Out clamped to
    Fit All, Reset Time View = Fit All + autoscale Y (button and
    double-click), Autoscale Y on every panel, viewport rebasing, and the
    Fit All span notice -- all in reconstruction time."""

    def test_box_zoom_and_pan_are_x_only(self):
        source = _source()
        # Every Y axis of every panel (Grouped: one; Combined: one per
        # display axis) is fixedrange.
        layout = _between(source, "function wwErPanelLayout(panel) {", "function wwErInitPanelPlot(panel)")
        assert "panel.axes.forEach((axis, index) => {" in layout
        assert "fixedrange: true," in layout
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
        assert '<button type="button" class="secondary ww-tg-autoscale-btn" id="wwErAutoscaleYBtn"' in page
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
        assert "for (const panel of plot.panels) for (const axis of panel.axes) axis.autoscaleYPending = true;" in reset
        assert "wwErApplyViewport(plot.fitAll);" in reset
        assert "wwErRequestFitAll" not in source

    def test_autoscale_y_uses_plotly_autorange_then_keeps_the_range(self):
        source = _source()
        apply = _between(source, "async function wwErApplyPendingAutoscaleY(panel) {", "\n        }\n")
        assert 'autorange[axis.placement.layoutKey + ".autorange"] = true;' in apply
        assert "await Plotly.relayout(panel.chartEl, autorange);" in apply
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
        assert 'unit_mode: "engineering"' in values
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
        axis = _between(source, "function wwErChannelAxis(item) {", "\n        }\n")
        assert "channel.display_axis_key" in axis
        assert "channel.display_axis_quantity" in axis and "channel.display_axis_unit" in axis
        groups = _between(source, "function wwErPlotGroups(items) {", "\n        }\n")
        assert 'item.axis.key !== null ? "axis:" + item.axis.key : "solo:" + item.key' in groups
        # Never a rule over channel names or unit strings in the frontend.
        for body in (axis, groups):
            for forbidden in (".test(", ".match(", "toLowerCase", "toUpperCase", "indexOf(\"k", "channelName.", "name.includes"):
                assert forbidden not in body
        title = _between(source, "function wwErAxisTitle(axis) {", "\n        }\n")
        assert '(axis.quantity || WW_ER_UNKNOWN_QUANTITY_LABEL) + (axis.unit ? " (" + axis.unit + ")" : "")' in title
        # The title quantity is the backend's; never a classification
        # sentinel or broad type copied in by the frontend.
        assert "quantity: channel.display_axis_quantity || null," in axis
        assert 'quantity: "Undefined"' not in axis
        assert "display_axis_quantity || channel.engineering_type" not in axis
        # One title helper: no other place in the module builds a title
        # from an axis quantity.
        module = _er_module(source)
        assert module.count(".quantity") == title.count(".quantity")
        for use in ("{ text: wwErAxisTitle(axis.axis) }", ": wwErAxisTitle(panel.axes[0].axis);", "escapeHtml(wwErAxisTitle(axis.axis))"):
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
        assert "const pending = !previous || previous.autoscaleYPending || previous.traceKeys !== traceKeys;" in render

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
        assert "const specs = wwErViewPanels(wwErPlotGroups(items), plot.viewMode);" in render
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
        assert "title: panel.combined ? { text: wwErAxisTitle(axis.axis) } : (axis.axis.unit || \"\")," in layout
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
        assert "escapeHtml(wwErAxisTitle(axis.axis))" in legend
        for forbidden in ("dash", "dot"):
            assert forbidden not in _between(_source(), "function wwErBuildTrace(trace) {", "function wwErLegendChipHtml(trace)")

    def test_waveform_layout_helpers_are_untouched(self):
        source = _source()
        layout = source[source.index("function wwAnalogPanelLayout(") : source.index("\n        }\n", source.index("function wwAnalogPanelLayout("))]
        for forbidden in ("autoshift", "overlaying", "wwEr"):
            assert forbidden not in layout
