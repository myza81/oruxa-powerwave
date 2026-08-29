"""Static regression checks for Slice 2 of waveform time synchronization's
frontend surface (frontend/index.html): the explicit common event t=0.
Mirrors test_frontend_synchronization.py's own pure string/index-based
approach -- no jsdom execution, just confirming the right markers exist in
the right places/order.
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


def test_t0_state_exists():
    source = _source()
    assert "timeGroupT0State: new Map()" in source
    assert "t0WorkspaceTime: null" not in source


def test_core_t0_helpers_exist():
    source = _source()
    assert "function wwT0ForGroup(groupId)" in source
    assert "function wwHasT0(groupId)" in source
    assert "function wwWorkspaceTimeToEventTime(workspaceTime, groupId)" in source
    assert "function wwEventTimeToWorkspaceTime(eventTime, groupId)" in source


def test_elapsed_to_plotly_x_delegates_to_t0_conversion():
    """The one centralized choke-point (task's own "extend the existing
    centralized time-conversion helpers, never scatter this arithmetic")
    -- every Plotly-facing coordinate becomes event-time-aware through
    this single pair of functions, with zero changes needed anywhere
    else that already calls them (beyond threading their own groupId
    through, TG-E). Both now REQUIRE an explicit groupId -- no hidden
    fallback to any one "primary" group."""
    source = _source()
    body = _function_body(
        source,
        "function wwElapsedToPlotlyX(groupId, elapsedSeconds)",
        "function wwPlotlyXToElapsed(groupId, x)",
    )
    assert "wwWorkspaceTimeToEventTime(elapsedSeconds, groupId)" in body

    body = _function_body(source, "function wwPlotlyXToElapsed(groupId, x)", "function wwNiceTickStep")
    assert "wwEventTimeToWorkspaceTime(Number(x), groupId)" in body


def test_fetch_synchronization_state_fetches_t0_per_group():
    """TG-E: t0 is genuinely Time-Group-scoped now -- this fetch resolves
    sources, then time-groups, then ONE t0 fetch PER KNOWN GROUP (run in
    parallel via Promise.all), rather than a single fetch for one
    resolved "primary" source."""
    source = _source()
    fn_idx = source.index("async function wwFetchSynchronizationStateForWorkspace()")
    fn_body = source[fn_idx : source.index("function wwParticipatingSourceIds()", fn_idx)]
    assert "/synchronization/t0" in fn_body
    assert "Promise.all(" in fn_body
    assert "ww.timeGroupT0State.clear();" in fn_body
    assert "ww.timeGroupT0State.set(groupId, t0);" in fn_body


def test_set_t0_puts_cursor_a_time_and_clear_t0_deletes():
    source = _source()

    set_idx = source.index("async function wwSetT0FromCursorAForGroup(groupId)")
    set_body = source[set_idx : source.index("async function wwClearT0ForGroup(groupId)", set_idx)]
    assert 'method: "PUT"' in set_body
    assert "/synchronization/t0" in set_body
    assert "t0_workspace_time: cursors.a.time" in set_body
    assert "ww.timeGroupT0State.set(groupId, body.t0_workspace_time);" in set_body

    clear_idx = source.index("async function wwClearT0ForGroup(groupId)")
    clear_body = source[clear_idx : source.index("function wwHandleSetOrClearT0ClickForGroup(groupId)", clear_idx)]
    assert 'method: "DELETE"' in clear_body
    assert "/synchronization/t0" in clear_body
    assert "ww.timeGroupT0State.delete(groupId);" in clear_body


def test_set_t0_requires_cursor_a_to_be_placed():
    """Task section 6/8: "If Cursor A does not exist/has not been placed,
    disable or reject Set as t=0 clearly -- never silently use an
    arbitrary time." -- both the guard clause inside the action itself
    AND the toolbar button's own disabled state must enforce this, using
    THIS group's own cursor state (wwTimeGroupCursorState(groupId)),
    never another group's."""
    source = _source()
    set_idx = source.index("async function wwSetT0FromCursorAForGroup(groupId)")
    set_body = source[set_idx : source.index("async function wwClearT0ForGroup(groupId)", set_idx)]
    assert "const cursors = wwTimeGroupCursorState(groupId);" in set_body
    assert "if (!cursors.enabled || !cursors.a.visible || !Number.isFinite(cursors.a.time)) return;" in set_body

    sync_idx = source.index("function wwSyncT0ControlsForGroup(groupId)")
    sync_body = source[sync_idx : source.index("async function wwSetT0FromCursorAForGroup(groupId)", sync_idx)]
    assert "const cursors = wwTimeGroupCursorState(groupId);" in sync_body
    assert "btn.disabled = !hasT0 && !cursorAReady;" in sync_body


def test_apply_t0_to_display_never_refetches():
    """Task's own Performance Requirement: applying t0 is presentation-
    only -- reprojects each channel's existing time array through
    wwElapsedToPlotlyX(), never a new network request.

    TG-E (task section 31): scoped to ONE group's own panels/ruler/
    digital chart only -- wwSyncTimeGroupRuler(groupId)/
    wwRebuildDigitalChart(groupId), never the "every active group" batch
    sweep -- a group's own t0 change must never touch an unrelated
    group's rendering."""
    source = _source()
    fn_idx = source.index("function wwApplyT0ToDisplayForGroup(groupId)")
    fn_body = source[fn_idx : source.index("function wwSyncT0ControlsForGroup(groupId)", fn_idx)]
    assert "fetch(" not in fn_body
    assert "wwElapsedToPlotlyX(groupId, t)" in fn_body
    assert "wwSyncTimeGroupRuler(groupId);" in fn_body
    assert "wwRebuildDigitalChart(groupId);" in fn_body
    assert "wwSyncAllTimeGroupRulers" not in fn_body
    assert "wwRebuildAllTimeGroupDigitalCharts" not in fn_body


def test_local_toolbar_t0_control_exists_and_old_global_ones_are_gone():
    """TG-E: "Set Cursor A as t=0"/"Clear t=0" moved into each Time Group
    Canvas's own local toolbar -- the old global #wwSetT0Btn/#statusBarT0
    are removed outright, not merely hidden, so there is exactly one
    active way to set/clear a Time Group's own t0."""
    source = _source()
    fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    assert fn_body.count("ww-tg-t0-btn") == 1
    btn_idx = fn_body.index("ww-tg-t0-btn")
    btn_tag = fn_body[max(0, btn_idx - 80) : fn_body.index(">", btn_idx)]
    assert "disabled" in btn_tag

    assert 'id="wwSetT0Btn"' not in source
    assert 'id="statusBarT0"' not in source
    assert 'id="statusBarT0Value"' not in source


def test_click_handler_wired_and_toggles_between_set_and_clear():
    source = _source()
    fn_idx = source.index("function wwHandleSetOrClearT0ClickForGroup(groupId)")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    assert "wwClearT0ForGroup(groupId);" in fn_body
    assert "wwSetT0FromCursorAForGroup(groupId);" in fn_body

    wire_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
    wire_body = source[wire_idx : source.index("\n        }\n", wire_idx)]
    assert 'canvasEl.querySelector(".ww-tg-t0-btn")' in wire_body
    assert "wwHandleSetOrClearT0ClickForGroup(groupId)" in wire_body


def test_cursor_overlay_refreshes_t0_controls():
    """Cursor A's own placement/removal must immediately update THAT
    group's own button's enabled state -- wired from the same function
    every other cursor-driven UI refresh already goes through, and now
    unconditional (never gated on being the primary group -- the OLD
    TG-D2-era limit this task's own predecessor slice left in place)."""
    source = _source()
    fn_idx = source.index("function wwUpdateCursorOverlayForGroup(")
    fn_body = source[fn_idx : fn_idx + 1600]
    assert "wwSyncT0ControlsForGroup(groupId);" in fn_body


def test_event_time_axis_title_and_signed_cursor_formatting():
    source = _source()
    assert 'if (wwHasT0(groupId)) return "Event Time (s)";' in source
    assert "function wwFormatSignedCursorDuration(seconds)" in source

    fmt_idx = source.index("function wwFormatCursorPointTime(")
    fmt_body = source[fmt_idx : source.index("\n        }\n", fmt_idx)]
    assert "wwHasT0(groupId)" in fmt_body
    assert "wwFormatSignedCursorDuration(wwWorkspaceTimeToEventTime(elapsedSeconds, groupId))" in fmt_body


def test_new_workspace_clears_t0_but_plain_clear_workspace_does_not():
    """Task section 14/15/16 (topology-driven reset) alongside the
    ORIGINAL, still-preserved Slice 2 policy: "Start New Workspace"
    clears EVERY Time Group's own t0, but plain "Clear workspace" does
    not (a still-loaded source's own group id is unchanged by a plain
    clear, so its own t0 remains meaningful) -- same established split
    ww.alignmentOffsets already has, deliberately NOT the newer,
    DOM-driven unconditional-clear policy TG-D2 gave cursor state (t0 is
    a plain number with no overlay DOM to invalidate)."""
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    reset_branch = source[clear_idx : source.index("            } else {", clear_idx)]
    assert "ww.timeGroupT0State.clear();" in reset_branch

    else_branch_idx = source.index("            } else {", clear_idx)
    else_branch = source[else_branch_idx : source.index("// Phase 2C-C1", else_branch_idx)]
    assert "ww.timeGroupT0State" not in else_branch


def test_cursor_values_fetch_uses_workspace_time_cursors_unaffected_by_t0():
    """Backend source-native queries must never receive event time
    directly -- cursors.a.time/cursors.b.time remain workspace time (the
    Slice 1 coordinate), so wwFetchCursorValuesForSource() needed zero
    Slice 2 changes: its existing wwWorkspaceTimeToSourceTime() inverse
    mapping is already correct regardless of t0."""
    source = _source()
    fn_idx = source.index("async function wwFetchCursorValuesForSource(sourceId)")
    fn_body = source[fn_idx : source.index("function wwFetchAllCursorValuesForGroup(groupId)", fn_idx)]
    assert "wwEventTimeToWorkspaceTime" not in fn_body
    assert "wwWorkspaceTimeToSourceTime(sourceId, aTime)" in fn_body
    assert "wwWorkspaceTimeToSourceTime(sourceId, bTime)" in fn_body
