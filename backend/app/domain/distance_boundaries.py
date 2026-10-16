"""Canonical distance-zone boundaries (DEC-199 Phase 2A) -- SHADOW MODE.

A relay-neutral description of a zone boundary, compiled into the V2 geometry kernel (`app.domain.distance_geometry`).
Phase 2A provides one boundary kind -- an **inclined resistive edge** -- and the shadow assembly of a zone from it. It is
not used by any production path: V1 (`app.domain.distance_protection`) stays authoritative for membership, readiness,
Apply and the plot, and nothing here changes a review, a blocker or a readiness state.

## The inclined resistive edge

``resistive(r_at_axis, angle_deg, side)``: the straight line that crosses the R axis at ``r_at_axis`` (ohms) and makes
``angle_deg`` with the +R axis (degrees, counter-clockwise; 0 < angle < 180). On the canonical plane (R horizontal,
X vertical):

    R(X) = r_at_axis + X * cot(angle)

* ``right``: the region left of / on the line, ``R <= R(X)``  -- a zone's right (+R side) limit;
* ``left``:  the region right of / on the line, ``R >= R(X)`` -- a zone's left (-R side) limit.

As a half-plane (unit normal n, n . p <= c), multiplying ``R - X cot(angle) <= r_at_axis`` by sin(angle) > 0:

    right:  ( sin a, -cos a) . (R, X) <=  r_at_axis * sin a
    left:   (-sin a,  cos a) . (R, X) <= -r_at_axis * sin a

At 90 deg this is the vertical ``R <= r_at_axis`` / ``R >= r_at_axis``. ``frame`` is explicit: ``absolute`` boundaries are
used as stated; ``zone`` boundaries are stated in the zone's own frame and are point-reflected (180 deg) for a reverse
zone, exactly as the kernel places any zone-local characteristic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.domain.distance_geometry import (
    BoundaryMeta,
    Characteristic,
    Direction,
    Frame,
    HalfPlane,
    Intersection,
)


class BoundarySide(StrEnum):
    RIGHT = "right"
    LEFT = "left"


class BoundaryFrame(StrEnum):
    ABSOLUTE = "absolute"
    ZONE = "zone"


@dataclass(frozen=True, slots=True)
class BoundarySource:
    """One source setting a boundary value was read from."""

    role: str                        # what it supplies, e.g. "r_at_axis", "angle_deg"
    name: str | None
    code: str | None
    raw_value: str | None
    unit: str
    page: int | None = None
    line: int | None = None


@dataclass(frozen=True, slots=True)
class BoundaryProvenance:
    sources: tuple[BoundarySource, ...]
    #: The canonical value this boundary represents geometrically (e.g. ``zones[Z1].resistive_reach.phase_phase``).
    canonical_path: str | None
    #: How the source values became the boundary (e.g. "r_at_axis = -R(Z1) ph-ph (per phase, direct)").
    transform: str
    #: The defining relation, as documented (e.g. "Rleft(X) = -R + X * cot(phi)").
    equation: str
    reference_ids: tuple[str, ...] = ()
    #: Who supplied the mapping (e.g. a catalog key); never consulted by the geometry.
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class ResistiveBoundary:
    """An inclined resistive edge (see the module docstring for the equations and the side convention)."""

    zone_id: str
    r_at_axis: float
    angle_deg: float
    side: BoundarySide
    frame: BoundaryFrame
    provenance: BoundaryProvenance
    unit: str = "ohm"
    #: exact | documented (an approximation is never a canonical boundary)
    fidelity: str = "documented"

    def __post_init__(self) -> None:
        if not (math.isfinite(self.r_at_axis) and math.isfinite(self.angle_deg)):
            raise ValueError("a resistive boundary needs a finite axis crossing and angle")
        if not 0.0 < self.angle_deg < 180.0:
            raise ValueError("a resistive boundary's angle must lie strictly between 0 and 180 degrees")
        if self.unit != "ohm":
            raise ValueError("a resistive boundary is stated in ohms")
        if self.fidelity not in ("exact", "documented"):
            raise ValueError("a canonical boundary is exact or documented, never approximate")

    def r_at(self, x: float) -> float:
        """R on the edge at reactance X: r_at_axis + X * cot(angle)."""
        a = math.radians(self.angle_deg)
        return self.r_at_axis + x * math.cos(a) / math.sin(a)

    def half_plane(self, direction: Direction | str = Direction.FORWARD) -> HalfPlane:
        """The edge's region as a kernel half-plane in the absolute frame."""
        a = math.radians(self.angle_deg)
        s, c = math.sin(a), math.cos(a)
        meta = BoundaryMeta(source_path=self.provenance.canonical_path, unit=self.unit, transform=self.provenance.transform,
                            frame=Frame.ZONE_LOCAL if self.frame is BoundaryFrame.ZONE else Frame.ABSOLUTE,
                            reference=",".join(self.provenance.reference_ids) or None, fidelity=self.fidelity)
        if self.side is BoundarySide.RIGHT:
            hp = HalfPlane(s, -c, self.r_at_axis * s, meta)
        else:
            hp = HalfPlane(-s, c, -self.r_at_axis * s, meta)
        if self.frame is BoundaryFrame.ZONE and Direction(direction) is Direction.REVERSE:
            hp = hp.reflected()
        return hp


@dataclass(frozen=True, slots=True)
class ShadowZoneGeometry:
    """A zone assembled from canonical boundaries, in the absolute frame. ``represented`` names the boundaries it holds;
    ``not_represented`` those a later phase adds (Phase 2A: no lower / directional limit)."""

    zone_id: str
    characteristic: Characteristic
    represented: tuple[str, ...]
    not_represented: tuple[str, ...]


def assemble_zone(zone_id: str, *, x_reach_ohm: float, direction: Direction | str,
                  boundaries: tuple[ResistiveBoundary, ...]) -> ShadowZoneGeometry:
    """A zone from its horizontal reactance limit (X <= x_reach_ohm, stated in the zone frame) and one right and one left
    resistive boundary. Phase 2A represents no lower / directional limit: the region is open below and is reported so."""
    sides = {b.side: b for b in boundaries if b.zone_id == zone_id}
    if set(sides) != {BoundarySide.RIGHT, BoundarySide.LEFT}:
        raise ValueError(f"zone {zone_id} needs one right and one left resistive boundary")
    if not (math.isfinite(x_reach_ohm) and x_reach_ohm > 0.0):
        raise ValueError("the reactance limit must be a positive finite reach")
    d = Direction(direction)
    top = HalfPlane(0.0, 1.0, x_reach_ohm)
    if d is Direction.REVERSE:
        top = top.reflected()
    region = Intersection((top, sides[BoundarySide.RIGHT].half_plane(d), sides[BoundarySide.LEFT].half_plane(d)))
    return ShadowZoneGeometry(zone_id, Characteristic(region, Frame.ABSOLUTE), ("top", "right", "left"), ("lower",))
