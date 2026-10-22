"""The canonical parameter registry: the application's own vocabulary for distance protection.

The registry is an external JSON file (``parameter_catalog/canonical/distance_protection.json``).
Each entry names a canonical parameter -- its id, the label the frontend shows, its engineering
type and unit, its presentation group and order, and the *engine path*: where in the canonical
model (`CanonicalDistanceProtectionModel`) the value lives. OEM catalogs map *into* these ids;
the Distance Protection engine only ever reads the canonical model these ids populate, never an
OEM file.

Engine path grammar::

    metadata.manufacturer                        document level, a Sourced field
    zones[].resistive_reach.phase_phase          the same field of every zone
    zones[].characteristic.parameters{name}      an `ExtraQuantity` called ``name`` in that tuple
    zones[].characteristic.geometry_mode         a plain (non-Sourced) enum field (``"plain": true``)

Every path is checked against the model's dataclasses when the registry loads, so a typo is a
load error and not a silently unreachable parameter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from app.domain.parameter_catalog.errors import CatalogIssue, CatalogValidationError, IssueCode
from app.domain.parameter_catalog.units import is_known_unit
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    GeometryMode,
    SettingBasis,
    TripCapability,
    ZoneDirection,
    ZoneStatus,
)

REGISTRY_SCHEMA = "oruxa.canonical-registry/1"

#: Canonical enums a parameter may take values from (value strings are the enums' values).
ENUM_TYPES: dict[str, type[Enum]] = {
    cls.__name__: cls
    for cls in (ZoneStatus, ZoneDirection, CharacteristicType, GeometryMode, SettingBasis, CompensationKind, TripCapability)
}

DATA_TYPES = frozenset({"number", "text", "boolean", "enum", "impedance"})
SCOPES = frozenset({"document", "zone"})

#: Contexts a structured ``applies_when`` / ``required_when`` condition may test.
CONDITION_KEYS: dict[str, str] = {"geometry_mode": "GeometryMode", "characteristic": "CharacteristicType"}

_PARAM_KEYS = frozenset({
    "id", "label", "label_variants", "data_type", "enum_type", "unit", "group", "order", "scope", "engine_path",
    "plain", "component_of", "applies_when", "required_when", "compensation_kind", "description",
})
_TOP_KEYS = frozenset({"schema", "registry_id", "version", "description", "groups", "parameters"})
_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PATH = re.compile(r"^(?P<base>[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*)(?:\{(?P<extra>[a-z][a-z0-9_]*)\})?$")


@dataclass(frozen=True)
class CanonicalParameter:
    id: str
    label: str
    data_type: str
    unit: str
    group: str
    order: int
    scope: str
    #: Where the value lives in the canonical model; ``None`` for a component of a composite value.
    engine_path: str | None = None
    enum_type: str | None = None
    #: A plain (non-``Sourced``) field of the canonical model: only the value is stored.
    plain: bool = False
    component_of: str | None = None
    #: Label overrides keyed by geometry mode (e.g. the phase-phase reach is the "Right Resistive
    #: Reach (+R)" of an explicit R/X zone).
    label_variants: dict[str, str] = field(default_factory=dict)
    applies_when: dict[str, str] = field(default_factory=dict)
    required_when: dict[str, str] = field(default_factory=dict)
    compensation_kind: str | None = None
    description: str = ""

    @property
    def extra_name(self) -> str | None:
        """The `ExtraQuantity` name when the value lives in an extras tuple, else ``None``."""
        m = _PATH.match(self.engine_path or "")
        return m["extra"] if m else None

    @property
    def model_path(self) -> str | None:
        """The engine path without the ``zones[].`` prefix and the ``{extra}`` suffix."""
        if not self.engine_path:
            return None
        m = _PATH.match(self.engine_path)
        base = m["base"] if m else self.engine_path
        return base.removeprefix("zones[].")

    def label_for(self, geometry_mode: str | None = None) -> str:
        return self.label_variants.get(geometry_mode or "", self.label)

    def enum_values(self) -> frozenset[str]:
        enum = ENUM_TYPES.get(self.enum_type or "")
        return frozenset(m.value for m in enum) if enum else frozenset()


@dataclass(frozen=True)
class CanonicalRegistry:
    registry_id: str
    version: str
    groups: dict[str, tuple[str, int]]
    parameters: tuple[CanonicalParameter, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {p.id: p for p in self.parameters})
        object.__setattr__(self, "_by_path", {p.engine_path: p for p in self.parameters if p.engine_path})

    def get(self, canonical_id: str) -> CanonicalParameter | None:
        return self._by_id.get(canonical_id)  # type: ignore[attr-defined]

    def __contains__(self, canonical_id: object) -> bool:
        return canonical_id in self._by_id  # type: ignore[attr-defined]

    def by_engine_path(self, engine_path: str) -> CanonicalParameter | None:
        return self._by_path.get(engine_path)  # type: ignore[attr-defined]

    def for_review_path(self, review_path: str) -> CanonicalParameter | None:
        """The parameter for a review item path such as ``zones[Z1].resistive_reach.phase_phase``
        or ``zones[Z1].characteristic.parameters[directional_arg_dir].value``."""
        m = re.match(r"^zones\[[^\]]*\]\.characteristic\.parameters\[(?P<n>[^\]]+)\]\.value$", review_path)
        if m:
            return self._by_path.get(f"zones[].characteristic.parameters{{{m['n']}}}")  # type: ignore[attr-defined]
        normalised = re.sub(r"^zones\[[^\]]*\]", "zones[]", review_path)
        return self._by_path.get(normalised)  # type: ignore[attr-defined]

    def label_for_review_path(self, review_path: str, geometry_mode: str | None = None) -> str | None:
        param = self.for_review_path(review_path)
        return param.label_for(geometry_mode) if param else None


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def _resolve_dataclass(cls: type, name: str) -> type | None:
    """The dataclass type of attribute ``name`` of ``cls`` (unwrapping Optional / tuple), if any."""
    hints = get_type_hints(cls)
    if name not in {f.name for f in fields(cls)}:
        return None
    hint = hints[name]
    candidates = [hint, *get_args(hint)]
    for arg in candidates:
        if get_origin(arg) is tuple:
            candidates.extend(get_args(arg))
    return next((c for c in candidates if isinstance(c, type) and is_dataclass(c)), None)


def _check_engine_path(param: dict, issues: list[CatalogIssue], where: str) -> None:
    path = param.get("engine_path")
    m = _PATH.match(path or "")
    if not m:
        issues.append(CatalogIssue(where, IssueCode.MALFORMED, f"engine_path {path!r} is not a valid path"))
        return
    scope = param.get("scope")
    base = m["base"]
    root: type = CanonicalDistanceProtectionModel
    if scope == "zone":
        if not base.startswith("zones[]."):
            issues.append(CatalogIssue(where, IssueCode.MALFORMED, "a zone-scope parameter's engine_path must start with 'zones[].'"))
            return
        base, root = base.removeprefix("zones[]."), DistanceZone
    elif base.startswith("zones[]"):
        issues.append(CatalogIssue(where, IssueCode.MALFORMED, "a document-scope parameter cannot target 'zones[]'"))
        return
    cls: type | None = root
    segments = base.split(".")
    for i, segment in enumerate(segments):
        if cls is None or segment not in {f.name for f in fields(cls)}:
            issues.append(CatalogIssue(where, IssueCode.MALFORMED, f"engine_path {path!r}: no field {segment!r} in the canonical model"))
            return
        if i < len(segments) - 1:
            cls = _resolve_dataclass(cls, segment)
        elif m["extra"]:
            hints = get_type_hints(cls)[segment]
            if ExtraQuantity not in get_args(hints) and ExtraQuantity not in [a for h in get_args(hints) for a in get_args(h)]:
                issues.append(CatalogIssue(where, IssueCode.MALFORMED, f"engine_path {path!r}: {segment!r} does not hold named extra quantities"))


def _condition_ok(cond: Any, where: str, issues: list[CatalogIssue]) -> dict[str, str]:
    if cond is None:
        return {}
    if not isinstance(cond, dict):
        issues.append(CatalogIssue(where, IssueCode.MALFORMED, "a condition must be an object"))
        return {}
    for key, value in cond.items():
        enum_name = CONDITION_KEYS.get(key)
        if enum_name is None:
            issues.append(CatalogIssue(f"{where}.{key}", IssueCode.UNKNOWN_FIELD, f"condition key {key!r} is not one of {sorted(CONDITION_KEYS)}"))
        elif value not in {m.value for m in ENUM_TYPES[enum_name]}:
            issues.append(CatalogIssue(f"{where}.{key}", IssueCode.INVALID_ENUM, f"{value!r} is not a {enum_name} value"))
    return {k: v for k, v in cond.items() if k in CONDITION_KEYS}


def parse_registry(data: Any, source: str = "canonical registry") -> CanonicalRegistry:
    """Validate the registry document and build it; raises `CatalogValidationError` listing every issue."""
    issues: list[CatalogIssue] = []
    if not isinstance(data, dict):
        raise CatalogValidationError(source, [CatalogIssue("$", IssueCode.MALFORMED, "the registry must be a JSON object")])
    for key in data:
        if key not in _TOP_KEYS:
            issues.append(CatalogIssue(key, IssueCode.UNKNOWN_FIELD, "unknown top-level key"))
    if data.get("schema") != REGISTRY_SCHEMA:
        issues.append(CatalogIssue("schema", IssueCode.MALFORMED, f"schema must be {REGISTRY_SCHEMA!r}"))
    for key in ("registry_id", "version"):
        if not isinstance(data.get(key), str) or not data.get(key):
            issues.append(CatalogIssue(key, IssueCode.MISSING_METADATA, f"{key} is required"))
    groups: dict[str, tuple[str, int]] = {}
    for i, g in enumerate(data.get("groups") or []):
        if not isinstance(g, dict) or not {"id", "label", "order"} <= set(g) or g["id"] in groups:
            issues.append(CatalogIssue(f"groups[{i}]", IssueCode.MALFORMED, "a group needs a unique id, a label and an order"))
        else:
            groups[g["id"]] = (g["label"], g["order"])
    if not groups:
        issues.append(CatalogIssue("groups", IssueCode.MISSING_METADATA, "at least one presentation group is required"))

    raw_params = data.get("parameters")
    if not isinstance(raw_params, list) or not raw_params:
        issues.append(CatalogIssue("parameters", IssueCode.MISSING_METADATA, "parameters must be a non-empty list"))
        raw_params = []
    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    params: list[CanonicalParameter] = []
    for i, p in enumerate(raw_params):
        where = f"parameters[{i}]"
        if not isinstance(p, dict):
            issues.append(CatalogIssue(where, IssueCode.MALFORMED, "a parameter must be an object"))
            continue
        pid = p.get("id")
        where = f"parameters[{pid or i}]"
        for key in p:
            if key not in _PARAM_KEYS:
                issues.append(CatalogIssue(f"{where}.{key}", IssueCode.UNKNOWN_FIELD, "unknown parameter key"))
        if not isinstance(pid, str) or not _ID.match(pid):
            issues.append(CatalogIssue(where, IssueCode.MALFORMED, "id must be dotted lower-case words, e.g. 'distance.zone.x_reach'"))
            continue
        if pid in seen_ids:
            issues.append(CatalogIssue(where, IssueCode.DUPLICATE, "duplicate canonical id"))
            continue
        seen_ids.add(pid)
        for key in ("label", "data_type", "group", "scope"):
            if not isinstance(p.get(key), str) or not p.get(key):
                issues.append(CatalogIssue(f"{where}.{key}", IssueCode.MISSING_METADATA, f"{key} is required"))
        if p.get("data_type") not in DATA_TYPES:
            issues.append(CatalogIssue(f"{where}.data_type", IssueCode.MALFORMED, f"data_type must be one of {sorted(DATA_TYPES)}"))
        if p.get("scope") not in SCOPES:
            issues.append(CatalogIssue(f"{where}.scope", IssueCode.MALFORMED, f"scope must be one of {sorted(SCOPES)}"))
        unit = p.get("unit", "")
        if not isinstance(unit, str) or not is_known_unit(unit):
            issues.append(CatalogIssue(f"{where}.unit", IssueCode.INVALID_UNIT, f"unknown canonical unit {unit!r}"))
        if p.get("group") not in groups:
            issues.append(CatalogIssue(f"{where}.group", IssueCode.MALFORMED, f"unknown presentation group {p.get('group')!r}"))
        if not isinstance(p.get("order"), int) or isinstance(p.get("order"), bool):
            issues.append(CatalogIssue(f"{where}.order", IssueCode.MALFORMED, "order must be an integer"))
        if p.get("data_type") == "enum":
            if p.get("enum_type") not in ENUM_TYPES:
                issues.append(CatalogIssue(f"{where}.enum_type", IssueCode.INVALID_ENUM, f"enum_type must be one of {sorted(ENUM_TYPES)}"))
        elif p.get("enum_type") is not None:
            issues.append(CatalogIssue(f"{where}.enum_type", IssueCode.INVALID_ENUM, "enum_type is only valid for data_type 'enum'"))
        component_of = p.get("component_of")
        if component_of is not None:
            if p.get("engine_path"):
                issues.append(CatalogIssue(where, IssueCode.MALFORMED, "a component has no engine_path of its own"))
        elif p.get("engine_path"):
            _check_engine_path(p, issues, f"{where}.engine_path")
            if p["engine_path"] in seen_paths:
                issues.append(CatalogIssue(where, IssueCode.DUPLICATE, f"engine_path already used by {seen_paths[p['engine_path']]}"))
            seen_paths[p["engine_path"]] = pid
        else:
            issues.append(CatalogIssue(where, IssueCode.MISSING_METADATA, "engine_path is required (or component_of for a component)"))
        variants = p.get("label_variants") or {}
        if not isinstance(variants, dict) or any(k not in {m.value for m in GeometryMode} for k in variants):
            issues.append(CatalogIssue(f"{where}.label_variants", IssueCode.MALFORMED, "label_variants keys must be geometry modes"))
            variants = {}
        kind = p.get("compensation_kind")
        if kind is not None and kind not in {m.value for m in CompensationKind}:
            issues.append(CatalogIssue(f"{where}.compensation_kind", IssueCode.INVALID_ENUM, f"{kind!r} is not a CompensationKind"))
        applies = _condition_ok(p.get("applies_when"), f"{where}.applies_when", issues)
        required = _condition_ok(p.get("required_when"), f"{where}.required_when", issues)
        if all(isinstance(p.get(k), str) for k in ("label", "data_type", "group", "scope")):
            params.append(CanonicalParameter(
                id=pid, label=p["label"], data_type=p["data_type"], unit=unit if isinstance(unit, str) else "",
                group=p["group"], order=p["order"] if isinstance(p.get("order"), int) else 0, scope=p["scope"],
                engine_path=p.get("engine_path"), enum_type=p.get("enum_type"), plain=bool(p.get("plain", False)),
                component_of=component_of, label_variants=dict(variants), applies_when=applies, required_when=required,
                compensation_kind=kind, description=p.get("description", ""),
            ))
    ids = {p.id for p in params}
    for p in params:
        if p.component_of and p.component_of not in ids:
            issues.append(CatalogIssue(f"parameters[{p.id}].component_of", IssueCode.UNKNOWN_CANONICAL, f"unknown composite {p.component_of!r}"))
    if issues:
        raise CatalogValidationError(source, issues)
    return CanonicalRegistry(data["registry_id"], data["version"], groups, tuple(params))


def load_registry(path: Path) -> CanonicalRegistry:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(str(path), [CatalogIssue("$", IssueCode.MALFORMED, f"cannot read registry: {exc}")]) from exc
    return parse_registry(data, str(path))
