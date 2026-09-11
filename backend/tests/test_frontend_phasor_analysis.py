"""Static structural regression checks for Phasor Analysis Slice 2
(frontend/index.html) -- the first `Analysis` menu consumer.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses -- this repo has no
browser/DOM test runner for the single-file frontend. Real
fetch/render/interaction BEHAVIOR is covered separately by
`browser-tests/phasor_analysis.spec.js` (Playwright, real browser) --
these tests only guard structural invariants a source-text assertion
CAN meaningfully verify (presence/absence of navigation elements,
function ordering, the shape of the mode-mapping/angle-selection logic,
absence of a manual channel picker or Playback wiring).
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


def _phasor_block(source: str) -> str:
    """The whole Phasor Analysis Slice 2 JS block -- from its own state
    object declaration (unique in the file, unlike the header comment
    text, which is echoed by an earlier HTML nav-button comment) to the
    pre-existing "// Init" section immediately after it."""
    start = source.index("const wwPhasorState = {")
    end = source.index("\n        // Init\n", start)
    return source[start:end]


class TestAnalysisMenuExists:
    def test_analysis_nav_button_exists(self):
        source = _source()
        assert 'id="mainNavAnalysisBtn"' in source

    def test_nav_tooltip_and_label_say_phasor_diagram_not_analysis(self):
        """UAT fix (2026-09-11): the bare "Analysis" tooltip/visible label
        was too generic with only one analyzer implemented -- both now
        read "Phasor Diagram" (the ONE destination that exists today);
        the page's own <h2> heading deliberately stays "Analysis" (see
        test_page_heading_remains_analysis below) since that is what will
        read correctly once a second analyzer exists. The `id` itself is
        unaffected -- only the two user-facing strings changed."""
        source = _source()
        body = _function_body(source, 'id="mainNavAnalysisBtn"', "</button>")
        assert 'title="Phasor Diagram"' in body
        assert '<span class="shell-nav-label">Phasor Diagram</span>' in body
        assert 'title="Analysis"' not in body
        assert '<span class="shell-nav-label">Analysis</span>' not in body

    def test_page_heading_remains_analysis(self):
        source = _source()
        assert "<h2>Analysis</h2>" in source

    def test_analysis_page_section_exists(self):
        source = _source()
        assert 'id="pageAnalysis"' in source

    def test_shellSetCurrentPage_has_analysis_case(self):
        source = _source()
        assert 'page !== "analysis"' in source
        assert 'document.getElementById("pageAnalysis").hidden = page !== "analysis"' in source
        assert 'setShellNavCurrent("mainNavAnalysisBtn", page === "analysis")' in source

    def test_analysis_nav_click_wires_to_shellSetCurrentPage(self):
        source = _source()
        assert 'document.getElementById("mainNavAnalysisBtn").addEventListener("click", () => shellSetCurrentPage("analysis"));' in source


class TestAnalysisTypeSubNav:
    """The seam future analyzers (Distance Protection/Overcurrent/
    Differential/Sequence Components) plug into -- only Phasor exists in
    this slice."""

    def test_analysis_type_nav_exists_with_exactly_one_entry(self):
        source = _source()
        assert 'class="ww-analysis-type-nav"' in source
        assert source.count('class="ww-analysis-type-item') == 1

    def test_phasor_is_the_one_analysis_type_entry(self):
        source = _source()
        assert 'id="wwAnalysisTypePhasorBtn"' in source
        assert 'data-analysis-type="phasor"' in source


class TestContextQuantityModeSelectors:
    def test_context_selector_exists(self):
        source = _source()
        assert 'id="wwPhasorContextSelect"' in source

    def test_quantity_selector_has_voltage_and_current_only(self):
        source = _source()
        body = _function_body(source, 'id="wwPhasorQuantitySelect"', "</select>")
        assert '<option value="voltage">Voltage</option>' in body
        assert '<option value="current">Current</option>' in body
        assert "power" not in body.lower()

    def test_mode_selector_has_four_modes(self):
        source = _source()
        body = _function_body(source, 'id="wwPhasorModeSelect"', "</select>")
        assert '<option value="phase_a">Phase A</option>' in body
        assert '<option value="phase_b">Phase B</option>' in body
        assert '<option value="phase_c">Phase C</option>' in body
        assert '<option value="three_phase" selected>Three Phase</option>' in body

    def test_mode_maps_directly_to_backend_mode_string_no_hardcoded_channel_rules(self):
        source = _source()
        body = _phasor_block(source)
        assert 'function wwPhasorBackendMode() {\n            return wwPhasorState.quantity + "_" + wwPhasorState.modeSuffix;' in body
        # No channel-name literal (e.g. "_VA"/"ALPHA1") appears in the
        # mode-mapping logic -- mapping is purely a string concatenation
        # of quantity + mode suffix, never a channel-selection rule.
        assert "_VA" not in body
        assert "_IA" not in body


class TestEngineeringContextPopulation:
    def test_fetches_from_the_existing_engineering_contexts_endpoint(self):
        source = _source()
        body = _phasor_block(source)
        assert '"/api/v1/workspaces/" + encodeURIComponent(workspaceId) + "/engineering-contexts"' in body

    def test_never_reimplements_context_detection(self):
        source = _source()
        body = _phasor_block(source)
        assert "detect_engineering_context" not in body.lower()
        assert "classify_waveform_form" not in body

    def test_status_badge_reuses_measurement_group_badge_vocabulary(self):
        source = _source()
        body = _phasor_block(source)
        assert "ww-mg-badge ww-mg-badge--" in body


class TestContextBootstrap:
    """UAT fix (2026-09-11): when the workspace has loaded sources but no
    Engineering Contexts yet, Phasor auto-bootstraps suggestions instead
    of leaving the engineer to go configure one elsewhere first."""

    def test_existing_contexts_skip_bootstrap_entirely(self):
        """Owner instruction: this fix must not alter already-working
        workflows -- if contexts.length > 0, render immediately, no
        suggestion request."""
        source = _source()
        body = _function_body(source, "async function wwPhasorLoadContexts", "async function wwPhasorRunBootstrap")
        assert "if (contexts.length > 0) {" in body
        # The "already exists" branch returns before ever reaching
        # wwPhasorRunBootstrap().
        assert body.index("if (contexts.length > 0) {") < body.index("await wwPhasorRunBootstrap(")

    def test_zero_contexts_triggers_bootstrap(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorLoadContexts", "async function wwPhasorRunBootstrap")
        assert "await wwPhasorRunBootstrap(workspaceId, epochAtStart);" in body

    def test_bootstrap_reuses_existing_suggest_endpoint_no_new_detection_engine(self):
        source = _source()
        body = _phasor_block(source)
        assert '"/sources/" + encodeURIComponent(sourceId) + "/engineering-contexts/suggest"' in body
        assert "function wwPhasorFetchSuggest" in body
        # No frontend channel-name parsing was introduced for detection.
        bootstrap_body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "channel_name.endsWith" not in bootstrap_body
        assert ".match(/" not in bootstrap_body

    def test_all_loaded_sources_are_considered_not_just_the_first(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "for (const source of sources) {" in body
        assert "sources[0]" not in body

    def test_one_source_failure_does_not_abort_the_others(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "let anyFailed = false;" in body
        assert "anyFailed = true;" in body

    def test_context_list_refetched_after_suggestions(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert body.count("wwPhasorFetchContexts(workspaceId)") == 1

    def test_newly_suggested_contexts_populate_selector_and_auto_select_first(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "wwPhasorRenderContextOptions();" in body
        assert "wwPhasorAutoSelectFirstContext();" in body

    def test_auto_select_only_happens_on_the_bootstrap_path(self):
        """The pre-existing "contexts already existed" branch in
        wwPhasorLoadContexts() must NOT auto-select -- owner instruction:
        preserve existing behavior there unchanged."""
        source = _source()
        load_contexts_body = _function_body(source, "async function wwPhasorLoadContexts", "async function wwPhasorRunBootstrap")
        assert "wwPhasorAutoSelectFirstContext" not in load_contexts_body

    def test_suggested_and_needs_review_contexts_are_not_filtered_out(self):
        """Detection may suggest; engineer confirmation remains
        authoritative -- suggested/needs_review contexts still populate
        the selector and still show their existing status badge, never
        auto-upgraded to confirmed."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderContextOptions", "function wwPhasorRenderContextBadge")
        assert "ctx.status" not in body  # no status-based filtering of the option list
        assert '.filter(' not in body
        badge_body = _function_body(source, "function wwPhasorRenderContextBadge", "function wwPhasorShowEmptyState")
        assert '"status": "confirmed"' not in badge_body
        assert "PATCH" not in badge_body

    def test_no_repeated_suggestion_loop(self):
        source = _source()
        body = _phasor_block(source)
        assert "bootstrapAttempted: false" in body
        load_contexts_body = _function_body(source, "async function wwPhasorLoadContexts", "async function wwPhasorRunBootstrap")
        assert "if (wwPhasorState.bootstrapAttempted) {" in load_contexts_body
        bootstrap_body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "wwPhasorState.bootstrapAttempted = true;" in bootstrap_body

    def test_zero_sources_shows_no_source_state_not_no_context_state(self):
        source = _source()
        body = _phasor_block(source)
        assert 'WW_PHASOR_MSG_NO_SOURCES = "No event sources are available. Load a recording before using Phasor Diagram."' in body
        bootstrap_body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "WW_PHASOR_MSG_NO_SOURCES" in bootstrap_body

    def test_failed_suggestion_surfaces_actionable_backend_unreachable_message(self):
        source = _source()
        body = _phasor_block(source)
        assert 'WW_PHASOR_MSG_BACKEND_UNREACHABLE = "Could not reach the backend while identifying engineering contexts."' in body
        bootstrap_body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "anyFailed ? WW_PHASOR_MSG_BACKEND_UNREACHABLE : WW_PHASOR_MSG_NO_SUGGESTIONS" in bootstrap_body

    def test_identifying_contexts_loading_message_shown_during_bootstrap(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert "wwPhasorShowEmptyState(WW_PHASOR_MSG_IDENTIFYING_CONTEXTS);" in body

    def test_still_no_manual_raw_channel_picker_introduced(self):
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index('id="wwPhasorSvg"')]
        assert "wwPhasorChannelSelect" not in panel_html
        assert "raw-channel" not in panel_html.lower()

    def test_stale_bootstrap_response_is_discarded(self):
        """Every async step inside the bootstrap re-checks the same
        epoch/workspaceId guard every other Phasor fetch already uses --
        a workspace change mid-bootstrap must never populate the wrong
        workspace's own selector."""
        source = _source()
        body = _function_body(source, "async function wwPhasorRunBootstrap", "function wwPhasorAutoSelectFirstContext")
        assert body.count("epochAtStart !== ww.epoch || currentWorkspaceId() !== workspaceId") >= 3


class TestResolverIntegration:
    def test_calls_existing_input_resolution_endpoint(self):
        source = _source()
        body = _phasor_block(source)
        assert '"/engineering-contexts/" + encodeURIComponent(contextId) + "/input-resolution?"' in body

    def test_phasor_not_requested_until_resolved(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestResolution", "async function wwPhasorRenderResolutionStatus".replace("async ", ""))
        assert 'if (resolution.status !== "resolved") {' in body
        assert "wwPhasorRequestCalculation();" in body

    def test_ambiguous_state_rendered_with_candidates(self):
        source = _source()
        body = _phasor_block(source)
        assert 'resolution.status === "ambiguous"' in body
        assert "Multiple candidates found" in body

    def test_needs_configuration_shows_backend_reason(self):
        source = _source()
        body = _phasor_block(source)
        assert 'resolution.status === "needs_configuration"' in body
        assert "wwPhasorReasonText" in body

    def test_no_manual_raw_channel_picker_in_normal_workflow(self):
        """The engineer never picks Va/Vb/Vc/Ia/Ib/Ic directly -- only
        Bay/Quantity/Mode selectors exist; there is no channel-name
        <select>/<input> anywhere in the Phasor panel markup."""
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index('id="wwPhasorSvg"')]
        assert "wwPhasorChannelSelect" not in panel_html
        assert "<select" not in panel_html.split('id="wwPhasorModeSelect"')[1].split("</select>")[1].split('id="wwPhasorTimeInput"')[0]


class TestAnalysisTimeAndDefault:
    def test_time_input_and_slider_exist(self):
        source = _source()
        assert 'id="wwPhasorTimeInput"' in source
        assert 'id="wwPhasorTimeSlider"' in source

    def test_default_time_prefers_cursor_a_then_buffered_start(self):
        source = _source()
        body = _function_body(source, "function wwPhasorComputeDefaultAnalysisTime", "function wwPhasorSyncTimeControls")
        assert "wwTimeGroupCursorState(groupId)" in body
        assert "cursors.a" in body
        assert "WW_PHASOR_DEFAULT_TIME_BUFFER_SECONDS" in body

    def test_analysis_time_converted_to_source_time_at_api_boundary_only(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestCalculation", "function wwPhasorUnavailableMessage")
        assert "wwWorkspaceTimeToSourceTime(anchorDisplaySourceId, wwPhasorState.analysisTime)" in body

    def test_no_second_global_time_controller(self):
        source = _source()
        body = _phasor_block(source)
        assert "requestAnimationFrame" not in body
        assert "performance.now()" not in body


class TestValueAndAngleRendering:
    def test_magnitude_uses_existing_engineering_formatter(self):
        source = _source()
        body = _phasor_block(source)
        assert "wwFormatEngineeringValue(role.magnitude_rms)" in body

    def test_three_phase_uses_relative_angle_as_primary(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderValuesAndDiagram", "function wwPhasorRenderDiagram")
        assert "const isRelative = roleKeys.length > 1;" in body
        assert "isRelative && role.angle_deg_relative !== null ? role.angle_deg_relative : role.angle_deg_absolute" in body

    def test_single_phase_never_fabricates_a_zero_reference(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderValuesAndDiagram", "function wwPhasorRenderDiagram")
        # Single-phase (roleKeys.length === 1) falls through to
        # angle_deg_absolute -- never a literal 0 substituted in.
        assert "angle_deg_absolute" in body

    def test_no_per_unit_normalization_in_this_slice(self):
        source = _source()
        body = _phasor_block(source)
        assert "unit_mode" not in body
        assert "per_unit" not in body.lower()


class TestSvgDiagram:
    def test_svg_element_exists_not_plotly(self):
        source = _source()
        assert 'id="wwPhasorSvg"' in source
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index("</section>", source.index('id="wwPhasorSvg"'))]
        assert "Plotly" not in panel_html

    def test_diagram_shares_one_magnitude_scale_across_vectors(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagram", "function wwPhasorVectorSvg")
        assert "const maxMagnitude = magnitudes.length > 0 ? Math.max(...magnitudes) : 0;" in body
        assert "const scale = maxMagnitude > 0 ? plotRadius / (1.15 * maxMagnitude) : 0;" in body
        # scale computed once, reused for every role -- never per-vector.
        assert body.count("const scale") == 1

    def test_vectors_never_show_without_explanation_when_unavailable(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderValuesAndDiagram", "function wwPhasorRenderDiagram")
        assert 'svg.innerHTML = "";' in body
        assert "wwPhasorUnavailableMessage(result)" in body


class TestStaleRequestProtection:
    def test_shared_request_generation_counter_exists(self):
        source = _source()
        body = _phasor_block(source)
        assert "requestGeneration: 0" in body
        assert body.count("++wwPhasorState.requestGeneration") == 2

    def test_resolution_fetch_checks_generation_before_applying(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestResolution", "function wwPhasorRenderResolutionStatus")
        assert "if (myGeneration !== wwPhasorState.requestGeneration" in body

    def test_calculation_fetch_checks_generation_before_applying(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestCalculation", "function wwPhasorUnavailableMessage")
        assert "if (myGeneration !== wwPhasorState.requestGeneration" in body

    def test_also_respects_workspace_wide_epoch_guard(self):
        source = _source()
        body = _phasor_block(source)
        assert "epochAtStart !== ww.epoch" in body


class TestNoPlaybackIntegrationYet:
    """Explicit scope exclusion for this slice -- Slice 3 adds this."""

    def test_no_wwplayback_reference_in_phasor_block(self):
        """No functional coupling to the Playback controller -- a
        COMMENT explaining the analogy to wwPlaybackReset()'s own
        wwClearWorkspace() registration is fine (and present); an actual
        call/property-access is not."""
        source = _source()
        body = _phasor_block(source)
        assert "wwPlaybackOnTick(" not in body
        assert "wwPlayback." not in body
        assert "wwPlayback.state" not in body
        assert "wwWirePlaybackControls(" not in body
        assert "wwSyncPlaybackControls(" not in body

    def test_no_play_pause_speed_seek_controls_in_phasor_panel(self):
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index("</section>\n                    </div>\n                </div>\n            </section>", source.index('id="wwPhasorPanel"'))]
        assert "wwPlaybackControls" not in panel_html
        assert "ww-tg-playback" not in panel_html

    def test_composition_point_comment_exists_for_slice_3(self):
        source = _source()
        assert "Slice 3 composition point" in source


class TestClearWorkspaceLifecycle:
    def test_wwclearworkspace_resets_phasor_state(self):
        source = _source()
        body = _function_body(source, "function wwClearWorkspace(options)", "for (const panel of ww.panels)")
        assert "wwPhasorResetState();" in body

    def test_reset_function_clears_selection_and_dom(self):
        source = _source()
        body = _function_body(source, "function wwPhasorResetState()", "// ------------------------------------------------------------------\n        // Init")
        assert "wwPhasorState.selectedContextId = null;" in body
        assert "wwPhasorState.requestGeneration += 1;" in body
