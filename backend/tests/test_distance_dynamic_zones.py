"""Slice 10 -- Dynamic Distance Protection zones: zone count is not a limitation.

Covers the whole backend path an extra distance zone travels:

    canonical model (any number of zones)
      -> engine adapter (one engine setting per canonical zone)
      -> Apply plan / payload (the complete zone collection, stable ids, source labels)
      -> analysis request (a generic ``zones`` collection under stable keys)
      -> engine evaluation (a generic zone loop; direction is a property of each zone)

Nothing here is specific to Zone P: the zones are given arbitrary ids, labels and numbers.
"""

from __future__ import annotations

import json
import math
import random

import pytest
from fastapi.testclient import TestClient

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    NamedZone,
    ZoneSettings,
    collect_zones,
    evaluate_manual_distance,
    evaluate_zones,
)
from app.domain.impedance import ImpedancePoint
from app.domain.phasor import ManualPhasorRoleInput
from app.domain.relay_import.apply_settings import ApplyRejectedError, build_apply_plan
from app.domain.relay_import.canonical_codec import decode_model, encode_model
from app.domain.relay_import.canonical_distance import (
    CharacteristicType,
    ImpedanceValue,
    ResistiveReach,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.provenance import unresolved
from app.domain.relay_import.review_state import ReviewDecisions
from app.main import create_app
from app.schemas.distance_protection_analysis import MAX_REQUEST_ZONES
from app.schemas.relay_import import ApplySettingsOut
from app.services.relay_apply_settings import apply_reviewed_settings
from tests.test_distance_protection_analysis_api import (
    _create_full_bay,
    _distance,
    _distance_locus,
    _upload_sine_source,
)
from tests.test_relay_import_engine_adapter import SEC, import_zone, m, model_of

MANUAL_URL = "/api/v1/workspaces/ws-dyn/distance-protection-manual"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


# ---------------------------------------------------------------------------
# Canonical model -> adapter -> Apply plan
# ---------------------------------------------------------------------------

#: Arbitrary identifiers and labels: OEMs skip numbers and use non-numeric names.
IDS_AND_LABELS = [
    ("Z1", "Zone 1"), ("Z2", "Zone 2"), ("Z3", "Zone 3"), ("Z4", "Zone 4"),
    ("ZP", "Zone P"), ("Z5", "Zone 5"), ("ZX7", "Backup 7"), ("A", "Alpha"),
]


def zones_for(pairs=IDS_AND_LABELS, **kw):
    return [import_zone(zid, name=name, **kw) for zid, name in pairs]


def plan_for(model, basis="secondary"):
    adaptation = adapt_to_engine(model, engine_basis=SEC)
    return adaptation, build_apply_plan(model, adaptation, impedance_basis=basis)


class TestApplyPlanCarriesEveryZone:
    def test_arbitrary_zone_count_is_applied_without_truncation(self):
        for count in (1, 3, 4, 5, 6, 8, 12):
            pairs = [(f"Q{i}", f"Stage {i}") for i in range(count)]
            adaptation, plan = plan_for(model_of(*zones_for(pairs)))
            assert adaptation.supported
            assert len(plan.zones) == count == len(adaptation.zones) == len(adaptation.zone_ids)
            assert all(z.enabled for z in plan.zones)

    def test_a_fifth_supported_enabled_zone_is_not_refused_for_its_number(self):
        adaptation, plan = plan_for(model_of(*zones_for(IDS_AND_LABELS[:5])))
        assert adaptation.supported and not adaptation.reasons
        assert [z.zone_id for z in plan.zones][-1] == "ZP" and plan.zones[-1].enabled

    def test_source_labels_are_preserved_not_renumbered(self):
        _, plan = plan_for(model_of(*zones_for()))
        assert [z.display_name for z in plan.zones] == [label for _, label in IDS_AND_LABELS]

    def test_a_zone_without_a_source_name_is_labelled_by_its_id(self):
        _, plan = plan_for(model_of(import_zone("Z1"), import_zone("ZQ")))
        assert [z.display_name for z in plan.zones] == ["Z1", "ZQ"]

    def test_identifiers_are_stable_whatever_the_order(self):
        zones = zones_for()
        shuffled = list(zones)
        random.Random(7).shuffle(shuffled)
        _, a = plan_for(model_of(*zones))
        _, b = plan_for(model_of(*shuffled))
        by_id = lambda plan: {z.zone_id: z for z in plan.zones}  # noqa: E731
        assert by_id(a) == by_id(b)
        assert [z.zone_id for z in b.zones] == [z.zone_id for z in shuffled]  # order is the model's, identity is the id

    def test_values_are_the_engine_adapters_own(self):
        model = model_of(*zones_for())
        adaptation, plan = plan_for(model)
        for engine, zone in zip(adaptation.zones, plan.zones):
            assert (zone.reactive_reach_ohm, zone.resistive_reach_forward_ohm, zone.resistive_reach_reverse_ohm) == (
                engine.reactive_reach_ohm, engine.resistive_reach_forward_ohm, engine.resistive_reach_reverse_ohm,
            )
            assert (zone.characteristic_angle_deg, zone.delay_s, zone.direction) == (
                engine.characteristic_angle_deg, engine.delay_s, engine.direction,
            )

    def test_mho_extra_zone_carries_its_mho_reach_only(self):
        zones = [import_zone(f"Z{i}", char=CharacteristicType.MHO) for i in range(1, 7)]
        _, plan = plan_for(model_of(*zones))
        for z in plan.zones:
            assert z.reach_ohm == 6.0 and z.reactive_reach_ohm is None and z.resistive_reach_forward_ohm is None


class TestDisabledExtraZones:
    def test_a_disabled_extra_zone_is_preserved_without_geometry(self):
        bare = import_zone(
            "ZP", name="Zone P", status=m(ZoneStatus.DISABLED),
            reach=unresolved(),
            resistive_reach=ResistiveReach(),
        )
        adaptation, plan = plan_for(model_of(*zones_for(IDS_AND_LABELS[:4]), bare))
        assert adaptation.supported
        zp = plan.zones[-1]
        assert (zp.zone_id, zp.display_name, zp.enabled) == ("ZP", "Zone P", False)
        for field in ("characteristic_angle_deg", "reach_ohm", "reactive_reach_ohm", "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm"):
            assert getattr(zp, field) is None

    def test_a_disabled_zone_never_blocks_however_many_there_are(self):
        off = [import_zone(f"D{i}", status=m(ZoneStatus.DISABLED)) for i in range(10)]
        adaptation, plan = plan_for(model_of(import_zone("Z1"), *off))
        assert adaptation.supported and len(plan.zones) == 11 and [z.enabled for z in plan.zones] == [True] + [False] * 10


class TestRefusals:
    @pytest.mark.parametrize("ctype", [CharacteristicType.LENTICULAR, CharacteristicType.POLYGON_CUSTOM, CharacteristicType.UNKNOWN])
    def test_an_unsupported_characteristic_on_an_extra_zone_still_rejects_apply(self, ctype):
        model = model_of(*zones_for(IDS_AND_LABELS[:4]), import_zone("ZP", char=ctype))
        adaptation = adapt_to_engine(model, engine_basis=SEC)
        assert not adaptation.supported
        assert UnsupportedCode.CHARACTERISTIC_UNSUPPORTED in {r.code for r in adaptation.reasons}
        assert {r.zone_id for r in adaptation.reasons} == {"ZP"}
        with pytest.raises(ApplyRejectedError):
            build_apply_plan(model, adaptation, impedance_basis="secondary")

    def test_an_unsupported_characteristic_is_never_faked_as_quadrilateral(self):
        model = model_of(import_zone("Z1"), import_zone("ZP", char=CharacteristicType.LENTICULAR))
        adaptation = adapt_to_engine(model, engine_basis=SEC)
        assert adaptation.characteristic is None and adaptation.zones is None

    def test_mixed_characteristics_across_extra_zones_are_refused(self):
        model = model_of(*zones_for(IDS_AND_LABELS[:4]), import_zone("ZP", char=CharacteristicType.MHO))
        assert UnsupportedCode.CHARACTERISTIC_MIXED in {r.code for r in adapt_to_engine(model, engine_basis=SEC).reasons}

    def test_an_unresolved_reach_on_an_extra_zone_rejects_apply(self):
        model = model_of(*zones_for(IDS_AND_LABELS[:4]), import_zone("ZP", reach=unresolved()))
        adaptation = adapt_to_engine(model, engine_basis=SEC)
        assert not adaptation.supported and {r.code for r in adaptation.reasons} == {UnsupportedCode.REACH_UNRESOLVED}
        with pytest.raises(ApplyRejectedError):
            build_apply_plan(model, adaptation, impedance_basis="secondary")

    def test_a_missing_timer_or_resistive_reach_on_an_extra_zone_rejects_apply(self):
        for kw, code in (
            ({"phase_timer_s": unresolved()}, UnsupportedCode.TIMER_UNRESOLVED),
            ({"resistive_reach": ResistiveReach(phase_phase=m(4.0))}, UnsupportedCode.RESISTIVE_REACH_UNRESOLVED),
            ({"resistive_reach": ResistiveReach(reverse=m(2.0))}, UnsupportedCode.RESISTIVE_REACH_UNRESOLVED),
        ):
            adaptation = adapt_to_engine(model_of(import_zone("Z1"), import_zone("ZP", **kw)), engine_basis=SEC)
            assert not adaptation.supported and {r.code for r in adaptation.reasons} == {code}

    @pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan])
    def test_invalid_geometry_values_reject_apply(self, bad):
        model = model_of(import_zone("Z1"), import_zone("ZP", reach=m(ImpedanceValue(magnitude_ohm=bad, angle_deg=80.0))))
        adaptation = adapt_to_engine(model, engine_basis=SEC)
        with pytest.raises(ApplyRejectedError):
            build_apply_plan(model, adaptation, impedance_basis="secondary")

    def test_an_unsupported_direction_on_an_extra_zone_is_refused_not_guessed(self):
        model = model_of(import_zone("Z1"), import_zone("ZP", direction=m(ZoneDirection.NON_DIRECTIONAL)))
        adaptation = adapt_to_engine(model, engine_basis=SEC)
        assert UnsupportedCode.DIRECTION_UNSUPPORTED in {r.code for r in adaptation.reasons}

    def test_an_enabled_extra_zone_with_unknown_status_is_refused_for_its_status(self):
        adaptation = adapt_to_engine(model_of(import_zone("Z1"), import_zone("ZP", status=unresolved())), engine_basis=SEC)
        assert {r.code for r in adaptation.reasons} == {UnsupportedCode.ZONE_STATUS_UNRESOLVED}


class TestDirectionIsAPropertyOfTheZone:
    def test_direction_does_not_depend_on_number_or_name(self):
        reverse, forward = m(ZoneDirection.REVERSE), m(ZoneDirection.FORWARD)
        zones = [
            import_zone("Z1", direction=reverse), import_zone("Z2"), import_zone("Z3", direction=reverse),
            import_zone("Z4", direction=forward), import_zone("ZP", direction=reverse), import_zone("Z6", direction=forward),
            import_zone("ZR", name="Reverse Zone", direction=forward),  # a *name* promises nothing
        ]
        _, plan = plan_for(model_of(*zones))
        assert {z.zone_id: z.direction for z in plan.zones} == {
            "Z1": "reverse", "Z2": "forward", "Z3": "reverse", "Z4": "forward", "ZP": "reverse", "Z6": "forward", "ZR": "forward",
        }

    def test_a_disabled_zone_whose_direction_is_not_stated_has_none(self):
        _, plan = plan_for(model_of(import_zone("Z1"), import_zone("Z4", status=m(ZoneStatus.DISABLED), direction=unresolved())))
        assert plan.zones[1].direction is None and plan.zones[1].enabled is False

    def test_a_reverse_zone_is_evaluated_by_the_same_generic_loop(self):
        at_200_degrees = ImpedancePoint(-9.4, -3.4, math.hypot(9.4, 3.4), math.degrees(math.atan2(-3.4, -9.4)))
        zones = [
            NamedZone(key, ZoneSettings(True, 15.0, None, None, None, 20.0, 0.0, direction))
            for key, direction in (("a", "forward"), ("b", "reverse"), ("c", "forward"), ("d", "reverse"), ("e", "reverse"))
        ]
        results = evaluate_zones(at_200_degrees, characteristic=CHARACTERISTIC_MHO, zones=zones)
        assert [(r.zone_key, r.direction, r.state) for r in results] == [
            ("a", "forward", "not_operated"), ("b", "reverse", "operated"), ("c", "forward", "not_operated"),
            ("d", "reverse", "operated"), ("e", "reverse", "operated"),
        ]


class TestSerialisationKeepsEveryZone:
    def test_canonical_codec_round_trip_preserves_all_zones(self):
        model = model_of(*zones_for(), import_zone("Z9", status=m(ZoneStatus.DISABLED)))
        decoded = decode_model(json.loads(json.dumps(encode_model(model))))
        assert [z.zone_id for z in decoded.zones] == [z.zone_id for z in model.zones]
        assert [z.name for z in decoded.zones] == [z.name for z in model.zones]
        assert decoded == model

    def test_apply_through_the_validation_context_returns_every_zone(self):
        model = model_of(*zones_for(), import_zone("Z9", status=m(ZoneStatus.DISABLED)))
        plan = apply_reviewed_settings(json.loads(json.dumps(encode_model(model))), ReviewDecisions())
        assert [z.zone_id for z in plan.zones] == [z.zone_id for z in model.zones]
        assert [z.enabled for z in plan.zones] == [True] * len(IDS_AND_LABELS) + [False]

    def test_wire_payload_round_trips_any_number_of_zones(self):
        _, plan = plan_for(model_of(*zones_for([(f"Z{i}", f"Zone {i}") for i in range(1, 15)])))
        from dataclasses import asdict

        zones = []
        for z in plan.zones:
            fields = asdict(z)
            fields["id"] = fields.pop("zone_id")
            zones.append(fields)
        out = ApplySettingsOut.model_validate({"characteristic": plan.characteristic, "impedance_basis": plan.impedance_basis, "zones": zones})
        again = ApplySettingsOut.model_validate_json(out.model_dump_json())
        assert [z.id for z in again.zones] == [f"Z{i}" for i in range(1, 15)] and again == out

    def test_the_payload_requires_at_least_one_zone_but_has_no_upper_bound(self):
        with pytest.raises(Exception):
            ApplySettingsOut(characteristic="mho", impedance_basis="secondary", zones=[])


# ---------------------------------------------------------------------------
# Engine: the generic zone collection
# ---------------------------------------------------------------------------

def inputs(offset: float = 0.0, current: float = 10.0):
    """Z = 10/20deg at offset 0 (|Z| scales with 1/current); 200deg at offset 180."""
    return (
        ManualPhasorRoleInput(True, 100.0, "V", 0.0), ManualPhasorRoleInput(True, 100.0, "V", -120.0),
        ManualPhasorRoleInput(True, current, "A", -20.0 + offset), ManualPhasorRoleInput(True, current, "A", -140.0 + offset),
    )


def run(zones=None, *, characteristic=CHARACTERISTIC_MHO, offset=0.0, current=10.0, **legacy):
    return evaluate_manual_distance(
        *inputs(offset, current), loop_label="AB", voltage_basis=SEC, vt_primary=None, vt_secondary=None,
        current_basis=SEC, ct_primary=None, ct_secondary=None, impedance_basis=SEC,
        characteristic=characteristic, zones=zones, **legacy,
    )


def mho_named(key, reach, angle=20.0, direction="forward", enabled=True, delay=0.0):
    return NamedZone(key, ZoneSettings(enabled, reach, None, None, None, angle, delay, direction))


class TestEngineZoneCollection:
    def test_any_number_of_zones_each_under_its_key(self):
        zones = [mho_named(f"k{i}", 5.0 + 3 * i) for i in range(10)]  # 5, 8, 11, 14, ... 32
        result = run(zones)
        assert [z.zone_key for z in result.zones] == [f"k{i}" for i in range(10)]
        # |Z| = 10 on the 20 degree diameter: inside once the reach is >= 10
        assert [z.state for z in result.zones] == ["not_operated", "not_operated"] + ["operated"] * 8

    def test_zone_state_depends_on_the_zone_not_on_its_position(self):
        a = run([mho_named("small", 5.0), mho_named("big", 20.0)])
        b = run([mho_named("big", 20.0), mho_named("small", 5.0)])
        assert {z.zone_key: z.state for z in a.zones} == {z.zone_key: z.state for z in b.zones}

    def test_standard_attributes_mirror_the_zones_with_those_keys(self):
        result = run([mho_named("zone2", 20.0), mho_named("zp", 20.0), mho_named("zone1", 5.0)])
        assert result.zone1.state == "not_operated" and result.zone2.state == "operated"
        assert result.zone3 is None and result.zone4 is None
        assert result.zone2 is result.zones[0] and result.zone1 is result.zones[2]

    def test_disabled_zone_is_reported_not_operated_without_geometry(self):
        result = run([NamedZone("off", ZoneSettings(enabled=False, characteristic_angle_deg=None, delay_s=None)), mho_named("on", 20.0)])
        assert [(z.zone_key, z.enabled, z.state) for z in result.zones] == [("off", False, "not_operated"), ("on", True, "operated")]

    def test_reverse_zone_numbered_first_and_forward_zone_numbered_last(self):
        zones = [mho_named("zone1", 15.0, direction="reverse"), mho_named("zone4", 15.0, direction="forward")]
        forward_point = run(zones, offset=0.0)
        reverse_point = run(zones, offset=180.0)
        assert {z.zone_key: z.state for z in forward_point.zones} == {"zone1": "not_operated", "zone4": "operated"}
        assert {z.zone_key: z.state for z in reverse_point.zones} == {"zone1": "operated", "zone4": "not_operated"}

    def test_zero_left_resistive_reach_is_valid_for_an_extra_zone(self):
        # Z = 5 /_ 20 degrees lies exactly on the left boundary (r' = 0) of a zone whose left reach is 0.
        zone = NamedZone("zp", ZoneSettings(True, None, 10.0, 5.0, 0.0, 20.0, 0.0))
        unset = NamedZone("zp", ZoneSettings(True, None, 10.0, 5.0, None, 20.0, 0.0))
        assert run([zone], characteristic=CHARACTERISTIC_QUADRILATERAL, current=20.0).zones[0].state == "operated"
        assert run([unset], characteristic=CHARACTERISTIC_QUADRILATERAL, current=20.0).zones[0].state == "not_operated"

    def test_collect_zones_rules(self):
        z = ZoneSettings()
        with pytest.raises(TypeError):
            collect_zones([NamedZone("a", z)], z, z, z)
        with pytest.raises(TypeError):
            collect_zones(None, z)
        with pytest.raises(ValueError):
            collect_zones([NamedZone("a", z), NamedZone("a", z)])
        assert [n.key for n in collect_zones(None, z, z, z)] == ["zone1", "zone2", "zone3", "zone4"]


# ---------------------------------------------------------------------------
# HTTP: the generic `zones` request parameter
# ---------------------------------------------------------------------------

def manual_query(zones=None, *, offset=0.0, **extra):
    q = dict(
        loop_label="AB", voltage_basis=SEC, current_basis=SEC, impedance_basis=SEC, characteristic="mho",
        v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
        v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
        i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20 + offset,
        i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140 + offset,
    )
    if zones is not None:
        q["zones"] = json.dumps(zones)
    q.update(extra)
    return q


def mho_json(key, reach, angle=20.0, direction="forward", enabled=True, delay=0.0):
    return {"key": key, "enabled": enabled, "direction": direction, "reach_ohm": reach, "characteristic_angle_deg": angle, "delay_s": delay}


class TestManualEndpointZonesParameter:
    def test_six_zones_are_returned_in_request_order_with_their_keys(self, client):
        zones = [
            mho_json("zone1", 5), mho_json("zone2", 12), mho_json("zone3", 30), mho_json("zone4", 30, direction="reverse"),
            mho_json("zp", 30, delay=10.0), mho_json("z6", 11, direction="forward", delay=1.5),
        ]
        body = client.get(MANUAL_URL, params=manual_query(zones)).json()
        assert body["status"] == "computed"
        assert [(z["zone_key"], z["state"]) for z in body["zones"]] == [
            ("zone1", "not_operated"), ("zone2", "operated"), ("zone3", "operated"), ("zone4", "not_operated"),
            ("zp", "operated"), ("z6", "operated"),
        ]
        assert [z["delay_s"] for z in body["zones"]] == [0, 0, 0, 0, 10.0, 1.5]
        assert [z["direction"] for z in body["zones"]] == ["forward", "forward", "forward", "reverse", "forward", "forward"]

    def test_standard_fields_mirror_matching_keys_only(self, client):
        body = client.get(MANUAL_URL, params=manual_query([mho_json("zone3", 30), mho_json("zp", 30)])).json()
        assert body["zone3"] == body["zones"][0] and body["zone1"] is None and body["zone4"] is None

    def test_a_fifth_enabled_zone_plots_and_operates_like_any_other(self, client):
        zones = [mho_json(f"zone{n}", 5) for n in (1, 2, 3)] + [mho_json("zone4", 5, direction="reverse"), mho_json("zp", 12)]
        body = client.get(MANUAL_URL, params=manual_query(zones)).json()
        assert [z["state"] for z in body["zones"]] == ["not_operated"] * 4 + ["operated"]

    def test_an_extra_reverse_zone_operates_on_a_reverse_fault_point(self, client):
        zones = [mho_json("zone1", 30), mho_json("zr", 30, direction="reverse")]
        forward = client.get(MANUAL_URL, params=manual_query(zones, offset=0)).json()
        reverse = client.get(MANUAL_URL, params=manual_query(zones, offset=180)).json()
        assert [z["state"] for z in forward["zones"]] == ["operated", "not_operated"]
        assert [z["state"] for z in reverse["zones"]] == ["not_operated", "operated"]

    def test_a_disabled_extra_zone_needs_no_geometry(self, client):
        zones = [mho_json("zone1", 30), {"key": "zp", "enabled": False}]
        body = client.get(MANUAL_URL, params=manual_query(zones)).json()
        assert body["zones"][1] == {"zone_key": "zp", "enabled": False, "state": "not_operated", "delay_s": None, "direction": "forward"}

    def test_extra_zone_with_zero_left_resistive_reach_is_valid(self, client):
        zone = {
            "key": "zp", "enabled": True, "reactive_reach_ohm": 10, "resistive_reach_forward_ohm": 5,
            "resistive_reach_reverse_ohm": 0, "characteristic_angle_deg": 20, "delay_s": 0,
        }
        q = manual_query([zone], characteristic="quadrilateral", i1_magnitude=20, i2_magnitude=20)
        assert client.get(MANUAL_URL, params=q).json()["zones"][0]["state"] == "operated"

    def test_zones_replace_the_legacy_slot_parameters_entirely(self, client):
        q = manual_query([mho_json("only", 30)], zone1_enabled=True, zone1_reach_ohm=30, zone1_characteristic_angle_deg=20)
        body = client.get(MANUAL_URL, params=q).json()
        assert [z["zone_key"] for z in body["zones"]] == ["only"] and body["zone1"] is None

    def test_the_legacy_request_is_unchanged_and_now_also_lists_its_zones(self, client):
        q = manual_query(zone1_enabled=True, zone1_reach_ohm=30, zone1_characteristic_angle_deg=20)
        body = client.get(MANUAL_URL, params=q).json()
        assert [z["zone_key"] for z in body["zones"]] == ["zone1", "zone2", "zone3", "zone4"]
        assert body["zones"][0] == body["zone1"] and body["zone4"]["direction"] == "reverse"

    def test_no_truncation_at_many_zones(self, client):
        zones = [mho_json(f"k{i}", 12) for i in range(MAX_REQUEST_ZONES)]
        body = client.get(MANUAL_URL, params=manual_query(zones)).json()
        assert len(body["zones"]) == MAX_REQUEST_ZONES and all(z["state"] == "operated" for z in body["zones"])

    @pytest.mark.parametrize(
        "raw",
        [
            "not json",
            json.dumps({"key": "a"}),  # not a list
            json.dumps([{"enabled": True}]),  # no key
            json.dumps([{"key": "a b"}]),  # key with a space
            json.dumps([{"key": ""}]),
            json.dumps([{"key": "a", "direction": "sideways"}]),
            json.dumps([{"key": "a", "colour": "red"}]),  # unknown field
            json.dumps([{"key": "a"}, {"key": "a"}]),  # duplicate keys
            json.dumps([{"key": f"k{i}"} for i in range(MAX_REQUEST_ZONES + 1)]),
            json.dumps([{"key": "a", "reach_ohm": "ten"}]),
        ],
    )
    def test_a_malformed_zones_parameter_is_rejected(self, client, raw):
        resp = client.get(MANUAL_URL, params=manual_query(None) | {"zones": raw})
        assert resp.status_code == 422, raw

    def test_an_empty_collection_is_valid_and_evaluates_nothing(self, client):
        body = client.get(MANUAL_URL, params=manual_query([])).json()
        assert body["status"] == "computed" and body["zones"] == []

    def test_openapi_exposes_the_generic_zones_parameter_on_all_three_endpoints(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for suffix in ("/distance-protection-manual", "/engineering-contexts/{engineering_context_id}/distance-protection",
                       "/engineering-contexts/{engineering_context_id}/distance-protection-locus"):
            path = next(p for p in paths if p.endswith(suffix))
            names = {param["name"] for param in paths[path]["get"]["parameters"]}
            assert "zones" in names and "zone1_enabled" in names


class TestRecordingEndpointsZonesParameter:
    def bay(self, client, workspace_id="ws-dyn-rec"):
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("DBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("DBAY_VB", "V", 100.0 * math.sqrt(2), -120.0), ("DBAY_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("DBAY_IA", "A", 10.0 * math.sqrt(2), -20.0), ("DBAY_IB", "A", 10.0 * math.sqrt(2), -140.0), ("DBAY_IC", "A", 10.0 * math.sqrt(2), 100.0),
        ])
        return workspace_id, _create_full_bay(client, workspace_id, source_id)["id"]

    def test_recording_mode_evaluates_a_fifth_and_sixth_zone(self, client):
        workspace_id, context_id = self.bay(client)
        zones = [mho_json("zone1", 5), mho_json("zone2", 5), mho_json("zone3", 30), mho_json("zone4", 5, direction="reverse"),
                 mho_json("zp", 30), mho_json("z6", 5)]
        resp = _distance(client, workspace_id, context_id, zones=json.dumps(zones))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert [(z["zone_key"], z["state"]) for z in body["zones"]] == [
            ("zone1", "not_operated"), ("zone2", "not_operated"), ("zone3", "operated"), ("zone4", "not_operated"),
            ("zp", "operated"), ("z6", "not_operated"),
        ]

    def test_recording_mode_reports_every_zone_even_when_the_loop_cannot_be_computed(self, client):
        workspace_id, context_id = self.bay(client)
        resp = _distance(client, workspace_id, context_id, analysis_time=99.0, zones=json.dumps([mho_json("a", 5), mho_json("b", 5)]))
        body = resp.json()
        assert body["status"] != "computed" and [z["zone_key"] for z in body["zones"]] == ["a", "b"]

    def test_the_locus_endpoint_accepts_the_generic_collection(self, client):
        workspace_id, context_id = self.bay(client)
        resp = _distance_locus(
            client, workspace_id, context_id, loop="AB", start_time=0.5, end_time=2.5, point_count=5,
            recording_basis="secondary", impedance_basis="secondary", characteristic="mho",
            zones=json.dumps([mho_json(f"k{i}", 10) for i in range(7)]),
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["points"]) == 5

    def test_a_bad_zones_parameter_is_a_422_on_the_recording_endpoint_too(self, client):
        workspace_id, context_id = self.bay(client)
        assert _distance(client, workspace_id, context_id, zones="nope").status_code == 422
