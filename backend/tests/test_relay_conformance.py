"""The generic relay conformance suite (Relay Scalability Phase 0, DEC-199).

One suite for every relay: the shipped catalogs, the synthetic sheets (``tests/relay_conformance/sheets``) and the
expectations (``tests/relay_conformance/expectations``) are the only inputs. Adding a relay adds data -- a catalog, its
references, a sheet spec and an expectation -- and no test code. Nothing here names a relay family.

* catalog integrity: valid, locked, documented derivations cite verified references, every reference cited;
* expectations: review, readiness, engine verdict, offers, approximations and Apply match (owner sheets gated on
  RELAY_SAMPLE_PDF_DIR); readiness and Apply agree; interpretation is deterministic;
* mutations generated from the sheet itself: a blank or malformed configured cell never becomes a value, note edits
  never change a configured value, disabling a zone removes its blockers, a catalog's harmless / geometry-affecting
  preserved values behave as declared;
* review authority per relay: a forged suggestion, a forged manual value and a tampered token are refused (the full
  security suites stay in their own modules).
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

import pytest

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.profile import CatalogProfile
from app.domain.parameter_catalog.loader import (
    CATALOG_ROOT,
    canonical_registry,
    check_lock,
    default_store,
    load_lock,
    validate_catalog_file,
)
from app.relay_profiles.identification_catalogue import build_registry
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.harness import (
    APPLY,
    VALIDATE,
    differences,
    engine_reasons,
    expectation_paths,
    load_expectation,
    observe,
    review_ref,
    reviewed_decisions,
    sample_pdf,
    upload,
)
from app.domain.distance_geometry import TOLERANCE_OHM
from app.domain.distance_geometry_compat import compile_v1_zone
from tests.relay_api_helpers import client  # noqa: F401
from tests.relay_conformance.golden import grid_points, v1_golden, zone_settings
from tests.relay_conformance.shadow_golden import shadow_golden
from tests.relay_conformance.sheet_spec import load_spec, note_lines, sheet_ids, sheet_lines, sheet_pdf

#: Deviations the suite reports but Phase 0 does not fix (tests/relay_conformance/known_findings.json).
FINDINGS = json.loads((Path(__file__).resolve().parent / "relay_conformance" / "known_findings.json").read_text(encoding="utf-8"))
EXPECTATIONS = {p.stem: load_expectation(p) for p in expectation_paths()}
SYNTHETIC = sorted(name for name, e in EXPECTATIONS.items() if e["sample"]["kind"] == "synthetic")
#: One base expectation per sheet (no overrides, no manual entries): the sheet-level mutation and authority suite runs on
#: it; a scenario variant (``<sheet>--<scenario>``) is compared with its expectation only.
BASES = sorted(n for n in SYNTHETIC if not EXPECTATIONS[n]["sample"].get("overrides") and not EXPECTATIONS[n]["sample"].get("manual"))
DISABLED_TEXTS = {"Disabled / Defeated", "Disabled", "Inactive"}
APP_DIR = Path(__file__).resolve().parents[1] / "app"
#: Relays whose catalog interprets them alone (no hand-written extension profile).
CATALOG_ONLY = sorted({e["identity"]["profile_id"] for e in EXPECTATIONS.values()
                       if e["sample"]["kind"] == "synthetic" and e["identity"]["catalog_id"]
                       and type(next(p for p in build_registry()._profiles if p.profile_id == e["identity"]["profile_id"])) is CatalogProfile
                       and next(p for p in build_registry()._profiles if p.profile_id == e["identity"]["profile_id"]).extension is None})


def merged(sample_overrides: dict | None, extra: dict) -> dict:
    """The expectation's own sheet overrides plus a mutation's (``set`` maps merge; the mutation wins)."""
    out = copy.deepcopy(sample_overrides or {})
    for key, value in extra.items():
        if isinstance(value, dict):
            out[key] = {**out.get(key, {}), **value}
        else:
            out[key] = value
    return out


def review_of(client, sheet: str, overrides: dict | None) -> dict:
    return upload(client, sheet_pdf(sheet, overrides))["review"]


def primary_items(review: dict) -> dict[str, dict]:
    return {i["item_id"]: i for g in review["groups"] for i in g["items"] if i["item_id"] and i["primary"]}


def zone_blockers(review: dict, zone: str) -> list[str]:
    out = []
    for g in review["groups"]:
        for i in g["items"]:
            if i["blocking"] and ((i["item_id"] or "").startswith(f"zones[{zone}]") or (i["item_id"] is None and g["id"] == f"zone-{zone}")):
                out.append(i["item_id"] or i["label"])
    return out


_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def line_key(sheet: str, source: dict) -> str | None:
    """The sheet line a review source came from (a line is keyed by its first cell: a code, a name or 'code name')."""
    keys = {line[0] for line in load_spec(sheet)["lines"] if line}
    code, name = source.get("code"), source.get("name")
    for candidate in (code, name, f"{code} {name}" if code and name else None):
        if candidate and candidate in keys:
            return candidate
    return None


def configured_number_rows(sheet: str, review: dict) -> dict[str, str]:
    """item_id -> sheet line key for every configured (Mapped) engineering value read from one numeric cell."""
    out = {}
    for item_id, item in primary_items(review).items():
        if not item_id.startswith(("zones[", "transformers.", "line.")) or item["category"] != "mapped":
            continue
        if len(item["sources"]) != 1 or not _NUMBER.match(str(item["raw_value"] or "")):
            continue
        key = line_key(sheet, item["sources"][0])
        if key is not None:
            out[item_id] = key
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------------------------------------------------

CATALOGS = sorted(default_store().catalogs, key=lambda c: c.key)


class TestCatalogIntegrity:
    def test_every_shipped_catalog_is_valid_and_locked(self):
        store = default_store()
        assert not store.rejected
        assert check_lock(store, load_lock()) == []
        for path in sorted(CATALOG_ROOT.rglob("*.json")):
            if path.name == "catalog.lock.json" or path.parent.name == "canonical":
                continue
            assert validate_catalog_file(path).issues == (), path.name

    @pytest.mark.parametrize("catalog", CATALOGS, ids=lambda c: c.catalog_id)
    def test_documented_derivations_cite_a_verified_reference(self, catalog):
        refs = {r.id: r for r in catalog.references}
        for m in catalog.mappings:
            if m.authority == "documented_derivation" and m.verification == "verified":
                assert any(refs[r].verification == "verified" for r in m.references), m.id

    @pytest.mark.parametrize("catalog", CATALOGS, ids=lambda c: c.catalog_id)
    def test_every_reference_is_cited_and_says_where_it_applies(self, catalog):
        cited = {r for m in catalog.mappings for r in m.references} | {r for b in catalog.boundaries for r in b.references}
        known = set(FINDINGS["uncited_references"].get(catalog.catalog_id, {}).get("ids", []))
        assert {ref.id for ref in catalog.references if ref.id not in cited} == known
        for ref in catalog.references:
            assert ref.document and ref.scope, ref.id

    @pytest.mark.parametrize("catalog", [c for c in CATALOGS if any(m.verification == "verified" for m in c.mappings)],
                             ids=lambda c: c.catalog_id)
    def test_documented_derivations_are_refused_without_a_verified_reference(self, catalog):
        path = next(p for p in CATALOG_ROOT.rglob("*.json") if p.name != "catalog.lock.json"
                    and json.loads(p.read_text(encoding="utf-8")).get("catalog_id") == catalog.catalog_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        for ref in data["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(data, canonical_registry(), source=catalog.catalog_id)
        failing = {i.path for i in exc.value.issues if i.code == IssueCode.UNVERIFIED_REFERENCE}
        assert {f"mappings[{m.id}].verification" for m in catalog.mappings if m.verification == "verified"} <= failing             or len(failing) == sum(1 for m in catalog.mappings if m.verification == "verified")

    @pytest.mark.parametrize("profile_id", CATALOG_ONLY)
    def test_a_catalog_only_relay_has_no_mapping_logic_in_production_python(self, profile_id):
        catalog = next(c for c in CATALOGS if c.profile_id == profile_id)
        token = re.sub(r"[^a-z0-9]", "", catalog.applicability.model.lower())
        hits = sorted(p.relative_to(APP_DIR).as_posix() for p in APP_DIR.rglob("*.py")
                      if token in re.sub(r"[^a-z0-9]", "", p.read_text(encoding="utf-8", errors="ignore").lower()))
        # recognition data only (the identification descriptor), never interpretation logic
        allowed = {"relay_profiles/identification_catalogue.py", *FINDINGS["production_mentions"].get(profile_id, {}).get("files", [])}
        assert set(hits) <= allowed, hits

    def test_every_catalog_and_hand_written_profile_has_a_sheet_and_an_expectation(self):
        covered = {EXPECTATIONS[n]["identity"]["catalog_id"] for n in SYNTHETIC} | {
            EXPECTATIONS[n]["identity"]["profile_id"] for n in SYNTHETIC}
        assert {c.catalog_id for c in CATALOGS} <= covered
        assert {"schneider-micom-p441", "hitachi-red670", "siemens-7sa511"} <= covered
        assert set(sheet_ids()) == {EXPECTATIONS[n]["sample"]["sheet"] for n in SYNTHETIC}


# ---------------------------------------------------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_the_relay_import_matches_its_expectation(client, name):
    expected = EXPECTATIONS[name]
    pdf = sample_pdf(expected["sample"])
    if pdf is None:
        pytest.skip("owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
    assert differences(expected, observe(client, pdf, expected["sample"].get("manual"))) == []


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_every_raw_setting_is_accounted_for(name):
    c = EXPECTATIONS[name]["coverage"]
    if c is None:
        pytest.skip("no catalog (hand-written profile)")
    # every extracted row is the catalog's, an extension profile's (catalog-first relays) or left unmapped -- never lost
    assert c["catalog_recognised_settings"] + c["extension_interpreted_settings"] + c["unmapped_settings"] == c["extracted_settings"]
    if EXPECTATIONS[name]["identity"]["profile_id"] in CATALOG_ONLY:
        assert c["extension_interpreted_settings"] == 0                        # catalog-only: nothing else read


# ---------------------------------------------------------------------------------------------------------------------
# Geometry (DEC-199 Phase 1): V1 stays authoritative; the V2 kernel runs in shadow mode against V1's goldens
# ---------------------------------------------------------------------------------------------------------------------

def compare_v2_with_golden(expectation: dict) -> dict:
    """Compile every zone V1 draws into the V2 kernel and compare membership (grid + probes) and outline with the V1
    golden. Returns counts; any mismatch fails."""
    golden = expectation["golden"]
    apply_zones = {z["id"]: z for z in (expectation["apply"].get("zones") or [])}
    counts = {"zones": 0, "points": 0, "skipped_near_boundary": 0}
    for zg in golden["zones"]:
        v2 = compile_v1_zone(zg["characteristic"], zone_settings(apply_zones[zg["id"]]))
        assert v2 is not None, zg["id"]
        for r, x, flag in grid_points(zg["grid"]):
            if flag == ".":
                counts["skipped_near_boundary"] += 1
                continue
            assert v2.contains(r, x) is (flag == "1"), (zg["id"], r, x)
            counts["points"] += 1
        for r, x, flag in zg["probes"]:
            assert v2.contains(r, x) is bool(flag), (zg["id"], "probe", r, x)
            counts["points"] += 1
        outline, key = v2.outline(), zg["outline"]
        assert outline.kind == key["kind"], zg["id"]
        if key["kind"] == "circle":
            assert math.hypot(outline.center[0] - key["center"][0], outline.center[1] - key["center"][1]) <= TOLERANCE_OHM
            assert abs(outline.radius - key["radius"]) <= TOLERANCE_OHM
        else:
            assert len(outline.vertices) == len(key["vertices"]) and not outline.clipped, zg["id"]
            for v in key["vertices"]:                      # golden vertices are rounded to 6 decimals: half a unit + tol
                assert min(math.hypot(v[0] - w[0], v[1] - w[1]) for w in outline.vertices) <= 5e-7 + TOLERANCE_OHM, (zg["id"], v)
        counts["zones"] += 1
    for zone_id in golden["not_drawn"]:
        assert compile_v1_zone(expectation["apply"]["characteristic"], zone_settings(apply_zones[zone_id])) is None, zone_id
    return counts


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_the_v1_geometry_matches_its_golden(name):
    """V1 (the production engine) recomputed from the expectation's Apply zones gives exactly the stored golden."""
    assert EXPECTATIONS[name]["golden"] == v1_golden(EXPECTATIONS[name]["apply"])


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_the_v2_kernel_reproduces_the_v1_golden(name):
    if not EXPECTATIONS[name]["golden"]["zones"] and not EXPECTATIONS[name]["golden"]["not_drawn"]:
        pytest.skip("V1 draws no zone for this sample (Apply is refused)")
    compare_v2_with_golden(EXPECTATIONS[name])


# ---------------------------------------------------------------------------------------------------------------------
# Shadow canonical boundaries (DEC-199 Phase 2A): OEM geometry V1 cannot draw, against independent engineering goldens
# ---------------------------------------------------------------------------------------------------------------------

SHADOW = sorted(n for n, e in EXPECTATIONS.items() if e.get("shadow_geometry"))


def shadow_zones(expectation: dict, pdf: bytes) -> dict:
    """The live shadow boundaries of a sample, assembled with the V2 kernel (absolute frame), by zone."""
    from app.domain.distance_boundaries import assemble_zone

    catalog = default_store().get(expectation["identity"]["catalog_id"])
    run = CatalogInterpreter(catalog, canonical_registry()).shadow_boundaries(extract_pdf(pdf).document)
    out = {}
    for zone_id, z in expectation["shadow_geometry"]["zones"].items():
        if z.get("shadow_geometry") == "exact":
            edges = tuple(b for b in run.boundaries if b.zone_id == zone_id)
            rays = tuple(b for b in run.directional if b.zone_id == zone_id)
            lower = next((b for b in run.lower if b.zone_id == zone_id), None)
            out[zone_id] = (edges + rays + ((lower,) if lower else ()),
                            assemble_zone(zone_id, x_reach_ohm=z["top"]["x_reach_ohm"], direction=z["direction"],
                                          boundaries=edges, directional=rays, lower=lower))
    return out


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_the_shadow_golden_is_the_documented_equation(name):
    """The stored engineering golden is R(X) = r_at_axis + X / tan(angle) of the recorded boundary (never V2)."""
    assert EXPECTATIONS[name].get("shadow_golden") == shadow_golden(EXPECTATIONS[name].get("shadow_geometry"))


@pytest.mark.parametrize("name", SHADOW)
def test_the_shadow_v2_geometry_reproduces_the_engineering_golden(name):
    e = EXPECTATIONS[name]
    pdf = sample_pdf(e["sample"])
    if pdf is None:
        pytest.skip("owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
    assembled = shadow_zones(e, pdf)
    assert set(assembled) == set(e["shadow_golden"])
    for zone_id, golden in e["shadow_golden"].items():
        boundaries, zone = assembled[zone_id]
        planes = {getattr(b, "side", None) or getattr(b, "retained_side", None) or "lower": b.half_plane(golden["direction"])
                  for b in boundaries}
        for x, r_right, r_left in golden["edge_points"]:               # every golden edge point lies on the V2 edge
            assert abs(planes["right"].signed_distance(r_right, x)) <= TOLERANCE_OHM, (zone_id, x, "right")
            assert abs(planes["left"].signed_distance(r_left, x)) <= TOLERANCE_OHM, (zone_id, x, "left")
        for side, r, x in golden.get("directional_points", ()):         # ... and every golden ray point on the V2 line
            assert abs(planes[side].signed_distance(r, x)) <= TOLERANCE_OHM, (zone_id, side, r, x)
        assert set(golden.get("directional", {})) == {b.retained_side.value for b in boundaries if hasattr(b, "retained_side")}
        for r, x, inside in golden["probes"] + golden.get("directional_probes", []):
            assert zone.characteristic.contains(r, x) is bool(inside), (zone_id, r, x)
        # DEC-199 Phase 2C: the lower limit on its own, then the closed region boundary by boundary
        assert ("lower" in planes) is ("lower" in golden)
        for r, x in golden.get("lower_points", ()):
            assert abs(planes["lower"].signed_distance(r, x)) <= TOLERANCE_OHM, (zone_id, r, x)
        for r, x, above in golden.get("lower_probes", ()):
            assert planes["lower"].contains(r, x) is bool(above), (zone_id, r, x)
        for label, r, x, inside in golden.get("boundary_probes", ()):
            assert zone.characteristic.contains(r, x) is bool(inside), (zone_id, label, r, x)
        if golden.get("closed"):
            outline = zone.characteristic.outline()                     # bounded: no plotting bounds needed
            assert outline.kind == "polygon" and len(outline.vertices) >= 3 and not outline.clipped, zone_id
            labels = {label for label, *_ in golden["boundary_probes"]}
            assert labels == {f"{k}_{b}" for b in golden["active"] for k in ("inside", "beyond")}, zone_id
        # placed once: the assembled zone is absolute, and placing it again changes nothing (no second reflection)
        assert zone.characteristic.to_absolute(golden["direction"]) is zone.characteristic


@pytest.mark.parametrize("name", SHADOW)
def test_a_shadow_zone_is_closed_exactly_when_every_declared_boundary_is_derived(name):
    """DEC-199 Phase 2C: a declared lower limit closes the region; a declared boundary that is not derived (e.g. no
    ArgDir / ArgNegRes on the sheet) or a sector of 180 deg or more leaves the zone unassembled -- never defaulted --
    with its derived boundaries and their provenance kept."""
    for zone_id, z in EXPECTATIONS[name]["shadow_geometry"]["zones"].items():
        rays, lower = z.get("directional"), z.get("lower", "undeclared")
        if z["shadow_geometry"] == "exact":
            assert ("lower" in z["represented"]) is (lower not in (None, "undeclared")), zone_id
            assert z["not_represented"] == ([] if "lower" in z["represented"] else ["lower"]), zone_id
            assert EXPECTATIONS[name]["shadow_golden"][zone_id].get("closed", False) is ("lower" in z["represented"])
            continue
        if rays is not None and len(rays) < 2:
            assert z["reason"].startswith("the directional boundaries are not derived"), zone_id
        elif "sweeps" in z["reason"]:                                   # a union the kernel refuses to stand in for
            assert set(rays) == {"counter_clockwise", "clockwise"} and all(r["sources"] for r in rays.values()), zone_id
            assert zone_id not in (EXPECTATIONS[name]["shadow_golden"] or {})


@pytest.mark.parametrize("name", SHADOW)
def test_geometry_exactness_and_relay_behaviour_fidelity_stay_distinct(name):
    """An assembled zone is the exact documented relation (`exact`); its relay-behaviour fidelity is the weakest of its
    boundaries' (static_equivalent once a voltage-polarised directional line is in it)."""
    order = ("exact", "documented", "static_equivalent")
    for zone_id, z in EXPECTATIONS[name]["shadow_geometry"]["zones"].items():
        if z["shadow_geometry"] != "exact":
            continue
        parts = [*z["edges"].values(), *(z.get("directional") or {}).values(), *([z["lower"]] if z.get("lower") else [])]
        assert z["relay_behaviour_fidelity"] == max((p["fidelity"] for p in parts), key=order.index), zone_id


@pytest.mark.parametrize("name", SHADOW)
def test_the_production_engine_still_holds_no_inclined_edge(name):
    """Shadow geometry never changes production: V1 keeps an inclined edge unresolved (Not yet supported)."""
    e = EXPECTATIONS[name]
    for zone_id, z in e["shadow_geometry"]["zones"].items():
        for side, b in z["edges"].items():
            if b["angle_deg"] != 90.0:
                assert e["values"].get(b["canonical_path"], [None, "unsupported"]) == [None, "unsupported"], (zone_id, side)
        assert z["production_geometry"] != "exact", zone_id


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_readiness_and_apply_agree(name):
    e = EXPECTATIONS[name]
    ready = e["readiness"]["reviewed"] in ("ready", "ready_approximate")
    assert (e["apply"]["status"] == 200) is ready
    assert (e["readiness"]["reviewed"] == "ready_approximate") is bool(e["approximations"])
    if not ready:
        assert e["apply"]["status"] == 409 and e["approximations"] == []


@pytest.mark.parametrize("name", SYNTHETIC)
def test_every_value_carries_its_catalog_provenance(client, name):
    e = EXPECTATIONS[name]
    if e["identity"]["profile_id"] not in CATALOG_ONLY:
        pytest.skip("a hand-written profile (or catalog-first extension) interprets part of this relay")
    review = upload(client, sample_pdf(e["sample"]))["review"]
    for item_id, item in primary_items(review).items():
        if item["value_text"] is not None and item_id.startswith(("zones[", "transformers.", "line.")):
            assert (item["catalog_id"], item["catalog_version"]) == (e["identity"]["catalog_id"], e["identity"]["catalog_version"])
            assert item["canonical_id"] and item["sources"], item_id


@pytest.mark.parametrize("name", SYNTHETIC)
def test_the_apply_payload_is_oem_neutral(client, name):
    e = EXPECTATIONS[name]
    if e["apply"]["status"] != 200:
        pytest.skip("not applicable (Apply is refused for this sheet)")
    review = upload(client, sample_pdf(e["sample"]))["review"]
    payload = json.dumps(client.post(APPLY, json=reviewed_decisions(review, e["sample"].get("manual"))).json())
    for word in (e["identity"]["model"], e["identity"]["profile_id"], e["identity"]["catalog_id"]):
        if word:
            assert word not in payload, word


@pytest.mark.parametrize("name", BASES)
class TestSyntheticSheet:
    def test_interpretation_is_deterministic(self, client, name):
        sample = EXPECTATIONS[name]["sample"]
        a, b = (review_of(client, sample["sheet"], sample.get("overrides")) for _ in range(2))
        for r in (a, b):
            r.pop("validation_token"), r.pop("import_id")
        assert a == b

    def test_a_relay_setting_that_does_not_exist_is_never_missing(self, client, name):
        e = EXPECTATIONS[name]
        catalog_id = e["identity"]["catalog_id"]
        if not catalog_id:
            pytest.skip("no catalog (hand-written profile)")
        pdf = sample_pdf(e["sample"])
        run = CatalogInterpreter(default_store().get(catalog_id), canonical_registry()).run(extract_pdf(pdf).document)
        by_target = {}
        for item_id, item in primary_items(upload(client, pdf)["review"]).items():
            zone = item_id[len("zones["):item_id.index("]")] if item_id.startswith("zones[") else ""
            by_target.setdefault((item.get("canonical_id"), zone), []).append(item)
        for (canonical, zone), outcome in run.outcomes.items():
            if outcome.mapping.not_exposed is not None and not outcome.result.is_resolved:
                for item in by_target.get((canonical, zone), []):
                    assert item["category"] == "not_exposed", (canonical, zone)

    def test_forged_suggestions_manual_values_and_tokens_are_refused(self, client, name):
        sample = EXPECTATIONS[name]["sample"]
        review = review_of(client, sample["sheet"], sample.get("overrides"))
        items = primary_items(review)
        base = {**review_ref(review), "confirmed": [], "suggested": [], "manual": []}
        unoffered = next((p for p, i in items.items() if i["value_text"] is None and not i.get("suggestion")), None)
        if unoffered:
            assert client.post(VALIDATE, json={**base, "suggested": [unoffered]}).status_code == 400
        engine_limit = next((p for p, i in items.items() if i["value_text"] is None
                             and i["category"] in ("unsupported", "unverified", "not_exposed")), None)
        if engine_limit:
            assert client.post(VALIDATE, json={**base, "manual": [{"item_id": engine_limit, "value": 1.0}]}).status_code == 400
        token = review["validation_token"]
        tampered = {**base, "validation_token": token[:-2] + ("AA" if token[-2:] != "AA" else "BB")}
        for url in (VALIDATE, APPLY):
            r = client.post(url, json=tampered)
            assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_review_token"

    # --- mutations generated from the sheet itself ----------------------------------------------------------------

    def test_a_blank_configured_cell_is_missing_never_a_range_or_default(self, client, name):
        sample = EXPECTATIONS[name]["sample"]
        sheet, ov = sample["sheet"], sample.get("overrides")
        rows = configured_number_rows(sheet, review_of(client, sheet, ov))
        unreadable = set(EXPECTATIONS[name].get("mutations", {}).get("blank_cell", {}).get("unreadable", []))
        seen = set()
        for key in sorted(set(rows.values())):
            mutated = primary_items(review_of(client, sheet, merged(ov, {"set": {key: ""}})))
            for item_id in (i for i, k in rows.items() if k == key):
                item = mutated[item_id]
                assert item["value_text"] is None, (key, item_id)                     # never a value, never the range
                if key in unreadable:                                                 # known finding F-1 (data)
                    assert item["category"] == "unreadable", (key, item_id)
                    seen.add(key)
                else:
                    assert (item["raw_value"], item["category"]) == (None, "missing"), (key, item_id)
        assert seen == unreadable, "the frozen blank-cell finding is out of date"

    def test_a_malformed_configured_cell_never_becomes_a_value(self, client, name):
        sample = EXPECTATIONS[name]["sample"]
        sheet, ov = sample["sheet"], sample.get("overrides")
        rows = configured_number_rows(sheet, review_of(client, sheet, ov))
        for key in sorted(set(rows.values())):
            mutated = primary_items(review_of(client, sheet, merged(ov, {"set": {key: "1,2x"}})))
            for item_id in (i for i, k in rows.items() if k == key):
                item = mutated[item_id]
                assert item["value_text"] is None and item["category"] in ("unreadable", "conflict", "unsupported"), (key, item_id)

    def test_editing_the_notes_changes_no_configured_or_documented_value(self, client, name):
        sample = EXPECTATIONS[name]["sample"]
        sheet, ov = sample["sheet"], sample.get("overrides")
        notes = note_lines(sheet, ov)
        if not notes:
            pytest.skip("the sheet has no notes")
        edited = [[re.sub(r"\d+(?:\.\d+)?\s*s\b", "9.99s", c) if c else c for c in line] for line in notes]
        assert edited != notes or not any(re.search(r"\d\s*s\b", c or "") for line in notes for c in line)

        def settled(review):
            return {k: (i["value_text"], i["category"]) for k, i in primary_items(review).items()
                    if i["category"] in ("mapped", "documented")}

        assert settled(review_of(client, sheet, merged(ov, {"notes": edited}))) == settled(review_of(client, sheet, ov))

    def test_disabling_a_zone_removes_its_blockers(self, client, name):
        e = EXPECTATIONS[name]
        mutation = e.get("mutations", {}).get("disable_zone")
        assert mutation is not None, "declare mutations.disable_zone (or its reason) in the expectation"
        if "zone" not in mutation:
            assert mutation.get("reason")
            pytest.skip(mutation["reason"])
        sheet, zone = e["sample"]["sheet"], mutation["zone"]
        overrides = merged(e["sample"].get("overrides"), {"set": mutation["set"]})
        assert zone_blockers(review_of(client, sheet, e["sample"].get("overrides")), zone), "pick a zone that has blockers"
        review = review_of(client, sheet, overrides)
        assert primary_items(review)[f"zones[{zone}].status"]["value_text"] in DISABLED_TEXTS
        assert zone_blockers(review, zone) == mutation.get("residual_blockers", [])     # residual: finding F-2 (data)
        verdict = engine_reasons(sheet_pdf(sheet, overrides))
        assert sorted(c for c, zones in verdict["reasons"].items() if zone in zones) == mutation.get("residual_engine_reasons", [])

    def test_preserved_geometry_settings_behave_as_the_catalog_declares(self, client, name):
        e = EXPECTATIONS[name]
        catalog_id = e["identity"]["catalog_id"]
        if not catalog_id:
            pytest.skip("no catalog (hand-written profile)")
        catalog = default_store().get(catalog_id)
        sheet, ov = e["sample"]["sheet"], e["sample"].get("overrides")
        keys = {line[0] for line in sheet_lines(sheet, ov) if line}
        checked = 0
        for rule in catalog.zone_preserved:
            if not (rule.material_unless or rule.always_material) or not rule.names:
                continue
            zones = [z for z in e["zones"] if "*" in rule.zones or z in rule.zones]
            for zone in zones:
                status = e["zones"][zone]["status"]
                if not (status[0] == "Enabled" or status[1] == "unverified"):            # in service, or geometry reviewed
                    continue
                for template in rule.names:
                    row = template.replace("{zone}", zone)
                    key = next((k for k in keys if k == row or k.endswith(" " + row)), None)
                    if key is None:
                        continue
                    for value, blocking in [*((v, False) for v in rule.material_unless), ("40", True), ("", True)]:
                        review = review_of(client, sheet, merged(ov, {"set": {key: value}}))
                        rows = [i for g in review["groups"] if g["id"] == f"zone-{zone}" for i in g["items"]
                                if i["item_id"] is None and i["label"] == row]
                        assert rows and rows[0]["blocking"] is blocking, (zone, row, value)
                        checked += 1
        if not checked:
            pytest.skip("the catalog declares no geometry-affecting preserved setting present on this sheet")
