"""Unit tests for app.domain.power_calculation (Slice 0).

Every expected value below is derived independently from closed-form
physics/phasor algebra, NOT from the implementation. This keeps the
golden-vector tests honest: a wrong formula in the module cannot produce
a passing test whose expected value was obtained from that same formula.

Sign convention (DEC-PWR-003, passive):
    S = V * conj(I) = P + jQ
    P > 0: element absorbs active power (load convention).
    Q > 0: inductive / lagging.
    Q < 0: capacitive / leading.
    PF = P / S  (signed, range [-1, 1]).

Apparent power (DEC-PWR-002, geometric):
    S = |S| = sqrt(P^2 + Q^2)
    NOT the arithmetic sum of per-phase magnitudes.
"""

from __future__ import annotations

import math

import pytest

from app.domain.power_calculation import (
    ALGORITHM_VERSION,
    APPARENT_POWER_DEFINITION_GEOMETRIC,
    POWER_FACTOR_SIGN_LAGGING,
    POWER_FACTOR_SIGN_LEADING,
    POWER_FACTOR_SIGN_UNDEFINED,
    POWER_FACTOR_SIGN_UNITY,
    SIGN_CONVENTION_PASSIVE,
    PerPhasePowerResult,
    SinglePhasePowerResult,
    ThreePhasePowerResult,
    _normalize_angle_deg,
    _power_factor_sign_from_q,
    _to_complex,
    angle_deg_valid,
    current_magnitude_valid,
    single_phase_power,
    three_phase_power,
    voltage_magnitude_valid,
)

# ---------------------------------------------------------------------------
# Tolerance: absolute, in SI units (W, var, VA, degrees).
# Power magnitudes are O(100 kVA) in the golden tests; 1e-6 absolute gives
# well over 10 significant figures of agreement.
# ---------------------------------------------------------------------------
_TOL_POWER = 1e-6   # watts / var / VA
_TOL_PF = 1e-9      # power-factor (dimensionless, range [-1, 1])
_TOL_DEG = 1e-9     # degrees


# ===========================================================================
# Internal helpers
# ===========================================================================

class TestToComplex:
    """_to_complex(mag, angle_deg) → complex phasor (polar → rectangular)."""

    def test_zero_angle(self):
        c = _to_complex(1000.0, 0.0)
        assert c.real == pytest.approx(1000.0, abs=_TOL_POWER)
        assert c.imag == pytest.approx(0.0, abs=_TOL_POWER)

    def test_90_degrees(self):
        c = _to_complex(1.0, 90.0)
        assert c.real == pytest.approx(0.0, abs=_TOL_POWER)
        assert c.imag == pytest.approx(1.0, abs=_TOL_POWER)

    def test_minus_90_degrees(self):
        c = _to_complex(1.0, -90.0)
        assert c.real == pytest.approx(0.0, abs=_TOL_POWER)
        assert c.imag == pytest.approx(-1.0, abs=_TOL_POWER)

    def test_180_degrees(self):
        c = _to_complex(1.0, 180.0)
        assert c.real == pytest.approx(-1.0, abs=_TOL_POWER)
        assert c.imag == pytest.approx(0.0, abs=_TOL_POWER)

    def test_zero_magnitude(self):
        c = _to_complex(0.0, 45.0)
        assert c == pytest.approx(0.0 + 0.0j, abs=_TOL_POWER)


class TestNormalizeAngleDeg:
    """_normalize_angle_deg maps any angle to (-180, 180]."""

    def test_zero(self):
        assert _normalize_angle_deg(0.0) == pytest.approx(0.0, abs=_TOL_DEG)

    def test_positive_in_range(self):
        assert _normalize_angle_deg(90.0) == pytest.approx(90.0, abs=_TOL_DEG)

    def test_180(self):
        assert _normalize_angle_deg(180.0) == pytest.approx(180.0, abs=_TOL_DEG)

    def test_minus_180_folds_to_180(self):
        # -180 ≡ 180 mod 360; the convention maps this to 180.
        result = _normalize_angle_deg(-180.0)
        assert result == pytest.approx(180.0, abs=_TOL_DEG)

    def test_270_folds_to_minus_90(self):
        assert _normalize_angle_deg(270.0) == pytest.approx(-90.0, abs=_TOL_DEG)

    def test_minus_270_folds_to_90(self):
        assert _normalize_angle_deg(-270.0) == pytest.approx(90.0, abs=_TOL_DEG)

    def test_360_folds_to_0(self):
        assert _normalize_angle_deg(360.0) == pytest.approx(0.0, abs=_TOL_DEG)


class TestPowerFactorSignFromQ:
    """_power_factor_sign_from_q classifies Q/S correctly."""

    def test_lagging_positive_q(self):
        assert _power_factor_sign_from_q(1000.0, 1414.2) == POWER_FACTOR_SIGN_LAGGING

    def test_leading_negative_q(self):
        assert _power_factor_sign_from_q(-1000.0, 1414.2) == POWER_FACTOR_SIGN_LEADING

    def test_unity_zero_q(self):
        assert _power_factor_sign_from_q(0.0, 1000.0) == POWER_FACTOR_SIGN_UNITY

    def test_unity_q_near_zero(self):
        # Q/S = 1e-12, well below threshold
        assert _power_factor_sign_from_q(1e-12, 1.0) == POWER_FACTOR_SIGN_UNITY

    def test_undefined_zero_s(self):
        assert _power_factor_sign_from_q(0.0, 0.0) == POWER_FACTOR_SIGN_UNDEFINED

    def test_undefined_negative_q_zero_s(self):
        # S = 0 always wins over Q sign
        assert _power_factor_sign_from_q(-1.0, 0.0) == POWER_FACTOR_SIGN_UNDEFINED


# ===========================================================================
# Validation predicates
# ===========================================================================

class TestValidationPredicates:
    def test_voltage_valid(self):
        assert voltage_magnitude_valid(0.0) is True
        assert voltage_magnitude_valid(11000.0) is True

    def test_voltage_negative_invalid(self):
        assert voltage_magnitude_valid(-1.0) is False

    def test_voltage_inf_invalid(self):
        assert voltage_magnitude_valid(float("inf")) is False

    def test_voltage_nan_invalid(self):
        assert voltage_magnitude_valid(float("nan")) is False

    def test_current_valid(self):
        assert current_magnitude_valid(0.0) is True
        assert current_magnitude_valid(100.0) is True

    def test_current_negative_invalid(self):
        assert current_magnitude_valid(-0.1) is False

    def test_angle_valid(self):
        assert angle_deg_valid(0.0) is True
        assert angle_deg_valid(-180.0) is True
        assert angle_deg_valid(360.0) is True

    def test_angle_inf_invalid(self):
        assert angle_deg_valid(float("inf")) is False

    def test_angle_nan_invalid(self):
        assert angle_deg_valid(float("nan")) is False


# ===========================================================================
# single_phase_power — golden vector tests
# ===========================================================================

class TestSinglePhaseStandardLaggingLoad:
    """V = 1000 V @ 0°, I = 100 A @ -30° (current lags voltage by 30°).

    Closed-form derivation:
        S = V * conj(I)
          = 1000∠0° × 100∠+30°   (conj flips sign of angle)
          = 100 000∠30°
        P = 100 000 × cos(30°) = 100 000 × (√3/2) = 50 000√3 ≈ 86 602.540 378 W
        Q = 100 000 × sin(30°) = 100 000 × 0.5     = 50 000 var
        S = 100 000 VA
        PF = P/S = √3/2 ≈ 0.866 025 (lagging)
        power_angle_deg = 30°
    """
    _P = 50_000.0 * math.sqrt(3)   # ≈ 86 602.540 378 W
    _Q = 50_000.0                   # var
    _S = 100_000.0                  # VA
    _PF = math.sqrt(3) / 2.0       # ≈ 0.866 025

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 100.0, -30.0)

    def test_p_watts(self):
        assert self._r.p_watts == pytest.approx(self._P, abs=_TOL_POWER)

    def test_q_var(self):
        assert self._r.q_var == pytest.approx(self._Q, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(self._S, abs=_TOL_POWER)

    def test_power_factor(self):
        assert self._r.power_factor == pytest.approx(self._PF, abs=_TOL_PF)

    def test_power_factor_sign_lagging(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_LAGGING

    def test_power_angle_deg(self):
        assert self._r.power_angle_deg == pytest.approx(30.0, abs=_TOL_DEG)

    def test_metadata(self):
        assert self._r.sign_convention == SIGN_CONVENTION_PASSIVE
        assert self._r.apparent_power_definition == APPARENT_POWER_DEFINITION_GEOMETRIC
        assert self._r.algorithm_version == ALGORITHM_VERSION

    def test_result_type(self):
        assert isinstance(self._r, SinglePhasePowerResult)


class TestSinglePhaseUnityPowerFactor:
    """V = 1000 V @ 0°, I = 100 A @ 0° (unity PF — resistive load).

    Derivation:
        S = 1000∠0° × 100∠0° = 100 000∠0°
        P = 100 000 W, Q = 0, S = 100 000 VA, PF = 1.0
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 100.0, 0.0)

    def test_p_watts(self):
        assert self._r.p_watts == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_q_var(self):
        assert self._r.q_var == pytest.approx(0.0, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_power_factor_unity(self):
        assert self._r.power_factor == pytest.approx(1.0, abs=_TOL_PF)

    def test_power_factor_sign_unity(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_UNITY

    def test_power_angle_deg(self):
        assert self._r.power_angle_deg == pytest.approx(0.0, abs=_TOL_DEG)


class TestSinglePhasePureInductiveLoad:
    """V = 1000 V @ 0°, I = 100 A @ -90° (pure inductive, current lags 90°).

    Derivation:
        S = 1000∠0° × 100∠+90° = 100 000∠90°
        P = 0 W, Q = 100 000 var, S = 100 000 VA
        PF = 0.0 (lagging), power_angle_deg = 90°
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 100.0, -90.0)

    def test_p_watts_zero(self):
        assert self._r.p_watts == pytest.approx(0.0, abs=_TOL_POWER)

    def test_q_var_positive(self):
        assert self._r.q_var == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_power_factor_zero(self):
        assert self._r.power_factor == pytest.approx(0.0, abs=_TOL_PF)

    def test_power_factor_sign_lagging(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_LAGGING

    def test_power_angle_deg(self):
        assert self._r.power_angle_deg == pytest.approx(90.0, abs=_TOL_DEG)


class TestSinglePhaseCapacitiveLeading:
    """V = 1000 V @ 0°, I = 100 A @ +30° (current leads voltage by 30°).

    Derivation:
        S = 1000∠0° × 100∠-30° = 100 000∠-30°
        P = 100 000 × cos(-30°) = 50 000√3 ≈ 86 602.540 W
        Q = 100 000 × sin(-30°) = -50 000 var   (negative = capacitive)
        PF = √3/2 ≈ 0.866 025 (leading)
        power_angle_deg = -30°
    """
    _P = 50_000.0 * math.sqrt(3)

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 100.0, +30.0)

    def test_p_watts(self):
        assert self._r.p_watts == pytest.approx(self._P, abs=_TOL_POWER)

    def test_q_var_negative(self):
        assert self._r.q_var == pytest.approx(-50_000.0, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_power_factor_sign_leading(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_LEADING

    def test_power_angle_deg(self):
        assert self._r.power_angle_deg == pytest.approx(-30.0, abs=_TOL_DEG)


class TestSinglePhaseReversePower:
    """V = 1000 V @ 0°, I = 100 A @ 180° (generating / reverse active flow).

    Derivation:
        S = 1000∠0° × 100∠-180° = 100 000∠-180°
        P = 100 000 × cos(-180°) = -100 000 W  (element supplies power)
        Q = 100 000 × sin(-180°) = 0 var
        S = 100 000 VA
        PF = P/S = -1.0 (negative — reverse flow; sign is preserved)
        power_factor_sign = "unity" (|Q| = 0, S > 0)
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 100.0, 180.0)

    def test_p_watts_negative(self):
        assert self._r.p_watts == pytest.approx(-100_000.0, abs=_TOL_POWER)

    def test_q_var_zero(self):
        assert self._r.q_var == pytest.approx(0.0, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(100_000.0, abs=_TOL_POWER)

    def test_power_factor_negative_one(self):
        # PF = P/S = -100 000 / 100 000 = -1.0 (signed, reverse flow)
        assert self._r.power_factor == pytest.approx(-1.0, abs=_TOL_PF)

    def test_power_factor_sign_unity(self):
        # Q = 0, S > 0 → unity classification; the SIGN of P is in power_factor
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_UNITY


class TestSinglePhaseZeroCurrent:
    """V = 1000 V @ 0°, I = 0 A (open circuit).

    Derivation:
        All products → 0; PF undefined (0/0).
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 0.0, 0.0, 0.0)

    def test_p_watts_zero(self):
        assert self._r.p_watts == pytest.approx(0.0, abs=_TOL_POWER)

    def test_q_var_zero(self):
        assert self._r.q_var == pytest.approx(0.0, abs=_TOL_POWER)

    def test_s_va_zero(self):
        assert self._r.s_va == pytest.approx(0.0, abs=_TOL_POWER)

    def test_power_factor_none(self):
        assert self._r.power_factor is None

    def test_power_factor_sign_undefined(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_UNDEFINED


class TestSinglePhaseZeroVoltage:
    """V = 0 V, I = 100 A — dead bus."""

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(0.0, 0.0, 100.0, -30.0)

    def test_s_va_zero(self):
        assert self._r.s_va == pytest.approx(0.0, abs=_TOL_POWER)

    def test_power_factor_none(self):
        assert self._r.power_factor is None

    def test_power_factor_sign_undefined(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_UNDEFINED


class TestSinglePhaseAngleIndependence:
    """Power depends only on the angle DIFFERENCE (theta_V - theta_I).

    V = 1000 V @ 45°, I = 100 A @ 15°: same 30° lead as the standard
    lagging test (delta = 45 - 15 = 30°), so P, Q, S must be identical.
    """
    _P = 50_000.0 * math.sqrt(3)
    _Q = 50_000.0
    _S = 100_000.0

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = single_phase_power(1000.0, 45.0, 100.0, 15.0)

    def test_p_matches_standard_lagging(self):
        assert self._r.p_watts == pytest.approx(self._P, abs=_TOL_POWER)

    def test_q_matches_standard_lagging(self):
        assert self._r.q_var == pytest.approx(self._Q, abs=_TOL_POWER)

    def test_s_matches_standard_lagging(self):
        assert self._r.s_va == pytest.approx(self._S, abs=_TOL_POWER)

    def test_power_factor_sign_lagging(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_LAGGING


# ===========================================================================
# three_phase_power — golden vector tests
# ===========================================================================

class TestThreePhaseBalanced:
    """Perfectly balanced positive-sequence 11 kV system, 100 A @ 0.866 PF lag.

    Phase voltages (line-to-neutral):
        V_R = 11 000/√3 ∠  0° V
        V_Y = 11 000/√3 ∠-120° V
        V_B = 11 000/√3 ∠-240° (= +120°) V

    Phase currents at 30° lag (0.866 PF):
        I_R = 100 ∠ -30° A
        I_Y = 100 ∠ -150° A
        I_B = 100 ∠  +90° A   (i.e. -270°)

    Per-phase derivation (identical for each, by symmetry):
        S_k = V_k * conj(I_k)
        delta_k = angle(V_k) - angle(I_k) = 0° - (-30°) = 30°  (same for all)
        P_k = |V_k|×|I_k|×cos(30°) = (11000/√3) × 100 × (√3/2)
            = 11000 × 100 / 2 = 550 000 W
        Q_k = (11000/√3) × 100 × sin(30°)
            = (11000/√3) × 50 = 550 000/√3 var
        S_k = (11000/√3) × 100 VA

    Three-phase totals:
        P_total = 3 × P_k = 1 650 000 W  = 1.65 MW
        Q_total = 3 × Q_k = 3 × 550000/√3 = 1 650 000/√3 var
        S_geometric = sqrt(P^2 + Q^2) = P_total / cos(30°) = P_total × 2/√3
                    = 1 650 000 × 2/√3 = 3 300 000/√3 VA
                    = (11000/√3) × 100 × 3  (which is also 3|S_k| — balanced)
    """
    _VLN = 11_000.0 / math.sqrt(3)    # V line-to-neutral
    _I   = 100.0                        # A
    _P_PER_PHASE = _VLN * _I * math.cos(math.radians(30.0))
    _Q_PER_PHASE = _VLN * _I * math.sin(math.radians(30.0))
    _S_PER_PHASE = _VLN * _I
    _P_TOTAL = 3.0 * _P_PER_PHASE
    _Q_TOTAL = 3.0 * _Q_PER_PHASE
    # For balanced: S_geometric == 3 * S_per_phase (triangle inequality is tight)
    _S_TOTAL = math.hypot(_P_TOTAL, _Q_TOTAL)
    _PF = math.sqrt(3) / 2.0            # cos(30°)

    @pytest.fixture(autouse=True)
    def result(self):
        vln = self._VLN
        self._r = three_phase_power(
            vln,   0.0, 100.0,  -30.0,
            vln, -120.0, 100.0, -150.0,
            vln,  120.0, 100.0,   90.0,
        )

    def test_p_watts(self):
        assert self._r.p_watts == pytest.approx(self._P_TOTAL, abs=_TOL_POWER)

    def test_q_var(self):
        assert self._r.q_var == pytest.approx(self._Q_TOTAL, abs=_TOL_POWER)

    def test_s_va(self):
        assert self._r.s_va == pytest.approx(self._S_TOTAL, abs=_TOL_POWER)

    def test_power_factor(self):
        assert self._r.power_factor == pytest.approx(self._PF, abs=_TOL_PF)

    def test_power_factor_sign_lagging(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_LAGGING

    def test_per_phase_p_r(self):
        assert self._r.phase_r.p_watts == pytest.approx(self._P_PER_PHASE, abs=_TOL_POWER)

    def test_per_phase_q_r(self):
        assert self._r.phase_r.q_var == pytest.approx(self._Q_PER_PHASE, abs=_TOL_POWER)

    def test_per_phase_s_r(self):
        assert self._r.phase_r.s_va == pytest.approx(self._S_PER_PHASE, abs=_TOL_POWER)

    def test_per_phase_symmetry(self):
        # All three phases should be equal (balanced system)
        r = self._r
        assert r.phase_r.p_watts == pytest.approx(r.phase_y.p_watts, abs=_TOL_POWER)
        assert r.phase_r.p_watts == pytest.approx(r.phase_b.p_watts, abs=_TOL_POWER)
        assert r.phase_r.q_var == pytest.approx(r.phase_y.q_var, abs=_TOL_POWER)
        assert r.phase_r.q_var == pytest.approx(r.phase_b.q_var, abs=_TOL_POWER)

    def test_metadata(self):
        assert self._r.sign_convention == SIGN_CONVENTION_PASSIVE
        assert self._r.apparent_power_definition == APPARENT_POWER_DEFINITION_GEOMETRIC
        assert self._r.algorithm_version == ALGORITHM_VERSION

    def test_result_type(self):
        assert isinstance(self._r, ThreePhasePowerResult)
        assert isinstance(self._r.phase_r, PerPhasePowerResult)

    def test_balanced_geometric_equals_arithmetic(self):
        """For a balanced system S_geometric == S_arithmetic = 3|S_k|."""
        r = self._r
        s_arithmetic = r.phase_r.s_va + r.phase_y.s_va + r.phase_b.s_va
        # Both should equal _S_TOTAL
        assert r.s_va == pytest.approx(s_arithmetic, abs=_TOL_POWER)


class TestThreePhasePerPhaseSumConsistency:
    """P_total = P_R + P_Y + P_B and Q_total = Q_R + Q_Y + Q_B hold for any
    three-phase system (linearity of complex power summation).

    Use an unbalanced case to avoid accidental cancellations: three
    different voltage magnitudes, three different current magnitudes and
    three different power angles.
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = three_phase_power(
            6351.0,   0.0, 120.0,  -25.0,   # Phase R: 6351 V, 120 A, 25° lag
            6000.0, -115.0, 95.0, -145.0,   # Phase Y: different magnitude & angle
            6600.0,  125.0, 80.0,   80.0,   # Phase B: leading (I leads V)
        )

    def test_p_total_equals_sum_of_phases(self):
        r = self._r
        expected = r.phase_r.p_watts + r.phase_y.p_watts + r.phase_b.p_watts
        assert r.p_watts == pytest.approx(expected, abs=_TOL_POWER)

    def test_q_total_equals_sum_of_phases(self):
        r = self._r
        expected = r.phase_r.q_var + r.phase_y.q_var + r.phase_b.q_var
        assert r.q_var == pytest.approx(expected, abs=_TOL_POWER)

    def test_s_geometric_from_totals(self):
        r = self._r
        expected = math.hypot(r.p_watts, r.q_var)
        assert r.s_va == pytest.approx(expected, abs=_TOL_POWER)


class TestThreePhaseGeometricLeArithmeticUnbalanced:
    """For an unbalanced three-phase system, S_geometric < S_arithmetic.

    This is the triangle inequality: |A + B + C| <= |A| + |B| + |C|.
    Equality holds only when all complex powers S_k are co-linear (same
    angle) -- i.e. a perfectly balanced system.

    Deliberately chosen so the three per-phase complex power angles differ
    (mixed lagging / leading / resistive) to produce a non-trivial
    inequality.
    """

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = three_phase_power(
            1000.0,  0.0, 100.0, -45.0,   # R: lagging 45° (P=Q=70711 W)
            1000.0, -120.0, 100.0, -90.0, # Y: lagging 30° (P large, Q moderate)
            1000.0,  120.0, 100.0, +80.0, # B: strongly leading
        )

    def test_s_geometric_less_than_arithmetic(self):
        r = self._r
        s_arithmetic = r.phase_r.s_va + r.phase_y.s_va + r.phase_b.s_va
        # Geometric must be strictly less (angles are different → non-trivial inequality)
        assert r.s_va < s_arithmetic

    def test_s_geometric_equals_sqrt_p2_q2(self):
        r = self._r
        assert r.s_va == pytest.approx(math.hypot(r.p_watts, r.q_var), abs=_TOL_POWER)


class TestThreePhaseAllZeroCurrent:
    """All currents zero: P = Q = S = 0, PF undefined."""

    @pytest.fixture(autouse=True)
    def result(self):
        self._r = three_phase_power(
            6351.0,   0.0, 0.0,   0.0,
            6351.0, -120.0, 0.0, -120.0,
            6351.0,  120.0, 0.0,  120.0,
        )

    def test_p_zero(self):
        assert self._r.p_watts == pytest.approx(0.0, abs=_TOL_POWER)

    def test_q_zero(self):
        assert self._r.q_var == pytest.approx(0.0, abs=_TOL_POWER)

    def test_s_zero(self):
        assert self._r.s_va == pytest.approx(0.0, abs=_TOL_POWER)

    def test_pf_none(self):
        assert self._r.power_factor is None

    def test_pf_sign_undefined(self):
        assert self._r.power_factor_sign == POWER_FACTOR_SIGN_UNDEFINED


class TestThreePhaseReverseTotalPower:
    """Balanced system where all currents are 180° out — generating / reverse flow.

    V_R = V_LN∠0°, I_R = 100∠150° (current 150° from voltage → phase difference
    angle = 0 - 150 = -150°, so after conj: +150°).

    Actually: if we set I to be 180° shifted from the lagging case:
        Standard lagging: I_R = 100∠-30°
        Reverse:          I_R = 100∠+150° (180° + (-30°))

    S_R = V_R * conj(I_R) = V_LN∠0° × 100∠-150° = 100*V_LN∠-150°
    P_R = 100*V_LN*cos(-150°) = -100*V_LN*(√3/2) < 0  (supplies power)
    Q_R = 100*V_LN*sin(-150°) = -100*V_LN*0.5         < 0  (capacitive in generation)
    """
    _VLN = 11_000.0 / math.sqrt(3)
    _P_PER_PHASE = -(_VLN * 100.0 * math.sqrt(3) / 2.0)  # negative
    _Q_PER_PHASE = -(_VLN * 100.0 * 0.5)                  # negative

    @pytest.fixture(autouse=True)
    def result(self):
        vln = self._VLN
        self._r = three_phase_power(
            vln,   0.0, 100.0,  150.0,
            vln, -120.0, 100.0,  30.0,
            vln,  120.0, 100.0, -90.0,
        )

    def test_p_total_negative(self):
        assert self._r.p_watts < 0.0
        assert self._r.p_watts == pytest.approx(3.0 * self._P_PER_PHASE, abs=_TOL_POWER)

    def test_pf_negative(self):
        assert self._r.power_factor is not None
        assert self._r.power_factor < 0.0

    def test_s_va_positive(self):
        # Apparent power is always non-negative regardless of direction
        assert self._r.s_va > 0.0
