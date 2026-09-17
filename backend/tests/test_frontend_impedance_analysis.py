"""Static structural regression checks for Impedance Locus v1
(frontend/index.html) -- the THIRD `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is not covered by a Playwright spec in this slice (see
docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md's own "Known
limitations" section) -- these checks catch structural regressions
(missing wiring, markup/JS drift, accidental protection-zone scope
creep) that a real browser is not required to detect.
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


class TestImpedanceNavAndPanel:
    def test_impedance_nav_button_exists_and_is_activated(self):
        source = _source()
        assert 'id="wwAnalysisTypeImpedanceBtn"' in source
        assert 'data-analysis-type="impedance"' in source
        # No longer a placeholder -- the real panel replaced it.
        panel = _function_body(source, 'id="wwImpedancePanel"', '<section class="ww-phasor-panel" id="wwSequencePanel"')
        assert "This analyzer is not implemented yet." not in panel

    def test_sequence_components_nav_still_a_placeholder(self):
        source = _source()
        panel = _function_body(source, 'id="wwSequencePanel"', "</section>\n                    </div>\n                </div>\n            </section>")
        assert "This analyzer is not implemented yet." in panel

    def test_analyzer_order_preserved(self):
        source = _source()
        nav = _function_body(source, 'class="ww-analysis-type-nav"', "</nav>")
        assert nav.index("Phasor") < nav.index("Overcurrent") < nav.index("Impedance Locus") < nav.index("Sequence Components")


class TestImpedanceMarkupSeparation:
    """Mirrors Overcurrent's own architectural-correction shape (see
    docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- three independent
    regions: an always-visible Input Source toggle, a Recording-only
    section, and an always-visible Body."""

    def test_input_source_toggle_is_a_direct_sibling_not_nested(self):
        source = _source()
        panel = _function_body(source, 'id="wwImpedancePanel"', 'id="wwImpedanceRecordingSection"')
        assert "ww-oc-input-source-panel" in panel
        assert 'id="wwImpedanceInputSourceRecordingBtn"' in panel
        assert 'id="wwImpedanceInputSourceManualBtn"' in panel

    def test_recording_section_holds_bay_and_playback(self):
        source = _source()
        section = _function_body(source, 'id="wwImpedanceRecordingSection"', 'id="wwImpedanceBody"')
        assert 'id="wwImpedanceContextSelect"' in section
        assert 'id="wwImpedancePlaybackPanel"' in section
        assert 'id="wwImpedanceRelatedWaveformsAnchor"' in section
        assert 'id="wwImpedanceEmptyState"' in section

    def test_body_holds_settings_manual_input_and_plot_never_recording_gated(self):
        source = _source()
        body = _function_body(source, 'id="wwImpedanceBody"', 'id="wwSequencePanel"')
        assert 'id="wwImpedancePhaseSelect"' in body
        assert 'id="wwImpedanceOutputBasisSelect"' in body
        assert 'id="wwImpedanceManualInputSection"' in body
        assert 'id="wwImpedanceSvg"' in body
        assert 'id="wwImpedanceValuesList"' in body


class TestImpedanceInputSourceReusesSharedConstants:
    def test_reuses_shared_ww_analysis_input_source_constants(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceSetInputSource", "function wwImpedanceSyncInputSourceButtons")
        assert "WW_ANALYSIS_INPUT_SOURCE_RECORDING" in fn
        assert "WW_ANALYSIS_INPUT_SOURCE_MANUAL" in fn
        # Never re-declares the shared constants under an Impedance-local name.
        assert "const WW_IMPEDANCE_INPUT_SOURCE" not in source

    def test_reuses_shared_axis_toggle_css_classes(self):
        source = _source()
        panel = _function_body(source, 'id="wwImpedancePanel"', 'id="wwImpedanceRecordingSection"')
        assert "ww-oc-axis-toggle-group" in panel
        assert "ww-oc-axis-toggle-btn" in panel


class TestImpedanceManualIndependentBases:
    def test_voltage_and_current_bases_are_two_separate_selects(self):
        source = _source()
        assert 'id="wwImpedanceManualVoltageBasisSelect"' in source
        assert 'id="wwImpedanceManualCurrentBasisSelect"' in source

    def test_manual_basis_changes_are_independent_state_writes(self):
        source = _source()
        voltage_handler = _function_body(
            source, 'document.getElementById("wwImpedanceManualVoltageBasisSelect")', 'document.getElementById("wwImpedanceManualCurrentBasisSelect")'
        )
        assert "wwImpedanceState.manual.voltageBasis" in voltage_handler
        assert "currentBasis" not in voltage_handler

    def test_impedance_output_basis_is_a_third_independent_selector(self):
        """Task's own section 11 -- Impedance basis is an OUTPUT basis,
        independent of both Voltage and Current input bases."""
        source = _source()
        assert 'id="wwImpedanceOutputBasisSelect"' in source
        fn = _function_body(source, 'function wwImpedanceRequestManualAnalysis', "function wwImpedanceRenderManualResult")
        assert "impedance_basis: wwImpedanceState.settings.outputBasis" in fn


class TestImpedanceLocusIsStaticNotPerTick:
    """Task's own section 19 -- the locus must be fetched only on
    context/phase/settings/time-range change, never per Playback tick."""

    def test_tick_handler_never_calls_locus_fetch(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceOnPlaybackTick", "const WW_IMPEDANCE_PLAYBACK_THROTTLE_MS")
        assert "wwImpedanceMaybeFetchLocus" not in fn
        assert "wwImpedanceFetchLocus" not in fn

    def test_locus_signature_short_circuits_redundant_fetches(self):
        source = _source()
        fn = _function_body(source, "async function wwImpedanceMaybeFetchLocus", "// ---- Rendering")
        assert "signature === wwImpedanceState.locusSignature" in fn

    def test_settings_change_invalidates_and_refetches_locus(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceHandleSettingsChanged", "function wwImpedanceHandlePhaseChanged")
        assert "wwImpedanceInvalidateLocus" in fn
        assert "wwImpedanceMaybeFetchLocus" in fn


class TestImpedanceEqualScalePlot:
    """Task's own section 14 -- one ohm horizontally must equal one ohm
    vertically; never independent X/Y graphical scales."""

    def test_single_shared_px_per_ohm_factor(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceRenderPlot", "// ---- Input Source (Recording/Manual)")
        assert "pxPerOhm" in fn
        # Both coordinates of toSvg() are derived from the SAME pxPerOhm.
        assert fn.count("pxPerOhm") >= 2

    def test_no_separate_x_and_y_scale_variables(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceRenderPlot", "// ---- Input Source (Recording/Manual)")
        assert "xScale" not in fn
        assert "yScale" not in fn


class TestImpedanceNotDistanceProtection:
    """Task's own explicit out-of-scope list (section 4/34) -- this v1
    must never introduce any protection-zone FUNCTIONALITY. Explanatory
    prose naming these concepts (e.g. "no zones/mho logic here") is
    expected and fine -- the codebase's own established convention
    (Overcurrent's module footer does the same) -- so this only checks
    for an actual identifier (a CSS class, element id, or function/
    variable name) built from one of these terms, never prose text."""

    FORBIDDEN_IDENTIFIER_FRAGMENTS = ("mho", "quadrilateral", "faultloop", "residual", "trip", "directional", "powerswing", "loadencroachment", "zone")

    def test_no_protection_zone_identifiers_in_impedance_module(self):
        import re

        source = _source()
        start = source.index("Impedance Locus v1 -- the THIRD Analysis-menu analyzer")
        end = source.index("const wwPhasorState = {")
        module = source[start:end]
        identifiers = set(re.findall(r'\b(?:function\s+(\w+)|const\s+(\w+)|id="(\w+)"|class="([\w\- ]+)")', module))
        flat = " ".join(" ".join(t) for t in identifiers).lower()
        for term in self.FORBIDDEN_IDENTIFIER_FRAGMENTS:
            assert term not in flat, f"forbidden protection-zone identifier fragment found: {term!r}"


class TestImpedanceWiredIntoSharedInfrastructure:
    def test_registered_as_context_consumer(self):
        source = _source()
        assert "onContexts: wwImpedanceOnAnalysisContexts" in source
        assert "onLifecyclePhase: wwImpedanceOnAnalysisLifecyclePhase" in source
        assert "onDiscovering: wwImpedanceOnAnalysisDiscovering" in source
        assert "onFreshContextsDiscovered: wwImpedanceOnAnalysisFreshContextsDiscovered" in source

    def test_subscribed_to_shared_playback_tick(self):
        source = _source()
        assert "wwPlaybackOnTick(wwImpedanceOnPlaybackTick);" in source

    def test_reset_on_workspace_clear(self):
        source = _source()
        assert "wwImpedanceResetState();" in source

    def test_mounts_shared_playback_control_surface(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceMountPlaybackControls", "// ---- The ONE tick subscriber")
        assert "wwCreatePlaybackControlsHtml()" in fn
        assert "wwWirePlaybackControls(mountEl, groupId)" in fn
        assert "wwSyncPlaybackControls(mountEl, groupId)" in fn

    def test_related_waveforms_declares_va_ia_pair_for_selected_phase(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceComputeActiveRelatedWaveformRoles", "function wwImpedancePushRelatedWaveformRoles")
        assert '"V" + phase.toLowerCase()' in fn
        assert '"I" + phase.toLowerCase()' in fn

    def test_manual_mode_declares_zero_related_waveform_roles(self):
        source = _source()
        fn = _function_body(source, "function wwImpedanceComputeActiveRelatedWaveformRoles", "function wwImpedancePushRelatedWaveformRoles")
        assert "if (wwImpedanceState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING) return [];" in fn
