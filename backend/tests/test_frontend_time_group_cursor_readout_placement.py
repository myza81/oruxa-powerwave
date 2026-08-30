"""Static regression checks for the A/B cursor readout's relocation
history, culminating in this task's own owner-requested correction:

1. DEC-066: moved `.ww-tg-cursor-readout` from the top
   `.ww-tg-toolbar-row` into the bottom sticky stack.
2. DEC-067: fixed a "not actually sticky" bug in that bottom placement
   by consolidating the slider+readout into one `.ww-tg-sticky-bottom`
   wrapper.
3. THIS task (owner reconsideration): the numerical A-B/Δt readout
   moved BACK to the top toolbar row (its original home, inheriting
   `.ww-tg-sticky-top`'s own already-proven sticky behavior); the
   small "[A ×]"/"[B ×]" position badges (`.ww-cursor-label`, inside
   `.ww-tg-cursor-label-layer`) moved from being an independent
   top-sticky sibling into `.ww-tg-ruler`'s own DOM subtree instead, so
   they inherit the ruler's own sticky behavior directly rather than
   needing their own.

Owner's own governing rule, verbatim: "Numerical A/B/ΔT values belong
in the proven sticky top Time Group control area, while the small A/B
position badges belong to the sticky ruler/time-axis layer."

This is a pure DOM-placement/CSS migration for the readout (same
element/classes/`wwUpdateCursorOverlayForGroup()` read/write path, same
cursor state/math) and a DOM-ownership + X-projection-formula change
for the badges (same element/classes/drag/close interaction, only the
`left` coordinate now reads relative to the ruler's own
`getBoundingClientRect()` instead of the workspace section's).

Mirrors this suite's own established pure string/index-based approach
-- no jsdom execution. Real multi-group/sticky/scroll/drag behavior is
proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.

Case-letter references (A-J) below refer to this task's own section 20
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


def _sticky_top_region(body: str) -> str:
    sticky_top_start = body.index('\'<div class="ww-tg-sticky-top">\'')
    panels_idx = body.index('\'<div class="ww-tg-panels">')
    return body[sticky_top_start:panels_idx]


def _ruler_region(body: str) -> str:
    ruler_start = body.index('\'<div class="ww-tg-ruler" hidden>\'')
    return body[ruler_start:]


# ==============================================================================
# Case A: .ww-tg-cursor-readout is back inside the top sticky Time
# Group region.
# ==============================================================================


class TestReadoutIsBackInTheTopStickyRegion:
    def test_readout_markup_is_inside_the_sticky_top_wrapper(self):
        source = _source()
        body = _canvas_template_body(source)
        region = _sticky_top_region(body)
        assert 'class="ww-tg-cursor-readout"' in region

    def test_readout_is_a_flex_item_of_the_toolbar_row_not_the_bottom_stack(self):
        source = _source()
        body = _canvas_template_body(source)
        toolbar_row_start = body.index('\'<div class="ww-tg-toolbar-row">\'')
        readout_idx = body.index('\'<div class="ww-tg-cursor-readout" hidden>\'')
        sticky_bottom_idx = body.index('\'<div class="ww-tg-sticky-bottom">\'')
        assert toolbar_row_start < readout_idx < sticky_bottom_idx

    def test_readout_css_declares_no_independent_sticky_positioning(self):
        """It inherits `.ww-tg-sticky-top`'s own sticky behavior as a
        normal flex-item descendant -- it must not also declare its own
        `position: sticky` (that would be a second, redundant/competing
        sticky mechanism)."""
        source = _source()
        idx = source.index(".ww-tg-cursor-readout {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky" not in block
        assert "position: absolute" not in block


# ==============================================================================
# Case B: exactly one numerical readout per canvas.
# ==============================================================================


class TestExactlyOneReadoutPerCanvas:
    def test_only_one_cursor_readout_markup_block_in_the_canvas_template(self):
        source = _source()
        body = _canvas_template_body(source)
        assert body.count('class="ww-tg-cursor-readout"') == 1

    def test_canvas_template_is_the_only_function_that_creates_readout_markup(self):
        source = _source()
        assert source.count('<div class="ww-tg-cursor-readout" hidden>') == 1


# ==============================================================================
# Case C: numerical readout no longer exists in the bottom sticky
# stack.
# ==============================================================================


class TestReadoutNoLongerInBottomStack:
    def test_sticky_bottom_wrapper_contains_only_the_slider_slot(self):
        source = _source()
        body = _canvas_template_body(source)
        wrapper_start = body.index('\'<div class="ww-tg-sticky-bottom">\'')
        wrapper_end = body.index('\'<div class="ww-tg-ruler" hidden>\'', wrapper_start)
        wrapper_region = body[wrapper_start:wrapper_end]
        assert 'class="ww-tg-slider-slot"' in wrapper_region
        assert "ww-tg-cursor-readout" not in wrapper_region

    def test_offset_sync_no_longer_folds_a_readout_height_into_anything(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvasStickyOffset(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "readoutEl" not in fn_body
        assert 'stickyBottomEl.style.bottom = rulerWrapEl.getBoundingClientRect().height + "px";' in fn_body


# ==============================================================================
# Case D: A/B cursor badges remain associated with the ruler/time-axis
# -- now structurally NESTED inside `.ww-tg-ruler`.
# ==============================================================================


class TestBadgesAreOwnedByTheRuler:
    def test_label_layer_markup_is_nested_inside_the_ruler(self):
        source = _source()
        body = _canvas_template_body(source)
        region = _ruler_region(body)
        assert 'class="ww-tg-cursor-label-layer"' in region

    def test_label_layer_is_no_longer_a_canvas_level_sibling_of_the_cursor_overlay(self):
        source = _source()
        body = _canvas_template_body(source)
        overlay_idx = body.index('\'<div class="ww-tg-cursor-overlay" hidden></div>\'')
        sticky_bottom_idx = body.index('\'<div class="ww-tg-sticky-bottom">\'')
        # Nothing named ww-tg-cursor-label-layer between the cursor
        # overlay and the sticky-bottom wrapper any more.
        assert "ww-tg-cursor-label-layer" not in body[overlay_idx:sticky_bottom_idx]

    def test_label_layer_css_is_absolute_not_independently_sticky(self):
        """It inherits `.ww-tg-ruler`'s own sticky behavior as a
        descendant -- no second, competing sticky mechanism, and no
        leftover dependency on the (now-removed) --ww-tg-sticky-top-h
        custom property."""
        source = _source()
        idx = source.index(".ww-tg-cursor-label-layer {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: absolute;" in block
        assert "position: sticky" not in block
        assert "--ww-tg-sticky-top-h" not in block

    def test_no_dangling_sticky_top_h_custom_property_remains_anywhere(self):
        """The property itself is gone from both its former CSS consumer
        and its former JS publisher -- only a historical explanatory
        comment naming it (describing its own removal) is expected to
        remain."""
        source = _source()
        assert 'setProperty("--ww-tg-sticky-top-h"' not in source
        assert "var(--ww-tg-sticky-top-h" not in source


# ==============================================================================
# Case E: A/B badges use group-aware X projection -- specifically, the
# SAME ruler-relative conversion the ruler's own stroke marks use, not
# the old canvas/section-relative one.
# ==============================================================================


class TestBadgesUseRulerRelativeGroupAwareProjection:
    def test_live_position_update_uses_ruler_rect_for_the_label(self):
        source = _source()
        fn_idx = source.index("function livePositionUpdate(kind, time)")
        fn_body = source[fn_idx : source.index("\n            }\n", fn_idx)]
        assert 'labelEl.style.left = (pageX - rulerRect.left) + "px";' in fn_body
        assert 'labelEl.style.left = (pageX - sectionRect.left)' not in fn_body

    def test_update_cursor_overlay_uses_ruler_rect_for_both_ab_and_suggested_labels(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count('labelEl.style.left = (pageX - rulerRect.left) + "px";') == 2
        assert 'labelEl.style.left = (pageX - sectionRect.left)' not in fn_body

    def test_wwcursortimetopixelx_is_still_the_one_shared_authority(self):
        """The badges never duplicate a second time-to-pixel formula --
        `wwCursorTimeToPixelX(groupId, time)` remains the single
        authority every projection (line, ruler stroke, badge) reads
        from; only the ELEMENT's own coordinate-space conversion
        (`- rulerRect.left` vs `- sectionRect.left`) changed."""
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwCursorTimeToPixelX(groupId,") >= 2


# ==============================================================================
# Case F/G: two groups have independent top readouts and ruler badges;
# layout-mode rebuilds never duplicate either.
# ==============================================================================


class TestIndependenceAndNoDuplicationAcrossGroupsAndLayoutRebuilds:
    def test_readout_and_label_layer_are_both_resolved_via_this_canvas_only(self):
        """Both resolvers are scoped `canvasEl.querySelector(...)` --
        never a workspace-wide id -- so two Time Groups' own elements
        can never cross-contaminate."""
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-label-layer")' in fn_body
        assert 'getElementById("wwCursorReadout")' not in fn_body
        assert 'getElementById("wwCursorLabelLayer")' not in fn_body

    def test_rebuild_layout_never_creates_a_new_canvas_readout_or_label_layer(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwCreateTimeGroupCanvasDom" not in fn_body
        assert "ww-tg-cursor-readout" not in fn_body
        assert "ww-tg-cursor-label-layer" not in fn_body


# ==============================================================================
# Case H: canvas removal removes both the readout and the badges (plain
# DOM children, no separate global state to orphan).
# ==============================================================================


class TestCanvasRemovalTakesReadoutAndBadgesWithIt:
    def test_no_workspace_global_readout_or_label_layer_id_or_state_exists(self):
        source = _source()
        assert 'id="wwCursorReadout"' not in source
        assert 'id="wwCursorLabelLayer"' not in source
        assert "ww.cursorReadout" not in source
        assert "ww.cursorLabelLayer" not in source


# ==============================================================================
# Case I: cursor state/math functions are byte-for-byte unchanged --
# this was a DOM placement/ownership migration only.
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

    def test_drag_wiring_still_attaches_directly_to_overlay_and_label_layer(self):
        """Event listeners are attached to the elements THEMSELVES
        (`overlay`/`labelLayer` variables resolved once at wiring time)
        -- moving the label layer deeper into the ruler's own subtree
        does not require rewiring anything here."""
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupCursorOverlay(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'overlay.addEventListener("pointerdown", onPointerDown);' in fn_body
        assert 'labelLayer.addEventListener("pointerdown", onPointerDown);' in fn_body
        assert 'overlay.addEventListener("click", onClick);' in fn_body
        assert 'labelLayer.addEventListener("click", onClick);' in fn_body

    def test_readout_inner_item_label_value_css_is_byte_for_byte_unchanged(self):
        """The owner's own manually-set item padding, font-size, and
        A-blue/B-red color convention are untouched throughout every
        relocation."""
        source = _source()
        idx = source.index(".ww-tg-cursor-readout-item {")
        block = source[idx : source.index("}", idx) + 1]
        assert "padding: 6px 10px;" in block
        assert "align-items: baseline;" in block
        assert "gap: 5px;" in block
        readout_idx = source.index(".ww-tg-cursor-readout {")
        readout_block = source[readout_idx : source.index("}", readout_idx) + 1]
        assert "font-size: 0.65rem;" in readout_block
        label_idx = source.index(".ww-tg-cursor-readout-label {")
        assert "text-transform: uppercase; letter-spacing: 0.03em;" in source[label_idx : label_idx + 120]
        value_idx = source.index(".ww-tg-cursor-readout-value {")
        assert "color: var(--text); font-weight: 600;" in source[value_idx : value_idx + 120]
        assert ".ww-cursor-readout-a .ww-tg-cursor-readout-value { color: var(--accent); }" in source
        assert ".ww-cursor-readout-b .ww-tg-cursor-readout-value { color: var(--error); }" in source
        assert ".ww-cursor-label--a { background: var(--accent); }" in source
        assert ".ww-cursor-label--b { background: var(--error); }" in source


# ==============================================================================
# Case J: slider/ruler sticky behavior preserved.
# ==============================================================================


class TestSliderRulerStickyBehaviorPreserved:
    def test_sticky_bottom_wrapper_is_still_position_sticky(self):
        source = _source()
        idx = source.index(".ww-tg-sticky-bottom {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky;" in block
        assert "background: var(--panel);" in block

    def test_ruler_is_still_an_independent_sticky_sibling_bottom_zero(self):
        source = _source()
        idx = source.index(".ww-tg-ruler {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky;" in block
        assert "bottom: 0;" in block

    def test_ruler_stays_outside_the_sticky_bottom_wrapper_in_dom_order(self):
        source = _source()
        body = _canvas_template_body(source)
        wrapper_close_idx = body.index(
            "'</div>' +\n                '<div class=\"ww-tg-ruler\" hidden>'"
        )
        ruler_idx = body.index('\'<div class="ww-tg-ruler" hidden>\'')
        assert body[wrapper_close_idx:ruler_idx].count("'<div") == 0

    def test_offset_sync_still_called_from_the_rulers_own_state_function(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("wrapEl.hidden = !hasChannels;", fn_idx) + 200]
        assert "wwSyncTimeGroupCanvasStickyOffset(groupId);" in fn_body

    def test_no_new_scroll_listener_was_added_for_this_task(self):
        source = _source()
        assert source.count('addEventListener("scroll"') == 1  # the pre-existing cursor-overlay-refresh listener only
