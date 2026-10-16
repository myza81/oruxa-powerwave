"""A synthetic Hitachi Energy RED670-shaped setting sheet for Slice 12 tests.

Mirrors the *shape* the generic PDF extractor produces for the owner's real RED670 sheet: a
``Scheme:`` header, ``name | value | range`` rows, function-instance section headings
(``IMP_PROT/DistanceZones/ZMQPDIS:1``), instance-prefixed parameters (``ZM01-:X1``), channel-numbered
CT / VT rows and the page-end scheme notes. The numbers are invented for the tests -- the owner's real
sheet and its settings are never committed (they are exercised only when ``RELAY_SAMPLE_PDF_DIR`` is set).

The sheet is built as a real PDF and read back through the real extractor, so the profile is always
tested on genuine ``RawRelayDocument`` output.
"""

from __future__ import annotations

from app.domain.relay_import.raw_document import RawRelayDocument
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import load_spec
from tests.relay_pdf_fixtures import build_pdf, rows_page

Row = tuple[str, str, str | None]  # name, value, printed range
Section = tuple[str, list[Row]]


ON_OFF = "OFF/ON"
DIR_RANGE = "Off/Non-dir/Forw/Rev"

# The default sheet is data (``tests/relay_conformance/sheets/red670.json``, DEC-199): three header lines, then
# function-instance sections (a one-cell heading such as ``IMP_PROT/DistanceZones/ZMQPDIS:1`` followed by its
# ``name | value | range`` rows), then the scheme notes.
_SPEC = load_spec("red670")
HEADER: tuple[tuple[str, ...], ...] = tuple(tuple(line) for line in _SPEC["lines"][:3])
NOTES: tuple[tuple[str, ...], ...] = tuple(tuple(note) for note in _SPEC["notes"])


def zone_rows(n: int, *, operation="ON", direction="Forward", x1="6", r1="1", x0="18", r0="5", rfpp="7", rfpe="15",
              pp="ON", pe="ON", timer_gate="ON", t="0.15", ibase="1200", ubase="220") -> list[Row]:
    """One ZMQPDIS instance's rows, for tests that build their own sections (the default zones are in the spec)."""
    p = f"ZM{n:02d}-:"
    return [
        (p + "Operation", operation, ON_OFF), (p + "IBase", ibase, "1-99999"), (p + "UBase", ubase, "0.05-2000"),
        (p + "OperationDir", direction, DIR_RANGE), (p + "X1", x1, "0.1-3000"), (p + "R1", r1, "0.01-1000"),
        (p + "X0", x0, "0.1-9000"), (p + "R0", r0, "0.01-3000"), (p + "RFPP", rfpp, "0.1-3000"),
        (p + "RFPE", rfpe, "0.1-9000"), (p + "OperationPP", pp, ON_OFF), (p + "Timer tPP", timer_gate, ON_OFF),
        (p + "tPP", t, "0-60"), (p + "OperationPE", pe, ON_OFF), (p + "Timer tPE", timer_gate, ON_OFF),
        (p + "tPE", t, "0-60"), (p + "IMinOpPP", "20", "10-1000"), (p + "IMinOpPE", "10", "10-1000"),
    ]


def default_sections() -> list[Section]:
    sections: list[Section] = []
    for line in _SPEC["lines"][3:]:
        if len(line) == 1:
            sections.append((line[0], []))
        else:
            sections[-1][1].append((line[0], line[1], line[2] if len(line) > 2 else None))
    return sections

def sheet_pdf(
    *,
    overrides: dict[str, tuple[str, str | None]] | None = None,
    drop: tuple[str, ...] = (),
    sections: list[Section] | None = None,
    extra: tuple[Row, ...] = (),
    notes: tuple[tuple[str, ...], ...] = NOTES,
    header: tuple[tuple[str, ...], ...] = HEADER,
) -> bytes:
    """The sheet as a real PDF. ``overrides`` replace a parameter's ``(value, range)`` by exact name,
    ``drop`` removes parameters, ``extra`` appends rows, ``sections`` replaces the default sections."""
    overrides = overrides or {}
    lines: list[list[str]] = [list(h) for h in header]
    for label, rows in sections or default_sections():
        lines.append([label])
        for name, value, rng in rows:
            if name in drop:
                continue
            value, rng = overrides.get(name, (value, rng))
            lines.append([name, value] + ([rng] if rng else []))
    for name, value, rng in extra:
        lines.append([name, value] + ([rng] if rng else []))
    lines += [list(n) for n in notes]
    pages = [rows_page(lines[i : i + 40]) for i in range(0, len(lines), 40)]
    return build_pdf(pages)


def make_doc(**kwargs) -> RawRelayDocument:
    result = extract_pdf(sheet_pdf(**kwargs))
    assert result.document is not None
    return result.document
