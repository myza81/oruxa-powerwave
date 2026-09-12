"""Static structural regression checks for the shared Analysis "Related
Waveforms" panel (frontend/index.html) -- the third shared Analysis
workspace primitive after the Engineering Context lifecycle and shared
Playback. Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses. Real fetch/render/
Playback-cursor/resize behavior is covered separately by
`browser-tests/analysis_related_waveforms.spec.js` (Playwright, real
browser).

Core architectural invariant under test: the analyzer decides WHAT
signals are relevant; the shared Analysis workspace decides HOW those
waveforms are fetched, grouped, rendered, and synchronized with
Playback.
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


class TestSharedPanelExistsOnce:
    def test_panel_exists_exactly_once_in_the_shared_shell(self):
        source = _source()
        assert source.count('id="wwAnalysisRelatedWaveformsPanel"') == 1

    def test_panel_is_a_direct_child_of_the_shared_analysis_content_not_inside_either_analyzer_panel(self):
        """Belongs to the shared Analysis shell, never a Phasor- or
        Overcurrent-specific card -- the panel's own static markup sits
        between `.ww-analysis-content`'s opening tag and `#wwPhasorPanel`'s
        own opening tag, i.e. BEFORE both analyzer panels, not nested
        inside either."""
        source = _source()
        shell_start = source.index('class="ww-analysis-content"')
        phasor_panel_start = source.index('id="wwPhasorPanel"', shell_start)
        panel_start = source.index('id="wwAnalysisRelatedWaveformsPanel"', shell_start)
        assert shell_start < panel_start < phasor_panel_start

    def test_one_anchor_per_analyzer_directly_below_its_own_playback_panel(self):
        source = _source()
        phasor_block = _function_body(source, 'id="wwPhasorPlaybackPanel"', 'id="wwPhasorStatusRow"')
        assert 'id="wwPhasorRelatedWaveformsAnchor"' in phasor_block
        overcurrent_block = _function_body(source, 'id="wwOvercurrentPlaybackPanel"', 'id="wwOvercurrentStatusRow"')
        assert 'id="wwOvercurrentRelatedWaveformsAnchor"' in overcurrent_block

    def test_not_duplicated_inside_either_analyzer_specific_markup(self):
        """No second #wwAnalysisRelatedWaveformsPanel/Voltage/Current
        chart element anywhere -- confirms the ONE shared DOM instance is
        reparented (never cloned) between analyzers."""
        source = _source()
        for element_id in (
            "wwAnalysisRelatedWaveformsVoltageChart", "wwAnalysisRelatedWaveformsCurrentChart",
            "wwAnalysisRelatedWaveformsBody", "wwAnalysisRelatedWaveformsResizeHandle",
        ):
            assert source.count('id="' + element_id + '"') == 1


class TestSharedRendererStatePath:
    def test_one_shared_state_object(self):
        source = _source()
        assert "const wwAnalysisRelatedWaveformsState = {" in source
        assert "wwPhasorRelatedWaveformsState" not in source
        assert "wwOvercurrentRelatedWaveformsState" not in source

    def test_one_shared_entry_point_both_analyzers_call(self):
        source = _source()
        assert source.count("function wwAnalysisSetRelatedWaveformRoles(") == 1
        phasor_push = _function_body(source, "function wwPhasorPushRelatedWaveformRoles", "\n        // Cheap re-render")
        assert "wwAnalysisSetRelatedWaveformRoles(" in phasor_push
        overcurrent_push = _function_body(source, "function wwOvercurrentPushRelatedWaveformRoles", "// Curve geometry depends ONLY")
        assert "wwAnalysisSetRelatedWaveformRoles(" in overcurrent_push

    def test_neither_analyzer_defines_its_own_waveform_rendering_engine(self):
        """Structural regression seam (task's own explicit instruction):
        no analyzer-specific renderer/fetch function -- confirms a future
        analyzer cannot silently add one without this test catching it."""
        source = _source()
        assert "function wwPhasorRenderRelatedWaveform" not in source
        assert "function wwOvercurrentRenderRelatedWaveform" not in source
        assert "function wwPhasorFetchRelatedWaveform" not in source
        assert "function wwOvercurrentFetchRelatedWaveform" not in source

    def test_analyzers_only_ever_declare_roles_never_render_or_fetch_directly(self):
        source = _source()
        phasor_fn = _function_body(source, "function wwPhasorComputeActiveRelatedWaveformRoles", "function wwPhasorPushRelatedWaveformRoles")
        assert "Plotly" not in phasor_fn
        assert "fetch(" not in phasor_fn
        overcurrent_fn = _function_body(source, "function wwOvercurrentComputeActiveRelatedWaveformRoles", "function wwOvercurrentPushRelatedWaveformRoles")
        assert "Plotly" not in overcurrent_fn
        assert "fetch(" not in overcurrent_fn

    def test_role_declaration_includes_the_required_identity_fields(self):
        """Task §7: role key, engineering type, canonical phase, resolved
        ChannelRef, display label."""
        source = _source()
        phasor_fn = _function_body(source, "function wwPhasorComputeActiveRelatedWaveformRoles", "function wwPhasorPushRelatedWaveformRoles")
        for field in ("roleKey", "engineeringType", "phase", "channelRef", "label"):
            assert field in phasor_fn

    def test_never_parses_a_channel_name_to_derive_a_role(self):
        source = _source()
        shared_module = _function_body(source, "const wwAnalysisRelatedWaveformsState = {", "function wwAnalysisMountRelatedWaveformsInto")
        assert "channel_name.split" not in shared_module
        assert "channel_name.match" not in shared_module
        assert ".endsWith(" not in shared_module


class TestSharedGrouping:
    def test_groups_by_engineering_type_field_not_name_prefix(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisRelatedWaveformsGroupRoles", "function wwAnalysisFetchChannelWaveform")
        assert 'r.engineeringType === engineeringType' in fn

    def test_partial_groups_are_valid_no_three_phase_requirement(self):
        source = _source()
        render_fn = _function_body(source, "function wwAnalysisRenderRelatedWaveforms", "function wwAnalysisRelatedWaveformsOnPlaybackTick")
        assert "=== 3" not in render_fn
        assert ".length !== 3" not in render_fn

    def test_only_voltage_and_current_groups_exist(self):
        source = _source()
        assert 'id="wwAnalysisRelatedWaveformsVoltageGroup"' in source
        assert 'id="wwAnalysisRelatedWaveformsCurrentGroup"' in source


class TestEmptyAndPartialStates:
    def test_empty_state_message_matches_owner_wording(self):
        source = _source()
        assert "No related waveform signals available for the current analysis." in source

    def test_neither_group_present_shows_empty_state_never_a_blank_plot(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisRenderRelatedWaveforms", "function wwAnalysisRelatedWaveformsOnPlaybackTick")
        assert "voltageRoles.length === 0 && currentRoles.length === 0" in fn
        assert "emptyState.hidden = false" in fn

    def test_one_family_present_hides_the_other_group_not_the_whole_panel(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisRenderRelatedWaveforms", "function wwAnalysisRelatedWaveformsOnPlaybackTick")
        assert "voltageGroup.hidden = voltageRoles.length === 0;" in fn
        assert "currentGroup.hidden = currentRoles.length === 0;" in fn


class TestPlaybackCursorSynchronization:
    def test_no_second_playback_clock_or_raf_loop(self):
        """No independent timer/clock anywhere in the shared module --
        the ONE `requestAnimationFrame` present belongs to the drag-
        resize handler's own rAF-coalescing (a UI-smoothness detail, not
        a clock), scoped separately below."""
        source = _source()
        shared_module = _function_body(source, "const wwAnalysisRelatedWaveformsState = {", "function wwAnalysisMountRelatedWaveformsInto")
        assert "setInterval(" not in shared_module
        assert "new Date(" not in shared_module
        assert "performance.now()" not in shared_module
        cursor_and_tick = _function_body(source, "function wwAnalysisRelatedWaveformsCursorShape", "function wwAnalysisResizeRelatedWaveformPlots")
        assert "requestAnimationFrame(" not in cursor_and_tick

    def test_cursor_reads_the_one_authoritative_shared_playback_time(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisRelatedWaveformsCursorShape", "function wwAnalysisRelatedWaveformsLayout")
        assert "wwPlayback.currentTime" in fn

    def test_registered_via_the_shared_tick_seam_exactly_once(self):
        source = _source()
        assert source.count("wwPlaybackOnTick(wwAnalysisRelatedWaveformsOnPlaybackTick)") == 1

    def test_tick_handler_updates_only_the_cursor_shape_never_refetches_or_rebuilds_traces(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisRelatedWaveformsOnPlaybackTick", "function wwAnalysisResizeRelatedWaveformPlots")
        assert "Plotly.relayout" in fn
        assert "Plotly.react" not in fn
        assert "fetch(" not in fn
        assert "wwAnalysisRefreshRelatedWaveforms" not in fn


class TestStaleResponseProtection:
    def test_refresh_uses_generation_epoch_and_workspace_guards(self):
        source = _source()
        fn = _function_body(source, "async function wwAnalysisRefreshRelatedWaveforms", "const WW_ARW_PLOTLY_CONFIG")
        assert "++s.requestGeneration" in fn
        assert "epochAtStart !== ww.epoch" in fn
        assert "currentWorkspaceId() !== workspaceId" in fn

    def test_context_change_clears_the_channel_cache(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisSetRelatedWaveformRoles", "function wwAnalysisRelatedWaveformsGroupRoles")
        assert "contextId !== s.contextId" in fn
        assert "s.channelCache.clear();" in fn

    def test_workspace_clear_resets_shared_related_waveforms_state(self):
        source = _source()
        clear_body = _function_body(source, "function wwClearWorkspace(options)", "function wwSyncTimeGroupCanvases")
        assert "wwAnalysisResetRelatedWaveformsState();" in clear_body


class TestNoOpWhenNothingMaterialChanged:
    def test_signature_short_circuit_prevents_redundant_pushes(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisSetRelatedWaveformRoles", "function wwAnalysisRelatedWaveformsGroupRoles")
        assert "if (signature === s.lastSignature) return;" in fn

    def test_only_uncached_channels_are_fetched(self):
        source = _source()
        fn = _function_body(source, "async function wwAnalysisRefreshRelatedWaveforms", "const WW_ARW_PLOTLY_CONFIG")
        assert "s.channelCache.has(key)" in fn

    def test_active_type_gate_prevents_the_hidden_analyzer_from_fighting_over_shared_state(self):
        """Real regression caught during implementation: both analyzers'
        own Playback tick handlers keep computing/rendering regardless of
        which panel is visible -- without this gate, two analyzers
        sharing one Time Group would thrash the shared role set (and
        therefore re-fetch) on every single tick."""
        source = _source()
        phasor_push = _function_body(source, "function wwPhasorPushRelatedWaveformRoles", "\n        // Cheap re-render")
        assert 'wwAnalysisActiveType !== "phasor"' in phasor_push
        overcurrent_push = _function_body(source, "function wwOvercurrentPushRelatedWaveformRoles", "// Curve geometry depends ONLY")
        assert 'wwAnalysisActiveType !== "overcurrent"' in overcurrent_push


class TestUnitsAndEngineering:
    def test_never_silently_applies_per_unit(self):
        source = _source()
        fn = _function_body(source, "async function wwAnalysisFetchChannelWaveform", "async function wwAnalysisRefreshRelatedWaveforms")
        assert 'url.searchParams.set("unit_mode", "engineering");' in fn

    def test_reuses_the_existing_waveform_endpoint_never_a_new_one(self):
        source = _source()
        fn = _function_body(source, "async function wwAnalysisFetchChannelWaveform", "async function wwAnalysisRefreshRelatedWaveforms")
        assert '"/sources/" + encodeURIComponent(channelRef.source_id) + "/waveform"' in fn
        assert '"/calculated-channels/" + encodeURIComponent(channelRef.calculated_channel_id) + "/waveform"' in fn

    def test_voltage_and_current_get_independent_y_axes_never_shared(self):
        """Two separate Plotly figures (one per family), each with its
        own yaxis/unit -- never one shared numerical axis."""
        source = _source()
        fn = _function_body(source, "function wwAnalysisRenderRelatedWaveforms", "function wwAnalysisRelatedWaveformsOnPlaybackTick")
        assert fn.count("Plotly.react(chartEl,") == 2


class TestPhasorVisibilitySync:
    def test_reuses_visible_roles_never_a_second_visibility_state(self):
        source = _source()
        fn = _function_body(source, "function wwPhasorComputeActiveRelatedWaveformRoles", "function wwPhasorPushRelatedWaveformRoles")
        assert "wwPhasorState.visibleRoles[roleKey] === false" in fn
        assert "RelatedWaveformVisible" not in source
        assert "wwArwVisibleRoles" not in source

    def test_push_wired_into_the_one_render_path_covers_the_toggle_case_too(self):
        """wwPhasorToggleRoleVisibility() -> wwPhasorRenderFromState() ->
        wwPhasorRenderDiagramResult() -- the push lives at the END of
        that one shared render path, so a visibility toggle automatically
        re-pushes without a second, toggle-specific hook."""
        source = _source()
        fn = _function_body(source, "function wwPhasorRenderDiagramResult", "function wwPhasorComputeActiveRelatedWaveformRoles")
        assert "wwPhasorPushRelatedWaveformRoles();" in fn

    def test_no_second_eye_control_introduced_for_waveforms(self):
        source = _source()
        arw_markup = _function_body(source, 'id="wwAnalysisRelatedWaveformsPanel"', "</section>")
        assert "toggle" not in arw_markup.lower()
        assert "eye" not in arw_markup.lower()


class TestOvercurrentPhaseSync:
    def test_single_current_role_driven_by_the_existing_phase_state(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentComputeActiveRelatedWaveformRoles", "function wwOvercurrentPushRelatedWaveformRoles")
        assert 'wwOvercurrentState.phase' in fn
        assert '"I" + wwOvercurrentState.phase' in fn

    def test_no_voltage_role_ever_declared_by_overcurrent(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentComputeActiveRelatedWaveformRoles", "function wwOvercurrentPushRelatedWaveformRoles")
        assert '"Voltage"' not in fn

    def test_only_computed_status_with_a_resolved_channel_ref_declares_a_role(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentComputeActiveRelatedWaveformRoles", "function wwOvercurrentPushRelatedWaveformRoles")
        assert 'result.status !== "computed"' in fn
        assert '!result.channel_ref' in fn


class TestAnalyzerSwitchBehavior:
    def test_switch_reparents_the_shared_panel_and_repushes_the_newly_active_analyzers_roles(self):
        source = _source()
        fn = _function_body(source, "function wwSetActiveAnalysisType", "document.getElementById(\"wwAnalysisTypePhasorBtn\")")
        assert 'wwAnalysisMountRelatedWaveformsInto("wwPhasorRelatedWaveformsAnchor");' in fn
        assert "wwPhasorPushRelatedWaveformRoles();" in fn
        assert 'wwAnalysisMountRelatedWaveformsInto("wwOvercurrentRelatedWaveformsAnchor");' in fn
        assert "wwOvercurrentPushRelatedWaveformRoles();" in fn

    def test_switch_never_touches_wwplayback(self):
        source = _source()
        fn = _function_body(source, "function wwSetActiveAnalysisType", "document.getElementById(\"wwAnalysisTypePhasorBtn\")")
        assert "wwPlayback." not in fn
        assert "wwPlaybackSeek" not in fn
        assert "wwPlaybackRestart" not in fn

    def test_reparent_moves_the_existing_node_never_clones_it(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisMountRelatedWaveformsInto", "// ==")
        assert "insertBefore" in fn
        assert "cloneNode" not in fn
        assert "innerHTML" not in fn


class TestResizableHeight:
    """Owner UAT addendum: the panel is vertically resizable by the
    user, implemented once at the shared Analysis level (never a
    per-analyzer resize implementation) -- reuses the EXACT existing
    `.ww-resize-handle` class/drag-mechanics pattern the Waveform page's
    own per-channel-panel resize already established."""

    def test_reuses_the_existing_resize_handle_css_class(self):
        source = _source()
        markup = _function_body(source, 'id="wwAnalysisRelatedWaveformsPanel"', "</section>")
        assert 'class="ww-resize-handle"' in markup

    def test_one_shared_resize_wiring_function_never_per_analyzer(self):
        source = _source()
        assert source.count("function wwAnalysisWireRelatedWaveformsResize") == 1
        assert "function wwPhasorWireRelatedWaveformsResize" not in source
        assert "function wwOvercurrentWireRelatedWaveformsResize" not in source

    def test_min_and_max_height_bounds_are_enforced(self):
        source = _source()
        assert "const WW_ARW_MIN_HEIGHT = 150;" in source
        assert "const WW_ARW_MAX_HEIGHT = 520;" in source
        fn = _function_body(source, "function wwAnalysisClampRelatedWaveformsHeight", "function wwAnalysisWireRelatedWaveformsResize")
        assert "Math.max(WW_ARW_MIN_HEIGHT" in fn
        assert "Math.min(WW_ARW_MAX_HEIGHT" in fn

    def test_height_persists_in_frontend_state_only_never_localstorage_or_backend(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisWireRelatedWaveformsResize", "function wwAnalysisMountRelatedWaveformsInto")
        assert "localStorage" not in fn
        assert "fetch(" not in fn

    def test_drag_uses_pointer_events_with_capture_mirroring_the_existing_handle(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisWireRelatedWaveformsResize", "function wwAnalysisMountRelatedWaveformsInto")
        assert "pointerdown" in fn
        assert "pointermove" in fn
        assert "pointerup" in fn
        assert "setPointerCapture" in fn

    def test_drag_resizes_plotly_via_rAF_and_a_final_authoritative_write(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisWireRelatedWaveformsResize", "function wwAnalysisMountRelatedWaveformsInto")
        assert "requestAnimationFrame(flushResize)" in fn
        assert "wwAnalysisResizeRelatedWaveformPlots();" in fn

    def test_resize_never_touches_roles_cache_or_triggers_a_refetch(self):
        source = _source()
        fn = _function_body(source, "function wwAnalysisWireRelatedWaveformsResize", "function wwAnalysisMountRelatedWaveformsInto")
        assert "wwAnalysisRefreshRelatedWaveforms" not in fn
        assert "channelCache" not in fn
        assert "fetch(" not in fn
