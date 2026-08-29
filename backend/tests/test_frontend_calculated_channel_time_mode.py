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
    """Multi-source sidebar redesign: wwParticipatingSourceIds() no longer
    needs its own per-calculated-channel wwTimingSourceIdForDisplaySourceId()
    resolution loop -- every source a calculated channel could possibly be
    grounded on is now unconditionally present in ww.sourceBounds the
    moment it is uploaded (wwEnsureSourceChannelsFetched() fetches EVERY
    source's own timebase eagerly, not only a single selected one), so
    "every key in ww.sourceBounds" already IS "every participating real
    source, including every calculated channel's own reference source" --
    see wwParticipatingSourceIds()'s own updated comment."""
    source = _source()
    body = _function_body(
        source,
        "function wwParticipatingSourceIds()",
        "function wwDeriveWorkspaceBounds()",
    )

    assert "return new Set(ww.sourceBounds.keys());" in body


def test_calculated_channel_absolute_time_mode_remains_presentation_only():
    """Boundary is wwApplyT0ToDisplay() -- see
    test_frontend_absolute_time_precision.py's own
    test_time_mode_switch_does_not_rewrite_trace_geometry for why: it is
    the Slice 2 function immediately following wwSetTimeMode() now, and
    it legitimately does fetch(...)/restyle x (t0 PUT/DELETE + trace
    re-projection), so it must stay excluded from this Absolute-Time-mode
    body."""
    source = _source()
    set_time_mode = _function_body(
        source,
        "function wwSetTimeMode(mode)",
        "function wwAnySourceIdForTimeGroup(groupId)",
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
