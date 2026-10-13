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
    """A declared capability gap: the document states something Oruxa's canonical model cannot
    represent. The canonical value stays unresolved (cause *unsupported*) but the evidence is
    preserved and cited."""

    note: str
    evidence: tuple[Selector, ...] = ()


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
class DistanceScope:
    code_prefixes: tuple[str, ...] = ()
    section_contains: tuple[str, ...] = ()
    names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Applicability:
    manufacturer: str
    family: str
    model: str
    #: Firmware / template version patterns the catalog covers; ``("*",)`` = any.
    versions: tuple[str, ...] = ("*",)


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
    #: The canonical registry version the catalog was validated against.
    registry_version: str = ""
    #: ``catalog_id@version`` -- what an import records as the interpretation's origin.
    source_path: str = ""

    @property
    def key(self) -> str:
        return f"{self.catalog_id}@{self.version}"

    @property
    def profile_version(self) -> str:
        """The version string an import carries (e.g. ``acme-x1-catalog-v1.0.0``)."""
        return f"{self.catalog_id}-v{self.version}"
