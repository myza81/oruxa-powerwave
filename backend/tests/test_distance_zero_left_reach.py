"""A quadrilateral Left Resistive Reach (-R) of exactly 0 ohm is a valid configured
value: the left boundary lies at R = 0 (in the zone's rotated frame, r' = 0).

    unset (None) -> not configured      0.0 -> valid      > 0 -> valid      < 0 -> invalid

Left/Right Resistive Reach is quadrilateral geometry; forward/reverse is the zone's
direction -- kept apart here. Includes the end-to-end regression review overlay ->
adapter -> engine, so "adapter ready but the engine never operates" cannot recur.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.domain.distance_protection import (
    CHARACTERISTIC_QUADRILATERAL,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    ZONE_STATE_NOT_OPERATED,
    ZONE_STATE_OPERATED,
    ZoneSettings,
    evaluate_zone_state,
    quadrilateral_zone_operated,
)
from app.domain.impedance import ImpedancePoint
from app.domain.relay_import.provenance import ReviewStatus
from app.domain.relay_import.review_state import ReviewDecisions, apply_review
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.services.relay_interpretation_summary import engine_adaptation
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_review_state import REVERSE, ZP_STATUS


def pt(r, x):
    return ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r)))


def quad(p, rr, direction=DIRECTION_FORWARD, angle=90.0, x=10.0, rf=5.0):
    return quadrilateral_zone_operated(
        p, reactive_reach_ohm=x, resistive_reach_forward_ohm=rf, resistive_reach_reverse_ohm=rr,
        characteristic_angle_deg=angle, direction=direction,
    )


def state(p, rr, **kw):
    zone = ZoneSettings(True, None, 10.0, 5.0, rr, kw.pop("angle", 90.0), 0.0, **kw)
    return evaluate_zone_state(p, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone)


class TestLeftReachSemantics:
    def test_unset_is_not_configured(self):
        assert state(pt(1.0, 5.0), None) == ZONE_STATE_NOT_OPERATED

    def test_zero_is_a_valid_configured_value(self):
        assert quad(pt(1.0, 5.0), 0.0) is True
        assert state(pt(1.0, 5.0), 0.0) == ZONE_STATE_OPERATED

    def test_positive_is_unchanged(self):
        assert quad(pt(-1.5, 5.0), 2.0) is True
        assert quad(pt(-2.5, 5.0), 2.0) is False
        assert quad(pt(-2.0, 5.0), 2.0) is True  # inclusive boundary, as before

    @pytest.mark.parametrize("bad", [-0.1, -5.0, math.nan, math.inf, -math.inf])
    def test_negative_or_non_finite_is_invalid(self, bad):
        assert quad(pt(1.0, 5.0), bad) is False


class TestZeroLeftGeometry:
    def test_positive_r_points_operate(self):
        for r in (0.5, 2.0, 5.0):
            assert quad(pt(r, 5.0), 0.0) is True

    def test_negative_r_beyond_the_boundary_does_not_operate(self):
        for r in (-0.5, -2.0, -50.0):
            assert quad(pt(r, 5.0), 0.0) is False

    def test_the_r_zero_boundary_is_inclusive_like_every_other_boundary(self):
        assert quad(pt(0.0, 5.0), 0.0) is True  # on the left boundary
        assert quad(pt(5.0, 5.0), 0.0) is True  # on the right boundary
        assert quad(pt(5.1, 5.0), 0.0) is False

    def test_rotated_angle_uses_the_perpendicular_frame(self):
        # theta=60: r' = R sin(60) - X cos(60). A point with r' > 0 operates, r' < 0 does not.
        inside, outside = pt(4.0, 2.0), pt(1.0, 4.0)
        assert 4.0 * math.sin(math.radians(60)) - 2.0 * math.cos(math.radians(60)) > 0
        assert quad(inside, 0.0, angle=60.0) is True
        assert quad(outside, 0.0, angle=60.0) is False

    def test_reverse_direction_is_the_same_zone_rotated_180_degrees(self):
        # In a reverse zone the positive-r' side lies at negative R; zero left reach
        # still means "no coverage beyond r' = 0 in the zone's own frame".
        for r in (-5.0, -2.0, -0.5, 0.0, 0.5, 2.0, 5.0):
            fwd = quad(pt(r, 5.0), 0.0, DIRECTION_FORWARD)
            rev = quad(pt(-r, -5.0), 0.0, DIRECTION_REVERSE)
            assert fwd == rev, r
        assert quad(pt(-2.0, -5.0), 0.0, DIRECTION_REVERSE) is True
        assert quad(pt(2.0, -5.0), 0.0, DIRECTION_REVERSE) is False
        assert state(pt(-2.0, -5.0), 0.0, direction=DIRECTION_REVERSE) == ZONE_STATE_OPERATED


# --- review overlay -> adapter -> engine ----------------------------------


def _inside_outside(zone: ZoneSettings):
    theta = math.radians(zone.characteristic_angle_deg)
    x_, rf = zone.reactive_reach_ohm / 2.0, zone.resistive_reach_forward_ohm

    def at(r_prime):
        return pt(x_ * math.cos(theta) + r_prime * math.sin(theta), x_ * math.sin(theta) - r_prime * math.cos(theta))

    return at(rf / 2.0), at(-0.5)


@pytest.fixture(scope="module")
def model():
    return MicomP441Profile().interpret(make_doc())


def _adapt(model, **decisions):
    effective = apply_review(model, ReviewDecisions(**decisions))
    return effective, engine_adaptation(effective)


def _suggested():
    return frozenset(REVERSE.format(z) for z in ("Z1", "Z2", "Z3"))


class TestReviewToEngine:
    def test_an_accepted_suggestion_is_supported_and_the_engine_operates(self, model):
        effective, adaptation = _adapt(model, suggested=_suggested(), manual={ZP_STATUS: "disabled"})
        assert adaptation.supported
        zone = adaptation.zones[0]
        assert zone.resistive_reach_reverse_ohm == 0.0
        inside, outside = _inside_outside(zone)
        kw = dict(characteristic=adaptation.characteristic)
        assert evaluate_zone_state(inside, zone=replace(zone, delay_s=0.0), **kw) == ZONE_STATE_OPERATED
        assert evaluate_zone_state(outside, zone=replace(zone, delay_s=0.0), **kw) == ZONE_STATE_NOT_OPERATED

    def test_a_missing_left_reach_is_not_supported_and_clearing_restores_that(self, model):
        _, adaptation = _adapt(model, manual={ZP_STATUS: "disabled"})
        assert not adaptation.supported

    def test_typed_zero_is_geometrically_equal_but_keeps_its_own_provenance(self, model):
        paths = [REVERSE.format(z) for z in ("Z1", "Z2", "Z3")]
        e_sug, a_sug = _adapt(model, suggested=_suggested(), manual={ZP_STATUS: "disabled"})
        e_man, a_man = _adapt(model, manual={p: 0 for p in paths} | {ZP_STATUS: "disabled"})
        assert a_sug.supported and a_man.supported
        assert a_sug.zones == a_man.zones  # identical engine input
        inside, outside = _inside_outside(a_man.zones[0])
        for p in (inside, outside):
            assert state_of(a_sug, p) == state_of(a_man, p)
        suggested = dict(e_sug.iter_sourced())[paths[0]].provenance.review.status
        typed = dict(e_man.iter_sourced())[paths[0]].provenance.review.status
        assert suggested is ReviewStatus.SUGGESTION_ACCEPTED and typed is ReviewStatus.RESOLVED_MANUALLY


def state_of(adaptation, point):
    zone = replace(adaptation.zones[0], delay_s=0.0)
    return evaluate_zone_state(point, characteristic=adaptation.characteristic, zone=zone)
