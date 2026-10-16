"""Distance geometry kernel (V2) -- SHADOW MODE (DEC-199 Phase 1).

A small, relay-neutral geometry kernel for distance characteristics. In Phase 1 it is **not used by any production
path**: the V1 engine (`app.domain.distance_protection`) stays authoritative for membership, readiness, Apply and the
plotted zones. The kernel exists so the generic conformance harness can prove it reproduces every shape V1 draws today
(`app.domain.distance_geometry_compat` compiles V1 zone settings into it) before any later phase relies on it.

## Coordinate convention (the one canonical plane)

* The plane is the impedance plane: horizontal axis **R** (resistance), vertical axis **X** (reactance), both in ohms,
  in whatever impedance basis (primary / secondary) the caller works in -- the kernel never converts a basis.
* Angles are in **degrees**, measured **counter-clockwise from the +R axis** (so +X is 90 deg, -R is 180 deg). Radians
  appear only inside the arithmetic.
* **Absolute frame**: the R-X plane of the measured loop impedance, as the relay sees it looking forward into the
  protected line. Membership and outlines are evaluated only in this frame.
* **Zone-local frame**: the frame a zone's characteristic is *stated* in before its direction is applied. A forward
  zone's local frame is the absolute frame; a reverse zone's local frame is the absolute frame rotated 180 deg (a point
  reflection through the origin), exactly as V1 defines a reverse zone.
* Every `Characteristic` carries its `frame` explicitly; there is no implicit default. Only an absolute characteristic
  can be evaluated or outlined (`to_absolute()` converts a zone-local one for a given direction).

## Tolerance policy (one policy, no per-relay epsilons)

* `TOLERANCE_OHM` (1e-6 ohm, the same absolute boundary tolerance V1 uses) is the only tolerance:
  * membership is boundary-inclusive within it (half-plane: signed distance <= tolerance; disk: distance from the centre
    <= radius + tolerance);
  * outline vertices are merged / compared within it;
  * V1 <-> V2 equivalence is judged on test points kept at least `guard_distance(scale)` away from every boundary
    (1e-3 of the zone's extent, never less than 1000 x the tolerance), so floating-point noise at a boundary can never
    decide a comparison.
* It is a numerical boundary-inclusion convention only, never an engineering margin.

## Primitives

`HalfPlane` (n . p <= offset, unit outward normal n), `Disk` (|p - c| <= radius), `Intersection` (all parts) and the
point reflection (`reflected()`, 180 deg about the origin). Nothing else in Phase 1: no union, no exclusion region.
Each boundary may carry `BoundaryMeta` (source path, unit, transform, frame, reference, fidelity) for later phases;
Phase 1 leaves it empty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Union

#: The single geometric tolerance (ohms): boundary inclusion, vertex merging / comparison. Equals V1's
#: `ZONE_BOUNDARY_TOLERANCE_OHM` so both engines include a boundary identically.
TOLERANCE_OHM = 1e-6
#: Test points used to compare engines stay this fraction of the zone extent away from every boundary.
GUARD_FRACTION = 1e-3
#: Default number of segments when a circular arc must be approximated in a polygon outline.
ARC_SEGMENTS = 72
#: Half-size of the working box used to outline a region; a vertex on this box means the region is unbounded there.
_WORKING_BOX_OHM = 1e6


def guard_distance(scale_ohm: float) -> float:
    """How far a comparison test point must stay from every boundary, for a zone of the given extent."""
    return max(GUARD_FRACTION * abs(scale_ohm), 1000.0 * TOLERANCE_OHM)


class Frame(StrEnum):
    ABSOLUTE = "absolute"
    ZONE_LOCAL = "zone_local"


class Direction(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True, slots=True)
class BoundaryMeta:
    """Where a boundary comes from (Phase 2 onwards). Optional; Phase 1 boundaries carry none."""

    source_path: str | None = None
    unit: str = "ohm"
    transform: str | None = None
    frame: Frame | None = None
    reference: str | None = None
    #: exact | documented | approximate | static_equivalent
    fidelity: str = "exact"


@dataclass(frozen=True, slots=True)
class HalfPlane:
    """The closed half-plane {(R, X) : nr * R + nx * X <= offset}; (nr, nx) is the unit outward normal."""

    nr: float
    nx: float
    offset: float
    meta: BoundaryMeta | None = None

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.nr, self.nx, self.offset)):
            raise ValueError("a half-plane needs finite coefficients")
        if abs(math.hypot(self.nr, self.nx) - 1.0) > 1e-12:
            raise ValueError("a half-plane normal must be a unit vector")

    @classmethod
    def from_normal_angle(cls, angle_deg: float, offset: float, meta: BoundaryMeta | None = None) -> "HalfPlane":
        """The half-plane whose outward normal points at `angle_deg` (CCW from +R), `offset` ohms from the origin."""
        a = math.radians(angle_deg)
        return cls(math.cos(a), math.sin(a), offset, meta)

    def signed_distance(self, r: float, x: float) -> float:
        """<= 0 inside, > 0 outside; the distance to the boundary line in ohms."""
        return self.nr * r + self.nx * x - self.offset

    def contains(self, r: float, x: float) -> bool:
        return self.signed_distance(r, x) <= TOLERANCE_OHM

    def reflected(self) -> "HalfPlane":
        """Rotated 180 deg about the origin: n . (-p) <= c  <=>  (-n) . p <= c."""
        return HalfPlane(-self.nr, -self.nx, self.offset, self.meta)


@dataclass(frozen=True, slots=True)
class Disk:
    """The closed disk {(R, X) : |(R, X) - (cr, cx)| <= radius}."""

    cr: float
    cx: float
    radius: float
    meta: BoundaryMeta | None = None

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.cr, self.cx, self.radius)) or self.radius <= 0.0:
            raise ValueError("a disk needs a finite centre and a positive radius")

    def signed_distance(self, r: float, x: float) -> float:
        return math.hypot(r - self.cr, x - self.cx) - self.radius

    def contains(self, r: float, x: float) -> bool:
        return math.hypot(r - self.cr, x - self.cx) <= self.radius + TOLERANCE_OHM

    def reflected(self) -> "Disk":
        return Disk(-self.cr, -self.cx, self.radius, self.meta)


@dataclass(frozen=True, slots=True)
class Intersection:
    """Every part holds (an empty intersection is the whole plane and is refused)."""

    parts: tuple["Region", ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("an intersection needs at least one part")

    def contains(self, r: float, x: float) -> bool:
        return all(p.contains(r, x) for p in self.parts)

    def reflected(self) -> "Intersection":
        return Intersection(tuple(p.reflected() for p in self.parts))

    def boundaries(self) -> tuple[Union[HalfPlane, Disk], ...]:
        out: list[Union[HalfPlane, Disk]] = []
        for p in self.parts:
            out += list(p.boundaries()) if isinstance(p, Intersection) else [p]
        return tuple(out)


Region = Union[HalfPlane, Disk, Intersection]


def _boundaries(region: Region) -> tuple[Union[HalfPlane, Disk], ...]:
    return region.boundaries() if isinstance(region, Intersection) else (region,)


@dataclass(frozen=True, slots=True)
class Outline:
    """A bounded outline for plotting: an exact circle, or a convex polygon (counter-clockwise vertices). `clipped`
    is True when the region is unbounded and the polygon was cut by the requested bounds. `approximated` is True when a
    circular arc was replaced by `ARC_SEGMENTS` chords."""

    kind: str                                         # "circle" | "polygon"
    vertices: tuple[tuple[float, float], ...] = ()
    center: tuple[float, float] | None = None
    radius: float | None = None
    clipped: bool = False
    approximated: bool = False


@dataclass(frozen=True, slots=True)
class Characteristic:
    """A zone characteristic: a region in an explicitly named frame."""

    region: Region
    frame: Frame

    def to_absolute(self, direction: Direction | str) -> "Characteristic":
        """A zone-local characteristic placed in the absolute frame for the zone's direction."""
        if self.frame is Frame.ABSOLUTE:
            return self
        d = Direction(direction)
        region = self.region.reflected() if d is Direction.REVERSE else self.region
        return Characteristic(region, Frame.ABSOLUTE)

    def reflected(self) -> "Characteristic":
        """The same characteristic rotated 180 deg about the origin (same frame)."""
        return Characteristic(self.region.reflected(), self.frame)

    def _absolute_only(self) -> None:
        if self.frame is not Frame.ABSOLUTE:
            raise ValueError("a zone-local characteristic must be placed in the absolute frame first (to_absolute)")

    def contains(self, r: float, x: float) -> bool:
        self._absolute_only()
        return self.region.contains(r, x)

    def boundary_distance(self, r: float, x: float) -> float:
        """The smallest distance from the point to any boundary of the characteristic (ohms)."""
        return min(abs(b.signed_distance(r, x)) for b in _boundaries(self.region))

    def outline(self, bounds: tuple[float, float, float, float] | None = None, arc_segments: int = ARC_SEGMENTS) -> Outline:
        """A bounded outline. A single disk is returned exactly; anything else as a convex polygon built by clipping.
        `bounds` = (r_min, r_max, x_min, x_max) is required only for an unbounded region."""
        self._absolute_only()
        parts = _boundaries(self.region)
        disks = [p for p in parts if isinstance(p, Disk)]
        planes = [p for p in parts if isinstance(p, HalfPlane)]
        if len(disks) == 1 and not planes:
            d = disks[0]
            return Outline("circle", center=(d.cr, d.cx), radius=d.radius)
        if disks:
            polygon = _disk_polygon(disks[0], arc_segments)
            clip = planes + [hp for d in disks[1:] for hp in _disk_chords(d, arc_segments)]
        else:
            b = _WORKING_BOX_OHM
            polygon = [(-b, -b), (b, -b), (b, b), (-b, b)]
            clip = planes
        for hp in clip:
            polygon = _clip(polygon, hp)
            if not polygon:
                return Outline("polygon", (), approximated=bool(disks))
        polygon = _dedupe(polygon)
        unbounded = any(max(abs(r), abs(x)) >= _WORKING_BOX_OHM * (1 - 1e-12) for r, x in polygon)
        clipped = False
        if unbounded:
            if bounds is None:
                raise ValueError("an unbounded characteristic needs plotting bounds")
            r0, r1, x0, x1 = bounds
            for hp in (HalfPlane(-1.0, 0.0, -r0), HalfPlane(1.0, 0.0, r1), HalfPlane(0.0, -1.0, -x0), HalfPlane(0.0, 1.0, x1)):
                polygon = _clip(polygon, hp)
            polygon, clipped = _dedupe(polygon), True
        return Outline("polygon", tuple(polygon), clipped=clipped, approximated=bool(disks))


def _disk_polygon(d: Disk, n: int) -> list[tuple[float, float]]:
    return [(d.cr + d.radius * math.cos(2 * math.pi * k / n), d.cx + d.radius * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _disk_chords(d: Disk, n: int) -> list[HalfPlane]:
    """The inscribed polygon's edges as half-planes (an approximation of the disk, flagged by the outline)."""
    out = []
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        out.append(HalfPlane(math.cos(a), math.sin(a), d.cr * math.cos(a) + d.cx * math.sin(a) + d.radius * math.cos(math.pi / n)))
    return out


def _clip(polygon: list[tuple[float, float]], hp: HalfPlane) -> list[tuple[float, float]]:
    """Sutherland-Hodgman: the part of a convex polygon inside one half-plane."""
    out: list[tuple[float, float]] = []
    n = len(polygon)
    for i in range(n):
        p, q = polygon[i], polygon[(i + 1) % n]
        dp, dq = hp.signed_distance(*p), hp.signed_distance(*q)
        if dp <= TOLERANCE_OHM:
            out.append(p)
        if (dp < -TOLERANCE_OHM and dq > TOLERANCE_OHM) or (dp > TOLERANCE_OHM and dq < -TOLERANCE_OHM):
            t = dp / (dp - dq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _dedupe(polygon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for v in polygon:
        if not out or math.hypot(v[0] - out[-1][0], v[1] - out[-1][1]) > TOLERANCE_OHM:
            out.append(v)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= TOLERANCE_OHM:
        out.pop()
    return out
