"""Canonical inclined resistive boundaries (DEC-199 Phase 2A, shadow mode): equations, sides, frames, reflection,
provenance, the catalog ``boundaries`` section, and proof that production interpretation never sees them."""

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
    ResistiveBoundary,
    assemble_zone,
)
from app.domain.distance_geometry import TOLERANCE_OHM, Frame
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

    def test_production_interpretation_and_coverage_never_see_the_boundaries(self):
        data = json.loads(SA613.read_text(encoding="utf-8"))
        bare = {k: v for k, v in copy.deepcopy(data).items() if k != "boundaries"}
        document = extract_pdf(sheet_pdf("7sa613")).document
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


def test_the_boundary_module_is_relay_neutral():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app" / "domain" / "distance_boundaries.py").read_text(encoding="utf-8").lower()
    for oem in ("siemens", "toshiba", "hitachi", "abb", "7sa", "grz", "rel511", "catalog_id"):
        assert oem not in text, oem
