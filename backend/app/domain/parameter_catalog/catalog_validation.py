"""Strict schema + semantic validation of an OEM parameter catalog.

`parse_catalog` turns catalog JSON into a typed `Catalog` or raises `CatalogValidationError`
listing *every* problem -- nothing is skipped or defaulted silently. A catalog that does not
validate is never used.

Schema checks: shape, types, required metadata, unknown keys, lifecycle, versions.
Semantic checks (against the canonical registry): unknown canonical target, invalid unit or a
missing conversion, duplicate / conflicting mappings, unsupported or mistyped transformation,
enum maps outside the canonical enum, zone targets the catalog's zone model does not define,
selectors that cannot match, a printed range / default / note offered as the configured
setting, and references to canonical values that are not available at that point.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.parameter_catalog.catalog_model import (
    AUTHORITIES,
    AUTHORITY_PRECEDENCE,
    CATALOG_SCHEMA,
    CONFIDENCES,
    LIFECYCLES,
    VALUE_SOURCE_PRECEDENCE,
    VALUE_SOURCES,
    Applicability,
    Catalog,
    ConditionalText,
    DistanceScope,
    Family,
    FamilyIndex,
    Gap,
    Gate,
    Identification,
    Mapping,
    NoteSubject,
    PreservedSettings,
    PrintedUnitRule,
    Selector,
    Step,
    Validation,
    ZoneModel,
    ZoneNoteRule,
)
from app.domain.parameter_catalog.errors import CatalogIssue, CatalogValidationError, IssueCode
from app.domain.parameter_catalog.registry import CanonicalParameter, CanonicalRegistry
from app.domain.parameter_catalog.transforms import PRIMITIVES, check_params, expected_unit
from app.domain.parameter_catalog.units import conversion_factor, is_known_unit

_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_TEMPLATE = re.compile(r"\{([A-Za-z_]+)\}")
_ZONE_VARS = {"n", "nn", "zone", "key"}
_FAMILY_VARS = {"n"}

_TOP_KEYS = {"schema", "catalog_id", "version", "lifecycle", "description", "applicability", "profile_id",
             "identification", "zones", "distance_scope", "mappings", "registry_version", "interpretation_notes",
             "source_notes", "zone_preserved"}
_NOTE_KEYS = {"pattern", "zone_id", "zone_ids", "subjects"}
_NOTE_SUBJECT_KEYS = {"subject", "pattern", "value"}
_NOTE_SUBJECTS = ("timer", "status")
_PRESERVED_KEYS = {"zone", "names", "name_pattern", "reason"}
_APPLICABILITY_KEYS = {"manufacturer", "family", "model", "versions"}
_IDENT_KEYS = {"model_patterns", "family_markers", "parameter_signatures", "scheme_pattern", "scheme_model_pattern", "version_pattern"}
_ZONES_KEYS = {"discover", "static"}
_SCOPE_KEYS = {"code_prefixes", "section_contains", "names", "name_patterns"}
_MAPPING_KEYS = {"id", "canonical", "zone", "source", "sources", "transform", "requires", "value_source", "authority",
                 "confidence", "note", "evidence", "evidence_from", "requires_resolved", "unresolved_note", "gap"}
_SELECTOR_KEYS = {"name", "code", "name_pattern", "pattern_in_text", "indexed_family", "zone_family", "section", "type",
                  "unit", "printed_unit", "validate", "allowed_text", "note"}
_PRINTED_KEYS = {"policy", "accept", "accept_if", "missing_when_unprinted"}
_VALIDATE_KEYS = {"within_printed_range", "allowed_values", "printed_range_pattern"}
_FAMILY_KEYS = {"index", "member", "expected_count", "aggregate"}
_ZONE_FAMILY_KEYS = {"member", "where", "aggregate", "min_count"}
_INDEX_KEYS = {"name_pattern", "value_pattern", "filter"}
_GATE_KEYS = {"source", "equals", "off_note", "missing_note"}
_GAP_KEYS = {"note", "evidence"}
_AGGREGATES = ("all_equal", "any")


class _Validator:
    def __init__(self, registry: CanonicalRegistry) -> None:
        self.registry = registry
        self.issues: list[CatalogIssue] = []

    def add(self, path: str, code: str, message: str) -> None:
        self.issues.append(CatalogIssue(path, code, message))

    def keys(self, obj: dict, allowed: set[str], path: str) -> None:
        for key in obj:
            if key not in allowed:
                self.add(f"{path}.{key}", IssueCode.UNKNOWN_FIELD, f"unknown key {key!r}")

    def string(self, obj: dict, key: str, path: str, *, required: bool = True) -> str | None:
        value = obj.get(key)
        if value is None or value == "":
            if required:
                self.add(f"{path}.{key}", IssueCode.MISSING_METADATA, f"{key} is required")
            return None
        if not isinstance(value, str):
            self.add(f"{path}.{key}", IssueCode.MALFORMED, f"{key} must be a string")
            return None
        return value

    def regex(self, pattern: Any, path: str, *, groups: int = 0, named: str | None = None) -> bool:
        if not isinstance(pattern, str) or not pattern:
            self.add(path, IssueCode.INVALID_SELECTOR, "a pattern must be a non-empty string")
            return False
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            self.add(path, IssueCode.INVALID_SELECTOR, f"not a valid regular expression: {exc}")
            return False
        if compiled.groups < groups:
            self.add(path, IssueCode.INVALID_SELECTOR, f"the pattern needs at least {groups} capture group(s)")
            return False
        if named and named not in compiled.groupindex:
            self.add(path, IssueCode.INVALID_SELECTOR, f"the pattern needs a named group (?P<{named}>...)")
            return False
        return True


def parse_catalog(data: Any, registry: CanonicalRegistry, source: str = "catalog", source_path: str = "") -> Catalog:
    """Validate ``data`` against the schema and ``registry``; raises `CatalogValidationError`."""
    v = _Validator(registry)
    if not isinstance(data, dict):
        raise CatalogValidationError(source, [CatalogIssue("$", IssueCode.MALFORMED, "a catalog must be a JSON object")])
    v.keys(data, _TOP_KEYS, "$")
    if data.get("schema") != CATALOG_SCHEMA:
        v.add("schema", IssueCode.MALFORMED, f"schema must be {CATALOG_SCHEMA!r}")

    catalog_id = v.string(data, "catalog_id", "$")
    if catalog_id and not _KEBAB.match(catalog_id):
        v.add("catalog_id", IssueCode.MALFORMED, "catalog_id must be lower-case kebab-case")
    version = v.string(data, "version", "$")
    if version and not _SEMVER.match(version):
        v.add("version", IssueCode.INVALID_VERSION, "version must be MAJOR.MINOR.PATCH")
    lifecycle = v.string(data, "lifecycle", "$")
    if lifecycle and lifecycle not in LIFECYCLES:
        v.add("lifecycle", IssueCode.INVALID_LIFECYCLE, f"lifecycle must be one of {list(LIFECYCLES)}")
    profile_id = v.string(data, "profile_id", "$", required=False) or catalog_id
    registry_version = v.string(data, "registry_version", "$", required=False) or ""
    if registry_version and registry_version.split(".")[0] != registry.version.split(".")[0]:
        v.add("registry_version", IssueCode.INVALID_VERSION,
              f"validated against canonical registry {registry_version}, but the registry in use is {registry.version}")

    notes = data.get("interpretation_notes", [])
    if not isinstance(notes, list) or not all(isinstance(x, str) for x in notes):
        v.add("interpretation_notes", IssueCode.MALFORMED, "interpretation_notes must be a list of strings")
        notes = []
    applicability = _applicability(v, data.get("applicability"))
    identification = _identification(v, data.get("identification"))
    zones = _zones(v, data.get("zones"))
    scope = _distance_scope(v, data.get("distance_scope"))
    note_rules = _source_notes(v, data.get("source_notes"))
    preserved = _zone_preserved(v, data.get("zone_preserved"), zones)

    raw_mappings = data.get("mappings")
    mappings: list[Mapping] = []
    if not isinstance(raw_mappings, list):
        v.add("mappings", IssueCode.MALFORMED, "mappings must be a list")
    else:
        if not raw_mappings and lifecycle != "draft":
            v.add("mappings", IssueCode.MISSING_METADATA, "a catalog past 'draft' needs at least one mapping")
        for i, raw in enumerate(raw_mappings):
            mapping = _mapping(v, raw, f"mappings[{i}]", zones, mappings)
            if mapping is not None:
                mappings.append(mapping)
        _cross_checks(v, mappings, zones)

    if v.issues or not (catalog_id and version and lifecycle and applicability and zones and profile_id):
        raise CatalogValidationError(source, v.issues or [CatalogIssue("$", IssueCode.MISSING_METADATA, "incomplete catalog")])
    return Catalog(
        catalog_id=catalog_id, version=version, lifecycle=lifecycle, applicability=applicability, profile_id=profile_id,
        mappings=tuple(_with_stage(m) for m in mappings), zones=zones, identification=identification,
        distance_scope=scope, description=str(data.get("description") or ""), notes=tuple(notes),
        source_notes=note_rules, zone_preserved=preserved,
        registry_version=registry_version or registry.version,
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# Header sections
# ---------------------------------------------------------------------------


def _applicability(v: _Validator, raw: Any) -> Applicability | None:
    if not isinstance(raw, dict):
        v.add("applicability", IssueCode.MISSING_METADATA, "applicability (manufacturer, family, model) is required")
        return None
    v.keys(raw, _APPLICABILITY_KEYS, "applicability")
    # an explicit ``"manufacturer": null`` states that the project has not established the manufacturer:
    # it is then never asserted (a missing key is still an error -- the author must say so on purpose)
    unasserted = "manufacturer" in raw and raw["manufacturer"] is None
    fields = {k: v.string(raw, k, "applicability") for k in ("family", "model")}
    fields["manufacturer"] = None if unasserted else v.string(raw, "manufacturer", "applicability")
    versions = raw.get("versions", ["*"])
    if not isinstance(versions, list) or not versions or not all(isinstance(x, str) and x for x in versions):
        v.add("applicability.versions", IssueCode.INVALID_VERSION, "versions must be a non-empty list of strings ('*' = any)")
        versions = ["*"]
    if not (fields["family"] and fields["model"] and (unasserted or fields["manufacturer"])):
        return None
    return Applicability(fields["manufacturer"], fields["family"], fields["model"], tuple(versions))  # type: ignore[arg-type]


def _identification(v: _Validator, raw: Any) -> Identification:
    if raw is None:
        return Identification()
    if not isinstance(raw, dict):
        v.add("identification", IssueCode.MALFORMED, "identification must be an object")
        return Identification()
    v.keys(raw, _IDENT_KEYS, "identification")
    out: dict[str, Any] = {}
    for key in ("model_patterns", "family_markers"):
        items = raw.get(key, [])
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            v.add(f"identification.{key}", IssueCode.MALFORMED, f"{key} must be a list of regular expressions")
            continue
        for k, pattern in enumerate(items):
            v.regex(pattern, f"identification.{key}[{k}]")
        out[key] = tuple(items)
    sigs = raw.get("parameter_signatures", [])
    if not isinstance(sigs, list) or not all(isinstance(x, dict) and {"name", "pattern"} <= set(x) for x in sigs):
        v.add("identification.parameter_signatures", IssueCode.MALFORMED, "parameter_signatures need a name and a pattern")
    else:
        for k, sig in enumerate(sigs):
            v.regex(sig["pattern"], f"identification.parameter_signatures[{k}].pattern")
        out["parameter_signatures"] = tuple(sigs)
    for key in ("scheme_pattern", "scheme_model_pattern", "version_pattern"):
        if raw.get(key) is not None:
            if v.regex(raw[key], f"identification.{key}", groups=1 if key == "scheme_pattern" else 0):
                out[key] = raw[key]
    return Identification(**out)


def _zones(v: _Validator, raw: Any) -> ZoneModel | None:
    if not isinstance(raw, dict) or len(set(raw) & _ZONES_KEYS) != 1 or set(raw) - _ZONES_KEYS:
        v.add("zones", IssueCode.MISSING_METADATA, "zones needs exactly one of 'discover' or 'static'")
        return None
    if "discover" in raw:
        d = raw["discover"]
        if not isinstance(d, dict) or not {"name_pattern", "id", "name"} <= set(d) or set(d) - {"name_pattern", "id", "name"}:
            v.add("zones.discover", IssueCode.MALFORMED, "discover needs name_pattern, id and name")
            return None
        ok = v.regex(d["name_pattern"], "zones.discover.name_pattern", named="n")
        for key in ("id", "name"):
            bad = set(_TEMPLATE.findall(str(d[key]))) - {"n"}
            if bad or "{n}" not in str(d[key]):
                v.add(f"zones.discover.{key}", IssueCode.INVALID_ZONE, f"the {key} template must use {{n}} (and only {{n}})")
                ok = False
        return ZoneModel("discover", d["name_pattern"], d["id"], d["name"]) if ok else None
    items = raw["static"]
    if not isinstance(items, list) or not items:
        v.add("zones.static", IssueCode.MALFORMED, "static must be a non-empty list of {id, name}")
        return None
    seen: set[str] = set()
    static: list[tuple[str, str]] = []
    keys: list[tuple[str, str]] = []
    for k, z in enumerate(items):
        if (not isinstance(z, dict) or not {"id", "name"} <= set(z) or set(z) - {"id", "name", "key"}
                or not all(isinstance(z[x], str) and z[x] for x in z)):
            v.add(f"zones.static[{k}]", IssueCode.MALFORMED, "a zone needs a string id and name (and an optional string key)")
            continue
        if z["id"] in seen:
            v.add(f"zones.static[{k}]", IssueCode.DUPLICATE, f"duplicate zone id {z['id']!r}")
            continue
        seen.add(z["id"])
        static.append((z["id"], z["name"]))
        keys.append((z["id"], z.get("key", z["id"])))
    return ZoneModel("static", static=tuple(static), keys=tuple(keys))


def _distance_scope(v: _Validator, raw: Any) -> DistanceScope:
    if raw is None:
        return DistanceScope()
    if not isinstance(raw, dict):
        v.add("distance_scope", IssueCode.MALFORMED, "distance_scope must be an object")
        return DistanceScope()
    v.keys(raw, _SCOPE_KEYS, "distance_scope")
    out = {}
    for key in _SCOPE_KEYS:
        items = raw.get(key, [])
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            v.add(f"distance_scope.{key}", IssueCode.MALFORMED, f"{key} must be a list of strings")
        else:
            if key == "name_patterns":
                for k, pattern in enumerate(items):
                    v.regex(pattern, f"distance_scope.name_patterns[{k}]")
            out[key] = tuple(items)
    return DistanceScope(**out)


def _source_notes(v: _Validator, raw: Any) -> tuple[ZoneNoteRule, ...]:
    """Zone document notes: provenance only, so there is nothing to type-check against the registry --
    only that every pattern compiles and every zone template is well-formed."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        v.add("source_notes", IssueCode.MALFORMED, "source_notes must be a list of note rules")
        return ()
    rules: list[ZoneNoteRule] = []
    for k, item in enumerate(raw):
        path = f"source_notes[{k}]"
        if not isinstance(item, dict) or "pattern" not in item:
            v.add(path, IssueCode.MALFORMED, "a note rule needs a pattern")
            continue
        v.keys(item, _NOTE_KEYS, path)
        ok = v.regex(item["pattern"], f"{path}.pattern", named="zone")
        zone_id = item.get("zone_id", "Z{zone}")
        if not isinstance(zone_id, str) or "{zone}" not in zone_id or set(_TEMPLATE.findall(zone_id)) - {"zone"}:
            v.add(f"{path}.zone_id", IssueCode.INVALID_ZONE, "zone_id must be a template using {zone} (and only {zone})")
            ok = False
        overrides = item.get("zone_ids", {})
        if not isinstance(overrides, dict) or not all(isinstance(a, str) and isinstance(b, str) and a and b
                                                      for a, b in overrides.items()):
            v.add(f"{path}.zone_ids", IssueCode.MALFORMED, "zone_ids must map note tokens to zone ids")
            ok, overrides = False, {}
        subjects: list[NoteSubject] = []
        for j, s in enumerate(item.get("subjects", [])):
            where = f"{path}.subjects[{j}]"
            if not isinstance(s, dict) or set(s) != _NOTE_SUBJECT_KEYS:
                v.add(where, IssueCode.MALFORMED, "a subject needs exactly subject, pattern and value")
                ok = False
                continue
            if s["subject"] not in _NOTE_SUBJECTS:
                v.add(f"{where}.subject", IssueCode.MALFORMED, f"subject must be one of {list(_NOTE_SUBJECTS)}")
                ok = False
            ok = v.regex(s["pattern"], f"{where}.pattern") and ok
            if not isinstance(s["value"], str) or not s["value"]:
                v.add(f"{where}.value", IssueCode.MALFORMED, "value must be a non-empty template")
                ok = False
            subjects.append(NoteSubject(str(s["subject"]), str(s["pattern"]), str(s["value"])))
        if ok:
            rules.append(ZoneNoteRule(item["pattern"], zone_id, tuple(overrides.items()), tuple(subjects)))
    return tuple(rules)


def _zone_preserved(v: _Validator, raw: Any, zones: ZoneModel | None) -> tuple[PreservedSettings, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        v.add("zone_preserved", IssueCode.MALFORMED, "zone_preserved must be a list")
        return ()
    out: list[PreservedSettings] = []
    for k, item in enumerate(raw):
        path = f"zone_preserved[{k}]"
        if not isinstance(item, dict):
            v.add(path, IssueCode.MALFORMED, "an entry must be an object")
            continue
        v.keys(item, _PRESERVED_KEYS, path)
        ok = True
        targets = _zone_targets(v, item.get("zone"), path, zones)
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            v.add(f"{path}.reason", IssueCode.MISSING_METADATA, "a reason is required: why the settings are kept uninterpreted")
            ok = False
        names = item.get("names")
        pattern = item.get("name_pattern")
        if (names is None) == (pattern is None):
            v.add(path, IssueCode.INVALID_SELECTOR, "give exactly one of names or name_pattern")
            continue
        if names is not None:
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
                v.add(f"{path}.names", IssueCode.INVALID_SELECTOR, "names must be a non-empty list of names")
                continue
            for j, name in enumerate(names):
                _check_template(v, f"{path}.names[{j}]", name, _ZONE_VARS, zones)
        else:
            if not isinstance(pattern, str) or not pattern:
                v.add(f"{path}.name_pattern", IssueCode.INVALID_SELECTOR, "name_pattern must be a non-empty string")
                continue
            _check_template(v, f"{path}.name_pattern", pattern, _ZONE_VARS, zones)
            ok = v.regex(_TEMPLATE.sub("x", pattern), f"{path}.name_pattern") and ok
        if ok and targets:
            out.append(PreservedSettings(targets, reason.strip(), tuple(names or ()), pattern))
    return tuple(out)


# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------


def _mapping(v: _Validator, raw: Any, path: str, zones: ZoneModel | None, earlier: list[Mapping]) -> Mapping | None:
    if not isinstance(raw, dict):
        v.add(path, IssueCode.MALFORMED, "a mapping must be an object")
        return None
    v.keys(raw, _MAPPING_KEYS, path)
    mid = v.string(raw, "id", path)
    path = f"mappings[{mid or path}]"
    if mid and any(m.id == mid for m in earlier):
        v.add(path, IssueCode.DUPLICATE, f"duplicate mapping id {mid!r}")
    canonical = v.string(raw, "canonical", path)
    param: CanonicalParameter | None = None
    if canonical:
        param = v.registry.get(canonical)
        if param is None:
            v.add(f"{path}.canonical", IssueCode.UNKNOWN_CANONICAL, f"{canonical!r} is not defined in the canonical registry")
        elif param.component_of:
            v.add(f"{path}.canonical", IssueCode.UNKNOWN_CANONICAL,
                  f"{canonical!r} is a component of {param.component_of!r}: map the composite, taking this as an input")
            param = None
    value_source = raw.get("value_source", "setting_value")
    if value_source not in VALUE_SOURCES:
        v.add(f"{path}.value_source", IssueCode.INVALID_VALUE_SOURCE, f"value_source must be one of {list(VALUE_SOURCES)}")
    elif value_source not in VALUE_SOURCE_PRECEDENCE:
        v.add(f"{path}.value_source", IssueCode.INVALID_VALUE_SOURCE,
              f"a {value_source!r} is not the configured setting and cannot supply a canonical value; "
              "only setting_value, engineering_instruction and profile_inference can")
    authority = raw.get("authority", "configured_setting")
    if authority not in AUTHORITIES:
        v.add(f"{path}.authority", IssueCode.MALFORMED, f"authority must be one of {list(AUTHORITIES)}")
    confidence = raw.get("confidence", "mapped")
    if confidence not in CONFIDENCES:
        v.add(f"{path}.confidence", IssueCode.MALFORMED, f"confidence must be one of {list(CONFIDENCES)}")
    if authority == "assumption" and confidence == "mapped":
        v.add(path, IssueCode.INVALID_VALUE_SOURCE, "an assumption can never be 'mapped'; its confidence must be 'inferred'")
    if authority == "configured_setting" and value_source not in ("setting_value",):
        v.add(path, IssueCode.INVALID_VALUE_SOURCE, "authority 'configured_setting' requires value_source 'setting_value'")
    if authority == "engineering_instruction" and value_source != "engineering_instruction":
        v.add(path, IssueCode.INVALID_VALUE_SOURCE, "authority 'engineering_instruction' requires value_source 'engineering_instruction'")

    # zone targets
    zone_ids: tuple[str, ...] = ()
    if param is not None:
        zone_raw = raw.get("zone")
        if param.scope == "zone":
            zone_ids = _zone_targets(v, zone_raw, path, zones)
        elif zone_raw is not None:
            v.add(f"{path}.zone", IssueCode.INVALID_ZONE, "a document-scope parameter takes no zone target")
    scoped = param is not None and param.scope == "zone"

    selector_vars = _ZONE_VARS if scoped else set()
    source = _selector(v, raw["source"], f"{path}.source", selector_vars, zones, scoped, param) if "source" in raw else None
    sources: list[tuple[str, Selector]] = []
    if "sources" in raw:
        if not isinstance(raw["sources"], dict) or not raw["sources"]:
            v.add(f"{path}.sources", IssueCode.MALFORMED, "sources must be a non-empty object of named selectors")
        else:
            for name, sel in raw["sources"].items():
                s = _selector(v, sel, f"{path}.sources.{name}", selector_vars, zones, scoped, param)
                if s is not None:
                    sources.append((name, s))
    if source is not None and "sources" in raw:
        v.add(path, IssueCode.MALFORMED, "give either 'source' or 'sources', not both")

    steps = _steps(v, raw.get("transform"), path)
    gates = _gates(v, raw.get("requires"), path, selector_vars, zones, scoped, param)
    evidence = _selector_list(v, raw.get("evidence"), f"{path}.evidence", selector_vars, zones, scoped, param)
    gap = None
    if raw.get("gap") is not None:
        g = raw["gap"]
        if not isinstance(g, dict) or "note" not in g:
            v.add(f"{path}.gap", IssueCode.MALFORMED, "a gap needs a note")
        else:
            v.keys(g, _GAP_KEYS, f"{path}.gap")
            gap = Gap(str(g["note"]), tuple(_selector_list(v, g.get("evidence"), f"{path}.gap.evidence", selector_vars, zones, scoped, param)))
    evidence_from = tuple(_canonical_list(v, raw.get("evidence_from"), f"{path}.evidence_from"))
    requires_resolved = tuple(_canonical_list(v, raw.get("requires_resolved"), f"{path}.requires_resolved"))

    if param is not None:
        if param.group == "relay":
            v.add(f"{path}.canonical", IssueCode.UNKNOWN_CANONICAL,
                  f"{param.id} is relay identity: it comes from the catalog's applicability and identification, not from a mapping")
        if steps and steps[0].type == "constant" and not param.plain and not (evidence or evidence_from):
            v.add(path, IssueCode.INVALID_TRANSFORM,
                  "a constant needs evidence (a selector or evidence_from) so that the value cites a source setting")
        _check_chain(v, path, param, source, sources, steps, gap)
        _check_units(v, path, param, source, sources, steps)
    if mid is None or canonical is None or param is None:
        return None
    return Mapping(
        id=mid, canonical=canonical, zones=zone_ids, source=source, sources=tuple(sources), steps=tuple(steps),
        gates=tuple(gates), value_source=value_source if isinstance(value_source, str) else "setting_value",
        authority=authority if isinstance(authority, str) else "configured_setting",
        confidence=confidence if isinstance(confidence, str) else "mapped", note=str(raw.get("note") or ""),
        evidence=tuple(evidence), evidence_from=evidence_from, requires_resolved=requires_resolved,
        unresolved_note=str(raw.get("unresolved_note") or ""), gap=gap,
    )


def _zone_targets(v: _Validator, raw: Any, path: str, zones: ZoneModel | None) -> tuple[str, ...]:
    if raw is None:
        v.add(f"{path}.zone", IssueCode.INVALID_ZONE, "a zone-scope parameter needs a 'zone' target ('*' or zone ids)")
        return ()
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list) or not items or not all(isinstance(x, str) and x for x in items):
        v.add(f"{path}.zone", IssueCode.INVALID_ZONE, "zone must be '*', a zone id or a list of zone ids")
        return ()
    if zones is None:
        return tuple(items)
    known = {zid for zid, _ in zones.static}
    for zid in items:
        if zid == "*":
            continue
        if zones.mode == "discover":
            v.add(f"{path}.zone", IssueCode.INVALID_ZONE, f"zone {zid!r}: discovered zones can only be targeted with '*'")
        elif zid not in known:
            v.add(f"{path}.zone", IssueCode.INVALID_ZONE, f"zone {zid!r} is not one of this catalog's zones {sorted(known)}")
    if "*" in items and len(items) > 1:
        v.add(f"{path}.zone", IssueCode.INVALID_ZONE, "'*' cannot be combined with zone ids")
    return tuple(items)


def _selector_list(v, raw, path, variables, zones, scoped, param) -> list[Selector]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        v.add(path, IssueCode.MALFORMED, "must be a list of selectors")
        return []
    out = []
    for k, sel in enumerate(raw):
        s = _selector(v, sel, f"{path}[{k}]", variables, zones, scoped, param)
        if s is not None:
            out.append(s)
    return out


def _canonical_list(v: _Validator, raw: Any, path: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        v.add(path, IssueCode.MALFORMED, "must be a list of canonical ids")
        return []
    for cid in raw:
        if cid not in v.registry:
            v.add(path, IssueCode.UNKNOWN_CANONICAL, f"{cid!r} is not defined in the canonical registry")
    return list(raw)


def _selector(v: _Validator, raw: Any, path: str, variables: set[str], zones: ZoneModel | None, scoped: bool,
              param: CanonicalParameter | None) -> Selector | None:
    if not isinstance(raw, dict):
        v.add(path, IssueCode.INVALID_SELECTOR, "a selector must be an object")
        return None
    v.keys(raw, _SELECTOR_KEYS, path)
    matches = [k for k in ("name", "code", "name_pattern", "pattern_in_text", "indexed_family", "zone_family") if k in raw]
    if "code" in raw and "name" in raw:
        matches = [k for k in matches if k != "name"]       # a code with its expected name is one match
    if len(matches) != 1:
        v.add(path, IssueCode.INVALID_SELECTOR, "a selector needs exactly one of name, code (+name), name_pattern, pattern_in_text, indexed_family, zone_family")
        return None
    kind = matches[0]
    out: dict[str, Any] = {}
    if kind in ("name", "code"):
        for key in ("name", "code"):
            if key in raw:
                if not isinstance(raw[key], str) or not raw[key].strip():
                    v.add(f"{path}.{key}", IssueCode.INVALID_SELECTOR, f"{key} must be a non-empty string")
                    return None
                out[key] = raw[key]
        if "name" in out:
            _check_template(v, f"{path}.name", out["name"], variables, zones)
    elif kind in ("name_pattern", "pattern_in_text"):
        if not v.regex(raw[kind], f"{path}.{kind}", groups=1 if kind == "pattern_in_text" else 0):
            return None
        out[kind] = raw[kind]
    elif kind == "indexed_family":
        out["family"] = _indexed_family(v, raw["indexed_family"], f"{path}.indexed_family", zones, scoped)
        if out["family"] is None:
            return None
    else:
        if scoped:
            v.add(path, IssueCode.INVALID_SELECTOR, "a zone_family selector reads across zones; use it in a document-scope mapping")
            return None
        out["family"] = _zone_family(v, raw["zone_family"], f"{path}.zone_family", zones)
        if out["family"] is None:
            return None
    if raw.get("section") is not None:
        if isinstance(raw["section"], str) and raw["section"]:
            out["section"] = raw["section"]
        else:
            v.add(f"{path}.section", IssueCode.INVALID_SELECTOR, "section must be a non-empty string")
    stype = raw.get("type", "number" if param is not None and param.data_type == "number" else "text")
    if stype not in ("number", "text"):
        v.add(f"{path}.type", IssueCode.MALFORMED, "type must be 'number' or 'text'")
        stype = "text"
    unit = raw.get("unit", param.unit if param is not None and stype == "number" else "")
    if not isinstance(unit, str) or not is_known_unit(unit):
        v.add(f"{path}.unit", IssueCode.INVALID_UNIT, f"unknown source unit {unit!r}")
        unit = ""
    printed = _printed_unit(v, raw.get("printed_unit"), f"{path}.printed_unit")
    validation = _validation(v, raw.get("validate"), f"{path}.validate")
    allowed = raw.get("allowed_text", [])
    if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
        v.add(f"{path}.allowed_text", IssueCode.MALFORMED, "allowed_text must be a list of strings")
        allowed = []
    return Selector(type=stype, unit=unit, printed_unit=printed, validate=validation, allowed_text=tuple(allowed),
                    note=str(raw.get("note") or ""), **out)


def _check_template(v: _Validator, path: str, text: str, allowed: set[str], zones: ZoneModel | None) -> None:
    for var in _TEMPLATE.findall(text):
        if var not in allowed:
            v.add(path, IssueCode.INVALID_SELECTOR, f"template variable {{{var}}} is not available here (allowed: {sorted(allowed) or 'none'})")
        elif var in ("n", "nn") and zones is not None and zones.mode != "discover":
            v.add(path, IssueCode.INVALID_SELECTOR, f"{{{var}}} needs discovered zones; this catalog lists its zones, use {{zone}}")
        elif var == "key" and zones is not None and zones.mode == "discover":
            v.add(path, IssueCode.INVALID_SELECTOR, "{key} needs listed zones; this catalog discovers its zones, use {n} / {nn}")


def _indexed_family(v: _Validator, raw: Any, path: str, zones: ZoneModel | None, scoped: bool) -> Family | None:
    if not isinstance(raw, dict) or not {"index", "member"} <= set(raw):
        v.add(path, IssueCode.INVALID_SELECTOR, "indexed_family needs an index and a member")
        return None
    v.keys(raw, _FAMILY_KEYS, path)
    idx = raw["index"]
    if not isinstance(idx, dict) or not {"name_pattern", "value_pattern"} <= set(idx):
        v.add(f"{path}.index", IssueCode.INVALID_SELECTOR, "index needs name_pattern (with group n) and value_pattern")
        return None
    v.keys(idx, _INDEX_KEYS, f"{path}.index")
    ok = v.regex(idx["name_pattern"], f"{path}.index.name_pattern", named="n")
    ok = v.regex(idx["value_pattern"], f"{path}.index.value_pattern") and ok
    flt = idx.get("filter")
    f_name = f_equals = None
    if flt is not None:
        if not isinstance(flt, dict) or set(flt) != {"name", "equals"}:
            v.add(f"{path}.index.filter", IssueCode.INVALID_SELECTOR, "filter needs name and equals")
            ok = False
        else:
            f_name, f_equals = flt["name"], flt["equals"]
            _check_template(v, f"{path}.index.filter.name", f_name, _FAMILY_VARS, None)
    member = raw["member"]
    if not isinstance(member, str) or "{n}" not in member:
        v.add(f"{path}.member", IssueCode.INVALID_SELECTOR, "member must be a name template containing {n}")
        ok = False
    else:
        _check_template(v, f"{path}.member", member, _FAMILY_VARS, None)
    agg = raw.get("aggregate", "all_equal")
    if agg not in _AGGREGATES:
        v.add(f"{path}.aggregate", IssueCode.INVALID_SELECTOR, f"aggregate must be one of {list(_AGGREGATES)}")
        ok = False
    count = raw.get("expected_count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 1):
        v.add(f"{path}.expected_count", IssueCode.INVALID_SELECTOR, "expected_count must be a positive integer")
        ok = False
    return Family("indexed", member, FamilyIndex(idx["name_pattern"], idx["value_pattern"], f_name, f_equals), count, agg) if ok else None


def _zone_family(v: _Validator, raw: Any, path: str, zones: ZoneModel | None) -> Family | None:
    if not isinstance(raw, dict) or "member" not in raw:
        v.add(path, IssueCode.INVALID_SELECTOR, "zone_family needs a member")
        return None
    v.keys(raw, _ZONE_FAMILY_KEYS, path)
    ok = True
    member = raw["member"]
    if not isinstance(member, str):
        v.add(f"{path}.member", IssueCode.INVALID_SELECTOR, "member must be a name template")
        return None
    _check_template(v, f"{path}.member", member, _ZONE_VARS, zones)
    where = raw.get("where")
    w_canon = w_equals = None
    if where is not None:
        if not isinstance(where, dict) or set(where) != {"canonical", "equals"}:
            v.add(f"{path}.where", IssueCode.INVALID_SELECTOR, "where needs canonical and equals")
            ok = False
        else:
            w_canon, w_equals = where["canonical"], where["equals"]
            target = v.registry.get(w_canon)
            if target is None or target.scope != "zone":
                v.add(f"{path}.where.canonical", IssueCode.UNKNOWN_CANONICAL, f"{w_canon!r} is not a zone-scope canonical parameter")
                ok = False
    agg = raw.get("aggregate", "all_equal")
    if agg not in _AGGREGATES:
        v.add(f"{path}.aggregate", IssueCode.INVALID_SELECTOR, f"aggregate must be one of {list(_AGGREGATES)}")
        ok = False
    min_count = raw.get("min_count", 1)
    if not isinstance(min_count, int) or isinstance(min_count, bool) or min_count < 0:
        v.add(f"{path}.min_count", IssueCode.INVALID_SELECTOR, "min_count must be a non-negative integer")
        ok = False
    return Family("zone", member, None, None, agg, w_canon, w_equals, min_count) if ok else None


def _printed_unit(v: _Validator, raw: Any, path: str) -> PrintedUnitRule:
    if raw is None:
        return PrintedUnitRule()
    if not isinstance(raw, dict):
        v.add(path, IssueCode.MALFORMED, "printed_unit must be an object")
        return PrintedUnitRule()
    v.keys(raw, _PRINTED_KEYS, path)
    policy = raw.get("policy", "if_printed")
    if policy not in ("if_printed", "required", "none", "ignore"):
        v.add(f"{path}.policy", IssueCode.MALFORMED, "policy must be if_printed, required, none or ignore")
        policy = "if_printed"
    accept = raw.get("accept", [])
    if not isinstance(accept, list) or not all(isinstance(x, str) for x in accept):
        v.add(f"{path}.accept", IssueCode.MALFORMED, "accept must be a list of strings")
        accept = []
    conditional: list[ConditionalText] = []
    for k, item in enumerate(raw.get("accept_if", [])):
        if not isinstance(item, dict) or set(item) != {"text", "when"} or not isinstance(item["when"], dict) or set(item["when"]) != {"canonical", "equals"}:
            v.add(f"{path}.accept_if[{k}]", IssueCode.MALFORMED, "accept_if items need 'text' and 'when' {canonical, equals}")
            continue
        target = v.registry.get(item["when"]["canonical"])
        if target is None or target.scope != "document":
            v.add(f"{path}.accept_if[{k}]", IssueCode.INVALID_REFERENCE, "the condition must name a document-scope canonical parameter")
            continue
        conditional.append(ConditionalText(item["text"], item["when"]["canonical"], item["when"]["equals"]))
    return PrintedUnitRule(policy, tuple(accept), tuple(conditional), bool(raw.get("missing_when_unprinted", False)))


def _validation(v: _Validator, raw: Any, path: str) -> Validation:
    if raw is None:
        return Validation()
    if not isinstance(raw, dict):
        v.add(path, IssueCode.MALFORMED, "validate must be an object")
        return Validation()
    v.keys(raw, _VALIDATE_KEYS, path)
    within = raw.get("within_printed_range", True)
    if not isinstance(within, bool):
        v.add(f"{path}.within_printed_range", IssueCode.MALFORMED, "must be true or false")
        within = True
    allowed = raw.get("allowed_values", [])
    if not isinstance(allowed, list) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in allowed):
        v.add(f"{path}.allowed_values", IssueCode.MALFORMED, "allowed_values must be a list of numbers")
        allowed = []
    pattern = raw.get("printed_range_pattern")
    if pattern is not None:
        v.regex(pattern, f"{path}.printed_range_pattern")
    return Validation(within, tuple(float(x) for x in allowed), pattern)


def _steps(v: _Validator, raw: Any, path: str) -> list[Step]:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[Step] = []
    for k, item in enumerate(items):
        where = f"{path}.transform[{k}]"
        if not isinstance(item, dict) or "type" not in item:
            v.add(where, IssueCode.INVALID_TRANSFORM, "a transform step needs a 'type'")
            continue
        primitive = PRIMITIVES.get(item["type"])
        if primitive is None:
            v.add(where, IssueCode.UNSUPPORTED_TRANSFORM,
                  f"unsupported transformation {item['type']!r}; supported: {sorted(PRIMITIVES)}")
            continue
        params = {k2: val for k2, val in item.items() if k2 not in ("type", "describe")}
        for problem in check_params(primitive, params):
            v.add(where, IssueCode.INVALID_TRANSFORM, problem)
        describe = item.get("describe")
        if describe is not None:
            if not isinstance(describe, str):
                v.add(f"{where}.describe", IssueCode.INVALID_TRANSFORM, "describe must be a string")
                describe = None
            else:
                bad = set(_TEMPLATE.findall(describe)) - {"raw", "input", "result"}
                if bad:
                    v.add(f"{where}.describe", IssueCode.INVALID_TRANSFORM, f"unknown placeholder(s) {sorted(bad)}; use {{raw}}, {{input}}, {{result}}")
        out.append(Step(item["type"], params, describe))
    return out


def _gates(v, raw, path, variables, zones, scoped, param) -> list[Gate]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        v.add(f"{path}.requires", IssueCode.MALFORMED, "requires must be a list of gates")
        return []
    out = []
    for k, g in enumerate(raw):
        where = f"{path}.requires[{k}]"
        if not isinstance(g, dict) or not {"source", "equals"} <= set(g):
            v.add(where, IssueCode.MALFORMED, "a gate needs a source and equals")
            continue
        v.keys(g, _GATE_KEYS, where)
        sel = _selector(v, {**g["source"], "type": "text"} if isinstance(g["source"], dict) else g["source"], f"{where}.source", variables, zones, scoped, param)
        equals = g["equals"] if isinstance(g["equals"], list) else [g["equals"]]
        if sel is not None and equals and all(isinstance(x, str) for x in equals):
            out.append(Gate(sel, tuple(equals), str(g.get("off_note") or ""), str(g.get("missing_note") or "")))
        elif sel is not None:
            v.add(where, IssueCode.MALFORMED, "equals must be a string or a list of strings")
    return out


# ---------------------------------------------------------------------------
# Type checking of a mapping's chain
# ---------------------------------------------------------------------------

_CANONICAL_TYPE = {"number": "number", "text": "text", "boolean": "boolean", "enum": "value", "impedance": "impedance"}


def _literal_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def _check_chain(v: _Validator, path: str, param: CanonicalParameter, source: Selector | None,
                 sources: list[tuple[str, Selector]], steps: list[Step], gap: Gap | None) -> None:
    if gap is not None:
        if source or sources or steps:
            v.add(path, IssueCode.MALFORMED, "a gap declares an unrepresentable source; it takes no source or transform")
        return
    first = PRIMITIVES.get(steps[0].type) if steps else None
    if first is None and steps:
        return                                                  # unsupported primitive already reported
    if not steps:
        if source is None:
            v.add(path, IssueCode.MALFORMED, "a mapping needs a source, sources, a constant transform or a gap")
            return
        current = source.type if source.family is None else "number" if source.type == "number" else "text"
        if param.data_type in ("enum", "boolean"):
            v.add(path, IssueCode.INVALID_TRANSFORM, f"a {param.data_type} parameter needs a transform that maps the source text to a canonical value")
            return
    else:
        if first.inputs == "many":
            if not sources:
                v.add(path, IssueCode.MALFORMED, f"'{first.name}' needs named 'sources'")
                return
            names = {n for n, _ in sources}
            needed = set(first.input_names)
            if first.name == "decision_table":
                for rule in steps[0].params.get("rules", []) if isinstance(steps[0].params.get("rules"), list) else []:
                    if isinstance(rule, dict) and isinstance(rule.get("when"), dict):
                        needed |= set(rule["when"])
            if not needed <= names:
                v.add(path, IssueCode.INVALID_TRANSFORM, f"'{first.name}' needs input(s) {sorted(needed - names)} in 'sources'")
            current = first.out_type
        elif first.inputs == "none":
            if source or sources:
                v.add(path, IssueCode.MALFORMED, f"'{first.name}' takes no source")
            current = first.out_type
        else:
            if source is None:
                v.add(path, IssueCode.MALFORMED, f"'{first.name}' needs a 'source'")
                return
            current = source.type
        if first.inputs == "one" and first.in_type not in ("any", current):
            v.add(path, IssueCode.INVALID_TRANSFORM, f"'{first.name}' reads {first.in_type} but the source is {current}")
        if first.inputs != "one":
            current = _step_out(first, steps[0], current)
        else:
            current = _step_out(first, steps[0], current)
        for k, step in enumerate(steps[1:], start=1):
            p = PRIMITIVES.get(step.type)
            if p is None:
                return
            if p.inputs != "one":
                v.add(f"{path}.transform[{k}]", IssueCode.INVALID_TRANSFORM, f"'{p.name}' takes its own inputs and can only be the first step")
                return
            if p.in_type not in ("any", current) and not (p.in_type == "text" and current == "value"):
                v.add(f"{path}.transform[{k}]", IssueCode.INVALID_TRANSFORM, f"'{p.name}' reads {p.in_type} but the previous step gives {current}")
            current = _step_out(p, step, current)
    wanted = _CANONICAL_TYPE[param.data_type]
    if current != "value" and current != wanted and not (wanted == "value" and current == "text"):
        v.add(path, IssueCode.INVALID_TRANSFORM, f"the mapping produces {current} but {param.id} is {param.data_type}")
    _check_literals(v, path, param, steps)


def _step_out(p, step: Step, current: str) -> str:
    if p.name == "regex" and step.params.get("as") == "number":
        return "number"
    if p.out_type == "same":
        return current
    if p.name == "constant":
        return _literal_type(step.params.get("value"))
    return p.out_type


def _check_literals(v: _Validator, path: str, param: CanonicalParameter, steps: list[Step]) -> None:
    """Every literal a step can produce (enum map values, constants, decision-table results) must be
    a legal value of the canonical parameter: a member of its enum, or of its type."""
    allowed = param.enum_values()
    for k, step in enumerate(steps):
        values: list[Any] = []
        if step.type == "enum" and isinstance(step.params.get("map"), dict):
            values = list(step.params["map"].values())
        elif step.type == "constant":
            values = [step.params.get("value")]
        elif step.type == "decision_table" and isinstance(step.params.get("rules"), list):
            values = [r.get("value") for r in step.params["rules"] if isinstance(r, dict)]
            if "default" in step.params:
                values.append(step.params["default"])
        for value in values:
            if param.data_type == "enum":
                if value not in allowed:
                    v.add(f"{path}.transform[{k}]", IssueCode.INVALID_ENUM,
                          f"{value!r} is not a {param.enum_type} value (allowed: {sorted(allowed)})")
            elif _literal_type(value) != _CANONICAL_TYPE[param.data_type]:
                v.add(f"{path}.transform[{k}]", IssueCode.INVALID_TRANSFORM,
                      f"{value!r} is a {_literal_type(value)} but {param.id} is {param.data_type}")


def _check_units(v: _Validator, path: str, param: CanonicalParameter, source: Selector | None,
                 sources: list[tuple[str, Selector]], steps: list[Step]) -> None:
    explicit = any(s.type == "unit_conversion" for s in steps)
    first = steps[0].type if steps and PRIMITIVES.get(steps[0].type) and PRIMITIVES[steps[0].type].inputs == "many" else None
    selectors = ([("value", "source", source)] if source else []) + [(n, f"sources.{n}", s) for n, s in sources]
    for input_name, name, sel in selectors:
        if sel.type != "number":
            continue
        target = expected_unit(first, input_name, param.unit, explicit)
        if target is None:
            continue
        if sel.unit != target and (conversion_factor(sel.unit, target) is None or not sel.unit):
            v.add(f"{path}.{name}", IssueCode.INVALID_UNIT,
                  f"the source is in {sel.unit or 'no unit'} but {param.id} needs {target or 'a dimensionless value'}, "
                  "and no conversion between them exists")


# ---------------------------------------------------------------------------
# Whole-catalog checks
# ---------------------------------------------------------------------------


def _rank(m: Mapping) -> tuple[int, int]:
    return AUTHORITY_PRECEDENCE[m.authority], VALUE_SOURCE_PRECEDENCE.index(m.value_source)


def _stage(m: Mapping, registry: CanonicalRegistry | None = None) -> int:
    selectors = [m.source, *(s for _, s in m.sources), *m.evidence, *(g.source for g in m.gates),
                 *(m.gap.evidence if m.gap else ())]
    if any(s is not None and s.family is not None and s.family.kind == "zone" for s in selectors):
        return 2
    return 1 if m.zones else 0


def _with_stage(m: Mapping) -> Mapping:
    from dataclasses import replace

    return replace(m, stage=_stage(m))


def _cross_checks(v: _Validator, mappings: list[Mapping], zones: ZoneModel | None) -> None:
    # duplicate / conflicting targets
    by_target: dict[tuple[str, str], list[Mapping]] = {}
    for m in mappings:
        for zid in m.zones or ("",):
            by_target.setdefault((m.canonical, zid), []).append(m)
    reported: set[frozenset[str]] = set()
    for (canonical, zid), group in by_target.items():
        wild = by_target.get((canonical, "*"), []) if zid != "*" and zid != "" else []
        for i, a in enumerate(group + wild):
            for b in (group + wild)[i + 1:]:
                if a.id == b.id or frozenset({a.id, b.id}) in reported:
                    continue
                reported.add(frozenset({a.id, b.id}))
                if _rank(a) == _rank(b):
                    same = a.source == b.source and a.sources == b.sources and a.steps == b.steps
                    v.add(f"mappings[{b.id}]", IssueCode.DUPLICATE if same else IssueCode.CONFLICT,
                          f"{'duplicates' if same else 'conflicts with'} mapping {a.id!r}: both map {canonical} for "
                          f"{'zone ' + zid if zid else 'the document'} at the same precedence {_rank(a)}")
    # compensation kinds must agree within a zone target
    kinds: dict[str, set[str]] = {}
    for m in mappings:
        param = v.registry.get(m.canonical)
        if param is not None and param.compensation_kind:
            for zid in m.zones:
                kinds.setdefault(zid, set()).add(param.compensation_kind)
    for zid, found in kinds.items():
        if len(found) > 1:
            v.add("mappings", IssueCode.CONFLICT, f"zone {zid!r} mixes residual-compensation kinds {sorted(found)}")
    # references must be available when the mapping runs
    position = {m.id: i for i, m in enumerate(mappings)}
    first_for: dict[str, Mapping] = {}
    for m in mappings:
        first_for.setdefault(m.canonical, m)

    def check_ref(m: Mapping, canonical: str, what: str) -> None:
        target = first_for.get(canonical)
        if target is None:
            v.add(f"mappings[{m.id}]", IssueCode.INVALID_REFERENCE, f"{what} {canonical!r}, which this catalog does not map")
            return
        t_stage, m_stage = _stage(target), _stage(m)
        if t_stage > m_stage or (t_stage == m_stage and position[target.id] > position[m.id]):
            v.add(f"mappings[{m.id}]", IssueCode.INVALID_REFERENCE,
                  f"{what} {canonical!r}, which is mapped by {target.id!r} after (or later in the order than) this mapping")

    for m in mappings:
        for cid in (*m.evidence_from, *m.requires_resolved):
            check_ref(m, cid, "depends on")
        selectors = [m.source, *(s for _, s in m.sources), *m.evidence, *(g.source for g in m.gates)]
        for s in selectors:
            if s is None:
                continue
            for rule in s.printed_unit.accept_if:
                check_ref(m, rule.canonical, "accepts a printed unit depending on")
            if s.family is not None and s.family.kind == "zone" and s.family.where_canonical:
                check_ref(m, s.family.where_canonical, "selects zones by")
