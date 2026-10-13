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
from tests.relay_pdf_fixtures import build_pdf, rows_page

# address -> (name, value, printed range or None), as the sheet prints them. A timer's value
# is "" (the cell is blank) with "Infinity" in the range column, exactly as the real sheet has it.
BASE: dict[str, tuple[str, str, str | None]] = {
    "1101": ("CT STARPNT", "TOWARDS LINE", "TWDS LINE/BUS"),
    "1103": ("Un PRIMARY", "110", "1-1200 kV"),
    "1104": ("Un SECOND.", "100", "80-125 V"),
    "1105": ("In PRIMARY", "800", "10-5000 AMP"),
    "1111": ("Ie CT", "PROTECTED LINE", "Protected,Parallel"),
    "1117": ("RE/RL", "0.7", "-7.00 to 7.00"),
    "1118": ("XE/XL", "0.4", "-7.00 to 7.00"),
    "1119": ("RM/RL", "0", "-7.00 to 7.00"),
    "1120": ("XM/XL", "0", "-7.00 to 7.00"),
    "1122": ("X SEC", "0.4", "0.010-5.000 ohms/km"),
    "1124": ("LINELENGTH", "25", "1.0-550.0 km"),
    "1201": ("DIST.PROT.", "ON", "ON,OFF"),
    "1202": ("DIR. FD&T4", "FORWARDS", "FWD,RVS,N/DIR"),
    "1203": ("T4", "", "Infinity"),
    "1204": ("T5", "Infinity", "Infinity"),
    "1301": ("R1", "2", "0.05-65 ohms"),
    "1302": ("X1", "3", "0.05-130 ohms"),
    "1303": ("R1E", "6", "0.05-130 ohms"),
    "1304": ("DIREC. Z1", "FORWARDS", "FWD,RVS,N/DIR"),
    "1305": ("T1 1PHASE", "", "Infinity"),
    "1306": ("T1 >1PHASE", "", "Infinity"),
    "1311": ("R2", "3", "0.05-65 ohms"),
    "1312": ("X2", "5", "0.05-130 ohms"),
    "1313": ("R2E", "8", "0.05-130 ohms"),
    "1314": ("DIREC. Z2", "FORWARDS", "FWD,RVS,N/DIR"),
    "1315": ("T2 1PHASE", "", "Infinity"),
    "1316": ("T2 >1PHASE", "", "Infinity"),
    "1317": ("TRIP 1P Z2", "NO", "NO,YES"),
    "1321": ("R3", "1", "0.05-65 ohms"),
    "1322": ("X3", "1.5", "0.05-130 ohms"),
    "1323": ("R3E", "3", "0.05-130 ohms"),
    "1324": ("DIREC. Z3", "REVERSE", "FWD,RVS,N/DIR"),
    "1325": ("T3", "", "Infinity"),
    "1401": ("R1B", "3", "0.05-65 ohms"),
    "1402": ("X1B", "5", "0.05-130 ohms"),
    "1403": ("R1BE", "8", "0.05-130 ohms"),
    "1404": ("DIREC. Z1B", "FORWARDS", "FWD,RVS,N/DIR"),
    "1405": ("T1B 1PHASE", "", "Infinity"),
    "1406": ("T1B >1PHASE", "", "Infinity"),
    "1411": ("R1L", "65", "0.05-65 ohms"),
    "1412": ("X1L", "130", "0.05-130 ohms"),
    "1413": ("R1LE", "130", "0.05-130 ohms"),
    "1414": ("DIREC. Z1L", "NON-DIRECTIONAL", "FWD,RVS,N/DIR"),
    "1415": ("T1L", "", "Infinity"),
    "1621": ("X+A", "20", "0.10-200.00 ohms"),
    "1622": ("X-A", "2", "0.10-200.00 ohms"),
    "1623": ("RA1", "6", "0.10-200.00 ohms"),
    "1703": ("PHPHE FLTS", "PHASE-PHASE ONLY", "PP,LEAD-PE,LAG-PE"),
    "1704": ("3PH FAULTS", "PHASE-PHASE ONLY", "EF,PP,PE"),
    "1705": ("1PH FAULTS", "PHASE-EARTH", "PE,PP"),
    "2002": ("P/S PROGR.", "BLOCK ALL", "BKA,BKZ1,BKANZ1,OOS"),
    "6101": ("BINARY INPUT 1", "As per design at site", None),  # outside Distance Protection
    "7812": ("DIST. PROT.", "EXIST", "EXIST,NOEXIST"),
}

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

# Scheme notes, one cell each (a name/value pair where the sheet prints two cells).
NOTES: tuple[tuple[str, ...], ...] = (
    ("Change Protection Scheme from 21Z Main to 21Z Backup with Z1 Delayed",),
    ("a) To confirm CT ratio", "800/1"),
    ("Zone 1", "Forward direction timer set to 0.15s (Delayed Zone 1)"),
    ("Zone 1B Inactive timer set to oos (Infinity)",),
    ("Zone 2", "Forward direction timer set to 0.45s"),
    ("Zone 3", "Reverse direction timer set to 3s"),
    ("Zone 4", "Forward direction timer set to 3s"),
)

HEADER = (
    ("LZOP: 132kV AAAA - BBBB No. 1", "Scheme: 7SA511_V3.2_1A"),
    ("Utility ID: 1", "Active Group: Rev0-Endorsed"),
    ("TAP NAME", "TAP SETTING", "TAP RANGE"),
    ("IN", "1", "1 AMP"),
)


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
