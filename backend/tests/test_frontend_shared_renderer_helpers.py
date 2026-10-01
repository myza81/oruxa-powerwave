"""Slice 3A (DEC-127, Option B): the renderer helpers shared by Waveform
and (later) Event Reconstruction are pure/parameter-driven, Waveform's
own functions delegate to them unchanged, and nothing plots Event
Reconstruction yet."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    return source[start : source.index("\n        }\n", start) + len("\n        }\n")]


def _code(body: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in body.splitlines())


SHARED_HELPERS = [
    "function wwPlotWidthForChart(chartEl)",
    "function wwPointBudgetForPlotWidth(plotWidth)",
    "function wwViewportTimeToSourceElapsed(viewportTime, offsetS)",
    "function wwSourceElapsedToViewportTime(elapsedSeconds, offsetS)",
    "async function wwFetchWaveformRange(request)",
    "function wwAnalogLineTrace({ x, y, customdata, color, name, hovertemplate, meta })",
    "function wwAnalogPanelLayout(colors, { xTitle, xRange, xTickFormat, yTitle, dragMode })",
    "function wwPanelMarkupHtml(label)",
    "function wwStepZoomXRange(range, direction)",
    "function wwClampRangeToBounds(bounds, start, end)",
    "function wwClampPanWindowToBounds(bounds, start, end)",
    "function wwPlotMetricsForChart(chartEl)",
    "function wwTimeToPageX(range, metrics, time)",
    "function wwPageXToTime(range, metrics, pageX)",
]


@pytest.mark.parametrize("signature", SHARED_HELPERS)
def test_shared_helper_reads_no_page_or_workspace_state(signature):
    body = _code(_function(_source(), signature))
    assert not re.search(r"\bww\.", body)
    assert "wwEr" not in body
    assert "document." not in body
    for waveform_only in ("TimeGroup", "t0", "Annotation", "Playback", "Split", "unitMode = ", "wwPanelTimeGroupId"):
        assert waveform_only not in body


@pytest.mark.parametrize(
    ("wrapper", "delegation"),
    [
        ("function wwPanelPlotWidth(panel)", "return wwPlotWidthForChart(panel && panel.chartEl);"),
        ("function wwPointBudgetForPanel(panel)", "return wwPointBudgetForPlotWidth(wwPanelPlotWidth(panel));"),
        ("async function wwFetchChannelRange(channelEntry, startTime, endTime, pointBudget)", "return wwFetchWaveformRange({"),
        ("function wwBuildTrace(channel, panel)", "const trace = wwAnalogLineTrace({"),
        ("function wwBuildLayout(panel, colors)", "const layout = wwAnalogPanelLayout(colors, {"),
        ("function wwCreatePanelDom(panel)", "container.innerHTML = wwPanelMarkupHtml(panel.label);"),
        ("async function wwStepZoomX(groupId, direction)", "let next = wwStepZoomXRange(range, direction);"),
        ("function wwClampRangeToTimeGroup(groupId, start, end)", "return wwClampRangeToBounds(wwDeriveTimeGroupBounds(groupId), start, end);"),
        ("function wwClampPanWindowToTimeGroup(groupId, start, end)", "return wwClampPanWindowToBounds(wwDeriveTimeGroupBounds(groupId), start, end);"),
        ("function wwCursorPlotMetrics(groupId)", "const metrics = wwPlotMetricsForChart(chartEl);"),
        ("function wwCursorTimeToPixelX(groupId, time)", "return wwTimeToPageX(range, wwCursorPlotMetrics(groupId), time);"),
        ("function wwCursorPixelXToTime(groupId, pageX, metrics)", "return wwPageXToTime(range, m, pageX);"),
    ],
)
def test_waveform_function_delegates_to_the_shared_helper(wrapper, delegation):
    assert delegation in _function(_source(), wrapper)


def test_waveform_fetch_wrapper_keeps_waveform_inputs():
    wrapper = _function(_source(), "async function wwFetchChannelRange(channelEntry, startTime, endTime, pointBudget)")
    for expected in (
        "requestState: channelEntry,",
        "isCalculated: wwIsCalculatedSourceId(channelEntry.sourceId),",
        "unitMode: ww.unitMode,",
        "timeOffsetS: alignmentOffset,",
    ):
        assert expected in wrapper


def test_fetch_core_keeps_the_existing_request_contract():
    core = _function(_source(), "async function wwFetchWaveformRange(request)")
    for expected in (
        'url.searchParams.set("channel_name", channelName);',
        'url.searchParams.set("start_time", nativeStart);',
        'url.searchParams.set("end_time", nativeEnd);',
        'url.searchParams.set("point_budget", String(pointBudget));',
        "if (requestState.abortController) requestState.abortController.abort();",
        "if (seq !== requestState.requestSeq) return { superseded: true };",
        '"/calculated-channels/" + encodeURIComponent(sourceId) + "/waveform"',
        '"/sources/" + encodeURIComponent(sourceId) + "/waveform"',
    ):
        assert expected in core


def test_event_reconstruction_does_not_plot_yet():
    source = _source()
    module = _code(source[source.index("// Event Reconstruction (DEC-123 Slice 0 shell") : source.index("// Phase 3B: Recordings page (section 5/8/9)")])
    for forbidden in ("Plotly", "wwFetchWaveformRange", "wwAnalogLineTrace", "wwAnalogPanelLayout", "wwPanelMarkupHtml"):
        assert forbidden not in module


def test_no_event_reconstruction_state_in_the_waveform_engine():
    source = _source()
    ww_state = source[source.index("        const ww = {") : source.index("\n        };\n", source.index("        const ww = {"))]
    assert "reconstruction" not in ww_state.lower()
    assert "wwEr" not in ww_state
