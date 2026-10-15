"""REL511 under DEC-198: documented relay behaviour replaces the artificial blockers; genuine unknowns stay.

* Characteristic (quadrilateral) and the phase-phase / phase-earth loops of every ENABLED zone are documented
  relay behaviour, cited to ABB 1MDB06309-YN (verified; applicability by function / parameter structure only).
  REL511 exposes no selector for them, so a disabled zone shows "not a relay setting", never Missing.
* Amendment 2 (catalog 1.2.0, ABB REL 511 2.3 / 2.5 manuals): the impedance basis is Secondary and RFNZn is the
  phase-earth fault-resistance reach in ohm/loop -- both documented relay behaviour. RFZn's meaning is documented
  too (phase-phase, ohm/loop, an inclined per-phase boundary), but the engine cannot draw that boundary: its +R is
  Unsupported (an engine limitation, no longer Unverified) and keeps the raw value and the exact relation.
* Still blocking: ZnBlock = On on an enabled zone (Unverified, value never interpreted), the RFZn boundary and the
  left / directional boundary (Unsupported, no 0 ohm offer). No approximation exists; REL511 stays Not ready.

The synthetic sheet (``relay_family_fixtures.rel511_pdf``): Zone 1 On (Z1Block On), Zone 2 Off (Z2Block Off).
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
from tests.test_relay_remaining_families import APPLY, VALIDATE, client, decisions, items, raw_rows, upload  # noqa: F401

REL511_JSON = CATALOG_ROOT / "hitachi_energy" / "rel511.json"
DOCUMENT = "ABB 1MDB06309-YN (issued April 1999; changed since June 1998)"
TITLE = "Line distance protection terminal REL 511"
TRM = "ABB 1MRK 506 101-UEN (version 2.3, May 2001)"
APP = "ABB 1MRK 506 109-UEN (version 2.3, July 2001)"
COMMISSIONING = "ABB 1MRK 506 167-UEN (revision B, December 2006)"

RF_UNSUPPORTED = ("A source fault-resistance setting is available and its resistive boundary is documented, but the "
                  "current engine cannot represent that boundary exactly.")
ZNBLOCK = "A setting that may change this zone's operation has a meaning that is not yet verified."
LEFT = "The Left Resistive Reach (−R) is unresolved."


@pytest.fixture(scope="module")
def review(client):
    return upload(client, F.rel511_pdf())["review"]


@pytest.fixture(scope="module")
def model():
    catalog = default_store().get("hitachi-rel511-catalog")
    return CatalogInterpreter(catalog, canonical_registry()).interpret(extract_pdf(F.rel511_pdf()).document)


def issues(review) -> dict[str, dict]:
    return {issue["message"]: issue for issue in review["blocking_issues"]}


def cited(item) -> list[tuple[str, str, str]]:
    return [(r["reference_id"], r["document"], r["verification"]) for r in item["references"]]


class TestDocumentedRelayBehaviour:
    def test_the_characteristic_is_documented_quadrilateral_cited_to_the_abb_reference(self, review):
        ch = items(review)["zones[Z1].characteristic.type"]
        assert (ch["value_text"], ch["category"], ch["status"], ch["authority"]) == (
            "Quadrilateral · Explicit R/X", "documented", "mapped", "documented_derivation")
        assert [(r["reference_id"], r["title"], r["document"], r["section"], r["page"], r["verification"]) for r in ch["references"]] == [
            ("abb-1mdb06309-yn-fig1", TITLE, DOCUMENT, "Fig. 1", "2-3", "verified")]
        # the applicability limitation travels with the provenance
        assert "not on a confirmed firmware-version match" in ch["references"][0]["scope"]
        # cited evidence: the zone's own reactance setting and its Operation switch (enabled zone only)
        assert {s["name"] for s in ch["sources"]} == {"X1Z1", "Operation_Z1"}
        # the reference does not claim the engine reproduces the line-angle-adjusted resistive lines
        assert "does not reproduce" in " ".join(ch["notes"])

    @pytest.mark.parametrize("path", ["zones[Z1].phase_phase_enabled", "zones[Z1].phase_earth_enabled"])
    def test_phase_phase_and_phase_earth_loops_are_documented_behaviour(self, review, path):
        loop = items(review)[path]
        assert (loop["value_text"], loop["category"], loop["authority"], loop["review_status"]) == (
            "Enabled", "documented", "documented_derivation", "mapped")             # not an assumption to confirm
        assert [(r["reference_id"], r["page"], r["verification"]) for r in loop["references"]] == [
            ("abb-1mdb06309-yn-p2", "2", "verified")]

    @pytest.mark.parametrize("field", ["characteristic.type", "phase_phase_enabled", "phase_earth_enabled"])
    def test_a_disabled_zone_shows_the_selectors_as_not_exposed_never_missing(self, review, field):
        item = items(review)[f"zones[Z2].{field}"]
        assert item["value_text"] is None and item["category"] == "not_exposed"
        assert not item["blocking"] and item["resolution"] is None and item["suggestion"] is None
        assert "no " in item["notes"][0] and "selector" in item["notes"][0]

    def test_no_zone_characteristic_or_loop_is_reported_missing(self, review):
        wanted = ("characteristic.type", "phase_phase_enabled", "phase_earth_enabled")
        assert not [p for p, i in items(review).items() if p.endswith(wanted) and i["category"] == "missing"]

    def test_the_scheme_marker_is_not_asserted_as_the_firmware_version(self, review):
        i = items(review)
        assert i["metadata.version"]["value_text"] is None
        assert i["metadata.scheme_name"]["value_text"] == "REL511_V1.2_TNB"           # kept as the scheme name


class TestDocumentedBasis:
    def test_the_basis_is_secondary_documented_relay_behaviour(self, review):
        basis = items(review)["transformers.setting_basis"]
        assert (basis["value_text"], basis["category"], basis["authority"], basis["blocking"]) == (
            "Secondary", "documented", "documented_derivation", False)
        assert basis["resolution"] is None and basis["suggestion"] is None          # not a decision for the user
        assert cited(basis) == [("abb-1mrk506109-uen-conv", APP, "verified"), ("abb-1mrk506101-uen-zm", TRM, "verified")]
        assert [s["name"] for s in basis["sources"]] == ["Ir"]                        # the rated current the ranges refer to
        assert not any("basis" in m for m in issues(review))

    def test_the_basis_is_never_derived_from_the_ct_vt_ratios(self, review):
        basis = items(review)["transformers.setting_basis"]
        assert "Not inferred from the CT / VT ratios" in basis["notes"][0]
        assert not {s["name"] for s in basis["sources"]} & {"CTPrim Iphases", "VTPrim Uphases", "Ur"}

    def test_the_applicability_limit_is_kept_with_the_references(self, review):
        for ref in items(review)["transformers.setting_basis"]["references"]:
            assert "likely but version-dependent" in ref["scope"] and "not a firmware-version match" in ref["scope"]


class TestFaultResistanceSemantics:
    def test_rfzn_is_documented_but_its_inclined_boundary_is_unsupported_not_unverified(self, review):
        rf = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert (rf["value_text"], rf["category"], rf["raw_value"], rf["blocking"]) == (None, "unsupported", "4.6", True)
        assert [s["name"] for s in rf["sources"]] == ["RFZ1"] and rf["resolution"] is None and rf["suggestion"] is None
        assert "phase-phase fault-resistance reach in ohm/loop" in rf["notes"][0]
        assert "has not yet been verified" not in rf["notes"][0]
        assert {r["reference_id"] for r in rf["references"]} == {
            "abb-1mrk506109-uen-pp", "abb-1mrk506101-uen-zm", "abb-1mrk506167-uen-zm"}

    def test_the_exact_documented_boundary_is_preserved_in_the_provenance(self, review, model):
        note = items(review)["zones[Z1].resistive_reach.phase_phase"]["notes"][0]
        assert "X <= X1Z1" in note
        assert "Rright(X) = R1Z1 * X / X1Z1 + RFZ1 / 2" in note and "Rleft(X) = R1Z1 * X / X1Z1 - RFZ1 / 2" in note
        pp = model.zone("Z1").resistive_reach.phase_phase
        assert not pp.is_resolved and pp.provenance.cause is UnresolvedCause.UNSUPPORTED
        assert pp.provenance.raw_value == "4.6" and pp.provenance.notes == (note,)
        assert all(r.verified for r in pp.provenance.references)

    def test_the_geometry_is_recorded_in_the_model_metadata(self, model):
        notes = " ".join(model.interpretation_notes)
        assert ("top X <= X1Zn; right R <= R1Zn * X / X1Zn + RFZn / 2; left R >= R1Zn * X / X1Zn - RFZn / 2") in notes
        assert "ArgDir in the fourth quadrant (5-45 deg" in notes and "ArgNegRes in the second quadrant (90-175 deg" in notes
        assert "rotated 180 deg" in notes

    def test_the_engine_reason_is_an_engine_limitation_worded_as_such(self, review):
        msgs = issues(review)
        assert msgs[RF_UNSUPPORTED]["kind"] == "" and msgs[RF_UNSUPPORTED]["zone_ids"] == ["Z1"]
        assert not any("Only a phase-earth resistive reach" in m for m in msgs)       # RFNZn is not the reason
        assert not any("has not yet been verified" in m for m in msgs)

    def test_rfnzn_is_documented_phase_earth_ohm_per_loop_and_never_blocks(self, review):
        pe = items(review)["zones[Z1].resistive_reach.phase_earth"]
        assert (pe["value_text"], pe["category"], pe["authority"], pe["raw_value"], pe["blocking"]) == (
            "15 Ω", "documented", "documented_derivation", "15", False)
        assert [s["name"] for s in pe["sources"]] == ["RFNZ1"]
        note = " ".join(pe["notes"])
        assert "loop-domain quantity" in note and "(2 * R1Zn + R0Zn) / 3 + RFNZn" in note
        assert "not halved and not converted into a phase-phase reach" in note
        assert {r["reference_id"] for r in pe["references"]} == {
            "abb-1mrk506109-uen-pe", "abb-1mrk506101-uen-zm", "abb-1mrk506167-uen-zm"}

    def test_rfnzn_is_not_turned_into_a_phase_phase_reach(self, model):
        rr = model.zone("Z1").resistive_reach
        assert rr.phase_earth.value == 15.0                                           # as printed, not halved
        assert not rr.phase_phase.is_resolved and not rr.common.is_resolved


class TestGenuineUnknownsStayBlocking:
    def test_znblock_on_in_an_enabled_zone_is_unverified_and_blocking(self, review):
        z1 = raw_rows(review, "Z1")["Z1Block"]
        assert (z1["raw_value"], z1["category"], z1["blocking"], z1["value_text"]) == ("On", "unverified", True, None)
        assert any("not yet verified" in n for n in z1["notes"])
        issue = issues(review)[ZNBLOCK]
        assert issue["kind"] == "unverified" and issue["zone_ids"] == ["Z1"]

    def test_znblock_off_in_a_disabled_zone_is_no_active_zone_blocker(self, review):
        z2 = raw_rows(review, "Z2")["Z2Block"]
        assert (z2["raw_value"], z2["blocking"], z2["category"]) == ("Off", False, "unsupported")

    def test_the_left_boundary_is_unsupported_with_no_zero_ohm_offer(self, client, review):
        left = items(review)["zones[Z1].resistive_reach.reverse"]
        assert (left["category"], left["blocking"], left["suggestion"], left["resolution"]) == ("unsupported", True, None, None)
        assert "R = R1Z1 * X / X1Z1 - RFZ1 / 2" in left["notes"][0] and "no left boundary is drawn or approximated" in left["notes"][0]
        body = decisions(review)
        body["suggested"] = ["zones[Z1].resistive_reach.reverse"]
        assert client.post(VALIDATE, json=body).status_code == 400                    # nor can it be forced


class TestReadinessAndCompletePicture:
    def test_every_genuine_blocker_is_listed_in_one_review(self, review):
        assert review["blocking_count"] == 3                                          # Z1 +R, Z1 -R, Z1Block
        assert set(issues(review)) == {ZNBLOCK, RF_UNSUPPORTED, LEFT}
        assert not any("Characteristic" in m or "Phase-phase operation" in m for m in issues(review))

    def test_no_approximation_and_never_ready(self, client, review, model):
        assert APPROVED_RULES == () and model_approximations(model) == ()
        assert review["approximate_count"] == 0 and review["readiness"]["status"] == "not_ready"
        body = decisions(review)                                                      # confirm every remaining assumption
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready" and state["blocking_count"] == 3
        assert client.post(APPLY, json=body).status_code == 409


class TestCatalog:
    def test_rel511_is_catalog_1_2_0_locked_and_deterministic(self):
        store = default_store()
        catalog = store.get("hitachi-rel511-catalog")
        assert catalog.version == "1.2.0" and catalog.lifecycle == "active"
        lock = load_lock()
        assert check_lock(store, lock) == [] and lock["hitachi-rel511-catalog@1.2.0"] == store.digests[catalog.key]
        assert {"hitachi-rel511-catalog@1.0.0", "hitachi-rel511-catalog@1.1.0"} <= set(lock)  # earlier versions kept
        assert {r.id: (r.document, r.verification) for r in catalog.references} == {
            "abb-1mdb06309-yn-fig1": (DOCUMENT, "verified"), "abb-1mdb06309-yn-p2": (DOCUMENT, "verified"),
            "abb-1mrk506101-uen-zm": (TRM, "verified"), "abb-1mrk506109-uen-conv": (APP, "verified"),
            "abb-1mrk506109-uen-pp": (APP, "verified"), "abb-1mrk506109-uen-pe": (APP, "verified"),
            "abb-1mrk506167-uen-zm": (COMMISSIONING, "verified"),
        }

    def test_the_derivations_are_refused_without_the_verified_reference(self):
        data = json.loads(REL511_JSON.read_text(encoding="utf-8"))
        without = copy.deepcopy(data)
        for ref in without["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(without, canonical_registry(), source="rel511")
        assert IssueCode.UNVERIFIED_REFERENCE in exc.value.codes()
        failing = " ".join(i.path for i in exc.value.issues if i.code == IssueCode.UNVERIFIED_REFERENCE)
        assert "rel511.basis" in failing and "rel511.r_phase_earth" in failing

    def test_basis_and_rf_semantics_are_mapped_but_no_plotted_reach_is(self):
        data = json.loads(REL511_JSON.read_text(encoding="utf-8"))
        by = {m["id"]: m for m in data["mappings"]}
        basis = by["rel511.basis"]
        assert basis["transform"] == {"type": "constant", "value": "secondary"} and basis["verification"] == "verified"
        assert all("ratio" not in json.dumps(e).lower() for e in basis["evidence"])
        right = by["rel511.r_right"]
        assert "kind" not in right["gap"] and "transform" not in right and "source" not in right   # unsupported, not mapped
        pe = by["rel511.r_phase_earth"]
        assert pe["source"]["name"] == "RFNZ{n}" and "transform" not in pe and pe["verification"] == "verified"
        assert "kind" not in by["rel511.r_left"]["gap"]                               # unsupported (default)
        assert [p["unverified_when"] for p in data["zone_preserved"]] == [["on"]]      # ZnBlock handling unchanged
        assert "version_pattern" not in data["identification"]

    def test_the_only_semantic_unknown_left_is_znblock(self):
        data = json.loads(REL511_JSON.read_text(encoding="utf-8"))
        assert [m["id"] for m in data["mappings"] if m.get("gap", {}).get("kind") == "unverified"] == []
        assert [p["names"] for p in data["zone_preserved"] if p.get("unverified_when")] == [["Z{n}Block"]]


# --- the owner's real sheet (never committed): RELAY_SAMPLE_PDF_DIR -----------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
def test_real_rel511_sheet_lists_only_genuine_blockers(client):
    path = Path(SAMPLE_DIR) / "rel511.pdf"
    if not path.exists():
        pytest.skip("rel511.pdf not available")
    review = upload(client, path.read_bytes())["review"]
    i = items(review)
    assert review["profile_version"] == "hitachi-rel511-catalog-v1.2.0"
    # 4 enabled zones x (RFZn boundary, -R boundary, ZnBlock = On); the basis no longer blocks
    assert review["blocking_count"] == 12 and review["readiness"]["status"] == "not_ready"
    # characteristic / PP / PE x Zones 1-4, the basis, RFNZn x Zones 1-5
    assert review["documented_count"] == 18 and review["approximate_count"] == 0
    assert review["unverified_count"] == 4                                            # ZnBlock = On, Zones 1-4
    assert i["transformers.setting_basis"]["value_text"] == "Secondary"
    assert all(i[f"zones[Z{n}].characteristic.type"]["category"] == "documented" for n in (1, 2, 3, 4))
    assert all(i[f"zones[Z{n}].resistive_reach.phase_phase"]["category"] == "unsupported" for n in (1, 2, 3, 4))
    assert [i[f"zones[Z{n}].resistive_reach.phase_phase"]["raw_value"] for n in (1, 2, 3, 4)] == ["4.62", "6.77", "11.87", "1.15"]
    assert [i[f"zones[Z{n}].resistive_reach.phase_earth"]["value_text"] for n in (1, 2, 3, 4)] == [
        "15.39 Ω", "17.5 Ω", "23.26 Ω", "3.85 Ω"]
    assert i["zones[Z5].characteristic.type"]["category"] == "not_exposed"            # Zone 5 is switched off
    by_message = issues(review)
    assert set(by_message) == {ZNBLOCK, RF_UNSUPPORTED, LEFT}
    assert by_message[ZNBLOCK]["zone_ids"] == ["Z1", "Z2", "Z3", "Z4"]
    assert by_message[RF_UNSUPPORTED]["zone_ids"] == ["Z1", "Z2", "Z3", "Z4"]
