"""Catalog-first interpretation: the catalog is authoritative for the canonical targets it maps.

A relay can be described entirely by a catalog (nothing else runs), or by a catalog **plus an extension
profile** that still owns the semantics the catalog schema cannot yet express (note-derived zone states,
residual-compensation vectors...). Precedence for every canonical value, per zone:

1. the active, validated catalog mapping -- authoritative, **even when it does not resolve**. A catalog
   target that is Missing / Conflict / Unreadable / Unsupported stays so; the extension's reading of the
   same field is discarded, never used as a fallback (no guessed profile logic behind a catalog's back);
2. the extension profile, for targets the catalog does not map at all;
3. unresolved / unmapped (the raw setting is retained as "Not interpreted").

``overlay`` therefore replaces, never merges: for each target the catalog resolved or declared, the
catalog's value (with its catalog id / version / canonical id / transformation / authority) is written over
whatever the extension produced. Nothing relay-specific lives here.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from typing import Any

from app.domain.parameter_catalog.interpreter import CatalogRun, set_path
from app.domain.parameter_catalog.registry import CanonicalRegistry
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel, UnresolvedSetting
from app.domain.relay_import.raw_document import RawRelayDocument


def _drop_extra(obj: Any, path: list[str], name: str) -> Any:
    """``obj`` without the ExtraQuantity called ``name`` at ``path`` (so a catalog value replaces it)."""
    head, rest = path[0], path[1:]
    if not is_dataclass(obj) or head not in {f.name for f in fields(obj)}:
        return obj
    current = getattr(obj, head)
    if rest:
        return replace(obj, **{head: _drop_extra(current, rest, name)})
    return replace(obj, **{head: tuple(e for e in current if getattr(e, "name", None) != name)})


def overlay(
    base: CanonicalDistanceProtectionModel, run: CatalogRun, registry: CanonicalRegistry, document: RawRelayDocument,
    profile_version: str,
) -> CanonicalDistanceProtectionModel:
    """``base`` (the extension's model) with every catalog-owned target replaced by the catalog's own."""
    holder: dict[str, Any] = {"metadata": base.metadata, "transformers": base.transformers, "line": base.line}
    zones = {z.zone_id: z for z in base.zones}
    catalog_zones = {z.zone_id: z for z in run.model.zones}
    notes: list[str] = []
    order = {p.id: p.order for p in registry.parameters}
    for (canonical, zone_id), outcome in sorted(run.outcomes.items(), key=lambda kv: (order.get(kv[0][0], 0), kv[0][1])):
        param = registry.get(canonical)
        if param is None:
            continue
        result = outcome.result
        if param.scope == "document":
            _write(holder, param, result)
            continue
        zone = zones.get(zone_id)
        if zone is None:
            notes.append(f"zone {zone_id}: the catalog maps {param.id}, but the profile found no such zone")
            continue
        zone_holder = {"zone": zone}
        if param.compensation_kind:
            # residual compensation is one composite value: take the catalog's whole vector
            source = catalog_zones.get(zone_id)
            if source is not None and source.compensation is not None:
                zone_holder["zone"] = replace(zone, compensation=source.compensation)
        else:
            _write(zone_holder, param, result)
        zones[zone_id] = zone_holder["zone"]
    merged = replace(
        base, metadata=holder["metadata"], transformers=holder["transformers"], line=holder["line"],
        zones=tuple(zones[z.zone_id] for z in base.zones),
        # the extension's narrative stays the relay's (the catalog's own notes describe a catalog-only
        # relay; per-value notes travel in each value's provenance)
        interpretation_notes=tuple(dict.fromkeys((*base.interpretation_notes, *notes))),
    )
    return _retain_unaccounted(merged, base, run, document, profile_version)


def _write(holder: dict[str, Any], param, result) -> None:
    if param.extra_name:
        segments = (param.model_path or "").split(".")
        root, rest = ("zone", segments) if (param.engine_path or "").startswith("zones[]") else (segments[0], segments[1:])
        holder[root] = _drop_extra(holder[root], rest, param.extra_name)
    set_path(holder, param, result)


def _retain_unaccounted(
    merged: CanonicalDistanceProtectionModel, base: CanonicalDistanceProtectionModel, run: CatalogRun,
    document: RawRelayDocument, profile_version: str,
) -> CanonicalDistanceProtectionModel:
    """Nothing is silently dropped. A setting the extension read for a value the catalog now owns may no
    longer be cited by any value: it is kept as a distance-related "Not interpreted" setting. A setting the
    extension left unmapped but a catalog value now cites is no longer unmapped."""
    cited = replace(merged, unmapped_settings=()).referenced_setting_ids()
    unmapped = [u for u in base.unmapped_settings if u.setting_id not in cited]
    kept = {u.setting_id for u in unmapped}
    lost = base.referenced_setting_ids() - cited - kept
    raw = {s.setting_id: s for s in document.settings}
    for setting_id in sorted(lost):
        s = raw.get(setting_id)
        unmapped.append(UnresolvedSetting(
            setting_id, s.name if s else None, s.raw_value if s else None, s.unit if s else None,
            reason=f"distance-related setting not interpreted by {profile_version}: the catalog now owns the value it fed",
        ))
    return replace(merged, unmapped_settings=tuple(unmapped))
