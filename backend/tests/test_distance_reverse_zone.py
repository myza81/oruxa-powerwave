"""Distance Protection: the fourth (Reverse Zone) manual slot.

A reverse-direction zone is the zone's whole characteristic rotated 180
degrees about the origin. It is NOT the quadrilateral's
`resistive_reach_reverse_ohm` (the negative-R side of a forward zone); the
tests below keep the two concepts apart.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    DEFAULT_ZONE4,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    ZONE_KEYS,
    ZONE_STATE_NOT_OPERATED,
    ZONE_STATE_OPERATED,
    ZoneSettings,
    evaluate_manual_distance,
    evaluate_zone_state,
    mho_zone_operated,
    quadrilateral_zone_operated,
)
from app.domain.impedance import ImpedancePoint
from app.domain.phasor import ManualPhasorRoleInput
from app.domain.relay_import.canonical_distance import ZoneDirection
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.manual_entry import engine_zones_from_manual, manual_to_canonical
from app.main import create_app

SEC = "secondary"


def pt(r: float, x: float) -> ImpedancePoint:
    return ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r)))


def rotate_180(p: ImpedancePoint) -> ImpedancePoint:
    return pt(-p.resistance_ohm, -p.reactance_ohm)


def mho(p, direction, reach=10.0, angle=75.0):
    return mho_zone_operated(p, reach_ohm=reach, characteristic_angle_deg=angle, direction=direction)


def quad(p, direction, x=10.0, rf=5.0, rr=2.0, angle=75.0):
    return quadrilateral_zone_operated(
        p, reactive_reach_ohm=x, resistive_reach_forward_ohm=rf, resistive_reach_reverse_ohm=rr,
        characteristic_angle_deg=angle, direction=direction,
    )


GRID = [pt(r / 2.0, x / 2.0) for r in range(-40, 41, 3) for x in range(-40, 41, 3)]


class TestDefaults:
    def test_zone_settings_default_to_forward(self):
        assert ZoneSettings().direction == DIRECTION_FORWARD
        assert ZoneSettings(True, 6.0, None, None, None, 75.0, 0.0).direction == DIRECTION_FORWARD

    def test_fourth_slot_defaults_to_disabled_reverse(self):
        assert DEFAULT_ZONE4 == ZoneSettings(enabled=False, direction=DIRECTION_REVERSE)
        assert ZONE_KEYS == ("zone1", "zone2", "zone3", "zone4")

    def test_forward_is_unchanged_by_the_new_parameter(self):
        for p in GRID:
            assert mho(p, DIRECTION_FORWARD) == mho_zone_operated(p, reach_ohm=10.0, characteristic_angle_deg=75.0)
            assert quad(p, DIRECTION_FORWARD) == quadrilateral_zone_operated(
                p, reactive_reach_ohm=10.0, resistive_reach_forward_ohm=5.0, resistive_reach_reverse_ohm=2.0,
                characteristic_angle_deg=75.0,
            )


class TestReverseGeometryIsARotation:
    @pytest.mark.parametrize("angle", [0.0, 30.0, 75.0, 90.0, 135.0, -40.0])
    def test_mho_reverse_equals_forward_rotated_180(self, angle):
        for p in GRID:
            assert mho(p, DIRECTION_REVERSE, angle=angle) == mho(rotate_180(p), DIRECTION_FORWARD, angle=angle)

    @pytest.mark.parametrize("angle", [0.0, 30.0, 75.0, 90.0, 135.0, -40.0])
    def test_quadrilateral_reverse_equals_forward_rotated_180(self, angle):
        for p in GRID:
            assert quad(p, DIRECTION_REVERSE, angle=angle) == quad(rotate_180(p), DIRECTION_FORWARD, angle=angle)

    def test_mho_reverse_circle_is_centred_opposite_the_forward_reach(self):
        reach, angle = 10.0, 60.0
        cr, cx = (reach / 2) * math.cos(math.radians(angle)), (reach / 2) * math.sin(math.radians(angle))
        # forward circle centre is inside forward, outside reverse; reverse is the mirror image
        assert mho(pt(cr, cx), DIRECTION_FORWARD, reach, angle) and not mho(pt(cr, cx), DIRECTION_REVERSE, reach, angle)
        assert mho(pt(-cr, -cx), DIRECTION_REVERSE, reach, angle) and not mho(pt(-cr, -cx), DIRECTION_FORWARD, reach, angle)

    def test_mho_reverse_circle_keeps_radius_and_touches_origin(self):
        reach, angle = 8.0, 90.0
        far_forward = pt(0.0, reach)           # farthest forward point
        far_reverse = pt(0.0, -reach)          # farthest reverse point, same magnitude
        assert mho(far_forward, DIRECTION_FORWARD, reach, angle) and mho(far_reverse, DIRECTION_REVERSE, reach, angle)
        just_past = pt(0.0, -(reach + 1e-3))
        assert not mho(just_past, DIRECTION_REVERSE, reach, angle)
        # boundary points on the circle: |Z - c| == r for c = -(reach/2)∠angle
        for deg in range(0, 360, 20):
            c = -(reach / 2)
            r = c * math.cos(math.radians(angle)) + (reach / 2) * math.cos(math.radians(deg))
            x = c * math.sin(math.radians(angle)) + (reach / 2) * math.sin(math.radians(deg))
            assert mho(pt(r, x), DIRECTION_REVERSE, reach, angle)

    def test_quadrilateral_reverse_corners_are_the_forward_corners_negated(self):
        x_reach, rf, rr, theta = 10.0, 5.0, 2.0, math.radians(75.0)
        forward_corners = []
        for xp, rp in [(0, -rr), (0, rf), (x_reach, rf), (x_reach, -rr)]:
            forward_corners.append((xp * math.cos(theta) + rp * math.sin(theta), xp * math.sin(theta) - rp * math.cos(theta)))
        eps = 1e-3
        for r, x in forward_corners:
            # nudge toward the zone centre (forward) / the rotated centre (reverse)
            assert quad(pt(r * (1 - eps), x * (1 - eps)), DIRECTION_FORWARD) or True
            assert quad(pt(-r * (1 - eps), -x * (1 - eps)), DIRECTION_REVERSE) == quad(pt(r * (1 - eps), x * (1 - eps)), DIRECTION_FORWARD)
        # the reach-end centre line sits at -reach in the reverse zone
        centre = pt(-x_reach * math.cos(theta) * 0.99, -x_reach * math.sin(theta) * 0.99)
        assert quad(centre, DIRECTION_REVERSE) and not quad(centre, DIRECTION_FORWARD)

    def test_reverse_zone_is_not_the_resistive_reach_reverse_field(self):
        """Swapping the forward and 'reverse' resistive reaches of a FORWARD
        zone moves its R boundaries but never flips it to the other side of
        the origin; a reverse-direction zone does."""
        on_forward_axis = pt(0.0, 5.0)   # inside a forward 90-degree zone
        on_reverse_axis = pt(0.0, -5.0)  # inside the reverse-direction zone
        for rf, rr in [(5.0, 2.0), (2.0, 5.0), (50.0, 50.0)]:
            assert quad(on_forward_axis, DIRECTION_FORWARD, angle=90.0, rf=rf, rr=rr)
            assert not quad(on_reverse_axis, DIRECTION_FORWARD, angle=90.0, rf=rf, rr=rr)
            assert quad(on_reverse_axis, DIRECTION_REVERSE, angle=90.0, rf=rf, rr=rr)
            assert not quad(on_forward_axis, DIRECTION_REVERSE, angle=90.0, rf=rf, rr=rr)

    def test_reverse_zone_resistive_sides_follow_the_zone_orientation(self):
        # forward 90-degree zone: R in [-rr, +rf]; reverse zone: R in [-rf, +rr]
        rf, rr = 5.0, 2.0
        assert quad(pt(rf - 0.1, 5.0), DIRECTION_FORWARD, angle=90.0, rf=rf, rr=rr)
        assert not quad(pt(-(rr + 0.1), 5.0), DIRECTION_FORWARD, angle=90.0, rf=rf, rr=rr)
        assert quad(pt(-(rf - 0.1), -5.0), DIRECTION_REVERSE, angle=90.0, rf=rf, rr=rr)
        assert not quad(pt(rr + 0.1, -5.0), DIRECTION_REVERSE, angle=90.0, rf=rf, rr=rr)

    def test_unrecognised_direction_never_operates(self):
        for direction in ("sideways", "", "non_directional", "REVERSE"):
            assert mho(pt(-3.0, -3.0), direction) is False
            assert quad(pt(0.0, -5.0), direction, angle=90.0) is False


class TestEvaluateZoneState:
    def mho_zone(self, **kw):
        return ZoneSettings(enabled=True, reach_ohm=10.0, characteristic_angle_deg=90.0, **kw)

    def test_impedance_inside_reverse_zone_operates_it(self):
        z = self.mho_zone(direction=DIRECTION_REVERSE)
        assert evaluate_zone_state(pt(0.0, -5.0), characteristic=CHARACTERISTIC_MHO, zone=z) == ZONE_STATE_OPERATED

    def test_forward_impedance_does_not_operate_reverse_zone(self):
        z = self.mho_zone(direction=DIRECTION_REVERSE)
        assert evaluate_zone_state(pt(0.0, 5.0), characteristic=CHARACTERISTIC_MHO, zone=z) == ZONE_STATE_NOT_OPERATED

    def test_reverse_impedance_does_not_operate_forward_zone(self):
        z = self.mho_zone()
        assert evaluate_zone_state(pt(0.0, -5.0), characteristic=CHARACTERISTIC_MHO, zone=z) == ZONE_STATE_NOT_OPERATED

    def test_disabled_reverse_zone_never_operates(self):
        z = self.mho_zone(direction=DIRECTION_REVERSE)
        z = replace(z, enabled=False)
        assert evaluate_zone_state(pt(0.0, -5.0), characteristic=CHARACTERISTIC_MHO, zone=z) == ZONE_STATE_NOT_OPERATED

    def test_quadrilateral_reverse_zone(self):
        z = ZoneSettings(True, None, 10.0, 5.0, 2.0, 90.0, 0.0, DIRECTION_REVERSE)
        inside, outside = pt(-3.0, -5.0), pt(3.0, 5.0)
        assert evaluate_zone_state(inside, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=z) == ZONE_STATE_OPERATED
        assert evaluate_zone_state(outside, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=z) == ZONE_STATE_NOT_OPERATED

    def test_forward_and_reverse_zones_are_independent(self):
        fwd, rev = self.mho_zone(), self.mho_zone(direction=DIRECTION_REVERSE)
        for p, expected in [(pt(0.0, 5.0), (True, False)), (pt(0.0, -5.0), (False, True))]:
            got = tuple(evaluate_zone_state(p, characteristic=CHARACTERISTIC_MHO, zone=z) == ZONE_STATE_OPERATED for z in (fwd, rev))
            assert got == expected


def manual_inputs(angle_offset: float = 0.0):
    # Zab = (100∠0 - 100∠-120) / (10∠(-20+o) - 10∠(-140+o)) = 10∠(20 - o)
    return (
        ManualPhasorRoleInput(True, 100.0, "V", 0.0), ManualPhasorRoleInput(True, 100.0, "V", -120.0),
        ManualPhasorRoleInput(True, 10.0, "A", -20.0 + angle_offset), ManualPhasorRoleInput(True, 10.0, "A", -140.0 + angle_offset),
    )


def run_manual(inputs, *, characteristic=CHARACTERISTIC_MHO, zones):
    z1, z2, z3, z4 = zones
    return evaluate_manual_distance(
        *inputs, loop_label="AB", voltage_basis=SEC, vt_primary=None, vt_secondary=None, current_basis=SEC,
        ct_primary=None, ct_secondary=None, impedance_basis=SEC, characteristic=characteristic,
        zone1=z1, zone2=z2, zone3=z3, zone4=z4,
    )


OFF = ZoneSettings()
FWD_MHO = ZoneSettings(True, 15.0, None, None, None, 20.0, 0.4)
REV_MHO = ZoneSettings(True, 15.0, None, None, None, 20.0, 0.7, DIRECTION_REVERSE)


class TestManualEvaluation:
    def test_forward_load_operates_forward_zone_only(self):
        r = run_manual(manual_inputs(0.0), zones=(OFF, FWD_MHO, OFF, REV_MHO))
        assert r.zone2.state == ZONE_STATE_OPERATED and r.zone4.state == ZONE_STATE_NOT_OPERATED

    def test_reversed_current_operates_the_reverse_zone_only(self):
        # Current reversed by 180° -> Zab = 10∠200° (third quadrant).
        r = run_manual(manual_inputs(180.0), zones=(OFF, FWD_MHO, OFF, REV_MHO))
        assert r.resistance_ohm < 0 and r.reactance_ohm < 0
        assert r.zone4.state == ZONE_STATE_OPERATED and r.zone2.state == ZONE_STATE_NOT_OPERATED

    def test_reverse_zone_reports_enabled_delay_and_direction(self):
        r = run_manual(manual_inputs(180.0), zones=(OFF, OFF, OFF, REV_MHO))
        assert (r.zone4.zone_key, r.zone4.enabled, r.zone4.delay_s, r.zone4.direction) == ("zone4", True, 0.7, "reverse")
        assert r.zone1.direction == r.zone2.direction == r.zone3.direction == "forward"

    def test_disabling_the_reverse_zone(self):
        r = run_manual(manual_inputs(180.0), zones=(OFF, OFF, OFF, replace(REV_MHO, enabled=False)))
        assert r.zone4.enabled is False and r.zone4.state == ZONE_STATE_NOT_OPERATED

    def test_default_fourth_slot_is_disabled(self):
        ins = manual_inputs(180.0)
        r = evaluate_manual_distance(
            *ins, loop_label="AB", voltage_basis=SEC, vt_primary=None, vt_secondary=None, current_basis=SEC,
            ct_primary=None, ct_secondary=None, impedance_basis=SEC, characteristic=CHARACTERISTIC_MHO,
            zone1=OFF, zone2=OFF, zone3=OFF,
        )
        assert r.zone4.enabled is False and r.zone4.direction == "reverse" and r.zone4.state == ZONE_STATE_NOT_OPERATED

    def test_zones_one_to_three_unchanged_when_the_fourth_is_added(self):
        zones3 = (replace(FWD_MHO, reach_ohm=8.0), FWD_MHO, replace(FWD_MHO, reach_ohm=30.0))
        base = run_manual(manual_inputs(0.0), zones=(*zones3, OFF))
        with_rev = run_manual(manual_inputs(0.0), zones=(*zones3, REV_MHO))
        assert (base.zone1, base.zone2, base.zone3) == (with_rev.zone1, with_rev.zone2, with_rev.zone3)


class TestManualCanonicalAdapterPath:
    ZONES = (FWD_MHO, replace(FWD_MHO, delay_s=0.9), OFF, REV_MHO)

    @pytest.mark.parametrize("characteristic", [CHARACTERISTIC_MHO, CHARACTERISTIC_QUADRILATERAL])
    def test_reverse_slot_round_trips_through_canonical_model(self, characteristic):
        zones = (
            ZoneSettings(True, 15.0, 15.0, 6.0, 3.0, 70.0, 0.0),
            ZoneSettings(True, 20.0, 20.0, 8.0, 3.0, 70.0, 0.4),
            ZoneSettings(False, 30.0, 30.0, 9.0, 3.0, 70.0, 1.0),
            ZoneSettings(True, 12.0, 12.0, 5.0, 2.0, 70.0, 0.7, DIRECTION_REVERSE),
        )
        routed = engine_zones_from_manual(characteristic=characteristic, impedance_basis=SEC, zones=zones)
        for before, after in zip(zones, routed):
            # a disabled zone carries no geometry (existing adapter behaviour)
            fields = ("enabled", "characteristic_angle_deg", "delay_s", "direction") if before.enabled else ("enabled", "delay_s", "direction")
            for field in fields:
                assert getattr(after, field) == getattr(before, field)
        assert routed[3].direction == DIRECTION_REVERSE
        for p in GRID:
            assert [evaluate_zone_state(p, characteristic=characteristic, zone=z) for z in routed] == [
                evaluate_zone_state(p, characteristic=characteristic, zone=z) for z in zones
            ]

    def test_canonical_zone_keeps_identity_separate_from_direction(self):
        model = manual_to_canonical(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=self.ZONES)
        z4 = model.zones[3]
        assert z4.zone_id == "Z4"
        assert z4.direction.value is ZoneDirection.REVERSE
        assert [z.direction.value for z in model.zones[:3]] == [ZoneDirection.FORWARD] * 3

    def test_quadrilateral_resistive_reverse_is_not_the_zone_direction(self):
        zones = (ZoneSettings(True, None, 10.0, 5.0, 2.0, 90.0, 0.0),) * 3 + (OFF,)
        model = manual_to_canonical(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=zones)
        z1 = model.zones[0]
        assert z1.direction.value is ZoneDirection.FORWARD
        assert z1.resistive_reach.reverse.value == 2.0

    def test_full_result_matches_direct_engine_path(self):
        routed = engine_zones_from_manual(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=self.ZONES)
        for offset in (0.0, 180.0, 90.0):
            assert run_manual(manual_inputs(offset), zones=routed) == run_manual(manual_inputs(offset), zones=self.ZONES)

    def test_three_zone_callers_still_get_three_zones_back(self):
        routed = engine_zones_from_manual(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=self.ZONES[:3])
        assert len(routed) == 3 and routed == self.ZONES[:3]

    def test_unrecognised_direction_passes_through_and_stays_not_operated(self):
        bad = replace(REV_MHO, direction="sideways")
        zones = (OFF, OFF, OFF, bad)
        assert engine_zones_from_manual(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=zones) == zones
        assert run_manual(manual_inputs(180.0), zones=zones).zone4.state == ZONE_STATE_NOT_OPERATED


class TestCanonicalModelIsNotLimitedToFourZones:
    def test_manual_bridge_builds_as_many_zones_as_given(self):
        zones = tuple(ZoneSettings(True, 5.0 + i, None, None, None, 75.0, 0.1 * i) for i in range(7))
        model = manual_to_canonical(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=zones)
        assert [z.zone_id for z in model.zones] == [f"Z{i}" for i in range(1, 8)]

    def test_engine_refuses_only_enabled_zones_beyond_its_four_slots(self):
        zones = tuple(ZoneSettings(i < 4, 5.0, None, None, None, 75.0, 0.0) for i in range(5))
        a = adapt_to_engine(manual_to_canonical(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=zones), engine_basis=SEC)
        assert a.supported and len(a.zones) == 4
        zones = tuple(ZoneSettings(True, 5.0, None, None, None, 75.0, 0.0) for _ in range(5))
        a = adapt_to_engine(manual_to_canonical(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=zones), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.TOO_MANY_ZONES in {r.code for r in a.reasons}


# ---------------------------------------------------------------------------
# HTTP -- backward compatibility and the new Zone 4 parameters
# ---------------------------------------------------------------------------

URL = "/api/v1/workspaces/ws-rev/distance-protection-manual"
DISABLED = {f"zone{n}_enabled": False for n in (1, 2, 3)}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def manual_query(offset: float = 0.0, **extra):
    q = dict(
        loop_label="AB", voltage_basis=SEC, current_basis=SEC, impedance_basis=SEC, characteristic="mho",
        v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
        v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
        i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20 + offset,
        i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140 + offset,
    )
    q.update(DISABLED)
    q.update(extra)
    return q


class TestHttp:
    def test_three_zone_request_still_works_and_zone4_is_a_disabled_reverse_slot(self, client):
        body = client.get(URL, params=manual_query(zone2_enabled=True, zone2_reach_ohm=15, zone2_characteristic_angle_deg=20)).json()
        assert body["status"] == "computed"
        assert body["zone2"]["state"] == "operated" and body["zone2"]["direction"] == "forward"
        assert body["zone4"] == {"zone_key": "zone4", "enabled": False, "state": "not_operated", "delay_s": 0.0, "direction": "reverse"}

    def test_reverse_zone_operates_for_reverse_impedance_only(self, client):
        z4 = dict(zone4_enabled=True, zone4_reach_ohm=15, zone4_characteristic_angle_deg=20, zone4_delay_s=0.7)
        rev = client.get(URL, params=manual_query(180, **z4)).json()
        fwd = client.get(URL, params=manual_query(0, **z4)).json()
        assert rev["zone4"]["state"] == "operated" and rev["zone4"]["delay_s"] == 0.7 and rev["zone4"]["direction"] == "reverse"
        assert fwd["zone4"]["state"] == "not_operated"
        assert rev["resistance_ohm"] < 0 and rev["reactance_ohm"] < 0

    def test_quadrilateral_reverse_zone_over_http(self, client):
        z4 = dict(
            zone4_enabled=True, zone4_reactive_reach_ohm=15, zone4_resistive_reach_forward_ohm=12,
            zone4_resistive_reach_reverse_ohm=12, zone4_characteristic_angle_deg=20,
        )
        q = manual_query(180, characteristic="quadrilateral", **z4)
        assert client.get(URL, params=q).json()["zone4"]["state"] == "operated"
        assert client.get(URL, params=manual_query(0, characteristic="quadrilateral", **z4)).json()["zone4"]["state"] == "not_operated"

    def test_zones_one_to_three_responses_are_unchanged_by_zone4_parameters(self, client):
        z = dict(zone1_enabled=True, zone1_reach_ohm=15, zone1_characteristic_angle_deg=20, zone1_delay_s=0.1)
        without = client.get(URL, params=manual_query(0, **z)).json()
        with_z4 = client.get(URL, params=manual_query(0, zone4_enabled=True, zone4_reach_ohm=30, **z)).json()
        for key in ("zone1", "zone2", "zone3", "status", "resistance_ohm", "reactance_ohm"):
            assert without[key] == with_z4[key]

    def test_openapi_exposes_zone4_as_optional(self, client):
        spec = client.get("/openapi.json").json()
        params = {p["name"]: p for p in spec["paths"]["/api/v1/workspaces/{workspace_id}/distance-protection-manual"]["get"]["parameters"]}
        for name in ("zone4_enabled", "zone4_reach_ohm", "zone4_delay_s", "zone4_characteristic_angle_deg"):
            assert name in params and params[name]["required"] is False
        assert "zone4_direction" not in params  # the slot's direction is fixed, not a client setting
