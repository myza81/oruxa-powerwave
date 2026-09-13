"""Static structural regression checks for Overcurrent Analysis v1
(frontend/index.html) -- the second `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is covered separately by `browser-tests/overcurrent_analysis.spec.js`.
"""

from __future__ import annotations

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

    def test_exactly_two_analysis_type_entries(self):
        source = _source()
        assert source.count('class="ww-analysis-type-item') == 2

    def test_analyzer_switcher_toggles_both_panels(self):
        source = _source()
        fn = _function_body(source, "const wwAnalysisPanelsByType", "document.getElementById(\"wwAnalysisTypePhasorBtn\")")
        assert "phasor:" in fn
        assert "overcurrent:" in fn
        assert "wwPhasorPanel" in fn
        assert "wwOvercurrentPanel" in fn
        assert "panelEl.hidden = panelType !== type;" in fn


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
        assert 'recordingBasis === "primary"' in fn

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
        body = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentUpdateCtFieldsVisibility")
        assert "Plotly" not in body


class TestOvercurrentViewport:
    """Adjustable-viewport UAT follow-up (2026-09-12): default display
    domain, absolute bounds, validation, dynamic 1-2-5/decade tick
    generation with the major/minor classification rule, zoom in/out/
    reset, and the default-vs-custom "0" origin rule."""

    def test_default_and_absolute_viewport_constants(self):
        source = _source()
        assert "const WW_OC_VIEWPORT_DEFAULT = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };" in source
        assert "const WW_OC_VIEWPORT_ABSOLUTE = { xMin: 0.1, xMax: 200, yMin: 0.01, yMax: 1000 };" in source

    def test_state_viewport_field_initialised_to_default(self):
        source = _source()
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchCharacteristics")
        assert "viewport: { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 }," in fn

    def test_reset_state_also_resets_viewport(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")
        assert 'wwOvercurrentState.viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };' in fn

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
            y: wwOvercurrentClassifyMajors(wwOvercurrentGenerateDecadeTicks(0.01, 100), 0.01),
        }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        payload = re.search(r"\{.*\}", result.stdout).group(0)
        import json

        data = json.loads(payload)
        assert data["x"] == [0.5, 1, 2, 5, 10, 20, 50, 100]
        assert data["y"] == [0.1, 1, 10, 100]

    def test_geometry_is_viewport_aware_and_gap_only_applies_to_default_view(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentChartGeometry(viewport)", "function wwOvercurrentPixelX")
        assert "wwOvercurrentIsDefaultViewport(viewport)" in fn
        assert "const gap = isDefault ? WW_OC_ORIGIN_GAP : 0;" in fn
        assert "logMMin: Math.log10(viewport.xMin)" in fn
        assert "logTMin: Math.log10(viewport.yMin)" in fn

    def test_default_view_shows_zero_origin_and_minor_reference_ticks(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        default_branch = _function_body(fn, "if (geo.isDefault) {", "} else {")
        assert "ww-oc-origin-label" in default_branch
        assert ">0</text>" in default_branch
        assert "ww-oc-tick-label-minor" in default_branch
        assert "Math.log10" not in default_branch[: default_branch.index("ww-oc-tick-label-minor")]

    def test_custom_view_shows_true_minimum_never_a_fake_zero(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        custom_branch = _function_body(fn, "} else {\n                const xMinPx", "// Axis titles")
        assert ">0</text>" not in custom_branch
        assert "ww-oc-origin-label" not in custom_branch
        assert 'class="ww-oc-tick-label"' in custom_branch

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
        source = _source()
        fn = _function_body(source, "function wwOvercurrentResetViewport()", "// ---- Settings wiring helpers")
        assert "wwOvercurrentState.viewport = { ...WW_OC_VIEWPORT_DEFAULT };" in fn

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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert fn.count('class="ww-oc-axis"') == 2

    def test_grid_lines_render_for_current_viewport_majors(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "Current / Pickup Multiple (M)" in fn
        assert "Expected Operating Time (s)" in fn

    def test_curve_is_clipped_not_clamped_or_distorted(self):
        """A real IDMT curve legitimately runs outside the fixed display
        window near M=1 for a slow TMS -- the curve path itself uses the
        SAME unclamped pixel mapping as the grid/ticks, then is clipped
        (never distorted) via an SVG clipPath, so the underlying
        engineering math is never altered to fit the frame."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "clipPath" in fn
        assert 'clip-path="url(#wwOvercurrentClip)"' in fn

    def test_curve_points_themselves_are_not_reclamped(self):
        """The curve path loop maps the visible-segment points' own
        `p[0]`/`p[1]` directly through the unclamped pixel functions --
        clamping is reserved for the single operating-point marker only,
        confirmed by the curve-path loop never calling
        wwOvercurrentClampedM/T."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        off_chart_branch = _function_body(fn, "} else {\n                    // Below pickup, off-chart", "}\n            }\n\n            svg.innerHTML")
        assert "wwOvercurrentEdgeArrowSvg" in off_chart_branch
        assert "ww-oc-position-marker" not in off_chart_branch
        assert "ww-oc-guide" not in off_chart_branch

    def test_position_marker_x_uses_clamped_m_never_distorts_the_true_value(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "const clampedM = wwOvercurrentClampedM(currentM, viewport);" in fn

    def test_below_pickup_never_calls_pixel_y_with_a_fabricated_time(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        below_branch = _function_body(fn, "} else if (mInRange) {", "}\n            }\n\n            svg.innerHTML")
        assert "wwOvercurrentPixelY" not in below_branch


class TestOperatingPointGuides:
    def test_above_pickup_still_renders_point_and_both_guides(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        above_branch = _function_body(fn, "if (Number.isFinite(currentT)) {", "} else {")
        assert "ww-oc-operating-point" in above_branch
        assert above_branch.count("ww-oc-guide") == 2

    def test_guides_align_with_the_clamped_tick_coordinate(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        above_branch = _function_body(fn, "if (Number.isFinite(currentT)) {", "} else {")
        assert "const clampedT = wwOvercurrentClampedT(currentT, viewport);" in above_branch

    def test_above_pickup_off_chart_uses_edge_indicator_for_the_out_of_range_axis(self):
        """UAT §11: if M or T lies outside the visible range, never
        redraw the operating point at the boundary as though the
        boundary were the true value -- an edge-indicator triangle
        replaces the circle for whichever axis is out of range, the
        other axis' guide is unaffected."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        curve_block = _function_body(fn, "if (points && points.length > 0) {", "// Operating point")
        assert "wwOvercurrentRelayCurrentToMultiple(viewport.xMin, pickup)" in curve_block
        assert "wwOvercurrentRelayCurrentToMultiple(viewport.xMax, pickup)" in curve_block
        assert "wwOvercurrentMultipleToRelayCurrent(p[0], pickup)" in curve_block

    def test_pickup_multiple_mode_passes_the_viewport_through_unchanged(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        curve_block = _function_body(fn, "if (points && points.length > 0) {", "// Operating point")
        assert "isRelayCurrentAxis && Number.isFinite(pickup) && pickup > 0" in curve_block
        assert ": viewport;" in curve_block


class TestAxisTitleSwitchesWithMode:
    def test_relay_current_axis_title_text_present(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "Relay Current (A secondary)" in fn
        assert 'isRelayCurrentAxis ? "Relay Current (A secondary)" : "Current / Pickup Multiple (M)"' in fn


class TestPickupBoundaryReference:
    def test_pickup_boundary_line_renders_at_m_equals_one_or_pickup_amps(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "const pickupBoundaryX = isRelayCurrentAxis ? pickup : 1.0;" in fn
        assert "ww-oc-pickup-boundary" in fn

    def test_pickup_boundary_skipped_when_outside_viewport(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        major_x_block = _function_body(fn, "for (const v of xMajors) {\n                const x = wwOvercurrentPixelX(v, geo);\n                parts.push('<line class=\"ww-oc-gridline\"", "Minor grid lines")
        assert "wwOvercurrentState.minorGridX" not in major_x_block
        assert "wwOvercurrentState.minorGridY" not in major_x_block

    def test_minor_gridlines_gated_independently_per_axis(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
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
            "wwOvercurrentSyncAxisModeButtons();\n        wwOvercurrentSyncGridToggleCheckboxes();\n        // The ONE, permanent subscription",
        )
        assert "wwOvercurrentState.minorGridY = event.target.checked;" in fn
        assert "wwOvercurrentRerenderChartFromState();" in fn


class TestCompressedSubPickupAxis:
    """Chart geometry refinement: in Pickup Multiple mode, whenever the
    viewport straddles M=1 (xMin < 1 < xMax), the below-pickup region
    (xMin -> 1) is visually compressed to ~5% of the plot width and the
    operating region (1 -> xMax) gets ~95% -- a single, centralized
    piecewise transform (`wwOvercurrentPixelX()`/
    `wwOvercurrentPlotXToPickupMultiple()`) every chart element shares.
    Relay Current mode and the Y axis are completely unaffected."""

    def _harness(self, x_axis_mode="pickup_multiple"):
        source = _source()
        geometry_fn = _function_body(
            source, "function wwOvercurrentChartGeometry(viewport)", "// The ONE authoritative Pickup Multiple X mapping pair"
        )
        pixel_x_fn = _function_body(source, "function wwOvercurrentPixelX(m, geo)", "// Inverse of `wwOvercurrentPixelX()`")
        inverse_fn = _function_body(source, "function wwOvercurrentPlotXToPickupMultiple(x, geo)", "function wwOvercurrentPixelY")
        is_default_fn = _function_body(source, "function wwOvercurrentIsDefaultViewport(v)", "// Hard validation")
        preamble = f"""
        const WW_OC_XAXIS_PICKUP_MULTIPLE = "pickup_multiple";
        const WW_OC_XAXIS_RELAY_CURRENT = "relay_current";
        const wwOvercurrentState = {{ xAxisMode: "{x_axis_mode}" }};
        const WW_OC_CHART_MARGIN = {{ left: 40, right: 14, top: 12, bottom: 34 }};
        const WW_OC_CHART_W = 320;
        const WW_OC_CHART_H = 240;
        const WW_OC_ORIGIN_GAP = 15;
        const WW_OC_VIEWPORT_DEFAULT = {{ xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 }};
        const WW_OC_SUBPICKUP_GUTTER_FRACTION = 0.05;
        """
        return preamble + is_default_fn + geometry_fn + pixel_x_fn + inverse_fn

    def test_below_pickup_region_occupies_approximately_5_percent_of_plot_width(self):
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        const pxAtMin = wwOvercurrentPixelX(viewport.xMin, geo);
        const pxAtOne = wwOvercurrentPixelX(1, geo);
        const plotWidth = geo.plotRight - geo.logLeft;
        console.log(JSON.stringify({
            belowFraction: (pxAtOne - pxAtMin) / plotWidth,
            breakApplies: geo.breakApplies,
        }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["breakApplies"] is True
        assert data["belowFraction"] == pytest.approx(0.05, abs=0.01)

    def test_operating_region_occupies_approximately_95_percent_of_plot_width(self):
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        const pxAtOne = wwOvercurrentPixelX(1, geo);
        const pxAtMax = wwOvercurrentPixelX(viewport.xMax, geo);
        const plotWidth = geo.plotRight - geo.logLeft;
        console.log(JSON.stringify({ aboveFraction: (pxAtMax - pxAtOne) / plotWidth }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["aboveFraction"] == pytest.approx(0.95, abs=0.01)

    def test_m_equals_1_maps_exactly_to_the_break_boundary(self):
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        console.log(JSON.stringify({ pxAtOne: wwOvercurrentPixelX(1, geo), breakPx: geo.breakPx }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["pxAtOne"] == pytest.approx(data["breakPx"], abs=1e-9)

    def test_mapping_is_monotonic_on_both_sides_of_the_break(self):
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        const belowSamples = [0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0].map((m) => wwOvercurrentPixelX(m, geo));
        const aboveSamples = [1.0, 2, 5, 10, 20, 50, 100].map((m) => wwOvercurrentPixelX(m, geo));
        console.log(JSON.stringify({ belowSamples, aboveSamples }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        for samples in (data["belowSamples"], data["aboveSamples"]):
            for a, b in zip(samples, samples[1:]):
                assert b > a

    def test_inverse_mapping_round_trips_representative_points(self):
        import json
        import subprocess

        points = [0.1, 0.2, 0.5, 1, 1.2, 2, 5, 10, 50, 100]
        script = self._harness() + f"""
        const viewport = {{ xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 }};
        const geo = wwOvercurrentChartGeometry(viewport);
        const points = {json.dumps(points)};
        const results = points.map((m) => {{
            const px = wwOvercurrentPixelX(m, geo);
            const recovered = wwOvercurrentPlotXToPickupMultiple(px, geo);
            return {{ m, recovered }};
        }});
        console.log(JSON.stringify(results));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        rows = json.loads(result.stdout)
        assert len(rows) == len(points)
        for row in rows:
            assert row["recovered"] == pytest.approx(row["m"], rel=1e-9)

    def test_no_break_when_viewport_excludes_values_below_1(self):
        """Task §12: a viewport entirely at/above M=1 must revert to the
        ordinary single log mapping -- never a forced, useless gutter."""
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 2, xMax: 20, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        console.log(JSON.stringify({ breakApplies: geo.breakApplies }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["breakApplies"] is False

    def test_break_applies_whenever_viewport_straddles_1(self):
        import json
        import subprocess

        script = self._harness() + """
        const viewport = { xMin: 0.5, xMax: 5, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        console.log(JSON.stringify({ breakApplies: geo.breakApplies }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["breakApplies"] is True

    def test_relay_current_mode_never_applies_the_break(self):
        import json
        import subprocess

        script = self._harness(x_axis_mode="relay_current") + """
        const viewport = { xMin: 0.1, xMax: 100, yMin: 0.01, yMax: 100 };
        const geo = wwOvercurrentChartGeometry(viewport);
        console.log(JSON.stringify({ breakApplies: geo.breakApplies }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        assert data["breakApplies"] is False

    def test_render_chart_draws_the_break_marker_only_when_it_applies(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "if (geo.breakApplies) {" in fn
        assert "wwOvercurrentAxisBreakSvg(geo)" in fn

    def test_axis_break_marker_uses_the_shared_pixel_mapping_never_a_separate_calculation(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentAxisBreakSvg(geo)", "function wwOvercurrentRenderChart")
        assert "wwOvercurrentPixelX(1, geo)" in fn
        assert "Math.log10" not in fn

    def test_gutter_fraction_constant_is_5_percent(self):
        source = _source()
        assert "const WW_OC_SUBPICKUP_GUTTER_FRACTION = 0.05;" in source


class TestPickupMultipleFixedMajorTicks:
    """Owner UAT correction (2026-09-13): the generic dynamic 1-2-5
    major-tick classifier never generates 3/4/6/7/8/9 at all, so they
    were wrongly absent from Pickup Multiple mode's always-visible major
    grid (only reachable, if at all, as minor-gated ticks). Pickup
    Multiple mode now uses its own FIXED, explicit major list --
    0 (visual-only, unchanged), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50,
    100 -- never derived from the generic progression+classification
    rule Relay Current mode and the Y axis still use."""

    def test_fixed_major_tick_constant_matches_the_owner_approved_list(self):
        source = _source()
        assert "const WW_OC_PICKUP_MULTIPLE_MAJOR_TICKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100];" in source

    def test_default_viewport_renders_every_owner_approved_major_via_node(self):
        import json
        import subprocess

        source = _source()
        const_decl = "const WW_OC_PICKUP_MULTIPLE_MAJOR_TICKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100];\n"
        fn = _function_body(source, "function wwOvercurrentPickupMultipleMajors(viewport)", "function wwOvercurrentFormatTickValue")
        script = const_decl + fn + "\nconsole.log(JSON.stringify(wwOvercurrentPickupMultipleMajors({ xMin: 0.1, xMax: 100 })));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        majors = json.loads(result.stdout)
        # 0 is never part of this array -- it stays the existing visual-
        # only origin annotation, asserted separately below.
        assert majors == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100]

    def test_3_4_6_7_8_9_are_present_as_majors_never_excluded(self):
        import json
        import subprocess

        source = _source()
        const_decl = "const WW_OC_PICKUP_MULTIPLE_MAJOR_TICKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100];\n"
        fn = _function_body(source, "function wwOvercurrentPickupMultipleMajors(viewport)", "function wwOvercurrentFormatTickValue")
        script = const_decl + fn + "\nconsole.log(JSON.stringify(wwOvercurrentPickupMultipleMajors({ xMin: 0.1, xMax: 100 })));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        majors = json.loads(result.stdout)
        for expected in (3, 4, 6, 7, 8, 9):
            assert expected in majors

    def test_zero_is_never_a_real_logarithmic_coordinate(self):
        """0 stays the existing visual-only origin label -- never part of
        the fixed major-tick array, never passed through Math.log10()."""
        source = _source()
        assert "0" not in [str(v) for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100]]
        fn = _function_body(source, "function wwOvercurrentPickupMultipleMajors(viewport)", "function wwOvercurrentFormatTickValue")
        assert "Math.log10" not in fn

    def test_render_chart_uses_the_fixed_majors_in_pickup_multiple_mode_and_the_generic_ones_in_relay_current_mode(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        assert "const xMajors = isRelayCurrentAxis ? wwOvercurrentXMajors(viewport) : wwOvercurrentPickupMultipleMajors(viewport);" in fn

    def test_default_viewport_gridline_count_reflects_the_new_fixed_major_list(self):
        """13 Pickup Multiple X majors (1..9, 10, 20, 50, 100) + 4 Y
        majors (0.1, 1, 10, 100) = 17 major gridlines for the default
        viewport -- confirmed end-to-end in browser-tests/
        overcurrent_analysis.spec.js's own "default viewport" test."""
        import json
        import subprocess

        source = _source()
        x_const = "const WW_OC_PICKUP_MULTIPLE_MAJOR_TICKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100];\n"
        x_fn = _function_body(source, "function wwOvercurrentPickupMultipleMajors(viewport)", "function wwOvercurrentFormatTickValue")
        y_fn = _function_body(source, "function wwOvercurrentGenerateDecadeTicks(min, max)", "// Major/minor classification")
        classify_fn = _function_body(source, "function wwOvercurrentClassifyMajors(allTicks, axisMin)", "function wwOvercurrentXMajors")
        y_majors_fn = _function_body(source, "function wwOvercurrentYMajors(viewport)", "// Pickup Multiple mode's own FIXED")
        script = x_const + x_fn + y_fn + classify_fn + y_majors_fn + """
        const xMajors = wwOvercurrentPickupMultipleMajors({ xMin: 0.1, xMax: 100 });
        const yMajors = wwOvercurrentYMajors({ yMin: 0.01, yMax: 100 });
        console.log(JSON.stringify({ xCount: xMajors.length, yCount: yMajors.length }));
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        counts = json.loads(result.stdout)
        assert counts["xCount"] == 13
        assert counts["yCount"] == 4


class TestPickupMultipleMinorsNeverDuplicateFixedMajors:
    """The owner's own correction: 3/4/6/7/8/9 must be MAJOR, not minor.
    Pickup Multiple mode's own dedicated minor generator must therefore
    never emit any of the fixed major values themselves -- only genuine
    subdivisions BETWEEN them (e.g. 1.2/1.4/1.6/1.8 between 1 and 2, the
    owner's own explicit example)."""

    def _minors(self, min_val, max_val):
        import json
        import subprocess

        source = _source()
        subdivisions_const = "const WW_OC_MINOR_POW125_SUBDIVISIONS = [[1, 2, 0.2], [2, 5, 0.5], [5, 10, 1]];\n"
        sub_pickup_fn = _function_body(
            source,
            "function wwOvercurrentPickupMultipleSubPickupMinors(viewport)",
            "function wwOvercurrentPickupMultipleMinors(viewport)",
        )
        fn = _function_body(
            source,
            "function wwOvercurrentPickupMultipleMinors(viewport)",
            "// X minors are mode-aware",
        )
        script = subdivisions_const + sub_pickup_fn + fn + f"\nconsole.log(JSON.stringify(wwOvercurrentPickupMultipleMinors({{ xMin: {min_val}, xMax: {max_val} }})));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_1_to_2_matches_owner_example(self):
        assert self._minors(1, 2) == pytest.approx([1.2, 1.4, 1.6, 1.8])

    def test_3_4_6_7_8_9_never_appear_as_minors(self):
        minors = self._minors(0.1, 100)
        for forbidden in (3, 4, 6, 7, 8, 9):
            assert forbidden not in minors

    def test_full_default_range_never_collides_with_any_fixed_major(self):
        minors = self._minors(0.1, 100)
        fixed_majors = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100}
        assert not (set(minors) & fixed_majors)

    def test_generalizes_the_0_2_step_to_every_unit_interval_below_10(self):
        minors = self._minors(0.1, 10)
        for n in range(1, 10):
            for step in (0.2, 0.4, 0.6, 0.8):
                assert pytest.approx(n + step) in minors

    def test_above_10_reuses_the_existing_decade_subdivision(self):
        minors = self._minors(10, 100)
        for expected in (12, 14, 16, 18, 25, 30, 35, 40, 45, 60, 70, 80, 90):
            assert expected in minors


class TestXMinorsDispatchesByAxisMode:
    def test_relay_current_mode_keeps_the_generic_minor_generator(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentXMinors(viewport)", "function wwOvercurrentYMinors")
        assert "WW_OC_XAXIS_RELAY_CURRENT" in fn
        assert "wwOvercurrentGenerateMinorPow125Ticks(viewport.xMin, viewport.xMax)" in fn
        assert "wwOvercurrentPickupMultipleMinors(viewport)" in fn


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
