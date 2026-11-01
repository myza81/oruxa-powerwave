"""Domain tests for evaluate_three_phase_power_channel() (DEC-208, Phase E-2A).

All expected values are derived from first-principles phasor algebra —
never from the implementation under test.

Sign convention (DEC-PWR-003, passive):
    S = V · conj(I) per phase;  S_total = Σ S_k
    P > 0: element absorbs active power (load convention).
    Q > 0: inductive / lagging load.
    Q < 0: capacitive / leading load.

Apparent power (DEC-PWR-002, geometric):
    |S_total| = sqrt(P_total² + Q_total²)
    NOT the arithmetic sum of per-phase |S_k|.

Null policy (DEC-208 propagate):
    ANY phase phasor unavailable at sample t → NaN at output sample t.
    No partial sum of fewer than 3 phases is ever returned silently.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.calculated_channel import (
    OP_ACTIVE_POWER,
    OP_APPARENT_POWER,
    OP_REACTIVE_POWER,
    evaluate_three_phase_power_channel,
)

F0_HZ = 50.0
FS_HZ = 5_000.0            # 100 samples/cycle — well above density threshold
_N_CYCLES = 5              # total recording length in cycles
_N = int(FS_HZ / F0_HZ * _N_CYCLES)
_TOL_ABS_MW = 1e-9         # MW / Mvar / MVA absolute tolerance on nanmean


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time() -> np.ndarray:
    return np.arange(_N, dtype=np.float64) / FS_HZ


def _sinusoid(amplitude: float, angle_deg: float) -> np.ndarray:
    """Pure sinusoid at F0_HZ: amplitude × sin(ωt + angle_deg)."""
    t = _time()
    return amplitude * np.sin(2 * np.pi * F0_HZ * t + math.radians(angle_deg))


def _balanced_inputs(
    v_rms: float,
    i_rms: float,
    pf_angle_deg: float,
    v1_phase_deg: float = 0.0,
) -> tuple[np.ndarray, ...]:
    """Return (time, v1,i1, v2,i2, v3,i3) for a balanced positive-sequence system.

    Phase sequence: v1=0°, v2=-120°, v3=+120° (relative to v1_phase_deg).
    Current lags voltage by pf_angle_deg (positive = lagging/inductive).
    Amplitudes: v_amp = v_rms × √2, i_amp = i_rms × √2.
    """
    v_amp = v_rms * math.sqrt(2)
    i_amp = i_rms * math.sqrt(2)
    v1 = _sinusoid(v_amp, v1_phase_deg + 0.0)
    v2 = _sinusoid(v_amp, v1_phase_deg - 120.0)
    v3 = _sinusoid(v_amp, v1_phase_deg + 120.0)
    i1 = _sinusoid(i_amp, v1_phase_deg + 0.0   - pf_angle_deg)
    i2 = _sinusoid(i_amp, v1_phase_deg - 120.0 - pf_angle_deg)
    i3 = _sinusoid(i_amp, v1_phase_deg + 120.0 - pf_angle_deg)
    return _time(), v1, i1, v2, i2, v3, i3


def _evaluate(operation: str, t, v1, i1, v2, i2, v3, i3) -> np.ndarray:
    return evaluate_three_phase_power_channel(
        operation,
        t,
        v1, 1.0, i1, 1.0,
        v2, 1.0, i2, 1.0,
        v3, 1.0, i3, 1.0,
    )


def _steady(arr: np.ndarray) -> np.ndarray:
    """Return the array after the first full cycle (skip phasor warm-up transient)."""
    skip = int(FS_HZ / F0_HZ)
    return arr[skip:]


# ---------------------------------------------------------------------------
# Scenario A — balanced golden test
# P = 1299.0381 W (≈ 1500 × cos 30°), Q = 750 var (= 1500 × sin 30°), S = 1500 VA
#
# Derivation:
#   V_rms = 100 V, I_rms = 5 A → S_per_phase = 500 VA
#   PF angle = 30° (lagging) → P_per_phase = 500 cos 30° = 250√3 ≈ 433.0127 W
#                               Q_per_phase = 500 sin 30° = 250 var
#   P_total = 3 × 250√3 = 750√3 ≈ 1299.0381 W
#   Q_total = 3 × 250   = 750 var
#   S_total = sqrt(P²+Q²) = sqrt((750√3)² + 750²) = 750×sqrt(3+1) = 1500 VA
# ---------------------------------------------------------------------------

_V_RMS_A = 100.0
_I_RMS_A = 5.0
_PF_ANGLE_A = 30.0

_P_TOTAL_A = 3 * _V_RMS_A * _I_RMS_A * math.cos(math.radians(_PF_ANGLE_A))
_Q_TOTAL_A = 3 * _V_RMS_A * _I_RMS_A * math.sin(math.radians(_PF_ANGLE_A))
_S_TOTAL_A = math.hypot(_P_TOTAL_A, _Q_TOTAL_A)


class TestScenarioA_BalancedGolden:
    """Scenario A: balanced 100 V / 5 A, 30° PF lag — golden numerical values."""

    @pytest.fixture(autouse=True)
    def _build(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(_V_RMS_A, _I_RMS_A, _PF_ANGLE_A)
        self._p = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER,  t, v1, i1, v2, i2, v3, i3)))
        self._q = np.nanmean(_steady(_evaluate(OP_REACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))
        self._s = np.nanmean(_steady(_evaluate(OP_APPARENT_POWER, t, v1, i1, v2, i2, v3, i3)))

    def test_active_power_mw(self):
        assert self._p == pytest.approx(_P_TOTAL_A / 1e6, rel=0.001)

    def test_reactive_power_mvar(self):
        assert self._q == pytest.approx(_Q_TOTAL_A / 1e6, rel=0.001)

    def test_apparent_power_mva(self):
        assert self._s == pytest.approx(_S_TOTAL_A / 1e6, rel=0.001)

    def test_golden_p_watts_value(self):
        """P_total ≈ 1299.038 W = 750√3 W — exact closed-form check."""
        assert self._p * 1e6 == pytest.approx(750.0 * math.sqrt(3), abs=0.001)

    def test_golden_q_var_value(self):
        assert self._q * 1e6 == pytest.approx(750.0, abs=0.001)

    def test_golden_s_va_value(self):
        assert self._s * 1e6 == pytest.approx(1500.0, abs=0.001)


# ---------------------------------------------------------------------------
# Scenario B — P_total = Σ P_k (linearity of Re)
# ---------------------------------------------------------------------------

class TestScenarioB_PLinearityOfPhases:
    """P_total must equal the sum of per-phase active powers (unbalanced case)."""

    def _per_phase_p(
        self, v_amp: float, i_amp: float, pf_angle_deg: float
    ) -> float:
        """Expected per-phase P from closed-form: V_rms × I_rms × cos(angle)."""
        return (v_amp / math.sqrt(2)) * (i_amp / math.sqrt(2)) * math.cos(math.radians(pf_angle_deg))

    def test_p_total_equals_sum_of_per_phase(self):
        t = _time()
        # Deliberately unbalanced: different amplitudes and PF angles per phase
        v1 = _sinusoid(141.0,  0.0)
        i1 = _sinusoid(  7.0, -20.0)
        v2 = _sinusoid(130.0, -120.0)
        i2 = _sinusoid(  9.0, -155.0)
        v3 = _sinusoid(150.0,  120.0)
        i3 = _sinusoid(  6.0,   85.0)

        p_total = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))

        # Compute per-phase expected from phasor algebra
        from app.domain.sliding_phasor import compute_sliding_phasor
        skip = int(FS_HZ / F0_HZ)
        p_sum = 0.0
        for v_arr, i_arr in [(v1, i1), (v2, i2), (v3, i3)]:
            vr = compute_sliding_phasor(t, v_arr, F0_HZ)
            ir = compute_sliding_phasor(t, i_arr, F0_HZ)
            s_k = vr.phasor * np.conj(ir.phasor)
            p_sum += np.nanmean(np.real(s_k)[skip:])

        np.testing.assert_allclose(p_total * 1e6, p_sum, rtol=1e-9)


# ---------------------------------------------------------------------------
# Scenario C — Q_total = Σ Q_k
# ---------------------------------------------------------------------------

class TestScenarioC_QLinearityOfPhases:
    """Q_total must equal the sum of per-phase reactive powers."""

    def test_q_total_equals_sum_of_per_phase(self):
        t = _time()
        v1 = _sinusoid(141.0,  0.0)
        i1 = _sinusoid(  7.0, -45.0)
        v2 = _sinusoid(130.0, -120.0)
        i2 = _sinusoid(  9.0, -165.0)
        v3 = _sinusoid(150.0,  120.0)
        i3 = _sinusoid(  6.0,   75.0)

        q_total = np.nanmean(_steady(_evaluate(OP_REACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))

        from app.domain.sliding_phasor import compute_sliding_phasor
        skip = int(FS_HZ / F0_HZ)
        q_sum = 0.0
        for v_arr, i_arr in [(v1, i1), (v2, i2), (v3, i3)]:
            vr = compute_sliding_phasor(t, v_arr, F0_HZ)
            ir = compute_sliding_phasor(t, i_arr, F0_HZ)
            s_k = vr.phasor * np.conj(ir.phasor)
            q_sum += np.nanmean(np.imag(s_k)[skip:])

        np.testing.assert_allclose(q_total * 1e6, q_sum, rtol=1e-9)


# ---------------------------------------------------------------------------
# Scenario D — |S_total|² = P_total² + Q_total² (triangle relation)
# ---------------------------------------------------------------------------

class TestScenarioD_ApparentPowerTriangle:
    """S² = P² + Q² must hold at every steady-state sample."""

    def test_s_squared_equals_p_squared_plus_q_squared(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, 30.0)
        p = _evaluate(OP_ACTIVE_POWER,   t, v1, i1, v2, i2, v3, i3)
        q = _evaluate(OP_REACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)
        s = _evaluate(OP_APPARENT_POWER, t, v1, i1, v2, i2, v3, i3)
        idx = slice(int(FS_HZ / F0_HZ), None)
        np.testing.assert_allclose(s[idx] ** 2, p[idx] ** 2 + q[idx] ** 2, rtol=1e-6)


# ---------------------------------------------------------------------------
# Scenario E — S_geometric < S_arithmetic for unbalanced load
# ---------------------------------------------------------------------------

class TestScenarioE_GeometricLessThanArithmetic:
    """For unbalanced loads with mixed PF angles, S_geometric < S_arithmetic."""

    def test_geometric_strictly_less_than_arithmetic(self):
        t = _time()
        # Phase 1: lagging 45° (large Q positive)
        # Phase 2: lagging 0° (no Q contribution)
        # Phase 3: leading 60° (large Q negative) → partial cancellation
        v_amp = 141.4  # ≈ 100√2 V
        i_amp = 7.07   # ≈ 5√2 A
        v1 = _sinusoid(v_amp,  0.0);    i1 = _sinusoid(i_amp, -45.0)
        v2 = _sinusoid(v_amp, -120.0);  i2 = _sinusoid(i_amp, -120.0)
        v3 = _sinusoid(v_amp,  120.0);  i3 = _sinusoid(i_amp,  120.0 + 60.0)

        from app.domain.sliding_phasor import compute_sliding_phasor
        skip = int(FS_HZ / F0_HZ)
        s_arithmetic = 0.0
        for v_arr, i_arr in [(v1, i1), (v2, i2), (v3, i3)]:
            vr = compute_sliding_phasor(t, v_arr, F0_HZ)
            ir = compute_sliding_phasor(t, i_arr, F0_HZ)
            s_k = vr.phasor * np.conj(ir.phasor)
            s_arithmetic += np.nanmean(np.abs(s_k)[skip:])

        s_geo = np.nanmean(_steady(_evaluate(OP_APPARENT_POWER, t, v1, i1, v2, i2, v3, i3))) * 1e6
        assert s_geo < s_arithmetic, (
            f"Expected S_geometric ({s_geo:.3f} VA) < S_arithmetic ({s_arithmetic:.3f} VA)"
        )


# ---------------------------------------------------------------------------
# Scenario F — passive sign convention: P > 0 for absorbing load
# ---------------------------------------------------------------------------

class TestScenarioF_PassiveSignConventionAbsorbing:
    """P > 0 when load absorbs power (current lags voltage, passive convention)."""

    def test_p_positive_for_lagging_load(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        p_mean = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))
        assert p_mean > 0.0, "P must be positive for absorbing (lagging) load"


# ---------------------------------------------------------------------------
# Scenario G — Q > 0 for inductive (lagging) load
# ---------------------------------------------------------------------------

class TestScenarioG_QPositiveInductive:
    """Q > 0 when current lags voltage (inductive / lagging load)."""

    def test_q_positive_for_lagging_load(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        q_mean = np.nanmean(_steady(_evaluate(OP_REACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))
        assert q_mean > 0.0, "Q must be positive for inductive (lagging) load"


# ---------------------------------------------------------------------------
# Scenario H — Q < 0 for capacitive (leading) load
# ---------------------------------------------------------------------------

class TestScenarioH_QNegativeCapacitive:
    """Q < 0 when current leads voltage (capacitive / leading load)."""

    def test_q_negative_for_leading_load(self):
        # pf_angle_deg < 0 → current leads voltage
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=-30.0)
        q_mean = np.nanmean(_steady(_evaluate(OP_REACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))
        assert q_mean < 0.0, "Q must be negative for capacitive (leading) load"


# ---------------------------------------------------------------------------
# Scenario I — NaN propagation: phase 1 phasor unavailable
# ---------------------------------------------------------------------------

class TestScenarioI_NanPhase1:
    """NaN in phase-1 voltage waveform → NaN at those output samples."""

    def test_nan_in_v1_propagates_to_output(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        v1 = v1.copy()
        mid = len(t) // 2
        v1[mid] = np.nan

        result = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
        )
        # The NaN window spreads across one DFT window; at least one NaN must appear
        assert np.any(np.isnan(result)), "NaN in phase-1 voltage must propagate to output"


# ---------------------------------------------------------------------------
# Scenario J — NaN propagation: phase 2 phasor unavailable
# ---------------------------------------------------------------------------

class TestScenarioJ_NanPhase2:
    """NaN in phase-2 current waveform → NaN at those output samples."""

    def test_nan_in_i2_propagates_to_output(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        i2 = i2.copy()
        mid = len(t) // 2
        i2[mid] = np.nan

        result = evaluate_three_phase_power_channel(
            OP_REACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
        )
        assert np.any(np.isnan(result)), "NaN in phase-2 current must propagate to output"


# ---------------------------------------------------------------------------
# Scenario K — NaN propagation: phase 3 phasor unavailable
# ---------------------------------------------------------------------------

class TestScenarioK_NanPhase3:
    """NaN in phase-3 voltage waveform → NaN at those output samples."""

    def test_nan_in_v3_propagates_to_output(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        v3 = v3.copy()
        mid = len(t) // 2
        v3[mid] = np.nan

        result = evaluate_three_phase_power_channel(
            OP_APPARENT_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
        )
        assert np.any(np.isnan(result)), "NaN in phase-3 voltage must propagate to output"


# ---------------------------------------------------------------------------
# Scenario L — No NaN in steady state for clean inputs
# ---------------------------------------------------------------------------

class TestScenarioL_NoNanInSteadyState:
    """Clean inputs with no NaN produce finite output past the warm-up window."""

    def test_all_operations_finite_in_steady_state(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        for op in (OP_ACTIVE_POWER, OP_REACTIVE_POWER, OP_APPARENT_POWER):
            result = _evaluate(op, t, v1, i1, v2, i2, v3, i3)
            steady = _steady(result)
            assert np.isfinite(steady).all(), f"op={op}: unexpected NaN/Inf in steady state"


# ---------------------------------------------------------------------------
# Scenario M — Unit scaling: kV × kA → correct MW magnitude
# ---------------------------------------------------------------------------

class TestScenarioM_UnitScaling:
    """Balanced 1 kV / 1 kA at 0° PF → P ≈ 1.5 MW after kV+kA → SI scaling."""

    def test_kv_ka_to_mw(self):
        # V amplitude = 1 kV (stored), I amplitude = 1 kA (stored), in-phase → P = Vrms × Irms × 3
        # Vrms = (1000 V)/√2, Irms = (1000 A)/√2 → P_per_phase = (1000/√2)² = 500 kW
        # P_total = 1500 kW = 1.5 MW
        t = _time()
        v_amp_kv = 1.0   # amplitude in kV
        i_amp_ka = 1.0   # amplitude in kA
        v1_kv = v_amp_kv * np.sin(2 * np.pi * F0_HZ * t)
        v2_kv = v_amp_kv * np.sin(2 * np.pi * F0_HZ * t - math.radians(120.0))
        v3_kv = v_amp_kv * np.sin(2 * np.pi * F0_HZ * t + math.radians(120.0))
        i1_ka = i_amp_ka * np.sin(2 * np.pi * F0_HZ * t)
        i2_ka = i_amp_ka * np.sin(2 * np.pi * F0_HZ * t - math.radians(120.0))
        i3_ka = i_amp_ka * np.sin(2 * np.pi * F0_HZ * t + math.radians(120.0))

        result = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1_kv, 1000.0, i1_ka, 1000.0,   # kV → V, kA → A
            v2_kv, 1000.0, i2_ka, 1000.0,
            v3_kv, 1000.0, i3_ka, 1000.0,
        )
        p_mean_mw = np.nanmean(_steady(result))
        # Expected: 3 × (1000/√2)² / 1e6 = 3 × 500 000 / 1e6 = 1.5 MW
        assert p_mean_mw == pytest.approx(1.5, rel=0.01)


# ---------------------------------------------------------------------------
# Scenario N — Reverse power: P < 0 for generating source
# ---------------------------------------------------------------------------

class TestScenarioN_ReversePower:
    """P < 0 when the three-phase element supplies power (generator convention)."""

    def test_p_negative_for_reverse_power_flow(self):
        # Currents are 180° out — equivalent to a generator supplying active power
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(
            v_rms=100.0, i_rms=5.0,
            pf_angle_deg=180.0,   # 180° lag ≡ reverse active, zero reactive
        )
        p_mean = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER, t, v1, i1, v2, i2, v3, i3)))
        assert p_mean < 0.0, "P must be negative for reverse (generating) power flow"

    def test_s_positive_for_reverse_power_flow(self):
        # Apparent power is always non-negative regardless of direction
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(
            v_rms=100.0, i_rms=5.0,
            pf_angle_deg=180.0,
        )
        s_mean = np.nanmean(_steady(_evaluate(OP_APPARENT_POWER, t, v1, i1, v2, i2, v3, i3)))
        assert s_mean > 0.0, "|S| must remain positive even for reverse power flow"


# ===========================================================================
# ENGINEERING VERIFICATION 1 — Unit scaling contract
# ===========================================================================
#
# Contract:
#   - evaluate_three_phase_power_channel() expects RAW stored values (not
#     pre-converted to SI) for each channel.
#   - Each *_scale_to_si factor is the SI multiplier for that specific
#     channel's declared storage unit (volts/declared-unit or A/declared-unit).
#   - Scaling happens once inside the evaluator via _si(values, scale).
#   - Mixed units (kV/A, V/kA, kV/kA, or different units per phase) are
#     handled correctly because every channel carries its own scale factor.
#   - Double-conversion cannot occur if callers pass raw values and the
#     correct scale factor: the service layer must pass raw stored arrays
#     (NOT pre-scaled arrays) alongside the parse_engineering_unit()-derived
#     scale_to_canonical factor, matching the existing single-phase pattern.
# ===========================================================================

class TestUnitScaling_kV_A:
    """kV voltage input, A current input: scale 1000.0/1.0 per phase."""

    def test_kv_voltage_a_current_p_matches_si(self):
        # Build identical inputs in SI, then store V as kV (÷ 1000) and pass
        # scale=1000.  Result must equal the SI version (scale=1.0) identically.
        t = _time()
        v1_si = _sinusoid(141.421, 0.0)
        v2_si = _sinusoid(141.421, -120.0)
        v3_si = _sinusoid(141.421, 120.0)
        i1_si = _sinusoid(7.071, -30.0)
        i2_si = _sinusoid(7.071, -150.0)
        i3_si = _sinusoid(7.071, 90.0)

        # SI reference
        p_si = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER, t, v1_si, i1_si, v2_si, i2_si, v3_si, i3_si)))

        # kV stored: divide V channels by 1000, pass scale=1000
        v1_kv = v1_si / 1000.0
        v2_kv = v2_si / 1000.0
        v3_kv = v3_si / 1000.0

        result = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1_kv, 1000.0, i1_si, 1.0,
            v2_kv, 1000.0, i2_si, 1.0,
            v3_kv, 1000.0, i3_si, 1.0,
        )
        p_kv_a = np.nanmean(_steady(result))

        np.testing.assert_allclose(p_kv_a, p_si, rtol=1e-9,
                                   err_msg="kV/A scaling must match SI reference")


class TestUnitScaling_V_kA:
    """V voltage input, kA current input: scale 1.0/1000.0 per phase."""

    def test_v_voltage_ka_current_q_matches_si(self):
        t = _time()
        v1_si = _sinusoid(141.421, 0.0)
        v2_si = _sinusoid(141.421, -120.0)
        v3_si = _sinusoid(141.421, 120.0)
        i1_si = _sinusoid(7.071, -30.0)
        i2_si = _sinusoid(7.071, -150.0)
        i3_si = _sinusoid(7.071, 90.0)

        q_si = np.nanmean(_steady(_evaluate(OP_REACTIVE_POWER, t, v1_si, i1_si, v2_si, i2_si, v3_si, i3_si)))

        # kA stored: divide I channels by 1000, pass scale=1000
        i1_ka = i1_si / 1000.0
        i2_ka = i2_si / 1000.0
        i3_ka = i3_si / 1000.0

        result = evaluate_three_phase_power_channel(
            OP_REACTIVE_POWER, t,
            v1_si, 1.0, i1_ka, 1000.0,
            v2_si, 1.0, i2_ka, 1000.0,
            v3_si, 1.0, i3_ka, 1000.0,
        )
        q_v_ka = np.nanmean(_steady(result))

        np.testing.assert_allclose(q_v_ka, q_si, rtol=1e-9,
                                   err_msg="V/kA scaling must match SI reference")


class TestUnitScaling_MixedPerPhase:
    """Different units for different phases — each channel carries its own scale."""

    def test_mixed_per_phase_scales_match_si(self):
        # Phase 1: kV voltage, A current (scale 1000/1)
        # Phase 2: V  voltage, kA current (scale 1/1000)
        # Phase 3: kV voltage, kA current (scale 1000/1000)
        t = _time()
        v1_si = _sinusoid(141.421, 0.0)
        v2_si = _sinusoid(141.421, -120.0)
        v3_si = _sinusoid(141.421, 120.0)
        i1_si = _sinusoid(7.071, -30.0)
        i2_si = _sinusoid(7.071, -150.0)
        i3_si = _sinusoid(7.071, 90.0)

        p_si = np.nanmean(_steady(_evaluate(OP_ACTIVE_POWER, t, v1_si, i1_si, v2_si, i2_si, v3_si, i3_si)))
        s_si = np.nanmean(_steady(_evaluate(OP_APPARENT_POWER, t, v1_si, i1_si, v2_si, i2_si, v3_si, i3_si)))

        result_p = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1_si / 1000.0, 1000.0,   i1_si,          1.0,    # ph1: kV / A
            v2_si,          1.0,       i2_si / 1000.0, 1000.0, # ph2: V / kA
            v3_si / 1000.0, 1000.0,   i3_si / 1000.0, 1000.0, # ph3: kV / kA
        )
        result_s = evaluate_three_phase_power_channel(
            OP_APPARENT_POWER, t,
            v1_si / 1000.0, 1000.0,   i1_si,          1.0,
            v2_si,          1.0,       i2_si / 1000.0, 1000.0,
            v3_si / 1000.0, 1000.0,   i3_si / 1000.0, 1000.0,
        )
        np.testing.assert_allclose(np.nanmean(_steady(result_p)), p_si, rtol=1e-9,
                                   err_msg="Mixed per-phase P must match SI reference")
        np.testing.assert_allclose(np.nanmean(_steady(result_s)), s_si, rtol=1e-9,
                                   err_msg="Mixed per-phase S must match SI reference")


class TestUnitScaling_DoubleConversionAbsence:
    """Confirm that SI inputs with scale=1.0 and kV inputs with scale=1000.0
    yield identical results — proving conversion happens exactly once."""

    def test_si_scale_1_equals_kv_scale_1000(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)

        # SI path: raw values are SI already, scale=1.0
        p_si = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
        )

        # kV path: divide V by 1000, scale=1000 (net effect identical to SI)
        p_kv = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1 / 1000.0, 1000.0, i1, 1.0,
            v2 / 1000.0, 1000.0, i2, 1.0,
            v3 / 1000.0, 1000.0, i3, 1.0,
        )

        np.testing.assert_array_equal(p_si, p_kv,
                                      err_msg="SI and kV-scaled paths must produce identical arrays")


# ===========================================================================
# ENGINEERING VERIFICATION 2 — Independent numerical equivalence
# ===========================================================================
#
# Method:
#   Build time-domain sinusoids, run evaluate_three_phase_power_channel(),
#   then independently extract phasors via compute_sliding_phasor() and feed
#   RMS magnitudes + angles to three_phase_power() (the scalar reference).
#   Compare P, Q, S at multiple steady-state sample indices.
#
# This verifies that the vectorized evaluator is algebraically identical to
# the scalar domain function — the only path from "raw waveforms" to "phasor
# power" that these tests share is the DFT window algorithm.
# ===========================================================================

import cmath as _cmath

from app.domain.sliding_phasor import compute_sliding_phasor as _csp
from app.domain.power_calculation import three_phase_power as _3pp


def _extract_phasors_at(t, v1, i1, v2, i2, v3, i3):
    """Return six SlidingPhasorResult objects for six channels."""
    return (
        _csp(t, v1, F0_HZ), _csp(t, i1, F0_HZ),
        _csp(t, v2, F0_HZ), _csp(t, i2, F0_HZ),
        _csp(t, v3, F0_HZ), _csp(t, i3, F0_HZ),
    )


def _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx: int):
    """Call three_phase_power() with phasor magnitudes and angles at `idx`."""
    def _mag_ang(ph):
        c = ph.phasor[idx]
        return abs(c), math.degrees(_cmath.phase(c))
    vm1, va1 = _mag_ang(v1r);  im1, ia1 = _mag_ang(i1r)
    vm2, va2 = _mag_ang(v2r);  im2, ia2 = _mag_ang(i2r)
    vm3, va3 = _mag_ang(v3r);  im3, ia3 = _mag_ang(i3r)
    return _3pp(vm1, va1, im1, ia1,
                vm2, va2, im2, ia2,
                vm3, va3, im3, ia3)


class TestNumericalEquivalenceBalanced:
    """Balanced case at 5000 Hz: evaluator must match three_phase_power() at
    five consecutive steady-state samples."""

    def setup_method(self):
        self.t, self.v1, self.i1, self.v2, self.i2, self.v3, self.i3 = \
            _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        self.phs = _extract_phasors_at(
            self.t, self.v1, self.i1, self.v2, self.i2, self.v3, self.i3)
        self.p_arr = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, self.t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.q_arr = evaluate_three_phase_power_channel(
            OP_REACTIVE_POWER, self.t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.s_arr = evaluate_three_phase_power_channel(
            OP_APPARENT_POWER, self.t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.steady_start = int(FS_HZ / F0_HZ)

    def test_p_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.p_arr[idx], ref.p_watts / 1e6, rtol=1e-10,
                err_msg=f"Balanced P mismatch at sample {idx}")

    def test_q_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.q_arr[idx], ref.q_var / 1e6, rtol=1e-10,
                err_msg=f"Balanced Q mismatch at sample {idx}")

    def test_s_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.s_arr[idx], ref.s_va / 1e6, rtol=1e-10,
                err_msg=f"Balanced S mismatch at sample {idx}")


class TestNumericalEquivalenceUnbalanced:
    """Unbalanced case at 5000 Hz: different V/I magnitudes and PF angles per phase."""

    def setup_method(self):
        t = _time()
        self.t = t
        self.v1 = _sinusoid(141.0,   0.0);    self.i1 = _sinusoid(7.0,   -20.0)
        self.v2 = _sinusoid(130.0, -115.0);   self.i2 = _sinusoid(9.0,  -145.0)
        self.v3 = _sinusoid(152.0,  125.0);   self.i3 = _sinusoid(6.0,   +80.0)
        self.phs = _extract_phasors_at(t, self.v1, self.i1, self.v2, self.i2, self.v3, self.i3)
        self.p_arr = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.q_arr = evaluate_three_phase_power_channel(
            OP_REACTIVE_POWER, t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.s_arr = evaluate_three_phase_power_channel(
            OP_APPARENT_POWER, t,
            self.v1, 1.0, self.i1, 1.0,
            self.v2, 1.0, self.i2, 1.0,
            self.v3, 1.0, self.i3, 1.0,
        )
        self.steady_start = int(FS_HZ / F0_HZ)

    def test_p_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.p_arr[idx], ref.p_watts / 1e6, rtol=1e-10,
                err_msg=f"Unbalanced P mismatch at sample {idx}")

    def test_q_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.q_arr[idx], ref.q_var / 1e6, rtol=1e-10,
                err_msg=f"Unbalanced Q mismatch at sample {idx}")

    def test_s_pointwise_five_samples(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.s_arr[idx], ref.s_va / 1e6, rtol=1e-10,
                err_msg=f"Unbalanced S mismatch at sample {idx}")


class TestNumericalEquivalence4096Hz:
    """Non-integer sampling configuration: 4096 Hz / 50 Hz fundamental.
    4096/50 = 81.92 samples/cycle — non-integer, exercises the irregular
    time-base path in compute_sliding_phasor()."""

    _FS = 4096.0
    _F0 = 50.0
    _N  = int(_FS * 5)   # 5 seconds

    def setup_method(self):
        t = np.arange(self._N, dtype=np.float64) / self._FS
        v_amp = 141.421  # ≈ 100√2 V → V_rms = 100 V
        i_amp = 7.071    # ≈ 5√2 A   → I_rms = 5 A
        v1 = v_amp * np.sin(2 * np.pi * self._F0 * t)
        v2 = v_amp * np.sin(2 * np.pi * self._F0 * t - math.radians(120.0))
        v3 = v_amp * np.sin(2 * np.pi * self._F0 * t + math.radians(120.0))
        i1 = i_amp * np.sin(2 * np.pi * self._F0 * t - math.radians(30.0))
        i2 = i_amp * np.sin(2 * np.pi * self._F0 * t - math.radians(150.0))
        i3 = i_amp * np.sin(2 * np.pi * self._F0 * t + math.radians(90.0))
        self.t, self.v1, self.i1 = t, v1, i1
        self.v2, self.i2, self.v3, self.i3 = v2, i2, v3, i3
        self.phs = _extract_phasors_at(t, v1, i1, v2, i2, v3, i3)
        self.p_arr = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
            nominal_frequency_hz=self._F0,
        )
        self.q_arr = evaluate_three_phase_power_channel(
            OP_REACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
            nominal_frequency_hz=self._F0,
        )
        self.s_arr = evaluate_three_phase_power_channel(
            OP_APPARENT_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
            nominal_frequency_hz=self._F0,
        )
        self.steady_start = int(self._FS / self._F0) + 1  # one cycle + 1

    def test_p_pointwise_five_samples_4096hz(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.p_arr[idx], ref.p_watts / 1e6, rtol=1e-8,
                err_msg=f"4096 Hz P mismatch at sample {idx}")

    def test_q_pointwise_five_samples_4096hz(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.q_arr[idx], ref.q_var / 1e6, rtol=1e-8,
                err_msg=f"4096 Hz Q mismatch at sample {idx}")

    def test_s_pointwise_five_samples_4096hz(self):
        v1r, i1r, v2r, i2r, v3r, i3r = self.phs
        for idx in range(self.steady_start, self.steady_start + 5):
            ref = _scalar_power_at(v1r, i1r, v2r, i2r, v3r, i3r, idx)
            np.testing.assert_allclose(
                self.s_arr[idx], ref.s_va / 1e6, rtol=1e-8,
                err_msg=f"4096 Hz S mismatch at sample {idx}")

    def test_steady_state_golden_p_4096hz(self):
        """P_total ≈ 750√3 W = 1299.038 W regardless of sampling rate."""
        steady = _steady(self.p_arr)
        assert np.nanmean(steady) * 1e6 == pytest.approx(750.0 * math.sqrt(3), rel=0.001)

    def test_steady_state_golden_q_4096hz(self):
        steady = _steady(self.q_arr)
        assert np.nanmean(steady) * 1e6 == pytest.approx(750.0, rel=0.001)

    def test_steady_state_golden_s_4096hz(self):
        steady = _steady(self.s_arr)
        assert np.nanmean(steady) * 1e6 == pytest.approx(1500.0, rel=0.001)


# ===========================================================================
# ENGINEERING VERIFICATION 3 — Six-channel timebase contract
# ===========================================================================
#
# evaluate_three_phase_power_channel() assumes that the caller has already
# proven all six channels share a common physical timebase.  The function
# accepts a SINGLE `time` array; it does NOT call timebases_aligned() itself.
#
# Timebase enforcement is the sole responsibility of the E-2B service layer,
# which must replicate the existing single-phase pattern:
#
#   1. For each of the six channels, resolve its (time, start_epoch,
#      reference_source_id) from the source/calculated-channel registry.
#   2. Call timebases_aligned(ref_a, elapsed_a, epoch_a, ref_b, elapsed_b,
#      epoch_b) for each pair against a designated reference channel (e.g.
#      V1).  A pair fails if:
#        a. reference_source_ids differ AND
#        b. start epochs are unknown (None), OR the sample-by-sample
#           absolute-instant difference exceeds TIME_ALIGNMENT_TOLERANCE_SECONDS
#           (300 ns).
#   3. If any pair fails alignment, raise IncompatibleTimeBaseError — never
#      pass misaligned channels to the evaluator.
#   4. The same tolerance constant (300 ns) and epoch-diff formula
#      (elapsed_diff + epoch_diff vs 0) must be used — no separate algorithm
#      is introduced for three-phase.
#   5. The evaluator never resamples, interpolates, or crops to overlap
#      (per the owner's explicit timebase guardrail).
#
# The tests below verify the evaluator's single-time-array assumption and
# confirm it does NOT embed any alignment logic (that is the service layer's
# role).  Alignment-correctness itself is already tested by
# test_calculated_channel_power.py::TestPowerChannelCrossSourceGuard (service
# layer path) and by the timebases_aligned() unit tests.
# ===========================================================================

class TestTimbaseContract_SingleArray:
    """The evaluator uses one shared time array for all six phasor computations.
    All six calls to compute_sliding_phasor() receive the SAME `time` object."""

    def test_evaluator_accepts_shared_timebase(self):
        """A single time array shared by all six channels produces a valid result."""
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        # Pass the SAME t to all six channels — this is the design contract
        result = evaluate_three_phase_power_channel(
            OP_ACTIVE_POWER, t,
            v1, 1.0, i1, 1.0,
            v2, 1.0, i2, 1.0,
            v3, 1.0, i3, 1.0,
        )
        assert result.shape == t.shape
        assert np.isfinite(_steady(result)).all()

    def test_output_length_equals_input_time_length(self):
        t, v1, i1, v2, i2, v3, i3 = _balanced_inputs(100.0, 5.0, pf_angle_deg=30.0)
        for op in (OP_ACTIVE_POWER, OP_REACTIVE_POWER, OP_APPARENT_POWER):
            result = evaluate_three_phase_power_channel(
                op, t,
                v1, 1.0, i1, 1.0,
                v2, 1.0, i2, 1.0,
                v3, 1.0, i3, 1.0,
            )
            assert len(result) == len(t), f"op={op}: output length must equal time array length"

    def test_300ns_constant_is_available_for_e2b(self):
        """TIME_ALIGNMENT_TOLERANCE_SECONDS (300 ns) must remain importable for E-2B."""
        from app.domain.calculated_channel import TIME_ALIGNMENT_TOLERANCE_SECONDS
        assert TIME_ALIGNMENT_TOLERANCE_SECONDS == pytest.approx(3e-7, rel=1e-9)

    def test_timebases_aligned_is_importable_for_e2b(self):
        """timebases_aligned() must remain importable and callable for E-2B."""
        from app.domain.calculated_channel import timebases_aligned
        import numpy as np
        t = np.arange(100, dtype=np.float64) / 5000.0
        # Same reference_source_id — trivially aligned
        assert timebases_aligned("src1", t, None, "src1", t, None) is True
        # Different source, no epoch — cannot prove alignment → False
        assert timebases_aligned("src1", t, None, "src2", t, None) is False
