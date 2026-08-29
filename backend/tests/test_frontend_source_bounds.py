"""Static regression checks for Phase 4A-UAT10 source-aware time bounds."""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_frontend_has_distinct_source_workspace_and_viewport_state():
    source = _source()

    assert "sourceBounds: new Map()" in source
    assert "workspaceBounds: null" in source
    assert "recordBounds" not in source


def test_source_bounds_come_from_backend_elapsed_timebase_metadata():
    source = _source()

    assert "function wwSourceBoundsFromTimebase(timebase)" in source
    assert "timebase.elapsed_start_seconds" in source
    assert "timebase.elapsed_end_seconds" in source
    assert "wwRememberSourceBoundsFromChannelsData(data)" in source


def test_source_timing_comes_from_backend_absolute_timebase_metadata():
    source = _source()

    assert "sourceTiming: new Map()" in source
    assert "function wwRememberSourceTimingFromChannelsData(data)" in source
    assert "const recordingStartTime = timebase.start_time || null" in source
    assert "recordingStartMs: wwParseNaiveTimestamp(recordingStartTime)" in source
    assert "timingReference: timebase.timing_reference || null" in source
    assert "wwRememberSourceTimingFromChannelsData(data)" in source


def test_opening_source_establishes_bounds_before_any_channel_fetch():
    source = _source()
    open_idx = source.index("wwRememberSourceBoundsFromChannelsData(data)")
    sync_idx = source.index("wwSyncChannelBrowserDisplayState()", open_idx)
    add_idx = source.find("wwAddSelectedChannels", open_idx, sync_idx)

    assert add_idx == -1


def test_reset_time_view_uses_workspace_bounds_not_waveform_response_bounds():
    source = _source()

    reset_idx = source.index("async function wwResetTimeView()")
    reset_body = source[reset_idx : source.index("// \"Autoscale Y\"", reset_idx)]
    assert "ww.workspaceBounds" in reset_body
    assert "recordBounds" not in reset_body


def test_waveform_fetch_no_longer_establishes_full_bounds_from_response():
    source = _source()

    load_idx = source.index("async function wwLoadChannelRange")
    load_body = source[load_idx : source.index("function wwBuildTrace", load_idx)]
    assert "body.start_time" not in load_body
    assert "body.end_time" not in load_body
    assert "sourceBounds" not in load_body


def test_zoom_pan_clamps_to_workspace_bounds():
    """Time Range slider: wwBroadcastViewportDebounced() was replaced by
    wwBroadcastGroupViewportDebounced() (resolves the panel's own Time
    Group, task section 3/6/8), which shares the actual clamp+debounce
    core (wwDebounceApplyGroupViewport()) with the slider's own drag
    handlers -- clamping is now per-Time-Group
    (wwClampRangeToTimeGroup()), which degenerates to exactly
    wwClampRangeToWorkspace()'s own old per-workspace behavior in the
    common single-Time-Group case."""
    source = _source()

    broadcast_idx = source.index("function wwBroadcastGroupViewportDebounced")
    broadcast_body = source[broadcast_idx : source.index("async function wwApplyAndFetchGroupViewport", broadcast_idx)]
    assert "wwDebounceApplyGroupViewport(groupId, startTime, endTime)" in broadcast_body

    debounce_idx = source.index("function wwDebounceApplyGroupViewport")
    debounce_body = source[debounce_idx : source.index("function wwClampPanWindowToTimeGroup", debounce_idx)]
    assert "wwClampRangeToTimeGroup(groupId, startTime, endTime)" in debounce_body
    assert "wwApplyAndFetchGroupViewport(groupId, clamped.start, clamped.end)" in debounce_body


def test_display_only_clear_preserves_selected_source_bounds():
    source = _source()

    reset_idx = source.index("wwClearWorkspace({ resetSourceBounds: true })")
    listener_idx = source.index('addEventListener("click", wwClearWorkspace)')
    clear_idx = source.index("function wwClearWorkspace(options)")
    clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]

    assert reset_idx < clear_idx
    assert listener_idx > clear_idx
    assert "if (options.resetSourceBounds)" in clear_body
    assert "ww.sourceBounds.clear()" in clear_body
    assert "ww.workspaceBounds = wwDeriveWorkspaceBounds()" in clear_body


def test_start_new_workspace_clears_source_timing_with_source_bounds():
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]

    assert "ww.sourceBounds.clear()" in clear_body
    assert "ww.sourceTiming.clear()" in clear_body
