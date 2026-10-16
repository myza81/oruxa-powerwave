"""V1 geometry goldens for the conformance expectations (DEC-199 Phase 1).

Built **only from V1**, never from the V2 kernel: the key geometry follows V1's own parameterisation (the formulas the
frontend draws: a mho circle on the diameter origin -> reach, a quadrilateral's corners from `x'` / `r'`), and every
membership is V1's `evaluate_zone_state`. A golden describes a zone exactly as the V1 engine draws / evaluates it today.

Per drawn zone (an Apply zone V1 evaluates; disabled or incomplete zones are listed in ``not_drawn``)::

    id, characteristic, geometry_mode, direction
    basis      the numeric engine inputs the shape comes from
    outline    {"kind": "polygon", "vertices": [[R, X], ...]}  (V1 corner order) | {"kind": "circle", "center", "radius"}
    grid       {"r": [min, max], "x": [min, max], "n": 17, "inside": "0101.."}  -- an n x n grid over the zone's extent
               (with the origin) plus a 25 % margin, row-major from (r_min, x_min), X fastest; "1" inside, "0" outside,
               "." a point too close to a boundary to compare (see `distance_geometry.guard_distance`)
    probes     [[R, X, 0|1], ...]  -- just inside / just outside each boundary (1 % of the extent) and the 180 deg
               reflection of each inside probe

Coordinates are rounded to 6 decimals and the rounded point is what V1 evaluated.
"""

from __future__ import annotations

import math
from typing import Any

from app.domain.distance_geometry import TOLERANCE_OHM, guard_distance
from app.domain.distance_protection import (
    ALGORITHM_VERSION,
    CHARACTERISTIC_MHO,
    DIRECTION_REVERSE,
    GEOMETRY_EXPLICIT_RX,
    ZONE_STATE_OPERATED,
    ZoneSettings,
    evaluate_zone_state,
)
from app.domain.impedance import ImpedancePoint

GRID_N = 17
GRID_MARGIN = 0.25
PROBE_FRACTION = 1e-2
_SETTINGS = ("enabled", "reach_ohm", "reactive_reach_ohm", "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm",
             "characteristic_angle_deg", "delay_s", "direction", "geometry_mode")


def zone_settings(apply_zone: dict[str, Any]) -> ZoneSettings:
    """The V1 engine input of one Apply zone (the fields map one to one)."""
    return ZoneSettings(**{k: apply_zone[k] for k in _SETTINGS if k in apply_zone})


def _round(v: float) -> float:
    return round(v, 6) + 0.0                                  # + 0.0 turns -0.0 into 0.0


def v1_inside(characteristic: str, zone: ZoneSettings, r: float, x: float) -> bool:
    point = ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r)))
    return evaluate_zone_state(point, characteristic=characteristic, zone=zone) == ZONE_STATE_OPERATED


def _theta_deg(zone: ZoneSettings) -> float:
    return 90.0 if zone.geometry_mode == GEOMETRY_EXPLICIT_RX else zone.characteristic_angle_deg


def v1_draws(characteristic: str, zone: ZoneSettings) -> bool:
    """Whether V1 evaluates / draws the zone: some point operates it (its reach point does for every valid shape)."""
    if not zone.enabled or zone.delay_s is None:
        return False
    sign = -1.0 if zone.direction == DIRECTION_REVERSE else 1.0
    try:
        t = math.radians(_theta_deg(zone))
        if characteristic == CHARACTERISTIC_MHO:
            probe = (sign * zone.reach_ohm / 2 * math.cos(t), sign * zone.reach_ohm / 2 * math.sin(t))
        else:
            probe = (sign * (zone.reactive_reach_ohm / 2 * math.cos(t)), sign * (zone.reactive_reach_ohm / 2 * math.sin(t)))
    except TypeError:
        return False
    return v1_inside(characteristic, zone, *probe)


def v1_key_geometry(characteristic: str, zone: ZoneSettings) -> dict[str, Any]:
    sign = -1.0 if zone.direction == DIRECTION_REVERSE else 1.0
    t = math.radians(_theta_deg(zone))
    if characteristic == CHARACTERISTIC_MHO:
        half = zone.reach_ohm / 2.0
        return {"kind": "circle", "center": [sign * half * math.cos(t), sign * half * math.sin(t)], "radius": half}
    xr, rr, rl = zone.reactive_reach_ohm, zone.resistive_reach_forward_ohm, zone.resistive_reach_reverse_ohm
    corners = [(0.0, -rl), (0.0, rr), (xr, rr), (xr, -rl)]                # (x', r'), the frontend's order
    return {"kind": "polygon", "vertices": [[sign * (a * math.cos(t) + b * math.sin(t)), sign * (a * math.sin(t) - b * math.cos(t))]
                                            for a, b in corners]}


def _boundary_distance(characteristic: str, zone: ZoneSettings, r: float, x: float) -> float:
    """Distance to the nearest V1 boundary line / circle (V1's own frame; lines taken as infinite -- conservative)."""
    if zone.direction == DIRECTION_REVERSE:
        r, x = -r, -x
    t = math.radians(_theta_deg(zone))
    if characteristic == CHARACTERISTIC_MHO:
        half = zone.reach_ohm / 2.0
        return abs(math.hypot(r - half * math.cos(t), x - half * math.sin(t)) - half)
    xp, rp = r * math.cos(t) + x * math.sin(t), r * math.sin(t) - x * math.cos(t)
    return min(abs(xp), abs(xp - zone.reactive_reach_ohm), abs(rp - zone.resistive_reach_forward_ohm),
               abs(rp + zone.resistive_reach_reverse_ohm))


def _extent(outline: dict[str, Any]) -> tuple[float, float, float, float]:
    if outline["kind"] == "circle":
        (cr, cx), rad = outline["center"], outline["radius"]
        pts = [(cr - rad, cx - rad), (cr + rad, cx + rad)]
    else:
        pts = [tuple(v) for v in outline["vertices"]]
    rs, xs = [p[0] for p in pts] + [0.0], [p[1] for p in pts] + [0.0]
    return min(rs), max(rs), min(xs), max(xs)


def _probes(characteristic: str, zone: ZoneSettings, outline: dict[str, Any], delta: float) -> list[tuple[float, float]]:
    out = []
    if outline["kind"] == "circle":
        (cr, cx), rad = outline["center"], outline["radius"]
        for k in range(8):
            a = 2 * math.pi * k / 8
            out += [(cr + (rad - delta) * math.cos(a), cx + (rad - delta) * math.sin(a)),
                    (cr + (rad + delta) * math.cos(a), cx + (rad + delta) * math.sin(a))]
        return out
    verts = outline["vertices"]
    gr, gx = sum(v[0] for v in verts) / len(verts), sum(v[1] for v in verts) / len(verts)
    for i in range(len(verts)):
        (ar, ax), (br, bx) = verts[i], verts[(i + 1) % len(verts)]
        mr, mx = (ar + br) / 2, (ax + bx) / 2
        length = math.hypot(br - ar, bx - ax)
        nr, nx = (bx - ax) / length, -(br - ar) / length
        if nr * (mr - gr) + nx * (mx - gx) < 0:                       # point the normal away from the centroid
            nr, nx = -nr, -nx
        out += [(mr - delta * nr, mx - delta * nx), (mr + delta * nr, mx + delta * nx)]
    return out


def zone_golden(characteristic: str, apply_zone: dict[str, Any]) -> dict[str, Any]:
    zone = zone_settings(apply_zone)
    outline = v1_key_geometry(characteristic, zone)
    r0, r1, x0, x1 = _extent(outline)
    span = max(r1 - r0, x1 - x0)
    r0, r1, x0, x1 = (_round(v) for v in (r0 - GRID_MARGIN * span, r1 + GRID_MARGIN * span, x0 - GRID_MARGIN * span, x1 + GRID_MARGIN * span))
    scale = max(abs(r0), abs(r1), abs(x0), abs(x1))
    guard = guard_distance(scale)
    inside = []
    for i in range(GRID_N):
        r = r0 + i * (r1 - r0) / (GRID_N - 1)
        for j in range(GRID_N):
            x = x0 + j * (x1 - x0) / (GRID_N - 1)
            if _boundary_distance(characteristic, zone, r, x) < guard:
                inside.append(".")
            else:
                inside.append("1" if v1_inside(characteristic, zone, r, x) else "0")
    probes = []
    for r, x in _probes(characteristic, zone, outline, PROBE_FRACTION * scale):
        r, x = _round(r), _round(x)
        if _boundary_distance(characteristic, zone, r, x) >= guard:
            probes.append([r, x, int(v1_inside(characteristic, zone, r, x))])
    for r, x, flag in list(probes):
        if flag and _boundary_distance(characteristic, zone, -r, -x) >= guard:
            probes.append([_round(-r), _round(-x), int(v1_inside(characteristic, zone, -r, -x))])
    basis = {k: apply_zone[k] for k in ("characteristic_angle_deg", "reach_ohm", "reactive_reach_ohm",
                                        "resistive_reach_forward_ohm", "resistive_reach_reverse_ohm") if apply_zone.get(k) is not None}
    rounded = ({"kind": "circle", "center": [_round(v) for v in outline["center"]], "radius": _round(outline["radius"])}
               if outline["kind"] == "circle" else {"kind": "polygon", "vertices": [[_round(a), _round(b)] for a, b in outline["vertices"]]})
    return {"id": apply_zone["id"], "characteristic": characteristic, "geometry_mode": zone.geometry_mode,
            "direction": zone.direction, "basis": basis, "outline": rounded,
            "grid": {"r": [r0, r1], "x": [x0, x1], "n": GRID_N, "inside": "".join(inside)}, "probes": probes}


def v1_golden(apply: dict[str, Any] | None) -> dict[str, Any]:
    """The golden section for an expectation, from its Apply outcome (the V1 engine input)."""
    zones, not_drawn = [], []
    characteristic = (apply or {}).get("characteristic")
    for z in (apply or {}).get("zones", []):
        if v1_draws(characteristic, zone_settings(z)):
            zones.append(zone_golden(characteristic, z))
        else:
            not_drawn.append(z["id"])
    return {"engine": ALGORITHM_VERSION, "tolerance_ohm": TOLERANCE_OHM, "zones": zones, "not_drawn": not_drawn}


def grid_points(grid: dict[str, Any]) -> list[tuple[float, float, str]]:
    """The golden grid's points with their expected flag ("1", "0" or "." = not compared)."""
    (r0, r1), (x0, x1), n = grid["r"], grid["x"], grid["n"]
    out, k = [], 0
    for i in range(n):
        r = r0 + i * (r1 - r0) / (n - 1)
        for j in range(n):
            out.append((r, x0 + j * (x1 - x0) / (n - 1), grid["inside"][k]))
            k += 1
    return out
