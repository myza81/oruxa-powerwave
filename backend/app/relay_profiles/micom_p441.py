"""MiCOM P441 engineering interpretation profile (Relay Import Slice 6).

``RawRelayDocument -> MicomP441Profile -> CanonicalDistanceProtectionModel``

All P441-specific knowledge -- parameter codes, expected names, unit and
basis conventions, the shared Zone 3/4 settings, scheme-note wording --
lives here and nowhere else. The generic PDF extractor, the relay
identifier, the canonical model and the Distance Protection engine know
nothing about it.

Profile version ``micom-p441-v1``. **Implemented / Awaiting Validation**: it
becomes ``Validated`` only after owner UAT against the real setting file.
A different P441 template or firmware may need a different version.

Rules this profile never breaks
-------------------------------
* A value is ``mapped`` only when the sheet states it unambiguously (a
  code-and-name-checked setting whose unit and basis the sheet establishes).
  Anything that rests on knowledge of the P441 family that the sheet does not
  repeat (reach angle = line angle, quadrilateral shape, the meaning of a
  residual-compensation pair, a zone being in service) is ``inferred`` and
  carries a note saying why.
* A setting is read only when its code *and* its name match this version's
  table. A known code under another name is unresolved, never trusted.
* A missing, duplicated-with-conflict, non-numeric, out-of-range or
  unit-unconfirmed setting becomes an unresolved value that keeps its raw
  text. Nothing is defaulted and nothing is converted (no CT/VT, no unit
  scaling, no K0 <-> Kr/Kx).
* Numeric presence never means "in service": Zone 4 carries numbers but is
  reported as defeated because the sheet's scheme notes say so.
* Every raw setting ends up either cited by a value or carried as an
  ``UnresolvedSetting``; none is dropped.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    ImpedanceValue,
    InstrumentTransformers,
    ProtectedLine,
    RelayMetadata,
    ResidualCompensation,
    ResistiveReach,
    SettingBasis,
    UnresolvedSetting,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.profile import MatchLevel, ProfileMatch
from app.domain.relay_import.provenance import (
    Sourced,
    SourceRef,
    UnresolvedCause,
    assumed_default,
    inferred,
    mapped,
    unresolved,
)
from app.domain.relay_import.raw_document import RawRelayDocument, RawSetting

PROFILE_ID = "schneider-micom-p441"
PROFILE_VERSION = "micom-p441-v1"
VALIDATION_STATUS = "Implemented / Awaiting Validation"

MANUFACTURER = "Schneider Electric"
FAMILY = "MiCOM P44x"
MODEL = "P441"

#: Parameter codes whose group is Distance Protection (distance element,
#: distance scheme, power swing). Everything else is outside this feature.
_DISTANCE_CODE_PREFIXES = ("30", "31", "32")

# ---------------------------------------------------------------------------
# The parameter table: code -> the name this version expects for it
# ---------------------------------------------------------------------------

_CT_PRIMARY = ("0A07", "Phase CT Primary")
_CT_SECONDARY = ("0A08", "Phase CT Sec'y")
_VT_PRIMARY = ("0A01", "Main VT Primary")
_VT_SECONDARY = ("0A02", "Main VT Sec'y")
_SETTING_VALUES = ("092E", "Setting Values")
_DIST_ENABLED = ("090D", "Dist. Protection")
_ACTIVE_GROUP = ("0903", "Active Settings")
_DISTANCE_UNIT = ("0D07", "Distance Unit")
_LINE_LENGTH = ("3002", "Line Length")
_LINE_IMPEDANCE = ("3004", "Line Impedance")
_LINE_ANGLE = ("3005", "Line Angle")
_ZONE_STATUS = ("3007", "Zone Status")
_FAULT_TYPE = ("3103", "Fault Type")
_Z1X = ("300B", "Z1X")
_ZP_DIRECTION = ("301D", "ZoneP - Direct")
_TILT_Z1M = ("3026", "Z1m Tilt Angle")
_TILT_Z1P = ("3027", "Z1p Tilt Angle")
_TILT_Z2ZP = ("3028", "Z2/Zp Tilt Angle")


@dataclass(frozen=True)
class _ZoneTable:
    zone_id: str
    name: str
    reach: tuple[str, str]
    r_phase: tuple[str, str]
    r_earth: tuple[str, str]
    timer: tuple[str, str]
    comp_magnitude: tuple[str, str]
    comp_angle: tuple[str, str]
    tilts: tuple[tuple[str, str], ...] = ()


_ZONE_TABLE = (
    _ZoneTable("Z1", "Zone 1", ("300A", "Z1"), ("300D", "R1Ph"), ("300C", "R1G"), ("300E", "tZ1"),
               ("3008", "kZ1 Res Comp"), ("3009", "kZ1 Angle"), (_TILT_Z1M, _TILT_Z1P)),
    _ZoneTable("Z2", "Zone 2", ("3011", "Z2"), ("3013", "R2Ph"), ("3012", "R2G"), ("3014", "tZ2"),
               ("300F", "kZ2 Res Comp"), ("3010", "kZ2 Angle"), (_TILT_Z2ZP,)),
    # Zones 3 and 4 share one compensation pair and one pair of resistive reaches.
    _ZoneTable("Z3", "Zone 3", ("3017", "Z3"), ("3019", "R3Ph-R4Ph"), ("3018", "R3G-R4G"), ("301A", "tZ3"),
               ("3015", "kZ3/4 Res Comp"), ("3016", "kZ3/4 Angle")),
    _ZoneTable("Z4", "Zone 4", ("301B", "Z4"), ("3019", "R3Ph-R4Ph"), ("3018", "R3G-R4G"), ("301C", "tZ4"),
               ("3015", "kZ3/4 Res Comp"), ("3016", "kZ3/4 Angle")),
    _ZoneTable("ZP", "Zone P", ("3020", "Zp"), ("3022", "RpPh"), ("3021", "RpG"), ("3023", "tZp"),
               ("301E", "kZp Res Comp"), ("301F", "kZp Angle"), (_TILT_Z2ZP,)),
)

# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_RANGE = re.compile(
    r"^\s*(?P<lo>[+-]?\d+(?:\.\d+)?)\s*(?:-|to)\s*(?P<hi>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>.*?)\s*$",
    re.IGNORECASE,
)
_SCHEME = re.compile(r"\bScheme:\s*(\S+)", re.IGNORECASE)
_MODEL_TOKEN = re.compile(r"(?<![A-Za-z0-9])P441(?![A-Za-z0-9])", re.IGNORECASE)
_VERSION_MARKER = re.compile(r"\bMinor\s+Ver\.?\s*([A-Za-z0-9.]+)", re.IGNORECASE)
_Z4_DEFEATED = re.compile(r"\bzone\s*4\s+(?:is\s+)?(?:defeated|disabled)\b|\bto\s+defeat\s+zone\s*4\b", re.IGNORECASE)
_Z4_ACTIVE = re.compile(r"\bzone\s*4\s+(?:is\s+)?(?:enabled|active|in\s+service)\b", re.IGNORECASE)
_ZP_MENTION = re.compile(r"\bzone\s*p\b", re.IGNORECASE)
_Z1_RELEASE = re.compile(r"\brelease\s+z1\s+only\b", re.IGNORECASE)
_TAP_3007 = re.compile(r"\btap\s*3007\b", re.IGNORECASE)
_CELLS = "cells:"


def _norm_name(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'")).strip().casefold()


def _clean(text: str | float | None) -> str:
    return "" if text is None else str(text).strip()


def _entry_text(s: RawSetting) -> str:
    return f"{s.name or ''} {s.raw_value if s.raw_value is not None else ''}"


def _range_text(s: RawSetting) -> str | None:
    """The printed range / options cell: the extractor's range, else the last
    cell of a four-column row (code | name | value | range)."""
    if s.setting_range and s.setting_range.text:
        return s.setting_range.text.strip()
    for note in s.notes:
        if note.startswith(_CELLS):
            cells = [c.strip() for c in note[len(_CELLS):].split("|")]
            if len(cells) >= 4 and cells[-1]:
                return cells[-1]
    return None


def _unit_of_range(text: str | None) -> tuple[float, float, str] | None:
    """(low, high, unit) of a printed numeric range such as ``0-10.0 s``."""
    m = _RANGE.match(text) if text else None
    if not m:
        return None
    return float(m["lo"]), float(m["hi"]), m["unit"].strip().rstrip(".")


def _parse_number(text: str) -> float | None:
    if not _NUMBER.match(text):
        return None
    value = float(text)
    return value if math.isfinite(value) else None


@dataclass
class _Read:
    """The outcome of looking up one code."""

    code: str
    name: str
    entries: tuple[RawSetting, ...] = ()
    raw: str | None = None
    problem: str | None = None
    #: Why the read failed, when it did (see `UnresolvedCause`); set with ``problem``.
    cause: UnresolvedCause | None = None
    notes: tuple[str, ...] = ()

    def fail(self, problem: str, cause: UnresolvedCause) -> None:
        self.problem = problem
        self.cause = cause

    @property
    def label(self) -> str:
        return f"{self.code} {self.name}".strip()

    @property
    def found(self) -> bool:
        return bool(self.entries)

    @property
    def ok(self) -> bool:
        return self.found and self.problem is None


@dataclass
class _Context:
    """Document-wide facts every zone needs, read once."""

    line_angle: float | None
    angle_read: _Read
    z4_state: tuple[str, tuple[RawSetting, ...]]
    dist_read: _Read = None  # type: ignore[assignment]
    dist_on: bool | None = None
    fault_read: _Read = None  # type: ignore[assignment]
    fault: tuple[bool, bool] | None = None
    z1x_read: _Read = None  # type: ignore[assignment]
    z1x: float | None = None
    zp_dir_read: _Read = None  # type: ignore[assignment]
    zp_dir: ZoneDirection | None = None
    z1_release: tuple[RawSetting, ...] = ()


class _Interpreter:
    """One interpretation run over one document (not reusable)."""

    def __init__(self, document: RawRelayDocument) -> None:
        self.doc = document
        self.by_code: dict[str, list[RawSetting]] = {}
        for s in document.settings:
            if s.parameter_id:
                self.by_code.setdefault(s.parameter_id.upper(), []).append(s)
        self.consumed: set[str] = set()
        self.notes: list[str] = []
        #: Phase CT secondary in amps once established (needed by the '/I1' ohm rule).
        self.ct_secondary: float | None = None

    # --- provenance plumbing ------------------------------------------------

    def refs(self, *entries: RawSetting) -> tuple[SourceRef, ...]:
        out: dict[str, SourceRef] = {}
        for e in entries:
            self.consumed.add(e.setting_id)
            out.setdefault(
                e.setting_id,
                SourceRef(
                    e.setting_id,
                    e.parameter_id,
                    e.name,
                    e.location.page,
                    f"page {e.location.page}, line {e.location.line}" if e.location.page and e.location.line else None,
                ),
            )
        return tuple(out.values())

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def good(
        self,
        value,
        reads: tuple[_Read, ...],
        *,
        status: str = "mapped",
        why: str = "",
        extra: tuple[RawSetting, ...] = (),
        raw: str | None = None,
    ) -> Sourced:
        entries = tuple(e for r in reads for e in r.entries) + extra
        notes = tuple(n for r in reads for n in r.notes) + ((why,) if why else ())
        raw = (raw if raw is not None else " | ".join(r.raw for r in reads if r.raw is not None)) or None
        build = mapped if status == "mapped" else inferred
        return build(
            value,
            sources=self.refs(*entries),
            profile_id=PROFILE_ID,
            profile_version=PROFILE_VERSION,
            raw_value=raw,
            notes=notes,
        )

    def bad(self, *reads: _Read, reason: str | None = None, cause: UnresolvedCause | None = None) -> Sourced:
        """An unresolved value that keeps the raw text and its sources. Its cause is
        the strongest one among the failed reads (conflict, then unreadable, then
        unsupported); an absent code or a bare ``reason`` is missing."""
        causes = {r.cause for r in reads if r.problem and r.cause} | ({cause} if cause else set())
        cause = next(
            (c for c in (UnresolvedCause.CONFLICT, UnresolvedCause.UNREADABLE, UnresolvedCause.UNSUPPORTED) if c in causes),
            UnresolvedCause.MISSING,
        )
        problems = [reason] if reason else []
        problems += [f"{r.label}: {r.problem}" for r in reads if r.problem]
        problems += [f"{r.label}: not present in the document" for r in reads if not r.found and not r.problem]
        for p in problems:
            self.note(p)
        entries = tuple(e for r in reads for e in r.entries)
        raw = " | ".join(r.raw for r in reads if r.raw is not None) or None
        return unresolved(raw, sources=self.refs(*entries), notes=tuple(problems), cause=cause)

    # --- lookups --------------------------------------------------------------

    def read(self, table: tuple[str, str]) -> _Read:
        """Entries for a code, validated by name and for duplicates."""
        code, expected = table
        found = tuple(self.by_code.get(code.upper(), ()))
        r = _Read(code, expected, found)
        if not found:
            return r
        wrong = [e for e in found if _norm_name(e.name) != _norm_name(expected)]
        if wrong:
            r.fail(
                f"the document names this code differently from what profile {PROFILE_VERSION} expects ({expected!r}); not trusted",
                UnresolvedCause.CONFLICT,
            )
            r.raw = _clean(found[0].raw_value) or None
            return r
        values = {_clean(e.raw_value) for e in found}
        if len(values) > 1:
            r.fail("conflicting duplicate entries; which applies is not guessed", UnresolvedCause.CONFLICT)
            r.raw = " / ".join(sorted(values))
            return r
        r.raw = _clean(found[0].raw_value)
        if not r.raw:
            r.fail("no value found", UnresolvedCause.UNREADABLE)
            r.raw = None
        elif len(found) > 1:
            r.notes = (f"{len(found)} identical duplicate entries in the document",)
        return r

    def number(self, table: tuple[str, str], *, unit: str | None, ct_secondary_a: float | None = None) -> tuple[_Read, float | None]:
        """A numeric setting whose printed range/unit must agree with ``unit``:
        ``A``, ``V``, ``s``, ``deg``, ``ohm`` (secondary ohms), ``factor``
        (dimensionless) or ``None`` (unit established elsewhere by the caller)."""
        r = self.read(table)
        if not r.ok:
            return r, None
        value = _parse_number(r.raw)
        if value is None:
            r.fail("the value is not a plain number", UnresolvedCause.UNREADABLE)
            return r, None
        rng = _unit_of_range(_range_text(r.entries[0]))
        if rng is not None:
            lo, hi, printed = rng
            if not (lo <= value <= hi):
                r.fail("the value is outside the setting range printed beside it", UnresolvedCause.CONFLICT)
                return r, None
        else:
            printed = _range_text(r.entries[0])
        if unit is None:
            return r, value
        if unit == "ohm":
            ok = (printed == "/I1" and ct_secondary_a == 1.0) or (printed or "").casefold() in {"ohm", "ohms", "ω"}  # "Ω".casefold() is "ω"
            if not ok:
                r.fail(
                    "the impedance unit could not be established as secondary ohms "
                    "(this version accepts '/I1' with a 1 A CT secondary, or an explicit ohm unit)",
                    UnresolvedCause.CONFLICT if printed else UnresolvedCause.MISSING,
                )
                return r, None
        elif unit == "factor":
            if printed:
                r.fail("expected a dimensionless setting but a unit is printed", UnresolvedCause.CONFLICT)
                return r, None
        elif printed != unit:
            r.fail(f"the printed unit is not the expected {unit!r}; no unit conversion is applied", UnresolvedCause.CONFLICT)
            return r, None
        return r, value

    def choice(self, table: tuple[str, str], options: dict[str, object]) -> tuple[_Read, object | None]:
        r = self.read(table)
        if not r.ok:
            return r, None
        key = _norm_name(r.raw)
        if key not in options:
            r.fail(f"the value is not recognised by profile {PROFILE_VERSION}", UnresolvedCause.UNSUPPORTED)
            return r, None
        return r, options[key]

    # --- the sections -----------------------------------------------------------

    def interpret(self) -> CanonicalDistanceProtectionModel:
        metadata = self.metadata()
        transformers = self.transformers()
        line, line_angle = self.line()
        zones = self.zones(line_angle)
        unmapped = self.leftovers()
        self.finish_notes(transformers)
        return CanonicalDistanceProtectionModel(
            metadata=metadata,
            transformers=transformers,
            line=line,
            zones=zones,
            unmapped_settings=unmapped,
            interpretation_notes=tuple(self.notes),
        )

    def metadata(self) -> RelayMetadata:
        schemes: dict[str, RawSetting] = {}
        for s in self.doc.settings:
            for text in (s.raw_value, s.name):
                m = _SCHEME.search(str(text)) if text else None
                if m:
                    schemes.setdefault(m.group(1), s)
        scheme_read = _Read(
            "", "Scheme", tuple(dict.fromkeys(schemes.values())), raw=" / ".join(f"Scheme: {t}" for t in schemes) or None
        )
        if len(schemes) > 1:
            scheme_read.fail("more than one scheme/template was stated; none selected", UnresolvedCause.CONFLICT)
        if scheme_read.found and scheme_read.problem is None:
            token = next(iter(schemes))
            scheme = self.good(token, (scheme_read,))
            if _MODEL_TOKEN.search(token):
                model = self.good(MODEL, (scheme_read,))
                manufacturer = self.good(
                    MANUFACTURER, (scheme_read,),
                    why="normalised from the P441 model per the identification catalogue; the manufacturer is not named in the document",
                )
                family = self.good(FAMILY, (scheme_read,), why="family label from the identification catalogue")
            else:
                model = manufacturer = family = self.bad(scheme_read, reason="the scheme does not name a P441", cause=UnresolvedCause.CONFLICT)
        else:
            scheme = model = manufacturer = family = self.bad(scheme_read)

        version_entries = [(s, m) for s in self.doc.settings if (m := _VERSION_MARKER.search(s.name or ""))]
        if version_entries:
            s, m = version_entries[0]
            version = unresolved(
                m.group(0),
                sources=self.refs(s),
                notes=("a 'Minor Ver.' marker appears in a free-text note; it is not a labelled firmware field, so it is kept raw",),
                cause=UnresolvedCause.MISSING,
            )
        else:
            version = unresolved(cause=UnresolvedCause.MISSING)

        group_read, group = self.choice(_ACTIVE_GROUP, {f"group {n}": f"Group {n}" for n in (1, 2, 3, 4)})
        active = self.good(group, (group_read,)) if group else self.bad(group_read)
        return RelayMetadata(
            source_format=self.doc.source_format,
            manufacturer=manufacturer,
            family=family,
            model=model,
            version=version,
            active_setting_group=active,
            profile_id=PROFILE_ID,
            profile_version=PROFILE_VERSION,
            scheme_name=scheme,
        )

    def transformers(self) -> InstrumentTransformers:
        ct_p, ct_p_v = self.number(_CT_PRIMARY, unit="A")
        ct_s = self.read(_CT_SECONDARY)
        ct_s_v: float | None = None
        if ct_s.ok:
            rng = _range_text(ct_s.entries[0]) or ""
            value = _parse_number(ct_s.raw)
            if re.fullmatch(r"1\s*A\s*/\s*5\s*A", rng, re.IGNORECASE) and value in (1.0, 5.0):
                ct_s_v = value
            else:
                ct_s.fail("the value and printed range do not establish a 1 A / 5 A secondary", UnresolvedCause.CONFLICT)
        vt_p, vt_p_v = self.number(_VT_PRIMARY, unit="V")
        vt_s, vt_s_v = self.number(_VT_SECONDARY, unit="V")

        def sourced(read: _Read, value) -> Sourced:
            return self.good(value, (read,)) if value is not None else self.bad(read)

        basis_read, basis = self.choice(
            _SETTING_VALUES, {"secondary": SettingBasis.SECONDARY, "primary": SettingBasis.PRIMARY}
        )
        setting_basis = (
            self.good(basis, (basis_read,), why="the relay's 'Setting Values' selection; the 'Measure't Setup' display selections are not the settings basis")
            if basis
            else self.bad(basis_read)
        )
        self.ct_secondary = ct_s_v
        self.note_ratio_check(ct_p_v, ct_s_v)
        return InstrumentTransformers(
            ct_primary_a=sourced(ct_p, ct_p_v),
            ct_secondary_a=sourced(ct_s, ct_s_v),
            vt_primary_v=sourced(vt_p, vt_p_v),
            vt_secondary_v=sourced(vt_s, vt_s_v),
            setting_basis=setting_basis,
        )

    def note_ratio_check(self, primary: float | None, secondary: float | None) -> None:
        """The verification notes restate the CT ratio; a disagreement is
        reported, never silently resolved either way."""
        for s in self.doc.settings:
            if "ct ratio" in (s.name or "").casefold() and s.raw_value:
                m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*", str(s.raw_value))
                if m and primary is not None and secondary is not None and (float(m[1]), float(m[2])) != (primary, secondary):
                    self.note(
                        "The CT ratio restated in the verification note differs from settings 0A07/0A08; "
                        "the settings were used and the difference needs review."
                    )

    def line(self) -> tuple[ProtectedLine, float | None]:
        unit_read, unit = self.choice(
            _DISTANCE_UNIT, {"kilometres": "km", "kilometers": "km", "km": "km", "miles": "mile", "mile": "mile"}
        )
        length_read, length = self.number(_LINE_LENGTH, unit=None)
        if length is not None and unit is not None:
            length_s = self.good(length, (length_read, unit_read), why="the unit is the relay's 'Distance Unit' selection (0D07)")
            unit_s = self.good(unit, (unit_read,))
        elif length is not None:
            length_s = self.bad(length_read, unit_read, reason="the line length unit could not be established (Distance Unit 0D07)")
            unit_s = self.bad(unit_read)
        else:
            length_s = self.bad(length_read)
            unit_s = self.bad(unit_read)
        angle_read, angle = self.number(_LINE_ANGLE, unit="deg")
        angle_s = self.good(angle, (angle_read,)) if angle is not None else self.bad(angle_read)
        imp_read, imp = self.number(_LINE_IMPEDANCE, unit="ohm", ct_secondary_a=self.ct_secondary)
        magnitude = self.good(imp, (imp_read,)) if imp is not None else self.bad(imp_read)
        extras = (ExtraQuantity("line_impedance_magnitude", magnitude, unit="ohm"),)
        # The sheet does not call the pair "positive sequence", so no sequence
        # impedance is claimed; magnitude and angle are kept separately.
        positive = unresolved(
            sources=(),
            notes=("the sheet gives a line impedance magnitude and a line angle without naming a sequence; they are kept separately, not combined",),
            cause=UnresolvedCause.MISSING,
        )
        self.note("Line impedance magnitude and line angle are kept as separate values; no sequence impedance is claimed or derived.")
        line = ProtectedLine(
            length=length_s,
            length_unit=unit_s,
            positive_sequence_impedance=positive,
            line_angle_deg=angle_s,
            extras=extras,
        )
        return line, angle

    # --- zones ---------------------------------------------------------------------

    def zones(self, line_angle: float | None) -> tuple[DistanceZone, ...]:
        ctx = _Context(line_angle=line_angle, angle_read=self.read(_LINE_ANGLE), z4_state=self.zone4_state())
        ctx.dist_read, ctx.dist_on = self.choice(_DIST_ENABLED, {"enabled": True, "disabled": False})
        ctx.fault_read, ctx.fault = self.choice(_FAULT_TYPE, {"both enabled": (True, True)})
        ctx.z1x_read, ctx.z1x = self.number(_Z1X, unit="ohm", ct_secondary_a=self.ct_secondary)
        ctx.zp_dir_read, ctx.zp_dir = self.choice(
            _ZP_DIRECTION, {"directional fwd": ZoneDirection.FORWARD, "directional rev": ZoneDirection.REVERSE}
        )
        if self.read(_ZONE_STATUS).found:
            self.note(
                "Zone Status (3007) is a bit string whose bit-to-zone layout is not decoded by this profile version; "
                "zone status comes from the Dist. Protection enable and the sheet's scheme notes."
            )
        self.note(
            "Zones 3 and 4 share one residual-compensation pair (kZ3/4) and one pair of resistive reaches "
            "(R3Ph-R4Ph, R3G-R4G); both zones cite the same settings."
        )
        self.note(
            "Resistive reach is carried as set (phase and earth kept separate); no per-loop or per-phase scaling is applied, "
            "and no Left Resistive Reach (−R) is stated by the sheet."
        )
        ctx.z1_release = tuple(s for s in self.doc.settings if _Z1_RELEASE.search(_entry_text(s)))
        if ctx.z1_release:
            self.note(
                "Scheme notes state that Zone 1 is released only during communication failure or 87L faulty; "
                "Zone 1 is reported as configured, not as operationally released."
            )
        return tuple(self.zone(t, ctx) for t in _ZONE_TABLE)

    def zone4_state(self) -> tuple[str, tuple[RawSetting, ...]]:
        """('defeated' | 'active' | 'conflict' | 'unstated', evidence entries)."""
        defeated = tuple(s for s in self.doc.settings if _Z4_DEFEATED.search(_entry_text(s)))
        active = tuple(s for s in self.doc.settings if _Z4_ACTIVE.search(_entry_text(s)))
        if defeated and active:
            return "conflict", defeated + active
        if defeated:
            return "defeated", defeated
        if active:
            return "active", active
        return "unstated", ()

    def zone(self, t: _ZoneTable, ctx: "_Context") -> DistanceZone:
        ct = self.ct_secondary
        reach_read, reach = self.number(t.reach, unit="ohm", ct_secondary_a=ct)
        rph_read, rph = self.number(t.r_phase, unit="ohm", ct_secondary_a=ct)
        rg_read, rg = self.number(t.r_earth, unit="ohm", ct_secondary_a=ct)
        timer_read, timer = self.number(t.timer, unit="s")
        comp_m_read, comp_m = self.number(t.comp_magnitude, unit="factor")
        comp_a_read, comp_a = self.number(t.comp_angle, unit="deg")

        status = self.status(t, ctx, reach_read)
        direction = self.direction(t, reach_read, ctx)

        if ctx.fault is not None:
            loop_why = "'Both Enabled' read as phase-phase and phase-earth fault types both enabled"
            pp = self.good(ctx.fault[0], (ctx.fault_read,), status="inferred", why=loop_why)
            pe = self.good(ctx.fault[1], (ctx.fault_read,), status="inferred", why=loop_why)
        else:
            pp = pe = self.bad(ctx.fault_read)

        if reach is not None and ctx.line_angle is not None:
            reach_s = self.good(
                ImpedanceValue(magnitude_ohm=reach, angle_deg=ctx.line_angle),
                (reach_read, ctx.angle_read),
                status="inferred",
                why="the reach is set at the line angle (3005); the sheet does not restate an angle per zone",
            )
        elif reach is not None:
            reach_s = self.bad(reach_read, ctx.angle_read, reason="the zone reach needs the line angle, which is unresolved")
        else:
            reach_s = self.bad(reach_read)

        evidence = tuple(e for r in (rph_read, rg_read) if r.ok for e in r.entries) or (
            reach_read.entries if reach_read.ok else ()
        )
        if evidence:
            ctype = inferred(
                CharacteristicType.QUADRILATERAL,
                sources=self.refs(*evidence),
                profile_id=PROFILE_ID,
                profile_version=PROFILE_VERSION,
                notes=(
                    "the P441 distance zones are quadrilateral; the sheet does not name the characteristic, "
                    "but it gives separate reactive and phase / earth resistive reaches",
                ),
            )
        else:
            ctype = unresolved(
                notes=("no usable reach or resistive reach to establish the characteristic",), cause=UnresolvedCause.MISSING
            )
        parameters: tuple[ExtraQuantity, ...] = ()
        if t.zone_id == "Z1":
            z1x_s = self.good(ctx.z1x, (ctx.z1x_read,)) if ctx.z1x is not None else self.bad(ctx.z1x_read)
            parameters = (ExtraQuantity("z1_extension_reach", z1x_s, unit="ohm"),)

        resistive = ResistiveReach(
            phase_phase=self.good(rph, (rph_read,)) if rph is not None else self.bad(rph_read),
            phase_earth=self.good(rg, (rg_read,)) if rg is not None else self.bad(rg_read),
        )
        timer_s = self.good(timer, (timer_read,)) if timer is not None else self.bad(timer_read)

        # Source-native residual compensation: magnitude + angle, never converted.
        comp_why = (
            "residual compensation factor magnitude and angle as the relay defines them; "
            "read as a K0-style magnitude/angle pair and never converted"
        )
        compensation = ResidualCompensation(
            kind=CompensationKind.K0_MAGNITUDE_ANGLE,
            k0_magnitude=(
                self.good(comp_m, (comp_m_read,), status="inferred", why=comp_why)
                if comp_m is not None
                else self.bad(comp_m_read)
            ),
            k0_angle_deg=(
                self.good(comp_a, (comp_a_read,), status="inferred", why=comp_why)
                if comp_a is not None
                else self.bad(comp_a_read)
            ),
        )

        # Tilts differ per loop type and are shared by zone groups: kept raw.
        tilts: list[UnresolvedSetting] = []
        for tilt in t.tilts:
            for e in self.read(tilt).entries:
                self.consumed.add(e.setting_id)
                tilts.append(
                    UnresolvedSetting(
                        e.setting_id,
                        e.name,
                        e.raw_value,
                        e.unit,
                        "tilt applies per fault-loop type / zone group; not mapped to a single zone tilt in this profile version",
                    )
                )
        return DistanceZone(
            zone_id=t.zone_id,
            name=t.name,
            status=status,
            direction=direction,
            phase_phase_enabled=pp,
            phase_earth_enabled=pe,
            common_timer_s=timer_s,
            characteristic=CharacteristicSpec(type=ctype, parameters=parameters),
            reach=reach_s,
            resistive_reach=resistive,
            compensation=compensation,
            unresolved_settings=tuple(tilts),
        )

    def status(self, t: _ZoneTable, ctx: "_Context", reach_read: _Read) -> Sourced:
        if ctx.dist_on is False:
            return self.good(
                ZoneStatus.DISABLED,
                (ctx.dist_read,),
                status="inferred",
                why="the Distance Protection function is disabled in the relay configuration",
            )
        if t.zone_id == "ZP" and self.zone_p_absent(ctx):
            return assumed_default(
                ZoneStatus.DISABLED,
                profile_id=PROFILE_ID,
                profile_version=PROFILE_VERSION,
                reason="Zone P not found in uploaded relay settings",
            )
        if t.zone_id == "Z4":
            kind, evidence = ctx.z4_state
            if kind == "defeated":
                tap = tuple(s for s in self.doc.settings if _TAP_3007.search(_entry_text(s)))
                return self.good(
                    ZoneStatus.DISABLED,
                    (self.read(_ZONE_STATUS),),
                    status="inferred",
                    why="the scheme notes state Zone 4 is defeated; its numeric settings are present but do not put it in service",
                    extra=evidence + tap,
                    raw=_entry_text(evidence[0]).strip(),
                )
            if kind == "active":
                return self.good(
                    ZoneStatus.ENABLED,
                    (),
                    status="inferred",
                    why="the document states Zone 4 is in service",
                    extra=evidence,
                    raw=_entry_text(evidence[0]).strip(),
                )
            if kind == "conflict":
                self.note("Zone 4 status: the document states both 'defeated' and 'enabled'; left unresolved.")
                return unresolved(
                    sources=self.refs(*evidence),
                    notes=("the document both defeats and enables Zone 4; none selected",),
                    cause=UnresolvedCause.CONFLICT,
                )
            return self.bad(
                self.read(_ZONE_STATUS),
                reason="Zone 4 in-service state is not stated outside the undecoded Zone Status bit string",
            )
        if t.zone_id in ("Z1", "Z2", "Z3") and ctx.dist_on is True:
            return self.good(
                ZoneStatus.ENABLED,
                (ctx.dist_read,),
                status="inferred",
                extra=reach_read.entries + (ctx.z1_release if t.zone_id == "Z1" else ()),
                why=(
                    "Distance Protection is enabled and this zone has its own settings; the P441 family keeps "
                    "Zones 1-3 available, but the sheet does not restate it"
                ),
            )
        if not ctx.dist_read.ok:
            return self.bad(ctx.dist_read, reason=f"{t.name} in-service state is not established")
        return self.bad(
            self.read(_ZONE_STATUS),
            reason=f"{t.name} in-service state is not established (the Zone Status bit string is not decoded)",
        )

    def zone_p_absent(self, ctx: "_Context") -> bool:
        """True only when Zone P is genuinely absent from a reliably read sheet: no Zone P
        setting (nor any mention of it) is present while the neighbouring zones' reaches
        and the Distance Protection function were read cleanly and the extractor raised no
        warning. Anything less -- observed Zone P rows, an unreadable or partial source --
        is not evidence of absence, so the state stays unresolved."""
        zp = next(t for t in _ZONE_TABLE if t.zone_id == "ZP")
        zp_codes = (zp.reach, zp.r_phase, zp.r_earth, zp.timer, zp.comp_magnitude, zp.comp_angle, _ZP_DIRECTION)
        if any(self.read(code).found for code in zp_codes):
            return False
        if any(_ZP_MENTION.search(_entry_text(s)) for s in self.doc.settings):
            return False
        neighbours = (self.read(t.reach) for t in _ZONE_TABLE if t.zone_id != "ZP")
        return ctx.dist_read.ok and not self.doc.warnings and all(r.ok for r in neighbours)

    def direction(self, t: _ZoneTable, reach_read: _Read, ctx: "_Context") -> Sourced:
        if t.zone_id == "ZP":
            return self.good(ctx.zp_dir, (ctx.zp_dir_read,)) if ctx.zp_dir is not None else self.bad(ctx.zp_dir_read)
        if t.zone_id in ("Z2", "Z3"):
            word = t.zone_id[1]
            hits = tuple(s for s in self.doc.settings if re.search(rf"\bzone\s*{word}\s+forward\b", _entry_text(s), re.IGNORECASE))
            if hits:
                return self.good(
                    ZoneDirection.FORWARD, (), why="the scheme notes state this zone's forward direction",
                    extra=hits, raw=_entry_text(hits[0]).strip(),
                )
        if t.zone_id == "Z4":
            relay_label = tuple(s for s in self.doc.settings if re.search(r"\bDIST\s+REV\s+OP\b", _entry_text(s), re.IGNORECASE))
            if reach_read.ok:
                return self.good(
                    ZoneDirection.REVERSE, (reach_read,), status="inferred",
                    why="Zone 4 is the reverse-looking zone of the P441 family; an output labelled 'DIST REV OP' agrees",
                    extra=relay_label,
                    raw="",
                )
            return self.bad(reach_read)
        if reach_read.ok:
            return self.good(
                ZoneDirection.FORWARD, (reach_read,), status="inferred",
                why="Zones 1-3 are forward-looking in the P441 family; the sheet does not restate it for this zone",
                raw="",
            )
        return self.bad(reach_read)

    # --- completeness ------------------------------------------------------------------------

    def leftovers(self) -> tuple[UnresolvedSetting, ...]:
        out = []
        for s in self.doc.settings:
            if s.setting_id in self.consumed:
                continue
            code = (s.parameter_id or "").upper()
            distance = code.startswith(_DISTANCE_CODE_PREFIXES)
            out.append(
                UnresolvedSetting(
                    s.setting_id, s.name, s.raw_value, s.unit,
                    reason=(
                        f"distance-related setting not interpreted by {PROFILE_VERSION}"
                        if distance
                        else "outside Distance Protection; retained, not interpreted"
                    ),
                    out_of_scope=not distance,
                )
            )
        return tuple(out)

    def finish_notes(self, transformers: InstrumentTransformers) -> None:
        if transformers.setting_basis.is_resolved and transformers.setting_basis.value is SettingBasis.SECONDARY:
            self.note("Settings are stated as secondary values; no CT/VT conversion has been applied.")


class MicomP441Profile:
    """``RelayProfile`` implementation for the MiCOM P441 (micom-p441-v1)."""

    profile_id = PROFILE_ID
    version = PROFILE_VERSION
    validation_status = VALIDATION_STATUS

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        """CONFIRMED only when the document's own scheme field names a P441.
        (Routing from an upload goes through the identification verdict; this
        keeps ``registry.interpret()`` from reading other relays as a P441.)"""
        for s in document.settings:
            for text in (s.raw_value, s.name):
                m = _SCHEME.search(str(text)) if text else None
                if m and _MODEL_TOKEN.search(m.group(1)):
                    return ProfileMatch(MatchLevel.CONFIRMED, ("scheme field names a P441",))
        return ProfileMatch(MatchLevel.NONE)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        interpreter = _Interpreter(document)
        return interpreter.interpret()
