"""GRZ100 under DEC-198 (Amendment 7): artificial semantics resolved; static geometry separated from PLC trip logic.

* Documented relay behaviour (Toshiba GRZ100 instruction manual 6F2S0834-0 and brochure 6641-1, version-dependent
  for the owner's GRZ100_201A_Ver2.1 sheet): the secondary-ohm basis, the fixed zone directions (forward Z1, Z1X, Z2,
  ZF, Z3; reverse ZR1, ZR2, Z4; non-directional ZND), the phase-fault / earth-fault elements of every zone (no
  selector -> "not a relay setting"), ZnS as the quadrilateral's X reach, Zone 1X's instantaneous trip.
* ZS-C / ZG-C stay exact configured characteristic selectors.
* Operational state: the relay runs a site-specific PLC program the source does not define, so no zone is Enabled or
  Disabled -- its status is Unverified (never offered for entry) while its configured geometry is still reviewed.
  Zone 4 (command protection only, no timer, no trip of its own) is preserved and not drawn.
* Engine limitations, blocking: the 75-degree right blinder BFRS, the left blinder / directional boundary (BFLS-angle,
  ZBS-angle), the reverse zones' forward offset (ZR1BT / ZR2BT), the non-directional impedance element ZND. No 0.00 ohm
  offer, no approximation (AGRZ-A / AGRZ-B documented only). No source value is missing.

The synthetic sheet is ``relay_family_fixtures.grz100_pdf`` (the owner sheet's shape, invented numbers).
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
from app.domain.relay_import.engine_adapter import (
    UnsupportedCode,
    adapt_to_engine,
    status_unverified,
    zone_geometry_reviewed,
)
from app.domain.relay_import.provenance import DocumentReference, UnresolvedCause, unresolved
from app.services.relay_pdf_extractor import extract_pdf
from tests import relay_family_fixtures as F
from tests.test_relay_remaining_families import APPLY, VALIDATE, client, decisions, group, items, raw_rows, upload  # noqa: F401

GRZ_JSON = CATALOG_ROOT / "toshiba" / "grz100.json"
CATALOG = "toshiba-grz100-catalog"
MANUAL = "Toshiba 6F2S0834-0 (Ver. 0.3)"
FORWARD, REVERSE = ("Z1", "Z1X", "Z2", "ZF", "Z3"), ("ZR1", "ZR2", "Z4")
TRIPPING = ("Z1", "Z1X", "Z2", "ZF", "Z3", "ZR1", "ZR2", "ZND")
QUADS = ("Z1", "Z1X", "Z2", "ZF", "Z3", "ZR1", "ZR2")

STATUS = ("The zone's settings are configured, but whether it trips in service depends on relay logic that is not "
          "verified (site-specific logic); no Enabled / Disabled state is assumed.")
NOT_TRIPPING = ("The zone's documented function is not a tripping zone the current engine models; its settings are "
                "preserved and it is not drawn.")
RF = ("A source fault-resistance setting is available and its resistive boundary is documented, but the current engine "
      "cannot represent that boundary exactly.")
LEFT = "The Left Resistive Reach (−R) is unresolved."
OFFSET = "A setting that changes this zone's boundary cannot yet be represented by the engine."
OFFSET_BLANK = "A setting that can change this zone's boundary has no configured value in the source."
NON_DIR = "Zone direction 'non_directional' is not supported; the engine models forward and reverse directional zones only."
CHARACTERISTIC = "Characteristic type is unresolved."


def quad(**kw) -> bytes:
    """The owner's selection: Quad for both the phase-fault and the earth-fault elements."""
    return F.grz100_pdf(zg_c="Quad", **kw)


@pytest.fixture(scope="module")
def review(client):
    return upload(client, quad())["review"]


def model_of(pdf: bytes):
    return CatalogInterpreter(default_store().get(CATALOG), canonical_registry()).interpret(extract_pdf(pdf).document)


@pytest.fixture(scope="module")
def model():
    return model_of(quad())


def issues(review) -> dict[str, dict]:
    return {issue["message"]: issue for issue in review["blocking_issues"]}


def cited(item) -> set[str]:
    return {r["reference_id"] for r in item["references"]}


def zone_items(review) -> dict[str, dict]:
    return {k: v for k, v in items(review).items() if k.startswith("zones[")}


class TestDocumentedSemantics:
    def test_the_basis_is_secondary_documented_never_from_the_ratios(self, review):
        basis = items(review)["transformers.setting_basis"]
        assert (basis["value_text"], basis["category"], basis["authority"], basis["blocking"]) == (
            "Secondary", "documented", "documented_derivation", False)
        assert [s["name"] for s in basis["sources"]] == ["Z1S", "Vn"]
        assert not {s["name"] for s in basis["sources"]} & {"CT", "VT"}
        assert "not inferred from the CT / VT ratios" in basis["notes"][0]
        assert cited(basis) == {"toshiba-6f2s0834-0-settings", "toshiba-6f2s0834-0-fault-locator"}

    def test_the_characteristic_selectors_stay_exact_configured_settings(self, review, client):
        ch = items(review)["zones[Z1].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["authority"], ch["raw_value"]) == (
            "Quadrilateral · Explicit R/X", "mapped", "configured_setting", "Quad | Quad")
        assert [s["name"] for s in ch["sources"]] == ["ZS-C", "ZG-C"]
        mixed = items(upload(client, F.grz100_pdf())["review"])["zones[Z1].characteristic.type"]   # Quad / Mho
        assert (mixed["value_text"], mixed["category"]) == ("Unknown · Explicit R/X", "unsupported")

    @pytest.mark.parametrize("zone, expected", [*((z, "Forward") for z in FORWARD), *((z, "Reverse") for z in REVERSE)])
    def test_the_direction_is_fixed_by_the_documented_zone_function(self, review, zone, expected):
        d = items(review)[f"zones[{zone}].direction"]
        assert (d["value_text"], d["category"], d["authority"], d["blocking"]) == (
            expected, "documented", "documented_derivation", False)
        assert cited(d) == {"toshiba-6f2s0834-0-distance", "toshiba-6641-1-brochure"}

    def test_znd_is_documented_non_directional_and_an_engine_limitation(self, review):
        d = items(review)["zones[ZND].direction"]
        assert (d["value_text"], d["category"]) == ("Non directional", "unsupported")
        assert issues(review)[NON_DIR]["zone_ids"] == ["ZND"]

    @pytest.mark.parametrize("field", ["phase_phase_enabled", "phase_earth_enabled"])
    @pytest.mark.parametrize("zone", [*TRIPPING, "Z4"])
    def test_the_phase_and_earth_fault_elements_are_inherent(self, review, zone, field):
        loop = items(review)[f"zones[{zone}].{field}"]
        assert (loop["value_text"], loop["category"], loop["authority"]) == ("Enabled", "documented", "documented_derivation")

    def test_the_earth_fault_element_cites_its_characteristic_selector_and_keeps_its_reach_row(self, review):
        assert [s["name"] for s in items(review)["zones[Z1].phase_earth_enabled"]["sources"]] == ["ZG-C"]
        z1g = raw_rows(review, "Z1")["Z1G"]                                            # the earth X reach is kept visible
        assert (z1g["raw_value"], z1g["blocking"]) == ("5.72", False) and "X reach" in " ".join(z1g["notes"])

    def test_no_artificial_missing_blocker_remains(self, review):
        assert [k for k, v in zone_items(review).items() if v["category"] == "missing"] == []
        msgs = set(issues(review))
        assert not any("Phase-phase operation" in m or "basis" in m or "Zone enabled/disabled status" in m for m in msgs)
        assert not any(i["category"] == "missing" for g in review["groups"] if g["kind"] == "zone" for i in g["items"])

    def test_the_references_are_version_dependent_and_not_the_exact_201a_manual(self, review):
        refs = items(review)["zones[Z1].direction"]["references"]
        assert all("Version-dependent" in r["scope"] for r in refs)
        assert any("not claimed as the exact 201A manual" in r["scope"] for r in refs)


class TestOperationalState:
    """Static geometry is reviewed; the trip state under the site-specific PLC program is not verified."""

    @pytest.mark.parametrize("zone", TRIPPING)
    def test_no_enabled_or_disabled_state_is_invented(self, review, zone):
        st = items(review)[f"zones[{zone}].status"]
        assert (st["value_text"], st["category"], st["blocking"]) == (None, "unverified", True)
        assert st["resolution"] is None and st["suggestion"] is None                  # never asked of the user
        assert group(review, zone)["state_label"] == "Operational status not verified"

    def test_one_unverified_issue_names_every_tripping_zone(self, review):
        issue = issues(review)[STATUS]
        assert (issue["zone_ids"], issue["kind"]) == (list(TRIPPING), "unverified")

    def test_the_default_logic_and_the_plc_program_are_cited(self, review):
        i = items(review)
        z1, zr2, z1x = i["zones[Z1].status"], i["zones[ZR2].status"], i["zones[Z1X].status"]
        assert [s["name"] for s in z1["sources"]] == ["Z1CNT", "PLC data"] and z1["raw_value"] == "4 | TNBGRZ100-01(FFF"
        assert "Z1CNT = 4 irrespective of the command protection" in z1["notes"][0]
        assert "[ZR2BT] is On" in zr2["notes"][0] and "site-specific logic not verified" in zr2["notes"][0]
        assert [s["name"] for s in z1x["sources"]] == ["Protection Scheme", "PLC data"]
        assert "Z1EXT" in z1x["notes"][0] and "Z1X_F.ENABLE" in z1x["notes"][0]
        assert "toshiba-6f2s0834-0-distance" in cited(z1)

    def test_the_backup_trip_switch_does_not_establish_the_state(self, review):
        zfbt = raw_rows(review, "ZF")["ZFBT"]
        assert (zfbt["raw_value"], zfbt["blocking"]) == ("Off", False)
        assert "does not establish the zone's operational state" in " ".join(zfbt["notes"])
        assert items(review)["zones[ZF].status"]["category"] == "unverified"           # Off is not "Disabled"

    def test_the_geometry_stays_available_despite_the_plc_caveat(self, review):
        i = items(review)
        assert [(z, i[f"zones[{z}].x_reach_ohm"]["value_text"]) for z in QUADS] == [
            ("Z1", "5.72 Ω"), ("Z1X", "9.6 Ω"), ("Z2", "7.4 Ω"), ("ZF", "7.4 Ω"), ("Z3", "13 Ω"), ("ZR1", "1.2 Ω"), ("ZR2", "1.6 Ω")]
        assert all(i[f"zones[{z}].x_reach_ohm"]["category"] == "documented" for z in QUADS)
        assert (i["zones[Z2].phase_timer_s"]["value_text"], i["zones[ZND].earth_timer_s"]["value_text"]) == ("0.3 s", "0.7 s")
        assert issues(review)[RF]["zone_ids"] == list(QUADS)                           # reviewed as for a zone in service

    def test_a_status_entry_is_refused(self, client, review):
        body = decisions(review, manual=[{"item_id": "zones[Z2].status", "value": "enabled"}])
        assert client.post(VALIDATE, json=body).status_code == 400

    def test_without_a_plc_row_the_state_is_still_not_asserted(self, client):
        i = items(upload(client, quad(plc=None))["review"])
        assert i["zones[Z2].status"]["category"] == "unverified"                       # the trip logic is programmable

    def test_the_adapter_reviews_an_unverified_zone_and_fails(self, model):
        z1 = model.zone("Z1")
        assert status_unverified(z1) and zone_geometry_reviewed(z1)
        adaptation = adapt_to_engine(replace(model, zones=(z1,)), engine_basis="secondary")
        codes = {r.code for r in adaptation.reasons}
        assert not adaptation.supported and UnsupportedCode.ZONE_STATUS_UNVERIFIED in codes
        assert UnsupportedCode.RESISTIVE_REACH_UNRESOLVED in codes and UnsupportedCode.ZONE_STATUS_UNRESOLVED not in codes


class TestGeometry:
    def test_bfrs_is_unsupported_inclined_geometry_never_a_silent_row(self, review):
        rr = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert (rr["value_text"], rr["raw_value"], rr["category"], rr["blocking"]) == (None, "20", "unsupported", True)
        assert [s["name"] for s in rr["sources"]] == ["BFRS"]
        assert "Rright(X) = BFRS + X * cot 75 deg" in rr["notes"][0]
        assert rr["suggestion"] is None and rr["resolution"] is None
        assert "BFRS" not in raw_rows(review, "Z1")

    def test_the_left_blinder_and_directional_angle_block_with_no_zero_offer(self, client, review):
        left = items(review)["zones[Z1].resistive_reach.reverse"]
        assert (left["raw_value"], left["category"], left["blocking"]) == ("120 | 15", "unsupported", True)
        assert [s["name"] for s in left["sources"]] == ["BFLS-angle", "ZBS-angle (quad)"]
        assert "not fully verified" in left["notes"][0]
        assert left["suggestion"] is None and left["resolution"] is None
        assert issues(review)[LEFT]["zone_ids"] == list(QUADS)
        body = decisions(review)
        assert body["suggested"] == []
        body["suggested"] = ["zones[Z1].resistive_reach.reverse"]
        assert client.post(VALIDATE, json=body).status_code == 400

    def test_the_reverse_blinders_are_unsupported(self, review):
        rr = items(review)["zones[ZR2].resistive_reach.phase_phase"]
        assert (rr["raw_value"], rr["category"], rr["blocking"]) == ("18 | 120", "unsupported", True)
        assert "X <= (R + Rs) * tan 75 deg" in rr["notes"][0]

    def test_the_earth_blinders_are_unsupported_not_missing(self, review):
        pe = items(review)["zones[Z1].resistive_reach.phase_earth"]
        assert (pe["raw_value"], pe["category"], pe["blocking"]) == ("20", "unsupported", False)

    def test_a_horizontal_zone1_line_is_exact_and_a_broken_line_blocks(self, client, review):
        tilt = items(review)["zones[Z1].tilt_deg"]
        assert (tilt["value_text"], tilt["category"], tilt["blocking"]) == ("0°", "mapped", False)
        assert items(review)["zones[Z1X].tilt_deg"]["value_text"] == "0°"            # Zone 1X follows Zone 1's line
        broken = upload(client, quad(z1_angle1="10"))["review"]
        assert items(broken)["zones[Z1].tilt_deg"]["category"] == "unsupported"
        assert any("tilt" in m.lower() for m in issues(broken))

    def test_zone_1x_trips_instantaneously(self, review):
        for t in ("phase_timer_s", "earth_timer_s"):
            item = items(review)[f"zones[Z1X].{t}"]
            assert (item["value_text"], item["category"]) == ("0 s", "documented")
            assert cited(item) == {"toshiba-6f2s0834-0-zone1x"}


class TestReverseOffsetZndAndZ4:
    @pytest.mark.parametrize("zone, value", [("ZR1", "Off"), ("ZR2", "On")])
    def test_the_reverse_zone_offset_is_preserved_and_blocks(self, review, zone, value):
        row = raw_rows(review, zone)[f"{zone}BT"]
        assert (row["raw_value"], row["category"], row["blocking"]) == (value, "unsupported", True)
        text = " ".join(row["notes"])
        assert "fixed at 7.5 ohm" in text and "limited to the Zone 1 reach" in text
        assert issues(review)[OFFSET]["zone_ids"] == ["ZR1", "ZR2"]

    def test_a_blank_backup_trip_switch_is_a_missing_source_value(self, client):
        review = upload(client, quad(bt={"ZR2BT": ""}))["review"]
        row = raw_rows(review, "ZR2")["ZR2BT"]
        assert (row["category"], row["blocking"]) == ("missing", True) and issues(review)[OFFSET_BLANK]["zone_ids"] == ["ZR2"]

    def test_znd_is_a_non_directional_impedance_element_not_a_quadrilateral(self, review):
        i = items(review)
        ch = i["zones[ZND].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["blocking"], ch["raw_value"]) == (None, "unsupported", True, "40 | 50")
        assert "impedance element" in ch["notes"][0] and "circle" in ch["notes"][0]
        assert issues(review)[CHARACTERISTIC]["zone_ids"] == ["ZND"]
        assert i["zones[ZND].reach"]["category"] == "unsupported"

    def test_zone_4_is_kept_as_a_reverse_command_protection_element_and_not_drawn(self, review):
        i = items(review)
        st = i["zones[Z4].status"]
        assert (st["category"], st["blocking"], st["resolution"]) == ("unsupported", True, None)
        assert "not for backup protection" in st["notes"][0]
        assert issues(review)[NOT_TRIPPING]["zone_ids"] == ["Z4"]
        assert i["zones[Z4].direction"]["value_text"] == "Reverse"
        assert all(i[f"zones[Z4].{t}"]["category"] == "not_exposed" for t in ("phase_timer_s", "earth_timer_s"))
        assert all("Z4" not in issue["zone_ids"] for m, issue in issues(review).items() if m != NOT_TRIPPING)
        assert raw_rows(review, "Z4")["Z4G"]["blocking"] is False
        assert i["zones[Z4].resistive_reach.reverse"]["suggestion"] is None          # no 0.00 ohm offer

    def test_the_earth_fault_compensation_is_preserved_not_mapped(self, review, model):
        krs = raw_rows(review, "Z1")["Krs"]
        assert (krs["raw_value"], krs["blocking"]) == ("560", False) and "Not the canonical Kr / Kx" in " ".join(krs["notes"])
        assert raw_rows(review, "ZR1")["KrsR"]["blocking"] is False
        assert all(z.compensation is None for z in model.zones)


class TestMho:
    def test_a_mho_selection_states_no_x_limit_and_invents_nothing(self, client):
        review = upload(client, F.grz100_pdf(zs_c="Mho", zg_c="Mho"))["review"]
        i = items(review)
        assert i["zones[Z1].characteristic.type"]["value_text"] == "Mho"
        assert "zones[Z1].x_reach_ohm" not in i and i["zones[Z1].reach"]["category"] == "unsupported"
        assert [k for k, v in zone_items(review).items() if v["category"] == "missing"] == []


class TestReadiness:
    def test_only_genuine_blockers_remain(self, review):
        assert set(issues(review)) == {STATUS, RF, LEFT, OFFSET, NON_DIR, CHARACTERISTIC, NOT_TRIPPING}

    def test_no_approximation_and_never_ready(self, client, review, model):
        assert APPROVED_RULES == () and model_approximations(model) == ()
        assert review["approximate_count"] == 0 and review["readiness"]["status"] == "not_ready"
        body = decisions(review)
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
            "toshiba-6f2s0834-0-distance": (MANUAL, "verified"), "toshiba-6f2s0834-0-settings": (MANUAL, "verified"),
            "toshiba-6f2s0834-0-zone1x": (MANUAL, "verified"), "toshiba-6f2s0834-0-elements": (MANUAL, "verified"),
            "toshiba-6f2s0834-0-fault-locator": (MANUAL, "verified"), "toshiba-6641-1-brochure": ("Toshiba 6641-1", "verified")}

    def test_the_derivations_are_refused_without_a_verified_reference(self):
        data = json.loads(GRZ_JSON.read_text(encoding="utf-8"))
        for ref in data["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(data, canonical_registry(), source="grz100")
        failing = " ".join(i.path for i in exc.value.issues if i.code == IssueCode.UNVERIFIED_REFERENCE)
        for mapping in ("grz100.basis", "grz100.direction.forward", "grz100.pp_enabled", "grz100.x_reach",
                        "grz100.phase_delay.z1x"):
            assert mapping in failing

    def test_no_resistive_edge_and_no_zone_state_is_mapped_from_a_value(self):
        by = {m["id"]: m for m in json.loads(GRZ_JSON.read_text(encoding="utf-8"))["mappings"]}
        for mid in ("grz100.r_right.forward", "grz100.r_left.forward", "grz100.r_right.reverse", "grz100.r_left.reverse"):
            assert "source" not in by[mid] and "gap" in by[mid]
        states = [m for m in by.values() if m["canonical"] == "distance.zone.status"]
        assert states and all("gap" in m for m in states)

    def test_the_approximation_candidates_are_documented_only(self):
        notes = " ".join(json.loads(GRZ_JSON.read_text(encoding="utf-8"))["interpretation_notes"])
        assert "AGRZ-A" in notes and "AGRZ-B" in notes and "not approved" in notes
        assert not any("AGRZ" in getattr(rule, "rule_id", "") for rule in APPROVED_RULES)


class TestGenericCapabilities:
    def test_always_material_is_exclusive_and_boolean(self):
        data = json.loads(GRZ_JSON.read_text(encoding="utf-8"))
        rule_index = next(k for k, p in enumerate(data["zone_preserved"]) if p.get("always_material"))
        for extra in ({"material_unless": ["x"]}, {"unverified_when": ["x"]}, {"always_material": "yes"}):
            bad = copy.deepcopy(data)
            bad["zone_preserved"][rule_index].update(extra)
            with pytest.raises(CatalogValidationError):
                parse_catalog(bad, canonical_registry(), source="grz100")

    def test_an_unrecognised_status_value_is_not_a_documented_zone_function(self, model):
        # an Unsupported status without a verified reference (e.g. a selector text the catalog does not know) still
        # reads as an unresolved status, never as a documented non-tripping element
        bare = replace(model.zone("Z2"), status=unresolved(cause=UnresolvedCause.UNSUPPORTED))
        codes = {r.code for r in adapt_to_engine(replace(model, zones=(bare,)), engine_basis="secondary").reasons}
        assert UnsupportedCode.ZONE_STATUS_UNRESOLVED in codes and UnsupportedCode.ZONE_STATUS_UNSUPPORTED not in codes
        ref = DocumentReference("r", "t", "verified", "d", "s", "1", "scope")
        documented = replace(bare, status=unresolved(cause=UnresolvedCause.UNSUPPORTED, references=(ref,)))
        codes = {r.code for r in adapt_to_engine(replace(model, zones=(documented,)), engine_basis="secondary").reasons}
        assert codes == {UnsupportedCode.ZONE_STATUS_UNSUPPORTED}


# --- the owner's real sheet (never committed): RELAY_SAMPLE_PDF_DIR -----------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
def test_real_grz100_sheet_lists_only_genuine_blockers(client):
    path = Path(SAMPLE_DIR) / "grz100.pdf"
    if not path.exists():
        pytest.skip("grz100.pdf not available")
    review = upload(client, path.read_bytes())["review"]
    i = items(review)
    assert review["profile_version"] == f"{CATALOG}-v1.1.0" and review["zone_count"] == 9
    # trip state x 8 (PLC) + Zone 4 + inclined +R and -R x 7 + ZR1 / ZR2 offset (2) + ZND characteristic and direction
    assert review["blocking_count"] == 26 and review["readiness"]["status"] == "not_ready"
    assert review["approximate_count"] == 0 and review["unreadable_count"] == 0 and review["unverified_count"] == 8
    assert set(issues(review)) == {STATUS, RF, LEFT, OFFSET, NON_DIR, CHARACTERISTIC, NOT_TRIPPING}
    assert [k for k, v in zone_items(review).items() if v["category"] == "missing"] == []
    assert (i["transformers.setting_basis"]["value_text"], i["transformers.setting_basis"]["category"]) == ("Secondary", "documented")
    assert [i[f"zones[{z}].x_reach_ohm"]["value_text"] for z in QUADS] == [
        "5.72 Ω", "12 Ω", "8.2 Ω", "8.2 Ω", "14.8 Ω", "1.4 Ω", "1.4 Ω"]
    assert i["zones[Z1].status"]["raw_value"] == "4 | TNBGRZ100-01(FFF"
    assert raw_rows(review, "ZR2")["ZR2BT"]["raw_value"] == "On"
    assert decisions(review)["suggested"] == []
