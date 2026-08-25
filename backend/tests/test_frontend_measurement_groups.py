"""Static regression checks for the DEC-050 Slice 6 Measurement Group
configuration workspace (frontend/index.html). Same source-text
substring-assertion pattern every other `test_frontend_*.py` file in
this suite already uses -- this repo has no browser/DOM test runner for
the single-file frontend. End-to-end browser verification (real
backend, real fetches, full Suggest -> Edit -> Save round trip for
Voltage and all three Current methods, cross-source isolation, Cancel-
discards-changes) was performed manually via Playwright against the
live app during implementation; these tests guard the static structure
and control-flow invariants that verification depends on, so they can't
silently regress later.
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


class TestModalAndDrawerMarkupExists:
    def test_measurement_groups_modal_markup_exists(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' in source
        assert 'id="measurementGroupsSourceSelect"' in source
        assert 'id="measurementGroupsSummary"' in source
        assert 'id="measurementGroupsBody"' in source
        assert 'id="measurementGroupsSuggestBtn"' in source
        assert 'id="measurementGroupsCloseBtn"' in source
        assert 'id="measurementGroupsCloseFooterBtn"' in source

    def test_edit_drawer_markup_exists(self):
        source = _source()
        assert 'id="wwMgDrawer"' in source
        assert 'id="wwMgDrawerBackdrop"' in source
        assert 'id="wwMgDrawerBody"' in source
        assert 'id="wwMgDrawerError"' in source
        assert 'id="wwMgDrawerSaveBtn"' in source
        assert 'id="wwMgDrawerCancelBtn"' in source

    def test_toolbar_gains_the_new_primary_entry_point(self):
        source = _source()
        assert 'id="wwManageMeasurementGroupsBtn"' in source
        assert "Manage Per-Unit / Measurement Groups" in source


class TestDec049CoexistenceUnchanged:
    """Task section 24: the legacy source-wide modal must remain fully
    reachable, never deleted, only de-emphasized."""

    def test_legacy_menu_item_still_exists_and_still_opens_the_old_modal(self):
        source = _source()
        assert 'id="wwManagePerUnitBasesBtn"' in source
        assert "Legacy source-wide base settings" in source
        # Still wired to the ORIGINAL, unmodified open function.
        wiring = _function_body(source, 'document.getElementById("wwManagePerUnitBasesBtn")', "document.addEventListener")
        assert "wwOpenPerUnitProfilesModal()" in wiring

    def test_legacy_modal_functions_are_unmodified_and_still_present(self):
        source = _source()
        for fn in (
            "async function wwOpenPerUnitProfilesModal()",
            "function wwClosePerUnitProfilesModal()",
            "async function wwApplyPerUnitProfileEditor",
            "async function wwDeletePerUnitProfileEditor()",
        ):
            assert fn in source

    def test_per_unit_source_wide_api_paths_are_untouched(self):
        source = _source()
        assert '"/per-unit/sources"' in source
        assert '"/per-unit/sources/"' in source


class TestNoHiddenModificationsOnOpen:
    """Task section 21: opening the modal, switching source, or opening
    the Edit drawer must never write anything -- only GET requests."""

    def test_open_modal_never_issues_a_mutating_request(self):
        source = _source()
        body = _function_body(source, "async function wwOpenMeasurementGroupsModal()", "function wwCloseMeasurementGroupsModal()")
        assert '"POST"' not in body
        assert '"PUT"' not in body
        assert '"PATCH"' not in body
        assert '"DELETE"' not in body
        assert "fetchSourcesList()" in body
        assert "wwLoadAndRenderMeasurementGroupsBody()" in body

    def test_source_select_change_never_issues_a_mutating_request(self):
        source = _source()
        body = _function_body(
            source, "async function wwMeasurementGroupsSourceSelectChange(sourceId)", "async function wwOpenMeasurementGroupsModal()"
        )
        assert '"POST"' not in body
        assert '"PUT"' not in body
        assert '"PATCH"' not in body

    def test_open_drawer_never_issues_any_fetch_at_all(self):
        source = _source()
        body = _function_body(source, "function wwOpenMgDrawer(groupId)", "function wwCloseMgDrawer()")
        assert "fetch(" not in body


class TestSuggestionsAreExplicitOnly:
    """Task section 20: Slice 2 grouping stays standalone/user-triggered
    only -- never invoked on open, source-select, or Save."""

    def test_suggest_function_is_only_wired_to_its_own_button(self):
        source = _source()
        # Exactly two occurrences of the bare call form: the function's
        # own declaration line, and the one click-handler call site --
        # never a third call from anywhere else.
        assert source.count("wwSuggestMeasurementGroups()") == 2
        assert "async function wwSuggestMeasurementGroups()" in source
        wiring = _function_body(source, 'document.getElementById("measurementGroupsSuggestBtn")', ");")
        assert "wwSuggestMeasurementGroups()" in wiring

    def test_suggest_is_never_called_from_open_or_select_or_save(self):
        source = _source()
        for fn_sig, next_sig in (
            ("async function wwOpenMeasurementGroupsModal()", "function wwCloseMeasurementGroupsModal()"),
            ("async function wwMeasurementGroupsSourceSelectChange(sourceId)", "async function wwOpenMeasurementGroupsModal()"),
            ("async function wwSaveMgDrawer()", "\n\n        // \"Reset Time View\""),
        ):
            body = _function_body(source, fn_sig, next_sig)
            assert "wwSuggestMeasurementGroups" not in body

    def test_suggest_endpoint_path_matches_the_backend_router(self):
        source = _source()
        body = _function_body(source, "async function wwSuggestMeasurementGroups()", "// ---- Edit drawer")
        assert "/measurement-groups/suggest" in body
        assert '"POST"' in body


class TestGroupingStatusPromotionOnSave:
    """Canonical document section 15: saving a base configuration is
    what promotes a suggested/needs_review group to confirmed -- never
    a separate confirmation step, and never touching an already-manual/
    confirmed group's own status."""

    def test_save_promotes_suggested_or_needs_review_only(self):
        source = _source()
        body = _function_body(source, "async function wwSaveMgDrawer()", "\n\n        // \"Reset Time View\"")
        assert 'state.originalStatus === "suggested" || state.originalStatus === "needs_review"' in body
        assert '"status": "confirmed"' in body or "status: \"confirmed\"" in body

    def test_edit_state_captures_the_original_status_for_both_kinds(self):
        source = _source()
        body = _function_body(source, "function wwMgGroupToEditState(group)", "function wwMgModeRow(")
        assert body.count("originalStatus: group.status") == 2


class TestVoltageAndCurrentConfigPayloads:
    def test_voltage_config_put_targets_the_correct_endpoint(self):
        source = _source()
        body = _function_body(source, "async function wwSaveMgDrawer()", "\n\n        // \"Reset Time View\"")
        assert '"/voltage-config"' in body
        assert "nominal_voltage_ll_kv: state.nominalKv" in body
        assert "reference_mode: state.referenceMode" in body

    def test_current_config_put_dispatches_on_method(self):
        source = _source()
        body = _function_body(source, "async function wwSaveMgDrawer()", "\n\n        // \"Reset Time View\"")
        assert '"/current-config"' in body
        assert "body.equipment_rating_mva = state.equipmentRatingMva" in body
        assert "body.linked_voltage_group_id = state.linkedVoltageGroupId" in body
        assert "body.manual_voltage_base_kv = state.manualVoltageBaseKv" in body
        assert "body.manual_ibase_ka = state.manualIbaseKa" in body

    def test_no_ct_vt_method_exists_anywhere_in_the_new_code(self):
        """Task section 13/41: only equipment_rating/manual/none --
        never a CT-primary or ratio-based method."""
        source = _source()
        body = _function_body(source, "let wwMgSourcesList = []", "// \"Reset Time View\"")
        for forbidden in ("ct_primary", "ct_ratio", "vt_ratio", "ctPrimary", "ctRatio", "vtRatio"):
            assert forbidden not in body

    def test_linked_voltage_group_dropdown_is_scoped_to_the_same_source(self):
        source = _source()
        body = _function_body(source, "function wwMgLinkableVoltageGroups()", "// Section 18")
        # Reads from the SAME source's own already-fetched group list --
        # never a second, cross-source fetch.
        assert "wwMgGroupsForSelectedSource()" in body


class TestCancelDiscardsUnsavedEdits:
    def test_cancel_button_calls_close_with_no_save_call(self):
        source = _source()
        wiring = _function_body(source, 'document.getElementById("wwMgDrawerCancelBtn")', ");")
        assert "wwCloseMgDrawer" in wiring
        assert "wwSaveMgDrawer" not in wiring

    def test_close_drawer_never_issues_a_network_request(self):
        source = _source()
        body = _function_body(source, "function wwCloseMgDrawer()", "async function wwSaveMgDrawer()")
        assert "fetch(" not in body

    def test_escape_closes_the_drawer_before_the_modal_behind_it(self):
        source = _source()
        # The WIRING block's own comment (not the earlier JS-module-level
        # comment of the same prefix) -- scoped precisely so an unrelated,
        # earlier "// Phase 2C-B1/C1" comment elsewhere in the file can
        # never truncate this slice short.
        body = _function_body(
            source,
            'document.getElementById("wwManageMeasurementGroupsBtn").addEventListener',
            "// Phase 2C-B1/C1: Grouped/Separate/Custom layout mode.",
        )
        drawer_check_index = body.index('wwCloseMgDrawer(); return;')
        modal_check_index = body.index("wwCloseMeasurementGroupsModal();", drawer_check_index)
        assert drawer_check_index < modal_check_index


class TestWorkspaceResetLifecycle:
    def test_start_new_workspace_clears_measurement_groups_and_closes_the_modal(self):
        source = _source()
        body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit")
        reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
        assert "ww.measurementGroups.clear();" in reset_branch
        assert "wwCloseMeasurementGroupsModal();" in reset_branch

    def test_measurement_groups_map_is_declared_in_ww_state(self):
        source = _source()
        assert "measurementGroups: new Map()," in source


class TestNoCrossSourceLeakageInMarkup:
    def test_source_select_change_reloads_the_group_list_for_the_new_source(self):
        source = _source()
        body = _function_body(
            source, "async function wwMeasurementGroupsSourceSelectChange(sourceId)", "async function wwOpenMeasurementGroupsModal()"
        )
        assert "wwMgSelectedSourceId = sourceId;" in body
        assert "wwLoadAndRenderMeasurementGroupsBody();" in body


class TestInputSuffixGroupAlignment:
    """UX follow-up: `.ww-pu-value-suffix-group`/`.ww-pu-suffix` is the
    ONE shared input-plus-unit-addon pattern used everywhere in this
    file (legacy Per-Unit modal's Voltage/Apparent-Power/Direct-Current
    Base fields, and every Measurement Group drawer field -- Nominal
    Voltage/Equipment Rating/Manual Voltage Base/Manual Ibase). Matching
    padding/font-size alone was proven (by direct pixel measurement in
    a real browser) NOT sufficient to equalize the input and suffix
    box heights -- only an explicit, identical `height` on both sides
    produced a pixel-exact match. This test locks that in so a future
    edit to either rule can't silently reintroduce the mismatch."""

    def test_input_and_suffix_share_an_explicit_identical_height(self):
        source = _source()
        group_rule = _function_body(source, ".ww-pu-value-suffix-group input {", ".ww-pu-suffix {")
        suffix_rule = _function_body(source, ".ww-pu-suffix {", "/* Phase 5C-UAT2")
        assert "height: 32px;" in group_rule
        assert "height: 32px;" in suffix_rule

    def test_input_and_suffix_share_the_same_font_size(self):
        source = _source()
        suffix_rule = _function_body(source, ".ww-pu-suffix {", "/* Phase 5C-UAT2")
        # Matches .ww-cc-field input's own font-size -- no larger
        # typography introduced anywhere by this fix.
        assert "font-size: 0.75rem;" in suffix_rule

    def test_this_is_the_only_input_suffix_css_rule_in_the_file(self):
        """Confirms a single shared fix, not one-off per-field styling."""
        source = _source()
        assert source.count(".ww-pu-suffix {") == 1
        assert source.count(".ww-pu-value-suffix-group {") == 1
