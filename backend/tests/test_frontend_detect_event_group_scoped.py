"""Static regression checks for TG-E's Detect Event changes: the
capability stays fully implemented and becomes genuinely Time-Group-aware
internally, but its normal frontend entry point is hidden from ordinary
product use (owner decision).

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_t0.py, test_frontend_detect_event.py) -- no
jsdom execution, just confirming the right gating/wiring/isolation
markers exist in the right places. Real multi-canvas isolation behavior
is proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.

Case-letter references (N-W) below refer to this task's own section 33
required-test list. test_frontend_detect_event.py itself already covers
the DEC-057/Slice-3-era baseline behavior (unchanged detection
algorithm/candidate shape/accept flow) -- this file adds ONLY the new
TG-E-specific group-scoping and UI-hiding coverage, never duplicating
that existing suite.
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


# ==============================================================================
# Case N: the normal frontend entry point is hidden -- a single named
# constant is the one source of truth, never fragile CSS alone.
# ==============================================================================


class TestDetectEventUiHidden:
    def test_ui_enabled_constant_exists_and_is_false(self):
        source = _source()
        assert "const WW_DETECT_EVENT_UI_ENABLED = false;" in source

    def test_button_hidden_state_is_driven_by_the_constant_not_a_hardcoded_css_rule(self):
        source = _source()
        idx = source.index('document.getElementById("wwDetectEventBtn").hidden = !WW_DETECT_EVENT_UI_ENABLED;')
        assert idx > -1
        # Never a bare `display: none` CSS rule targeting this button's
        # own id -- the hide is a JS-driven attribute, not stylesheet-only.
        assert "#wwDetectEventBtn { display: none" not in source
        assert "#wwDetectEventBtn{display:none" not in source

    def test_click_listener_stays_wired_regardless_of_the_flag(self):
        """Task section 27: "re-enabling later should require only a
        small exposure change, not another architecture migration" --
        the listener itself is wired unconditionally; only .hidden is
        gated."""
        source = _source()
        idx = source.index('document.getElementById("wwDetectEventBtn").addEventListener("click",')
        line = source[idx : source.index("\n", idx)]
        assert "wwOpenDetectEventModal(wwPrimaryTimeGroupId())" in line


# ==============================================================================
# Case O: the internal entry point remains fully functional -- every
# workflow function this capability needs still exists, unremoved.
# ==============================================================================


class TestInternalEntryPointStillFullyFunctional:
    def test_open_modal_takes_an_explicit_group_id_and_is_still_callable(self):
        source = _source()
        assert "function wwOpenDetectEventModal(groupId)" in source

    def test_every_core_workflow_function_still_exists(self):
        source = _source()
        for fn_signature in (
            "function wwDetectEventSourceOptionsHtml(groupId)",
            "function wwDetectEventChannelOptionsHtml(sourceId)",
            "function wwDetectEventVisibleSourceNativeRange(sourceId, groupId)",
            "async function wwHandleDetectEventAnalyseClick()",
            "async function wwAcceptDetectedEvent()",
            "function wwCloseDetectEventModal()",
            "function wwResetDetectEventSuggestion()",
        ):
            assert fn_signature in source, f"expected {fn_signature} to still exist"

    def test_modal_dom_and_result_panel_are_not_removed(self):
        source = _source()
        assert 'id="wwDetectEventOverlay"' in source
        assert 'id="wwDetectEventSourceSelect"' in source
        assert 'id="wwDetectEventChannelSelect"' in source
        assert 'id="wwDetectEventAcceptBtn"' in source
        assert 'id="wwDetectEventResult"' in source


# ==============================================================================
# Case P/Q: source filtering -- only the launching Time Group's own
# member sources are ever offered, regardless of which group is asked
# for.
# ==============================================================================


class TestSourceListIsFilteredToTheLaunchingGroup:
    def test_source_options_html_requires_a_group_id_and_filters_by_it(self):
        source = _source()
        fn_idx = source.index("function wwDetectEventSourceOptionsHtml(groupId)")
        fn_body = source[fn_idx : source.index("function wwDetectEventChannelOptionsHtml", fn_idx)]
        assert "if (wwTimeGroupIdForDisplaySourceId(inventory.sourceId) !== groupId) continue;" in fn_body

    def test_open_modal_passes_its_own_group_id_straight_into_the_source_list_builder(self):
        source = _source()
        fn_idx = source.index("function wwOpenDetectEventModal(groupId)")
        fn_body = source[fn_idx : source.index("function wwCloseDetectEventModal()", fn_idx)]
        assert "sourceSelect.innerHTML = wwDetectEventSourceOptionsHtml(groupId);" in fn_body

    def test_no_call_site_ever_omits_the_group_id_argument(self):
        """A stale call like wwDetectEventSourceOptionsHtml() with zero
        arguments would silently pass `undefined` as groupId -- every
        real source would then fail the `=== groupId` filter and the
        dropdown would render empty, a loud, structural failure mode by
        construction rather than a leak into another group."""
        source = _source()
        assert "wwDetectEventSourceOptionsHtml()" not in source


# ==============================================================================
# Case R: "Current visible range" uses the launching group's own
# viewport, never the single global/primary ww.viewport.
# ==============================================================================


class TestCurrentVisibleRangeUsesTheLaunchingGroupsOwnViewport:
    def test_visible_source_native_range_reads_this_groups_own_visible_range(self):
        source = _source()
        fn_idx = source.index("function wwDetectEventVisibleSourceNativeRange(sourceId, groupId)")
        fn_body = source[fn_idx : source.index("async function wwHandleDetectEventAnalyseClick()", fn_idx)]
        assert "const range = wwTimeGroupVisibleRange(groupId);" in fn_body
        assert "ww.viewport" not in fn_body

    def test_analyse_handler_derives_group_id_from_the_selected_source_before_converting(self):
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert "const groupId = sourceId ? wwTimeGroupIdForDisplaySourceId(sourceId) : null;" in fn_body
        assert "wwDetectEventVisibleSourceNativeRange(sourceId, groupId)" in fn_body


# ==============================================================================
# Case S: "Full recording" still means only the selected source within
# the selected Time Group -- never a workspace-wide search.
# ==============================================================================


class TestFullRecordingScopedToTheSelectedSourceOnly:
    def test_full_mode_sends_only_the_explicit_source_id_no_group_or_workspace_wide_field(self):
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert 'const body = { source_id: sourceId, channel_name: channelName, sensitivity: sensitivity };' in fn_body
        assert 'let searchRangeInfo = { mode: "full" };' in fn_body
        # No group-scoped or workspace-scoped field is ever added to the
        # POST body for "full" mode -- source_id alone already resolves
        # an unambiguous, single source's own full record.
        assert "group_id" not in fn_body


# ==============================================================================
# Case T: candidate isolation -- a Group 1 candidate can never alter
# Group 2's own state, by construction of the source filtering above.
# ==============================================================================


class TestCandidateIsolation:
    def test_suggested_event_is_one_transient_object_whose_own_group_is_always_derivable(self):
        """No per-group Map is needed for candidate state (task section
        24's own explicit allowance: "do not overengineer if the modal
        is transient and groupId can be explicit context") -- unambiguous
        ownership instead comes from the dropdown's own group-filtered
        source list (Case P/Q above): whichever source the candidate
        names, wwTimeGroupIdForDisplaySourceId(sourceId) always resolves
        back to the SAME group that launched the modal, never another."""
        source = _source()
        idx = source.index("suggestedEvent: {")
        body = source[idx : source.index("};", idx)]
        assert "sourceId: null" in body

    def test_render_result_derives_its_own_group_id_from_the_candidates_own_source(self):
        source = _source()
        fn_idx = source.index("function wwRenderDetectEventResult(view, channelUnit, searchRangeInfo)")
        fn_body = source[fn_idx : source.index("function wwResetDetectEventSuggestion()", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(ww.suggestedEvent.sourceId);" in fn_body


# ==============================================================================
# Case U: accepting a candidate sets ONLY that candidate's own owning
# group's t0 -- every other group's own t0 is untouched.
# ==============================================================================


class TestAcceptOnlyChangesTheOwningGroupsT0:
    def test_accept_derives_group_id_from_the_candidates_own_source_and_writes_only_that_key(self):
        source = _source()
        fn_idx = source.index("async function wwAcceptDetectedEvent()")
        fn_body = source[fn_idx : source.index("function wwUpdateEditGroupsButtonVisibility()", fn_idx)]
        assert "const groupId = wwTimeGroupIdForDisplaySourceId(sourceId);" in fn_body
        assert "ww.timeGroupT0State.set(groupId, body.t0_workspace_time);" in fn_body
        assert "wwApplyT0ToDisplayForGroup(groupId);" in fn_body
        # Never a bare, groupId-less write -- no lingering single-scalar
        # assignment path remains.
        assert "ww.timeGroupT0State.set(" in fn_body
        assert fn_body.count("ww.timeGroupT0State.set(") == 1


# ==============================================================================
# Case V: cancel leaves every t0 value unchanged -- only the transient
# candidate is cleared.
# ==============================================================================


class TestCancelChangesNoT0:
    def test_close_modal_never_touches_t0_state(self):
        source = _source()
        fn_idx = source.index("function wwCloseDetectEventModal()")
        fn_body = source[fn_idx : source.index("function wwDetectEventShowError(", fn_idx)]
        assert "timeGroupT0State" not in fn_body
        assert "wwResetDetectEventSuggestion();" in fn_body

    def test_reset_suggestion_never_touches_t0_state(self):
        source = _source()
        fn_idx = source.index("function wwResetDetectEventSuggestion()")
        fn_body = source[fn_idx : source.index("function wwOpenDetectEventModal(groupId)", fn_idx)]
        assert "timeGroupT0State" not in fn_body


# ==============================================================================
# Case W: the detection algorithm itself is untouched -- this slice is
# scope/ownership only, never a signal-processing redesign.
# ==============================================================================


class TestDetectionAlgorithmUnchanged:
    def test_analyse_request_shape_sent_to_the_backend_is_unchanged(self):
        """The exact same three fields, the exact same endpoint -- no
        new parameter (e.g. a group_id) was added to the wire contract;
        group-awareness is a purely frontend selection-scoping concern,
        never a backend algorithm change."""
        source = _source()
        fn_idx = source.index("async function wwHandleDetectEventAnalyseClick()")
        fn_body = source[fn_idx : source.index("async function wwAcceptDetectedEvent()", fn_idx)]
        assert '"/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/synchronization/detect-event"' in fn_body
        assert 'method: "POST"' in fn_body
        assert "source_id: sourceId" in fn_body
        assert "channel_name: channelName" in fn_body
        assert "sensitivity: sensitivity" in fn_body

    def test_result_rendering_still_surfaces_the_same_quality_and_rms_fields(self):
        source = _source()
        fn_idx = source.index("function wwRenderDetectEventResult(view, channelUnit, searchRangeInfo)")
        fn_body = source[fn_idx : source.index("function wwResetDetectEventSuggestion()", fn_idx)]
        assert "view.quality" in fn_body
        assert "view.baseline_rms" in fn_body
        assert "view.changed_rms" in fn_body
        assert "view.change_ratio" in fn_body
        assert "view.direction" in fn_body
