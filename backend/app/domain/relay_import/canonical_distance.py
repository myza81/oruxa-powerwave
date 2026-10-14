"""OEM-neutral canonical Distance Protection model.

Produced by a relay profile from a `RawRelayDocument`; consumed (in later
slices) by the manual-entry form and the distance characteristic engine.
It deliberately does NOT assume one impedance reach plus one resistance per
zone, a fixed zone count, or any one manufacturer's vocabulary.

Principles encoded here:
- every engineering value is `Sourced` (value + provenance);
- different source representations (polar vs rectangular impedance, K0 vs
  Kr/Kx vs RE/RL-XE/XL) are preserved as given, never silently converted;
- anything a profile could not interpret is carried as `UnresolvedSetting`
  and never invented into an electrical meaning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import Iterator

from app.domain.relay_import.provenance import Sourced, SourceRef, unresolved
from app.domain.relay_import.raw_document import SourceFormat


def _unresolved_field():
    return field(default_factory=unresolved)


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------


class ZoneStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class ZoneDirection(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"
    NON_DIRECTIONAL = "non_directional"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class CharacteristicType(StrEnum):
    QUADRILATERAL = "quadrilateral"
    MHO = "mho"
    LENTICULAR = "lenticular"
    POLYGON_CUSTOM = "polygon_custom"
    #: The OEM characteristic is not understood (yet). Not drawable.
    UNKNOWN = "unknown"


class GeometryMode(StrEnum):
    """How a zone's reach is stated -- the representation the source used, never converted.

    ``POLAR_REACH``: one reach as a magnitude at an angle (``DistanceZone.reach``), the
    form a mho or a tilted quadrilateral uses. ``EXPLICIT_RX``: orthogonal R / X limits
    (``DistanceZone.x_reach_ohm`` and the resistive reaches), with no reach angle at
    all. Only a quadrilateral can be ``EXPLICIT_RX``."""

    POLAR_REACH = "polar_reach"
    EXPLICIT_RX = "explicit_rx"


class SettingBasis(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    UNKNOWN = "unknown"


class CompensationKind(StrEnum):
    K0_MAGNITUDE_ANGLE = "k0_magnitude_angle"
    KR_KX = "kr_kx"
    RE_RL_XE_XL = "re_rl_xe_xl"
    OEM_SPECIFIC = "oem_specific"


# ---------------------------------------------------------------------------
# Small value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImpedanceValue:
    """An impedance in ohms, in the representation the source used.

    Exactly one complete form must be present: rectangular (`r_ohm` and
    `x_ohm`) or polar (`magnitude_ohm` and `angle_deg`). The form given is
    kept as-is; `to_rectangular()` is an explicit conversion for callers
    that ask for it (polar -> R + jX is exact by definition).
    """

    r_ohm: float | None = None
    x_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None

    def __post_init__(self) -> None:
        rect = self.r_ohm is not None and self.x_ohm is not None
        polar = self.magnitude_ohm is not None and self.angle_deg is not None
        half_rect = (self.r_ohm is None) != (self.x_ohm is None)
        half_polar = (self.magnitude_ohm is None) != (self.angle_deg is None)
        if half_rect or half_polar or not (rect or polar):
            raise ValueError("ImpedanceValue needs a complete rectangular (r, x) or polar (magnitude, angle) form")

    @property
    def is_rectangular(self) -> bool:
        return self.r_ohm is not None

    @property
    def is_polar(self) -> bool:
        return self.magnitude_ohm is not None

    def to_rectangular(self) -> tuple[float, float]:
        if self.r_ohm is not None and self.x_ohm is not None:
            return self.r_ohm, self.x_ohm
        angle = math.radians(self.angle_deg)
        return self.magnitude_ohm * math.cos(angle), self.magnitude_ohm * math.sin(angle)


@dataclass(frozen=True)
class ExtraQuantity:
    """A named quantity with no dedicated canonical field (optional line
    data, OEM geometry parameters...). Kept so nothing is lost."""

    name: str
    value: Sourced
    unit: str | None = None


@dataclass(frozen=True)
class UnresolvedSetting:
    """A raw setting a profile saw but could not give electrical meaning."""

    setting_id: str
    name: str | None
    raw_value: str | float | None
    unit: str | None = None
    reason: str = ""
    #: True when the setting is outside Distance Protection altogether
    #: (recorders, communications, labels...). It is still retained so no
    #: source setting is silently discarded, but it is not an open question.
    out_of_scope: bool = False


# ---------------------------------------------------------------------------
# Relay / transformers / line
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelayMetadata:
    source_format: SourceFormat
    manufacturer: Sourced = _unresolved_field()
    family: Sourced = _unresolved_field()
    model: Sourced = _unresolved_field()
    version: Sourced = _unresolved_field()
    active_setting_group: Sourced = _unresolved_field()
    #: Profile that produced this interpretation; None for the generic
    #: fallback, which interprets nothing.
    profile_id: str | None = None
    profile_version: str | None = None
    #: The scheme / template name the document states, as written.
    scheme_name: Sourced = _unresolved_field()


@dataclass(frozen=True)
class InstrumentTransformers:
    ct_primary_a: Sourced = _unresolved_field()
    ct_secondary_a: Sourced = _unresolved_field()
    vt_primary_v: Sourced = _unresolved_field()
    vt_secondary_v: Sourced = _unresolved_field()
    voltage_base_v: Sourced = _unresolved_field()
    current_base_a: Sourced = _unresolved_field()
    #: Whether the relay's impedance settings are primary or secondary ohms
    #: (a `SettingBasis`).
    setting_basis: Sourced = _unresolved_field()
    #: CT / VT turns ratios (dimensionless), for relays that state a ratio instead of
    #: primary and secondary values. Kept as stated; never split into primary / secondary.
    ct_ratio: Sourced = _unresolved_field()
    vt_ratio: Sourced = _unresolved_field()


@dataclass(frozen=True)
class ProtectedLine:
    length: Sourced = _unresolved_field()
    length_unit: Sourced = _unresolved_field()
    #: R1/X1 or |Z1|,angle -- as the source gave it (`ImpedanceValue`).
    positive_sequence_impedance: Sourced = _unresolved_field()
    #: R0/X0 or |Z0|,angle (`ImpedanceValue`).
    zero_sequence_impedance: Sourced = _unresolved_field()
    line_angle_deg: Sourced = _unresolved_field()
    extras: tuple[ExtraQuantity, ...] = ()


# ---------------------------------------------------------------------------
# Zone pieces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResistiveReach:
    """Resistive reach in ohms. Relays differ: one value, separate
    phase-phase / phase-earth values, or a reverse reach."""

    common: Sourced = _unresolved_field()
    phase_phase: Sourced = _unresolved_field()  # e.g. RFPP
    phase_earth: Sourced = _unresolved_field()  # e.g. RFPE
    reverse: Sourced = _unresolved_field()
    extras: tuple[ExtraQuantity, ...] = ()


_COMPENSATION_COMPONENTS = {
    CompensationKind.K0_MAGNITUDE_ANGLE: ("k0_magnitude", "k0_angle_deg"),
    CompensationKind.KR_KX: ("kr", "kx"),
    CompensationKind.RE_RL_XE_XL: ("re_rl", "xe_xl"),
    CompensationKind.OEM_SPECIFIC: (),
}
_ALL_COMPENSATION_COMPONENTS = ("k0_magnitude", "k0_angle_deg", "kr", "kx", "re_rl", "xe_xl")


@dataclass(frozen=True)
class ResidualCompensation:
    """Earth-fault residual compensation, in the source's own definition.

    `kind` records which definition the source used; only the components of
    that definition may be populated, and no conversion between definitions
    is performed here (they are not interchangeable without knowing the
    relay's reference impedance and convention).
    """

    kind: CompensationKind
    k0_magnitude: Sourced = _unresolved_field()
    k0_angle_deg: Sourced = _unresolved_field()
    kr: Sourced = _unresolved_field()
    kx: Sourced = _unresolved_field()
    re_rl: Sourced = _unresolved_field()
    xe_xl: Sourced = _unresolved_field()
    oem_values: tuple[ExtraQuantity, ...] = ()

    def __post_init__(self) -> None:
        allowed = _COMPENSATION_COMPONENTS[self.kind]
        for name in _ALL_COMPENSATION_COMPONENTS:
            if name not in allowed and getattr(self, name).is_resolved:
                raise ValueError(f"{name} is not a component of a {self.kind.value} compensation")
        if self.oem_values and self.kind is not CompensationKind.OEM_SPECIFIC:
            raise ValueError("oem_values are only valid for an oem_specific compensation")


@dataclass(frozen=True)
class CharacteristicSpec:
    """Which geometry a zone uses, plus whatever geometry parameters the
    profile could establish. Only QUADRILATERAL and MHO are drawable by the
    current engine; the rest are representable so support can grow without
    reshaping this model."""

    #: A `CharacteristicType`.
    type: Sourced = _unresolved_field()
    #: Geometry parameters beyond the zone's reach/resistive reach/tilt
    #: (e.g. lens width, blinder angles, OEM-specific shape values).
    parameters: tuple[ExtraQuantity, ...] = ()
    #: Explicit (R, X) vertices in ohms for POLYGON_CUSTOM.
    polygon_vertices_ohm: tuple[tuple[float, float], ...] = ()
    #: Free-text OEM description when the type is UNKNOWN / unresolved.
    oem_description: str | None = None
    #: How the reach is stated (see `GeometryMode`). The default keeps every existing
    #: polar zone (and the manual form) exactly as it was.
    geometry_mode: GeometryMode = GeometryMode.POLAR_REACH

    def __post_init__(self) -> None:
        if self.polygon_vertices_ohm and len(self.polygon_vertices_ohm) < 3:
            raise ValueError("a polygon needs at least three vertices")


class SourceNoteKind(StrEnum):
    #: A requirement or design intent written in the document's notes: what the
    #: relay *should* be set to, not what it is set to.
    PROPOSED_REQUIREMENT = "proposed_requirement"


@dataclass(frozen=True)
class SourceNote:
    """A statement in the source document about a zone that is not one of its
    settings. Kept apart from every setting: it never becomes a value, a status or a
    default, and is shown as a document note with its source."""

    kind: SourceNoteKind
    #: The document's own words.
    text: str
    #: What the note is about (``timer`` / ``status``) and the figure it states, when the
    #: profile could read them; ``None`` otherwise.
    subject: str | None = None
    value_text: str | None = None
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class DistanceZone:
    zone_id: str
    name: str | None = None
    status: Sourced = _unresolved_field()  # ZoneStatus
    direction: Sourced = _unresolved_field()  # ZoneDirection
    phase_phase_enabled: Sourced = _unresolved_field()  # bool
    phase_earth_enabled: Sourced = _unresolved_field()  # bool
    phase_timer_s: Sourced = _unresolved_field()
    earth_timer_s: Sourced = _unresolved_field()
    common_timer_s: Sourced = _unresolved_field()
    characteristic: CharacteristicSpec = field(default_factory=CharacteristicSpec)
    #: Impedance reach for phase (loop) faults (`ImpedanceValue`).
    reach: Sourced = _unresolved_field()
    #: Separate earth-loop reach, where the relay defines one.
    earth_reach: Sourced = _unresolved_field()
    #: Zero-sequence reach (R0/X0), where the relay defines it per zone.
    zero_sequence_reach: Sourced = _unresolved_field()
    resistive_reach: ResistiveReach = field(default_factory=ResistiveReach)
    compensation: ResidualCompensation | None = None
    tilt_deg: Sourced = _unresolved_field()
    unresolved_settings: tuple[UnresolvedSetting, ...] = ()
    #: Reactive reach (X), ohms (a number): the reach of an ``EXPLICIT_RX`` zone, whose
    #: ``reach`` stays unresolved because no polar reach exists. Right (+R) and left (-R)
    #: resistive limits are ``resistive_reach.phase_phase`` / ``.reverse``.
    x_reach_ohm: Sourced = _unresolved_field()
    #: Document notes about this zone (proposed requirements...). Never settings.
    source_notes: tuple[SourceNote, ...] = ()

    def __post_init__(self) -> None:
        if not self.zone_id:
            raise ValueError("a zone needs a non-empty zone_id")


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalDistanceProtectionModel:
    metadata: RelayMetadata
    transformers: InstrumentTransformers = field(default_factory=InstrumentTransformers)
    line: ProtectedLine = field(default_factory=ProtectedLine)
    zones: tuple[DistanceZone, ...] = ()
    #: Raw settings no profile mapping claimed (document level).
    unmapped_settings: tuple[UnresolvedSetting, ...] = ()
    interpretation_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [z.zone_id for z in self.zones]
        if len(set(ids)) != len(ids):
            raise ValueError("zone_id values must be unique within a model")

    def zone(self, zone_id: str) -> DistanceZone | None:
        return next((z for z in self.zones if z.zone_id == zone_id), None)

    def iter_sourced(self) -> Iterator[tuple[str, Sourced]]:
        """Every `Sourced` value in the model with a dotted path, for review
        and confirmation workflows."""
        yield from _walk("", self)

    def referenced_setting_ids(self) -> frozenset[str]:
        """Every raw `setting_id` the model accounts for: cited by any value's
        provenance, or carried as an `UnresolvedSetting`. A raw setting in
        neither set was silently discarded by the profile."""
        ids: set[str] = set()
        for _, sourced in self.iter_sourced():
            ids.update(ref.setting_id for ref in sourced.provenance.sources)
        ids.update(u.setting_id for u in self.unmapped_settings)
        for zone in self.zones:
            ids.update(u.setting_id for u in zone.unresolved_settings)
            ids.update(ref.setting_id for note in zone.source_notes for ref in note.sources)
        return frozenset(ids)

    def items_needing_confirmation(self) -> tuple[str, ...]:
        return tuple(path for path, s in self.iter_sourced() if s.needs_confirmation)

    def unresolved_paths(self) -> tuple[str, ...]:
        return tuple(path for path, s in self.iter_sourced() if not s.is_resolved)


def item_label(item: object, index: int) -> str:
    """The bracketed label a tuple element gets in an `iter_sourced` path
    (``zones[Z1]``, ``extras[tilt]``): its zone id or name, else its index."""
    return getattr(item, "zone_id", None) or getattr(item, "name", None) or str(index)


def _walk(prefix: str, obj) -> Iterator[tuple[str, Sourced]]:
    if isinstance(obj, Sourced):
        yield prefix, obj
    elif isinstance(obj, (tuple, list)):
        for i, item in enumerate(obj):
            yield from _walk(f"{prefix}[{item_label(item, i)}]", item)
    elif is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            yield from _walk(f"{prefix}.{f.name}" if prefix else f.name, getattr(obj, f.name))
