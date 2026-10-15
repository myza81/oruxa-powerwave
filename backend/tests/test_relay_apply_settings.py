"""Apply Settings (Slice 9) and its Slice 10 generalisation: a backend-authoritative apply of a
reviewed relay import, carrying the complete zone collection (any number of zones)."""

from __future__ import annotations

import io
import json
import math
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_distance import ZoneStatus
from app.domain.relay_import.defeated_zone import infer_defeated_zones
from app.domain.relay_import.provenance import MappingStatus, Provenance, ProvenanceOrigin, Sourced
from app.domain.relay_import.review_state import ReviewDecisions
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.schemas.relay_import import ApplyZoneOut
from app.services.relay_review_validation import reviewed_state
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_review_state import REVERSE, UPLOAD, VALIDATE

APPLY = "/api/v1/relay-import/review/apply"
Z123 = ("Z1", "Z2", "Z3")
ZP_STATUS = "zones[ZP].status"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def review(client):
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
    return r.json()["review"]


def _assumptions(review):
    return [
        i["item_id"]
        for g in review["groups"]
        for i in g["items"]
        if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"
    ]


def _ready_body(review, *, left="suggested"):
    body = {"validation_context": review["validation_context"], "confirmed": _assumptions(review)}
    paths = [REVERSE.format(z) for z in Z123]
    if left == "suggested":
        body["suggested"] = paths
    else:
        body["manual"] = [{"item_id": p, "value": 0} for p in paths]
    return body


class TestReadinessGate:
    def test_not_ready_is_rejected_with_no_payload(self, client, review):
        r = client.post(APPLY, json={"validation_context": review["validation_context"]})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "apply_not_ready"
        assert set(r.json()) == {"detail"}

    def test_ready_after_confirmation_is_rejected(self, client, review):
        body = _ready_body(review) | {"confirmed": []}
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "ready_after_confirmation"
        r = client.post(APPLY, json=body)
        assert r.status_code == 409 and "Confirm" in r.json()["detail"]["message"]

    def test_ready_applies_after_the_backend_revalidates(self, client, review):
        body = _ready_body(review)
        assert client.post(VALIDATE, json=body).json()["readiness"]["status"] == "ready"
        r = client.post(APPLY, json=body)
        assert r.status_code == 200
        out = r.json()
        assert out["characteristic"] == "quadrilateral" and out["impedance_basis"] in ("primary", "secondary")
        # every canonical zone, in order, under its stable id -- Zone P included (it is disabled)
        assert [z["id"] for z in out["zones"]] == ["Z1", "Z2", "Z3", "Z4", "ZP"]
        assert [z["display_name"] for z in out["zones"]] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone P"]

    def test_an_undecodable_context_is_refused(self, client, review):
        ctx = dict(review["validation_context"])
        ctx["zones"] = "garbage"
        r = client.post(APPLY, json={"validation_context": ctx})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_review"


class TestPayload:
    def _apply(self, client, review, **kw):
        return client.post(APPLY, json=_ready_body(review, **kw)).json()

    def test_zones_1_to_3_populate_and_disabled_zones_do_not(self, client, review):
        out = self._apply(client, review)
        z1, z2, z3, z4, zp = out["zones"]
        for z in (z1, z2, z3):
            assert z["enabled"] and z["direction"] == "forward"
            assert z["reactive_reach_ohm"] > 0 and z["resistive_reach_forward_ohm"] > 0
            assert z["reach_ohm"] is None and z["characteristic_angle_deg"] is not None
        # the sample defeats Zone 4 and Zone P: preserved, disabled, no geometry fabricated
        for z, direction in ((z4, "reverse"), (zp, "forward")):
            assert z["enabled"] is False and z["direction"] == direction
            for key in ("reactive_reach_ohm", "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm", "characteristic_angle_deg", "reach_ohm"):
                assert z[key] is None

    def test_suggested_zero_left_reach_is_0_0(self, client, review):
        out = self._apply(client, review)
        for z in out["zones"][:3]:
            assert z["resistive_reach_reverse_ohm"] == 0.0 and z["enabled"]
        assert '"resistive_reach_reverse_ohm":0.0' in json.dumps(out, separators=(",", ":"))

    def test_manual_zero_and_suggested_zero_give_the_same_engine_input(self, client, review):
        assert self._apply(client, review, left="suggested") == self._apply(client, review, left="manual")

    def test_payload_holds_no_document_data(self, client, review):
        out = self._apply(client, review)
        # DEC-198: approximations[] is part of the generic payload; empty because no rule is approved
        assert set(out) == {"characteristic", "impedance_basis", "zones", "approximations"} and out["approximations"] == []
        assert set(out["zones"][0]) == set(ApplyZoneOut.model_fields)
        text = json.dumps(out)
        for token in ("P441", "MiCOM", "pdf", "sheet", "Schneider", "raw"):
            assert token not in text

    def test_payload_equals_the_adapter_engine_input(self, client, review):
        body = _ready_body(review)
        decisions = ReviewDecisions(confirmed=frozenset(body["confirmed"]), suggested=frozenset(body["suggested"]))
        _, adaptation, _ = reviewed_state(review["validation_context"], decisions)
        out = client.post(APPLY, json=body).json()
        assert [z["id"] for z in out["zones"]] == list(adaptation.zone_ids)
        for z, engine in zip(out["zones"], adaptation.zones):
            assert z["enabled"] == engine.enabled
            if engine.enabled:
                assert z["reactive_reach_ohm"] == engine.reactive_reach_ohm
                assert z["resistive_reach_forward_ohm"] == engine.resistive_reach_forward_ohm
                assert z["resistive_reach_reverse_ohm"] == engine.resistive_reach_reverse_ohm
                assert z["characteristic_angle_deg"] == engine.characteristic_angle_deg
                assert z["delay_s"] == engine.delay_s


class TestZonesAndRules:
    def test_enabled_zone_p_without_its_left_reach_blocks_apply(self, client, review):
        body = _ready_body(review)
        body["confirmed"] = [p for p in body["confirmed"] if p != ZP_STATUS]
        body["manual"] = [{"item_id": ZP_STATUS, "value": "enabled"}]
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "not_ready"
        assert any("Left Resistive Reach" in i["message"] for i in state["blocking_issues"])
        r = client.post(APPLY, json=body)
        assert r.status_code == 409 and set(r.json()) == {"detail"}

    def test_enabled_zone_p_with_a_complete_geometry_is_applied_as_a_fifth_zone(self, client, review):
        """Slice 10: nothing but missing values stands between an enabled fifth zone and Apply."""
        body = _ready_body(review)
        body["confirmed"] = [p for p in body["confirmed"] if p != ZP_STATUS]
        body["suggested"] = [*body["suggested"], REVERSE.format("ZP")]
        body["manual"] = [{"item_id": ZP_STATUS, "value": "enabled"}]
        state = client.post(VALIDATE, json=body).json()
        assert state["readiness"]["status"] == "ready", state["blocking_issues"]
        r = client.post(APPLY, json=body)
        assert r.status_code == 200
        zones = {z["id"]: z for z in r.json()["zones"]}
        assert list(zones) == ["Z1", "Z2", "Z3", "Z4", "ZP"]
        zp = zones["ZP"]
        assert zp["enabled"] and zp["display_name"] == "Zone P" and zp["direction"] == "forward"
        assert zp["reactive_reach_ohm"] is not None and zp["resistive_reach_forward_ohm"] is not None
        assert zp["resistive_reach_reverse_ohm"] == 0.0 and zp["delay_s"] == 10.0
        assert zones["Z4"]["enabled"] is False  # untouched

    def test_inferred_disabled_zone_p_does_not_block(self, client, review):
        """The 10 s rule disabled Zone P, so it is respected during Apply."""
        state = client.post(VALIDATE, json=_ready_body(review)).json()
        zp = {i["item_id"]: i for i in state["items"]}[ZP_STATUS]
        assert zp["value_text"].lower().startswith("disabled")
        assert client.post(APPLY, json=_ready_body(review)).status_code == 200

    def test_explicit_status_overrides_the_ten_second_inference(self):
        model = MicomP441Profile().interpret(make_doc())
        assert infer_defeated_zones(model).zone("ZP").status.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION
        explicit = Sourced(ZoneStatus.ENABLED, Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.MANUAL_ENTRY))
        zones = tuple(replace(z, status=explicit) if z.zone_id == "ZP" else z for z in model.zones)
        assert infer_defeated_zones(replace(model, zones=zones)).zone("ZP").status.value is ZoneStatus.ENABLED

    def test_provenance_stays_distinct_and_is_untouched_by_apply(self, client, review):
        body = _ready_body(review)
        before = client.post(VALIDATE, json=body).json()
        client.post(APPLY, json=body)
        assert client.post(VALIDATE, json=body).json() == before
        items = {i["item_id"]: i for i in before["items"]}
        assert items[REVERSE.format("Z1")]["resolution_origin"] == "suggestion"
        manual = client.post(VALIDATE, json=_ready_body(review, left="manual")).json()
        assert {i["item_id"]: i for i in manual["items"]}[REVERSE.format("Z1")]["resolution_origin"] == "manual"


class TestPayloadValidation:
    @pytest.mark.parametrize("field", ["reactive_reach_ohm", "resistive_reach_reverse_ohm", "delay_s"])
    @pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan])
    def test_schema_rejects_invalid_values(self, field, bad):
        with pytest.raises(Exception):
            ApplyZoneOut(id="Z1", display_name="Zone 1", enabled=True, direction="forward", **{field: bad})

    def test_zero_is_valid(self):
        z = ApplyZoneOut(id="Z1", display_name="Zone 1", enabled=True, direction="forward", resistive_reach_reverse_ohm=0.0)
        assert z.resistive_reach_reverse_ohm == 0.0
