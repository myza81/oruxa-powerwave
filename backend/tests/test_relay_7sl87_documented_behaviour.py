"""7SL87 under DEC-198 (Amendment 3): documented relay behaviour replaces the artificial blockers; genuine gaps stay.

* The characteristic of every ENABLED zone stated with the quadrilateral parameter set (X reach, R (ph-g), R (ph-ph),
  Zone-inclination angle) is documented relay behaviour, cited to Siemens C53000-G5040-C011-9 (V07.50; version-dependent
  for the owner's 7SL87_8.81 sheet). SIPROTEC 5 exposes no characteristic selector, so a switched-off zone shows
  "not a relay setting", never Missing.
* The phase-phase / phase-earth loops stay Mapped from the configured Function mode (all Siemens option texts).
* R (ph-ph) is a per-phase value used directly (never halved) -- but its resistance line is inclined at the distance
  characteristic angle: Rright(X) = R + X * cot(phi). The engine draws a vertical +R, so at 82.7 deg the +R is
  Unsupported (engine limitation) and blocks; only at 90 deg is R (ph-ph) exactly the +R.
* The operate-delay loop assignment is documented, but a blank setting cell stays a missing source value.
* The left / directional boundary is Unsupported (not Missing) with no 0.00 ohm offer.
* The phase-phase load cutout in use is preserved and blocks (its effect on the zone is not yet verified).
* No approximation exists (candidate A7 is documented only); 7SL87 stays Not ready.

The synthetic sheet (``relay_family_fixtures.sl87_pdf``): Zone 1 on / Forward, Zone 2 off / Reverse.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry, check_lock, default_store, load_lock
from app.domain.relay_import.apply_settings import model_approximations
from app.domain.relay_import.approximation import APPROVED_RULES
from app.domain.relay_import.provenance import UnresolvedCause
from app.services.relay_pdf_extractor import extract_pdf
from tests import relay_family_fixtures as F
from tests.test_relay_remaining_families import APPLY, VALIDATE, client, decisions, group, items, raw_rows, upload  # noqa: F401

SL87_JSON = CATALOG_ROOT / "siemens" / "siprotec5_7sl87.json"
DOCUMENT = "Siemens C53000-G5040-C011-9 (V07.50, Edition 11.2017)"
CATALOG = "siemens-siprotec5-7sl87-catalog"

RF_UNSUPPORTED = ("A source fault-resistance setting is available and its resistive boundary is documented, but the "
                  "current engine cannot represent that boundary exactly.")
UNVERIFIED = "A setting that may change this zone's operation has a meaning that is not yet verified."
LEFT = "The Left Resistive Reach (−R) is unresolved."
DELAY = "The zone delay is unresolved."
LOAD_CUTOUT_PP = "21.901.3661.105 Use ph-ph load cutout"


@pytest.fixture(scope="module")
def review(client):
    return upload(client, F.sl87_pdf())["review"]


def model_of(pdf: bytes):
    catalog = default_store().get(CATALOG)
    return CatalogInterpreter(catalog, canonical_registry()).interpret(extract_pdf(pdf).document)


@pytest.fixture(scope="module")
def model():
    return model_of(F.sl87_pdf())


def issues(review) -> dict[str, dict]:
    return {issue["message"]: issue for issue in review["blocking_issues"]}


def cited(item) -> set[str]:
    return {r["reference_id"] for r in item["references"]}


class TestCharacteristic:
    def test_an_enabled_zone_is_documented_quadrilateral_cited_to_the_siemens_manual(self, review):
        ch = items(review)["zones[Z1].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["status"], ch["authority"], ch["blocking"]) == (
            "Quadrilateral · Explicit R/X", "documented", "mapped", "documented_derivation", False)
        assert [(r["reference_id"], r["document"], r["verification"]) for r in ch["references"]] == [
            ("siemens-c53000-g5040-c011-9-zones", DOCUMENT, "verified"), ("siemens-c53000-g5040-c011-9-quad", DOCUMENT, "verified")]
        # the quadrilateral parameter set is the evidence, gated on the zone being switched on
        assert {s["name"] for s in ch["sources"]} == {
            "21.901.3571.102 X reach", "21.901.3571.104 R (ph-ph)", "21.901.3571.103 R (ph-g)",
            "21.901.3571.113 Zone-inclination angle", "21.901.3571.1 Mode"}
        assert "no characteristic selector" in ch["notes"][0] and "does not reproduce" in ch["notes"][0]

    def test_the_applicability_is_version_dependent_relative_to_the_owner_sheet(self, review):
        for ref in items(review)["zones[Z1].characteristic.type"]["references"]:
            assert "7SL87_8.81" in ref["scope"] and "version-dependent" in ref["scope"] and "not a firmware-version match" in ref["scope"]

    def test_a_switched_off_zone_shows_the_selector_as_not_exposed_never_missing(self, review):
        ch = items(review)["zones[Z2].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["blocking"], ch["resolution"], ch["suggestion"]) == (
            None, "not_exposed", False, None, None)
        assert "no characteristic selector" in ch["notes"][0]

    def test_the_characteristic_is_never_missing_and_never_a_blocker(self, review):
        assert not [p for p, i in items(review).items() if p.endswith("characteristic.type") and i["category"] == "missing"]
        assert not any("Characteristic" in m for m in issues(review))


class TestLoops:
    def test_pp_and_pe_stay_mapped_from_the_configured_function_mode(self, review):
        for path in ("zones[Z1].phase_phase_enabled", "zones[Z1].phase_earth_enabled"):
            loop = items(review)[path]
            assert (loop["value_text"], loop["category"], loop["authority"], loop["raw_value"]) == (
                "Enabled", "mapped", "configured_setting", "ph-gnd and ph-ph")         # a setting, not documented behaviour

    @pytest.mark.parametrize(("mode", "pp", "pe"), [
        ("ph-ph only", "Enabled", "Disabled"), ("ph-gnd only", "Disabled", "Enabled"),
        ("ph-ph", "Enabled", "Disabled"), ("ph-gnd", "Disabled", "Enabled"),
    ])
    def test_every_siemens_function_mode_text_is_recognised(self, client, mode, pp, pe):
        i = items(upload(client, F.sl87_pdf(function_mode=mode))["review"])
        assert (i["zones[Z1].phase_phase_enabled"]["value_text"], i["zones[Z1].phase_earth_enabled"]["value_text"]) == (pp, pe)
        loop = i["zones[Z1].phase_phase_enabled"]
        assert (loop["raw_value"], loop["authority"]) == (mode, "configured_setting")    # read, never Unsupported text
        # a zone without phase-phase loops is read correctly but the phase-phase engine cannot draw it
        assert loop["category"] == ("mapped" if pp == "Enabled" else "unsupported")


class TestResistanceConvention:
    def test_at_a_vertical_characteristic_angle_r_ph_ph_is_the_plus_r_directly_never_halved(self, client):
        rr = items(upload(client, F.sl87_pdf(angle="90"))["review"])["zones[Z1].resistive_reach.phase_phase"]
        # the gate (the angle) is cited with the value, as for every gated read; the value is R (ph-ph) itself
        assert (rr["value_text"], rr["raw_value"], rr["category"], rr["blocking"]) == ("3.1 Ω", "90 | 3.1", "documented", False)
        assert cited(rr) == {"siemens-c53000-g5040-c011-9-quad"}
        assert "per-phase" in " ".join(rr["notes"]) and "not halved" in " ".join(rr["notes"])
        assert model_of(F.sl87_pdf(angle="90")).zone("Z1").resistive_reach.phase_phase.value == 3.1

    def test_the_per_phase_convention_is_recorded_with_the_inclined_plus_r(self, review):
        note = items(review)["zones[Z1].resistive_reach.phase_phase"]["notes"][0]
        assert "per-phase (conductor / positive-sequence)" in note and "not halved" in note

    def test_r_ph_g_is_mapped_as_printed_per_phase_and_not_drawn(self, review):
        pe = items(review)["zones[Z1].resistive_reach.phase_earth"]
        assert (pe["value_text"], pe["category"], pe["blocking"]) == ("11 Ω", "mapped", False)
        assert "per-phase value" in pe["notes"][-1] and cited(pe) == {"siemens-c53000-g5040-c011-9-quad"}


class TestDelays:
    def test_blank_z1_delay_cells_remain_source_values_missing(self, review):
        i = items(review)
        for path in ("zones[Z1].phase_timer_s", "zones[Z1].earth_timer_s"):
            item = i[path]
            assert (item["value_text"], item["raw_value"], item["category"]) == (None, None, "missing")
            assert any("blank" in n and "Infinity" in n for n in item["notes"])
            assert item["suggestion"] is None                                         # no proposed timer, no note value
        assert i["zones[Z1].phase_timer_s"]["blocking"] and DELAY in issues(review)
        assert [n["title"] for n in group(review, "Z1")["source_notes"]] == ["Zone 1 timer requirement: 0.15 s"]  # provenance only

    def test_the_delay_loop_assignment_is_documented_when_the_cells_are_set(self, client):
        i = items(upload(client, F.sl87_pdf(z1_delays=("0.05", "0.15")))["review"])
        pp, pe = i["zones[Z1].phase_timer_s"], i["zones[Z1].earth_timer_s"]
        assert (pp["value_text"], pp["category"], pp["authority"]) == ("0.15 s", "documented", "documented_derivation")
        assert (pe["value_text"], pe["category"], pe["authority"]) == ("0.05 s", "documented", "documented_derivation")
        assert [s["name"] for s in pp["sources"]] == ["21.901.3571.112 Operate delay (multi-ph.)"]
        assert [s["name"] for s in pe["sources"]] == ["21.901.3571.110 Operate delay (1-phase)"]
        assert "multi-phase faults" in " ".join(pp["notes"]) and "single-phase" in " ".join(pe["notes"])
        assert cited(pp) == cited(pe) == {"siemens-c53000-g5040-c011-9-quad"}


class TestInclinedBoundary:
    def test_the_82_7_degree_angle_is_no_longer_silently_preserved(self, review):
        rr = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert (rr["value_text"], rr["category"], rr["raw_value"], rr["blocking"]) == (None, "unsupported", "3.1 | 82.7", True)
        assert [s["name"] for s in rr["sources"]] == ["21.901.3571.104 R (ph-ph)", "21.901.2311.107 Dist. characteristic angle"]
        # no separate, non-blocking preserved row for the angle remains
        assert "21.901.2311.107 Dist. characteristic angle" not in raw_rows(review, "Z1")

    def test_the_exact_relation_and_angle_are_kept_in_provenance_and_model_metadata(self, review, model):
        note = items(review)["zones[Z1].resistive_reach.phase_phase"]["notes"][0]
        assert "Rright(X) = R + X * cot(phi)" in note and "Dist. characteristic angle = 82.7" in note
        assert "no approximation is applied" in note
        pp = model.zone("Z1").resistive_reach.phase_phase
        assert not pp.is_resolved and pp.provenance.cause is UnresolvedCause.UNSUPPORTED
        assert pp.provenance.raw_value == "3.1 | 82.7" and all(r.verified for r in pp.provenance.references)
        notes = " ".join(model.interpretation_notes)
        assert "Rright(X) = R (ph-ph) + X * cot(phi)" in notes and "candidate A7" in notes and "not approved" in notes

    def test_plus_r_stays_unsupported_with_no_entry_or_suggestion_offered(self, review):
        rr = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert rr["resolution"] is None and rr["suggestion"] is None
        msgs = issues(review)
        assert msgs[RF_UNSUPPORTED]["kind"] == "" and msgs[RF_UNSUPPORTED]["zone_ids"] == ["Z1"]   # an engine limit

    def test_the_zero_zone_inclination_stays_exact_and_mapped(self, review):
        tilt = items(review)["zones[Z1].tilt_deg"]
        assert (tilt["value_text"], tilt["category"], tilt["blocking"]) == ("0°", "mapped", False)


class TestLeftBoundary:
    def test_the_left_boundary_is_unsupported_not_missing_with_no_zero_ohm_offer(self, client, review):
        left = items(review)["zones[Z1].resistive_reach.reverse"]
        assert (left["category"], left["blocking"], left["suggestion"], left["resolution"]) == ("unsupported", True, None, None)
        assert "does not mean the zone has no left boundary" in left["notes"][0]
        assert "no left boundary is drawn, offered or approximated" in left["notes"][0]
        assert cited(left) == {"siemens-c53000-g5040-c011-9-direction"}
        body = decisions(review)
        assert body["suggested"] == []                                                # nothing is offered at all
        body["suggested"] = ["zones[Z1].resistive_reach.reverse"]
        assert client.post(VALIDATE, json=body).status_code == 400                    # nor can it be forced


class TestLoadCutout:
    def test_the_phase_phase_load_cutout_in_use_is_preserved_and_blocks(self, review):
        rows = raw_rows(review, "Z1")
        use = rows[LOAD_CUTOUT_PP]
        assert (use["raw_value"], use["category"], use["blocking"], use["value_text"]) == ("YES", "unverified", True, None)
        assert "not assumed to have no effect" in " ".join(use["notes"])
        assert (rows["21.901.3661.106 R load cutout (ph-ph)"]["raw_value"], rows["21.901.3661.107 Angle load cutout (ph-ph)"]["raw_value"]) == ("44.8", "45")
        issue = issues(review)[UNVERIFIED]
        assert issue["kind"] == "unverified" and issue["zone_ids"] == ["Z1"]          # the enabled zone only

    def test_the_phase_ground_load_cutout_is_preserved_but_does_not_block_the_phase_phase_plot(self, review):
        use = raw_rows(review, "Z1")["21.901.3661.102 Use ph-g load cutout"]
        assert (use["raw_value"], use["category"], use["blocking"]) == ("YES", "unsupported", False)

    def test_a_load_cutout_switched_off_creates_no_blocker(self, client):
        review = upload(client, F.sl87_pdf(load_cutout_pp="NO"))["review"]
        assert raw_rows(review, "Z1")[LOAD_CUTOUT_PP]["blocking"] is False and UNVERIFIED not in issues(review)


class TestReadiness:
    def test_every_genuine_blocker_is_listed_in_one_review(self, review):
        # Zone 1: the blank phase delay, the inclined +R, the left boundary and the phase-phase load cutout in use
        assert review["blocking_count"] == 4
        assert set(issues(review)) == {DELAY, RF_UNSUPPORTED, LEFT, UNVERIFIED}

    def test_no_approximation_and_not_ready_even_with_the_timers_supplied(self, client, review, model):
        assert APPROVED_RULES == () and model_approximations(model) == ()
        assert review["approximate_count"] == 0 and review["readiness"]["status"] == "not_ready"
        timers = [{"item_id": "zones[Z1].phase_timer_s", "value": 0.15}, {"item_id": "zones[Z1].earth_timer_s", "value": 0.15}]
        body = decisions(review, manual=timers)
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready" and state["blocking_count"] == 3   # +R, -R, load cutout
        assert client.post(APPLY, json=body).status_code == 409


class TestCatalog:
    def test_7sl87_is_catalog_1_1_0_locked_with_the_earlier_version_kept(self):
        store = default_store()
        catalog = store.get(CATALOG)
        assert catalog.version == "1.1.0" and catalog.lifecycle == "active"
        lock = load_lock()
        assert check_lock(store, lock) == [] and lock[f"{CATALOG}@1.1.0"] == store.digests[catalog.key]
        assert f"{CATALOG}@1.0.0" in lock
        assert {r.id: (r.document, r.verification) for r in catalog.references} == {
            f"siemens-c53000-g5040-c011-9-{k}": (DOCUMENT, "verified") for k in ("zones", "quad", "direction", "load")}

    def test_the_documented_derivations_are_refused_without_a_verified_reference(self):
        data = json.loads(SL87_JSON.read_text(encoding="utf-8"))
        without = copy.deepcopy(data)
        for ref in without["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(without, canonical_registry(), source="7sl87")
        failing = " ".join(i.path for i in exc.value.issues if i.code == IssueCode.UNVERIFIED_REFERENCE)
        assert "7sl87.characteristic" in failing and "7sl87.phase_delay" in failing and "7sl87.r_right.vertical" in failing

    def test_no_vertical_plus_r_is_mapped_at_an_inclined_angle_and_no_approximation_rule_exists(self):
        data = json.loads(SL87_JSON.read_text(encoding="utf-8"))
        by = {m["id"]: m for m in data["mappings"]}
        assert "kind" not in by["7sl87.r_right"]["gap"] and "source" not in by["7sl87.r_right"]   # unsupported, not mapped
        vertical = by["7sl87.r_right.vertical"]
        assert vertical["requires"][0]["source"]["name"] == "21.901.2311.107 Dist. characteristic angle"
        assert set(vertical["requires"][0]["equals"]) == {"90", "90.0", "90.00"} and "transform" not in vertical  # never halved
        assert "kind" not in by["7sl87.r_left"]["gap"] and "evidence" not in by["7sl87.r_left"]["gap"]


# --- the owner's real sheet (never committed): RELAY_SAMPLE_PDF_DIR -----------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
def test_real_7sl87_sheet_lists_only_genuine_blockers(client):
    path = Path(SAMPLE_DIR) / "7sl87.pdf"
    if not path.exists():
        pytest.skip("7sl87.pdf not available")
    review = upload(client, path.read_bytes())["review"]
    i = items(review)
    assert review["profile_version"] == f"{CATALOG}-v1.1.0"
    # Zones 1-3 (enabled) x (blank phase delay, inclined +R, left boundary, phase-phase load cutout in use)
    assert review["blocking_count"] == 12 and review["readiness"]["status"] == "not_ready"
    assert review["documented_count"] == 3 and review["approximate_count"] == 0     # characteristic x Zones 1-3
    assert review["not_exposed_count"] == 3                                           # characteristic x Zones 4-6 (off)
    assert set(issues(review)) == {DELAY, RF_UNSUPPORTED, LEFT, UNVERIFIED}
    for issue in issues(review).values():
        assert issue["zone_ids"] == ["Z1", "Z2", "Z3"]
    assert [i[f"zones[Z{n}].resistive_reach.phase_phase"]["raw_value"] for n in (1, 2, 3)] == ["3.1 | 82.7", "3.6 | 82.7", "6.6 | 82.7"]
    assert all(i[f"zones[Z{n}].{t}"]["category"] == "missing" for n in (1, 2, 3) for t in ("phase_timer_s", "earth_timer_s"))
    assert all(i[f"zones[Z{n}].resistive_reach.reverse"]["suggestion"] is None for n in (1, 2, 3))
    assert decisions(review)["suggested"] == []
