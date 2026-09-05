"""Structural checks for the Waveform page view-mode controls cleanup:
the top-right Waveform/Table/Split selector (`#shellViewToggle` and its
three buttons) is redundant now that Table View (DEC-079) has its own
real Main Sidebar Menu entry, and is removed entirely; Split View
itself is retained, moved to a new standalone toolbar button
(`#wwSplitViewBtn`) beside Custom Layout on the Waveform toolbar.

These are static source-text checks, the same convention every other
test_frontend_*.py file in this suite uses -- no JS execution engine is
part of this repository's test harness.
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


class TestOldSelectorRemoved:
    def test_shell_view_toggle_group_and_its_three_buttons_are_gone(self):
        source = _source()
        assert 'id="shellViewToggle"' not in source
        assert 'id="shellViewWaveformBtn"' not in source
        assert 'id="shellViewTableBtn"' not in source
        assert 'id="shellViewSplitBtn"' not in source


class TestMainSidebarMenuUnaffected:
    """The Main Sidebar Menu's own Waveform/Table entries never depended
    on the removed selector -- they already call shellSetActiveView()
    directly."""

    def test_main_nav_waveform_btn_still_present_and_wired(self):
        source = _source()
        assert 'id="mainNavWaveformBtn"' in source
        body = _function_body(
            source,
            'document.getElementById("mainNavWaveformBtn").addEventListener("click"',
            "document.getElementById(\"mainNavRecordingsBtn\")",
        )
        assert 'shellSetActiveView("waveform")' in body

    def test_main_nav_table_btn_still_present_and_wired(self):
        source = _source()
        assert 'id="mainNavTableBtn"' in source
        body = _function_body(
            source,
            'document.getElementById("mainNavTableBtn").addEventListener("click"',
            'document.getElementById("mainNavSettingsBtn")',
        )
        assert 'shellSetActiveView("table")' in body


class TestNewSplitViewToolbarButton:
    def test_button_exists_beside_custom_layout_with_correct_tooltip(self):
        source = _source()
        custom_idx = source.index('id="layoutModeCustomBtn"')
        layout_group_close = source.index("</div>", custom_idx)
        split_idx = source.index('id="wwSplitViewBtn"')
        next_control_idx = source.index('id="editChannelGroupsBtn"')
        # The new button must appear shortly after Custom Layout's own
        # group closes, before the NEXT toolbar control -- "immediately
        # beside" it, never buried far away or accidentally placed inside
        # the mutually-exclusive Grouped/Separate/Custom radio group
        # itself.
        assert layout_group_close < split_idx < next_control_idx

        body = _function_body(source, '<button class="ww-icon-btn" type="button" id="wwSplitViewBtn"', "</button>")
        assert "Split View — Show waveform and table side by side" in body
        assert 'class="ww-icon-btn"' in body
        # Never the old page-tab style.
        assert 'class="theme-toggle"' not in body

    def test_button_is_standalone_not_inside_layout_mode_radio_group(self):
        source = _source()
        group_start = source.index('id="layoutModeToggle"')
        group_end = source.index("</div>", group_start)
        split_idx = source.index('id="wwSplitViewBtn"')
        assert not (group_start < split_idx < group_end)

    def test_click_toggles_between_split_and_waveform(self):
        source = _source()
        body = _function_body(
            source,
            'document.getElementById("wwSplitViewBtn").addEventListener("click"',
            "document.getElementById(\"shellSidebarToggleBtn\")",
        )
        assert 'shellSetActiveView(shell.activeView === "split" ? "waveform" : "split")' in body


class TestSharedActiveViewMechanismUnchanged:
    """shellSetActiveView() must remain the ONE place shell.activeView
    and #viewWaveform/#viewTable/#viewSplit visibility are set -- only
    its own reference to the removed buttons changes."""

    def test_still_the_one_place_toggling_the_three_view_sections(self):
        source = _source()
        body = _function_body(
            source, "function shellSetActiveView(view)", "function setShellNavCurrent"
        )
        assert 'document.getElementById("viewWaveform").hidden = view !== "waveform"' in body
        assert 'document.getElementById("viewTable").hidden = view !== "table"' in body
        assert 'document.getElementById("viewSplit").hidden = view !== "split"' in body
        assert 'wwSplitViewBtn").setAttribute("aria-pressed"' in body
        assert "shellViewWaveformBtn" not in body
        assert "shellViewTableBtn" not in body
        assert "shellViewSplitBtn" not in body

    def test_shell_set_current_page_no_longer_references_removed_toggle(self):
        source = _source()
        body = _function_body(
            source, "function shellSetCurrentPage(page)", "function wwSyncT0Controls"
            if "function wwSyncT0Controls" in source else "function shellSetCurrentPage"
        )
        assert "shellViewToggle" not in body


class TestSplitViewCapabilityRetained:
    def test_view_split_section_still_exists(self):
        source = _source()
        assert 'id="viewSplit"' in source

    def test_split_placeholder_content_unchanged(self):
        source = _source()
        body = _function_body(source, 'id="viewSplit"', "</section>")
        assert "Not implemented yet" in body
