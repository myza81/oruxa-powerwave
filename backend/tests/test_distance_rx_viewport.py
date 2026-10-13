"""Behavioural tests for the Distance Protection R-X viewport helpers
(Fit Zones / Zoom / ticks). The helpers are pure, DOM-free JavaScript in
frontend/index.html (between the WW_DISTANCE_VIEWPORT_PURE_BEGIN/END
markers); they are extracted and executed under node. Viewport-only --
protection calculations are covered by test_distance_protection_*.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not available")


def _pure_block() -> str:
    src = FRONTEND.read_text(encoding="utf-8")
    block = re.search(r"WW_DISTANCE_VIEWPORT_PURE_BEGIN(.*?)// WW_DISTANCE_VIEWPORT_PURE_END", src, re.S).group(1)
    fmt = re.search(r"function wwImpedanceFormatTick\(value\) \{.*?\n        \}", src, re.S).group(0)
    return fmt + "\n" + block


def _run(expr: str):
    js = _pure_block() + f"\nprocess.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _zone(**kw):
    z = dict(enabled=True, characteristicAngleDeg=90, reachOhm=None, reactiveReachOhm=None,
             resistiveForwardOhm=None, resistiveReverseOhm=None)
    z.update(kw)
    return z


def _quad(x, rf, rr, **kw):
    return _zone(reactiveReachOhm=x, resistiveForwardOhm=rf, resistiveReverseOhm=rr, **kw)


def _zones(z1=None, z2=None, z3=None):
    off = _zone(enabled=False)
    return {"zone1": z1 or off, "zone2": z2 or off, "zone3": z3 or off}


def fit(zones, ch):
    return _run(f"wwDistanceFitView({json.dumps(zones)}, {json.dumps(ch)})")


def test_small_quadrilateral_fit_is_tight_with_margin():
    # X=10, Rf=4, Rr=2 at 90 deg: R in [-2, 4] (span 6), X in [0, 10] (span 10)
    v = fit(_zones(_quad(10, 4, 2)), "quadrilateral")
    assert v["centerR"] == pytest.approx(1.0)
    assert v["centerX"] == pytest.approx(5.0)
    assert v["half"] == pytest.approx(5 * 1.2)
    # far tighter than the legacy overview (nice limit of 10*1.3 -> 20)
    assert v["half"] < 10


def test_nested_quadrilaterals_outer_zone_determines_fit():
    v = fit(_zones(_quad(5, 2, 1), _quad(10, 4, 2), _quad(20, 8, 4)), "quadrilateral")
    assert v["centerX"] == pytest.approx(10.0)
    assert v["half"] == pytest.approx(10 * 1.2)


def test_mho_full_circle_included():
    v = fit(_zones(_zone(reachOhm=10)), "mho")
    # circle: centre (0, 5), radius 5 -> X in [0,10], R in [-5,5]
    assert v["centerR"] == pytest.approx(0.0, abs=1e-9)
    assert v["centerX"] == pytest.approx(5.0)
    assert v["half"] == pytest.approx(5 * 1.2)


def test_negative_r_extent_not_clipped():
    v = fit(_zones(_quad(4, 1, 9)), "quadrilateral")  # R in [-9, 1], X in [0, 4]
    assert v["centerR"] - v["half"] <= -9
    assert v["centerR"] + v["half"] >= 1
    assert v["centerX"] - v["half"] <= 0 and v["centerX"] + v["half"] >= 4


def test_rotated_characteristic_uses_true_geometry():
    zone = _quad(10, 4, 2, characteristicAngleDeg=75)
    v = fit(_zones(zone), "quadrilateral")
    b = _run(f"wwDistanceZoneBounds({json.dumps(zone)}, 'quadrilateral')")
    assert v["centerR"] - v["half"] <= b["rMin"] and v["centerR"] + v["half"] >= b["rMax"]
    assert v["centerX"] - v["half"] <= b["xMin"] and v["centerX"] + v["half"] >= b["xMax"]


def test_disabled_zone_excluded():
    big_disabled = _quad(100, 40, 20, enabled=False)
    v = fit(_zones(_quad(10, 4, 2), big_disabled), "quadrilateral")
    assert v["half"] == pytest.approx(5 * 1.2)


def test_no_valid_zone_returns_null():
    assert fit(_zones(), "quadrilateral") is None
    assert fit(_zones(_quad(0, 4, 2)), "quadrilateral") is None  # not drawable
    assert fit(_zones(_zone(reachOhm=None)), "mho") is None
    assert fit(_zones(_quad(None, 4, 2)), "quadrilateral") is None


def test_zone_for_other_characteristic_not_fitted():
    # quadrilateral fields only -> nothing to fit in Mho mode
    assert fit(_zones(_quad(10, 4, 2)), "mho") is None


def test_zoom_in_out_keeps_centre_and_is_predictable():
    v = {"centerR": 3, "centerX": 7, "half": 12}
    zi = _run(f"wwDistanceZoomView({json.dumps(v)}, WW_DISTANCE_VIEW_ZOOM_FACTOR)")
    zo = _run(f"wwDistanceZoomView({json.dumps(v)}, 1 / WW_DISTANCE_VIEW_ZOOM_FACTOR)")
    assert (zi["centerR"], zi["centerX"]) == (3, 7) and (zo["centerR"], zo["centerX"]) == (3, 7)
    assert zi["half"] == pytest.approx(8.0) and zo["half"] == pytest.approx(18.0)


def test_zoom_limits_respected():
    lo = _run("wwDistanceZoomView({centerR:0,centerX:0,half:0.11}, 1.5)")["half"]
    hi = _run("wwDistanceZoomView({centerR:0,centerX:0,half:99999}, 1/1.5)")["half"]
    assert lo == pytest.approx(_run("WW_DISTANCE_VIEW_MIN_HALF"))
    assert hi == pytest.approx(_run("WW_DISTANCE_VIEW_MAX_HALF"))


def test_fit_clamps_tiny_characteristics():
    v = fit(_zones(_quad(0.01, 0.004, 0.002)), "quadrilateral")
    assert v["half"] == pytest.approx(_run("WW_DISTANCE_VIEW_MIN_HALF"))


def test_view_is_square_so_scale_is_one_to_one():
    # A view carries ONE half-span: both axes cover exactly 2*half ohm and
    # the renderer's single pxPerOhm = RADIUS / half maps each to the same
    # 2*RADIUS pixels. A Mho circle's bounds are therefore square too.
    v = fit(_zones(_quad(10, 4, 2)), "quadrilateral")
    assert set(v) == {"centerR", "centerX", "half"}
    b = _run("wwDistanceZoneBounds(%s, 'mho')" % json.dumps(_zone(reachOhm=8, characteristicAngleDeg=60)))
    assert b["rMax"] - b["rMin"] == pytest.approx(b["xMax"] - b["xMin"])


def test_ticks_scale_with_range_and_format_sensibly():
    assert _run("wwDistanceNiceStep(12)") == 2
    assert _run("wwDistanceNiceStep(4000)") == 500
    assert _run("wwDistanceTickValues(-1.2, 11.2, 2)") == [0, 2, 4, 6, 8, 10]
    assert 4 <= len(_run("wwDistanceTickValues(-6, 6, wwDistanceNiceStep(12))")) <= 9
    assert _run("wwDistanceFormatTick(0.25, 0.05)") == "0.25"
    assert _run("wwDistanceFormatTick(1.05, 0.05)") == "1.05"
    assert _run("wwDistanceFormatTick(8, 2)") == "8.0"
    assert _run("wwDistanceFormatTick(2000, 500)") == "2.0k"


def test_degenerate_input_stays_finite():
    v = fit(_zones(_zone(reachOhm=1e-9)), "mho")
    assert all(isinstance(v[k], (int, float)) for k in v)
    assert v["half"] >= 0.1


# --- Reverse Zone (zone4: direction "reverse" = the characteristic rotated 180 degrees) ---


def _rev(z):
    return dict(z, direction="reverse")


def test_reverse_mho_fit_is_mirrored_through_the_origin():
    fwd = fit(_zones(_zone(reachOhm=10, characteristicAngleDeg=60)), "mho")
    rev = fit({"zone1": _zone(enabled=False), "zone2": _zone(enabled=False), "zone3": _zone(enabled=False),
               "zone4": _rev(_zone(reachOhm=10, characteristicAngleDeg=60))}, "mho")
    assert rev["centerR"] == pytest.approx(-fwd["centerR"])
    assert rev["centerX"] == pytest.approx(-fwd["centerX"])
    assert rev["half"] == pytest.approx(fwd["half"])


def test_reverse_quadrilateral_bounds_are_the_negated_forward_bounds():
    z = _quad(10, 4, 2, characteristicAngleDeg=75)
    fwd = _run(f"wwDistanceZoneBounds({json.dumps(z)}, 'quadrilateral')")
    rev = _run(f"wwDistanceZoneBounds({json.dumps(_rev(z))}, 'quadrilateral')")
    assert rev["rMin"] == pytest.approx(-fwd["rMax"]) and rev["rMax"] == pytest.approx(-fwd["rMin"])
    assert rev["xMin"] == pytest.approx(-fwd["xMax"]) and rev["xMax"] == pytest.approx(-fwd["xMin"])


def test_fit_zones_includes_the_reverse_zone_negative_extent():
    off = _zone(enabled=False)
    fwd_only = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off, "zone4": off}, "quadrilateral")
    both = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off, "zone4": _rev(_quad(10, 4, 2))}, "quadrilateral")
    # forward X in [0, 10], reverse X in [-10, 0] -> union spans [-10, 10]
    assert both["centerX"] == pytest.approx(0.0)
    assert both["half"] > fwd_only["half"]
    assert both["half"] == pytest.approx(10 * 1.2)  # span 20 (larger axis) / 2 * 1.2 margin


def test_disabled_reverse_zone_does_not_affect_fit_and_missing_zone4_is_ignored():
    off = _zone(enabled=False)
    base = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off}, "quadrilateral")  # no zone4 key at all
    with_off = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off, "zone4": _rev(_zone(enabled=False))}, "quadrilateral")
    assert base == with_off


def test_forward_zone_bounds_are_unchanged_by_the_direction_field():
    z = _quad(10, 4, 2, characteristicAngleDeg=75)
    assert _run(f"wwDistanceZoneBounds({json.dumps(z)}, 'quadrilateral')") == _run(
        f"wwDistanceZoneBounds({json.dumps(dict(z, direction='forward'))}, 'quadrilateral')"
    )


def test_fit_view_stays_square_with_a_reverse_zone():
    # 1:1 R/X scaling is a property of the view being a square window.
    v = fit({"zone1": _quad(10, 4, 2), "zone2": _zone(enabled=False), "zone3": _zone(enabled=False),
             "zone4": _rev(_quad(6, 3, 3))}, "quadrilateral")
    assert set(v) == {"centerR", "centerX", "half"}


# --- Slice 10: Fit Zones walks the whole zone collection, whatever the keys ---------------------


def test_fit_zones_includes_a_fifth_zone_under_any_key():
    off = _zone(enabled=False)
    base = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off, "zone4": off}, "quadrilateral")
    with_fifth = fit({"zone1": _quad(10, 4, 2), "zone2": off, "zone3": off, "zone4": off, "z_zp": _quad(40, 30, 0)}, "quadrilateral")
    assert with_fifth["half"] > base["half"]
    # the fifth zone alone defines the view when it is the only one drawn
    alone = fit({"z_zp": _quad(40, 30, 0, characteristicAngleDeg=90)}, "quadrilateral")
    assert alone["centerR"] == pytest.approx(15.0) and alone["centerX"] == pytest.approx(20.0)
    assert alone["half"] == pytest.approx(20 * 1.2)  # X span 40 is the larger axis


def test_fit_zones_includes_an_extra_reverse_zone_and_ignores_a_disabled_extra_zone():
    forward = {"zone1": _quad(10, 4, 2)}
    reverse = dict(forward, z_zr=_rev(_quad(10, 4, 2)))
    assert fit(reverse, "quadrilateral")["half"] > fit(forward, "quadrilateral")["half"]
    # a disabled zone never affects the fit, however large its stored numbers
    big_but_off = dict(forward, z_off=_quad(1000, 1000, 1000, enabled=False))
    assert fit(big_but_off, "quadrilateral") == fit(forward, "quadrilateral")


def test_fit_zones_is_independent_of_zone_order():
    zones = {"a": _quad(10, 4, 2), "b": _quad(20, 5, 1, characteristicAngleDeg=75), "c": _rev(_quad(8, 3, 3))}
    reordered = {"c": zones["c"], "a": zones["a"], "b": zones["b"]}
    assert fit(zones, "quadrilateral") == fit(reordered, "quadrilateral")


def test_fit_zones_with_no_drawable_zone_is_null_for_any_collection():
    assert fit({"zone1": _zone(enabled=False), "z_zp": _zone(enabled=False)}, "mho") is None
    assert fit({}, "mho") is None


# ---- explicit R/X zones: X / +R / -R limits and no angle ----


def _explicit(x, rf, rr, **kw):
    return _zone(geometryMode="explicit_rx", characteristicAngleDeg=None, reactiveReachOhm=x,
                 resistiveForwardOhm=rf, resistiveReverseOhm=rr, **kw)


def _bounds(zone, ch="quadrilateral"):
    return _run(f"wwDistanceZoneBounds({json.dumps(zone)}, {json.dumps(ch)})")


def test_an_explicit_rx_zone_is_drawn_in_the_orthogonal_frame_without_an_angle():
    b = _bounds(_explicit(2.74, 1.84, 0.0))
    assert b["rMax"] == pytest.approx(1.84) and b["xMax"] == pytest.approx(2.74)
    assert b["rMin"] == pytest.approx(0.0, abs=1e-9) and b["xMin"] == pytest.approx(0.0, abs=1e-9)


def test_an_explicit_rx_zone_equals_a_polar_zone_at_90_degrees():
    explicit, polar = _bounds(_explicit(4.47, 2.12, 0.5)), _bounds(_quad(4.47, 2.12, 0.5))
    for key in ("rMin", "rMax", "xMin", "xMax"):
        assert explicit[key] == pytest.approx(polar[key], abs=1e-9)


def test_a_reverse_explicit_rx_zone_is_the_forward_one_rotated_180_degrees():
    fwd, rev = _bounds(_explicit(0.69, 0.46, 0.0)), _bounds(_explicit(0.69, 0.46, 0.0, direction="reverse"))
    assert rev["rMin"] == pytest.approx(-fwd["rMax"]) and rev["rMax"] == pytest.approx(-fwd["rMin"], abs=1e-9)
    assert rev["xMin"] == pytest.approx(-fwd["xMax"]) and rev["xMax"] == pytest.approx(-fwd["xMin"], abs=1e-9)


def test_a_polar_zone_without_an_angle_is_still_not_drawn_but_an_explicit_one_is():
    assert _bounds(_quad(4, 3, 1, characteristicAngleDeg=None)) is None
    assert _bounds(_explicit(4, 3, 1)) is not None


def test_polar_and_explicit_zones_fit_together():
    v = fit({"a": _quad(5, 2, 1, characteristicAngleDeg=80), "b": _explicit(10, 4, 2)}, "quadrilateral")
    assert v["half"] >= 5 * 1.2 and v["centerX"] > 0


def test_the_frame_angle_helper_never_invents_an_angle_for_a_polar_zone():
    assert _run('wwDistanceZoneFrameAngleDeg({"geometryMode":"polar","characteristicAngleDeg":75})') == 75
    assert _run('wwDistanceZoneFrameAngleDeg({"geometryMode":"explicit_rx","characteristicAngleDeg":null})') == 90
    assert _run('wwDistanceZoneFrameAngleDeg({"characteristicAngleDeg":null})') is None  # a polar zone's missing angle stays missing
