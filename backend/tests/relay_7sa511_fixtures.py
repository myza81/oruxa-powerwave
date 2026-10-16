"""A synthetic Siemens 7SA511-shaped setting sheet for Slice 11 tests.

Mirrors the *shape* the generic PDF extractor produces for the owner's real
7SA511 sheet (DIGSI address + name in one cell, then value, then printed range;
a tap table for the nominal current; operating timers whose TAP SETTING cell is
BLANK with ``Infinity`` printed in the range column; scheme notes naming zones). The
numbers are invented for the tests -- the owner's real
sheet and its settings are never committed (they are exercised only when
``RELAY_SAMPLE_PDF_DIR`` is set).

The sheet is built as a real PDF and read back through the real extractor, so
the profile is always tested on genuine ``RawRelayDocument`` output.
"""

from __future__ import annotations

from app.domain.relay_import.raw_document import RawRelayDocument
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import load_spec
from tests.relay_pdf_fixtures import build_pdf, rows_page


# The sheet is data (``tests/relay_conformance/sheets/7sa511.json``, DEC-199): four header lines (the last is the
# nominal-current tap row), then "address name" | value | printed range rows -- a timer's value is "" (the cell is
# blank) with "Infinity" in the range column, exactly as the real sheet has it -- then the scheme notes.
_SPEC = load_spec("7sa511")
HEADER: tuple[tuple[str, ...], ...] = tuple(tuple(line) for line in _SPEC["lines"][:4])
BASE: dict[str, tuple[str, str, str | None]] = {
    line[0].split(" ", 1)[0]: (line[0].split(" ", 1)[1], line[1], line[2] if len(line) > 2 else None)
    for line in _SPEC["lines"][4:]
}
NOTES: tuple[tuple[str, ...], ...] = tuple(tuple(note) for note in _SPEC["notes"])

#: The same timers with ``Infinity`` in the setting (value) column itself -- the one place it
#: would be a configured value.
INFINITY_IN_VALUE_COLUMN: dict[str, tuple[str, str, str | None]] = {
    code: (BASE[code][0], "Infinity", None)
    for code in ("1203", "1305", "1306", "1315", "1316", "1325", "1405", "1406", "1415")
}

#: A finite-delay variant of every operating timer (the sheet normally leaves them blank).
FINITE_TIMERS: dict[str, tuple[str, str, str | None]] = {
    "1203": ("T4", "3", "0.00-32.00 s"),
    "1305": ("T1 1PHASE", "0.1", "0.00-32.00 s"),
    "1306": ("T1 >1PHASE", "0.15", "0.00-32.00 s"),
    "1315": ("T2 1PHASE", "0.4", "0.00-32.00 s"),
    "1316": ("T2 >1PHASE", "0.45", "0.00-32.00 s"),
    "1325": ("T3", "3", "0.00-32.00 s"),
    "1405": ("T1B 1PHASE", "", "Infinity"),
    "1406": ("T1B >1PHASE", "", "Infinity"),
    "1415": ("T1L", "", "Infinity"),
}

def _row(code: str, name: str, value: str, rng: str | None) -> list[str]:
    cells = [f"{code} {name}", value]
    if rng:
        cells.append(rng)
    return cells


def sheet_pdf(
    *,
    overrides: dict[str, tuple[str, str, str | None]] | None = None,
    drop: tuple[str, ...] = (),
    extra: tuple[tuple[str, str, str, str | None], ...] = (),
    notes: tuple[tuple[str, ...], ...] = NOTES,
    header: tuple[tuple[str, ...], ...] = HEADER,
) -> bytes:
    """The sheet as a real PDF. ``overrides`` replace (or add) an address, ``drop``
    removes addresses, ``extra`` appends raw rows ``(code, name, value, range)``."""
    rows = dict(BASE)
    rows.update(overrides or {})
    for code in drop:
        rows.pop(code)
    lines = [list(h) for h in header]
    lines += [_row(code, *cells) for code, cells in sorted(rows.items())]
    lines += [_row(*e) for e in extra]
    lines += [list(n) for n in notes]
    pages = [rows_page(lines[i : i + 40]) for i in range(0, len(lines), 40)]
    return build_pdf(pages)


def make_doc(**kwargs) -> RawRelayDocument:
    result = extract_pdf(sheet_pdf(**kwargs))
    assert result.document is not None
    return result.document
