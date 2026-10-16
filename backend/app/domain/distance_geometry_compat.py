"""V1 -> V2 compatibility compiler -- temporary migration infrastructure (DEC-199 Phase 1, shadow mode).

Compiles the existing V1 engine input (one characteristic for the analysis plus a `ZoneSettings`) into the V2 geometry
kernel (`app.domain.distance_geometry`), so the conformance harness can prove V2 reproduces every shape V1 draws. It
reads only the engine input -- never a catalog, a profile or a relay name -- and it is used by tests only; V1 stays
production-authoritative.

The compilation follows V1 exactly (`app.domain.distance_protection`):

* the same preconditions as `evaluate_zone_state` -- a disabled zone, a missing delay, a missing angle on a polar zone,
  explicit R/X limits on a non-quadrilateral, missing or invalid geometry values, or an unknown direction compile to
  `None` (V1 never operates for them);
* mho: the disk on the diameter from the origin to `reach_ohm` at `characteristic_angle_deg`;
* quadrilateral (polar): V1's rotated rectangle `0 <= x' <= X`, `-R_left <= r' <= R_right` with
  `x' = R cos(theta) + X sin(theta)` and `r' = R sin(theta) - X cos(theta)` -- four half-planes;
* quadrilateral (explicit R/X): the same rectangle in the orthogonal frame (theta = 90 deg, computed as V1 computes it);
* reverse: the zone-local characteristic point-reflected into the absolute frame (V1 reflects the measured point
  instead; the two are the same set).
"""

from __future__ import annotations

import math

from app.domain.distance_geometry import Characteristic, Direction, Disk, Frame, HalfPlane, Intersection
from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    GEOMETRY_EXPLICIT_RX,
    KNOWN_DIRECTIONS,
    ZoneSettings,
)

#: V1's orthogonal frame for explicit R/X limits (`distance_protection._ORTHOGONAL_FRAME_DEG`).
_ORTHOGONAL_FRAME_DEG = 90.0


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def compile_v1_zone(characteristic: str, zone: ZoneSettings) -> Characteristic | None:
    """The zone's V1 geometry as a V2 characteristic in the absolute frame, or `None` when V1 draws / operates nothing."""
    if not zone.enabled or zone.delay_s is None or zone.direction not in KNOWN_DIRECTIONS:
        return None
    explicit = zone.geometry_mode == GEOMETRY_EXPLICIT_RX
    if explicit and characteristic != CHARACTERISTIC_QUADRILATERAL:
        return None
    if not explicit and (zone.characteristic_angle_deg is None or not _finite(zone.characteristic_angle_deg)):
        return None                                   # V1: no angle, or one that makes its maths NaN -- never operates
    if characteristic == CHARACTERISTIC_MHO:
        if zone.reach_ohm is None or not (_finite(zone.reach_ohm) and zone.reach_ohm > 0.0):
            return None
        theta = math.radians(zone.characteristic_angle_deg)
        half = zone.reach_ohm / 2.0
        local = Characteristic(Disk(half * math.cos(theta), half * math.sin(theta), half), Frame.ZONE_LOCAL)
        return local.to_absolute(Direction(zone.direction))
    if characteristic != CHARACTERISTIC_QUADRILATERAL:
        return None
    xr, rr, rl = zone.reactive_reach_ohm, zone.resistive_reach_forward_ohm, zone.resistive_reach_reverse_ohm
    if xr is None or rr is None or rl is None:
        return None
    if not (_finite(xr, rr, rl) and xr > 0.0 and rr > 0.0 and rl >= 0.0):
        return None
    theta = math.radians(_ORTHOGONAL_FRAME_DEG if explicit else zone.characteristic_angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    region = Intersection((
        HalfPlane(-c, -s, 0.0),          # x' >= 0         (the directional line)
        HalfPlane(c, s, xr),             # x' <= X         (the reactance line)
        HalfPlane(s, -c, rr),            # r' <= R_right   (the right resistive limit)
        HalfPlane(-s, c, rl),            # r' >= -R_left   (the left resistive limit)
    ))
    return Characteristic(region, Frame.ZONE_LOCAL).to_absolute(Direction(zone.direction))
