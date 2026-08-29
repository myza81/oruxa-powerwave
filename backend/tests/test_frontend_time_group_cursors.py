"""Static regression checks for TG-D2 -- migrating Cursor A/B and A-B
measurement/information state into each Time Group Canvas.

Governing principle under test throughout this file (the task's own
verbatim rule): "Cursor A/B is meaningful only inside one coherent Time
Group. No cursor state, overlay, value, or A-B measurement may leak
across Time Group boundaries."

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_toolbar.py, test_frontend_time_group_canvas_empty_state.py)
-- no jsdom execution, just confirming the right state model, gating,
wiring, and isolation markers exist in the right places. Real
multi-canvas isolation behavior (Group 1 unaffected by Group 2) is
proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.

Case-letter references (A-P) below refer to this task's own section 32
required-test list.
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


# ==============================================================================
# Case A/B: state model -- one independent cursor pair per Time Group,
# never one workspace-wide pair.
# ==============================================================================


class TestPerGroupStateModel:
    def test_state_is_a_map_keyed_by_group_id_not_a_single_object(self):
        source = _source()
        assert "timeGroupCursorState: new Map()," in source
        # The old single workspace-wide object is gone entirely.
        assert "measurementCursors:" not in source

    def test_default_resolver_never_mutates_the_map(self):
        """wwTimeGroupCursorState(groupId) is READ-ONLY -- an untouched
        group must not silently gain a Map entry just from being
        queried (Case A: querying Group 2 before it is ever touched
        must not affect Group 1 or create ambiguous shared state)."""
        source = _source()
        fn_idx = source.index("function wwTimeGroupCursorState(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert ".set(" not in fn_body
        assert "enabled: false" in fn_body

    def test_ensure_resolver_creates_and_caches_a_real_entry(self):
        source = _source()
        fn_idx = source.index("function wwEnsureTimeGroupCursorStateEntry(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "ww.timeGroupCursorState.get(groupId)" in fn_body
        assert "ww.timeGroupCursorState.set(groupId, entry)" in fn_body

    def test_every_write_path_goes_through_the_ensure_resolver_not_a_raw_set(self):
        """Every mutator (toggle, visibility, init positions) must use
        the get-or-create resolver -- never construct/replace a Map
        entry by hand, which would risk clobbering sibling state."""
        source = _source()
        for fn_sig, next_sig in [
            ("function wwToggleMeasurementCursors(groupId)", "function wwSetMeasurementCursorVisible"),
            ("function wwSetMeasurementCursorVisible(groupId, kind, visible)", "// TG-D2: wwReinitCursorsForNewViewport"),
            ("function wwInitMeasurementCursorPositions(groupId)", "// TG-D2: the per-group toolbar mode toggle"),
        ]:
            body = _function_body(source, fn_sig, next_sig)
            assert "wwEnsureTimeGroupCursorStateEntry(groupId)" in body


# ==============================================================================
# Case C: per-group toolbar control -- enabling Group 1 never enables
# Group 2, and the old global control is gone.
# ==============================================================================


class TestPerGroupToolbarControl:
    def test_cursor_mode_button_markup_lives_inside_the_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("ww-tg-cursor-mode-btn") == 1

    def test_button_is_wired_to_toggle_with_this_canvass_own_group_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-cursor-mode-btn")' in fn_body
        assert "wwToggleMeasurementCursors(groupId)" in fn_body

    def test_old_global_cursor_mode_button_id_is_fully_removed(self):
        source = _source()
        assert 'id="wwCursorModeBtn"' not in source


# ==============================================================================
# Case C/D: toggle-and-place semantics preserved exactly -- enable ->
# auto-init at 1/3-2/3 (only the first time), never click-to-place.
# ==============================================================================


class TestToggleAndPlacementSemanticsPreserved:
    def test_toggle_off_retains_stored_times_untouched(self):
        source = _source()
        fn_idx = source.index("function wwToggleMeasurementCursors(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        off_branch = fn_body[fn_body.index("if (cursors.enabled) {") : fn_body.index("return;\n            }\n            cursors.enabled = true;")]
        assert "cursors.enabled = false;" in off_branch
        assert ".time = " not in off_branch

    def test_toggle_on_only_fresh_inits_when_both_times_are_still_null(self):
        source = _source()
        fn_idx = source.index("function wwToggleMeasurementCursors(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (!Number.isFinite(cursors.a.time) || !Number.isFinite(cursors.b.time)) {" in fn_body
        assert "wwInitMeasurementCursorPositions(groupId);" in fn_body

    def test_toggle_on_restores_visibility_for_both_cursors(self):
        source = _source()
        fn_idx = source.index("function wwToggleMeasurementCursors(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "cursors.a.visible = true;" in fn_body
        assert "cursors.b.visible = true;" in fn_body

    def test_init_positions_uses_this_groups_own_visible_range_at_one_third_two_thirds(self):
        source = _source()
        fn_idx = source.index("function wwInitMeasurementCursorPositions(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupVisibleRange(groupId)" in fn_body
        assert "entry.a.time = range.start + width / 3;" in fn_body
        assert "entry.b.time = range.start + (2 * width) / 3;" in fn_body


# ==============================================================================
# Case D/I/J: cursor coordinate is canonical Time Group time, never a
# pixel, and every projection helper requires an explicit groupId
# (task section 9's own anti-pattern warning: "avoid hidden fallback
# to primary group").
# ==============================================================================


class TestProjectionHelpersRequireExplicitGroupId:
    def test_time_to_pixel_signature_takes_group_id_first(self):
        source = _source()
        assert "function wwCursorTimeToPixelX(groupId, time)" in source

    def test_pixel_to_time_signature_takes_group_id_first(self):
        source = _source()
        assert "function wwCursorPixelXToTime(groupId, pageX, metrics)" in source

    def test_plot_metrics_signature_takes_group_id(self):
        source = _source()
        assert "function wwCursorPlotMetrics(groupId)" in source

    def test_time_to_pixel_reads_this_groups_own_visible_range_not_the_global_viewport(self):
        """The specific regression this task exists to prevent: a
        non-primary canvas must never have its cursor projected using
        ww.viewport (the primary group's own range)."""
        source = _source()
        fn_idx = source.index("function wwCursorTimeToPixelX(groupId, time)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupVisibleRange(groupId)" in fn_body
        assert "ww.viewport" not in fn_body

    def test_pixel_to_time_reads_this_groups_own_visible_range_not_the_global_viewport(self):
        source = _source()
        fn_idx = source.index("function wwCursorPixelXToTime(groupId, pageX, metrics)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupVisibleRange(groupId)" in fn_body
        assert "ww.viewport" not in fn_body


# ==============================================================================
# Case F/G/H: each Time Group Canvas owns its own overlay DOM -- never
# one workspace-wide overlay singleton.
# ==============================================================================


class TestOverlayDomLivesInsideEachCanvas:
    def test_overlay_and_label_layer_markup_appear_exactly_once_per_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count('class="ww-tg-cursor-overlay"') == 1
        assert fn_body.count('class="ww-tg-cursor-label-layer"') == 1

    def test_no_workspace_level_cursor_overlay_singleton_remains(self):
        source = _source()
        assert 'id="wwCursorOverlay"' not in source
        assert 'id="wwCursorLabelLayer"' not in source

    def test_canvas_creation_wires_the_per_canvas_overlay_exactly_once(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwWireTimeGroupCursorOverlay(") == 1
        assert "wwWireTimeGroupCursorOverlay(section, groupId);" in fn_body

    def test_overlay_wiring_resolves_dom_from_its_own_canvas_element_scoped_queries(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupCursorOverlay(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-cursor-overlay")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-label-layer")' in fn_body


# ==============================================================================
# Case F/G/H (continued): the overlay UPDATE function is per-group, and
# a workspace-wide sweep only ever touches ACTIVE groups via the
# per-group function -- never a second, separate rendering path.
# ==============================================================================


class TestOverlayUpdateIsPerGroupScoped:
    def test_update_function_takes_group_id_and_resolves_this_groups_own_canvas(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : fn_idx + 1600]
        assert "wwTimeGroupCanvasEl(groupId)" in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-overlay")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-label-layer")' in fn_body
        assert 'canvasEl.querySelector(".ww-tg-cursor-readout")' in fn_body

    def test_batch_wrapper_loops_every_active_group_through_the_same_per_group_function(self):
        source = _source()
        fn_idx = source.index("function wwUpdateAllCursorOverlays()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwActiveTimeGroupIds()" in fn_body
        assert "wwUpdateCursorOverlayForGroup(groupId)" in fn_body

    def test_a_missing_canvas_for_the_given_group_is_a_safe_no_op(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : fn_idx + 300]
        assert "if (!canvasEl) return;" in fn_body


# ==============================================================================
# Case A/E: A-B info panel moved into each canvas, computed only from
# that group's own cursor state.
# ==============================================================================


class TestABReadoutPanelIsPerGroup:
    def test_readout_markup_lives_in_the_canvas_template_hidden_by_default(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count('class="ww-tg-cursor-readout" hidden') == 1
        assert "ww-tg-cursor-readout-value--a" in fn_body
        assert "ww-tg-cursor-readout-value--b" in fn_body
        assert "ww-tg-cursor-readout-value--delta" in fn_body

    def test_readout_values_are_populated_from_this_groups_own_cursor_state_only(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwFormatCursorPointTime(cursors.a.time, groupId)" in fn_body
        assert "wwFormatCursorPointTime(cursors.b.time, groupId)" in fn_body
        assert "wwFormatCursorDuration(cursors.b.time - cursors.a.time)" in fn_body

    def test_readout_visibility_follows_this_groups_own_enabled_flag(self):
        source = _source()
        fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "readoutEl.hidden = !active;" in fn_body


# ==============================================================================
# Case P: no stale global status-bar A/B/Δt readout left representing
# "whichever group was clicked last."
# ==============================================================================


class TestGlobalStatusBarCursorReadoutRemoved:
    def test_status_bar_no_longer_carries_any_of_the_old_cursor_readout_ids(self):
        source = _source()
        assert 'id="wwCursorReadout"' not in source
        assert 'id="statusBarCursorA"' not in source
        assert 'id="statusBarCursorB"' not in source
        assert 'id="statusBarCursorDelta"' not in source

    def test_status_spacer_and_t0_status_item_are_still_present(self):
        """The spacer/T0 item are unrelated to this migration and must
        survive -- confirms the removal was targeted, not a wholesale
        deletion of the status bar region."""
        source = _source()
        assert "ww-status-spacer" in source
        assert 'id="statusBarT0"' in source


# ==============================================================================
# Case D/E (channel-value correctness): a channel's Cur A/Cur B sidebar
# value must use ITS OWN owning group's cursor state -- this is the
# core fix for cross-group channel-value leakage.
# ==============================================================================


class TestChannelValueLookupUsesOwningGroup:
    def test_analog_cur_value_text_resolves_its_own_sources_owning_group_first(self):
        source = _source()
        fn_idx = source.index("function wwCurValueText(sourceId, channelName, kind)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupIdForDisplaySourceId(sourceId)" in fn_body
        assert 'if (groupId === null) return "—";' in fn_body
        assert "wwTimeGroupCursorState(groupId)" in fn_body

    def test_digital_cur_state_text_resolves_its_own_sources_owning_group_first(self):
        source = _source()
        fn_idx = source.index("function wwDigitalCurStateText(sourceId, channelName, kind)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupIdForDisplaySourceId(sourceId)" in fn_body
        assert 'if (groupId === null) return "—";' in fn_body
        assert "wwTimeGroupCursorState(groupId)" in fn_body


# ==============================================================================
# Case L/M/N: topology-driven reset -- merge/split/last-channel removal
# clear the affected group's own cursor state; a group that survives
# unchanged keeps its own state.
# ==============================================================================


class TestTopologyDrivenStateReset:
    def test_pruning_loop_deletes_cursor_state_only_for_groups_that_actually_disappeared(self):
        source = _source()
        fn_idx = source.index("for (const canvasEl of Array.from(container.querySelectorAll(\".ww-time-group-canvas\")))")
        fn_body = source[fn_idx : fn_idx + 1800]
        assert "if (!sortedIds.includes(groupId)) {" in fn_body
        assert "ww.timeGroupCursorState.delete(groupId);" in fn_body

    def test_zero_active_groups_branch_clears_cursor_state_entirely(self):
        source = _source()
        idx = source.index("ww.rulerReadyByGroup.clear();\n                ww.digitalChartReadyByGroup.clear();")
        block = source[idx : idx + 900]
        assert "ww.timeGroupCursorState.clear();" in block

    def test_clear_workspace_clears_cursor_state_unconditionally_for_both_branches(self):
        """Deliberate TG-D2 policy change: BOTH "Clear workspace" and
        "Start New Workspace" now clear per-group cursor state (every
        canvas -- and its own overlay DOM -- is destroyed either way),
        unlike the old single-cursor era where plain "Clear workspace"
        left cursor state alone. The clearing lines must appear BEFORE
        the resetSourceBounds-only branch, i.e. unconditionally."""
        source = _source()
        fn_idx = source.index("function wwClearWorkspace(options)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        clear_call_idx = fn_body.index("ww.timeGroupCursorState.clear();")
        branch_idx = fn_body.index("if (options.resetSourceBounds) {")
        assert clear_call_idx < branch_idx
        assert "ww.cursorValues.clear();" in fn_body
        assert "ww.digitalCursorValues.clear();" in fn_body

    def test_old_single_cursor_reset_helpers_are_fully_retired(self):
        """Both functions' bodies are deleted (only an explanatory
        comment referencing their old names by way of documentation
        remains) -- no real call site invokes either as a function
        call (`name(` with an opening paren immediately after)."""
        source = _source()
        assert "function wwReinitCursorsForNewViewport()" not in source
        assert "function wwResetMeasurementCursors()" not in source
        assert "wwReinitCursorsForNewViewport();" not in source
        assert "wwResetMeasurementCursors();" not in source


# ==============================================================================
# Section 27: t0 stays primary-group-scoped this slice (deferred to
# TG-E) -- explicitly, not via a silent/ambiguous global read.
# ==============================================================================


class TestT0StaysExplicitlyPrimaryGroupScopedThisSlice:
    def test_sync_t0_controls_reads_the_primary_groups_own_cursor_state(self):
        source = _source()
        fn_idx = source.index("function wwSyncT0Controls()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupCursorState(wwPrimaryTimeGroupId())" in fn_body

    def test_set_t0_from_cursor_a_reads_the_primary_groups_own_cursor_state(self):
        source = _source()
        fn_idx = source.index("async function wwSetT0FromCursorA()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupCursorState(wwPrimaryTimeGroupId())" in fn_body


# ==============================================================================
# Section 30: annotations are an explicit non-goal this slice -- must
# keep working, EXPLICITLY scoped to the primary group (never a hidden
# default now that the projection helper requires a groupId).
# ==============================================================================


class TestAnnotationProjectionExplicitlyStaysPrimaryGroupScoped:
    def test_annotation_page_position_passes_the_primary_group_id_explicitly(self):
        source = _source()
        fn_idx = source.index("function wwAnchoredAnnotationPagePosition(annotation)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwCursorTimeToPixelX(wwPrimaryTimeGroupId(), time)" in fn_body


# ==============================================================================
# Section 31 (performance): a single group's own cursor movement/resize
# must never touch an unrelated group's canvas -- targeted calls use
# the per-group function directly; only genuinely workspace-wide
# triggers use the batch sweep.
# ==============================================================================


class TestTargetedVsBatchOverlayUpdatesAreCorrectlyClassified:
    def test_panel_resize_targets_only_that_panels_own_group(self):
        source = _source()
        fn_idx = source.index("function wwResizePanelPlot(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwUpdateCursorOverlayForGroup(wwPanelTimeGroupId(panel));" in fn_body

    def test_full_visible_plot_resize_sweep_uses_the_batch_form(self):
        source = _source()
        fn_idx = source.index("function wwResizeAllVisiblePlots()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwUpdateAllCursorOverlays();" in fn_body

    def test_layout_mode_rebuild_uses_the_batch_form_at_least_once(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("wwUpdateAllCursorOverlays();") >= 1


# ==============================================================================
# Case I/J: viewport changes (zoom/pan/reset) must never mutate stored
# cursor times -- only pixel projection is recomputed. Verified
# structurally: neither the zoom-step nor pan/reset functions ever
# assign to a cursor's own `.time` field.
# ==============================================================================


class TestViewportChangesNeverMutateStoredCursorTimes:
    def test_step_zoom_x_never_assigns_a_cursor_time(self):
        source = _source()
        fn_idx = source.index("async function wwStepZoomX(groupId, direction)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "cursors.a.time =" not in fn_body
        assert "cursors.b.time =" not in fn_body
        assert ".a.time =" not in fn_body
        assert ".b.time =" not in fn_body
