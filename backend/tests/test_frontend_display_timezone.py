"""DEC-122 static guards: engineering timestamps are displayed in ONE
display timezone through one shared helper, never per format and never
by manual offset arithmetic. Behaviour is verified in the browser by
browser-tests/display-timezone.spec.js."""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _body(source: str, signature: str) -> str:
    start = source.index(signature)
    end = source.index("\n        function ", start + len(signature))
    return source[start:end]


def test_default_display_timezone_is_an_iana_zone_with_config_override():
    body = _body(_source(), "function wwDisplayTimezone()")
    assert '"Asia/Kuala_Lumpur"' in body
    assert "POWERWAVE_CONFIG" in body and "displayTimezone" in body


def test_conversion_uses_intl_time_zone_not_offset_arithmetic():
    source = _source()
    formatter = _body(source, "function wwDisplayWallClockFormatter()")
    assert "Intl.DateTimeFormat" in formatter and "timeZone: zone" in formatter
    convert = _body(source, "function wwDisplayWallClockIso(canonicalIso)")
    assert "formatToParts" in convert
    assert "getTimezoneOffset" not in convert  # never the browser's own zone
    assert not re.search(r"\b8\s*\*\s*(60|3600)", convert)  # never a hard-coded +08:00


def test_no_format_specific_display_branch():
    source = _source()
    for name in ("wwDisplayWallClockIso", "wwFormatEngineeringTimestamp", "wwRecordingDisplayStartTime"):
        body = _body(source, f"function {name}(")
        assert "BEN" not in body and "COMTRADE" not in body and "provider_type" not in body


def test_recording_and_trigger_times_use_the_canonical_instant():
    source = _source()
    identity = _body(source, "function wwFormatRecordingTimeIdentity(source, opts)")
    assert "wwFormatEngineeringTimestamp(source.start_time_utc)" in identity
    assert "wwFormatEngineeringTimestamp(source.trigger_time_utc)" in source


def test_absolute_anchor_uses_the_display_wall_clock_everywhere():
    source = _source()
    assert source.count('data-recording-start-time="\' + escapeHtml(wwRecordingDisplayStartTime(timebase)') == 2
    assert "const recordingStartTime = wwRecordingDisplayStartTime(timebase);" in source
    assert "timebase.start_time || null;\n            ww.sourceTiming" not in source
