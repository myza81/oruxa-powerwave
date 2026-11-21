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


class TestModalAndDrawerRemovedInPuUi001:
    """PU-UI-001 Step C: the MG modal overlay and the MG edit drawer are
    removed.  Recording Details is now the sole Measurement Group
    configuration surface."""

    def test_measurement_groups_modal_markup_removed(self):
        source = _source()
        assert 'id="measurementGroupsOverlay"' not in source
        assert 'id="measurementGroupsSourceSelect"' not in source
        assert 'id="measurementGroupsSummary"' not in source
        assert 'id="measurementGroupsBody"' not in source
        assert 'id="measurementGroupsSuggestBtn"' not in source
        assert 'id="measurementGroupsCloseBtn"' not in source
        assert 'id="measurementGroupsCloseFooterBtn"' not in source

    def test_edit_drawer_markup_removed(self):
        source = _source()
        assert 'id="wwMgDrawer"' not in source
        assert 'id="wwMgDrawerBackdrop"' not in source
        assert 'id="wwMgDrawerBody"' not in source
        assert 'id="wwMgDrawerSaveBtn"' not in source
        assert 'id="wwMgDrawerCancelBtn"' not in source

    def test_mg_open_close_functions_removed(self):
        source = _source()
        assert 'async function wwOpenMeasurementGroupsModal()' not in source
        assert 'function wwCloseMeasurementGroupsModal()' not in source
        assert 'function wwOpenMgDrawer(' not in source
        assert 'function wwCloseMgDrawer()' not in source
        assert 'async function wwSaveMgDrawer()' not in source

    def test_mg_render_and_state_functions_removed(self):
        source = _source()
        assert 'let wwMgSourcesList' not in source
        assert 'let wwMgSelectedSourceId' not in source
        assert 'function wwMgGroupsForSelectedSource()' not in source
        assert 'function wwMgLinkableVoltageGroups()' not in source
        assert 'function wwRenderMeasurementGroupsBody(' not in source
        assert 'function wwLoadAndRenderMeasurementGroupsBody(' not in source
        assert 'async function wwMeasurementGroupsSourceSelectChange(' not in source
        assert 'async function wwSuggestMeasurementGroups()' not in source
        assert 'function wwRenderMgDrawerVoltage(' not in source
        assert 'function wwRenderMgDrawerCurrent(' not in source
        assert 'function wwMgGroupToEditState(' not in source

    def test_rd_navigation_helpers_replace_mg_modal_entry_points(self):
        source = _source()
        assert 'function wwNavigateToRdForGroup(' in source

    def test_toolbar_exposes_eng_pu_toggle_only_no_hub_entry(self):
        """PU-UI-001 Slice B: the Hub (#wwOpenPerUnitSettingsBtn) has been
        retired; the toolbar's unit mode area now contains only the ENG/PU
        toggle.  PU configuration is managed via Recording Details."""
        source = _source()
        assert 'id="wwUnitModeMenu"' not in source
        assert 'id="wwOpenPerUnitSettingsBtn"' not in source
        assert 'id="wwManageMeasurementGroupsBtn"' not in source
        assert 'id="wwManagePerUnitBasesBtn"' not in source
        # ENG/PU toggle buttons remain
        assert 'id="wwUnitEngineeringBtn"' in source
        assert 'id="wwUnitPerUnitBtn"' in source


class TestDec049CoexistenceAfterPuUi001:
    """PU-UI-001 Steps B and C: the SD modal and MG modal are removed.
    DEC-049 source-wide resolution continues on the backend for ungrouped
    channels (DEC-051) but its frontend editor surface is gone.
    Recording Details is the sole configuration entry point."""

    def test_source_default_modal_removed_in_step_b(self):
        source = _source()
        assert 'id="perUnitProfilesOverlay"' not in source
        assert 'async function wwOpenPerUnitProfilesModal(' not in source
        assert 'function wwClosePerUnitProfilesModal()' not in source
        assert 'async function wwApplyPerUnitProfileEditor()' not in source
        assert 'async function wwDeletePerUnitProfileEditor()' not in source

    def test_no_user_facing_legacy_wording_remains(self):
        source = _source()
        assert "Legacy source-wide base settings" not in source
        assert 'class="ww-split-menu-item--legacy"' not in source

    def test_per_unit_source_wide_api_paths_removed_with_sd_modal(self):
        """The SD modal was the only frontend caller of these paths;
        removing it means the path strings are gone too."""
        source = _source()
        assert '"/per-unit/sources"' not in source
        assert '"/per-unit/sources/"' not in source


class TestMgModalFunctionsRemovedInPuUi001:
    """PU-UI-001 Step C: modal-open, source-select-change, and
    drawer-open functions are all gone.  These tests confirm removal."""

    def test_open_modal_function_removed(self):
        source = _source()
        assert 'async function wwOpenMeasurementGroupsModal()' not in source
        assert 'function wwCloseMeasurementGroupsModal()' not in source

    def test_source_select_change_function_removed(self):
        source = _source()
        assert 'async function wwMeasurementGroupsSourceSelectChange(' not in source

    def test_open_drawer_function_removed(self):
        source = _source()
        assert 'function wwOpenMgDrawer(' not in source
        assert 'function wwCloseMgDrawer()' not in source


class TestSuggestFunctionRemovedInPuUi001:
    """PU-UI-001 Step C: `wwSuggestMeasurementGroups` was wired only to
    the MG modal's Suggest button, which is now gone.  Suggestion is
    performed via Recording Details or the Compliance bootstrap path."""

    def test_mg_modal_suggest_function_removed(self):
        source = _source()
        assert 'async function wwSuggestMeasurementGroups()' not in source
        assert 'id="measurementGroupsSuggestBtn"' not in source

    def test_suggest_still_reachable_via_compliance_bootstrap(self):
        """Compliance bootstrap (`wwComplianceSuggestGroupsForSource`) uses
        the same /measurement-groups/suggest backend endpoint."""
        source = _source()
        assert "measurement-groups/suggest" in source


class TestMgDrawerSaveFunctionRemovedInPuUi001:
    """PU-UI-001 Step C: `wwSaveMgDrawer`, `wwMgGroupToEditState`, and
    related helpers are removed with the MG drawer.  The equivalent
    PUT /voltage-config and PUT /current-config calls now live in
    Recording Details."""

    def test_save_drawer_function_removed(self):
        source = _source()
        assert 'async function wwSaveMgDrawer()' not in source
        assert 'function wwMgGroupToEditState(' not in source

    def test_voltage_config_endpoint_still_used_by_rd(self):
        """Recording Details uses the same /voltage-config endpoint."""
        source = _source()
        assert '"/voltage-config"' in source

    def test_current_config_endpoint_still_used_by_rd(self):
        """Recording Details uses the same /current-config endpoint."""
        source = _source()
        assert '"/current-config"' in source


class TestMgModalStateVariablesRemovedInPuUi001:
    """MG modal-scoped state variables are removed with the modal."""

    def test_mg_sources_list_and_state_variables_removed(self):
        source = _source()
        assert 'let wwMgSourcesList' not in source
        assert 'let wwMgSelectedSourceId' not in source
        assert 'let wwMgEditState' not in source

    def test_no_ct_vt_method_in_mg_configuration_code(self):
        """Task section 13/41: MG configuration only uses equipment_rating/
        manual/none -- never a CT-primary or ratio-based method.  The check
        is scoped to the /current-config payload builder in Recording Details
        (the replacement for the removed wwSaveMgDrawer), not the whole file
        (CT/VT metadata objects exist in calibration code elsewhere)."""
        source = _source()
        # Find the current-config section of RD's apply handler.
        start = source.index('"/current-config"')
        end = source.index("\n        }", start)
        segment = source[start:end]
        for forbidden in ("ct_primary_a", "ct_ratio", "ctPrimary", "ctRatio"):
            assert forbidden not in segment

    def test_mg_linkable_voltage_groups_function_removed(self):
        source = _source()
        assert 'function wwMgLinkableVoltageGroups()' not in source


class TestMgDrawerButtonsRemovedInPuUi001:
    """PU-UI-001 Step C: drawer buttons and their event handlers are
    removed with the drawer."""

    def test_drawer_buttons_removed(self):
        source = _source()
        assert 'id="wwMgDrawerCancelBtn"' not in source
        assert 'id="wwMgDrawerSaveBtn"' not in source
        assert 'id="wwMgDrawerCloseBtn"' not in source
        assert 'id="wwMgDrawerBackdrop"' not in source

    def test_drawer_open_close_functions_removed(self):
        source = _source()
        assert 'function wwCloseMgDrawer()' not in source
        assert 'function wwOpenMgDrawer(' not in source


class TestWorkspaceResetLifecycle:
    def test_start_new_workspace_clears_measurement_groups_no_modal_close(self):
        """PU-UI-001 Step C: `wwCloseMeasurementGroupsModal()` is removed
        with the modal; `ww.measurementGroups.clear()` remains because
        the data Map is still used by Recording Details."""
        source = _source()
        body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit")
        reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
        assert "ww.measurementGroups.clear();" in reset_branch
        assert "wwCloseMeasurementGroupsModal();" not in reset_branch

    def test_measurement_groups_map_is_declared_in_ww_state(self):
        source = _source()
        assert "measurementGroups: new Map()," in source


class TestNoCrossSourceLeakageAfterPuUi001:
    def test_mg_source_select_change_function_removed_no_cross_source_leak(self):
        """PU-UI-001 Step C: `wwMeasurementGroupsSourceSelectChange` was the
        modal-scoped source picker -- removed with the modal.  Cross-source
        isolation is now enforced by Recording Details' own scoped state."""
        source = _source()
        assert 'async function wwMeasurementGroupsSourceSelectChange(' not in source
        assert 'let wwMgSelectedSourceId' not in source


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
