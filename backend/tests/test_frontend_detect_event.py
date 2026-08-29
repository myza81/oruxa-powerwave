"""Static regression checks for Slice 3 of waveform time synchronization's
frontend surface (frontend/index.html): assisted event t=0 detection.
Mirrors test_frontend_synchronization_t0.py's own pure string/index-based
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


def test_suggested_event_state_exists():
    source = _source()
    idx = source.index("suggestedEvent: {")
    body = source[idx : source.index("};", idx)]
    assert "visible: false" in body
    assert "workspaceTime: null" in body


def test_toolbar_and_modal_ui_exist():
    source = _source()
    assert 'id="wwDetectEventBtn"' in source
    assert 'id="wwDetectEventOverlay"' in source
    assert 'id="wwDetectEventSourceSelect"' in source
    assert 'id="wwDetectEventChannelSelect"' in source
    assert 'id="wwDetectEventSensitivitySelect"' in source
    assert 'id="wwDetectEventAnalyseBtn"' in source
    assert 'id="wwDetectEventResult"' in source
    assert 'id="wwDetectEventAcceptBtn"' in source
    assert 'id="wwDetectEventCancelBtn"' in source
    assert 'id="wwDetectEventReplaceHint"' in source


def test_no_separate_replace_confirmation_panel_exists():
    """UAT fix: the old two-step "click Set as t=0, THEN see a second
    panel with its own Replace t=0/Cancel" flow is gone entirely -- one
    footer, one Cancel, one accept action, full stop."""
    source = _source()
    assert "wwDetectEventReplaceConfirm" not in source
    assert 'id="wwDetectEventReplaceConfirmBtn"' not in source
    assert 'id="wwDetectEventReplaceCancelBtn"' not in source
    assert "wwHandleDetectEventAcceptClick" not in source
    assert "wwHandleDetectEventReplaceCancelClick" not in source


def test_modal_has_exactly_one_footer_and_one_cancel_button():
    """UAT fix: "The modal should also have only one visible Cancel
    action" -- verified structurally: exactly one .group-editor-footer
    and exactly one id="wwDetectEvent...CancelBtn"-shaped element in
    the whole modal block."""
    source = _source()
    modal_idx = source.index('id="wwDetectEventOverlay"')
    modal_body = source[modal_idx : source.index("<!-- Slice 6:", modal_idx)]
    assert modal_body.count("group-editor-footer") == 1
    assert modal_body.count("Cancel</button>") == 1
    assert modal_body.count('id="wwDetectEventAcceptBtn"') == 1


def test_accept_button_starts_disabled_with_no_candidate():
    source = _source()
    idx = source.index('id="wwDetectEventAcceptBtn"')
    tag = source[idx : source.index(">", idx)]
    assert "disabled" in tag


def test_sensitivity_select_offers_exactly_three_plain_tiers():
    """Task section 8: three tiers, never raw tunable parameters (sigma/
    window_samples/derivative_threshold) exposed in the UI."""
    source = _source()
    idx = source.index('id="wwDetectEventSensitivitySelect"')
    body = source[idx : source.index("</select>", idx)]
    assert 'value="conservative"' in body
    assert 'value="normal" selected' in body
    assert 'value="sensitive"' in body
    assert "sigma" not in body.lower()
    assert "window_samples" not in body.lower()


def test_source_channel_candidates_are_real_analog_channels_only():
    """Task section 5/30: explicit source+channel selection, real
    source analog channels only -- never calculated channels, never an
    automatic best-channel choice."""
    source = _source()
    fn_idx = source.index("function wwDetectEventSourceOptionsHtml(groupId)")
    fn_body = source[fn_idx : source.index("function wwDetectEventChannelOptionsHtml", fn_idx)]
    assert "ww.sourceChannelInventory" in fn_body
    assert "calculatedChannels" not in fn_body


def test_analyse_posts_to_detect_event_endpoint():
    source = _source()
    fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
    fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
    assert '"/synchronization/detect-event"' in fn_body
    assert 'method: "POST"' in fn_body
    assert "source_id: sourceId" in fn_body
    assert "channel_name: channelName" in fn_body
    assert "sensitivity: sensitivity" in fn_body


def test_analyse_never_puts_or_deletes_the_t0_endpoint():
    """Task section 26: "Do not make this endpoint set t0
    automatically." -- verified on the frontend side too: the Analyse
    handler must never itself PUT/DELETE/GET .../t0 at all.

    TG-E: the group-scoped "does this group already have a t0" check
    (groupHasT0, used to label the Accept button "Set as t=0" vs
    "Replace t=0") is now a direct read of ww.timeGroupT0State
    (wwHasT0(groupId)) -- the cache TG-E's own
    wwFetchSynchronizationStateForWorkspace() already keeps fresh per
    group -- rather than a separate network round trip the OLD
    single-scalar-era code needed. No fetch of any kind to
    .../synchronization/t0 happens in this handler at all now."""
    source = _source()
    fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
    fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
    assert "/synchronization/t0" not in fn_body
    assert "const groupHasT0 = wwHasT0(groupId);" in fn_body
    assert 'method: "PUT"' not in fn_body
    assert 'method: "DELETE"' not in fn_body


def test_preview_marker_is_shown_before_acceptance_is_possible():
    """Task section 13: the suggested point must be visible on the
    waveform BEFORE acceptance -- the marker is set (ww.suggestedEvent,
    then wwUpdateAllCursorOverlays(), TG-D2's per-group-aware sweep)
    unconditionally on a found result, strictly before
    wwRenderDetectEventResult() ever enables the Accept button."""
    source = _source()
    fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
    fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
    marker_idx = fn_body.index("ww.suggestedEvent = {")
    overlay_idx = fn_body.index("wwUpdateAllCursorOverlays();", marker_idx)
    render_idx = fn_body.index("wwRenderDetectEventResult(", overlay_idx)
    assert marker_idx < overlay_idx < render_idx


def test_accept_reuses_the_existing_t0_put_endpoint_only():
    """Task section 14/25: "reuse the existing t0 service... do not
    create a second t0 implementation." -- verified structurally:
    acceptance calls the SAME PUT .../synchronization/t0 Slice 2 already
    established, then the SAME three follow-up calls
    wwSetT0FromCursorAForGroup() itself makes on success -- but resolved
    to the CANDIDATE's own owning group (never the primary group), so
    "candidate from Group 2 -> set Group 2 t0" only. This is the ONE
    accept path for both "Set as t=0" and "Replace t=0" -- there is no
    separate replace-specific implementation (UAT fix: both button
    states click straight into this same function)."""
    source = _source()
    fn_idx = source.index("async function wwAcceptDetectedEvent()")
    fn_body = source[fn_idx : source.index("function wwUpdateEditGroupsButtonVisibility()", fn_idx)]
    assert '"/synchronization/t0"' in fn_body
    assert 'method: "PUT"' in fn_body
    assert "t0_workspace_time: workspaceTime" in fn_body
    assert "const groupId = wwTimeGroupIdForDisplaySourceId(sourceId);" in fn_body
    assert "ww.timeGroupT0State.set(groupId, body.t0_workspace_time);" in fn_body
    assert "wwSyncT0ControlsForGroup(groupId);" in fn_body
    assert "wwApplyT0ToDisplayForGroup(groupId);" in fn_body


def test_accept_button_wired_directly_to_the_single_accept_function():
    """UAT fix: no intermediate click-reveals-a-second-panel step --
    clicking the (state-appropriately-labeled) accept button calls
    wwAcceptDetectedEvent() directly."""
    source = _source()
    idx = source.index('document.getElementById("wwDetectEventAcceptBtn").addEventListener')
    line = source[idx : source.index("\n", idx)]
    assert '"click", wwAcceptDetectedEvent' in line


class TestAcceptButtonStateDependsOnlyOnT0:
    """Task's own governing UX principle: exactly one primary
    acceptance action, state-appropriate, never both at once."""

    def test_sync_function_labels_replace_when_t0_exists_and_set_otherwise(self):
        """TG-E: once a candidate exists, the label must reflect THAT
        candidate's own source's time group -- never an unrelated
        group's t0 -- via ww.suggestedEvent.groupHasT0. Before any
        analysis has run yet (no source selected), it falls back to the
        CURRENTLY-SELECTED source's own group (the dropdown is already
        filtered to the launching group -- never a shared/primary-group
        default)."""
        source = _source()
        fn_idx = source.index("function wwSyncDetectEventAcceptButtonState()")
        fn_body = source[fn_idx : source.index("function wwInvalidateDetectEventSuggestion()", fn_idx)]
        assert 'acceptBtn.textContent = hasT0 ? "Replace t=0" : "Set as t=0";' in fn_body
        assert "hasT0 = ww.suggestedEvent.groupHasT0;" in fn_body
        assert "hasT0 = selectedGroupId !== null && wwHasT0(selectedGroupId);" in fn_body

    def test_hint_only_shown_when_t0_exists_and_a_candidate_is_active(self):
        """The "already defined" context text is gated on BOTH t0
        existing AND there being something to accept -- never dangling
        above a disabled button."""
        source = _source()
        fn_idx = source.index("function wwSyncDetectEventAcceptButtonState()")
        fn_body = source[fn_idx : source.index("function wwInvalidateDetectEventSuggestion()", fn_idx)]
        assert "hintEl.hidden = !(hasT0 && !acceptBtn.disabled);" in fn_body

    def test_render_result_resyncs_button_state_for_both_found_and_not_found(self):
        source = _source()
        fn_idx = source.index("function wwRenderDetectEventResult(view, channelUnit, searchRangeInfo)")
        fn_body = source[fn_idx : source.index("function wwResetDetectEventSuggestion()", fn_idx)]
        # Appears once in the found=false early-return branch, once at
        # the end of the found=true branch -- both paths re-sync.
        assert fn_body.count("wwSyncDetectEventAcceptButtonState();") == 2

    def test_open_modal_syncs_button_state_fresh(self):
        """Reopening the modal (or opening it for the first time) must
        immediately reflect whatever t0 state the workspace is
        CURRENTLY in -- never a stale label left over from a previous
        session's Accept."""
        source = _source()
        fn_idx = source.index("function wwOpenDetectEventModal(groupId)")
        fn_body = source[fn_idx : source.index("function wwCloseDetectEventModal()", fn_idx)]
        assert "wwSyncDetectEventAcceptButtonState();" in fn_body
        assert "document.getElementById(\"wwDetectEventAcceptBtn\").disabled = true;" in fn_body


class TestStaleSuggestionInvalidatedOnSelectionChange:
    """Task's own edge case: "source/channel changed after a candidate
    was generated" must never leave a stale candidate's Accept button
    enabled for a selection that was never actually analysed."""

    def test_invalidate_function_disables_accept_and_clears_marker(self):
        source = _source()
        fn_idx = source.index("function wwInvalidateDetectEventSuggestion()")
        fn_body = source[fn_idx : source.index("function wwRenderDetectEventResult(", fn_idx)]
        assert 'document.getElementById("wwDetectEventAcceptBtn").disabled = true;' in fn_body
        assert "wwResetDetectEventSuggestion();" in fn_body
        assert "wwSyncDetectEventAcceptButtonState();" in fn_body

    def test_source_channel_and_sensitivity_changes_all_invalidate(self):
        source = _source()
        idx = source.index('// Slice 3 of waveform time synchronization: "Detect Event Origin".')
        block = source[idx : source.index("// Phase 2C-B1/C1", idx)]
        # source, channel, sensitivity, AND (UAT correction) the two
        # Detection range radios -- 4 distinct wiring call sites total.
        assert block.count("wwInvalidateDetectEventSuggestion") == 4


def test_cancel_and_close_never_touch_t0_or_offsets():
    """Task section 15: rejection removes only the temporary suggestion
    -- t0 and every source's own alignment offset are untouched."""
    source = _source()
    fn_idx = source.index("function wwCloseDetectEventModal()")
    fn_body = source[fn_idx : source.index("function wwDetectEventShowError(", fn_idx)]
    assert "ww.t0WorkspaceTime" not in fn_body
    assert "alignmentOffsets" not in fn_body
    assert "wwResetDetectEventSuggestion();" in fn_body


def test_reset_suggestion_clears_marker_and_refreshes_overlay():
    source = _source()
    fn_idx = source.index("function wwResetDetectEventSuggestion()")
    fn_body = source[fn_idx : source.index("function wwOpenDetectEventModal(groupId)", fn_idx)]
    assert "visible: false" in fn_body
    assert "workspaceTime: null" in fn_body
    # TG-D2: a full per-group sweep (the suggestion may have been
    # showing in any one Time Group's own overlay, or none).
    assert "wwUpdateAllCursorOverlays();" in fn_body


def test_cursor_overlay_draws_the_suggestion_marker_independent_of_cursor_mode():
    """Task section 13: the marker must be able to show even when A/B
    cursor mode itself is off -- the overlay's own drawing gate must
    admit EITHER cursor-mode-active OR a visible suggestion, not only
    the former."""
    source = _source()
    fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
    body = source[fn_idx : fn_idx + 10000]
    assert "suggestionVisible" in body
    assert "const drawAnything = active || suggestionVisible;" in body
    assert 'data-cursor-line="suggested"' in body


def test_workspace_time_never_inferred_from_plotly_labels():
    """Task section 18: use the centralized mapping helpers; the
    suggestion marker's own pixel projection must go through the SAME
    wwCursorTimeToPixelX() authority every other cursor already uses,
    never a second X-projection."""
    source = _source()
    fn_idx = source.index("function wwUpdateCursorOverlayForGroup(groupId)")
    body = source[fn_idx : fn_idx + 12000]
    # Anchored on this block's own unique comment, not the bare
    # `data-cursor-line="suggested"` selector -- that selector also
    # appears earlier, in the early-return branch's own defensive
    # hidden-state reset (see that branch's own comment).
    suggested_block_idx = body.index('Slice 3: the "Suggested event" preview marker -- SAME')
    suggested_block = body[suggested_block_idx : suggested_block_idx + 1200]
    # TG-D2: the group-scoped helper's signature now requires an
    # explicit groupId -- never a hidden/defaulted primary-group
    # fallback (task section 9).
    assert "wwCursorTimeToPixelX(groupId, suggestion.workspaceTime)" in suggested_block


def test_new_workspace_clears_suggestion_but_plain_clear_workspace_does_not():
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    reset_branch = source[clear_idx : source.index("            } else {", clear_idx)]
    assert "wwCloseDetectEventModal();" in reset_branch

    else_branch_idx = source.index("            } else {", clear_idx)
    else_branch = source[else_branch_idx : source.index("// Phase 2C-C1", else_branch_idx)]
    assert "wwCloseDetectEventModal" not in else_branch
    assert "wwResetDetectEventSuggestion" not in else_branch


# ==============================================================================
# UAT correction: viewport-bounded ("Current visible range") detection,
# with "Full recording" retained as an explicit secondary option.
# ==============================================================================


def test_detection_range_ui_exists_with_visible_as_default():
    source = _source()
    assert 'id="wwDetectEventRangeVisible"' in source
    assert 'id="wwDetectEventRangeFull"' in source
    visible_idx = source.index('id="wwDetectEventRangeVisible"')
    visible_tag = source[visible_idx : source.index(">", visible_idx)]
    assert "checked" in visible_tag
    full_idx = source.index('id="wwDetectEventRangeFull"')
    full_tag = source[full_idx : source.index(">", full_idx)]
    assert "checked" not in full_tag


def test_detection_range_rows_reuse_the_existing_stacked_radio_pattern():
    """Task section 2/6: no new picker primitive, no numeric range
    form -- reuses the SAME .ww-pu-mode-row pattern the Per-Unit
    Current Base picker already established."""
    source = _source()
    idx = source.index('id="wwDetectEventRangeVisibleRow"')
    row_html = source[max(0, idx - 200) : idx + 400]
    assert "ww-pu-mode-row" in row_html
    assert "Current visible range" in row_html
    assert "Full recording" in source


def test_open_modal_resets_range_to_visible_every_time():
    source = _source()
    fn_idx = source.index("function wwOpenDetectEventModal(groupId)")
    fn_body = source[fn_idx : source.index("function wwCloseDetectEventModal()", fn_idx)]
    assert 'document.getElementById("wwDetectEventRangeVisible").checked = true;' in fn_body
    assert "wwSyncDetectEventRangeRowHighlight();" in fn_body


class TestVisibleRangeTimeMapping:
    """Task section 4/21: "Use existing helpers. Do not duplicate
    hardcoded formulas." TG-E: this now uses the LAUNCHING GROUP's own
    wwTimeGroupVisibleRange(groupId) -- never the single global/primary
    ww.viewport blindly -- composed with the SAME Slice 1
    wwWorkspaceTimeToSourceTime() helper every other source-native
    request already uses, never a second hand-rolled formula and never
    a separate "apply t0" step (that would double-apply it)."""

    def test_conversion_function_reuses_the_existing_slice_1_helper_only(self):
        source = _source()
        fn_idx = source.index("function wwDetectEventVisibleSourceNativeRange(sourceId, groupId)")
        fn_body = source[fn_idx : source.index("async function wwHandleDetectEventAnalyseClick()", fn_idx)]
        assert "wwWorkspaceTimeToSourceTime(sourceId, range.start)" in fn_body
        assert "wwWorkspaceTimeToSourceTime(sourceId, range.end)" in fn_body
        # No second/hand-rolled arithmetic -- no raw "+"/"-" against
        # t0 or alignmentOffsets anywhere in this function.
        assert "t0WorkspaceTime" not in fn_body
        assert "timeGroupT0State" not in fn_body
        assert "alignmentOffsets" not in fn_body

    def test_no_viewport_returns_null_never_throws(self):
        source = _source()
        fn_idx = source.index("function wwDetectEventVisibleSourceNativeRange(sourceId, groupId)")
        fn_body = source[fn_idx : source.index("async function wwHandleDetectEventAnalyseClick()", fn_idx)]
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "if (!range) return null;" in fn_body


class TestViewportCapturedAtAnalyseTime:
    """Task section 7/21: "Use the viewport that exists when the
    engineer clicks Analyse, not a stale range captured when the modal
    first opened." -- verified structurally: the conversion call happens
    INSIDE wwHandleDetectEventAnalyseClick() itself (reading the
    launching group's own current viewport fresh at call time), never
    precomputed in wwOpenDetectEventModal(groupId)."""

    def test_open_modal_never_reads_the_viewport(self):
        source = _source()
        fn_idx = source.index("function wwOpenDetectEventModal(groupId)")
        fn_body = source[fn_idx : source.index("function wwCloseDetectEventModal()", fn_idx)]
        assert "ww.viewport" not in fn_body
        assert "wwTimeGroupVisibleRange" not in fn_body

    def test_analyse_handler_computes_the_range_itself(self):
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert "wwDetectEventVisibleSourceNativeRange(sourceId, groupId)" in fn_body


class TestNoSilentFullRecordFallback:
    """Task section 15 (mandatory): if Current visible range cannot run,
    tell the engineer -- never silently switch to Full recording."""

    def test_missing_viewport_shows_an_error_and_returns_without_fetching(self):
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        guard_idx = fn_body.index("if (!converted) {")
        guard_end_idx = fn_body.index("}", guard_idx)
        guard_block = fn_body[guard_idx : guard_end_idx + 1]
        assert "wwDetectEventShowError(" in guard_block
        assert "return;" in guard_block
        # The guard must return BEFORE ever building a "full recording"
        # style request (no search_start_time/search_end_time assigned
        # inside this same guard block).
        assert "search_start_time" not in guard_block

    def test_full_mode_omits_search_bounds_entirely(self):
        """Selecting Full recording sends no search_start_time/
        search_end_time at all -- the backend's own existing "omitted ->
        whole record" semantics (task section 5), not a fabricated
        full-span pair computed on the frontend."""
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert 'let searchRangeInfo = { mode: "full" };' in fn_body
        if_idx = fn_body.index('if (rangeMode === "visible")')
        assert "body.search_start_time" in fn_body[if_idx:]


def test_result_shows_search_range_scope():
    """Task section 17: "a subtle indication of the search scope in the
    result" -- reuses wwFormatCursorPointTime() (never a bespoke
    duration formatter, stays consistent with the app's own current
    Elapsed/Absolute/event-relative display mode). TG-D2: the label
    helper now takes an explicit groupId too (the suggestion's own
    owning Time Group, never a hidden primary-group default)."""
    source = _source()
    fn_idx = source.index("function wwDetectEventSearchRangeLabel(searchRangeInfo, groupId)")
    fn_body = source[fn_idx : source.index("function wwRenderDetectEventResult(", fn_idx)]
    assert 'return "Full recording";' in fn_body
    assert "wwFormatCursorPointTime(searchRangeInfo.workspaceStart, groupId)" in fn_body
    assert "wwFormatCursorPointTime(searchRangeInfo.workspaceEnd, groupId)" in fn_body

    render_idx = source.index("function wwRenderDetectEventResult(view, channelUnit, searchRangeInfo)")
    render_body = source[render_idx : source.index("function wwResetDetectEventSuggestion()", render_idx)]
    assert "Search range: " in render_body
    # Shown for BOTH found and not-found results (task section 16: "no
    # clear event" within a selected range is still a valid result that
    # should say what was searched).
    assert render_body.count("searchRangeLine") >= 3


def test_range_radio_change_invalidates_a_stale_candidate():
    """Task's own edge case: switching Detection range after a
    candidate was already found under the OTHER mode must not leave a
    stale Accept button enabled."""
    source = _source()
    idx = source.index('for (const radio of [document.getElementById("wwDetectEventRangeVisible")')
    block = source[idx : idx + 600]
    assert "wwSyncDetectEventRangeRowHighlight();" in block
    assert "wwInvalidateDetectEventSuggestion();" in block
