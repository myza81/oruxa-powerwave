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
        labels = ["Recordings", "Waveform", "Table", "Calculated Channels", "Analysis", "Compliance"]
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

    def test_voltage_panel_heading_is_provisional_wording(self):
        source = _source()
        page = _compliance_page(source)
        assert "Voltage Compliance &amp; Capability" in page

    def test_five_workflow_sections_exist_in_order(self):
        source = _source()
        page = _compliance_page(source)
        labels = ["Measurement", "Reference Layers", "Event Alignment", "Comparison Chart", "Results"]
        positions = [page.index(f"<h2>{label}</h2>") for label in labels]
        assert positions == sorted(positions)

    def test_measurement_shows_neutral_empty_state(self):
        source = _source()
        page = _compliance_page(source)
        assert "No assessment quantity selected" in page

    def test_reference_layers_shows_empty_state_and_disabled_add_button(self):
        source = _source()
        page = _compliance_page(source)
        assert "No reference layers added" in page
        add_btn = _function_body(page, 'id="wwComplianceAddReferenceBtn"', "</button>")
        assert "disabled" in add_btn
        assert "+ Add Reference" in add_btn

    def test_event_alignment_shows_empty_state_no_automatic_detection(self):
        source = _source()
        page = _compliance_page(source)
        assert "No event reference set" in page
        assert "wwComplianceDetectEvent" not in source
        assert "wwComplianceAutoAlign" not in source

    def test_comparison_chart_present_and_empty(self):
        source = _source()
        page = _compliance_page(source)
        assert 'id="wwComplianceChartWrap"' in page
        assert "No voltage assessment configured" in page

    def test_results_shows_neutral_empty_state_no_fake_verdicts(self):
        source = _source()
        page = _compliance_page(source)
        results = _function_body(page, 'id="wwComplianceResultsPanel"', "</section>")
        assert "Results will appear after a measurement" in results
        assert "Compliant" not in results
        assert "Boundary Breached" not in results
        assert "Within Capability" not in results


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


class TestComplianceMeasurementSlice2Structure:
    """Slice 2 (Measurement Selection + Normalization Foundation) --
    structural guards for the real Assessment Quantity workflow that
    replaces Slice 1's disabled placeholder select."""

    def test_measurement_select_is_no_longer_a_disabled_placeholder(self):
        source = _source()
        page = _compliance_page(source)
        select = _function_body(page, 'id="wwComplianceMeasurementSelect"', "</select>")
        assert "disabled" not in select
        assert "aria-disabled" not in select
        assert 'value="">Select a quantity' in select

    def test_measurement_summary_rows_exist_and_start_hidden(self):
        source = _source()
        page = _compliance_page(source)
        summary = _function_body(page, 'id="wwComplianceMeasurementSummary"', "</div>\n                                </section>")
        assert 'id="wwComplianceMeasurementSummary" hidden' in page
        for element_id in (
            "wwComplianceMeasurementStatusRow", "wwComplianceMeasurementInput", "wwComplianceMeasurementInputType",
            "wwComplianceMeasurementDerivedAs", "wwComplianceMeasurementBase", "wwComplianceMeasurementUnit",
        ):
            assert f'id="{element_id}"' in summary

    def test_quantity_catalogue_is_never_hardcoded_in_markup(self):
        """The dropdown starts with only the placeholder option -- every
        real quantity option is populated from the backend catalogue at
        runtime (wwComplianceRenderQuantityOptions()), never duplicated
        as static HTML that could drift from app.domain.compliance_
        measurement.VOLTAGE_QUANTITIES."""
        source = _source()
        page = _compliance_page(source)
        select = _function_body(page, 'id="wwComplianceMeasurementSelect"', "</select>")
        assert select.count("<option") == 1

    def test_required_slice2_js_functions_exist(self):
        source = _source()
        for fn in (
            "function wwComplianceLoadQuantities(",
            "function wwComplianceRenderQuantityOptions(",
            "function wwComplianceOnQuantityChange(",
            "function wwComplianceFetchMeasurement(",
            "function wwComplianceRenderMeasurement(",
        ):
            assert fn in source

    def test_endpoints_are_workspace_scoped_never_engineering_context_scoped(self):
        """Compliance still does not register as an Engineering Context
        consumer (DEC-100/DEC-101) -- neither new endpoint call embeds an
        engineering_context_id, unlike every Analysis-menu analyzer's own
        `.../engineering-contexts/{id}/...` calls."""
        source = _source()
        assert "/compliance/voltage/quantities" in source
        assert "/compliance/voltage/measurement" in source
        measurement_fetch = _function_body(source, "function wwComplianceFetchMeasurement(", "\n        }")
        assert "engineering-contexts" not in measurement_fetch
        assert "engineering_context_id" not in measurement_fetch

    def test_render_compliance_page_still_never_touches_analyzer_state(self):
        """Extends the existing Slice 1 guard: the Slice 2 additions to
        wwRenderCompliancePage() (loading quantities, refreshing the
        selected measurement) must never call any shared Analysis/
        Playback/analyzer entry point."""
        source = _source()
        render_fn = _function_body(source, "function wwRenderCompliancePage() {", "\n        }")
        assert "wwAnalysisLoadContexts" not in render_fn
        assert "wwAnalysisRegisterContextConsumer" not in render_fn
        assert "wwPlayback" not in render_fn
        assert "wwPhasorState" not in render_fn
        assert "wwSequenceState" not in render_fn
        assert "wwDistanceState" not in render_fn
        assert "wwComplianceLoadQuantities" in render_fn


class TestComplianceOutOfScopeSlice2:
    """task's own explicit Slice 2 scope boundary: only Measurement is
    implemented -- Reference Layers, Event Alignment, comparison curves,
    and compliance evaluation remain exactly the Slice 1 placeholders."""

    def test_reference_layers_and_event_alignment_still_disabled_placeholders(self):
        source = _source()
        page = _compliance_page(source)
        add_ref_btn = _function_body(page, 'id="wwComplianceAddReferenceBtn"', "</button>")
        assert "disabled" in add_ref_btn
        alignment_controls = _function_body(page, 'id="wwComplianceAlignmentControls"', "</div>")
        # Each of the 3 buttons (Shift-left, t0, Shift-right) carries both
        # `disabled` and `aria-disabled="true"` -- "disabled" is also a
        # substring of "aria-disabled", so 3 buttons -> 6 occurrences.
        assert alignment_controls.count("disabled") == 6

    def test_no_reference_profile_alignment_or_evaluation_logic_added(self):
        source = _source()
        page = _compliance_page(source)
        for forbidden in (
            "wwComplianceEvaluate", "wwComplianceBreach", "wwComplianceMargin",
            "wwComplianceApplyShift", "wwComplianceSetT0", "wwComplianceDetectEvent", "wwComplianceAutoAlign",
            "profile_json", "profileJson", "malaysian_grid_code", "MalaysianGridCode",
        ):
            assert forbidden not in page

    def test_still_no_backend_endpoint_beyond_the_two_measurement_endpoints(self):
        source = _source()
        assert "/api/v1/compliance" not in source
        assert "reference-layer" not in source
        assert "event-alignment" not in source
