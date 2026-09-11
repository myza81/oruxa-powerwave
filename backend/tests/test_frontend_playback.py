"""Static structural regression checks for Event Playback (frontend/
index.html) -- Slice 1 (Core Playback Engine) and Slice 2 (Essential
Playback Controls: fixed speed + seek).

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses -- this repo has no
browser/DOM test runner for the single-file frontend. Real timer/rAF/
Plotly-overlay BEHAVIOR is covered separately by
`browser-tests/playback.spec.js` (Playwright, real browser) -- these
tests only guard structural invariants a source-text assertion CAN
meaningfully verify (ordering, presence, absence of coupling to Cursor
A/B or to a backend endpoint, the shape of the speed/seek re-anchoring
algorithms).

Playback is frontend/session state only (no backend API changes in
either slice) -- every test below is source-only; none touches the
backend.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
BACKEND_API_DIR = Path(__file__).resolve().parents[2] / "backend" / "app" / "api" / "v1"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class TestPlaybackIsNotATopLevelPage:
    """Owner UX correction (post-Slice-1-UAT, supersedes the original
    Slice 1 "Playback is a top-level page" design, see DECISIONS.md
    DEC-085's own revision note): Playback is a shared, reusable
    workspace capability, never a standalone application page/menu
    destination. No dedicated Playback menu item, page section, page-
    routing case, or page-status renderer may exist anywhere."""

    def test_no_dedicated_playback_nav_button_exists(self):
        source = _source()
        assert 'id="mainNavPlaybackBtn"' not in source

    def test_no_dedicated_playback_page_section_exists(self):
        source = _source()
        assert 'id="pagePlayback"' not in source
        assert 'id="wwPlaybackPageStatus"' not in source

    def test_shellSetCurrentPage_has_no_playback_case(self):
        source = _source()
        assert 'page === "playback"' not in source
        assert 'page !== "playback"' not in source
        assert 'shellSetCurrentPage("playback")' not in source
        assert "function wwRenderPlaybackPage" not in source

    def test_analysis_menu_exists_but_is_not_a_playback_destination(self):
        """Superseded by Phasor Analysis Slice 2 (2026-09-11): the task
        that originally wrote this test explicitly deferred creating the
        Analysis menu ("do not create it prematurely"); Phasor Analysis
        Slice 2 is the task that deliberately creates it, as the FIRST
        real `Analysis` consumer. The invariant this class actually cares
        about survives unchanged: Playback itself still has no dedicated
        page/nav destination of its own -- the Analysis menu exists for
        Phasor, never for Playback.

        Further superseded by the Phasor UAT fix (2026-09-11): the nav
        item's own visible label/tooltip changed from "Analysis" to
        "Phasor Diagram" (too generic with only one analyzer
        implemented) -- the destination's `id` (`mainNavAnalysisBtn`)
        and its underlying page (`#pageAnalysis`, `<h2>Analysis</h2>`)
        are unchanged; see test_frontend_phasor_analysis.py's own
        `TestAnalysisMenuExists` for the full, current assertions on
        the nav button's exact text."""
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        assert 'id="mainNavAnalysisBtn"' in nav_list
        assert '<span class="shell-nav-label">Phasor Diagram</span>' in nav_list
        assert 'id="mainNavPlaybackBtn"' not in nav_list
        assert '<span class="shell-nav-label">Playback</span>' not in nav_list

    def test_analysis_follows_calculated_channels_before_tools_placeholder(self):
        """Confirms the nav list's current real shape: Calculated
        Channels, then the new Analysis destination (Phasor Analysis
        Slice 2), then the still-disabled Tools placeholder -- nothing
        Playback-specific spliced in anywhere."""
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        cc_index = nav_list.index('id="mainNavCalculatedChannelsBtn"')
        tools_index = nav_list.index('title="Tools -- coming soon"')
        between = nav_list[cc_index:tools_index]
        # Exactly two shell-nav-items (Calculated Channels itself, then
        # Analysis) between Calculated Channels' own start and the Tools
        # placeholder -- nothing Playback-specific spliced in.
        assert between.count('class="shell-nav-item"') == 2
        assert 'id="mainNavAnalysisBtn"' in between


class TestPlaybackIsAReusableEmbeddableCapability:
    """The architecture-correction's own positive requirement: a shared,
    container-parameterized control surface -- markup/wiring/sync all
    live in ONE place, never duplicated per mount point, never assuming
    "the Time Group canvas" internally."""

    def test_reusable_markup_factory_exists_and_is_called_once_per_canvas(self):
        source = _source()
        assert "function wwCreatePlaybackControlsHtml()" in source
        toolbar_fn = _function_body(
            source, "function wwCreateTimeGroupCanvasDom(groupId)", "function wwEnsureTimeGroupCanvasDom"
        )
        assert toolbar_fn.count("const playbackControlsHtml = wwCreatePlaybackControlsHtml();") == 1
        assert "playbackControlsHtml.transportHtml" in toolbar_fn
        assert "playbackControlsHtml.seekRowHtml" in toolbar_fn
        # The markup itself (button/select/input tags) no longer lives
        # inline in the canvas template -- only the factory call + its
        # two returned-fragment references do.
        assert '<button type="button" class="secondary ww-tg-playback-restart-btn"' not in toolbar_fn

    def test_wire_sync_and_tick_functions_are_container_parameterized(self):
        """Never an internal wwTimeGroupCanvasEl(groupId) lookup inside
        the reusable functions themselves -- only their Time-Group-
        specific thin wrapper is allowed to do that resolution."""
        source = _source()
        for signature, next_signature in [
            ("function wwWirePlaybackControls(containerEl, groupId)", "function wwSyncPlaybackControls"),
            ("function wwSyncPlaybackControls(containerEl, groupId)", "function wwUpdatePlaybackControlsTick"),
            ("function wwUpdatePlaybackControlsTick(containerEl, groupId)", "function wwPlaybackUpdateTimeReadout"),
        ]:
            fn = _function_body(source, signature, next_signature)
            assert "wwTimeGroupCanvasEl(" not in fn, f"{signature} must not resolve its own container"

    def test_waveform_toolbar_delegates_to_the_reusable_wiring_function(self):
        source = _source()
        wiring_fn = _function_body(
            source, "function wwWireTimeGroupToolbar(canvasEl, groupId)", "function wwWireSplitMenuOutsideClickDismissal"
        )
        assert "wwWirePlaybackControls(canvasEl, groupId);" in wiring_fn
        # No duplicated inline listener wiring left behind.
        assert 'querySelector(".ww-tg-playback-restart-btn")' not in wiring_fn
        assert 'querySelector(".ww-tg-playback-speed-select")' not in wiring_fn

    def test_time_group_specific_sync_and_tick_are_thin_delegating_wrappers(self):
        source = _source()
        sync_fn = _function_body(source, "function wwPlaybackSyncToolbarForGroup(groupId)", "function wwPlaybackSetSpeed")
        assert "wwSyncPlaybackControls(canvasEl, groupId);" in sync_fn
        # No re-implemented play/pause-label or readout/slider logic here.
        assert "textContent = isPlaying" not in sync_fn

        tick_fn = _function_body(source, "function wwPlaybackRenderTick()", "function wwPlaybackPlay")
        assert "wwUpdatePlaybackControlsTick(canvasEl" in tick_fn

    def test_no_duplicate_timing_or_seek_logic_outside_the_one_engine(self):
        """The task's own explicit "Do NOT duplicate: timing logic / rAF
        loops / seek logic / speed logic / playback state / range
        calculation" -- confirmed by there being exactly ONE definition
        of each core engine primitive, and exactly one place a seek
        slider's own `input`/`change` listeners are attached (inside the
        one reusable wiring function)."""
        source = _source()
        assert source.count("function wwPlaybackTick(nowMs)") == 1
        assert source.count("function wwPlaybackHandleSeekInput(groupId, rawTime)") == 1
        assert source.count("wwPlaybackHandleSeekInput(groupId, parseFloat(seekSlider.value))") == 1
        assert source.count("wwPlaybackHandleSeekCommit(groupId, parseFloat(seekSlider.value))") == 1


class TestTimeGroupToolbarControls:
    """Everyday Play/Pause/Restart/Speed/Seek controls live on each Time
    Group's own waveform toolbar -- markup owned by
    wwCreatePlaybackControlsHtml(), wiring owned by
    wwWirePlaybackControls(), both called (never re-implemented) from
    wwCreateTimeGroupCanvasDom()/wwWireTimeGroupToolbar() -- the same
    established per-canvas pattern Reset Time View/Autoscale Y/Cursor
    mode already use for their OWN controls."""

    def test_reusable_markup_includes_every_control(self):
        source = _source()
        markup_fn = _function_body(source, "function wwCreatePlaybackControlsHtml()", "function wwPlaybackState")
        assert "ww-tg-playback-restart-btn" in markup_fn
        assert "ww-tg-playback-play-btn" in markup_fn
        assert "ww-tg-playback-time-readout" in markup_fn
        assert "ww-tg-playback-speed-select" in markup_fn
        assert "ww-tg-playback-seek-slider" in markup_fn
        # Never free-entry speed -- a <select>, never a text/number input.
        assert '<select class="ww-tg-playback-speed-select"' in markup_fn
        assert 'type="number"' not in markup_fn

    def test_reusable_wiring_binds_every_control(self):
        source = _source()
        wiring_fn = _function_body(
            source, "function wwWirePlaybackControls(containerEl, groupId)", "function wwSyncPlaybackControls"
        )
        assert "wwPlaybackRestart(groupId)" in wiring_fn
        assert "wwPlaybackHandlePlayPauseClick(groupId)" in wiring_fn
        assert "wwPlaybackHandleSpeedChange(speedSelect)" in wiring_fn
        assert "wwPlaybackHandleSeekInput(groupId" in wiring_fn
        assert "wwPlaybackHandleSeekCommit(groupId" in wiring_fn


class TestPlaybackCursorIsSeparateFromCursorAB:
    """Owner's explicit boundary: Playback Cursor must NOT reuse Cursor A/
    B -- separate DOM identity, separate state, never a read/write of
    ww.timeGroupCursorState."""

    def test_dedicated_overlay_dom_exists_and_differs_from_cursor_ab(self):
        source = _source()
        toolbar_fn = _function_body(
            source, "function wwCreateTimeGroupCanvasDom(groupId)", "function wwEnsureTimeGroupCanvasDom"
        )
        assert "ww-tg-playback-cursor-overlay" in toolbar_fn
        assert "ww-tg-playback-cursor-line" in toolbar_fn
        # Structurally a SIBLING of, never the same element as, Cursor A/B's
        # own overlay.
        assert '<div class="ww-tg-cursor-overlay" hidden></div>' in toolbar_fn
        assert 'class="ww-tg-playback-cursor-overlay"' in toolbar_fn

    def test_playback_cursor_update_never_touches_cursor_ab_state(self):
        source = _source()
        fn = _function_body(
            source, "function wwUpdatePlaybackCursorOverlay(groupId, time)", "function wwHidePlaybackCursorOverlay"
        )
        assert "wwTimeGroupCursorState" not in fn
        assert "ww.timeGroupCursorState" not in fn

    def test_playback_engine_never_writes_cursor_ab_state(self):
        source = _source()
        engine = _function_body(
            source,
            "const WW_PLAYBACK_STATE_STOPPED",
            "function wwStickyRulerElapsedUnit",
        )
        assert "ww.timeGroupCursorState.set" not in engine
        assert "ww.timeGroupCursorState.get" not in engine
        assert "cursors.a.time =" not in engine
        assert "cursors.b.time =" not in engine

    def test_playback_cursor_reuses_cursor_ab_pixel_conversion_primitives(self):
        """Reuse the MATH (wwCursorPlotMetrics/wwCursorTimeToPixelX), not
        the STATE -- confirms the audit's own "share the primitives,
        never the DOM/state" recommendation was actually followed."""
        source = _source()
        fn = _function_body(
            source, "function wwUpdatePlaybackCursorOverlay(groupId, time)", "function wwHidePlaybackCursorOverlay"
        )
        assert "wwCursorPlotMetrics(groupId)" in fn
        assert "wwCursorTimeToPixelX(groupId, time)" in fn


class TestWorkspaceClearResetsPlayback:
    def test_wwClearWorkspace_calls_wwPlaybackReset(self):
        source = _source()
        fn = _function_body(
            source, "function wwClearWorkspace(options)", "function wwPlaybackState"
        )
        assert "wwPlaybackReset();" in fn

    def test_wwPlaybackReset_cancels_the_rAF_loop_and_clears_active_group(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackReset()", "function wwPlaybackTick")
        assert "cancelAnimationFrame" in fn
        assert "wwPlayback.activeTimeGroupId = null;" in fn
        assert "wwPlayback.generation += 1;" in fn

    def test_time_group_disappearing_also_resets_playback(self):
        source = _source()
        fn = _function_body(
            source, "function wwSyncTimeGroupCanvases()", "// Only a REASSIGNMENT"
        )
        assert "wwPlayback.activeTimeGroupId" in fn
        assert "wwPlaybackReset()" in fn


class TestOneActiveTimeGroupAtATime:
    """Owner decision: only ONE Time Group plays at a time, driven by ONE
    shared Playback Controller / one requestAnimationFrame loop -- never
    a per-group Map, never two simultaneous loops."""

    def test_wwPlayback_state_is_a_flat_single_instance_object(self):
        source = _source()
        state_obj = _function_body(source, "const wwPlayback = {", "};")
        assert "activeTimeGroupId" in state_obj
        assert "new Map()" not in state_obj
        assert "timeGroupPlaybackState" not in source

    def test_play_cancels_any_existing_rAF_before_scheduling_a_new_one(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        assert "cancelAnimationFrame(wwPlayback.rafId)" in fn
        assert "requestAnimationFrame(wwPlaybackTick)" in fn

    def test_play_hides_the_previous_groups_own_playback_cursor_on_switch(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        assert "wwHidePlaybackCursorOverlay(previousGroupId)" in fn


class TestTimingUsesWallClockAnchorNotAssumedFrameInterval:
    def test_tick_recomputes_from_performance_now_anchor(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackTick(nowMs)", "function wwPlaybackRenderTick")
        assert "wwPlayback.wallClockAnchorMs" in fn
        assert "wwPlayback.recordingTimeAnchor" in fn
        # Milliseconds -> seconds conversion must be present (performance.now() is ms).
        assert "/ 1000" in fn
        # Must NOT increment by an assumed per-frame delta.
        assert "currentTime +=" not in fn
        assert "currentTime = currentTime +" not in fn

    def test_play_anchors_with_performance_now(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        assert "performance.now()" in fn

    def test_play_never_resets_speed(self):
        """Slice 2 supersedes Slice 1's original 'speed is fixed at 1x'
        rule -- Play must NOT reset `wwPlayback.speed`, since Slice 2
        requires it to persist across Play/Pause/Restart/seek (only a
        whole-workspace reset touches it -- see TestSpeedControl below)."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        assert "wwPlayback.speed = 1;" not in fn
        assert "wwPlayback.speed =" not in fn


class TestCanonicalTimeCoordinateIsWorkspaceTime:
    def test_readout_reuses_the_existing_cursor_time_formatter(self):
        """Never a second/independent clock -- reuses
        wwFormatCursorPointTime(), the SAME formatter Cursor A/B/Δt
        already use, so display automatically follows whatever Time
        Mode/t0 is active without any new conversion logic."""
        source = _source()
        fn = _function_body(
            source, "function wwPlaybackUpdateTimeReadout(containerEl, groupId)", "function wwPlaybackSyncToolbarForGroup"
        )
        assert "wwFormatCursorPointTime(wwPlayback.currentTime, groupId)" in fn

    def test_play_and_restart_source_bounds_from_the_existing_time_group_bounds_function(self):
        source = _source()
        play_fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        restart_fn = _function_body(source, "function wwPlaybackRestart(groupId)", "function wwPlaybackSyncToolbarForGroup")
        assert "wwDeriveTimeGroupBounds(groupId)" in play_fn
        assert "wwDeriveTimeGroupBounds(groupId)" in restart_fn


class TestDigitalStateIsResolvedLocally:
    def test_digital_state_lookup_never_issues_a_fetch(self):
        source = _source()
        fn = _function_body(
            source, "function wwPlaybackDigitalStateAtTime(entry, time)", "function wwPlaybackDigitalStateFor"
        )
        assert "fetch(" not in fn
        fn2 = _function_body(
            source, "function wwPlaybackDigitalStateFor(sourceId, channelName, time)", "function wwStickyRulerElapsedUnit"
        )
        assert "fetch(" not in fn2
        assert "ww.digitalDisplayed.get" in fn2


class TestNoBackendPlaybackEndpoint:
    """Playback is frontend/session state -- Slice 1 must not call, or
    expect, any backend Playback endpoint."""

    def test_frontend_playback_code_never_fetches_a_playback_endpoint(self):
        source = _source()
        engine = _function_body(
            source, "const WW_PLAYBACK_STATE_STOPPED", "function wwStickyRulerElapsedUnit"
        )
        assert "/playback" not in engine
        assert "fetch(" not in engine

    def test_no_playback_api_router_exists_in_the_backend(self):
        assert BACKEND_API_DIR.is_dir()
        for path in BACKEND_API_DIR.glob("*.py"):
            assert "playback" not in path.name.lower(), f"Unexpected backend Playback API file: {path.name}"

    def test_no_backend_api_file_defines_a_playback_route(self):
        for path in BACKEND_API_DIR.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            assert "/playback" not in text, f"Unexpected /playback route reference in {path.name}"


class TestPlaybackConsumerSeam:
    """A minimal callback-list seam, never a generic event-bus/third-party
    dependency -- future analysis overlays subscribe without knowing how
    playback timing itself works."""

    def test_on_tick_returns_an_unsubscribe_function(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackOnTick(callback)", "function wwPlaybackNotifyTick")
        assert "return function wwPlaybackUnsubscribe()" in fn
        assert "splice" in fn

    def test_no_new_event_bus_dependency_introduced(self):
        source = _source()
        engine = _function_body(
            source, "const WW_PLAYBACK_STATE_STOPPED", "function wwStickyRulerElapsedUnit"
        )
        assert "EventEmitter" not in engine
        assert "new Event(" not in engine
        assert "CustomEvent" not in engine

    def test_state_accessor_and_tick_notifier_both_exist(self):
        source = _source()
        assert "function wwPlaybackState()" in source
        assert "function wwPlaybackOnTick(callback)" in source
        assert "function wwPlaybackNotifyTick()" in source


# ======================================================================
# Slice 2: Essential Playback Controls (fixed speed + seek)
# ======================================================================


class TestSpeedControl:
    """Test 1/2 of the task's own focused-coverage list: the supported
    speed set is EXACTLY 0.25/0.5/1/2/4, default 1x, never free entry."""

    def test_supported_speed_set_is_exactly_the_required_five_values(self):
        source = _source()
        assert "const WW_PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 4];" in source

    def test_default_speed_constant_is_1x(self):
        source = _source()
        assert "const WW_PLAYBACK_DEFAULT_SPEED = 1;" in source
        # The controller's own initial value uses that constant, not a
        # second hardcoded literal.
        state_obj = _function_body(source, "const wwPlayback = {", "};")
        assert "speed: WW_PLAYBACK_DEFAULT_SPEED," in state_obj

    def test_speed_selector_is_a_select_not_free_entry(self):
        source = _source()
        markup_fn = _function_body(source, "function wwCreatePlaybackControlsHtml()", "function wwPlaybackState")
        select_html = _function_body(markup_fn, '<select class="ww-tg-playback-speed-select"', "</select>")
        for option in ('value="0.25"', 'value="0.5"', 'value="1" selected', 'value="2"', 'value="4"'):
            assert option in select_html
        # No free-entry alternative (a text/number input) anywhere nearby.
        assert 'type="number"' not in markup_fn
        assert 'class="ww-tg-playback-speed-input"' not in markup_fn

    def test_set_speed_rejects_unsupported_values(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackSetSpeed(newSpeed)", "function wwPlaybackHandleSpeedChange")
        assert "WW_PLAYBACK_SPEEDS.includes(newSpeed)" in fn
        assert "WW_PLAYBACK_DEFAULT_SPEED" in fn


class TestSpeedChangeReanchoring:
    """Tests 3-5 of the task's own focused-coverage list: no jump, no
    second rAF loop, and a paused speed change only updates the stored
    value (never touches anchors)."""

    def test_speed_change_while_playing_reanchors_from_current_time_not_a_recompute(self):
        """'No jump' -- the new anchor is read directly from
        wwPlayback.currentTime (already correct every frame via the
        existing tick loop), never a second/independent time calculation
        that could disagree with it."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackSetSpeed(newSpeed)", "function wwPlaybackHandleSpeedChange")
        playing_branch = _function_body(
            fn, "if (wwPlayback.state === WW_PLAYBACK_STATE_PLAYING) {", "wwPlayback.speed = speed;"
        )
        assert "wwPlayback.recordingTimeAnchor = wwPlayback.currentTime;" in playing_branch
        assert "wwPlayback.wallClockAnchorMs = performance.now();" in playing_branch

    def test_speed_change_never_creates_a_second_rAF_loop(self):
        """The existing rAF chain is left running untouched -- no
        cancelAnimationFrame/requestAnimationFrame call anywhere in
        wwPlaybackSetSpeed() itself."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackSetSpeed(newSpeed)", "function wwPlaybackHandleSpeedChange")
        assert "requestAnimationFrame" not in fn
        assert "cancelAnimationFrame" not in fn

    def test_paused_speed_change_only_updates_the_stored_value(self):
        """No anchor mutation outside the `state === PLAYING` guard --
        confirms a paused/stopped speed change is a pure value update,
        applied automatically whenever playback next resumes (via
        wwPlaybackPlay()'s own existing resume logic), never eagerly
        re-anchoring a non-running clock."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackSetSpeed(newSpeed)", "function wwPlaybackHandleSpeedChange")
        # Exactly one occurrence of each anchor assignment, both inside
        # the PLAYING-only guard already verified above -- i.e. neither
        # anchor is touched a second time outside that guard.
        assert fn.count("wwPlayback.recordingTimeAnchor =") == 1
        assert fn.count("wwPlayback.wallClockAnchorMs = performance.now();") == 1

    def test_speed_persists_across_play_pause_restart(self):
        """Play/Pause/Restart must never reset `speed` -- only a whole-
        workspace reset does (see TestWorkspaceResetSpeedDefault)."""
        source = _source()
        for signature, next_signature in [
            ("function wwPlaybackPlay(groupId)", "function wwPlaybackPause"),
            ("function wwPlaybackPause()", "function wwPlaybackHandlePlayPauseClick"),
            ("function wwPlaybackRestart(groupId)", "function wwPlaybackSyncToolbarForGroup"),
        ]:
            fn = _function_body(source, signature, next_signature)
            assert "wwPlayback.speed =" not in fn, f"{signature} must not touch wwPlayback.speed"


class TestSeekBehavior:
    """Tests 6-8 of the task's own focused-coverage list: seek while
    stopped/paused/playing, and Restart returns the slider/cursor/
    currentTime to the range start."""

    def test_seek_input_suspends_the_clock_only_on_the_first_event_of_a_gesture(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackHandleSeekInput(groupId, rawTime)", "function wwPlaybackHandleSeekCommit")
        assert "if (!wwPlaybackSeekDragging) {" in fn
        assert "cancelAnimationFrame(wwPlayback.rafId);" in fn
        # Never re-anchors mid-drag -- that only happens on commit.
        assert "wwPlayback.recordingTimeAnchor = clamped;" not in fn
        assert "requestAnimationFrame(wwPlaybackTick)" not in fn

    def test_seek_input_never_fabricates_or_touches_engineering_data(self):
        """Slice 2's own explicit boundary: seeking selects a TIME only --
        never an analog/interpolated value, never a backend call."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackHandleSeekInput(groupId, rawTime)", "function wwPlaybackHandleSeekCommit")
        assert "fetch(" not in fn
        for token in ("interpolat", "Va", "Vb", "Vc", "Ia", "Ib", "Ic", "impedance", "phasor"):
            assert token not in fn

    def test_seek_commit_resumes_playing_only_if_it_was_playing_before_the_gesture(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackHandleSeekCommit(groupId, rawTime)", "function wwPlaybackSyncSeekSliderBounds")
        assert "const wasPlaying = wwPlaybackSeekWasPlaying;" in fn
        assert "if (wasPlaying) {" in fn
        assert "wwPlayback.state = WW_PLAYBACK_STATE_PLAYING;" in fn
        assert "wwPlayback.state = WW_PLAYBACK_STATE_PAUSED;" in fn
        assert "if (wasPlaying) {\n                wwPlayback.rafId = requestAnimationFrame(wwPlaybackTick);" in fn

    def test_seek_never_mutates_cursor_ab_state(self):
        source = _source()
        input_fn = _function_body(source, "function wwPlaybackHandleSeekInput(groupId, rawTime)", "function wwPlaybackHandleSeekCommit")
        commit_fn = _function_body(source, "function wwPlaybackHandleSeekCommit(groupId, rawTime)", "function wwPlaybackSyncSeekSliderBounds")
        for fn in (input_fn, commit_fn):
            assert "ww.timeGroupCursorState" not in fn

    def test_seek_slider_wired_with_input_and_change_events(self):
        source = _source()
        wiring_fn = _function_body(
            source, "function wwWirePlaybackControls(containerEl, groupId)", "function wwSyncPlaybackControls"
        )
        assert '.addEventListener("input", ()' in wiring_fn
        assert '.addEventListener("change", ()' in wiring_fn

    def test_restart_resets_current_time_to_start_and_syncs_the_seek_slider(self):
        source = _source()
        restart_fn = _function_body(source, "function wwPlaybackRestart(groupId)", "function wwWirePlaybackControls")
        assert "wwPlayback.currentTime = bounds.start;" in restart_fn
        assert "wwPlaybackSyncToolbarForGroup(groupId);" in restart_fn
        # wwPlaybackSyncToolbarForGroup() delegates to the reusable
        # wwSyncPlaybackControls(), which is what actually updates the
        # seek slider's bounds/value -- verified once, generically,
        # rather than duplicated in every caller.
        sync_fn = _function_body(
            source, "function wwSyncPlaybackControls(containerEl, groupId)", "function wwUpdatePlaybackControlsTick"
        )
        assert "wwPlaybackSyncSeekSliderBounds(containerEl, groupId);" in sync_fn
        assert "wwPlaybackUpdateSeekSlider(containerEl, groupId);" in sync_fn

    def test_seek_slider_value_never_fights_an_active_user_drag(self):
        source = _source()
        fn = _function_body(
            source, "function wwPlaybackUpdateSeekSlider(containerEl, groupId)", "function wwUpdatePlaybackCursorOverlay"
        )
        assert "document.activeElement !== sliderEl" in fn


class TestWorkspaceResetSpeedDefault:
    """Test 10 (workspace reset) of the task's own focused-coverage list,
    specifically the speed default the task calls out by name."""

    def test_wwPlaybackReset_restores_default_speed(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackReset()", "function wwPlaybackTick")
        assert "wwPlayback.speed = WW_PLAYBACK_DEFAULT_SPEED;" in fn
        assert "wwPlaybackSyncAllToolbarSpeedSelects();" in fn


class TestPlaybackCompletionDoesNotAutoWrap:
    def test_tick_stops_at_end_time_without_scheduling_another_frame(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackTick(nowMs)", "function wwPlaybackRenderTick")
        completion_branch = _function_body(fn, "if (rawTime >= wwPlayback.endTime)", "wwPlayback.currentTime = rawTime;")
        assert "requestAnimationFrame" not in completion_branch
        assert 'wwPlayback.state = WW_PLAYBACK_STATE_STOPPED;' in completion_branch
