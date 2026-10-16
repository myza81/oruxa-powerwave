"""7SA613 under DEC-198 (Amendment 6): artificial semantic blockers resolved; genuine source and engine gaps kept.

* Documented relay behaviour (Siemens 7SA6 manuals C53000-G1176-C156-2 / -7, version-dependent for the V4.2-style
  parameter set): the polygonal characteristic and the phase-phase / phase-earth loops of every zone in service (no
  selector exists -> "not a relay setting" for an inactive zone), the secondary-ohm setting basis, R(Zn) ph-ph as a
  per-phase value and the T-1phase / T-multi-phase loop assignment.
* An explicit 'Infinity' delay is a configured value ("∞ (no timed trip)") -- never Unreadable; an enabled zone whose
  delay is infinite is an engine limitation (no zone that only picks up).
* Blank Z1-Z3 delay cells and a blank R load (ph-ph) stay source-data gaps; the inclined +R / -R edges (distance angle),
  the non-directional Zone 5 and a stated load cutout are engine limitations. No 0.00 ohm offer, no approximation.

The synthetic sheet (``relay_family_fixtures.sa613_pdf``): Z1 / Z1B Forward, Z4 Inactive, Z5 Non-Directional.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry, check_lock, default_store, load_lock
from app.domain.relay_import.apply_settings import model_approximations
from app.domain.relay_import.approximation import APPROVED_RULES
from app.domain.relay_import.engine_adapter import adapt_to_engine
from app.domain.relay_import.provenance import UnresolvedCause
from app.services.relay_pdf_extractor import extract_pdf
from tests import relay_family_fixtures as F
from tests.test_relay_remaining_families import APPLY, VALIDATE, client, decisions, group, items, raw_rows, upload  # noqa: F401

SA613_JSON = CATALOG_ROOT / "siemens" / "siprotec4_7sa613.json"
CATALOG = "siemens-7sa613-catalog"
V42 = "Siemens C53000-G1176-C156-2 (V4.2)"
V470 = "Siemens C53000-G1176-C156-7 (V4.70, 02.2011)"

RF = ("A source fault-resistance setting is available and its resistive boundary is documented, but the current engine "
      "cannot represent that boundary exactly.")
LEFT = "The Left Resistive Reach (−R) is unresolved."
DELAY = "The zone delay is unresolved."
INFINITE = ("The zone delay is set to infinity: the zone picks up but does not trip on its own timer. The current engine "
            "cannot represent a zone that only picks up.")
NON_DIR = "Zone direction 'non_directional' is not supported; the engine models forward and reverse directional zones only."
LOAD_MISSING = "A setting that can change this zone's boundary has no configured value in the source."
LOAD_STATED = "A setting that changes this zone's boundary cannot yet be represented by the engine."
NO_TRIP = "∞ (no timed trip)"


@pytest.fixture(scope="module")
def review(client):
    return upload(client, F.sa613_pdf())["review"]


def model_of(pdf: bytes):
    return CatalogInterpreter(default_store().get(CATALOG), canonical_registry()).interpret(extract_pdf(pdf).document)


@pytest.fixture(scope="module")
def model():
    return model_of(F.sa613_pdf())


def issues(review) -> dict[str, dict]:
    return {issue["message"]: issue for issue in review["blocking_issues"]}


def cited(item) -> set[str]:
    return {r["reference_id"] for r in item["references"]}


class TestDocumentedSemantics:
    def test_the_characteristic_is_a_documented_polygon_cited_to_both_manuals(self, review):
        ch = items(review)["zones[Z1].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["authority"], ch["blocking"]) == (
            "Quadrilateral · Explicit R/X", "documented", "documented_derivation", False)
        assert cited(ch) == {"siemens-c53000-g1176-c156-2-polygon", "siemens-c53000-g1176-c156-7-polygon",
                             "siemens-c53000-g1176-c156-7-ordering"}
        assert {"R(Z1) ph-ph", "X(Z1)", "RE(Z1) ph-E", "FCT Distance", "Op. mode Z1"} <= {s["name"] for s in ch["sources"]}
        assert "polygon-only" in ch["notes"][0] and "address 115" in ch["notes"][0]

    def test_the_applicability_is_version_dependent(self, review):
        for ref in items(review)["zones[Z1].characteristic.type"]["references"]:
            assert "version-dependent" in ref["scope"]
        assert any("no firmware version is asserted" in r["scope"] for r in items(review)["zones[Z1].characteristic.type"]["references"])

    @pytest.mark.parametrize("field", ["characteristic.type", "phase_phase_enabled", "phase_earth_enabled"])
    def test_an_inactive_zone_shows_the_selectors_as_not_exposed(self, review, field):
        item = items(review)[f"zones[Z4].{field}"]                                     # Op. mode Z4 = Inactive
        assert (item["category"], item["blocking"], item["resolution"]) == ("not_exposed", False, None)

    @pytest.mark.parametrize("path", ["zones[Z1].phase_phase_enabled", "zones[Z1].phase_earth_enabled",
                                      "zones[Z5].phase_phase_enabled", "zones[Z1B].phase_earth_enabled"])
    def test_the_loops_are_documented_behaviour_for_zones_in_service(self, review, path):
        loop = items(review)[path]
        assert (loop["value_text"], loop["category"], loop["authority"]) == ("Enabled", "documented", "documented_derivation")

    def test_the_two_phase_earth_loop_selection_is_preserved_not_a_loop_switch(self, review):
        row = raw_rows(review, "Z1")["2Ph-E faults"]
        assert (row["raw_value"], row["blocking"]) == ("only phase-phase loops", False)
        assert "not the polygon boundary" in " ".join(row["notes"])

    def test_the_basis_is_secondary_documented_never_from_ratios(self, review):
        basis = items(review)["transformers.setting_basis"]
        assert (basis["value_text"], basis["category"], basis["authority"], basis["blocking"]) == (
            "Secondary", "documented", "documented_derivation", False)
        assert [s["name"] for s in basis["sources"]] == ["CT SECONDARY", "R(Z1) ph-ph"]
        assert not {s["name"] for s in basis["sources"]} & {"CT PRIMARY", "Unom PRIMARY", "Unom SECONDARY"}
        assert "not inferred from the CT / VT ratios" in basis["notes"][0]
        assert cited(basis) == {"siemens-c53000-g1176-c156-2-settings", "siemens-c53000-g1176-c156-7-ordering"}

    def test_artificial_blockers_are_gone(self, review):
        msgs = set(issues(review))
        assert not any("Characteristic" in m or "Phase-phase operation" in m or "basis" in m for m in msgs)


class TestTimers:
    def test_blank_z1_cells_stay_missing_and_block(self, review):
        i = items(review)
        for path in ("zones[Z1].phase_timer_s", "zones[Z1].earth_timer_s"):
            assert (i[path]["value_text"], i[path]["raw_value"], i[path]["category"]) == (None, None, "missing")
            assert any("blank" in n for n in i[path]["notes"])
        assert i["zones[Z1].phase_timer_s"]["blocking"] and DELAY in issues(review)
        assert [n["title"] for n in group(review, "Z1")["source_notes"]] == ["Zone 1 timer requirement: 0.15 s"]

    def test_the_loop_assignment_is_documented_when_the_cells_are_set(self, client):
        i = items(upload(client, F.sa613_pdf(z1_delays=("0.05", "0.15")))["review"])
        pp, pe = i["zones[Z1].phase_timer_s"], i["zones[Z1].earth_timer_s"]
        assert (pp["value_text"], pp["category"], pe["value_text"], pe["category"]) == ("0.15 s", "documented", "0.05 s", "documented")
        assert [s["name"] for s in pp["sources"]] == ["T1-multi-phase"] and [s["name"] for s in pe["sources"]] == ["T1-1phase"]

    def test_explicit_infinity_is_a_configured_value_never_unreadable(self, review, model):
        i = items(review)
        for path in ("zones[Z4].common_timer_s", "zones[Z5].common_timer_s", "zones[Z1B].phase_timer_s", "zones[Z1B].earth_timer_s"):
            assert (i[path]["value_text"], i[path]["raw_value"], i[path]["status"]) == (NO_TRIP, "Infinity", "mapped"), path
            assert i[path]["category"] != "unreadable"
        assert model.zone("Z5").common_timer_s.value == float("inf")                   # preserved, never a finite number

    def test_an_infinite_delay_on_a_zone_in_service_is_an_engine_limitation(self, review):
        i = items(review)
        assert (i["zones[Z5].common_timer_s"]["category"], i["zones[Z1B].phase_timer_s"]["category"]) == ("unsupported", "unsupported")
        assert issues(review)[INFINITE]["zone_ids"] == ["Z5", "Z1B"] and issues(review)[INFINITE]["kind"] == ""
        assert i["zones[Z4].common_timer_s"]["category"] == "mapped"                  # Z4 is out of service: no limit

    def test_a_disabled_zone_with_an_infinite_delay_carries_no_delay_and_is_not_refused(self, model):
        adaptation = adapt_to_engine(replace(model, zones=(model.zone("Z4"),)), engine_basis="secondary")
        assert any("Z4: the delay is set to infinity (no timed trip); no delay is carried" in w for w in adaptation.warnings)
        assert not any("infinity" in r.message for r in adaptation.reasons)


class TestGeometry:
    def test_r_ph_ph_is_per_phase_and_direct_at_a_vertical_angle(self, client):
        rr = items(upload(client, F.sa613_pdf(angle="90"))["review"])["zones[Z1].resistive_reach.phase_phase"]
        assert (rr["value_text"], rr["category"]) == ("1.5 Ω", "documented")         # not halved
        assert "per-phase" in " ".join(rr["notes"])

    def test_the_distance_angle_now_blocks_both_resistive_edges(self, review, model):
        i = items(review)
        for edge in ("phase_phase", "reverse"):
            item = i[f"zones[Z1].resistive_reach.{edge}"]
            assert (item["value_text"], item["category"], item["blocking"], item["raw_value"]) == (None, "unsupported", True, "1.5 | 82")
            assert [s["name"] for s in item["sources"]] == ["R(Z1) ph-ph", "Distance Angle"]
            assert item["suggestion"] is None and item["resolution"] is None          # no 0.00 ohm offer, no entry
        assert "Rright(X) = R + X * cot(phi)" in i["zones[Z1].resistive_reach.phase_phase"]["notes"][0]
        assert "Rleft(X) = -R + X * cot(phi)" in i["zones[Z1].resistive_reach.reverse"]["notes"][0]
        assert "Distance Angle" not in raw_rows(review, "Z1")                         # no longer a silent preserved row
        assert issues(review)[RF]["zone_ids"] == ["Z1", "Z5", "Z1B"] and issues(review)[LEFT]["zone_ids"] == ["Z1", "Z5", "Z1B"]
        assert model.zone("Z1").resistive_reach.reverse.provenance.cause is UnresolvedCause.UNSUPPORTED

    def test_no_zero_ohm_offer_and_it_cannot_be_forced(self, client, review):
        body = decisions(review)
        assert body["suggested"] == []
        body["suggested"] = ["zones[Z1].resistive_reach.reverse"]
        assert client.post(VALIDATE, json=body).status_code == 400

    def test_zone_reduction_zero_is_an_exact_tilt_and_non_zero_blocks(self, client, review):
        tilt = items(review)["zones[Z1].tilt_deg"]
        assert (tilt["value_text"], tilt["category"], tilt["blocking"]) == ("0°", "mapped", False)
        tilted = upload(client, F.sa613_pdf(zone_reduction="10"))["review"]
        assert items(tilted)["zones[Z1].tilt_deg"]["category"] == "unsupported"
        assert any("tilt" in m.lower() for m in issues(tilted))

    def test_z5_stays_non_directional_with_its_reverse_reach_preserved(self, review):
        i = items(review)
        assert (i["zones[Z5].direction"]["value_text"], i["zones[Z5].direction"]["category"]) == ("Non directional", "unsupported")
        assert issues(review)[NON_DIR]["zone_ids"] == ["Z5"]
        row = raw_rows(review, "Z5")["X(Z5)-"]
        assert row["raw_value"] == "7" and "entire parallelogram" in " ".join(row["notes"])


class TestLoadCutout:
    def test_a_blank_phase_phase_r_load_is_a_blocking_source_gap(self, review):
        row = raw_rows(review, "Z1")["R load (ph-ph)"]
        assert (row["raw_value"], row["category"], row["blocking"]) == (None, "missing", True)
        assert issues(review)[LOAD_MISSING]["zone_ids"] == ["Z1", "Z5", "Z1B"]       # zones in service only
        assert raw_rows(review, "Z4")["R load (ph-ph)"]["blocking"] is False

    def test_the_phase_earth_load_cutout_is_kept_but_does_not_block_the_phase_phase_plot(self, review):
        row = raw_rows(review, "Z1")["R load (ph-E)"]
        assert row["blocking"] is False and "not draw" in " ".join(row["notes"])

    def test_infinity_switches_the_cutout_off_and_a_stated_value_is_an_engine_limit(self, client):
        off = upload(client, F.sa613_pdf(r_load_pp="Infinity"))["review"]
        assert raw_rows(off, "Z1")["R load (ph-ph)"]["blocking"] is False
        assert LOAD_MISSING not in issues(off) and LOAD_STATED not in issues(off)
        stated = upload(client, F.sa613_pdf(r_load_pp="40"))["review"]
        row = raw_rows(stated, "Z1")["R load (ph-ph)"]
        assert (row["raw_value"], row["category"], row["blocking"]) == ("40", "unsupported", True)
        assert LOAD_STATED in issues(stated)                                          # no "no intersection" claimed


class TestReadiness:
    def test_only_genuine_blockers_remain(self, review):
        assert {DELAY, RF, LEFT, INFINITE, NON_DIR, LOAD_MISSING} <= set(issues(review))

    def test_no_approximation_and_never_ready(self, client, review, model):
        assert APPROVED_RULES == () and model_approximations(model) == ()
        assert review["approximate_count"] == 0 and review["readiness"]["status"] == "not_ready"
        body = decisions(review, manual=[{"item_id": "zones[Z1].phase_timer_s", "value": 0.15}])
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "not_ready"
        assert client.post(APPLY, json=body).status_code == 409


class TestCatalog:
    def test_catalog_1_1_0_is_locked_with_the_earlier_version_kept(self):
        store = default_store()
        catalog = store.get(CATALOG)
        assert catalog.version == "1.1.0" and catalog.lifecycle == "active"
        lock = load_lock()
        assert check_lock(store, lock) == [] and lock[f"{CATALOG}@1.1.0"] == store.digests[catalog.key]
        assert f"{CATALOG}@1.0.0" in lock
        assert {r.id: (r.document, r.verification) for r in catalog.references} == {
            "siemens-c53000-g1176-c156-2-polygon": (V42, "verified"), "siemens-c53000-g1176-c156-2-settings": (V42, "verified"),
            "siemens-c53000-g1176-c156-7-polygon": (V470, "verified"), "siemens-c53000-g1176-c156-7-ordering": (V470, "verified")}

    def test_the_derivations_are_refused_without_a_verified_reference(self):
        data = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        for ref in data["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(data, canonical_registry(), source="7sa613")
        failing = " ".join(i.path for i in exc.value.issues if i.code == IssueCode.UNVERIFIED_REFERENCE)
        for mapping in ("7sa613.characteristic", "7sa613.pp_enabled", "7sa613.basis", "7sa613.delay_z1_pp"):
            assert mapping in failing

    def test_no_vertical_edge_is_mapped_at_an_inclined_angle(self):
        by = {m["id"]: m for m in json.loads(SA613_JSON.read_text(encoding="utf-8"))["mappings"]}
        assert "source" not in by["7sa613.r_right"] and "source" not in by["7sa613.r_left"]
        assert by["7sa613.r_right.vertical"]["requires"][0]["equals"] == ["90", "90.0"]


class TestGenericCapabilities:
    def test_infinity_is_only_for_number_sources(self):
        data = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        bad = copy.deepcopy(data)
        next(m for m in bad["mappings"] if m["id"] == "7sa613.line_length_unit")["source"]["infinity"] = True
        with pytest.raises(CatalogValidationError):
            parse_catalog(bad, canonical_registry(), source="7sa613")

    def test_a_source_without_the_infinity_option_still_refuses_infinity(self, client):
        data = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        plain = copy.deepcopy(data)
        next(m for m in plain["mappings"] if m["id"] == "7sa613.delay_z4")["source"].pop("infinity")
        catalog = parse_catalog(plain, canonical_registry(), source="7sa613")
        z4 = CatalogInterpreter(catalog, canonical_registry()).interpret(extract_pdf(F.sa613_pdf()).document).zone("Z4")
        assert not z4.common_timer_s.is_resolved and z4.common_timer_s.provenance.cause is UnresolvedCause.UNREADABLE

    def test_unverified_when_and_material_unless_are_exclusive(self):
        data = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        bad = copy.deepcopy(data)
        rule = next(p for p in bad["zone_preserved"] if p["names"] == ["R load (ph-ph)"])
        rule["unverified_when"] = ["x"]
        with pytest.raises(CatalogValidationError):
            parse_catalog(bad, canonical_registry(), source="7sa613")


# --- the owner's real sheet (never committed): RELAY_SAMPLE_PDF_DIR -----------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
def test_real_7sa613_sheet_lists_only_genuine_blockers(client):
    path = Path(SAMPLE_DIR) / "7sa613.pdf"
    if not path.exists():
        pytest.skip("7sa613.pdf not available")
    review = upload(client, path.read_bytes())["review"]
    i = items(review)
    assert review["profile_version"] == f"{CATALOG}-v1.1.0"
    # Z1-Z3 delays (3) + inclined +R and -R x Z1, Z2, Z3, Z5, Z1B (10) + blank R load (ph-ph) x 5 zones in service (5)
    assert review["blocking_count"] == 18 and review["readiness"]["status"] == "not_ready"
    assert review["approximate_count"] == 0 and review["unreadable_count"] == 0
    assert set(issues(review)) == {DELAY, RF, LEFT, INFINITE, NON_DIR, LOAD_MISSING}
    assert issues(review)[DELAY]["zone_ids"] == ["Z1", "Z2", "Z3"]
    assert issues(review)[INFINITE]["zone_ids"] == ["Z5", "Z1B"]
    assert all(i[f"zones[{z}].characteristic.type"]["category"] == "documented" for z in ("Z1", "Z2", "Z3", "Z5", "Z1B"))
    assert i["zones[Z4].characteristic.type"]["category"] == "not_exposed"
    assert (i["transformers.setting_basis"]["value_text"], i["transformers.setting_basis"]["category"]) == ("Secondary", "documented")
    assert [i[f"zones[{z}].resistive_reach.phase_phase"]["raw_value"] for z in ("Z1", "Z2", "Z3")] == ["1.5 | 82", "1.7 | 82", "2.4 | 82"]
    assert (i["zones[Z1].tilt_deg"]["value_text"], i["zones[Z1].tilt_deg"]["category"]) == ("0°", "mapped")
    assert decisions(review)["suggested"] == []
