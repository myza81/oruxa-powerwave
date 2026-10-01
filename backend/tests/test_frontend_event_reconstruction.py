"""Static structural regression checks for the Event Reconstruction
Slice 0 frontend shell (page, left recording panel, waveform workspace
shell and toolbar), and for the boundaries it must keep with the shared
Waveform engine."""

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
    module = _between(source, "// Event Reconstruction -- Slice 0 (frontend shell only)", "// Phase 3B: Recordings page (section 5/8/9)")
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

    def test_left_recording_panel_exists(self):
        page = _er_page(_source())
        assert '<aside id="wwErSidebar" aria-label="Event Reconstruction recordings">' in page
        assert 'id="wwErRecordingsHeading">Recordings <span id="wwErRecordingsCountBadge" class="count-badge">(0)</span></h2>' in page
        assert 'id="wwErRecordingsPanel"' in page
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
        assert "Record selection and plotting are not available yet." in page

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
        set_mode = _between(source, "function wwErSetDragMode(mode) {", "function wwErSourceRowHtml(source)")
        assert "wwErState.dragMode = mode;" in set_mode
        assert "Plotly" not in set_mode

    def test_no_event_reconstruction_channel_presentation_store(self):
        source = _source()
        module = _er_module(source)
        state = _between(source, "const wwErState = {", "};")
        assert state.split("{", 1)[1].strip() == 'dragMode: "zoom",'
        for forbidden in ("PresentationOverrides", "channelColors", "ColorOverride", "DisplayName =", "new Map(", "localStorage"):
            assert forbidden not in module
        # The only ER-owned persisted value is the left panel width.
        assert re.findall(r"const (?:WW_ER_|wwEr)\w+", module) == ["const WW_ER_SIDEBAR_WIDTH_STORAGE_KEY", "const wwErState"]

    def test_recording_rows_are_read_only_metadata(self):
        module = _er_module(_source())
        row = _between(_source(), "function wwErSourceRowHtml(source) {", "function wwErRenderRecordings(sources)")
        for helper in ("recordingDisplayName(source)", "wwFormatSourceSummaryLine(source)", "wwFormatSourceTimeIdentity(source)"):
            assert helper in row
        # No channel tree, channel toggles, sync badge or Time Group data.
        for forbidden in ("renderAnalogGroup", "renderDigitalGroup", "channel-row--toggle", "wwSourceSyncBadgeHtml", "timeGroup", "synchronization"):
            assert forbidden not in module

    def test_page_entry_only_reads_the_existing_sources_list(self):
        entered = _between(_source(), "async function wwErOnPageEntered() {", "\n        }\n")
        assert "await fetchSourcesList();" in entered
        assert "fetch(" not in entered.replace("fetchSourcesList(", "")

    def test_sidebar_drawer_targets_the_current_page_row(self):
        source = _source()
        helper = _between(source, "function shellSidebarDrawerRowEl() {", "\n        }\n")
        assert 'shell.currentPage === "event-reconstruction" ? "pageEventReconstruction" : "workspaceRow"' in helper
        assert 'document.getElementById("wwErSidebarBackdrop").addEventListener("click", () => shellSetSidebarDrawerOpen(false));' in source
