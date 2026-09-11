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


class TestBayIsTheOnlyPrimaryControl:
    """Phasor UAT redesign: bay-centric -- Engineering Context selection
    is the ONLY primary control. Quantity/Mode selectors are removed
    entirely; every supported role is always requested together."""

    def test_context_selector_exists(self):
        source = _source()
        assert 'id="wwPhasorContextSelect"' in source

    def test_quantity_selector_removed(self):
        source = _source()
        assert 'id="wwPhasorQuantitySelect"' not in source
        assert "wwPhasorState.quantity" not in source

    def test_mode_selector_removed(self):
        source = _source()
        assert 'id="wwPhasorModeSelect"' not in source
        assert "wwPhasorState.modeSuffix" not in source
        assert "wwPhasorBackendMode" not in source

    def test_controls_row_has_no_other_select_besides_context(self):
        source = _source()
        body = _function_body(source, 'class="ww-phasor-controls-row"', "</section>")
        assert body.count("<select") == 1
        assert 'id="wwPhasorContextSelect"' in body


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


class TestBayCentricAggregation:
    """Phasor UAT redesign: ONE aggregated fetch (`GET .../phasor-
    diagram`) resolves and estimates every supported role
    (Va/Vb/Vc/Ia/Ib/Ic) together -- no separate input-resolution call, no
    per-role fetch, never a whole-page failure for a partial bay."""

    def test_calls_the_aggregated_phasor_diagram_endpoint(self):
        source = _source()
        body = _phasor_block(source)
        assert '"/engineering-contexts/" + encodeURIComponent(contextId) + "/phasor-diagram?"' in body
        # The old two-call flow is gone entirely.
        assert "/input-resolution?" not in body
        assert '"/phasor?"' not in body

    def test_single_fetch_function_no_separate_resolution_call(self):
        source = _source()
        body = _phasor_block(source)
        assert "function wwPhasorFetchDiagram(" in body
        assert "function wwPhasorFetchResolution" not in body
        assert "function wwPhasorFetchResult" not in body

    def test_selecting_a_context_goes_straight_to_the_diagram_fetch(self):
        source = _source()
        body = _function_body(source, "function wwPhasorLoadForSelectedContext", "function wwPhasorAnchorDisplaySourceIdForContext")
        assert "wwPhasorRequestDiagram();" in body

    def test_whole_result_blocked_status_shows_banner(self):
        source = _source()
        body = _phasor_block(source)
        assert 'diagram.status === "needs_configuration"' in body
        assert "wwPhasorWholeResultBlockedMessage" in body

    def test_per_role_status_vocabulary_rendered(self):
        """One bad role (missing/ambiguous/needs_configuration/
        not_eligible) is rendered on its OWN row and never blocks any
        other role's own row."""
        source = _source()
        body = _function_body(source, "function wwPhasorRoleStatusLabel", "function wwPhasorRenderDiagramResult")
        for status in ("missing:", "needs_configuration:", "ambiguous:", "not_eligible:"):
            assert status in body

    def test_no_manual_raw_channel_picker_in_normal_workflow(self):
        """The engineer never picks Va/Vb/Vc/Ia/Ib/Ic directly -- the Bay
        (Engineering Context) selector is the only channel-adjacent
        control; there is no channel-name <select>/<input> anywhere in
        the Phasor panel markup."""
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index('id="wwPhasorSvg"')]
        assert "wwPhasorChannelSelect" not in panel_html
        assert "raw-channel" not in panel_html.lower()
        assert panel_html.count("<select") == 1  # the Bay/Engineering Context selector only


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
        body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert "wwWorkspaceTimeToSourceTime(anchorDisplaySourceId, wwPhasorState.analysisTime)" in body

    def test_anchor_is_any_context_member_never_a_role_matching_decision(self):
        """wwPhasorAnchorDisplaySourceIdForContext() picks a time-axis
        conversion anchor from the context's own FIRST member -- it must
        never inspect phase/engineering_type (that would duplicate the
        resolver's own role-matching, which the redesign explicitly
        forbids in the frontend)."""
        source = _source()
        body = _function_body(source, "function wwPhasorAnchorDisplaySourceIdForContext", "async function wwPhasorRequestDiagram")
        assert "ctx.members[0]" in body
        assert ".phase" not in body
        assert "engineering_type" not in body

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

    def test_table_uses_absolute_angle_only_never_relative(self):
        """Owner instruction: the numeric table's primary angle must
        never mismatch what the diagram itself draws -- the diagram
        always uses `angle_deg_absolute`, so the redesigned table shows
        ONLY that value, never `angle_deg_relative`, avoiding the
        mismatch risk entirely."""
        source = _source()
        body = _function_body(source, "function wwPhasorValueRowHtml", "function wwPhasorRenderValuesList")
        assert "role.angle_deg_absolute" in body
        assert "angle_deg_relative" not in body

    def test_voltage_and_current_sections_exist(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderValuesList", "function wwPhasorFamilyMaxMagnitude")
        assert "ww-phasor-family-heading\">Voltage" in body
        assert "ww-phasor-family-heading\">Current" in body
        assert "WW_PHASOR_VOLTAGE_ROLES" in body
        assert "WW_PHASOR_CURRENT_ROLES" in body

    def test_all_six_roles_in_fixed_order(self):
        source = _source()
        body = _phasor_block(source)
        assert 'WW_PHASOR_DIAGRAM_ROLE_ORDER = ["Va", "Vb", "Vc", "Ia", "Ib", "Ic"];' in body
        assert 'WW_PHASOR_VOLTAGE_ROLES = ["Va", "Vb", "Vc"];' in body
        assert 'WW_PHASOR_CURRENT_ROLES = ["Ia", "Ib", "Ic"];' in body

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

    def test_voltage_and_current_use_separate_graphical_scales(self):
        """Owner instruction: Va/Vb/Vc share ONE scale, Ia/Ib/Ic share a
        SEPARATE scale -- never one raw numeric radius shared across both
        families, and never a per-vector individual scale within a
        family."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "wwPhasorFamilyMaxMagnitude(diagram, WW_PHASOR_VOLTAGE_ROLES)" in body
        assert "wwPhasorFamilyMaxMagnitude(diagram, WW_PHASOR_CURRENT_ROLES)" in body
        assert "const voltageScale = voltageMax > 0 ? plotRadius / (1.15 * voltageMax) : 0;" in body
        assert "const currentScale = currentMax > 0 ? plotRadius / (1.15 * currentMax) : 0;" in body
        # Exactly one scale variable per family -- never per-vector.
        assert body.count("const voltageScale") == 1
        assert body.count("const currentScale") == 1

    def test_scaling_is_graphical_only_never_touches_magnitude_rms(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        # magnitude_rms is only ever READ (multiplied into a local pixel
        # radius `r`), never reassigned.
        assert "role.magnitude_rms =" not in body
        assert "const r = role.magnitude_rms * scale;" in body

    def test_scale_note_shown_only_when_both_families_present(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "if (voltageMax > 0 && currentMax > 0) {" in body
        assert "scaleNote.hidden = false;" in body
        assert "Current vectors scaled" in body

    def test_geometry_uses_absolute_angle_never_relative(self):
        """Critical: the combined diagram must never independently
        zero-reference Voltage and Current -- doing so would destroy the
        true V-I angular relationship. Only `angle_deg_absolute` ever
        drives vector geometry."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "role.angle_deg_absolute * Math.PI / 180" in body
        assert "angle_deg_relative" not in body

    def test_current_vectors_are_dashed_voltage_vectors_are_solid(self):
        source = _source()
        body = _phasor_block(source)
        assert "ww-phasor-vector--current" in body
        assert "const isCurrent = roleKey.charAt(0) === \"I\";" in body

    def test_hidden_roles_are_skipped_by_visibility_state(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "if (wwPhasorState.visibleRoles[roleKey] === false) continue;" in body

    def test_vectors_never_show_without_explanation_when_unavailable(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramResult", "function wwPhasorRenderFromState")
        assert 'statusRow.textContent = "Could not reach the backend.";' in body
        assert "wwPhasorWholeResultBlockedMessage(diagram)" in body


class TestStaleRequestProtection:
    def test_shared_request_generation_counter_exists(self):
        source = _source()
        body = _phasor_block(source)
        assert "requestGeneration: 0" in body
        # Only ONE fetch now (the aggregated diagram fetch) -- the old
        # two-call (resolution, then calculation) flow is gone, so there
        # is exactly one generation-bump site.
        assert body.count("++wwPhasorState.requestGeneration") == 1

    def test_diagram_fetch_checks_generation_before_applying(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert "if (myGeneration !== wwPhasorState.requestGeneration" in body

    def test_also_respects_workspace_wide_epoch_guard(self):
        source = _source()
        body = _phasor_block(source)
        assert "epochAtStart !== ww.epoch" in body


class TestVisibilityState:
    """Phasor UAT redesign: individual vector visibility is a PURE
    frontend display preference -- it never re-runs the backend
    estimator, never touches Engineering Context membership, phase
    identity, resolver rules, or Measurement Groups."""

    def test_visible_roles_state_exists_and_starts_empty(self):
        source = _source()
        body = _phasor_block(source)
        assert "visibleRoles: {}," in body

    def test_row_is_an_accessible_toggle_button_not_a_tiny_icon(self):
        """Reuses the EXACT #channelGroups row-as-toggle-button
        convention (role="button", tabindex, aria-pressed) rather than a
        small icon-only hit target."""
        source = _source()
        body = _function_body(source, "function wwPhasorValueRowHtml", "function wwPhasorRenderValuesList")
        assert "ww-phasor-value-row--toggle" in body
        assert 'role="button" tabindex="0" aria-pressed="' in body
        assert "ww-phasor-value-row--hidden" in body

    def test_toggle_re_renders_locally_never_refetches(self):
        source = _source()
        body = _function_body(source, "function wwPhasorToggleRoleVisibility", "function wwPhasorValueRowHtml")
        assert "wwPhasorRenderFromState();" in body
        assert "wwPhasorRequestDiagram" not in body
        assert "fetch(" not in body

    def test_render_from_state_never_fetches(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderFromState", "function wwPhasorToggleRoleVisibility")
        assert "await" not in body
        assert "wwPhasorFetchDiagram" not in body

    def test_delegated_click_and_keydown_wiring_exists(self):
        source = _source()
        assert '.closest(".ww-phasor-value-row--toggle")' in source
        assert 'event.key !== "Enter" && event.key !== " "' in source
        assert "document.getElementById(\"wwPhasorValuesList\").addEventListener(\"click\"" in source
        assert "document.getElementById(\"wwPhasorValuesList\").addEventListener(\"keydown\"" in source

    def test_visibility_reset_only_on_context_change_not_on_time_change(self):
        """A genuinely different Engineering Context resets visibility to
        "all available roles visible"; an Analysis Time change on the
        SAME context must never do this."""
        source = _source()
        load_context_body = _function_body(source, "function wwPhasorLoadForSelectedContext", "function wwPhasorAnchorDisplaySourceIdForContext")
        assert "wwPhasorState.visibleRoles = {};" in load_context_body
        time_input_body = source[source.index("function wwPhasorOnAnalysisTimeInput"):source.index("}", source.index("function wwPhasorOnAnalysisTimeInput"))]
        assert "wwPhasorState.visibleRoles" not in time_input_body

    def test_default_visibility_never_overwrites_an_existing_preference(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert '!(roleKey in wwPhasorState.visibleRoles)' in body

    def test_missing_or_ambiguous_roles_have_no_toggle_control(self):
        source = _source()
        body = _function_body(source, "function wwPhasorValueRowHtml", "function wwPhasorRenderValuesList")
        assert 'role.status !== "available"' in body


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
