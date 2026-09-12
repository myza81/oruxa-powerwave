"""Static structural regression checks for Overcurrent Analysis v1
(frontend/index.html) -- the second `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is covered separately by `browser-tests/overcurrent_analysis.spec.js`.
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
        fn = _function_body(source, "const wwOvercurrentState = {", "function wwOvercurrentFetchContexts")
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
        """The curve path loop maps `p[0]`/`p[1]` (the raw backend-
        returned points) directly through the unclamped pixel functions
        -- clamping is reserved for the single operating-point marker
        only, confirmed by the curve-path loop never calling
        wwOvercurrentClampedM/T."""
        source = _source()
        fn = _function_body(source, "function wwOvercurrentRenderChart(points, currentM, currentT)", "function wwOvercurrentRerenderChartFromState")
        curve_loop = _function_body(fn, "const curvePath = points.map", "parts.push('<path")
        assert "wwOvercurrentClampedM" not in curve_loop
        assert "wwOvercurrentClampedT" not in curve_loop
        assert "wwOvercurrentPixelX(p[0], geo)" in curve_loop
        assert "wwOvercurrentPixelY(p[1], geo)" in curve_loop


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
