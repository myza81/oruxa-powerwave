"""Golden tests for the Line-to-Line Voltage pure domain rules (DEC-115).

Expected values are derived independently here (explicit per-pair
subtraction written out by hand, and closed-form trigonometry), never by
calling the code under test a second time.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.calculated_channel import ALL_OPERATIONS
from app.domain.line_to_line_voltage import (
    OP_LINE_TO_LINE_VOLTAGE,
    OUTPUT_ALL_THREE,
    PAIR_OPERANDS,
    PAIR_ORDER,
    default_output_name,
    evaluate_line_to_line_instantaneous,
    output_valid,
    pairs_for_output,
    required_phases,
)

F0 = 50.0
FS = 5000.0
T = np.arange(0, 0.1, 1 / FS)


def _phase(mag, angle_deg):
    return mag * np.cos(2 * np.pi * F0 * T + np.radians(angle_deg))


def _pair(pair, va, vb, vc):
    by_phase = {"A": va, "B": vb, "C": vc}
    minuend, subtrahend = PAIR_OPERANDS[pair]
    return evaluate_line_to_line_instantaneous(by_phase[minuend], by_phase[subtrahend])


class TestFrozenConvention:
    def test_cyclic_pair_table(self):
        assert PAIR_OPERANDS == {"AB": ("A", "B"), "BC": ("B", "C"), "CA": ("C", "A")}
        assert PAIR_ORDER == ("AB", "BC", "CA")

    def test_vac_is_not_a_canonical_pair(self):
        assert "AC" not in PAIR_OPERANDS
        assert not output_valid("AC")

    def test_operation_is_not_a_generic_operation(self):
        """The generic create endpoint must never be able to build an L-L
        channel from two arbitrary inputs."""
        assert OP_LINE_TO_LINE_VOLTAGE not in ALL_OPERATIONS

    def test_outputs_and_required_phases(self):
        assert pairs_for_output("AB") == ("AB",)
        assert pairs_for_output(OUTPUT_ALL_THREE) == ("AB", "BC", "CA")
        assert required_phases("AB") == ("A", "B")
        assert required_phases("BC") == ("B", "C")
        assert required_phases("CA") == ("A", "C")
        assert required_phases(OUTPUT_ALL_THREE) == ("A", "B", "C")
        with pytest.raises(ValueError):
            pairs_for_output("XY")

    def test_bay_aware_default_names(self):
        assert [default_output_name("KPDN1", p) for p in PAIR_ORDER] == ["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA"]


class TestBalancedInstantaneous:
    def test_pointwise_subtraction_golden(self):
        va, vb, vc = _phase(100.0, 0), _phase(100.0, -120), _phase(100.0, 120)
        np.testing.assert_array_equal(_pair("AB", va, vb, vc), va - vb)
        np.testing.assert_array_equal(_pair("BC", va, vb, vc), vb - vc)
        np.testing.assert_array_equal(_pair("CA", va, vb, vc), vc - va)

    def test_balanced_result_is_sqrt3_times_phase_leading_30deg(self):
        """Closed form for a balanced ABC set: vab(t) = sqrt(3)*V*cos(wt+30)."""
        va, vb, vc = _phase(100.0, 0), _phase(100.0, -120), _phase(100.0, 120)
        np.testing.assert_allclose(_pair("AB", va, vb, vc), _phase(100.0 * math.sqrt(3), 30), atol=1e-9)
        np.testing.assert_allclose(_pair("BC", va, vb, vc), _phase(100.0 * math.sqrt(3), -90), atol=1e-9)
        np.testing.assert_allclose(_pair("CA", va, vb, vc), _phase(100.0 * math.sqrt(3), 150), atol=1e-9)


class TestUnbalancedDisturbance:
    def test_exact_pointwise_subtraction_not_sqrt3_scaling(self):
        """A-phase sag to 30 % with B shifted +15 deg: the true VAB is the
        exact difference, and differs materially from any sqrt(3)*VLN
        approximation of it."""
        va, vb, vc = _phase(30.0, 0), _phase(100.0, -105), _phase(100.0, 120)
        vab = _pair("AB", va, vb, vc)
        np.testing.assert_array_equal(vab, va - vb)
        # Closed-form magnitude of the true VAB phasor.
        true_peak = abs(30.0 * np.exp(0j) - 100.0 * np.exp(1j * math.radians(-105)))
        assert np.max(np.abs(vab)) == pytest.approx(true_peak, rel=2e-3)
        # sqrt(3) x |VA| (or |VB|) would be badly wrong in this disturbance.
        assert abs(np.max(np.abs(vab)) - math.sqrt(3) * 30.0) > 40.0
        assert abs(np.max(np.abs(vab)) - math.sqrt(3) * 100.0) > 40.0

    def test_arbitrary_samples(self):
        va = np.array([1.0, -2.5, 3.25, 0.0])
        vb = np.array([0.5, 4.0, -1.0, 7.0])
        vc = np.array([-3.0, 1.5, 2.0, -0.5])
        np.testing.assert_array_equal(_pair("AB", va, vb, vc), [0.5, -6.5, 4.25, -7.0])
        np.testing.assert_array_equal(_pair("BC", va, vb, vc), [3.5, 2.5, -3.0, 7.5])
        np.testing.assert_array_equal(_pair("CA", va, vb, vc), [-4.0, 4.0, -1.25, -0.5])


class TestPolarity:
    def test_vca_is_vc_minus_va(self):
        va, vc = np.array([10.0, 20.0]), np.array([1.0, 2.0])
        vca = _pair("CA", va, np.zeros(2), vc)
        np.testing.assert_array_equal(vca, [-9.0, -18.0])  # vc - va, never va - vc

    def test_three_pairs_sum_to_zero(self):
        va, vb, vc = _phase(30.0, 0), _phase(100.0, -105), _phase(80.0, 110)
        total = _pair("AB", va, vb, vc) + _pair("BC", va, vb, vc) + _pair("CA", va, vb, vc)
        np.testing.assert_allclose(total, 0.0, atol=1e-9)


class TestNullSemantics:
    def test_nan_propagates_pointwise(self):
        va = np.array([1.0, np.nan, 3.0])
        vb = np.array([0.5, 0.5, np.nan])
        out = evaluate_line_to_line_instantaneous(va, vb)
        assert out[0] == 0.5
        assert np.isnan(out[1]) and np.isnan(out[2])
