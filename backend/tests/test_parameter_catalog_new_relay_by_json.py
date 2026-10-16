"""The success criterion: a new relay is added by a validated JSON catalog -- and no Python.

"Acme X1" below exists nowhere in the source tree. Its catalog is written to a temporary catalog
directory, activated (lifecycle ``active``), and a PDF setting sheet in its own vocabulary is uploaded
through the real API. It must be identified, interpreted, reviewed with the application's standard
terms (its own names only under *Source*), made ready, applied, and plotted by the unchanged engine.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.parameter_catalog.loader import CATALOG_ROOT, REGISTRY_FILE, load_store
from app.main import create_app
from app.relay_profiles.identification_catalogue import build_registry
from tests.relay_pdf_fixtures import build_pdf, rows_page
from tests.relay_review_tokens import review_ref

UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"


def zone_mappings(zone: str) -> list[dict]:
    def num(mid, canonical, name, unit="ohm", **kw):
        return {"id": f"acme.{zone}.{mid}", "canonical": canonical, "zone": zone,
                "source": {"name": name, "type": "number", "unit": unit}, **kw}

    p = f"{zone} "
    return [
        {"id": f"acme.{zone}.status", "canonical": "distance.zone.status", "zone": zone, "source": {"name": p + "Enable"},
         "transform": {"type": "enum", "map": {"Yes": "enabled", "No": "disabled"}}},
        {"id": f"acme.{zone}.direction", "canonical": "distance.zone.direction", "zone": zone, "source": {"name": p + "Direction"},
         "transform": {"type": "enum", "map": {"Fwd": "forward", "Rev": "reverse"}}},
        {"id": f"acme.{zone}.geometry", "canonical": "distance.zone.geometry_mode", "zone": zone,
         "transform": {"type": "constant", "value": "explicit_rx"}},
        num("x", "distance.zone.x_reach", p + "X Reach"),
        num("r_right", "distance.zone.r_right", p + "R Right"),
        num("r_left", "distance.zone.r_left", p + "R Left"),
        {"id": f"acme.{zone}.characteristic", "canonical": "distance.zone.characteristic", "zone": zone,
         "transform": {"type": "constant", "value": "quadrilateral"}, "evidence": [{"name": p + "X Reach"}],
         "requires_resolved": ["distance.zone.x_reach"], "authority": "documented_derivation",
         "note": "Acme X-Series distance zones are quadrilateral."},
        num("delay", "distance.zone.common_delay", p + "Delay", "s"),
        {"id": f"acme.{zone}.pp", "canonical": "distance.zone.pp_enabled", "zone": zone, "source": {"name": p + "PP Loops"},
         "transform": {"type": "boolean"}},
        {"id": f"acme.{zone}.pe", "canonical": "distance.zone.pe_enabled", "zone": zone, "source": {"name": p + "PE Loops"},
         "transform": {"type": "boolean"}},
    ]


def acme_catalog(lifecycle: str = "active") -> dict:
    def doc_num(mid, canonical, name, unit, **kw):
        return {"id": f"acme.{mid}", "canonical": canonical, "source": {"name": name, "type": "number", "unit": unit}, **kw}

    return {
        "schema": "oruxa.parameter-catalog/1",
        "catalog_id": "acme-x1",
        "version": "1.0.0",
        "lifecycle": lifecycle,
        "applicability": {"manufacturer": "Acme Protection", "family": "X-Series", "model": "X1"},
        "identification": {
            "model_patterns": ["X-?1"], "family_markers": ["Acme"],
            "scheme_model_pattern": "(?<![A-Za-z0-9])X-?1(?![A-Za-z0-9])",
            "version_pattern": "(V\\d+(?:\\.\\d+)*)",
            "parameter_signatures": [{"name": "acme-zone-names", "pattern": "^Z[1-4] (?:Enable|Direction)$", "min_matches": 2}],
        },
        "zones": {"static": [{"id": "Z1", "name": "Zone 1"}, {"id": "Z2", "name": "Zone 2"}]},
        "distance_scope": {"names": ["Z1 Enable", "Z2 Enable"]},
        "mappings": [
            doc_num("ct_p", "ct_vt.ct_primary", "CT Primary", "A"),
            doc_num("ct_s", "ct_vt.ct_secondary", "CT Secondary", "A"),
            doc_num("vt_p", "ct_vt.vt_primary", "VT Primary", "kV"),
            doc_num("vt_s", "ct_vt.vt_secondary", "VT Secondary", "V"),
            {"id": "acme.basis", "canonical": "ct_vt.impedance_basis", "source": {"name": "Impedance Basis"},
             "transform": {"type": "enum", "map": {"Primary": "primary", "Secondary": "secondary"}}},
            *zone_mappings("Z1"), *zone_mappings("Z2"),
        ],
    }


ACME_ROWS = [
    ["Acme Protection X-Series", "Scheme: X1_V2.0_demo"],
    ["Parameter", "Setting", "Range"],
    ["CT Primary", "800", "1-30000 A"], ["CT Secondary", "1", "1-5 A"],
    ["VT Primary", "132", "0.1-1000 kV"], ["VT Secondary", "110", "50-140 V"],
    ["Impedance Basis", "Primary", "Primary/Secondary"],
    ["Z1 Enable", "Yes", "Yes/No"], ["Z1 Direction", "Fwd", "Fwd/Rev"], ["Z1 X Reach", "6", "0.1-300 ohm"],
    ["Z1 R Right", "4", "0.1-300 ohm"], ["Z1 R Left", "1.5", "0.1-300 ohm"], ["Z1 Delay", "0", "0-10 s"],
    ["Z1 PP Loops", "On", "On/Off"], ["Z1 PE Loops", "On", "On/Off"],
    ["Z2 Enable", "Yes", "Yes/No"], ["Z2 Direction", "Fwd", "Fwd/Rev"], ["Z2 X Reach", "11", "0.1-300 ohm"],
    ["Z2 R Right", "7", "0.1-300 ohm"], ["Z2 R Left", "2.5", "0.1-300 ohm"], ["Z2 Delay", "0.4", "0-10 s"],
    ["Z2 PP Loops", "On", "On/Off"], ["Z2 PE Loops", "On", "On/Off"],
    ["Hostname", "relay-7", None],
]


def acme_pdf() -> bytes:
    return build_pdf([rows_page([row if row[-1] is not None else row[:-1] for row in ACME_ROWS])])


@pytest.fixture
def store(tmp_path: Path):
    (tmp_path / "canonical").mkdir()
    shutil.copy(CATALOG_ROOT / REGISTRY_FILE, tmp_path / REGISTRY_FILE)
    (tmp_path / "acme").mkdir()
    (tmp_path / "acme" / "x1.json").write_text(json.dumps(acme_catalog()), encoding="utf-8")
    store = load_store(tmp_path)
    assert not store.rejected, [str(r) for r in store.rejected]
    return store


@pytest.fixture
def client(settings, store, monkeypatch):
    registry = build_registry(store)
    monkeypatch.setattr("app.services.relay_import_upload_service.default_registry", lambda: registry)
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client, data: bytes):
    r = client.post(UPLOAD, files={"file": ("acme.pdf", io.BytesIO(data), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


class TestANewRelayNeedsOnlyAJsonCatalog:
    def test_the_relay_is_identified_and_interpreted_by_the_catalog_alone(self, client):
        body = upload(client, acme_pdf())
        assert (body["identification_status"], body["manufacturer"], body["relay_family"], body["model"], body["profile_id"]) == (
            "identified", "Acme Protection", "X-Series", "X1", "acme-x1")
        assert body["interpretation_status"] in ("interpreted", "incomplete") and body["zone_count"] == 2
        assert body["profile_version"] == "acme-x1-v1.0.0"                         # the catalog version that produced it

    def test_the_review_uses_the_standard_terms_and_keeps_the_oem_names_under_source(self, client):
        review = upload(client, acme_pdf())["review"]
        assert review["profile_version"] == "acme-x1-v1.0.0"
        z1 = next(g for g in review["groups"] if g["id"] == "zone-Z1")
        labels = [i["label"] for i in z1["items"]]
        assert {"Status", "Direction", "Characteristic", "Reactive Reach (X)", "Right Resistive Reach (+R)",
                "Left Resistive Reach (−R)", "Time Delay", "Phase-Phase Faults", "Earth Faults"} <= set(labels)
        everything = json.dumps([(i["label"], i["full_label"]) for g in review["groups"] for i in g["items"]])
        for oem_term in ("X Reach", "R Right", "R Left", "Z1 Enable", "PP Loops", "Impedance Basis"):
            assert oem_term not in everything
        x = next(i for i in z1["items"] if i["label"] == "Reactive Reach (X)")
        assert x["value_text"] == "6 Ω" and x["status"] == "mapped" and x["sources"][0]["name"] == "Z1 X Reach"
        assert (x["catalog_id"], x["catalog_version"], x["canonical_id"]) == ("acme-x1", "1.0.0", "distance.zone.x_reach")
        assert x["raw_value"] == "6" and x["sources"][0]["page"] == 1

    def test_unit_conversion_and_transformation_are_visible_in_the_review(self, client):
        review = upload(client, acme_pdf())["review"]
        vt = next(i for g in review["groups"] for i in g["items"] if i["item_id"] == "transformers.vt_primary_v")
        assert vt["value_text"] == "132000 V" and vt["raw_value"] == "132" and vt["transformation"] == "132 kV → 132000 V"

    def test_settings_the_catalog_does_not_map_are_preserved_not_interpreted(self, client):
        review = upload(client, acme_pdf())["review"]
        assert review["not_interpreted_count"] + len(review["out_of_scope"]) >= 1
        assert "Hostname" in json.dumps(review["out_of_scope"] + review["not_interpreted"])

    def test_the_relay_reaches_ready_and_applies_through_the_unchanged_pipeline(self, client):
        review = upload(client, acme_pdf())["review"]
        confirm = [i["item_id"] for g in review["groups"] for i in g["items"]
                   if i["item_id"] and i["primary"] and i["review_status"] == "to_confirm" and i["category"] == "assumption"]
        body = {**review_ref(review), "confirmed": confirm}
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "ready", state["blocking_issues"]
        out = client.post(APPLY, json=body).json()
        assert out["characteristic"] == "quadrilateral" and out["impedance_basis"] == "primary"
        z1, z2 = out["zones"]
        assert (z1["reactive_reach_ohm"], z1["resistive_reach_forward_ohm"], z1["resistive_reach_reverse_ohm"], z1["delay_s"]) == (6.0, 4.0, 1.5, 0.0)
        assert (z2["reactive_reach_ohm"], z2["resistive_reach_forward_ohm"], z2["resistive_reach_reverse_ohm"], z2["delay_s"]) == (11.0, 7.0, 2.5, 0.4)
        assert z1["geometry_mode"] == "explicit_rx" and z1["enabled"] and z1["direction"] == "forward"
        assert "Acme" not in json.dumps(out)                                          # the engine payload is OEM-neutral

    def test_a_catalog_that_is_not_active_changes_nothing(self, settings, tmp_path, monkeypatch):
        (tmp_path / "canonical").mkdir()
        shutil.copy(CATALOG_ROOT / REGISTRY_FILE, tmp_path / REGISTRY_FILE)
        (tmp_path / "acme").mkdir()
        (tmp_path / "acme" / "x1.json").write_text(json.dumps(acme_catalog("tested")), encoding="utf-8")
        registry = build_registry(load_store(tmp_path))
        monkeypatch.setattr("app.services.relay_import_upload_service.default_registry", lambda: registry)
        with TestClient(create_app(settings)) as c:
            body = upload(c, acme_pdf())
        assert body["interpretation_status"] == "not_supported" and body["review"] is None

    def test_an_edited_catalog_that_fails_validation_is_never_used(self, settings, tmp_path, monkeypatch):
        (tmp_path / "canonical").mkdir()
        shutil.copy(CATALOG_ROOT / REGISTRY_FILE, tmp_path / REGISTRY_FILE)
        (tmp_path / "acme").mkdir()
        broken = acme_catalog()
        broken["mappings"][0]["canonical"] = "ct_vt.not_a_thing"
        (tmp_path / "acme" / "x1.json").write_text(json.dumps(broken), encoding="utf-8")
        store = load_store(tmp_path)
        assert store.rejected and not store.catalogs
        registry = build_registry(store)
        monkeypatch.setattr("app.services.relay_import_upload_service.default_registry", lambda: registry)
        with TestClient(create_app(settings)) as c:
            assert upload(c, acme_pdf())["interpretation_status"] == "not_supported"


class TestTheKeyAcceptanceNoPythonProfileJsonOnly:
    """DEC-195's acceptance test: a relay that exists only as a JSON catalog -> the standard review model."""

    def test_no_python_anywhere_knows_the_relay(self):
        app_dir = Path(__file__).resolve().parents[1] / "app"
        hits = [p.name for p in app_dir.rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".html", ".js")
                and "acme" in p.read_text(encoding="utf-8", errors="ignore").lower()]
        assert hits == [], f"the synthetic relay must exist only in the test's JSON, but app/ mentions it: {hits}"
        assert not list(app_dir.rglob("*acme*"))

    def test_its_profile_is_the_generic_catalog_profile_with_no_hand_written_extension(self, store):
        from app.domain.parameter_catalog.profile import CatalogProfile

        profile = next(p for p in build_registry(store)._profiles if p.profile_id == "acme-x1")          # noqa: SLF001
        assert type(profile) is CatalogProfile and profile.extension is None

    def test_raw_parameters_become_canonical_fields_and_the_standard_review_dto(self, client):
        body = upload(client, acme_pdf())
        review = body["review"]
        # extracted raw parameters -> catalog -> canonical fields -> standard review DTO
        by_id = {i["item_id"]: i for g in review["groups"] for i in g["items"] if i["item_id"]}
        assert by_id["zones[Z1].x_reach_ohm"]["canonical_id"] == "distance.zone.x_reach"
        assert by_id["zones[Z1].x_reach_ohm"]["label"] == "Reactive Reach (X)"
        assert by_id["zones[Z1].x_reach_ohm"]["sources"][0]["name"] == "Z1 X Reach"        # the OEM name: Source only
        assert by_id["zones[Z2].resistive_reach.phase_phase"]["value_text"] == "7 Ω"
        assert by_id["zones[Z2].direction"]["value_text"] == "Forward"
        assert by_id["transformers.vt_primary_v"]["transformation"] == "132 kV → 132000 V"

    def test_the_response_reports_catalog_identity_and_coverage(self, client):
        body = upload(client, acme_pdf())
        assert (body["catalog_id"], body["catalog_version"]) == ("acme-x1", "1.0.0")
        c = body["catalog_coverage"]
        assert c["extracted_settings"] >= 20 and c["catalog_mapped_settings"] >= 18
        assert c["extension_interpreted_settings"] == 0                              # no extension exists for this relay
        assert c["catalog_recognised_settings"] + c["unmapped_settings"] == c["extracted_settings"]
        assert body["review"]["catalog_coverage"] == c and body["review"]["catalog_id"] == "acme-x1"
        assert "Hostname" not in json.dumps(c)                                       # counts only, never content

    def test_the_catalog_can_be_dry_run_against_the_pdf_before_it_is_made_available(self, store):
        from app.services.relay_pdf_extractor import extract_pdf
        from app.domain.parameter_catalog.dry_run import dry_run

        report = dry_run(store.get("acme-x1"), store.registry, extract_pdf(acme_pdf()).document)
        assert report.counts()["mapped"] >= 18 and report.counts()["conflict"] == 0
        assert any(u.name == "Hostname" for u in report.unmapped)
