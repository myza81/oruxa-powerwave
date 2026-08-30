"""Static regression checks for the A/B cursor readout's relocation
from the top `.ww-tg-toolbar-row` (top sticky area) into the bottom
sticky stack (between the Time Range slider and the ruler) of each
Time Group Canvas.

Owner UX request, verbatim governing rule: "The A/B cursor readout
remains Time-Group-local and functional exactly as before, but its
visual home moves from the top control area to the bottom sticky
time-axis region."

This is a pure DOM-placement/CSS migration -- the SAME
`.ww-tg-cursor-readout` element/classes, the SAME
`wwUpdateCursorOverlayForGroup(groupId)` read/write path, the SAME
cursor state/math (`ww.timeGroupCursorState`, `wwFormatCursorPointTime`,
`wwFormatCursorDuration`) -- only WHERE the element lives in the
template and how its own sticky `bottom` offset is computed changed.

Follow-up bugfix (owner UAT on commit eb55528): the initial relocation
used THREE independent `position: sticky` siblings (slider/readout/
ruler) with JS-computed `bottom` offsets; the readout was found to not
actually stay stuck while scrolling. `.ww-tg-slider-slot` and
`.ww-tg-cursor-readout` now share ONE `.ww-tg-sticky-bottom` wrapper
(normal-flow children, browser-computed height) -- see
`TestStickyBottomWrapperBugfix` below and this file's own inline
comments throughout for the full root-cause writeup.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_toolbar.py, test_frontend_time_range_slider.py)
-- no jsdom execution. Real multi-group/sticky/scroll behavior is
proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.

Case-letter references (A-H) below refer to this task's own section 21
required-test list.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _canvas_template_body(source: str) -> str:
    start = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
    end = source.index("function wwEnsureTimeGroupCanvasDom(groupId)", start)
    return source[start:end]


# ==============================================================================
# Case A: no .ww-tg-cursor-readout remains inside the top sticky
# header/toolbar region.
# ==============================================================================


class TestReadoutNoLongerInTopStickyRegion:
    def test_sticky_top_wrapper_markup_contains_no_cursor_readout(self):
        source = _source()
        body = _canvas_template_body(source)
        sticky_top_start = body.index('\'<div class="ww-tg-sticky-top">\'')
        # The sticky-top wrapper's own closing sequence is the run of
        # three consecutive '</div>' literals right before
        # '.ww-tg-panels' (closes .ww-tg-toolbar, .ww-tg-toolbar-row,
        # .ww-tg-sticky-top in turn) -- see wwCreateTimeGroupCanvasDom()'s
        # own template for the exact structure.
        panels_idx = body.index('\'<div class="ww-tg-panels">')
        sticky_top_region = body[sticky_top_start:panels_idx]
        assert "ww-tg-cursor-readout" not in sticky_top_region

    def test_toolbar_row_comment_documents_the_relocation(self):
        source = _source()
        idx = source.index(".ww-tg-toolbar-row {")
        comment_region = source[max(0, idx - 900) : idx]
        assert "moved to the bottom sticky stack" in comment_region


# ==============================================================================
# Case C: readout is structurally located in the bottom stack, between
# the slider and the ruler.
# ==============================================================================


class TestReadoutIsBetweenSliderAndRuler:
    def test_dom_order_is_slider_then_readout_then_ruler(self):
        source = _source()
        body = _canvas_template_body(source)
        slider_idx = body.index('\'<div class="ww-tg-slider-slot">')
        readout_idx = body.index('\'<div class="ww-tg-cursor-readout" hidden>\'')
        ruler_idx = body.index('\'<div class="ww-tg-ruler" hidden>\'')
        assert slider_idx < readout_idx < ruler_idx, (
            "expected DOM order slider -> cursor readout -> ruler in the "
            "bottom sticky stack"
        )

    def test_slider_and_readout_share_one_wrapper_ruler_stays_independent(self):
        """Bugfix (owner UAT on eb55528, readout not actually sticky):
        `.ww-tg-slider-slot` and `.ww-tg-cursor-readout` are both nested
        INSIDE `.ww-tg-sticky-bottom` (normal-flow children of ONE
        sticky wrapper) -- `.ww-tg-ruler` is NOT, staying a direct,
        independent sibling of the wrapper so its own `offsetTop` keeps
        resolving relative to the canvas root (Phase 4B-UAT2's own
        cursor-overlay-height fix depends on this)."""
        source = _source()
        body = _canvas_template_body(source)
        wrapper_open_idx = body.index('\'<div class="ww-tg-sticky-bottom">\'')
        slider_idx = body.index('\'<div class="ww-tg-slider-slot">', wrapper_open_idx)
        readout_idx = body.index('\'<div class="ww-tg-cursor-readout" hidden>\'', wrapper_open_idx)
        wrapper_close_idx = body.index("'</div>' +\n                '</div>' +\n                '<div class=\"ww-tg-ruler\" hidden>'")
        ruler_idx = body.index('\'<div class="ww-tg-ruler" hidden>\'')
        assert wrapper_open_idx < slider_idx < readout_idx < wrapper_close_idx <= ruler_idx

    def test_readout_css_sits_in_the_shared_bottom_wrapper_section_after_the_ruler(self):
        """Bugfix (owner UAT on eb55528): the readout and slider are now
        both normal-flow children of `.ww-tg-sticky-bottom`, declared in
        source after `.ww-tg-ruler` (which stays independent) -- order
        within that shared section is wrapper, then slider, then
        readout (matching DOM order top-to-bottom)."""
        source = _source()
        ruler_css_idx = source.index(".ww-tg-ruler {")
        wrapper_css_idx = source.index(".ww-tg-sticky-bottom {", ruler_css_idx)
        slider_css_idx = source.index(".ww-tg-slider-slot:not(:empty) {", wrapper_css_idx)
        readout_css_idx = source.index(".ww-tg-cursor-readout {", slider_css_idx)
        assert ruler_css_idx < wrapper_css_idx < slider_css_idx < readout_css_idx


# ==============================================================================
# Case B: exactly one cursor readout per rendered Time Group Canvas --
# structural guarantee: exactly one place in the template creates it.
# ==============================================================================


class TestExactlyOneReadoutPerCanvas:
    def test_only_one_cursor_readout_markup_block_in_the_canvas_template(self):
        source = _source()
        body = _canvas_template_body(source)
        assert body.count('class="ww-tg-cursor-readout"') == 1

    def test_canvas_template_is_the_only_function_that_creates_readout_markup(self):
        """wwCreateTimeGroupCanvasDom() is the ONE place that builds a
        canvas's own DOM (dataset.built-style guards elsewhere in this
        file exist for OTHER sub-regions, not this one) -- confirms no
        second code path could ever insert a second readout element."""
        source = _source()
        assert source.count('<div class="ww-tg-cursor-readout" hidden>') == 1


# ==============================================================================
# Case D/E: readout updates remain scoped to the correct group -- the
# resolver is still a per-canvas class query, never a global id.
# ==============================================================================


class TestReadoutUpdatesStayGroupScoped:
    def test_update_function_still_resolves_the_readout_via_this_canvas_only(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout-value--a")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout-value--b")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout-value--delta")' in fn_body
        # Never a workspace-wide getElementById lookup for the readout.
        assert 'getElementById("wwCursorReadout")' not in fn_body


# ==============================================================================
# Case F: layout-mode rebuilds never duplicate the readout -- the
# canvas root itself (and therefore its one readout child) is not
# recreated by a layout-mode switch, only panels are.
# ==============================================================================


class TestLayoutRebuildNeverDuplicatesReadout:
    def test_rebuild_layout_never_creates_a_new_canvas_or_readout(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwCreateTimeGroupCanvasDom" not in fn_body
        assert "ww-tg-cursor-readout" not in fn_body


# ==============================================================================
# Case G: canvas removal removes the readout naturally (it is a plain
# DOM child, no separate global readout/state to orphan).
# ==============================================================================


class TestCanvasRemovalTakesReadoutWithIt:
    def test_no_workspace_global_readout_id_or_state_exists(self):
        source = _source()
        assert 'id="wwCursorReadout"' not in source
        assert "ww.cursorReadout" not in source


# ==============================================================================
# Case H: cursor math/state functions are byte-for-byte unchanged --
# this was a DOM placement/CSS migration only.
# ==============================================================================


class TestCursorMathAndStateUntouched:
    def test_readout_value_computation_lines_are_unchanged(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : fn_idx + 4000]
        assert "const aShown = cursors.a.visible && Number.isFinite(cursors.a.time);" in fn_body
        assert "const bShown = cursors.b.visible && Number.isFinite(cursors.b.time);" in fn_body
        assert 'aEl.textContent = aShown ? wwFormatCursorPointTime(cursors.a.time, groupId) : "—";' in fn_body
        assert 'bEl.textContent = bShown ? wwFormatCursorPointTime(cursors.b.time, groupId) : "—";' in fn_body
        assert 'dEl.textContent = aShown && bShown ? wwFormatCursorDuration(cursors.b.time - cursors.a.time) : "—";' in fn_body
        assert "readoutEl.hidden = !active;" in fn_body

    def test_cursor_state_map_and_resolvers_are_unchanged(self):
        source = _source()
        assert "ww.timeGroupCursorState" in source
        assert "function wwTimeGroupCursorState(groupId)" in source
        assert "function wwEnsureTimeGroupCursorStateEntry(groupId)" in source

    def test_readout_inner_item_label_value_css_is_byte_for_byte_unchanged(self):
        """Only the OUTER `.ww-tg-cursor-readout` container's own layout
        properties (position/bottom/background/border/justify-content)
        changed -- the inner item/label/value rules, including the
        owner's own manually-set item padding, are untouched."""
        source = _source()
        idx = source.index(".ww-tg-cursor-readout-item {")
        block = source[idx : source.index("}", idx) + 1]
        assert "padding: 6px 10px;" in block
        assert "align-items: baseline;" in block
        assert "gap: 5px;" in block
        label_idx = source.index(".ww-tg-cursor-readout-label {")
        assert "text-transform: uppercase; letter-spacing: 0.03em;" in source[label_idx : label_idx + 120]
        value_idx = source.index(".ww-tg-cursor-readout-value {")
        assert "color: var(--text); font-weight: 600;" in source[value_idx : value_idx + 120]
        assert ".ww-cursor-readout-a .ww-tg-cursor-readout-value { color: var(--accent); }" in source
        assert ".ww-cursor-readout-b .ww-tg-cursor-readout-value { color: var(--error); }" in source


# ==============================================================================
# Bugfix (owner UAT on eb55528, "readout is NOT actually sticky while
# scrolling"): the shared `.ww-tg-sticky-bottom` wrapper. Case-letter
# references (A-I) below refer to THIS follow-up task's own section 12
# required-test list -- runtime-only behaviors (B/E/F/G/H) are proven
# live via Playwright (see this task's own live-UAT report); the
# assertions here lock in the structural contract that behavior
# depends on.
# ==============================================================================


class TestStickyBottomWrapperBugfix:
    def test_case_a_wrapper_is_position_sticky(self):
        source = _source()
        idx = source.index(".ww-tg-sticky-bottom {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky;" in block

    def test_case_c_ruler_is_the_wrappers_own_next_sibling_in_dom_order(self):
        source = _source()
        body = _canvas_template_body(source)
        wrapper_close_idx = body.index(
            "'</div>' +\n                '</div>' +\n                '<div class=\"ww-tg-ruler\" hidden>'"
        )
        ruler_idx = body.index('\'<div class="ww-tg-ruler" hidden>\'')
        # The wrapper's own closing sequence is immediately followed by
        # the ruler's own opening tag -- no other sibling in between.
        assert body[wrapper_close_idx:ruler_idx].count("'<div") == 0

    def test_case_d_slider_is_the_wrappers_own_first_child(self):
        source = _source()
        body = _canvas_template_body(source)
        wrapper_open_idx = body.index('\'<div class="ww-tg-sticky-bottom">\'')
        slider_idx = body.index('\'<div class="ww-tg-slider-slot">', wrapper_open_idx)
        # Nothing else opens between the wrapper and the slider slot.
        assert body[wrapper_open_idx + len('\'<div class="ww-tg-sticky-bottom">\''):slider_idx].strip() in ("", "+")

    def test_case_e_hidden_readout_still_collapses_via_display_none(self):
        source = _source()
        assert ".ww-tg-cursor-readout[hidden] { display: none; }" in source

    def test_case_h_readout_still_wraps_at_narrow_widths(self):
        source = _source()
        idx = source.index(".ww-tg-cursor-readout {")
        block = source[idx : source.index("}", idx) + 1]
        assert "flex-wrap: wrap;" in block

    def test_case_i_top_sticky_toolbar_css_is_untouched_by_this_bugfix(self):
        source = _source()
        idx = source.index(".ww-tg-sticky-top {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky;" in block
        assert "top: 0;" in block
        assert "z-index: 5;" in block
        assert "background: var(--panel);" in block

    def test_offset_sync_still_called_from_the_rulers_own_state_function(self):
        """Same established call site as before this bugfix -- only the
        function BODY's own internals changed, not who calls it or
        when."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("wrapEl.hidden = !hasChannels;", fn_idx) + 200]
        assert "wwSyncTimeGroupCanvasStickyOffset(groupId);" in fn_body

    def test_no_new_scroll_listener_was_added_for_this_bugfix(self):
        source = _source()
        assert source.count('addEventListener("scroll"') == 1  # the pre-existing cursor-overlay-refresh listener only
