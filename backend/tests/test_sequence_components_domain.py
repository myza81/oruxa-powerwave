"""Domain-level tests for Sequence Components v1
(`app.domain.sequence_components`) -- golden balanced/zero/negative
symmetrical-component results, mixed/unbalanced input, angle
normalization, and the sequence-ratio numerical-validity guardrail. See
docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md.
"""

from __future__ import annotations

import cmath
import math

import pytest

from app.domain.sequence_components import (
    MIN_POSITIVE_SEQUENCE_MAGNITUDE,
    compute_symmetrical_components,
    sequence_ratio_percent,
)

_TOL = 1e-6


class TestGoldenBalancedPositiveSequence:
    """Task's own core regression (section 3): a balanced three-phase set
    Va=100/0, Vb=100/-120, Vc=100/120 must produce V1~=100/0, V2~=0,
    V0~=0 -- proves the chosen phase-sequence convention (a=exp(j120deg),
    X1 = (Xa+a*Xb+a^2*Xc)/3) against the standard textbook definition,
    never an accidentally-swapped V1/V2."""

    def test_voltage(self):
        result = compute_symmetrical_components(100.0, 0.0, 100.0, -120.0, 100.0, 120.0)
        assert result.positive_magnitude == pytest.approx(100.0, abs=_TOL)
        assert result.positive_angle_deg == pytest.approx(0.0, abs=_TOL)
        assert result.negative_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.zero_magnitude == pytest.approx(0.0, abs=_TOL)

    def test_current_equivalent(self):
        """Task's own section 3 "add equivalent current test" -- the
        transform itself is quantity-agnostic (pure magnitude/angle
        math), so a balanced current set proves the identical property."""
        result = compute_symmetrical_components(40.0, 0.0, 40.0, -120.0, 40.0, 120.0)
        assert result.positive_magnitude == pytest.approx(40.0, abs=_TOL)
        assert result.positive_angle_deg == pytest.approx(0.0, abs=_TOL)
        assert result.negative_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.zero_magnitude == pytest.approx(0.0, abs=_TOL)

    def test_not_off_by_a_rotation(self):
        """A common implementation bug is reporting V1 at the wrong
        angle (e.g. off by the rotation operator itself) -- pins the
        exact angle, not just "close to something small.\""""
        result = compute_symmetrical_components(100.0, 10.0, 100.0, -110.0, 100.0, 130.0)
        assert result.positive_magnitude == pytest.approx(100.0, abs=_TOL)
        assert result.positive_angle_deg == pytest.approx(10.0, abs=_TOL)


class TestGoldenPureZeroSequence:
    """Task's own section 4: Va=Vb=Vc=100/0 -> V0=100/0, V1~=0, V2~=0."""

    def test_voltage(self):
        result = compute_symmetrical_components(100.0, 0.0, 100.0, 0.0, 100.0, 0.0)
        assert result.zero_magnitude == pytest.approx(100.0, abs=_TOL)
        assert result.zero_angle_deg == pytest.approx(0.0, abs=_TOL)
        assert result.positive_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.negative_magnitude == pytest.approx(0.0, abs=_TOL)

    def test_current(self):
        result = compute_symmetrical_components(15.0, 45.0, 15.0, 45.0, 15.0, 45.0)
        assert result.zero_magnitude == pytest.approx(15.0, abs=_TOL)
        assert result.zero_angle_deg == pytest.approx(45.0, abs=_TOL)
        assert result.positive_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.negative_magnitude == pytest.approx(0.0, abs=_TOL)


class TestGoldenPureNegativeSequence:
    """Task's own section 4: a valid REVERSE (B/C-swapped) sequence set
    must produce a dominant V2, with V1~=0 and V0~=0."""

    def test_voltage(self):
        # Reverse rotation: Va=100/0, Vb=100/+120, Vc=100/-120 (B and C
        # swapped relative to the golden positive-sequence set above).
        result = compute_symmetrical_components(100.0, 0.0, 100.0, 120.0, 100.0, -120.0)
        assert result.negative_magnitude == pytest.approx(100.0, abs=_TOL)
        assert result.negative_angle_deg == pytest.approx(0.0, abs=_TOL)
        assert result.positive_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.zero_magnitude == pytest.approx(0.0, abs=_TOL)

    def test_current(self):
        result = compute_symmetrical_components(20.0, 0.0, 20.0, 120.0, 20.0, -120.0)
        assert result.negative_magnitude == pytest.approx(20.0, abs=_TOL)
        assert result.negative_angle_deg == pytest.approx(0.0, abs=_TOL)
        assert result.positive_magnitude == pytest.approx(0.0, abs=_TOL)
        assert result.zero_magnitude == pytest.approx(0.0, abs=_TOL)


class TestMixedUnbalancedInput:
    """A genuinely unbalanced set must produce non-trivial V0/V1/V2 --
    verified against an independently hand-summed reference (never a
    value re-derived from this same implementation)."""

    def test_reference_conservation_identity(self):
        """Xa = X0 + X1 + X2 always holds exactly (Fortescue's own
        inverse-transform identity) -- an implementation-independent
        sanity check on any input, balanced or not."""
        ma, aa = 100.0, 5.0
        mb, ab = 80.0, -130.0
        mc, ac = 60.0, 118.0
        result = compute_symmetrical_components(ma, aa, mb, ab, mc, ac)
        xa = cmath.rect(ma, math.radians(aa))
        x0 = cmath.rect(result.zero_magnitude, math.radians(result.zero_angle_deg))
        x1 = cmath.rect(result.positive_magnitude, math.radians(result.positive_angle_deg))
        x2 = cmath.rect(result.negative_magnitude, math.radians(result.negative_angle_deg))
        reconstructed_a = x0 + x1 + x2
        assert reconstructed_a.real == pytest.approx(xa.real, abs=1e-6)
        assert reconstructed_a.imag == pytest.approx(xa.imag, abs=1e-6)

    def test_hand_derived_example(self):
        """Va=100/0, Vb=90/-100, Vc=95/130 -- independently hand-summed
        via `a=exp(j120deg)` outside this module (never copy-pasted from
        the implementation itself). Closure-pass hardening (task's own
        section 19 "do not rely only on magnitude"): asserts real,
        imaginary, magnitude, AND angle for all three components, not
        magnitude alone -- a transform that got the ROTATION DIRECTION
        or a sign wrong could still coincidentally match on magnitude."""
        a = complex(math.cos(math.radians(120.0)), math.sin(math.radians(120.0)))
        a2 = a * a
        xa = cmath.rect(100.0, math.radians(0.0))
        xb = cmath.rect(90.0, math.radians(-100.0))
        xc = cmath.rect(95.0, math.radians(130.0))
        expected_x0 = (xa + xb + xc) / 3.0
        expected_x1 = (xa + a * xb + a2 * xc) / 3.0
        expected_x2 = (xa + a2 * xb + a * xc) / 3.0

        result = compute_symmetrical_components(100.0, 0.0, 90.0, -100.0, 95.0, 130.0)
        for result_mag, result_ang, expected in (
            (result.zero_magnitude, result.zero_angle_deg, expected_x0),
            (result.positive_magnitude, result.positive_angle_deg, expected_x1),
            (result.negative_magnitude, result.negative_angle_deg, expected_x2),
        ):
            assert result_mag == pytest.approx(abs(expected), abs=1e-6)
            actual = cmath.rect(result_mag, math.radians(result_ang))
            assert actual.real == pytest.approx(expected.real, abs=1e-6)
            assert actual.imag == pytest.approx(expected.imag, abs=1e-6)

    def test_hand_derived_example_current(self):
        """Task's own section 19 "test both Voltage and Current" for the
        unbalanced/mixed case, not just the three pure golden cases --
        Ia=40/15, Ib=32/-95, Ic=45/160, independently hand-summed
        exactly like the Voltage case above."""
        a = complex(math.cos(math.radians(120.0)), math.sin(math.radians(120.0)))
        a2 = a * a
        xa = cmath.rect(40.0, math.radians(15.0))
        xb = cmath.rect(32.0, math.radians(-95.0))
        xc = cmath.rect(45.0, math.radians(160.0))
        expected_x0 = (xa + xb + xc) / 3.0
        expected_x1 = (xa + a * xb + a2 * xc) / 3.0
        expected_x2 = (xa + a2 * xb + a * xc) / 3.0

        result = compute_symmetrical_components(40.0, 15.0, 32.0, -95.0, 45.0, 160.0)
        for result_mag, result_ang, expected in (
            (result.zero_magnitude, result.zero_angle_deg, expected_x0),
            (result.positive_magnitude, result.positive_angle_deg, expected_x1),
            (result.negative_magnitude, result.negative_angle_deg, expected_x2),
        ):
            assert result_mag == pytest.approx(abs(expected), abs=1e-6)
            actual = cmath.rect(result_mag, math.radians(result_ang))
            assert actual.real == pytest.approx(expected.real, abs=1e-6)
            assert actual.imag == pytest.approx(expected.imag, abs=1e-6)


class TestAngleNormalization:
    """Uses the same `(-180, 180]` convention as Phasor -- never a
    separate normalization for Sequence Components (task's own section
    17)."""

    def test_output_angles_within_normalized_range(self):
        result = compute_symmetrical_components(100.0, 179.0, 100.0, -170.0, 100.0, 200.0)
        for angle in (result.zero_angle_deg, result.positive_angle_deg, result.negative_angle_deg):
            assert -180.0 < angle <= 180.0

    def test_boundary_180_normalizes_to_180(self):
        result = compute_symmetrical_components(50.0, 180.0, 50.0, 180.0, 50.0, 180.0)
        # Pure zero sequence at exactly 180 degrees.
        assert result.zero_angle_deg == pytest.approx(180.0, abs=_TOL)


class TestSequenceRatioGuardrail:
    """Task's own section 18: |X2|/|X1| and |X0|/|X1| must never divide
    blindly -- a near-zero positive sequence reports an explicit
    unavailable (`None`) ratio, never Infinity/NaN. Purely a numerical
    guard, never a protection threshold."""

    def test_normal_ratio(self):
        assert sequence_ratio_percent(5.0, 100.0) == pytest.approx(5.0, abs=_TOL)

    def test_zero_positive_sequence_returns_none(self):
        assert sequence_ratio_percent(5.0, 0.0) is None

    def test_below_floor_returns_none(self):
        assert sequence_ratio_percent(5.0, MIN_POSITIVE_SEQUENCE_MAGNITUDE / 2.0) is None

    def test_at_floor_is_accepted(self):
        assert sequence_ratio_percent(5.0, MIN_POSITIVE_SEQUENCE_MAGNITUDE) is not None

    def test_never_returns_nan_or_inf(self):
        result = sequence_ratio_percent(5.0, 0.0)
        assert result is None  # never float("nan") or float("inf")

    def test_zero_numerator_is_a_valid_zero_ratio(self):
        # A magnitude of exactly zero (e.g. a perfectly balanced set) is
        # a valid, meaningful 0% ratio -- not itself a guardrail case.
        assert sequence_ratio_percent(0.0, 100.0) == pytest.approx(0.0, abs=_TOL)

    def test_negative_or_nan_denominator_returns_none(self):
        assert sequence_ratio_percent(5.0, float("nan")) is None
