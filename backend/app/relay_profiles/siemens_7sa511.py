"""Siemens SIPROTEC 7SA511 engineering interpretation profile (Relay Import Slice 11).

``RawRelayDocument -> Siemens7SA511Profile -> CanonicalDistanceProtectionModel``

All 7SA511-specific knowledge -- DIGSI setting addresses and their expected
names, the unit and basis conventions of this setting-sheet template, the
Siemens zone naming (Z1, Z1B, Z2, Z3, Z1L and the Z4 fault-detection stage),
the ``Infinity`` entry of the timer rows and the R / RE, X / XE reach conventions --
lives here and nowhere else. The generic PDF extractor, the relay identifier,
the canonical model, the review, Apply Settings, the engine adapter and the
Distance Protection engine know nothing about it.

Profile version ``siemens-7sa511-v2`` (v1 read the sheet's range column as the timer
value and a note as a zone state; see the DEC-196 amendment). **Implemented / Awaiting Validation**:
it becomes ``Validated`` only after owner UAT against the real setting file.

This profile is deliberately written on its own. It does not derive from, or
share a base class with, any other Siemens profile: whether 7SA511, 7SA613 and
SIPROTEC 5 share enough to justify a family abstraction is decided when those
profiles exist and can be compared (not before).

Rules this profile never breaks
-------------------------------
* A value is ``mapped`` only when the sheet states it unambiguously (a
  code-and-name-checked setting whose unit the sheet establishes). Anything
  that rests on knowledge of the 7SA5 family that the sheet does not repeat
  (the secondary basis of the ohm settings, which loop an ``R`` / ``RE`` setting
  belongs to, which loops the global fault-type selection enables) is ``inferred``
  and carries a note.
* A setting is read only when its code *and* its name match this version's
  table. A known code under another name is unresolved, never trusted.
* A missing, conflicting, non-numeric, out-of-range or unit-unconfirmed
  setting becomes an unresolved value that keeps its raw text. Nothing is
  defaulted; the only unit conversion is kV -> V where the printed range says kV.
* The operating-timer rows of the sheet have a blank TAP SETTING cell; the word
  ``Infinity`` sits in the *range / allowed-values* column. That is not the
  configured delay and not a statement that the zone is out of service: the delay
  stays unresolved (Missing, so the user may state one). Only an ``Infinity`` in
  the value column itself is read as the Siemens "never" timer -- and even that is
  never turned into a finite delay or a zone state.
* The 7SA511 has no per-zone enable setting. ``1201 DIST.PROT. = ON`` says the
  distance *function* is on, not that any zone is enabled, so a zone's state is
  unresolved unless the function itself is switched off. A finite delay is
  deliberately *not* read as "enabled" either, so the generic 10.0 s defeated-zone
  rule (applied by the registry, not here, and not duplicated) and the user's own
  review decide.
* The sheet's notes ("Verification to be done", "Backup 21Z scheme requirements":
  timers, an inactive Zone 1B) are requirements and design intent, not current
  settings. They are kept as zone source notes with their source line and are never
  copied into a value or a status.
* The zones are quadrilaterals stated as explicit R / X limits (``X`` and ``R``,
  ``RE``); the sheet gives no reach angle, so none is modelled or invented. No left
  (-R) resistive limit is stated, so none is invented either.
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
    GeometryMode,
    InstrumentTransformers,
    ProtectedLine,
    RelayMetadata,
    ResidualCompensation,
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

PROFILE_ID = "siemens-7sa511"
PROFILE_VERSION = "siemens-7sa511-v2"
VALIDATION_STATUS = "Implemented / Awaiting Validation"

MANUFACTURER = "Siemens"
FAMILY = "SIPROTEC 7SA5"
MODEL = "7SA511"

#: Setting addresses (DIGSI numbering) from 1101 up to and including the
#: teleprotection / weak-infeed blocks belong to the distance function: system
#: data used by it, the distance zones, fault detection, loop selection, power
#: swing and the distance schemes. Everything else (device configuration,
#: communication, recorders, auto-reclose, other protection functions) does not.
_DISTANCE_ADDRESSES = range(1101, 2400)

# ---------------------------------------------------------------------------
# The parameter table: address -> the name this version expects for it
# ---------------------------------------------------------------------------

_VT_PRIMARY = ("1103", "Un PRIMARY")
_VT_SECONDARY = ("1104", "Un SECOND.")
_CT_PRIMARY = ("1105", "In PRIMARY")
_RE_RL = ("1117", "RE/RL")
_XE_XL = ("1118", "XE/XL")
_RM_RL = ("1119", "RM/RL")
_XM_XL = ("1120", "XM/XL")
_X_PER_LENGTH = ("1122", "X SEC")
_LINE_LENGTH = ("1124", "LINELENGTH")
_DIST_ON = ("1201", "DIST.PROT.")
_DIST_EXISTS = ("7812", "DIST. PROT.")
_DIR_FD_T4 = ("1202", "DIR. FD&T4")
_T4 = ("1203", "T4")
_PHPHE_FAULTS = ("1703", "PHPHE FLTS")
_THREE_PHASE_FAULTS = ("1704", "3PH FAULTS")
_ONE_PHASE_FAULTS = ("1705", "1PH FAULTS")

#: The fault-detection (impedance) polygon that delimits the Z4 stage. Its axis
#: and direction semantics are not decoded by this version; the rows are cited
#: by Z4's unresolved reach so they stay visible beside it.
_FD_POLYGON = (
    ("1621", "X+A"), ("1622", "X-A"), ("1623", "RA1"), ("1624", "RA2"),
    ("1625", "RA1E"), ("1626", "RA2E"), ("1627", "ANGLE PHIA"), ("1628", "ANGLE PHIAE"),
)
_T5 = ("1204", "T5")


@dataclass(frozen=True)
class _ZoneTable:
    zone_id: str
    name: str
    label: str  # how the sheet's notes write the zone ("Zone 1B" -> "1B")
    r_phase: tuple[str, str] | None = None
    x_reach: tuple[str, str] | None = None
    r_earth: tuple[str, str] | None = None
    direction: tuple[str, str] | None = None
    #: single-phase-fault and multi-phase-fault delays (two-timer zones) ...
    timer_single: tuple[str, str] | None = None
    timer_multi: tuple[str, str] | None = None
    #: ... or the one delay of a single-timer zone.
    timer_common: tuple[str, str] | None = None
    #: Zone 4 is the fault-detection stage: no zone-specific R / X settings.
    fault_detection: bool = False

    def codes(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            c for c in (self.r_phase, self.x_reach, self.r_earth, self.direction, self.timer_single,
                        self.timer_multi, self.timer_common) if c
        )


_ZONE_TABLE = (
    _ZoneTable("Z1", "Zone 1", "1", ("1301", "R1"), ("1302", "X1"), ("1303", "R1E"), ("1304", "DIREC. Z1"),
               ("1305", "T1 1PHASE"), ("1306", "T1 >1PHASE")),
    _ZoneTable("Z2", "Zone 2", "2", ("1311", "R2"), ("1312", "X2"), ("1313", "R2E"), ("1314", "DIREC. Z2"),
               ("1315", "T2 1PHASE"), ("1316", "T2 >1PHASE")),
    _ZoneTable("Z3", "Zone 3", "3", ("1321", "R3"), ("1322", "X3"), ("1323", "R3E"), ("1324", "DIREC. Z3"),
               timer_common=("1325", "T3")),
    _ZoneTable("Z4", "Zone 4", "4", direction=_DIR_FD_T4, timer_common=_T4, fault_detection=True),
    _ZoneTable("Z1B", "Zone 1B", "1B", ("1401", "R1B"), ("1402", "X1B"), ("1403", "R1BE"), ("1404", "DIREC. Z1B"),
               ("1405", "T1B 1PHASE"), ("1406", "T1B >1PHASE")),
    _ZoneTable("Z1L", "Zone 1L", "1L", ("1411", "R1L"), ("1412", "X1L"), ("1413", "R1LE"), ("1414", "DIREC. Z1L"),
               timer_common=("1415", "T1L")),
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
_MODEL_TOKEN = re.compile(r"(?<![A-Za-z0-9])7SA511(?![A-Za-z0-9])", re.IGNORECASE)
_VERSION_TOKEN = re.compile(r"(?<![A-Za-z0-9])(V\d+(?:\.\d+)*)(?![A-Za-z0-9.])")
_TAP_RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:A|AMP)\s*$", re.IGNORECASE)
_CT_RATIO_NOTE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*")
_INFINITE = {"infinity", "inf", "∞", "oo"}
_STATED_TIMER = re.compile(r"\btimer\s+set\s+to\s+(\d+(?:\.\d+)?)\s*s\b", re.IGNORECASE)
_STATED_INACTIVE = re.compile(r"(?<!not\s)\b(?:inactive|out\s+of\s+service)\b", re.IGNORECASE)
_CELLS = "cells:"

#: Printed unit text -> the unit this profile expects, per quantity.
_UNIT_TEXT = {
    "A": {"a", "amp", "amps"},
    "V": {"v"},
    "kV": {"kv"},
    "s": {"s", "sec"},
    "ohm": {"ohm", "ohms", "ω"},
    "km": {"km"},
    "ohm/km": {"ohm/km", "ohms/km", "ω/km"},
    "factor": {""},
}

_DIRECTIONS = {
    "forwards": ZoneDirection.FORWARD,
    "forward": ZoneDirection.FORWARD,
    "reverse": ZoneDirection.REVERSE,
    "reverse direction": ZoneDirection.REVERSE,
    "non-directional": ZoneDirection.NON_DIRECTIONAL,
    "non directional": ZoneDirection.NON_DIRECTIONAL,
}


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


def _split_range(text: str | None) -> tuple[float, float, str] | None:
    """(low, high, unit) of a printed numeric range such as ``0.05-65 ohms``."""
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
    """The outcome of looking up one address."""

    code: str
    name: str
    entries: tuple[RawSetting, ...] = ()
    raw: str | None = None
    problem: str | None = None
    cause: UnresolvedCause | None = None
    notes: tuple[str, ...] = ()
    #: True when the value is the Siemens ``Infinity`` timer setting.
    infinite: bool = False
    #: True when the setting's value cell is blank (the row may still print a range).
    blank: bool = False
    #: The printed range / allowed-values cell, when there is one.
    range_text: str | None = None

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

    dist_reads: tuple[_Read, ...] = ()
    dist_on: bool | None = None
    pp_read: _Read = None  # type: ignore[assignment]
    pp: bool | None = None
    pe_read: _Read = None  # type: ignore[assignment]
    pe: bool | None = None
    re_rl_read: _Read = None  # type: ignore[assignment]
    re_rl: float | None = None
    xe_xl_read: _Read = None  # type: ignore[assignment]
    xe_xl: float | None = None


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
        #: Per zone id, the delay reads (kept for the zone's status).
        self._timer_reads: dict[str, dict[str, _Read]] = {}

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
        unsupported); an absent address or a bare ``reason`` is missing."""
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
        """Entries for an address, validated by name and for duplicates."""
        code, expected = table
        found = tuple(self.by_code.get(code.upper(), ()))
        r = _Read(code, expected, found)
        if not found:
            return r
        wrong = [e for e in found if _norm_name(e.name) != _norm_name(expected)]
        if wrong:
            r.fail(
                f"the document names this address differently from what profile {PROFILE_VERSION} expects "
                f"({expected!r}); not trusted",
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
        r.range_text = _range_text(found[0])
        if not r.raw:
            r.fail("no value found", UnresolvedCause.UNREADABLE)
            r.raw = None
            r.blank = True
        elif len(found) > 1:
            r.notes = (f"{len(found)} identical duplicate entries in the document",)
        return r

    def number(self, table: tuple[str, str], *, unit: str, allow_infinite: bool = False) -> tuple[_Read, float | None]:
        """A numeric setting whose printed range/unit must agree with ``unit`` (a
        key of ``_UNIT_TEXT``). A kV setting is returned in volts. With
        ``allow_infinite`` the Siemens ``Infinity`` timer is recognised: the read
        stays ok, ``infinite`` is set and no number is returned."""
        r = self.read(table)
        if not r.ok:
            return r, None
        if allow_infinite and _norm_name(r.raw) in _INFINITE:
            r.infinite = True
            return r, None
        value = _parse_number(r.raw)
        if value is None:
            r.fail("the value is not a plain number", UnresolvedCause.UNREADABLE)
            return r, None
        rng = _split_range(_range_text(r.entries[0]))
        printed = rng[2] if rng is not None else (_range_text(r.entries[0]) or "")
        if rng is not None and not (rng[0] <= value <= rng[1]):
            r.fail("the value is outside the setting range printed beside it", UnresolvedCause.CONFLICT)
            return r, None
        if unit == "s" and rng is None and not printed:
            return r, value  # a delay printed without a range carries no unit text to check
        if printed.casefold() not in _UNIT_TEXT[unit]:
            r.fail(
                f"the printed unit {printed!r} does not establish {unit!r}; no unit conversion is applied",
                UnresolvedCause.CONFLICT if printed else UnresolvedCause.MISSING,
            )
            return r, None
        if unit == "kV":
            r.notes = (*r.notes, "the printed range is in kV; converted to volts (x 1000)")
            return r, value * 1000.0
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

    def statements(self, label: str) -> tuple[RawSetting, ...]:
        """Scheme-note entries about one zone ("Zone 1B Inactive timer ...")."""
        pattern = re.compile(rf"^\s*zone\s*{re.escape(label)}(?![0-9A-Za-z])", re.IGNORECASE)
        return tuple(s for s in self.doc.settings if not s.parameter_id and pattern.match(_entry_text(s)))

    # --- the sections -----------------------------------------------------------

    def interpret(self) -> CanonicalDistanceProtectionModel:
        metadata = self.metadata()
        transformers = self.transformers()
        line = self.line()
        zones = self.zones()
        unmapped = self.leftovers()
        self.finish_notes(zones)
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
        version = unresolved(cause=UnresolvedCause.MISSING)
        if scheme_read.found and scheme_read.problem is None:
            token = next(iter(schemes))
            scheme = self.good(token, (scheme_read,))
            if _MODEL_TOKEN.search(token):
                model = self.good(MODEL, (scheme_read,))
                manufacturer = self.good(
                    MANUFACTURER, (scheme_read,),
                    why="normalised from the 7SA511 model per the identification catalogue; the manufacturer is not named in the document",
                )
                family = self.good(FAMILY, (scheme_read,), why="family label from the identification catalogue")
                v = _VERSION_TOKEN.search(token)
                if v:
                    version = self.good(
                        v.group(1), (scheme_read,),
                        why="the version marker written in the scheme / device designation",
                    )
            else:
                model = manufacturer = family = self.bad(
                    scheme_read, reason="the scheme does not name a 7SA511", cause=UnresolvedCause.CONFLICT
                )
        else:
            scheme = model = manufacturer = family = self.bad(scheme_read)

        # The header's "Active Group" is a document revision label (e.g. an
        # issue/endorsement code), not a Siemens parameter-set selection.
        header = tuple(s for s in self.doc.settings if _norm_name(s.raw_value).startswith("active group:"))
        active = unresolved(
            header[0].raw_value if header else None,
            sources=self.refs(*header),
            notes=("the header's 'Active Group' reads as a document revision label, not a relay parameter-set setting; not interpreted",),
            cause=UnresolvedCause.MISSING,
        )
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
        vt_p, vt_p_v = self.number(_VT_PRIMARY, unit="kV")
        vt_s, vt_s_v = self.number(_VT_SECONDARY, unit="V")

        # The CT secondary is the relay's nominal-current tap ("IN", "1 AMP").
        tap = _Read("", "IN")
        for s in self.doc.settings:
            if not s.parameter_id and _norm_name(s.name) == "in":
                cells = next((n[len(_CELLS):].split("|") for n in s.notes if n.startswith(_CELLS)), None)
                if cells and len(cells) >= 3:
                    tap = _Read("", "IN", (s,), raw=_clean(s.raw_value) or None)
                    printed = _TAP_RANGE.match(cells[2].strip())
                    value = _parse_number(_clean(s.raw_value))
                    if not (printed and value is not None and value == float(printed.group(1))):
                        tap.fail("the tap value and its printed range do not establish a nominal current", UnresolvedCause.CONFLICT)
                break
        ct_s_v = _parse_number(tap.raw or "") if tap.ok else None

        def sourced(read: _Read, value, **kw) -> Sourced:
            return self.good(value, (read,), **kw) if value is not None else self.bad(read)

        self.note_ratio_check(ct_p_v, ct_s_v)

        # The sheet says only "ohms" -- never primary or secondary.
        x_rows = next((self.read(z.x_reach).entries for z in _ZONE_TABLE if z.x_reach and self.read(z.x_reach).found), ())
        evidence = x_rows[:1] + tap.entries
        basis = self.good(
            SettingBasis.SECONDARY, (), status="inferred", extra=evidence, raw="",
            why=(
                "The sheet states its impedance settings in 'ohms' without saying primary or secondary. Siemens 7SA5 "
                "impedance settings are secondary values (relay-family convention) and the printed setting ranges do "
                "not depend on the CT/VT ratio. Confirm this before relying on it."
            ),
        ) if evidence else unresolved(
            notes=("no impedance setting was found to establish the basis",), cause=UnresolvedCause.MISSING
        )
        return InstrumentTransformers(
            ct_primary_a=sourced(ct_p, ct_p_v),
            ct_secondary_a=(
                self.good(
                    ct_s_v, (tap,),
                    why="the relay's nominal-current tap (IN); the scheme name and the verification note agree",
                )
                if ct_s_v is not None else self.bad(tap)
            ),
            vt_primary_v=sourced(vt_p, vt_p_v),
            vt_secondary_v=sourced(vt_s, vt_s_v),
            setting_basis=basis,
        )

    def note_ratio_check(self, primary: float | None, secondary: float | None) -> None:
        """The verification notes restate the CT ratio; a disagreement is
        reported, never silently resolved either way."""
        for s in self.doc.settings:
            if "ct ratio" in (s.name or "").casefold() and s.raw_value:
                m = _CT_RATIO_NOTE.fullmatch(str(s.raw_value))
                if m and primary is not None and secondary is not None and (float(m[1]), float(m[2])) != (primary, secondary):
                    self.note(
                        "The CT ratio restated in the verification note differs from the CT settings; "
                        "the settings were used and the difference needs review."
                    )

    def line(self) -> ProtectedLine:
        length_read, length = self.number(_LINE_LENGTH, unit="km")
        if length is not None:
            length_s = self.good(length, (length_read,))
            unit_s = self.good("km", (length_read,), why="the unit printed in the setting's range")
        else:
            length_s = self.bad(length_read)
            unit_s = self.bad(length_read)
        x_read, x_per_km = self.number(_X_PER_LENGTH, unit="ohm/km")
        rm_read, rm = self.number(_RM_RL, unit="factor")
        xm_read, xm = self.number(_XM_XL, unit="factor")
        extras = (
            ExtraQuantity("reactance_per_length", self.good(x_per_km, (x_read,)) if x_per_km is not None else self.bad(x_read), unit="ohm/km"),
            ExtraQuantity("mutual_compensation_rm_rl", self.good(rm, (rm_read,)) if rm is not None else self.bad(rm_read)),
            ExtraQuantity("mutual_compensation_xm_xl", self.good(xm, (xm_read,)) if xm is not None else self.bad(xm_read)),
        )
        positive = unresolved(
            notes=("the sheet gives a reactance per length only, without naming a sequence or a resistance; no sequence impedance is claimed",),
            cause=UnresolvedCause.MISSING,
        )
        self.note(
            "The line is described by a reactance per length and a length only; no line angle and no "
            "sequence impedance are stated, so none is claimed or derived."
        )
        return ProtectedLine(
            length=length_s,
            length_unit=unit_s,
            positive_sequence_impedance=positive,
            line_angle_deg=unresolved(cause=UnresolvedCause.MISSING),
            extras=extras,
        )

    # --- zones ---------------------------------------------------------------------

    def context(self) -> _Context:
        ctx = _Context()
        on_read, on = self.choice(_DIST_ON, {"on": True, "off": False})
        ex_read, ex = self.choice(_DIST_EXISTS, {"exist": True, "noexist": False, "non-exist": False, "no exist": False})
        ctx.dist_reads = (on_read, ex_read)
        if on is False or ex is False:
            ctx.dist_on = False
        elif on is True and (ex is True or not ex_read.found):
            ctx.dist_on = True

        pp3_read, pp3 = self.choice(_THREE_PHASE_FAULTS, {"phase-phase only": True, "phase-phase": True})
        ctx.pp_read, ctx.pp = pp3_read, (True if pp3 else None)
        pe1_read, pe1 = self.choice(_ONE_PHASE_FAULTS, {"phase-earth": True})
        ctx.pe_read, ctx.pe = pe1_read, (True if pe1 else None)
        ctx.re_rl_read, ctx.re_rl = self.number(_RE_RL, unit="factor")
        ctx.xe_xl_read, ctx.xe_xl = self.number(_XE_XL, unit="factor")
        self.note(
            "Fault-type loop selection (PHPHE FLTS, 3PH FAULTS, 1PH FAULTS) and the earth compensation "
            "(RE/RL, XE/XL) are relay-wide settings; every zone cites the same values."
        )
        return ctx

    def zones(self) -> tuple[DistanceZone, ...]:
        ctx = self.context()
        present = [t for t in _ZONE_TABLE if any(self.read(c).found for c in t.codes())]
        return tuple(self.zone(t, ctx) for t in present)

    def zone(self, t: _ZoneTable, ctx: _Context) -> DistanceZone:
        rph_read, rph = self.number(t.r_phase, unit="ohm") if t.r_phase else (None, None)
        x_rd, x_val = self.number(t.x_reach, unit="ohm") if t.x_reach else (None, None)
        rpe_read, rpe = self.number(t.r_earth, unit="ohm") if t.r_earth else (None, None)

        timers = self.timers(t)
        direction = self.direction(t)
        status = self.status(t, ctx, timers)

        pp = (
            self.good(True, (ctx.pp_read,), status="inferred",
                      why="3PH FAULTS selects the phase-phase loop; this relay-wide selection is applied to every zone")
            if ctx.pp else self.bad(ctx.pp_read)
        )
        pe = (
            self.good(True, (ctx.pe_read,), status="inferred",
                      why="1PH FAULTS selects the phase-earth loop; this relay-wide selection is applied to every zone")
            if ctx.pe else self.bad(ctx.pe_read)
        )

        if t.fault_detection:
            polygon = tuple(e for code in _FD_POLYGON for e in self.read(code).entries)
            why = (
                "Zone 4 is the fault-detection stage: it has no zone-specific R / X settings. Its extent is the "
                "fault-detection polygon (1621-1628), whose axes and direction are not decoded by this profile version."
            )
            reach_s = unresolved(
                sources=self.refs(*polygon), notes=(why,), cause=UnresolvedCause.MISSING
            )
            ctype = unresolved(notes=(why,), cause=UnresolvedCause.MISSING)
            x_s = unresolved(notes=(why,), cause=UnresolvedCause.MISSING)
            resistive = ResistiveReach()
        else:
            # The sheet states X and R as separate limits and no reach angle: the reach is carried
            # as an explicit X limit, never as a polar magnitude-at-angle.
            reach_s = unresolved(
                notes=("this zone states explicit R / X limits; it has no polar reach and no reach angle",),
                cause=UnresolvedCause.MISSING,
            )
            x_s = self.good(x_val, (x_rd,)) if x_val is not None else self.bad(x_rd)
            evidence = tuple(e for r in (rph_read, rpe_read, x_rd) if r is not None and r.ok for e in r.entries)
            ctype = (
                inferred(
                    CharacteristicType.QUADRILATERAL,
                    sources=self.refs(*evidence),
                    profile_id=PROFILE_ID,
                    profile_version=PROFILE_VERSION,
                    notes=(
                        "the 7SA511 distance zones are polygons (quadrilaterals); the sheet does not name the "
                        "characteristic, but it gives separate reactance and phase / earth resistance reaches",
                    ),
                )
                if evidence
                else unresolved(notes=("no usable reach to establish the characteristic",), cause=UnresolvedCause.MISSING)
            )
            loop_why = (
                "the unsuffixed R setting is read as the phase-phase loop and the 'E' setting as the phase-earth loop "
                "(the sheet pairs them and uses the 'E' suffix for earth quantities, as in RE/RL and XE/XL); "
                "the sheet does not label the loop type"
            )
            resistive = ResistiveReach(
                phase_phase=self.good(rph, (rph_read,), status="inferred", why=loop_why) if rph is not None else self.bad(rph_read),
                phase_earth=self.good(rpe, (rpe_read,), status="inferred", why=loop_why) if rpe is not None else self.bad(rpe_read),
            )

        compensation = None
        if not t.fault_detection:
            compensation = ResidualCompensation(
                kind=CompensationKind.RE_RL_XE_XL,
                re_rl=self.good(ctx.re_rl, (ctx.re_rl_read,)) if ctx.re_rl is not None else self.bad(ctx.re_rl_read),
                xe_xl=self.good(ctx.xe_xl, (ctx.xe_xl_read,)) if ctx.xe_xl is not None else self.bad(ctx.xe_xl_read),
            )

        return DistanceZone(
            zone_id=t.zone_id,
            name=t.name,
            status=status,
            direction=direction,
            phase_phase_enabled=pp,
            phase_earth_enabled=pe,
            phase_timer_s=timers.get("multi", unresolved()),
            earth_timer_s=timers.get("single", unresolved()),
            common_timer_s=timers.get("common", unresolved()),
            characteristic=CharacteristicSpec(
                type=ctype, geometry_mode=GeometryMode.POLAR_REACH if t.fault_detection else GeometryMode.EXPLICIT_RX
            ),
            reach=reach_s,
            x_reach_ohm=x_s,
            source_notes=self.source_notes(t),
            resistive_reach=resistive,
            compensation=compensation,
        )

    def timers(self, t: _ZoneTable) -> dict[str, Sourced]:
        """The zone's delays by kind (``single`` / ``multi`` / ``common``). A finite
        delay is a value; a blank cell or an ``Infinity`` is kept unresolved (Missing);
        the zone's operating-delay reads are kept for the status."""
        out: dict[str, Sourced] = {}
        reads: dict[str, _Read] = {}
        loop_why = {
            "single": "T..1PHASE is the delay for single-phase faults, which the relay-wide loop selection evaluates in the phase-earth loop",
            "multi": "T..>1PHASE is the delay for multi-phase faults, which the relay-wide loop selection evaluates in the phase-phase loop",
        }
        for kind, table in (("single", t.timer_single), ("multi", t.timer_multi), ("common", t.timer_common)):
            if table is None:
                continue
            read, value = self.number(table, unit="s", allow_infinite=True)
            reads[kind] = read
            if value is not None:
                out[kind] = (
                    self.good(value, (read,), status="inferred", why=loop_why[kind]) if kind != "common" else self.good(value, (read,))
                )
            elif read.infinite:
                out[kind] = unresolved(
                    read.raw, sources=self.refs(*read.entries), cause=UnresolvedCause.MISSING,
                    notes=(
                        "The sheet sets this delay to Infinity (no finite operating delay is stated), so none is assumed; "
                        "state the delay in the review if the zone is in service.",
                    ),
                )
            elif read.blank:
                notes = ["The sheet leaves the setting cell of this timer blank, so no delay is stated."]
                if read.range_text and _norm_name(read.range_text) in _INFINITE:
                    notes.append(
                        "The 'Infinity' printed in the range column is the allowed value of the setting, not the configured "
                        "delay. It is not read as a delay, and not as the zone being out of service."
                    )
                notes.append("State the delay in the review if the zone is in service.")
                out[kind] = unresolved(
                    None, sources=self.refs(*read.entries), notes=tuple(notes), cause=UnresolvedCause.MISSING
                )
            else:
                out[kind] = self.bad(read)
        self._timer_reads[t.zone_id] = reads
        return out

    def direction(self, t: _ZoneTable) -> Sourced:
        read, value = self.choice(t.direction, _DIRECTIONS) if t.direction else (_Read("", ""), None)
        if value is not None:
            return self.good(value, (read,))
        return self.bad(read)

    def status(self, t: _ZoneTable, ctx: _Context, timers: dict[str, Sourced]) -> Sourced:
        reads = self._timer_reads[t.zone_id].values()
        timer_entries = tuple(e for r in reads for e in r.entries)
        if ctx.dist_on is False:
            decisive = next((r for r in ctx.dist_reads if r.ok and _norm_name(r.raw) in {"off", "noexist", "non-exist", "no exist"}), ctx.dist_reads[0])
            return self.good(
                ZoneStatus.DISABLED, (decisive,), status="inferred",
                why="the Distance Protection function is switched off or not present in the relay configuration",
            )
        if ctx.dist_on is None:
            return self.bad(*ctx.dist_reads, reason=f"{t.name} in-service state is not established (Distance Protection state unresolved)")
        # The 7SA511 has no per-zone enable setting, and 1201 DIST.PROT. = ON is the state of the whole
        # distance function. Neither that, nor a finite delay, nor a design note makes a zone enabled or
        # disabled: the state is left unresolved so that the generic defeated-zone rule (a 10.0 s delay)
        # and the user's own review decide, never this profile.
        function_entries = tuple(e for r in ctx.dist_reads if r.ok for e in r.entries)
        return unresolved(
            sources=self.refs(*function_entries, *timer_entries),
            notes=(
                f"{t.name} has no per-zone enable setting. DIST.PROT. = ON states that the distance function as a whole "
                "is on, not that this zone is enabled; no zone state is assumed.",
            ),
            cause=UnresolvedCause.MISSING,
        )

    def source_notes(self, t: _ZoneTable) -> tuple[SourceNote, ...]:
        """The document's notes about one zone, kept as notes: requirements and design intent
        ("Backup 21Z scheme requirements"), never the zone's current settings."""
        out = []
        for s in self.statements(t.label):
            text = _entry_text(s).strip()
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
        out = []
        for s in self.doc.settings:
            if s.setting_id in self.consumed:
                continue
            code = (s.parameter_id or "")
            distance = code.isdigit() and int(code) in _DISTANCE_ADDRESSES
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

    def finish_notes(self, zones: tuple[DistanceZone, ...]) -> None:
        if any(z.x_reach_ohm.is_resolved for z in zones):
            self.note(
                "Zone reach is stated as explicit R / X limits: the reactive reach (X) and the resistive reach (R). "
                "The sheet states no reach angle, so none is modelled."
            )
            self.note("No Left Resistive Reach (−R) is stated by the sheet.")
        if any(z.source_notes for z in zones):
            self.note(
                "The sheet's notes state timers and zone states as verification / backup-scheme requirements. They are "
                "document notes, not current settings, and are not applied; state the delays and zone states that apply "
                "in the review."
            )


class Siemens7SA511Profile:
    """``RelayProfile`` implementation for the Siemens SIPROTEC 7SA511 (siemens-7sa511-v1)."""

    profile_id = PROFILE_ID
    version = PROFILE_VERSION
    validation_status = VALIDATION_STATUS

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        """CONFIRMED only when the document's own scheme field names a 7SA511.
        (Routing from an upload goes through the identification verdict; this
        keeps ``registry.interpret()`` from reading other relays as a 7SA511.)"""
        for s in document.settings:
            for text in (s.raw_value, s.name):
                m = _SCHEME.search(str(text)) if text else None
                if m and _MODEL_TOKEN.search(m.group(1)):
                    return ProfileMatch(MatchLevel.CONFIRMED, ("scheme field names a 7SA511",))
        return ProfileMatch(MatchLevel.NONE)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        return _Interpreter(document).interpret()
