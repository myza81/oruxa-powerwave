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
    source = _source()

    broadcast_idx = source.index("function wwBroadcastViewportDebounced")
    broadcast_body = source[broadcast_idx : source.index("async function wwApplyAndFetchViewport", broadcast_idx)]
    assert "wwClampRangeToWorkspace(startTime, endTime)" in broadcast_body
    assert "wwApplyAndFetchViewport(clamped.start, clamped.end)" in broadcast_body
