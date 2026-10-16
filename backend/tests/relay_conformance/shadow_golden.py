"""Independent engineering goldens for shadow (V2) canonical boundaries (DEC-199 Phase 2A).

V1 cannot draw an inclined resistive edge, so V1 is not the truth source here. Each golden is computed from the
documented relation only -- ``R(X) = r_at_axis + X / tan(angle)`` with the zone's X reach -- using plain arithmetic, never
the V2 kernel or the boundary compiler. Per assembled zone::

    x_reach_ohm, cot      the numbers the golden is built from
    edge_points           [[X, R_right(X), R_left(X)], ...] at X = 0, 0.25, 0.5 and 1.0 x the X reach
    probes                [[R, X, 0|1], ...] -- just inside / just outside each resistive edge at X = 0.25, 0.5 and
                          0.999 x the X reach, and just below / above the top at mid-width; 1 = inside the
                          represented region (left edge <= R <= right edge, X <= X reach). Phase 2A represents no lower
                          limit, so no probe is placed below X = 0.

A reverse zone's points are reflected through the origin (its edges are stated in the zone frame). Values are rounded to
9 decimals; a probe is 1 % of the X reach away from its boundary.
"""

from __future__ import annotations

import math
from typing import Any

FRACTIONS = (0.0, 0.25, 0.5, 1.0)
PROBE_LEVELS = (0.25, 0.5, 0.999)
PROBE_FRACTION = 1e-2


def _r(v: float) -> float:
    return round(v, 9) + 0.0


def zone_golden(zone: dict[str, Any]) -> dict[str, Any]:
    right, left = zone["edges"]["right"], zone["edges"]["left"]
    xr = zone["top"]["x_reach_ohm"]
    if right["angle_deg"] != left["angle_deg"]:
        raise ValueError("Phase 2A goldens assume one angle for both edges (the documented parallelogram)")
    cot = 1.0 / math.tan(math.radians(right["angle_deg"]))
    sign = -1.0 if zone["direction"] == "reverse" else 1.0

    def edge(x: float) -> tuple[float, float]:
        return right["r_at_axis"] + x * cot, left["r_at_axis"] + x * cot

    delta = PROBE_FRACTION * xr
    probes = []
    for f in PROBE_LEVELS:
        x = f * xr
        rr, rl = edge(x)
        probes += [[rr - delta, x, 1], [rr + delta, x, 0], [rl + delta, x, 1], [rl - delta, x, 0]]
    rr, rl = edge(xr)
    mid = (rr + rl) / 2
    probes += [[mid, xr - delta, 1], [mid, xr + delta, 0]]
    return {
        "x_reach_ohm": xr, "cot": _r(cot), "direction": zone["direction"],
        "edge_points": [[_r(sign * f * xr), _r(sign * edge(f * xr)[0]), _r(sign * edge(f * xr)[1])] for f in FRACTIONS],
        "probes": [[_r(sign * r), _r(sign * x), inside] for r, x, inside in probes],
    }


def shadow_golden(shadow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not shadow:
        return None
    return {zone_id: zone_golden(z) for zone_id, z in shadow["zones"].items() if z.get("shadow_geometry") == "exact"}
