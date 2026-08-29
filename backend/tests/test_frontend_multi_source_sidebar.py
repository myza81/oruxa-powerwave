"""Static regression checks for the multi-source Workspace Sidebar
redesign (owner UAT finding after Waveform Time Synchronization Slice 1:
"the waveform workspace now supports multiple active recordings, but the
left sidebar still visually behaves like a single-record workspace").

Mirrors this codebase's own established frontend test style (pure
string/index checks against frontend/index.html, no jsdom execution --
see test_frontend_source_bounds.py).
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


def test_singular_active_recording_is_removed():
    source = _source()
    assert ">Active Recording<" not in source
    assert 'id="active-recording-heading"' not in source
    assert 'class="active-recording"' not in source
    assert "activeRecordingContent" not in source
    assert "activeRecordingEmpty" not in source
    assert "function renderActiveRecording" not in source


def test_recordings_heading_shows_a_live_source_count():
    source = _source()
    assert '<h2 id="channels-heading">Recordings <span id="wwRecordingsCountBadge" class="count-badge">(0)</span></h2>' in source
    fn_body = _function_body(source, "async function wwRenderWorkspaceRecordings(sources)", "function wwResetWorkspaceRecordingsPanel")
    assert 'badge.textContent = "(" + sources.length + ")"' in fn_body


def test_each_source_gets_its_own_collapsible_hierarchy():
    source = _source()
    fn_body = _function_body(source, "function wwRenderSourceRecordingHtml(sourceSummary, isFirst)", "async function wwRenderWorkspaceRecordings")
    assert 'class="source-recording"' in fn_body
    assert "data-source-id=" in fn_body
    assert "renderAnalogGroup(data.analog_channels, data.source, data.timebase)" in fn_body
    assert "renderDigitalGroup(data.digital_channels, data.source, data.timebase)" in fn_body


def test_sources_are_never_merged_into_one_flat_list():
    """wwRenderWorkspaceRecordings() calls wwRenderSourceRecordingHtml()
    once PER SOURCE (never once with a concatenated channel list), and
    renderAnalogGroup()/renderDigitalGroup() are each called exactly once
    per source's own cached data -- channel ownership is therefore always
    structurally scoped to one source's own <details> subtree."""
    source = _source()
    fn_body = _function_body(source, "async function wwRenderWorkspaceRecordings(sources)", "function wwResetWorkspaceRecordingsPanel")
    assert "sources.map((s, index) => wwRenderSourceRecordingHtml(s, index === 0)).join" in fn_body


def test_channel_rows_carry_their_own_source_identity():
    """Pre-existing, unchanged: every analog/digital row already embeds
    data-source-id -- multi-source safety at the row level predates this
    redesign and is preserved verbatim."""
    source = _source()
    analog_attrs = _function_body(source, "function analogChannelRowAttrs(source, channel, timebase)", "function digitalChannelNameCellHtml")
    assert "data-source-id=" in analog_attrs
    digital_attrs = _function_body(source, "function digitalChannelRowAttrs(source, channel, timebase)", "// ----")
    assert "data-source-id=" in digital_attrs


def test_group_toggle_membership_is_dom_scoped_not_attribute_keyed():
    """Two sources sharing a subgroup name (e.g. both having a "Voltage"
    group) must never cross-toggle -- wwChannelGroupRows() resolves
    membership via button.closest(), not a global data-subgroup lookup."""
    source = _source()
    fn_body = _function_body(source, "function wwChannelGroupRows(button)", "function analogMetaFromRow")
    assert 'button.closest("details.channel-subgroup")' in fn_body


def test_source_summary_metadata_line_uses_already_available_fields():
    source = _source()
    fn_body = _function_body(source, "function wwFormatSourceSummaryLine(source)", "function wwSourceSyncBadgeHtml")
    assert "source.analog_channel_count" in fn_body
    assert "source.digital_channel_count" in fn_body
    assert "wwFormatCompactSamplingRate(source.sampling_rates)" in fn_body
    assert "wwFormatCompactDuration(source.duration_seconds)" in fn_body


def test_sampling_rate_formatting_uses_khz_and_multi_rate_fallback():
    source = _source()
    fn_body = _function_body(source, "function wwFormatCompactSamplingRate(samplingRates)", "function wwFormatCompactDuration")
    assert 'if (samplingRates.length > 1) return "Multi-rate";' in fn_body
    assert '" kHz"' in fn_body
    assert '" Hz"' in fn_body
    # Never confuses this with nominal grid frequency.
    assert "nominal_frequency" not in fn_body


def test_duration_formatting_is_compact_not_fixed_three_decimals():
    source = _source()
    fn_body = _function_body(source, "function wwFormatCompactDuration(seconds)", "function wwFormatSourceSummaryLine")
    assert "toPrecision(3)" in fn_body
    # The pre-existing Recordings-page formatter (fixed 3 decimals) is a
    # separate, untouched function -- this must not have replaced it.
    assert "function formatRecordingDuration(seconds)" in source
    assert "seconds.toFixed(3)" in source


def test_bottom_status_bar_no_longer_shows_single_source_metadata():
    source = _source()
    assert "statusBarStation" not in source
    assert "statusBarSampleRate" not in source
    assert "statusBarDuration" not in source
    assert "statusBarChannelCount" not in source
    assert "function shellUpdateStatusBar(" not in source
    assert "function shellUpdateStatusBarChannelCount(" not in source
    assert "function shellSetStatusBarWaveformFieldsVisible(" not in source
    # Workspace identity is untouched. TG-D2: the former global A/B/Δt
    # cursor readout (#wwCursorReadout) was removed from the status bar
    # entirely -- each Time Group Canvas now carries its own
    # `.ww-tg-cursor-readout` instead (see test_frontend_time_group_cursors.py),
    # so there is no longer a single workspace-wide readout to assert
    # here.
    assert 'id="statusBarWorkspaceId"' in source
    assert 'id="wwCursorReadout"' not in source


def test_analog_defaults_open_digital_defaults_collapsed():
    source = _source()
    analog_group = _function_body(source, "function renderAnalogGroup(channels, source, timebase)", "// Phase 4A: presentation-group labels")
    assert 'return \'<details class="channel-group" open data-group="analog"\'' in analog_group

    digital_group = _function_body(source, "function renderDigitalGroup(channels, source, timebase)", "function renderChannelTable")
    assert 'return \'<details class="channel-group" data-group="digital"\'' in digital_group
    assert '<details class="channel-group" open data-group="digital"' not in digital_group


def test_first_source_defaults_expanded_additional_sources_collapsed():
    source = _source()
    fn_body = _function_body(source, "function wwRenderSourceRecordingHtml(sourceSummary, isFirst)", "async function wwRenderWorkspaceRecordings")
    assert "(isFirst ? ' open' : '')" in fn_body
    assert 'data-default-open="\' + isFirst + \'"' in fn_body


def test_search_spans_every_source_but_preserves_ownership():
    source = _source()
    fn_body = _function_body(source, "function setupChannelSearch(analogChannels, digitalChannels)", "function escapeHtml")
    assert 'document.querySelectorAll("#channelGroups details.source-recording")' in fn_body
    # A source with zero matches collapses out of the way, same as a
    # subgroup with zero matches.
    assert "source.hidden = !hasMatch;" in fn_body
    assert "if (hasMatch) source.open = true;" in fn_body
    # Clearing search restores every level's own default state, source
    # included -- and explicitly un-hides sub-groups/sources a PREVIOUS
    # search may have hidden (never left stale-hidden after clearing).
    assert "for (const sub of subgroups) { sub.hidden = false; sub.open = true; }" in fn_body
    assert 'source.open = source.dataset.defaultOpen === "true";' in fn_body


def test_expand_state_survives_a_structural_rebuild():
    """A source/group/subgroup's own open/closed state must not silently
    reset every time the whole tree is rebuilt (source added/removed,
    another source's data arriving) -- see the capture/restore pair."""
    source = _source()
    assert "function wwCaptureChannelTreeExpandState()" in source
    assert "function wwRestoreChannelTreeExpandState(state)" in source
    fn_body = _function_body(source, "async function wwRenderWorkspaceRecordings(sources)", "function wwResetWorkspaceRecordingsPanel")
    assert "const expandState = wwCaptureChannelTreeExpandState();" in fn_body
    assert "wwRestoreChannelTreeExpandState(expandState);" in fn_body


def test_source_removal_drops_its_cached_channel_data():
    source = _source()
    fn_body = _function_body(source, "async function performRemoveSource(sourceId)", "// ------------------------------------------------------------------\n        // Channel detail")
    assert "ww.sourceChannelsData.delete(sourceId);" in fn_body
    assert "await refreshAllSourceViews();" in fn_body


def test_workspace_reset_clears_source_hierarchy_state():
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    clear_body = source[clear_idx : source.index("// Phase 2C-C1", clear_idx)]
    assert "ww.sourceChannelsData.clear();" in clear_body
    assert "ww.sourceBounds.clear()" in clear_body

    reset_idx = source.index("async function resetToNewWorkspace()")
    reset_body = source[reset_idx : source.index("async function checkApiHealth", reset_idx)]
    assert "wwResetWorkspaceRecordingsPanel();" in reset_body
    assert "focusedSourceId = null;" in reset_body


def test_channel_toggle_and_visibility_sync_are_unchanged_in_mechanism():
    """The hierarchy changed; the underlying selection/visibility
    machinery must not have (task section 16)."""
    source = _source()
    assert "function wwToggleAnalogChannelDisplay(row)" in source
    assert "function wwToggleDigitalChannelDisplay(row)" in source
    assert 'document.querySelectorAll("#channelGroups tr.channel-row--toggle")' in source
    sync_body = _function_body(source, "function wwSyncChannelBrowserDisplayState()", "function wwChannelGroupRows")
    assert "wwIsAnalogChannelVisible(row.dataset.sourceId, row.dataset.channelName)" in sync_body
    assert "wwIsDigitalChannelVisible(row.dataset.sourceId, row.dataset.channelName)" in sync_body


def test_focused_source_id_is_distinct_from_participating_sources():
    """Task section 12: an internally-kept "selected/focused" source is
    acceptable, but must never be conflated with "which sources
    participate in the workspace" -- every source in ww.sourceBounds
    participates, regardless of focusedSourceId."""
    source = _source()
    assert "let focusedSourceId = null;" in source
    assert "let selectedSourceId" not in source
    fn_body = _function_body(source, "function wwParticipatingSourceIds()", "// Slice 1: ww.sourceBounds always holds")
    assert "focusedSourceId" not in fn_body
    assert "return new Set(ww.sourceBounds.keys());" in fn_body


def test_optional_synchronization_badge_reads_but_never_mutates_sync_state():
    source = _source()
    fn_body = _function_body(source, "function wwSourceSyncBadgeHtml(sourceId)", "// Generic <details> open/closed state capture")
    assert "ww.referenceSourceId" in fn_body
    assert "wwAlignmentOffsetForSource(sourceId)" in fn_body
    assert ".set(" not in fn_body
    assert "= sourceId" not in fn_body


def test_sync_badge_refreshes_live_when_an_offset_changes():
    """Found during live verification: an offset change (via the
    Synchronize Sources modal) does not itself rebuild the sidebar tree,
    so without a dedicated patch step the sidebar's own sync badge would
    silently go stale until some unrelated event rebuilt the whole tree.
    wwSyncApplyOffsetChangeSideEffectsForGroup() must call a targeted
    patch, not a full wwRenderWorkspaceRecordings() rebuild (which would
    also reset the engineer's own expand/collapse state and the search
    box)."""
    source = _source()
    assert "function wwRefreshSourceSyncBadges()" in source
    effects_body = _function_body(
        source, "async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)", "function wwRefreshSourceSyncBadges"
    )
    assert "wwRefreshSourceSyncBadges();" in effects_body
    assert "await wwRenderWorkspaceRecordings(" not in effects_body

    badge_fn_body = _function_body(source, "function wwRefreshSourceSyncBadges()", "async function wwSyncPutOffset")
    assert 'document.querySelectorAll("#channelGroups details.source-recording")' in badge_fn_body
    assert "wwSourceSyncBadgeHtml(sourceId)" in badge_fn_body
