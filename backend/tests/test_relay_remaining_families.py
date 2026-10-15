"""The remaining relay families, interpreted by validated JSON catalogs only (no hand-written profile).

REL670 (READY FOR OWNER UAT), REL511 / 7SL87 / 7SA613 / GRZ100 / GRL200 / RCS-941 / RELZ100 (PARTIALLY SUPPORTED)
and LFZP111 (DEFERRED). Every test reads a real PDF through the real extractor and the real upload API; the
synthetic sheets are in ``relay_family_fixtures``. The owner's real sheets are exercised at the end when
``RELAY_SAMPLE_PDF_DIR`` is set (never committed).

For the partial / deferred relays the tests prove what is *not* invented: zone states, directions, bases,
characteristics, timers, loop conventions, geometry.
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.relay_profiles.identification_catalogue import build_registry
from tests import relay_family_fixtures as F

UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"
APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.config import Settings

    settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("s")),
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
                        git_sha="local", version="local")
    with TestClient(create_app(replace(settings, max_relay_import_upload_size_mb=5))) as c:
        yield c


def upload(client, pdf: bytes) -> dict:
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def items(review) -> dict[str, dict]:
    """Review rows by canonical path; a value shown as two rows (R / X, magnitude / angle) keeps its primary row."""
    out: dict[str, dict] = {}
    for g in review["groups"]:
        for i in g["items"]:
            if i["item_id"]:
                out.setdefault(i["item_id"], i)
    return out


def group(review, zone_id: str) -> dict:
    return next(g for g in review["groups"] if g["id"] == f"zone-{zone_id}")


def raw_rows(review, zone_id: str) -> dict[str, dict]:
    """The zone's preserved raw settings (no canonical meaning), by their source name."""
    return {i["label"]: i for i in group(review, zone_id)["items"] if i["item_id"] is None}


def unresolved(item: dict, category: str) -> bool:
    return item["value_text"] is None and item["category"] == category


def decisions(review, *, confirm=True, suggested=True, manual=()):
    confirmed = [i["item_id"] for g in review["groups"] for i in g["items"]
                 if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"]
    offered = [i["item_id"] for g in review["groups"] for i in g["items"] if i["item_id"] and i.get("suggestion")]
    return {"validation_context": review["validation_context"], "confirmed": confirmed if confirm else [],
            "suggested": offered if suggested else [], "manual": list(manual)}


def assert_every_raw_setting_is_accounted_for(body):
    c = body["catalog_coverage"]
    assert c["catalog_recognised_settings"] + c["unmapped_settings"] == c["extracted_settings"]
    assert c["extension_interpreted_settings"] == 0                                     # catalog-only: nothing else read


# ---------------------------------------------------------------------------------------------------------------
# Catalog-only architecture
# ---------------------------------------------------------------------------------------------------------------

FAMILIES = {
    # name: (pdf builder, profile id, catalog id, model)
    "rel670": (F.rel670_pdf, "hitachi-rel670", "hitachi-rel670-catalog", "REL670"),
    "rel511": (F.rel511_pdf, "hitachi-rel511", "hitachi-rel511-catalog", "REL511"),
    "7sl87": (F.sl87_pdf, "siemens-siprotec5-7sl87", "siemens-siprotec5-7sl87-catalog", "7SL87"),
    "7sa613": (F.sa613_pdf, "siemens-7sa613", "siemens-7sa613-catalog", "7SA613"),
    "grz100": (F.grz100_pdf, "toshiba-grz100", "toshiba-grz100-catalog", "GRZ100"),
    "grl200": (F.grl200_pdf, "toshiba-grl200", "toshiba-grl200-catalog", "GRL200"),
    "rcs941": (F.rcs941_pdf, "nr-rcs941", "nr-rcs941-catalog", "RCS-941"),
    "lfzp111": (F.lfzp_pdf, "lfzp111", "lfzp111-catalog", "LFZP111"),
    "relz100": (F.relz100_pdf, "relz100", "relz100-catalog", "RELZ100"),
}


#: The active catalog version per family (REL511 1.1.0: documented relay behaviour, DEC-198).
CATALOG_VERSIONS = {name: "1.1.0" if name == "rel511" else "1.0.0" for name in FAMILIES}


class TestEveryFamilyIsCatalogOnly:
    @pytest.mark.parametrize("name", FAMILIES)
    def test_identified_and_interpreted_by_its_own_active_catalog(self, client, name):
        pdf, profile_id, catalog_id, model = FAMILIES[name]
        body = upload(client, pdf())
        assert (body["identification_status"], body["profile_id"], body["model"]) == ("identified", profile_id, model)
        assert (body["catalog_id"], body["catalog_version"]) == (catalog_id, CATALOG_VERSIONS[name])
        assert body["profile_version"] == f"{catalog_id}-v{CATALOG_VERSIONS[name]}"
        assert body["interpretation_status"] == "interpreted" and body["review"] is not None
        assert_every_raw_setting_is_accounted_for(body)

    @pytest.mark.parametrize("name", FAMILIES)
    def test_its_profile_is_the_generic_catalog_profile_with_no_python_extension(self, name):
        from app.domain.parameter_catalog.profile import CatalogProfile

        profile = next(p for p in build_registry()._profiles if p.profile_id == FAMILIES[name][1])   # noqa: SLF001
        assert type(profile) is CatalogProfile and profile.extension is None

    @pytest.mark.parametrize("name", FAMILIES)
    def test_the_review_uses_standard_terms_and_every_value_carries_catalog_provenance(self, client, name):
        review = upload(client, FAMILIES[name][0]())["review"]
        for item in items(review).values():
            if item["value_text"] is not None and item["item_id"].startswith(("zones[", "transformers.", "line.")):
                assert item["catalog_id"] == FAMILIES[name][2] and item["catalog_version"] == CATALOG_VERSIONS[name]
                assert item["canonical_id"] and item["sources"], item["item_id"]


class TestRel670CatalogOnlyProof:
    """REL670 reaches review -> readiness -> Apply -> Distance Protection through catalog JSON only."""

    def test_no_production_python_contains_rel670_mapping_logic(self):
        hits = sorted(p.relative_to(APP_DIR).as_posix() for p in APP_DIR.rglob("*.py")
                      if "rel670" in p.read_text(encoding="utf-8", errors="ignore").lower().replace("-", ""))
        # the only mention is the pre-existing identification descriptor (recognition data, not mapping)
        assert hits == ["relay_profiles/identification_catalogue.py"]
        lines = (APP_DIR / "relay_profiles" / "identification_catalogue.py").read_text(encoding="utf-8").splitlines()
        mentions = [ln.strip() for ln in lines if "rel670" in ln.lower().replace("-", "").replace("?", "")]
        assert mentions == ['profile_id="hitachi-rel670",', 'model="REL670",', 'model_patterns=(r"REL-?670",),']
        assert (APP_DIR / "data" / "parameter_catalog" / "hitachi_energy" / "rel670.json").exists()

    def test_review_readiness_apply_and_engine(self, client):
        review = upload(client, F.rel670_pdf())["review"]
        state = client.post(VALIDATE, json=decisions(review, confirm=False, suggested=False)).json()
        assert state["readiness"]["status"] == "not_ready"                         # the ZDRDIR left boundary blocks
        # Zone 2 is in service but its Timer tPP switch is OFF: no delay is assumed, the user states one
        body = decisions(review)
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "not_ready"
        body = decisions(review, manual=[{"item_id": "zones[Z2].phase_timer_s", "value": 1.0}])
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        assert (out["characteristic"], out["impedance_basis"]) == ("quadrilateral", "primary")
        z1, z2 = out["zones"]
        assert (z1["id"], z1["direction"], z1["reactive_reach_ohm"], z1["resistive_reach_forward_ohm"],
                z1["resistive_reach_reverse_ohm"], z1["delay_s"], z1["geometry_mode"]) == ("Z1", "forward", 6.0, 4.0, 0.0, 0.2, "explicit_rx")
        assert z2["direction"] == "reverse" and z2["enabled"]
        assert "REL670" not in json.dumps(out) and "RFPP" not in json.dumps(out)    # the engine payload is OEM-neutral


class TestRel670:
    def test_bare_channel_labels_are_read_without_channel_type_rows(self, client):
        i = items(upload(client, F.rel670_pdf())["review"])
        assert (i["transformers.ct_primary_a"]["value_text"], i["transformers.ct_secondary_a"]["value_text"]) == ("1200 A", "1 A")
        assert [s["name"] for s in i["transformers.ct_primary_a"]["sources"]] == ["CTprim1", "CTprim2", "CTprim3"]  # never IN (600)
        assert i["transformers.vt_primary_v"]["value_text"] == "132000 V" and i["transformers.vt_primary_v"]["category"] == "assumption"

    def test_rfpp_is_halved_with_raw_value_and_transformation_rfpe_is_not(self, client):
        i = items(upload(client, F.rel670_pdf())["review"])
        rr = i["zones[Z1].resistive_reach.phase_phase"]
        assert (rr["value_text"], rr["raw_value"], rr["category"]) == ("4 Ω", "8", "assumption")
        assert "÷ 2" in rr["transformation"] and rr["sources"][0]["name"] == "ZM01-:RFPP"
        pe = i["zones[Z1].resistive_reach.phase_earth"]
        assert (pe["value_text"], pe["raw_value"], pe["transformation"]) == ("12 Ω", "12", None)

    def test_zone_state_and_direction_come_from_the_configured_settings(self, client):
        i = items(upload(client, F.rel670_pdf())["review"])
        assert (i["zones[Z1].status"]["value_text"], i["zones[Z1].direction"]["value_text"]) == ("Enabled", "Forward")
        assert (i["zones[Z2].status"]["value_text"], i["zones[Z2].direction"]["value_text"]) == ("Enabled", "Reverse")

    def test_a_timer_switched_off_is_missing_and_the_note_is_never_the_value(self, client):
        review = upload(client, F.rel670_pdf())["review"]
        i = items(review)
        assert i["zones[Z1].phase_timer_s"]["value_text"] == "0.2 s"                  # the setting, not the note's 0.15
        assert unresolved(i["zones[Z2].phase_timer_s"], "missing")                    # Timer tPP OFF; the note's 3 s unused
        notes = [n["title"] for n in group(review, "Z1")["source_notes"]]
        assert notes == ["Zone 1 timer requirement: 0.15 s"]

    def test_the_directional_left_boundary_is_a_capability_gap_not_zero(self, client):
        i = items(upload(client, F.rel670_pdf())["review"])
        left = i["zones[Z1].resistive_reach.reverse"]
        assert unresolved(left, "unsupported") and {s["name"] for s in left["sources"]} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}
        assert left["suggestion"] and "approximation" in json.dumps(left).lower()


class TestRel511:
    def test_verified_subset(self, client):
        review = upload(client, F.rel511_pdf())["review"]
        i = items(review)
        assert (i["zones[Z1].status"]["value_text"], i["zones[Z1].direction"]["value_text"]) == ("Enabled", "Forward")
        assert i["zones[Z2].status"]["value_text"].startswith("Disabled")
        assert (i["zones[Z1].x_reach_ohm"]["value_text"], i["zones[Z1].common_timer_s"]["value_text"]) == ("3 Ω", "0 s")
        assert i["transformers.ct_primary_a"]["value_text"] == "600 A"

    def test_not_invented_basis_rf_convention_zone_block(self, client):
        """DEC-198: the characteristic and loops are documented relay behaviour (see
        test_relay_rel511_documented_behaviour.py); the basis, the RF conversion and ZnBlock stay unverified."""
        review = upload(client, F.rel511_pdf())["review"]
        i = items(review)
        assert unresolved(i["transformers.setting_basis"], "unverified")
        assert i["zones[Z1].characteristic.type"]["category"] == "documented"
        rf = i["zones[Z1].resistive_reach.phase_phase"]
        assert unresolved(rf, "unverified") and rf["raw_value"] == "4.6"            # preserved, neither halved nor used
        assert raw_rows(review, "Z1")["Z1Block"]["raw_value"] == "On"                 # preserved, never a state
        assert unresolved(i["zones[Z1].resistive_reach.phase_earth"], "unverified")   # RFN preserved, not used

    def test_a_10_s_timer_switched_off_neither_delays_nor_defeats_the_zone_by_itself(self, client):
        i = items(upload(client, F.rel511_pdf())["review"])
        assert unresolved(i["zones[Z2].common_timer_s"], "missing")
        assert i["zones[Z2].status"]["sources"][0]["name"] == "Operation_Z2"         # explicit, not the 10 s rule
        assert unresolved(i["zones[Z2].direction"], "unsupported")                   # 'None' is not an option printed

    def test_review_only_never_ready(self, client):
        review = upload(client, F.rel511_pdf())["review"]
        assert client.post(VALIDATE, json=decisions(review)).json()["readiness"]["status"] == "not_ready"


class TestSiprotec5_7SL87:
    def test_edit_mode_basis_and_configured_values(self, client):
        review = upload(client, F.sl87_pdf())["review"]
        i = items(review)
        assert i["transformers.setting_basis"]["value_text"] == "Primary" and i["transformers.setting_basis"]["category"] == "mapped"
        assert (i["zones[Z1].x_reach_ohm"]["value_text"], i["zones[Z1].resistive_reach.phase_phase"]["value_text"],
                i["zones[Z1].resistive_reach.phase_earth"]["value_text"]) == ("4.7 Ω", "3.1 Ω", "11 Ω")
        assert i["zones[Z2].status"]["value_text"].startswith("Disabled") and i["zones[Z2].direction"]["value_text"] == "Reverse"
        assert i["zones[Z1].compensation.kr"]["value_text"] == "1.7"                  # zone-specific compensation: YES
        assert unresolved(i["zones[Z2].compensation.kr"], "missing")                  # NO: the zone's own Kr is not used

    def test_blank_timer_cells_are_missing_never_infinity_or_the_notes(self, client):
        review = upload(client, F.sl87_pdf())["review"]
        i = items(review)
        for zone in ("Z1", "Z2"):
            for timer in ("phase_timer_s", "earth_timer_s"):
                item = i[f"zones[{zone}].{timer}"]
                assert unresolved(item, "missing") and item["raw_value"] is None
                assert any("blank" in n and "Infinity" in n for n in item["notes"])
        assert [n["title"] for n in group(review, "Z1")["source_notes"]] == ["Zone 1 timer requirement: 0.15 s"]

    def test_explicit_zero_tilt_is_a_valid_setting_and_the_inclined_boundary_still_blocks_apply(self, client):
        review = upload(client, F.sl87_pdf())["review"]
        i = items(review)
        tilt = i["zones[Z1].tilt_deg"]
        assert (tilt["value_text"], tilt["raw_value"], tilt["category"]) == ("0°", "0", "mapped")  # 0 kept as 0, not Missing
        assert not any("tilt" in r["message"].lower() for r in review["blocking_issues"])
        assert raw_rows(review, "Z1")["21.901.2311.107 Dist. characteristic angle"]["raw_value"] == "82.7"
        assert unresolved(i["zones[Z1].characteristic.type"], "missing")             # not named: not assumed
        assert client.post(VALIDATE, json=decisions(review)).json()["readiness"]["status"] == "not_ready"

    def test_a_non_zero_tilt_stays_unsupported_and_blocks(self, client):
        review = upload(client, F.sl87_pdf(tilt="5"))["review"]
        tilt = items(review)["zones[Z1].tilt_deg"]
        assert (tilt["value_text"], tilt["category"]) == ("5°", "unsupported")
        assert any("tilt" in r["message"].lower() for r in review["blocking_issues"])

    @pytest.mark.parametrize(("cell", "category"), [("", "missing"), ("abc", "unreadable")])
    def test_a_blank_or_malformed_tilt_is_never_read_as_zero(self, client, cell, category):
        tilt = items(upload(client, F.sl87_pdf(tilt=cell))["review"])["zones[Z1].tilt_deg"]
        assert unresolved(tilt, category)


class TestSiprotec4_7SA613:
    def test_units_from_the_range_column_and_op_mode(self, client):
        i = items(upload(client, F.sa613_pdf())["review"])
        assert (i["transformers.vt_primary_v"]["value_text"], i["transformers.vt_primary_v"]["category"]) == ("275000 V", "mapped")
        assert i["transformers.ct_primary_a"]["value_text"] == "1200 A"
        assert (i["zones[Z1].status"]["value_text"], i["zones[Z1].direction"]["value_text"]) == ("Enabled", "Forward")
        assert i["zones[Z4].status"]["value_text"].startswith("Disabled")             # Op. mode Inactive
        assert i["zones[Z5].direction"]["category"] == "unsupported"                  # non-directional: engine limit

    def test_timers_are_never_taken_from_the_range_column_or_infinity(self, client):
        i = items(upload(client, F.sa613_pdf())["review"])
        assert unresolved(i["zones[Z1].phase_timer_s"], "missing") and unresolved(i["zones[Z1].earth_timer_s"], "missing")
        t4 = i["zones[Z4].common_timer_s"]
        assert unresolved(t4, "unreadable") and t4["raw_value"] == "Infinity"
        assert any("not a finite delay" in n for n in t4["notes"])

    def test_z5_reverse_reach_and_zone_reduction_are_preserved_not_drawn(self, client):
        review = upload(client, F.sa613_pdf())["review"]
        assert items(review)["zones[Z5].x_reach_ohm"]["value_text"] == "10 Ω"         # X(Z5)+
        assert raw_rows(review, "Z5")["X(Z5)-"]["raw_value"] == "7"
        assert raw_rows(review, "Z1")["Zone Reduction"]["category"] == "unsupported"

    def test_basis_and_characteristic_are_not_inferred(self, client):
        i = items(upload(client, F.sa613_pdf())["review"])
        assert unresolved(i["transformers.setting_basis"], "missing")
        assert unresolved(i["zones[Z1].characteristic.type"], "missing")


class TestGrz100:
    def test_ratios_timers_and_line_data(self, client):
        i = items(upload(client, F.grz100_pdf())["review"])
        assert (i["transformers.ct_ratio"]["value_text"], i["transformers.vt_ratio"]["value_text"]) == ("1200", "1200")
        assert unresolved(i["transformers.ct_primary_a"], "missing")                  # a ratio is never split
        assert (i["zones[Z1].phase_timer_s"]["value_text"], i["zones[Z2].phase_timer_s"]["value_text"]) == ("0 s", "0.3 s")

    def test_differing_phase_and_earth_characteristics_are_not_forced_into_one(self, client):
        i = items(upload(client, F.grz100_pdf())["review"])
        char = i["zones[Z1].characteristic.type"]
        assert char["value_text"] == "Unknown" and char["category"] == "unsupported"

    def test_blinders_and_reach_settings_are_preserved_and_no_state_or_direction_invented(self, client):
        review = upload(client, F.grz100_pdf())["review"]
        rows = raw_rows(review, "Z1")
        assert {"Z1S", "BFRS", "BFLS-angle", "Z1S-angle1"} <= set(rows)
        assert all(r["category"] == "unsupported" for r in rows.values())
        i = items(review)
        assert unresolved(i["zones[Z1].status"], "missing") and unresolved(i["zones[Z1].direction"], "missing")
        assert [n["title"] for n in group(review, "ZR2")["source_notes"]] == ["Zone R2 timer requirement: 3 s"]


class TestGrl200:
    def test_element_enables_direction_reach_and_timers(self, client):
        i = items(upload(client, F.grl200_pdf())["review"])
        assert (i["zones[Z1].phase_phase_enabled"]["value_text"], i["zones[Z1].phase_earth_enabled"]["value_text"]) == ("Enabled", "Enabled")
        assert i["zones[Z1].direction"]["value_text"] == "Forward"
        assert i["zones[Z1].reach"]["value_text"] == "3.59 Ω"
        assert (i["zones[Z1].phase_timer_s"]["value_text"], i["zones[Z1].earth_timer_s"]["value_text"]) == ("0.15 s", "0.15 s")

    def test_mho_phase_with_quad_earth_is_unsupported_not_faked(self, client):
        review = upload(client, F.grl200_pdf())["review"]
        i = items(review)
        assert i["zones[Z1].characteristic.type"]["value_text"] == "Unknown"
        assert i["zones[Z1].characteristic.type"]["category"] == "unsupported"
        assert "Prot/G1/Trip/Distance_ZS/Z1S-R.Reach" in raw_rows(review, "Z1")       # the blinder, preserved

    def test_not_invented_status_disagreeing_direction_ct_vt(self, client):
        i = items(upload(client, F.grl200_pdf())["review"])
        assert unresolved(i["zones[Z1].status"], "missing")
        assert i["zones[Z2].direction"]["value_text"] is None                       # ZS Reverse vs ZG Forward
        assert unresolved(i["transformers.ct_primary_a"], "missing")                 # the notes' CT ratio is not a setting


class TestRcs941:
    def test_polar_reach_timers_and_gated_earth_quad(self, client):
        i = items(upload(client, F.rcs941_pdf())["review"])
        assert i["zones[Z1].reach"]["value_text"] == "0.53 Ω" and "80" in i["zones[Z1].reach"]["raw_value"]
        assert i["zones[Z1].common_timer_s"]["value_text"] == "0.15 s"
        assert i["zones[Z2].phase_timer_s"]["value_text"] == "0.45 s"
        assert i["zones[Z1].resistive_reach.phase_earth"]["value_text"] == "2.44 Ω"
        assert unresolved(i["zones[Z2].resistive_reach.phase_earth"], "missing")      # En_ZPG2_Quad = 0

    def test_no_zone_state_no_forward_direction_and_a_reverse_zone_assumption(self, client):
        review = upload(client, F.rcs941_pdf())["review"]
        i = items(review)
        assert unresolved(i["zones[Z1].status"], "missing") and unresolved(i["zones[Z1].direction"], "missing")
        assert (i["zones[ZR].direction"]["value_text"], i["zones[ZR].direction"]["category"]) == ("Reverse", "assumption")
        assert [n["title"] for n in group(review, "ZR")["source_notes"]] == ["Reverse Zone timer requirement: 3 s"]
        assert raw_rows(review, "Z1")["Z_PG1"]["category"] == "unsupported"


class TestLfzp111:
    def test_deferred_limited_review(self, client):
        review = upload(client, F.lfzp_pdf())["review"]
        i = items(review)
        assert unresolved(i["metadata.manufacturer"], "missing")                     # not asserted
        assert (i["transformers.ct_ratio"]["value_text"], i["transformers.vt_ratio"]["value_text"]) == ("600", "1200")
        assert (i["zones[Z1].status"]["value_text"], i["zones[Z1].status"]["category"]) == ("Enabled", "assumption")
        assert i["zones[Z2].status"]["value_text"].startswith("Disabled")

    def test_multipliers_are_preserved_and_no_reach_timer_or_characteristic_is_derived(self, client):
        review = upload(client, F.lfzp_pdf())["review"]
        i = items(review)
        assert raw_rows(review, "Z2")["KZ2"]["raw_value"] == "1.64"
        for zone in ("Z1", "Z2", "Z3"):
            assert unresolved(i[f"zones[{zone}].reach"], "missing")
            assert unresolved(i[f"zones[{zone}].common_timer_s"], "missing")
            assert unresolved(i[f"zones[{zone}].characteristic.type"], "missing")


class TestRelz100:
    def test_suspicious_line_data_is_kept_exactly_as_printed(self, client):
        i = items(upload(client, F.relz100_pdf())["review"])
        z1 = i["line.positive_sequence_impedance"]
        assert z1["raw_value"] == "4.381 + j0.74" and z1["value_text"] == "4.381 Ω"   # R1 > X1, not corrected
        assert i["transformers.vt_secondary_v"]["value_text"] == "110 V"

    def test_direction_only_where_stated_and_no_state_basis_or_rf_conversion(self, client):
        review = upload(client, F.relz100_pdf())["review"]
        i = items(review)
        assert unresolved(i["zones[Z1].direction"], "missing")
        assert i["zones[Z4].direction"]["value_text"] == "Non directional"
        assert unresolved(i["zones[Z1].status"], "missing") and unresolved(i["transformers.setting_basis"], "missing")
        assert unresolved(i["zones[Z1].resistive_reach.phase_phase"], "unsupported")
        assert unresolved(i["zones[Z5].common_timer_s"], "missing")                   # TimerT5 OFF: the 10 s is unused
        assert unresolved(i["zones[Z5].status"], "missing")                           # and never defeats the zone
        assert raw_rows(review, "Z1")["Z<Prot_Zone1:KN1"]["raw_value"] == "0.7"


# ---------------------------------------------------------------------------------------------------------------
# The owner's real sheets (not committed): RELAY_SAMPLE_PDF_DIR
# ---------------------------------------------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
needs_samples = pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
REAL = {
    "rel670": ("rel670.pdf", "hitachi-rel670", 4), "rel511": ("rel511.pdf", "hitachi-rel511", 5),
    "7sl87": ("7sl87.pdf", "siemens-siprotec5-7sl87", 6), "7sa613": ("7sa613.pdf", "siemens-7sa613", 6),
    "grz100": ("grz100.pdf", "toshiba-grz100", 8), "grl200": ("grl200.pdf", "toshiba-grl200", 6),
    "rcs941": ("rcs.pdf", "nr-rcs941", 4), "lfzp111": ("lfzp.pdf", "lfzp111", 5), "relz100": ("relz100.pdf", "relz100", 5),
}


def real(client, name):
    path = Path(SAMPLE_DIR) / REAL[name][0]
    if not path.exists():
        pytest.skip(f"{path.name} not available")
    return upload(client, path.read_bytes())


@needs_samples
class TestRealSamples:
    @pytest.mark.parametrize("name", REAL)
    def test_identified_interpreted_and_fully_accounted(self, client, name):
        body = real(client, name)
        assert (body["profile_id"], body["zone_count"], body["confidence"]) == (REAL[name][1], REAL[name][2], "high")
        assert body["interpretation_status"] == "interpreted"
        assert_every_raw_setting_is_accounted_for(body)
        assert body["catalog_coverage"]["canonical_values_conflicting"] == 0

    def test_rel670_real_sheet_ready_and_applied(self, client):
        review = real(client, "rel670")["review"]
        i = items(review)
        assert (i["zones[Z4].status"]["value_text"], i["zones[Z4].direction"]["value_text"]) == ("Enabled", "Reverse")
        assert (i["zones[Z1].resistive_reach.phase_phase"]["value_text"], i["zones[Z1].resistive_reach.phase_phase"]["raw_value"]) == ("0.49 Ω", "0.98")
        body = decisions(review)
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        assert [(z["id"], z["direction"], z["reactive_reach_ohm"], z["delay_s"]) for z in out["zones"]] == [
            ("Z1", "forward", 0.65, 0.15), ("Z2", "forward", 1.3, 0.45), ("Z3", "forward", 4.65, 3.0), ("Z4", "reverse", 0.16, 3.0)]

    def test_7sl87_real_sheet_timers_missing_and_basis_primary(self, client):
        i = items(real(client, "7sl87")["review"])
        assert i["transformers.setting_basis"]["value_text"] == "Primary"
        assert all(unresolved(i[f"zones[Z{n}].{t}"], "missing") for n in (1, 2, 3) for t in ("phase_timer_s", "earth_timer_s"))

    def test_7sa613_real_sheet_no_timer_and_no_basis(self, client):
        i = items(real(client, "7sa613")["review"])
        assert all(i[f"zones[{z}].{t}"]["value_text"] is None
                   for z, t in (("Z1", "phase_timer_s"), ("Z2", "earth_timer_s"), ("Z3", "common_timer_s"), ("Z1B", "phase_timer_s")))
        assert unresolved(i["transformers.setting_basis"], "missing")

    @pytest.mark.parametrize("name", ["rel511", "7sl87", "7sa613", "grz100", "grl200", "rcs941", "lfzp111", "relz100"])
    def test_partial_and_deferred_relays_stay_review_only(self, client, name):
        review = real(client, name)["review"]
        assert client.post(VALIDATE, json=decisions(review)).json()["readiness"]["status"] == "not_ready"
