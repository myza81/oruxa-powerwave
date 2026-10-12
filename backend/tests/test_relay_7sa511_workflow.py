"""Slice 11 architecture test: a second OEM through the *unchanged* generic pipeline.

    7SA511 PDF -> extract -> identify -> profile -> canonical -> review -> readiness
               -> Apply payload -> analysis engine

Nothing here knows the relay: the helpers read generic review/apply DTOs only. If supporting the
7SA511 had needed relay-specific review, readiness, Apply or plotting logic, this file could not be
written this way.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.relay_7sa511_fixtures import FINITE_TIMERS, sheet_pdf

UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"
MANUAL_URL = "/api/v1/workspaces/ws-7sa/distance-protection-manual"
SEC = "secondary"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client, **kw):
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(sheet_pdf(**kw)), "application/pdf")})
    assert r.status_code == 200
    return r.json()


def assumptions(review):
    return [
        i["item_id"]
        for g in review["groups"]
        for i in g["items"]
        if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"
    ]


def user_decisions(review, *, timers=True):
    """What an engineer does in the generic review: states which zones are in service, a delay for
    each (the sheet leaves the timer cells blank), accepts the 0.00 ohm suggestion for the missing Left (-R) reach,
    then confirms the assumptions."""
    manual = [
        {"item_id": "zones[Z1].status", "value": "enabled"},
        {"item_id": "zones[Z2].status", "value": "enabled"},
        {"item_id": "zones[Z3].status", "value": "enabled"},
        {"item_id": "zones[Z4].status", "value": "disabled"},
        {"item_id": "zones[Z1B].status", "value": "disabled"},
        {"item_id": "zones[Z1L].status", "value": "disabled"},
    ]
    if timers:
        manual += [
            {"item_id": "zones[Z1].phase_timer_s", "value": 0.15},
            {"item_id": "zones[Z2].phase_timer_s", "value": 0.45},
            {"item_id": "zones[Z3].common_timer_s", "value": 3},
        ]
    return {
        "validation_context": review["validation_context"],
        "manual": manual,
        "suggested": [f"zones[{z}].resistive_reach.reverse" for z in ("Z1", "Z2", "Z3")],
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
            if z["characteristic_angle_deg"] is not None:  # an explicit R/X zone carries no angle
                item["characteristic_angle_deg"] = z["characteristic_angle_deg"]
        out.append(item)
    return out


def analysis(client, zones, *, current):
    q = dict(
        loop_label="AB", voltage_basis=SEC, current_basis=SEC, impedance_basis=SEC, characteristic="quadrilateral",
        v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0, v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
        i1_enabled=True, i1_magnitude=current[0], i1_unit="A", i1_angle_deg=current[1],
        i2_enabled=True, i2_magnitude=current[0], i2_unit="A", i2_angle_deg=current[1] - 120, zones=json.dumps(zones),
    )
    return client.get(MANUAL_URL, params=q).json()


class TestUploadAndReview:
    def test_upload_identifies_interprets_and_reviews_the_7sa511(self, client):
        body = upload(client)
        assert (body["identification_status"], body["manufacturer"], body["model"], body["profile_id"]) == (
            "identified", "Siemens", "7SA511", "siemens-7sa511",
        )
        assert body["interpretation_status"] == "interpreted" and body["zone_count"] == 6
        review = body["review"]
        assert (review["manufacturer"], review["model"], review["profile_version"]) == ("Siemens", "7SA511", "siemens-7sa511-v2")

    def test_the_generic_review_builds_one_group_per_zone_with_the_sheets_own_labels(self, client):
        review = upload(client)["review"]
        zone_groups = [g for g in review["groups"] if g["kind"] == "zone"]
        assert [g["title"] for g in zone_groups] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 1B", "Zone 1L"]
        # the sheet's Zone 1B "inactive" line is a document note: it states no current zone state
        assert zone_groups[4]["state_label"] == "Status unresolved"
        assert [g["state_label"] for g in zone_groups] == ["Status unresolved"] * 6

    def test_counts_and_blockers_are_reported_by_the_generic_taxonomy(self, client):
        review = upload(client)["review"]
        assert review["readiness"]["status"] == "not_ready"
        assert review["assumption_count"] > 0 and review["missing_count"] > 0 and review["blocking_count"] > 0
        assert review["conflict_count"] == 0 and review["unreadable_count"] == 0
        messages = {b["message"] for b in review["blocking_issues"]}
        assert "Zone enabled/disabled status is unresolved." in messages

    def test_provenance_is_available_for_every_listed_value(self, client):
        review = upload(client)["review"]
        x2 = next(i for g in review["groups"] for i in g["items"] if i["item_id"] == "zones[Z2].x_reach_ohm")
        assert x2["label"] == "Reactive Reach (X)" and x2["category"] == "mapped"
        assert x2["sources"][0]["code"] == "1312" and x2["sources"][0]["name"] == "X2"
        timer = next(i for g in review["groups"] for i in g["items"] if i["item_id"] == "zones[Z2].phase_timer_s")
        assert timer["category"] == "missing" and timer["raw_value"] is None and timer["value_text"] is None

    def test_explicit_rx_zones_show_x_and_resistive_reaches_and_no_fake_angle(self, client):
        review = upload(client)["review"]
        for zid in ("Z1", "Z2", "Z3"):
            group = next(g for g in review["groups"] if g["id"] == f"zone-{zid}")
            labels = [i["label"] for i in group["items"]]
            assert "Reactive Reach (X)" in labels and "Right Resistive Reach (+R)" in labels
            assert "Left Resistive Reach (−R)" in labels and "Earth Resistive Reach" in labels
            assert not any("Angle" in label for label in labels) and "Reach" not in labels
            ch = next(i for i in group["items"] if i["label"] == "Characteristic")
            assert ch["value_text"] == "Quadrilateral · Explicit R/X"

    def test_page_5_requirements_are_shown_as_document_notes_beside_the_zone(self, client):
        review = upload(client)["review"]
        group = {g["id"]: g for g in review["groups"]}
        z1 = group["zone-Z1"]["source_notes"]
        assert [(n["kind_label"], n["title"]) for n in z1] == [
            ("Document note / proposed requirement", "Zone 1 timer requirement: 0.15 s")
        ]
        assert z1[0]["sources"] and z1[0]["text"].startswith("Zone 1")
        assert group["zone-Z1B"]["source_notes"][0]["title"] == "Zone 1B status requirement: Inactive (out of service)"
        # a note is never a value: the zone's own timer still shows nothing
        timer = next(i for i in group["zone-Z1"]["items"] if i["item_id"] == "zones[Z1].phase_timer_s")
        assert timer["value_text"] is None and "0.15" not in json.dumps(timer)

    def test_summary_fields_carry_no_document_values(self, client):
        body = upload(client)
        body.pop("review")
        text = json.dumps(body)
        for content in ("800", "110", "0.371", "1312", "X2", "Un PRIMARY", "TOWARDS LINE"):
            assert content not in text


class TestReadinessAndApply:
    def test_apply_is_refused_until_the_backend_says_ready(self, client):
        review = upload(client)["review"]
        r = client.post(APPLY, json={"validation_context": review["validation_context"]})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "apply_not_ready"

    def test_the_real_blocker_is_zone_state_and_delay_not_a_siemens_rule(self, client):
        review = upload(client)["review"]
        body = user_decisions(review, timers=False)
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready"
        assert any("delay is unresolved" in b["message"] for b in state["blocking_issues"])

    def test_ready_to_apply_after_the_users_decisions(self, client):
        review = upload(client)["review"]
        body = user_decisions(review)
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "ready"
        r = client.post(APPLY, json=body)
        assert r.status_code == 200
        out = r.json()
        assert out["characteristic"] == "quadrilateral" and out["impedance_basis"] == "secondary"
        assert [z["id"] for z in out["zones"]] == ["Z1", "Z2", "Z3", "Z4", "Z1B", "Z1L"]
        z1, z2, z3, z4, z1b, z1l = out["zones"]
        assert (z1["enabled"], z1["direction"], z1["reactive_reach_ohm"], z1["resistive_reach_forward_ohm"]) == (True, "forward", 3.0, 2.0)
        assert (z1["resistive_reach_reverse_ohm"], z1["delay_s"]) == (0.0, 0.15)
        # explicit R/X travels through Apply as it is: no angle, never converted to a polar reach
        assert z1["geometry_mode"] == "explicit_rx" and z1["characteristic_angle_deg"] is None and z1["reach_ohm"] is None
        assert all(z["geometry_mode"] == "explicit_rx" for z in (z2, z3))
        assert (z2["reactive_reach_ohm"], z2["resistive_reach_forward_ohm"], z2["delay_s"]) == (5.0, 3.0, 0.45)
        assert (z3["direction"], z3["delay_s"]) == ("reverse", 3.0)
        for z in (z4, z1b, z1l):  # disabled zones are present but carry no geometry
            assert z["enabled"] is False and z["reactive_reach_ohm"] is None and z["resistive_reach_forward_ohm"] is None
            assert z["characteristic_angle_deg"] is None

    def test_the_phase_earth_resistive_reach_is_not_what_is_applied(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        assert out["zones"][0]["resistive_reach_forward_ohm"] == 2.0  # R1 (phase-phase), not R1E = 6.0
        assert "6.0" not in json.dumps(out["zones"][0:3])

    def test_payload_is_the_generic_dto_and_holds_no_relay_or_document_data(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        assert set(out) == {"characteristic", "impedance_basis", "zones"}
        assert all(set(z) <= {"id", "display_name", "enabled", "direction", "delay_s", "geometry_mode", "characteristic_angle_deg",
                              "reach_ohm", "reactive_reach_ohm", "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm"}
                   for z in out["zones"])
        text = json.dumps(out)
        for token in ("7SA", "Siemens", "SIPROTEC", "DIGSI", "pdf", "sheet", "Infinity", "raw", "requirement"):
            assert token not in text

    def test_a_blocking_zone_stays_blocking_enabled_zone_4_cannot_be_applied(self, client):
        review = upload(client)["review"]
        body = user_decisions(review)
        body["manual"] = [m for m in body["manual"] if m["item_id"] != "zones[Z4].status"] + [{"item_id": "zones[Z4].status", "value": "enabled"}]
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready"
        assert client.post(APPLY, json=body).status_code == 409

    def test_the_finite_delay_variant_needs_no_timer_entry(self, client):
        review = upload(client, overrides=FINITE_TIMERS)["review"]
        body = user_decisions(review, timers=False)
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        out = client.post(APPLY, json=body).json()
        assert [z["delay_s"] for z in out["zones"][:3]] == [0.15, 0.45, 3.0]

    def test_the_users_zone_1b_choice_is_needed_because_the_note_states_nothing(self, client):
        review = upload(client)["review"]
        body = user_decisions(review)
        body["manual"] = [m for m in body["manual"] if m["item_id"] != "zones[Z1B].status"]
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready"
        assert any(b["zone_ids"] == ["Z1B"] or "Z1B" in b["zone_ids"] for b in state["blocking_issues"])

    def test_a_10_s_delay_is_disabled_by_the_generic_rule_and_not_applied(self, client):
        ten = {"1405": ("T1B 1PHASE", "10", "0.00-32.00 s"), "1406": ("T1B >1PHASE", "10", "0.00-32.00 s"),
               "1305": ("T1 1PHASE", "10", "0.00-32.00 s"), "1306": ("T1 >1PHASE", "10", "0.00-32.00 s")}
        review = upload(client, overrides=ten)["review"]
        z1 = next(g for g in review["groups"] if g["id"] == "zone-Z1")
        assert z1["state_label"] == "Disabled" and "10.0 s" in (z1["state_note"] or "")


class TestAnalysisEngine:
    """Apply payload -> the unchanged analysis request/engine: the R-X result."""

    def _zones(self, client):
        out = client.post(APPLY, json=user_decisions(upload(client)["review"])).json()
        return to_analysis_zones(out)

    def test_a_forward_fault_inside_zones_1_and_2_only(self, client):
        body = analysis(client, self._zones(client), current=(100, -20))  # Z = 1 ohm at 20 deg
        states = {z["zone_key"]: z["state"] for z in body["zones"]}
        assert body["status"] == "computed"
        assert states == {"Z1": "operated", "Z2": "operated", "Z3": "not_operated", "Z4": "not_operated", "Z1B": "not_operated", "Z1L": "not_operated"}

    def test_a_reverse_fault_operates_the_reverse_zone_3_only(self, client):
        body = analysis(client, self._zones(client), current=(100, 160))
        states = {z["zone_key"]: z["state"] for z in body["zones"]}
        assert states["Z3"] == "operated" and states["Z1"] == states["Z2"] == "not_operated"

    def test_a_point_beyond_zone_1_resistive_reach_but_inside_zone_2(self, client):
        body = analysis(client, self._zones(client), current=(36, -20))  # Z ~ 2.8 ohm at 20 deg -> R 2.6 > 2, X 0.95
        states = {z["zone_key"]: z["state"] for z in body["zones"]}
        assert (states["Z1"], states["Z2"]) == ("not_operated", "operated")
