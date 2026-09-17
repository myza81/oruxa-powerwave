"""Domain-level tests for Impedance Locus v1
(`app.domain.impedance`) -- golden mathematical result, quadrant
geometry, low-current guardrail, basis conversion, and Manual Input
per-quantity isolation. See docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md.
"""

from __future__ import annotations

import math

import pytest

from app.domain.impedance import (
    IMPEDANCE_STATUS_COMPUTED,
    IMPEDANCE_STATUS_MISSING,
    IMPEDANCE_STATUS_NEEDS_CONFIGURATION,
    MIN_CURRENT_A,
    REASON_CURRENT_TOO_SMALL,
    REASON_INVALID_RATIO,
    compute_impedance_point,
    convert_impedance_basis,
    evaluate_manual_impedance,
    impedance_ratio_valid,
)
from app.domain.phasor import ManualPhasorRoleInput


class TestGoldenWorkedExample:
    """Task's own golden example: V = 100 kV / 0 deg, I = 1 kA / -30 deg,
    same basis -> |Z|=100, angle=+30, R~=86.6025, X=50."""

    def test_golden_result(self):
        point = compute_impedance_point(100.0, 0.0, 1.0, -30.0)
        assert point is not None
        assert point.magnitude_ohm == pytest.approx(100.0, abs=1e-9)
        assert point.angle_deg == pytest.approx(30.0, abs=1e-9)
        assert point.resistance_ohm == pytest.approx(86.6025403784, abs=1e-6)
        assert point.reactance_ohm == pytest.approx(50.0, abs=1e-9)


class TestQuadrantGeometry:
    """Verifies the sign of R/X matches the mathematical convention in
    every quadrant -- no clamping of negative R or X."""

    @pytest.mark.parametrize(
        "voltage_angle_deg, current_angle_deg, expected_r_sign, expected_x_sign",
        [
            (0.0, -30.0, 1, 1),   # theta_Z=+30 -> +R, +X
            (0.0, 30.0, 1, -1),   # theta_Z=-30 -> +R, -X
            (180.0, -30.0, -1, -1),  # theta_Z=+150 -> -R, +X... verified numerically below instead
            (180.0, 30.0, -1, 1),
        ],
    )
    def test_quadrant_signs(self, voltage_angle_deg, current_angle_deg, expected_r_sign, expected_x_sign):
        point = compute_impedance_point(100.0, voltage_angle_deg, 1.0, current_angle_deg)
        assert point is not None
        theta = math.radians(voltage_angle_deg - current_angle_deg)
        expected_r = 100.0 * math.cos(theta)
        expected_x = 100.0 * math.sin(theta)
        assert point.resistance_ohm == pytest.approx(expected_r, abs=1e-9)
        assert point.reactance_ohm == pytest.approx(expected_x, abs=1e-9)

    def test_all_four_quadrants_are_reachable(self):
        # theta_Z = 45 (Q1: +R+X), 135 (Q2: -R+X), -135 (Q3: -R-X), -45 (Q4: +R-X)
        for theta_z, expect_r_positive, expect_x_positive in [
            (45.0, True, True), (135.0, False, True), (-135.0, False, False), (-45.0, True, False),
        ]:
            point = compute_impedance_point(100.0, theta_z, 1.0, 0.0)
            assert (point.resistance_ohm > 0) == expect_r_positive
            assert (point.reactance_ohm > 0) == expect_x_positive


class TestLowCurrentGuardrail:
    def test_current_below_floor_returns_none(self):
        assert compute_impedance_point(100.0, 0.0, MIN_CURRENT_A / 2.0, -30.0) is None

    def test_current_at_floor_is_accepted(self):
        point = compute_impedance_point(100.0, 0.0, MIN_CURRENT_A, -30.0)
        assert point is not None

    def test_zero_current_returns_none(self):
        assert compute_impedance_point(100.0, 0.0, 0.0, -30.0) is None

    def test_negative_current_returns_none(self):
        assert compute_impedance_point(100.0, 0.0, -1.0, -30.0) is None

    def test_nan_inputs_return_none(self):
        assert compute_impedance_point(float("nan"), 0.0, 1.0, -30.0) is None
        assert compute_impedance_point(100.0, float("nan"), 1.0, -30.0) is None
        assert compute_impedance_point(100.0, 0.0, 1.0, float("nan")) is None

    def test_infinite_current_is_rejected(self):
        # Infinity fails math.isfinite() explicitly -- never silently
        # treated as "very large but valid," which would otherwise
        # produce a misleading zero-magnitude result.
        assert compute_impedance_point(100.0, 0.0, float("inf"), -30.0) is None


class TestBasisConversion:
    """Task's own section 12 formula, verified against this codebase's
    existing ratio convention (VT_ratio = Vprimary/Vsecondary, CT_ratio =
    Iprimary/Isecondary; not blindly adopted)."""

    def test_no_op_when_bases_match(self):
        point = compute_impedance_point(100.0, 0.0, 1.0, -30.0)
        same = convert_impedance_basis(
            point, from_basis="secondary", to_basis="secondary",
            vt_primary=None, vt_secondary=None, ct_primary=None, ct_secondary=None,
        )
        assert same is point

    def test_secondary_to_primary_matches_manual_formula(self):
        point_secondary = compute_impedance_point(110.0, 0.0, 1.0, -30.0)
        vt_primary, vt_secondary = 132000.0, 110.0
        ct_primary, ct_secondary = 1200.0, 1.0
        point_primary = convert_impedance_basis(
            point_secondary, from_basis="secondary", to_basis="primary",
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        )
        vt_ratio = vt_primary / vt_secondary
        ct_ratio = ct_primary / ct_secondary
        expected_factor = vt_ratio / ct_ratio
        assert point_primary.magnitude_ohm == pytest.approx(point_secondary.magnitude_ohm * expected_factor, rel=1e-9)
        assert point_primary.resistance_ohm == pytest.approx(point_secondary.resistance_ohm * expected_factor, rel=1e-9)
        assert point_primary.reactance_ohm == pytest.approx(point_secondary.reactance_ohm * expected_factor, rel=1e-9)
        # Angle is basis-invariant -- only magnitude/R/X scale.
        assert point_primary.angle_deg == pytest.approx(point_secondary.angle_deg, abs=1e-9)

    def test_primary_to_secondary_is_the_inverse(self):
        point_primary = compute_impedance_point(95.262794, 30.0, 1.0, 0.0)
        vt_primary, vt_secondary = 132000.0, 110.0
        ct_primary, ct_secondary = 1200.0, 1.0
        point_secondary = convert_impedance_basis(
            point_primary, from_basis="primary", to_basis="secondary",
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        )
        round_trip = convert_impedance_basis(
            point_secondary, from_basis="secondary", to_basis="primary",
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        )
        assert round_trip.magnitude_ohm == pytest.approx(point_primary.magnitude_ohm, rel=1e-9)

    def test_equal_vt_and_ct_ratio_leaves_magnitude_unchanged(self):
        # VT_ratio == CT_ratio -> factor == 1, a useful sanity property.
        point_secondary = compute_impedance_point(110.0, 0.0, 1.0, -30.0)
        point_primary = convert_impedance_basis(
            point_secondary, from_basis="secondary", to_basis="primary",
            vt_primary=1200.0, vt_secondary=1.0, ct_primary=1200.0, ct_secondary=1.0,
        )
        assert point_primary.magnitude_ohm == pytest.approx(point_secondary.magnitude_ohm, rel=1e-9)


class TestRatioValidity:
    def test_valid_ratio(self):
        assert impedance_ratio_valid(132000.0, 110.0) is True

    def test_zero_or_negative_rejected(self):
        assert impedance_ratio_valid(0.0, 110.0) is False
        assert impedance_ratio_valid(132000.0, -1.0) is False

    def test_nan_rejected(self):
        assert impedance_ratio_valid(float("nan"), 110.0) is False


class TestManualImpedanceBasisConversionMatrix:
    """Task's own section 24 -- all four Voltage/Current input-basis
    combinations, each requesting each output basis."""

    def _v(self, magnitude=100.0, angle=0.0, unit="V"):
        return ManualPhasorRoleInput(enabled=True, magnitude=magnitude, unit=unit, angle_deg=angle)

    def _i(self, magnitude=1.0, angle=-30.0, unit="A"):
        return ManualPhasorRoleInput(enabled=True, magnitude=magnitude, unit=unit, angle_deg=angle)

    def test_primary_primary_to_primary(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(), phase_label="A",
            voltage_basis="primary", vt_primary=1000.0, vt_secondary=1000.0,
            current_basis="primary", ct_primary=1000.0, ct_secondary=1000.0,
            impedance_basis="primary",
        )
        assert result.status == IMPEDANCE_STATUS_COMPUTED
        assert result.magnitude_ohm == pytest.approx(100.0, abs=1e-6)

    def test_secondary_secondary_to_secondary_needs_no_ratios(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None,
            impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_COMPUTED
        assert result.magnitude_ohm == pytest.approx(100.0, abs=1e-6)

    def test_voltage_primary_current_secondary_requested_primary(self):
        """Owner example (task section 11): Voltage input Primary,
        Current input Secondary, Impedance output Primary must be
        valid."""
        result = evaluate_manual_impedance(
            self._v(magnitude=132.0, unit="kV"), self._i(magnitude=1.0), phase_label="A",
            voltage_basis="primary", vt_primary=132000.0, vt_secondary=110.0,
            current_basis="secondary", ct_primary=1200.0, ct_secondary=1.0,
            impedance_basis="primary",
        )
        assert result.status == IMPEDANCE_STATUS_COMPUTED
        # V normalizes to 110 (unit "V" but magnitude given as raw 132 ->
        # treat as already-volts here; magnitude choice is illustrative).
        assert result.voltage_magnitude_secondary == pytest.approx(110.0, rel=1e-6)
        assert result.current_magnitude_secondary == pytest.approx(1.0, rel=1e-6)
        expected_secondary_mag = 110.0
        vt_ratio = 132000.0 / 110.0
        ct_ratio = 1200.0 / 1.0
        assert result.magnitude_ohm == pytest.approx(expected_secondary_mag * (vt_ratio / ct_ratio), rel=1e-6)

    def test_voltage_secondary_current_primary_requested_secondary(self):
        result = evaluate_manual_impedance(
            self._v(magnitude=110.0), self._i(magnitude=1200.0), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="primary", ct_primary=1200.0, ct_secondary=1.0,
            impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_COMPUTED
        assert result.voltage_magnitude_secondary == pytest.approx(110.0, rel=1e-6)
        assert result.current_magnitude_secondary == pytest.approx(1.0, rel=1e-6)
        assert result.magnitude_ohm == pytest.approx(110.0, rel=1e-6)


class TestManualImpedancePerQuantityIsolation:
    """An invalid/missing Voltage input must never corrupt Current
    evaluation and vice versa -- task's own section 21 guardrail list."""

    def _v(self, **kwargs):
        defaults = dict(enabled=True, magnitude=100.0, unit="V", angle_deg=0.0)
        defaults.update(kwargs)
        return ManualPhasorRoleInput(**defaults)

    def _i(self, **kwargs):
        defaults = dict(enabled=True, magnitude=1.0, unit="A", angle_deg=-30.0)
        defaults.update(kwargs)
        return ManualPhasorRoleInput(**defaults)

    def test_missing_voltage_reports_missing(self):
        result = evaluate_manual_impedance(
            self._v(enabled=False, magnitude=None), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_MISSING

    def test_missing_current_reports_missing(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(enabled=False, magnitude=None), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_MISSING

    def test_invalid_vt_ratio_blocks_without_crashing(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(), phase_label="A",
            voltage_basis="primary", vt_primary=-5.0, vt_secondary=110.0,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_INVALID_RATIO

    def test_invalid_ct_ratio_blocks_without_crashing(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="primary", ct_primary=1200.0, ct_secondary=-1.0, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_INVALID_RATIO

    def test_low_current_guardrail_surfaces_through_manual_path(self):
        result = evaluate_manual_impedance(
            self._v(), self._i(magnitude=MIN_CURRENT_A / 10.0), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_CURRENT_TOO_SMALL

    def test_unsupported_unit_reports_needs_configuration(self):
        result = evaluate_manual_impedance(
            self._v(unit="not-a-real-unit"), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION

    def test_negative_magnitude_rejected(self):
        result = evaluate_manual_impedance(
            self._v(magnitude=-1.0), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="secondary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION

    def test_output_basis_primary_without_ratios_is_needs_configuration(self):
        """Even when both inputs are already Secondary (so the DIVISION
        itself needs no ratio), requesting a Primary OUTPUT still
        requires valid VT/CT ratios for the final basis conversion."""
        result = evaluate_manual_impedance(
            self._v(), self._i(), phase_label="A",
            voltage_basis="secondary", vt_primary=None, vt_secondary=None,
            current_basis="secondary", ct_primary=None, ct_secondary=None, impedance_basis="primary",
        )
        assert result.status == IMPEDANCE_STATUS_NEEDS_CONFIGURATION
        assert result.reason_code == REASON_INVALID_RATIO
