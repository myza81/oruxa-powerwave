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


def _shared_analysis_block(source: str) -> str:
    """The shared Analysis Engineering Context lifecycle module
    (2026-09-12 owner UAT fix) -- context discovery/bootstrap, now owned
    by the Analysis workspace rather than any individual analyzer. From
    its own state declaration through the last shared function
    (wwAnalysisDiscoverUncoveredSources), up to the Overcurrent-specific
    message constant that immediately follows it in the file."""
    start = source.index("const wwAnalysisContextState = {")
    end = source.index("const WW_OVERCURRENT_MSG_SELECT_CONTEXT", start)
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
    """The seam future analyzers (Distance Protection/Differential/
    Sequence Components) plug into -- Phasor and Overcurrent (Overcurrent
    Analysis v1) are the first two."""

    def test_analysis_type_nav_exists_with_exactly_two_entries(self):
        source = _source()
        assert 'class="ww-analysis-type-nav"' in source
        assert source.count('class="ww-analysis-type-item') == 2

    def test_phasor_is_an_analysis_type_entry(self):
        source = _source()
        assert 'id="wwAnalysisTypePhasorBtn"' in source
        assert 'data-analysis-type="phasor"' in source

    def test_overcurrent_is_an_analysis_type_entry(self):
        source = _source()
        assert 'id="wwAnalysisTypeOvercurrentBtn"' in source
        assert 'data-analysis-type="overcurrent"' in source


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
        body = _shared_analysis_block(source)
        assert '"/api/v1/workspaces/" + encodeURIComponent(workspaceId) + "/engineering-contexts"' in body

    def test_never_reimplements_context_detection(self):
        source = _source()
        body = _shared_analysis_block(source)
        assert "detect_engineering_context" not in body.lower()
        assert "classify_waveform_form" not in body

    def test_status_badge_reuses_measurement_group_badge_vocabulary(self):
        source = _source()
        body = _phasor_block(source)
        assert "ww-mg-badge ww-mg-badge--" in body


class TestSharedAnalysisContextLifecycle:
    """2026-09-12 owner UAT fix -- root cause: Engineering Context
    discovery/bootstrap used to live entirely inside Phasor's own code
    path, while Overcurrent only ever read whatever contexts already
    existed. Opening Overcurrent directly on a fresh upload (without
    ever visiting Phasor first) therefore showed an empty Bay selector,
    an order-dependent bug that would recur for every future analyzer
    too. Fix: discovery/bootstrap moved to the shared Analysis workspace
    (`wwAnalysisLoadContexts()` and friends, below `const
    wwAnalysisContextState`) -- Phasor/Overcurrent are now pure
    CONSUMERS via `wwAnalysisRegisterContextConsumer()`, migrated here
    (logic unchanged) from the old Phasor-only `TestContextBootstrap`.
    Multi-upload bootstrap fix (2026-09-12, itself relocated unchanged):
    automatic Engineering Context suggestion is SOURCE-COVERAGE driven,
    not workspace-empty-driven -- a source uploaded AFTER the
    workspace's first context already exists must still be discovered,
    never silently skipped merely because `contexts.length > 0`."""

    def test_wwrenderanalysispage_calls_the_shared_loader_exactly_once(self):
        """The historical bug in one assertion: a single shared fetch/
        discovery entry point, never one per analyzer."""
        source = _source()
        fn = _function_body(source, "function wwRenderAnalysisPage()", "function wwPhasorOnAnalysisContexts")
        assert fn.count("wwAnalysisLoadContexts()") == 1
        assert "wwPhasorLoadContexts" not in fn
        assert "wwOvercurrentLoadContexts" not in fn

    def test_existing_contexts_published_immediately_discovery_runs_in_background(self):
        """Owner instruction: an already-usable Bay selector must never
        be blanked merely because another source is being suggested --
        the "at least one context exists" branch publishes FIRST, then
        kicks off discovery for whatever else is uncovered, non-blocking."""
        source = _source()
        body = _function_body(source, "function wwAnalysisHandleContextsFetched", "async function wwAnalysisDiscoverUncoveredSources")
        assert "if (contexts.length > 0) {" in body
        assert "wwAnalysisPublishContexts(contexts);" in body
        assert "wwAnalysisDiscoverUncoveredSources(workspaceId, epochAtStart, contexts, false);" in body
        # The publish call happens BEFORE discovery is kicked off -- never
        # the other way around.
        assert body.index("wwAnalysisPublishContexts(contexts);") < body.index("wwAnalysisDiscoverUncoveredSources(workspaceId, epochAtStart, contexts, false);")

    def test_zero_contexts_triggers_blocking_discovery_without_a_premature_publish(self):
        source = _source()
        body = _function_body(source, "function wwAnalysisHandleContextsFetched", "async function wwAnalysisDiscoverUncoveredSources")
        assert "wwAnalysisDiscoverUncoveredSources(workspaceId, epochAtStart, contexts, true);" in body
        # The zero-contexts branch does not itself call wwAnalysisPublishContexts
        # (that would prematurely show every consumer's own empty
        # selector before discovery even starts) -- only the >0 branch above does.
        tail = body[body.index("if (contexts.length > 0) {"):]
        zero_branch = tail[tail.index("}\n\n"):]
        assert "wwAnalysisPublishContexts" not in zero_branch

    def test_coverage_determined_from_member_source_id_never_name_or_count(self):
        """A source is covered if and only if at least one context
        contains a member whose channel_ref.source_id matches it --
        never context display name, status, or count."""
        source = _source()
        body = _function_body(source, "function wwAnalysisCoveredSourceIds", "function wwAnalysisLoadContexts")
        assert 'ref.kind === "source" && ref.source_id' in body
        assert "display_name" not in body
        assert ".status" not in body

    def test_uncovered_sources_computed_by_set_difference_not_context_count(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "wwAnalysisCoveredSourceIds(knownContexts)" in body
        assert "!coveredSourceIds.has(source.source_id)" in body

    def test_bootstrap_reuses_existing_suggest_endpoint_no_new_detection_engine(self):
        source = _source()
        body = _shared_analysis_block(source)
        assert '"/sources/" + encodeURIComponent(sourceId) + "/engineering-contexts/suggest"' in body
        assert "function wwAnalysisFetchSuggest" in body
        # No frontend channel-name parsing was introduced for detection.
        discover_body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "channel_name.endsWith" not in discover_body
        assert ".match(/" not in discover_body

    def test_all_uncovered_sources_are_considered_not_just_the_first(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "for (const source of uncoveredSources) {" in body
        assert "sources[0]" not in body
        assert "uncoveredSources[0]" not in body

    def test_one_source_failure_does_not_abort_the_others(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "let anyFailed = false;" in body
        assert "anyFailed = true;" in body

    def test_context_list_refetched_once_after_suggestions(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert body.count("wwAnalysisFetchContexts(workspaceId)") == 1

    def test_fresh_discovery_publishes_contexts_and_notifies_the_fresh_hook(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "wwAnalysisPublishContexts(contexts);" in body
        assert "wwAnalysisPublishFreshContextsDiscovered(contexts);" in body

    def test_fresh_hook_only_fires_on_the_zero_context_path_never_the_background_path(self):
        """Owner instruction: adding an uncovered source B must not
        unnecessarily switch the engineer away from an already-selected
        bay A -- the fresh-discovery hook is scoped to `blocking &&
        !hadContextsBefore`, never fired for the incremental/background
        discovery path. Whether to actually auto-select (given the
        consumer's OWN current selection) is each analyzer's own policy,
        not decided here."""
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "if (blocking && !hadContextsBefore) {" in body
        assert "wwAnalysisPublishFreshContextsDiscovered(contexts);" in body

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

    def test_attempted_source_ids_are_per_source_never_a_single_workspace_boolean(self):
        """Replaces the old workspace-wide `bootstrapAttempted` boolean --
        a per-source Set means a LATER-uploaded source can still be
        discovered even after an earlier source's own attempt already
        happened; a source is marked attempted individually, never the
        whole workspace at once. Now lives on the SHARED
        `wwAnalysisContextState`, never duplicated per-analyzer."""
        source = _source()
        body = _shared_analysis_block(source)
        assert "attemptedSourceIds: new Set()," in body
        assert "bootstrapAttempted" not in body
        discover_body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "!wwAnalysisContextState.attemptedSourceIds.has(source.source_id)" in discover_body
        assert "wwAnalysisContextState.attemptedSourceIds.add(source.source_id);" in discover_body

    def test_attempted_source_ids_reset_once_from_wwclearworkspace(self):
        source = _source()
        reset_body = _function_body(source, "function wwAnalysisResetContextState()", "const WW_PHASOR_DIAGRAM_ROLE_ORDER")
        assert "wwAnalysisContextState.attemptedSourceIds = new Set();" in reset_body
        clear_body = _function_body(source, "function wwClearWorkspace(options)", "function wwSyncTimeGroupCanvases")
        assert "wwAnalysisResetContextState();" in clear_body
        # Never duplicated back onto either analyzer's own per-workspace reset.
        assert "attemptedSourceIds" not in _function_body(source, "function wwPhasorResetState()", "\n        // Init\n")
        assert "attemptedSourceIds" not in _function_body(source, "function wwOvercurrentResetState()", "const wwPhasorState")

    def test_zero_sources_publishes_the_no_sources_phase(self):
        source = _source()
        body = _shared_analysis_block(source)
        assert 'WW_ANALYSIS_CONTEXT_PHASE_NO_SOURCES = "no_sources"' in body
        discover_body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "WW_ANALYSIS_CONTEXT_PHASE_NO_SOURCES" in discover_body

    def test_failed_suggestion_surfaces_the_unreachable_phase(self):
        source = _source()
        body = _shared_analysis_block(source)
        assert 'WW_ANALYSIS_CONTEXT_PHASE_UNREACHABLE = "unreachable"' in body
        discover_body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "anyFailed ? WW_ANALYSIS_CONTEXT_PHASE_UNREACHABLE : WW_ANALYSIS_CONTEXT_PHASE_NO_SUGGESTIONS" in discover_body

    def test_identifying_phase_only_published_when_blocking(self):
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "if (blocking) {" in body
        assert "wwAnalysisPublishLifecyclePhase(WW_ANALYSIS_CONTEXT_PHASE_IDENTIFYING);" in body

    def test_non_blocking_discovery_only_toggles_the_subtle_indicator_never_a_full_empty_state(self):
        """The incremental/background discovery path must never replace
        an already-usable page with a full empty state -- it only ever
        toggles the subtle, non-blocking indicator."""
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert "wwAnalysisSetDiscovering(true);" in body
        assert "wwAnalysisSetDiscovering(false);" in body

    def test_discovering_indicator_elements_exist_for_every_analyzer(self):
        """Future-analyzer protection seam: every analyzer that consumes
        the shared lifecycle owns its own discovering-indicator DOM
        element, proving the indicator toggle is per-CONSUMER, never a
        single Phasor-only element a future analyzer would have no way
        to hook into."""
        source = _source()
        assert 'id="wwPhasorDiscoveringIndicator"' in source
        assert 'id="wwOvercurrentDiscoveringIndicator"' in source

    def test_still_no_manual_raw_channel_picker_introduced(self):
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index('id="wwPhasorSvg"')]
        assert "wwPhasorChannelSelect" not in panel_html
        assert "raw-channel" not in panel_html.lower()

    def test_stale_discovery_response_is_discarded(self):
        """Every async step inside discovery re-checks the same
        epoch/workspaceId guard every other Analysis fetch already
        uses -- a workspace change mid-discovery must never populate the
        wrong workspace's own selector."""
        source = _source()
        body = _function_body(source, "async function wwAnalysisDiscoverUncoveredSources", "const WW_OVERCURRENT_MSG_SELECT_CONTEXT")
        assert body.count("epochAtStart !== ww.epoch || currentWorkspaceId() !== workspaceId") >= 3


class TestSharedAnalysisContextConsumers:
    """Per-analyzer CONSUMER behavior -- each analyzer's own reaction to
    the shared list/phase/discovering/fresh-discovery signals, and the
    future-analyzer-protection registration seam itself (owner
    instruction: prove analyzers obtain contexts from the shared
    lifecycle rather than inventing their own bootstrap, so a future
    `wwImpedanceLoadContexts()`-style regression is structurally
    impossible to miss)."""

    def test_both_analyzers_register_as_consumers_of_the_shared_lifecycle(self):
        source = _source()
        assert source.count("wwAnalysisRegisterContextConsumer({") == 2
        phasor_call = source[source.index("onContexts: wwPhasorOnAnalysisContexts"):]
        phasor_call = phasor_call[: phasor_call.index("});")]
        assert "onLifecyclePhase: wwPhasorOnAnalysisLifecyclePhase" in phasor_call
        assert "onDiscovering: wwPhasorOnAnalysisDiscovering" in phasor_call
        assert "onFreshContextsDiscovered: wwPhasorOnAnalysisFreshContextsDiscovered" in phasor_call
        overcurrent_call = source[source.index("onContexts: wwOvercurrentOnAnalysisContexts"):]
        overcurrent_call = overcurrent_call[: overcurrent_call.index("});")]
        assert "onLifecyclePhase: wwOvercurrentOnAnalysisLifecyclePhase" in overcurrent_call
        assert "onDiscovering: wwOvercurrentOnAnalysisDiscovering" in overcurrent_call
        assert "onFreshContextsDiscovered: wwOvercurrentOnAnalysisFreshContextsDiscovered" in overcurrent_call

    def test_neither_analyzer_defines_its_own_independent_bootstrap_entry_point(self):
        """The structural regression seam: neither analyzer may define a
        `wwXxxLoadContexts()`/`wwXxxDiscoverUncoveredSources()` of its
        own again -- both must route through the shared functions."""
        source = _source()
        assert "function wwPhasorLoadContexts" not in source
        assert "function wwOvercurrentLoadContexts" not in source
        assert "function wwPhasorDiscoverUncoveredSources" not in source
        assert "function wwOvercurrentDiscoverUncoveredSources" not in source
        assert "function wwPhasorFetchContexts" not in source
        assert "function wwOvercurrentFetchContexts" not in source

    def test_phasor_consumer_populates_selector_and_preserves_selection(self):
        source = _source()
        fn = _function_body(source, "function wwPhasorOnAnalysisContexts(contexts)", "function wwPhasorOnAnalysisLifecyclePhase")
        assert "wwPhasorState.contexts = contexts;" in fn
        assert "wwPhasorRenderContextOptions();" in fn
        assert "wwPhasorLoadForSelectedContext();" in fn
        assert "wwPhasorShowNoContextSelected();" in fn

    def test_overcurrent_consumer_populates_selector_and_preserves_selection(self):
        source = _source()
        fn = _function_body(source, "function wwOvercurrentOnAnalysisContexts(contexts)", "function wwOvercurrentOnAnalysisLifecyclePhase")
        assert "wwOvercurrentState.contexts = contexts;" in fn
        assert "wwOvercurrentRenderContextOptions();" in fn
        assert "wwOvercurrentLoadForSelectedContext();" in fn
        assert "wwOvercurrentShowNoContextSelected();" in fn

    def test_each_consumer_maps_every_lifecycle_phase_to_its_own_message(self):
        source = _source()
        phasor_fn = _function_body(source, "function wwPhasorOnAnalysisLifecyclePhase(phase)", "function wwPhasorOnAnalysisDiscovering")
        for phase, message in (
            ("WW_ANALYSIS_CONTEXT_PHASE_IDENTIFYING", "WW_PHASOR_MSG_IDENTIFYING_CONTEXTS"),
            ("WW_ANALYSIS_CONTEXT_PHASE_NO_SOURCES", "WW_PHASOR_MSG_NO_SOURCES"),
            ("WW_ANALYSIS_CONTEXT_PHASE_NO_SUGGESTIONS", "WW_PHASOR_MSG_NO_SUGGESTIONS"),
            ("WW_ANALYSIS_CONTEXT_PHASE_UNREACHABLE", "WW_PHASOR_MSG_BACKEND_UNREACHABLE"),
        ):
            assert phase in phasor_fn and message in phasor_fn

        overcurrent_fn = _function_body(source, "function wwOvercurrentOnAnalysisLifecyclePhase(phase)", "function wwOvercurrentOnAnalysisDiscovering")
        for phase, message in (
            ("WW_ANALYSIS_CONTEXT_PHASE_IDENTIFYING", "WW_OVERCURRENT_MSG_IDENTIFYING_CONTEXTS"),
            ("WW_ANALYSIS_CONTEXT_PHASE_NO_SOURCES", "WW_OVERCURRENT_MSG_NO_SOURCES"),
            ("WW_ANALYSIS_CONTEXT_PHASE_NO_SUGGESTIONS", "WW_OVERCURRENT_MSG_NO_SUGGESTIONS"),
            ("WW_ANALYSIS_CONTEXT_PHASE_UNREACHABLE", "WW_OVERCURRENT_MSG_BACKEND_UNREACHABLE"),
        ):
            assert phase in overcurrent_fn and message in overcurrent_fn

    def test_each_analyzer_auto_selects_only_when_it_has_no_selection_of_its_own(self):
        """Never steals a selection an analyzer already has -- each
        consumer's own fresh-discovery hook checks its OWN
        selectedContextId before acting, independent of any other
        analyzer's own selection state."""
        source = _source()
        phasor_fn = _function_body(source, "function wwPhasorOnAnalysisFreshContextsDiscovered()", "// Registered with the shared Analysis context lifecycle")
        assert "if (wwPhasorState.selectedContextId) return;" in phasor_fn
        assert "wwPhasorLoadForSelectedContext();" in phasor_fn

        overcurrent_fn = _function_body(source, "function wwOvercurrentOnAnalysisFreshContextsDiscovered()", "// Registered with the shared Analysis context lifecycle")
        assert "if (wwOvercurrentState.selectedContextId) return;" in overcurrent_fn
        assert "wwOvercurrentLoadForSelectedContext();" in overcurrent_fn


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


class TestPlaybackTimeControl:
    """Phasor Playback integration: the mounted Playback seek scrubber
    (the EXACT reusable control surface the Waveform Time Group toolbar
    also mounts) IS Phasor's own analysis time control now -- the old,
    separate Analysis Time number input + slider, and the Cursor-A-
    preferring default-time heuristic that used to feed it, are removed
    entirely."""

    def test_old_analysis_time_input_and_slider_removed(self):
        source = _source()
        assert 'id="wwPhasorTimeInput"' not in source
        assert 'id="wwPhasorTimeSlider"' not in source
        assert "wwPhasorComputeDefaultAnalysisTime" not in source
        assert "wwPhasorSyncTimeControls" not in source
        assert "wwPhasorOnAnalysisTimeInput" not in source

    def test_initial_claim_time_never_applies_to_the_restart_button_itself(self):
        """wwPhasorComputeInitialClaimTime() is a ONE-TIME convenience for
        a context's very FIRST claim only -- the mounted Restart BUTTON
        is wired directly to the bare, unchanged wwPlaybackRestart(),
        never followed by this heuristic, so pressing Restart always
        lands honestly at bounds.start (see the dedicated Restart-behavior
        test below)."""
        source = _source()
        wire_body = _function_body(source, "function wwPhasorMountPlaybackControls", "function wwPhasorLoadForSelectedContext")
        assert "wwPhasorComputeInitialClaimTime" not in wire_body

    def test_playback_composition_point_exists(self):
        source = _source()
        assert 'id="wwPhasorPlaybackPanel"' in source
        assert 'id="wwPhasorPlaybackMount"' in source

    def test_mounts_the_shared_reusable_playback_control_surface(self):
        """Reuses wwCreatePlaybackControlsHtml()/wwWirePlaybackControls()/
        wwSyncPlaybackControls() -- the EXACT same functions the Waveform
        Time Group toolbar mounts -- never a Phasor-specific duplicate."""
        source = _source()
        body = _function_body(source, "function wwPhasorMountPlaybackControls", "function wwPhasorLoadForSelectedContext")
        assert "wwCreatePlaybackControlsHtml()" in body
        assert "wwWirePlaybackControls(mountEl, groupId)" in body
        assert "wwSyncPlaybackControls(mountEl, groupId)" in body

    def test_analysis_time_driven_by_shared_playback_state(self):
        source = _source()
        body = _function_body(source, "function wwPhasorOnPlaybackTick", "function wwPhasorPlaybackDesiredTimeChanged")
        assert "wwPhasorState.analysisTime = currentTime;" in body

    def test_analysis_time_converted_to_source_time_at_api_boundary_only(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert "wwWorkspaceTimeToSourceTime(anchorDisplaySourceId, desiredTime)" in body

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

    def test_restart_claims_a_not_yet_active_group_never_a_buffered_start(self):
        """Owner instruction: Playback owns event time -- a freshly
        selected context claims its own resolved Time Group via the
        EXISTING, UNCHANGED wwPlaybackRestart() (lands at bounds.start),
        never a Phasor-specific "buffered default start" that would dodge
        an honest insufficient-history result."""
        source = _source()
        body = _function_body(source, "function wwPhasorLoadForSelectedContext", "function wwPhasorOnPlaybackTick")
        assert "wwPlaybackRestart(groupId);" in body

    def test_no_second_global_time_controller(self):
        """Phasor never builds its own timer/rAF loop -- the only
        `performance.now()` uses in this block measure elapsed REAL time
        to RATE-LIMIT an HTTP fetch (the throttle helpers), never to
        compute a time value itself. (A prose comment merely EXPLAINING
        "never a second requestAnimationFrame loop" is fine and expected;
        only an actual call is checked here.)"""
        source = _source()
        body = _phasor_block(source)
        assert "requestAnimationFrame(" not in body
        assert "setInterval(" not in body
        assert "new Date()" not in body
        throttle_body = _function_body(source, "function wwPhasorMaybeFetchForPlayback", "function wwPhasorSetUpdatingIndicator")
        assert "performance.now()" in throttle_body


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
        assert "const voltageScale = voltageMax > 0 ? wwPhasorState.frozenVoltageScale : 0;" in body
        assert "const currentScale = currentMax > 0 ? wwPhasorState.frozenCurrentScale : 0;" in body
        # Exactly one scale variable per family -- never per-vector.
        assert body.count("const voltageScale") == 1
        assert body.count("const currentScale") == 1

    def test_playback_stability_diagram_scale_frozen_from_first_result_never_shrinks(self):
        """Owner instruction: avoid constant rescaling during Playback,
        which can visually hide real magnitude movement -- each family's
        own scale is established once (from its first valid result) and
        only ever adjusted to EXPAND headroom (never silently shrunk back
        down merely because a later magnitude happens to be smaller)."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "wwPhasorState.frozenVoltageScale === null || voltageMax * wwPhasorState.frozenVoltageScale > plotRadius" in body
        assert "wwPhasorState.frozenCurrentScale === null || currentMax * wwPhasorState.frozenCurrentScale > plotRadius" in body

    def test_frozen_scale_released_on_restart_to_a_fresh_run(self):
        """Restart is a fresh "playback run" boundary -- landing exactly
        at the Time Group's own start releases the frozen scale so it
        re-establishes from the next result; natural end-of-range
        completion (a different landing time) does not."""
        source = _source()
        body = _function_body(source, "function wwPhasorOnPlaybackTick", "function wwPhasorPlaybackDesiredTimeChanged")
        assert "transitioned && playback.currentTime === playback.startTime && playback.state !== WW_PLAYBACK_STATE_PLAYING" in body
        assert "wwPhasorState.frozenVoltageScale = null;" in body
        assert "wwPhasorState.frozenCurrentScale = null;" in body

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


class TestChartGridAndAxisLabels:
    """Chart UX refinement (2026-09-12): a clearer coordinate system --
    thin Cartesian grid lines, a stronger central axis, and Real/
    Imaginary axis-direction labels -- layered around the EXISTING
    circular rings/vectors, never replacing them."""

    def test_grid_lines_render(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "ww-phasor-grid-line" in body

    def test_grid_is_sparse_matching_the_existing_ring_radii_not_dense_graph_paper(self):
        """Owner instruction: the grid must remain secondary to the
        vectors, never a dense graph-paper mesh -- confirmed by reusing
        the SAME three ring fractions, never a finer/independent grid
        resolution."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        grid_section = body[body.index("ww-phasor-grid-line") - 200 : body.index("ww-phasor-ring\" cx=")]
        assert "for (const frac of [1 / 3, 2 / 3, 1])" in grid_section

    def test_real_axis_label_renders(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert 'ww-phasor-axis-title' in body
        assert ">Real</text>" in body

    def test_imaginary_axis_label_renders(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert ">Imaginary</text>" in body

    def test_axis_titles_painted_after_vectors_so_they_are_never_hidden(self):
        """UAT follow-up (2026-09-12): the axis-title elements are pushed
        to `parts` AFTER the per-role vector loop -- SVG paints later
        elements on top, so 'Real'/'Imaginary' can never be obscured by a
        vector, reversing the original (grid-secondary) ordering after
        owner UAT reported the labels were not reliably visible."""
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        axis_title_idx = body.index("ww-phasor-axis-title")
        vector_loop_idx = body.index("for (const roleKey of WW_PHASOR_DIAGRAM_ROLE_ORDER)")
        assert axis_title_idx > vector_loop_idx

    def test_axis_titles_positioned_within_the_svg_viewbox_margin(self):
        """The SVG's own viewBox extends to +-122 (rings/axes/vectors stay
        within +-100) specifically to give the axis-title labels
        comfortable clearance from the edge -- never edge-clipped, the
        other half of the same owner UAT report."""
        source = _source()
        assert 'viewBox="-122 -122 244 244"' in source
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert 'x="112"' in body  # Real
        assert 'y="-112"' in body  # Imaginary

    def test_existing_rings_and_vectors_still_render(self):
        source = _source()
        body = _function_body(source, "function wwPhasorRenderDiagramSvg", "function wwPhasorVectorSvg")
        assert "ww-phasor-ring" in body
        assert "wwPhasorVectorSvg(x, y, wwPhasorRoleColor(roleKey), roleKey, isCurrent)" in body


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
        "all available roles visible" -- tracked via `lastLoadedContextId`
        so a mere page revisit (or an Analysis Time/Playback tick) with
        the SAME context selected never does this; wwPhasorOnPlaybackTick()
        (the function that drives every Playback-induced time change)
        never touches `visibleRoles` at all."""
        source = _source()
        load_context_body = _function_body(source, "function wwPhasorLoadForSelectedContext", "function wwPhasorOnPlaybackTick")
        assert "const isNewContext = contextId !== wwPhasorState.lastLoadedContextId;" in load_context_body
        assert "if (isNewContext) {" in load_context_body
        assert "wwPhasorState.visibleRoles = {};" in load_context_body
        tick_body = _function_body(source, "function wwPhasorOnPlaybackTick", "function wwPhasorPlaybackDesiredTimeChanged")
        assert "wwPhasorState.visibleRoles" not in tick_body

    def test_default_visibility_never_overwrites_an_existing_preference(self):
        source = _source()
        body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert '!(roleKey in wwPhasorState.visibleRoles)' in body

    def test_missing_or_ambiguous_roles_have_no_toggle_control(self):
        source = _source()
        body = _function_body(source, "function wwPhasorValueRowHtml", "function wwPhasorRenderValuesList")
        assert 'role.status !== "available"' in body


class TestPlaybackIntegration:
    """Phasor Playback integration: Phasor consumes the ONE shared,
    reusable `wwPlayback` controller (unchanged) -- it never builds a
    second controller, timer, or independent time field. See
    TestPlaybackTimeControl above for the time-control-specific checks."""

    def test_playback_controller_functions_referenced(self):
        """Functional coupling to the shared controller IS now expected
        (the opposite of the pre-Playback slice) -- Phasor calls the
        real, unchanged wwPlayback* functions, never a copy of them."""
        source = _source()
        body = _phasor_block(source)
        assert "wwPlaybackOnTick(" in body
        assert "wwPlaybackRestart(" in body
        assert "wwPlayback.activeTimeGroupId" in body
        assert "wwPlayback.currentTime" in body
        # The tick-subscriber callback's own `playback` PARAMETER *is*
        # `wwPlayback` itself (passed by wwPlaybackNotifyTick(currentTime,
        # wwPlayback)) -- referenced as `playback.state` inside that one
        # callback, never re-declared or copied.
        assert "playback.state" in body

    def test_play_pause_speed_seek_controls_are_the_mounted_playback_surface(self):
        """The static HTML template carries only an EMPTY composition-
        point container (`#wwPhasorPlaybackMount`) -- the actual Play/
        Pause/Speed/Seek controls are populated entirely at runtime by
        wwPhasorMountPlaybackControls() calling the shared
        wwCreatePlaybackControlsHtml() factory, never hand-rolled static
        markup of Phasor's own."""
        source = _source()
        panel_html = source[source.index('id="wwPhasorPanel"'):source.index("</section>\n                    </div>\n                </div>\n            </section>", source.index('id="wwPhasorPanel"'))]
        assert 'id="wwPhasorPlaybackMount"></div>' in panel_html
        assert "ww-tg-playback" not in panel_html  # only ever injected dynamically, never static
        assert 'class="secondary ww-tg-playback-restart-btn"' not in panel_html

    def test_no_duplicate_playback_controller_declared(self):
        """Exactly one wwPlayback state object exists in the whole file --
        Phasor never declares its own second copy."""
        source = _source()
        assert source.count("const wwPlayback = {") == 1

    def test_no_phasor_specific_timer_or_clock(self):
        source = _source()
        body = _phasor_block(source)
        assert "setInterval(" not in body
        assert "requestAnimationFrame(" not in body

    def test_aggregated_endpoint_used_never_role_per_request_fan_out(self):
        source = _source()
        body = _phasor_block(source)
        assert body.count('"/phasor-diagram?"') == 1
        assert "/phasor?" not in body

    def test_throttle_respects_one_request_in_flight_plus_latest_desired_time(self):
        """"Never allow Playback to produce a growing queue of Phasor HTTP
        requests" -- one request in flight, plus the LATEST desired time;
        a completed fetch re-checks and re-fetches immediately if the
        desired time has since moved on."""
        source = _source()
        body = _function_body(source, "function wwPhasorMaybeFetchForPlayback", "function wwPhasorSetUpdatingIndicator")
        assert "if (wwPhasorPlaybackFetchInFlight) return;" in body
        assert "elapsedMs < WW_PHASOR_PLAYBACK_THROTTLE_MS" in body
        request_body = _function_body(source, "async function wwPhasorRequestDiagram", "function wwPhasorWholeResultBlockedMessage")
        assert "wwPhasorMaybeFetchForPlayback();" in request_body

    def test_exact_convergence_on_settle_transitions(self):
        """Pause/Restart/a seek commit landing in "paused"/Playback
        reaching its own endTime/a live seek `input` event while already
        paused -- every one of these is NOT "playing" and must converge
        to the EXACT settled time, never a throttled approximation.
        Deliberately keyed on `playback.state`, never on the transition
        signature alone -- a seek while ALREADY paused never changes that
        signature (paused -> paused), and ticks only arrive from the rAF
        loop while actually playing, so gating this on "did the state
        STRING change" would leave a paused seek's own desired time stuck
        unfetched forever with nothing left to retry it."""
        source = _source()
        body = _function_body(source, "function wwPhasorOnPlaybackTick", "function wwPhasorPlaybackDesiredTimeChanged")
        assert "if (playback.state === WW_PLAYBACK_STATE_PLAYING) {" in body
        assert "wwPhasorMaybeFetchForPlayback();" in body
        assert "wwPhasorRequestExactPlaybackFetch();" in body

    def test_no_second_analysis_time_field_reintroduced(self):
        source = _source()
        body = _phasor_block(source)
        assert 'type="number"' not in body

    def test_no_quantity_mode_or_combined_mode_selector_reintroduced(self):
        """The bay-centric redesign already made a Quantity/Mode selector
        obsolete (every role is always requested together) -- Playback
        integration must not reintroduce one, nor a NEW "combined mode"
        selector, since combined display is now inherent to every bay."""
        source = _source()
        body = _phasor_block(source)
        assert "wwPhasorQuantitySelect" not in body
        assert "wwPhasorModeSelect" not in body
        assert "combined_mode" not in body.lower()
        assert "combinedMode" not in body

    def test_no_per_unit_or_plotly(self):
        source = _source()
        body = _phasor_block(source)
        assert "unit_mode" not in body
        assert "per_unit" not in body.lower()
        assert "Plotly" not in body

    def test_composition_point_comment_updated_for_playback(self):
        source = _source()
        assert "Phasor Playback integration" in source


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


class TestAnalysisShellVisualPolish:
    """Visual polish pass (2026-09-12): reusable Analysis shell layout,
    compact typography, restructured context bar/Playback ribbon. Behavior
    is unchanged -- see the classes above for that coverage; these tests
    guard the structural/typography invariants the polish task itself
    calls out explicitly."""

    def test_page_title_and_description_present(self):
        source = _source()
        assert "<h2>Analysis</h2>" in source
        assert "Engineering analyzers built on automatic Engineering Context resolution." in source

    def test_analyzer_nav_item_typography_is_compact(self):
        source = _source()
        body = _function_body(source, ".ww-analysis-type-item {", ".ww-analysis-content {")
        assert "font-size: 0.75rem;" in body

    def test_context_bar_label_and_control_row_are_structurally_separate(self):
        """Bay/Engineering Context label sits on its own line; the
        selector and its status badge sit together on one aligned row
        below it -- the badge no longer floats next to the label text."""
        source = _source()
        body = _function_body(source, 'class="ww-phasor-controls-row"', "</section>")
        assert 'class="ww-phasor-field-label"' in body
        assert 'class="ww-phasor-field-control-row"' in body
        label_idx = body.index('class="ww-phasor-field-label"')
        badge_idx = body.index('id="wwPhasorContextBadge"')
        select_idx = body.index('id="wwPhasorContextSelect"')
        assert label_idx < select_idx < badge_idx

    def test_playback_ribbon_uses_shared_analysis_mount_styling(self):
        """The ribbon restyle lives on the shared Analysis Playback seam,
        so Phasor and every later analyzer mounting the reusable factory
        inherit the same compact one-row control surface."""
        source = _source()
        css_body = _function_body(source, ".ww-analysis-playback-panel {", ".ww-phasor-status-row {")
        assert "ww-analysis-playback-panel" in source
        assert "ww-analysis-playback-mount" in source
        assert "display: contents;" in css_body
        assert ".ww-analysis-playback-mount .ww-tg-playback-seek-row" in css_body
        assert ".ww-analysis-playback-mount .ww-tg-playback-time-readout" in css_body
        markup_fn = _function_body(source, "function wwCreatePlaybackControlsHtml()", "function wwPlaybackState")
        for option in ('value="0.05"', 'value="0.1"', 'value="1" selected'):
            assert option in markup_fn

    def test_no_polar_view_or_visualization_mode_selector(self):
        """Only one meaningful visualization mode exists today -- a mode
        selector is explicitly deferred until a genuine second view
        exists (owner instruction)."""
        source = _source()
        body = _phasor_block(source)
        assert "Polar View" not in body
        assert "wwPhasorViewMode" not in body

    def test_values_panel_uses_aligned_magnitude_and_angle_columns(self):
        source = _source()
        body = _function_body(source, "function wwPhasorValueRowHtml", "function wwPhasorRenderValuesList")
        assert "ww-phasor-value-magnitude" in body
        assert "ww-phasor-value-angle" in body

    def test_normal_analysis_ui_text_stays_at_or_under_0_75rem(self):
        """Explicit audit of the Analysis-page-specific selectors this
        polish pass touched -- every one caps at 0.75rem (owner
        instruction), excluding only the page title/description (the
        larger app-wide heading/subtitle scale, asserted separately
        above)."""
        source = _source()
        css_body = _function_body(source, ".ww-analysis-shell {", "</style>")
        import re

        analysis_selectors = (
            ".ww-analysis-type-item",
            ".ww-phasor-panel h3",
            ".ww-phasor-field",
            ".ww-phasor-field select",
            ".ww-phasor-status-row",
            ".ww-phasor-role-status-text",
            ".ww-phasor-value-row",
            ".ww-phasor-warnings",
            ".ww-phasor-scale-note",
            ".ww-phasor-discovering-indicator",
        )
        for selector in analysis_selectors:
            start = css_body.index(selector + " {")
            end = css_body.index("}", start)
            block = css_body[start:end]
            sizes = [float(m) for m in re.findall(r"font-size:\s*([\d.]+)rem", block)]
            assert sizes, f"{selector} declares no rem font-size"
            for size in sizes:
                assert size <= 0.75, f"{selector} font-size {size}rem exceeds the 0.75rem Analysis-workspace cap"
