"""Hitachi Energy (formerly ABB) Relion RED670 engineering interpretation profile (Relay Import Slice 12).

``RawRelayDocument -> HitachiRed670Profile -> CanonicalDistanceProtectionModel``

All RED670-specific knowledge -- the function-instance naming (``ZM01-:`` is the first
``ZMQPDIS`` distance-zone instance), the parameter names of a Relion 670 setting sheet, the
``Operation`` / ``OperationDir`` / ``Timer tPP`` activation parameters, the ``X1`` / ``RFPP`` /
``RFPE`` reach vocabulary and the channel-numbered CT / VT parameters (``CTprim1`` ...) -- lives
here and nowhere else. The generic PDF extractor, the relay identifier, the canonical model, the
review, Apply Settings, the engine adapter and the Distance Protection engine know nothing about it.

Profile version ``hitachi-red670-v1``. **Implemented / Awaiting Validation**: it becomes
``Validated`` only after owner UAT against the real setting file.

This profile stands alone (no base class shared with any other relay profile): what is
shared between families is decided when more profiles exist to compare.

Rules this profile never breaks
-------------------------------
* A value is ``mapped`` only when the sheet states it. Whatever rests on Relion 670 family
  knowledge the sheet does not repeat (the primary-ohm basis, the quadrilateral characteristic,
  the kV / V units of the VT rows, the per-loop reading of ``RFPP`` / ``RFPE``) is ``inferred``
  and carries a note.
* A zone's state is read from the zone's own activation parameters (``Operation`` and
  ``OperationDir``). An operating delay is read only from ``tPP`` / ``tPE`` and only while its
  ``Timer`` switch is ON. The page-16 scheme requirements (timers, "Zone 4 Inactive") are kept as
  zone source notes; they are never copied into a value or a status.
* The geometry is what the sheet states: a reactive reach (``X1``), phase-phase and phase-earth
  resistive reaches (``RFPP`` / ``RFPE``), no reach angle -- explicit R/X limits. No angle is
  derived or invented. The sheet states **no left (-R) resistive reach**: the left / lower
  boundary of a Relion 670 zone comes from the separate directional element (``ZDRDIR``,
  ``ArgDir`` / ``ArgNegRes``), which the generic model cannot represent. The Left Resistive
  Reach is therefore Missing, with that element's rows cited beside it.
* Phase-phase and phase-earth values are kept distinct (``RFPP`` vs ``RFPE``, ``tPP`` vs
  ``tPE``, ``OperationPP`` vs ``OperationPE``). Nothing is collapsed.
* Every raw setting ends up either cited by a value or carried as an ``UnresolvedSetting``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    DistanceZone,
    ExtraQuantity,
    GeometryMode,
    ImpedanceValue,
    InstrumentTransformers,
    ProtectedLine,
    RelayMetadata,
    ResistiveReach,
    SettingBasis,
    SourceNote,
    SourceNoteKind,
    UnresolvedSetting,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.profile import MatchLevel, ProfileMatch
from app.domain.relay_import.provenance import (
    Sourced,
    SourceRef,
    UnresolvedCause,
    inferred,
    mapped,
    unresolved,
)
from app.domain.relay_import.raw_document import RawRelayDocument, RawSetting

PROFILE_ID = "hitachi-red670"
PROFILE_VERSION = "hitachi-red670-v1"
VALIDATION_STATUS = "Implemented / Awaiting Validation"

MANUFACTURER = "Hitachi Energy"
FAMILY = "Relion 670"
MODEL = "RED670"

# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_RANGE = re.compile(
    r"^\s*(?P<lo>[+-]?\d+(?:\.\d+)?)\s*(?:-|to)\s*(?P<hi>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>.*?)\s*$",
    re.IGNORECASE,
)
_SCHEME = re.compile(r"\bScheme:\s*(\S+)", re.IGNORECASE)
_ACTIVE_GROUP = re.compile(r"^\s*Active\s+Group:\s*(\S.*?)\s*$", re.IGNORECASE)
_MODEL_TOKEN = re.compile(r"(?<![A-Za-z0-9])RED-?670(?![A-Za-z0-9])", re.IGNORECASE)
_VERSION_TOKEN = re.compile(r"(?<![A-Za-z0-9])(V\d+(?:\.\d+)*)(?![A-Za-z0-9.])")
_ZONE_PREFIX = re.compile(r"^(ZM(\d{2}))-:", re.IGNORECASE)
_ZONE_SECTION = re.compile(r"^IMP_PROT/DistanceZones/ZMQPDIS:(\d+)$", re.IGNORECASE)
_PHASE_CURRENT_CHANNEL = re.compile(r"_IL([123])$", re.IGNORECASE)
_PHASE_VOLTAGE_CHANNEL = re.compile(r"_UL([123])$", re.IGNORECASE)
_CHANNEL_NUMBER = re.compile(r"^NAMECH(\d+)$", re.IGNORECASE)
_STATED_TIMER = re.compile(r"\btimer\s+set\s+to\s+(\d+(?:\.\d+)?)\s*s\b", re.IGNORECASE)
_STATED_INACTIVE = re.compile(r"(?<!not\s)\b(?:inactive|out\s+of\s+service)\b", re.IGNORECASE)
_ZONE_NOTE_NAME = re.compile(r"^\s*zone\s*(\d+)\s*$", re.IGNORECASE)

#: Sections of the sheet that belong to the distance function (the zones themselves and the
#: functions that act with them). Everything else is retained but marked outside Distance Protection.
_DISTANCE_SECTIONS = (
    "/DistanceZones/", "/Phase Selection/", "/DirectionalImpedance/", "/AutomaticSOTF/",
    "/PowerSwingDetection/", "/FuseFailure/", "/FaultLocator/",
)
_DISTANCE_NOTE_NAMES = {"psb", "sotf"}

#: The directional element whose angles bound a zone on the left / lower side.
_DIRECTIONAL_ELEMENT = ("ZD01-:ArgDir", "ZD01-:ArgNegRes")

#: Printed unit text accepted for a quantity (an empty printed unit is always accepted: the
#: sheet usually prints a bare range).
_UNIT_TEXT = {
    "ohm": {"ohm", "ohms", "ω"},
    "s": {"s", "sec"},
    "A": {"a", "amp"},
    "kV": {"kv"},
    "V": {"v"},
    "": {""},
}

_DIRECTIONS = {
    "forward": ZoneDirection.FORWARD,
    "forw": ZoneDirection.FORWARD,
    "reverse": ZoneDirection.REVERSE,
    "rev": ZoneDirection.REVERSE,
    "non-dir": ZoneDirection.NON_DIRECTIONAL,
    "non-directional": ZoneDirection.NON_DIRECTIONAL,
    "off": ZoneDirection.INACTIVE,
}
_ON_OFF = {"on": True, "off": False}


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'")).strip().casefold()


def _clean(text: str | float | None) -> str:
    return "" if text is None else str(text).strip()


def _range_text(s: RawSetting) -> str | None:
    return s.setting_range.text.strip() if s.setting_range and s.setting_range.text else None


def _split_range(text: str | None) -> tuple[float, float, str] | None:
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
    """The outcome of looking up one parameter."""

    name: str
    entries: tuple[RawSetting, ...] = ()
    raw: str | None = None
    problem: str | None = None
    cause: UnresolvedCause | None = None
    notes: tuple[str, ...] = ()

    def fail(self, problem: str, cause: UnresolvedCause) -> None:
        self.problem = problem
        self.cause = cause

    @property
    def found(self) -> bool:
        return bool(self.entries)

    @property
    def ok(self) -> bool:
        return self.found and self.problem is None


class _Interpreter:
    """One interpretation run over one document (not reusable)."""

    def __init__(self, document: RawRelayDocument) -> None:
        self.doc = document
        self.by_name: dict[str, list[RawSetting]] = {}
        for s in document.settings:
            if s.name:
                self.by_name.setdefault(_norm(s.name), []).append(s)
        self.consumed: set[str] = set()
        self.notes: list[str] = []

    # --- provenance plumbing ------------------------------------------------

    def refs(self, *entries: RawSetting) -> tuple[SourceRef, ...]:
        out: dict[str, SourceRef] = {}
        for e in entries:
            self.consumed.add(e.setting_id)
            out.setdefault(
                e.setting_id,
                SourceRef(
                    e.setting_id, e.parameter_id, e.name, e.location.page,
                    f"page {e.location.page}, line {e.location.line}" if e.location.page and e.location.line else None,
                ),
            )
        return tuple(out.values())

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def good(self, value, reads: tuple[_Read, ...], *, status: str = "mapped", why: str = "",
             extra: tuple[RawSetting, ...] = (), raw: str | None = None) -> Sourced:
        entries = tuple(e for r in reads for e in r.entries) + extra
        notes = tuple(n for r in reads for n in r.notes) + ((why,) if why else ())
        raw = (raw if raw is not None else " | ".join(r.raw for r in reads if r.raw is not None)) or None
        build = mapped if status == "mapped" else inferred
        return build(value, sources=self.refs(*entries), profile_id=PROFILE_ID, profile_version=PROFILE_VERSION,
                     raw_value=raw, notes=notes)

    def bad(self, *reads: _Read, reason: str | None = None, cause: UnresolvedCause | None = None,
            extra: tuple[RawSetting, ...] = ()) -> Sourced:
        """An unresolved value keeping the raw text and sources. Cause: the strongest among the
        failed reads (conflict, unreadable, unsupported); an absent parameter or bare reason is missing."""
        causes = {r.cause for r in reads if r.problem and r.cause} | ({cause} if cause else set())
        cause = next(
            (c for c in (UnresolvedCause.CONFLICT, UnresolvedCause.UNREADABLE, UnresolvedCause.UNSUPPORTED) if c in causes),
            UnresolvedCause.MISSING,
        )
        problems = [reason] if reason else []
        problems += [f"{r.name}: {r.problem}" for r in reads if r.problem]
        problems += [f"{r.name}: not present in the document" for r in reads if not r.found and not r.problem]
        for p in problems:
            self.note(p)
        entries = tuple(e for r in reads for e in r.entries) + extra
        raw = " | ".join(r.raw for r in reads if r.raw is not None) or None
        return unresolved(raw, sources=self.refs(*entries), notes=tuple(problems), cause=cause)

    # --- lookups --------------------------------------------------------------

    def read(self, name: str) -> _Read:
        found = tuple(self.by_name.get(_norm(name), ()))
        r = _Read(name, found)
        if not found:
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

    def number(self, name: str, *, unit: str = "") -> tuple[_Read, float | None]:
        """A numeric setting: a plain decimal inside the printed range, whose printed unit text (if
        any) agrees with ``unit``. No unit conversion is ever applied."""
        r = self.read(name)
        if not r.ok:
            return r, None
        value = _parse_number(r.raw)
        if value is None:
            r.fail("the value is not a plain number", UnresolvedCause.UNREADABLE)
            return r, None
        rng = _split_range(_range_text(r.entries[0]))
        if rng is not None:
            if not (rng[0] <= value <= rng[1]):
                r.fail("the value is outside the setting range printed beside it", UnresolvedCause.CONFLICT)
                return r, None
            if rng[2] and rng[2].casefold() not in _UNIT_TEXT[unit]:
                r.fail(f"the printed unit {rng[2]!r} does not match the expected unit; no conversion is applied",
                       UnresolvedCause.CONFLICT)
                return r, None
        return r, value

    def choice(self, name: str, options: dict[str, object]) -> tuple[_Read, object | None]:
        r = self.read(name)
        if not r.ok:
            return r, None
        key = _norm(r.raw)
        if key not in options:
            r.fail(f"the value is not recognised by profile {PROFILE_VERSION}", UnresolvedCause.UNSUPPORTED)
            return r, None
        return r, options[key]

    # --- the sections -----------------------------------------------------------

    def interpret(self) -> CanonicalDistanceProtectionModel:
        metadata = self.metadata()
        zone_numbers = sorted({int(m.group(2)) for s in self.doc.settings if s.name and (m := _ZONE_PREFIX.match(s.name))})
        zones = tuple(self.zone(n) for n in zone_numbers)
        transformers = self.transformers(zones)
        line = self.line()
        unmapped = self.leftovers()
        self.finish_notes(zones)
        return CanonicalDistanceProtectionModel(
            metadata=metadata, transformers=transformers, line=line, zones=zones,
            unmapped_settings=unmapped, interpretation_notes=tuple(self.notes),
        )

    def metadata(self) -> RelayMetadata:
        schemes: dict[str, RawSetting] = {}
        for s in self.doc.settings:
            for text in (s.raw_value, s.name):
                m = _SCHEME.search(str(text)) if text else None
                if m:
                    schemes.setdefault(m.group(1), s)
        scheme_read = _Read("Scheme", tuple(dict.fromkeys(schemes.values())),
                            raw=" / ".join(f"Scheme: {t}" for t in schemes) or None)
        if len(schemes) > 1:
            scheme_read.fail("more than one scheme/template was stated; none selected", UnresolvedCause.CONFLICT)
        version = unresolved(cause=UnresolvedCause.MISSING)
        if scheme_read.found and scheme_read.problem is None:
            token = next(iter(schemes))
            scheme = self.good(token, (scheme_read,))
            if _MODEL_TOKEN.search(token):
                model = self.good(MODEL, (scheme_read,))
                manufacturer = self.good(
                    MANUFACTURER, (scheme_read,),
                    why="normalised from the RED670 model per the identification catalogue; the manufacturer is not named in the document",
                )
                family = self.good(FAMILY, (scheme_read,), why="family label from the identification catalogue")
                v = _VERSION_TOKEN.search(token)
                if v:
                    version = self.good(v.group(1), (scheme_read,), why="the version marker written in the scheme / device designation")
            else:
                model = manufacturer = family = self.bad(scheme_read, reason="the scheme does not name a RED670",
                                                         cause=UnresolvedCause.CONFLICT)
        else:
            scheme = model = manufacturer = family = self.bad(scheme_read)

        groups = {m.group(1): s for s in self.doc.settings for text in (s.raw_value,) if text and (m := _ACTIVE_GROUP.match(str(text)))}
        if len(groups) == 1:
            label, entry = next(iter(groups.items()))
            active = self.good(
                label, (_Read("Active Group", (entry,), raw=str(entry.raw_value)),),
                why="the header's 'Active Group' field, as written; it is a label, not checked against the relay's setting-group number",
            )
        else:
            active = unresolved(cause=UnresolvedCause.CONFLICT if groups else UnresolvedCause.MISSING)
        return RelayMetadata(
            source_format=self.doc.source_format, manufacturer=manufacturer, family=family, model=model,
            version=version, active_setting_group=active, profile_id=PROFILE_ID,
            profile_version=PROFILE_VERSION, scheme_name=scheme,
        )

    # --- transformers ------------------------------------------------------------

    def channels(self, name_re: re.Pattern, channel_type: str) -> list[int]:
        """Channel numbers whose ``NAMECH<n>`` is a phase channel (``..._IL1`` / ``..._UL1``) of the
        given ``ChannelType``. The line's CT / VT are these channels; unused channels keep defaults."""
        out = []
        for s in self.doc.settings:
            m = _CHANNEL_NUMBER.match(s.name or "")
            if not m or not name_re.search(_clean(s.raw_value)):
                continue
            n = int(m.group(1))
            kind = self.read(f"ChannelType{n}")
            if kind.ok and _norm(kind.raw) == _norm(channel_type):
                out.append(n)
        return sorted(out)

    def agreed(self, prefix: str, channels: list[int], what: str, *, unit: str, complete: int = 3) -> tuple[tuple[_Read, ...], float | None]:
        """One value shared by all phase channels: identical on every channel (else a conflict)."""
        reads, values = [], []
        for n in channels:
            r, v = self.number(f"{prefix}{n}", unit=unit)
            reads.append(r)
            values.append(v)
        if len(channels) != complete:
            for r in reads:
                self.refs(*r.entries)
            self.note(f"{what}: expected {complete} phase channels, found {len(channels)}; not resolved.")
            return tuple(reads), None
        if any(v is None for v in values) or len(set(values)) != 1:
            if all(v is not None for v in values):
                self.note(f"{what}: the phase channels do not agree ({sorted(set(values))}); none selected.")
                for r in reads:
                    r.fail("the phase channels do not agree", UnresolvedCause.CONFLICT)
            return tuple(reads), None
        return tuple(reads), values[0]

    def transformers(self, zones: tuple[DistanceZone, ...]) -> InstrumentTransformers:
        ct_ch = self.channels(_PHASE_CURRENT_CHANNEL, "CurrentProtection")
        vt_ch = self.channels(_PHASE_VOLTAGE_CHANNEL, "Voltage")
        ct_p_reads, ct_p = self.agreed("CTprim", ct_ch, "CT primary", unit="A")
        ct_s_reads, ct_s = self.agreed("CTsec", ct_ch, "CT secondary", unit="A")
        vt_p_reads, vt_p = self.agreed("VTprim", vt_ch, "VT primary", unit="kV")
        vt_s_reads, vt_s = self.agreed("VTsec", vt_ch, "VT secondary", unit="V")
        phase_names = "the three phase current channels (NAMECH ..._IL1 / IL2 / IL3)"
        voltage_names = "the three phase voltage channels (NAMECH ..._UL1 / UL2 / UL3)"

        def solved(value, reads, why, status="mapped"):
            return self.good(value, reads, status=status, why=why) if value is not None else self.bad(*reads)

        vt_unit_why = (
            "The sheet prints no unit for this VT row. kV (primary) and V (secondary) are the Relion 670 convention; "
            "the header (275kV) and the UBase rows agree. Confirm the unit."
        )
        # A channel's extras: the residual (IN) channel and the unused channels are not read.
        self.note(
            "CT and VT ratios are read from the channels named as the phase currents / voltages (IL1-IL3, UL1-UL3); "
            "the residual (IN) channel and the unused channels keep their defaults and are not interpreted."
        )

        # Bases: IBase / UBase of the zones that are in service (a disabled zone keeps placeholder defaults).
        live = [z for z in zones if z.status.is_resolved and z.status.value is ZoneStatus.ENABLED]
        i_reads, i_vals, u_reads, u_vals = [], [], [], []
        for z in live:
            n = int(z.zone_id[1:])
            r, v = self.number(f"ZM{n:02d}-:IBase", unit="A")
            i_reads.append(r); i_vals.append(v)
            r, v = self.number(f"ZM{n:02d}-:UBase", unit="kV")
            u_reads.append(r); u_vals.append(v)
        i_base = solved(i_vals[0], tuple(i_reads), "IBase of the zones in service (identical)") \
            if i_vals and None not in i_vals and len(set(i_vals)) == 1 else self.bad(*i_reads) if i_reads else unresolved(cause=UnresolvedCause.MISSING)
        u_base = solved(
            u_vals[0] * 1000.0, tuple(u_reads), "UBase (kV, phase-to-phase) of the zones in service (identical), converted to volts. " + vt_unit_why,
            status="inferred",
        ) if u_vals and None not in u_vals and len(set(u_vals)) == 1 else self.bad(*u_reads) if u_reads else unresolved(cause=UnresolvedCause.MISSING)

        evidence = tuple(e for z in zones for e in self.entries_of(f"ZM{int(z.zone_id[1:]):02d}-:IBase") + self.entries_of(f"ZM{int(z.zone_id[1:]):02d}-:UBase")
                         if z in live)
        basis = self.good(
            SettingBasis.PRIMARY, (), status="inferred", extra=evidence, raw="",
            why=(
                "The sheet gives its impedance settings (X1, R1, RFPP ...) without a unit or a basis. Every distance function "
                "carries IBase / UBase, and Relion 670 impedance settings are primary ohms referred to those bases (family "
                "convention); the printed ranges do not depend on the CT / VT ratio. Confirm this before relying on it."
            ),
        ) if evidence else unresolved(
            notes=("no zone in service carries IBase / UBase to establish the basis",), cause=UnresolvedCause.MISSING
        )
        return InstrumentTransformers(
            ct_primary_a=solved(ct_p, ct_p_reads, f"identical on {phase_names}"),
            ct_secondary_a=solved(ct_s, ct_s_reads, f"identical on {phase_names}"),
            vt_primary_v=solved(vt_p * 1000.0 if vt_p is not None else None, vt_p_reads,
                                f"identical on {voltage_names}; kV converted to volts. " + vt_unit_why, status="inferred"),
            vt_secondary_v=solved(vt_s, vt_s_reads, f"identical on {voltage_names}. " + vt_unit_why, status="inferred"),
            voltage_base_v=u_base,
            current_base_a=i_base,
            setting_basis=basis,
        )

    def entries_of(self, name: str) -> tuple[RawSetting, ...]:
        return tuple(self.by_name.get(_norm(name), ()))

    # --- line ---------------------------------------------------------------------

    def line(self) -> ProtectedLine:
        length_read, length = self.number("FLO1-:LineLength")
        r1, r1v = self.number("FLO1-:R1L", unit="ohm")
        x1, x1v = self.number("FLO1-:X1L", unit="ohm")
        r0, r0v = self.number("FLO1-:R0L", unit="ohm")
        x0, x0v = self.number("FLO1-:X0L", unit="ohm")
        why = ("read from the fault locator's line data: '1' / '0' are the positive / zero sequence and 'L' the protected "
               "line in the sheet's own names; the sheet does not label them")

        def pair(r, rv, x, xv):
            if rv is None or xv is None:
                return self.bad(r, x)
            return self.good(ImpedanceValue(r_ohm=rv, x_ohm=xv), (r, x), status="inferred", why=why,
                             raw=f"{r.raw} + j{x.raw}")

        self.note(
            "No line angle is stated, and none is derived from R1L / X1L; the line length has no printed unit "
            "(km or miles), so its unit is left unresolved."
        )
        return ProtectedLine(
            length=self.good(length, (length_read,)) if length is not None else self.bad(length_read),
            length_unit=unresolved(
                sources=self.refs(*length_read.entries) if length_read.found else (),
                notes=("the sheet prints no unit for LineLength (km and miles are both possible); none is assumed",),
                cause=UnresolvedCause.MISSING,
            ),
            positive_sequence_impedance=pair(r1, r1v, x1, x1v),
            zero_sequence_impedance=pair(r0, r0v, x0, x0v),
            line_angle_deg=unresolved(cause=UnresolvedCause.MISSING),
        )

    # --- zones ---------------------------------------------------------------------

    def zone(self, n: int) -> DistanceZone:
        p = f"ZM{n:02d}-:"
        zone_id, name = f"Z{n}", f"Zone {n}"
        op_r, op = self.choice(p + "Operation", _ON_OFF)
        dir_r, direction = self.choice(p + "OperationDir", _DIRECTIONS)

        status = self.status(zone_id, name, op_r, op, dir_r, direction)
        dir_s = self.good(direction, (dir_r,)) if direction is not None else self.bad(dir_r)

        pp_r, pp = self.choice(p + "OperationPP", _ON_OFF)
        pe_r, pe = self.choice(p + "OperationPE", _ON_OFF)
        pp_s = self.good(pp, (pp_r,)) if pp is not None else self.bad(pp_r)
        pe_s = self.good(pe, (pe_r,)) if pe is not None else self.bad(pe_r)

        x_r, x = self.number(p + "X1", unit="ohm")
        r1_r, r1 = self.number(p + "R1", unit="ohm")
        x0_r, x0 = self.number(p + "X0", unit="ohm")
        r0_r, r0 = self.number(p + "R0", unit="ohm")
        rfpp_r, rfpp = self.number(p + "RFPP", unit="ohm")
        rfpe_r, rfpe = self.number(p + "RFPE", unit="ohm")

        label = self.entries_of(f"IMP_PROT/DistanceZones/ZMQPDIS:{n}")
        evidence = tuple(label) + tuple(e for r in (x_r, rfpp_r, rfpe_r) if r.ok for e in r.entries)
        ctype = (
            inferred(
                CharacteristicType.QUADRILATERAL, sources=self.refs(*evidence), profile_id=PROFILE_ID,
                profile_version=PROFILE_VERSION,
                notes=(
                    "The sheet names the function block (ZMQPDIS) and gives a reactive reach with separate phase-phase / "
                    "phase-earth resistive reaches, but does not name the characteristic. ZMQPDIS is the Relion 670 "
                    "quadrilateral distance function (family knowledge).",
                ),
            )
            if label and x is not None
            else unresolved(
                sources=self.refs(*label), cause=UnresolvedCause.MISSING,
                notes=("the zone's ZMQPDIS section heading or its reactive reach was not found; the characteristic is not established",),
            )
        )

        loop_why = (
            "Relion 670 resistive reaches RFPP / RFPE are fault-resistance reaches per loop (ohm/loop), which the sheet "
            "does not state. The value is used as printed; if the relay's boundary in the measured impedance plane is a "
            "fraction of it (per-phase), the drawn boundary is wider than the relay's. Confirm."
        )
        left_note = (
            "The sheet states no left (-R) resistive reach. In a Relion 670 zone the left / lower boundary is formed by the "
            "directional element (ZDRDIR: ArgDir, ArgNegRes), which is not a resistive reach and which the current model cannot "
            "represent. Its rows are cited here. A drawn left boundary would be an approximation chosen by the user."
        )
        directional = tuple(e for nm in _DIRECTIONAL_ELEMENT for e in self.entries_of(nm))
        resistive = ResistiveReach(
            phase_phase=self.good(rfpp, (rfpp_r,), status="inferred", why=loop_why) if rfpp is not None else self.bad(rfpp_r),
            phase_earth=self.good(rfpe, (rfpe_r,), status="inferred", why=loop_why) if rfpe is not None else self.bad(rfpe_r),
            reverse=unresolved(sources=self.refs(*directional), notes=(left_note,), cause=UnresolvedCause.MISSING),
        )
        r1_extra = ExtraQuantity(
            "positive_sequence_resistance_r1",
            self.good(r1, (r1_r,), why="Stated by the sheet as the zone's R1. How the relay uses it is not stated; it does not set the drawn boundary.")
            if r1 is not None else self.bad(r1_r),
            unit="ohm",
        )
        zero = (
            self.good(ImpedanceValue(r_ohm=r0, x_ohm=x0), (r0_r, x0_r), raw=f"{r0_r.raw} + j{x0_r.raw}",
                      why="R0 / X0: the zone's zero-sequence reach; the relay derives its earth-fault compensation from R1 / X1 and R0 / X0. Preserved, not plotted.")
            if r0 is not None and x0 is not None else self.bad(r0_r, x0_r)
        )
        return DistanceZone(
            zone_id=zone_id, name=name, status=status, direction=dir_s,
            phase_phase_enabled=pp_s, phase_earth_enabled=pe_s,
            phase_timer_s=self.timer(n, "PP"), earth_timer_s=self.timer(n, "PE"),
            characteristic=CharacteristicSpec(type=ctype, parameters=(r1_extra,), geometry_mode=GeometryMode.EXPLICIT_RX),
            reach=unresolved(notes=("this zone states explicit R / X limits; it has no polar reach and no reach angle",),
                             cause=UnresolvedCause.MISSING),
            x_reach_ohm=self.good(x, (x_r,)) if x is not None else self.bad(x_r),
            zero_sequence_reach=zero,
            resistive_reach=resistive,
            source_notes=self.source_notes(n),
        )

    def status(self, zone_id, name, op_r, op, dir_r, direction) -> Sourced:
        """The zone's own activation parameters. ``Operation`` OFF, or ``OperationDir`` Off, puts
        the zone out of service; ON with a Forward / Reverse / Non-dir direction puts it in service.
        Anything else is unresolved."""
        off = op is False or direction is ZoneDirection.INACTIVE
        on = op is True and direction is not None and direction is not ZoneDirection.INACTIVE
        reads = tuple(r for r in (op_r, dir_r) if r.ok)
        if off:
            return self.good(ZoneStatus.DISABLED, reads, why=f"{name} is switched off by its own parameters (Operation / OperationDir)")
        if on:
            return self.good(ZoneStatus.ENABLED, reads, why=f"{name}: Operation is ON and OperationDir sets a direction")
        return self.bad(op_r, dir_r, reason=f"{name} in-service state is not established from Operation / OperationDir")

    def timer(self, n: int, loop: str) -> Sourced:
        p = f"ZM{n:02d}-:"
        gate_r, gate = self.choice(f"{p}Timer t{loop}", _ON_OFF)
        val_r, val = self.number(f"{p}t{loop}", unit="s")
        if gate is True and val is not None:
            return self.good(val, (gate_r, val_r))
        if gate is False:
            return unresolved(
                val_r.raw, sources=self.refs(*gate_r.entries, *val_r.entries), cause=UnresolvedCause.MISSING,
                notes=(f"The 'Timer t{loop}' switch is OFF, so t{loop} is not an operating delay of this zone; none is assumed.",),
            )
        if not gate_r.found and val is not None:
            return self.bad(gate_r, val_r, reason=f"the 'Timer t{loop}' switch was not found, so t{loop} is not established as in use")
        return self.bad(gate_r, val_r)

    def source_notes(self, n: int) -> tuple[SourceNote, ...]:
        """The document's notes about one zone ("Zone 1 | Forward direction timer set to 0.15s"),
        kept as notes: requirements and design intent, never the zone's settings."""
        out = []
        for s in self.doc.settings:
            m = _ZONE_NOTE_NAME.match(s.name or "")
            if s.parameter_id or not m or int(m.group(1)) != n or not _clean(s.raw_value):
                continue
            text = f"{s.name.strip()}  {_clean(s.raw_value)}"
            timer = _STATED_TIMER.search(text)
            if timer:
                subject, value = "timer", f"{timer.group(1)} s"
            elif _STATED_INACTIVE.search(text):
                subject, value = "status", "Inactive (out of service)"
            else:
                subject = value = None
            out.append(SourceNote(SourceNoteKind.PROPOSED_REQUIREMENT, text, subject, value, sources=self.refs(s)))
        return tuple(out)

    # --- completeness ------------------------------------------------------------------------

    def leftovers(self) -> tuple[UnresolvedSetting, ...]:
        out, section = [], ""
        for s in self.doc.settings:
            name = s.name or ""
            if "/" in name and s.raw_value is None and not s.parameter_id and re.match(r"^[A-Za-z_]+/", name):
                section = name
            if s.setting_id in self.consumed:
                continue
            distance = any(k in section for k in _DISTANCE_SECTIONS) or _norm(name) in _DISTANCE_NOTE_NAMES
            out.append(UnresolvedSetting(
                s.setting_id, s.name, s.raw_value, s.unit,
                reason=(f"distance-related setting not interpreted by {PROFILE_VERSION}" if distance
                        else "outside Distance Protection; retained, not interpreted"),
                out_of_scope=not distance,
            ))
        return tuple(out)

    def finish_notes(self, zones: tuple[DistanceZone, ...]) -> None:
        if zones:
            self.note(
                "Zone N is the ZMQPDIS function instance N (parameters 'ZM0N-:...'); the numbering follows the instance "
                "number and agrees with the sheet's scheme notes. A setting sheet carries settings only: blocking and "
                "tripping logic in the relay configuration is not visible here."
            )
            self.note(
                "Zone reach is stated as a reactive reach (X1) with phase-phase / phase-earth resistive reaches (RFPP / RFPE) "
                "and no reach angle, so none is modelled. No Left Resistive Reach (-R) is stated: the left boundary comes from "
                "the directional element (ZDRDIR), which the model cannot represent."
            )
            self.note(
                "Earth-fault compensation is derived by the relay from the zone's R1 / X1 and R0 / X0; no compensation "
                "factor is stated, so none is computed here. R0 / X0 are kept as the zone's zero-sequence reach."
            )
        if any(z.source_notes for z in zones):
            self.note(
                "The sheet's scheme requirements (timers, 'Zone 4 Inactive') are document notes, not current settings; the "
                "zone states and delays above come from the zones' own parameters."
            )


class HitachiRed670Profile:
    """``RelayProfile`` implementation for the Hitachi Energy / ABB Relion RED670 (hitachi-red670-v1)."""

    profile_id = PROFILE_ID
    version = PROFILE_VERSION
    validation_status = VALIDATION_STATUS

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        """CONFIRMED only when the document's own scheme field names a RED670."""
        for s in document.settings:
            for text in (s.raw_value, s.name):
                m = _SCHEME.search(str(text)) if text else None
                if m and _MODEL_TOKEN.search(m.group(1)):
                    return ProfileMatch(MatchLevel.CONFIRMED, ("scheme field names a RED670",))
        return ProfileMatch(MatchLevel.NONE)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        return _Interpreter(document).interpret()
