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
from tests.relay_pdf_fixtures import build_pdf, rows_page

Row = tuple[str, str, str | None]  # name, value, printed range
Section = tuple[str, list[Row]]

HEADER: tuple[tuple[str, ...], ...] = (
    ("LZOP: 275kV AAAA - BBBB No 1", "Scheme: RED670_V1.2_21_F11L"),
    ("Utility ID: 1", "Active Group: SET-TEST-R1"),
    ("TAP NAME", "TAP SETTING", "TAP RANGE"),
)

ON_OFF = "OFF/ON"
DIR_RANGE = "Off/Non-dir/Forw/Rev"


def _ct_channels() -> list[Row]:
    rows: list[Row] = []
    for n, name in ((1, "CH1_IL1"), (2, "CH2_IL2"), (3, "CH3_IL3"), (4, "CH4_IN")):
        rows += [(f"NAMECH{n}", name, None), (f"ChannelType{n}", "CurrentProtection", None),
                 (f"CTsec{n}", "1", "1-10"), (f"CTprim{n}", "1200", "1-99999")]
    for n in (5, 6):  # unused channels keep their defaults
        rows += [(f"NAMECH{n}", f"CH{n}", None), (f"ChannelType{n}", "CurrentProtection", None),
                 (f"CTsec{n}", "1", "1-10"), (f"CTprim{n}", "99999", "1-99999")]
    return rows


def _vt_channels() -> list[Row]:
    rows: list[Row] = []
    for n, name in ((7, "CH7_UL1"), (8, "CH8_UL2"), (9, "CH9_UL3")):
        rows += [(f"NAMECH{n}", name, None), (f"ChannelType{n}", "Voltage", None),
                 (f"VTsec{n}", "110", "0.001-999.999"), (f"VTprim{n}", "220", "0.05-2000")]
    for n in (10, 11):
        rows += [(f"NAMECH{n}", f"CH{n}", None), (f"ChannelType{n}", "Voltage", None),
                 (f"VTsec{n}", "999.999", "0.001-999.999"), (f"VTprim{n}", "2000", "0.05-2000")]
    return rows


def zone_rows(n: int, *, operation="ON", direction="Forward", x1="6", r1="1", x0="18", r0="5", rfpp="7", rfpe="15",
              pp="ON", pe="ON", timer_gate="ON", t="0.15", ibase="1200", ubase="220") -> list[Row]:
    p = f"ZM{n:02d}-:"
    rows: list[Row] = [
        (p + "Operation", operation, ON_OFF), (p + "IBase", ibase, "1-99999"), (p + "UBase", ubase, "0.05-2000"),
        (p + "OperationDir", direction, DIR_RANGE), (p + "X1", x1, "0.1-3000"), (p + "R1", r1, "0.01-1000"),
        (p + "X0", x0, "0.1-9000"), (p + "R0", r0, "0.01-3000"), (p + "RFPP", rfpp, "0.1-3000"),
        (p + "RFPE", rfpe, "0.1-9000"), (p + "OperationPP", pp, ON_OFF), (p + "Timer tPP", timer_gate, ON_OFF),
        (p + "tPP", t, "0-60"), (p + "OperationPE", pe, ON_OFF), (p + "Timer tPE", timer_gate, ON_OFF),
        (p + "tPE", t, "0-60"), (p + "IMinOpPP", "20", "10-1000"), (p + "IMinOpPE", "10", "10-1000"),
    ]
    return rows


def default_sections() -> list[Section]:
    return [
        ("HW Configuration/TRM_61_6U_3I", _ct_channels() + _vt_channels()),
        ("IMP_PROT/DistanceZones/ZMQPDIS:1", zone_rows(1, x1="6", r1="1", x0="18", r0="5", rfpp="7", rfpe="15", t="0.15")),
        ("IMP_PROT/DistanceZones/ZMQPDIS:2", zone_rows(2, x1="11", r1="1.5", x0="30", r0="9", rfpp="10", rfpe="20", t="0.45")),
        ("IMP_PROT/DistanceZones/ZMQPDIS:3", zone_rows(3, x1="20", r1="3", x0="50", r0="15", rfpp="18", rfpe="28", t="3")),
        ("IMP_PROT/DistanceZones/ZMQPDIS:4", zone_rows(
            4, operation="OFF", direction="Off", x1="0.1", r1="0.01", x0="0.1", r0="0.01", rfpp="0.1", rfpe="0.1",
            pp="OFF", pe="OFF", timer_gate="OFF", t="0", ibase="1", ubase="0.05")),
        ("IMP_PROT/DirectionalImpedance/ZDRDIR:1", [
            ("ZD01-:IBase", "1200", "1-99999"), ("ZD01-:ArgNegRes", "115", "90-175"), ("ZD01-:ArgDir", "15", "5-45"),
        ]),
        ("IMP_PROT/FaultLocator/LMBRFLO:1", [
            ("FLO1-:R1L", "1.2", "0.001-1500"), ("FLO1-:X1L", "9", "0.001-1500"),
            ("FLO1-:R0L", "8", "0.001-1500"), ("FLO1-:X0L", "26", "0.001-1500"), ("FLO1-:LineLength", "30", "0-10000"),
        ]),
        ("Communication/Station communication", [("IEC61850:Operation", "ON", ON_OFF)]),  # outside Distance Protection
    ]


NOTES: tuple[tuple[str, ...], ...] = (
    ("Backup 21Z with Delayed Zone 1 scheme requirements:",),
    ("Zone 1", "Forward direction timer set to 0.15s"),
    ("Zone 2", "Forward direction timer set to 0.45s"),
    ("Zone 3", "Forward direction timer set to 3s"),
    ("Zone 4", "Inactive (Having duplicated BB Protection)"),
)


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
