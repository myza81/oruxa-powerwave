"""REL511 under DEC-198: documented relay behaviour replaces the artificial blockers; genuine unknowns stay.

* Characteristic (quadrilateral) and the phase-phase / phase-earth loops of every ENABLED zone are documented
  relay behaviour, cited to ABB 1MDB06309-YN (verified; applicability by function / parameter structure only).
  REL511 exposes no selector for them, so a disabled zone shows "not a relay setting", never Missing.
* Still blocking, honestly classified: the impedance basis and the RFZn conversion (Unverified), ZnBlock = On on
  an enabled zone (Unverified, value never interpreted), the left / directional boundary (Unsupported, no 0 ohm
  offer). No approximation exists; REL511 stays Not ready; one review lists every blocker.

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
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry, check_lock, default_store, load_lock
from tests import relay_family_fixtures as F
from tests.test_relay_remaining_families import APPLY, VALIDATE, client, decisions, items, raw_rows, upload  # noqa: F401

REL511_JSON = CATALOG_ROOT / "hitachi_energy" / "rel511.json"
DOCUMENT = "ABB 1MDB06309-YN (issued April 1999; changed since June 1998)"
TITLE = "Line distance protection terminal REL 511"


@pytest.fixture(scope="module")
def review(client):
    return upload(client, F.rel511_pdf())["review"]


def issues(review) -> dict[str, dict]:
    return {issue["message"]: issue for issue in review["blocking_issues"]}


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


class TestGenuineUnknownsStayBlocking:
    def test_the_basis_is_unverified_and_blocking_not_a_missing_row(self, review):
        basis = items(review)["transformers.setting_basis"]
        assert (basis["value_text"], basis["category"], basis["blocking"], basis["resolution"]) == (None, "unverified", True, None)
        assert "has not yet been verified" in basis["notes"][0]
        assert any("has not yet been verified for this relay" in m for m in issues(review))

    def test_rfzn_is_preserved_but_its_conversion_is_unverified_and_blocking(self, review):
        rf = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert (rf["value_text"], rf["category"], rf["raw_value"], rf["blocking"]) == (None, "unverified", "4.6", True)
        assert [s["name"] for s in rf["sources"]] == ["RFZ1"] and rf["resolution"] is None and rf["suggestion"] is None
        assert "has not yet been verified" in rf["notes"][0]
        msgs = issues(review)
        assert ("A source fault-resistance setting is available, but its conversion to the plotted resistive "
                "boundary has not yet been verified.") in msgs
        assert not any("Only a phase-earth resistive reach" in m for m in msgs)       # the misleading wording is gone

    def test_rfnzn_is_preserved_and_unverified_but_not_a_blocker(self, review):
        pe = items(review)["zones[Z1].resistive_reach.phase_earth"]
        assert (pe["value_text"], pe["category"], pe["raw_value"], pe["blocking"]) == (None, "unverified", "15", False)

    def test_znblock_on_in_an_enabled_zone_is_unverified_and_blocking(self, review):
        z1 = raw_rows(review, "Z1")["Z1Block"]
        assert (z1["raw_value"], z1["category"], z1["blocking"], z1["value_text"]) == ("On", "unverified", True, None)
        assert any("not yet verified" in n for n in z1["notes"])
        issue = issues(review)["A setting that may change this zone's operation has a meaning that is not yet verified."]
        assert issue["kind"] == "unverified" and issue["zone_ids"] == ["Z1"]

    def test_znblock_off_in_a_disabled_zone_is_no_active_zone_blocker(self, review):
        z2 = raw_rows(review, "Z2")["Z2Block"]
        assert (z2["raw_value"], z2["blocking"], z2["category"]) == ("Off", False, "unsupported")

    def test_the_left_boundary_is_unsupported_with_no_zero_ohm_offer(self, client, review):
        left = items(review)["zones[Z1].resistive_reach.reverse"]
        assert (left["category"], left["blocking"], left["suggestion"], left["resolution"]) == ("unsupported", True, None, None)
        body = decisions(review)
        body["suggested"] = ["zones[Z1].resistive_reach.reverse"]
        assert client.post(VALIDATE, json=body).status_code == 400                    # nor can it be forced


class TestReadinessAndCompletePicture:
    def test_every_genuine_blocker_is_listed_in_one_review(self, review):
        assert review["blocking_count"] == 4                                          # basis, Z1 +R, Z1 -R, Z1Block
        assert set(issues(review)) == {
            "The primary/secondary basis of the impedance settings has not yet been verified for this relay; it is not inferred.",
            "A setting that may change this zone's operation has a meaning that is not yet verified.",
            "A source fault-resistance setting is available, but its conversion to the plotted resistive boundary has not yet been verified.",
            "The Left Resistive Reach (−R) is unresolved.",
        }
        assert not any("Characteristic" in m or "Phase-phase operation" in m for m in issues(review))

    def test_no_approximation_and_never_ready(self, client, review):
        assert review["approximate_count"] == 0 and review["readiness"]["status"] == "not_ready"
        body = decisions(review)                                                      # confirm every remaining assumption
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready" and state["blocking_count"] == 4
        assert client.post(APPLY, json=body).status_code == 409


class TestCatalog:
    def test_rel511_is_catalog_1_1_0_locked_and_deterministic(self):
        store = default_store()
        catalog = store.get("hitachi-rel511-catalog")
        assert catalog.version == "1.1.0" and catalog.lifecycle == "active"
        assert check_lock(store, load_lock()) == [] and load_lock()["hitachi-rel511-catalog@1.1.0"] == store.digests[catalog.key]
        assert {r.id: r.verification for r in catalog.references} == {"abb-1mdb06309-yn-fig1": "verified", "abb-1mdb06309-yn-p2": "verified"}

    def test_the_derivations_are_refused_without_the_verified_reference(self):
        data = json.loads(REL511_JSON.read_text(encoding="utf-8"))
        without = copy.deepcopy(data)
        for ref in without["references"]:
            ref["verification"] = "unverified"
        with pytest.raises(CatalogValidationError) as exc:
            parse_catalog(without, canonical_registry(), source="rel511")
        assert IssueCode.UNVERIFIED_REFERENCE in exc.value.codes()

    def test_no_basis_or_rf_conversion_is_mapped(self):
        data = json.loads(REL511_JSON.read_text(encoding="utf-8"))
        by = {m["id"]: m for m in data["mappings"]}
        assert "gap" in by["rel511.basis"] and by["rel511.basis"]["gap"]["kind"] == "unverified"
        assert by["rel511.r_right"]["gap"]["kind"] == "unverified" and "transform" not in by["rel511.r_right"]
        assert by["rel511.r_phase_earth"]["gap"]["kind"] == "unverified"
        assert "kind" not in by["rel511.r_left"]["gap"]                               # unsupported (default)
        assert "version_pattern" not in data["identification"]


# --- the owner's real sheet (never committed): RELAY_SAMPLE_PDF_DIR -----------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
def test_real_rel511_sheet_lists_only_genuine_blockers(client):
    path = Path(SAMPLE_DIR) / "rel511.pdf"
    if not path.exists():
        pytest.skip("rel511.pdf not available")
    review = upload(client, path.read_bytes())["review"]
    i = items(review)
    assert review["profile_version"] == "hitachi-rel511-catalog-v1.1.0"
    # 1 basis + 4 enabled zones x (+R conversion, -R boundary, ZnBlock = On)
    assert review["blocking_count"] == 13 and review["readiness"]["status"] == "not_ready"
    assert review["documented_count"] == 12 and review["approximate_count"] == 0
    assert all(i[f"zones[Z{n}].characteristic.type"]["category"] == "documented" for n in (1, 2, 3, 4))
    assert i["zones[Z5].characteristic.type"]["category"] == "not_exposed"            # Zone 5 is switched off
    by_message = issues(review)
    assert by_message["A setting that may change this zone's operation has a meaning that is not yet verified."]["zone_ids"] == [
        "Z1", "Z2", "Z3", "Z4"]
    assert len(by_message) == 4
