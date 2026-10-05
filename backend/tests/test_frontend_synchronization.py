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
    """Timestamp-Based Initial Alignment and Time Groups: `alignmentOffsets`
    now holds each source's EFFECTIVE offset, and the single scalar
    `referenceSourceId` was replaced by a `referenceSourceIds` Set --
    multiple independent time groups can each have their own origin/
    reference source at once (task section 9)."""
    source = _source()
    assert "alignmentOffsets: new Map()" in source
    assert "referenceSourceIds: new Set()" in source


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
    """Slice 2 renamed this to wwFetchSynchronizationStateForWorkspace()
    (it now also fetches .../t0 in parallel) -- the offsets/reference-
    source half of its contract is unchanged."""
    source = _source()
    assert "async function wwFetchSynchronizationStateForWorkspace()" in source
    assert "/synchronization/sources" in source
    assert "row.is_reference" in source


def test_analog_waveform_fetch_converts_request_and_shifts_response():
    """Slice 3A (DEC-127): the same conversion, now through the shared
    offset helpers -- request range `workspace - offset`, response
    `native + offset`, with this channel's own alignment offset."""
    source = _source()
    fn_idx = source.index("async function wwFetchChannelRange(channelEntry, startTime, endTime, pointBudget)")
    wrapper = source[fn_idx : source.index("async function wwFetchWaveformRange(request)", fn_idx)]
    assert "const alignmentOffset = wwAlignmentOffsetForDisplaySourceId(channelEntry.sourceId);" in wrapper
    assert "nativeStart: wwViewportTimeToSourceElapsed(startTime, alignmentOffset)," in wrapper
    assert "nativeEnd: wwViewportTimeToSourceElapsed(endTime, alignmentOffset)," in wrapper
    assert "timeOffsetS: alignmentOffset," in wrapper
    core_idx = source.index("async function wwFetchWaveformRange(request)")
    core = source[core_idx : source.index("function wwFriendlyError", core_idx)]
    assert "body.time.map((t) => wwSourceElapsedToViewportTime(t, timeOffsetS))" in core
    to_native = source[source.index("function wwViewportTimeToSourceElapsed(viewportTime, offsetS)"):]
    assert "viewportTime - offsetS" in to_native[:300]
    to_viewport = source[source.index("function wwSourceElapsedToViewportTime(elapsedSeconds, offsetS)"):]
    assert "return elapsedSeconds + offsetS;" in to_viewport[:200]


def test_cursor_values_fetch_converts_request_and_shifts_sample_time_echo():
    source = _source()
    fn_idx = source.index("async function wwFetchCursorValuesForSource(sourceId)")
    fn_body = source[fn_idx : source.index("function wwFetchAllCursorValuesForGroup(groupId)", fn_idx)]
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

    rebuild_idx = source.index("function wwRebuildDigitalChart(groupId)")
    rebuild_body = source[rebuild_idx : source.index("const groupRange = wwTimeGroupVisibleRange(groupId);", rebuild_idx)]
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
    fetch_idx = select_body.index("await wwFetchSynchronizationStateForWorkspace();")
    refresh_idx = select_body.index("await refreshSourceList();")
    assert fetch_idx < refresh_idx


def test_source_removal_refreshes_alignment_offsets():
    source = _source()
    remove_idx = source.index("async function performRemoveSource(sourceId)")
    remove_body = source[remove_idx : source.index("// ----", remove_idx)]
    assert "await wwFetchSynchronizationStateForWorkspace();" in remove_body


def test_start_new_workspace_clears_alignment_offset_state():
    """Timestamp-Based Initial Alignment and Time Groups: "Start New
    Workspace" clears every Time-Group-related cache, not just the
    original two -- manual/timestamp-placement offsets, the per-source
    group lookup, and the group catalogue itself, alongside the
    original effective-offset map and reference-source set."""
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]
    assert "ww.alignmentOffsets.clear()" in clear_body
    assert "ww.manualAlignmentOffsets.clear()" in clear_body
    assert "ww.timestampPlacementOffsets.clear()" in clear_body
    assert "ww.timeGroupBySourceId.clear()" in clear_body
    assert "ww.timeGroups.clear()" in clear_body
    assert "ww.referenceSourceIds.clear()" in clear_body


def test_synchronize_sources_ui_is_removed_but_shared_ms_helpers_survive():
    """Waveform toolbar refinement (owner ticket): the "Synchronize
    Sources" modal (its own entry point, `.ww-tg-sync-btn`, had no other
    caller) was removed outright -- see test_frontend_time_group_sync.py's
    own TestSynchronizeSourcesRemoved for the full removal coverage. The
    ms<->seconds conversion helpers survive (Event Reconstruction's own,
    unrelated per-record correction feature reuses them directly), so
    they are asserted present here, not absent."""
    source = _source()
    assert 'id="wwSyncBtn"' not in source
    assert 'id="wwSyncOverlay"' not in source
    assert "async function wwOpenSyncModal(groupId)" not in source
    assert "function wwCloseSyncModal()" not in source
    assert "function wwSyncMsToOffsetSeconds(ms)" in source
    assert "return ms / 1000;" in source
    assert "function wwSyncOffsetToMsDisplay(offsetSeconds)" in source
    assert "offsetSeconds * 1000" in source


def test_annotation_offset_limitation_is_documented():
    """Task's own Absolute-Time-Display guidance applied to annotations:
    do not silently leave Callout/+Peak/-Peak un-offset-aware -- confirm
    it is at least explicitly documented as a known Slice 1 gap."""
    source = _source()
    callout_idx = source.index("async function wwCreateCalloutFromClick(panel, channel, approximateElapsedSeconds)")
    preceding = source[max(0, callout_idx - 1200) : callout_idx]
    assert "NOT offset-aware" in preceding
