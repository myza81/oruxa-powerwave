"""Static structural regression checks for the Event Reconstruction
frontend: the Slice 0 shell (page, left panel, waveform workspace shell,
toolbar), the Slice 2 selection workflow wired to the Slice 1 API, and
the boundaries both must keep with the shared Waveform engine."""

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

    def test_left_panel_has_reconstruction_and_time_group_sections(self):
        page = _er_page(_source())
        assert '<aside id="wwErSidebar" aria-label="Event Reconstruction records">' in page
        assert 'id="wwErDefinitionHeading">Reconstruction <span id="wwErMemberCountBadge" class="count-badge">(0)</span></h2>' in page
        for element_id in ("wwErNotices", "wwErMembersPanel", "wwErClearBtn", "wwErStatus", "wwErGroupsPanel"):
            assert f'id="{element_id}"' in page
        assert 'id="wwErGroupsHeading">Time Groups <span id="wwErGroupsCountBadge" class="count-badge">(0)</span></h2>' in page
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
        assert "Plotting the reconstruction is not available yet." in page

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
        keys = re.findall(r"^\s*(\w+):", state.split("{", 1)[1], re.MULTILINE)
        # Workspace state and the last API responses only.
        assert keys == [
            "dragMode", "sources", "timeGroups", "definition", "previousCorrections",
            "channelsBySource", "calculatedChannels", "selectedChannels", "loadSeq", "busy",
        ]
        for forbidden in ("PresentationOverrides", "channelColors", "ColorOverride", "DisplayName =", "new Map(", "localStorage"):
            assert forbidden not in module
        # The only ER-owned persisted value is the left panel width.
        assert re.findall(r"const (?:WW_ER_|wwEr)\w+", module) == ["const WW_ER_SIDEBAR_WIDTH_STORAGE_KEY", "const wwErState"]

    def test_left_panel_never_reuses_waveform_channel_tree_or_sync_state(self):
        module = _er_module(_source())
        for forbidden in (
            "renderAnalogGroup", "renderDigitalGroup", "channel-row--toggle", "wwSourceSyncBadgeHtml",
            "/synchronization", "wwOpenSyncModal", "source-recording-sync-badge",
        ):
            assert forbidden not in module

    def test_no_plotting_yet(self):
        module = _er_module(_source())
        assert "Plotly" not in module
        assert "ww-chart" not in module

    def test_page_entry_and_refresh_read_only_existing_lists(self):
        source = _source()
        entered = _between(source, "async function wwErOnPageEntered() {", "\n        }\n")
        assert "await wwErRefresh();" in entered
        refresh = _between(source, "async function wwErRefresh() {", "async function wwErOnPageEntered()")
        assert 'fetchSourcesList(), wwErFetchJson("/time-groups"), wwErFetchJson("/definition"),' in refresh
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
    """Slice 2 (DEC-125): the left panel is driven by the Slice 1 API only."""

    def test_api_base_is_the_event_reconstruction_router(self):
        url = _between(_source(), "function wwErApiUrl(path) {", "\n        }\n")
        assert '"/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/event-reconstruction" + path' in url

    def test_every_write_is_one_of_the_slice_1_endpoints(self):
        module = _er_module(_source())
        writes = re.findall(r'wwErMutate\("(\w+)", "([^"]+)"', module)
        assert sorted(set(writes)) == sorted({
            ("PUT", "/definition"),
            ("PUT", "/definition/reference"),
            ("PUT", "/definition/members/"),
            ("DELETE", "/definition/members/"),
            ("DELETE", "/definition"),
        })
        assert module.count('"/correction"') == 2

    def test_time_groups_are_sorted_chronologically_with_ineligible_after(self):
        sort = _between(_source(), "function wwErSortedTimeGroups() {", "function wwErMembershipBlockedReason()")
        assert "Date.parse(a.start_time_utc) - Date.parse(b.start_time_utc)" in sort
        assert "filter((g) => g.eligible)" in sort and "filter((g) => !g.eligible)" in sort

    def test_ineligible_groups_show_the_backend_reason_and_no_add_action(self):
        row = _between(_source(), "function wwErGroupRowHtml(group) {", "function wwErRender()")
        assert "group.reason_message" in row
        assert 'data-reason-code="' in row
        assert '\'<span class="ww-er-badge">Not eligible</span>\'' in row
        add = row.index('wwErActionButton("add-group"')
        assert row.rfind("group.eligible", 0, add) != -1

    def test_membership_changes_never_drop_stale_members_implicitly(self):
        source = _source()
        blocked = _between(source, "function wwErMembershipBlockedReason() {", "function wwErReconfirmPlan()")
        assert "Choose a current member as reference first." in blocked
        assert "Re-confirm or remove the stale members first." in blocked
        for name, nxt in (("function wwErAddGroup(groupId) {", "function wwErRemoveMember(memberId)"),
                          ("function wwErRemoveMember(memberId) {", "async function wwErReconfirmStale()")):
            assert "wwErMembershipBlockedReason()" in _between(source, name, nxt)

    def test_stale_corrections_are_shown_but_never_sent(self):
        source = _source()
        reconfirm = _between(source, "async function wwErReconfirmStale() {", "function wwErRemoveStale()")
        # New members start at 0: the PUT carries group ids and a reference only.
        assert "wwErPutDefinition(plan.groupIds, plan.referenceGroupId)" in reconfirm
        assert "correction_s:" not in reconfirm
        member_row = _between(source, "function wwErMemberRowHtml(member) {", "function wwErGroupRowHtml(group)")
        assert "(kept, not applied)" in member_row
        assert "Previous correction (not applied)" in member_row

    def test_corrections_use_the_existing_millisecond_conversion_point(self):
        module = _er_module(_source())
        assert "correction_s: wwSyncMsToOffsetSeconds(ms)" in module
        assert "wwSyncOffsetToMsDisplay(correctionS)" in module

    def test_reference_is_only_changed_by_explicit_api_call(self):
        module = _er_module(_source())
        assert 'wwErMutate("PUT", "/definition/reference", { member_id: memberId })' in module
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
        assert "wwErNotifyWorkspaceChanged();" in _between(
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
        # No second grouping implementation anywhere in Event Reconstruction.
        module = _er_module(source)
        assert "ANALOG_GROUP_ORDER" not in module and "engineering_type ||" not in module

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
        assert 'wwErChannelRowAttrs(member.member_id, "calculated", c.id, c.name, c.reference_source_id)' in tree

    def test_presentation_is_read_only(self):
        module = _er_module(_source())
        for forbidden in (
            "wwSetChannelDisplayName", "wwResetChannelDisplayName", "wwSetChannelColorOverride",
            "wwResetChannelColorOverride", "wwOpenChannelContextMenu", "contextmenu", 'type="color"',
            "Rename", "Change colour", '"POST"', "wwCreateCalculatedChannel", "wwDeleteCalculatedChannel",
        ):
            assert forbidden not in module
        assert "wwChannelDisplayName(row.dataset.erSourceId, row.dataset.erChannelName)" in module

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

    def test_stale_members_get_no_channel_tree(self):
        row = _between(_source(), "function wwErMemberRowHtml(member) {", "function wwErGroupRowHtml(group)")
        current_branch, stale_branch = row.split("} else {", 1)
        assert "wwErMemberTreeHtml(member)" in current_branch
        assert "wwErMemberTreeHtml" not in stale_branch.split("return '<div", 1)[0]
        assert "Channel selection is unavailable until this member is re-confirmed." in stale_branch

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
        timing = _between(_source(), "function wwErSourceTiming(displaySourceId) {", "function wwErMemberRowHtml(member)")
        assert "const timingSourceId = calculated ? calculated.reference_source_id : displaySourceId;" in timing
        assert "for (const member of wwErCurrentMembers()) {" in timing
        assert "member.source_timings || []" in timing
        assert "totalOffsetS: timing.total_reconstruction_offset_s," in timing
        # No second timing model: no origin/placement arithmetic in the frontend.
        for forbidden in ("start_time_utc", "recorded_placement_s", "within_group_offset_s +", "correction_s"):
            assert forbidden not in timing

    def test_mapping_arithmetic_is_not_repeated_elsewhere_in_the_module(self):
        module = _er_module(_source())
        assert module.count("total_reconstruction_offset_s") == 1
