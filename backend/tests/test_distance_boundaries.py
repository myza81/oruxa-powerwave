"""Canonical shadow boundaries (DEC-199 Phase 2A / 2B / 2C, shadow mode): inclined resistive edges, directional half-planes
and lower reactance limits --
equations, sides, frames, reflection, provenance, the catalog ``boundaries`` section, and proof that production
interpretation never sees them."""

from __future__ import annotations

import copy
import json
import math

import pytest

from app.domain.distance_boundaries import (
    BoundaryFrame,
    BoundaryProvenance,
    BoundarySide,
    BoundarySource,
    DirectionalBoundary,
    ReactanceLowerBoundary,
    ResistiveBoundary,
    RetainedSide,
    TiltedReactanceBoundary,
    assemble_zone,
)
from app.domain.distance_geometry import TOLERANCE_OHM, Frame, HalfPlane
from app.domain.parameter_catalog.catalog_model import ConstantValue
from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import sheet_pdf

PROV = BoundaryProvenance((BoundarySource("r_at_axis", "R", "1", "2", "ohm"), BoundarySource("angle_deg", "phi", "2", "70", "deg")),
                          "zones[Z].resistive_reach.phase_phase", "r_at_axis = +R; angle = phi", "R(X) = R + X cot(phi)", ("ref-a",), "test")


def edge(r0: float, angle: float, side: str, frame: str = "zone") -> ResistiveBoundary:
    return ResistiveBoundary("Z", r0, angle, BoundarySide(side), BoundaryFrame(frame), PROV)


class TestEquation:
    @pytest.mark.parametrize("angle", [20.0, 45.0, 60.0, 82.0, 90.0, 110.0, 150.0])
    def test_the_edge_crosses_the_r_axis_at_r0_and_follows_cot(self, angle):
        e = edge(2.0, angle, "right")
        for x in (0.0, 1.0, -3.0, 7.5):
            expected = 2.0 + x / math.tan(math.radians(angle))
            assert e.r_at(x) == pytest.approx(expected, abs=1e-12)
            assert abs(e.half_plane().signed_distance(expected, x)) <= TOLERANCE_OHM    # the point lies on the edge

    def test_hand_worked_values_at_82_degrees(self):
        # cot(82 deg) = 0.1405408347; R = 1.5, X = 2.4: 1.5 + 0.3372980 = 1.8372980 (right), -1.5 + 0.3372980 (left)
        assert edge(1.5, 82.0, "right").r_at(2.4) == pytest.approx(1.8372980, abs=1e-6)
        assert edge(-1.5, 82.0, "left").r_at(2.4) == pytest.approx(-1.1627020, abs=1e-6)

    def test_ninety_degrees_degenerates_to_a_vertical_limit(self):
        right, left = edge(3.0, 90.0, "right").half_plane(), edge(-1.0, 90.0, "left").half_plane()
        assert (right.nr, right.offset) == pytest.approx((1.0, 3.0)) and abs(right.nx) < 1e-15
        assert (left.nr, left.offset) == pytest.approx((-1.0, 1.0)) and abs(left.nx) < 1e-15
        for x in (-5.0, 0.0, 5.0):
            assert right.contains(2.99, x) and not right.contains(3.01, x)
            assert left.contains(-0.99, x) and not left.contains(-1.01, x)


class TestSides:
    @pytest.mark.parametrize("angle", [30.0, 82.0, 120.0])
    def test_right_keeps_r_at_or_below_the_edge_and_left_at_or_above(self, angle):
        right, left = edge(1.0, angle, "right").half_plane(), edge(-1.0, angle, "left").half_plane()
        for x in (0.0, 2.0, 5.0):
            rr, rl = edge(1.0, angle, "right").r_at(x), edge(-1.0, angle, "left").r_at(x)
            assert right.contains(rr - 0.01, x) and not right.contains(rr + 0.01, x)
            assert left.contains(rl + 0.01, x) and not left.contains(rl - 0.01, x)

    def test_a_parallelogram_from_two_edges_and_the_top(self):
        z = assemble_zone("Z", x_reach_ohm=2.4, direction="forward",
                          boundaries=(ResistiveBoundary("Z", 1.5, 82.0, BoundarySide.RIGHT, BoundaryFrame.ZONE, PROV),
                                      ResistiveBoundary("Z", -1.5, 82.0, BoundarySide.LEFT, BoundaryFrame.ZONE, PROV)))
        c = z.characteristic
        assert (z.represented, z.not_represented) == (("top", "right", "left"), ("lower",))
        assert c.contains(1.83, 2.39) and not c.contains(1.85, 2.39)           # the right edge has moved out by 0.337 at the top
        assert c.contains(-1.16, 2.39) and not c.contains(-1.17, 2.39)
        assert c.contains(0.0, 2.4) and not c.contains(0.0, 2.41)


class TestFrames:
    def test_a_zone_frame_edge_is_reflected_for_a_reverse_zone(self):
        e = edge(2.0, 70.0, "right", "zone")
        fwd, rev = e.half_plane("forward"), e.half_plane("reverse")
        for r, x in ((1.0, 1.0), (3.0, 0.5), (-2.0, 4.0)):
            assert rev.contains(-r, -x) == fwd.contains(r, x)

    def test_an_absolute_edge_ignores_the_zone_direction(self):
        e = edge(2.0, 70.0, "right", "absolute")
        assert e.half_plane("reverse") == e.half_plane("forward")

    def test_an_assembled_reverse_zone_is_the_point_reflection_of_the_forward_one(self):
        edges = (edge(1.0, 75.0, "right"), edge(-0.5, 75.0, "left"))
        fwd = assemble_zone("Z", x_reach_ohm=2.0, direction="forward", boundaries=edges).characteristic
        rev = assemble_zone("Z", x_reach_ohm=2.0, direction="reverse", boundaries=edges).characteristic
        assert fwd.frame is Frame.ABSOLUTE and rev.frame is Frame.ABSOLUTE
        for r, x in ((0.5, 1.0), (1.2, 1.9), (-0.4, 0.2), (0.0, 2.1)):
            assert rev.contains(-r, -x) == fwd.contains(r, x)


class TestValidationAndProvenance:
    @pytest.mark.parametrize("kw", [{"angle_deg": 0.0}, {"angle_deg": 180.0}, {"r_at_axis": float("nan")}, {"fidelity": "approximate"},
                                    {"unit": "kohm"}])
    def test_invalid_boundaries_are_refused(self, kw):
        base = dict(zone_id="Z", r_at_axis=1.0, angle_deg=80.0, side=BoundarySide.RIGHT, frame=BoundaryFrame.ZONE, provenance=PROV)
        with pytest.raises(ValueError):
            ResistiveBoundary(**{**base, **kw})

    def test_the_provenance_travels_into_the_kernel_half_plane(self):
        meta = edge(2.0, 70.0, "right").half_plane("reverse").meta
        assert (meta.source_path, meta.unit, meta.frame, meta.reference, meta.fidelity) == (
            "zones[Z].resistive_reach.phase_phase", "ohm", Frame.ZONE_LOCAL, "ref-a", "documented")
        assert meta.transform == "r_at_axis = +R; angle = phi"


SA613 = CATALOG_ROOT / "siemens" / "siprotec4_7sa613.json"
REL511 = CATALOG_ROOT / "hitachi_energy" / "rel511.json"


def catalog(data):
    return parse_catalog(data, canonical_registry(), source="test")


class TestCatalogSection:
    def test_the_catalog_section_is_validated(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        for change in ({"side": "middle"}, {"kind": "blinder"}, {"frame": "implicit"}, {"fidelity": "approximate"},
                       {"references": []}, {"equation": ""}, {"r_at_axis": {"source": {"name": "R({zone}) ph-ph", "unit": "ohm"}, "sign": 2}}):
            bad = copy.deepcopy(data)
            bad["boundaries"][0].update(change)
            with pytest.raises(CatalogValidationError):
                catalog(bad)

    @pytest.mark.parametrize("path,sheet,overrides", [(SA613, "7sa613", {}), (SA613, "7sa613", {"set": {"1307 Zone Reduction": "10"}}),
                                                      (REL511, "rel511", {"variant": "directional"}), (REL511, "rel511", {}),
                                                      (CATALOG_ROOT / "siemens" / "siprotec5_7sl87.json", "7sl87", {})])
    def test_production_interpretation_and_coverage_never_see_the_boundaries(self, path, sheet, overrides):
        data = json.loads(path.read_text(encoding="utf-8"))
        bare = {k: v for k, v in copy.deepcopy(data).items() if k != "boundaries"}
        document = extract_pdf(sheet_pdf(sheet, overrides)).document
        with_b, without = (CatalogInterpreter(catalog(d), canonical_registry()).run(document) for d in (data, bare))
        assert with_b.model == without.model
        assert with_b.consumed == without.consumed and with_b.preserved_ids == without.preserved_ids

    def test_shadow_evaluation_reads_values_and_keeps_provenance_without_consuming(self):
        document = extract_pdf(sheet_pdf("7sa613")).document
        run = CatalogInterpreter(catalog(json.loads(SA613.read_text(encoding="utf-8"))), canonical_registry()).shadow_boundaries(document)
        z1 = {b.side: b for b in run.boundaries if b.zone_id == "Z1"}
        assert (z1[BoundarySide.RIGHT].r_at_axis, z1[BoundarySide.LEFT].r_at_axis, z1[BoundarySide.RIGHT].angle_deg) == (1.5, -1.5, 82.0)
        roles = {s.role: (s.code, s.name, s.raw_value, s.unit) for s in z1[BoundarySide.LEFT].provenance.sources}
        assert roles == {"r_at_axis": ("1302", "R(Z1) ph-ph", "1.5", "ohm"), "angle_deg": ("1211", "Distance Angle", "82", "deg")}
        assert z1[BoundarySide.LEFT].provenance.canonical_path == "zones[Z1].resistive_reach.reverse"
        assert "-R(Z1) ph-ph" in z1[BoundarySide.LEFT].provenance.transform
        assert {u[1] for u in run.unresolved} >= {"Z4", "Z5"}                       # Inactive, Non-Directional: not derived

    def test_a_blank_or_unreadable_value_derives_no_boundary(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        for cell in ("", "1,5x"):
            document = extract_pdf(sheet_pdf("7sa613", {"set": {"1302 R(Z1) ph-ph": cell}})).document
            run = CatalogInterpreter(catalog(data), canonical_registry()).shadow_boundaries(document)
            assert not any(b.zone_id == "Z1" for b in run.boundaries)


def rel511_run(overrides: dict) -> "object":
    document = extract_pdf(sheet_pdf("rel511", overrides)).document
    return CatalogInterpreter(catalog(json.loads(REL511.read_text(encoding="utf-8"))), canonical_registry()).shadow_boundaries(document)


SL87 = CATALOG_ROOT / "siemens" / "siprotec5_7sl87.json"


def sa613_run(overrides: dict) -> "object":
    document = extract_pdf(sheet_pdf("7sa613", overrides)).document
    return CatalogInterpreter(catalog(json.loads(SA613.read_text(encoding="utf-8"))), canonical_registry()).shadow_boundaries(document)


def sl87_run(overrides: dict) -> "object":
    document = extract_pdf(sheet_pdf("7sl87", overrides)).document
    return CatalogInterpreter(catalog(json.loads(SL87.read_text(encoding="utf-8"))), canonical_registry()).shadow_boundaries(document)


class TestDirectionalCatalogSection:
    """The OEM -> canonical angle conversion is explicit in the catalog and its provenance (REL511 is the first case)."""

    def test_a_fourth_quadrant_magnitude_becomes_a_negative_canonical_angle(self):
        run = rel511_run({"variant": "directional"})
        z1 = {b.retained_side: b for b in run.directional if b.zone_id == "Z1"}
        assert (z1[CCW].angle_deg, z1[CW].angle_deg) == (-15.0, 115.0)     # ArgDir 15 -> -15; ArgNegRes 115 -> +115
        assert [(s.role, s.name, s.raw_value, s.unit) for s in z1[CCW].provenance.sources] == [("angle_deg", "ArgDir", "15", "deg")]
        assert z1[CCW].provenance.transform == "canonical angle = -ArgDir = -15 deg (ArgDir 15 as printed, deg)"
        assert "Canonical angle = -ArgDir" in z1[CCW].provenance.convention
        assert "Canonical angle = +ArgNegRes" in z1[CW].provenance.convention
        assert {b.fidelity for b in run.directional} == {"static_equivalent"}
        assert {b.frame for b in run.directional} == {BoundaryFrame.ZONE}
        assert "abb-1mrk506109-uen-dir" in z1[CCW].provenance.reference_ids

    def test_the_resistive_lines_cross_at_half_the_loop_reach_parallel_to_the_line_impedance(self):
        z1 = {b.side: b for b in rel511_run({"variant": "directional"}).boundaries if b.zone_id == "Z1"}
        assert (z1[BoundarySide.RIGHT].r_at_axis, z1[BoundarySide.LEFT].r_at_axis) == (2.3, -2.3)        # RFZ1 4.6 / 2
        assert z1[BoundarySide.RIGHT].angle_deg == pytest.approx(80.5376777920, abs=1e-9)                # atan(3 / 0.5)
        assert "0.5 x RFZ1" in z1[BoundarySide.RIGHT].provenance.transform

    @pytest.mark.parametrize("name,value", [("ArgDir", "-15"), ("ArgDir", "50"), ("ArgNegRes", "25"), ("ArgNegRes", "-115")])
    def test_a_value_outside_the_documented_range_is_not_derived(self, name, value):
        # e.g. a sheet printing ArgDir already signed (-15), or ArgNegRes measured from the X axis (25): not inferred
        run = rel511_run({"variant": "directional", "set": {name: value}})
        assert not any(b.provenance.sources[0].name == name for b in run.directional)
        assert any(name in why and "outside the documented setting range" in why for _, _, why in run.unresolved)

    def test_a_sheet_without_the_directional_settings_derives_none(self):
        run = rel511_run({})
        assert run.directional == ()
        assert {why for bid, z, why in run.unresolved if z == "Z1" and "directional" in bid} == {
            "ArgDir: not present in the document", "ArgNegRes: not present in the document"}

    def test_the_directional_section_is_validated(self):
        data = json.loads(REL511.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "directional")
        for change in ({"retained_side": "forward"}, {"side": "right"}, {"convention": ""}, {"fidelity": "approximate"},
                       {"r_at_axis": {"source": {"name": "RFZ{n}", "unit": "ohm"}}},
                       {"angle_deg": {"source": {"name": "ArgDir", "unit": "deg"}, "sign": -1, "range": [45, 5]}},
                       {"angle_deg": {"source": {"name": "ArgDir", "unit": "ohm"}}}):
            bad = copy.deepcopy(data)
            bad["boundaries"][k].update(change)
            with pytest.raises(CatalogValidationError):
                catalog(bad)
        bad = copy.deepcopy(data)
        del bad["boundaries"][k]["convention"]
        with pytest.raises(CatalogValidationError):
            catalog(bad)
        bad = copy.deepcopy(data)
        bad["boundaries"][0]["r_at_axis"]["scale"] = 2
        with pytest.raises(CatalogValidationError):
            catalog(bad)

    def test_no_relion_670_catalog_declares_a_directional_mapping(self):
        # DEC-199 Phase 2B: Relion 670 ZDRDIR mapping deferred pending verified v1.2 technical-manual evidence
        paths = sorted((CATALOG_ROOT / "hitachi_energy").glob("re*670*.json"))
        assert [p.name for p in paths] == ["red670.json", "rel670.json"]
        for path in paths:
            assert "boundaries" not in json.loads(path.read_text(encoding="utf-8")), path.name


# ---------------------------------------------------------------------------------------------------------------------
# Directional half-planes (DEC-199 Phase 2B). Expected sides come from the angle of the point (atan2), worked by hand --
# never from the half-plane normal under test.
# ---------------------------------------------------------------------------------------------------------------------

DPROV = BoundaryProvenance((BoundarySource("angle_deg", "phi", None, "15", "deg"),), None, "angle = -phi", "a < arg Z", ("ref-a",),
                           "test", "phi is a magnitude below +R")
CCW, CW = RetainedSide.COUNTER_CLOCKWISE, RetainedSide.CLOCKWISE


def ray(angle: float, side: RetainedSide, frame: str = "zone", fidelity: str = "documented") -> DirectionalBoundary:
    return DirectionalBoundary("Z", angle, side, BoundaryFrame(frame), DPROV, fidelity)


def polar(angle: float, rho: float) -> tuple[float, float]:
    return rho * math.cos(math.radians(angle)), rho * math.sin(math.radians(angle))


class TestDirectionalLine:
    @pytest.mark.parametrize("angle", [-135.0, -15.0, 0.0, 37.0, 90.0, 115.0, 180.0])
    def test_the_line_passes_through_the_origin_along_the_ray(self, angle):
        for side in (CCW, CW):
            hp = ray(angle, side).half_plane()
            assert hp.offset == 0.0 and abs(hp.signed_distance(0.0, 0.0)) <= TOLERANCE_OHM
            for rho in (0.5, 3.0, 40.0):                          # (rho cos a, rho sin a) and its opposite lie on the line
                for point in (polar(angle, rho), polar(angle + 180.0, rho)):
                    assert abs(hp.signed_distance(*point)) <= TOLERANCE_OHM, (angle, side, rho)
            assert ray(angle, side).point_at(2.0) == pytest.approx(polar(angle, 2.0))

    @pytest.mark.parametrize("angle", [-135.0, -15.0, 0.0, 37.0, 90.0, 115.0, 180.0])
    def test_the_two_retained_sides_are_complementary(self, angle):
        ccw, cw = ray(angle, CCW).half_plane(), ray(angle, CW).half_plane()
        for turn in (5.0, 60.0, 175.0):                           # turned counter-clockwise off the ray: ccw side only
            assert ccw.contains(*polar(angle + turn, 2.0)) and not cw.contains(*polar(angle + turn, 2.0)), turn
            assert cw.contains(*polar(angle - turn, 2.0)) and not ccw.contains(*polar(angle - turn, 2.0)), turn

    def test_zero_degrees_keeps_x_non_negative_or_non_positive(self):
        ccw, cw = ray(0.0, CCW).half_plane(), ray(0.0, CW).half_plane()
        assert (ccw.nr, ccw.nx) == pytest.approx((0.0, -1.0)) and (cw.nr, cw.nx) == pytest.approx((0.0, 1.0))
        for r in (-5.0, 0.0, 5.0):
            assert ccw.contains(r, 0.1) and not ccw.contains(r, -0.1)
            assert cw.contains(r, -0.1) and not cw.contains(r, 0.1)

    def test_ninety_degrees_keeps_r_non_positive_or_non_negative(self):
        ccw, cw = ray(90.0, CCW).half_plane(), ray(90.0, CW).half_plane()
        assert (ccw.nr, ccw.nx) == pytest.approx((1.0, 0.0)) and (cw.nr, cw.nx) == pytest.approx((-1.0, 0.0))
        for x in (-5.0, 0.0, 5.0):
            assert ccw.contains(-0.1, x) and not ccw.contains(0.1, x)
            assert cw.contains(0.1, x) and not cw.contains(-0.1, x)

    def test_a_second_quadrant_line(self):
        # 115 deg: X = R tan 115 = -2.1445 R. (-1, 1) is at 135 deg (beyond the ray), (-1, 3) at 108.43 deg (short of it).
        ccw, cw = ray(115.0, CCW).half_plane(), ray(115.0, CW).half_plane()
        assert ccw.contains(-1.0, 1.0) and not cw.contains(-1.0, 1.0)
        assert cw.contains(-1.0, 3.0) and not ccw.contains(-1.0, 3.0)
        assert abs(cw.signed_distance(-1.0, 2.1445069205)) <= TOLERANCE_OHM

    def test_a_fourth_quadrant_line(self):
        # -15 deg: X = -0.26795 R. (1, 0) is at 0 deg (above the ray), (1, -0.5) at -26.57 deg (below it).
        ccw, cw = ray(-15.0, CCW).half_plane(), ray(-15.0, CW).half_plane()
        assert ccw.contains(1.0, 0.0) and not cw.contains(1.0, 0.0)
        assert cw.contains(1.0, -0.5) and not ccw.contains(1.0, -0.5)
        assert abs(ccw.signed_distance(1.0, -0.2679491924)) <= TOLERANCE_OHM

    @pytest.mark.parametrize("kw", [{"angle_deg": -180.0}, {"angle_deg": 180.5}, {"angle_deg": float("nan")},
                                    {"fidelity": "approximate"}, {"frame": "zone"}, {"retained_side": "forward"}])
    def test_invalid_directional_boundaries_are_refused(self, kw):
        base = dict(zone_id="Z", angle_deg=-15.0, retained_side=CCW, frame=BoundaryFrame.ZONE, provenance=DPROV)
        with pytest.raises(ValueError):
            DirectionalBoundary(**{**base, **kw})

    def test_fidelity_and_the_source_convention_travel_with_the_half_plane(self):
        b = ray(-15.0, CCW, fidelity="static_equivalent")
        meta = b.half_plane("reverse").meta
        assert (meta.fidelity, meta.unit, meta.frame, meta.transform) == ("static_equivalent", "deg", Frame.ZONE_LOCAL, "angle = -phi")
        assert b.provenance.convention == "phi is a magnitude below +R"


def sector_zone(direction: str, lower: float = -15.0, upper: float = 115.0, frame: str = "zone"):
    edges = (edge(4.0, 80.0, "right"), edge(-4.0, 80.0, "left"))
    return assemble_zone("Z", x_reach_ohm=5.0, direction=direction, boundaries=edges,
                         directional=(ray(lower, CCW, frame), ray(upper, CW, frame)))


class TestDirectionalSector:
    # The sector -15 < arg Z < 115 (inside the resistive band and below X = 5): expected by the point's angle.
    INSIDE = [(1.0, 1.0), (2.0, 0.2), (1.0, -0.2), (0.0, 2.0), (-0.5, 2.0), (-0.3, 1.0)]     # 45, 5.7, -11.3, 90, 104, 106.7 deg
    OUTSIDE = [(-1.0, -1.0), (-2.0, 0.5), (1.0, -0.5), (-1.0, 1.0), (0.0, -1.0), (-1.0, 0.0)]  # 225, 166, -26.6, 135, -90, 180 deg

    def test_the_forward_sector_is_the_region_between_the_two_lines(self):
        c = sector_zone("forward").characteristic
        for p in self.INSIDE:
            assert c.contains(*p), p
        for p in self.OUTSIDE:
            assert not c.contains(*p), p
        assert sector_zone("forward").represented == ("top", "right", "left", "directional")

    def test_the_reverse_sector_is_one_point_reflection_of_the_forward_one(self):
        fwd, rev = sector_zone("forward").characteristic, sector_zone("reverse").characteristic
        for p in self.INSIDE:                                      # reverse: 165 < arg Z < 295, by hand
            assert rev.contains(-p[0], -p[1]), p
        for p in self.OUTSIDE:
            assert not rev.contains(-p[0], -p[1]), p
        for k in range(72):                                        # everywhere: rev(p) == fwd(-p)
            p = polar(k * 5.0 + 2.5, 0.37 * (1 + k % 7))
            assert rev.contains(*p) == fwd.contains(-p[0], -p[1]), p

    def test_a_reverse_zone_cannot_be_reflected_twice(self):
        rev = sector_zone("reverse").characteristic
        assert rev.frame is Frame.ABSOLUTE and rev.to_absolute("reverse") is rev
        assert rev.contains(-1.0, -1.0) and not rev.contains(1.0, 1.0)     # a second reflection would swap these

    def test_absolute_frame_lines_are_not_reflected_with_the_zone(self):
        # zone-frame top and band are reflected (top becomes X >= -5; the band is symmetric); absolute lines stay forward
        rev = sector_zone("reverse", frame="absolute").characteristic
        assert rev.contains(1.0, 1.0) and not rev.contains(-1.0, -1.0)
        assert rev.contains(1.0, 6.0)          # above the forward top: only the reflected top (X >= -5) applies

    @pytest.mark.parametrize("lower,upper", [(-45.0, 175.0), (-90.0, 90.0), (10.0, 10.0), (20.0, 10.0)])
    def test_a_sector_of_180_degrees_or_more_is_refused(self, lower, upper):
        # -45..175 sweeps 220 deg: the region between the rays is then the union of the half-planes, not their intersection
        with pytest.raises(ValueError, match="sector"):
            sector_zone("forward", lower, upper)

    def test_one_line_per_retained_side(self):
        with pytest.raises(ValueError):
            assemble_zone("Z", x_reach_ohm=5.0, direction="forward", boundaries=(edge(4.0, 80.0, "right"), edge(-4.0, 80.0, "left")),
                          directional=(ray(-15.0, CCW), ray(-10.0, CCW)))


# ---------------------------------------------------------------------------------------------------------------------
# Lower reactance limit X >= -x_minus (DEC-199 Phase 2C). Expected sides are the plain inequality on X.
# ---------------------------------------------------------------------------------------------------------------------

LPROV = BoundaryProvenance((BoundarySource("x_minus", "X", "9", "3", "ohm"),), "zones[Z].x_reach_ohm", "x_minus = +X", "X >= -X",
                           ("ref-a",), "test")


def low(x_minus: float, frame: str = "zone", fidelity: str = "documented") -> ReactanceLowerBoundary:
    return ReactanceLowerBoundary("Z", x_minus, BoundaryFrame(frame), LPROV, fidelity=fidelity)


class TestReactanceLower:
    @pytest.mark.parametrize("x_minus", [0.25, 1.0, 3.0, 47.5])
    def test_a_positive_x_minus_is_a_limit_below_the_origin(self, x_minus):
        hp = low(x_minus).half_plane()
        assert (hp.nr, hp.nx, hp.offset) == (0.0, -1.0, x_minus)
        for r in (-10.0, 0.0, 4.0):
            assert abs(hp.signed_distance(r, -x_minus)) <= TOLERANCE_OHM        # on X = -x_minus
            assert hp.contains(r, -x_minus + 0.01) and not hp.contains(r, -x_minus - 0.01)
        assert hp.contains(0.0, 0.0) and hp.signed_distance(0.0, 0.0) == -x_minus   # the origin is x_minus inside

    def test_zero_is_x_non_negative(self):
        hp = low(0.0).half_plane()
        assert hp.contains(5.0, 0.0) and hp.contains(-5.0, 0.001) and not hp.contains(0.0, -0.001)

    @pytest.mark.parametrize("x_minus", [0.0, 2.0])
    def test_a_zone_frame_limit_is_reflected_for_a_reverse_zone(self, x_minus):
        rev = low(x_minus, "zone").half_plane("reverse")                       # X >= -x  ->  X <= x
        assert (rev.nr, rev.nx, rev.offset) == (0.0, 1.0, x_minus)
        assert rev.contains(1.0, x_minus - 0.01) and not rev.contains(1.0, x_minus + 0.01)
        for r, x in ((1.0, -1.5), (-3.0, 2.5), (0.0, -2.01)):
            assert rev.contains(-r, -x) == low(x_minus, "zone").half_plane().contains(r, x)

    def test_an_absolute_limit_is_not_reflected(self):
        assert low(2.0, "absolute").half_plane("reverse") == low(2.0, "absolute").half_plane("forward")

    def test_the_provenance_travels_into_the_kernel_half_plane(self):
        meta = low(3.0).half_plane("reverse").meta
        assert (meta.source_path, meta.unit, meta.frame, meta.reference, meta.fidelity, meta.transform) == (
            "zones[Z].x_reach_ohm", "ohm", Frame.ZONE_LOCAL, "ref-a", "documented", "x_minus = +X")

    @pytest.mark.parametrize("kw", [{"x_minus": -0.5}, {"x_minus": float("nan")}, {"x_minus": float("inf")}, {"frame": "zone"},
                                    {"unit": "kohm"}, {"fidelity": "approximate"}, {"fidelity": "static_equivalent"}])
    def test_invalid_lower_limits_are_refused(self, kw):
        base = dict(zone_id="Z", x_minus=1.0, frame=BoundaryFrame.ZONE, provenance=LPROV)
        with pytest.raises(ValueError):
            ReactanceLowerBoundary(**{**base, **kw})

    def test_a_closed_parallelogram_and_its_reverse(self):
        edges = (edge(1.5, 80.0, "right"), edge(-1.5, 80.0, "left"))
        fwd = assemble_zone("Z", x_reach_ohm=2.0, direction="forward", boundaries=edges, lower=low(2.0))
        rev = assemble_zone("Z", x_reach_ohm=2.0, direction="reverse", boundaries=edges, lower=low(2.0))
        assert (fwd.represented, fwd.not_represented) == (("top", "right", "left", "lower"), ())
        outline = fwd.characteristic.outline()                                  # bounded: no plotting bounds needed
        assert not outline.clipped and len(outline.vertices) == 4
        # hand-worked: cot 80 = 0.17633; at X = -1.99 the band is R in [-1.85090, 1.14910]
        assert fwd.characteristic.contains(0.0, -1.99) and not fwd.characteristic.contains(0.0, -2.01)
        assert fwd.characteristic.contains(1.14, -1.99) and not fwd.characteristic.contains(1.16, -1.99)
        for r, x in ((0.0, -1.99), (0.0, -2.01), (1.14, -1.99), (0.5, 1.0), (0.0, 2.01)):
            assert rev.characteristic.contains(-r, -x) == fwd.characteristic.contains(r, x)
        assert rev.characteristic.to_absolute("reverse") is rev.characteristic

    def test_a_lower_limit_of_another_zone_is_refused(self):
        with pytest.raises(ValueError):
            assemble_zone("Y", x_reach_ohm=2.0, direction="forward",
                          boundaries=(ResistiveBoundary("Y", 1.0, 80.0, BoundarySide.RIGHT, BoundaryFrame.ZONE, PROV),
                                      ResistiveBoundary("Y", -1.0, 80.0, BoundarySide.LEFT, BoundaryFrame.ZONE, PROV)),
                          lower=low(2.0))


class TestLowerCatalogSection:
    def test_the_documented_lower_limit_is_the_zone_reach_as_printed(self):
        run = rel511_run({"variant": "directional"})
        z1 = next(b for b in run.lower if b.zone_id == "Z1")
        assert (z1.x_minus, z1.frame, z1.unit, z1.fidelity) == (3.0, BoundaryFrame.ZONE, "ohm", "documented")
        assert [(s.role, s.name, s.raw_value, s.unit) for s in z1.provenance.sources] == [("x_minus", "X1Z1", "3", "ohm")]
        assert z1.provenance.transform == "x_minus = +X1Z1 (as printed, ohm): X >= -3 ohm"
        assert z1.provenance.canonical_path == "zones[Z1].x_reach_ohm"
        assert "Eq. 33" in z1.provenance.equation and "abb-1mrk506109-uen-pp" in z1.provenance.reference_ids
        assert {b.zone_id for b in run.lower} == {"Z1", "Z2"}

    def test_the_lower_limit_does_not_need_the_directional_settings(self):
        run = rel511_run({})                                                    # the synthetic sheet: no ArgDir / ArgNegRes
        assert [b.x_minus for b in run.lower] == [3.0] and run.directional == ()

    def test_the_lower_section_is_validated(self):
        data = json.loads(REL511.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "reactance_lower")
        for change in ({"x_minus": {"source": {"name": "X1Z{n}", "unit": "ohm"}, "sign": -1}}, {"x_minus": {"source": {"name": "X1Z{n}", "unit": "deg"}}},
                       {"angle_deg": {"source": {"name": "ArgDir", "unit": "deg"}}}, {"side": "right"}, {"retained_side": "clockwise"},
                       {"r_at_axis": {"source": {"name": "RFZ{n}", "unit": "ohm"}}}, {"fidelity": "static_equivalent"}, {"frame": "implicit"}):
            bad = copy.deepcopy(data)
            bad["boundaries"][k].update(change)
            with pytest.raises(CatalogValidationError):
                catalog(bad)
        bad = copy.deepcopy(data)
        del bad["boundaries"][k]["x_minus"]
        with pytest.raises(CatalogValidationError):
            catalog(bad)


# ---------------------------------------------------------------------------------------------------------------------
# Tilted upper reactance limit X <= x_at_reference - R * tan(tilt_deg) (DEC-199 Phase 2D). Expected sides come from the
# plain line equation, worked by hand.
# ---------------------------------------------------------------------------------------------------------------------

UPROV = BoundaryProvenance((BoundarySource("x_at_reference", "X", "9", "2.4", "ohm"), BoundarySource("tilt_deg", "ZR", "10", "10", "deg")),
                           "zones[Z].tilt_deg", "x_at_reference = +X; tilt_deg = +ZR", "X <= Xref - R tan(tilt)", ("ref-a",), "test")


def upper(x_at_reference: float, tilt_deg: float, frame: str = "zone", fidelity: str = "documented") -> TiltedReactanceBoundary:
    return TiltedReactanceBoundary("Z", x_at_reference, tilt_deg, BoundaryFrame(frame), UPROV, fidelity=fidelity)


class TestTiltedUpper:
    def test_the_line_passes_through_the_pivot_point(self):
        for tilt in (-45.0, -10.0, 0.0, 10.0, 45.0, 89.0):
            b = upper(2.4, tilt)
            assert b.x_at(0.0) == pytest.approx(2.4)
            assert abs(b.half_plane().signed_distance(0.0, 2.4)) <= TOLERANCE_OHM

    def test_retained_side_is_below_the_line(self):
        b = upper(2.4, 10.0)
        hp = b.half_plane()
        for r in (-5.0, 0.0, 3.0):
            x = b.x_at(r)
            assert hp.contains(r, x - 0.01) and not hp.contains(r, x + 0.01)

    def test_zero_tilt_is_exactly_the_plain_horizontal_top(self):
        hp = upper(2.4, 0.0).half_plane()
        assert (hp.nr, hp.nx, hp.offset) == (0.0, 1.0, 2.4)        # bit-exact: sin(0.0) == 0.0, cos(0.0) == 1.0
        assert hp == HalfPlane(0.0, 1.0, 2.4, hp.meta)

    def test_a_positive_tilt_lowers_the_limit_as_r_increases(self):
        b = upper(2.4, 10.0)
        # hand-worked: tan(10 deg) = 0.1763270; X(1) = 2.4 - 0.1763270 = 2.2236730; X(-1) = 2.5763270
        assert b.x_at(1.0) == pytest.approx(2.2236730, abs=1e-6) and b.x_at(1.0) < 2.4
        assert b.x_at(-1.0) == pytest.approx(2.5763270, abs=1e-6) and b.x_at(-1.0) > 2.4

    def test_a_negative_tilt_raises_the_limit_as_r_increases(self):
        b = upper(2.4, -10.0)
        assert b.x_at(1.0) == pytest.approx(2.5763270, abs=1e-6) and b.x_at(1.0) > 2.4
        assert b.x_at(-1.0) == pytest.approx(2.2236730, abs=1e-6) and b.x_at(-1.0) < 2.4

    def test_a_zone_frame_limit_is_reflected_for_a_reverse_zone(self):
        fwd, rev = upper(2.4, 10.0).half_plane(), upper(2.4, 10.0).half_plane("reverse")
        for r, x in ((1.0, 1.0), (3.0, -0.5), (-2.0, 4.0)):
            assert rev.contains(-r, -x) == fwd.contains(r, x)

    def test_an_absolute_limit_is_not_reflected(self):
        b = upper(2.4, 10.0, "absolute")
        assert b.half_plane("reverse") == b.half_plane("forward")

    def test_the_provenance_and_fidelity_travel_into_the_kernel_half_plane(self):
        meta = upper(2.4, 10.0, fidelity="exact").half_plane("reverse").meta
        assert (meta.source_path, meta.unit, meta.frame, meta.reference, meta.fidelity, meta.transform) == (
            "zones[Z].tilt_deg", "ohm", Frame.ZONE_LOCAL, "ref-a", "exact", "x_at_reference = +X; tilt_deg = +ZR")

    @pytest.mark.parametrize("kw", [{"tilt_deg": -90.0}, {"tilt_deg": 90.0}, {"tilt_deg": float("nan")}, {"x_at_reference": float("inf")},
                                    {"frame": "zone"}, {"unit": "kohm"}, {"fidelity": "approximate"}, {"fidelity": "static_equivalent"}])
    def test_invalid_tilted_limits_are_refused(self, kw):
        base = dict(zone_id="Z", x_at_reference=2.4, tilt_deg=10.0, frame=BoundaryFrame.ZONE, provenance=UPROV)
        with pytest.raises(ValueError):
            TiltedReactanceBoundary(**{**base, **kw})

    def test_the_tilted_limit_is_added_alongside_the_plain_top_not_in_its_place(self):
        # at R = -1 the tilted line alone would allow X up to 2.576 (see test_a_positive_tilt...); the plain top
        # X <= 2.4 still binds there -- added alongside, not replacing it
        z = assemble_zone("Z", x_reach_ohm=2.4, direction="forward",
                          boundaries=(edge(1.5, 80.0, "right"), edge(-1.5, 80.0, "left")), upper=upper(2.4, 10.0))
        assert z.characteristic.contains(-1.0, 2.39) and not z.characteristic.contains(-1.0, 2.41)
        # at R = +1 (inside the resistive band) the tilted line is the tighter constraint: X <= 2.2236730
        assert z.characteristic.contains(1.0, 2.22) and not z.characteristic.contains(1.0, 2.24)
        assert z.represented == ("top", "right", "left", "tilt") and z.not_represented == ("lower",)

    def test_zero_tilt_assembled_matches_the_untilted_zone_exactly(self):
        edges = (edge(1.5, 80.0, "right"), edge(-1.5, 80.0, "left"))
        with_zero_tilt = assemble_zone("Z", x_reach_ohm=2.4, direction="forward", boundaries=edges, upper=upper(2.4, 0.0))
        untilted = assemble_zone("Z", x_reach_ohm=2.4, direction="forward", boundaries=edges)
        for r, x in ((0.0, 2.4), (0.0, 2.41), (1.8, 2.4), (-1.8, 2.4), (0.0, -5.0)):
            assert with_zero_tilt.characteristic.contains(r, x) == untilted.characteristic.contains(r, x)

    def test_an_upper_limit_of_another_zone_is_refused(self):
        with pytest.raises(ValueError):
            assemble_zone("Y", x_reach_ohm=2.0, direction="forward",
                          boundaries=(ResistiveBoundary("Y", 1.0, 80.0, BoundarySide.RIGHT, BoundaryFrame.ZONE, PROV),
                                      ResistiveBoundary("Y", -1.0, 80.0, BoundarySide.LEFT, BoundaryFrame.ZONE, PROV)),
                          upper=upper(2.0, 10.0))


class TestTiltCatalogSection:
    def test_7sa613_zone_reduction_is_only_derived_for_z1(self):
        run = sa613_run({"set": {"1307 Zone Reduction": "10"}})
        z1 = next(b for b in run.upper if b.zone_id == "Z1")
        assert (z1.x_at_reference, z1.tilt_deg, z1.frame, z1.fidelity) == (2.4, 10.0, BoundaryFrame.ZONE, "documented")
        assert [(s.role, s.name, s.raw_value, s.unit) for s in z1.provenance.sources] == [
            ("x_at_reference", "X(Z1)", "2.4", "ohm"), ("tilt_deg", "Zone Reduction", "10", "deg")]
        assert z1.provenance.transform == "x_at_reference = +X(Z1) (as printed, ohm); tilt_deg = +Zone Reduction = 10 deg (Zone Reduction 10 as printed, deg)"
        assert z1.provenance.canonical_path == "zones[Z1].tilt_deg"
        assert {b.zone_id for b in run.upper} == {"Z1"}                # Z1B and the higher zones have no such tilt

    def test_7sa613_default_zero_is_derived_too(self):
        run = sa613_run({})
        assert [(b.zone_id, b.tilt_deg) for b in run.upper] == [("Z1", 0.0)]

    def test_7sl87_zone_inclination_is_derived_per_zone(self):
        run = sl87_run({"set": {"21.901.3571.113 Zone-inclination angle": "5"}})
        z1 = next(b for b in run.upper if b.zone_id == "Z1")
        assert (z1.x_at_reference, z1.tilt_deg) == (4.7, 5.0)
        assert "21.901.3571.102 X reach" in z1.provenance.transform

    @pytest.mark.parametrize("sheet,run_fn,field,value", [
        ("7sa613", sa613_run, "1307 Zone Reduction", "50"),             # outside the documented 0-45 deg range
        ("7sl87", sl87_run, "21.901.3571.113 Zone-inclination angle", "50"),
    ])
    def test_a_value_outside_the_documented_range_is_not_derived(self, sheet, run_fn, field, value):
        run = run_fn({"set": {field: value}})
        assert not any(b.zone_id == "Z1" for b in run.upper)
        assert any("outside the documented setting range" in why for _, zone, why in run.unresolved if zone == "Z1")

    def test_a_blank_or_malformed_tilt_derives_no_boundary(self):
        for cell in ("", "abc"):
            run = sa613_run({"set": {"1307 Zone Reduction": cell}})
            assert not any(b.zone_id == "Z1" for b in run.upper)

    def test_the_tilt_section_is_validated(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "reactance_upper")
        for change in ({"side": "right"}, {"retained_side": "clockwise"}, {"angle_deg": {"source": {"name": "Distance Angle", "unit": "deg"}}},
                       {"r_at_axis": {"source": {"name": "R({zone}) ph-ph", "unit": "ohm"}}}, {"fidelity": "static_equivalent"},
                       {"tilt_deg": {"source": {"name": "Zone Reduction", "unit": "deg"}, "range": [45, 0]}},
                       {"tilt_deg": {"source": {"name": "Zone Reduction", "unit": "ohm"}}},
                       {"x_at_reference": {"source": {"name": "X(Z1)", "unit": "deg"}}}):
            bad = copy.deepcopy(data)
            bad["boundaries"][k].update(change)
            with pytest.raises(CatalogValidationError):
                catalog(bad)
        bad = copy.deepcopy(data)
        del bad["boundaries"][k]["x_at_reference"]
        with pytest.raises(CatalogValidationError):
            catalog(bad)
        bad = copy.deepcopy(data)
        del bad["boundaries"][k]["tilt_deg"]
        with pytest.raises(CatalogValidationError):
            catalog(bad)


# ---------------------------------------------------------------------------------------------------------------------
# Generic constant-value boundaries (DEC-199 Phase 2G): {"constant": number, "unit": ..., "name": ...} in place of
# {"source": ...}. First verified case: GRZ100's fixed 75 deg right blinder angle.
# ---------------------------------------------------------------------------------------------------------------------

GRZ100 = CATALOG_ROOT / "toshiba" / "grz100.json"


def grz100_run(overrides: dict) -> "object":
    document = extract_pdf(sheet_pdf("grz100", overrides)).document
    return CatalogInterpreter(catalog(json.loads(GRZ100.read_text(encoding="utf-8"))), canonical_registry()).shadow_boundaries(document)


class TestConstantCatalogSection:
    """Generic validation of ``{"constant": ..., "unit": ..., "name": ...}``, independent of GRZ100."""

    def test_a_valid_constant_is_accepted(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "resistive")
        ok = copy.deepcopy(data)
        ok["boundaries"][k]["angle_deg"] = {"constant": 75, "unit": "deg", "name": "test constant"}
        catalog(ok)                                                        # does not raise

    @pytest.mark.parametrize("angle_deg", [
        {"constant": 75, "unit": "deg", "name": "x", "source": {"name": "Distance Angle", "unit": "deg"}},  # both
        {"constant": "75", "unit": "deg", "name": "x"},                    # string
        {"constant": True, "unit": "deg", "name": "x"},                    # bool
        {"constant": float("nan"), "unit": "deg", "name": "x"},            # NaN
        {"constant": float("inf"), "unit": "deg", "name": "x"},            # infinite
        {"constant": 75, "unit": "ohm", "name": "x"},                      # wrong unit
        {"constant": 75, "unit": "deg"},                                   # no name
        {"constant": 75, "unit": "deg", "name": ""},                       # blank name
        {"constant": 75, "unit": "deg", "name": "x", "range": [0, 45]},    # range not allowed on a constant
        {"constant": 75, "unit": "deg", "name": "x", "sign": 2},           # bad sign
    ])
    def test_invalid_constants_are_refused(self, angle_deg):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "resistive")
        bad = copy.deepcopy(data)
        bad["boundaries"][k]["angle_deg"] = angle_deg
        with pytest.raises(CatalogValidationError):
            catalog(bad)

    def test_a_constant_boundary_still_needs_a_verified_reference(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        k = next(i for i, b in enumerate(data["boundaries"]) if b["kind"] == "resistive")
        bad = copy.deepcopy(data)
        bad["boundaries"][k]["angle_deg"] = {"constant": 75, "unit": "deg", "name": "x"}
        bad["boundaries"][k]["references"] = []
        with pytest.raises(CatalogValidationError):
            catalog(bad)

    def test_existing_source_based_boundaries_are_unaffected(self):
        """Regression (DEC-199 Phase 2G): adding constant support changes nothing about REL511 / 7SA613 / 7SL87's own
        source-based mappings."""
        for path in (SA613, REL511, SL87):
            data = json.loads(path.read_text(encoding="utf-8"))
            c = catalog(data)                                             # still parses
            for b in c.boundaries:
                if b.angle_deg is not None:
                    assert not isinstance(b.angle_deg, ConstantValue), (path.name, b.id)


class TestGRZ100CatalogSection:
    def test_the_right_blinder_is_a_resistive_boundary_at_a_fixed_75_degrees(self):
        run = grz100_run({})
        by_zone = {b.zone_id: b for b in run.boundaries}
        assert set(by_zone) == {"Z1", "Z1X", "Z2", "ZF", "Z3"}            # forward zones only -- never ZR1/ZR2/ZND/Z4
        z1 = by_zone["Z1"]
        assert (z1.r_at_axis, z1.angle_deg, z1.side, z1.frame, z1.fidelity) == (
            20.0, 75.0, BoundarySide.RIGHT, BoundaryFrame.ZONE, "documented")
        roles = {s.role: (s.name, s.raw_value, s.unit, s.page, s.line) for s in z1.provenance.sources}
        assert roles["r_at_axis"] == ("BFRS", "20", "ohm", 1, 33)          # read from the document, with a location
        assert roles["angle_deg"][1:3] == ("75", "deg") and roles["angle_deg"][3:] == (None, None)  # a constant: no location
        assert "abb-" not in str(z1.provenance.reference_ids)             # Toshiba references, never ABB's
        assert set(z1.provenance.reference_ids) == {"toshiba-6f2s0834-0-elements", "toshiba-6f2s0834-0-settings"}
        assert z1.provenance.canonical_path == "zones[Z1].resistive_reach.phase_phase"

    def test_a_blank_bfrs_derives_no_boundary_and_substitutes_no_default(self):
        """The safeguard this phase exists for: a missing configured BFRS is never silently replaced by the fixed
        75 deg constant standing in for it, and the 75 deg constant never substitutes for BFRS either."""
        for cell in ("", "x"):
            run = grz100_run({"set": {"BFRS": cell}})
            assert run.boundaries == ()
            assert {zone for bid, zone, why in run.unresolved if bid == "grz100.boundary.right"} == {
                "Z1", "Z1X", "Z2", "ZF", "Z3"}

    def test_mho_characteristic_derives_no_boundary(self):
        run = grz100_run({"set": {"ZS-C": "Mho"}})
        assert run.boundaries == ()
        assert all("Mho" in why for _, _, why in run.unresolved)

    def test_production_interpretation_and_coverage_never_see_the_boundary(self):
        data = json.loads(GRZ100.read_text(encoding="utf-8"))
        bare = {k: v for k, v in copy.deepcopy(data).items() if k != "boundaries"}
        document = extract_pdf(sheet_pdf("grz100")).document
        with_b, without = (CatalogInterpreter(catalog(d), canonical_registry()).run(document) for d in (data, bare))
        assert with_b.model == without.model
        assert with_b.consumed == without.consumed and with_b.preserved_ids == without.preserved_ids

    def test_the_catalog_section_is_validated(self):
        data = json.loads(GRZ100.read_text(encoding="utf-8"))
        for change in ({"side": "top"}, {"retained_side": "clockwise"}, {"frame": "implicit"}, {"fidelity": "static_equivalent"},
                       {"zone": ["ZQ"]}, {"r_at_axis": {"source": {"name": "BRRS", "unit": "ohm"}, "sign": 2}}):
            bad = copy.deepcopy(data)
            bad["boundaries"][0].update(change)
            with pytest.raises(CatalogValidationError):
                catalog(bad)


def test_the_boundary_module_is_relay_neutral():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app" / "domain" / "distance_boundaries.py").read_text(encoding="utf-8").lower()
    for oem in ("siemens", "toshiba", "hitachi", "abb", "7sa", "7sl", "grz", "rel511", "rel670", "red670", "argdir", "argnegres",
                "zdrdir", "zone reduction", "zone-inclination", "bfrs", "blinder", "catalog_id"):
        assert oem not in text, oem
