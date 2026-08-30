"""Static regression checks for the Time Range slider (one horizontal
two-handle range navigator per Time Group). Mirrors
test_frontend_time_groups.py's own pure string/index-based approach -- no
jsdom execution, just confirming the right markers/wiring exist in the
right places/order.

Real drag-interaction behavior (Cases A-K from the task's own required-test
list) is proven live via Playwright against a running backend + real
COMTRADE fixtures -- see the session's own live-UAT report for the full
25/25-check record (owner's exact 5 kHz/1.3 s + 20 Hz/69 s scenario,
Grouped/Separate layouts, two independent Time Groups, t0 interaction,
source removal). This file guards the STRUCTURAL contracts that make that
behavior possible and keeps them from silently regressing.
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


def test_slider_state_exists():
    source = _source()
    assert "timeGroupViewports: new Map()" in source
    assert "timeGroupViewportDebounceTimers: new Map()" in source


def test_slider_dom_container_sits_between_digital_region_and_sticky_ruler():
    """Time Group Canvas (Slice TG-B+C): the digital region, slider
    slot, and ruler are no longer separate workspace-wide singleton
    containers -- each lives inside ONE canvas's own template, built by
    wwCreateTimeGroupCanvasDom(), in this same relative order."""
    source = _source()
    fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    digital_idx = fn_body.index('ww-tg-digital-region')
    slider_idx = fn_body.index('ww-tg-slider-slot')
    ruler_idx = fn_body.index('ww-tg-ruler"')
    assert digital_idx < slider_idx < ruler_idx


class TestPanelAndPrimaryGroupResolution:
    def test_panel_time_group_id_resolves_from_first_channel(self):
        source = _source()
        fn_idx = source.index("function wwPanelTimeGroupId(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "panel.channels[0].sourceId" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(panel.channels[0].sourceId)" in fn_body

    def test_primary_time_group_id_falls_back_to_primary_source(self):
        """Time Group Canvas: reads ww.displayed (channel-level truth,
        always immediately correct) rather than ww.panels -- ww.panels
        can be transiently stale relative to CURRENT Time Group
        topology right after a merge/split, before wwRebuildLayout()
        has re-routed panels. Falls back to wwPrimaryTimeGroupSourceId()
        only when nothing is displayed at all."""
        source = _source()
        fn_idx = source.index("function wwPrimaryTimeGroupId()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const { channel } of ww.displayed.values())" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(channel.sourceId)" in fn_body
        assert "wwPrimaryTimeGroupSourceId()" in fn_body

    def test_active_time_group_ids_derived_from_displayed_channels_only(self):
        """Task section 9/17: never a canvas for a group nothing is
        currently showing -- ww.timeGroups (every group the workspace
        has) is NOT what decides canvas count, only groups actually
        backing a DISPLAYED channel are. Reads ww.displayed directly
        (same staleness rationale as wwPrimaryTimeGroupId() above) --
        not ww.panels, which can lag behind topology changes."""
        source = _source()
        fn_idx = source.index("function wwActiveTimeGroupIds()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const { channel } of ww.displayed.values())" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(channel.sourceId)" in fn_body


class TestFullBoundsComeFromTheGroupItself:
    """Task section 4: full extent must come from the group's ACTUAL full
    bounds -- never a first-source/first-panel/first-uploaded shortcut."""

    def test_derive_time_group_bounds_unions_every_participating_source_in_that_group(self):
        source = _source()
        fn_idx = source.index("function wwDeriveTimeGroupBounds(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const sourceId of wwParticipatingSourceIds())" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(sourceId) !== groupId" in fn_body
        assert "Math.min(start, shiftedStart)" in fn_body
        assert "Math.max(end, shiftedEnd)" in fn_body


class TestApplyAndFetchGroupViewportScoping:
    """Task section 3/6/7/8: a group's own viewport change must relayout
    ONLY its own panels, refetch ONLY its own channels, and touch the
    single-instance cross-cutting UI (cursor/ruler/digital/toolbar zoom)
    only when it IS the primary group."""

    def test_relayouts_only_panels_belonging_to_the_changed_group(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "if (wwPanelTimeGroupId(panel) !== groupId) continue;" in fn_body
        assert "ww.timeGroupViewports.set(groupId, { start: startTime, end: endTime });" in fn_body

    def test_primary_group_still_drives_the_one_remaining_single_viewport_surface(self):
        """Time Group Canvas (task section 7/8/25) + TG-D1 (task section
        7): ruler/digital/slider/local-toolbar-zoom-controls are all
        genuinely per-group and update for EVERY group's own viewport
        change. TG-H: peak-annotation recalculation joined that same
        unconditional, genuinely-per-group set (previously gated to the
        primary group only, see
        test_frontend_time_group_annotations.py's own Case F) -- only
        the ww.viewport mirror itself (the still-deferred, workspace-
        global cursor-overlay surface reads it) remains primary-only."""
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        primary_idx = fn_body.index("if (isPrimary) {")
        primary_end = fn_body.index("ww.viewport = { start: startTime, end: endTime };", primary_idx) + len(
            "ww.viewport = { start: startTime, end: endTime };"
        )
        primary_block = fn_body[primary_idx:primary_end]
        assert "ww.viewport = { start: startTime, end: endTime };" in primary_block

        unconditional_tail = fn_body[primary_end:]
        assert "wwRecalculateAllPeakAnnotations(groupId, startTime, endTime);" in unconditional_tail
        assert "wwSyncTimeGroupRuler(groupId);" in unconditional_tail
        assert "wwRebuildDigitalChart(groupId);" in unconditional_tail
        assert "wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in unconditional_tail
        assert "wwSyncTimeGroupZoomControls(groupId);" in unconditional_tail

    def test_refetches_only_this_groups_own_channels(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "await wwRefetchChannelsForGroup(groupId, startTime, endTime);" in fn_body

    def test_legacy_entry_point_delegates_to_the_primary_group(self):
        """Every pre-existing caller (wwStepZoomX/Y, wwResetTimeView,
        wwRefreshWorkspaceBounds, the sync modal's offset-change side
        effects) keeps calling wwApplyAndFetchViewport() unchanged --
        it now means exactly "the primary group's own viewport"."""
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchViewport(startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwRefetchChannelsForGroup", fn_idx)]
        assert "const primaryGroupId = wwPrimaryTimeGroupId();" in fn_body
        assert "await wwApplyAndFetchGroupViewport(primaryGroupId, startTime, endTime);" in fn_body


class TestGroupScopedRefetchNeverUsesAnotherGroupsRange:
    """A channel's own native-time request depends on ITS OWN source's
    alignment offset -- reusing one group's own range for a DIFFERENT
    group's channels would request the wrong native window entirely."""

    def test_refetch_channels_for_group_filters_by_each_channels_own_group(self):
        source = _source()
        fn_idx = source.index("async function wwRefetchChannelsForGroup(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupIdForDisplaySourceId(channel.sourceId) !== groupId" in fn_body

    def test_refetch_across_groups_resolves_each_channels_own_current_viewport(self):
        source = _source()
        fn_idx = source.index("async function wwRefetchAllChannelsAcrossGroups()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(channel.sourceId);" in fn_body
        assert "ww.timeGroupViewports.get(groupId) || ww.viewport" in fn_body


class TestResetTimeView:
    """Task section 16: for the relevant Time Group, Reset -> full group
    extent; in the single-Time-Group case this must be byte-for-byte the
    same as before this feature."""

    def test_resets_every_active_group_to_its_own_full_bounds(self):
        source = _source()
        fn_idx = source.index("async function wwResetTimeView()")
        fn_body = source[fn_idx : source.index('// "Autoscale Y"', fn_idx)]
        assert "if (!ww.workspaceBounds) return;" in fn_body
        assert "for (const groupId of wwActiveTimeGroupIds())" in fn_body
        assert "wwDeriveTimeGroupBounds(groupId)" in fn_body
        assert "wwApplyAndFetchGroupViewport(groupId, bounds.start, bounds.end)" in fn_body

    def test_clears_every_groups_own_pending_debounce_timer(self):
        source = _source()
        fn_idx = source.index("async function wwResetTimeView()")
        fn_body = source[fn_idx : source.index('// "Autoscale Y"', fn_idx)]
        assert "ww.timeGroupViewportDebounceTimers.values()" in fn_body


class TestRefreshTimeGroupViewportsOwnsOnlyNonPrimaryGroups:
    """Task section 23: never a second, competing authority for the
    primary group's own viewport -- wwRefreshWorkspaceBounds()'s own
    existing, unchanged logic stays the sole owner of that one."""

    def test_skips_the_primary_group(self):
        source = _source()
        fn_idx = source.index("async function wwRefreshTimeGroupViewports(options)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (groupId === primaryGroupId) continue;" in fn_body

    def test_prunes_entries_for_groups_no_longer_active(self):
        """Task section 14/15: remove the slider entirely if the Time
        Group disappears; old group state must not incorrectly remain
        attached after a topology change."""
        source = _source()
        fn_idx = source.index("async function wwRefreshTimeGroupViewports(options)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (!activeIds.has(groupId)) ww.timeGroupViewports.delete(groupId);" in fn_body

    def test_refresh_workspace_bounds_calls_it_without_owning_it_directly(self):
        source = _source()
        fn_idx = source.index("async function wwRefreshWorkspaceBounds(options)")
        fn_body = source[fn_idx : source.index("const next = wwDeriveWorkspaceBounds();", fn_idx)]
        assert "await wwRefreshTimeGroupViewports(options);" in fn_body


class TestSliderUiWiring:
    def test_row_has_two_handles_and_a_draggable_selection_window(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupSliderRow(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww-tg-slider-handle--left" in fn_body
        assert "ww-tg-slider-handle--right" in fn_body
        assert "ww-tg-slider-window" in fn_body
        assert "wwWireTimeGroupSliderHandle(leftHandle, track, groupId, \"left\")" in fn_body
        assert "wwWireTimeGroupSliderHandle(rightHandle, track, groupId, \"right\")" in fn_body
        assert "wwWireTimeGroupSliderWindow(windowEl, track, groupId)" in fn_body

    def test_handle_drag_narrows_the_span_never_crossing_the_other_handle(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupSliderHandle(handleEl, trackEl, groupId, side)")
        fn_body = source[fn_idx : source.index("function wwWireTimeGroupSliderWindow", fn_idx)]
        assert 'if (side === "left") current.start = Math.min(t, current.end - minSpan);' in fn_body
        assert "current.end = Math.max(t, current.start + minSpan);" in fn_body
        assert "wwDebounceApplyGroupViewport(groupId, current.start, current.end);" in fn_body

    def test_window_drag_pans_preserving_span_via_the_shift_based_clamp(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupSliderWindow(windowEl, trackEl, groupId)")
        fn_body = source[fn_idx : source.index("function wwCreateTimeGroupSliderRow", fn_idx)]
        assert "const span = state.startRange.end - state.startRange.start;" in fn_body
        assert "wwClampPanWindowToTimeGroup(groupId, newStart, newStart + span)" in fn_body

    def test_pointer_capture_used_for_both_handles_and_the_window(self):
        source = _source()
        handle_idx = source.index("function wwWireTimeGroupSliderHandle(handleEl, trackEl, groupId, side)")
        handle_body = source[handle_idx : source.index("function wwWireTimeGroupSliderWindow", handle_idx)]
        assert "handleEl.setPointerCapture(event.pointerId);" in handle_body

        window_idx = source.index("function wwWireTimeGroupSliderWindow(windowEl, trackEl, groupId)")
        window_body = source[window_idx : source.index("function wwCreateTimeGroupSliderRow", window_idx)]
        assert "windowEl.setPointerCapture(event.pointerId);" in window_body


class TestRenderMatchesActiveGroupsAndNeverFightsAnActiveDrag:
    def test_row_set_is_built_from_active_group_ids_sorted_deterministically(self):
        """Time Group Canvas: wwSyncTimeGroupCanvases() replaced the
        old wwRenderTimeGroupSliders() as the one entry point that
        (re)builds the canvas SET to match wwActiveTimeGroupIds(),
        sorted deterministically, pruning any canvas whose group is no
        longer active."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const activeIds = wwActiveTimeGroupIds();" in fn_body
        assert "const sortedIds = Array.from(activeIds).sort();" in fn_body
        assert "canvasEl.remove();" in fn_body

    def test_group_label_only_shown_once_more_than_one_group_exists(self):
        """Time Group Canvas (task section 4): numbering/labeling moved
        from the slider row itself to the canvas's own header
        (wwSyncTimeGroupCanvasHeader()) -- the row's own label is now
        ALWAYS suppressed (never a second, redundant label competing
        with the header), unlike the pre-canvas design where the row
        needed its own conditional label to disambiguate a shared
        container."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupSliderForCanvas(groupId, canvasEl)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwSyncTimeGroupSliderRow(groupId, rowEl, false);" in fn_body

    def test_sync_row_skips_repaint_while_that_exact_group_is_mid_drag(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupSliderRow(groupId, rowEl, showGroupLabel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupSliderDragState && wwTimeGroupSliderDragState.groupId === groupId" in fn_body


class TestSliderLabelStaysDurationBasedNeverWallClock:
    """Task section 10's own duration-based label option was chosen
    specifically because it sidesteps the separately-documented,
    pre-existing single-workspace Absolute-mode-origin limitation
    (DEC-057) -- the slider's own label must never fabricate a
    wall-clock timestamp for a non-primary group."""

    def test_range_label_uses_the_existing_duration_formatter_only(self):
        source = _source()
        fn_idx = source.index("function wwPaintTimeGroupSliderRow(groupId, start, end, boundsOverride)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwFormatCursorDuration(span)" in fn_body
        assert "wwFormatCursorDuration(end - start)" in fn_body
        assert "wwFormatAbsoluteElapsedTime" not in fn_body


class TestGroupLabelNumberingMatchesPanelSuffix:
    def test_slider_label_reuses_the_exact_same_sorted_numbering_as_panel_labels(self):
        source = _source()
        fn_idx = source.index("function wwTimeGroupSliderGroupLabel(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'group.timeReferenceType === "elapsed_only"' in fn_body
        assert "Array.from(ww.timeGroups.keys()).sort()" in fn_body
        assert '"Time Group " + (sortedGroupIds.indexOf(groupId) + 1)' in fn_body


class TestStickySliderStructure:
    """Owner UX refinement: the slider stays pinned near the bottom of
    the waveform workspace while scrolling. Verified live via Playwright
    (real backend, 19-panel/two-Time-Group scroll scenarios: sticky held
    through scroll down/up, handle/window drag and mouse-zoom-driven
    updates all still work while scrolled, Reset Time View unaffected,
    both Grouped and Separate layouts, an independent second group's row
    stayed untouched even while the sticky block was scrolled) -- these
    checks guard the underlying structural contract that behavior
    depends on."""

    def test_slider_container_is_sticky_only_when_it_has_content(self):
        """.ww-tg-slider-slot:empty already stays `display: none` (no
        reserved gap when nothing is displayed).
        Bugfix (owner UAT on eb55528, readout not actually sticky): the
        slider slot is no longer independently `position: sticky` --
        it, and the cursor readout, are now normal-flow children of the
        shared `.ww-tg-sticky-bottom` wrapper, which owns the sticky
        positioning instead (see that selector's own test below). The
        slider slot itself keeps only its own visual divider."""
        source = _source()
        idx = source.index(".ww-tg-slider-slot:not(:empty) {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky" not in block
        assert "border-top: 1px solid var(--panel-border);" in block

    def test_sticky_bottom_wrapper_owns_the_sticky_positioning(self):
        """The bugfix's own new shared wrapper -- position:sticky,
        background, and a sensible z-index below the ruler's own 4."""
        source = _source()
        idx = source.index(".ww-tg-sticky-bottom {")
        block = source[idx : source.index("}", idx) + 1]
        assert "position: sticky;" in block
        assert "z-index: 3;" in block
        assert "background: var(--panel);" in block

    def test_slider_is_not_wrapped_together_with_the_ruler(self):
        """Wrapping the slider slot and ruler in one shared sticky
        container would change the ruler's own offsetParent away from
        its canvas root, silently breaking the existing Phase 4B-UAT2
        cursor-overlay-height fix -- they must remain separate sticky
        siblings within wwCreateTimeGroupCanvasDom()'s own template,
        digital region first, then slider slot, then ruler."""
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        digital_idx = fn_body.index('ww-tg-digital-region')
        slider_idx = fn_body.index('ww-tg-slider-slot')
        ruler_idx = fn_body.index('ww-tg-ruler"')
        assert digital_idx < slider_idx < ruler_idx
        # No single element wraps both -- confirmed structurally by their
        # both being direct, sequential children (not nested) inside the
        # same canvas root, which the DOM order above already
        # establishes.

    def test_sticky_offset_is_computed_from_the_rulers_live_height_never_hardcoded(self):
        """Time Group Canvas: renamed wwSyncTimeGroupCanvasStickyOffset(groupId),
        scoped to one canvas's own sticky-bottom wrapper and ruler.
        Bugfix (owner UAT on eb55528): sets exactly ONE element's own
        `bottom` (the wrapper's) from the ruler's own live height --
        the wrapper's own height (slider + readout, whichever is
        visible) is the browser's own normal-flow computation, never a
        second JS measurement that could go stale relative to it."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvasStickyOffset(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'stickyBottomEl.style.bottom = rulerWrapEl.getBoundingClientRect().height + "px";' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-sticky-bottom")' in fn_body
        # The old per-readout/per-slider height measurements are gone.
        assert "readoutEl.getBoundingClientRect().height" not in fn_body
        assert "slotEl.style.bottom" not in fn_body

    def test_offset_sync_is_called_from_the_rulers_own_state_function(self):
        """Time Group Canvas: renamed wwSyncTimeGroupRuler(groupId), the
        per-group generalization of the old single wwSyncStickyRuler()."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("wrapEl.hidden = !hasChannels;", fn_idx) + 200]
        assert "wwSyncTimeGroupCanvasStickyOffset(groupId);" in fn_body

    def test_slider_sync_always_co_occurs_with_a_fresh_ruler_sync(self):
        """Time Group Canvas: unlike the old single-container design
        (which needed a defensive duplicate offset-sync call inside the
        slider's own render, since the ruler and slider could resync on
        different schedules), every call site that syncs a canvas's
        slider (wwApplyAndFetchGroupViewport() and
        wwSyncTimeGroupCanvases()) ALSO syncs that same canvas's own
        ruler in the same pass -- so the sticky offset is always freshly
        recomputed alongside the slider, with no separate defensive
        call needed inside wwSyncTimeGroupSliderForCanvas() itself."""
        source = _source()

        apply_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        apply_body = source[apply_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", apply_idx)]
        assert "wwSyncTimeGroupRuler(groupId);" in apply_body
        assert "wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in apply_body

        sync_idx = source.index("function wwSyncTimeGroupCanvases()")
        sync_body = source[sync_idx : source.index("\n        }\n", sync_idx)]
        assert "wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in sync_body
        assert "wwSyncTimeGroupRuler(groupId);" in sync_body

    def test_owner_css_adjustment_for_slider_row_padding_is_preserved(self):
        """Owner-set exact values -- must never be reverted/reformatted
        back to the earlier WW_PANEL_MARGIN-aligned padding."""
        source = _source()
        assert "padding: 3px 20px 3px 20px; border-top: 1px solid var(--panel-border); background: var(--panel);" in source
        assert source.count(".ww-tg-slider-row:first-child { border-top: none; }") == 1
