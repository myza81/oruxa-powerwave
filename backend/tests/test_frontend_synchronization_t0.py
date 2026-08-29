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
    assert "t0WorkspaceTime: null" in source


def test_core_t0_helpers_exist():
    source = _source()
    assert "function wwT0WorkspaceTime()" in source
    assert "function wwHasT0()" in source
    assert "function wwWorkspaceTimeToEventTime(workspaceTime)" in source
    assert "function wwEventTimeToWorkspaceTime(eventTime)" in source


def test_elapsed_to_plotly_x_delegates_to_t0_conversion():
    """The one centralized choke-point (task's own "extend the existing
    centralized time-conversion helpers, never scatter this arithmetic")
    -- every Plotly-facing coordinate becomes event-time-aware through
    this single pair of functions, with zero changes needed anywhere
    else that already calls them."""
    source = _source()
    body = _function_body(
        source,
        "function wwElapsedToPlotlyX(elapsedSeconds)",
        "function wwPlotlyXToElapsed(x)",
    )
    assert "wwWorkspaceTimeToEventTime(elapsedSeconds)" in body

    body = _function_body(source, "function wwPlotlyXToElapsed(x)", "function wwNiceTickStep")
    assert "wwEventTimeToWorkspaceTime(Number(x))" in body


def test_fetch_synchronization_state_fetches_t0_alongside_offsets():
    """Timestamp-Based Initial Alignment and Time Groups: t0 is now
    Time-Group-scoped, so this fetch became sequential -- sources, then
    time-groups, then (only once a primary source is known via
    wwPrimaryTimeGroupSourceId()) that group's own t0 -- rather than a
    single parallel fetch keyed by nothing but the workspace."""
    source = _source()
    fn_idx = source.index("async function wwFetchSynchronizationStateForWorkspace()")
    fn_body = source[fn_idx : source.index("function wwParticipatingSourceIds()", fn_idx)]
    assert "/synchronization/t0" in fn_body
    assert "ww.t0WorkspaceTime = t0Body.t0_workspace_time;" in fn_body


def test_set_t0_puts_cursor_a_time_and_clear_t0_deletes():
    source = _source()

    set_idx = source.index("async function wwSetT0FromCursorA()")
    set_body = source[set_idx : source.index("async function wwClearT0()", set_idx)]
    assert 'method: "PUT"' in set_body
    assert "/synchronization/t0" in set_body
    assert "t0_workspace_time: cursors.a.time" in set_body
    assert "ww.t0WorkspaceTime = body.t0_workspace_time;" in set_body

    clear_idx = source.index("async function wwClearT0()")
    clear_body = source[clear_idx : source.index("function wwHandleSetOrClearT0Click()", clear_idx)]
    assert 'method: "DELETE"' in clear_body
    assert "/synchronization/t0" in clear_body
    assert "ww.t0WorkspaceTime = null;" in clear_body


def test_set_t0_requires_cursor_a_to_be_placed():
    """Task section 6: "If Cursor A does not exist/has not been placed,
    disable or reject Set as t=0 clearly -- never silently use an
    arbitrary time." -- both the guard clause inside the action itself
    AND the toolbar button's own disabled state must enforce this."""
    source = _source()
    set_idx = source.index("async function wwSetT0FromCursorA()")
    set_body = source[set_idx : source.index("async function wwClearT0()", set_idx)]
    assert "if (!cursors.enabled || !cursors.a.visible || !Number.isFinite(cursors.a.time)) return;" in set_body

    sync_idx = source.index("function wwSyncT0Controls()")
    sync_body = source[sync_idx : source.index("async function wwSetT0FromCursorA()", sync_idx)]
    assert "btn.disabled = !hasT0 && !cursorAReady;" in sync_body


def test_apply_t0_to_display_never_refetches():
    """Task's own Performance Requirement: applying t0 is presentation-
    only -- reprojects each channel's existing time array through
    wwElapsedToPlotlyX(), never a new network request.

    Time Group Canvas: the ruler and digital chart are now genuinely
    per-group, so this resyncs EVERY active group's own ruler/digital
    chart (wwSyncAllTimeGroupRulers()/wwRebuildAllTimeGroupDigitalCharts())
    rather than a single workspace-wide one."""
    source = _source()
    fn_idx = source.index("function wwApplyT0ToDisplay()")
    fn_body = source[fn_idx : source.index("function wwSyncT0Controls()", fn_idx)]
    assert "fetch(" not in fn_body
    assert ".map(wwElapsedToPlotlyX)" in fn_body
    assert "wwSyncAllTimeGroupRulers();" in fn_body
    assert "wwRebuildAllTimeGroupDigitalCharts();" in fn_body


def test_toolbar_and_status_bar_ui_exist():
    source = _source()
    assert 'id="wwSetT0Btn"' in source
    assert 'id="statusBarT0"' in source
    assert 'id="statusBarT0Value"' in source
    # Never a silent default-on state -- disabled/hidden until something
    # valid exists to act on.
    btn_idx = source.index('id="wwSetT0Btn"')
    btn_tag = source[btn_idx : source.index(">", btn_idx)]
    assert "disabled" in btn_tag
    status_idx = source.index('id="statusBarT0"')
    status_tag = source[status_idx : source.index(">", status_idx)]
    assert "hidden" in status_tag


def test_click_handler_wired_and_toggles_between_set_and_clear():
    source = _source()
    fn_idx = source.index("function wwHandleSetOrClearT0Click()")
    fn_body = source[fn_idx : source.index('document.getElementById("wwSetT0Btn").addEventListener', fn_idx)]
    assert "wwClearT0();" in fn_body
    assert "wwSetT0FromCursorA();" in fn_body
    assert 'document.getElementById("wwSetT0Btn").addEventListener("click", wwHandleSetOrClearT0Click);' in source


def test_cursor_overlay_refreshes_t0_controls():
    """Cursor A's own placement/removal must immediately update the
    button's enabled state -- wired from the same function every other
    cursor-driven UI refresh already goes through."""
    source = _source()
    fn_idx = source.index("function wwUpdateCursorOverlay(")
    fn_body = source[fn_idx : fn_idx + 1400]
    assert "wwSyncT0Controls();" in fn_body


def test_event_time_axis_title_and_signed_cursor_formatting():
    source = _source()
    assert 'if (wwHasT0()) return "Event Time (s)";' in source
    assert "function wwFormatSignedCursorDuration(seconds)" in source

    fmt_idx = source.index("function wwFormatCursorPointTime(")
    fmt_body = source[fmt_idx : source.index("\n        }\n", fmt_idx)]
    assert "wwHasT0()" in fmt_body
    assert "wwFormatSignedCursorDuration(wwWorkspaceTimeToEventTime(elapsedSeconds))" in fmt_body


def test_new_workspace_clears_t0_but_plain_clear_workspace_does_not():
    """Task section 15: t0 is workspace-scoped state that must be cleared
    when starting a new workspace, but NOT when a still-selected source's
    own data remains (the "Clear workspace" else-branch, same policy as
    ww.alignmentOffsets)."""
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    reset_branch = source[clear_idx : source.index("            } else {", clear_idx)]
    assert "ww.t0WorkspaceTime = null;" in reset_branch
    assert "wwSyncT0Controls();" in reset_branch

    else_branch_idx = source.index("            } else {", clear_idx)
    else_branch = source[else_branch_idx : source.index("// Phase 2C-C1", else_branch_idx)]
    assert "ww.t0WorkspaceTime" not in else_branch


def test_cursor_values_fetch_uses_workspace_time_cursors_unaffected_by_t0():
    """Backend source-native queries must never receive event time
    directly -- cursors.a.time/cursors.b.time remain workspace time (the
    Slice 1 coordinate), so wwFetchCursorValuesForSource() needed zero
    Slice 2 changes: its existing wwWorkspaceTimeToSourceTime() inverse
    mapping is already correct regardless of t0."""
    source = _source()
    fn_idx = source.index("async function wwFetchCursorValuesForSource(sourceId)")
    fn_body = source[fn_idx : source.index("function wwFetchAllCursorValues()", fn_idx)]
    assert "wwEventTimeToWorkspaceTime" not in fn_body
    assert "wwWorkspaceTimeToSourceTime(sourceId, aTime)" in fn_body
    assert "wwWorkspaceTimeToSourceTime(sourceId, bTime)" in fn_body
