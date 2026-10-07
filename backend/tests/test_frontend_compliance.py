"""Static structural regression checks for Compliance & Capability --
Slice 1 (workspace shell only, frontend/index.html).

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses -- this repo has no
browser/DOM test runner for the single-file frontend. Real navigation/
layout/responsive BEHAVIOR is covered separately by
`browser-tests/compliance.spec.js` (Playwright, real browser) -- these
tests only guard structural invariants a source-text assertion CAN
meaningfully verify: top-level menu registration/order, the Compliance
page/panel's existence, the Voltage sub-nav, and the five workflow
section identifiers in order. Deliberately avoids brittle whole-markup
snapshots (task's own explicit instruction) -- assertions target small,
specifically-scoped substrings, never a full-file diff.
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


def _compliance_page(source: str) -> str:
    """The whole #pageCompliance HTML section, from its own opening tag
    to the next top-level page section (#pageDataPreparation, which
    immediately follows it in the DOM)."""
    start = source.index('<section id="pageCompliance"')
    end = source.index('<section id="pageDataPreparation"', start)
    return source[start:end]


class TestComplianceTopLevelNav:
    def test_compliance_nav_button_exists_after_analysis(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        analysis_index = nav_list.index('id="mainNavAnalysisBtn"')
        compliance_index = nav_list.index('id="mainNavComplianceBtn"')
        assert analysis_index < compliance_index
        assert '<span class="shell-nav-label">Compliance</span>' in nav_list

    def test_full_main_nav_order_matches_requested_sequence(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        labels = ["Recordings", "Waveform", "Table", "Calculated Channels", "Analysis", "Compliance", "Calculator"]
        positions = [nav_list.index(f'<span class="shell-nav-label">{label}</span>') for label in labels]
        assert positions == sorted(positions)

    def test_shellSetCurrentPage_handles_compliance_page(self):
        source = _source()
        assert 'page !== "compliance"' in source
        assert 'document.getElementById("pageCompliance").hidden = page !== "compliance";' in source
        assert 'setShellNavCurrent("mainNavComplianceBtn", page === "compliance")' in source
        assert (
            'document.getElementById("mainNavComplianceBtn").addEventListener'
            '("click", () => shellSetCurrentPage("compliance"));'
        ) in source

    def test_compliance_page_does_not_touch_analysis_or_playback_state(self):
        """Compliance opening must never initialize/alter Playback,
        Analysis Input Source, Engineering Context analyzer state,
        Sequence state, or Distance state (task's own explicit isolation
        requirement) -- verified by confirming the on-entry render hook
        calls nothing beyond its own nav-sync helper."""
        source = _source()
        render_fn = _function_body(source, "function wwRenderCompliancePage() {", "\n        }")
        assert "wwAnalysisLoadContexts" not in render_fn
        assert "wwPlayback" not in render_fn
        assert "wwPhasorState" not in render_fn
        assert "wwSequenceState" not in render_fn
        assert "wwDistanceState" not in render_fn


class TestCompliancePageStructure:
    def test_compliance_page_exists_hidden_with_expected_heading(self):
        source = _source()
        assert '<section id="pageCompliance" aria-label="Compliance" hidden>' in source
        page = _compliance_page(source)
        assert "<h2>Compliance</h2>" in page

    def test_voltage_is_the_sole_compliance_function_and_is_active(self):
        source = _source()
        page = _compliance_page(source)
        nav = _function_body(page, 'aria-label="Compliance function"', "</nav>")
        assert nav.count('class="ww-analysis-type-item') == 1
        assert 'id="wwComplianceTypeVoltageBtn"' in nav
        assert 'class="ww-analysis-type-item active"' in nav
        assert 'aria-current="true"' in nav

    def test_voltage_function_icon_uses_the_owner_asset_not_inline_svg(self):
        """Branding update (owner ticket): the Voltage function nav
        item's former hand-drawn inline <svg> is replaced by a
        data-ww-icon placeholder resolving to the owner-supplied
        frontend/assets/icons/compliance/voltage.svg, same mask-image
        registry mechanism the Analysis page's own analyzer-type icons
        already use (DEC-152) -- never a redrawn icon, never a second
        icon system. Label, click handler, routing, tooltip,
        accessibility and layout are all untouched by this change."""
        source = _source()
        page = _compliance_page(source)
        btn = _function_body(page, 'id="wwComplianceTypeVoltageBtn"', "</button>")
        assert '<svg' not in btn
        assert 'data-ww-icon="COMPLIANCE_VOLTAGE"' in btn
        assert 'class="ww-analysis-type-icon" aria-hidden="true"' in btn
        assert '<span class="ww-analysis-type-label">Voltage</span>' in btn

        registry_idx = source.index("const WW_TOOL_ICONS = {")
        registry = source[registry_idx : source.index("};", registry_idx)]
        assert 'COMPLIANCE_VOLTAGE: "assets/icons/compliance/voltage.svg",' in registry
        asset_path = FRONTEND.parent / "assets" / "icons" / "compliance" / "voltage.svg"
        assert asset_path.is_file()

    def test_voltage_panel_heading_is_provisional_wording(self):
        source = _source()
        page = _compliance_page(source)
        assert "Voltage Compliance &amp; Capability" in page

    def test_workflow_sections_exist_in_order_reference_first(self):
        """DEC-167: Reference Layers come FIRST (Reference defines),
        Measurement second (Measurement satisfies); Event Alignment is no
        longer a sibling card but a subsection inside Measurement."""
        source = _source()
        page = _compliance_page(source)
        labels = ["Reference Layers", "Measurement", "Comparison Chart"]
        positions = [page.index(f"<h2>{label}</h2>") for label in labels]
        assert positions == sorted(positions)
        assert "<h2>Event Alignment</h2>" not in page
        assert 'id="wwComplianceEventAlignmentCard"' not in page

    def test_event_alignment_is_a_subsection_of_the_measurement_card(self):
        source = _source()
        page = _compliance_page(source)
        measurement = _function_body(page, 'id="wwComplianceMeasurementCard"', "</section>")
        assert 'id="wwComplianceEventAlignmentSection"' in measurement
        assert '<h3 class="ww-compliance-subheading">Event Alignment</h3>' in measurement
        assert 'id="wwComplianceEventAlignmentEmptyState"' in measurement
        assert 'id="wwComplianceAlignmentControls"' in measurement
        # Readiness comes before Event Alignment inside the card.
        assert measurement.index('id="wwComplianceReadiness"') < measurement.index('id="wwComplianceEventAlignmentSection"')

    def test_measurement_shows_neutral_empty_state(self):
        """Static default (2026-09-20 UAT correction, wording refined
        2026-09-23): the FIRST thing the engineer must resolve is now a
        Bay/Measurement Group, not an assessment quantity -- "No
        assessment quantity selected" is still a real, reachable state,
        just no longer the static markup's own default (see
        TestComplianceMeasurementGroupSelectorStructure for the group-
        selection empty states)."""
        source = _source()
        page = _compliance_page(source)
        assert "No Voltage Measurement Group is available for this workspace." in page
        # DEC-167: there is no assessment-quantity step any more.
        assert "No assessment quantity selected" not in source

    def test_reference_layers_shows_empty_state_and_active_add_button(self):
        """Compliance Slice 3: Reference Layers is no longer a Slice 1/2
        disabled placeholder -- "+ Add Reference" is a real, ENABLED
        entry point (see TestComplianceReferenceLayersStructure for the
        full Slice 3 structural surface)."""
        source = _source()
        page = _compliance_page(source)
        assert "No reference added yet." in page
        add_btn = _function_body(page, 'id="wwComplianceAddReferenceBtn"', "</button>")
        assert "disabled" not in add_btn
        assert "+ Add Reference" in add_btn

    def test_event_alignment_shows_empty_state_no_automatic_detection(self):
        source = _source()
        page = _compliance_page(source)
        # DEC-170: Compliance-local alignment; starts "Not aligned", never automatic.
        assert 'id="wwComplianceEventAlignmentEmptyState"' in page
        assert "Not aligned" in page
        assert "Select the disturbance event on the Comparison Chart and set it as Reference t=0." in page
        assert "wwComplianceDetectEvent" not in source
        assert "wwComplianceAutoAlign" not in source

    def test_comparison_chart_present_and_empty(self):
        """Compliance Slice 3: the static default empty state now reads
        in terms of Reference Layers (the chart can render before any
        Measurement/voltage assessment exists at all -- mid-conversation
        product requirement), not the old Slice 1/2 "No voltage
        assessment configured" wording."""
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceChartWrap"' in page
        assert 'id="wwComplianceChartPlot"' in page
        assert "No reference layers to display" in page

    def test_results_section_is_removed_until_evaluation_semantics_are_defined(self):
        """Owner decision (UAT cleanup): no Results card -- not even a
        placeholder -- until PASS/FAIL semantics are explicitly approved."""
        source = _source()
        page = _compliance_page(source)
        assert "<h2>Results</h2>" not in page
        assert "wwComplianceResultsPanel" not in source
        assert "wwComplianceResultsEmptyState" not in source
        assert "ww-compliance-results-panel" not in source
        assert "Results will appear after" not in source
        for verdict in ("Compliant", "Boundary Breached", "Within Capability"):
            assert verdict not in page

    def test_chart_has_no_note_or_legend_strip_below_plotly(self):
        """The Comparison Chart owns the full right-panel height: the HTML
        legend list and the measurement/alignment note are gone (Plotly's own
        legend and the 'Reference t=0' label carry that information)."""
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceChartLegend"' not in page
        assert 'id="wwComplianceChartMeasurementNote"' not in page
        assert "wwRefRenderChartLegend" not in source
        assert "wwComplianceChartMeasurementMessage" not in source
        assert "Measurement aligned: recording" not in source

    def test_left_navigation_card_stretches_with_the_workspace(self):
        """The Functions card shares the shell's height (flex stretch), with no
        fixed pixel height of its own on desktop."""
        source = _source()
        assert "#pageCompliance .ww-analysis-type-nav { min-height: 0; }" in source


class TestComplianceOutOfScopeSlice1:
    def test_no_profile_evaluation_or_breach_logic_in_the_compliance_page(self):
        """Checks for real implementation identifiers, not the scope-
        boundary explained in this slice's own HTML comments (which
        legitimately names LVRT/HVRT to document that they are NOT
        drawn)."""
        source = _source()
        page = _compliance_page(source)
        for forbidden in (
            "profile_json", "profileJson",
            "malaysian_grid_code", "MalaysianGridCode",
            "wwComplianceEvaluate", "wwComplianceBreach", "wwComplianceMargin",
        ):
            assert forbidden not in page

    def test_no_backend_endpoint_or_persistence_added_for_compliance(self):
        source = _source()
        assert "/api/v1/compliance" not in source
        assert "localStorage" not in _compliance_page(source)


class TestComplianceMeasurementReadinessStructure:
    """DEC-167 -- Measurement is driven by the active Reference(s). The
    Slice 2 Assessment Quantity workflow (independent quantity select,
    Input/Input Type/Derived As/Base/Assessment Unit rows) is retired:
    "Reference defines. Measurement satisfies." """

    def test_independent_quantity_unit_and_representation_selectors_are_gone(self):
        source = _source()
        page = _compliance_page(source)
        measurement = _function_body(page, 'id="wwComplianceMeasurementCard"', "</section>")
        for retired in (
            "wwComplianceMeasurementSelect", "wwComplianceMeasurementField", "wwComplianceMeasurementSummary",
            "Assessment quantity", "Assessment Unit", "Derived As",
        ):
            assert retired not in measurement, retired
        # The only <select> left in the card is the Bay / Measurement Group picker.
        assert measurement.count("<select") == 1
        for retired_fn in (
            "wwComplianceLoadQuantities", "wwComplianceRenderQuantityOptions", "wwComplianceOnQuantityChange",
            "wwComplianceFetchMeasurement", "wwComplianceRenderMeasurement(",
        ):
            assert retired_fn not in source, retired_fn
        assert "/compliance/voltage/quantities" not in source

    def test_readiness_and_requirement_elements_exist_and_start_hidden(self):
        source = _source()
        page = _compliance_page(source)
        card = _function_body(page, 'id="wwComplianceMeasurementCard"', "</section>")
        assert 'id="wwComplianceRequirements" hidden' in card
        assert 'id="wwComplianceReadiness" hidden' in card
        for element_id in (
            "wwComplianceRequirementList", "wwComplianceReadinessStatus", "wwComplianceReadinessRefs",
            "wwCompliancePrepareBtn", "wwComplianceConfigureBaseBtn", "wwCompliancePrepareError",
        ):
            assert f'id="{element_id}"' in card
        assert 'id="wwCompliancePrepareBtn" hidden' in card
        assert 'id="wwComplianceConfigureBaseBtn" hidden' in card
        assert "Requirements from active references" in card
        assert "Measurement readiness" in card

    def test_requirements_are_read_only_text_never_inputs(self):
        source = _source()
        page = _compliance_page(source)
        requirements = _function_body(page, 'id="wwComplianceRequirements"', "</div>")
        assert "<input" not in requirements and "<select" not in requirements

    def test_readiness_status_vocabulary(self):
        source = _source()
        for message in (
            "✓ Ready for assessment", "⚠ Action required", "✕ Measurement cannot satisfy this reference",
        ):
            assert message in source

    def test_required_readiness_js_functions_exist(self):
        source = _source()
        for fn in (
            "function wwComplianceRequirementHtml(",
            "function wwComplianceRenderRequirements(",
            "function wwComplianceRefreshReadiness(",
            "function wwComplianceRenderReadiness(",
            "async function wwCompliancePrepareMeasurement(",
            "async function wwComplianceOpenConfigureBase(",
        ):
            assert fn in source

    def test_endpoints_are_workspace_scoped_never_engineering_context_scoped(self):
        """Compliance still does not register as an Engineering Context
        consumer (DEC-100/DEC-101/DEC-102/DEC-167) -- none of its calls
        embed an engineering_context_id; the backend's single read-only
        context lookup (DEC-167) is server-side only."""
        source = _source()
        assert "/compliance/voltage/measurement-groups" in source
        assert "/compliance/voltage/readiness" in source
        assert "/compliance/voltage/prepare" in source
        for fn_start in (
            "function wwComplianceRefreshReadiness(",
            "async function wwCompliancePrepareMeasurement(",
            "function wwComplianceLoadGroups(",
        ):
            body = _function_body(source, fn_start, "\n        }")
            assert "engineering-contexts" not in body
            assert "engineering_context_id" not in body

    def test_prepare_goes_through_the_backend_and_refreshes_shared_calculated_channels(self):
        source = _source()
        prepare = _function_body(source, "async function wwCompliancePrepareMeasurement(", "\n        }")
        assert "/compliance/voltage/prepare" in prepare
        # Created channels are ordinary Calculated Channels: the shared frontend
        # state is refreshed from the backend, never a Compliance-private store.
        assert "wwFetchCalculatedChannels()" in prepare
        assert "localStorage" not in prepare

    def test_configure_base_reuses_the_existing_group_editor_never_a_new_one(self):
        source = _source()
        page = _compliance_page(source)
        configure = _function_body(source, "async function wwComplianceOpenConfigureBase(", "\n        }")
        assert "wwOpenMeasurementGroupsModal()" in configure
        assert "wwOpenMgDrawer(" in configure
        for forbidden in ("voltage-config", "nominal_voltage_ll_kv", "nominalKv"):
            assert forbidden not in configure
        assert "wwMgDrawer" not in page and "measurementGroupsOverlay" not in page

    def test_group_editor_save_refreshes_compliance_readiness_when_active(self):
        source = _source()
        save = _function_body(source, "async function wwSaveMgDrawer() {", "\n        }")
        assert 'shell.currentPage === "compliance"' in save
        assert "wwComplianceRefreshReadiness()" in save

    def test_layer_changes_recheck_readiness(self):
        source = _source()
        refresh = _function_body(source, "async function wwRefRefreshLayersAndChart() {", "\n        }")
        assert "wwComplianceRefreshReadiness()" in refresh

    def test_render_compliance_page_still_never_touches_analyzer_state(self):
        source = _source()
        render_fn = _function_body(source, "function wwRenderCompliancePage() {", "\n        }")
        assert "wwAnalysisLoadContexts" not in render_fn
        assert "wwAnalysisRegisterContextConsumer" not in render_fn
        assert "wwPlayback" not in render_fn
        assert "wwPhasorState" not in render_fn
        assert "wwSequenceState" not in render_fn
        assert "wwDistanceState" not in render_fn
        assert "wwComplianceLoadGroups" in render_fn


class TestComplianceMeasurementGroupSelectorStructure:
    """2026-09-20 UAT correction -- Bay/Measurement Group selection
    scopes role resolution, per owner UAT: a bare Assessment Quantity
    selector was ambiguous once more than one bay/Measurement Group
    exists in the workspace."""

    def test_group_select_exists_above_requirements_and_readiness_and_starts_hidden(self):
        source = _source()
        page = _compliance_page(source)
        card = _function_body(page, 'id="wwComplianceMeasurementCard"', "</section>")
        group_index = card.index('id="wwComplianceGroupField"')
        assert group_index < card.index('id="wwComplianceRequirements"')
        assert group_index < card.index('id="wwComplianceReadiness"')
        assert 'id="wwComplianceGroupField" hidden' in card
        group_select = _function_body(card, 'id="wwComplianceGroupSelect"', "</select>")
        assert "disabled" not in group_select
        assert 'value="">Select a Bay / Measurement Group' in group_select
        assert group_select.count("<option") == 1  # populated at runtime only

    def test_group_field_uses_the_task_specified_label(self):
        source = _source()
        page = _compliance_page(source)
        assert "Bay / Measurement Group</span>" in page

    def test_required_group_selector_js_functions_exist(self):
        source = _source()
        for fn in (
            "function wwComplianceLoadGroups(",
            "function wwComplianceRenderGroupOptions(",
            "function wwComplianceOnGroupChange(",
            "function wwComplianceRenderMeasurementCardState(",
            "function wwComplianceShowGroupsFetchError(",
        ):
            assert fn in source

    def test_readiness_fetch_sends_measurement_group_id(self):
        source = _source()
        readiness_fetch = _function_body(source, "function wwComplianceRefreshReadiness(", "\n        }")
        assert "measurement_group_id" in readiness_fetch

    def test_auto_select_only_when_exactly_one_usable_group(self):
        """task section 5: auto-select only when exactly one USABLE
        candidate exists -- never guess among multiple, never skip a
        genuine single candidate, and never count a review-required
        group as a candidate (2026-09-23 correction: the dropdown is
        built from wwComplianceUsableGroups(), not the raw list)."""
        source = _source()
        render_fn = _function_body(source, "function wwComplianceRenderGroupOptions() {", "\n        }")
        assert "usable.length === 1" in render_fn
        assert "wwComplianceUsableGroups()" in render_fn

    def test_required_empty_state_strings_present(self):
        source = _source()
        for message in (
            "No Voltage Measurement Group is available for this workspace.",
            "Voltage Measurement Groups were found, but they require review before use.",
            "Select a Bay / Measurement Group to continue.",
        ):
            assert message in source


class TestComplianceMeasurementGroupBootstrapAndReviewState:
    """2026-09-23 UAT correction -- Compliance must not dead-end merely
    because the engineer never visited Manage Measurement Groups first;
    review-required groups must be distinguishable from a genuinely
    empty workspace, never silently collapsed into the same message."""

    def test_bootstrap_reuses_the_existing_suggest_endpoint_never_a_second_detector(self):
        source = _source()
        bootstrap_fn = _function_body(source, "async function wwComplianceBootstrapGroupsIfNeeded() {", "\n        }")
        assert "fetchSourcesList" in bootstrap_fn
        suggest_fn = _function_body(source, "function wwComplianceSuggestGroupsForSource(", "\n        }")
        assert "measurement-groups/suggest" in suggest_fn
        assert 'method: "POST"' in suggest_fn
        # No client-side name parsing/fabrication of any kind (task
        # section 13's own explicit prohibition).
        for forbidden in ("KPDN", "SLKS", "MCRS", "SGT1", ".split(", ".match(", "RegExp"):
            assert forbidden not in suggest_fn
            assert forbidden not in bootstrap_fn

    def test_load_groups_bootstraps_before_listing(self):
        source = _source()
        load_fn = _function_body(source, "async function wwComplianceLoadGroups() {", "\n        }")
        assert "wwComplianceBootstrapGroupsIfNeeded" in load_fn
        assert load_fn.index("wwComplianceBootstrapGroupsIfNeeded") < load_fn.index("measurement-groups")

    def test_usable_and_review_required_are_distinct_collections(self):
        source = _source()
        assert "function wwComplianceUsableGroups() {" in source
        assert "function wwComplianceReviewRequiredGroups() {" in source
        usable_fn = _function_body(source, "function wwComplianceUsableGroups() {", "\n        }")
        assert 'g.status !== "needs_review"' in usable_fn
        review_fn = _function_body(source, "function wwComplianceReviewRequiredGroups() {", "\n        }")
        assert 'g.status === "needs_review"' in review_fn

    def test_card_state_distinguishes_no_groups_from_review_required(self):
        source = _source()
        card_state_fn = _function_body(source, "function wwComplianceRenderMeasurementCardState() {", "\n        }")
        assert "usableCount === 0 && reviewCount === 0" in card_state_fn
        assert "usableCount === 0 && reviewCount > 0" in card_state_fn

    def test_manage_groups_button_exists_reuses_existing_modal_never_a_new_editor(self):
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceManageGroupsBtn" hidden' in page
        open_fn = _function_body(source, "function wwComplianceOpenManageGroups() {", "\n        }")
        assert "wwOpenMeasurementGroupsModal()" in open_fn
        # Never a second Measurement Group editor/drawer defined inside
        # the Compliance page section itself.
        compliance_page_text = page
        assert "wwMgDrawer" not in compliance_page_text
        assert "measurementGroupsOverlay" not in compliance_page_text

    def test_closing_the_management_modal_refreshes_compliance_only_when_active(self):
        source = _source()
        close_fn = _function_body(source, "function wwCloseMeasurementGroupsModal() {", "\n        }")
        assert 'shell.currentPage === "compliance"' in close_fn
        assert "wwComplianceLoadGroups()" in close_fn


class TestComplianceOutOfScopeSlice2:
    """task's own explicit Slice 2 scope boundary: only Measurement is
    implemented -- Reference Layers, Event Alignment, comparison curves,
    and compliance evaluation remain exactly the Slice 1 placeholders.

    Superseded IN PART by Compliance Slice 3 (see
    TestComplianceOutOfScopeSlice3 below): Reference Layers and the
    Comparison Chart's own static reference-curve rendering are now
    real, not placeholders. Event Alignment, Results, and every
    evaluation/breach/margin concept remain exactly as described here --
    kept verbatim as the accurate historical record of what Slice 2
    still excluded, not retroactively rewritten."""

    def test_event_alignment_is_compliance_local_and_set_starts_disabled(self):
        """Superseded Slice 2 placeholder check (DEC-170): the controls are
        real; "Set as Reference t=0" stays disabled until a measured point is
        selected, and no control is worded as Waveform t0."""
        source = _source()
        page = _compliance_page(source)
        controls = _function_body(page, 'id="wwComplianceAlignmentControls"', "</div>")
        # The explicit selection mode starts with "Select Event Point" (disabled until a
        # measured trace is plotted); "Set as Reference t=0" only exists while selecting.
        select_btn = _function_body(controls, 'id="wwComplianceAlignSelectBtn"', "</button>")
        assert "disabled" in select_btn and "Select Event Point" in select_btn
        set_btn = _function_body(controls, 'id="wwComplianceAlignSetBtn"', "</button>")
        assert "hidden" in set_btn and "Set as Reference t=0" in set_btn
        for label in ("Choose Again", "Change Alignment", "Cancel", "Clear Alignment"):
            assert label in controls
        fine = _function_body(page, 'id="wwComplianceAlignmentFineControls"', "</div>")
        assert "Shift Earlier" in fine and "Shift Later" in fine
        assert "Set t0 in Waveform" not in source

    def test_no_reference_profile_alignment_or_evaluation_logic_added(self):
        source = _source()
        page = _compliance_page(source)
        for forbidden in (
            "wwComplianceEvaluate", "wwComplianceBreach", "wwComplianceMargin",
            "wwComplianceSetT0", "wwComplianceDetectEvent", "wwComplianceAutoAlign",
            "malaysian_grid_code", "MalaysianGridCode",
        ):
            assert forbidden not in page

    def test_event_alignment_endpoint_is_compliance_scoped_never_waveform_t0(self):
        source = _source()
        assert "/api/v1/compliance" not in source
        assert "/compliance/voltage/event-alignment" in source


class TestComplianceOutOfScopeSlice3:
    """Compliance Slice 3's OWN explicit scope boundary (task section 18/
    19): Reference Profiles/Layers and static Comparison Chart rendering
    are real; Event Alignment, Results, and every evaluation/breach/
    tolerance/PASS-FAIL concept remain exactly the Slice 1 placeholders.
    No production Malaysia Grid Code (or any other named official
    requirement) built-in exists (task section 9)."""

    def test_no_evaluation_breach_tolerance_or_verdict_logic_added(self):
        source = _source()
        page = _compliance_page(source)
        for forbidden in (
            "wwComplianceEvaluate", "wwRefEvaluate", "wwRefBreach", "wwRefMargin", "wwRefTolerance",
            "wwComplianceBreach", "wwComplianceMargin", "wwComplianceSetT0",
            "wwComplianceDetectEvent", "wwComplianceAutoAlign",
        ):
            assert forbidden not in page
        for verdict in ("Compliant", "Boundary Breached", "Within Capability"):
            assert verdict not in page

    def test_no_malaysia_grid_code_or_other_named_official_requirement(self):
        """Task section 9's own explicit constraint: no production
        built-in profile may be fabricated from memory/assumptions. The
        empty production built-in directory is the authoritative proof
        (backend/tests/test_reference_profile_builtins.py); this is the
        frontend-side companion guard that no such name ever leaked into
        client-side code either."""
        source = _source()
        for forbidden in ("Malaysia Grid Code", "MalaysianGridCode", "malaysian_grid_code"):
            assert forbidden not in source

    def test_event_alignment_remains_and_results_are_absent(self):
        source = _source()
        page = _compliance_page(source)
        assert "Not aligned" in page
        assert "wwComplianceResultsPanel" not in source

    def test_reference_layers_endpoint_exists_but_no_evaluation_endpoint(self):
        source = _source()
        assert "/reference-profiles" in source
        assert "/reference-layers" in source
        assert "/api/v1/compliance" not in source
        assert "/synchronization/t0" not in source[source.index("function wwComplianceAlignmentUrl"):source.index("function wwComplianceHasTraces")]  # DEC-170


class TestComplianceReferenceLayersStructure:
    """Compliance Slice 3's own structural surface: the active Reference
    Layers card, the three new modals (Add Reference / Manage Profiles /
    profile editor), and the Comparison Chart's Plotly mount point."""

    def test_reference_layers_card_has_add_and_manage_actions(self):
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceAddReferenceBtn"' in page
        # Add Reference UX: ONE top-level action; the library lives inside Add Reference.
        assert 'id="wwRefManageProfilesBtn"' not in source
        assert "Reference Library&hellip;" not in page
        assert 'id="wwRefLayerList"' in page

    def test_three_new_modals_exist(self):
        source = _source()
        assert 'id="wwRefAddOverlay"' in source
        assert 'id="wwRefManageOverlay"' not in source
        assert 'id="wwRefEditorOverlay"' in source

    def test_profile_editor_is_table_first_never_freehand_dragging(self):
        """Table-first numeric POINT entry (DEC-166), no freehand curve
        dragging. The per-row segment fields (start/end time, start/end
        value, Constant/Linear) are gone from the normal editor."""
        source = _source()
        assert 'id="wwRefEditorLowerTable"' in source
        assert 'id="wwRefEditorUpperTable"' in source
        assert "ww-ref-pt-time" in source
        assert "ww-ref-pt-value" in source
        for retired in ("ww-ref-seg-start-time", "ww-ref-seg-end-time", "ww-ref-seg-start-value",
                        "ww-ref-seg-end-value", "ww-ref-seg-type"):
            assert retired not in source, retired
        # No drag-based curve editing exists anywhere for this feature.
        for forbidden in ("wwRefDrag", "wwRefEditorDrag", "wwRefCurveDrag"):
            assert forbidden not in source

    def test_comparison_chart_has_a_plotly_mount_point_not_a_second_library(self):
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceChartPlot"' in page
        chart_fn = _function_body(source, "function wwRefRenderChart() {", "// ---- Compliance Slice 3 -- Reference Profiles/Layers wiring ----")
        assert "Plotly.react(" in chart_fn

    def test_reference_layer_compatibility_is_three_way_never_two_way(self):
        """Mid-conversation amendment: "no Measurement selected" must
        never collapse into "incompatible"."""
        source = _source()
        assert "not_yet_applicable" in source
        assert "compatible" in source
        assert "incompatible" in source

    def test_reference_layers_load_unconditionally_on_page_render(self):
        """The mid-conversation product requirement itself: Reference
        Layers/Comparison Chart load regardless of Measurement/group/
        source state -- wwRenderCompliancePage() calls them
        unconditionally, never behind an `if` gated on group/quantity
        selection."""
        source = _source()
        render_fn = _function_body(source, "function wwRenderCompliancePage() {", "\n        }")
        assert "wwRefLoadProfiles()" in render_fn
        assert "wwRefRefreshLayersAndChart()" in render_fn


class TestAssessmentDefinitionEditorStructure:
    """DEC-110 -- the profile editor's own Assessment Definition surface
    (task section 10): representation/phase treatment/specific member/
    measurement location/interpretation source, member shown only when
    applicable, no raw internal enum names exposed to the engineer."""

    def test_evaluation_quantity_select_no_longer_exists(self):
        """Retired in favor of the Assessment Definition fields below --
        never both at once."""
        source = _source()
        assert 'id="wwRefEditorQuantity"' not in source
        assert "wwRefPopulateQuantitySelect" not in source

    def test_assessment_definition_fields_exist(self):
        source = _source()
        for field_id in ("wwRefEditorRepresentation", "wwRefEditorPhaseTreatment", "wwRefEditorMember"):
            assert f'id="{field_id}"' in source
        # DEC-166: measurement location and interpretation source left the editor.
        for retired in ("wwRefEditorMeasurementLocation", "wwRefEditorProvenance"):
            assert f'id="{retired}"' not in source

    def test_member_field_visibility_is_computed_never_always_visible(self):
        source = _source()
        fn = _function_body(source, "function wwRefEditorUpdateMemberFieldVisibility() {", "\n        }")
        assert "fieldEl.hidden = true" in fn
        assert "fieldEl.hidden = false" in fn
        # DEC-166: only Phase Evaluation = Single reveals the Voltage selector.
        assert 'treatmentSelect.value === "single"' in fn

    def test_select_options_use_human_labels_not_raw_enum_names(self):
        """Task section 10: 'Do not expose raw internal enum names.'"""
        source = _source()
        representation_field = _function_body(source, 'id="wwRefEditorRepresentation"', "</select>")
        assert "Line-Line RMS" in representation_field
        assert "Phase-Ground RMS" in representation_field
        assert "Positive-Sequence RMS" in representation_field
        phase_treatment_field = _function_body(source, 'id="wwRefEditorPhaseTreatment"', "</select>")
        assert "Each Phase" in phase_treatment_field

    def test_layer_summary_helper_exists_and_handles_unspecified(self):
        source = _source()
        fn = _function_body(source, "function wwRefDescribeAssessmentDefinition(definition, options) {", "\n        }")
        assert "Assessment convention not specified" in fn
        assert "Assessment: " in fn

    def test_reference_layer_row_renders_the_assessment_summary(self):
        source = _source()
        fn = _function_body(source, "function wwRefRenderLayersCard() {", "\n        async function wwRefToggleLayerVisibility")
        assert "wwRefDescribeAssessmentDefinition(" in fn
        assert "ww-ref-layer-summary" in fn

    def test_no_evaluation_or_measurement_resolver_logic_was_added(self):
        """Task section 15's own explicit exclusion list."""
        source = _source()
        for forbidden in (
            "wwRefResolveTrace", "wwRefDeriveMeasured", "wwRefEvaluateAssessment",
            "wwRefMinAggregate", "wwRefMaxAggregate", "wwRefEachPhaseEvaluate",
        ):
            assert forbidden not in source


class TestReferenceLibraryTerminologyDEC111:
    """DEC-111 section 21: generic, jurisdiction-neutral wording only --
    "Reference Profiles"/"Reference Library"/"Import Reference"/"Export
    Reference"/"Reference Layers", never "My Profiles"/"Malaysian
    Requirements"/"User Library" (there are no user identities and
    Powerwave is jurisdiction-neutral)."""

    def test_preferred_terminology_is_present(self):
        source = _source()
        assert "Reference Library" not in _function_body(source, 'id="wwComplianceReferenceLayersCard"', "</section>")
        assert "Create Custom Reference" in source
        assert "Import Reference" in source

    def test_rejected_terminology_is_absent(self):
        source = _source()
        for forbidden in ("My Profiles", "User Library", "Malaysian Requirements"):
            assert forbidden not in source

    def test_empty_states_read_as_an_intentional_product_state_not_a_failure(self):
        """Task section 22: zero profiles by default is a valid product
        state -- the empty-state wording must say so plainly, never look
        like a loading failure."""
        source = _source()
        assert "No reference profiles loaded" in source


class TestJurisdictionNeutralUiDEC111:
    """Frontend-side companion to `test_reference_profile_jurisdiction_
    neutrality.py`'s backend production-code check: no named grid code/
    utility/OEM ever appears in the Compliance page's own static markup
    or its Reference Profile/Layer JS (comments in OTHER, unrelated
    parts of this same file are out of scope for this specific guard --
    see that backend test's own module docstring for the full
    "documentation is fine, code is not" reasoning this mirrors)."""

    def test_no_named_jurisdiction_or_oem_in_the_compliance_page_markup(self):
        source = _source()
        page = _compliance_page(source)
        for forbidden in ("Malaysia", "Huawei", "ENTSO-E", "AEMO"):
            assert forbidden not in page


class TestOperatingEnvelopeEditorStructure:
    """DEC-166 -- the simplified Operating Envelope editor's structure."""

    def test_normal_fields_are_name_category_envelope_and_phase_evaluation(self):
        source = _source()
        for field_id in (
            "wwRefEditorName", "wwRefEditorCategory", "wwRefEditorLowerEnabled", "wwRefEditorUpperEnabled",
            "wwRefEditorComplianceRegion", "wwRefEditorPhaseTreatment", "wwRefEditorAssessmentSummary",
            "wwRefEditorPreviewPlot", "wwRefEditorLowerAddRowBtn", "wwRefEditorUpperAddRowBtn",
        ):
            assert f'id="{field_id}"' in source, field_id
        assert "+ Add Point" in source
        assert "Save Reference" in source

    def test_phase_evaluation_has_no_unspecified_option_for_new_profiles(self):
        source = _source()
        field = _function_body(source, 'id="wwRefEditorPhaseTreatment"', "</select>")
        for label in ("Each Phase", "Minimum", "Maximum", "Single"):
            assert label in field
        assert "unspecified" not in field.lower()
        representation = _function_body(source, 'id="wwRefEditorRepresentation"', "</select>")
        assert "unspecified" not in representation.lower()

    def test_a_legacy_unspecified_value_is_preserved_through_an_explicit_option(self):
        source = _source()
        fn = _function_body(source, "function wwRefEditorSetAssessmentControls(definition, hasLegacyUnspecified) {", "\n        }")
        assert "Unspecified (legacy)" in fn
        assert "Not specified (legacy)" in fn

    def test_advanced_settings_and_metadata_are_collapsed_details(self):
        source = _source()
        for details_id in ("wwRefEditorAdvanced", "wwRefEditorMetadata"):
            tag = _function_body(source, f'<details id="{details_id}"', ">")
            assert " open" not in tag
        assert "Advanced Settings" in source
        assert "Reference Source / Metadata" in source

    def test_advanced_defaults_are_visible_not_hidden(self):
        source = _source()
        advanced = _function_body(source, '<details id="wwRefEditorAdvanced"', "</details>")
        assert 'value="pu" selected' in advanced
        assert 'value="line_line_rms" selected' in advanced
        assert 'id="wwRefEditorEvalStart" value="0"' in advanced
        assert 'id="wwRefEditorTolerance" value="0"' in advanced
        for auto_id in ("wwRefEditorEvalEndAuto", "wwRefEditorDisplayStartAuto", "wwRefEditorDisplayEndAuto"):
            assert f'id="{auto_id}" checked' in advanced
        assert "Auto &mdash; same as display end" in advanced

    def test_retired_per_row_segment_type_and_location_controls_are_gone(self):
        source = _source()
        editor = _function_body(source, 'id="wwRefEditorOverlay"', "<!-- Waveform toolbar refinement")
        for retired in ("Constant", "Linear", "Specific member", "Measurement location", "Interpretation source"):
            # `Linear`/`Constant` survive only in the read-only legacy segment renderer (JS), never as editor markup.
            assert retired not in editor, retired

    def test_translation_helpers_mirror_the_backend_and_the_save_path_uses_them(self):
        source = _source()
        assert "function wwRefEnvPointsToSegments(points) {" in source
        assert "function wwRefEnvFindCrossing(lowerSegments, upperSegments) {" in source
        save = _function_body(source, "async function wwRefEditorSave() {", "\n        }")
        assert "wwRefEditorEvaluate()" in save
        assert "evaluation.errors.length" in save  # Save is blocked, never silently repaired
        build = _function_body(source, "function wwRefEditorBuildRequestBody(evaluation) {", "\n        }")
        assert "evaluation.segments[boundary]" in build
        assert "original.measurement_location" in build  # an existing profile keeps what it stored

    def test_legacy_boundaries_are_saved_back_verbatim(self):
        source = _source()
        build = _function_body(source, "function wwRefEditorBuildRequestBody(evaluation) {", "\n        }")
        assert "evaluation.legacy" in build
        assert "editor.original[boundary + \"_boundary\"]" in build

    def test_preview_reuses_plotly_and_adds_no_second_charting_library(self):
        source = _source()
        fn = _function_body(source, "function wwRefEditorRenderPreview(evaluation) {", "\n        }")
        assert "Plotly.react(" in fn
        assert "fill: \"toself\"" in fn


class TestAddReferenceUnifiedFlowStructure:
    """Add Reference UX -- "+ Add Reference" is the single top-level action; the
    Reference Library is one source within it."""

    def test_card_has_only_the_add_reference_action(self):
        source = _source()
        card = _function_body(source, 'id="wwComplianceReferenceLayersCard"', "</section>")
        assert card.count("<button") == 1
        assert 'id="wwComplianceAddReferenceBtn"' in card

    def test_add_dialog_has_search_list_create_and_import(self):
        source = _source()
        dialog = _function_body(source, 'id="wwRefAddOverlay"', 'id="wwRefEditorOverlay"')
        for element_id in (
            "wwRefAddSearch", "wwRefAddList", "wwRefAddNewProfileBtn", "wwRefAddImportInput", "wwRefAddError",
        ):
            assert f'id="{element_id}"' in dialog
        assert "Available References" in dialog
        assert "Saved References" not in dialog
        assert "Create New" in dialog

    def test_no_separate_library_dialog_or_functions_remain(self):
        source = _source()
        for retired in (
            "wwRefManageOverlay", "wwRefManageList", "wwRefOpenManageDialog", "wwRefCloseManageDialog",
            "wwRefRenderManageDialogList", "wwRefManageImportFile", "wwRefManageProfilesBtn",
        ):
            assert retired not in source, retired

    def test_row_actions_are_behind_one_lightweight_menu(self):
        source = _source()
        render = _function_body(source, "function wwRefRenderAddDialogList() {", "\n        }\n\n        async function wwRefOpenAddDialog")
        assert "ww-ref-row-menu" in render
        for button in ("wwRefMgViewBtn-", "wwRefMgEditBtn-", "wwRefMgDupBtn-", "wwRefMgExportBtn-", "wwRefMgRemoveBtn-"):
            assert button in render
        assert "Already added" in render

    def test_a_profile_that_is_already_active_is_never_added_twice(self):
        source = _source()
        add = _function_body(source, "async function wwRefAddProfileAsLayer(", "\n        }")
        assert "layer.profile_id === profileId" in add

    def test_creating_a_profile_makes_it_active_and_returns_to_compliance(self):
        source = _source()
        save = _function_body(source, "async function wwRefEditorSave() {", "\n        }")
        assert "wwRefAddProfileAsLayer(saved.id)" in save
        assert "!isUpdate" in save

    def test_adding_a_layer_goes_through_the_layer_refresh_that_rechecks_readiness(self):
        source = _source()
        add = _function_body(source, "async function wwRefAddProfileAsLayer(", "\n        }")
        assert "wwRefRefreshLayersAndChart()" in add
        refresh = _function_body(source, "async function wwRefRefreshLayersAndChart() {", "\n        }")
        assert "wwComplianceRefreshReadiness()" in refresh


class TestReferenceLayerCardIdentityFirst:
    """The Reference Layer card answers "what reference is this?": full name,
    category, assessment definition -- and no measurement/compatibility status."""

    def test_card_does_not_render_the_compatibility_pill(self):
        source = _source()
        fn = _function_body(source, "function wwRefRenderLayersCard() {", "\n        async function wwRefToggleLayerVisibility")
        assert "wwRefCompatBadgeHtml(" not in fn
        assert "layer.compatibility.status" not in fn and "layer.compatibility.reason" not in fn

    def test_name_leads_with_category_and_assessment_beneath(self):
        source = _source()
        fn = _function_body(source, "function wwRefRenderLayersCard() {", "\n        async function wwRefToggleLayerVisibility")
        assert fn.index("ww-ref-layer-name") < fn.index("ww-ref-layer-category") < fn.index("ww-ref-layer-summary")
        assert "wwRefCategoryBadgeHtml(profile.category)" in fn
        assert "ww-ref-layer-remove-btn" in fn and "wwRefLayerVis-" in fn

    def test_name_wraps_instead_of_truncating_and_category_is_half_rem(self):
        source = _source()
        name_rule = _function_body(source, "        .ww-ref-layer-name {", "}")
        assert "text-overflow" not in name_rule and "nowrap" not in name_rule
        assert "overflow-wrap: anywhere" in name_rule
        assert ".ww-ref-layer-row .ww-ref-badge { font-size: 0.5rem;" in source


class TestAlignmentUxAndFixedWorkspaceUatRefinement:
    """UAT refinement of DEC-169/DEC-170: guided selection mode, a visible
    Reference t=0 label, a fixed-height desktop workspace."""

    def test_chart_click_only_selects_in_the_explicit_selection_mode(self):
        source = _source()
        fn = _function_body(source, "function wwComplianceOnChartClick(", "// ---- Resizable two-column workspace")
        assert fn.index("if (!wwComplianceState.aligning) return;") < fn.index("plotEl.data[point.curveNumber]")
        assert 'plotted.meta.role !== "measurement"' in fn  # trace role, never legend text

    def test_reference_t0_label_is_paper_anchored_inside_the_plot(self):
        source = _source()
        fn = _function_body(source, "function wwRefRenderChart() {", "// (Placed after the shared")
        label = _function_body(fn, 'x: 0, y: 1, xref: "x", yref: "paper", text: "Reference t=0"', 'name: "reference-t0-label"')
        assert 'yref: "paper"' in label and 'yanchor: "top"' in label and "yshift: -4" in label
        assert 'yanchor: "bottom"' not in label  # the old, clipped placement

    def test_fixed_height_workspace_with_independent_left_scroll_on_desktop_only(self):
        source = _source()
        start = source.index("@media (min-width: 1101px) {\r\n            #pageCompliance { padding" if "\r\n" in source else "@media (min-width: 1101px) {\n            #pageCompliance { padding")
        block = source[start:source.index("}\n        }" if "\r\n" not in source else "}\r\n        }", start) + 20]
        assert "overflow-y: auto" in block and ".ww-compliance-config-column" in block
        assert "min-height: 0" in block
        # The stacked layout (<= 1100px) is untouched: normal page scrolling, no handle.
        stacked = _function_body(source, "@media (max-width: 1100px) {\n            .ww-compliance-split" if "\r\n" not in source else "@media (max-width: 1100px) {\r\n            .ww-compliance-split", "}")
        assert "flex-direction: column" in stacked

    def test_guided_alignment_markup(self):
        page = _compliance_page(_source())
        assert 'id="wwComplianceAlignSelectBtn"' in page and "Select Event Point" in page
        assert "Select the disturbance event on the Comparison Chart." in page
        assert "Set that point as Reference t=0." in page
        assert "<span>Reference t=0</span>" in page and "Reference position" not in page
        assert 'id="wwComplianceChartSelectBanner"' in page
        assert "Click a measured trace at the disturbance start" in page
