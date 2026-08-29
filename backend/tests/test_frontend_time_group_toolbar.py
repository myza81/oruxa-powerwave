"""Static regression checks for TG-D1 -- migrating Zoom In/Zoom Out
(staged, X/Y split-button), Reset Time View, and Autoscale Y into each
Time Group Canvas's own local navigation toolbar.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_range_slider.py, test_frontend_time_group_canvas_empty_state.py)
-- no jsdom execution, just confirming the right gating/wiring/isolation
markers exist in the right places. Real multi-canvas isolation behavior
(a click inside Group 2 never touching Group 1) is proven live via
Playwright against a running backend -- see this task's own live-UAT
report for the full record.
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


class TestLocalToolbarShellReusesExistingStructure:
    """Task section 5: use the existing `.ww-tg-toolbar` shell from
    TG-B+C -- never a second toolbar container, never singleton ids
    reintroduced inside a repeated Time Group canvas."""

    def test_exactly_one_toolbar_container_per_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count('class="ww-tg-toolbar"') == 1

    def test_local_toolbar_markup_carries_no_singleton_ids(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        toolbar_start = fn_body.index('class="ww-tg-toolbar"')
        toolbar_end = fn_body.index("ww-tg-panels", toolbar_start)
        toolbar_markup = fn_body[toolbar_start:toolbar_end]
        assert ' id="' not in toolbar_markup

    def test_canvas_creation_wires_the_toolbar_exactly_once(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwWireTimeGroupToolbar(") == 1
        assert "wwWireTimeGroupToolbar(section, groupId);" in fn_body

    def test_local_toolbar_carries_all_four_migrated_controls(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww-tg-zoom-in-split" in fn_body
        assert "ww-tg-zoom-out-split" in fn_body
        assert "ww-tg-reset-view-btn" in fn_body
        assert "ww-tg-autoscale-btn" in fn_body


class TestZoomFunctionsAcceptGroupId:
    """Task section 7: generalize wwStepZoomX()/wwStepZoomY() to accept
    a groupId, reading/writing that group's own viewport rather than
    the single workspace-wide ww.viewport."""

    def test_step_zoom_x_signature_takes_group_id_first(self):
        source = _source()
        assert "async function wwStepZoomX(groupId, direction)" in source

    def test_step_zoom_x_reads_this_groups_own_visible_range(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "ww.viewport" not in fn_body

    def test_step_zoom_x_zoom_out_clamps_to_this_groups_own_bounds(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwClampPanWindowToTimeGroup(groupId, next.start, next.end)" in fn_body

    def test_step_zoom_x_applies_through_the_group_scoped_viewport_call(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "clearTimeout(ww.timeGroupViewportDebounceTimers.get(groupId));" in fn_body
        assert "await wwApplyAndFetchGroupViewport(groupId, next.start, next.end);" in fn_body

    def test_step_zoom_x_preserves_the_exact_stepping_factors_and_floor(self):
        """Preserve current stage sizes/numeric semantics exactly --
        task section 7's own explicit requirement."""
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "direction === \"in\" ? WW_ZOOM_STEP_IN_FACTOR : WW_ZOOM_STEP_OUT_FACTOR" in fn_body
        assert "Math.max(newSpan, WW_MIN_X_SPAN_SECONDS)" in fn_body

    def test_step_zoom_y_signature_takes_group_id_first(self):
        source = _source()
        assert "function wwStepZoomY(groupId, direction)" in source

    def test_step_zoom_y_resolves_the_active_panel_scoped_to_this_group(self):
        """Task section 9: Y zoom applies only to panels inside the
        launching Time Group -- never wwActivePanel() unscoped."""
        source = _source()
        fn_idx = source.index("function wwStepZoomY(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const panel = wwActivePanelForGroup(groupId);" in fn_body
        assert "wwActivePanel()" not in fn_body

    def test_step_zoom_y_preserves_exact_range_reading_and_floor_semantics(self):
        source = _source()
        fn_idx = source.index("function wwStepZoomY(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "fl && fl.yaxis ? fl.yaxis.range : null" in fn_body
        assert "Math.max(newSpan, WW_MIN_Y_SPAN)" in fn_body
        assert '"yaxis.autorange": false' in fn_body


class TestActivePanelForGroupExcludesOtherGroups:
    """Task section 9: 'ensure unrelated groups are excluded' -- the
    per-group fallback must never resolve to ww.panels[0] outright,
    which could belong to a different Time Group."""

    def test_falls_back_to_the_first_panel_belonging_to_this_group_only(self):
        source = _source()
        fn_idx = source.index("function wwActivePanelForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPanelTimeGroupId(active) === groupId" in fn_body
        assert "ww.panels.find((p) => wwPanelTimeGroupId(p) === groupId)" in fn_body
        assert "ww.panels[0]" not in fn_body

    def test_never_mutates_the_global_active_panel_pointer(self):
        """A group-scoped fallback lookup must not have the side effect
        of reassigning ww.activePanelGroupKey (that would be an
        invisible cross-group side effect through shared global
        state)."""
        source = _source()
        fn_idx = source.index("function wwActivePanelForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.activePanelGroupKey =" not in fn_body


class TestResetIsGroupScopedOnly:
    """Task section 10: confirm/harden Reset Time View's per-group
    semantics -- the group toolbar must use the group-specific
    implementation, never the workspace-wide reset-all."""

    def test_reset_one_time_group_view_never_loops_every_active_group(self):
        source = _source()
        fn_idx = source.index("async function wwResetOneTimeGroupView(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwDeriveTimeGroupBounds(groupId)" in fn_body
        assert "await wwApplyAndFetchGroupViewport(groupId, bounds.start, bounds.end);" in fn_body
        assert "wwActiveTimeGroupIds()" not in fn_body

    def test_local_toolbar_reset_button_wired_to_the_group_specific_function(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-reset-view-btn")' in fn_body
        assert "wwResetOneTimeGroupView(groupId)" in fn_body

    def test_workspace_wide_reset_time_view_kept_only_as_a_compatibility_wrapper(self):
        """Task section 10: 'if a workspace-global helper must remain
        for compatibility, keep it as a wrapper' -- confirmed no longer
        wired to any button."""
        source = _source()
        assert "async function wwResetTimeView()" in source
        assert 'addEventListener("click", wwResetTimeView)' not in source


class TestAutoscaleIsGroupScopedOnly:
    """Task section 11: Autoscale Y applies only to analog panels in
    the launching Time Group."""

    def test_autoscale_for_group_filters_by_this_groups_own_panels(self):
        source = _source()
        fn_idx = source.index("function wwAutoscaleYForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (wwPanelTimeGroupId(panel) !== groupId) continue;" in fn_body
        assert '"yaxis.autorange": true' in fn_body

    def test_local_toolbar_autoscale_button_wired_to_the_group_specific_function(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-autoscale-btn")' in fn_body
        assert "wwAutoscaleYForGroup(groupId)" in fn_body

    def test_workspace_wide_autoscale_y_kept_only_as_a_compatibility_wrapper(self):
        source = _source()
        assert "function wwAutoscaleY()" in source
        assert 'addEventListener("click", wwAutoscaleY)' not in source


class TestToolbarWiringResolvesControlsFromTheLaunchingCanvas:
    """Task section 6: avoid document.getElementById() for per-group
    controls -- prefer scoped canvasEl.querySelector(), a reusable
    wiring helper receiving groupId. No manual per-group duplication."""

    def test_wire_time_group_toolbar_never_uses_document_get_element_by_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert "document.getElementById(" not in fn_body

    def test_wire_time_group_toolbar_resolves_zoom_splits_scoped_to_canvas(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert 'canvasEl.querySelector(action === "in" ? ".ww-tg-zoom-in-split" : ".ww-tg-zoom-out-split")' in fn_body

    def test_zoom_main_button_click_dispatches_with_this_groups_own_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert "mainBtn.addEventListener(\"click\", () => wwPerformZoomStep(groupId, action));" in fn_body

    def test_zoom_menu_item_click_dispatches_with_this_groups_own_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n\n", fn_idx)]
        assert "wwSetZoomStepAxis(groupId, action, item.dataset.axis);" in fn_body

    def test_created_exactly_once_per_canvas_not_a_document_wide_singleton_wire_up(self):
        """The former wwWireZoomStepSplitButtons() wired two singleton
        ids ONCE at page load; wwWireTimeGroupToolbar() must instead be
        callable once per canvas, with zero references to a single
        global wiring entry point remaining."""
        source = _source()
        assert "function wwWireZoomStepSplitButtons(" not in source


class TestPerGroupZoomAxisPreferenceIsolated:
    """Case isolation for the split-button's own remembered X/Y
    preference -- choosing Y in Group 2's menu must never affect Group
    1's own remembered axis or button label."""

    def test_zoom_step_axis_state_is_a_per_group_map(self):
        source = _source()
        assert "zoomStepAxisByGroup: new Map()" in source

    def test_axis_resolver_defaults_to_x_for_an_unset_group(self):
        source = _source()
        fn_idx = source.index("function wwZoomStepAxisForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'ww.zoomStepAxisByGroup.get(groupId) || { in: "x", out: "x" }' in fn_body

    def test_set_zoom_step_axis_only_updates_this_groups_own_entry(self):
        source = _source()
        fn_idx = source.index("function wwSetZoomStepAxis(groupId, action, axis)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.zoomStepAxisByGroup.set(groupId, { ...current, [action]: resolvedAxis });" in fn_body

    def test_zoom_step_axis_map_cleared_on_workspace_clear(self):
        source = _source()
        fn_idx = source.index("function wwClearWorkspace(options)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.zoomStepAxisByGroup.clear();" in fn_body

    def test_zoom_step_axis_map_pruned_when_a_groups_canvas_is_pruned(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.zoomStepAxisByGroup.delete(groupId);" in fn_body


class TestSyncTimeGroupZoomControlsIsGroupScoped:
    """The per-group generalization of the original
    wwSyncZoomStepControls() -- tooltip/checkmark/disabled-state sync
    scoped to ONE canvas via wwTimeGroupCanvasEl(groupId), never a
    document-wide singleton lookup."""

    def test_resolves_canvas_scoped_to_this_group(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupZoomControls(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const canvasEl = wwTimeGroupCanvasEl(groupId);" in fn_body
        assert "document.getElementById(" not in fn_body

    def test_zoom_out_disabled_state_reads_this_groups_own_bounds(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupZoomControls(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupVisibleRange(groupId)" in fn_body
        assert "wwDeriveTimeGroupBounds(groupId)" in fn_body

    def test_batch_sync_loops_every_active_group(self):
        source = _source()
        fn_idx = source.index("function wwSyncAllTimeGroupZoomControls()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const groupId of wwActiveTimeGroupIds()) wwSyncTimeGroupZoomControls(groupId);" in fn_body


class TestSliderRulerDigitalZoomStayTogetherAfterAnyGroupViewportChange:
    """Task section 16/17: after any X zoom/reset action, viewport <->
    slider <-> ruler <-> digital must remain synchronized for that
    group -- all four sync calls must live in the SAME unconditional
    (not primary-gated) section of wwApplyAndFetchGroupViewport()."""

    def test_ruler_digital_slider_and_zoom_controls_all_resync_unconditionally(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        primary_idx = fn_body.index("if (isPrimary) {")
        primary_end = fn_body.index("wwRecalculateAllPeakAnnotations(startTime, endTime);", primary_idx) + len(
            "wwRecalculateAllPeakAnnotations(startTime, endTime);"
        )
        unconditional_tail = fn_body[primary_end:]
        assert "wwSyncTimeGroupRuler(groupId);" in unconditional_tail
        assert "wwRebuildDigitalChart(groupId);" in unconditional_tail
        assert "wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in unconditional_tail
        assert "wwSyncTimeGroupZoomControls(groupId);" in unconditional_tail

    def test_panel_relayout_restricted_to_this_groups_own_panels(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "if (wwPanelTimeGroupId(panel) !== groupId) continue;" in fn_body

    def test_refetch_restricted_to_this_groups_own_channels(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "await wwRefetchChannelsForGroup(groupId, startTime, endTime);" in fn_body


class TestDoubleClickAutorangeGestureIsGroupScoped:
    """Plotly's own native double-click-to-autorange gesture on a panel
    is a Reset action too -- must reset only that panel's own Time
    Group, matching the isolation rule for every other Reset path."""

    def test_autorange_gesture_resets_only_the_panels_own_group(self):
        source = _source()
        fn_idx = source.index("function wwWirePanelRelayout(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwResetOneTimeGroupView(wwPanelTimeGroupId(panel));" in fn_body
        assert "wwResetTimeView();" not in fn_body


class TestLayoutModePreservesLocalToolbarOwnership:
    """Task section K / TG-D1's own non-goal list: Layout Mode stays
    workspace-global, but a layout-mode switch must never destroy or
    duplicate a canvas's own local toolbar -- wwRebuildLayout() only
    ever clears each canvas's own `.ww-tg-panels`, never the canvas
    root (and therefore never its toolbar) itself."""

    def test_rebuild_layout_only_clears_the_panels_container_never_the_toolbar(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-panels")' in fn_body
        assert "ww-tg-toolbar" not in fn_body
        assert "wwCreateTimeGroupCanvasDom" not in fn_body


class TestGlobalDuplicatesRemoved:
    """Task section 12: after migration, the original workspace-global
    toolbar must not retain a duplicate, still-active way to invoke any
    of the four migrated controls."""

    def test_no_global_zoom_split_button_markup_remains(self):
        source = _source()
        for stale_id in ("wwZoomInSplit", "wwZoomOutSplit", "wwZoomInBtn", "wwZoomOutBtn", "wwZoomInMenu", "wwZoomOutMenu"):
            assert f'id="{stale_id}"' not in source, f"stale global zoom markup id={stale_id} still present"

    def test_no_global_reset_or_autoscale_button_markup_remains(self):
        source = _source()
        assert 'id="wwResetViewBtn"' not in source
        assert 'id="wwAutoscaleBtn"' not in source

    def test_no_global_wiring_call_for_the_old_singleton_split_buttons(self):
        source = _source()
        assert "wwWireZoomStepSplitButtons();" not in source

    def test_deferred_global_controls_are_still_present_and_untouched(self):
        """Task section 4/12: Layout Mode, Time Mode, Unit Mode,
        Synchronise Sources, upload, and the annotation drawer all
        remain workspace-global -- confirms this slice did not
        accidentally remove or migrate them. (Cursor A/B was migrated in
        the later TG-D2 slice, and t0 in the later TG-E slice -- see
        test_frontend_time_group_cursors.py/test_frontend_synchronization_t0.py
        for their own coverage.)"""
        source = _source()
        for still_global_id in (
            "layoutModeGroupedBtn",
            "timeModeAbsoluteBtn",
            "wwUnitModeBtn",
            "recordingsUploadBtn",
        ):
            assert f'id="{still_global_id}"' in source, f"expected still-global control id={still_global_id} to remain"


class TestMergeSplitLifecycleAlwaysProducesAToolbar:
    """Task section 18/Case L: toolbar count follows active Time Group
    count. Since every Time Group Canvas -- however it comes to exist,
    whether from a genuinely new group, a merge, or a split -- is only
    ever created through the ONE wwCreateTimeGroupCanvasDom() template
    (which always includes the toolbar and always wires it), there is
    no code path that can produce a canvas without a local toolbar, and
    no separate/duplicate creation path that could double-wire one."""

    def test_only_one_function_builds_a_time_group_canvas_root(self):
        source = _source()
        assert source.count("section.className = \"ww-time-group-canvas\";") == 1

    def test_canvas_creating_helper_has_no_new_unaudited_call_sites(self):
        source = _source()
        # "= wwEnsureTimeGroupCanvasDom(groupId)" matches every CALL site
        # (an assignment/ternary result) but not the function's own
        # `function wwEnsureTimeGroupCanvasDom(groupId) {` signature.
        count = source.count("wwEnsureTimeGroupCanvasDom(groupId)") - 1
        assert count == 4, (
            "A new, unaudited call site to the CREATING "
            "wwEnsureTimeGroupCanvasDom() was added this slice -- every "
            "canvas (and therefore every toolbar) must still only ever "
            "come from the same four already-audited creators."
        )
