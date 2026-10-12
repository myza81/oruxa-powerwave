"""Extraction Review (Slice 7) with review state (Slice 8): a presentation-shaped
view of an interpreted relay.

Built request-scoped from the canonical model plus the RawRelayDocument (the
raw document is what lets each value cite its source line, text and raw value),
returned inside the upload response and then dropped -- nothing is stored and
the Distance Protection form is never touched. The review is relay-neutral: it
walks the canonical model, so the number of zones, the compensation kind and the
characteristic are whatever the profile produced.

It adds no engineering meaning. Wording that explains *why* something is
inferred or unresolved is the profile's own note carried through; the only
fixed phrases here are presentation labels and the generic "not stated" text
for an expected value the profile never touched.

Slice 8: the same builder renders an *effective reviewed model* (the original
interpretation plus the user's session overlay, see `review_state`). Every item
carries the canonical path it came from as its ``item_id`` -- the key the user's
decisions use -- the original interpretation ``status`` (never rewritten by a
confirmation) and a separate ``review_status``. Counts, blocking items and the
readiness are all computed here from the items, so what the panel counts is
exactly what it lists. Counting convention: one count per canonical value (a
reach and its angle are one), over the values the review lists, plus the zone
settings the profile declined (always unresolved, never resolvable).

Slice 8A: every item also carries a presentation ``category`` (Mapped /
Assumption / Missing / Conflict / Unsupported / Unreadable). It is derived from
three facts kept separate -- the profile's interpretation status, the recorded
cause of an unresolved value (source / extraction) and the engine adapter's
verdict (capability) -- and it never replaces them: ``status`` stays the profile's
own mapped / inferred / unresolved, and a confirmation leaves the category alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    ImpedanceValue,
    UnresolvedSetting,
    ZoneStatus,
    item_label,
)
from app.domain.relay_import.engine_adapter import EngineAdaptation, zone_active
from app.domain.relay_import.provenance import MappingStatus, ProvenanceOrigin, ReviewStatus, Sourced, SourceRef
from app.domain.relay_import.review_state import (
    ResolutionKind,
    ResolutionSpec,
    blocking_issues,
    blocking_paths,
    compute_readiness,
    engine_limits,
    resolution_spec,
    suggestion_spec,
)
from app.domain.relay_import.raw_document import RawRelayDocument, RawSetting

NOT_STATED = "No value is stated in the document."
NOT_REQUIRED_REASON = "Not required while zone is disabled"
_ZONE_PATH = re.compile(r"^zones\[(?P<zone>[^\]]+)\]\.(?P<rest>.+)$")


@dataclass(frozen=True)
class ReviewSource:
    """Where one interpreted value came from. Never a file path."""

    code: str | None
    name: str | None
    raw_value: str | None
    page: int | None
    line: int | None
    source_text: str | None


@dataclass(frozen=True)
class ReviewResolution:
    """How the user may supply a value for this item (see `ResolutionSpec`)."""

    kind: str  # number | choice
    unit_symbol: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ReviewSuggestion:
    """A value Oruxa may offer for a missing item. Not a source or profile value and
    never applied unless the user explicitly accepts it."""

    value_text: str
    rationale: str


@dataclass(frozen=True)
class ReviewItem:
    key: str
    label: str
    #: Label including its group (e.g. "Zone 1 Reach"), for the provenance heading.
    full_label: str
    #: Formatted engineering value with its unit; ``None`` when unresolved.
    value_text: str | None
    #: The profile's interpretation status: mapped | inferred | unresolved. A
    #: confirmation or manual resolution never rewrites it.
    status: str  # mapped | inferred | unresolved
    #: Profile wording: why it is inferred, or why it is unresolved.
    notes: tuple[str, ...] = ()
    raw_value: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    sources: tuple[ReviewSource, ...] = ()
    #: Slice 8. The canonical path the user's decisions refer to; ``None`` for a
    #: zone setting the profile declined (it has no canonical target).
    item_id: str | None = None
    #: False on the second row of a value shown as two rows (reach + angle): the
    #: decision controls and the counts belong to the first row only.
    primary: bool = True
    #: mapped | to_confirm | confirmed | unresolved | resolved_manually
    review_status: str = "mapped"
    #: Unresolved and the current engine adapter needs it.
    blocking: bool = False
    #: The user consciously left this unresolved item as it is.
    left_unresolved: bool = False
    #: The value the user entered, with its unit (manual resolution only).
    user_value_text: str | None = None
    #: Present while the user may supply or change the value.
    resolution: ReviewResolution | None = None
    #: Present while the item is still missing and Oruxa has a neutral suggestion for it.
    suggestion: ReviewSuggestion | None = None
    #: Who supplied the effective value of a user-resolved item: ``manual`` (typed or
    #: chosen) | ``suggestion`` (an Oruxa suggestion the user accepted); ``None`` otherwise.
    resolution_origin: str | None = None
    #: Slice 8A. How the uncertainty is *presented*: mapped | assumption | missing |
    #: conflict | unsupported | unreadable. Derived, never stored: the profile's
    #: interpretation status, the unresolved cause and the engine adapter stay
    #: separate (see `_category`). A confirmation never changes it -- a confirmed
    #: assumption is still an assumption.
    category: str = "mapped"
    #: The adapter's own message when the current engine refuses (or cannot use) this
    #: value; ``None`` otherwise. Describes the engine, not the document.
    engine_reason: str | None = None
    #: True for an unresolved zone-local setting of a zone that is authoritatively
    #: disabled and that no enabled function needs: the finding stays visible but is not a
    #: blocker and gets no suggestion. Never set for the zone's own status.
    not_required: bool = False
    #: Why it is not required (shown beside the category); ``None`` unless ``not_required``.
    not_required_reason: str | None = None


@dataclass(frozen=True)
class ReviewGroup:
    id: str
    kind: str  # relay | transformers | line | zone | compensation
    title: str
    #: Zone state (e.g. "Disabled / Defeated"); ``None`` for non-zone groups.
    state_label: str | None = None
    state_status: str | None = None
    #: Slice 8: the zone state in review vocabulary (see `ReviewItem.review_status`).
    state_review_status: str | None = None
    #: Helper text for a zone whose state Oruxa assumed (e.g. an absent optional zone).
    state_note: str | None = None
    items: tuple[ReviewItem, ...] = ()


@dataclass(frozen=True)
class ReviewRawSetting:
    code: str | None
    name: str | None
    raw_value: str | None
    page: int | None
    line: int | None
    reason: str = ""


@dataclass(frozen=True)
class ReviewEngineReason:
    #: Zones the same adapter message applies to (empty = the whole model).
    zone_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ReviewEngine:
    status: str  # ready | not_ready
    reasons: tuple[ReviewEngineReason, ...] = ()
    #: Canonical information preserved in the model but unused by the engine.
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewBlockingIssue:
    """Why the current engine cannot take the (reviewed) model. ``item_ids`` are
    the canonical values that would address it; an issue can outlive all of them."""

    message: str
    zone_ids: tuple[str, ...] = ()
    item_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewReadiness:
    #: not_ready | ready_after_confirmation | ready (see `review_state.Readiness`).
    status: str
    #: Inferred values still waiting for the user's confirmation.
    pending_confirmations: int
    #: Unresolved values the current engine adapter needs.
    blocking_unresolved: int


@dataclass(frozen=True)
class ExtractionReview:
    manufacturer: str | None
    relay_family: str | None
    model: str | None
    profile_id: str | None
    profile_version: str | None
    zone_count: int
    #: Mapped values the user has not been asked about.
    mapped_count: int
    #: Inferred values still awaiting confirmation.
    to_confirm_count: int
    #: Unresolved values (blocking or not), including the ones left unresolved.
    unresolved_count: int
    not_interpreted_count: int
    #: Inferred values the user confirmed this session.
    confirmed_count: int
    #: Unresolved values the user supplied this session.
    resolved_manually_count: int
    #: Unresolved values the current engine adapter needs (a subset of the unresolved).
    #: These are *settings*; `blocking_issues` are the adapter's *reasons*.
    blocking_count: int
    #: Unresolved values that belong only to a disabled zone and are therefore not required.
    #: They are excluded from the Missing / Unreadable counts and never block.
    not_required_count: int
    #: Slice 8A presentation counts, per canonical value. Assumptions still awaiting
    #: confirmation; open Missing / Unreadable values; every Conflict and Unsupported
    #: value (an engine limit is not cleared by a decision about the value).
    assumption_count: int
    missing_count: int
    conflict_count: int
    unsupported_count: int
    unreadable_count: int
    readiness: ReviewReadiness
    blocking_issues: tuple[ReviewBlockingIssue, ...]
    #: reviewable | incomplete (interpretation quality, apart from the engine).
    interpretation: str
    engine: ReviewEngine
    notes: tuple[str, ...] = ()
    groups: tuple[ReviewGroup, ...] = ()
    #: Distance-related settings the profile retained but did not interpret.
    not_interpreted: tuple[ReviewRawSetting, ...] = ()
    #: Settings outside Distance Protection, retained so nothing is discarded.
    out_of_scope: tuple[ReviewRawSetting, ...] = ()
    #: Slice 8. The original interpretation as JSON-safe data. The browser holds it
    #: in tab memory and returns it with its decisions so the backend can validate
    #: them without keeping any state (see `canonical_codec`). ``None`` when the
    #: review is built only to read its state back.
    validation_context: dict | None = None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_UNIT_SYMBOLS = {"ohm": "Ω", "deg": "°", "s": "s", "A": "A", "V": "V", "km": "km", "mile": "mile", "mi": "mile"}
_NO_SPACE_UNITS = {"°"}

_STATUS_LABELS = {
    ZoneStatus.ENABLED.value: "Enabled",
    ZoneStatus.DISABLED.value: "Disabled / Defeated",
    ZoneStatus.INACTIVE.value: "Inactive",
    ZoneStatus.UNKNOWN.value: "Unknown",
}
_CHARACTERISTIC_LABELS = {
    CharacteristicType.QUADRILATERAL.value: "Quadrilateral",
    CharacteristicType.MHO.value: "Mho",
    CharacteristicType.LENTICULAR.value: "Lenticular",
    CharacteristicType.POLYGON_CUSTOM.value: "Polygon / custom",
    CharacteristicType.UNKNOWN.value: "Unknown",
}
_COMPENSATION_COMPONENTS = {
    CompensationKind.K0_MAGNITUDE_ANGLE: (
        ("k0_magnitude", "K0 Magnitude", ""),
        ("k0_angle_deg", "K0 Angle", "°"),
    ),
    CompensationKind.KR_KX: (("kr", "Kr", ""), ("kx", "Kx", "")),
    CompensationKind.RE_RL_XE_XL: (("re_rl", "RE/RL", ""), ("xe_xl", "XE/XL", "")),
}


def _number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.10g}"


def _with_unit(text: str, unit: str | None) -> str:
    symbol = _UNIT_SYMBOLS.get(unit or "", unit or "")
    if not symbol:
        return text
    return f"{text}{symbol}" if symbol in _NO_SPACE_UNITS else f"{text} {symbol}"


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _enum_str(value: object) -> object:
    return getattr(value, "value", value)


def _value_text(value: object, unit: str | None = None) -> str:
    if isinstance(value, bool):
        return "Enabled" if value else "Disabled"
    if isinstance(value, (int, float)):
        return _with_unit(_number(float(value)), unit)
    text = str(_enum_str(value))
    return text.replace("_", " ").capitalize() if text.islower() else text


# ---------------------------------------------------------------------------
# Item construction
# ---------------------------------------------------------------------------


_REVIEW_STATUS_BY_MAPPING = {
    MappingStatus.MAPPED: "mapped",
    MappingStatus.INFERRED: "to_confirm",
    MappingStatus.UNRESOLVED: "unresolved",
}


def _interpretation_status(sourced: Sourced) -> str:
    """The profile's own status, ignoring any session review."""
    p = sourced.provenance
    original = p.review.original_status if p.review else p.status
    return original.value


def _review_status(sourced: Sourced) -> str:
    p = sourced.provenance
    record = p.review
    if record is None:
        if p.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION:
            return "assumed"
        return _REVIEW_STATUS_BY_MAPPING[p.status]
    if record.status is ReviewStatus.CONFIRMED:
        return "confirmed"
    if record.status in (ReviewStatus.RESOLVED_MANUALLY, ReviewStatus.SUGGESTION_ACCEPTED):
        return "resolved_manually"
    return "unresolved"


def _category(sourced: Sourced, limit: tuple[str, str] | None) -> str:
    """The presentation category of one value. Three independent facts feed it and
    none is collapsed into another:

    * engine capability -- a *resolved* value the adapter cannot represent is
      Unsupported, and one that disagrees with another resolved value is a Conflict;
    * interpretation -- mapped stays Mapped; inferred is an Assumption (the source
      was read, an engineering assumption was needed);
    * source / extraction -- an unresolved value is Missing, Conflict, Unreadable
      or Unsupported according to its recorded cause (unclassified means Missing).
    """
    if limit is not None and sourced.is_resolved:
        return limit[0]
    original = _interpretation_status(sourced)
    if original == MappingStatus.MAPPED.value:
        return "mapped"
    if original == MappingStatus.INFERRED.value:
        return "assumption"
    cause = sourced.provenance.cause
    return cause.value if cause else "missing"


def _resolution_origin(sourced: Sourced) -> str | None:
    record = sourced.provenance.review
    if record is None:
        return None
    if record.status is ReviewStatus.RESOLVED_MANUALLY:
        return "manual"
    if record.status is ReviewStatus.SUGGESTION_ACCEPTED:
        return "suggestion"
    return None


def _suggestion(path: str | None, sourced: Sourced, category: str) -> ReviewSuggestion | None:
    """Offered only for a value that is still Missing (never a conflict, an unreadable
    cell or an engine limit) and only where Oruxa has a specific neutral suggestion."""
    if path is None or sourced.is_resolved or category != "missing":
        return None
    spec = suggestion_spec(path)
    return ReviewSuggestion(spec.value_text, spec.rationale) if spec else None


def _resolution(path: str | None, sourced: Sourced, category: str) -> ReviewResolution | None:
    if path is None or _review_status(sourced) not in ("unresolved", "resolved_manually"):
        return None
    # Typing a value is offered only where the source simply lacks it (or could not be
    # read) and the canonical type is known; a conflict, or a limit of the engine, is
    # not something a typed value resolves.
    if category not in ("missing", "unreadable") and _review_status(sourced) != "resolved_manually":
        return None
    spec: ResolutionSpec | None = resolution_spec(path)
    if spec is None:
        return None
    if spec.kind is ResolutionKind.NUMBER:
        return ReviewResolution("number", _UNIT_SYMBOLS.get(spec.unit or "", spec.unit), spec.minimum, spec.maximum)
    return ReviewResolution("choice", options=spec.options)


class _Builder:
    def __init__(
        self,
        document: RawRelayDocument,
        blocking: frozenset[str] = frozenset(),
        limits: dict[str, tuple[str, str]] | None = None,
        inactive_zones: frozenset[str] = frozenset(),
    ) -> None:
        self._raw: dict[str, RawSetting] = {s.setting_id: s for s in document.settings}
        self._blocking = blocking
        self._limits = limits or {}
        self._inactive = inactive_zones

    def _not_required(self, path: str | None, sourced: Sourced) -> bool:
        """Zone-local, unresolved, in an authoritatively disabled zone, and not a canonical
        dependency of the adapter (``blocking``). Decided from the canonical path, never from
        the section the row is shown under, so a value an enabled function needs still blocks."""
        match = _ZONE_PATH.match(path or "")
        return bool(
            match
            and match["zone"] in self._inactive
            and not match["rest"] == "status"
            and not sourced.is_resolved
            and path not in self._blocking
        )

    def source(self, ref) -> ReviewSource:
        raw = self._raw.get(ref.setting_id)
        return ReviewSource(
            code=(raw.parameter_id if raw else None) or ref.parameter_id,
            name=(raw.name if raw else None) or ref.parameter_name,
            raw_value=None if raw is None or raw.raw_value is None else str(raw.raw_value),
            page=(raw.location.page if raw else None) or ref.page,
            line=raw.location.line if raw else None,
            source_text=raw.source_text if raw else None,
        )

    def item(
        self,
        key: str,
        label: str,
        group_label: str,
        sourced: Sourced,
        *,
        text: str | None = None,
        unit: str | None = None,
        extra_sources: tuple = (),
        extra_notes: tuple[str, ...] = (),
        path: str | None = None,
        primary: bool = True,
    ) -> ReviewItem:
        prov = sourced.provenance
        refs = (*prov.sources, *(r for r in extra_sources if r not in prov.sources))
        notes = (*prov.notes, *(n for n in extra_notes if n not in prov.notes))
        if not sourced.is_resolved:
            value_text = None
            if not notes:
                notes = (NOT_STATED,)
        else:
            value_text = text if text is not None else _value_text(sourced.value, unit)
        record = prov.review
        review_status = _review_status(sourced)
        limit = self._limits.get(path) if path else None
        category = _category(sourced, limit)
        not_required = self._not_required(path, sourced)
        return ReviewItem(
            key=key,
            label=label,
            full_label=f"{group_label} {label}".strip() if group_label else label,
            value_text=value_text,
            status=_interpretation_status(sourced),
            notes=notes,
            raw_value=None if prov.raw_value is None else str(prov.raw_value),
            profile_id=prov.profile_id,
            profile_version=prov.profile_version,
            sources=tuple(self.source(r) for r in refs),
            item_id=path,
            primary=primary,
            review_status=review_status,
            blocking=path is not None and not sourced.is_resolved and path in self._blocking,
            left_unresolved=record is not None and record.status is ReviewStatus.LEFT_UNRESOLVED,
            user_value_text=record.user_value_text if record else None,
            resolution=_resolution(path, sourced, category),
            suggestion=None if not_required else _suggestion(path, sourced, category),
            not_required=not_required,
            not_required_reason=NOT_REQUIRED_REASON if not_required else None,
            resolution_origin=_resolution_origin(sourced),
            category=category,
            engine_reason=limit[1] if limit else None,
        )

    def impedance(
        self, key: str, label: str, group_label: str, sourced: Sourced, path: str | None = None
    ) -> list[ReviewItem]:
        value = sourced.value
        if isinstance(value, ImpedanceValue):
            if value.is_polar:
                parts = [
                    (f"{key}", label, _with_unit(_number(value.magnitude_ohm), "ohm")),
                    (f"{key}.angle", f"{label} Angle", _with_unit(_number(value.angle_deg), "deg")),
                ]
            else:
                parts = [
                    (f"{key}.r", f"{label} R", _with_unit(_number(value.r_ohm), "ohm")),
                    (f"{key}.x", f"{label} X", _with_unit(_number(value.x_ohm), "ohm")),
                ]
            return [
                self.item(k, lab, group_label, sourced, text=t, path=path, primary=i == 0)
                for i, (k, lab, t) in enumerate(parts)
            ]
        return [self.item(key, label, group_label, sourced, path=path)]

    def extras(
        self, key: str, group_label: str, extras: tuple[ExtraQuantity, ...], path: str
    ) -> list[ReviewItem]:
        return [
            self.item(
                f"{key}.{e.name}", _humanize(e.name), group_label, e.value, unit=e.unit,
                path=f"{path}[{item_label(e, i)}].value",
            )
            for i, e in enumerate(extras)
        ]

    def unresolved_setting(self, key: str, group_label: str, setting: UnresolvedSetting) -> ReviewItem:
        raw = self._raw.get(setting.setting_id)
        sources = (self.source_from_setting(setting.setting_id),) if raw else ()
        return ReviewItem(
            key=key,
            label=setting.name or setting.setting_id,
            full_label=f"{group_label} {setting.name or setting.setting_id}".strip(),
            value_text=None,
            status=MappingStatus.UNRESOLVED.value,
            notes=(setting.reason,) if setting.reason else (NOT_STATED,),
            raw_value=None if setting.raw_value is None else str(setting.raw_value),
            sources=sources,
            review_status="unresolved",
            # Retained raw because this profile version has no canonical meaning for it
            # (e.g. a per-loop tilt): Oruxa cannot represent or use it, and nothing the
            # user does with it changes that.
            category="unsupported",
        )

    def source_from_setting(self, setting_id: str) -> ReviewSource:
        return self.source(SourceRef(setting_id))

    def raw_row(self, setting: UnresolvedSetting) -> ReviewRawSetting:
        raw = self._raw.get(setting.setting_id)
        return ReviewRawSetting(
            code=raw.parameter_id if raw else None,
            name=setting.name or (raw.name if raw else None),
            raw_value=None if setting.raw_value is None else _with_unit(str(setting.raw_value), setting.unit),
            page=raw.location.page if raw else None,
            line=raw.location.line if raw else None,
            reason=setting.reason,
        )


def _touched(sourced: Sourced) -> bool:
    p = sourced.provenance
    return bool(sourced.is_resolved or p.sources or p.raw_value is not None or p.notes)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def _relay_group(b: _Builder, model: CanonicalDistanceProtectionModel) -> ReviewGroup:
    m = model.metadata
    items = [
        b.item("relay.manufacturer", "Manufacturer", "", m.manufacturer, path="metadata.manufacturer"),
        b.item("relay.family", "Relay Family", "", m.family, path="metadata.family"),
        b.item("relay.model", "Model", "", m.model, path="metadata.model"),
        b.item("relay.scheme", "Scheme / Template", "", m.scheme_name, path="metadata.scheme_name"),
        b.item("relay.version", "Firmware Version", "", m.version, path="metadata.version"),
        b.item(
            "relay.setting_group", "Active Setting Group", "", m.active_setting_group,
            path="metadata.active_setting_group",
        ),
    ]
    return ReviewGroup("relay", "relay", "Relay / source information", items=tuple(items))


def _transformer_group(b: _Builder, model: CanonicalDistanceProtectionModel) -> ReviewGroup:
    t = model.transformers
    items = [
        b.item("ct.primary", "CT Primary", "", t.ct_primary_a, unit="A", path="transformers.ct_primary_a"),
        b.item("ct.secondary", "CT Secondary", "", t.ct_secondary_a, unit="A", path="transformers.ct_secondary_a"),
        b.item("vt.primary", "VT Primary", "", t.vt_primary_v, unit="V", path="transformers.vt_primary_v"),
        b.item("vt.secondary", "VT Secondary", "", t.vt_secondary_v, unit="V", path="transformers.vt_secondary_v"),
        b.item("basis", "Setting Values Basis", "", t.setting_basis, path="transformers.setting_basis"),
        b.item("base.voltage", "Voltage Base", "", t.voltage_base_v, unit="V", path="transformers.voltage_base_v"),
        b.item("base.current", "Current Base", "", t.current_base_a, unit="A", path="transformers.current_base_a"),
    ]
    return ReviewGroup("ct_vt", "transformers", "CT / VT", items=tuple(items))


def _line_group(b: _Builder, model: CanonicalDistanceProtectionModel) -> ReviewGroup:
    line = model.line
    unit_value = line.length_unit.value if line.length_unit.is_resolved else None
    length_text = _value_text(line.length.value, str(unit_value) if unit_value else None) if line.length.is_resolved else None
    items = [
        b.item(
            "line.length", "Line Length", "", line.length, text=length_text,
            extra_sources=line.length_unit.provenance.sources if unit_value else (),
            path="line.length",
        ),
        b.item("line.angle", "Line Angle", "", line.line_angle_deg, unit="deg", path="line.line_angle_deg"),
        *b.impedance(
            "line.z1", "Positive-Sequence Impedance", "", line.positive_sequence_impedance,
            "line.positive_sequence_impedance",
        ),
    ]
    if _touched(line.zero_sequence_impedance):
        items += b.impedance(
            "line.z0", "Zero-Sequence Impedance", "", line.zero_sequence_impedance, "line.zero_sequence_impedance"
        )
    items += b.extras("line", "", line.extras, "line.extras")
    return ReviewGroup("line", "line", "Protected line", items=tuple(items))


def _zone_state(zone: DistanceZone) -> tuple[str, str, str]:
    """(label, interpretation status, review status) of the zone's own status."""
    status = zone.status
    if not status.is_resolved:
        return "Status unresolved", _interpretation_status(status), _review_status(status)
    label = _STATUS_LABELS.get(str(_enum_str(status.value)), "Unknown")
    if status.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION:
        label = label.split(" / ")[0]  # Oruxa's assumption, not a relay "Defeated" statement
    return label, _interpretation_status(status), _review_status(status)


def _zone_group(b: _Builder, zone: DistanceZone) -> ReviewGroup:
    name = zone.name or f"Zone {zone.zone_id}"
    pre = f"zone.{zone.zone_id}"
    zp = f"zones[{zone.zone_id}]"
    items: list[ReviewItem] = []

    state_text = None if not zone.status.is_resolved else _zone_state(zone)[0]
    items.append(b.item(f"{pre}.status", "Status", name, zone.status, text=state_text, path=f"{zp}.status"))
    items.append(b.item(f"{pre}.direction", "Direction", name, zone.direction, path=f"{zp}.direction"))
    ctype = zone.characteristic.type
    ctype_text = _CHARACTERISTIC_LABELS.get(str(_enum_str(ctype.value))) if ctype.is_resolved else None
    items.append(
        b.item(f"{pre}.characteristic", "Characteristic", name, ctype, text=ctype_text, path=f"{zp}.characteristic.type")
    )
    items += b.impedance(f"{pre}.reach", "Reach", name, zone.reach, f"{zp}.reach")
    if _touched(zone.earth_reach):
        items += b.impedance(f"{pre}.earth_reach", "Earth Reach", name, zone.earth_reach, f"{zp}.earth_reach")
    if _touched(zone.zero_sequence_reach):
        items += b.impedance(
            f"{pre}.zero_reach", "Zero-Sequence Reach", name, zone.zero_sequence_reach, f"{zp}.zero_sequence_reach"
        )

    rr = zone.resistive_reach
    if _touched(rr.common):
        items.append(
            b.item(f"{pre}.rr.common", "Resistive Reach", name, rr.common, unit="ohm", path=f"{zp}.resistive_reach.common")
        )
    items.append(
        b.item(
            f"{pre}.rr.pp", "Phase-Phase Resistive Reach", name, rr.phase_phase, unit="ohm",
            path=f"{zp}.resistive_reach.phase_phase",
        )
    )
    items.append(
        b.item(
            f"{pre}.rr.pe", "Earth Resistive Reach", name, rr.phase_earth, unit="ohm",
            path=f"{zp}.resistive_reach.phase_earth",
        )
    )
    quadrilateral = ctype.is_resolved and ctype.value == CharacteristicType.QUADRILATERAL
    if quadrilateral or _touched(rr.reverse):
        items.append(
            b.item(
                f"{pre}.rr.reverse", "Left Resistive Reach (−R)", name, rr.reverse, unit="ohm",
                path=f"{zp}.resistive_reach.reverse",
            )
        )
    items += b.extras(f"{pre}.rr", name, rr.extras, f"{zp}.resistive_reach.extras")

    timers = [
        (f"{pre}.timer", "Time Delay", zone.common_timer_s, "common_timer_s"),
        (f"{pre}.timer.pp", "Phase Time Delay", zone.phase_timer_s, "phase_timer_s"),
        (f"{pre}.timer.pe", "Earth Time Delay", zone.earth_timer_s, "earth_timer_s"),
    ]
    shown = [t for t in timers if _touched(t[2])]
    for key, label, timer, attr in shown or timers[:1]:
        items.append(b.item(key, label, name, timer, unit="s", path=f"{zp}.{attr}"))

    items.append(
        b.item(f"{pre}.pp_enabled", "Phase-Phase Faults", name, zone.phase_phase_enabled, path=f"{zp}.phase_phase_enabled")
    )
    items.append(
        b.item(f"{pre}.pe_enabled", "Earth Faults", name, zone.phase_earth_enabled, path=f"{zp}.phase_earth_enabled")
    )
    if _touched(zone.tilt_deg):
        items.append(b.item(f"{pre}.tilt", "Tilt Angle", name, zone.tilt_deg, unit="deg", path=f"{zp}.tilt_deg"))
    items += b.extras(f"{pre}.char", name, zone.characteristic.parameters, f"{zp}.characteristic.parameters")
    for u in zone.unresolved_settings:
        if not u.out_of_scope:
            items.append(b.unresolved_setting(f"{pre}.raw.{u.setting_id}", name, u))

    state_label, state_status, state_review = _zone_state(zone)
    note = None
    if zone.status.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION:
        note = (
            f"{name} was not found in the uploaded relay settings. "
            "Oruxa assumes this optional zone is disabled."
        )
    return ReviewGroup(
        f"zone-{zone.zone_id}", "zone", name, state_label, state_status, state_review, note, tuple(items)
    )


def _compensation_group(b: _Builder, model: CanonicalDistanceProtectionModel) -> ReviewGroup | None:
    items: list[ReviewItem] = []
    for zone in model.zones:
        comp = zone.compensation
        if comp is None:
            continue
        name = zone.name or f"Zone {zone.zone_id}"
        if comp.kind is CompensationKind.OEM_SPECIFIC:
            items += b.extras(f"comp.{zone.zone_id}", name, comp.oem_values, f"zones[{zone.zone_id}].compensation.oem_values")
            continue
        for attr, label, unit in _COMPENSATION_COMPONENTS[comp.kind]:
            items.append(
                b.item(
                    f"comp.{zone.zone_id}.{attr}", f"{name} {label}", "", getattr(comp, attr), unit=unit or None,
                    path=f"zones[{zone.zone_id}].compensation.{attr}",
                )
            )
    return ReviewGroup("compensation", "compensation", "Residual compensation", items=tuple(items)) if items else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _engine_reasons(adaptation: EngineAdaptation) -> tuple[ReviewEngineReason, ...]:
    """Adapter reasons, with one identical message across several zones merged."""
    return tuple(ReviewEngineReason(issue.zone_ids, issue.message) for issue in blocking_issues(adaptation))


def _counted_items(groups: list[ReviewGroup]) -> list[ReviewItem]:
    """One item per canonical value (a value shown as two rows counts once), plus
    every item with no canonical target (a declined zone setting)."""
    return [item for group in groups for item in group.items if item.primary]


def build_extraction_review(
    model: CanonicalDistanceProtectionModel,
    document: RawRelayDocument,
    adaptation: EngineAdaptation,
    *,
    not_interpreted: int,
) -> ExtractionReview:
    inactive = frozenset(z.zone_id for z in model.zones if zone_active(z) is False)
    b = _Builder(document, blocking_paths(adaptation), engine_limits(adaptation), inactive)
    groups = [_relay_group(b, model), _transformer_group(b, model), _line_group(b, model)]
    groups += [_zone_group(b, z) for z in model.zones]
    comp = _compensation_group(b, model)
    if comp:
        groups.append(comp)
    meta = model.metadata
    counted = _counted_items(groups)

    def count(status: str) -> int:
        return sum(1 for item in counted if item.review_status == status)

    def in_category(category: str, *review_statuses: str, required_only: bool = False) -> int:
        return sum(
            1 for item in counted
            if item.category == category
            and (not review_statuses or item.review_status in review_statuses)
            and not (required_only and item.not_required)
        )

    blocking_unresolved = sum(1 for item in counted if item.blocking)
    pending = count("to_confirm")
    readiness = compute_readiness(
        engine_supported=adaptation.supported, pending_confirmations=pending, blocking_unresolved=blocking_unresolved
    )
    return ExtractionReview(
        manufacturer=meta.manufacturer.value,
        relay_family=meta.family.value,
        model=meta.model.value,
        profile_id=meta.profile_id,
        profile_version=meta.profile_version,
        zone_count=len(model.zones),
        mapped_count=sum(1 for item in counted if item.review_status == "mapped" and item.category == "mapped"),
        to_confirm_count=pending,
        assumption_count=in_category("assumption", "to_confirm"),
        missing_count=in_category("missing", "unresolved", required_only=True),
        conflict_count=in_category("conflict"),
        unsupported_count=in_category("unsupported"),
        unreadable_count=in_category("unreadable", "unresolved", required_only=True),
        unresolved_count=count("unresolved"),
        not_interpreted_count=not_interpreted,
        confirmed_count=count("confirmed"),
        resolved_manually_count=count("resolved_manually"),
        blocking_count=blocking_unresolved,
        not_required_count=sum(1 for item in counted if item.not_required),
        readiness=ReviewReadiness(readiness.value, pending, blocking_unresolved),
        blocking_issues=tuple(
            ReviewBlockingIssue(issue.message, issue.zone_ids, issue.paths) for issue in blocking_issues(adaptation)
        ),
        interpretation="reviewable" if model.zones else "incomplete",
        engine=ReviewEngine(
            status="ready" if adaptation.supported else "not_ready",
            reasons=_engine_reasons(adaptation),
            warnings=adaptation.warnings,
        ),
        notes=model.interpretation_notes,
        groups=tuple(groups),
        not_interpreted=tuple(b.raw_row(u) for u in model.unmapped_settings if not u.out_of_scope),
        out_of_scope=tuple(b.raw_row(u) for u in model.unmapped_settings if u.out_of_scope),
    )
