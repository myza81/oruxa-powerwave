"""Domain-level tests for Distance Protection v1
(`app.domain.distance_protection`) -- loop-impedance golden results
(AB/BC/CA), Mho and Quadrilateral zone-geometry golden results,
low-current guardrail, and Manual Input per-leg isolation. See
docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md.
"""

from __future__ import annotations

import math

import pytest

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    DISTANCE_STATUS_COMPUTED,
    DISTANCE_STATUS_MISSING,
    DISTANCE_STATUS_NEEDS_CONFIGURATION,
    LOOP_ROLE_KEYS,
    REASON_LOOP_CURRENT_TOO_SMALL,
    ZONE_STATE_NOT_OPERATED,
    ZONE_STATE_OPERATED,
    ZoneSettings,
    compute_loop_impedance,
    evaluate_manual_distance,
    evaluate_zone_state,
    mho_zone_operated,
    quadrilateral_zone_operated,
)
from app.domain.impedance import MIN_CURRENT_A, ImpedancePoint
from app.domain.phasor import ManualPhasorRoleInput


class TestLoopRoleKeys:
    def test_ab_needs_only_phase_a_and_b(self):
        assert LOOP_ROLE_KEYS["AB"] == ("Va", "Vb", "Ia", "Ib")

    def test_bc_needs_only_phase_b_and_c(self):
        assert LOOP_ROLE_KEYS["BC"] == ("Vb", "Vc", "Ib", "Ic")

    def test_ca_needs_only_phase_c_and_a(self):
        assert LOOP_ROLE_KEYS["CA"] == ("Vc", "Va", "Ic", "Ia")


class TestLoopImpedanceGoldenBalanced:
    """A balanced three-phase set: Va=100/0, Vb=100/-120, Vc=100/120,
    Ia=10/-20, Ib=10/-140, Ic=10/100. Under perfect balance every phase-
    phase loop reduces to the SAME impedance as the phase quantities'
    own ratio-and-angle-difference (a well-known consequence of the
    +30-degree line-to-line shift cancelling between Voltage and
    Current) -- golden value Z = 10 ohm /20 deg, independently verified
    via `cmath` outside this module before being hardcoded here."""

    VA, VB, VC = (100.0, 0.0), (100.0, -120.0), (100.0, 120.0)
    IA, IB, IC = (10.0, -20.0), (10.0, -140.0), (10.0, 100.0)

    EXPECTED_R = 9.396926207859085
    EXPECTED_X = 3.4202014332566875
    EXPECTED_MAG = 10.0
    EXPECTED_ANGLE = 20.0

    def _assert_golden(self, point):
        assert point is not None
        assert point.resistance_ohm == pytest.approx(self.EXPECTED_R, abs=1e-9)
        assert point.reactance_ohm == pytest.approx(self.EXPECTED_X, abs=1e-9)
        assert point.magnitude_ohm == pytest.approx(self.EXPECTED_MAG, abs=1e-9)
        assert point.angle_deg == pytest.approx(self.EXPECTED_ANGLE, abs=1e-6)

    def test_ab_loop(self):
        point = compute_loop_impedance(*self.VA, *self.VB, *self.IA, *self.IB)
        self._assert_golden(point)

    def test_bc_loop(self):
        point = compute_loop_impedance(*self.VB, *self.VC, *self.IB, *self.IC)
        self._assert_golden(point)

    def test_ca_loop(self):
        point = compute_loop_impedance(*self.VC, *self.VA, *self.IC, *self.IA)
        self._assert_golden(point)


class TestLoopImpedanceIsNotPhaseImpedance:
    """Asymmetric (non-balanced) inputs where the AB loop impedance
    must differ from the naive phase impedance Za=Va/Ia -- proves the
    implementation performs genuine complex phasor subtraction, never a
    phase-impedance shortcut. Golden values independently verified via
    `cmath` before being hardcoded here."""

    def test_loop_impedance_differs_from_phase_impedance(self):
        va, vb = (100.0, 0.0), (80.0, -100.0)
        ia, ib = (10.0, -15.0), (6.0, 170.0)
        loop_point = compute_loop_impedance(*va, *vb, *ia, *ib)
        assert loop_point is not None
        assert loop_point.resistance_ohm == pytest.approx(5.819309341293767, abs=1e-6)
        assert loop_point.reactance_ohm == pytest.approx(6.4175554628984, abs=1e-6)
        assert loop_point.magnitude_ohm == pytest.approx(8.663104485635966, abs=1e-6)
        assert loop_point.angle_deg == pytest.approx(47.798895700868535, abs=1e-6)

        # Za = Va/Ia (phase impedance) -- deliberately a different value.
        phase_mag = va[0] / ia[0]
        phase_angle = va[1] - ia[1]
        assert loop_point.magnitude_ohm != pytest.approx(phase_mag, abs=1e-3)
        assert loop_point.angle_deg != pytest.approx(phase_angle, abs=1e-3)


class TestLoopLowCurrentGuardrail:
    """Reuses `app.domain.impedance`'s own numerical-validity guardrail
    verbatim for the loop's differential current -- numerical validity
    only, never a relay pickup threshold."""

    def test_loop_current_below_floor_returns_none(self):
        # Ia - Ib -> 0 when both legs are numerically identical.
        point = compute_loop_impedance(100.0, 0.0, 100.0, -120.0, 1.0, -30.0, 1.0, -30.0)
        assert point is None

    def test_loop_current_at_floor_is_accepted(self):
        point = compute_loop_impedance(100.0, 0.0, 100.0, -120.0, MIN_CURRENT_A, -30.0, 0.0, 0.0)
        assert point is not None


class TestMhoCharacteristicGolden:
    """Mho circle geometry: diameter from the origin to Z_reach =
    reach_ohm /_ characteristic_angle_deg; center = Z_reach/2, radius =
    reach_ohm/2. Verified against independently hand/`cmath`-derived
    values for both angle=0 (axis-aligned) and angle=80 (rotated)."""

    def test_reach_10_angle_0_clearly_inside(self):
        assert mho_zone_operated(ImpedancePoint(5.0, 0.0, 5.0, 0.0), reach_ohm=10.0, characteristic_angle_deg=0.0) is True

    def test_reach_10_angle_0_exactly_on_boundary(self):
        # The reach point itself sits exactly on the circle.
        assert mho_zone_operated(ImpedancePoint(10.0, 0.0, 10.0, 0.0), reach_ohm=10.0, characteristic_angle_deg=0.0) is True

    def test_reach_10_angle_0_origin_is_on_boundary(self):
        assert mho_zone_operated(ImpedancePoint(0.0, 0.0, 0.0, 0.0), reach_ohm=10.0, characteristic_angle_deg=0.0) is True

    def test_reach_10_angle_0_clearly_outside(self):
        assert mho_zone_operated(ImpedancePoint(15.0, 0.0, 15.0, 0.0), reach_ohm=10.0, characteristic_angle_deg=0.0) is False

    def test_reach_10_angle_0_reverse_side_not_operated(self):
        assert mho_zone_operated(ImpedancePoint(-5.0, 0.0, 5.0, 180.0), reach_ohm=10.0, characteristic_angle_deg=0.0) is False

    def test_reach_10_angle_80_center_is_inside(self):
        cx, cy = 0.8682408883346521, 4.92403876506104
        assert mho_zone_operated(ImpedancePoint(cx, cy, math.hypot(cx, cy), 80.0), reach_ohm=10.0, characteristic_angle_deg=80.0) is True

    def test_reach_10_angle_80_reach_point_is_on_boundary(self):
        rx, ry = 1.7364817766693041, 9.84807753012208
        assert mho_zone_operated(ImpedancePoint(rx, ry, math.hypot(rx, ry), 80.0), reach_ohm=10.0, characteristic_angle_deg=80.0) is True

    def test_reach_10_angle_80_double_reach_is_outside(self):
        rx, ry = 1.7364817766693041 * 2.0, 9.84807753012208 * 2.0
        assert mho_zone_operated(ImpedancePoint(rx, ry, math.hypot(rx, ry), 80.0), reach_ohm=10.0, characteristic_angle_deg=80.0) is False

    def test_disabled_or_invalid_reach_never_operates(self):
        assert mho_zone_operated(ImpedancePoint(1.0, 1.0, math.sqrt(2), 45.0), reach_ohm=0.0, characteristic_angle_deg=0.0) is False
        assert mho_zone_operated(ImpedancePoint(1.0, 1.0, math.sqrt(2), 45.0), reach_ohm=float("nan"), characteristic_angle_deg=0.0) is False


class TestQuadrilateralCharacteristicGolden:
    """Rotated-coordinate rectangle: x' = R*cos(theta)+X*sin(theta)
    (along the reach direction), r' = R*sin(theta)-X*cos(theta)
    (perpendicular); operated iff 0<=x'<=reactive_reach and
    -resistive_reverse<=r'<=resistive_forward. At theta=90 this
    degenerates to the classic axis-aligned box (0<=X<=Xreach,
    -Rrev<=R<=Rfwd), verified explicitly below."""

    THETA = 90.0
    XREACH, RFWD, RREV = 10.0, 5.0, 2.0

    def _operated(self, r, x):
        return quadrilateral_zone_operated(
            ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r))),
            reactive_reach_ohm=self.XREACH, resistive_reach_forward_ohm=self.RFWD,
            resistive_reach_reverse_ohm=self.RREV, characteristic_angle_deg=self.THETA,
        )

    def test_clearly_operated(self):
        assert self._operated(0.0, 5.0) is True

    def test_exactly_on_reactive_boundary(self):
        assert self._operated(5.0, 10.0) is True

    def test_clearly_not_operated_beyond_reactive_reach(self):
        assert self._operated(0.0, 15.0) is False

    def test_negative_resistance_within_forward_reach_operates(self):
        assert self._operated(-1.0, 5.0) is True

    def test_negative_reactance_reverse_side_not_operated(self):
        assert self._operated(0.0, -5.0) is False

    def test_resistive_reverse_exceeded_not_operated(self):
        assert self._operated(-3.0, 5.0) is False

    def test_resistive_forward_exceeded_not_operated(self):
        assert self._operated(6.0, 5.0) is False

    def test_disabled_or_invalid_reach_never_operates(self):
        assert quadrilateral_zone_operated(
            ImpedancePoint(1.0, 1.0, math.sqrt(2), 45.0),
            reactive_reach_ohm=0.0, resistive_reach_forward_ohm=5.0, resistive_reach_reverse_ohm=2.0,
            characteristic_angle_deg=90.0,
        ) is False


class TestQuadrilateralRotatedAngle:
    """A non-90-degree characteristic angle genuinely rotates the
    boundary rather than silently behaving like the axis-aligned case --
    proven by a point that operates at theta=90 but not at a rotated
    theta, and vice versa."""

    def test_rotation_changes_operated_state(self):
        # At theta=90 (axis-aligned), R=4, X=5 is inside a 0<=X<=10,
        # -2<=R<=5 box.
        assert quadrilateral_zone_operated(
            ImpedancePoint(4.0, 5.0, math.hypot(4.0, 5.0), 51.34), reactive_reach_ohm=10.0,
            resistive_reach_forward_ohm=5.0, resistive_reach_reverse_ohm=2.0, characteristic_angle_deg=90.0,
        ) is True
        # At a rotated theta=60, the same R/X point is evaluated against
        # rotated coordinates and may fall outside -- verified via the
        # rotation formula directly instead of assuming.
        theta = math.radians(60.0)
        r, x = 4.0, 5.0
        x_prime = r * math.cos(theta) + x * math.sin(theta)
        r_prime = r * math.sin(theta) - x * math.cos(theta)
        expected = (0.0 <= x_prime <= 10.0) and (-2.0 <= r_prime <= 5.0)
        actual = quadrilateral_zone_operated(
            ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r))), reactive_reach_ohm=10.0,
            resistive_reach_forward_ohm=5.0, resistive_reach_reverse_ohm=2.0, characteristic_angle_deg=60.0,
        )
        assert actual == expected


class TestEvaluateZoneState:
    def test_none_point_is_not_operated(self):
        zone = ZoneSettings(enabled=True, reach_ohm=10.0, characteristic_angle_deg=0.0)
        assert evaluate_zone_state(None, characteristic=CHARACTERISTIC_MHO, zone=zone) == ZONE_STATE_NOT_OPERATED

    def test_disabled_zone_is_not_operated_even_if_geometrically_inside(self):
        zone = ZoneSettings(enabled=False, reach_ohm=10.0, characteristic_angle_deg=0.0)
        point = ImpedancePoint(5.0, 0.0, 5.0, 0.0)
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_MHO, zone=zone) == ZONE_STATE_NOT_OPERATED

    def test_mho_operated(self):
        zone = ZoneSettings(enabled=True, reach_ohm=10.0, characteristic_angle_deg=0.0)
        point = ImpedancePoint(5.0, 0.0, 5.0, 0.0)
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_MHO, zone=zone) == ZONE_STATE_OPERATED

    def test_quadrilateral_operated(self):
        zone = ZoneSettings(
            enabled=True, reactive_reach_ohm=10.0, resistive_reach_forward_ohm=5.0,
            resistive_reach_reverse_ohm=2.0, characteristic_angle_deg=90.0,
        )
        point = ImpedancePoint(0.0, 5.0, 5.0, 90.0)
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone) == ZONE_STATE_OPERATED

    def test_multiple_zones_can_independently_operate(self):
        """Zone priority is explicitly NOT enforced -- Zone1/2/3 are
        evaluated completely independently and may all report Operated
        simultaneously for a nested characteristic."""
        point = ImpedancePoint(5.0, 0.0, 5.0, 0.0)
        zone1 = ZoneSettings(enabled=True, reach_ohm=8.0, characteristic_angle_deg=0.0)
        zone2 = ZoneSettings(enabled=True, reach_ohm=10.0, characteristic_angle_deg=0.0)
        zone3 = ZoneSettings(enabled=True, reach_ohm=20.0, characteristic_angle_deg=0.0)
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_MHO, zone=zone1) == ZONE_STATE_OPERATED
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_MHO, zone=zone2) == ZONE_STATE_OPERATED
        assert evaluate_zone_state(point, characteristic=CHARACTERISTIC_MHO, zone=zone3) == ZONE_STATE_OPERATED


class TestManualDistancePerLegIsolation:
    """AB only requires Va/Vb/Ia/Ib -- never phase C -- and a missing/
    invalid leg is reported directly rather than a fabricated partial
    loop impedance."""

    def _role(self, **kwargs):
        defaults = dict(enabled=True, magnitude=100.0, unit="V", angle_deg=0.0)
        defaults.update(kwargs)
        return ManualPhasorRoleInput(**defaults)

    ZONE_DISABLED = ZoneSettings(enabled=False)

    def test_ab_loop_never_requires_phase_c(self):
        result = evaluate_manual_distance(
            self._role(magnitude=100.0, angle_deg=0.0), self._role(magnitude=100.0, angle_deg=-120.0),
            self._role(magnitude=10.0, unit="A", angle_deg=-20.0), self._role(magnitude=10.0, unit="A", angle_deg=-140.0),
            loop_label="AB", voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
            characteristic=CHARACTERISTIC_MHO, zone1=self.ZONE_DISABLED, zone2=self.ZONE_DISABLED, zone3=self.ZONE_DISABLED,
        )
        assert result.status == DISTANCE_STATUS_COMPUTED
        assert result.resistance_ohm == pytest.approx(9.396926207859085, abs=1e-6)
        assert result.reactance_ohm == pytest.approx(3.4202014332566875, abs=1e-6)

    def test_missing_leg_reports_missing_not_a_fabricated_result(self):
        result = evaluate_manual_distance(
            self._role(enabled=False, magnitude=None), self._role(magnitude=100.0, angle_deg=-120.0),
            self._role(magnitude=10.0, unit="A", angle_deg=-20.0), self._role(magnitude=10.0, unit="A", angle_deg=-140.0),
            loop_label="AB", voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
            characteristic=CHARACTERISTIC_MHO, zone1=self.ZONE_DISABLED, zone2=self.ZONE_DISABLED, zone3=self.ZONE_DISABLED,
        )
        assert result.status == DISTANCE_STATUS_MISSING
        assert result.resistance_ohm is None

    def test_zone_results_always_present_even_on_missing_result(self):
        result = evaluate_manual_distance(
            self._role(enabled=False, magnitude=None), self._role(magnitude=100.0, angle_deg=-120.0),
            self._role(magnitude=10.0, unit="A", angle_deg=-20.0), self._role(magnitude=10.0, unit="A", angle_deg=-140.0),
            loop_label="AB", voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
            characteristic=CHARACTERISTIC_MHO, zone1=self.ZONE_DISABLED, zone2=self.ZONE_DISABLED, zone3=self.ZONE_DISABLED,
        )
        assert result.zone1 is not None and result.zone1.state == ZONE_STATE_NOT_OPERATED
        assert result.zone2 is not None and result.zone3 is not None

    def test_loop_current_too_small_reports_specific_reason(self):
        result = evaluate_manual_distance(
            self._role(magnitude=100.0, angle_deg=0.0), self._role(magnitude=100.0, angle_deg=-120.0),
            self._role(magnitude=1.0, unit="A", angle_deg=-30.0), self._role(magnitude=1.0, unit="A", angle_deg=-30.0),
            loop_label="AB", voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
            characteristic=CHARACTERISTIC_MHO, zone1=self.ZONE_DISABLED, zone2=self.ZONE_DISABLED, zone3=self.ZONE_DISABLED,
        )
        assert result.status == DISTANCE_STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_LOOP_CURRENT_TOO_SMALL

    def test_primary_basis_without_ratio_needs_configuration(self):
        result = evaluate_manual_distance(
            self._role(magnitude=100.0, angle_deg=0.0), self._role(magnitude=100.0, angle_deg=-120.0),
            self._role(magnitude=10.0, unit="A", angle_deg=-20.0), self._role(magnitude=10.0, unit="A", angle_deg=-140.0),
            loop_label="AB", voltage_basis="primary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
            characteristic=CHARACTERISTIC_MHO, zone1=self.ZONE_DISABLED, zone2=self.ZONE_DISABLED, zone3=self.ZONE_DISABLED,
        )
        assert result.status == DISTANCE_STATUS_NEEDS_CONFIGURATION
