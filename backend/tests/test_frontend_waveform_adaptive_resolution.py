"""Static checks for analog waveform adaptive display-resolution wiring."""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


def test_named_pixel_aware_budget_constants_are_present():
    source = _source()

    assert "const WW_POINT_BUDGET_MIN = 4000;" in source
    assert "const WW_POINT_BUDGET_MAX = 20000;" in source
    assert "const WW_POINT_BUDGET_PER_PIXEL = 4;" in source
    assert "const WW_POINT_BUDGET = 4000;" not in source


def test_point_budget_uses_actual_plot_domain_width_not_browser_width():
    source = _source()
    width_body = _function_body(
        source,
        "function wwPanelPlotWidth(panel)",
        "function wwPointBudgetForPanel(panel)",
    )

    assert "chartEl._fullLayout" in width_body
    assert "fl.xaxis._length" in width_body
    assert "chartEl.getBoundingClientRect()" in width_body
    assert "WW_PANEL_MARGIN.l" in width_body
    assert "window.innerWidth" not in width_body
    assert "document.documentElement.clientWidth" not in width_body


def test_point_budget_clamps_to_approved_min_and_max():
    source = _source()
    clamp_body = _function_body(
        source,
        "function wwClampPointBudget(value)",
        "function wwPanelPlotWidth(panel)",
    )
    budget_body = _function_body(
        source,
        "function wwPointBudgetForPanel(panel)",
        "async function wwFetchChannelRange",
    )

    assert "Math.max(WW_POINT_BUDGET_MIN, Math.min(WW_POINT_BUDGET_MAX, rounded))" in clamp_body
    assert "plotWidth * WW_POINT_BUDGET_PER_PIXEL" in budget_body
    assert "return WW_POINT_BUDGET_MIN" in budget_body


def test_waveform_fetch_sends_panel_specific_point_budget():
    source = _source()
    load_body = _function_body(
        source,
        "async function wwLoadChannelRange",
        "// ------------------------------------------------------------------\n        // Panel DOM + Plotly lifecycle",
    )
    fetch_body = _function_body(
        source,
        "async function wwFetchChannelRange",
        "function wwFriendlyError",
    )

    assert "wwFetchChannelRange(channelEntry, startTime, endTime, wwPointBudgetForPanel(panel))" in load_body
    assert 'url.searchParams.set("point_budget", String(pointBudget))' in fetch_body
    assert "String(WW_POINT_BUDGET" not in fetch_body


def test_zoom_still_requests_elapsed_engineering_range_in_all_time_modes():
    source = _source()
    relayout_body = _function_body(
        source,
        "function wwWirePanelRelayout(panel)",
        "function wwBroadcastViewportDebounced",
    )
    fetch_body = _function_body(
        source,
        "async function wwFetchChannelRange",
        "function wwFriendlyError",
    )

    assert "wwPlotlyXToElapsed(x0)" in relayout_body
    assert "wwPlotlyXToElapsed(x1)" in relayout_body
    # Slice 1 of waveform time synchronization: the fetch now converts the
    # caller's workspace-time startTime/endTime into this channel's own
    # source-native range (nativeStart/nativeEnd, via
    # wwWorkspaceTimeToSourceTime) before building the request -- still
    # the same elapsed/engineering coordinate system, never re-transformed
    # through a display-mode-specific wwElapsedToPlotlyX() call.
    assert 'url.searchParams.set("start_time", nativeStart)' in fetch_body
    assert 'url.searchParams.set("end_time", nativeEnd)' in fetch_body
    assert "wwElapsedToPlotlyX(startTime)" not in fetch_body
    assert "wwElapsedToPlotlyX(endTime)" not in fetch_body
