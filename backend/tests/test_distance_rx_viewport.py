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
