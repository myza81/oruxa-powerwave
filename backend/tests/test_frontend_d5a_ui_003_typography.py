"""D5A-UI-003: the Recording Details redesign adds surfaces and shapes, never type sizes.

The application's own `.ww-rd-*` rules own font size, weight, line height and the compact spacing. The two redesign CSS
blocks (UI-REC-001, D5A-UI-002) must not restate them, and every selector in them must stay inside Recording Details so no
other page's typography or spacing can change.
"""

from __future__ import annotations

import re
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
BLOCKS = (("UI-REC-001-CSS-START", "UI-REC-001-CSS-END"), ("D5A-UI-002-CSS-START", "D5A-UI-002-CSS-END"))
TYPE_PROPERTIES = ("font-size", "font-weight", "line-height", "letter-spacing", "min-height")


def _css(start: str, end: str) -> str:
    begin = SOURCE.rindex("/*", 0, SOURCE.index(start))
    stop = SOURCE.rindex("/*", 0, SOURCE.index(end, begin))
    return re.sub(r"/\*.*?\*/", "", SOURCE[begin:stop], flags=re.S)


def _selectors(css: str) -> list[str]:
    selectors: list[str] = []
    for head in re.findall(r"([^{}]+)\{", css):
        head = head.strip()
        if head.startswith("@"):
            continue
        selectors.extend(part.strip() for part in head.split(","))
    return selectors


def test_redesign_blocks_do_not_override_type_size_or_weight():
    for start, end in BLOCKS:
        css = _css(start, end)
        for prop in TYPE_PROPERTIES:
            assert not re.search(rf"(?<![-\w]){prop}\s*:(?!\s*inherit\b)", css), f"{prop} is restated in {start}"


def test_redesign_blocks_stay_inside_recording_details():
    allowed = re.compile(r"^(#wwRd|\.ww-rd-)")
    for start, end in BLOCKS:
        for selector in _selectors(_css(start, end)):
            assert allowed.match(selector), f"selector escapes Recording Details: {selector!r} ({start})"


def test_card_and_control_metrics_use_the_baseline_scale():
    css = _css("UI-REC-001-CSS-START", "D5A-UI-002-CSS-END")
    assert "padding: 12px 14px" in css  # the baseline .ww-rd-section padding
    assert "margin-bottom: 10px" in css  # the baseline vertical gap (heading / field grid / divider)
    assert not re.search(r"padding:\s*(1[6-9]|2\d)px\s+(1[6-9]|2\d)px", css)
