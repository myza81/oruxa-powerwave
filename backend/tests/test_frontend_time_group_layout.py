"""Static regression checks for TG-G's two priority correctness fixes:

**Priority issue A (DEC-061)** -- a non-primary Time Group's own analog
panel X-axis could show the PRIMARY Time Group's own Absolute-time
origin/range after a layout-mode round trip. Root cause: wwBuildLayout()
built its xaxis range/tick-format from the single global `ww.viewport`
directly instead of that panel's own group's range
(wwTimeGroupVisibleRange(groupId), the SAME per-group range source the
ruler already used). Fixed by routing wwBuildLayout() through that
existing helper.

**Priority issue B** -- the cursor A/B overlay's own hit-area spanned
the FULL Time Group canvas height (through the header+toolbar row), so
a cursor positioned near a toolbar button's own X coordinate could
pointer-intercept it. Fixed by starting the overlay's own top/height at
`.ww-tg-panels`'s own offsetTop instead of the canvas's own top (0).

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_t0.py, test_frontend_time_group_cursors.py) --
no jsdom execution, just confirming the right range source/geometry
exists in the right place. Real multi-group visual/interaction behavior
is proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.

Case-letter references (A-M) below refer to TG-G's own section 21/22
required-test list.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


# ==============================================================================
# Cases A-G: wwBuildLayout() builds its range from THIS panel's own
# group, never the single global ww.viewport directly.
# ==============================================================================


class TestBuildLayoutUsesItsOwnGroupsRange:
    def test_build_layout_resolves_groupid_then_range_through_the_shared_helper(self):
        source = _source()
        fn_idx = source.index("function wwBuildLayout(panel, colors)")
        fn_body = source[fn_idx : fn_idx + 1900]
        assert "const groupId = wwPanelTimeGroupId(panel);" in fn_body
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "wwElapsedToPlotlyX(groupId, range.start)" in fn_body
        assert "wwElapsedToPlotlyX(groupId, range.end)" in fn_body
        assert "wwTimeAxisTickFormat(range && range.start, range && range.end, groupId)" in fn_body

    def test_build_layout_no_longer_reads_ww_viewport_directly_for_its_range(self):
        """The DEC-061 root cause, byte-for-byte: this exact expression
        must no longer appear anywhere in wwBuildLayout()'s own body."""
        source = _source()
        fn_idx = source.index("function wwBuildLayout(panel, colors)")
        fn_body = source[fn_idx : fn_idx + 1400]
        assert "wwElapsedToPlotlyX(groupId, ww.viewport.start)" not in fn_body
        assert "ww.viewport ? [wwElapsedToPlotlyX" not in fn_body

    def test_time_group_visible_range_is_the_established_per_group_source_the_ruler_already_uses(self):
        """wwTimeGroupVisibleRange(groupId) is not new -- it already backs
        the ruler (wwSyncTimeGroupRuler()) and the slider. Confirms
        wwBuildLayout() now reuses that SAME resolver rather than
        introducing a second, potentially-diverging one, and confirms its
        own primary/non-primary split is unchanged (zero behavior change
        for the primary group's own panels -- Case A)."""
        source = _source()
        fn_idx = source.index("function wwTimeGroupVisibleRange(groupId)")
        fn_body = source[fn_idx : fn_idx + 300]
        assert 'if (groupId === wwPrimaryTimeGroupId()) return ww.viewport;' in fn_body
        assert "return ww.timeGroupViewports.get(groupId) || null;" in fn_body

    def test_layout_mode_rebuild_recreates_every_panel_through_the_fixed_helper(self):
        """Case B/C/D: Grouped/Separate/Custom round trips and repeated
        round trips all tear panels down and recreate them via
        wwCreatePanelDom()/wwInitPanelPlot() -> wwBuildLayout() -- since
        that function now always re-derives its own group's range fresh
        (never carrying forward a stale/primary range), every round trip
        is correct by construction, not by special-casing the rebuild
        path itself."""
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        # wwRebuildLayout() itself must not read/branch on ww.viewport or
        # wwPrimaryTimeGroupId() to decide a panel's own range -- that
        # decision now lives entirely inside wwBuildLayout()/
        # wwTimeGroupVisibleRange(), a single source of truth.
        assert "ww.viewport" not in fn_body
        assert "wwPrimaryTimeGroupId()" not in fn_body

    def test_zoom_pan_reset_already_relayout_through_an_explicit_per_group_range(self):
        """Case E: wwApplyAndFetchGroupViewport(groupId, ...) (the shared
        implementation behind Zoom/Pan/Reset Time View/Autoscale for
        every group) already calls Plotly.relayout with an EXPLICIT
        groupId and that call's own startTime/endTime -- never
        ww.viewport -- so a non-primary group's own zoom/pan/reset was
        never affected by the DEC-061 bug and needs no change here."""
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "Plotly.relayout(panel.chartEl, wwTimeAxisRelayout(startTime, endTime, groupId));" in fn_body

    def test_t0_set_clear_never_touches_the_range_source(self):
        """Case F: t0 set/clear (TG-E) only ever changes the coordinate
        TRANSFORM (wwElapsedToPlotlyX/wwWorkspaceTimeToEventTime), never
        wwBuildLayout()'s own range source -- confirmed structurally by
        the absence of any range/viewport mutation in these functions."""
        source = _source()
        for fn_sig, next_sig in [
            ("async function wwSetT0FromCursorAForGroup(groupId)", "async function wwClearT0ForGroup(groupId)"),
            ("async function wwClearT0ForGroup(groupId)", "function wwHandleSetOrClearT0ClickForGroup(groupId)"),
        ]:
            fn_idx = source.index(fn_sig)
            fn_body = source[fn_idx : source.index(next_sig, fn_idx)]
            assert "ww.viewport =" not in fn_body
            assert "timeGroupViewports.set" not in fn_body

    def test_manual_sync_offset_changes_never_touch_the_range_source_directly(self):
        """Case G: Synchronise Sources' own offset-change side effects
        (TG-F) refetch/rebuild through the existing per-group helpers
        (wwSyncTimeGroupRuler/wwRebuildDigitalChart/wwRefetchChannelsForGroup)
        -- confirmed already audited and unchanged by DEC-063's own
        record -- never assign wwBuildLayout()'s own range source
        directly."""
        source = _source()
        fn_idx = source.index("function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)")
        fn_body = source[fn_idx : fn_idx + 2000]
        assert "ww.viewport =" not in fn_body
        assert "timeGroupViewports.set(" not in fn_body


# ==============================================================================
# Cases H-M: cursor overlay hit-area no longer covers the toolbar.
# ==============================================================================


class TestCursorOverlayExcludesToolbarRegion:
    def test_overlay_top_and_height_are_derived_from_the_panels_element_offset(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : fn_idx + 8800]
        assert 'const panelsEl = canvasEl.querySelector(".ww-tg-panels");' in fn_body
        assert "const overlayTop = panelsEl ? panelsEl.offsetTop : 0;" in fn_body
        assert 'overlayEl.style.top = overlayTop + "px";' in fn_body
        assert 'overlayEl.style.height = Math.max(0, rulerWrapEl.offsetTop - overlayTop) + "px";' in fn_body
        # The DEC-061-adjacent old expression -- overlay starting at the
        # canvas's own top (0) rather than the panels region -- must be
        # gone.
        assert 'overlayEl.style.height = Math.max(0, rulerWrapEl.offsetTop) + "px";' not in fn_body

    def test_cursor_hit_and_line_still_span_the_full_overlay_box(self):
        """The drag hit-strip/visible line are unchanged -- they still
        fill their own overlay's top/bottom: 0 box; only the OVERLAY's
        own box got narrower (excludes the toolbar), so the fix is
        entirely geometric/scoping, not a rewrite of the drag/line CSS
        itself (Case L: dragging in the waveform region is unaffected)."""
        source = _source()
        overlay_css_idx = source.index(".ww-tg-cursor-overlay {")
        line_css_idx = source.index(".ww-cursor-line {", overlay_css_idx)
        hit_css_idx = source.index(".ww-cursor-hit {", line_css_idx)
        line_css = source[line_css_idx : line_css_idx + 200]
        hit_css = source[hit_css_idx : hit_css_idx + 200]
        assert "top: 0; bottom: 0;" in line_css
        assert "top: 0; bottom: 0;" in hit_css

    def test_cursor_x_positioning_is_independent_of_the_overlay_top_change(self):
        """Case D/E/H-J: horizontal cursor placement (the actual toolbar-
        click-interception risk is purely a VERTICAL hit-area concern) is
        computed from Plotly's own page-absolute plot geometry
        (wwCursorPlotMetrics), never the overlay's own top/height -- so
        narrowing the overlay vertically cannot desync cursor X
        positions."""
        source = _source()
        fn_idx = source.index("function wwCursorTimeToPixelX(groupId, time)")
        fn_body = source[fn_idx : fn_idx + 500]
        assert "metrics.plotLeftPage + frac * metrics.plotWidth" in fn_body
        assert "overlayEl" not in fn_body
        assert ".offsetTop" not in fn_body

    def test_label_layer_offset_from_the_sticky_toolbar_fix_is_unchanged(self):
        """Case M: the cursor A/B label pills lived in the SEPARATE
        `.ww-tg-cursor-label-layer` (not the overlay this TG-G fix
        touched), positioned below the sticky header/toolbar via
        `--ww-tg-sticky-top-h` -- confirming that TG-G fix did not need
        to (and did not) touch that mechanism.
        A later owner UX correction moved the label layer into
        `.ww-tg-ruler`'s own DOM subtree instead (see
        test_frontend_time_group_cursor_readout_placement.py's own
        badge-relocation coverage for the CURRENT contract) -- this test
        only confirms `--ww-tg-sticky-top-h` itself is gone now that its
        one consumer moved, which is what TG-G's own cursor-overlay fix
        left in place until that later, separate task changed it."""
        source = _source()
        assert 'setProperty("--ww-tg-sticky-top-h"' not in source
        assert "var(--ww-tg-sticky-top-h" not in source
        css_idx = source.index(".ww-tg-cursor-label-layer {")
        css_body = source[css_idx : css_idx + 200]
        assert "position: absolute;" in css_body

    def test_sticky_toolbar_wrapper_itself_is_unchanged_by_this_fix(self):
        """Case K: the sticky toolbar (recently committed) must still be
        exactly one wrapper per canvas with the same sticky/z-index/
        background contract -- this fix only touched the cursor overlay's
        own top/height, never `.ww-tg-sticky-top`."""
        source = _source()
        css_idx = source.index(".ww-tg-sticky-top {")
        css_body = source[css_idx : css_idx + 200]
        assert "position: sticky;" in css_body
        assert "top: 0;" in css_body
        assert "z-index: 5;" in css_body
        assert "background: var(--panel);" in css_body


# ==============================================================================
# Singleton DOM audit (TG-G section 11): the legacy workspace-global
# singleton ids must remain fully absent -- no real DOM/getElementById
# reference, only (if anything) historical comment mentions.
# ==============================================================================


class TestLegacySingletonIdsRemainAbsent:
    def test_no_legacy_time_group_singleton_ids_are_referenced_as_real_dom_ids(self):
        source = _source()
        legacy_ids = [
            "wwPanels",
            "wwDigitalRegion",
            "wwStickyRuler",
            "wwCursorOverlay",
            "wwCursorReadout",
            "wwSetT0Btn",
            "wwSyncBtn",
            "wwCursorModeBtn",
            "wwCursorLabelLayer",
        ]
        for legacy_id in legacy_ids:
            assert 'getElementById("' + legacy_id + '")' not in source
            assert 'id="' + legacy_id + '"' not in source
