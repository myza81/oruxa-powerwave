"""Synthetic setting sheets for the remaining relay families (REL670, REL511, 7SL87, 7SA613, GRZ100, GRL200,
RCS-941, LFZP111, RELZ100).

Each mirrors the *shape* the generic PDF extractor produces for the owner's real sheet of that family
(names, value / range columns, blank setting cells, scheme notes); the numbers are invented for the tests.
The owner's real sheets are never committed (they are exercised only when ``RELAY_SAMPLE_PDF_DIR`` is set).
Every sheet is built as a real PDF and read back through the real extractor.
"""

from __future__ import annotations

from tests.relay_pdf_fixtures import build_pdf, rows_page

Row = tuple[str, ...]

#: Column x positions for sheets whose setting names are long (DIGSI 5 addresses, GR200 paths): the real
#: sheets print them in a wide name column, so the value column must not start inside the name.
WIDE_COLUMNS = (20, 330, 440, 520)


def _page(lines: list[list[str]], columns: tuple[int, ...] | None) -> list[tuple[int, int, str]]:
    if columns is None:
        return rows_page(lines)
    items, y = [], 780
    for row in lines:
        items += [(x, y, cell) for cell, x in zip(row, columns, strict=False)]
        y -= 15
    return items


def sheet_pdf(scheme: str, rows: list[Row], notes: list[Row] = (), *, active_group: str = "Rev0-Endorsed",
              columns: tuple[int, ...] | None = None) -> bytes:
    lines: list[list[str]] = [
        ["LZOP: 132kV AAAA - BBBB No. 1", f"Scheme: {scheme}"],
        ["Utility ID: 1", f"Active Group: {active_group}"],
        ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ]
    lines += [list(r) for r in rows]
    lines += [["NOTES:"]] + [list(n) for n in notes]
    per_page = 40 if columns is None else 50
    pages = [_page(lines[i : i + per_page], columns) for i in range(0, len(lines), per_page)]
    return build_pdf(pages)


# --- Hitachi Energy / ABB REL670 (Relion 670; channel names IL1..UL3 with no ChannelType rows) ------------

def _rel670_zone(n: int, op: str, direction: str, x: str, rfpp: str, rfpe: str, timer: str, t: str) -> list[Row]:
    p = f"ZM0{n}-:"
    return [
        (f"IMP_PROT/DistanceZones/ZMQPDIS:{n}",),
        (p + "Operation", op, "OFF/ON"), (p + "IBase", "1200", "1-99999"), (p + "UBase", "132", "0.05-2000"),
        (p + "OperationDir", direction, "Off/Non-dir/Forw/Rev"), (p + "X1", x, "0.1-3000"), (p + "R1", "1", "0.01-1000"),
        (p + "X0", "18", "0.1-9000"), (p + "R0", "4", "0.01-3000"), (p + "RFPP", rfpp, "0.1-3000"), (p + "RFPE", rfpe, "0.1-9000"),
        (p + "OperationPP", "ON", "OFF/ON"), (p + "Timer tPP", timer, "OFF/ON"), (p + "tPP", t, "0-60"),
        (p + "OperationPE", "ON", "OFF/ON"), (p + "Timer tPE", timer, "OFF/ON"), (p + "tPE", t, "0-60"),
    ]


REL670_ROWS: list[Row] = [
    ("HW Configuration/BIM3",), ("BIM3:Operation", "ON", "OFF/ON"), ("BIM3:OscRelease", "30", "1-30"),
    ("HW Configuration/TRM_61_6U_3I",),
    ("NAMECH1", "IL1"), ("CTsec1", "1", "1-10"), ("CTprim1", "1200", "1-99999"),
    ("NAMECH2", "IL2"), ("CTsec2", "1", "1-10"), ("CTprim2", "1200", "1-99999"),
    ("NAMECH3", "IL3"), ("CTsec3", "1", "1-10"), ("CTprim3", "1200", "1-99999"),
    ("NAMECH4", "IN"), ("CTsec4", "1", "1-10"), ("CTprim4", "600", "1-99999"),       # residual: never read
    ("NAMECH7", "UL1"), ("VTsec7", "110", "0.001-999.999"), ("VTprim7", "132", "0.05-2000"),
    ("NAMECH8", "UL2"), ("VTsec8", "110", "0.001-999.999"), ("VTprim8", "132", "0.05-2000"),
    ("NAMECH9", "UL3"), ("VTsec9", "110", "0.001-999.999"), ("VTprim9", "132", "0.05-2000"),
    *_rel670_zone(1, "ON", "Forward", "6", "8", "12", "ON", "0.2"),
    *_rel670_zone(2, "ON", "Reverse", "2", "3", "5", "OFF", "1"),
    ("IMP_PROT/DirectionalImpedance/ZDRDIR:1",),
    ("ZD01-:ArgNegRes", "115", "90-175"), ("ZD01-:ArgDir", "15", "5-45"),
    ("IMP_PROT/FaultLocator/LMBRFLO:1",),
    ("FLO1-:R1L", "0.5", "0.001-1500"), ("FLO1-:X1L", "3", "0.001-1500"),
    ("FLO1-:R0L", "1.5", "0.001-1500"), ("FLO1-:X0L", "9", "0.001-1500"), ("FLO1-:LineLength", "10", "0-10000"),
]
REL670_NOTES: list[Row] = [("Zone 1 Forward direction timer set to 0.15s",), ("Zone 2 Reverse direction timer set to 3s",)]


def rel670_pdf(rows: list[Row] = REL670_ROWS) -> bytes:
    return sheet_pdf("REL670_V1.2_21", rows, REL670_NOTES)


# --- Hitachi Energy / ABB REL511 ------------------------------------------------------------------------------

REL511_ROWS: list[Row] = [
    ("Ur", "110", "100/110/115/120"), ("Ir", "1", "1"),
    ("VTPrim Uphases", "132", "1-9999"), ("CTPrim Iphases", "600", "1-9999"),
    ("Operation_Z1", "On", "On/Off"), ("X1Z1", "3", "0.1-150"), ("R1Z1", "0.5", "0.1-150"), ("X0Z1", "9", "0.1-1200"),
    ("R0Z1", "3", "0.1-1200"), ("RFZ1", "4.6", "0.1-150"), ("RFNZ1", "15", "0.1-150"), ("Timer t1", "On", "On/Off"),
    ("t1", "0", "0.0-10.0 s"), ("DirZ1", "Forward", "Non/Forward/Reverse"), ("Z1Block", "On", "On/Off"),
    ("Operation_Z2", "Off", "On/Off"), ("X1Z2", "5", "0.1-150"), ("R1Z2", "0.9", "0.1-150"), ("X0Z2", "14", "0.1-1200"),
    ("R0Z2", "4.5", "0.1-1200"), ("RFZ2", "6", "0.1-150"), ("RFNZ2", "17", "0.1-150"), ("Timer t2", "Off", "On/Off"),
    ("t2", "10", "0.0-10.0 s"), ("DirZ2", "None", "Non/Forward/Reverse"), ("Z2Block", "Off", "On/Off"),
    ("Operation_PSB", "On", "On/Off"),
    ("Length unit", "KM", "KM/MI"), ("Line Length", "16", "0-10,000"),
    ("X1", "4.4", "0.001-1500.0 ohms"), ("R1", "0.8", "0.001-1500.0 ohms"),
    ("X0", "13", "0.001-1500.0 ohms"), ("R0", "4", "0.001-1500.0 ohms"),
]
REL511_NOTES: list[Row] = [("Zone 1 Forward direction timer set to 0s",)]


def rel511_pdf() -> bytes:
    return sheet_pdf("REL511_V1.2_TNB", REL511_ROWS, REL511_NOTES)


# --- Siemens SIPROTEC 5 7SL87 -----------------------------------------------------------------------------------

def _7sl87_zone(n: int, mode: str, direction: str, x: str, r_pp: str, r_pg: str, spec: str) -> list[Row]:
    p = f"21.901.357{n}."
    return [
        (f"21 Distance prot.1 > Z{n}",),
        (p + "1 Mode", mode, "off/on/test"), (p + "2 Operate & flt.rec. blocked", "NO", "NO/YES"),
        (p + "101 Function mode", "ph-gnd and ph-ph", "SIP5_Function mode"),
        (p + "114 Zone-spec. residu. comp.", spec, "NO/YES"), (p + "109 Directional mode", direction, "Fwd/Rev/Non-dir"),
        (p + "102 X reach", x, "0.05-600"), (p + "103 R (ph-g)", r_pg, "0.05-600"), (p + "104 R (ph-ph)", r_pp, "0.05-600"),
        (p + "113 Zone-inclination angle", "0", "0-45"),
        (p + "110 Operate delay (1-phase)", "", "Infinity"), (p + "112 Operate delay (multi-ph.)", "", "Infinity"),
        (p + "105 Kr", "1.7", "-0.33-11"), (p + "106 Kx", "0.6", "-0.33-11"),
        (p + "107 K0", "0", "0-11"), (p + "108 Angle (K0)", "0", "-180-180"),
    ]


SL87_ROWS: list[Row] = [
    ("Type", "7SL87"), ("Edit mode", "Primary", "Edit Mode"),
    ("91.115 Set. format residu. comp.", "Kr, Kx", "KR, Kx/K0"),
    ("11.931.8881.101 Rated primary current", "1500", "1-100000"),
    ("11.931.8881.102 Rated secondary current", "1", "1-5"),
    ("11.941.8911.101 Rated primary voltage", "275", "0.2-1200"),
    ("11.941.8911.102 Rated secondary voltage", "110", "80-230"),
    ("21.9001.114 Line length", "20", "0.1-1000"), ("21.9001.108 Line angle", "82.7", "10-89"),
    ("21.901.2311.107 Dist. characteristic angle", "82.7", "30-90"),
    *_7sl87_zone(1, "on", "Forward", "4.7", "3.1", "11", "YES"),
    *_7sl87_zone(2, "off", "Reverse", "10", "5", "10", "NO"),
]
SL87_NOTES: list[Row] = [("Zone 1", "Forward direction timer set to 0.15s"), ("Zone 2", "Inactive (duplicated protection)")]


def sl87_pdf() -> bytes:
    return sheet_pdf("7SL87_8.81", SL87_ROWS, SL87_NOTES, columns=WIDE_COLUMNS)


# --- Siemens SIPROTEC 4 7SA613 -----------------------------------------------------------------------------------

SA613_ROWS: list[Row] = [
    ("0203 Unom PRIMARY", "275", "1-1200 kV"), ("0204 Unom SECONDARY", "110", "80-125 V"),
    ("0205 CT PRIMARY", "1200", "10-5000 AMP"), ("0206 CT SECONDARY", "1", "1 AMP"),
    ("0236 Distance Unit", "km", "km/Miles"), ("0237 Format Z0/Z1", "RE/RL and XE/XL", "K0 Setting Format"),
    ("1105 Line Angle", "82", "30-89 deg."), ("1111 Line Length", "20", "1-1000 km"),
    ("1116 RE/RL(Z1)", "1.5", "-0.33-7"), ("1117 XE/XL(Z1)", "0.5", "-0.33-7"),
    ("1118 RE/RL(Z1B...Z5)", "1.5", "-0.33-7"), ("1119 XE/XL(Z1B...Z5)", "0.5", "-0.33-7"),
    ("1201 FCT Distance", "ON", "ON,OFF"), ("1211 Distance Angle", "82", "30-89 deg."),
    ("1301 Op. mode Z1", "Forward", "Fwd/Rev/Non/Inactive"), ("1302 R(Z1) ph-ph", "1.5", "0.05-250 ohms"),
    ("1303 X(Z1)", "2.4", "0.05-250 ohms"), ("1304 RE(Z1) ph-E", "7.8", "0.05-250 ohms"),
    ("1307 Zone Reduction", "0", "0-45 deg."),
    ("1305 T1-1phase", "", "Infinity"), ("1306 T1-multi-phase", "", "Infinity"),
    ("1331 Op. mode Z4", "Inactive", "Fwd/Rev/Non/Inactive"), ("1332 R(Z4) ph-ph", "250", "0.05-250 ohms"),
    ("1333 X(Z4)", "250", "0.05-250 ohms"), ("1335 T4 DELAY", "Infinity", "Infinity"),
    ("1341 Op. mode Z5", "Non-Directional", "Fwd/Rev/Non/Inactive"), ("1342 R(Z5) ph-ph", "2.9", "0.05-250 ohms"),
    ("1343 X(Z5)+", "10", "0.05-250 ohms"), ("1346 X(Z5)-", "7", "0.05-250 ohms"),
]
SA613_NOTES: list[Row] = [("Zone 1 Forward direction timer set to 0.15s",)]


def sa613_pdf() -> bytes:
    return sheet_pdf("7SA6131_4AB02_3GA0", SA613_ROWS, SA613_NOTES)


# --- Toshiba GRZ100 ---------------------------------------------------------------------------------------------

GRZ100_ROWS: list[Row] = [
    ("[Parameter]",), ("VT", "1200", "1-20000"), ("CT", "1200", "1-20000"),
    ("X1", "6.7", "0.0-999.9 ohms"), ("X0", "21", "0.0-999.9 ohms"), ("R1", "1.2", "0.0-999.9 ohms"),
    ("R0", "7", "0.0-999.9 ohms"), ("Line", "24.9", "0.0-399.9 km"),
    ("[Trip/Com(Sw)]",), ("ZS-C", "Quad", "Mho/Quad"), ("ZG-C", "Mho", "Mho/Quad"),
    ("[Trip/Com(Ele)]",), ("Z1S", "5.72", "0.10-250.00 ohms"), ("Z1S-angle1", "0", "0-45 degree"),
    ("BFRS", "20", "0.5-100.0 ohms"), ("BFLS-angle", "120", "90-135 degree"),
    ("TZ1S", "0", "0.00-10.00 s"), ("TZ2S", "0.3", "0.00-10.00 s"),
    ("Z1G", "5.72", "0.10-250.00 ohms"), ("TZ1G", "0", "0.00-10.00 s"), ("Krs", "560", "0-1000 %"),
]
GRZ100_NOTES: list[Row] = [("Zone 1", "Forward direction timer set to 0.0s"), ("Zone R2", "Reverse direction timer set to 3s")]


def grz100_pdf() -> bytes:
    return sheet_pdf("GRZ100_201A_Ver2.1", GRZ100_ROWS, GRZ100_NOTES)


# --- Toshiba GRL200 ---------------------------------------------------------------------------------------------

_ZS, _ZG = "Prot/G1/Trip/Distance_ZS/", "Prot/G1/Trip/Distance_ZG/"
GRL200_ROWS: list[Row] = [
    ("Active Group", "1", "1-8"),
    ("Fault Locator/FL_Unit", "km", "km/mile"), ("Fault Locator/FL_1Line_km", "17.6", "0-500"),
    ("Fault Locator/Line1/FL_1X1", "4.76", "0-1000"), ("Fault Locator/Line1/FL_1R1", "0.45", "0-1000"),
    ("Fault Locator/Line1/FL_1X0", "12.58", "0-1000"), ("Fault Locator/Line1/FL_1R0", "3.89", "0-1000"),
    (_ZS + "Common/ZS-Chara", "MHO", "MHO;QUAD"), (_ZG + "Common/ZG-Chara", "QUAD", "MHO;QUAD"),
    (_ZS + "Z1S-EN", "On", "Off/On"), (_ZS + "Z1S-Dir", "Forward", "Forward/Rever/NonDir"),
    (_ZS + "Z1S-Mho.Angle", "85", "30-90"), (_ZS + "Z1S-Mho.Reach", "3.59", "0.1-500"),
    (_ZS + "Z1S-R.Reach", "4.2", "0.1-500"), (_ZS + "Z1S-R.Angle", "75", "30-90"), (_ZS + "TZ1S", "0.15", "0-100"),
    (_ZS + "Z2S-EN", "Off", "Off/On"), (_ZS + "Z2S-Dir", "Reverse", "Forward/Rever/NonDir"),
    (_ZG + "Z1G-EN", "On", "Off/On"), (_ZG + "Z1G-Dir", "Forward", "Forward/Rever/NonDir"),
    (_ZG + "Z1G-R.Reach", "15", "0.1-500"), (_ZG + "Z1G-X.Reach", "3.57", "0.1-500"),
    (_ZG + "Z1G-I0K/Z1G-Krs", "856", "0-1000"), (_ZG + "TZ1G", "0.15", "0-100"),
    (_ZG + "Z2G-EN", "Off", "Off/On"), (_ZG + "Z2G-Dir", "Forward", "Forward/Rever/NonDir"),
]


def grl200_pdf() -> bytes:
    return sheet_pdf("GRL200_TNB", GRL200_ROWS, [("CT Ratio @ ATWR", ": 2500/1")], columns=WIDE_COLUMNS)


# --- NR Electric RCS-941 -----------------------------------------------------------------------------------------

RCS941_ROWS: list[Row] = [
    ("U1n", "76.2", "10-655.35 kV"), ("U2n", "63.5", "57.73-100 V"), ("I1n", "1200", "0-13107 A"), ("I2n", "1", "1A"),
    ("K0", "0.83", "0-2"),
    ("Z_PG1", "0.53", "0.05-200 Ohms"), ("t_Z1", "0.15", "0-25 s"), ("Z_PP1", "0.53", "0.05-200 Ohms"),
    ("Z_PG2", "1.23", "0.05-200 Ohms"), ("t_PG2", "0.45", "0-25 s"), ("Z_PP2", "1.23", "0.05-200 Ohms"),
    ("t_PP2", "0.45", "0-25 s"), ("Z_Rev", "0.15", "0.05-200 Ohms"), ("t_Rev", "3", "0-25 s"),
    ("R1_Quad", "2.44", "0.05-200 Ohms"), ("R2_Quad", "4.92", "0.05-200 Ohms"), ("phi1_Reach", "80", "45-89 deg"),
    ("X1L", "0.76", "0-655.35"), ("R1L", "0.13", "0-655.35"), ("X0L", "2.59", "0-655.35"), ("R0L", "0.59", "0-655.35"),
    ("LineLength", "2.62", "0-655.35"),
    ("En_ZPG1", "1", "0/1"), ("En_ZPG2", "0", "0/1"), ("En_ZPP1", "1", "0/1"), ("En_ZPP2", "1", "0/1"),
    ("En_ZPG_Rev", "1", "0/1"), ("En_ZPP_Rev", "1", "0/1"), ("En_ZPG1_Quad", "1", "0/1"), ("En_ZPG2_Quad", "0", "0/1"),
]
RCS941_NOTES: list[Row] = [("Zone 1", "Forward direction timer set to 0.15s"), ("Zone 3R Reverse direction timer set to 3s",)]


def rcs941_pdf() -> bytes:
    return sheet_pdf("RCS-941_MY_1A", RCS941_ROWS, RCS941_NOTES)


# --- LFZP111 -------------------------------------------------------------------------------------------------------

LFZP_ROWS: list[Row] = [
    ("In", "1", "1 or 5"), ("KZPh", "0.39", "0.040-1.000"), ("KZ1", "1", "1.00-49.98"), ("KZ2", "1.64", "1.00-49.98"),
    ("KZ3", "4.46", "1.00-49.98"), ("CT Ratio (N:1)", "600", "10:1 - 2000:1"), ("VT Ratio (N:1)", "1200", "10:1 - 5000:1"),
    ("Line Length", "10.9", "0-1000"), ("ZONE 1 TRIPPING", "ENABLED", "ENABLED/BLOCKED"),
    ("Z2(T) TRIPPING", "BLOCKED", "ENABLED/BLOCKED"), ("Z3(T) TRIPPING", "ENABLED", "ENABLED/BLOCKED"),
    ("DIST G CHARACTERISTIC", "QUADRILATERAL", "MHO/QUAD"), ("LINE UNITS", "Km", "Km/Miles/100%"),
]


def lfzp_pdf() -> bytes:
    return sheet_pdf("LFZP111_1A", LFZP_ROWS)


# --- RELZ100 ---------------------------------------------------------------------------------------------------------

RELZ_ROWS: list[Row] = [
    ("Ref_Transf:CT_Prim", "1200", "1-9999"), ("Ref_Transf:CT_Sec", "1", "1"),
    ("Ref_Transf:VT_Prim", "132", "1-999"), ("Ref_Transf:VT_Sec", "0.11", "0.10, 0.11"),
    ("Ref_Line:Length", "16.23", "0-10000"), ("Ref_Line:X1", "0.74", "0.001-1500"), ("Ref_Line:R1", "4.381", "0.001-1500"),
    ("Ref_Line:X0", "4.178", "0.001-1500"), ("Ref_Line:R0", "13.676", "0.001-1500"),
    ("Z<Prot_Zone1:X1", "3.91", "0.1-150.0"), ("Z<Prot_Zone1:R1", "5.69", "0.1-150.0"), ("Z<Prot_Zone1:KN1", "0.7", "-3.0-3.0"),
    ("Z<Prot_Zone1:RN1", "16.69", "0.1-150.0"), ("Z<Prot_Zone1:T1", "0", "0-10.0"),
    ("Z<Prot_Zone4:X4", "11.81", "0.1-150.0"), ("Z<Prot_Zone4:R4", "8.21", "0.1-150.0"), ("Z<Prot_Zone4:T4", "0", "0-10.0"),
    ("Z<Prot_Zone5:X5", "150", "0.1-150.0"), ("Z<Prot_Zone5:T5", "10", "0-10.0"),
    ("Ref_Line:Length_Unit", "km", "km/mi"), ("Z<Prot_Zone1:TimerT1", "ON", "ON/OFF"),
    ("Z<Prot_Zone4:TimerT4", "ON", "ON/OFF"), ("Z<Prot_Zone4:Dir", "NonDirectional", "NonDir/Rev/Fwd"),
    ("Z<Prot_Zone5:TimerT5", "OFF", "ON/OFF"),
]


def relz100_pdf() -> bytes:
    return sheet_pdf("RELZ100_3.0_OPS_A1", RELZ_ROWS, [("Setting based on line length 16.23km",)])
