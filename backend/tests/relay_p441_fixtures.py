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

# code -> (name, value, printed range), as the sheet prints them.
BASE: dict[str, tuple[str, str, str | None]] = {
    "0903": ("Active Settings", "Group 1", "Grp 1/2/3/4"),
    "090D": ("Dist. Protection", "Enabled", "Enabled/Disabled"),
    "092E": ("Setting Values", "Secondary", "Sec'y/Primary"),
    "0A01": ("Main VT Primary", "132000", "100-1000000V"),
    "0A02": ("Main VT Sec'y", "110", "80-140V"),
    "0A07": ("Phase CT Primary", "1200", "1-30000A"),
    "0A08": ("Phase CT Sec'y", "1", "1A/5A"),
    "0D02": ("Local Values", "Primary", "Sec'y/Primary"),
    "0D07": ("Distance Unit", "Kilometres", "Miles/km"),
    "3002": ("Line Length", "7.03", "0.3-1000"),
    "3004": ("Line Impedance", "2", "0.001-500 /I1"),
    "3005": ("Line Angle", "80", "-90 to +90 deg."),
    "3007": ("Zone Status", "01010", "P441 Zone Status"),
    "3008": ("kZ1 Res Comp", "0.718", "0-7"),
    "3009": ("kZ1 Angle", "-11.5", "-180 to +180 deg."),
    "300A": ("Z1", "1.43", "0.001-500 /I1"),
    "300B": ("Z1X", "0.001", "0.001-500 /I1"),
    "300C": ("R1G", "7.02", "0-400 /I1"),
    "300D": ("R1Ph", "2.11", "0-400 /I1"),
    "300E": ("tZ1", "0", "0-10.0 s"),
    "300F": ("kZ2 Res Comp", "0.706", "0-7"),
    "3010": ("kZ2 Angle", "-11.4", "-180 to +180 deg."),
    "3011": ("Z2", "2.13", "0.001-500 /I1"),
    "3012": ("R2G", "10.47", "0-400 /I1"),
    "3013": ("R2Ph", "3.14", "0-400 /I1"),
    "3014": ("tZ2", "0.3", "0-10.0 s"),
    "3015": ("kZ3/4 Res Comp", "0.715", "0-7"),
    "3016": ("kZ3/4 Angle", "-11.5", "-180 to +180 deg."),
    "3017": ("Z3", "4.48", "0.001-500 /I1"),
    "3018": ("R3G-R4G", "17.19", "0-400 /I1"),
    "3019": ("R3Ph-R4Ph", "6.34", "0-400 /I1"),
    "301A": ("tZ3", "3", "0-10.0 s"),
    "301B": ("Z4", "0.36", "0.001-500 /I1"),
    "301C": ("tZ4", "3", "0-10.0 s"),
    "301D": ("ZoneP - Direct", "Directional Fwd", "Directional FWD/REV"),
    "301E": ("kZp Res Comp", "0", "0-7"),
    "301F": ("kZp Angle", "0", "-180 to +180 deg."),
    "3020": ("Zp", "0.001", "0.001-500 /I1"),
    "3021": ("RpG", "0", "0-400 /I1"),
    "3022": ("RpPh", "0", "0-400 /I1"),
    "3023": ("tZp", "10", "0-10.0 s"),
    "3026": ("Z1m Tilt Angle", "0", "-45 to 45 deg."),
    "3027": ("Z1p Tilt Angle", "0", "-45 to 45 deg."),
    "3028": ("Z2/Zp Tilt Angle", "0", "-45 to 45 deg."),
    "3103": ("Fault Type", "Both Enabled", "44x Fault Type"),
    "4602": ("VTS Time Delay", "5", "1-20"),  # outside Distance Protection
}

NOTES = (
    "Zone 2 Forward direction timer set to 0.3s",
    "Zone 3 Forward direction timer set to 3s",
    "Zone 4 Defeated",
)

SCHEME_ROW = ("LZOP: 132kV AAAA - BBBB", "Scheme: SE_P441?A1???038?JE")


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
