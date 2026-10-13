"""Slice 12 architecture test: a third OEM through the *unchanged* generic pipeline.

    RED670 PDF -> extract -> identify -> profile -> canonical -> review -> readiness
               -> Apply payload -> analysis engine

Nothing here knows the relay: the helpers read generic review/apply DTOs only. If supporting the
RED670 had needed relay-specific review, readiness, Apply or plotting logic, this file could not be
written this way. The one thing RED670 needs from the user is an explicit *visualization approximation*
for its Left Resistive Reach: the relay's real left boundary is the ZDRDIR directional element, a capability
gap the model cannot represent, so the review marks the item Unsupported and offers the same generic 0.00 ohm
suggestion (DEC-185) worded as an approximation, never as the relay's geometry.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.relay_red670_fixtures import default_sections, sheet_pdf, zone_rows

UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"
MANUAL_URL = "/api/v1/workspaces/ws-red/distance-protection-manual"
PRIMARY = "primary"
LEFT = "resistive_reach.reverse"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client, pdf: bytes | None = None, **kw):
    pdf = pdf if pdf is not None else sheet_pdf(**kw)
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200
    return r.json()


def assumptions(review):
    return [
        i["item_id"]
        for g in review["groups"]
        for i in g["items"]
        if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"
    ]


def user_decisions(review, zones=("Z1", "Z2", "Z3")):
    """What an engineer does in the generic review: takes the 0.00 ohm visualization approximation for each
    unsupported Left (-R) reach, then confirms the assumptions."""
    return {
        "validation_context": review["validation_context"],
        "suggested": [f"zones[{z}].{LEFT}" for z in zones],
        "confirmed": assumptions(review),
    }


def to_analysis_zones(payload):
    """The browser's mapping of the generic Apply payload onto the analysis ``zones`` request."""
    out = []
    for z in payload["zones"]:
        item = {"key": z["id"], "enabled": z["enabled"], "direction": z["direction"] or "forward"}
        if z["enabled"]:
            item.update(
                reactive_reach_ohm=z["reactive_reach_ohm"], resistive_reach_forward_ohm=z["resistive_reach_forward_ohm"],
                resistive_reach_reverse_ohm=z["resistive_reach_reverse_ohm"], delay_s=z["delay_s"],
                geometry_mode=z["geometry_mode"],
            )
            if z["characteristic_angle_deg"] is not None:
                item["characteristic_angle_deg"] = z["characteristic_angle_deg"]
        out.append(item)
    return out


def analysis(client, zones, *, z_ohm, z_angle_deg):
    q = dict(
        vt_primary=220000, vt_secondary=110, ct_primary=1200, ct_secondary=1,
        loop_label="AB", voltage_basis=PRIMARY, current_basis=PRIMARY, impedance_basis=PRIMARY, characteristic="quadrilateral",
        v1_enabled=True, v1_magnitude=1000, v1_unit="V", v1_angle_deg=0, v2_enabled=True, v2_magnitude=1000, v2_unit="V", v2_angle_deg=-120,
        i1_enabled=True, i1_magnitude=1000 / z_ohm, i1_unit="A", i1_angle_deg=-z_angle_deg,
        i2_enabled=True, i2_magnitude=1000 / z_ohm, i2_unit="A", i2_angle_deg=-z_angle_deg - 120, zones=json.dumps(zones),
    )
    return client.get(MANUAL_URL, params=q).json()


class TestUploadAndReview:
    def test_upload_identifies_interprets_and_reviews_the_red670(self, client):
        body = upload(client)
        assert (body["identification_status"], body["manufacturer"], body["relay_family"], body["model"], body["profile_id"]) == (
            "identified", "Hitachi Energy", "Relion 670", "RED670", "hitachi-red670",
        )
        assert body["interpretation_status"] == "interpreted" and body["zone_count"] == 4
        review = body["review"]
        assert (review["manufacturer"], review["model"], review["profile_version"]) == ("Hitachi Energy", "RED670", "hitachi-red670-v1")

    def test_the_generic_review_builds_one_group_per_instance_with_the_sheets_own_activation(self, client):
        review = upload(client)["review"]
        zone_groups = [g for g in review["groups"] if g["kind"] == "zone"]
        assert [g["title"] for g in zone_groups] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4"]
        # activation comes from the zones' own parameters: nothing is Missing, nothing is asked of the user
        assert [g["state_label"] for g in zone_groups][:3] == ["Enabled"] * 3
        assert zone_groups[3]["state_label"].startswith("Disabled")
        for g in zone_groups:
            st = next(i for i in g["items"] if i["label"] == "Status")
            assert st["category"] == "mapped" and st["review_status"] == "mapped"

    def test_the_only_blocker_is_the_left_resistive_reach_of_the_zones_in_service(self, client):
        review = upload(client)["review"]
        assert review["readiness"]["status"] == "not_ready"
        assert [b["message"] for b in review["blocking_issues"]] == ["The Left Resistive Reach (−R) is unresolved."]
        assert review["blocking_count"] == 3  # Zones 1-3; the disabled Zone 4 never blocks
        assert review["conflict_count"] == 0 and review["unreadable_count"] == 0
        left = next(i for g in review["groups"] for i in g["items"] if i["item_id"] == f"zones[Z1].{LEFT}")
        # a genuine capability gap, not a missing number: the relay's real boundary is ZDRDIR's angles
        assert left["category"] == "unsupported" and left["value_text"] is None
        assert left["suggestion"] and "0.00" in json.dumps(left["suggestion"])
        assert "approximation" in left["suggestion"]["rationale"] and "not the relay's geometry" in left["suggestion"]["rationale"]
        # the native source of that boundary is cited beside the unsupported value, with its raw angles
        assert {s["name"] for s in left["sources"]} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}
        assert {s["raw_value"] for s in left["sources"]} == {"15", "115"}
        assert "capability gap" in " ".join(left["notes"])

    def test_explicit_rx_zones_show_x_and_resistive_reaches_and_no_fake_angle(self, client):
        review = upload(client)["review"]
        for zid in ("Z1", "Z2", "Z3"):
            group = next(g for g in review["groups"] if g["id"] == f"zone-{zid}")
            labels = [i["label"] for i in group["items"]]
            assert "Reactive Reach (X)" in labels and "Right Resistive Reach (+R)" in labels
            assert "Left Resistive Reach (−R)" in labels and "Earth Resistive Reach" in labels
            assert "Zero-Sequence Reach R" in labels  # preserved, distinct, not plotted
            assert not any("Angle" in label for label in labels) and "Reach" not in labels
            ch = next(i for i in group["items"] if i["label"] == "Characteristic")
            # ZMQPDIS is the quadrilateral function: authoritative family semantics, not an assumption
            assert ch["value_text"] == "Quadrilateral · Explicit R/X" and ch["category"] == "mapped"
            assert ch["authority"] == "documented_derivation"
            labels_all = [i["label"] for i in group["items"]]
            assert "Directional Arg Dir" in labels_all and "Directional Arg Neg Res" in labels_all  # ZDRDIR angles kept

    def test_pp_and_pe_values_are_both_listed_with_their_own_source(self, client):
        review = upload(client)["review"]
        items = {i["item_id"]: i for g in review["groups"] for i in g["items"]}
        pp, pe = items["zones[Z2].resistive_reach.phase_phase"], items["zones[Z2].resistive_reach.phase_earth"]
        # RFPP is a loop value (10 ohm/loop): the phase-phase boundary is 5 ohm; RFPE (20) is used as printed
        assert (pp["value_text"], pe["value_text"]) == ("5 Ω", "20 Ω")
        assert (pp["sources"][0]["name"], pe["sources"][0]["name"]) == ("ZM02-:RFPP", "ZM02-:RFPE")
        assert pp["sources"][0]["raw_value"] == "10" and pp["raw_value"] == "10"  # the OEM value is not lost
        assert "÷ 2" in pp["transformation"] and pe["transformation"] is None
        assert pp["authority"] == "documented_derivation" and pe["authority"] == "configured_setting"
        assert items["zones[Z2].phase_timer_s"]["sources"][0]["name"] in {"ZM02-:Timer tPP", "ZM02-:tPP"}

    def test_scheme_notes_are_document_notes_beside_the_zone(self, client):
        review = upload(client)["review"]
        group = {g["id"]: g for g in review["groups"]}
        assert [n["title"] for n in group["zone-Z1"]["source_notes"]] == ["Zone 1 timer requirement: 0.15 s"]
        assert group["zone-Z4"]["source_notes"][0]["title"] == "Zone 4 status requirement: Inactive (out of service)"

    def test_summary_fields_carry_no_document_values(self, client):
        body = upload(client)
        body.pop("review")
        text = json.dumps(body)
        for content in ("1200", "220000", "SET-TEST-R1", "CTprim1", "0.15", "1.2 "):
            assert content not in text


class TestReadinessAndApply:
    def test_apply_is_refused_until_the_backend_says_ready(self, client):
        review = upload(client)["review"]
        r = client.post(APPLY, json={"validation_context": review["validation_context"]})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "apply_not_ready"

    def test_ready_to_apply_after_the_suggestion_and_confirmations(self, client):
        review = upload(client)["review"]
        body = user_decisions(review)
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        assert out["characteristic"] == "quadrilateral" and out["impedance_basis"] == "primary"
        assert [z["id"] for z in out["zones"]] == ["Z1", "Z2", "Z3", "Z4"]
        z1, z2, z3, z4 = out["zones"]
        assert (z1["enabled"], z1["direction"], z1["reactive_reach_ohm"], z1["resistive_reach_forward_ohm"]) == (True, "forward", 6.0, 3.5)
        assert (z1["resistive_reach_reverse_ohm"], z1["delay_s"]) == (0.0, 0.15)
        assert z1["geometry_mode"] == "explicit_rx" and z1["characteristic_angle_deg"] is None and z1["reach_ohm"] is None
        assert (z2["reactive_reach_ohm"], z2["resistive_reach_forward_ohm"], z2["delay_s"]) == (11.0, 5.0, 0.45)
        assert (z3["reactive_reach_ohm"], z3["resistive_reach_forward_ohm"], z3["delay_s"]) == (20.0, 9.0, 3.0)
        assert z4["enabled"] is False and z4["reactive_reach_ohm"] is None and z4["resistive_reach_forward_ohm"] is None

    def test_the_phase_earth_values_are_not_what_is_applied(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        text = json.dumps(out["zones"][0:3])
        for earth in ("15.0", "20.0", "28.0"):  # RFPE of Z1-Z3
            assert earth not in text.replace("\"reactive_reach_ohm\": 20.0", "")

    def test_payload_is_the_generic_dto_and_holds_no_relay_or_document_data(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        assert set(out) == {"characteristic", "impedance_basis", "zones"}
        text = json.dumps(out)
        for token in ("RED670", "Hitachi", "Relion", "ZM0", "ZMQPDIS", "pdf", "sheet", "raw", "requirement"):
            assert token not in text

    def test_confirming_without_the_suggestion_stays_not_ready(self, client):
        review = upload(client)["review"]
        body = user_decisions(review, zones=())
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "not_ready"
        assert client.post(APPLY, json=body).status_code == 409

    def test_a_zone_switched_off_by_its_own_parameter_is_not_applied_and_needs_no_left_reach(self, client):
        sections = [(label, zone_rows(1, operation="OFF") if label.endswith("ZMQPDIS:1") else rows) for label, rows in default_sections()]
        review = upload(client, sections=sections)["review"]
        body = user_decisions(review, zones=("Z2", "Z3"))
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        assert [z["enabled"] for z in out["zones"]] == [False, True, True, False]

    def test_a_switched_off_timer_is_missing_and_the_user_states_it(self, client):
        sections = [(label, zone_rows(2, timer_gate="OFF") if label.endswith("ZMQPDIS:2") else rows) for label, rows in default_sections()]
        review = upload(client, sections=sections)["review"]
        body = user_decisions(review)
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready"
        assert any("delay is unresolved" in b["message"] for b in state["blocking_issues"])
        body["manual"] = [{"item_id": "zones[Z2].phase_timer_s", "value": 0.45}]
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"

    def test_a_non_directional_zone_in_service_is_refused_not_approximated(self, client):
        sections = [(label, zone_rows(3, direction="Non-dir") if label.endswith("ZMQPDIS:3") else rows) for label, rows in default_sections()]
        review = upload(client, sections=sections)["review"]
        state = client.post(VALIDATE, json=user_decisions(review)).json()
        assert state["readiness"]["status"] == "not_ready"
        assert any("non_directional" in b["message"] for b in state["blocking_issues"])


class TestAnalysisEngine:
    """Apply payload -> the unchanged analysis request/engine: the R-X result (primary ohms)."""

    def _zones(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        return to_analysis_zones(out)

    def _states(self, client, z_ohm, angle):
        body = analysis(client, self._zones(client), z_ohm=z_ohm, z_angle_deg=angle)
        assert body["status"] == "computed"
        return {z["zone_key"]: z["state"] for z in body["zones"]}

    def test_a_forward_fault_inside_every_zone(self, client):
        assert self._states(client, 5, 60) == {"Z1": "operated", "Z2": "operated", "Z3": "operated", "Z4": "not_operated"}

    def test_a_fault_beyond_zone_1_reactive_reach_is_in_zones_2_and_3(self, client):
        s = self._states(client, 8, 60)  # R 4, X 6.93 > 6
        assert (s["Z1"], s["Z2"], s["Z3"]) == ("not_operated", "operated", "operated")

    def test_a_fault_beyond_zone_2_is_in_zone_3_only(self, client):
        s = self._states(client, 15, 60)  # R 7.5, X 12.99 > 11
        assert (s["Z1"], s["Z2"], s["Z3"]) == ("not_operated", "not_operated", "operated")

    def test_a_point_beyond_zone_1_resistive_reach(self, client):
        s = self._states(client, 5, 20)  # R 4.70 > 3.5 (Z1 +R = RFPP 7 / 2) but < 5 (Z2 +R), X 1.71
        assert (s["Z1"], s["Z2"]) == ("not_operated", "operated")

    def test_a_reverse_fault_operates_no_zone_because_all_are_forward(self, client):
        s = self._states(client, 5, 240)
        assert set(s.values()) == {"not_operated"}


# ---------------------------------------------------------------------------
# Real owner sample (not committed): RELAY_SAMPLE_PDF_DIR
# ---------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
needs_sample = pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")


@needs_sample
class TestRealSample:
    @pytest.fixture
    def real(self, client):
        path = Path(SAMPLE_DIR) / "red670.pdf"
        if not path.exists():
            pytest.skip("red670.pdf not available")
        return upload(client, path.read_bytes())

    def test_identified_and_interpreted(self, real):
        assert (real["manufacturer"], real["model"], real["profile_id"], real["confidence"]) == ("Hitachi Energy", "RED670", "hitachi-red670", "high")
        assert real["interpretation_status"] == "interpreted" and real["zone_count"] == 4

    def test_real_blocker_is_only_the_left_reach_of_the_three_zones_in_service(self, real):
        review = real["review"]
        assert review["readiness"]["status"] == "not_ready"
        assert [b["message"] for b in review["blocking_issues"]] == ["The Left Resistive Reach (−R) is unresolved."]
        assert review["blocking_count"] == 3 and review["conflict_count"] == 0 and review["unreadable_count"] == 0

    def test_ready_apply_and_plot_the_real_zones(self, client, real):
        body = user_decisions(real["review"])
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        got = [(z["id"], z["enabled"], z["reactive_reach_ohm"], z["resistive_reach_forward_ohm"], z["delay_s"]) for z in out["zones"]]
        assert got[:3] == [("Z1", True, 7.87, 3.895, 0.15), ("Z2", True, 13.63, 5.835, 0.45), ("Z3", True, 24.97, 10.955, 3.0)]
        assert got[3][:2] == ("Z4", False)
        assert out["impedance_basis"] == "primary"
        # 10 ohm at 80 deg (R 1.7, X 9.85): beyond Zone 1 X (7.87), inside Zone 2 (13.63)
        res = analysis(client, to_analysis_zones(out), z_ohm=10, z_angle_deg=80)
        states = {z["zone_key"]: z["state"] for z in res["zones"]}
        assert (states["Z1"], states["Z2"], states["Z3"], states["Z4"]) == ("not_operated", "operated", "operated", "not_operated")
