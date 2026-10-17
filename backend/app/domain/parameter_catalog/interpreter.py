"""The generic matcher / transformer: a `Catalog` + a `RawRelayDocument` -> a canonical model.

This module contains **no manufacturer-specific logic**. Everything relay-specific arrives as
catalog data; the steps here are always the same:

1. find the zone instances the catalog describes;
2. for each mapping (document level, then zone level, then document level that reads zones):
   match raw settings by code / name / section, read the declared value source, validate type,
   range and unit, apply the approved transformation primitives, and record provenance;
3. write each resulting `Sourced` into the canonical model at the engine path the canonical
   registry gives for its target;
4. keep every raw setting nothing consumed as *not interpreted*.

Precedence when more than one mapping could supply the same canonical value: the strongest
authority wins (explicit configured setting > structured engineering instruction > documented
deterministic derivation > assumption), and the winner's provenance is the one recorded. A
mapping that does not resolve falls through to the next; if none resolves, the strongest
mapping's unresolved result (with its cause and notes) is kept. A printed range, a default or a
free-text note is never a value source (the catalog validator refuses it).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any

from app.domain.parameter_catalog.catalog_model import (
    AUTHORITY_PRECEDENCE,
    VALUE_SOURCE_PRECEDENCE,
    BoundarySpec,
    Catalog,
    Family,
    Mapping,
    Selector,
)
from app.domain.parameter_catalog.registry import ENUM_TYPES, CanonicalParameter, CanonicalRegistry
from app.domain.distance_boundaries import (
    BoundaryFrame,
    BoundaryProvenance,
    BoundarySide,
    BoundarySource,
    DirectionalBoundary,
    ReactanceLowerBoundary,
    ResistiveBoundary,
    RetainedSide,
    TiltedReactanceBoundary,
)
from app.domain.parameter_catalog.transforms import PRIMITIVES, TransformError, expected_unit, fmt, norm_text
from app.domain.parameter_catalog.units import conversion_factor, printed_matches
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    InstrumentTransformers,
    ProtectedLine,
    RelayMetadata,
    ResidualCompensation,
    SourceNote,
    SourceNoteKind,
    UnresolvedSetting,
)
from app.domain.relay_import.provenance import (
    DocumentReference,
    MappingAuthority,
    Sourced,
    SourceRef,
    UnresolvedCause,
    inferred,
    mapped,
    unresolved,
)
from app.domain.relay_import.raw_document import RawRelayDocument, RawSetting

_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_RANGE = re.compile(
    r"^\s*(?P<lo>[+-]?\d+(?:\.\d+)?)\s*(?:-|to)\s*(?P<hi>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>.*?)\s*$", re.IGNORECASE,
)
_CELLS = "cells:"
_TEMPLATE = re.compile(r"\{([A-Za-z_]+)\}")
#: A section heading row: a path-like name with no value and no parameter code (``GROUP/Sub/Function:1``).
_HEADING = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*/")

#: Strongest first: when several reads of one value fail, the strongest cause names the problem.
_CAUSE_ORDER = (UnresolvedCause.CONFLICT, UnresolvedCause.UNREADABLE, UnresolvedCause.UNSUPPORTED)
#: Primitives whose sentence belongs in the provenance ("how the printed value became the canonical one").
_NUMERIC_STEPS = frozenset({"scale", "multiply", "divide", "ratio", "unit_conversion", "percentage"})


#: How a source states "infinity" (case-folded).
_INFINITY_TEXTS = frozenset({"infinity", "∞", "inf", "oo"})


def _clean(text: Any) -> str:
    return "" if text is None else str(text).strip()


def _fill(template: str, variables: dict[str, Any]) -> str:
    return _TEMPLATE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), template)


def _range_text(s: RawSetting) -> str | None:
    """The printed range / options cell: the extractor's range, else the last cell of a
    four-column row (code | name | value | range)."""
    if s.setting_range and s.setting_range.text:
        return s.setting_range.text.strip()
    for note in s.notes:
        if note.startswith(_CELLS):
            cells = [c.strip() for c in note[len(_CELLS):].split("|")]
            if len(cells) >= 4 and cells[-1]:
                return cells[-1]
    return None


#: The extractor's rule for a table row whose value cell is blank while its range cell is filled.
_BLANK_VALUE_RULE = "row:blank_value_range"


def _blank_setting_cell(s: RawSetting) -> bool:
    return s.extraction is not None and _BLANK_VALUE_RULE in s.extraction.notes


@dataclass
class _Read:
    """The outcome of looking up one source (or one family of sources)."""

    name: str
    entries: tuple[RawSetting, ...] = ()
    raw: str | None = None
    problem: str | None = None
    cause: UnresolvedCause | None = None
    notes: tuple[str, ...] = ()
    value: Any = None
    #: Sentence for a unit conversion applied while reading (``220 kV → 220000 V``).
    conversion: str | None = None

    def fail(self, problem: str, cause: UnresolvedCause) -> None:
        self.problem = problem
        self.cause = cause
        self.value = None

    @property
    def found(self) -> bool:
        return bool(self.entries)

    @property
    def ok(self) -> bool:
        return self.found and self.problem is None


@dataclass(frozen=True)
class PlainValue:
    """The value for a plain (non-``Sourced``) canonical field, e.g. a geometry mode."""

    value: Any

    is_resolved = True


@dataclass
class Outcome:
    """What one canonical target resolved to, and which mapping supplied it."""

    result: Sourced | PlainValue
    mapping: Mapping
    zone: str = ""


@dataclass(frozen=True)
class CatalogRun:
    """One interpretation run: the catalog's own model, its per-target outcomes and the ids of every
    raw setting a mapping consumed (whether or not it resolved)."""

    model: CanonicalDistanceProtectionModel
    outcomes: dict[tuple[str, str], Outcome]
    consumed: frozenset[str]
    #: Rows kept as zone document notes (provenance only, never values).
    note_ids: frozenset[str] = frozenset()
    #: Rows kept raw with their zone (recognised, not interpreted: a capability gap).
    preserved_ids: frozenset[str] = frozenset()


#: Said once when any zone carries document notes.
ZONE_NOTES_STATEMENT = (
    "The sheet's notes about zones (scheme requirements such as proposed timers or states) are shown beside "
    "their zones as document notes. They are not settings and are never used as values, states or defaults."
)


class CatalogInterpreter:
    """Interprets documents with one validated catalog (stateless between calls)."""

    def __init__(self, catalog: Catalog, registry: CanonicalRegistry) -> None:
        self.catalog = catalog
        self.registry = registry

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        return _Run(self.catalog, self.registry, document).run()

    def run(self, document: RawRelayDocument) -> "CatalogRun":
        """The model plus what produced it: every resolved target with its mapping, and the raw
        settings a mapping consumed. The catalog-first profile and the dry-run read this."""
        run = _Run(self.catalog, self.registry, document)
        model = run.run()
        return CatalogRun(model, dict(run.results), frozenset(run.consumed), frozenset(run.note_ids),
                          frozenset(run.preserved_ids))

    def trace(self, document: RawRelayDocument) -> dict[tuple[str, str], Outcome]:
        """Every resolved canonical target with the mapping that supplied it (for tests and tooling)."""
        run = _Run(self.catalog, self.registry, document)
        run.run()
        return dict(run.results)

    def shadow_boundaries(self, document: RawRelayDocument) -> "BoundaryRun":
        """DEC-199 Phase 2A / 2B / 2C / 2D, SHADOW MODE: the catalog's canonical boundaries for this document. Never
        part of the canonical model, a review or readiness, and nothing is consumed (coverage is unchanged)."""
        run = _Run(self.catalog, self.registry, document)
        run._zones()
        boundaries: list[ResistiveBoundary] = []
        directional: list[DirectionalBoundary] = []
        lower: list[ReactanceLowerBoundary] = []
        upper: list[TiltedReactanceBoundary] = []
        unresolved: list[tuple[str, str, str]] = []
        for spec in self.catalog.boundaries:
            for z in run.zone_vars:
                if "*" not in spec.zones and z["zone"] not in spec.zones:
                    continue
                closed = None
                for gate in spec.gates:
                    g = run.locate(gate.source, z)
                    if not g.ok or norm_text(g.raw) not in {norm_text(x) for x in gate.equals}:
                        closed = f"{g.name} is {g.raw!r}" if g.ok else f"{g.name}: {g.problem or 'not present in the document'}"
                        break
                if closed:
                    unresolved.append((spec.id, z["zone"], closed))
                    continue
                try:
                    derived = self._shadow_boundary(run, spec, z)
                except ValueError as exc:
                    unresolved.append((spec.id, z["zone"], str(exc)))
                    continue
                (directional if isinstance(derived, DirectionalBoundary)
                 else lower if isinstance(derived, ReactanceLowerBoundary)
                 else upper if isinstance(derived, TiltedReactanceBoundary) else boundaries).append(derived)
        return BoundaryRun(tuple(boundaries), tuple(unresolved), tuple(directional), tuple(lower), tuple(upper))

    def _shadow_boundary(self, run: "_Run", spec: BoundarySpec,
                         z: dict[str, Any]) -> "ResistiveBoundary | DirectionalBoundary | ReactanceLowerBoundary | TiltedReactanceBoundary":
        """One boundary of one zone; a ValueError says why it is not derived."""
        canonical = _fill(spec.canonical, z) if spec.canonical else None
        if spec.kind == "reactance_lower":
            xm = run._boundary_number(spec.x_minus, z)
            if xm.problem:
                raise ValueError(f"{xm.name}: {xm.problem}")
            sources = tuple(BoundarySource("x_minus", e.name, e.parameter_id, _clean(e.raw_value) or None, spec.x_minus.unit,
                                           e.location.page, e.location.line) for e in xm.entries[:1])
            return ReactanceLowerBoundary(
                z["zone"], xm.value, BoundaryFrame(spec.frame),
                BoundaryProvenance(sources, canonical, f"x_minus = +{xm.name} (as printed, ohm): X >= -{fmt(xm.value)} ohm",
                                   spec.equation, spec.references, self.catalog.key, spec.convention),
                fidelity=spec.fidelity)
        if spec.kind == "reactance_upper":
            xref = run._boundary_number(spec.x_at_reference, z)
            if xref.problem:
                raise ValueError(f"{xref.name}: {xref.problem}")
            tilt = run._boundary_number(spec.tilt_deg, z)
            if tilt.problem:
                raise ValueError(f"{tilt.name}: {tilt.problem}")
            if spec.tilt_range is not None and not spec.tilt_range[0] <= tilt.value <= spec.tilt_range[1]:
                lo, hi = spec.tilt_range
                raise ValueError(f"{tilt.name}: {fmt(tilt.value)} is outside the documented setting range {fmt(lo)}-{fmt(hi)} "
                                 "deg, so the documented tilt convention is not established for it")
            tilt_deg = spec.tilt_sign * tilt.value
            sources = tuple(
                BoundarySource(role, read.name, e.parameter_id, _clean(e.raw_value) or None, sel.unit, e.location.page, e.location.line)
                for role, read, sel in (("x_at_reference", xref, spec.x_at_reference), ("tilt_deg", tilt, spec.tilt_deg))
                for e in read.entries[:1]
            )
            transform = (f"x_at_reference = +{xref.name} (as printed, ohm); "
                        f"tilt_deg = {'-' if spec.tilt_sign < 0 else '+'}{tilt.name} = {fmt(tilt_deg)} deg "
                        f"({tilt.name} {fmt(tilt.value)} as printed, deg)")
            return TiltedReactanceBoundary(
                z["zone"], xref.value, tilt_deg, BoundaryFrame(spec.frame),
                BoundaryProvenance(sources, canonical, transform, spec.equation, spec.references, self.catalog.key, spec.convention),
                fidelity=spec.fidelity)
        reads: list[tuple[str, _Read, Selector]] = []
        if spec.r_at_axis is not None:
            reads.append(("r_at_axis", run._boundary_number(spec.r_at_axis, z), spec.r_at_axis))
        if spec.angle_atan2 is not None:
            reads += [("angle_x", run._boundary_number(spec.angle_atan2[0], z), spec.angle_atan2[0]),
                      ("angle_r", run._boundary_number(spec.angle_atan2[1], z), spec.angle_atan2[1])]
        else:
            reads.append(("angle_deg", run._boundary_number(spec.angle_deg, z), spec.angle_deg))
        problem = next((f"{x.name}: {x.problem}" for _, x, _ in reads if x.problem), None)
        if problem:
            raise ValueError(problem)
        sources = tuple(
            BoundarySource(role, e.name, e.parameter_id, _clean(e.raw_value) or None, sel.unit, e.location.page, e.location.line)
            for role, read, sel in reads for e in read.entries[:1]
        )
        values = {role: read for role, read, _ in reads}
        if spec.angle_atan2 is not None:
            x, r = values["angle_x"], values["angle_r"]
            if not x.value > 0.0:
                raise ValueError(f"{x.name}: the reactance an edge is parallel to must be positive")
            angle = math.degrees(math.atan2(x.value, r.value))
            angle_text = f"angle = atan2({x.name}, {r.name}) = {fmt(angle)} deg"
        else:
            a = values["angle_deg"]
            if spec.angle_range is not None and not spec.angle_range[0] <= a.value <= spec.angle_range[1]:
                lo, hi = spec.angle_range
                raise ValueError(f"{a.name}: {fmt(a.value)} is outside the documented setting range {fmt(lo)}-{fmt(hi)} deg, "
                                 "so the documented angle convention is not established for it")
            angle = spec.angle_sign * a.value
            angle_text = (f"angle = {'-' if spec.angle_sign < 0 else ''}{a.name} = {fmt(angle)} deg "
                          f"({a.name} {fmt(a.value)} as printed, deg)")
        if spec.kind == "directional":
            provenance = BoundaryProvenance(sources, canonical, f"canonical {angle_text}", spec.equation, spec.references,
                                            self.catalog.key, spec.convention)
            return DirectionalBoundary(z["zone"], angle, RetainedSide(spec.retained_side), BoundaryFrame(spec.frame),
                                       provenance, fidelity=spec.fidelity)
        rd = values["r_at_axis"]
        sign = "-" if spec.r_sign < 0 else "+"
        scale = "" if spec.r_scale == 1.0 else f"{fmt(spec.r_scale)} x "
        transform = (f"r_at_axis = {sign}{scale}{rd.name} (as printed, ohm); angle = {values['angle_deg'].name} (deg)"
                     if spec.angle_atan2 is None else f"r_at_axis = {sign}{scale}{rd.name} (as printed, ohm); {angle_text}")
        return ResistiveBoundary(
            z["zone"], spec.r_sign * spec.r_scale * rd.value, angle, BoundarySide(spec.side), BoundaryFrame(spec.frame),
            BoundaryProvenance(sources, canonical, transform, spec.equation, spec.references, self.catalog.key, spec.convention),
            fidelity=spec.fidelity,
        )


@dataclass(frozen=True)
class BoundaryRun:
    """The shadow boundaries of one document (DEC-199 Phase 2A / 2B / 2C / 2D) and the (boundary id, zone, why) of
    those not derived: resistive edges in ``boundaries``, directional half-planes in ``directional``, lower reactance
    limits in ``lower``, tilted upper reactance limits in ``upper``."""

    boundaries: tuple["ResistiveBoundary", ...]
    unresolved: tuple[tuple[str, str, str], ...]
    directional: tuple["DirectionalBoundary", ...] = ()
    lower: tuple["ReactanceLowerBoundary", ...] = ()
    upper: tuple["TiltedReactanceBoundary", ...] = ()


class _Run:
    """One interpretation run over one document (not reusable)."""

    def __init__(self, catalog: Catalog, registry: CanonicalRegistry, document: RawRelayDocument) -> None:
        self.cat = catalog
        self.reg = registry
        self.doc = document
        self.by_name: dict[str, list[RawSetting]] = {}
        self.by_code: dict[str, list[RawSetting]] = {}
        self.by_id: dict[str, RawSetting] = {s.setting_id: s for s in document.settings}
        for s in document.settings:
            if s.name:
                self.by_name.setdefault(norm_text(s.name), []).append(s)
            if s.parameter_id:
                self.by_code.setdefault(s.parameter_id.upper(), []).append(s)
        self.consumed: set[str] = set()
        self.notes: list[str] = []
        self.results: dict[tuple[str, str], Outcome] = {}
        self.zone_vars: list[dict[str, Any]] = []
        self.note_ids: set[str] = set()
        self.preserved_ids: set[str] = set()
        self.zone_notes: dict[str, list[SourceNote]] = {}
        self.zone_kept: dict[str, dict[str, UnresolvedSetting]] = {}

    # --- provenance plumbing ----------------------------------------------------

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
        if text and text not in self.notes:
            self.notes.append(text)

    def _ids(self, m: Mapping) -> dict[str, Any]:
        return {"catalog_id": self.cat.catalog_id, "catalog_version": self.cat.version, "canonical_id": m.canonical,
                "references": self._references(m)}

    def _references(self, m: Mapping) -> tuple[DocumentReference, ...]:
        """DEC-198: the catalog references a mapping cites, as provenance (identification only)."""
        out = []
        for rid in m.references:
            ref = self.cat.reference(rid)
            if ref is not None:
                out.append(DocumentReference(ref.id, ref.title, ref.verification, ref.document, ref.section, ref.page, ref.scope))
        return tuple(out)

    def good(self, m: Mapping, value: Any, reads: list[_Read], *, transformation: str | None = None,
             raw: str | None = None) -> Sourced:
        entries = tuple(e for r in reads for e in r.entries)
        notes = tuple(n for r in reads for n in r.notes) + ((m.note,) if m.note else ())
        raw = raw or " | ".join(r.raw for r in reads if r.raw is not None) or None
        sources = self.refs(*entries)
        if not sources:
            return unresolved(raw, notes=(m.unresolved_note or "no source setting supports this value",),
                              cause=UnresolvedCause.MISSING, **self._ids(m))
        build = mapped if m.confidence == "mapped" else inferred
        return build(
            value, sources=sources, profile_id=self.cat.profile_id, profile_version=self.cat.profile_version,
            raw_value=raw, notes=notes, transformation=transformation, authority=MappingAuthority(m.authority),
            **self._ids(m),
        )

    def bad(self, m: Mapping, reads: list[_Read], *, reason: str | None = None, cause: UnresolvedCause | None = None) -> Sourced:
        """An unresolved value keeping the raw text and sources. Cause: the strongest among the failed
        reads (conflict, unreadable, unsupported); an absent source or a bare reason is *missing*."""
        causes = {r.cause for r in reads if r.problem and r.cause} | ({cause} if cause else set())
        cause = next((c for c in _CAUSE_ORDER if c in causes), UnresolvedCause.MISSING)
        problems = [reason] if reason else []
        problems += [f"{r.name}: {r.problem}" for r in reads if r.problem]
        problems += [f"{r.name}: not present in the document" for r in reads if not r.found and not r.problem]
        for p in problems:
            self.note(p)
        entries = tuple(e for r in reads for e in r.entries)
        raw = " | ".join(r.raw for r in reads if r.raw is not None) or None
        return unresolved(raw, sources=self.refs(*entries), notes=tuple(problems), cause=cause, **self._ids(m))

    # --- locating and reading sources ------------------------------------------------

    def locate(self, sel: Selector, variables: dict[str, Any]) -> _Read:
        if sel.pattern_in_text:
            return self._locate_text(sel)
        if sel.name_pattern:
            pattern = re.compile(sel.name_pattern)
            found = tuple(s for s in self.doc.settings if s.name and pattern.search(s.name))
            name = sel.name_pattern
        elif sel.code:
            found = tuple(self.by_code.get(sel.code.upper(), ()))
            name = f"{sel.code} {sel.name or ''}".strip()
        else:
            name = _fill(sel.name or "", variables)
            found = tuple(self.by_name.get(norm_text(name), ()))
        if sel.section:
            found = tuple(s for s in found if sel.section in " / ".join(s.section_path) or sel.section in (s.name or ""))
        r = _Read(name, found)
        if not found:
            return r
        if sel.code and sel.name:
            expected = _fill(sel.name, variables)
            if any(norm_text(e.name) != norm_text(expected) for e in found):
                r.fail(
                    f"the document names this code differently from what catalog {self.cat.key} expects ({expected!r}); not trusted",
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
        if not r.raw and _blank_setting_cell(found[0]):
            # the extractor established that the configured-setting cell is empty and that the text beside
            # it sits in the range column: the setting is not stated (Missing), and the range is not a value
            shown = _range_text(found[0])
            r.fail("the configured setting cell is blank" + (f" (the range column shows {shown!r}, which is not a setting)" if shown else "")
                   + "; no value is assumed", UnresolvedCause.MISSING)
            r.raw = None
        elif not r.raw:
            r.fail("no value found", UnresolvedCause.UNREADABLE)
            r.raw = None
        elif len(found) > 1:
            r.notes = (f"{len(found)} identical duplicate entries in the document",)
        return r

    def _boundary_number(self, sel: Selector, variables: dict[str, Any]) -> _Read:
        """A plain number for a shadow boundary (no transformation): located without being consumed; a blank or
        missing cell, a non-number or a printed unit that disagrees leaves it unread."""
        r = self.locate(sel, variables)
        if not r.found:
            r.fail("not present in the document", UnresolvedCause.MISSING)
        if r.problem:
            return r
        if not _NUMBER.match(r.raw or ""):
            r.fail("the value is not a plain number", UnresolvedCause.UNREADABLE)
            return r
        rng = _range_text(r.entries[0])
        m = _RANGE.match(rng) if rng else None
        problem = self._printed_unit_problem(sel, m["unit"].strip().rstrip(".") if m else "")
        if problem:
            r.fail(*problem)
            return r
        r.value = float(r.raw)
        return r

    def _locate_text(self, sel: Selector) -> _Read:
        pattern = re.compile(sel.pattern_in_text or "", re.IGNORECASE)
        hits: dict[str, RawSetting] = {}
        for s in self.doc.settings:
            for text in (s.raw_value, s.name):
                m = pattern.search(str(text)) if text else None
                if m:
                    hits.setdefault(m.group(1), s)
        r = _Read(sel.pattern_in_text or "", tuple(dict.fromkeys(hits.values())), raw=" / ".join(hits) or None)
        if len(hits) > 1:
            r.fail("more than one distinct value was found; none selected", UnresolvedCause.CONFLICT)
        elif hits:
            r.raw = next(iter(hits))
        return r

    def parse(self, r: _Read, sel: Selector, mapping: Mapping, param: CanonicalParameter, input_name: str = "value") -> _Read:
        """Type, range, allowed values and printed-unit checks for one located source."""
        if not r.ok:
            return r
        if sel.allowed_text and norm_text(r.raw) not in {norm_text(t) for t in sel.allowed_text}:
            r.fail(f"the value is not recognised by catalog {self.cat.key}", UnresolvedCause.UNSUPPORTED)
            return r
        if sel.type != "number":
            r.value = r.raw
            return r
        if sel.infinity and norm_text(r.raw) in _INFINITY_TEXTS:
            # the relay's own documented setting "infinity" (e.g. a stage that never trips on time): a
            # configured value, never a default, a range or a finite number
            r.value = math.inf
            return r
        if not _NUMBER.match(r.raw or ""):
            r.fail("the value is not a plain number", UnresolvedCause.UNREADABLE)
            return r
        value = float(r.raw)
        rng_text = _range_text(r.entries[0])
        if sel.infinity and rng_text and norm_text(rng_text) in _INFINITY_TEXTS:
            # an infinity-capable setting whose range column shows only "Infinity": not a printed unit
            rng_text = ""
        printed = ""
        val = sel.validate
        if val.printed_range_pattern is not None:
            if not re.fullmatch(val.printed_range_pattern, rng_text or "", re.IGNORECASE):
                r.fail("the value and printed range do not establish the expected setting", UnresolvedCause.CONFLICT)
                return r
        elif val.within_printed_range:
            m = _RANGE.match(rng_text) if rng_text else None
            if m:
                if not (float(m["lo"]) <= value <= float(m["hi"])):
                    r.fail("the value is outside the setting range printed beside it", UnresolvedCause.CONFLICT)
                    return r
                printed = m["unit"].strip().rstrip(".")
            else:
                printed = rng_text or ""
        if val.allowed_values and value not in val.allowed_values:
            r.fail("the value and printed range do not establish an accepted setting", UnresolvedCause.CONFLICT)
            return r
        problem = self._printed_unit_problem(sel, printed)
        if problem:
            r.fail(*problem)
            return r
        explicit = any(s.type == "unit_conversion" for s in mapping.steps)
        many = bool(mapping.steps) and PRIMITIVES[mapping.steps[0].type].inputs == "many"
        target = expected_unit(mapping.steps[0].type if many else None, input_name, param.unit, explicit)
        if sel.unit and target and sel.unit != target:
            factor = conversion_factor(sel.unit, target)
            if factor is None:
                r.fail(f"no conversion from {sel.unit} to {target}", UnresolvedCause.UNSUPPORTED)
                return r
            r.conversion = f"{fmt(value)} {sel.unit} → {fmt(value * factor)} {target}"
            value = value * factor
        r.value = value
        return r

    def _printed_unit_problem(self, sel: Selector, printed: str) -> tuple[str, UnresolvedCause] | None:
        rule = sel.printed_unit
        if rule.policy == "ignore":
            return None
        if rule.policy == "none":
            return ("expected a dimensionless setting but a unit is printed", UnresolvedCause.CONFLICT) if printed else None
        if not printed and rule.policy == "if_printed":
            return None
        accepted = printed_matches(sel.unit, printed) or printed.casefold() in {a.casefold() for a in rule.accept}
        if not accepted:
            for cond in rule.accept_if:
                held = self.results.get((cond.canonical, ""))
                if (cond.text.casefold() == printed.casefold() and held is not None
                        and isinstance(held.result, Sourced) and held.result.is_resolved and held.result.value == cond.equals):
                    accepted = True
        if accepted:
            return None
        if not printed and rule.missing_when_unprinted:
            return ("the unit could not be established from the document", UnresolvedCause.MISSING)
        shown = f"the printed unit {printed!r}" if printed else "no unit"
        return (f"{shown} does not match the expected unit {sel.unit or '(none)'}; no unit conversion is applied", UnresolvedCause.CONFLICT)

    # --- families ---------------------------------------------------------------------

    def read_family(self, sel: Selector, mapping: Mapping, param: CanonicalParameter, variables: dict[str, Any]) -> tuple[_Read, str | None]:
        """One joined read for a family: its value is the agreed member value. ``all_equal`` needs
        every member read and identical (else a conflict); ``any`` takes the first readable member."""
        fam = sel.family
        assert fam is not None
        members = ([{"n": n} for n in self._channel_indices(fam)] if fam.kind == "indexed" else self._live_zones(fam))
        reads = []
        for v in members:
            member = Selector(name=fam.member, type=sel.type, unit=sel.unit, printed_unit=sel.printed_unit,
                              validate=sel.validate, allowed_text=sel.allowed_text)
            reads.append(self.parse(self.locate(member, {**variables, **v}), sel, mapping, param))
        entries = tuple(e for r in reads for e in r.entries)
        why: str | None = None
        value: Any = None
        if fam.kind == "indexed" and fam.expected_count is not None and len(reads) != fam.expected_count:
            self.refs(*entries)
            why = f"expected {fam.expected_count} channels, found {len(reads)}; not resolved."
        else:
            values = [r.value if r.ok else None for r in reads]
            if fam.kind == "zone" and len(reads) < fam.min_count:
                value = None
            elif fam.aggregate == "any":
                usable = [x for x in values if x is not None]
                value = usable[0] if usable else None
            elif values and all(x is not None for x in values) and len(set(values)) != 1:
                for r in reads:
                    r.fail("the members do not agree", UnresolvedCause.CONFLICT)
                why = f"the members do not agree ({sorted(set(values))}); none selected."
            elif values and all(x is not None for x in values):
                value = values[0]
        joined = _Read(
            param.label, entries, raw=" | ".join(r.raw for r in reads if r.raw is not None) or None,
            notes=tuple(n for r in reads for n in r.notes), value=value,
            conversion=next((r.conversion for r in reads if r.conversion), None),
        )
        failed = [r for r in reads if r.problem]
        if failed:
            joined.problem = "; ".join(f"{r.name}: {r.problem}" for r in failed)
            joined.cause = next((c for c in _CAUSE_ORDER if c in {r.cause for r in failed}), UnresolvedCause.MISSING)
            joined.value = None
        return joined, why

    def _channel_indices(self, fam: Family) -> list[int]:
        idx = fam.index
        assert idx is not None
        name_re, value_re = re.compile(idx.name_pattern), re.compile(idx.value_pattern)
        out = []
        for s in self.doc.settings:
            m = name_re.match(s.name or "")
            if not m or not value_re.search(_clean(s.raw_value)):
                continue
            n = int(m.group("n"))
            if idx.filter_name:
                kind = self.locate(Selector(name=idx.filter_name), {"n": n})
                if not (kind.ok and norm_text(kind.raw) == norm_text(idx.filter_equals)):
                    continue
            out.append(n)
        return sorted(out)

    def _live_zones(self, fam: Family) -> list[dict[str, Any]]:
        if not fam.where_canonical:
            return list(self.zone_vars)
        live = []
        for z in self.zone_vars:
            held = self.results.get((fam.where_canonical, z["zone"]))
            if held is not None and held.result.is_resolved and _plain(held.result) == fam.where_equals:
                live.append(z)
        return live

    # --- evaluating one mapping ------------------------------------------------------------

    def evaluate(self, m: Mapping, zone: dict[str, Any] | None) -> Sourced | PlainValue:
        param = self.reg.get(m.canonical)
        assert param is not None
        variables = zone or {}
        if m.gap is not None:
            return self._gap(m, param, variables)
        if m.not_exposed is not None:
            return self._not_exposed(m, param, variables)
        first = PRIMITIVES[m.steps[0].type] if m.steps else None
        if first is not None and first.inputs == "none":
            return self._constant(m, param, variables)

        inputs: dict[str, _Read] = {}
        whys: list[str] = []
        for name, sel in ([("value", m.source)] if m.source else []) + list(m.sources):
            if sel.family is not None:
                inputs[name], why = self.read_family(sel, m, param, variables)
                if why:
                    whys.append(why)
            else:
                read = self.parse(self.locate(sel, variables), sel, m, param, name)
                if read.problem and sel.note:                 # the catalog's own words on why it cannot be read
                    read.problem = f"{read.problem} -- {_fill(sel.note, variables)}"
                inputs[name] = read

        gate_reads, failure = self._check_gates(m, param, variables, inputs)
        if failure is not None:
            return failure
        reads = [*gate_reads, *inputs.values()]
        try:
            value, description = self._run_steps(m, inputs)
        except TransformError as exc:
            cause = UnresolvedCause(exc.cause) if exc.cause in {c.value for c in UnresolvedCause} else UnresolvedCause.UNREADABLE
            return self.bad(m, reads, reason=str(exc), cause=cause)
        if value is None:
            return self.bad(m, reads, reason=" ".join(whys) or m.unresolved_note or None)
        cited = [r for r in reads if r.ok] if first is not None and first.name == "decision_table" else reads
        return self.good(m, self._coerce(param, value), cited, transformation=description, raw=_composite_raw(first, inputs))

    def _run_steps(self, m: Mapping, inputs: dict[str, _Read]) -> tuple[Any, str | None]:
        """Apply the mapping's transformation chain to the (parsed) inputs. Returns (value, sentence)."""
        sentences = [r.conversion for r in inputs.values() if r.conversion]
        steps = list(m.steps)
        if steps and PRIMITIVES[steps[0].type].inputs == "many":
            first = PRIMITIVES[steps.pop(0).type]
            step0 = m.steps[0]
            available = {name: r.value for name, r in inputs.items() if r.ok and r.value is not None}
            if (first.name == "decision_table" and not available) or (first.name != "decision_table" and len(available) < len(inputs)):
                return None, None
            current, sentence = first.run(step0.params, available)
            before, raw = None, " | ".join(str(x) for x in available.values())
            if step0.describe:
                sentences.append(step0.describe.format_map(_Safe({"raw": raw, "input": raw, "result": fmt(current)})))
            elif sentence and first.name in _NUMERIC_STEPS:
                sentences.append(sentence)
        else:
            r = inputs["value"]
            if not r.ok or r.value is None:
                return None, None
            current, raw = r.value, r.raw or ""
        for step in steps:
            primitive = PRIMITIVES[step.type]
            before = current
            current, sentence = primitive.run(step.params, {"value": current})
            if step.describe:
                sentences.append(step.describe.format_map(_Safe({"raw": raw, "input": fmt(before), "result": fmt(current)})))
            elif sentence and step.type in _NUMERIC_STEPS:
                sentences.append(sentence)
        return current, ("; ".join(sentences) or None)

    def _coerce(self, param: CanonicalParameter, value: Any) -> Any:
        if param.data_type == "enum" and param.enum_type:
            return ENUM_TYPES[param.enum_type](value)
        return value

    # --- gates ------------------------------------------------------------------------------

    def _check_gates(self, m: Mapping, param: CanonicalParameter, variables: dict[str, Any],
                     inputs: dict[str, _Read]) -> tuple[list[_Read], Sourced | None]:
        """Each gate must read as one of its ``equals`` texts for the value to be in use."""
        gate_reads: list[_Read] = []
        value = inputs.get("value")
        value_ok = value is not None and value.ok and value.value is not None
        for gate in m.gates:
            g = self.parse(self.locate(gate.source, variables), gate.source, m, param)
            gate_reads.append(g)
            if g.ok and norm_text(g.raw) in {norm_text(x) for x in gate.equals}:
                continue
            reads = [g, *inputs.values()]
            if g.ok:                                           # the gate is closed (e.g. the timer switch is OFF)
                note = _fill(gate.off_note, variables) or f"{g.name} is {g.raw}, so this value is not in use; none is assumed."
                return gate_reads, unresolved(
                    value.raw if value is not None else None,
                    sources=self.refs(*g.entries, *(e for r in inputs.values() for e in r.entries)),
                    cause=UnresolvedCause.MISSING, notes=(note,), **self._ids(m),
                )
            if not g.found and value_ok:
                reason = _fill(gate.missing_note, variables) or f"{g.name} was not found, so this value is not established as in use"
                return gate_reads, self.bad(m, reads, reason=reason)
            return gate_reads, self.bad(m, reads)
        return gate_reads, None

    # --- constants and gaps ---------------------------------------------------------------------

    def _evidence(self, selectors: tuple[Selector, ...], variables: dict[str, Any]) -> list[RawSetting]:
        out: list[RawSetting] = []
        for sel in selectors:
            if sel.family is None:
                out.extend(self.locate(sel, variables).entries)
                continue
            fam = sel.family
            members = self._live_zones(fam) if fam.kind == "zone" else [{"n": n} for n in self._channel_indices(fam)]
            found = [e for v in members for e in self.locate(Selector(name=fam.member), {**variables, **v}).entries]
            if len({e.setting_id for e in found}) >= max(fam.min_count, 1):
                out.extend(found)
        return out

    def _constant(self, m: Mapping, param: CanonicalParameter, variables: dict[str, Any]) -> Sourced | PlainValue:
        # A gate holds for a constant as for a read value (e.g. a documented zone behaviour applies only
        # while the zone's own switch is On); the gate's setting is then cited as evidence.
        gate_reads, failure = self._check_gates(m, param, variables, {})
        if failure is not None:
            return failure
        value = self._coerce(param, m.steps[0].params["value"])
        note = m.unresolved_note or "the evidence for this value was not found in the document"
        zone_id = variables.get("zone", "")
        evidence = self._evidence(m.evidence, variables)
        missing = (m.evidence and not evidence) or any(
            (held := self.results.get((cid, zone_id)) or self.results.get((cid, ""))) is None or not held.result.is_resolved
            for cid in m.requires_resolved
        )
        if missing:
            if param.plain:
                return unresolved(notes=(note,), cause=UnresolvedCause.MISSING, **self._ids(m))
            self.note(note)
            return unresolved(sources=self.refs(*evidence), notes=(note,), cause=UnresolvedCause.MISSING, **self._ids(m))
        if param.plain:
            return PlainValue(value)
        cited = list(evidence) + [e for g in gate_reads for e in g.entries if e not in evidence]
        for cid in m.evidence_from:
            held = self.results.get((cid, zone_id)) or self.results.get((cid, ""))
            if held is not None and isinstance(held.result, Sourced) and held.result.is_resolved:
                cited.extend(self.by_id[r.setting_id] for r in held.result.provenance.sources if r.setting_id in self.by_id)
        return self.good(m, value, [_Read(param.label, tuple(cited))])

    def _gap(self, m: Mapping, param: CanonicalParameter, variables: dict[str, Any]) -> Sourced:
        assert m.gap is not None
        reads = [self.locate(sel, variables) for sel in m.gap.evidence]
        shown = ", ".join(f"{e.name} = {_clean(e.raw_value)}" for r in reads for e in r.entries[:1])
        note = _fill(m.gap.note, {**variables, "evidence": shown})
        unverified = m.gap.kind == "unverified"
        if unverified:
            self.note(f"{param.label}: not yet verified for this relay - what it means, or how it converts, is not established")
        else:
            self.note(f"{param.label}: capability gap - the source states a value Oruxa cannot represent")
        return unresolved(
            " | ".join(r.raw for r in reads if r.raw is not None) or None,
            sources=self.refs(*(e for r in reads for e in r.entries)), notes=(note,),
            cause=UnresolvedCause.UNVERIFIED if unverified else UnresolvedCause.UNSUPPORTED,
            **self._ids(m),
        )

    def _not_exposed(self, m: Mapping, param: CanonicalParameter, variables: dict[str, Any]) -> Sourced:
        """DEC-198: the relay has no such setting. Never a value and never *Missing*: only a documented
        derivation mapping of the same target can supply the value (it is tried first)."""
        assert m.not_exposed is not None
        return unresolved(notes=(_fill(m.not_exposed.note, variables),), cause=UnresolvedCause.NOT_EXPOSED, **self._ids(m))

    # --- running the catalog --------------------------------------------------------------------

    def run(self) -> CanonicalDistanceProtectionModel:
        self._zones()
        order = sorted(range(len(self.cat.mappings)), key=lambda i: (self.cat.mappings[i].stage, i))
        done: set[tuple[str, str]] = set()
        for i in order:
            m = self.cat.mappings[i]
            targets = [""] if not m.zones else [z["zone"] for z in self.zone_vars if "*" in m.zones or z["zone"] in m.zones]
            for zid in targets:
                if (m.canonical, zid) not in done:
                    done.add((m.canonical, zid))
                    self._resolve(m.canonical, zid)
        # after the mappings, so neither can take a setting a mapping reads
        self._preserve_zone_settings()
        self._collect_zone_notes()
        return self._assemble()

    # --- zone-level raw settings and document notes --------------------------------------------

    def _preserve_zone_settings(self) -> None:
        """Keep the catalog's declared raw zone settings with their zone (shared settings with every
        zone that declares them), uninterpreted, each with the catalog's reason."""
        taken = set(self.consumed)
        for rule in self.cat.zone_preserved:
            for z in self.zone_vars:
                if "*" not in rule.zones and z["zone"] not in rule.zones:
                    continue
                if rule.names:
                    wanted = {norm_text(_fill(n, z)) for n in rule.names}
                    hits = [s for s in self.doc.settings if s.name and norm_text(s.name) in wanted]
                else:
                    pattern = re.compile(_fill(rule.name_pattern or "", {k: re.escape(str(v)) for k, v in z.items()}))
                    hits = [s for s in self.doc.settings if s.name and pattern.search(s.name)]
                kept = self.zone_kept.setdefault(z["zone"], {})
                material = {norm_text(x) for x in rule.unverified_when}
                harmless = {norm_text(x) for x in rule.material_unless}
                for s in hits:
                    if s.setting_id in taken:
                        continue
                    raw = _clean(s.raw_value) if s.raw_value is not None else ""
                    cause = "unverified"
                    if rule.unverified_when:
                        is_material = bool(raw) and norm_text(raw) in material
                    elif rule.material_unless or rule.always_material:
                        # a geometry-affecting setting: harmless only with a value that has no effect (none, when
                        # always material); a blank cell leaves its effect unknown (missing), any other value is
                        # not representable
                        is_material = not raw or norm_text(raw) not in harmless
                        cause = "missing" if not raw else "unsupported"
                    else:
                        is_material = False
                    kept.setdefault(s.setting_id, UnresolvedSetting(
                        s.setting_id, s.name, s.raw_value, s.unit, reason=rule.reason,
                        material=is_material, material_cause=cause,
                    ))
                    self.preserved_ids.add(s.setting_id)
        self.consumed |= self.preserved_ids

    def _collect_zone_notes(self) -> None:
        """Rows the catalog declares to be notes about a zone become that zone's `SourceNote`s: the
        document's own words with their source -- never a value, a status or a default."""
        if not self.cat.source_notes:
            return
        known = {z["zone"] for z in self.zone_vars}
        for s in self.doc.settings:
            if s.setting_id in self.consumed or s.parameter_id:
                continue
            value = _clean(s.raw_value)
            text = f"{_clean(s.name)}  {value}".strip() if value else _clean(s.name)
            for rule in self.cat.source_notes:
                m = re.search(rule.pattern, text) if text else None
                if not m:
                    continue
                token = m.group("zone")
                zone_id = dict(rule.zone_ids).get(token) or _fill(rule.zone_id, {"zone": token})
                if zone_id not in known:
                    continue
                subject = value_text = None
                for sub in rule.subjects:
                    found = re.search(sub.pattern, text)
                    if found:
                        groups = {str(i): g or "" for i, g in enumerate(found.groups(), start=1)}
                        subject, value_text = sub.subject, re.sub(r"\{(\d+)\}", lambda g: groups.get(g.group(1), g.group(0)), sub.value)
                        break
                self.zone_notes.setdefault(zone_id, []).append(
                    SourceNote(SourceNoteKind.PROPOSED_REQUIREMENT, text, subject, value_text, sources=self.refs(s))
                )
                self.note_ids.add(s.setting_id)
                break
        if self.zone_notes:
            self.note(ZONE_NOTES_STATEMENT)

    def _zones(self) -> None:
        z = self.cat.zones
        if z.mode == "discover":
            pattern = re.compile(z.name_pattern or "")
            numbers = sorted({int(m.group("n")) for s in self.doc.settings if s.name and (m := pattern.match(s.name))})
            self.zone_vars = [
                {"n": n, "nn": f"{n:02d}", "zone": _fill(z.id_template, {"n": n}), "name": _fill(z.name_template, {"n": n})}
                for n in numbers
            ]
        else:
            keys = dict(z.keys)
            self.zone_vars = [{"zone": zid, "name": name, "key": keys.get(zid, zid)} for zid, name in z.static]

    def _resolve(self, canonical: str, zone_id: str) -> None:
        """Evaluate every mapping of one target, strongest first; the first that resolves wins."""
        candidates = [
            m for m in self.cat.mappings
            if m.canonical == canonical and (not zone_id or "*" in m.zones or zone_id in m.zones)
        ]
        # A not-exposed declaration never resolves: it is tried last, and if nothing resolves it is the
        # result kept (the relay has no such setting -- not a missing source value). DEC-198.
        candidates.sort(key=lambda m: (m.not_exposed is not None, AUTHORITY_PRECEDENCE[m.authority],
                                       VALUE_SOURCE_PRECEDENCE.index(m.value_source)))
        zone = next((z for z in self.zone_vars if z["zone"] == zone_id), None) if zone_id else None
        first: Sourced | PlainValue | None = None
        chosen = candidates[0]
        final: Sourced | PlainValue | None = None
        for m in candidates:
            result = self.evaluate(m, zone)
            if result.is_resolved:
                final, chosen = result, m
                break
            if first is None or m.not_exposed is not None:
                first = result
                chosen = m
        self.results[(canonical, zone_id)] = Outcome(final if final is not None else first, chosen, zone_id)  # type: ignore[arg-type]

    # --- assembling the canonical model ---------------------------------------------------------

    def _assemble(self) -> CanonicalDistanceProtectionModel:
        holder = {"metadata": self._metadata(), "transformers": InstrumentTransformers(), "line": ProtectedLine()}
        for p in sorted((p for p in self.reg.parameters if p.scope == "document" and (p.id, "") in self.results), key=lambda p: p.order):
            set_path(holder, p, self.results[(p.id, "")].result)
        zones = tuple(self._zone(z) for z in self.zone_vars)
        return CanonicalDistanceProtectionModel(
            metadata=holder["metadata"], transformers=holder["transformers"], line=holder["line"], zones=zones,
            unmapped_settings=self._leftovers(), interpretation_notes=(*self.cat.notes, *self.notes),
        )

    def _zone(self, z: dict[str, Any]) -> DistanceZone:
        holder: dict[str, Any] = {"zone": DistanceZone(zone_id=z["zone"], name=z["name"])}
        compensation: dict[str, Any] = {}
        kinds: set[str] = set()
        for p in sorted((p for p in self.reg.parameters if p.scope == "zone" and (p.id, z["zone"]) in self.results), key=lambda p: p.order):
            result = self.results[(p.id, z["zone"])].result
            if p.compensation_kind:
                kinds.add(p.compensation_kind)
                compensation[(p.engine_path or "").rsplit(".", 1)[1]] = result
            else:
                set_path(holder, p, result)
        zone = holder["zone"]
        if compensation and len(kinds) == 1:
            zone = replace(zone, compensation=ResidualCompensation(kind=CompensationKind(next(iter(kinds))), **compensation))
        notes, kept = self.zone_notes.get(z["zone"]), self.zone_kept.get(z["zone"])
        if notes or kept:
            zone = replace(zone, source_notes=tuple(notes or ()), unresolved_settings=tuple((kept or {}).values()))
        return zone

    def _metadata(self) -> RelayMetadata:
        """Relay identity from the catalog's applicability, cited to the scheme / template field the
        document itself states (a catalog never *infers* which relay it is from magnitudes)."""
        ident, app = self.cat.identification, self.cat.applicability
        pattern = re.compile(ident.scheme_pattern, re.IGNORECASE)
        schemes: dict[str, RawSetting] = {}
        for s in self.doc.settings:
            for text in (s.raw_value, s.name):
                m = pattern.search(str(text)) if text else None
                if m:
                    schemes.setdefault(m.group(1), s)
        base = dict(source_format=self.doc.source_format, profile_id=self.cat.profile_id, profile_version=self.cat.profile_version)
        if len(schemes) != 1:
            return RelayMetadata(**base)
        token, entry = next(iter(schemes.items()))
        ids = {"catalog_id": self.cat.catalog_id, "catalog_version": self.cat.version}

        def good(value, canonical: str, why: str = "") -> Sourced:
            return mapped(
                value, sources=self.refs(entry), profile_id=self.cat.profile_id, profile_version=self.cat.profile_version,
                raw_value=f"Scheme: {token}", notes=(why,) if why else (), canonical_id=canonical,
                authority=MappingAuthority.CONFIGURED_SETTING, **ids,
            )

        scheme = good(token, "relay.scheme")
        if ident.scheme_model_pattern and not re.search(ident.scheme_model_pattern, token, re.IGNORECASE):
            return RelayMetadata(**base, scheme_name=scheme)
        version = unresolved(**ids, canonical_id="relay.version")
        if ident.version_pattern and (v := re.search(ident.version_pattern, token)):
            version = good(v.group(1), "relay.version", "the version marker written in the scheme / device designation")
        manufacturer = (
            good(app.manufacturer, "relay.manufacturer",
                 "normalised from the relay model per the catalog; the manufacturer is not named in the document")
            if app.manufacturer is not None
            else unresolved(notes=("the manufacturer of this relay line is not established by the project and is not asserted",),
                            cause=UnresolvedCause.MISSING, **ids, canonical_id="relay.manufacturer")
        )
        return RelayMetadata(
            **base, scheme_name=scheme, version=version,
            manufacturer=manufacturer,
            family=good(app.family, "relay.family", "family label from the catalog"),
            model=good(app.model, "relay.model"),
        )

    def _leftovers(self) -> tuple[UnresolvedSetting, ...]:
        scope = self.cat.distance_scope
        names = {norm_text(n) for n in scope.names}
        out = []
        running = ""                                        # the section heading row most recently seen
        for s in self.doc.settings:
            if s.raw_value is None and not s.parameter_id and _HEADING.match(s.name or ""):
                running = s.name or ""
            if s.setting_id in self.consumed:
                continue
            section = f"{' / '.join(s.section_path)} {running}"
            distance = (
                bool(scope.code_prefixes) and (s.parameter_id or "").upper().startswith(scope.code_prefixes)
            ) or any(k in section for k in scope.section_contains) or norm_text(s.name) in names or any(
                re.search(p, s.name or "") for p in scope.name_patterns
            )
            out.append(UnresolvedSetting(
                s.setting_id, s.name, s.raw_value, s.unit,
                reason=(f"distance-related setting not interpreted by {self.cat.profile_version}" if distance
                        else "outside Distance Protection; retained, not interpreted"),
                out_of_scope=not distance,
            ))
        return tuple(out)


class _Safe(dict):
    def __missing__(self, key):  # an unknown placeholder stays visible instead of raising
        return "{" + key + "}"


def _composite_raw(first, inputs: dict[str, "_Read"]) -> str | None:
    """The printed text of an impedance assembled from two settings (``1.2 + j9``, ``8 ∠ 75``)."""
    if first is None or first.name not in ("impedance_rx", "impedance_polar"):
        return None
    a, b = (inputs.get(k) for k in first.input_names)
    if a is None or b is None or a.raw is None or b.raw is None:
        return None
    return f"{a.raw} + j{b.raw}" if first.name == "impedance_rx" else f"{a.raw} ∠ {b.raw}°"


def _plain(result: Sourced | PlainValue) -> Any:
    value = result.value
    return getattr(value, "value", value)


def set_path(holder: dict, param: CanonicalParameter, result: Sourced | PlainValue) -> None:
    """Write ``result`` at ``param``'s engine path into the dict of root objects (``metadata``,
    ``transformers``, ``line`` or ``zone``)."""
    if param.plain:
        if not result.is_resolved:
            return
        value = result.value
        if param.enum_type and isinstance(value, str):
            value = ENUM_TYPES[param.enum_type](value)
    else:
        value = result
    segments = (param.model_path or "").split(".")
    root, rest = ("zone", segments) if (param.engine_path or "").startswith("zones[]") else (segments[0], segments[1:])
    holder[root] = _replace_in(holder[root], rest, value, param.extra_name, param)


def _replace_in(obj: Any, path: list[str], value: Any, extra: str | None, param: CanonicalParameter) -> Any:
    head, rest = path[0], path[1:]
    if not is_dataclass(obj) or head not in {f.name for f in fields(obj)}:
        raise ValueError(f"the engine path of {param.id} does not resolve at {head!r}")
    current = getattr(obj, head)
    if rest:
        return replace(obj, **{head: _replace_in(current, rest, value, extra, param)})
    if extra:
        return replace(obj, **{head: (*current, ExtraQuantity(extra, value, unit=param.unit or None))})
    return replace(obj, **{head: value})
