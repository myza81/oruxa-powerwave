"""Static structural regression checks for Event Playback Slice 1 (Core
Playback Engine), frontend/index.html.

Same source-text substring-assertion pattern every other
`test_frontend_*.py` file in this suite already uses -- this repo has no
browser/DOM test runner for the single-file frontend. Real timer/rAF/
Plotly-overlay BEHAVIOR is covered separately by
`browser-tests/playback.spec.js` (Playwright, real browser) -- these
tests only guard structural invariants a source-text assertion CAN
meaningfully verify (ordering, presence, absence of coupling to Cursor
A/B or to a backend endpoint).

Playback is frontend/session state only (no backend API changes this
slice) -- every test below is source-only; none touches the backend.
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


class TestMainMenuPosition:
    """Playback must be a top-level main-menu item, immediately after
    Calculated Channels, per the owner-approved ordering (Calculated
    Channels / Playback / a future Analysis item, not implemented yet)."""

    def test_playback_nav_button_exists(self):
        source = _source()
        assert 'id="mainNavPlaybackBtn"' in source
        assert 'id="pagePlayback"' in source

    def test_playback_button_immediately_follows_calculated_channels_in_nav_list(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        cc_index = nav_list.index('id="mainNavCalculatedChannelsBtn"')
        playback_index = nav_list.index('id="mainNavPlaybackBtn"')
        tools_index = nav_list.index('title="Tools -- coming soon"')
        assert cc_index < playback_index < tools_index, (
            "Playback must sit between Calculated Channels and the (still-disabled) "
            "Tools/future-Analysis placeholder items"
        )

    def test_no_analysis_menu_item_added_yet(self):
        source = _source()
        nav_list = _function_body(source, 'class="shell-nav-list"', 'class="shell-nav-bottom"')
        assert 'id="mainNavAnalysisBtn"' not in nav_list
        assert '<span class="shell-nav-label">Analysis</span>' not in nav_list, (
            "Slice 1 preserves ordering/direction for a future Analysis menu item -- "
            "it must not actually create one yet"
        )

    def test_playback_page_routes_through_shellSetCurrentPage(self):
        source = _source()
        assert 'page !== "playback"' in source
        assert 'document.getElementById("pagePlayback").hidden = page !== "playback";' in source
        assert 'setShellNavCurrent("mainNavPlaybackBtn", page === "playback");' in source
        wiring = _function_body(
            source, 'document.getElementById("mainNavPlaybackBtn")', "\n"
        )
        assert 'shellSetCurrentPage("playback")' in wiring

    def test_playback_page_is_not_a_configuration_dashboard(self):
        """Owner instruction: keep this page minimal -- only status text,
        never a second copy of the transport controls."""
        source = _source()
        page_body = _function_body(source, 'id="pagePlayback"', "<!-- CSV/Excel ingestion Slice 3")
        assert "wwPlaybackPageStatus" in page_body
        assert "ww-tg-playback-play-btn" not in page_body
        assert "ww-tg-playback-restart-btn" not in page_body


class TestTimeGroupToolbarControls:
    """Everyday Play/Pause/Restart controls live on each Time Group's own
    waveform toolbar, built once by wwCreateTimeGroupCanvasDom() and wired
    once by wwWireTimeGroupToolbar() -- the same established per-canvas
    pattern Reset Time View/Autoscale Y/Cursor mode already use."""

    def test_toolbar_template_includes_playback_controls(self):
        source = _source()
        toolbar_fn = _function_body(
            source, "function wwCreateTimeGroupCanvasDom(groupId)", "function wwEnsureTimeGroupCanvasDom"
        )
        assert "ww-tg-playback-restart-btn" in toolbar_fn
        assert "ww-tg-playback-play-btn" in toolbar_fn
        assert "ww-tg-playback-time-readout" in toolbar_fn
        # No speed/seek controls yet -- explicitly out of scope this slice.
        assert "playback-speed" not in toolbar_fn
        assert "playback-seek" not in toolbar_fn
        assert "playback-scrubber" not in toolbar_fn

    def test_toolbar_wiring_binds_both_buttons(self):
        source = _source()
        wiring_fn = _function_body(
            source, "function wwWireTimeGroupToolbar(canvasEl, groupId)", "function wwWireSplitMenuOutsideClickDismissal"
        )
        assert "wwPlaybackRestart(groupId)" in wiring_fn
        assert "wwPlaybackHandlePlayPauseClick(groupId)" in wiring_fn


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

    def test_speed_is_fixed_at_1x_this_slice(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackPlay(groupId)", "function wwPlaybackPause")
        assert "wwPlayback.speed = 1;" in fn
        assert "ww-tg-playback-speed" not in source


class TestCanonicalTimeCoordinateIsWorkspaceTime:
    def test_readout_reuses_the_existing_cursor_time_formatter(self):
        """Never a second/independent clock -- reuses
        wwFormatCursorPointTime(), the SAME formatter Cursor A/B/Δt
        already use, so display automatically follows whatever Time
        Mode/t0 is active without any new conversion logic."""
        source = _source()
        fn = _function_body(source, "function wwPlaybackUpdateTimeReadout(groupId)", "function wwUpdatePlaybackCursorOverlay")
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
            source, "function wwPlaybackDigitalStateFor(sourceId, channelName, time)", "function wwRenderPlaybackPage"
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


class TestPlaybackCompletionDoesNotAutoWrap:
    def test_tick_stops_at_end_time_without_scheduling_another_frame(self):
        source = _source()
        fn = _function_body(source, "function wwPlaybackTick(nowMs)", "function wwPlaybackRenderTick")
        completion_branch = _function_body(fn, "if (rawTime >= wwPlayback.endTime)", "wwPlayback.currentTime = rawTime;")
        assert "requestAnimationFrame" not in completion_branch
        assert 'wwPlayback.state = WW_PLAYBACK_STATE_STOPPED;' in completion_branch
