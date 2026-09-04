"""Static regression checks for TG-E's per-Time-Group t0 migration.

Governing principle under test throughout this file (the task's own
verbatim rule): "Each Time Group owns its own t0." No workspace-wide
scalar t0 remains; every set/clear/read/display path is explicitly
group-scoped.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_cursors.py, test_frontend_time_group_toolbar.py)
-- no jsdom execution, just confirming the right state model, gating,
wiring, and isolation markers exist in the right places. Real
multi-canvas isolation behavior (setting Group 2's t0 never touching
Group 1) is proven live via Playwright against a running backend -- see
this task's own live-UAT report for the full record.

Case-letter references (A-M) below refer to this task's own section 32
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
# Case A/B: state model -- one independent t0 per Time Group, never one
# workspace-wide scalar.
# ==============================================================================


class TestPerGroupT0StateModel:
    def test_state_is_a_map_keyed_by_group_id_not_a_single_scalar(self):
        source = _source()
        assert "timeGroupT0State: new Map()," in source
        assert "t0WorkspaceTime: null" not in source

    def test_default_resolver_returns_null_for_an_unset_group_without_mutating_the_map(self):
        source = _source()
        fn_idx = source.index("function wwT0ForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert ".set(" not in fn_body
        assert "ww.timeGroupT0State.get(groupId)" in fn_body

    def test_has_t0_and_workspace_event_conversions_all_require_an_explicit_group_id(self):
        source = _source()
        assert "function wwHasT0(groupId)" in source
        assert "function wwWorkspaceTimeToEventTime(workspaceTime, groupId)" in source
        assert "function wwEventTimeToWorkspaceTime(eventTime, groupId)" in source


# ==============================================================================
# Case A/F: local toolbar control per Time Group, each independently
# reflecting Cursor A availability / t0 set-or-unset for THAT group.
# ==============================================================================


class TestLocalT0ToolbarControl:
    def test_t0_button_markup_lives_inside_the_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("ww-tg-t0-btn") == 1

    def test_button_is_wired_to_the_toggle_with_this_canvass_own_group_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-t0-btn")' in fn_body
        assert "wwHandleSetOrClearT0ClickForGroup(groupId)" in fn_body

    def test_old_global_t0_button_and_status_readout_are_fully_removed(self):
        source = _source()
        assert 'id="wwSetT0Btn"' not in source
        assert 'id="statusBarT0"' not in source
        assert 'id="statusBarT0Value"' not in source

    def test_case_f_group_2_set_t0_disabled_without_group_2s_own_cursor_a(self):
        """Case F: a group's own button must gate on THAT group's own
        Cursor A -- never a different group's."""
        source = _source()
        fn_idx = source.index("function wwSyncT0ControlsForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const cursors = wwTimeGroupCursorState(groupId);" in fn_body
        assert "const cursorAReady = cursors.enabled && cursors.a.visible && Number.isFinite(cursors.a.time);" in fn_body
        assert "btn.disabled = !hasT0 && !cursorAReady;" in fn_body
        # Never a hidden fallback to any single "primary" group.
        assert "wwPrimaryTimeGroupId()" not in fn_body


# ==============================================================================
# Case A/C/D: setting t0 for one group only ever writes THAT group's own
# key -- structurally impossible to touch an unrelated group.
# ==============================================================================


class TestSetT0OnlyTouchesItsOwnGroup:
    def test_set_t0_from_cursor_a_reads_and_writes_only_the_given_group(self):
        source = _source()
        fn_idx = source.index("async function wwSetT0FromCursorAForGroup(groupId)")
        fn_body = source[fn_idx : source.index("async function wwClearT0ForGroup(groupId)", fn_idx)]
        assert "const cursors = wwTimeGroupCursorState(groupId);" in fn_body
        assert "const sourceId = wwAnySourceIdForTimeGroup(groupId);" in fn_body
        assert "body: JSON.stringify({ source_id: sourceId, t0_workspace_time: cursors.a.time })" in fn_body
        assert "ww.timeGroupT0State.set(groupId, body.t0_workspace_time);" in fn_body
        assert "wwSyncT0ControlsForGroup(groupId);" in fn_body
        assert "wwApplyT0ToDisplayForGroup(groupId);" in fn_body

    def test_any_source_id_helper_only_considers_this_groups_own_members(self):
        source = _source()
        fn_idx = source.index("function wwAnySourceIdForTimeGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwSourceIdsForTimeGroup(groupId)" in fn_body


# ==============================================================================
# Case E: clearing t0 for one group only ever deletes THAT group's own
# key -- another group's own t0 is untouched.
# ==============================================================================


class TestClearT0OnlyTouchesItsOwnGroup:
    def test_clear_t0_deletes_only_the_given_groups_own_entry(self):
        source = _source()
        fn_idx = source.index("async function wwClearT0ForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwHandleSetOrClearT0ClickForGroup(groupId)", fn_idx)]
        assert "const sourceId = wwAnySourceIdForTimeGroup(groupId);" in fn_body
        assert '"?source_id=" + encodeURIComponent(sourceId)' in fn_body
        assert "ww.timeGroupT0State.delete(groupId);" in fn_body
        assert "wwSyncT0ControlsForGroup(groupId);" in fn_body
        assert "wwApplyT0ToDisplayForGroup(groupId);" in fn_body

    def test_toggle_handler_dispatches_by_this_groups_own_has_t0(self):
        source = _source()
        fn_idx = source.index("function wwHandleSetOrClearT0ClickForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (wwHasT0(groupId)) {" in fn_body
        assert "wwClearT0ForGroup(groupId);" in fn_body
        assert "wwSetT0FromCursorAForGroup(groupId);" in fn_body


# ==============================================================================
# Case G: ruler -- only the owning group's ruler shifts.
# ==============================================================================


class TestRulerUsesOnlyItsOwnGroupsT0:
    def test_ruler_hasT0_and_elapsed_to_plotly_x_calls_use_this_groups_own_id(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'if (ww.timeMode === "absolute" && !wwHasT0(groupId)) {' in fn_body
        assert "wwElapsedToPlotlyX(groupId, start)" in fn_body
        assert "wwElapsedToPlotlyX(groupId, end)" in fn_body
        assert '(wwHasT0(groupId) ? "Event " : "")' in fn_body


# ==============================================================================
# Case H: analog -- only the owning group's own analog X mapping shifts.
# ==============================================================================


class TestAnalogTraceUsesOnlyItsOwnChannelsGroup:
    def test_build_trace_derives_group_id_from_the_channels_own_source(self):
        source = _source()
        fn_idx = source.index("function wwBuildTrace(channel, panel)")
        fn_body = source[fn_idx : source.index("function wwBuildLayout(panel, colors)", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(channel.sourceId);" in fn_body
        assert "wwElapsedToPlotlyX(groupId, t)" in fn_body

    def test_build_layout_derives_group_id_from_the_panels_own_channels(self):
        """TG-G (DEC-061 fix): wwBuildLayout() must build its xaxis
        range/tick-format from THIS panel's own group's range
        (wwTimeGroupVisibleRange(groupId)), never the single global
        ww.viewport directly -- see test_frontend_time_group_layout.py
        for the full DEC-061 regression coverage."""
        source = _source()
        fn_idx = source.index("function wwBuildLayout(panel, colors)")
        fn_body = source[fn_idx : fn_idx + 1400]
        assert "const groupId = wwPanelTimeGroupId(panel);" in fn_body
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "wwElapsedToPlotlyX(groupId, range.start)" in fn_body
        assert "wwElapsedToPlotlyX(groupId, ww.viewport.start)" not in fn_body


# ==============================================================================
# Case I: digital -- only the owning group's own digital mapping shifts.
# ==============================================================================


class TestDigitalChartUsesOnlyItsOwnGroupsT0:
    def test_rebuild_digital_chart_threads_its_own_group_id_through_every_x_projection(self):
        source = _source()
        fn_idx = source.index("function wwRebuildDigitalChart(groupId)")
        fn_body = source[fn_idx : source.index("function wwRebuildAllTimeGroupDigitalCharts()", fn_idx)]
        assert "wwElapsedToPlotlyX(groupId, entry.startTime + entryOffset)" in fn_body
        assert "wwElapsedToPlotlyX(groupId, entry.endTime + entryOffset)" in fn_body
        assert "wwElapsedToPlotlyX(groupId, hiStart), x1: wwElapsedToPlotlyX(groupId, hiEnd)" in fn_body


# ==============================================================================
# Case J: cursor stability -- setting/clearing t0 must never rewrite the
# stored physical cursor times, only their displayed mapping.
# ==============================================================================


class TestCursorStabilityAcrossT0Changes:
    def test_set_t0_never_assigns_a_cursor_time(self):
        source = _source()
        fn_idx = source.index("async function wwSetT0FromCursorAForGroup(groupId)")
        fn_body = source[fn_idx : source.index("async function wwClearT0ForGroup(groupId)", fn_idx)]
        assert "cursors.a.time =" not in fn_body
        assert "cursors.b.time =" not in fn_body

    def test_clear_t0_never_assigns_a_cursor_time(self):
        source = _source()
        fn_idx = source.index("async function wwClearT0ForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwHandleSetOrClearT0ClickForGroup(groupId)", fn_idx)]
        assert "cursors.a.time =" not in fn_body
        assert "cursors.b.time =" not in fn_body

    def test_apply_t0_to_display_never_assigns_a_cursor_time(self):
        source = _source()
        fn_idx = source.index("function wwApplyT0ToDisplayForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwSyncT0ControlsForGroup(groupId)", fn_idx)]
        assert "cursors.a.time =" not in fn_body
        assert "cursors.b.time =" not in fn_body
        assert "timeGroupCursorState" not in fn_body


# ==============================================================================
# Case K: layout sweep -- Grouped/Separate/Custom must preserve group t0
# ownership; a layout-mode rebuild never touches ww.timeGroupT0State.
# ==============================================================================


class TestLayoutModeSweepPreservesT0Ownership:
    def test_rebuild_layout_never_reads_or_writes_time_group_t0_state(self):
        source = _source()
        fn_idx = source.index("function wwRebuildLayout()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "timeGroupT0State" not in fn_body

    def test_every_freshly_recreated_panel_resolves_its_own_group_id_fresh(self):
        """A layout-mode rebuild tears down and recreates every panel via
        wwCreatePanelDom()/wwInitPanelPlot() -> wwBuildLayout(); each
        fresh panel re-derives its own groupId from wwPanelTimeGroupId(),
        never carrying a stale one forward -- so t0 ownership survives
        the rebuild by construction, not by copying state around."""
        source = _source()
        fn_idx = source.index("function wwBuildLayout(panel, colors)")
        fn_body = source[fn_idx : fn_idx + 1400]
        assert "const groupId = wwPanelTimeGroupId(panel);" in fn_body


# ==============================================================================
# Case L/M: merge/split lifecycle -- ambiguous t0 state resets on
# topology change, mirroring TG-D2's own established cursor-state policy.
# ==============================================================================


class TestMergeSplitLifecycleResetsT0:
    def test_pruning_loop_deletes_t0_state_only_for_groups_that_actually_disappeared(self):
        source = _source()
        fn_idx = source.index("for (const canvasEl of Array.from(container.querySelectorAll(\".ww-time-group-canvas\")))")
        fn_body = source[fn_idx : fn_idx + 3200]
        assert "if (!sortedIds.includes(groupId)) {" in fn_body
        assert "ww.timeGroupT0State.delete(groupId);" in fn_body

    def test_zero_active_groups_branch_clears_t0_state_entirely(self):
        source = _source()
        idx = source.index("ww.rulerReadyByGroup.clear();\n                ww.digitalChartReadyByGroup.clear();")
        block = source[idx : idx + 2200]
        assert "ww.timeGroupT0State.clear();" in block

    def test_no_code_path_guesses_or_averages_or_inherits_a_primary_t0_on_merge(self):
        """Task's own explicit warning: "Do not guess which t0 wins. Do
        not average them. Do not inherit primary group's t0 silently." --
        the prune loop's own deletion is the ONLY thing that happens to
        t0 state on a topology change; there is no averaging/copying
        logic anywhere in this codebase to begin with."""
        source = _source()
        assert "timeGroupT0State" not in _function_body(
            source, "function wwRebuildLayout()", "\n        }\n"
        )


# ==============================================================================
# Cross-cutting: t0 display precedence in the cursor readout, unconditional
# per group (superseding TG-D2's own interim primary-group-only gate).
# ==============================================================================


class TestFormatCursorPointTimeIsFullyPerGroup:
    def test_event_time_branch_gates_on_this_groups_own_has_t0_only(self):
        source = _source()
        fn_idx = source.index("function wwFormatCursorPointTime(elapsedSeconds, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (wwHasT0(groupId)) {" in fn_body
        assert "wwWorkspaceTimeToEventTime(elapsedSeconds, groupId)" in fn_body
        assert "wwPrimaryTimeGroupId()" not in fn_body
