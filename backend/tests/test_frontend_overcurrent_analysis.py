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
        fn = _function_body(source, "function wwOvercurrentEnsureCurveAndRenderPoint(result)", "function wwOvercurrentChartXY")
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
