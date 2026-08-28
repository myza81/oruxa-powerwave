"""Static regression checks for "Timestamp-Based Initial Alignment and Time
Groups"'s frontend surface (frontend/index.html). Mirrors
test_frontend_synchronization.py/test_frontend_synchronization_t0.py/
test_frontend_detect_event.py's own pure string/index-based approach -- no
jsdom execution, just confirming the right markers exist in the right
places/order.

Backend-level Time-Group derivation/composition is already fully covered by
test_time_grouping_domain.py/test_time_grouping_service.py/
test_time_groups_api.py -- this file only exercises the frontend's own
consumption of that state: per-group state caches, group-aware panel
splitting, group-scoped t0 quick actions, and the manual/timestamp-placement
split in the Synchronize Sources modal.
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


def test_time_group_state_exists():
    source = _source()
    assert "manualAlignmentOffsets: new Map()" in source
    assert "timestampPlacementOffsets: new Map()" in source
    assert "timeGroupBySourceId: new Map()" in source
    assert "timeGroups: new Map()" in source
    assert "referenceSourceIds: new Set()" in source


def test_timestamp_placement_offset_helper_exists():
    source = _source()
    fn_idx = source.index("function wwTimestampPlacementOffsetForSource(sourceId)")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    assert "ww.timestampPlacementOffsets.get(sourceId)" in fn_body


def test_time_group_id_lookup_reuses_the_same_grounding_source_resolution():
    """Task section 34: source timing (and therefore time-group
    membership) is a source-level property, never resolved per channel --
    verified by confirming the lookup reuses the SAME
    wwTimingSourceIdForDisplaySourceId() resolution
    wwAlignmentOffsetForDisplaySourceId() already uses, never a second,
    independent "which source owns this" rule."""
    source = _source()
    fn_idx = source.index("function wwTimeGroupIdForDisplaySourceId(displaySourceId)")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    assert "wwTimingSourceIdForDisplaySourceId(displaySourceId)" in fn_body
    assert "ww.timeGroupBySourceId.get(sourceId)" in fn_body


class TestPanelLabelsStayCurrentAsGroupTopologyChanges:
    """Live-UAT-discovered gap, fixed in this same change: wwPanelLabelFor()
    is normally only ever called once, at the moment a panel is first
    created -- so an already-rendered panel's own "Time Group N" suffix
    could go stale (keep showing no suffix, or the wrong number) if a
    LATER upload/removal changes the workspace's own group topology.
    wwRefreshTimeGroupPanelLabels() re-derives every existing panel's own
    label from its first channel and patches the DOM text in place,
    called once every time fresh sync/time-group state loads."""

    def test_refresh_function_recomputes_every_panels_label_from_its_first_channel(self):
        source = _source()
        fn_idx = source.index("function wwRefreshTimeGroupPanelLabels()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPanelLabelFor(panel.channels[0])" in fn_body
        assert "panel.label = freshLabel;" in fn_body
        assert 'panel.headerEl && panel.headerEl.querySelector(".ww-panel-label")' in fn_body

    def test_fetch_synchronization_state_calls_the_refresh_after_group_state_loads(self):
        source = _source()
        fn_idx = source.index("async function wwFetchSynchronizationStateForWorkspace()")
        fn_body = source[fn_idx : source.index("function wwRefreshTimeGroupPanelLabels()", fn_idx)]
        assert "wwRefreshTimeGroupPanelLabels();" in fn_body


def test_fetch_synchronization_state_populates_time_group_caches():
    source = _source()
    fn_idx = source.index("async function wwFetchSynchronizationStateForWorkspace()")
    fn_body = source[fn_idx : source.index("function wwParticipatingSourceIds()", fn_idx)]
    assert "/synchronization/time-groups" in fn_body
    assert "ww.timeGroupBySourceId.set(row.source_id, row.time_group_id);" in fn_body
    assert "ww.timeGroups.set(group.group_id" in fn_body
    assert "wwPrimaryTimeGroupSourceId()" in fn_body


def test_primary_time_group_source_id_is_the_first_alignment_offsets_key():
    """Documented, deliberately narrow scope decision: the shared toolbar
    quick action has no explicit source context of its own, so it targets
    one deterministic "primary" source rather than attempting to divine
    which of possibly-several time groups the engineer means."""
    source = _source()
    fn_idx = source.index("function wwPrimaryTimeGroupSourceId()")
    fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
    assert "ww.alignmentOffsets.keys()" in fn_body
    assert "return null;" in fn_body


class TestPanelSplittingByTimeGroup:
    """Task section 27/28/1: "one waveform panel = one coherent time
    domain" -- two channels of the same engineering type from different
    time groups must never land in the same Grouped-mode panel."""

    def test_panel_group_key_is_prefixed_with_the_channels_own_time_group(self):
        source = _source()
        fn_idx = source.index("function wwPanelGroupKeyFor(channel)")
        fn_body = source[fn_idx : source.index("function wwTimeGroupLabelSuffix", fn_idx)]
        assert "wwTimeGroupIdForDisplaySourceId(channel.sourceId)" in fn_body
        assert 'baseKey = timeGroupId + "::" + baseKey;' in fn_body

    def test_separate_and_custom_layout_modes_are_untouched(self):
        """Separate mode already gives every channel its own panel;
        Custom is the engineer's own explicit, deliberate grouping choice
        -- neither should be prefixed by time-group id."""
        source = _source()
        fn_idx = source.index("function wwPanelGroupKeyFor(channel)")
        fn_body = source[fn_idx : source.index("function wwTimeGroupLabelSuffix", fn_idx)]
        separate_idx = fn_body.index('if (ww.layoutMode === "separate")')
        custom_idx = fn_body.index('if (ww.layoutMode === "custom")')
        prefix_idx = fn_body.index("timeGroupId + ")
        assert separate_idx < custom_idx < prefix_idx


class TestTimeGroupPanelLabeling:
    """Task section 29: a compact per-panel timing label, but ONLY once a
    genuinely multi-group workspace exists -- the single-group common case
    must render identically to before this feature existed."""

    def test_label_suffix_is_empty_for_a_single_group_workspace(self):
        source = _source()
        fn_idx = source.index("function wwTimeGroupLabelSuffix(channel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (ww.timeGroups.size <= 1) return" in fn_body

    def test_elapsed_only_group_gets_a_fixed_label_never_a_fabricated_absolute_one(self):
        source = _source()
        fn_idx = source.index("function wwTimeGroupLabelSuffix(channel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert '"elapsed_only"' in fn_body
        assert "Elapsed / unaligned" in fn_body

    def test_panel_label_appends_the_time_group_suffix(self):
        source = _source()
        fn_idx = source.index("function wwPanelLabelFor(channel)")
        fn_body = source[fn_idx : source.index("function ", fn_idx + 20)]
        assert "wwTimeGroupLabelSuffix(channel)" in fn_body


class TestSyncModalManualVsTimestampPlacementSplit:
    """Task section 20/25: manual sync must keep working exactly as
    before for the common single-group case, but the modal must now show
    the derived timestamp placement as read-only provenance context, never
    let it be edited directly, and compose the two only at read time."""

    def test_row_renderer_takes_both_manual_and_timestamp_placement_separately(self):
        source = _source()
        assert (
            "function wwRenderSyncSourceRow(source, manualOffsetSeconds, timestampPlacementSeconds, isReference)"
            in source
        )

    def test_editable_field_binds_to_manual_offset_only(self):
        source = _source()
        fn_idx = source.index(
            "function wwRenderSyncSourceRow(source, manualOffsetSeconds, timestampPlacementSeconds, isReference)"
        )
        fn_body = source[fn_idx : source.index("function wwRenderSyncBody", fn_idx)]
        assert "wwSyncOffsetToMsDisplay(manualOffsetSeconds)" in fn_body
        assert "wwSyncOffsetToMsDisplay(timestampPlacementSeconds)" in fn_body
        # The read-only placement note is gated on a non-zero value --
        # never shown (clutter) for the common zero-offset case.
        assert "timestampPlacementSeconds !== 0" in fn_body

    def test_render_body_supplies_manual_and_timestamp_placement_from_their_own_maps(self):
        source = _source()
        fn_idx = source.index("function wwRenderSyncBody(sources)")
        fn_body = source[fn_idx : source.index("async function wwOpenSyncModal()", fn_idx)]
        assert "ww.manualAlignmentOffsets.get(source.source_id) || 0" in fn_body
        assert "wwTimestampPlacementOffsetForSource(source.source_id)" in fn_body
        assert "ww.referenceSourceIds.has(source.source_id)" in fn_body

    def test_step_offset_baseline_reads_manual_offset_only(self):
        """Stepping (+/-1ms etc.) must adjust the MANUAL correction only
        -- never silently also shift the derived timestamp placement."""
        source = _source()
        fn_idx = source.index("async function wwSyncStepOffset(sourceId, stepMs)")
        fn_body = source[fn_idx : fn_idx + 800]
        assert "ww.manualAlignmentOffsets.get(sourceId)" in fn_body


class TestResetSemanticsAreManualOnly:
    """Task section 21: "Reset source" / "Reset All" must return a source
    to its TIMESTAMP-DERIVED position, never to absolute zero -- verified
    via the relabeled buttons/tooltips that make this explicit."""

    def test_reset_button_label_and_tooltip_clarify_manual_only_scope(self):
        source = _source()
        assert "Reset manual adjustment" in source
        assert "the manual correction only" in source

    def test_reset_all_button_label_and_tooltip_clarify_manual_only_scope(self):
        source = _source()
        assert "Reset All Manual Adjustments" in source
        assert "every source's own manual correction only" in source


class TestT0GroupScopedQuickActions:
    """Task section 24/26: setting/clearing t0 via the shared toolbar
    resolves the primary time group's own origin source; Detect Event's
    Accept always uses the explicitly-selected source's own group."""

    def test_set_t0_from_cursor_a_resolves_the_primary_group_source(self):
        source = _source()
        fn_idx = source.index("async function wwSetT0FromCursorA()")
        fn_body = source[fn_idx : source.index("async function wwClearT0()", fn_idx)]
        assert "const sourceId = wwPrimaryTimeGroupSourceId();" in fn_body
        assert "if (sourceId === null) return;" in fn_body
        assert "source_id: sourceId" in fn_body

    def test_clear_t0_resolves_the_primary_group_source_as_a_query_param(self):
        source = _source()
        fn_idx = source.index("async function wwClearT0()")
        fn_body = source[fn_idx : source.index("function wwHandleSetOrClearT0Click()", fn_idx)]
        assert "const sourceId = wwPrimaryTimeGroupSourceId();" in fn_body
        assert "if (sourceId === null) return;" in fn_body
        assert '"?source_id=" + encodeURIComponent(sourceId)' in fn_body

    def test_accept_detected_event_uses_the_explicitly_selected_source(self):
        source = _source()
        fn_idx = source.index("async function wwAcceptDetectedEvent()")
        fn_body = source[fn_idx : source.index("function wwUpdateEditGroupsButtonVisibility()", fn_idx)]
        assert "const sourceId = ww.suggestedEvent.sourceId;" in fn_body
        assert "source_id: sourceId" in fn_body


class TestDetectEventGroupScopedT0Lookup:
    """Task section 26: the Analyse handler resolves a fresh, group-scoped
    t0 read for the SELECTED source right after a candidate is found, so
    the Accept button's own label reflects that group -- not the shared
    toolbar's primary-group cache, which could be a different group
    entirely in a multi-group workspace."""

    def test_analyse_handler_fetches_t0_scoped_to_the_selected_source(self):
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert "/synchronization/t0" in fn_body
        assert "groupHasT0" in fn_body

    def test_suggested_event_state_carries_group_has_t0(self):
        source = _source()
        idx = source.index("suggestedEvent: {")
        body = source[idx : source.index("};", idx)]
        assert "groupHasT0: false" in body

    def test_reset_suggestion_clears_group_has_t0(self):
        source = _source()
        fn_idx = source.index("function wwResetDetectEventSuggestion()")
        fn_body = source[fn_idx : source.index("function wwOpenDetectEventModal()", fn_idx)]
        assert "groupHasT0: false" in fn_body
