"""The V2 distance geometry kernel (DEC-199 Phase 1, shadow mode): primitives, frames, tolerance, outlines, and
independent engineering checkpoints (geometry mathematics, not snapshots)."""

from __future__ import annotations

import math
import time

import pytest

from app.domain.distance_geometry import (
    TOLERANCE_OHM,
    BoundaryMeta,
    Characteristic,
    Direction,
    Disk,
    Frame,
    HalfPlane,
    Intersection,
    guard_distance,
)


def box(r_left: float, r_right: float, x_low: float, x_high: float) -> Characteristic:
    return Characteristic(Intersection((
        HalfPlane(-1.0, 0.0, r_left), HalfPlane(1.0, 0.0, r_right), HalfPlane(0.0, -1.0, -x_low), HalfPlane(0.0, 1.0, x_high),
    )), Frame.ABSOLUTE)


def same_vertices(a, b, tol=TOLERANCE_OHM) -> bool:
    a, b = list(a), list(b)
    return len(a) == len(b) and all(any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol for q in b) for p in a)


class TestPrimitives:
    def test_half_plane_membership_is_boundary_inclusive_within_the_tolerance(self):
        hp = HalfPlane(1.0, 0.0, 2.0)                                    # R <= 2
        assert hp.contains(2.0, 5.0) and hp.contains(2.0 + 0.5 * TOLERANCE_OHM, 0.0)
        assert not hp.contains(2.0 + 2 * TOLERANCE_OHM, 0.0)
        assert hp.signed_distance(3.0, 1.0) == pytest.approx(1.0)

    def test_a_half_plane_normal_must_be_a_unit_vector_and_finite(self):
        with pytest.raises(ValueError):
            HalfPlane(1.0, 1.0, 0.0)
        with pytest.raises(ValueError):
            HalfPlane(float("nan"), 0.0, 0.0)
        hp = HalfPlane.from_normal_angle(90.0, 3.0)                       # X <= 3 (normal at +90 deg, CCW from +R)
        assert hp.contains(10.0, 3.0) and not hp.contains(0.0, 3.1)

    def test_disk_membership_and_validation(self):
        d = Disk(1.0, 1.0, 1.0)
        assert d.contains(1.0, 2.0) and d.contains(2.0, 1.0) and not d.contains(2.0, 2.0)
        assert d.contains(1.0, 2.0 + 0.5 * TOLERANCE_OHM) and not d.contains(1.0, 2.0 + 2 * TOLERANCE_OHM)
        with pytest.raises(ValueError):
            Disk(0.0, 0.0, 0.0)

    def test_intersection_needs_every_part_and_is_never_empty(self):
        region = Intersection((HalfPlane(1.0, 0.0, 2.0), Disk(0.0, 0.0, 3.0)))
        assert region.contains(1.0, 1.0) and not region.contains(2.5, 0.0) and not region.contains(0.0, 3.5)
        with pytest.raises(ValueError):
            Intersection(())

    def test_point_reflection_is_a_180_degree_rotation_about_the_origin(self):
        z = box(0.5, 2.0, 0.0, 3.0)
        flipped = z.reflected()
        for r, x in ((1.0, 1.0), (-0.4, 2.9), (1.9, 0.1), (3.0, 1.0), (1.0, -1.0)):
            assert flipped.contains(-r, -x) == z.contains(r, x)
        assert flipped.reflected() == z

    def test_boundary_meta_is_carried_and_kept_by_reflection(self):
        meta = BoundaryMeta(source_path="zones[Z1].x_reach_ohm", transform="direct", frame=Frame.ZONE_LOCAL, fidelity="exact")
        assert HalfPlane(0.0, 1.0, 2.0, meta).reflected().meta is meta


class TestFrames:
    def test_a_zone_local_characteristic_is_never_evaluated_without_placing_it(self):
        local = Characteristic(HalfPlane(1.0, 0.0, 1.0), Frame.ZONE_LOCAL)
        with pytest.raises(ValueError):
            local.contains(0.0, 0.0)
        with pytest.raises(ValueError):
            local.outline()

    def test_placing_a_reverse_zone_reflects_it_and_a_forward_zone_is_unchanged(self):
        local = Characteristic(Disk(1.0, 2.0, 1.0), Frame.ZONE_LOCAL)
        assert local.to_absolute(Direction.FORWARD).region == Disk(1.0, 2.0, 1.0)
        assert local.to_absolute("reverse").region == Disk(-1.0, -2.0, 1.0)
        assert local.to_absolute("reverse").frame is Frame.ABSOLUTE
        with pytest.raises(ValueError):
            local.to_absolute("non_directional")


class TestOutlines:
    def test_a_single_disk_outlines_exactly(self):
        o = Characteristic(Disk(1.0, 2.0, 0.5), Frame.ABSOLUTE).outline()
        assert (o.kind, o.center, o.radius, o.approximated) == ("circle", (1.0, 2.0), 0.5, False)

    def test_a_rectangle_outlines_to_its_four_corners_counter_clockwise(self):
        o = box(1.0, 4.0, 0.0, 6.0).outline()
        assert o.kind == "polygon" and not o.clipped
        assert same_vertices(o.vertices, [(-1.0, 0.0), (4.0, 0.0), (4.0, 6.0), (-1.0, 6.0)])
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(o.vertices, o.vertices[1:] + o.vertices[:1])) / 2
        assert area == pytest.approx(30.0)                                # positive: counter-clockwise

    def test_a_zero_width_side_keeps_its_corners(self):
        o = box(0.0, 4.0, 0.0, 6.0).outline()                             # left limit exactly on the X axis
        assert same_vertices(o.vertices, [(0.0, 0.0), (4.0, 0.0), (4.0, 6.0), (0.0, 6.0)])

    def test_an_unbounded_region_needs_bounds_and_is_marked_clipped(self):
        half = Characteristic(HalfPlane(0.0, 1.0, 2.0), Frame.ABSOLUTE)    # X <= 2: unbounded
        with pytest.raises(ValueError):
            half.outline()
        o = half.outline(bounds=(-5.0, 5.0, -5.0, 5.0))
        assert o.clipped and same_vertices(o.vertices, [(-5.0, -5.0), (5.0, -5.0), (5.0, 2.0), (-5.0, 2.0)])

    def test_disk_and_half_planes_outline_as_an_approximated_polygon(self):
        o = Characteristic(Intersection((Disk(0.0, 0.0, 2.0), HalfPlane(0.0, -1.0, 0.0))), Frame.ABSOLUTE).outline()
        assert o.kind == "polygon" and o.approximated
        assert all(v[1] >= -TOLERANCE_OHM and math.hypot(*v) <= 2.0 + TOLERANCE_OHM for v in o.vertices)

    def test_an_empty_intersection_has_no_outline_vertices(self):
        o = Characteristic(Intersection((HalfPlane(1.0, 0.0, -1.0), HalfPlane(-1.0, 0.0, -1.0))), Frame.ABSOLUTE).outline(
            bounds=(-5, 5, -5, 5))
        assert o.vertices == ()


class TestEngineeringCheckpoints:
    """Independent geometry: what the shapes must be, worked out by hand."""

    def test_explicit_rx_rectangle_limits(self):
        z = box(1.0, 4.0, 0.0, 6.0)                                       # X <= 6, -1 <= R <= 4, X >= 0
        assert z.contains(3.99, 5.99) and not z.contains(3.99, 6.01)      # top X limit
        assert not z.contains(4.01, 1.0)                                  # +R limit
        assert z.contains(-0.99, 1.0) and not z.contains(-1.01, 1.0)      # -R limit
        assert not z.contains(1.0, -0.01)                                 # X >= 0 (forward)

    def test_reverse_characteristic_maps_a_point_to_its_180_degree_reflection(self):
        z = Characteristic(box(1.0, 4.0, 0.0, 6.0).region, Frame.ZONE_LOCAL).to_absolute("reverse")
        assert z.contains(-3.0, -5.0) and not z.contains(3.0, 5.0)
        assert z.contains(0.9, -2.0) and not z.contains(1.1, -2.0)        # the local -R side ends on +R

    def test_mho_centre_radius_and_known_points(self):
        reach, angle = 10.0, 75.0
        t = math.radians(angle)
        mho = Characteristic(Disk(reach / 2 * math.cos(t), reach / 2 * math.sin(t), reach / 2), Frame.ABSOLUTE)
        assert mho.contains(0.0, 0.0)                                     # the origin is on the circle
        assert mho.contains(reach * math.cos(t), reach * math.sin(t))     # the reach point is on the circle
        assert not mho.contains(1.01 * reach * math.cos(t), 1.01 * reach * math.sin(t))
        assert not mho.contains(-0.1 * math.cos(t), -0.1 * math.sin(t))  # just behind the origin
        o = mho.outline()
        assert o.center == pytest.approx((1.2940952255, 4.8296291314)) and o.radius == 5.0

    def test_rotated_rectangle_corners(self):
        # V1's polar quadrilateral at 60 deg: x' along 60 deg (reach 4), r' along -30 deg (right 2, left 1)
        t = math.radians(60.0)
        c, s = math.cos(t), math.sin(t)
        quad = Characteristic(Intersection((HalfPlane(-c, -s, 0.0), HalfPlane(c, s, 4.0), HalfPlane(s, -c, 2.0), HalfPlane(-s, c, 1.0))),
                              Frame.ABSOLUTE)
        expected = [(0 * c + r * s, 0 * s - r * c) for r in (-1.0, 2.0)] + [(4 * c + r * s, 4 * s - r * c) for r in (2.0, -1.0)]
        assert same_vertices(quad.outline().vertices, expected)
        hand = [(-0.8660254, 0.5), (1.7320508, -1.0), (3.7320508, 2.4641016), (1.1339746, 3.9641016)]   # worked by hand
        assert [v for p in expected for v in p] == pytest.approx([v for p in hand for v in p], abs=1e-7)


def test_guard_distance_scales_with_the_zone_and_never_drops_to_the_tolerance():
    assert guard_distance(100.0) == pytest.approx(0.1)
    assert guard_distance(0.0) == pytest.approx(1000 * TOLERANCE_OHM)


def test_membership_and_outline_are_fast_enough_for_interactive_plotting():
    t = math.radians(80.0)
    c, s = math.cos(t), math.sin(t)
    quad = Characteristic(Intersection((HalfPlane(-c, -s, 0.0), HalfPlane(c, s, 4.0), HalfPlane(s, -c, 2.0), HalfPlane(-s, c, 1.0))),
                          Frame.ABSOLUTE)
    start = time.perf_counter()
    for i in range(20_000):
        quad.contains((i % 200) * 0.05 - 5.0, (i // 200) * 0.1 - 5.0)
    for _ in range(200):
        quad.outline()
    assert time.perf_counter() - start < 2.0                              # pathological-runtime guard, not a benchmark
