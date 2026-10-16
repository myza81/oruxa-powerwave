"""The V1 -> V2 compatibility compiler (DEC-199 Phase 1): every V1 shape -- mho, polar (rotated) quadrilateral and
explicit R/X quadrilateral, forward and reverse -- compiles to a V2 characteristic with V1's membership, and every zone V1
never operates compiles to nothing."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.domain.distance_geometry import Frame, guard_distance
from app.domain.distance_geometry_compat import compile_v1_zone
from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    GEOMETRY_EXPLICIT_RX,
    ZoneSettings,
)
from tests.relay_conformance.golden import _boundary_distance, v1_inside, v1_key_geometry

MHO = [ZoneSettings(enabled=True, reach_ohm=reach, characteristic_angle_deg=angle, direction=d)
       for reach in (0.5, 8.0, 120.0) for angle in (45.0, 75.0, 90.0, 110.0) for d in ("forward", "reverse")]
POLAR = [ZoneSettings(enabled=True, reactive_reach_ohm=xr, resistive_reach_forward_ohm=rr, resistive_reach_reverse_ohm=rl,
                      characteristic_angle_deg=angle, direction=d)
         for xr, rr, rl in ((1.43, 2.11, 0.0), (6.0, 4.0, 1.5), (40.0, 25.0, 10.0)) for angle in (60.0, 80.0, 90.0)
         for d in ("forward", "reverse")]
EXPLICIT = [ZoneSettings(enabled=True, reactive_reach_ohm=xr, resistive_reach_forward_ohm=rr, resistive_reach_reverse_ohm=rl,
                         characteristic_angle_deg=None, direction=d, geometry_mode=GEOMETRY_EXPLICIT_RX)
            for xr, rr, rl in ((6.0, 4.0, 0.0), (2.0, 1.5, 0.5), (150.0, 65.0, 65.0)) for d in ("forward", "reverse")]
CASES = [(CHARACTERISTIC_MHO, z) for z in MHO] + [(CHARACTERISTIC_QUADRILATERAL, z) for z in POLAR + EXPLICIT]


def label(case) -> str:
    ch, z = case
    return f"{ch}-{z.geometry_mode}-{z.direction}-{z.reach_ohm or z.reactive_reach_ohm}-{z.characteristic_angle_deg}"


@pytest.mark.parametrize("case", CASES, ids=label)
def test_v2_membership_equals_v1_over_a_dense_grid(case):
    characteristic, zone = case
    v2 = compile_v1_zone(characteristic, zone)
    assert v2 is not None and v2.frame is Frame.ABSOLUTE
    key = v1_key_geometry(characteristic, zone)
    pts = [tuple(key["center"])] if key["kind"] == "circle" else [tuple(v) for v in key["vertices"]]
    span = max(max(abs(p[0]) for p in pts), max(abs(p[1]) for p in pts)) + (key.get("radius") or 0.0)
    guard = guard_distance(span)
    compared = 0
    for i in range(41):
        for j in range(41):
            r, x = -1.5 * span + 3 * span * i / 40, -1.5 * span + 3 * span * j / 40
            if _boundary_distance(characteristic, zone, r, x) < guard:
                continue
            assert v2.contains(r, x) == v1_inside(characteristic, zone, r, x), (r, x)
            compared += 1
    assert compared > 1500


@pytest.mark.parametrize("case", CASES, ids=label)
def test_v2_outline_equals_the_v1_key_geometry(case):
    characteristic, zone = case
    v2 = compile_v1_zone(characteristic, zone).outline()
    key = v1_key_geometry(characteristic, zone)
    if key["kind"] == "circle":
        assert v2.kind == "circle"
        assert math.hypot(v2.center[0] - key["center"][0], v2.center[1] - key["center"][1]) <= 1e-6
        assert abs(v2.radius - key["radius"]) <= 1e-6
    else:
        assert v2.kind == "polygon" and len(v2.vertices) == 4 and not v2.clipped
        for v in key["vertices"]:
            assert min(math.hypot(v[0] - w[0], v[1] - w[1]) for w in v2.vertices) <= 1e-6


@pytest.mark.parametrize("change", [
    {"enabled": False}, {"delay_s": None}, {"characteristic_angle_deg": None}, {"characteristic_angle_deg": float("nan")},
    {"direction": "non_directional"}, {"reactive_reach_ohm": 0.0}, {"resistive_reach_forward_ohm": -1.0},
    {"resistive_reach_reverse_ohm": -0.1}, {"reactive_reach_ohm": None}, {"reactive_reach_ohm": float("inf")},
])
def test_a_zone_v1_never_operates_compiles_to_nothing(change):
    zone = replace(POLAR[0], **change)
    assert compile_v1_zone(CHARACTERISTIC_QUADRILATERAL, zone) is None
    assert not any(v1_inside(CHARACTERISTIC_QUADRILATERAL, zone, r / 4, x / 4) for r in range(-20, 21) for x in range(-20, 21))


@pytest.mark.parametrize("change", [{"reach_ohm": None}, {"reach_ohm": 0.0}, {"characteristic_angle_deg": None}])
def test_an_incomplete_mho_compiles_to_nothing(change):
    assert compile_v1_zone(CHARACTERISTIC_MHO, replace(MHO[0], **change)) is None


def test_explicit_limits_are_never_a_mho_and_an_unknown_characteristic_is_nothing():
    assert compile_v1_zone(CHARACTERISTIC_MHO, EXPLICIT[0]) is None
    assert compile_v1_zone("lenticular", POLAR[0]) is None


def test_the_compiler_is_relay_neutral():
    from pathlib import Path

    for name in ("distance_geometry.py", "distance_geometry_compat.py"):
        text = (Path(__file__).resolve().parents[1] / "app" / "domain" / name).read_text(encoding="utf-8").lower()
        assert "catalog" not in text.replace("never a catalog", "") and "profile_id" not in text
        for oem in ("siemens", "toshiba", "hitachi", "abb", "schneider", "micom", "rel670", "7sa", "grz", "p441"):
            assert oem not in text, oem
