"""D5A-2B2C-1B owner review: a recorded Distance result with no valid loop impedance evaluates NO zone.

`not_operated` is the geometric result of a VALID impedance that does not satisfy a zone. A recorded result that has no valid
impedance -- blocked by Recording Details (side, VT/CT), a missing / ambiguous phasor, a loop current below the floor -- must
not report `not_operated`: it reports no zone at all (`zone1`..`zone4` null, `zones` empty), using the response model's existing
nullable / empty fields (no schema change). These are direct API tests; the protection is not frontend-only.

Hand-derived reference (as in the oracle suite): V 66 000 V / 66 V, I 400 A / 2 A, so |Z| = 165 ohm (Primary) / 33 ohm
(Secondary) at +30 degrees. A mho zone whose characteristic angle equals the line angle operates iff |Z| <= reach.
"""

from __future__ import annotations

import json

import pytest

from tests.test_d5a2a_protection_instrument_context_api import _contexts
from tests.test_d5a2b1_independent_side_conversion import ANGLE, _ALL, _bay, _context, _dist, _dist_locus, client  # noqa: F401
from tests.test_distance_protection_analysis_api import _mho_zone_params

SLOTS = ("zone1", "zone2", "zone3", "zone4")
Z_SEC = 33.0


def _mho(key, reach, *, enabled=True, direction="forward", delay=0.0):
    return {"key": key, "enabled": enabled, "direction": direction, "reach_ohm": reach, "characteristic_angle_deg": ANGLE, "delay_s": delay}


def _no_zone_evaluation(body):
    assert body["zones"] == [], body["zones"]
    assert [body[k] for k in SLOTS] == [None] * 4
    for key in ("magnitude_ohm", "resistance_ohm", "reactance_ohm", "angle_deg"):
        assert body[key] is None, key                       # no impedance either: the two facts go together


def _huge_zones():
    """Zones that would classify ANY valid impedance as operated -- so a reported `not_operated` could only be a placeholder."""
    return _mho_zone_params(1, reach_ohm=1.0e9, characteristic_angle_deg=ANGLE) | _mho_zone_params(2, reach_ohm=1.0e9, characteristic_angle_deg=ANGLE)


# =========================================================================== valid impedance: unchanged zone states


def test_a_valid_impedance_inside_a_zone_is_operated_and_outside_is_not_operated(client):
    ws = "zne-valid"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    body = _dist(client, ws, ctx, impedance_basis="secondary",
                 **_mho_zone_params(1, reach_ohm=50.0, characteristic_angle_deg=ANGLE),       # |Z| 33 <= 50
                 **_mho_zone_params(2, reach_ohm=10.0, characteristic_angle_deg=ANGLE),       # |Z| 33 > 10
                 **_mho_zone_params(3, enabled=False)).json()
    assert body["status"] == "computed" and body["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    assert [(z["zone_key"], z["state"]) for z in body["zones"]] == [("zone1", "operated"), ("zone2", "not_operated"),
                                                                    ("zone3", "not_operated"), ("zone4", "not_operated")]
    assert body["zone1"]["state"] == "operated" and body["zone2"]["state"] == "not_operated"
    assert body["zone3"]["enabled"] is False and body["zone3"]["state"] == "not_operated"        # a disabled zone of a valid result
    assert body["zone4"]["enabled"] is False


def test_the_output_side_does_not_change_which_zones_operate_for_the_same_reach_in_that_basis(client):
    ws = "zne-valid-basis"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")
    for out, z in (("primary", 165.0), ("secondary", 33.0)):
        inside = _dist(client, ws, ctx, impedance_basis=out, **_mho_zone_params(1, reach_ohm=z * 1.01, characteristic_angle_deg=ANGLE)).json()
        outside = _dist(client, ws, ctx, impedance_basis=out, **_mho_zone_params(1, reach_ohm=z * 0.99, characteristic_angle_deg=ANGLE)).json()
        assert (inside["zone1"]["state"], outside["zone1"]["state"]) == ("operated", "not_operated"), out


def test_standard_and_dynamic_zone_configurations_stay_intact_when_computed(client):
    ws = "zne-dynamic"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    zones = [_mho("zone1", 5), _mho("zone2", 5), _mho("zone3", 50), _mho("zone4", 5, direction="reverse"), _mho("zp", 50), _mho("z6", 5)]
    body = _dist(client, ws, ctx, impedance_basis="secondary", zones=json.dumps(zones)).json()
    assert body["status"] == "computed"
    assert [(z["zone_key"], z["state"]) for z in body["zones"]] == [
        ("zone1", "not_operated"), ("zone2", "not_operated"), ("zone3", "operated"), ("zone4", "not_operated"),
        ("zp", "operated"), ("z6", "not_operated")]
    assert body["zone3"]["state"] == "operated" and body["zone4"]["direction"] == "reverse"
    assert [body[k]["zone_key"] for k in SLOTS] == list(SLOTS)                                    # the standard slots mirror their keys


# =========================================================================== no valid impedance: no zone evaluation

BLOCKERS = [
    ("side-undefined", dict(ps={n: "" for n in _ALL}), "voltage_side_authority_unavailable"),
    ("current-side-undefined", dict(ps={"IA": "", "IB": "", "IC": ""}), "current_side_inferred"),
    ("vt-unavailable", dict(v_side="secondary", i_side="primary", groups=False), "vt_authority_unavailable"),
    ("mixed-group", dict(ps={"VB": "S"}), "voltage_group_side_conflict"),
    ("mixed-legs", dict(ps={"VB": "S"}, groups=False), "voltage_mixed_side_within_quantity"),
]


@pytest.mark.parametrize("name,bay,code", BLOCKERS, ids=[b[0] for b in BLOCKERS])
def test_a_blocked_recorded_distance_reports_no_zone_and_keeps_the_waveform_references(client, name, bay, code):
    ws = f"zne-blocked-{name}"
    _src, ctx = _bay(client, ws, **bay)
    body = _dist(client, ws, ctx, impedance_basis="primary", **_huge_zones()).json()
    assert (body["status"], body["reason_code"]) == ("needs_configuration", code)
    _no_zone_evaluation(body)
    assert [body[k]["channel_name"] for k in ("v1_channel_ref", "v2_channel_ref", "i1_channel_ref", "i2_channel_ref")] == [
        "ZBAY_VA", "ZBAY_VB", "ZBAY_IA", "ZBAY_IB"]                                              # Related Waveforms keep working
    assert (body["voltage_unit"], body["current_unit"]) == ("V", "A")


def test_a_required_ct_that_is_unavailable_reports_no_zone(client):
    ws = "zne-ct"
    src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")
    client.app.state.current_group_config_registry.delete(ws, f"ig-{src}")
    body = _dist(client, ws, ctx, impedance_basis="primary", **_huge_zones()).json()
    assert body["reason_code"] == "ct_authority_unavailable"
    _no_zone_evaluation(body)


def test_a_contradicting_assertion_reports_no_zone(client):
    ws = "zne-assert"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    body = _dist(client, ws, ctx, impedance_basis="secondary", voltage_side="primary", **_huge_zones()).json()
    assert body["reason_code"] == "voltage_side_contradicts_recording"
    _no_zone_evaluation(body)


def test_a_loop_current_below_the_floor_reports_no_zone(client):
    ws = "zne-lowcurrent"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", i_rms=0.0005)
    body = _dist(client, ws, ctx, impedance_basis="secondary", **_huge_zones()).json()
    assert (body["status"], body["reason_code"]) == ("needs_configuration", "loop_current_too_small")
    _no_zone_evaluation(body)
    assert body["i1_channel_ref"]["channel_name"] == "ZBAY_IA"


def test_an_unavailable_phasor_reports_no_zone_whatever_the_zone_collection(client):
    """A time outside the recording leaves no valid phasor. Standard slots and a dynamic collection behave the same."""
    ws = "zne-phasor"
    _src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary")
    standard = _dist(client, ws, ctx, impedance_basis="secondary", analysis_time=99.0, **_huge_zones()).json()
    assert standard["status"] != "computed"
    _no_zone_evaluation(standard)
    dynamic = _dist(client, ws, ctx, impedance_basis="secondary", analysis_time=99.0,
                    zones=json.dumps([_mho("a", 1e9), _mho("zp", 1e9), _mho("z6", 1e9)])).json()
    assert dynamic["status"] != "computed"
    _no_zone_evaluation(dynamic)


def test_a_missing_current_channel_reports_no_zone_and_its_natural_status(client):
    ws = "zne-unresolved"
    _src, ctx = _bay(client, ws, members=("VA", "VB", "VC"))                                      # no current in the context
    body = _dist(client, ws, ctx, impedance_basis="secondary", **_huge_zones()).json()
    assert body["status"] != "computed" and body["reason_code"] not in (None, "current_side_inferred")
    _no_zone_evaluation(body)
    assert body["i1_channel_ref"] is None and body["v1_channel_ref"]["channel_name"] == "ZBAY_VA"   # an unresolved leg is never invented


def test_a_calculated_channel_reports_no_zone(client, monkeypatch):
    from app.domain.calculated_channel import ChannelRef
    from app.services import independent_side_service as svc
    ws = "zne-calculated"
    _src, ctx = _bay(client, ws)
    real = svc.resolve_analysis_roles
    monkeypatch.setattr(svc, "resolve_analysis_roles", lambda **kw: (
        [(k, ChannelRef(kind="calculated", calculated_channel_id="calc-1") if k.startswith("V") else r) for k, r in real(**kw)[0]], real(**kw)[1]))
    body = _dist(client, ws, ctx, impedance_basis="primary", **_huge_zones()).json()
    assert body["reason_code"] == "calculated_channel_side_unavailable"
    _no_zone_evaluation(body)


def test_the_blocked_to_valid_transition_is_driven_only_by_recording_details(client):
    """Fixing the cause (here: the engineer sets the side) makes the SAME request evaluate its zones."""
    from tests.test_d5a_ui_002_group_measurement_side import _set_rec
    ws = "zne-transition"
    src, ctx = _bay(client, ws, v_side="secondary", i_side="secondary", ps={n: "" for n in _ALL})
    request = dict(impedance_basis="secondary", **_mho_zone_params(1, reach_ohm=50.0, characteristic_angle_deg=ANGLE))
    blocked = _dist(client, ws, ctx, **request).json()
    _no_zone_evaluation(blocked)
    _set_rec(client, ws, src, "secondary", "recorder did not flag sides")
    valid = _dist(client, ws, ctx, **request).json()
    assert valid["status"] == "computed" and valid["zone1"]["state"] == "operated" and len(valid["zones"]) == 4


# =========================================================================== unchanged neighbours


def test_manual_mode_is_unchanged(client):
    """The Manual calculator keeps its behaviour, including the zone entries of a result without a valid impedance."""
    base = {"loop_label": "AB", "voltage_basis": "secondary", "current_basis": "secondary", "impedance_basis": "secondary",
            "characteristic": "mho", **_mho_zone_params(1, reach_ohm=200.0, characteristic_angle_deg=30.0),
            **{f"zone{n}_enabled": False for n in (2, 3)},
            "v1_enabled": True, "v1_magnitude": 100, "v1_unit": "V", "v1_angle_deg": 0, "v2_enabled": True, "v2_magnitude": 100,
            "v2_unit": "V", "v2_angle_deg": -120, "i1_enabled": True, "i1_magnitude": 1, "i1_unit": "A", "i1_angle_deg": -30,
            "i2_enabled": True, "i2_magnitude": 1, "i2_unit": "A", "i2_angle_deg": -150}
    url = "/api/v1/workspaces/zne-manual/distance-protection-manual"
    valid = client.get(url, params=base).json()
    assert valid["status"] == "computed" and valid["magnitude_ohm"] == pytest.approx(100.0, rel=1e-6)
    assert valid["zone1"]["state"] == "operated" and len(valid["zones"]) == 4
    unavailable = client.get(url, params={**base, "i1_magnitude": 0, "i2_magnitude": 0}).json()
    assert unavailable["status"] != "computed"
    assert [z["zone_key"] for z in unavailable["zones"]] == ["zone1", "zone2", "zone3", "zone4"]       # unchanged: the manual path is not touched
    assert unavailable["zone1"] is not None


def test_the_locus_is_unchanged_it_never_carried_zone_state(client):
    ws = "zne-locus"
    _src, ctx = _bay(client, ws, v_side="primary", i_side="secondary")
    locus = _dist_locus(client, ws, ctx, impedance_basis="secondary", **_huge_zones()).json()
    assert set(locus) == {"engineering_context_id", "loop", "points", "side_conversion"}
    assert len(locus["points"]) == 3
    for point in locus["points"]:
        assert set(point) == {"analysis_time", "status", "resistance_ohm", "reactance_ohm", "magnitude_ohm", "angle_deg", "reason_code"}
        assert point["status"] == "computed" and point["magnitude_ohm"] == pytest.approx(Z_SEC, rel=1e-3)
    blocked_ws = "zne-locus-blocked"
    _s, bctx = _bay(client, blocked_ws, ps={n: "" for n in _ALL})
    blocked = _dist_locus(client, blocked_ws, bctx, impedance_basis="primary").json()
    assert {p["reason_code"] for p in blocked["points"]} == {"voltage_side_authority_unavailable"}
    assert all(set(p) == set(locus["points"][0]) for p in blocked["points"])


def test_the_response_schema_is_unchanged(client):
    """No public schema change: the zone fields were already nullable / empty-by-default, and a zone's `state` is still the
    two-valued `operated` / `not_operated`."""
    schemas = client.app.openapi()["components"]["schemas"]
    recorded = schemas["DistanceAnalysisResultOut"]["properties"]
    for key in SLOTS[:3]:
        assert any(opt.get("type") == "null" for opt in recorded[key]["anyOf"]), key
    assert recorded["zones"].get("default") == []
    assert schemas["ZoneResultOut"]["properties"]["state"]["enum"] == ["operated", "not_operated"]
    assert "ZoneResultOut" in json.dumps(recorded["zone1"])
    assert "D5A-2B2C-1B" not in json.dumps(schemas["ZoneResultOut"])                                # the zone result itself is untouched
