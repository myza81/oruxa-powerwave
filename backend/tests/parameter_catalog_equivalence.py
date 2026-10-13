"""Compare a hand-written profile's canonical model with a catalog's, field by field.

The catalog is the *new* source of relay meaning; the hand-written profile is the proven one. For
every canonical parameter the catalog maps, the two models must carry the same value, the same
interpretation status, the same unresolved cause and (optionally) the same cited source settings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.loader import canonical_registry
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.provenance import Sourced


def review_path(param, zone_id: str | None) -> str | None:
    """The `iter_sourced` path of a canonical parameter in a model."""
    path = param.engine_path
    if not path:
        return None
    if zone_id is not None:
        path = path.replace("zones[]", f"zones[{zone_id}]", 1)
    if param.extra_name:
        base = path.split("{")[0]
        return f"{base}[{param.extra_name}].value"
    return path


def sourced_map(model: CanonicalDistanceProtectionModel) -> dict[str, Sourced]:
    return dict(model.iter_sourced())


def same_value(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


@dataclass(frozen=True)
class Difference:
    path: str
    what: str
    profile: Any
    catalog: Any

    def __str__(self) -> str:
        return f"{self.path}: {self.what}: profile={self.profile!r} catalog={self.catalog!r}"


def differences(
    profile_model: CanonicalDistanceProtectionModel,
    catalog_model: CanonicalDistanceProtectionModel,
    catalog: Catalog,
    *,
    sources: bool = False,
    raw: bool = False,
) -> tuple[list[Difference], int]:
    """(differences, number of Sourced fields compared) over every canonical parameter the catalog maps."""
    reg = canonical_registry()
    p_map, c_map = sourced_map(profile_model), sourced_map(catalog_model)
    zone_ids = [z.zone_id for z in profile_model.zones]
    out: list[Difference] = []
    compared = 0
    for canonical in dict.fromkeys(m.canonical for m in catalog.mappings):
        param = reg.get(canonical)
        assert param is not None
        # only the zones the catalog actually maps this parameter for (the rest stays the profile's)
        mapped_zones = {z for m in catalog.mappings if m.canonical == canonical for z in m.zones}
        targets = [None] if param.scope == "document" else [z for z in zone_ids if "*" in mapped_zones or z in mapped_zones]
        for zid in targets:
            if param.plain:
                for z_p, z_c in zip(profile_model.zones, catalog_model.zones):
                    if z_p.zone_id == zid:
                        compared += 1
                        if z_p.characteristic.geometry_mode != z_c.characteristic.geometry_mode:
                            out.append(Difference(f"zones[{zid}].geometry_mode", "value", z_p.characteristic.geometry_mode, z_c.characteristic.geometry_mode))
                continue
            path = review_path(param, zid)
            p, c = p_map.get(path), c_map.get(path)
            if p is None and c is None:
                continue
            assert p is not None and c is not None, f"{path}: present in only one model"
            compared += 1
            if not same_value(p.value, c.value):
                out.append(Difference(path, "value", p.value, c.value))
            if p.provenance.status != c.provenance.status:
                out.append(Difference(path, "status", p.provenance.status, c.provenance.status))
            if p.provenance.cause != c.provenance.cause:
                out.append(Difference(path, "cause", p.provenance.cause, c.provenance.cause))
            if sources and {s.setting_id for s in p.provenance.sources} != {s.setting_id for s in c.provenance.sources}:
                out.append(Difference(path, "sources", sorted(s.setting_id for s in p.provenance.sources), sorted(s.setting_id for s in c.provenance.sources)))
            if raw and p.provenance.raw_value != c.provenance.raw_value:
                out.append(Difference(path, "raw value", p.provenance.raw_value, c.provenance.raw_value))
    return out, compared
