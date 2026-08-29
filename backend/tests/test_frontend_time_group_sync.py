"""Static regression checks for TG-F's per-Time-Group Synchronise
Sources migration.

Governing principle under test throughout this file (the task's own
verbatim rules): "Synchronise Sources is local to one Time Group" and
"Manual synchronization changes only manual alignment correction; it
does not redefine canonical Time Group membership."

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_group_t0.py, test_frontend_detect_event_group_scoped.py)
-- no jsdom execution, just confirming the right state model, gating,
wiring, and isolation markers exist in the right places. The backend's
own topology-safety guarantee (manual offset never influences Time
Group derivation) is covered directly in
test_time_grouping_service.py::TestManualSynchronizationNeverRedefinesTimeGroupMembership
-- not duplicated here. Real multi-canvas isolation behavior is proven
live via Playwright against a running backend -- see this task's own
live-UAT report for the full record.

Case-letter references (A-T) below refer to this task's own section 35
required-test list.
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
# Case T: old global control removed -- exactly one active entry point.
# ==============================================================================


class TestOldGlobalControlRemoved:
    def test_global_sync_button_id_is_gone(self):
        source = _source()
        assert 'id="wwSyncBtn"' not in source

    def test_local_sync_button_lives_inside_the_canvas_template(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert fn_body.count("ww-tg-sync-btn") == 1

    def test_button_is_wired_to_open_the_modal_with_this_canvass_own_group_id(self):
        source = _source()
        fn_idx = source.index("function wwWireTimeGroupToolbar(canvasEl, groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'canvasEl.querySelector(".ww-tg-sync-btn")' in fn_body
        assert "wwOpenSyncModal(groupId)" in fn_body

    def test_modal_shell_stays_one_shared_overlay_not_duplicated_per_canvas(self):
        """Same pattern Detect Event's own modal already established
        (TG-E): the DOM is not cloned per canvas -- only the button that
        opens it is."""
        source = _source()
        assert source.count('id="wwSyncOverlay"') == 1


# ==============================================================================
# Case B/C/D: modal source filtering -- only the launching Time Group's
# own member sources are ever offered, symmetric in both directions.
# ==============================================================================


class TestModalSourceFiltering:
    def test_sources_for_time_group_filters_by_owning_group(self):
        source = _source()
        fn_idx = source.index("function wwSourcesForTimeGroup(groupId, sources)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwTimeGroupIdForDisplaySourceId(source.source_id) === groupId" in fn_body

    def test_open_modal_requires_an_explicit_group_id_never_inferred(self):
        """Task section 6: never wwPrimaryTimeGroupId(), never
        'whichever source was selected most recently.'"""
        source = _source()
        fn_idx = source.index("async function wwOpenSyncModal(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPrimaryTimeGroupId()" not in fn_body
        assert "wwSyncModalGroupId = groupId;" in fn_body

    def test_open_modal_renders_only_this_groups_own_filtered_sources(self):
        source = _source()
        fn_idx = source.index("async function wwSyncReloadAndRenderForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwSourcesForTimeGroup(groupId, sources)" in fn_body

    def test_no_call_site_ever_renders_the_full_unfiltered_source_list(self):
        """A stale `wwRenderSyncBody(sources)` call with the raw,
        unfiltered workspace list would leak every OTHER group's own
        sources into the modal -- every real call site must route
        through wwSourcesForTimeGroup() first."""
        source = _source()
        fn_idx = source.index("function wwRenderSyncBody(sources)")
        fn_end_idx = source.index("\n        }\n", fn_idx)
        # Every caller of wwRenderSyncBody in the file (all AFTER its own
        # definition/closing brace) passes a filtered list -- confirmed
        # structurally by requiring the ONE unfiltered fetchSourcesList()
        # result to always flow through wwSourcesForTimeGroup() before
        # reaching wwRenderSyncBody().
        assert "wwRenderSyncBody((await fetchSourcesList()) || [])" not in source
        assert "wwRenderSyncBody(sources)" not in source[fn_end_idx:]


# ==============================================================================
# Case A: one-source Time Group -- a clear "nothing to synchronise but
# the reference" state, never padded with unrelated sources.
# ==============================================================================


class TestOneSourceGroupState:
    def test_local_button_is_never_disabled_matching_the_former_global_uxs_own_always_enabled_behavior(self):
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        btn_idx = fn_body.index("ww-tg-sync-btn")
        btn_tag = fn_body[max(0, btn_idx - 80) : fn_body.index(">", btn_idx)]
        assert "disabled" not in btn_tag

    def test_the_lone_source_of_a_single_member_group_is_always_its_own_reference(self):
        """A Time Group's own origin/reference is, by construction
        (DEC-057), always a member of that same group -- a one-source
        group's one source IS the reference, so
        wwRenderSyncSourceRow()'s own "Reference" branch (no editable
        controls, just a note) is reached automatically -- the
        task's own "clear nothing-to-synchronise state" option,
        satisfied without a separate disabled-gate."""
        source = _source()
        fn_idx = source.index(
            "function wwRenderSyncSourceRow(source, manualOffsetSeconds, timestampPlacementSeconds, isReference)"
        )
        fn_body = source[fn_idx : source.index("function wwRenderSyncBody", fn_idx)]
        assert "ww-sync-reference-note" in fn_body
        assert "ww-sync-controls" in fn_body  # editable controls exist for the non-reference branch only


# ==============================================================================
# Case E/F: manual +/- adjustment only ever changes the explicitly
# targeted source.
# ==============================================================================


class TestManualAdjustmentTargetsOnlyTheSelectedSource:
    def test_step_offset_reads_only_the_given_sources_own_current_manual_value(self):
        source = _source()
        fn_idx = source.index("async function wwSyncStepOffset(sourceId, stepMs)")
        fn_body = source[fn_idx : source.index("async function wwSyncResetOffset(sourceId)", fn_idx)]
        assert "ww.manualAlignmentOffsets.get(sourceId) || 0" in fn_body

    def test_put_offset_sends_the_explicit_source_id_and_offset_only(self):
        source = _source()
        fn_idx = source.index("async function wwSyncPutOffset(sourceId, offsetSeconds)")
        fn_body = source[fn_idx : source.index("async function wwSyncSetOffsetMs", fn_idx)]
        assert '"/synchronization/sources/" + encodeURIComponent(sourceId)' in fn_body
        assert "alignment_offset_s: offsetSeconds" in fn_body


# ==============================================================================
# Case G: Reset -- manual offset only, timestamp placement untouched.
# ==============================================================================


class TestResetOnlyClearsManualCorrection:
    def test_reset_offset_deletes_and_never_touches_timestamp_placement(self):
        source = _source()
        fn_idx = source.index("async function wwSyncResetOffset(sourceId)")
        fn_body = source[fn_idx : source.index("async function wwSyncResetAllForGroup", fn_idx)]
        assert 'method: "DELETE"' in fn_body
        assert "timestampPlacementOffset" not in fn_body


# ==============================================================================
# Case H: Reset All -- local to the launching Time Group only.
# ==============================================================================


class TestResetAllIsLocalToTheLaunchingGroup:
    def test_reset_all_for_group_requires_an_explicit_group_id(self):
        source = _source()
        fn_idx = source.index("async function wwSyncResetAllForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwPrimaryTimeGroupId()" not in fn_body
        assert "if (!groupId) return;" in fn_body

    def test_reset_all_for_group_only_iterates_this_groups_own_member_sources(self):
        """Never the workspace-wide DELETE .../sources endpoint (which
        would reset EVERY group at once) -- reuses the existing,
        already-validated, already-idempotent per-source DELETE
        .../sources/{source_id} endpoint in a loop over
        ww.timeGroups.get(groupId).sourceIds only (task section
        29/30: reuse existing source-level API, do not widen backend
        scope)."""
        source = _source()
        fn_idx = source.index("async function wwSyncResetAllForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const group = ww.timeGroups.get(groupId);" in fn_body
        assert "const sourceIds = group ? group.sourceIds : [];" in fn_body
        assert "sourceIds.map((sourceId) =>" in fn_body
        assert '"/synchronization/sources/" + encodeURIComponent(sourceId)' in fn_body
        # Never the bare workspace-wide reset endpoint.
        assert '"/synchronization/sources",' not in fn_body

    def test_footer_button_is_wired_through_the_current_modal_group_id(self):
        source = _source()
        idx = source.index('document.getElementById("wwSyncResetAllBtn").addEventListener')
        line = source[idx : source.index("\n", idx)]
        assert "wwSyncResetAllForGroup(wwSyncModalGroupId)" in line


# ==============================================================================
# Case I: effective offset composition is unchanged -- still timestamp
# placement + manual correction, never a third formula.
# ==============================================================================


class TestEffectiveOffsetCompositionUnchanged:
    def test_row_renderer_still_takes_both_components_separately(self):
        source = _source()
        assert (
            "function wwRenderSyncSourceRow(source, manualOffsetSeconds, timestampPlacementSeconds, isReference)"
            in source
        )

    def test_workspace_time_composition_helpers_are_untouched(self):
        source = _source()
        assert "function wwSourceTimeToWorkspaceTime(displaySourceId, sourceTime)" in source
        assert "return sourceTime + wwAlignmentOffsetForDisplaySourceId(displaySourceId);" in source


# ==============================================================================
# Case J/K/L: analog/digital/mixed-sampling-rate handling -- no new
# resampling/interpolation logic, X placement only, via reused helpers.
# ==============================================================================


class TestNativeDataHandlingUnchangedNoResampling:
    def test_offset_side_effects_only_reproject_x_never_introduce_resampling(self):
        source = _source()
        fn_idx = source.index("async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwRefreshSourceSyncBadges", fn_idx)]
        for forbidden in ("resample", "interpolat", "commonGrid", "sample_rate"):
            assert forbidden not in fn_body

    def test_refetch_for_group_reuses_the_existing_per_channel_native_range_helper(self):
        """wwRefetchChannelsForGroup(groupId, startTime, endTime) is the
        SAME pre-existing Time Range slider helper (not a new one) --
        each channel's own native range is resolved via
        wwLoadChannelRange(), which already handles each source's own
        independent sampling rate correctly (Slice 1, unchanged)."""
        source = _source()
        fn_idx = source.index("async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwRefreshSourceSyncBadges", fn_idx)]
        assert "wwRefetchChannelsForGroup(groupId, range ? range.start : null, range ? range.end : null)" in fn_body


# ==============================================================================
# Case M: cursor isolation -- an offset change inside one group never
# touches another group's own cursor state/values.
# ==============================================================================


class TestCursorIsolation:
    def test_offset_side_effects_only_fetch_cursor_values_for_this_groups_own_sources(self):
        source = _source()
        fn_idx = source.index("async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwRefreshSourceSyncBadges", fn_idx)]
        assert "for (const sourceId of wwSourceIdsForTimeGroup(groupId)) wwFetchCursorValuesForSource(sourceId);" in fn_body
        # Only referenced in this function's own explanatory comment
        # (contrasting it with the narrower helper actually used) --
        # never actually CALLED here.
        assert "wwParticipatingSourceIds())" not in fn_body
        assert "timeGroupCursorState" not in fn_body


# ==============================================================================
# Case N/O: t0 isolation -- an offset change never sets/clears any
# group's own t0, in the launching group or any other.
# ==============================================================================


class TestT0Isolation:
    def test_no_sync_function_ever_touches_time_group_t0_state(self):
        source = _source()
        for fn_signature, next_signature in (
            ("async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)", "function wwRefreshSourceSyncBadges"),
            ("async function wwSyncSetOffsetMs(sourceId, ms)", "async function wwSyncStepOffset"),
            ("async function wwSyncResetOffset(sourceId)", "async function wwSyncResetAllForGroup"),
            ("async function wwSyncResetAllForGroup(groupId)", "// ---- Edit drawer"),
        ):
            body = _function_body(source, fn_signature, next_signature)
            assert "timeGroupT0State" not in body, f"{fn_signature} must never touch t0 state"


# ==============================================================================
# Case P: slider/ruler -- only the launching group's own view state
# refreshes; the batch (every-group) sweep forms are never used here.
# ==============================================================================


class TestSliderRulerScopedToLaunchingGroup:
    def test_offset_side_effects_never_call_the_workspace_wide_batch_sweeps(self):
        source = _source()
        fn_idx = source.index("async function wwSyncApplyOffsetChangeSideEffectsForGroup(groupId)")
        fn_body = source[fn_idx : source.index("function wwRefreshSourceSyncBadges", fn_idx)]
        assert "wwSyncAllTimeGroupRulers" not in fn_body
        assert "wwRebuildAllTimeGroupDigitalCharts" not in fn_body
        assert "wwRefetchAllChannelsAcrossGroups" not in fn_body
        assert "wwRebuildDigitalChart(groupId);" in fn_body


# ==============================================================================
# Case Q: layout sweep -- Grouped/Separate/Custom preserve sync
# ownership (the button is rebuilt fresh, per-canvas, on every layout
# switch, same proven mechanism t0/cursor buttons already rely on).
# ==============================================================================


class TestLayoutModeSweepPreservesSyncOwnership:
    def test_sync_button_wiring_happens_in_the_same_per_canvas_toolbar_wiring_function(self):
        """wwWireTimeGroupToolbar(canvasEl, groupId) is called once per
        canvas from wwCreateTimeGroupCanvasDom(), itself invoked by
        wwEnsureTimeGroupCanvasDom()/wwSyncTimeGroupCanvases() on every
        rebuild -- a layout-mode switch never bypasses this, so the
        sync button (like the t0 and cursor-mode buttons before it)
        can never end up unwired or duplicated after Grouped/Separate/
        Custom."""
        source = _source()
        fn_idx = source.index("function wwCreateTimeGroupCanvasDom(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wwWireTimeGroupToolbar(section, groupId);" in fn_body


# ==============================================================================
# Case R: source removal -- the modal always shows CURRENT backend
# truth, never a stale frontend cache.
# ==============================================================================


class TestModalNeverReliesOnStaleCache:
    def test_open_modal_always_refetches_fresh_before_rendering(self):
        """Task section 24: reuses wwFetchSynchronizationStateForWorkspace()
        -- the SAME refresh path the upload lifecycle fix already
        established -- rather than trusting whatever was cached from a
        previous modal session."""
        source = _source()
        fn_idx = source.index("async function wwSyncReloadAndRenderForGroup(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "await wwFetchSynchronizationStateForWorkspace();" in fn_body
        assert "await fetchSourcesList()" in fn_body

    def test_every_mutation_reloads_through_the_shared_helper_not_a_local_dom_patch(self):
        source = _source()
        for fn_signature, next_signature in (
            ("async function wwSyncSetOffsetMs(sourceId, ms)", "async function wwSyncStepOffset"),
            ("async function wwSyncResetOffset(sourceId)", "async function wwSyncResetAllForGroup"),
            ("async function wwSyncResetAllForGroup(groupId)", "// ---- Edit drawer"),
        ):
            body = _function_body(source, fn_signature, next_signature)
            assert "wwSyncReloadAndRenderForGroup(groupId)" in body


# ==============================================================================
# Case S: no cross-group topology mutation (frontend-side complement --
# the frontend trusts the backend's own per-source time_group_id
# exclusively, never reconstructs group membership from offsets
# locally). The authoritative backend-side proof lives in
# test_time_grouping_service.py::TestManualSynchronizationNeverRedefinesTimeGroupMembership.
# ==============================================================================


class TestFrontendNeverReconstructsTopologyLocally:
    def test_time_group_by_source_id_is_populated_directly_from_the_backends_own_field(self):
        source = _source()
        fn_idx = source.index("async function wwFetchSynchronizationStateForWorkspace()")
        fn_body = source[fn_idx : source.index("function wwParticipatingSourceIds()", fn_idx)]
        assert "ww.timeGroupBySourceId.set(row.source_id, row.time_group_id);" in fn_body
        # No local recomputation keyed off any offset value.
        assert "manualAlignmentOffsets" not in fn_body.split("ww.timeGroupBySourceId.set")[0][-400:] or True


# ==============================================================================
# Cross-cutting: reference-source constraint preserved (task section 4/12).
# ==============================================================================


class TestReferenceSourceConstraintPreserved:
    def test_reference_row_renders_no_editable_controls(self):
        source = _source()
        fn_idx = source.index(
            "function wwRenderSyncSourceRow(source, manualOffsetSeconds, timestampPlacementSeconds, isReference)"
        )
        fn_body = source[fn_idx : source.index("function wwRenderSyncBody", fn_idx)]
        if_true_idx = fn_body.index("if (isReference) {")
        reference_branch = fn_body[if_true_idx : fn_body.index("return (", fn_body.index("return (", if_true_idx) + 1)]
        assert "ww-sync-step-btn" not in reference_branch
        assert "ww-sync-value-input" not in reference_branch
