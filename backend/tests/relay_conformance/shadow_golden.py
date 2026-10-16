"""Independent engineering goldens for shadow (V2) canonical boundaries (DEC-199 Phase 2A / 2B).

V1 cannot draw an inclined resistive edge or a directional line, so V1 is not the truth source here. Each golden is
computed from the documented relations only, using plain arithmetic -- never the V2 kernel, its half-plane normals or the
boundary compiler:

* resistive edges: ``R(X) = r_at_axis + X / tan(angle)`` with the zone's X reach (``X <= X reach``);
* directional lines (Phase 2B): a ray at its canonical angle; membership is the documented angular condition on
  ``arg(Z) = atan2(X, R)`` -- the counter-clockwise sweep from the counter-clockwise-retained ray to the point is no more
  than the sweep to the clockwise-retained ray (one ray alone: the point is within 180 deg on its retained side).

Per assembled zone::

    x_reach_ohm, cot      the numbers the golden is built from
    edge_points           [[X, R_right(X), R_left(X)], ...] at X = 0, 0.25, 0.5 and 1.0 x the X reach
    probes                [[R, X, 0|1], ...] -- just inside / just outside each resistive edge at X = 0.25, 0.5 and
                          0.999 x the X reach, and just below / above the top at mid-width; 1 = inside the
                          represented region. No lower limit is represented, so no resistive probe is placed below X = 0.
    directional           (Phase 2B, a zone with directional lines only) {retained side: canonical angle}
    directional_points    [[retained side, R, X], ...] on each ray at 0.25, 0.5 and 1.0 x the X reach
    directional_probes    [[R, X, 0|1], ...] -- each ray +/- 2 deg at 0.1 and 0.25 x the X reach, and representative
                          first-quadrant, +X, negative-R, -X and third-quadrant (reverse) points

A resistive probe closer than a quarter of the probe offset to a directional line, and a directional probe that close
to any documented line, is dropped (its side would be decided by rounding). A reverse zone's points are reflected through the origin once (its boundaries are stated in the zone frame).
Values are rounded to 9 decimals; a resistive probe is 1 % of the X reach away from its boundary.
"""

from __future__ import annotations

import math
from typing import Any

FRACTIONS = (0.0, 0.25, 0.5, 1.0)
PROBE_LEVELS = (0.25, 0.5, 0.999)
PROBE_FRACTION = 1e-2
RAY_FRACTIONS = (0.25, 0.5, 1.0)
RAY_PROBE_RADII = (0.1, 0.25)
RAY_PROBE_DEG = 2.0
#: Representative directions (deg from +R) at 0.2 x the X reach: first quadrant, +X, negative R, -X, third quadrant.
REPRESENTATIVE_DEG = (30.0, 60.0, 90.0, 100.0, 150.0, 180.0, -90.0, -135.0)


def _r(v: float) -> float:
    return round(v, 9) + 0.0


def zone_golden(zone: dict[str, Any]) -> dict[str, Any]:
    right, left = zone["edges"]["right"], zone["edges"]["left"]
    xr = zone["top"]["x_reach_ohm"]
    if right["angle_deg"] != left["angle_deg"]:
        raise ValueError("the goldens assume one angle for both edges (the documented parallelogram)")
    a = math.radians(right["angle_deg"])
    cot = 1.0 / math.tan(a)
    sign = -1.0 if zone["direction"] == "reverse" else 1.0
    rays = {side: ray["angle_deg"] for side, ray in (zone.get("directional") or {}).items()}

    def edge(x: float) -> tuple[float, float]:
        return right["r_at_axis"] + x * cot, left["r_at_axis"] + x * cot

    def in_sector(r: float, x: float) -> bool:
        phi = math.degrees(math.atan2(x, r))
        ccw, cw = rays.get("counter_clockwise"), rays.get("clockwise")
        if ccw is not None and cw is not None:
            return (phi - ccw) % 360.0 <= (cw - ccw) % 360.0
        if ccw is not None:
            return (phi - ccw) % 360.0 <= 180.0
        if cw is not None:
            return (cw - phi) % 360.0 <= 180.0
        return True

    def inside(r: float, x: float) -> int:
        rr, rl = edge(x)
        return int(rl <= r <= rr and x <= xr and in_sector(r, x))

    def clear(r: float, x: float, resistive: bool = True) -> bool:
        rr, rl = edge(x)
        gaps = [abs(r - rr) * math.sin(a), abs(r - rl) * math.sin(a), abs(x - xr)] if resistive else []
        gaps += [abs(-math.sin(math.radians(t)) * r + math.cos(math.radians(t)) * x) for t in rays.values()]
        return not gaps or min(gaps) >= 0.25 * PROBE_FRACTION * xr

    delta = PROBE_FRACTION * xr
    probes = []
    for f in PROBE_LEVELS:
        x = f * xr
        rr, rl = edge(x)
        probes += [(rr - delta, x), (rr + delta, x), (rl + delta, x), (rl - delta, x)]
    rr, rl = edge(xr)
    mid = (rr + rl) / 2
    probes += [(mid, xr - delta), (mid, xr + delta)]
    out: dict[str, Any] = {
        "x_reach_ohm": xr, "cot": _r(cot), "direction": zone["direction"],
        "edge_points": [[_r(sign * f * xr), _r(sign * edge(f * xr)[0]), _r(sign * edge(f * xr)[1])] for f in FRACTIONS],
        "probes": [[_r(sign * r), _r(sign * x), inside(r, x)] for r, x in probes if clear(r, x, resistive=False)],
    }
    if rays:
        def polar(t: float, rho: float) -> tuple[float, float]:
            return rho * math.cos(math.radians(t)), rho * math.sin(math.radians(t))

        points = [[side, *polar(t, f * xr)] for side, t in sorted(rays.items()) for f in RAY_FRACTIONS]
        candidates = [polar(t + s * RAY_PROBE_DEG, f * xr) for t in sorted(rays.values()) for f in RAY_PROBE_RADII for s in (-1, 1)]
        candidates += [polar(t, 0.2 * xr) for t in REPRESENTATIVE_DEG]
        out["directional"] = {side: rays[side] for side in sorted(rays)}
        out["directional_points"] = [[side, _r(sign * r), _r(sign * x)] for side, r, x in points]
        out["directional_probes"] = [[_r(sign * r), _r(sign * x), inside(r, x)] for r, x in candidates if clear(r, x)]
    return out


def shadow_golden(shadow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not shadow:
        return None
    return {zone_id: zone_golden(z) for zone_id, z in shadow["zones"].items() if z.get("shadow_geometry") == "exact"}
