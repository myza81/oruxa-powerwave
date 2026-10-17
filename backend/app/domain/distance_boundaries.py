"""Canonical distance-zone boundaries (DEC-199 Phase 2A / 2B / 2C / 2D) -- SHADOW MODE.

A relay-neutral description of a zone boundary, compiled into the V2 geometry kernel (`app.domain.distance_geometry`).
Four boundary kinds -- an **inclined resistive edge** (Phase 2A), a **directional half-plane** through the origin
(Phase 2B), a **lower reactance limit** ``X >= -x_minus`` (Phase 2C) and a **tilted upper reactance limit** through a
point on the X axis (Phase 2D) -- and the shadow assembly of a zone from them. It is not used by any production path:
V1 (`app.domain.distance_protection`) stays authoritative for membership, readiness, Apply and the plot, and nothing
here changes a review, a blocker or a readiness state.

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

## The directional half-plane (DEC-199 Phase 2B)

``directional(angle_deg, retained_side, frame)``: the straight line through the origin along the ray at ``angle_deg``
(degrees, counter-clockwise from +R; -180 < angle <= 180, so a fourth-quadrant ray has a negative angle). With the ray's
unit direction u = (cos a, sin a), the cross product u x p = -sin a * R + cos a * X is >= 0 on the side reached by turning
the ray counter-clockwise and <= 0 on the side reached by turning it clockwise:

* ``counter_clockwise``: { (R, X) : -sin a * R + cos a * X >= 0 }  -- as a half-plane ( sin a, -cos a) . (R, X) <= 0;
* ``clockwise``:         { (R, X) :  sin a * R - cos a * X >= 0 }  -- as a half-plane (-sin a,  cos a) . (R, X) <= 0.

E.g. at 0 deg the counter-clockwise side is X >= 0; at 90 deg it is R <= 0. The retained side is stated
mathematically, never as "forward" / "reverse": a relay's forward region is a statement about which side its
documentation keeps, made by the mapping, not by this module.

**Two rays bound a sector.** The region between a counter-clockwise-retained ray at ``a1`` and a clockwise-retained ray
at ``a2`` is the sector swept counter-clockwise from ``a1`` to ``a2`` (``a1 < arg(Z) < a2``) only when that sweep is
narrower than 180 deg: a wider sector is the *union* of the two half-planes, not their intersection, and the kernel
has no union. `assemble_zone` therefore refuses a sweep of 180 deg or more rather than produce a different region.

## The lower reactance limit (DEC-199 Phase 2C)

``reactance_lower(x_minus, frame)``: ``X >= -x_minus`` (ohms, ``x_minus >= 0``), the horizontal line ``x_minus`` below
the R axis -- as a half-plane ``(0, -1) . (R, X) <= x_minus``. A ``zone`` limit is point-reflected for a reverse zone
(``X <= x_minus`` in the absolute frame); an ``absolute`` one is not.

## The tilted upper reactance limit (DEC-199 Phase 2D)

``reactance_upper(x_at_reference, tilt_deg, frame)``: the straight line through the point ``(0, x_at_reference)`` on
the X axis, retaining ``X <= x_at_reference - R * tan(tilt_deg)``. ``tilt_deg`` is the line's rotation from horizontal
(degrees, ``-90 < tilt_deg < 90``); a positive value lowers the retained region as R increases. Multiplying by
cos(tilt_deg) > 0:

    (sin(tilt_deg), cos(tilt_deg)) . (R, X) <= x_at_reference * cos(tilt_deg)

At ``tilt_deg = 0`` this is exactly the plain horizontal top ``HalfPlane(0, 1, x_at_reference)`` -- the same formula
`assemble_zone` already uses for ``x_reach_ohm``, not a separate case.

This boundary is **added alongside** the zone's existing horizontal top, never in its place: the two half-planes
together, intersected, implement "inclined ... in the 1st quadrant" (the documented scope of every verified case)
without any quadrant-conditional logic in the kernel -- for R >= 0 the tilted line is the tighter of the two and
binds; for R < 0 the plain horizontal one is tighter and binds, exactly reproducing the horizontal top there. This
requires the two boundaries to share the same X-axis crossing (``x_at_reference`` = the zone's own ``x_reach_ohm``);
`assemble_zone` does not cross-check the two values (they are read from the same raw setting by construction).

``fidelity`` says how the boundary relates to **relay behaviour** (exact | documented | static_equivalent). It is
distinct from the geometry, which represents the documented relation exactly in every case: a ``static_equivalent``
boundary is the exact half-plane of a documented static characteristic whose relay decision is dynamic (e.g. a
polarising voltage with memory) -- the static R-X line is its steady-state equivalent, not the relay's every decision.
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
    #: How the source states the value when it differs from the canonical convention (e.g. a magnitude below +R).
    convention: str | None = None


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
class ReactanceLowerBoundary:
    """A lower reactance limit ``X >= -x_minus`` (ohms): the horizontal line ``x_minus`` below the R axis (``x_minus = 0``
    is ``X >= 0``). As a kernel half-plane ``(0, -1) . (R, X) <= x_minus``. ``frame`` is explicit: a ``zone`` limit is
    point-reflected for a reverse zone (it becomes ``X <= x_minus``); an ``absolute`` one is used as stated."""

    zone_id: str
    x_minus: float
    frame: BoundaryFrame
    provenance: BoundaryProvenance
    unit: str = "ohm"
    #: exact | documented (an approximation is never a canonical boundary)
    fidelity: str = "documented"

    def __post_init__(self) -> None:
        if not math.isfinite(self.x_minus) or self.x_minus < 0.0:
            raise ValueError("a lower reactance limit lies at or below the R axis: x_minus must be finite and >= 0")
        if not isinstance(self.frame, BoundaryFrame):
            raise ValueError("a lower reactance limit states its frame")
        if self.unit != "ohm":
            raise ValueError("a lower reactance limit is stated in ohms")
        if self.fidelity not in ("exact", "documented"):
            raise ValueError("a canonical boundary is exact or documented, never approximate")

    def half_plane(self, direction: Direction | str = Direction.FORWARD) -> HalfPlane:
        """The limit as a kernel half-plane in the absolute frame (reflected once for a reverse zone-frame limit)."""
        meta = BoundaryMeta(source_path=self.provenance.canonical_path, unit=self.unit, transform=self.provenance.transform,
                            frame=Frame.ZONE_LOCAL if self.frame is BoundaryFrame.ZONE else Frame.ABSOLUTE,
                            reference=",".join(self.provenance.reference_ids) or None, fidelity=self.fidelity)
        hp = HalfPlane(0.0, -1.0, self.x_minus, meta)
        if self.frame is BoundaryFrame.ZONE and Direction(direction) is Direction.REVERSE:
            hp = hp.reflected()
        return hp


@dataclass(frozen=True, slots=True)
class TiltedReactanceBoundary:
    """A tilted upper reactance limit through ``(0, x_at_reference)`` (see the module docstring for the equation and
    why it is added alongside the horizontal top, never in its place)."""

    zone_id: str
    x_at_reference: float
    tilt_deg: float
    frame: BoundaryFrame
    provenance: BoundaryProvenance
    unit: str = "ohm"
    #: exact | documented (an approximation is never a canonical boundary)
    fidelity: str = "documented"

    def __post_init__(self) -> None:
        if not (math.isfinite(self.x_at_reference) and math.isfinite(self.tilt_deg)):
            raise ValueError("a tilted reactance limit needs a finite axis crossing and tilt")
        if not -90.0 < self.tilt_deg < 90.0:
            raise ValueError("a tilted reactance limit's tilt must lie strictly between -90 and 90 degrees")
        if not isinstance(self.frame, BoundaryFrame):
            raise ValueError("a tilted reactance limit states its frame")
        if self.unit != "ohm":
            raise ValueError("a tilted reactance limit is stated in ohms")
        if self.fidelity not in ("exact", "documented"):
            raise ValueError("a canonical boundary is exact or documented, never approximate")

    def x_at(self, r: float) -> float:
        """X on the line at resistance R: x_at_reference - R * tan(tilt_deg)."""
        return self.x_at_reference - r * math.tan(math.radians(self.tilt_deg))

    def half_plane(self, direction: Direction | str = Direction.FORWARD) -> HalfPlane:
        """The limit as a kernel half-plane in the absolute frame (reflected once for a reverse zone-frame limit). At
        tilt_deg = 0 this is exactly HalfPlane(0, 1, x_at_reference), the existing horizontal top."""
        a = math.radians(self.tilt_deg)
        s, c = math.sin(a), math.cos(a)
        meta = BoundaryMeta(source_path=self.provenance.canonical_path, unit=self.unit, transform=self.provenance.transform,
                            frame=Frame.ZONE_LOCAL if self.frame is BoundaryFrame.ZONE else Frame.ABSOLUTE,
                            reference=",".join(self.provenance.reference_ids) or None, fidelity=self.fidelity)
        hp = HalfPlane(s, c, self.x_at_reference * c, meta)
        if self.frame is BoundaryFrame.ZONE and Direction(direction) is Direction.REVERSE:
            hp = hp.reflected()
        return hp


class RetainedSide(StrEnum):
    COUNTER_CLOCKWISE = "counter_clockwise"
    CLOCKWISE = "clockwise"


#: How a boundary relates to relay behaviour (the geometry itself is always the exact documented relation).
DIRECTIONAL_FIDELITY = ("exact", "documented", "static_equivalent")


@dataclass(frozen=True, slots=True)
class DirectionalBoundary:
    """A directional half-plane through the origin (see the module docstring for the side convention)."""

    zone_id: str
    angle_deg: float
    retained_side: RetainedSide
    frame: BoundaryFrame
    provenance: BoundaryProvenance
    fidelity: str = "documented"

    def __post_init__(self) -> None:
        if not math.isfinite(self.angle_deg) or not -180.0 < self.angle_deg <= 180.0:
            raise ValueError("a directional boundary's angle must be finite, in (-180, 180] degrees")
        if not isinstance(self.retained_side, RetainedSide):
            raise ValueError("a directional boundary states its retained side")
        if not isinstance(self.frame, BoundaryFrame):
            raise ValueError("a directional boundary states its frame")
        if self.fidelity not in DIRECTIONAL_FIDELITY:
            raise ValueError("a canonical boundary is exact, documented or static_equivalent, never approximate")

    def point_at(self, radius_ohm: float) -> tuple[float, float]:
        """The point of the ray at the given distance from the origin (R, X), in the frame the boundary is stated in."""
        a = math.radians(self.angle_deg)
        return radius_ohm * math.cos(a), radius_ohm * math.sin(a)

    def half_plane(self, direction: Direction | str = Direction.FORWARD) -> HalfPlane:
        """The retained side as a kernel half-plane in the absolute frame (reflected once for a reverse zone-frame line)."""
        a = math.radians(self.angle_deg)
        s, c = math.sin(a), math.cos(a)
        meta = BoundaryMeta(source_path=self.provenance.canonical_path, unit="deg", transform=self.provenance.transform,
                            frame=Frame.ZONE_LOCAL if self.frame is BoundaryFrame.ZONE else Frame.ABSOLUTE,
                            reference=",".join(self.provenance.reference_ids) or None, fidelity=self.fidelity)
        hp = HalfPlane(s, -c, 0.0, meta) if self.retained_side is RetainedSide.COUNTER_CLOCKWISE else HalfPlane(-s, c, 0.0, meta)
        if self.frame is BoundaryFrame.ZONE and Direction(direction) is Direction.REVERSE:
            hp = hp.reflected()
        return hp


def sector_sweep_deg(ccw: DirectionalBoundary, cw: DirectionalBoundary) -> float:
    """The angle swept counter-clockwise from the counter-clockwise-retained ray to the clockwise-retained one, [0, 360)."""
    return (cw.angle_deg - ccw.angle_deg) % 360.0


@dataclass(frozen=True, slots=True)
class ShadowZoneGeometry:
    """A zone assembled from canonical boundaries, in the absolute frame. ``represented`` names the boundaries it holds;
    ``not_represented`` those a later phase adds (no lower limit yet; no directional limit unless one is given)."""

    zone_id: str
    characteristic: Characteristic
    represented: tuple[str, ...]
    not_represented: tuple[str, ...]


def assemble_zone(zone_id: str, *, x_reach_ohm: float, direction: Direction | str,
                  boundaries: tuple[ResistiveBoundary, ...],
                  directional: tuple[DirectionalBoundary, ...] = (),
                  lower: ReactanceLowerBoundary | None = None,
                  upper: TiltedReactanceBoundary | None = None) -> ShadowZoneGeometry:
    """A zone from its horizontal reactance limit (X <= x_reach_ohm, stated in the zone frame), one right and one left
    resistive boundary and, optionally, its directional half-planes (at most one per retained side), its lower
    reactance limit and its tilted upper reactance limit. Without a lower limit the region is open below and is
    reported so (``not_represented``); the tilted upper limit is added *alongside* the horizontal top (see the module
    docstring), never in its place, so it never makes the zone unbounded or changes ``not_represented``.

    Every boundary is placed in the absolute frame exactly once, by its own frame and the zone direction; the result is
    an absolute characteristic, which `Characteristic.to_absolute` leaves unchanged -- a reverse zone cannot be
    reflected twice."""
    sides = {b.side: b for b in boundaries if b.zone_id == zone_id}
    if set(sides) != {BoundarySide.RIGHT, BoundarySide.LEFT}:
        raise ValueError(f"zone {zone_id} needs one right and one left resistive boundary")
    if not (math.isfinite(x_reach_ohm) and x_reach_ohm > 0.0):
        raise ValueError("the reactance limit must be a positive finite reach")
    rays = [b for b in directional if b.zone_id == zone_id]
    by_side = {b.retained_side: b for b in rays}
    if len(by_side) != len(rays):
        raise ValueError(f"zone {zone_id} has more than one directional boundary on one retained side")
    if len(by_side) == 2:
        sweep = sector_sweep_deg(by_side[RetainedSide.COUNTER_CLOCKWISE], by_side[RetainedSide.CLOCKWISE])
        if not 0.0 < sweep < 180.0:
            raise ValueError(f"the directional sector of zone {zone_id} sweeps {sweep:g} deg: only a sector narrower than "
                             "180 deg is the intersection of its two half-planes (a wider one is their union, which the "
                             "kernel does not represent)")
    d = Direction(direction)
    top = HalfPlane(0.0, 1.0, x_reach_ohm)
    if d is Direction.REVERSE:
        top = top.reflected()
    if lower is not None and lower.zone_id != zone_id:
        raise ValueError(f"the lower reactance limit of zone {lower.zone_id} is not zone {zone_id}'s")
    if upper is not None and upper.zone_id != zone_id:
        raise ValueError(f"the tilted upper reactance limit of zone {upper.zone_id} is not zone {zone_id}'s")
    parts = (top, sides[BoundarySide.RIGHT].half_plane(d), sides[BoundarySide.LEFT].half_plane(d),
             *(b.half_plane(d) for b in rays), *((lower.half_plane(d),) if lower else ()),
             *((upper.half_plane(d),) if upper else ()))
    represented = (("top", "right", "left") + (("directional",) if rays else ()) + (("lower",) if lower else ())
                  + (("tilt",) if upper else ()))
    not_represented = () if lower else ("lower",)
    return ShadowZoneGeometry(zone_id, Characteristic(Intersection(parts), Frame.ABSOLUTE), represented, not_represented)
