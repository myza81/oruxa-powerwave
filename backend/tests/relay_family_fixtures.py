"""Synthetic setting sheets for the remaining relay families (REL670, REL511, 7SL87, 7SA613, GRZ100, GRL200,
RCS-941, LFZP111, RELZ100).

The sheets themselves are data: ``tests/relay_conformance/sheets/<id>.json`` (DEC-199, the single source shared with
the browser tests). Each mirrors the *shape* the generic PDF extractor produces for the owner's real sheet of that family
(names, value / range columns, blank setting cells, scheme notes); the numbers are invented for the tests. The owner's
real sheets are never committed (they are exercised only when ``RELAY_SAMPLE_PDF_DIR`` is set). Every sheet is built
as a real PDF and read back through the real extractor. The functions below only name the cells a test varies.
"""

from __future__ import annotations

from tests.relay_conformance.sheet_spec import sheet_pdf


def rel670_pdf() -> bytes:
    return sheet_pdf("rel670")


def rel511_pdf() -> bytes:
    return sheet_pdf("rel511")


def sl87_pdf(*, tilt: str = "0", angle: str = "82.7", function_mode: str = "ph-gnd and ph-ph", z1_delays: tuple[str, str] = ("", ""),
             load_cutout_pp: str | None = "YES") -> bytes:
    """``tilt`` replaces every zone's Zone-inclination angle cell ("" = a blank cell beside its range); ``angle`` the
    distance characteristic angle; ``function_mode`` Zone 1's Function mode; ``z1_delays`` Zone 1's (1-phase, multi-ph.)
    operate-delay cells (blank by default, as on the owner sheet); ``load_cutout_pp`` the 'Use ph-ph load cutout' cell
    (``None`` drops the phase-phase load-cutout rows)."""
    cells = {
        "21.901.3571.113 Zone-inclination angle": tilt, "21.901.3572.113 Zone-inclination angle": tilt,
        "21.901.2311.107 Dist. characteristic angle": angle, "21.901.3571.101 Function mode": function_mode,
        "21.901.3571.110 Operate delay (1-phase)": z1_delays[0], "21.901.3571.112 Operate delay (multi-ph.)": z1_delays[1],
    }
    if load_cutout_pp is None:
        return sheet_pdf("7sl87", {"set": cells, "drop": ["21.901.3661.105 Use ph-ph load cutout",
                                                          "21.901.3661.106 R load cutout (ph-ph)",
                                                          "21.901.3661.107 Angle load cutout (ph-ph)"]})
    return sheet_pdf("7sl87", {"set": {**cells, "21.901.3661.105 Use ph-ph load cutout": load_cutout_pp}})


def sa613_pdf(*, angle: str = "82", zone_reduction: str = "0", r_load_pp: str = "", z1_delays: tuple[str, str] = ("", ""),
              z5_mode: str = "Non-Directional") -> bytes:
    """The owner sheet's shape (invented numbers): blank Z1 delay cells, 'Infinity' T4 / T5 / T1B, a blank R load
    (ph-ph) beside an 'Infinity' range. ``angle`` sets 1211 Distance Angle, ``zone_reduction`` 1307, ``r_load_pp``
    1243 ("" = blank), ``z1_delays`` the (T1-1phase, T1-multi-phase) cells and ``z5_mode`` Zone 5's Op. mode."""
    return sheet_pdf("7sa613", {"set": {
        "1211 Distance Angle": angle, "1307 Zone Reduction": zone_reduction, "1243 R load (ph-ph)": r_load_pp,
        "1305 T1-1phase": z1_delays[0], "1306 T1-multi-phase": z1_delays[1], "1341 Op. mode Z5": z5_mode,
    }})


def grz100_pdf(*, zs_c: str = "Quad", zg_c: str = "Mho", z1_angle1: str = "0", plc: str | None = "TNBGRZ100-01(FFF",
               bt: dict[str, str] | None = None) -> bytes:
    """The owner sheet's shape (invented numbers): every distance zone with its phase (S) and earth (G) element, the
    backup-trip switches and the site PLC program name. ``zg_c`` defaults to Mho (a phase / earth characteristic
    mismatch); ``z1_angle1`` sets Z1S-angle1, ``plc`` the 'PLC data' row (None drops it) and ``bt`` overrides
    backup-trip switches by name (e.g. ``{"ZR2BT": "Off"}``)."""
    cells = {"ZS-C": zs_c, "ZG-C": zg_c, "Z1S-angle1": z1_angle1, **(bt or {})}
    if plc is None:
        return sheet_pdf("grz100", {"set": cells, "drop": ["PLC data"]})
    return sheet_pdf("grz100", {"set": {**cells, "PLC data": plc}})


def grl200_pdf() -> bytes:
    return sheet_pdf("grl200")


def rcs941_pdf() -> bytes:
    return sheet_pdf("rcs941")


def lfzp_pdf() -> bytes:
    return sheet_pdf("lfzp111")


def relz100_pdf() -> bytes:
    return sheet_pdf("relz100")
