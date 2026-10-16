"""A synthetic MiCOM P441-shaped setting sheet for Slice 6 tests.

Mirrors the shape the generic extractor produces for the owner's real sheet
(parameter code / name / value / printed range). Shared by the profile tests
and the upload API tests; the real sheet itself is never committed.
"""

from __future__ import annotations

import itertools
import re

from app.domain.relay_import.raw_document import (
    RawRelayDocument,
    RawSetting,
    SettingRange,
    SourceFormat,
    SourceLocation,
)

from tests.relay_conformance.sheet_spec import load_spec

# The sheet is data (``tests/relay_conformance/sheets/p441.json``, DEC-199): the scheme row, then
# code -> (name, value, printed range) as the sheet prints them, then the scheme notes.
_SPEC = load_spec("p441")
SCHEME_ROW: tuple[str, str] = tuple(_SPEC["lines"][0])
BASE: dict[str, tuple[str, str, str | None]] = {code: (name, value, rng) for code, name, value, rng in _SPEC["lines"][1:]}
NOTES: tuple[str, ...] = tuple(note[0] for note in _SPEC["notes"])

def _row(sid: str, code: str | None, name: str, value: str | None, rng: str | None, page: int, line: int) -> RawSetting:
    return RawSetting(
        setting_id=sid,
        name=name,
        parameter_id=code,
        raw_value=value,
        normalized_value=float(value) if value and re.fullmatch(r"-?\d+(\.\d+)?", value) else None,
        setting_range=SettingRange(text=rng) if rng else None,
        location=SourceLocation(page=page, line=line),
        source_text=" ".join(x for x in (code, name, value, rng) if x),
    )


def make_doc(
    *,
    overrides: dict[str, tuple[str, str, str | None]] | None = None,
    drop: tuple[str, ...] = (),
    extra: tuple[tuple[str | None, str, str | None, str | None], ...] = (),
    notes: tuple[str, ...] = NOTES,
    scheme: tuple[str, str] | None = SCHEME_ROW,
) -> RawRelayDocument:
    rows = dict(BASE)
    rows.update(overrides or {})
    for code in drop:
        rows.pop(code)
    counter = itertools.count(1)
    settings: list[RawSetting] = []
    if scheme:
        settings.append(_row(f"p1-e{next(counter)}", None, scheme[0], scheme[1], None, 1, 1))
    for code, (name, value, rng) in rows.items():
        settings.append(_row(f"p1-e{next(counter)}", code, name, value, rng, 3, 10 + len(settings)))
    for code, name, value, rng in extra:
        settings.append(_row(f"p1-e{next(counter)}", code, name, value, rng, 4, 10 + len(settings)))
    for text in notes:
        settings.append(_row(f"p5-e{next(counter)}", None, text, None, None, 5, 30 + len(settings)))
    return RawRelayDocument(SourceFormat.PDF, tuple(settings), extractor_id="test")
