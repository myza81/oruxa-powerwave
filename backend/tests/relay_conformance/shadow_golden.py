"""Independent engineering goldens for shadow (V2) canonical boundaries (DEC-199 Phase 2A / 2B / 2C).

V1 cannot draw an inclined resistive edge, a directional line or a lower reactance limit, so V1 is not the truth source
here. Each golden is computed from the documented relations only, using plain arithmetic -- never the V2 kernel, its
half-plane normals or the boundary compiler:

* resistive edges: ``R(X) = r_at_axis + X / tan(angle)`` with the zone's X reach (``X <= X reach``);
* directional lines (Phase 2B): a ray at its canonical angle; membership is the documented angular condition on
  ``arg(Z) = atan2(X, R)`` -- the counter-clockwise sweep from the counter-clockwise-retained ray to the point is no more
  than the sweep to the clockwise-retained ray (one ray alone: the point is within 180 deg on its retained side);
* lower reactance limit (Phase 2C): ``X >= -x_minus``.

Per assembled zone::

    x_reach_ohm, cot      the numbers the golden is built from
    edge_points           [[X, R_right(X), R_left(X)], ...] at X = 0, 0.25, 0.5 and 1.0 x the X reach
    probes                [[R, X, 0|1], ...] -- just inside / just outside each resistive edge at X = 0.25, 0.5 and
                          0.999 x the X reach, and just below / above the top at mid-width; 1 = inside the
                          represented region. No resistive probe is placed below X = 0.
    directional           (Phase 2B, a zone with directional lines only) {retained side: canonical angle}
    directional_points    [[retained side, R, X], ...] on each ray at 0.25, 0.5 and 1.0 x the X reach
    directional_probes    [[R, X, 0|1], ...] -- each ray +/- 2 deg at 0.1 and 0.25 x the X reach, and representative
                          first-quadrant, +X, negative-R, -X and third-quadrant (reverse) points
    lower                 (Phase 2C, a zone with a lower limit only) x_minus
    lower_points          [[R, X], ...] on X = -x_minus at 0.25, 0.5 and 0.75 across the resistive band there
    lower_probes          [[R, X, 0|1], ...] just above (1) / below (0) each lower point: the lower limit's own side
    closed                true when top, lower, right and left are all present (a bounded region)
    active                the boundaries with a stretch on the region's outline, found by sampling each documented
                          line for points that satisfy every other relation with a clearance of 3 probe offsets
    boundary_probes       [[label, R, X, 0|1], ...] -- for each active boundary one point a probe offset inside
                          ("inside_<b>") and one outside ("beyond_<b>"), stepped off that sampled point (vertically for
                          top / lower, horizontally for an edge, by angle for a ray); 0|1 from the documented relations

A resistive probe closer than a quarter of the probe offset to a directional line, and a directional probe that close
to any documented line, is dropped (its side would be decided by rounding). A reverse zone's points are reflected
through the origin once (its boundaries are stated in the zone frame). Values are rounded to 9 decimals; a probe offset
is 1 % of the X reach.
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
LOWER_FRACTIONS = (0.25, 0.5, 0.75)
#: Samples per documented line when looking for a stretch of the region's outline.
LINE_SAMPLES = 401


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
    xm = (zone.get("lower") or {}).get("x_minus")

    def edge(x: float) -> tuple[float, float]:
        return right["r_at_axis"] + x * cot, left["r_at_axis"] + x * cot

    def in_sector(r: float, x: float, sides: dict[str, float]) -> bool:
        phi = math.degrees(math.atan2(x, r))
        ccw, cw = sides.get("counter_clockwise"), sides.get("clockwise")
        if ccw is not None and cw is not None:
            return (phi - ccw) % 360.0 <= (cw - ccw) % 360.0
        if ccw is not None:
            return (phi - ccw) % 360.0 <= 180.0
        if cw is not None:
            return (cw - phi) % 360.0 <= 180.0
        return True

    def inside(r: float, x: float) -> int:
        rr, rl = edge(x)
        return int(rl <= r <= rr and x <= xr and (xm is None or x >= -xm) and in_sector(r, x, rays))

    def gaps(r: float, x: float) -> dict[str, float]:
        """The signed distance to each documented line, positive on the retained side (sample selection only)."""
        rr, rl = edge(x)
        out = {"top": xr - x, "right": (rr - r) * math.sin(a), "left": (r - rl) * math.sin(a)}
        if xm is not None:
            out["lower"] = x + xm
        for side, t in rays.items():
            cross = -math.sin(math.radians(t)) * r + math.cos(math.radians(t)) * x
            out[side] = cross if side == "counter_clockwise" else -cross
        return out

    def clear(r: float, x: float, resistive: bool = True) -> bool:
        d = gaps(r, x)
        lines = list(d) if resistive else list(rays)
        return not lines or min(abs(d[k]) for k in lines) >= 0.25 * PROBE_FRACTION * xr

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

    def polar(t: float, rho: float) -> tuple[float, float]:
        return rho * math.cos(math.radians(t)), rho * math.sin(math.radians(t))

    if rays:
        points = [[side, *polar(t, f * xr)] for side, t in sorted(rays.items()) for f in RAY_FRACTIONS]
        candidates = [polar(t + s * RAY_PROBE_DEG, f * xr) for t in sorted(rays.values()) for f in RAY_PROBE_RADII for s in (-1, 1)]
        candidates += [polar(t, 0.2 * xr) for t in REPRESENTATIVE_DEG]
        out["directional"] = {side: rays[side] for side in sorted(rays)}
        out["directional_points"] = [[side, _r(sign * r), _r(sign * x)] for side, r, x in points]
        out["directional_probes"] = [[_r(sign * r), _r(sign * x), inside(r, x)] for r, x in candidates if clear(r, x)]
    if xm is None:
        return out

    rr, rl = edge(-xm)
    on_lower = [(rl + f * (rr - rl), -xm) for f in LOWER_FRACTIONS]
    out["lower"] = xm
    out["lower_points"] = [[_r(sign * r), _r(sign * x)] for r, x in on_lower]
    out["lower_probes"] = [[_r(sign * r), _r(sign * (x + s * delta)), int(s > 0)] for r, x in on_lower for s in (1, -1)]
    out["closed"] = True                                       # top, lower, right and left are all present

    # the outline: each documented line sampled for a stretch where every other relation holds with clearance
    reach = 2.0 * (xr + xm + abs(right["r_at_axis"]) + abs(left["r_at_axis"]))
    n = LINE_SAMPLES - 1
    lines = {
        "top": [(edge(xr)[1] + k / n * (edge(xr)[0] - edge(xr)[1]), xr) for k in range(LINE_SAMPLES)],
        "lower": [(rl + k / n * (rr - rl), -xm) for k in range(LINE_SAMPLES)],
        "right": [(edge(x)[0], x) for x in (-xm + k / n * (xr + xm) for k in range(LINE_SAMPLES))],
        "left": [(edge(x)[1], x) for x in (-xm + k / n * (xr + xm) for k in range(LINE_SAMPLES))],
        **{side: [polar(t, k / n * reach) for k in range(1, LINE_SAMPLES)] for side, t in rays.items()},
    }
    active, boundary_probes = [], []
    for name, samples in lines.items():
        ok = [p for p in samples if all(g >= 3 * delta for k, g in gaps(*p).items() if k != name)]
        if not ok:
            continue                                           # the line never bounds the region
        r, x = ok[len(ok) // 2]
        if name in ("top", "lower"):
            step = (0.0, -delta) if name == "top" else (0.0, delta)
            pin, pout = (r + step[0], x + step[1]), (r - step[0], x - step[1])
        elif name in ("right", "left"):
            step = -delta if name == "right" else delta
            pin, pout = (r + step, x), (r - step, x)
        else:
            rho, t = math.hypot(r, x), math.degrees(math.atan2(x, r))
            turn = math.degrees(delta / rho) * (1 if name == "counter_clockwise" else -1)
            pin, pout = polar(t + turn, rho), polar(t - turn, rho)
        active.append(name)
        boundary_probes += [[f"inside_{name}", _r(sign * pin[0]), _r(sign * pin[1]), inside(*pin)],
                            [f"beyond_{name}", _r(sign * pout[0]), _r(sign * pout[1]), inside(*pout)]]
    out["active"] = active
    out["boundary_probes"] = boundary_probes
    return out


def shadow_golden(shadow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not shadow:
        return None
    return {zone_id: zone_golden(z) for zone_id, z in shadow["zones"].items() if z.get("shadow_geometry") == "exact"}
