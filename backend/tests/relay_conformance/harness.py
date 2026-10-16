"""The generic relay conformance harness: observe one relay sheet end to end and compare it with its expectation.

``observe`` runs a sheet through the real upload API (extraction -> identification -> catalog interpretation ->
review), validates it twice through the real API (no decisions; then every assumption confirmed and every offered
suggestion accepted) and tries Apply with the reviewed decisions. The engine adapter's reason *codes* (not its wording)
are read in-process from the same interpretation the upload service uses. The result is a compact, engineering-semantic
record -- identity, counts, readiness, zone inventory, every canonical value (text and category), preserved zone
settings, blockers, offers, approximations and the Apply outcome -- with no notes, provenance prose or volatile ids.

Expectation (``"schema": "oruxa.relay-expectation/1"``) = such a record plus ``sample``:

    {"kind": "synthetic", "sheet": "<sheet id>", "overrides": {...}}   a sheet from ``sheets/``
    {"kind": "real", "file": "<name>.pdf"}                            an owner sheet in RELAY_SAMPLE_PDF_DIR

Every top-level key an expectation states is compared exactly (a real-sheet expectation may state fewer keys, and
``values`` may be marked ``"values_mode": "subset"``). ``golden`` is reserved for Phase 1 (V1 vs V2 geometry: golden
points / outlines) and is not compared yet. Nothing here knows a relay family.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from app.relay_profiles.identification_catalogue import default_registry
from app.services.relay_interpretation_summary import engine_adaptation, summarize_interpretation
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import sheet_pdf

EXPECTATIONS_DIR = Path(__file__).resolve().parent / "expectations"
SCHEMA = "oruxa.relay-expectation/1"
UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"

#: The review counters an expectation freezes (the review payload's own ``<name>_count`` fields).
COUNTS = ("mapped", "documented", "assumption", "to_confirm", "missing", "conflict", "unsupported", "unverified",
          "not_exposed", "unreadable", "approximate", "blocking", "not_required")
#: Canonical fields whose category decides a zone's geometry classification.
GEOMETRY_FIELDS = ("characteristic.type", "x_reach_ohm", "reach", "resistive_reach.phase_phase", "resistive_reach.reverse",
                   "tilt_deg")
#: Weakest first: the first category present names the zone's geometry classification.
GEOMETRY_ORDER = ("unverified", "unsupported", "missing", "conflict", "unreadable", "approximate", "assumption", "documented")
#: Keys an observation always has; ``golden`` (Phase 1) is never observed.
OBSERVED_KEYS = ("identity", "counts", "readiness", "zones", "engine", "blocking", "values", "provenance", "preserved", "offers",
                 "approximations", "apply", "not_interpreted_distance", "coverage", "catalog_sources_absent",
                 "shadow_geometry")


# --- samples ---------------------------------------------------------------------------------------------------------

def expectation_paths() -> list[Path]:
    return sorted(EXPECTATIONS_DIR.glob("*.json"))


def load_expectation(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema") == SCHEMA, f"{path.name}: not a {SCHEMA} expectation"
    return data


def sample_dir() -> Path | None:
    value = os.environ.get("RELAY_SAMPLE_PDF_DIR")
    return Path(value) if value else None


def sample_pdf(sample: dict[str, Any]) -> bytes | None:
    """The sample's bytes; ``None`` for a real sheet that is not available here (the test is then skipped)."""
    if sample["kind"] == "synthetic":
        return sheet_pdf(sample["sheet"], sample.get("overrides"))
    directory = sample_dir()
    path = directory / sample["file"] if directory else None
    return path.read_bytes() if path and path.exists() else None


# --- observation -------------------------------------------------------------------------------------------------------

def upload(client, pdf: bytes) -> dict[str, Any]:
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def review_ref(review: dict[str, Any]) -> dict[str, Any]:
    return {"validation_token": review["validation_token"], "import_id": review["import_id"]}


def items(review: dict[str, Any]) -> list[tuple[dict, dict]]:
    return [(g, i) for g in review["groups"] for i in g["items"]]


def reviewed_decisions(review: dict[str, Any], manual: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Confirm every assumption and accept every offered suggestion -- what a user can do without typing a value -- plus
    the manual entries an expectation states (``sample.manual``: ``[{"item_id": ..., "value": ...}]``)."""
    confirmed = [i["item_id"] for _, i in items(review)
                 if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"]
    suggested = [i["item_id"] for _, i in items(review) if i["item_id"] and i.get("suggestion")]
    return {**review_ref(review), "confirmed": confirmed, "suggested": suggested, "manual": list(manual or [])}


def engine_reasons(pdf: bytes) -> dict[str, Any]:
    """The engine adapter's verdict on the interpreted model, by reason code (zone ids sorted; "-" = document level)."""
    document = extract_pdf(pdf).document
    if document is None:
        return {"supported": None, "reasons": {}}
    registry = default_registry()
    summary = summarize_interpretation(registry, document, registry.identify(document))
    if summary.model is None:
        return {"supported": None, "reasons": {}}
    adaptation = engine_adaptation(summary.model)
    reasons: dict[str, list[str]] = {}
    for reason in adaptation.reasons:
        zones = reasons.setdefault(reason.code.value, [])
        zone = reason.zone_id or "-"
        if zone not in zones:
            zones.append(zone)
    return {"supported": adaptation.supported, "reasons": {k: sorted(v) for k, v in sorted(reasons.items())}}


def catalog_selectors(catalog) -> list[tuple[Any, Any]]:
    """Every (mapping, plain name selector) a catalog reads: value sources, gates, evidence and gap evidence (patterns
    and families excluded -- they name no single row)."""
    out = []
    for m in catalog.mappings:
        sels = ([m.source] if m.source else []) + [s for _, s in m.sources] + [g.source for g in m.gates] + list(m.evidence)
        sels += list(m.gap.evidence) if m.gap else []
        out += [(m, s) for s in sels if s.family is None and not s.name_pattern and not s.pattern_in_text and (s.name or s.code)]
    return out


def absent_sources(catalog, document) -> list[str]:
    """The catalog's selectors (filled per zone) that find no row in the document -- the interpreter's own matching."""
    from app.domain.parameter_catalog.interpreter import _Run   # the same locate() the interpretation uses
    from app.domain.parameter_catalog.loader import canonical_registry

    run = _Run(catalog, canonical_registry(), document)
    run._zones()
    absent: set[str] = set()
    for m, sel in catalog_selectors(catalog):
        targets = [{}] if not m.zones else [z for z in run.zone_vars if "*" in m.zones or z["zone"] in m.zones]
        for variables in targets:
            read = run.locate(sel, variables)
            if not read.found:
                absent.add(read.name)
    return sorted(absent)


def shadow_geometry(pdf: bytes, catalog_id: str | None, zones: dict[str, Any]) -> dict[str, Any] | None:
    """DEC-199 Phase 2A / 2B, SHADOW ONLY: the catalog's canonical boundaries for this document and, per zone, the V2
    assembly beside the production (V1) classification. ``None`` when the catalog declares no boundary. A zone whose
    catalog declares directional boundaries is assembled only when all of them are derived."""
    if not catalog_id:
        return None
    from app.domain.distance_boundaries import BoundarySide, assemble_zone
    from app.domain.parameter_catalog.interpreter import CatalogInterpreter
    from app.domain.parameter_catalog.loader import canonical_registry, default_store

    catalog = default_store().get(catalog_id)
    if not catalog.boundaries:
        return None
    document = extract_pdf(pdf).document
    run = CatalogInterpreter(catalog, canonical_registry()).shadow_boundaries(document)
    registry = default_registry()
    model = summarize_interpretation(registry, document, registry.identify(document)).model
    out: dict[str, Any] = {"unresolved": [list(u) for u in run.unresolved], "zones": {}}
    directional_specs = [s for s in catalog.boundaries if s.kind == "directional"]

    def sources(b) -> list:
        return [[x.role, " ".join(v for v in (x.code, x.name) if v), x.raw_value, x.unit] for x in b.provenance.sources]

    for zone_id in sorted({b.zone_id for b in run.boundaries}):
        edges = [b for b in run.boundaries if b.zone_id == zone_id]
        rays = [b for b in run.directional if b.zone_id == zone_id]
        declared = [s for s in directional_specs if "*" in s.zones or zone_id in s.zones]
        record: dict[str, Any] = {"production_geometry": zones.get(zone_id, {}).get("geometry"), "edges": {}}
        for b in edges:
            record["edges"][b.side.value] = {
                "r_at_axis": b.r_at_axis, "angle_deg": b.angle_deg, "frame": b.frame.value, "unit": b.unit,
                "fidelity": b.fidelity, "canonical_path": b.provenance.canonical_path,
                "sources": sources(b), "references": list(b.provenance.reference_ids), "equation": b.provenance.equation,
            }
        if declared:
            # DEC-199 Phase 2B: the canonical angle beside the raw OEM value, its convention and the transform
            record["directional"] = {b.retained_side.value: {
                "angle_deg": b.angle_deg, "frame": b.frame.value, "fidelity": b.fidelity, "sources": sources(b),
                "convention": b.provenance.convention, "transform": b.provenance.transform,
                "references": list(b.provenance.reference_ids), "equation": b.provenance.equation,
            } for b in sorted(rays, key=lambda b: b.retained_side.value)}
        zone = model.zone(zone_id) if model else None
        x, tilt, direction = (zone.x_reach_ohm, zone.tilt_deg, zone.direction) if zone else (None, None, None)
        reason = None
        if not (x is not None and x.is_resolved):
            reason = "the reactance limit (X) is not resolved"
        elif tilt is not None and (tilt.is_resolved and tilt.value != 0.0 or not tilt.is_resolved and tilt.provenance.sources):
            reason = "a non-zero or unread top-line tilt is not represented in Phase 2A"
        elif not (direction and direction.is_resolved and str(getattr(direction.value, "value", direction.value)) in ("forward", "reverse")):
            reason = "the zone direction is not forward / reverse"
        elif {e.side for e in edges} != {BoundarySide.RIGHT, BoundarySide.LEFT}:
            reason = "a right and a left boundary are both needed"
        elif len(rays) != len(declared):
            reason = "the directional boundaries are not derived (the catalog declares them for this zone)"
        assembled = None
        if not reason:
            d = str(getattr(direction.value, "value", direction.value))
            try:
                assembled = assemble_zone(zone_id, x_reach_ohm=x.value, direction=d, boundaries=tuple(edges), directional=tuple(rays))
            except ValueError as exc:
                reason = str(exc)
        if reason:
            record.update({"shadow_geometry": "not_assembled", "reason": reason})
        else:
            # "exact": the assembly represents the documented relations exactly (geometry); how each boundary relates to
            # relay behaviour is its own `fidelity` (e.g. static_equivalent)
            record.update({"shadow_geometry": "exact", "direction": d, "top": {"x_reach_ohm": x.value, "canonical_path": f"zones[{zone_id}].x_reach_ohm"},
                           "represented": list(assembled.represented), "not_represented": list(assembled.not_represented)})
        out["zones"][zone_id] = record
    return out


def source_coverage(pdf: bytes, catalog_id: str | None) -> list[str] | None:
    if not catalog_id:
        return None
    from app.domain.parameter_catalog.loader import default_store

    document = extract_pdf(pdf).document
    return absent_sources(default_store().get(catalog_id), document) if document is not None else None


def _zone_of(item_id: str) -> str | None:
    return item_id[len("zones["):item_id.index("]")] if item_id.startswith("zones[") else None


def _field_of(item_id: str) -> str:
    return item_id.split("].", 1)[1] if "]." in item_id else item_id


def _geometry(zone_items: list[dict], state_status: str | None, status_text: str | None) -> str:
    if status_text in ("Disabled / Defeated", "Disabled", "Inactive"):
        return "not_in_service"
    categories = {i["category"] for i in zone_items if i["item_id"] and _field_of(i["item_id"]) in GEOMETRY_FIELDS}
    categories |= {i["category"] for i in zone_items if i["item_id"] is None and i["blocking"]}
    return next((c for c in GEOMETRY_ORDER if c in categories), "exact")


def _apply_zone(z: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "enabled", "direction", "delay_s", "geometry_mode", "characteristic_angle_deg", "reach_ohm",
            "reactive_reach_ohm", "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm")
    return {k: z.get(k) for k in keep if k in z}


def _source_name(source: dict[str, Any]) -> str:
    return " ".join(x for x in (source.get("code"), source.get("name")) if x)


def observe(client, pdf: bytes, manual: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body = upload(client, pdf)
    review = body.get("review")
    identity = {k: body.get(k) for k in ("identification_status", "manufacturer", "relay_family", "model", "profile_id",
                                         "profile_version", "catalog_id", "catalog_version", "confidence",
                                         "interpretation_status", "zone_count")}
    out: dict[str, Any] = {"identity": identity}
    if review is None:
        return out
    out["counts"] = {name: review[f"{name}_count"] for name in COUNTS}
    out["readiness"] = {"initial": review["readiness"]["status"]}

    zones, values, provenance, preserved, blocking = {}, {}, {}, {}, {}
    for g in review["groups"]:
        if g["kind"] == "zone":
            zid = g["id"][len("zone-"):]
            by_field = {_field_of(i["item_id"]): i for i in g["items"] if i["item_id"] and i["primary"]}
            st, dr, ch = by_field.get("status", {}), by_field.get("direction", {}), by_field.get("characteristic.type", {})
            zones[zid] = {
                "name": g["title"],
                "status": [st.get("value_text"), st.get("category")],
                "direction": [dr.get("value_text"), dr.get("category")],
                "characteristic": [ch.get("value_text"), ch.get("category")],
                "geometry": _geometry(g["items"], g.get("state_status"), st.get("value_text")),
            }
        for i in g["items"]:
            if i["item_id"] and i["primary"]:
                values[i["item_id"]] = [i["value_text"], i["category"]]
                cited = {"raw": i["raw_value"], "sources": [_source_name(x) for x in i.get("sources", [])],
                         "references": [r["reference_id"] for r in i.get("references", [])]}
                if cited["raw"] is not None or cited["sources"] or cited["references"]:
                    provenance[i["item_id"]] = {k: v for k, v in cited.items() if v not in (None, [])}
                if i["blocking"]:
                    blocking[i["item_id"]] = i["category"]
            elif i["item_id"] is None and g["kind"] == "zone":
                key = f"{g['id'][len('zone-'):]}/{i['label']}"
                preserved[key] = [i["raw_value"], i["category"], i["blocking"]]
                if i["blocking"]:
                    blocking[f"raw:{key}"] = i["category"]
    out["zones"] = zones
    out["engine"] = engine_reasons(pdf)
    out["blocking"] = dict(sorted(blocking.items()))
    out["values"] = dict(sorted(values.items()))
    out["provenance"] = dict(sorted(provenance.items()))
    out["preserved"] = dict(sorted(preserved.items()))
    out["offers"] = {
        "suggestions": sorted(i["item_id"] for _, i in items(review) if i["item_id"] and i.get("suggestion")),
        "manual_entries": sorted(i["item_id"] for _, i in items(review) if i["item_id"] and i["primary"] and i.get("resolution")),
    }
    decisions = reviewed_decisions(review, manual)
    validated = client.post(VALIDATE, json=decisions)
    out["readiness"]["reviewed"] = validated.json()["readiness"]["status"] if validated.status_code == 200 else validated.status_code
    applied = client.post(APPLY, json=decisions)
    result: dict[str, Any] = {"status": applied.status_code}
    if applied.status_code == 200:
        payload = applied.json()
        result["characteristic"], result["impedance_basis"] = payload.get("characteristic"), payload.get("impedance_basis")
        result["zones"] = [_apply_zone(z) for z in payload["zones"]]
        out["approximations"] = payload.get("approximations", [])
    else:
        out["approximations"] = []
    out["apply"] = result
    out["not_interpreted_distance"] = sorted(
        {u["name"] for u in review.get("not_interpreted", []) if u.get("name")}
    )
    coverage = review.get("catalog_coverage") or body.get("catalog_coverage")
    out["coverage"] = dict(sorted(coverage.items())) if coverage else None
    out["catalog_sources_absent"] = source_coverage(pdf, body.get("catalog_id"))
    out["shadow_geometry"] = shadow_geometry(pdf, body.get("catalog_id"), out["zones"])
    return out


# --- comparison --------------------------------------------------------------------------------------------------------

def differences(expected: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    """Human-readable differences for every key the expectation states (``sample`` / ``golden`` / notes excluded)."""
    out: list[str] = []
    subset = expected.get("values_mode") == "subset"
    for key, want in expected.items():
        if key in ("schema", "sample", "golden", "shadow_golden", "values_mode", "description", "browser", "mutations"):
            continue
        got = observed.get(key)
        if key in ("values", "provenance") and subset:
            for path, value in want.items():
                if got is None or got.get(path) != value:
                    out.append(f"{key}[{path}]: expected {value!r}, got {None if got is None else got.get(path)!r}")
            continue
        if isinstance(want, dict) and isinstance(got, dict):
            for k in sorted(set(want) | set(got)):
                if want.get(k, "<absent>") != got.get(k, "<absent>"):
                    out.append(f"{key}[{k}]: expected {want.get(k, '<absent>')!r}, got {got.get(k, '<absent>')!r}")
        elif want != got:
            out.append(f"{key}: expected {want!r}, got {got!r}")
    return out
