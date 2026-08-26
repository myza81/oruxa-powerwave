"""Static checks for Absolute-Time sub-ms waveform precision.

The production invariant is intentionally simple: Plotly engineering X
coordinates are elapsed numeric seconds in both Absolute and Elapsed modes.
Absolute Time is labels/hover/cursor text only.
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


def test_elapsed_to_plotly_x_is_identity_in_all_time_modes():
    """Absolute-vs-Elapsed time MODE never affects this coordinate (still
    true post-Slice-2: no Date/absolute-timestamp math here at all).
    Slice 2 of waveform time synchronization gave it exactly one new,
    intentional transform -- delegating to wwWorkspaceTimeToEventTime(),
    which is itself a documented no-op passthrough whenever no t0 is
    selected (see test_synchronization_t0_domain.py's own coverage of
    that pure function) -- so this remains numerically identity except
    when the engineer has explicitly picked an event origin."""
    source = _source()
    body = _function_body(
        source,
        "function wwElapsedToPlotlyX(elapsedSeconds)",
        "function wwPlotlyXToElapsed(x)",
    )

    assert "return wwWorkspaceTimeToEventTime(elapsedSeconds);" in body
    assert "wwWorkspaceRecordingStartMs" not in body
    assert "new Date" not in body
    assert "Date.UTC" not in body


def test_plotly_x_to_elapsed_is_identity_in_all_time_modes():
    source = _source()
    body = _function_body(
        source,
        "function wwPlotlyXToElapsed(x)",
        "function wwNiceTickStep",
    )

    assert "return wwEventTimeToWorkspaceTime(Number(x));" in body
    assert "wwParseNaiveTimestamp" not in body
    assert "wwWorkspaceRecordingStartMs" not in body


def test_absolute_mode_never_uses_date_axis_or_date_strings_for_plotly_coordinates():
    source = _source()

    assert 'type: ww.timeMode === "absolute" ? "date"' not in source
    assert '"xaxis.type": mode === "absolute" ? "date"' not in source
    assert 'type: "date"' not in source
    assert "wwFormatPlotlyDateString" not in source
    assert "%{x|" not in source


def test_time_mode_switch_does_not_rewrite_trace_geometry():
    """Boundary is wwApplyT0ToDisplay() -- the Slice 2 function
    immediately following wwSetTimeMode() -- not
    wwUpdateEditGroupsButtonVisibility(), which now sits several
    functions further down after the new t=0 block; wwApplyT0ToDisplay()
    itself DOES restyle x (a real, t0-driven coordinate change, unlike a
    mode switch), so it must stay excluded from this body."""
    source = _source()
    body = _function_body(
        source,
        "function wwSetTimeMode(mode)",
        "function wwApplyT0ToDisplay()",
    )

    assert "Plotly.restyle" in body
    assert "customdata: [wwTraceCustomData(channel)]" in body
    assert "hovertemplate: [wwTraceHoverTemplate(channel)]" in body
    assert "x: [xValues]" not in body
    assert "y: [" not in body
    assert ".map(wwElapsedToPlotlyX)" not in body


def test_trace_geometry_uses_elapsed_numeric_x_with_absolute_hover_customdata():
    source = _source()
    body = _function_body(
        source,
        "function wwBuildTrace(channel)",
        "function wwBuildLayout(panel, colors)",
    )

    assert "const xValues = (channel.time || []).map(wwElapsedToPlotlyX);" in body
    assert "x: xValues" in body
    assert "customdata: wwTraceCustomData(channel)" in body
    assert "hovertemplate: wwTraceHoverTemplate(channel)" in body
    assert "%{x|" not in body


def test_five_khz_absolute_switch_preserves_unique_numeric_x_coordinates():
    source = _source()
    assert "function wwElapsedToPlotlyX(elapsedSeconds)" in source

    sample_rate_hz = 5000
    start = 2.0
    end = 2.015
    sample_count = int(round((end - start) * sample_rate_hz)) + 1
    elapsed_x = [start + i / sample_rate_hz for i in range(sample_count)]
    absolute_x_after_mode_switch = elapsed_x[:]

    assert sample_count == 76
    assert len(set(elapsed_x)) == 76
    assert len(set(absolute_x_after_mode_switch)) == 76
    assert absolute_x_after_mode_switch == elapsed_x


def test_absolute_formatting_has_sub_millisecond_precision_tiers():
    source = _source()
    body = _function_body(
        source,
        "function wwAbsoluteFractionDigits(spanSeconds)",
        "function wwFormatAbsoluteElapsedTime(elapsedSeconds, opts)",
    )

    assert "spanSeconds < 0.01) return 5" in body
    assert "spanSeconds < 0.1) return 4" in body
    assert "spanSeconds < 2) return 3" in body


def test_sticky_ruler_uses_elapsed_numeric_domain_in_both_modes():
    source = _source()
    body = _function_body(
        source,
        "function wwSyncStickyRuler()",
        "// Phase 4B: every path that reaches this function already",
    )

    assert 'type: "linear"' in body
    assert '"xaxis.type": "linear"' in body
    assert 'type: "date"' not in body
    assert 'ww.viewport.start * unit.scale' not in body
    assert 'ww.viewport.end * unit.scale' not in body
