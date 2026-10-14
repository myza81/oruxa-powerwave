"""Relay Import Slice 7: read-only Extraction Review (DTO + upload response)."""

from __future__ import annotations

import io
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_distance import DistanceZone
from app.main import create_app
from app.relay_profiles.identification_catalogue import default_registry
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.schemas.relay_import import ExtractionReviewOut
from app.services.relay_extraction_review import NOT_STATED, build_extraction_review
from app.services.relay_interpretation_summary import engine_adaptation, summarize_interpretation
from tests.relay_p441_fixtures import make_doc
from tests.relay_pdf_fixtures import build_pdf, rows_page, simple_pdf
from tests.test_relay_import_upload import _p441_pdf

URL = "/api/v1/relay-import/upload"
BACKEND_APP = Path(__file__).resolve().parents[1] / "app"
EXTRA = (("5000", "Recorder Channel 1", "ABC", None), ("3040", "Power Swing Block", "Enabled", "Enabled/Disabled"))


def _review(**kwargs):
    doc = make_doc(**kwargs)
    registry = default_registry()
    summary = summarize_interpretation(registry, doc, registry.identify(doc))
    return summary, summary.review


def _items(review):
    return {i.key: i for g in review.groups for i in g.items}


def _group(review, group_id):
    return next(g for g in review.groups if g.id == group_id)


@pytest.fixture
def client(settings):
    with TestClient(create_app(replace(settings, max_relay_import_upload_size_mb=1))) as c:
        yield c


class TestReviewDto:
    def test_review_exists_only_for_an_interpreted_relay(self):
        summary, review = _review()
        assert summary.status.value == "interpreted" and review is not None
        registry = default_registry()
        other = make_doc(scheme=("LZOP", "Scheme: XYZ9000_V1"))                  # not a recognised relay
        none = summarize_interpretation(registry, other, registry.identify(other))
        assert none.status.value == "not_supported" and none.review is None

    def test_relay_profile_and_counts_follow_the_listed_items(self):
        """Review counts are per canonical value the review lists (Slice 8), so the
        pending inferred count equals the profile's inferred count while mapped and
        unresolved follow what is listed (see the module docstring)."""
        summary, review = _review()
        assert (review.manufacturer, review.relay_family, review.model) == ("Schneider Electric", "MiCOM P44x", "P441")
        assert (review.profile_id, review.profile_version) == ("schneider-micom-p441", "micom-p441-v1")
        assert review.zone_count == summary.zone_count == 5
        assert review.to_confirm_count == summary.inferred_setting_count
        assert review.not_interpreted_count == summary.not_interpreted_setting_count
        assert review.confirmed_count == review.resolved_manually_count == 0
        assert review.unresolved_count >= summary.unresolved_setting_count  # required placeholders are listed too
        assert 0 < review.blocking_count <= review.unresolved_count
        assert review.interpretation == "reviewable"

    def test_zones_are_generated_from_the_model_in_order(self):
        _, review = _review()
        zones = [g for g in review.groups if g.kind == "zone"]
        assert [g.id for g in zones] == ["zone-Z1", "zone-Z2", "zone-Z3", "zone-Z4", "zone-ZP"]
        assert [g.title for g in zones] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone P"]

    def test_zone_count_follows_the_model_not_a_fixed_four(self):
        doc = make_doc()
        registry = default_registry()
        model = MicomP441Profile().interpret(doc)
        seven = replace(model, zones=(*model.zones, DistanceZone("Z7", "Zone 7"), DistanceZone("Z8")))
        review = build_extraction_review(
            seven, doc, engine_adaptation(seven), not_interpreted=0
        )
        titles = [g.title for g in review.groups if g.kind == "zone"]
        assert review.zone_count == 7 and titles[-2:] == ["Zone 7", "Zone Z8"]
        one = replace(model, zones=model.zones[:1])
        short = build_extraction_review(one, doc, engine_adaptation(one), not_interpreted=0)
        assert [g.id for g in short.groups if g.kind == "zone"] == ["zone-Z1"]
        assert registry  # the registry is shared, untouched

    def test_p441_values_are_reviewable_with_units(self):
        _, review = _review()
        i = _items(review)
        assert i["ct.primary"].value_text == "1200 A" and i["ct.secondary"].value_text == "1 A"
        assert i["vt.primary"].value_text == "132000 V" and i["vt.secondary"].value_text == "110 V"
        assert i["basis"].value_text == "Secondary"
        assert i["line.length"].value_text == "7.03 km"
        assert i["line.angle"].value_text == "80°"
        assert i["line.line_impedance_magnitude"].value_text == "2 Ω"
        assert i["zone.Z1.reach"].value_text == "1.43 Ω" and i["zone.Z1.reach.angle"].value_text == "80°"
        assert i["zone.Z1.rr.pe"].value_text == "7.02 Ω" and i["zone.Z1.rr.pp"].value_text == "2.11 Ω"
        assert i["zone.Z1.timer"].value_text == "0 s" and i["zone.Z2.timer"].value_text == "0.3 s"
        assert i["zone.Z3.reach"].value_text == "4.48 Ω" and i["zone.Z3.timer"].value_text == "3 s"
        assert i["comp.Z1.k0_magnitude"].value_text == "0.718" and i["comp.Z1.k0_angle_deg"].value_text == "-11.5°"

    def test_labels_are_engineering_labels_not_field_names(self):
        _, review = _review()
        for item in _items(review).values():
            assert "_" not in item.label and "_" not in item.full_label
            assert item.label[:1].isupper()
        assert _items(review)["zone.Z1.rr.pe"].full_label == "Zone 1 Earth Resistive Reach"

    def test_status_is_preserved_per_item(self):
        _, review = _review()
        i = _items(review)
        assert i["ct.primary"].status == "mapped"
        assert i["zone.Z1.reach"].status == "inferred" and i["zone.Z1.reach.angle"].status == "inferred"
        assert i["zone.ZP.status"].status == "inferred" and i["zone.ZP.status"].value_text == "Disabled"
        assert i["zone.Z2.direction"].status == "mapped" and i["zone.Z1.direction"].status == "inferred"
        assert {x.status for x in i.values()} == {"mapped", "inferred", "unresolved"}

    def test_inferred_items_carry_the_profile_reason(self):
        _, review = _review()
        reach = _items(review)["zone.Z1.reach"]
        assert any("line angle" in n for n in reach.notes)
        assert all(i.notes for i in _items(review).values() if i.status != "mapped")

    def test_unresolved_items_explain_why(self):
        _, review = _review()
        i = _items(review)
        assert any("10.0 s operating delay" in n for n in i["zone.ZP.status"].notes)
        assert i["zone.Z1.rr.reverse"].status == "unresolved" and i["zone.Z1.rr.reverse"].notes == (NOT_STATED,)
        assert any("not mapped to a single zone tilt" in n for n in i["zone.Z1.raw.p1-e44"].notes)

    def test_zone_4_is_disabled_but_keeps_its_numbers(self):
        _, review = _review()
        z4 = _group(review, "zone-Z4")
        assert z4.state_label == "Disabled / Defeated"
        by_key = {x.key: x for x in z4.items}
        assert by_key["zone.Z4.status"].value_text == "Disabled / Defeated"
        assert by_key["zone.Z4.reach"].value_text == "0.36 Ω" and by_key["zone.Z4.timer"].value_text == "3 s"
        assert by_key["zone.Z4.rr.pe"].value_text == "17.19 Ω"

    def test_zone_p_is_its_own_section_disabled_by_the_defeated_delay_assumption(self):
        _, review = _review()
        zp = _group(review, "zone-ZP")
        assert zp.title == "Zone P" and zp.state_label == "Disabled" and zp.state_status == "inferred"
        assert zp.items[0].key == "zone.ZP.status" and zp.items[0].category == "assumption"
        assert any(x.key == "zone.ZP.reach" and x.value_text == "0.001 Ω" for x in zp.items)

    def test_compensation_is_its_own_group_with_one_pair_per_zone(self):
        _, review = _review()
        comp = _group(review, "compensation")
        assert [i.label for i in comp.items][:2] == ["Zone 1 K0 Magnitude", "Zone 1 K0 Angle"]
        assert len(comp.items) == 10

    def test_unused_optional_placeholders_are_not_shown_but_required_unresolved_are(self):
        _, review = _review()
        keys = set(_items(review))
        assert "zone.Z1.earth_reach" not in keys and "zone.Z1.tilt" not in keys and "line.z0" not in keys
        assert {"relay.version", "base.voltage", "base.current", "line.z1"} <= keys

    def test_provenance_fields_cite_code_name_raw_page_line_text_and_profile(self):
        _, review = _review()
        item = _items(review)["zone.Z1.rr.pe"]
        (src,) = item.sources
        assert (src.code, src.name, src.raw_value, src.page) == ("300C", "R1G", "7.02", 3)
        assert isinstance(src.line, int) and "R1G" in src.source_text and "7.02" in src.source_text
        # DEC-195: the phase-earth resistive reach is catalog-owned, so the catalog version is the provenance
        assert (item.profile_id, item.profile_version) == ("schneider-micom-p441", "schneider-micom-p44x-catalog-v1.0.0")
        assert (item.catalog_id, item.catalog_version) == ("schneider-micom-p44x-catalog", "1.0.0")
        assert item.raw_value == "7.02"

    def test_multi_source_values_cite_every_source(self):
        _, review = _review()
        reach = _items(review)["zone.Z1.reach"]
        assert [s.code for s in reach.sources] == ["300A", "3005"]
        length = _items(review)["line.length"]
        assert {s.code for s in length.sources} == {"3002", "0D07"}

    def test_no_item_exposes_a_filesystem_path(self):
        _, review = _review()
        text = repr(asdict(review))
        for marker in ("C:\\", "D:\\", "/Users/", "/home/", "/tmp"):
            assert marker not in text

    def test_engine_compatibility_is_separate_and_lists_the_adapter_reasons(self):
        summary, review = _review()
        assert review.interpretation == "reviewable" and review.engine.status == "not_ready"
        messages = [r.message for r in review.engine.reasons]
        assert not any("ZP" in m for m in messages) and any("Left Resistive Reach" in m for m in messages)
        assert len(messages) == len(set(messages))  # identical messages are merged across zones
        merged = next(r for r in review.engine.reasons if "Left Resistive Reach" in r.message)
        assert len(merged.zone_ids) >= 2
        assert all(w.startswith("Engine: ") for w in summary.warnings if "Engine" in w)

    def test_a_model_without_zones_is_incomplete_not_reviewable(self):
        doc = make_doc()
        model = MicomP441Profile().interpret(doc)
        simple = replace(model, zones=())
        review = build_extraction_review(simple, doc, engine_adaptation(simple), not_interpreted=0)
        assert review.interpretation == "incomplete" and review.engine.status == "not_ready"

    def test_raw_uninterpreted_settings_are_preserved_and_split(self):
        _, review = _review(extra=EXTRA)
        names = {r.name for r in review.out_of_scope}
        assert {"Recorder Channel 1", "VTS Time Delay"} <= names
        retained = {r.name: r for r in (*review.not_interpreted, *review.out_of_scope)}
        row = retained["Recorder Channel 1"]
        assert (row.code, row.raw_value, row.page) == ("5000", "ABC", 4) and isinstance(row.line, int)
        assert "Power Swing Block" in {r.name for r in review.not_interpreted}

    def test_every_raw_setting_is_reachable_from_the_review(self):
        doc = make_doc(extra=EXTRA)
        model = MicomP441Profile().interpret(doc)
        assert model.referenced_setting_ids() == {s.setting_id for s in doc.settings}

    def test_review_is_deterministic(self):
        assert _review(extra=EXTRA)[1] == _review(extra=EXTRA)[1]

    def test_a_review_failure_does_not_fail_the_interpretation(self, monkeypatch):
        import app.services.relay_interpretation_summary as mod

        def boom(*a, **k):
            raise RuntimeError("secret 1.43")

        monkeypatch.setattr(mod, "build_extraction_review", boom)
        summary, review = _review()
        assert summary.status.value == "interpreted" and review is None and summary.zone_count == 5


class TestUploadResponse:
    def test_upload_returns_the_review_for_an_interpreted_p441(self, client):
        r = client.post(URL, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
        assert r.status_code == 200
        body = r.json()
        review = ExtractionReviewOut(**body["review"])
        assert review.zone_count == body["zone_count"] == 5
        assert review.to_confirm_count == body["inferred_setting_count"]
        assert review.engine.status == "not_ready"
        values = {i.key: i.value_text for g in review.groups for i in g.items}
        assert values["ct.primary"] == "1200 A" and values["zone.Z1.rr.pe"] == "7.02 Ω"
        assert len(r.content) < 250_000  # concise enough to ride in the upload response

    def test_review_is_null_for_unsupported_and_unreadable(self, client):
        # a relay no profile or catalog interprets (every catalogued family now has one)
        sheet = simple_pdf([["Scheme: XYZ9000_V1"], ["R1", "1.84", "0-655.35"]])
        body = client.post(URL, files={"file": ("a.pdf", io.BytesIO(sheet), "application/pdf")}).json()
        assert body["interpretation_status"] == "not_supported" and body["review"] is None
        scanned = client.post(URL, files={"file": ("a.pdf", io.BytesIO(build_pdf(["image"])), "application/pdf")}).json()
        assert scanned["review"] is None

    def test_repeat_upload_is_independent_and_nothing_is_retained(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        before = set(vars(client.app.state))
        files = lambda: {"file": ("a.pdf", io.BytesIO(_p441_pdf()), "application/pdf")}  # noqa: E731
        first = client.post(URL, files=files()).json()
        second = client.post(URL, files=files()).json()
        assert first["review"] == second["review"]
        assert set(vars(client.app.state)) == before
        assert list(tmp_path.iterdir()) == []


class TestNoPersistence:
    def test_review_modules_have_no_persistence_code(self):
        for path in (
            BACKEND_APP / "services" / "relay_extraction_review.py",
            BACKEND_APP / "services" / "relay_interpretation_summary.py",
        ):
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "psycopg", "sqlalchemy", "app.storage", "get_storage", "import tempfile",
                "open(", "write_bytes", "write_text", "mkdir", "STORAGE_PATH", "pickle", "shelve",
            ):
                assert forbidden not in text, (path.name, forbidden)

    def test_there_is_no_review_endpoint_that_reads_stored_state(self):
        from app.api.v1.relay_import import router

        # Slices 8-9 add two endpoints, both stateless: the interpretation arrives in the request.
        assert {r.path for r in router.routes} == {
            "/api/v1/relay-import/upload",
            "/api/v1/relay-import/review/validate",
            "/api/v1/relay-import/review/apply",
        }

    def test_review_schema_has_no_apply_semantics(self):
        names = set(ExtractionReviewOut.model_fields)
        assert not any(word in n for n in names for word in ("apply", "accept", "populate"))


def test_generic_review_module_names_no_relay():
    text = (BACKEND_APP / "services" / "relay_extraction_review.py").read_text(encoding="utf-8")
    for token in ("P441", "MiCOM", "7SA", "Siemens", "Schneider"):
        assert token not in text
