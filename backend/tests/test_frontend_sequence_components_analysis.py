"""Static structural regression checks for Sequence Components v1
(frontend/index.html) -- the FOURTH `Analysis` menu consumer. Same
source-text substring-assertion pattern every other `test_frontend_*.py`
file in this suite already uses. Real fetch/render/interaction behavior
is covered by `browser-tests/sequence_components_analysis.spec.js`
(Playwright) -- these checks catch structural regressions (missing
wiring, markup/JS drift, accidental protection-interpretation scope
creep) that a real browser is not required to detect.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
THEME = Path(__file__).resolve().parents[2] / "frontend" / "theme.css"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _theme_source() -> str:
    return THEME.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestSequenceNavAndPanel:
    def test_sequence_nav_button_exists_and_is_activated(self):
        source = _source()
        assert 'id="wwAnalysisTypeSequenceBtn"' in source
        assert 'data-analysis-type="sequence"' in source
        panel = _function_body(source, 'id="wwSequencePanel"', "</section>\n                    </div>\n                </div>\n            </section>")
        assert "This analyzer is not implemented yet." not in panel

    def test_analyzer_order_preserved(self):
        source = _source()
        nav = _function_body(source, 'class="ww-analysis-type-nav"', "</nav>")
        assert (
            nav.index("Overcurrent") < nav.index("Impedance Locus") < nav.index("Distance Protection")
            < nav.index("Phasor") < nav.index("Sequence Components")
        )

    def test_panel_routing_table_includes_sequence(self):
        source = _source()
        fn = _function_body(source, "const wwAnalysisPanelsByType", "function wwSetActiveAnalysisType")
        assert 'sequence: "wwSequencePanel"' in fn


class TestSequenceMarkupSeparation:
    """Mirrors Impedance Locus's/Overcurrent's own architectural-
    correction shape (see docs/project-memory/ANALYSIS_INPUT_SOURCE.md)
    -- three independent regions: an always-visible Input Source toggle,
    a Recording-only section, and an always-visible Body."""

    def test_input_source_toggle_is_a_direct_sibling_not_nested(self):
        source = _source()
        panel = _function_body(source, 'id="wwSequencePanel"', 'id="wwSequenceRecordingSection"')
        assert "ww-oc-input-source-panel" in panel
        assert 'id="wwSequenceInputSourceRecordingBtn"' in panel
        assert 'id="wwSequenceInputSourceManualBtn"' in panel

    def test_recording_section_holds_bay_and_playback(self):
        source = _source()
        section = _function_body(source, 'id="wwSequenceRecordingSection"', 'id="wwSequenceManualInputSection"')
        assert 'id="wwSequenceContextSelect"' in section
        assert 'id="wwSequencePlaybackPanel"' in section
        assert 'id="wwSequenceRelatedWaveformsAnchor"' in section
        assert 'id="wwSequenceEmptyState"' in section

    def test_body_holds_values_ratios_and_diagram_never_recording_gated(self):
        source = _source()
        body = _function_body(source, 'id="wwSequenceBody"', "<!-- CSV/Excel ingestion Slice 3")
        assert 'id="wwSequenceValuesList"' in body
        assert 'id="wwSequenceRatiosList"' in body
        assert 'id="wwSequenceSvg"' in body


class TestSequenceInputSourceReusesSharedConstants:
    def test_reuses_shared_ww_analysis_input_source_constants(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceSetInputSource", "function wwSequenceSyncInputSourceButtons")
        assert "WW_ANALYSIS_INPUT_SOURCE_RECORDING" in fn
        assert "WW_ANALYSIS_INPUT_SOURCE_MANUAL" in fn
        assert "const WW_SEQUENCE_INPUT_SOURCE" not in source

    def test_reuses_shared_axis_toggle_css_classes(self):
        source = _source()
        panel = _function_body(source, 'id="wwSequencePanel"', 'id="wwSequenceRecordingSection"')
        assert "ww-oc-axis-toggle-group" in panel
        assert "ww-oc-axis-toggle-btn" in panel


class TestSequenceManualReusesPhasorSixRoleShape:
    """Task's own section 7 -- Manual entry stays phase-domain (Va/Vb/Vc/
    Ia/Ib/Ic), reusing the identical Manual Phasor architecture, never a
    direct V0/V1/V2 entry field."""

    def test_six_manual_role_rows_exist(self):
        source = _source()
        for role in ("Va", "Vb", "Vc", "Ia", "Ib", "Ic"):
            assert 'id="wwSequenceManual' + role + 'Enabled"' in source
            assert 'id="wwSequenceManual' + role + 'Magnitude"' in source
            assert 'id="wwSequenceManual' + role + 'Unit"' in source
            assert 'id="wwSequenceManual' + role + 'Angle"' in source

    def test_voltage_and_current_bases_are_two_separate_selects(self):
        source = _source()
        assert 'id="wwSequenceManualVoltageBasisSelect"' in source
        assert 'id="wwSequenceManualCurrentBasisSelect"' in source

    def test_manual_basis_changes_are_independent_state_writes(self):
        source = _source()
        voltage_handler = _function_body(
            source,
            'document.getElementById("wwSequenceManualVoltageBasisSelect").addEventListener("change"',
            'document.getElementById("wwSequenceManualCurrentBasisSelect").addEventListener("change"',
        )
        assert "wwSequenceState.manual.voltageBasis" in voltage_handler
        assert "currentBasis" not in voltage_handler

    def test_manual_request_reuses_shared_manual_phasor_role_order(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceRequestManualAnalysis", "function wwSequenceFetchAnalysis")
        assert "WW_PHASOR_DIAGRAM_ROLE_ORDER" in fn
        # Never a second, sequence-only manual role list.
        assert "WW_SEQUENCE_MANUAL_ROLE_ORDER" not in source

    def test_manual_endpoint_is_workspace_scoped_sequence_components_manual(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceFetchManualAnalysis", "function wwSequenceRequestManualAnalysis")
        assert "/sequence-components-manual" in fn


class TestSequenceCompleteSetRequirement:
    """Task's own section 8 -- unlike Manual Phasor visualization,
    Sequence Components mathematically require a complete three-phase
    set per family; the transform is derived FROM `voltage_sequences`/
    `current_sequences`, never from individual Va/Vb/Vc availability on
    the frontend (that guardrail is backend-authoritative)."""

    def test_role_value_reads_from_family_not_individual_phase(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceRoleValue", "function wwSequenceSetInputSource")
        assert "voltage_sequences" in source
        assert "current_sequences" in source
        assert "family.status" in fn


class TestSequenceRatiosAreDescriptiveOnly:
    """Task's own section 9/18 -- ratios are shown, never compared
    against a threshold; a null/undefined/non-finite ratio renders as an
    explicit unavailable text, never Infinity/NaN."""

    def test_ratio_rows_cover_all_four_ratios(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceRenderRatiosList", "// The one render path")
        # DEC-117 Amendment 2: numerator/denominator role keys, rendered
        # V<sub>2</sub> / V<sub>1</sub> by the shared formatter.
        assert 'wwSequenceRatioRowHtml("V2", "V1",' in fn
        assert 'wwSequenceRatioRowHtml("V0", "V1",' in fn
        assert 'wwSequenceRatioRowHtml("I2", "I1",' in fn
        assert 'wwSequenceRatioRowHtml("I0", "I1",' in fn

    def test_unavailable_ratio_never_renders_infinity_or_nan(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceFormatRatio", "function wwSequenceRatioRowHtml")
        assert '"Unavailable"' in fn
        assert "Number.isFinite" in fn

    def test_no_protection_threshold_comparison(self):
        """Task's own explicit out-of-scope list -- no unbalance-limit/
        threshold-comparison keyword exists anywhere in this analyzer's
        own code."""
        source = _source()
        seq_module = _function_body(source, "Sequence Components v1 -- the FOURTH Analysis-menu analyzer", "// ------------------------------------------------------------------\n        // Init")
        for forbidden in ("threshold_exceeded", "unbalance_limit", "trip_", "relay_operat"):
            assert forbidden not in seq_module


class TestSequenceColorIdentityNeverReusesPhaseColors:
    """Task's own section 13 -- positive/negative/zero identity must not
    reuse the phase A/B/C color convention."""

    def test_dedicated_sequence_color_tokens_exist_in_theme(self):
        theme = _theme_source()
        assert "--ww-seq-positive" in theme
        assert "--ww-seq-negative" in theme
        assert "--ww-seq-zero" in theme

    def test_role_color_function_uses_sequence_tokens_not_phase_tokens(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceRoleColor", "function wwSequenceFamilyForRole")
        assert "--ww-seq-positive" in fn
        assert "--ww-seq-negative" in fn
        assert "--ww-seq-zero" in fn
        assert "--ww-phase-a" not in fn
        assert "--ww-phase-b" not in fn
        assert "--ww-phase-c" not in fn


class TestSequenceScaleNeverLeaksBetweenRecordingAndManual:
    """Mirrors Phasor's own bug-fixed invariant (task's own section 11)
    -- implemented correctly from day one here: Manual always recomputes
    fresh; the frozen-scale fields are only ever read/written on the
    Recording branch."""

    def test_manual_branch_never_touches_frozen_scale_fields(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceRenderDiagramSvg", "function wwSequenceResetState")
        manual_branch = _function_body(fn, "if (isManual) {", "} else {")
        assert "frozenVoltageScale" not in manual_branch
        assert "frozenCurrentScale" not in manual_branch


class TestSequenceSharedContextLifecycleConsumer:
    """Owner instruction (Overcurrent's own 2026-09-12 UAT fix, repeated
    for every analyzer since): no analyzer may invent its own context-
    discovery bootstrap."""

    def test_no_own_context_fetch_or_discovery_function(self):
        source = _source()
        assert "function wwSequenceLoadContexts" not in source
        assert "function wwSequenceDiscoverUncoveredSources" not in source
        assert "function wwSequenceFetchContexts" not in source

    def test_registers_as_consumer_with_all_four_callbacks(self):
        source = _source()
        call = source[source.index("onContexts: wwSequenceOnAnalysisContexts"):]
        call = call[: call.index("});")]
        assert "onLifecyclePhase: wwSequenceOnAnalysisLifecyclePhase" in call
        assert "onDiscovering: wwSequenceOnAnalysisDiscovering" in call
        assert "onFreshContextsDiscovered: wwSequenceOnAnalysisFreshContextsDiscovered" in call


class TestSequencePlaybackIntegration:
    def test_registers_with_the_one_shared_playback_controller(self):
        source = _source()
        assert "wwPlaybackOnTick(wwSequenceOnPlaybackTick)" in source

    def test_no_second_timer_or_raf_loop(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceOnPlaybackTick", "const WW_SEQUENCE_PLAYBACK_THROTTLE_MS")
        assert "requestAnimationFrame" not in fn
        assert "setInterval" not in fn

    def test_manual_mode_gates_off_the_recording_fetch_pipeline(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceOnPlaybackTick", "const WW_SEQUENCE_PLAYBACK_THROTTLE_MS")
        assert "wwSequenceState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING" in fn


class TestSequenceRelatedWaveformsShowsSourcePhaseQuantities:
    """Task's own section 15 -- Related Waveforms must show the source
    Va/Vb/Vc/Ia/Ib/Ic quantities the sequence transform was derived
    from, never the V0/V1/V2/I0/I1/I2 sequence values themselves (which
    have no waveform of their own)."""

    def test_pushed_roles_are_phase_domain_not_sequence_domain(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceComputeActiveRelatedWaveformRoles", "function wwSequencePushRelatedWaveformRoles")
        for phase_role in ('"Va"', '"Vb"', '"Vc"', '"Ia"', '"Ib"', '"Ic"'):
            assert phase_role in fn
        for sequence_role in ('"V1"', '"V2"', '"V0"', '"I1"', '"I2"', '"I0"'):
            assert sequence_role not in fn

    def test_manual_mode_declares_zero_active_roles(self):
        source = _source()
        fn = _function_body(source, "function wwSequenceComputeActiveRelatedWaveformRoles", "function wwSequencePushRelatedWaveformRoles")
        assert "if (wwSequenceState.inputSource !== WW_ANALYSIS_INPUT_SOURCE_RECORDING) return [];" in fn


class TestSequenceNotProtectionInterpretation:
    """Task's own explicit out-of-scope list (section 30) -- this v1
    must never introduce any protection-interpretation FUNCTIONALITY.
    Explanatory prose naming these concepts (e.g. "no relay logic here")
    is fine; only executable/keyword scope creep is forbidden."""

    def test_no_protection_keywords_in_sequence_module(self):
        source = _source()
        seq_module = _function_body(source, "Sequence Components v1 -- the FOURTH Analysis-menu analyzer", "// ------------------------------------------------------------------\n        // Init")
        for forbidden in ("distanceProtection", "faultClassification", "groundFault", "negativeSequenceRelay", "tripDecision"):
            assert forbidden not in seq_module
