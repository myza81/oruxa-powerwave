"""Typed form of an OEM parameter catalog (the result of `catalog_validation.parse_catalog`).

An OEM catalog says what one relay family's setting names *mean* in canonical terms. It is data
(JSON), never code: every field here is a plain value, and the only behaviour a catalog can ask
for is a named transformation primitive (see `transforms`). The matcher (`interpreter`) reads
these objects; it contains no manufacturer-specific logic.

Format version ``oruxa.parameter-catalog/1``. A catalog has:

* identity -- ``catalog_id``, ``version``, ``lifecycle`` (draft -> validated -> tested -> active)
  and ``applicability`` (manufacturer / family / model / firmware versions);
* ``identification`` -- how a document is recognised as this relay (used when the catalog is the
  relay's interpretation profile);
* ``zones`` -- how the distance zones are found (discovered by a name pattern, or listed);
* ``mappings`` -- each maps one or more source parameters to a canonical parameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

CATALOG_SCHEMA = "oruxa.parameter-catalog/1"

LIFECYCLES = ("draft", "validated", "tested", "active")

#: What a source value is. Only ``setting_value`` (the configured setting) may supply a canonical
#: value; the others are recorded so that a range column, a default or a note can never be
#: mistaken for the setting itself.
VALUE_SOURCES = (
    "setting_value",          # the configured setting as the document states it
    "range",                  # the printed range / allowed values column
    "default",                # a default value column
    "document_note",          # free text in the document
    "engineering_instruction",  # a structured engineering instruction
    "profile_inference",      # the catalog's own inference
)
#: Value sources that may supply a canonical value, strongest first (their precedence).
VALUE_SOURCE_PRECEDENCE = ("setting_value", "engineering_instruction", "profile_inference")

AUTHORITIES = ("configured_setting", "engineering_instruction", "documented_derivation", "assumption")
#: Evidence strength, strongest first. When more than one mapping could supply the same canonical
#: value, the strongest that resolves wins and its provenance is the one recorded.
AUTHORITY_PRECEDENCE = {name: rank for rank, name in enumerate(AUTHORITIES)}

CONFIDENCES = ("mapped", "inferred")

#: DEC-198: how far a cited reference has been checked. Only a ``verified`` reference can carry a
#: mapping that declares itself a verified documented derivation.
REFERENCE_VERIFICATIONS = ("verified", "unverified")
#: DEC-198: what a declared gap is about. ``unsupported`` -- the meaning is understood but Oruxa's
#: canonical model / engine cannot represent it (the default, as before); ``unverified`` -- what the
#: value means, or how it converts, is not established for this relay.
GAP_KINDS = ("unsupported", "unverified")


@dataclass(frozen=True)
class PrintedUnitRule:
    """How the unit text printed beside a setting (its range column) is checked.

    ``policy``: ``if_printed`` -- an empty printed unit is accepted, a printed one must match;
    ``required`` -- a matching printed unit must exist; ``none`` -- the setting is dimensionless
    and no unit may be printed; ``ignore`` -- not checked (a unit established elsewhere).
    ``accept`` adds printed texts to the unit's own aliases; ``accept_if`` accepts a text only
    while another canonical value holds (e.g. ``/I1`` only for a 1 A CT secondary).
    """

    policy: str = "if_printed"
    accept: tuple[str, ...] = ()
    accept_if: tuple["ConditionalText", ...] = ()
    #: Cause when the check fails: ``conflict`` (default) or ``missing`` when nothing is printed.
    missing_when_unprinted: bool = False


@dataclass(frozen=True)
class ConditionalText:
    text: str
    canonical: str
    equals: Any


@dataclass(frozen=True)
class Validation:
    within_printed_range: bool = True
    allowed_values: tuple[float, ...] = ()
    #: The printed range text must fully match this pattern (instead of a numeric range).
    printed_range_pattern: str | None = None


@dataclass(frozen=True)
class FamilyIndex:
    """The members of an indexed family are found by a name pattern; ``n`` is its numeric group."""

    name_pattern: str
    value_pattern: str
    filter_name: str | None = None
    filter_equals: str | None = None


@dataclass(frozen=True)
class Family:
    #: ``indexed`` (channels found by name) or ``zone`` (the zones of the document).
    kind: str
    member: str
    index: FamilyIndex | None = None
    expected_count: int | None = None
    aggregate: str = "all_equal"
    #: ``zone`` families only: use the zones whose canonical value equals this.
    where_canonical: str | None = None
    where_equals: Any = None
    min_count: int = 1


@dataclass(frozen=True)
class ConstantValue:
    """A fixed numeric value an OEM reference establishes directly for a boundary parameter (DEC-199 Phase 2G) --
    never read from the document, and never a stand-in for a missing configured setting. ``value`` is the magnitude
    as the reference states it (a sign, where the field has one, is applied the same way as for a source-based
    value); ``unit`` is explicit because a boundary parameter is never unitless; ``name`` is the label its
    provenance shows (e.g. "BFR characteristic angle (fixed)"), since there is no document row to name it."""

    value: float
    unit: str
    name: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("a constant boundary value must be finite")
        if not self.unit:
            raise ValueError("a constant boundary value states its unit")
        if not self.name:
            raise ValueError("a constant boundary value states its provenance label")


@dataclass(frozen=True)
class Selector:
    """Finds raw settings in a `RawRelayDocument` and says how to read their value.

    Exactly one *match* is set: ``name`` (exact, whitespace/case-folded; with ``code`` it also
    needs the code), ``code`` (the manufacturer's parameter id; a ``name`` beside it must agree),
    ``name_pattern`` (regex over names), ``pattern_in_text`` (regex over name or value text, first
    group is the value) or a ``family``. Templates ``{n}`` / ``{nn}`` / ``{zone}`` in ``name``
    take the zone number / zero-padded number / zone id of a zone-scope mapping.
    """

    name: str | None = None
    code: str | None = None
    name_pattern: str | None = None
    pattern_in_text: str | None = None
    family: Family | None = None
    section: str | None = None
    #: How the matched value text is read: ``number`` (a plain decimal) or ``text``.
    type: str = "text"
    #: The unit the number is stated in (``""`` when the document states none).
    unit: str = ""
    printed_unit: PrintedUnitRule = field(default_factory=PrintedUnitRule)
    validate: Validation = field(default_factory=Validation)
    #: Text values (case-folded) the source may take; any other is unsupported, not guessed.
    allowed_text: tuple[str, ...] = ()
    #: Free text shown when this source cannot be read (appended to the generic note).
    note: str = ""
    #: A ``number`` source whose setting may be set to infinity (the relay's own documented value,
    #: e.g. a stage timer that never trips on time): "Infinity" / "∞" is then read as a configured
    #: value (``math.inf``) instead of an unreadable one. Never a default and never a range value.
    infinity: bool = False


@dataclass(frozen=True)
class Step:
    """One transformation primitive and its parameters (see `transforms.PRIMITIVES`)."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    #: Optional template for the provenance sentence: ``{raw}``, ``{input}``, ``{result}``.
    describe: str | None = None


@dataclass(frozen=True)
class Gate:
    """A condition on another source that must hold for the mapped value to be in use
    (e.g. a timer value counts only while its ``Timer`` switch is ON)."""

    source: Selector
    equals: tuple[str, ...]
    off_note: str = ""
    missing_note: str = ""


@dataclass(frozen=True)
class Gap:
    """A declared gap: the document states something Oruxa does not turn into a canonical value. The
    canonical value stays unresolved but the evidence is preserved and cited. ``kind`` (DEC-198) says
    why: ``unsupported`` (understood, not representable -- cause *unsupported*) or ``unverified``
    (meaning / conversion not established -- cause *unverified*)."""

    note: str
    evidence: tuple[Selector, ...] = ()
    kind: str = "unsupported"


@dataclass(frozen=True)
class NotExposed:
    """DEC-198: the relay does not expose this canonical parameter as a configurable setting (fixed /
    inherent behaviour). It is *not* a missing source value. It never supplies a value: only a
    verified documented derivation mapping of the same target can, and wins when it resolves."""

    note: str


@dataclass(frozen=True)
class Reference:
    """DEC-198: an authoritative reference a catalog cites (an OEM manual section, an application note,
    an owner decision). Identification only -- the catalog never carries the reference's text."""

    id: str
    title: str
    verification: str
    document: str | None = None
    section: str | None = None
    page: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class Mapping:
    id: str
    canonical: str
    #: Zone ids the mapping applies to; ``("*",)`` = every zone; empty for a document-scope mapping.
    zones: tuple[str, ...] = ()
    source: Selector | None = None
    sources: tuple[tuple[str, Selector], ...] = ()
    steps: tuple[Step, ...] = ()
    gates: tuple[Gate, ...] = ()
    value_source: str = "setting_value"
    authority: str = "configured_setting"
    confidence: str = "mapped"
    note: str = ""
    #: Constant / gap mappings cite these (evidence that the constant applies).
    evidence: tuple[Selector, ...] = ()
    evidence_from: tuple[str, ...] = ()
    requires_resolved: tuple[str, ...] = ()
    unresolved_note: str = ""
    gap: Gap | None = None
    #: DEC-198: the relay does not expose this setting (see `NotExposed`).
    not_exposed: NotExposed | None = None
    #: DEC-198: ids of the catalog `references` this mapping cites.
    references: tuple[str, ...] = ()
    #: DEC-198: ``"verified"`` declares a verified documented derivation (it must cite a verified
    #: reference); ``None`` when not declared.
    verification: str | None = None
    #: Computed by the validator: 0 = document level, 1 = zone level, 2 = document level that
    #: reads zone results (a zone family).
    stage: int = 0


@dataclass(frozen=True)
class ZoneModel:
    #: ``discover``: ``name_pattern`` has a group ``n`` (the instance number).
    mode: str
    name_pattern: str | None = None
    id_template: str = "Z{n}"
    name_template: str = "Zone {n}"
    static: tuple[tuple[str, str], ...] = ()  # (zone id, zone name)
    #: Listed zones only: (zone id, key) -- the token ``{key}`` stands for in templates (default: the id),
    #: for sheets whose parameter names use a zone token other than the zone id (``Z_PP1``, ``Z_Rev``).
    keys: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Identification:
    """How a document is recognised as this relay (the catalog acting as an interpretation profile)."""

    model_patterns: tuple[str, ...] = ()
    family_markers: tuple[str, ...] = ()
    parameter_signatures: tuple[dict[str, Any], ...] = ()
    #: Regex whose first group is the scheme / template token (default ``Scheme: <token>``).
    scheme_pattern: str = r"\bScheme:\s*(\S+)"
    #: The scheme token must match this for the document to be confirmed as this relay.
    scheme_model_pattern: str | None = None
    version_pattern: str | None = None


@dataclass(frozen=True)
class NoteSubject:
    """What a zone note is about and the figure it states. ``pattern`` is searched in the note's text;
    ``value`` is a template whose ``{1}`` is the pattern's first group (e.g. ``"{1} s"``)."""

    subject: str                     # "timer" | "status"
    pattern: str
    value: str


@dataclass(frozen=True)
class ZoneNoteRule:
    """Document notes about a zone (scheme requirements, design intent). A matching row becomes a
    `SourceNote` of the zone it names -- provenance only: it never supplies a value, a status or a
    default. ``pattern`` is searched in a row's text (name and value) and has a named group ``zone``;
    ``zone_id`` turns that token into a zone id (``{zone}``), ``zone_ids`` overrides listed tokens.
    A note naming no zone of the document stays a raw, not-interpreted row."""

    pattern: str
    zone_id: str = "Z{zone}"
    zone_ids: tuple[tuple[str, str], ...] = ()
    subjects: tuple[NoteSubject, ...] = ()


@dataclass(frozen=True)
class PreservedSettings:
    """Raw zone settings the catalog recognises but gives no canonical meaning (blinder geometry, reach
    multipliers ...). They are kept with their zone -- shown in its review group as unsupported, never
    resolvable items carrying ``reason`` -- instead of in the document's leftovers. Exactly one of
    ``names`` (templated names) or ``name_pattern`` (a templated regex) is set; ``{zone}`` / ``{n}`` /
    ``{nn}`` are filled per zone (regex-escaped in a pattern). A setting a mapping already reads is never
    taken."""

    zones: tuple[str, ...]
    reason: str
    names: tuple[str, ...] = ()
    name_pattern: str | None = None
    #: DEC-198: raw values (case-folded) with which the setting may materially change the zone's
    #: operation although its meaning is not verified -- such a row is Unverified and blocks an
    #: enabled zone. The value is never interpreted.
    unverified_when: tuple[str, ...] = ()
    #: DEC-198: raw values (case-folded) with which this geometry-affecting setting has no effect on
    #: the drawn zone (e.g. "infinity" = the load cutout is off). Any other value blocks an enabled
    #: zone: a blank configured cell as a missing source value, a stated value as a boundary the
    #: engine cannot represent. The value is never interpreted.
    material_unless: tuple[str, ...] = ()
    #: DEC-198: a geometry-affecting setting with no harmless value -- whatever it is set to, it gives the
    #: zone a documented boundary part the engine cannot represent (e.g. a switch that only chooses between
    #: two offset reaches). A stated value blocks an enabled zone as an engine limitation, a blank configured
    #: cell as a missing source value. The value is never interpreted.
    always_material: bool = False


@dataclass(frozen=True)
class DistanceScope:
    code_prefixes: tuple[str, ...] = ()
    section_contains: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    #: Regular expressions over setting names (for codes written inside the name, e.g. ``21.901.``).
    name_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Applicability:
    #: ``None`` when the catalog explicitly does not assert a manufacturer (not established by the project).
    manufacturer: str | None
    family: str
    model: str
    #: Firmware / template version patterns the catalog covers; ``("*",)`` = any.
    versions: tuple[str, ...] = ("*",)


@dataclass(frozen=True)
class BoundarySpec:
    """DEC-199 Phase 2A / 2B / 2C / 2D / 2G: a canonical zone boundary the catalog derives from settings, evaluated in
    SHADOW mode only (never part of the canonical model, a review or readiness) (`app.domain.distance_boundaries`):

    * ``kind`` "resistive" -- an inclined resistive edge ``R(X) = r_at_axis + X * cot(angle)``, with
      ``r_at_axis = r_sign * r_scale * source`` and the angle either ``angle_sign * source`` or
      ``atan2(x source, r source)`` (a line parallel to the impedance R + jX);
    * ``kind`` "directional" -- a half-plane through the origin along the ray at ``angle_sign * source`` degrees,
      keeping ``retained_side``. ``convention`` states how the source writes the angle when it is not the canonical one;
    * ``kind`` "reactance_lower" (Phase 2C) -- a lower reactance limit ``X >= -x_minus`` with ``x_minus`` the source
      value as printed;
    * ``kind`` "reactance_upper" (Phase 2D) -- a tilted upper reactance limit through ``(0, x_at_reference)``, with
      ``tilt_deg = tilt_sign * source``, added *alongside* the zone's plain horizontal top (never in its place).

    ``angle_range`` / ``tilt_range`` is the documented setting range of the *source* value: a value outside it is not
    derived (it would mean the documented convention does not hold for that value). It never applies to a
    `ConstantValue` (Phase 2G): a fixed OEM constant has no configured-setting range to fall outside of, and
    carries no range field at all -- see ``catalog_validation._boundaries``."""

    id: str
    zones: tuple[str, ...]
    kind: str                                         # resistive | directional | reactance_lower | reactance_upper
    frame: str                                        # zone | absolute
    #: A document-read value, or (Phase 2G) a fixed OEM constant -- never a stand-in for a missing configured value.
    angle_deg: Selector | ConstantValue | None = None
    angle_sign: float = 1.0                           # +1 or -1: angle = sign * the source value
    angle_range: tuple[float, float] | None = None
    angle_atan2: tuple[Selector, Selector] | None = None   # (x source, r source): angle = atan2(x, r)
    side: str | None = None                           # resistive: right | left
    r_at_axis: Selector | ConstantValue | None = None
    r_sign: float = 1.0                               # +1 or -1
    r_scale: float = 1.0                              # a documented factor (e.g. 0.5 for half a loop reach)
    x_minus: Selector | None = None                   # reactance_lower: X >= -x_minus
    x_at_reference: Selector | None = None            # reactance_upper: the X-axis crossing of the tilted line
    tilt_deg: Selector | None = None                  # reactance_upper: the source of the tilt angle
    tilt_sign: float = 1.0                            # +1 or -1: tilt_deg = sign * the source value
    tilt_range: tuple[float, float] | None = None
    retained_side: str | None = None                  # directional: counter_clockwise | clockwise
    convention: str | None = None
    gates: tuple[Gate, ...] = ()
    fidelity: str = "documented"                      # exact | documented (| static_equivalent: directional or resistive)
    references: tuple[str, ...] = ()
    equation: str = ""
    #: The canonical value the boundary represents, templated (e.g. ``zones[{zone}].resistive_reach.phase_phase``).
    canonical: str | None = None


@dataclass(frozen=True)
class Catalog:
    catalog_id: str
    version: str
    lifecycle: str
    applicability: Applicability
    profile_id: str
    mappings: tuple[Mapping, ...]
    zones: ZoneModel
    identification: Identification = field(default_factory=Identification)
    distance_scope: DistanceScope = field(default_factory=DistanceScope)
    description: str = ""
    #: Interpretation notes added to every model this catalog produces (relay-level statements the
    #: settings themselves do not carry, e.g. how zone instances are numbered).
    notes: tuple[str, ...] = ()
    #: Document notes about zones, kept as zone source notes (never values).
    source_notes: tuple[ZoneNoteRule, ...] = ()
    #: Raw zone settings kept with their zone, uninterpreted.
    zone_preserved: tuple[PreservedSettings, ...] = ()
    #: DEC-198: the authoritative references the mappings cite, by id.
    references: tuple[Reference, ...] = ()
    #: DEC-199 Phase 2A: canonical boundaries evaluated in shadow mode only.
    boundaries: tuple[BoundarySpec, ...] = ()
    #: The canonical registry version the catalog was validated against.
    registry_version: str = ""
    #: ``catalog_id@version`` -- what an import records as the interpretation's origin.
    source_path: str = ""

    def reference(self, reference_id: str) -> Reference | None:
        return next((r for r in self.references if r.id == reference_id), None)

    @property
    def key(self) -> str:
        return f"{self.catalog_id}@{self.version}"

    @property
    def profile_version(self) -> str:
        """The version string an import carries (e.g. ``example-catalog-v1.0.0``)."""
        return f"{self.catalog_id}-v{self.version}"
