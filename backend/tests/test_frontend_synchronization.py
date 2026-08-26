"""Static regression checks for Slice 1 of waveform time synchronization's
frontend surface (frontend/index.html). Mirrors
test_frontend_source_bounds.py's own pure string/index-based approach --
no jsdom execution, just confirming the right markers exist in the right
places/order, consistent with this codebase's established frontend test
style.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_alignment_offset_state_exists():
    source = _source()
    assert "alignmentOffsets: new Map()" in source
    assert "referenceSourceId: null" in source


def test_core_conversion_helpers_exist():
    source = _source()
    assert "function wwSourceTimeToWorkspaceTime(displaySourceId, sourceTime)" in source
    assert "return sourceTime + wwAlignmentOffsetForDisplaySourceId(displaySourceId);" in source
    assert "function wwWorkspaceTimeToSourceTime(displaySourceId, workspaceTime)" in source
    assert "return workspaceTime - wwAlignmentOffsetForDisplaySourceId(displaySourceId);" in source


def test_calculated_channels_resolve_offset_through_their_reference_source():
    source = _source()
    fn_idx = source.index("function wwAlignmentOffsetForDisplaySourceId(displaySourceId)")
    fn_body = source[fn_idx : source.index("function wwSourceTimeToWorkspaceTime", fn_idx)]
    assert "wwTimingSourceIdForDisplaySourceId(displaySourceId)" in fn_body


def test_fetch_alignment_offsets_hits_the_synchronization_sources_endpoint():
    source = _source()
    assert "async function wwFetchAlignmentOffsetsForWorkspace()" in source
    assert "/synchronization/sources" in source
    assert "row.is_reference" in source


def test_analog_waveform_fetch_converts_request_and_shifts_response():
    source = _source()
    fn_idx = source.index("async function wwFetchChannelRange(channelEntry, startTime, endTime, pointBudget)")
    fn_body = source[fn_idx : source.index("function wwFriendlyError", fn_idx)]
    assert "wwAlignmentOffsetForDisplaySourceId(channelEntry.sourceId)" in fn_body
    assert "wwWorkspaceTimeToSourceTime(channelEntry.sourceId, startTime)" in fn_body
    assert "wwWorkspaceTimeToSourceTime(channelEntry.sourceId, endTime)" in fn_body
    assert "body.time.map((t) => t + alignmentOffset)" in fn_body


def test_cursor_values_fetch_converts_request_and_shifts_sample_time_echo():
    source = _source()
    fn_idx = source.index("async function wwFetchCursorValuesForSource(sourceId)")
    fn_body = source[fn_idx : source.index("// Section 32 (Phase 4C1)/17 (Phase 4C2)", fn_idx)]
    assert "wwWorkspaceTimeToSourceTime(sourceId, aTime)" in fn_body
    assert "wwWorkspaceTimeToSourceTime(sourceId, bTime)" in fn_body
    assert "cursor_a_time: nativeATime" in fn_body
    assert "cursor_b_time: nativeBTime" in fn_body
    assert "aSampleTimeNative + alignmentOffset" in fn_body
    assert "bSampleTimeNative + alignmentOffset" in fn_body


def test_workspace_bounds_derivation_applies_offset():
    source = _source()
    fn_idx = source.index("function wwDeriveWorkspaceBounds()")
    fn_body = source[fn_idx : source.index("function wwClampRangeToWorkspace", fn_idx)]
    assert "wwAlignmentOffsetForSource(sourceId)" in fn_body
    assert "bounds.start + offset" in fn_body
    assert "bounds.end + offset" in fn_body


def test_digital_channels_apply_offset_at_render_time_not_fetch_time():
    source = _source()
    # wwAddDigitalChannels must NOT bake an offset into stored transitions/
    # start/end -- see that decision's own comment for why (staleness
    # avoidance: an offset change would otherwise require a full re-fetch).
    add_idx = source.index("async function wwAddDigitalChannels(channelMetas, options)")
    add_body = source[add_idx : source.index("function wwRemoveDigitalChannelByKey", add_idx)]
    assert "wwAlignmentOffsetForSource" not in add_body

    intervals_idx = source.index("function wwDigitalHighIntervals(entry)")
    intervals_body = source[intervals_idx : source.index("// ONE Plotly figure, two traces", intervals_idx)]
    assert "wwAlignmentOffsetForSource(entry.sourceId)" in intervals_body

    rebuild_idx = source.index("function wwRebuildDigitalChart()")
    rebuild_body = source[rebuild_idx : source.index("const xrange = ww.viewport", rebuild_idx)]
    assert "entryOffset" in rebuild_body
    assert "entry.startTime + entryOffset" in rebuild_body
    assert "entry.endTime + entryOffset" in rebuild_body


def test_select_source_refreshes_offsets_before_deriving_workspace_bounds():
    """Multi-source sidebar redesign: selectSource() no longer fetches
    /channels or calls wwRememberSourceBoundsFromChannelsData() directly
    -- that now happens inside wwEnsureSourceChannelsFetched(), invoked
    (for every uploaded source) via refreshSourceList() ->
    wwRenderWorkspaceRecordings(). The ordering guarantee this test
    protects still holds: alignment offsets must be fetched before that
    bounds-establishing call chain runs, so a newly-opened/re-opened
    source's shifted extent and sync badge are correct on first render."""
    source = _source()
    select_idx = source.index("async function selectSource(sourceId)")
    select_body = source[select_idx : source.index("wwSyncChannelBrowserDisplayState();", select_idx)]
    fetch_idx = select_body.index("await wwFetchAlignmentOffsetsForWorkspace();")
    refresh_idx = select_body.index("await refreshSourceList();")
    assert fetch_idx < refresh_idx


def test_source_removal_refreshes_alignment_offsets():
    source = _source()
    remove_idx = source.index("async function performRemoveSource(sourceId)")
    remove_body = source[remove_idx : source.index("// ----", remove_idx)]
    assert "await wwFetchAlignmentOffsetsForWorkspace();" in remove_body


def test_start_new_workspace_clears_alignment_offset_state():
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]
    assert "ww.alignmentOffsets.clear()" in clear_body
    assert "ww.referenceSourceId = null" in clear_body


def test_manual_alignment_ui_exists():
    source = _source()
    assert 'id="wwSyncBtn"' in source
    assert 'id="wwSyncOverlay"' in source
    assert 'id="wwSyncResetAllBtn"' in source
    assert "function wwOpenSyncModal()" in source
    assert "function wwCloseSyncModal()" in source


def test_set_offset_hits_put_and_reset_hits_delete():
    source = _source()
    put_idx = source.index("async function wwSyncPutOffset(sourceId, offsetSeconds)")
    put_body = source[put_idx : source.index("async function wwSyncSetOffsetMs", put_idx)]
    assert 'method: "PUT"' in put_body
    assert "/synchronization/sources/" in put_body

    reset_idx = source.index("async function wwSyncResetOffset(sourceId)")
    reset_body = source[reset_idx : source.index("async function wwSyncResetAll", reset_idx)]
    assert 'method: "DELETE"' in reset_body

    reset_all_idx = source.index("async function wwSyncResetAll()")
    reset_all_body = source[reset_all_idx : source.index("// ---- Edit drawer", reset_all_idx)]
    assert 'method: "DELETE"' in reset_all_body
    assert '"/synchronization/sources"' in reset_all_body or '/synchronization/sources"' in reset_all_body


def test_ui_stores_seconds_not_milliseconds():
    """Task's own Precision Requirement: UI may DISPLAY milliseconds, but
    the stored/transmitted value must remain seconds."""
    source = _source()
    assert "function wwSyncMsToOffsetSeconds(ms)" in source
    assert "return ms / 1000;" in source
    assert "function wwSyncOffsetToMsDisplay(offsetSeconds)" in source
    assert "offsetSeconds * 1000" in source


def test_offset_change_side_effects_reuse_existing_refetch_orchestrator():
    """Task's own Performance Requirement: never a fragile, separate
    frontend-only offset-application path -- reuse the SAME
    wwRefetchAllChannels()/wwRebuildDigitalChart() call sites zoom/pan/
    unit-mode-switch already funnel through."""
    source = _source()
    fn_idx = source.index("async function wwSyncApplyOffsetChangeSideEffects()")
    fn_body = source[fn_idx : source.index("async function wwSyncPutOffset", fn_idx)]
    assert "wwRefreshWorkspaceBounds(" in fn_body
    assert "wwRefetchAllChannels(vp.start, vp.end)" in fn_body
    assert "wwRebuildDigitalChart()" in fn_body


def test_annotation_offset_limitation_is_documented():
    """Task's own Absolute-Time-Display guidance applied to annotations:
    do not silently leave Callout/+Peak/-Peak un-offset-aware -- confirm
    it is at least explicitly documented as a known Slice 1 gap."""
    source = _source()
    callout_idx = source.index("async function wwCreateCalloutFromClick(panel, channel, approximateElapsedSeconds)")
    preceding = source[max(0, callout_idx - 1200) : callout_idx]
    assert "NOT offset-aware" in preceding
