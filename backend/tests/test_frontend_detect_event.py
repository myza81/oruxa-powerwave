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
    assert 'id="wwDetectEventReplaceConfirm"' in source
    assert 'id="wwDetectEventReplaceConfirmBtn"' in source


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
    fn_idx = source.index("function wwDetectEventSourceOptionsHtml()")
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


def test_analyse_never_calls_the_t0_endpoint():
    """Task section 26: "Do not make this endpoint set t0
    automatically." -- verified on the frontend side too: the Analyse
    handler must never itself PUT/DELETE .../t0."""
    source = _source()
    fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
    fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
    assert "/synchronization/t0" not in fn_body


def test_preview_marker_is_shown_before_acceptance_is_possible():
    """Task section 13: the suggested point must be visible on the
    waveform BEFORE acceptance -- the marker is set (ww.suggestedEvent,
    then wwUpdateCursorOverlay()) unconditionally on a found result,
    strictly before wwRenderDetectEventResult() ever enables the Accept
    button."""
    source = _source()
    fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
    fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
    marker_idx = fn_body.index("ww.suggestedEvent = {")
    overlay_idx = fn_body.index("wwUpdateCursorOverlay();", marker_idx)
    render_idx = fn_body.index("wwRenderDetectEventResult(", overlay_idx)
    assert marker_idx < overlay_idx < render_idx


def test_accept_reuses_the_existing_t0_put_endpoint_only():
    """Task section 14: "reuse the existing t0 service... do not create
    a second t0 implementation." -- verified structurally: acceptance
    calls the SAME PUT .../synchronization/t0 Slice 2 already
    established, then the SAME three follow-up calls
    wwSetT0FromCursorA() itself makes on success."""
    source = _source()
    fn_idx = source.index("async function wwAcceptDetectedEvent()")
    fn_body = source[fn_idx : source.index("function wwHandleDetectEventAcceptClick()", fn_idx)]
    assert '"/synchronization/t0"' in fn_body
    assert 'method: "PUT"' in fn_body
    assert "t0_workspace_time: workspaceTime" in fn_body
    assert "ww.t0WorkspaceTime = body.t0_workspace_time;" in fn_body
    assert "wwSyncT0Controls();" in fn_body
    assert "wwApplyT0ToDisplay();" in fn_body


def test_accept_while_t0_exists_requires_explicit_replace_confirmation():
    """Task section 16: never silently replace an already-defined t0."""
    source = _source()
    fn_idx = source.index("function wwHandleDetectEventAcceptClick()")
    fn_body = source[fn_idx : source.index("function wwHandleDetectEventReplaceCancelClick()", fn_idx)]
    assert "if (wwHasT0())" in fn_body
    assert "wwDetectEventReplaceConfirm" in fn_body
    replace_confirm_shown_before_accept = fn_body.index("wwDetectEventReplaceConfirm") < fn_body.rindex("wwAcceptDetectedEvent();")
    assert replace_confirm_shown_before_accept


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
    fn_body = source[fn_idx : source.index("function wwOpenDetectEventModal()", fn_idx)]
    assert "visible: false" in fn_body
    assert "workspaceTime: null" in fn_body
    assert "wwUpdateCursorOverlay();" in fn_body


def test_cursor_overlay_draws_the_suggestion_marker_independent_of_cursor_mode():
    """Task section 13: the marker must be able to show even when A/B
    cursor mode itself is off -- the overlay's own drawing gate must
    admit EITHER cursor-mode-active OR a visible suggestion, not only
    the former."""
    source = _source()
    fn_idx = source.index("function wwUpdateCursorOverlay()")
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
    fn_idx = source.index("function wwUpdateCursorOverlay()")
    body = source[fn_idx : fn_idx + 12000]
    # Anchored on this block's own unique comment, not the bare
    # `data-cursor-line="suggested"` selector -- that selector also
    # appears earlier, in the early-return branch's own defensive
    # hidden-state reset (see that branch's own comment).
    suggested_block_idx = body.index('Slice 3: the "Suggested event" preview marker -- SAME')
    suggested_block = body[suggested_block_idx : suggested_block_idx + 1200]
    assert "wwCursorTimeToPixelX(suggestion.workspaceTime)" in suggested_block


def test_new_workspace_clears_suggestion_but_plain_clear_workspace_does_not():
    source = _source()
    clear_idx = source.index("function wwClearWorkspace(options)")
    reset_branch = source[clear_idx : source.index("            } else {", clear_idx)]
    assert "wwCloseDetectEventModal();" in reset_branch

    else_branch_idx = source.index("            } else {", clear_idx)
    else_branch = source[else_branch_idx : source.index("// Phase 2C-C1", else_branch_idx)]
    assert "wwCloseDetectEventModal" not in else_branch
    assert "wwResetDetectEventSuggestion" not in else_branch
