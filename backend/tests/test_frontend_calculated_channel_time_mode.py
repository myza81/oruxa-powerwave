"""Static regression checks for calculated-channel time-mode eligibility."""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


def test_calculated_channel_meta_inherits_reference_source_timing():
    source = _source()
    body = _function_body(
        source,
        "function wwCalculatedChannelMeta(calc)",
        "function wwToggleCalculatedChannelDisplay(calc)",
    )

    assert "wwSourceTimingAuthority(calc.reference_source_id)" in body
    assert "sourceId: calc.id" in body
    assert 'sourceName: "Calculated Channels"' in body
    assert "recordingStartTime: timing.recordingStartTime" in body
    assert "timingReference: timing.timingReference" in body
    assert "recordingStartTime: null" not in body
    assert "timingReference: null" not in body


def test_calculated_channel_display_identity_is_not_used_as_timing_authority():
    source = _source()
    body = _function_body(
        source,
        "function wwTimingSourceIdForDisplaySourceId(sourceId)",
        "function wwParticipatingSourceIds()",
    )

    assert "wwIsCalculatedSourceId(sourceId)" in body
    assert "ww.calculatedChannels.get(sourceId)" in body
    assert "calc.reference_source_id" in body
    assert "return (calc && calc.reference_source_id) || sourceId;" in body


def test_participating_sources_use_calculated_reference_source_for_bounds():
    source = _source()
    body = _function_body(
        source,
        "function wwParticipatingSourceIds()",
        "function wwDeriveWorkspaceBounds()",
    )

    assert "wwTimingSourceIdForDisplaySourceId(channel.sourceId)" in body
    assert "ww.sourceBounds.has(timingSourceId)" in body
    assert "ids.add(timingSourceId)" in body


def test_calculated_channel_absolute_time_mode_remains_presentation_only():
    source = _source()
    set_time_mode = _function_body(
        source,
        "function wwSetTimeMode(mode)",
        "function wwUpdateEditGroupsButtonVisibility()",
    )
    calculated_meta = _function_body(
        source,
        "function wwCalculatedChannelMeta(calc)",
        "function wwToggleCalculatedChannelDisplay(calc)",
    )

    assert "fetch(" not in set_time_mode
    assert "x: [xValues]" not in set_time_mode
    assert "y: [" not in set_time_mode
    assert "recordingStartTime: timing.recordingStartTime" in calculated_meta
