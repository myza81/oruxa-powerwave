"""Static structural regression checks for Overcurrent Analysis v1
(frontend/index.html) -- the second `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is covered separately by `browser-tests/overcurrent_analysis.spec.js`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestOvercurrentInAnalysisNav:
    def test_overcurrent_nav_button_exists(self):
        source = _source()
        assert 'id="wwAnalysisTypeOvercurrentBtn"' in source
        assert 'data-analysis-type="overcurrent"' in source

    def test_phasor_nav_button_still_exists(self):
        source = _source()
        assert 'id="wwAnalysisTypePhasorBtn"' in source
        assert 'data-analysis-type="phasor"' in source

    def test_analysis_type_menu_contains_implemented_and_placeholder_entries(self):
        source = _source()
        nav = _function_body(source, 'class="ww-analysis-type-nav"', '</nav>')
        assert nav.count('class="ww-analysis-type-item') == 5
        for label in ("Phasor", "Overcurrent", "Impedance Locus", "Sequence Components", "Distance Protection"):
            assert label in nav
        assert "Differential" not in nav

    def test_analyzer_switcher_toggles_implemented_and_placeholder_panels(self):
        source = _source()
        fn = _function_body(source, "const wwAnalysisPanelsByType", "document.getElementById(\"wwAnalysisTypePhasorBtn\")")
        assert "phasor:" in fn
        assert "overcurrent:" in fn
        assert "impedance:" in fn
        assert "sequence:" in fn
        assert "wwPhasorPanel" in fn
        assert "wwOvercurrentPanel" in fn
        assert "wwImpedancePanel" in fn
        assert "wwSequencePanel" in fn
        assert "panelEl.hidden = panelType !== type;" in fn
        assert "wwAnalysisSetRelatedWaveformRoles([], null, null);" in fn


class TestOvercurrentPanelStructure:
    def test_panel_section_exists(self):
        source = _source()
        assert 'id="wwOvercurrentPanel"' in source

    def test_context_selector_exists(self):
        source = _source()
        assert 'id="wwOvercurrentContextSelect"' in source
        assert 'id="wwOvercurrentContextBadge"' in source

    def test_phase_selector_exists_with_three_phases(self):
        source = _source()
        body = _function_body(source, 'id="wwOvercurrentPanel"', 'id="wwOvercurrentPlaybackPanel"')
        assert 'id="wwOvercurrentPhaseSelect"' in body
        assert '<option value="A">Phase A</option>' in body
        assert '<option value="B">Phase B</option>' in body
        assert '<option value="C">Phase C</option>' in body

    def test_no_raw_channel_picker(self):
        """Bay/Engineering Context + Phase is the entire input surface --
        never a manual raw-channel picker."""
        source = _source()
        body = _function_body(source, 'id="wwOvercurrentPanel"', 'id="wwOvercurrentSvg"')
        assert "wwOvercurrentChannelSelect" not in body
        assert "channel_name" not in body  # never hand-typed in markup

    def test_playback_composition_point_reuses_shared_markup(self):
        source = _source()
        assert 'id="wwOvercurrentPlaybackPanel"' in source
        assert 'id="wwOvercurrentPlaybackMount"' in source
        assert 'ww-analysis-playback-panel" id="wwOvercurrentPlaybackPanel"' in source
        assert 'ww-analysis-playback-mount" id="wwOvercurrentPlaybackMount"' in source

    def test_characteristic_selector_exists(self):
        source = _source()
        assert 'id="wwOvercurrentCharacteristicSelect"' in source

    def test_pickup_and_tms_inputs_exist(self):
        source = _source()
        assert 'id="wwOvercurrentPickupInput"' in source
        assert 'id="wwOvercurrentTmsInput"' in source

    def test_recording_basis_selector_exists(self):
        source = _source()
        assert 'id="wwOvercurrentBasisSelect"' in source
        assert '<option value="secondary" selected>Secondary</option>' in source
        assert '<option value="primary">Primary</option>' in source

    def test_ct_fields_exist_and_hidden_by_default(self):
        """CT Primary/Secondary render but start `hidden` -- shown only
        when recording basis is Primary (never required for Secondary)."""
        source = _source()
        body = _function_body(source, 'id="wwOvercurrentCtPrimaryField"', 'id="wwOvercurrentValuesList"')
        assert 'id="wwOvercurrentCtPrimaryField" hidden' in source
        assert 'id="wwOvercurrentCtSecondaryField" hidden' in source
        assert 'id="wwOvercurrentCtPrimaryInput"' in body
        assert 'id="wwOvercurrentCtSecondaryInput"' in body

    def test_ct_fields_visibility_toggled_by_basis_change(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentUpdateCtFieldsVisibility()", "function wwOvercurrentHandleSettingsChanged")
        assert "wwOvercurrentCtPrimaryField" in fn
        assert "wwOvercurrentCtSecondaryField" in fn
        assert "wwOvercurrentCtFieldsNeeded()" in fn

    def test_ct_fields_needed_considers_both_recording_and_manual_basis(self):
        """Manual Input / Calculator mode (2026-09-16): CT Primary/
        Secondary are shared, never duplicated between modes (task §5) --
        their FIELDS become visible whenever EITHER the shared Recording
        basis OR Manual's own basis needs them, so switching Manual's own
        Basis selector to Primary never hides the CT inputs regardless of
        what the shared "Recording current basis" dropdown reads."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentCtFieldsNeeded()", "function wwOvercurrentUpdateCtFieldsVisibility")
        assert 'recordingBasis === "primary"' in fn
        assert "manual.inputBasis === \"primary\"" in fn
        assert "WW_ANALYSIS_INPUT_SOURCE_MANUAL" in fn

    def test_numeric_result_fields_render(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderResult(result)", "function wwOvercurrentEnsureCurveAndRenderPoint")
        for label in (
            "Measured RMS current", "Relay-equivalent current", "Pickup",
            "Multiple of pickup", "Expected operating time", "Above-pickup duration",
        ):
            assert label in fn

    def test_characteristic_chart_exists_not_plotly(self):
        source = _source()
        assert 'id="wwOvercurrentSvg"' in source
        body = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentUpdateCtFieldsVisibility")
        assert "Plotly" not in body


class TestOvercurrentViewport:
    """Adjustable-viewport UAT follow-up (2026-09-12): default display
    domain, absolute bounds, validation, dynamic 1-2-5/decade tick
    generation with the major/minor classification rule, zoom in/out/
    reset, and true positive log-axis minima."""

    def test_default_and_absolute_viewport_constants(self):
        """Owner axis simplification: the Pickup Multiple default is the
        true log range 0.1x-100x and Y is 0.1s-100s."""
        source = _source()
        assert "const WW_OC_VIEWPORT_DEFAULT = { xMin: 0.1, xMax: 100, yMin: 0.1, yMax: 100 };" in source
        assert "const WW_OC_VIEWPORT_ABSOLUTE = { xMin: 0.1, xMax: 200, yMin: 0.01, yMax: 1000 };" in source

    def test_state_viewport_field_initialised_to_default(self):
        source = _source()
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchCharacteristics")
        assert "viewport: { xMin: 0.1, xMax: 100, yMin: 0.1, yMax: 100 }," in fn

    def test_reset_state_also_resets_viewport(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")
        assert 'wwOvercurrentState.viewport = { xMin: 0.1, xMax: 100, yMin: 0.1, yMax: 100 };' in fn

    def test_validation_rejects_out_of_bound_and_non_finite_and_inverted(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentViewportValid(v)", "function wwOvercurrentGeneratePow125Ticks")
        assert "Number.isFinite" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.xMin" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.xMax" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.yMin" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.yMax" in fn
        assert "xMin < xMax" in fn
        assert "yMin < yMax" in fn

    def test_tick_generation_uses_log10_never_linear_spacing(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentGeneratePow125Ticks(min, max)", "function wwOvercurrentGenerateDecadeTicks")
        assert "Math.log10(min)" in fn
        assert "Math.log10(max)" in fn

    def test_major_minor_classification_reproduces_owner_default_lists(self):
        """The dynamic classification rule (exclude progression values
        <= 2x the axis minimum from the major set) must reproduce the
        owner's own explicit default major-tick lists exactly."""
        import re
        import subprocess
        import sys

        source = _source()
        gen_pow125 = _function_body(source, "function wwOvercurrentGeneratePow125Ticks(min, max)", "function wwOvercurrentGenerateDecadeTicks")
        gen_decade = _function_body(source, "function wwOvercurrentGenerateDecadeTicks(min, max)", "function wwOvercurrentClassifyMajors")
        classify = _function_body(source, "function wwOvercurrentClassifyMajors(allTicks, axisMin)", "function wwOvercurrentXMajors")
        script = gen_pow125 + "\n" + gen_decade + "\n" + classify + """
        console.log(JSON.stringify({
            x: wwOvercurrentClassifyMajors(wwOvercurrentGeneratePow125Ticks(0.1, 100), 0.1),
            y: wwOvercurrentGenerateDecadeTicks(0.1, 100),
        }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        payload = re.search(r"\{.*\}", result.stdout).group(0)
        import json

        data = json.loads(payload)
        assert data["x"] == [0.5, 1, 2, 5, 10, 20, 50, 100]
        assert data["y"] == [0.1, 1, 10, 100]

    def test_geometry_is_viewport_aware_with_no_origin_gap(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentChartGeometry(viewport)", "function wwOvercurrentPixelX")
        assert "WW_OC_ORIGIN_GAP" not in source
        assert "breakApplies" not in fn
        assert "logLeft: plotLeft" in fn
        assert "logBottom: plotBottom" in fn
        assert "logMMin: Math.log10(viewport.xMin)" in fn
        assert "logTMin: Math.log10(viewport.yMin)" in fn

    def test_chart_has_no_visual_zero_origin_labels(self):
        source = _source()
        assert "ww-oc-origin-label" not in source
        assert "ww-oc-tick-label-minor" not in source

    def test_render_path_has_no_fake_zero_branch(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "geo.isDefault" not in fn
        assert ">0</text>" not in fn

    def test_zoom_centers_in_log_space_and_clamps_to_absolute_bounds(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentZoom(factor)", "function wwOvercurrentResetViewport")
        assert "Math.log10(v.xMin)" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.xMin" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.xMax" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.yMin" in fn
        assert "WW_OC_VIEWPORT_ABSOLUTE.yMax" in fn
        assert "wwOvercurrentRerenderChartFromState();" in fn

    def test_zoom_never_refetches_curve_or_touches_playback(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentZoom(factor)", "function wwOvercurrentResetViewport")
        assert "wwOvercurrentFetchCurve" not in fn
        assert "wwPlayback" not in fn
        assert "wwOvercurrentHandleSettingsChanged" not in fn

    def test_reset_returns_to_exact_default_viewport(self):
        """Reset restores deterministic defaults, independent of the
        current operating point."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetViewport()", "// ---- Settings wiring helpers")
        assert "wwOvercurrentDynamicYMin" not in source
        assert "wwOvercurrentState.viewport = { xMin: WW_OC_VIEWPORT_DEFAULT.xMin, xMax: WW_OC_VIEWPORT_DEFAULT.xMax, yMin: WW_OC_VIEWPORT_DEFAULT.yMin, yMax: WW_OC_VIEWPORT_DEFAULT.yMax };" in fn

    def test_view_controls_markup_exists(self):
        source = _source()
        for element_id in (
            "wwOvercurrentViewXMin", "wwOvercurrentViewXMax",
            "wwOvercurrentViewYMin", "wwOvercurrentViewYMax",
            "wwOvercurrentZoomInBtn", "wwOvercurrentZoomOutBtn", "wwOvercurrentResetViewBtn",
        ):
            assert 'id="' + element_id + '"' in source

    def test_view_input_listeners_never_call_settings_changed(self):
        source = _source()
        fn = _function_body(source, '["wwOvercurrentViewXMin"', "wwOvercurrentSyncViewportInputs();")
        assert "wwOvercurrentHandleSettingsChanged" not in fn
        assert "wwOvercurrentApplyViewportFromInputs" in fn
        assert "wwOvercurrentZoom(0.5)" in fn
        assert "wwOvercurrentZoom(2)" in fn
        assert "wwOvercurrentResetViewport" in fn


class TestChartAxesGridAndTicks:
    """Chart UX refinement (2026-09-12): a full engineering chart frame
    -- axis lines, grid, and the owner's own exact displayed tick-label
    sets -- around the existing curve/operating-point geometry, which
    stays mathematically unchanged."""

    def test_x_and_y_axis_lines_render(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert fn.count('class="ww-oc-axis"') == 2

    def test_grid_lines_render_for_current_viewport_majors(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "ww-oc-gridline" in fn
        assert "for (const v of xMajors)" in fn
        assert "for (const v of yMajors)" in fn

    def test_ticks_use_the_log_transform_never_linear_spacing(self):
        """Tick/grid pixel positions must come from the same
        `Math.log10()`-based mapping the curve itself uses -- never a
        uniform/linear index-based spacing."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentPixelX(m, geo)", "function wwOvercurrentPixelY")
        assert "Math.log10(m)" in fn
        assert "geo.logMMin" in fn
        assert "geo.logMMax" in fn

    def test_axis_titles_unchanged_text(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "Current / Pickup Multiple (M)" in fn
        assert "Expected Operating Time (s)" in fn

    def test_curve_is_clipped_not_clamped_or_distorted(self):
        """A real IDMT curve legitimately runs outside the fixed display
        window near M=1 for a slow TMS -- the curve path itself uses the
        SAME unclamped pixel mapping as the grid/ticks, then is clipped
        (never distorted) via an SVG clipPath, so the underlying
        engineering math is never altered to fit the frame."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "clipPath" in fn
        assert 'clip-path="url(#wwOvercurrentClip)"' in fn

    def test_curve_points_themselves_are_not_reclamped(self):
        """The curve path loop maps the visible-segment points' own
        `p[0]`/`p[1]` directly through the unclamped pixel functions --
        clamping is reserved for the single operating-point marker only,
        confirmed by the curve-path loop never calling
        wwOvercurrentClampedM/T."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        curve_loop = _function_body(fn, "const curvePath = segment.map", "parts.push('<path")
        assert "wwOvercurrentClampedM" not in curve_loop
        assert "wwOvercurrentClampedT" not in curve_loop
        assert "wwOvercurrentPixelX(p[0], geo)" in curve_loop
        assert "wwOvercurrentPixelY(p[1], geo)" in curve_loop

    def test_curve_uses_the_exact_visible_segment_never_the_raw_fetched_points(self):
        """2026-09-12 chart-viewport-alignment UAT follow-up: the rendered
        path's own coordinates come from `wwOvercurrentVisibleCurveSegment()`
        (exact analytic viewport-boundary intersections), never directly
        from the raw fetched `points` array -- `points` is retained only
        as an availability gate (curve data confirmed fetched for this
        characteristic/TMS), never as the source of the rendered
        coordinates. Chart UX enhancement (axis-representation toggle):
        the segment is now solved against an M-domain-equivalent viewport
        (`mDomainViewport`, identity in Pickup Multiple mode, pickup-
        divided in Relay Current mode) rather than the raw active
        viewport directly, since the exact boundary solve is always
        defined in the characteristic's own M variable -- see
        TestAxisRepresentationToggle below for the Relay Current
        transform's own dedicated coverage."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        curve_block = _function_body(fn, "if (points && points.length > 0) {", "// Operating point")
        assert "wwOvercurrentVisibleCurveSegment(mDomainViewport)" in curve_block
        assert "if (segment) {" in curve_block
        assert "points.map" not in curve_block


class TestVisibleCurveSegmentBoundaryExactness:
    """2026-09-12 chart-viewport-alignment UAT follow-up: the visible
    curve must enter/exit the chart at the EXACT mathematical viewport-
    boundary intersection, never at whatever coarse pre-sampled point
    happens to fall inside the visible range. See
    `wwOvercurrentVisibleCurveSegment()`'s own docstring and
    `backend/tests/test_overcurrent_domain.py::
    TestSolveMultipleOfPickupForOperatingTime` for the backend's own
    exact-inverse proof of the identical formula."""

    def test_forward_and_inverse_are_direct_mirrors_of_the_backend_formula(self):
        source = _source()
        eval_t = _function_body(source, "function wwOvercurrentEvalT(constants, tms, m)", "function wwOvercurrentSolveMForT")
        assert "Math.pow(m, constants.alpha) - 1.0" in eval_t
        assert "tms * (constants.k / denominator + constants.c)" in eval_t

        solve_m = _function_body(source, "function wwOvercurrentSolveMForT(constants, tms, t)", "function wwOvercurrentCurrentConstants")
        assert "t / tms - constants.c" in solve_m
        assert "constants.k / denom" in solve_m
        assert "Math.pow(base, 1.0 / constants.alpha)" in solve_m

    def test_constants_are_sourced_from_backend_returned_characteristics_never_hand_typed(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentCurrentConstants()", "const WW_OC_VISIBLE_SEGMENT_SAMPLE_COUNT")
        assert "wwOvercurrentState.characteristics" in fn
        assert "wwOvercurrentState.settings.characteristicId" in fn
        # Never a second hand-typed k/alpha table (e.g. "k: 0.14" literals).
        assert "0.14" not in fn
        assert "13.5" not in fn
        assert "80.0" not in fn

    def test_visible_segment_uses_monotonic_boundary_selection_never_a_numeric_search(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentVisibleCurveSegment(viewport)", "function wwOvercurrentChartGeometry")
        assert "wwOvercurrentSolveMForT(constants, tms, viewport.yMax)" in fn
        assert "wwOvercurrentSolveMForT(constants, tms, viewport.yMin)" in fn
        assert "Math.max(mTop, viewport.xMin)" in fn
        assert "Math.min(mBottom, viewport.xMax)" in fn
        # Exact boundary values are used directly, never re-derived/rounded.
        assert "startM === mTop ? viewport.yMax" in fn
        assert "endM === mBottom ? viewport.yMin" in fn

    def test_visible_segment_samples_in_log_space(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentVisibleCurveSegment(viewport)", "function wwOvercurrentChartGeometry")
        assert "Math.log(startM)" in fn
        assert "Math.log(endM)" in fn
        assert "Math.exp(logStart + frac * (logEnd - logStart))" in fn

    def test_visible_segment_returns_null_when_no_portion_is_visible(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentVisibleCurveSegment(viewport)", "function wwOvercurrentChartGeometry")
        assert "if (!(startM < endM)) return null;" in fn


class TestForwardInverseFormulaMatchesBackend:
    """Executes the frontend's own `wwOvercurrentEvalT`/
    `wwOvercurrentSolveMForT` functions via Node and cross-checks them
    against the exact same expected values the backend's own
    `TestSolveMultipleOfPickupForOperatingTime` asserts -- proving the
    two implementations stay in exact algebraic correspondence, not
    merely that each looks reasonable in isolation."""

    def test_round_trip_matches_backend_for_every_characteristic_tms_and_target_time(self):
        import json
        import subprocess

        source = _source()
        eval_t = _function_body(source, "function wwOvercurrentEvalT(constants, tms, m)", "function wwOvercurrentSolveMForT")
        solve_m = _function_body(source, "function wwOvercurrentSolveMForT(constants, tms, t)", "function wwOvercurrentCurrentConstants")
        script = eval_t + "\n" + solve_m + """
        const characteristics = {
            SI: { k: 0.14, alpha: 0.02, c: 0.0 },
            VI: { k: 13.5, alpha: 1.0, c: 0.0 },
            EI: { k: 80.0, alpha: 2.0, c: 0.0 },
        };
        const results = [];
        for (const name of Object.keys(characteristics)) {
            for (const tms of [0.025, 0.1, 0.5, 1.0, 1.2]) {
                for (const t of [1000, 500, 100, 10, 1]) {
                    const m = wwOvercurrentSolveMForT(characteristics[name], tms, t);
                    const recovered = wwOvercurrentEvalT(characteristics[name], tms, m);
                    results.push({ name, tms, t, m, recovered });
                }
            }
        }
        console.log(JSON.stringify(results));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        rows = json.loads(result.stdout)
        assert len(rows) == 75
        for row in rows:
            assert row["m"] is not None and row["m"] > 1.0
            assert row["recovered"] == pytest.approx(row["t"], rel=1e-9)


class TestBelowPickupPositionMarker:
    """Chart UX refinement: below pickup, the chart still communicates
    WHERE the current sits on the X axis -- without ever fabricating a
    y-value/expected-operating-time point. Adjustable-viewport UAT
    follow-up (2026-09-12) adds a further split: on-chart (X inside the
    current viewport) vs. off-chart (X outside it, §10)."""

    def test_below_pickup_on_chart_shows_position_marker_and_vertical_guide_never_a_y_value(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        on_chart_branch = _function_body(fn, "} else if (mInRange) {", "} else {")
        assert "ww-oc-position-marker" in on_chart_branch
        assert "ww-oc-guide" in on_chart_branch
        # Never the same operating-point class/color used for a genuine computed result.
        assert "ww-oc-operating-point" not in on_chart_branch
        assert "wwOvercurrentPixelY" not in on_chart_branch

    def test_below_pickup_off_chart_shows_edge_indicator_never_a_fabricated_position(self):
        """UAT §10: if the true current value is outside the visible X
        range, never falsely clamp-and-present it as though the boundary
        were the true value -- an edge indicator only, no position-marker
        circle, no full-height guide (whose direction would mislead)."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        off_chart_branch = _function_body(fn, "} else {\n                    // Below pickup, off-chart", "}\n            }\n\n            svg.innerHTML")
        assert "wwOvercurrentEdgeArrowSvg" in off_chart_branch
        assert "ww-oc-position-marker" not in off_chart_branch
        assert "ww-oc-guide" not in off_chart_branch

    def test_position_marker_x_uses_clamped_m_never_distorts_the_true_value(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "const clampedM = wwOvercurrentClampedM(currentM, viewport);" in fn

    def test_below_pickup_never_calls_pixel_y_with_a_fabricated_time(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        below_branch = _function_body(fn, "} else if (mInRange) {", "}\n            }\n\n            svg.innerHTML")
        assert "wwOvercurrentPixelY" not in below_branch


class TestOperatingPointGuides:
    def test_above_pickup_still_renders_point_and_both_guides(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        above_branch = _function_body(fn, "if (Number.isFinite(currentT)) {", "} else {")
        assert "ww-oc-operating-point" in above_branch
        assert above_branch.count("ww-oc-guide") == 2

    def test_guides_align_with_the_clamped_tick_coordinate(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        above_branch = _function_body(fn, "if (Number.isFinite(currentT)) {", "} else {")
        assert "const clampedT = wwOvercurrentClampedT(currentT, viewport);" in above_branch

    def test_above_pickup_off_chart_uses_edge_indicator_for_the_out_of_range_axis(self):
        """UAT §11: if M or T lies outside the visible range, never
        redraw the operating point at the boundary as though the
        boundary were the true value -- an edge-indicator triangle
        replaces the circle for whichever axis is out of range, the
        other axis' guide is unaffected."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert 'wwOvercurrentEdgeArrowSvg(px, py, currentM < viewport.xMin ? "left" : "right")' in fn
        assert 'wwOvercurrentEdgeArrowSvg(px, py, currentT < viewport.yMin ? "down" : "up")' in fn


class TestNoRelayOperationClaims:
    """Owner instruction: never say 'relay tripped'/'relay should
    trip'/'relay failed to trip' anywhere in the Overcurrent UI text."""

    def test_no_forbidden_wording_in_overcurrent_block(self):
        source = _source()
        body = _function_body(source, 'id="wwOvercurrentPanel"', 'id="wwOvercurrentSvg"')
        lowered = body.lower()
        assert "relay tripped" not in lowered
        assert "relay should trip" not in lowered
        assert "relay operated" not in lowered
        assert "failed to trip" not in lowered

    def test_threshold_alert_wording_is_qualified(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderResult(result)", "function wwOvercurrentEnsureCurveAndRenderPoint")
        assert "characteristic-analysis observation only" in fn
        # Split across two concatenated string literals in the source --
        # asserted as two adjoining halves rather than one contiguous
        # substring.
        assert "it does " in fn
        assert "not mean the relay operated, should have operated, or failed to operate" in fn


class TestSharedPlaybackWiringUntouched:
    """Overcurrent must reuse the EXACT shared control-surface functions
    Phasor already mounts -- never a duplicated/parallel implementation,
    never a second timer/rAF loop, never Overcurrent-specific speed
    options."""

    def test_mount_function_reuses_shared_factory_and_wiring(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentMountPlaybackControls(groupId)", "function wwOvercurrentOnPlaybackTick")
        assert "wwCreatePlaybackControlsHtml()" in fn
        assert "wwWirePlaybackControls(mountEl, groupId)" in fn
        assert "wwSyncPlaybackControls(mountEl, groupId)" in fn

    def test_tick_subscriber_registered_via_shared_seam(self):
        source = _source()
        assert "wwPlaybackOnTick(wwOvercurrentOnPlaybackTick)" in source

    def test_no_second_raf_loop_or_timer(self):
        source = _source()
        body = _function_body(source, "// Overcurrent Analysis v1 -- the SECOND Analysis-menu analyzer.", "function wwOvercurrentResetState")
        assert "requestAnimationFrame(" not in body
        assert "setInterval(" not in body

    def test_throttle_uses_performance_now_to_rate_limit_never_to_clock(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentMaybeFetchForPlayback()", "function wwOvercurrentSetUpdatingIndicator")
        assert "performance.now()" in fn
        assert "WW_OVERCURRENT_PLAYBACK_THROTTLE_MS" in fn

    def test_no_overcurrent_specific_speed_options(self):
        """No second/duplicated speed-value list -- Overcurrent's own
        code only ever REFERENCES the shared `.ww-tg-playback-speed-
        select` class (to attach its own safety-net re-sync listener, the
        identical pattern Phasor's own mount already uses), it never
        redeclares WW_PLAYBACK_SPEEDS or a second option list."""
        source = _source()
        body = _function_body(source, "// Overcurrent Analysis v1 -- the SECOND Analysis-menu analyzer.", "function wwOvercurrentResetState")
        assert "WW_PLAYBACK_SPEEDS" not in body
        assert '<option value="0.05"' not in body
        assert body.count('querySelector(".ww-tg-playback-speed-select")') == 1


class TestCurveCachingNotRefetchedPerTick:
    def test_curve_fetch_only_when_characteristic_or_tms_differs_from_cache(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentEnsureCurveAndRenderPoint(result)", "function wwOvercurrentChartGeometry")
        assert "cache.characteristicId === s.characteristicId && cache.tms === s.tms" in fn

    def test_settings_change_forces_exact_not_throttled_fetch(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentHandleSettingsChanged()", "function wwOvercurrentResetState")
        assert "wwOvercurrentRequestExactPlaybackFetch()" in fn


class TestClearWorkspaceLifecycle:
    def test_wwclearworkspace_resets_overcurrent_state(self):
        source = _source()
        fn = _function_body(source, "function wwClearWorkspace(options)", "for (const panel of ww.panels)")
        assert "wwOvercurrentResetState();" in fn


class TestAxisRepresentationToggleMarkupAndDefaults:
    """Chart UX enhancement -- Feature A: the compact X-axis representation
    toggle. Default Pickup Multiple; a purely frontend chart-display
    choice, never a different calculation (see TestAxisTransformMath below
    for the exact `Irelay = M * Ipickup` proof)."""

    def test_toggle_buttons_exist(self):
        source = _source()
        assert 'id="wwOvercurrentAxisModePickupBtn"' in source
        assert 'id="wwOvercurrentAxisModeRelayBtn"' in source
        assert 'data-axis-mode="pickup_multiple"' in source
        assert 'data-axis-mode="relay_current"' in source

    def test_minor_grid_checkboxes_exist(self):
        source = _source()
        assert 'id="wwOvercurrentMinorGridXCheckbox"' in source
        assert 'id="wwOvercurrentMinorGridYCheckbox"' in source
        assert 'type="checkbox"' in _function_body(source, 'id="wwOvercurrentMinorGridXCheckbox"', 'id="wwOvercurrentMinorGridYCheckbox"')

    def test_default_axis_mode_is_pickup_multiple(self):
        source = _source()
        assert "const WW_OC_XAXIS_PICKUP_MULTIPLE = \"pickup_multiple\";" in source
        assert "const WW_OC_XAXIS_RELAY_CURRENT = \"relay_current\";" in source
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchCharacteristics")
        assert "xAxisMode: WW_OC_XAXIS_PICKUP_MULTIPLE," in fn

    def test_default_minor_grid_toggles_are_off(self):
        source = _source()
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchCharacteristics")
        assert "minorGridX: false," in fn
        assert "minorGridY: false," in fn

    def test_reset_state_also_resets_axis_mode_and_grid_toggles(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")
        assert "wwOvercurrentState.xAxisMode = WW_OC_XAXIS_PICKUP_MULTIPLE;" in fn
        assert "wwOvercurrentState.minorGridX = false;" in fn
        assert "wwOvercurrentState.minorGridY = false;" in fn


class TestAxisRepresentationToggleBehavior:
    def test_set_axis_mode_never_touches_backend_or_playback(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetXAxisMode(mode)", "function wwOvercurrentSyncAxisModeButtons")
        assert "wwOvercurrentFetchCurve" not in fn
        assert "wwOvercurrentFetchAnalysis" not in fn
        assert "wwPlayback" not in fn
        assert "wwOvercurrentHandleSettingsChanged" not in fn
        assert "wwOvercurrentRerenderChartFromState();" in fn

    def test_set_axis_mode_remembers_each_modes_own_x_range(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetXAxisMode(mode)", "function wwOvercurrentSyncAxisModeButtons")
        assert "wwOvercurrentState.savedXRangeByMode[wwOvercurrentState.xAxisMode] =" in fn
        assert "const saved = wwOvercurrentState.savedXRangeByMode[mode];" in fn

    def test_set_axis_mode_never_touches_y_bounds(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetXAxisMode(mode)", "function wwOvercurrentSyncAxisModeButtons")
        assert "yMin: wwOvercurrentState.viewport.yMin, yMax: wwOvercurrentState.viewport.yMax," in fn

    def test_toggle_wiring_never_calls_settings_changed_or_playback(self):
        source = _source()
        fn = _function_body(
            source,
            'document.getElementById("wwOvercurrentAxisModePickupBtn").addEventListener',
            "wwPlaybackOnTick(wwOvercurrentOnPlaybackTick);",
        )
        assert "wwOvercurrentHandleSettingsChanged" not in fn
        assert "wwPlaybackSeek" not in fn
        assert "wwOvercurrentSetXAxisMode(WW_OC_XAXIS_PICKUP_MULTIPLE)" in fn
        assert "wwOvercurrentSetXAxisMode(WW_OC_XAXIS_RELAY_CURRENT)" in fn


class TestAxisTransformMath:
    """Executes the frontend's own conversion helpers via Node -- proves
    the exact bidirectional `Irelay = M * Ipickup` relationship (task's
    own golden example: pickup 0.8 A, M=2.5 -> relay current 2.0 A) and
    that the guardrails never divide/multiply by a non-finite or
    non-positive pickup."""

    def test_multiple_to_relay_current_matches_owner_golden_example(self):
        import json
        import subprocess

        source = _source()
        to_relay = _function_body(source, "function wwOvercurrentMultipleToRelayCurrent(multiple, pickup)", "function wwOvercurrentRelayCurrentToMultiple")
        to_multiple = _function_body(source, "function wwOvercurrentRelayCurrentToMultiple(relayCurrent, pickup)", "function wwOvercurrentOperatingPointX")
        script = to_relay + "\n" + to_multiple + """
        console.log(JSON.stringify({
            relay: wwOvercurrentMultipleToRelayCurrent(2.5, 0.8),
            multiple: wwOvercurrentRelayCurrentToMultiple(2.0, 0.8),
            nullOnBadPickup: wwOvercurrentMultipleToRelayCurrent(2.5, 0),
            nullOnNonFinite: wwOvercurrentRelayCurrentToMultiple(NaN, 0.8),
        }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["relay"] == pytest.approx(2.0)
        assert data["multiple"] == pytest.approx(2.5)
        assert data["nullOnBadPickup"] is None
        assert data["nullOnNonFinite"] is None

    def test_round_trip_is_exact_for_a_range_of_pickups_and_multiples(self):
        import json
        import subprocess

        source = _source()
        to_relay = _function_body(source, "function wwOvercurrentMultipleToRelayCurrent(multiple, pickup)", "function wwOvercurrentRelayCurrentToMultiple")
        to_multiple = _function_body(source, "function wwOvercurrentRelayCurrentToMultiple(relayCurrent, pickup)", "function wwOvercurrentOperatingPointX")
        script = to_relay + "\n" + to_multiple + """
        const rows = [];
        for (const pickup of [0.1, 0.5, 0.8, 1.0, 5.0]) {
            for (const multiple of [1.5, 2.0, 2.5, 10.0, 40.0]) {
                const relay = wwOvercurrentMultipleToRelayCurrent(multiple, pickup);
                const recovered = wwOvercurrentRelayCurrentToMultiple(relay, pickup);
                rows.push({ pickup, multiple, relay, recovered });
            }
        }
        console.log(JSON.stringify(rows));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        rows = json.loads(result.stdout)
        assert len(rows) == 25
        for row in rows:
            assert row["recovered"] == pytest.approx(row["multiple"], rel=1e-12)


class TestOperatingPointXPicksTheActiveModesField:
    def test_operating_point_x_selects_relay_current_or_multiple_by_mode(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentOperatingPointX(result)", "function wwOvercurrentRelayCurrentAbsoluteBounds")
        assert "result.relay_secondary_current" in fn
        assert "result.multiple_of_pickup" in fn
        assert "WW_OC_XAXIS_RELAY_CURRENT" in fn

    def test_render_call_sites_use_the_mode_aware_helper(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentEnsureCurveAndRenderPoint(result)", "// ---- Chart: log(M) x log(t) TCC-style plot")
        assert fn.count("wwOvercurrentOperatingPointX(") == 2
        assert "result.multiple_of_pickup" not in fn
        rerender_fn = _function_body(source, "function wwOvercurrentRerenderChartFromState()", "function wwOvercurrentSyncViewportInputs")
        assert "wwOvercurrentOperatingPointX(latest)" in rerender_fn


class TestCurveTransformForRelayCurrentMode:
    """Task §14: the exact curve-viewport-boundary solution stays
    authoritative in the M domain; Relay Current mode transforms the
    exact M-domain intersections via `Irelay = M * Ipickup`, never a
    second numeric solve."""

    def test_render_chart_solves_in_m_domain_then_transforms_to_amps(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        curve_block = _function_body(fn, "if (points && points.length > 0) {", "// Operating point")
        assert "wwOvercurrentRelayCurrentToMultiple(viewport.xMin, pickup)" in curve_block
        assert "wwOvercurrentRelayCurrentToMultiple(viewport.xMax, pickup)" in curve_block
        assert "wwOvercurrentMultipleToRelayCurrent(p[0], pickup)" in curve_block

    def test_pickup_multiple_mode_passes_the_viewport_through_unchanged(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        curve_block = _function_body(fn, "if (points && points.length > 0) {", "// Operating point")
        assert "isRelayCurrentAxis && Number.isFinite(pickup) && pickup > 0" in curve_block
        assert ": viewport;" in curve_block


class TestAxisTitleSwitchesWithMode:
    def test_relay_current_axis_title_text_present(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "Relay Current (A secondary)" in fn
        assert 'isRelayCurrentAxis ? "Relay Current (A secondary)" : "Current / Pickup Multiple (M)"' in fn


class TestPickupBoundaryReference:
    def test_pickup_boundary_line_renders_at_m_equals_one_or_pickup_amps(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "const pickupBoundaryX = isRelayCurrentAxis ? pickup : 1.0;" in fn
        assert "ww-oc-pickup-boundary" in fn

    def test_pickup_boundary_skipped_when_outside_viewport(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        boundary_block = _function_body(fn, "const pickupBoundaryX", "// The characteristic curve")
        assert "pickupBoundaryX >= viewport.xMin" in boundary_block
        assert "pickupBoundaryX <= viewport.xMax" in boundary_block


class TestMinorGridToggles:
    def test_major_gridlines_always_render_regardless_of_minor_toggles(self):
        """Major gridlines are drawn unconditionally (no `if
        (wwOvercurrentState.minorGridX/Y)` guard around the existing
        major-tick loops) -- only the NEW minor-gridline blocks are
        gated."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        major_x_block = _function_body(fn, "for (const v of xMajors) {\n                const x = wwOvercurrentPixelX(v, geo);\n                parts.push('<line class=\"ww-oc-gridline\"", "Minor grid lines")
        assert "wwOvercurrentState.minorGridX" not in major_x_block
        assert "wwOvercurrentState.minorGridY" not in major_x_block

    def test_minor_gridlines_gated_independently_per_axis(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "if (wwOvercurrentState.minorGridX) {" in fn
        assert "if (wwOvercurrentState.minorGridY) {" in fn
        assert fn.count('class="ww-oc-gridline ww-oc-gridline-minor"') == 2

    def test_minor_gridlines_use_a_lighter_class_than_major(self):
        source = _source()
        assert ".ww-oc-gridline-minor" in source

    def test_minor_x_checkbox_wiring_rerenders_without_backend_call(self):
        source = _source()
        fn = _function_body(
            source,
            'document.getElementById("wwOvercurrentMinorGridXCheckbox").addEventListener',
            'document.getElementById("wwOvercurrentMinorGridYCheckbox").addEventListener',
        )
        assert "wwOvercurrentState.minorGridX = event.target.checked;" in fn
        assert "wwOvercurrentRerenderChartFromState();" in fn
        assert "fetch" not in fn.lower()

    def test_minor_y_checkbox_wiring_rerenders_without_backend_call(self):
        source = _source()
        fn = _function_body(
            source,
            'document.getElementById("wwOvercurrentMinorGridYCheckbox").addEventListener',
            "wwOvercurrentSyncAxisModeButtons();",
        )
        assert "wwOvercurrentState.minorGridY = event.target.checked;" in fn
        assert "wwOvercurrentRerenderChartFromState();" in fn


class TestMinorTickGenerationMatrix:
    """Task §9: the classic log-log graph-paper 1-2-5 minor subdivision,
    proved via direct Node execution -- the owner's own explicit example
    (1.2/1.4/1.6/1.8 between 1 and 2) plus the wider decade pattern, never
    a single linear 0.2 step across the whole range."""

    def test_minor_pow125_ticks_between_1_and_2_match_owner_example(self):
        import json
        import subprocess

        source = _source()
        fn = _function_body(source, "function wwOvercurrentGenerateMinorPow125Ticks(min, max)", "function wwOvercurrentGenerateMinorDecadeTicks")
        const_decl = "const WW_OC_MINOR_POW125_SUBDIVISIONS = [[1, 2, 0.2], [2, 5, 0.5], [5, 10, 1]];\n"
        script = const_decl + fn + "\nconsole.log(JSON.stringify(wwOvercurrentGenerateMinorPow125Ticks(1, 2)));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        ticks = json.loads(result.stdout)
        assert ticks == pytest.approx([1.2, 1.4, 1.6, 1.8])

    def test_minor_pow125_ticks_full_decade_use_log_appropriate_subdivisions(self):
        import json
        import subprocess

        source = _source()
        fn = _function_body(source, "function wwOvercurrentGenerateMinorPow125Ticks(min, max)", "function wwOvercurrentGenerateMinorDecadeTicks")
        const_decl = "const WW_OC_MINOR_POW125_SUBDIVISIONS = [[1, 2, 0.2], [2, 5, 0.5], [5, 10, 1]];\n"
        script = const_decl + fn + "\nconsole.log(JSON.stringify(wwOvercurrentGenerateMinorPow125Ticks(1, 10)));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        ticks = json.loads(result.stdout)
        # Never a uniform linear 0.2 step across the whole 1->10 range --
        # the step widens per sub-interval (0.2 within 1-2, 0.5 within
        # 2-5, 1 within 5-10).
        assert ticks == pytest.approx([1.2, 1.4, 1.6, 1.8, 2.5, 3.0, 3.5, 4.0, 4.5, 6, 7, 8, 9])

    def test_minor_decade_ticks_are_the_standard_2_to_9_log_paper_set(self):
        import json
        import subprocess

        source = _source()
        fn = _function_body(source, "function wwOvercurrentGenerateMinorDecadeTicks(min, max)", "function wwOvercurrentXMinors")
        script = fn + "\nconsole.log(JSON.stringify(wwOvercurrentGenerateMinorDecadeTicks(0.01, 100)));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        ticks = json.loads(result.stdout)
        expected = [round(b * 10 ** e, 10) for e in range(-2, 2) for b in range(2, 10)]
        assert ticks == pytest.approx(expected)


class TestRelayCurrentAxisAlignedWithPickupMultiple:
    """Relay Current is related to
    Pickup Multiple by Irelay = M * Ipickup, so Relay Current's own
    default viewport, major ticks, and minor ticks must all derive from
    the SAME M-domain positions Pickup Multiple uses, scaled by the
    current pickup -- never hard-coded amp values or an independently-
    derived current-domain classification. Golden scenario throughout:
    pickup = 0.8 A secondary (task's own worked example)."""

    def _harness(self, pickup=0.8):
        source = _source()
        pieces = [
            f'const wwOvercurrentState = {{ settings: {{ pickupCurrentSecondary: {pickup} }} }};',
            _function_body(source, "const WW_OC_VIEWPORT_DEFAULT = { xMin: 0.1, xMax: 100, yMin: 0.1, yMax: 100 };", "function wwOvercurrentIsDefaultViewport"),
            _function_body(source, "const WW_OC_PICKUP_MULTIPLE_MAJOR_TICKS = [0.1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100];", "function wwOvercurrentFormatTickValue"),
            _function_body(source, "function wwOvercurrentRelayCurrentAbsoluteBounds()", "function wwOvercurrentActiveXAbsoluteBounds"),
            "const WW_OC_MINOR_POW125_SUBDIVISIONS = [[1, 2, 0.2], [2, 5, 0.5], [5, 10, 1]];",
            _function_body(source, "function wwOvercurrentPickupMultipleSubPickupMinors(viewport)", "function wwOvercurrentXMinors"),
        ]
        return "\n".join(pieces)

    def _run(self, script):
        import json
        import subprocess

        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_default_relay_current_viewport_is_0_08_to_80_at_pickup_0_8(self):
        script = self._harness(pickup=0.8) + "\nconsole.log(JSON.stringify(wwOvercurrentRelayCurrentDefaultViewport()));"
        viewport = self._run(script)
        assert viewport["xMin"] == pytest.approx(0.08, rel=1e-9)
        assert viewport["xMax"] == pytest.approx(80, rel=1e-9)

    def test_relay_current_majors_are_m_domain_list_scaled_by_pickup(self):
        script = self._harness(pickup=0.8) + """
        const viewport = { xMin: 0.08, xMax: 80 };
        console.log(JSON.stringify(wwOvercurrentRelayCurrentMajors(viewport)));
        """
        majors = self._run(script)
        assert majors == pytest.approx([0.08, 0.8, 1.6, 2.4, 3.2, 4.0, 4.8, 5.6, 6.4, 7.2, 8.0, 16, 40, 80])

    def test_golden_m_to_ampere_worked_examples(self):
        """M=1 -> 0.8 A, M=2 -> 1.6 A, M=3 -> 2.4 A, M=10 -> 8 A,
        M=20 -> 16 A, M=50 -> 40 A, M=100 -> 80 A."""
        script = self._harness(pickup=0.8) + """
        const viewport = { xMin: 0.08, xMax: 80 };
        const majors = wwOvercurrentRelayCurrentMajors(viewport);
        console.log(JSON.stringify(majors));
        """
        majors = self._run(script)
        expected_m = [0.1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100]
        for m, tick in zip(expected_m, majors):
            assert tick == pytest.approx(m * 0.8, rel=1e-9)

    def test_relay_current_majors_include_the_viewports_own_minimum(self):
        script = self._harness(pickup=0.8) + """
        const viewport = { xMin: 0.08, xMax: 80 };
        console.log(JSON.stringify(wwOvercurrentRelayCurrentMajors(viewport)));
        """
        majors = self._run(script)
        assert majors[0] == pytest.approx(0.08, rel=1e-9)

    def test_relay_current_minors_are_m_domain_minors_scaled_by_pickup(self):
        """Between M=1 and M=2, the M-domain minors are 1.2/1.4/1.6/1.8
        -- at pickup 0.8 A these become 0.96/1.12/1.28/1.44 A."""
        script = self._harness(pickup=0.8) + """
        const viewport = { xMin: 0.8, xMax: 1.6 };
        console.log(JSON.stringify(wwOvercurrentRelayCurrentMinors(viewport)));
        """
        minors = self._run(script)
        assert minors == pytest.approx([0.96, 1.12, 1.28, 1.44])

    def test_relay_current_default_viewport_tracks_a_pickup_change(self):
        """A different pickup produces a proportionally different
        default -- never a stale/cached value from an earlier pickup."""
        script = self._harness(pickup=1.0) + "\nconsole.log(JSON.stringify(wwOvercurrentRelayCurrentDefaultViewport()));"
        viewport = self._run(script)
        assert viewport["xMin"] == pytest.approx(0.1, rel=1e-9)
        assert viewport["xMax"] == pytest.approx(100, rel=1e-9)

    def test_relay_current_absolute_bounds_still_derive_from_the_shared_absolute_constant(self):
        """Unaffected by this correction -- already correctly pickup-
        relative before, still is."""
        script = self._harness(pickup=0.8) + "\nconsole.log(JSON.stringify(wwOvercurrentRelayCurrentAbsoluteBounds()));"
        bounds = self._run(script)
        assert bounds["xMin"] == pytest.approx(0.08, rel=1e-9)
        assert bounds["xMax"] == pytest.approx(160, rel=1e-9)


class TestRelayCurrentPickupBoundaryVisualEquivalence:
    """Relay Current and Pickup Multiple default viewports are
    geometrically equivalent: M=1 and I=pickup share a pixel, as do
    M=10 and I=10*pickup."""

    def _run(self, script):
        import json
        import subprocess

        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_default_viewports_are_pixel_equivalent_at_m_1_and_m_10(self):
        source = _source()
        geometry_fn = _function_body(source, "function wwOvercurrentChartGeometry(viewport)", "function wwOvercurrentPixelX")
        pixel_x_fn = _function_body(source, "function wwOvercurrentPixelX(m, geo)", "// Inverse of `wwOvercurrentPixelX()`")
        script = f"""
        const WW_OC_CHART_MARGIN = {{ left: 40, right: 14, top: 12, bottom: 34 }};
        const WW_OC_CHART_W = 320;
        const WW_OC_CHART_H = 240;
        {geometry_fn}
        {pixel_x_fn}
        const pickupGeo = wwOvercurrentChartGeometry({{ xMin: 0.1, xMax: 100, yMin: 0.1, yMax: 100 }});
        const relayGeo = wwOvercurrentChartGeometry({{ xMin: 0.12, xMax: 120, yMin: 0.1, yMax: 100 }});
        console.log(JSON.stringify({{
            m1: wwOvercurrentPixelX(1, pickupGeo),
            iPickup: wwOvercurrentPixelX(1.2, relayGeo),
            m10: wwOvercurrentPixelX(10, pickupGeo),
            i10Pickup: wwOvercurrentPixelX(12, relayGeo),
        }}));
        """
        positions = self._run(script)
        assert positions["m1"] == pytest.approx(positions["iPickup"], rel=1e-9)
        assert positions["m10"] == pytest.approx(positions["i10Pickup"], rel=1e-9)

    def test_pickup_boundary_value_in_relay_current_mode_is_the_pickup_itself(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "const pickupBoundaryX = isRelayCurrentAxis ? pickup : 1.0;" in fn


class TestRelayCurrentModeSwitchZeroBackendRequests:
    """Switching X-axis representation modes -- including with the new
    pickup-scaled default/majors/minors -- must remain frontend-only,
    reusing the already-fetched curve/already-computed result verbatim
    (unchanged invariant from DEC-092, re-verified after this axis-
    alignment correction)."""

    def test_set_x_axis_mode_never_calls_fetch(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetXAxisMode(mode)", "function wwOvercurrentSyncAxisModeButtons")
        assert "fetch(" not in fn
        assert "wwOvercurrentFetchAnalysis" not in fn
        assert "wwOvercurrentFetchCurve" not in fn

    def test_relay_current_majors_minors_default_viewport_never_call_fetch(self):
        source = _source()
        for fn_name, next_name in [
            ("function wwOvercurrentRelayCurrentMajors(viewport)", "function wwOvercurrentFormatTickValue"),
            ("function wwOvercurrentRelayCurrentMinors(viewport)", "function wwOvercurrentXMinors"),
            ("function wwOvercurrentRelayCurrentDefaultViewport()", "function wwOvercurrentActiveXAbsoluteBounds"),
        ]:
            fn = _function_body(source, fn_name, next_name)
            assert "fetch(" not in fn


class TestSettingsFormLayoutCorrection:
    """Owner UAT correction (2026-09-16): the PRIOR redesign gave each
    settings field a fixed pixel width (200px/140px/90px/etc), which
    could exceed its actual grid cell inside the real (often narrower
    than a full viewport) settings card -- overflowing into the
    neighboring column. Corrected to a container-responsive grid
    (`minmax(0, 1fr)` columns + `width: 100%` controls) so a control can
    never be wider than the space genuinely available to it, and the
    owner-mandated exact control CSS is restored. Presentation/layout
    only -- field ids, input types/attributes/validation are untouched,
    so every existing functional test in this file continues to pass
    unmodified."""

    def test_settings_grid_uses_container_responsive_columns_never_fixed_widths(self):
        source = _source()
        css_rule = _function_body(source, ".ww-oc-settings-grid {", "}")
        assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in css_rule
        # The old brittle fixed-pixel-per-field rules are gone entirely.
        for selector in [
            "#wwOvercurrentCharacteristicSelect { width:",
            "#wwOvercurrentBasisSelect { width:",
            "#wwOvercurrentPickupInput { width:",
            "#wwOvercurrentTmsInput { width:",
            "#wwOvercurrentCtPrimaryInput { width:",
            "#wwOvercurrentCtSecondaryInput { width:",
        ]:
            assert selector not in source

    def test_field_wrapper_allows_its_grid_track_to_shrink_below_content_size(self):
        source = _source()
        scoped_rule = _function_body(source, ".ww-oc-settings-grid .ww-phasor-field {", "}")
        assert "min-width: 0;" in scoped_rule
        # Phasor's own context-bar fields elsewhere keep their original
        # 220px min-width -- this override is scoped to the OC grid only.
        base_rule = _function_body(source, ".ww-phasor-field {", ".ww-phasor-field[hidden]")
        assert "min-width: 220px;" in base_rule

    def test_controls_use_the_exact_owner_mandated_css_properties(self):
        """Acceptance criteria (2026-09-16, not a suggestion): every
        settings control must carry exactly these six properties --
        the SAME values the page's own global `select {}` baseline
        already uses, not the prior pass's own compact override."""
        source = _source()
        css_rule = _function_body(source, ".ww-oc-settings-grid select,", ":focus")
        assert "background: var(--panel);" in css_rule
        assert "border: 1px solid var(--panel-border);" in css_rule
        assert "border-radius: var(--radius);" in css_rule
        assert "padding: 8px 10px;" in css_rule
        assert "font-size: 0.7rem;" in css_rule
        assert "color: var(--text);" in css_rule
        assert "width: 100%;" in css_rule
        assert "box-sizing: border-box;" in css_rule

    def test_focus_state_is_preserved(self):
        source = _source()
        focus_rule = _function_body(source, ".ww-oc-settings-grid select:focus,", "}")
        assert "outline: none;" in focus_rule
        assert "border-color: var(--accent-dim);" in focus_rule

    def test_characteristic_and_basis_span_the_full_row_never_squeezed_to_half_width(self):
        source = _source()
        assert 'class="ww-phasor-field ww-oc-field-full">\n                                            <span class="ww-phasor-field-label">Characteristic</span>' in source
        assert 'class="ww-phasor-field ww-oc-field-full">\n                                            <span class="ww-phasor-field-label">Recording current basis</span>' in source
        css_rule = _function_body(source, ".ww-oc-field-full {", "}")
        assert "grid-column: 1 / -1;" in css_rule
        # Pickup/TMS and the two CT fields deliberately do NOT get this
        # class -- they fall through to the grid's own 2-column
        # auto-flow, pairing two-per-row.
        pickup_label = _function_body(source, '<span class="ww-phasor-field-label">Pickup current</span>', "</label>")
        assert "ww-oc-field-full" not in source[source.index('id="wwOvercurrentPickupInput"') - 300 : source.index('id="wwOvercurrentPickupInput"')]

    def test_pickup_label_shortened_with_unit_moved_inline_next_to_the_value(self):
        """Replaces the former "Pickup current (A secondary)" label
        (which wrapped to two lines in a narrow column) -- the unit
        stays fully explicit, just positioned next to the VALUE."""
        source = _source()
        assert '<span class="ww-phasor-field-label">Pickup current</span>' in source
        assert '<span class="ww-phasor-field-label">Pickup current (A secondary)</span>' not in source
        assert '<span class="ww-oc-field-unit">A secondary</span>' in source
        input_row_rule = _function_body(source, ".ww-oc-field-input-row {", "}")
        assert "display: flex;" in input_row_rule
        assert "min-width: 0;" in input_row_rule

    def test_other_five_labels_unchanged(self):
        source = _source()
        assert '<span class="ww-phasor-field-label">Characteristic</span>' in source
        assert '<span class="ww-phasor-field-label">TMS</span>' in source
        assert '<span class="ww-phasor-field-label">Recording current basis</span>' in source
        assert '<span class="ww-phasor-field-label">CT Primary (A)</span>' in source
        assert '<span class="ww-phasor-field-label">CT Secondary (A)</span>' in source

    def test_field_ids_types_and_validation_attributes_are_byte_for_byte_unchanged(self):
        """Presentation/layout only -- every functionally-relevant
        attribute (id, type, min/max/step/value) is untouched."""
        source = _source()
        assert 'id="wwOvercurrentCharacteristicSelect"></select>' in source
        assert 'type="number" id="wwOvercurrentPickupInput" min="0" step="0.01" value="1.00">' in source
        assert 'type="number" id="wwOvercurrentTmsInput" min="0.025" max="1.2" step="0.005" value="0.10">' in source
        assert 'type="number" id="wwOvercurrentCtPrimaryInput" min="0" step="1">' in source
        assert 'type="number" id="wwOvercurrentCtSecondaryInput" min="0" step="0.01">' in source
        assert 'id="wwOvercurrentBasisSelect">' in source

    def test_responsive_fallback_uses_a_container_query_scoped_to_the_settings_card_not_the_viewport(self):
        """Owner's own explicit instruction: "the important dimension is
        the actual width of the SETTINGS / LIVE VALUES card... do not
        use a global page-wide breakpoint." A CSS container query
        (`container-type` on `.ww-phasor-values-panel` itself) responds
        to the CARD's own rendered width, never the browser viewport."""
        source = _source()
        panel_rule = _function_body(source, ".ww-phasor-values-panel {", "}")
        assert "container-type: inline-size;" in panel_rule
        assert "@container ww-oc-settings-panel" in source
        container_block = _function_body(source, "@container ww-oc-settings-panel", "\n        .ww-oc-values-list")
        assert "grid-template-columns: minmax(0, 1fr);" in container_block


class TestChartControlsToolbarRedesign:
    """UI/UX-only redesign (2026-09-16) of the OC chart control toolbar --
    View X/Y Min/Max, Zoom -/+/Reset, the Pickup Multiple/Relay Current
    axis-mode toggle, and the Minor grid X/Y checkboxes. No OC math,
    viewport semantics, IDMT logic, or network behavior is touched by
    any assertion in this class -- see TestOvercurrentViewport,
    TestAxisRepresentationToggleBehavior, and TestMinorGridToggles for
    the untouched behavioral coverage. Markup itself was already close
    to the target two-row toolbar shape; this redesign is CSS-only."""

    def test_view_inputs_carry_the_exact_owner_mandated_css_properties(self):
        source = _source()
        css_rule = _function_body(source, '.ww-oc-view-field input[type="number"] {', "}")
        assert "background: var(--panel);" in css_rule
        assert "border: 1px solid var(--panel-border);" in css_rule
        assert "border-radius: var(--radius);" in css_rule
        assert "padding: 6px 8px;" in css_rule
        assert "font-size: 0.7rem;" in css_rule
        assert "color: var(--text);" in css_rule
        assert "box-sizing: border-box;" in css_rule

    def test_view_input_width_is_within_the_owner_target_range(self):
        """Target ~48-55px -- wide enough for "1000"/"0.1" without
        clipping, per the task's own explicit examples."""
        source = _source()
        css_rule = _function_body(source, '.ww-oc-view-field input[type="number"] {', "}")
        match = re.search(r"width:\s*(\d+)px;", css_rule)
        assert match is not None
        width = int(match.group(1))
        assert 48 <= width <= 55

    def test_view_row_and_axis_row_stay_two_wrapping_flex_rows(self):
        """The two logical rows (View/Zoom, then X-axis/Minor grid) each
        wrap independently -- never a single unbroken row that could
        overflow a narrower panel, and never collapsed into one row."""
        source = _source()
        view_rule = _function_body(source, ".ww-oc-view-controls {", "}")
        assert "display: flex;" in view_rule
        assert "flex-wrap: wrap;" in view_rule
        axis_rule = _function_body(source, ".ww-oc-axis-controls {", "}")
        assert "display: flex;" in axis_rule
        assert "flex-wrap: wrap;" in axis_rule

    def test_zoom_and_reset_buttons_are_grouped_and_compact(self):
        source = _source()
        group_rule = _function_body(source, ".ww-oc-view-zoom-group {", "}")
        assert "display: inline-flex;" in group_rule
        btn_rule = _function_body(source, ".ww-oc-zoom-btn {", "}")
        assert "font-size: 0.7rem;" in btn_rule
        assert 'id="wwOvercurrentZoomOutBtn" class="ww-oc-zoom-btn"' in source
        assert 'id="wwOvercurrentZoomInBtn" class="ww-oc-zoom-btn"' in source
        assert 'id="wwOvercurrentResetViewBtn" class="ww-oc-zoom-btn ww-oc-reset-btn"' in source

    def test_axis_toggle_group_forms_one_shared_rounded_segmented_shape(self):
        """Never two independent buttons, never a single toggle switch --
        one bordered/rounded outer container clips both segments to a
        shared shape via `overflow: hidden`."""
        source = _source()
        group_rule = _function_body(source, ".ww-oc-axis-toggle-group {", "}")
        assert "display: inline-flex;" in group_rule
        assert "border-radius: var(--radius);" in group_rule
        assert "overflow: hidden;" in group_rule
        # Individual segments have no independent radius/border of their
        # own -- the shared shape comes only from the group above.
        btn_rule = _function_body(source, ".ww-oc-axis-toggle-btn {", ".ww-oc-axis-toggle-btn + .ww-oc-axis-toggle-btn")
        assert "border-radius: 0;" in btn_rule

    def test_minor_grid_checkboxes_are_compact_and_use_the_accent_color(self):
        source = _source()
        checkbox_rule = _function_body(source, '.ww-oc-grid-toggle-field input[type="checkbox"] {', "}")
        assert "width: 14px;" in checkbox_rule
        assert "height: 14px;" in checkbox_rule
        assert "accent-color: var(--accent);" in checkbox_rule
        field_rule = _function_body(source, ".ww-oc-grid-toggle-field {", "}")
        assert "align-items: center;" in field_rule
        assert 'class="ww-oc-grid-toggle-field"><input type="checkbox" id="wwOvercurrentMinorGridXCheckbox"> X</label>' in source
        assert 'class="ww-oc-grid-toggle-field"><input type="checkbox" id="wwOvercurrentMinorGridYCheckbox"> Y</label>' in source


class TestManualInputCalculatorMode:
    """Manual Input / Calculator mode -- the first implementation of the
    shared Analysis Input Source concept (see
    docs/project-memory/ANALYSIS_INPUT_SOURCE.md). No IEC IDMT
    calculation, CT conversion, or engineering-unit normalization is
    duplicated here -- every assertion in this class is about UI/state
    wiring; the actual calculation is exercised end-to-end by
    test_overcurrent_analysis_api.py::TestManualAnalysisEndpoint and
    test_overcurrent_analysis_service.py::TestManualOvercurrentAnalysis."""

    def test_shared_input_source_constants_are_not_oc_specific(self):
        """Task's own explicit "do not make the shared state OC-specific
        if avoidable" -- named `WW_ANALYSIS_*`, not `WW_OC_*`, so a
        future analyzer's own manual mode reuses these SAME two
        constants."""
        source = _source()
        assert 'const WW_ANALYSIS_INPUT_SOURCE_RECORDING = "recording";' in source
        assert 'const WW_ANALYSIS_INPUT_SOURCE_MANUAL = "manual";' in source

    def test_oc_state_owns_its_own_input_source_and_manual_fields(self):
        """Input-source selection is per-analyzer (mirrors
        `selectedContextId`'s own established precedent) -- OC's manual
        value state lives on `wwOvercurrentState`, never a shared/global
        object a future analyzer could accidentally collide with."""
        source = _source()
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchCharacteristics")
        assert "inputSource: WW_ANALYSIS_INPUT_SOURCE_RECORDING," in fn
        assert "manual: {" in fn
        assert "inputCurrent: 30000," in fn
        assert 'inputCurrentUnit: "A",' in fn
        assert 'inputBasis: "primary",' in fn
        assert "latestResult: null," in fn

    def test_input_source_segmented_control_markup(self):
        source = _source()
        assert 'id="wwOvercurrentInputSourceRecordingBtn" class="ww-oc-axis-toggle-btn ww-oc-axis-toggle-btn--active" data-input-source="recording" aria-pressed="true">Recording<' in source
        assert 'id="wwOvercurrentInputSourceManualBtn" class="ww-oc-axis-toggle-btn" data-input-source="manual" aria-pressed="false">Manual<' in source
        # Reuses the EXACT same segmented-control classes the Pickup
        # Multiple/Relay Current toggle already established -- visual
        # consistency, never a second toggle style (task §4).
        group_rule = _function_body(source, ".ww-oc-axis-toggle-group {", "}")
        assert "border-radius: var(--radius);" in group_rule
        assert "overflow: hidden;" in group_rule

    def test_manual_input_section_markup_and_default_hidden(self):
        source = _source()
        assert 'id="wwOvercurrentManualInputSection" hidden>' in source
        assert 'id="wwOvercurrentManualCurrentInput" min="0" step="1" value="30000"' in source
        assert 'id="wwOvercurrentManualUnitSelect"' in source
        assert '<option value="A" selected>A</option>' in source
        assert '<option value="kA">kA</option>' in source
        assert 'id="wwOvercurrentManualBasisSelect"' in source
        assert '<option value="primary" selected>Primary</option>' in source
        assert '<option value="secondary">Secondary</option>' in source

    def test_relay_settings_are_never_duplicated_inside_the_manual_section(self):
        """Task §5: Characteristic/Pickup/TMS/Recording basis/CT must
        never be repeated inside the Manual Input section -- only the
        current VALUE'S OWN source/basis/unit fields live there."""
        source = _source()
        manual_section = _function_body(
            source, 'id="wwOvercurrentManualInputSection"', '<div class="ww-oc-values-list"'
        )
        for forbidden_id in (
            "wwOvercurrentCharacteristicSelect", "wwOvercurrentPickupInput", "wwOvercurrentTmsInput",
            "wwOvercurrentBasisSelect", "wwOvercurrentCtPrimaryInput", "wwOvercurrentCtSecondaryInput",
        ):
            assert forbidden_id not in manual_section

    def test_set_input_source_switches_state_and_ui_never_touches_relay_settings(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetInputSource(mode, isAutomatic)", "function wwOvercurrentSyncInputSourceButtons")
        assert "wwOvercurrentState.inputSource = mode;" in fn
        assert "wwOvercurrentSyncInputSourceButtons();" in fn
        assert "wwOvercurrentUpdateManualSectionVisibility();" in fn
        assert "wwOvercurrentUpdateCtFieldsVisibility();" in fn
        assert "wwOvercurrentState.settings" not in fn  # never touches the shared relay settings object

    def test_switching_to_manual_triggers_manual_recompute_switching_back_forces_exact_recording_refresh(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetInputSource(mode, isAutomatic)", "function wwOvercurrentSyncInputSourceButtons")
        assert "wwOvercurrentRequestManualAnalysis();" in fn
        assert "wwOvercurrentRequestExactPlaybackFetch();" in fn

    def test_handle_settings_changed_dispatches_by_active_input_source(self):
        """Task §5's own "switching mode must not alter relay settings" +
        "settings stay authoritative in both modes" -- ONE shared
        settings-changed handler, dispatching to whichever pipeline is
        currently active."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentHandleSettingsChanged()", "// ---- Manual Input")
        assert "WW_ANALYSIS_INPUT_SOURCE_MANUAL" in fn
        assert "wwOvercurrentRequestManualAnalysis();" in fn
        assert "wwOvercurrentRequestExactPlaybackFetch();" in fn

    def test_manual_input_validity_guard_rejects_blank_nan_infinity_negative_zero(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentManualInputIsValid()", "function wwOvercurrentRequestManualAnalysis")
        assert "Number.isFinite(value)" in fn
        assert "value > 0" in fn

    def test_request_manual_analysis_never_fires_for_invalid_input(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRequestManualAnalysis()", "function wwOvercurrentRenderManualResult")
        assert "if (!wwOvercurrentManualInputIsValid())" in fn
        assert "wwOvercurrentFetchManualAnalysis" in fn
        # The early-invalid branch returns before ever reaching the fetch call.
        invalid_branch = _function_body(fn, "if (!wwOvercurrentManualInputIsValid()) {", "}")
        assert "wwOvercurrentFetchManualAnalysis" not in invalid_branch

    def test_manual_fetch_reuses_the_shared_ct_settings_never_a_second_ct_input(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRequestManualAnalysis()", "function wwOvercurrentRenderManualResult")
        assert "s.ctPrimary" in fn
        assert "s.ctSecondary" in fn
        assert "recording_basis: m.inputBasis," in fn

    def test_manual_fetch_url_targets_the_workspace_scoped_manual_endpoint(self):
        source = _source()
        fn = _function_body(
            source, "function wwOvercurrentFetchManualAnalysis(workspaceId, params)", "// ---- Characteristics list",
        )
        assert '"/overcurrent-manual?"' in fn
        assert "/engineering-contexts/" not in fn

    def test_manual_request_generation_guards_against_stale_responses(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRequestManualAnalysis()", "function wwOvercurrentRenderManualResult")
        assert "++wwOvercurrentState.manualRequestGeneration" in fn
        assert "myGeneration !== wwOvercurrentState.manualRequestGeneration" in fn
        assert "epochAtStart !== ww.epoch" in fn
        assert "currentWorkspaceId() !== workspaceId" in fn

    def test_render_manual_result_shows_exactly_the_three_task_specified_rows(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderManualResult(result)", "function wwOvercurrentResetState")
        assert '"Relay-equivalent current"' in fn
        assert '"Multiple of pickup"' in fn
        assert '"Expected operating time"' in fn
        # None of the recording-only rows ever appear in Manual mode.
        for forbidden_row in ("Measured RMS current", '"Pickup"', "Above-pickup duration"):
            assert forbidden_row not in fn

    def test_render_manual_result_below_pickup_wording(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderManualResult(result)", "function wwOvercurrentResetState")
        assert '"< 1 ×"' in fn
        assert '"Not applicable / below pickup"' in fn

    def test_render_manual_result_guards_against_being_called_while_not_in_manual_mode(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderManualResult(result)", "function wwOvercurrentResetState")
        assert "if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_MANUAL) return;" in fn

    def test_render_result_guards_against_being_called_while_in_manual_mode(self):
        """The reverse guard -- a stale/late-resolving RECORDING fetch
        must never clobber the Manual UI."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderResult(result)", "function wwOvercurrentComputeActiveRelatedWaveformRoles")
        assert "if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING) return;" in fn

    def test_manual_result_never_shows_the_threshold_alert(self):
        """No above-pickup-DURATION concept exists for a standalone
        manual value -- the qualified threshold_exceeded alert never
        applies in Manual mode."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderManualResult(result)", "function wwOvercurrentResetState")
        assert "alertEl.hidden = true;" in fn
        assert "threshold_exceeded" not in fn

    def test_playback_tick_gated_off_entirely_in_manual_mode(self):
        """Task §12: manual OC calculation must not depend on
        wwPlayback.currentTime, and the operating point must remain
        stable while Playback moves -- the fetch-triggering half of the
        tick handler is gated on the active input source; the transport-
        UI-sync half above stays unconditional (shared/global Playback)."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentOnPlaybackTick(currentTime, playback)", "// ---- Throttled")
        assert 'if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING) return;' in fn
        # The guard sits AFTER the transport-controls sync block (still
        # runs regardless of mode) but BEFORE the fetch-triggering branch.
        guard_index = fn.index("WW_ANALYSIS_INPUT_SOURCE_RECORDING) return;")
        sync_index = fn.index("wwSyncPlaybackControls")
        fetch_index = fn.index("wwOvercurrentMaybeFetchForPlayback();")
        assert sync_index < guard_index < fetch_index

    def test_related_waveform_roles_are_empty_in_manual_mode_never_a_fabricated_waveform(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentComputeActiveRelatedWaveformRoles()", "function wwOvercurrentPushRelatedWaveformRoles")
        assert "if (wwOvercurrentState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING) return [];" in fn

    def test_ensure_curve_and_render_point_is_shared_verbatim_between_both_modes(self):
        """No separate manual-only chart-rendering path -- the SAME
        function, threading only a cosmetic `isManual` flag through to
        wwOvercurrentRenderChart() for its own "Manual input point"
        treatment (task §2: never a second, manual-only engine)."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentEnsureCurveAndRenderPoint(result)", "// ---- Chart:")
        assert "const isManual = wwOvercurrentState.inputSource === WW_ANALYSIS_INPUT_SOURCE_MANUAL;" in fn
        assert fn.count("wwOvercurrentRenderChart(") >= 2

    def test_manual_operating_point_gets_a_distinct_visual_marker_and_tooltip(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT, isManual)", "function wwOvercurrentRerenderChartFromState")
        assert "ww-oc-manual-marker" in fn
        assert "<title>Manual input point</title>" in fn
        css_rule = _function_body(source, ".ww-oc-manual-marker {", "}")
        assert "stroke-dasharray" in css_rule

    def test_reset_state_clears_input_source_and_manual_state(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")
        assert "wwOvercurrentState.inputSource = WW_ANALYSIS_INPUT_SOURCE_RECORDING;" in fn
        assert "wwOvercurrentState.manual = { inputCurrent: 30000, inputCurrentUnit: \"A\", inputBasis: \"primary\", latestResult: null };" in fn

    def test_manual_fields_use_change_event_never_per_keystroke_input_event(self):
        """Design choice (documented in the task's own final report): the
        browser's native "change" event (fires on blur/Enter, matching
        every OTHER OC settings field's own established convention) is
        the debounce mechanism -- never a live per-keystroke "input"
        listener, and never an extra timer."""
        source = _source()
        for field_id in ("wwOvercurrentManualCurrentInput", "wwOvercurrentManualUnitSelect", "wwOvercurrentManualBasisSelect"):
            assert f'document.getElementById("{field_id}").addEventListener("change"' in source
            assert f'document.getElementById("{field_id}").addEventListener("input"' not in source


class TestManualModeIsIndependentOfRecordings:
    """Architectural correction (2026-09-16): "Manual Input must be
    fully independent from waveform/event recordings." Manual mode is a
    standalone engineering calculator -- it must never require a
    recording, Engineering Context, Time Group, or Playback source to
    become usable. See docs/project-memory/ANALYSIS_INPUT_SOURCE.md.
    """

    def test_input_source_panel_lives_outside_and_before_the_recording_section(self):
        """The Input Source toggle is a permanent top-level sibling of
        the Recording-only section, never nested inside it -- otherwise
        hiding the Recording section would also hide the very control
        needed to switch back out of Manual mode. Scoped to OC's own
        panel (from `id="wwOvercurrentPanel"` to `id="wwOvercurrentRecordingSection"`)
        rather than a bare `source.index()` -- Phasor's own Manual Input
        slice reuses the identical `ww-oc-input-source-panel` class name
        (task's own "same segmented-control language as OC" instruction)
        for ITS OWN Input Source panel, which sits EARLIER in the file,
        so an unscoped search would find Phasor's occurrence instead of
        OC's."""
        source = _source()
        panel_index = source.index('id="wwOvercurrentPanel"')
        section = _function_body(source, 'id="wwOvercurrentPanel"', 'id="wwOvercurrentRecordingSection"')
        assert 'class="panel ww-oc-input-source-panel"' in section
        recording_section_index = source.index('id="wwOvercurrentRecordingSection"', panel_index)
        input_source_index = panel_index + section.index('class="panel ww-oc-input-source-panel"')
        assert panel_index < input_source_index < recording_section_index

    def test_recording_only_markup_lives_inside_the_recording_section(self):
        """Bay/Context selector, Playback panel, Related Waveforms
        anchor, and the recording empty-state all require a recording --
        they must be nested INSIDE `#wwOvercurrentRecordingSection` so
        the single `hidden` toggle on that container hides all of them
        at once."""
        source = _source()
        section = _function_body(
            source, 'id="wwOvercurrentRecordingSection"', 'id="wwOvercurrentBody"'
        )
        for required_id in (
            "wwOvercurrentContextSelect", "wwOvercurrentPhaseSelect",
            "wwOvercurrentPlaybackPanel", "wwOvercurrentRelatedWaveformsAnchor",
            "wwOvercurrentEmptyState",
        ):
            assert required_id in section

    def test_oc_body_markup_lives_outside_the_recording_section_never_gated_by_it(self):
        """Settings/Manual Input/Results/Chart (`#wwOvercurrentBody`) must
        NOT be nested inside `#wwOvercurrentRecordingSection` -- Manual
        mode's own controls must never share that container's hidden
        state."""
        source = _source()
        recording_section_start = source.index('id="wwOvercurrentRecordingSection"')
        body_index = source.index('id="wwOvercurrentBody"')
        # #wwOvercurrentBody's own <div> must close the RecordingSection's
        # <div> first -- i.e. appear as a sibling, not a descendant. The
        # simplest structural proxy already used by this file's own
        # sibling-nesting checks elsewhere: the RecordingSection's closing
        # tag comment/marker appears before wwOvercurrentBody's opening tag.
        assert recording_section_start < body_index
        assert "<!-- ALWAYS visible once the Overcurrent tab is" in source[:body_index]

    def test_recording_section_hidden_css_override_exists(self):
        """Precedent bug (`.ww-phasor-body[hidden]`,
        `.ww-phasor-panel[hidden]`, `.ww-phasor-field[hidden]`): a
        `display: flex` rule on a class defeats the browser's native
        `[hidden] { display: none }` unless explicitly overridden."""
        source = _source()
        rule = _function_body(source, "#wwOvercurrentRecordingSection {", "}")
        assert "display: flex;" in rule
        override = _function_body(source, "#wwOvercurrentRecordingSection[hidden] {", "}")
        assert "display: none;" in override

    def test_ww_overcurrent_body_never_hidden_by_show_empty_state(self):
        """`wwOvercurrentShowEmptyState()` used to hide the WHOLE
        `#wwOvercurrentBody` (which, before the correction, wrongly
        contained Manual's own controls too) -- it must no longer touch
        `#wwOvercurrentBody` at all."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentShowEmptyState(message)", "function wwOvercurrentLoadForSelectedContext")
        assert 'getElementById("wwOvercurrentBody")' not in fn

    def test_load_for_selected_context_never_touches_ww_overcurrent_body(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentLoadForSelectedContext()", "function wwOvercurrentSetInputSource")
        assert 'getElementById("wwOvercurrentBody")' not in fn

    def test_reset_state_never_hides_ww_overcurrent_body(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")
        assert 'getElementById("wwOvercurrentBody")' not in fn

    def test_empty_state_wording_never_implies_the_whole_analyzer_is_unusable(self):
        """The four `WW_OVERCURRENT_MSG_*` constants are shown exclusively
        inside the (now Recording-scoped) empty state -- their wording
        must say a recording/upload is missing, never that Overcurrent
        Analysis itself is unavailable."""
        source = _source()
        msg_block = _function_body(source, "WW_OVERCURRENT_MSG_NO_SOURCES", "function ")
        assert "No recording loaded" in msg_block
        assert "Overcurrent Analysis" not in msg_block

    def test_recording_button_disabled_and_hint_driven_by_availability(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentUpdateInputSourceAvailability()", "function wwOvercurrentSyncManualInputFields")
        assert "const available = wwOvercurrentState.contexts.length > 0;" in fn
        assert "recordingBtn.disabled = !available;" in fn
        assert "hint.hidden = available;" in fn

    def test_availability_auto_switch_never_fires_while_a_different_analyzer_tab_is_visible(self):
        """Guards against firing a background `/overcurrent-manual`
        request purely because the shared context list updated while a
        different (or no) Analysis tab is showing."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentUpdateInputSourceAvailability()", "function wwOvercurrentSyncManualInputFields")
        assert 'if (wwAnalysisActiveType !== "overcurrent") return;' in fn

    def test_availability_auto_switch_never_overrides_a_deliberate_user_choice(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentUpdateInputSourceAvailability()", "function wwOvercurrentSyncManualInputFields")
        assert "if (!wwOvercurrentState.inputSourceAutoSelected) return;" in fn

    def test_a_deliberate_manual_click_disables_future_auto_switching(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetInputSource(mode, isAutomatic)", "function wwOvercurrentSyncInputSourceButtons")
        assert "if (!isAutomatic) wwOvercurrentState.inputSourceAutoSelected = false;" in fn

    def test_switching_to_recording_is_blocked_while_recording_is_unavailable(self):
        """Prevents a stale/forced click (e.g. Playwright's `force: true`,
        or a race where the button hasn't re-disabled visually yet) from
        ever switching into a Recording state that has nothing to show."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentSetInputSource(mode, isAutomatic)", "function wwOvercurrentSyncInputSourceButtons")
        assert "if (mode === WW_ANALYSIS_INPUT_SOURCE_RECORDING && !wwOvercurrentState.recordingAvailable) return;" in fn

    def test_global_init_does_not_eagerly_call_availability_check(self):
        """A deliberately-NOT-added eager call: `wwOvercurrentState.contexts`
        starts as `[]` on every raw page load, so calling the
        availability check (and its auto-switch side effect) at global
        Init time would fire a real `/overcurrent-manual` background
        request on every page load, even for a user who never opens
        Analysis at all. The lazy trigger points
        (`wwOvercurrentOnAnalysisContexts`/`wwOvercurrentOnAnalysisLifecyclePhase`/
        `wwSetActiveAnalysisType`) only ever fire once Analysis has
        genuinely been rendered."""
        source = _source()
        init_block = source[source.rindex("wwOvercurrentUpdateManualSectionVisibility();"):]
        # Only ONE more matching call may exist after this point in the
        # file (the resize/init tail), and it must NOT be the
        # availability check re-added eagerly.
        assert "wwOvercurrentUpdateInputSourceAvailability();" not in init_block[:400]

    def test_on_analysis_contexts_and_lifecycle_phase_both_refresh_availability(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentOnAnalysisContexts(contexts)", "function wwOvercurrentOnAnalysisLifecyclePhase")
        assert "wwOvercurrentUpdateInputSourceAvailability();" in fn
        fn2 = _function_body(source, "function wwOvercurrentOnAnalysisLifecyclePhase(phase)", "function wwOvercurrentOnAnalysisDiscovering")
        assert "wwOvercurrentUpdateInputSourceAvailability();" in fn2

    def test_set_active_analysis_type_rechecks_availability_for_overcurrent(self):
        source = _source()
        fn = _function_body(
            source, "function wwSetActiveAnalysisType(type)",
            'document.getElementById("wwAnalysisTypePhasorBtn")',
        )
        oc_branch_start = fn.index('else if (type === "overcurrent") {')
        oc_branch_end = fn.index("} else {", oc_branch_start)
        oc_branch = fn[oc_branch_start:oc_branch_end]
        assert "wwOvercurrentUpdateInputSourceAvailability();" in oc_branch

    def test_manual_endpoint_wiring_carries_no_context_or_source_dependency(self):
        """Reconfirms the manual fetch path (already covered from a
        different angle by `test_manual_fetch_url_targets_the_workspace_scoped_manual_endpoint`
        above) never threads a context id, source id, phase, or time
        group into the request -- workspace id is the only identifier
        it needs."""
        source = _source()
        fn = _function_body(
            source, "function wwOvercurrentRequestManualAnalysis()", "function wwOvercurrentRenderManualResult"
        )
        for forbidden in ("selectedContextId", "activeTimeGroupId", "sourceId", "phase:"):
            assert forbidden not in fn
