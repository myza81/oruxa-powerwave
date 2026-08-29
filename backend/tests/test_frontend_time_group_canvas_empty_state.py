"""Static regression checks for the Time Group Canvas empty-state
lifecycle fix (owner UAT finding on Slice TG-B+C): a Time Group Canvas
-- header, toolbar, Reset Time View, analog panel container, digital
panel, Time Range slider, sticky ruler -- must render only once its own
Time Group owns at least one currently DISPLAYED channel (analog or
digital), never merely because a source is loaded/visible in the
sidebar or has synchronization state.

Mirrors this suite's own established pure string/index-based approach
(test_frontend_time_range_slider.py, test_frontend_time_groups.py) --
no jsdom execution, just confirming the canonical helper exists and
that every canvas-creation call site is actually gated by it, never a
scattered ad hoc DOM-hiding condition. Real end-to-end lifecycle
behavior (upload -> empty state -> first channel -> canvas appears ->
last channel removed -> canvas disappears -> multi-group isolation) is
proven live via Playwright against a running backend -- see this
task's own live-UAT report for the full record.
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


class TestCanonicalHelperExists:
    """Preferred fix: one canonical helper, not scattered per-surface
    DOM-hiding conditions."""

    def test_wwTimeGroupHasDisplayedChannels_exists(self):
        source = _source()
        assert "function wwTimeGroupHasDisplayedChannels(groupId)" in source

    def test_helper_checks_both_analog_and_digital_displayed_maps(self):
        source = _source()
        fn_idx = source.index("function wwTimeGroupHasDisplayedChannels(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const { channel } of ww.displayed.values())" in fn_body
        assert "for (const entry of ww.digitalDisplayed.values())" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(channel.sourceId) === groupId" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(entry.sourceId) === groupId" in fn_body

    def test_null_group_id_is_never_treated_as_having_content(self):
        source = _source()
        fn_idx = source.index("function wwTimeGroupHasDisplayedChannels(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (groupId === null) return false;" in fn_body


class TestActiveTimeGroupIdsCoversDigitalOnlyGroups:
    """Case C (digital-only display must still create the canvas): the
    active-group derivation must not silently skip a group whose only
    displayed membership is digital -- the pre-fix version only ever
    scanned ww.displayed (analog)."""

    def test_active_ids_scans_digital_displayed_too(self):
        source = _source()
        fn_idx = source.index("function wwActiveTimeGroupIds()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "for (const { channel } of ww.displayed.values())" in fn_body
        assert "for (const entry of ww.digitalDisplayed.values())" in fn_body
        assert "wwTimeGroupIdForDisplaySourceId(entry.sourceId)" in fn_body


class TestDigitalChartCreationGatedByDisplayedChannels:
    """wwRebuildDigitalChart() used to call the CREATING
    wwEnsureTimeGroupCanvasDom() unconditionally -- the root cause of a
    canvas rendering for a source with zero displayed channels whenever
    this function was reached for that group (e.g. via
    wwApplyAndFetchGroupViewport()'s own primary-group resolution
    falling back to a merely-loaded source)."""

    def test_creation_is_conditional_on_the_canonical_helper(self):
        source = _source()
        fn_idx = source.index("function wwRebuildDigitalChart(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const hasDisplayedChannels = wwTimeGroupHasDisplayedChannels(groupId);" in fn_body
        assert (
            "const canvasEl = hasDisplayedChannels ? wwEnsureTimeGroupCanvasDom(groupId) : wwTimeGroupCanvasEl(groupId);"
            in fn_body
        )

    def test_no_longer_calls_the_creating_helper_unconditionally(self):
        source = _source()
        fn_idx = source.index("function wwRebuildDigitalChart(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const canvasEl = wwEnsureTimeGroupCanvasDom(groupId);\n" not in fn_body


class TestRulerCreationGatedByDisplayedChannels:
    """Same root-cause fix, applied to the ruler -- previously created
    unconditionally and only hid its OWN wrap element afterward, never
    asking whether the canvas ROOT itself (header/toolbar/Reset Time
    View/slider) should exist at all."""

    def test_creation_is_conditional_on_the_canonical_helper(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const hasChannels = wwTimeGroupHasDisplayedChannels(groupId);" in fn_body
        assert (
            "const canvasEl = hasChannels ? wwEnsureTimeGroupCanvasDom(groupId) : wwTimeGroupCanvasEl(groupId);"
            in fn_body
        )

    def test_no_longer_calls_the_creating_helper_unconditionally(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const canvasEl = wwEnsureTimeGroupCanvasDom(groupId);\n" not in fn_body

    def test_ruler_wrap_visibility_still_derived_from_the_same_flag(self):
        """The ruler wrap's own hidden state and the creation gate must
        never disagree -- both come from the same single `hasChannels`
        value computed once at the top of the function."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupRuler(groupId)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "wrapEl.hidden = !hasChannels;" in fn_body


class TestSliderSyncNeverCreatesACanvasOfItsOwn:
    """wwApplyAndFetchGroupViewport()'s own slider-sync call site was
    already using the non-creating wwTimeGroupCanvasEl() lookup -- this
    locks that in, since it is what makes the ruler/digital fix above
    sufficient on its own (no separate slider-specific gate needed)."""

    def test_slider_sync_call_site_uses_non_creating_lookup(self):
        source = _source()
        fn_idx = source.index("async function wwApplyAndFetchGroupViewport(groupId, startTime, endTime)")
        fn_body = source[fn_idx : source.index("async function wwApplyAndFetchViewport(startTime, endTime)", fn_idx)]
        assert "const canvasEl = wwTimeGroupCanvasEl(groupId);" in fn_body
        assert "if (canvasEl) wwSyncTimeGroupSliderForCanvas(groupId, canvasEl);" in fn_body


class TestOnlyLegitimateCreatorsCallTheCreatingHelper:
    """Every call to the CREATING wwEnsureTimeGroupCanvasDom() must be
    either (a) already gated by wwTimeGroupHasDisplayedChannels()
    (digital chart, ruler -- fixed above), (b) wwCreatePanelDom()
    itself, safe by construction because a channel is always added to
    ww.displayed BEFORE its own panel is created, or (c)
    wwSyncTimeGroupCanvases()'s own loop, already scoped to
    wwActiveTimeGroupIds()'s own sorted, de-duplicated active set. No
    other, unaudited call site may exist."""

    def test_exactly_four_call_sites_of_the_creating_helper(self):
        source = _source()
        # "= wwEnsureTimeGroupCanvasDom(groupId)" matches every CALL
        # site (an assignment/ternary result) but not the function's
        # own `function wwEnsureTimeGroupCanvasDom(groupId) {` signature.
        count = source.count("wwEnsureTimeGroupCanvasDom(groupId)") - 1
        # wwCreatePanelDom, the two conditional (ternary) call sites
        # inside wwRebuildDigitalChart/wwSyncTimeGroupRuler, and
        # wwSyncTimeGroupCanvases's own loop.
        assert count == 4, (
            "A new, unaudited call site to the CREATING "
            "wwEnsureTimeGroupCanvasDom() was added -- every call site must "
            "either be gated by wwTimeGroupHasDisplayedChannels() or be one "
            "of the three already-audited legitimate creators."
        )

    def test_create_panel_dom_adds_to_displayed_before_creating_its_panel(self):
        """wwCreatePanelDom() itself does no gating -- it is safe only
        because wwAddSelectedChannels() always writes ww.displayed.set()
        for the new channel BEFORE calling wwCreatePanelDom() for its
        panel, so wwTimeGroupHasDisplayedChannels() would already
        return true for that group by the time creation happens."""
        source = _source()
        fn_idx = source.index("async function wwAddSelectedChannels(channelMetas, options)")
        fn_body = source[fn_idx : source.index("if (jobs.length === 0) return;", fn_idx)]
        displayed_set_idx = fn_idx + fn_body.index("ww.displayed.set(key, { panel, channel: channelEntry });")
        create_panel_call_idx = source.index(
            "for (const panel of newlyCreatedPanels) wwCreatePanelDom(panel);",
            fn_idx,
        )
        assert create_panel_call_idx > displayed_set_idx


class TestCanvasSyncPruningUsesTheSameActiveSet:
    """Case F (final channel removal): wwSyncTimeGroupCanvases()'s own
    pruning loop must key off the SAME wwActiveTimeGroupIds() (now
    digital-aware), so removing a group's last displayed channel --
    analog or digital -- correctly tears down its canvas DOM."""

    def test_sync_canvases_derives_sorted_ids_from_active_time_group_ids(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const activeIds = wwActiveTimeGroupIds();" in fn_body
        assert "const sortedIds = Array.from(activeIds).sort();" in fn_body

    def test_canvases_not_in_the_active_set_are_removed(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "if (!sortedIds.includes(groupId)) {" in fn_body
        assert "canvasEl.remove();" in fn_body

    def test_empty_active_set_clears_the_whole_container(self):
        """source loaded + zero displayed channels workspace-wide ->
        zero canvases: the container is cleared entirely when no group
        is active, regardless of how many sources are merely loaded."""
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert 'if (sortedIds.length === 0) {' in fn_body
        assert 'container.innerHTML = "";' in fn_body


class TestEmptyActiveSetAlsoClearsPerGroupReadyState:
    """Regression for a genuine bug found live during this task's own
    UAT: the `sortedIds.length === 0` early-return branch used to clear
    the canvas DOM (container.innerHTML = "") WITHOUT also clearing
    ww.rulerReadyByGroup/ww.digitalChartReadyByGroup/
    ww.digitalClickWiredByGroup -- that cleanup only lived in the
    pruning loop this early return skips past. The next time that same
    group ever got a displayed channel again, its stale
    `rulerReadyByGroup === true` made wwSyncTimeGroupRuler() call
    Plotly.relayout() on a brand-new, never-newPlot()'d chart element
    (since the old one was destroyed via innerHTML), throwing an
    uncaught TypeError reading Plotly's own internal `_guiEditing`.
    Reproduced live: Case A -> B -> remove (down to zero groups) ->
    C (digital-only, same group) threw exactly this error before the
    fix; 0 errors after it."""

    def test_empty_branch_clears_all_three_ready_state_maps(self):
        source = _source()
        fn_idx = source.index("function wwSyncTimeGroupCanvases()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        empty_branch_idx = fn_body.index("if (sortedIds.length === 0) {")
        empty_branch_end = fn_body.index("return;\n            }", empty_branch_idx)
        empty_branch = fn_body[empty_branch_idx:empty_branch_end]
        assert "ww.rulerReadyByGroup.clear();" in empty_branch
        assert "ww.digitalChartReadyByGroup.clear();" in empty_branch
        assert "ww.digitalClickWiredByGroup.clear();" in empty_branch


class TestPanelPurgeOnRemovalNeverRacesPlotlysOwnPendingAutoMarginCallback:
    """Regression for a second genuine bug found live during this same
    UAT pass: wwRemovePanelDom() called the synchronous, unguarded
    Plotly.purge(panel.chartEl) -- unlike wwRebuildLayout()'s own panel-
    purge loop (already fixed for this exact class of race in the prior
    Time Group Canvas slice), this one call site was never updated.
    Toggling a channel on and immediately back off (exactly what the
    empty-state lifecycle does in Cases B/F, D/F, and G) could purge a
    panel before Plotly's own deferred auto-margin redraw callback (from
    that SAME panel's own recent Plotly.newPlot()) had run, throwing an
    uncaught TypeError reading Plotly's own internal
    `_redrawFromAutoMarginCount`. Reproduced live on every single-
    channel removal before the fix; 0 errors after it."""

    def test_panel_purge_is_deferred_to_the_next_animation_frame(self):
        source = _source()
        fn_idx = source.index("function wwRemovePanelDom(panel)")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const chartElToPurge = panel.chartEl;" in fn_body
        assert "requestAnimationFrame(() => Plotly.purge(chartElToPurge));" in fn_body
        assert "Plotly.purge(panel.chartEl);\n" not in fn_body


class TestEmptyStateMessageUnchanged:
    """Do not redesign the empty-state UX -- the existing message and
    its existing, already-correct analog+digital gate must remain
    exactly as they were."""

    def test_empty_state_message_text_present(self):
        source = _source()
        assert "Select channels from the sidebar to display waveforms." in source

    def test_empty_state_gate_checks_both_panels_and_digital_displayed(self):
        source = _source()
        fn_idx = source.index("function wwUpdateEmptyState()")
        fn_body = source[fn_idx : source.index("\n        }\n", fn_idx)]
        assert "const empty = ww.panels.length === 0 && ww.digitalDisplayed.size === 0;" in fn_body
