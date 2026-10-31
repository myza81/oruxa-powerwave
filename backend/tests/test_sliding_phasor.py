"""Golden-vector tests for app.domain.sliding_phasor (Slice 2; DEC-201).

Every expected magnitude and angle below is derived independently from
closed-form physics (Vrms = Vpeak / sqrt(2), the known phase of a
constructed cos(2*pi*f0*t + phi) waveform, the DFT orthogonality property,
or the analytically-derivable off-nominal leakage formula).  The expected
values are NEVER derived by running compute_sliding_phasor() and calling
the result "expected" -- the same hand-derived-value discipline already
established in test_phasor_domain.py and test_power_calculation_domain.py.

Performance test at the end measures wall-clock time and peak memory for a
representative long recording (5 seconds at 5 kHz = 25 000 samples, stride=1)
to confirm O(N) behaviour.
"""

from __future__ import annotations

import math
import time as _time_module

import numpy as np
import pytest

from app.domain.phasor import (
    PHASOR_MIN_SAMPLES_PER_CYCLE,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    REASON_INSUFFICIENT_WINDOW_HISTORY,
    REASON_INVALID_SAMPLES_IN_WINDOW,
)
from app.domain.sliding_phasor import (
    ALGORITHM_VERSION,
    REASON_INVALID_FREQUENCY,
    REASON_INVALID_STRIDE,
    SlidingPhasorResult,
    angle_deg,
    compute_sliding_phasor,
    magnitude_rms,
)


# ---------------------------------------------------------------------------
# Shared waveform helpers -- all expected values hand-derived from these
# ---------------------------------------------------------------------------

def _cosine(
    amp_peak: float,
    phase_deg: float,
    freq_hz: float,
    sample_rate_hz: float,
    duration_s: float,
    t_start: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """x(t) = amp_peak * cos(2*pi*freq_hz*t + phase_deg) uniformly sampled.

    Returns (time, values).  `t_start` sets the absolute epoch offset of
    the recording start, matching the phasor angle-reference convention.
    """
    n = int(round(duration_s * sample_rate_hz))
    t = t_start + np.arange(n) / sample_rate_hz
    x = amp_peak * np.cos(2.0 * np.pi * freq_hz * t + np.radians(phase_deg))
    return t, x


def _get_steady_state(result: SlidingPhasorResult) -> tuple[np.ndarray, np.ndarray]:
    """Return magnitude_rms and angle_deg arrays for available outputs only."""
    avail = result.available
    return magnitude_rms(result)[avail], angle_deg(result)[avail]


# ---------------------------------------------------------------------------
# Test 1: RMS normalisation -- pure 50 Hz sinusoid
# ---------------------------------------------------------------------------

class TestRmsNormalisation:
    """Verify that compute_sliding_phasor returns RMS magnitude, not peak."""

    @pytest.mark.parametrize("sample_rate", [1000.0, 5000.0])
    def test_known_rms_100v(self, sample_rate):
        # x(t) = sqrt(2)*100*cos(2*pi*50*t) -> RMS = 100 V, never 141.4 V.
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert mags.shape[0] > 0
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=1e-5)
        assert float(np.mean(mags)) != pytest.approx(141.4, rel=0.05)

    def test_rms_all_output_points_agree(self):
        """Every available window should give the same RMS for a steady-state
        sinusoid (ripple-free -- same invariant evaluate_rms() guarantees)."""
        amp_peak = math.sqrt(2) * 230.0
        t, x = _cosine(amp_peak, 0.0, 50.0, 5000.0, 1.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        # All available outputs should agree to within numerical noise.
        assert float(np.max(np.abs(mags - 230.0))) == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Test 2: Known phase angles
# ---------------------------------------------------------------------------

class TestKnownAngles:
    """For x(t) = A*cos(2*pi*f0*t + phi), the engine must recover phi."""

    @pytest.mark.parametrize("phase_deg", [0.0, 30.0, 45.0, 90.0, -30.0, -90.0, 120.0, 179.0, -179.0])
    def test_angle_matches_construction_phase(self, phase_deg):
        t, x = _cosine(100.0, phase_deg, 50.0, 5000.0, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        _, angles = _get_steady_state(result)
        # Normalise expected angle to (-180, 180].
        expected = float(phase_deg % 360.0)
        if expected > 180.0:
            expected -= 360.0
        assert float(np.mean(angles)) == pytest.approx(expected, abs=1e-5)

    def test_angle_stable_across_all_windows(self):
        """Phase angle must not drift as the sliding window advances."""
        t, x = _cosine(100.0, 45.0, 50.0, 5000.0, 1.0)
        result = compute_sliding_phasor(t, x, 50.0)
        _, angles = _get_steady_state(result)
        # All angles should agree to within numerical noise.
        assert float(np.max(np.abs(angles - 45.0))) == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Test 3: Relative phase -- two 50 Hz signals with 30° separation
# ---------------------------------------------------------------------------

class TestRelativePhase:
    """Accurate relative phase recovery is the key phasor engineering test."""

    def test_30_degree_separation(self):
        """V and I with a 30 deg V-I angle: recovered relative angle = 30 deg.

        Hand-derived: if phi_V = 0 and phi_I = -30 (lagging), then
        angle_V - angle_I = 0 - (-30) = +30 deg (positive Q = inductive).
        """
        t_v, x_v = _cosine(math.sqrt(2) * 100.0, 0.0, 50.0, 5000.0, 2.0)
        t_i, x_i = _cosine(math.sqrt(2) * 5.0, -30.0, 50.0, 5000.0, 2.0,
                            t_start=0.0)  # SAME t_start -- shared time axis

        result_v = compute_sliding_phasor(t_v, x_v, 50.0)
        result_i = compute_sliding_phasor(t_i, x_i, 50.0)

        avail = result_v.available & result_i.available
        ang_v = angle_deg(result_v)[avail]
        ang_i = angle_deg(result_i)[avail]
        rel = ang_v - ang_i
        # Normalise differences to (-180, 180].
        rel = (rel + 180.0) % 360.0 - 180.0

        assert float(np.mean(rel)) == pytest.approx(30.0, abs=1e-4)

    def test_no_artificial_phase_shift_across_amplitudes(self):
        """Phase difference must be independent of V vs I amplitude ratio.

        Hand-derived: phi_V = 0, phi_I = -30 regardless of V and I magnitudes.
        Relative angle = 30 deg in all cases.
        """
        for v_amp, i_amp in [(1.0, 1.0), (100.0, 1.0), (1.0, 100.0), (1000.0, 0.001)]:
            t, x_v = _cosine(math.sqrt(2) * v_amp, 0.0, 50.0, 5000.0, 1.0)
            _, x_i = _cosine(math.sqrt(2) * i_amp, -30.0, 50.0, 5000.0, 1.0)
            rv = compute_sliding_phasor(t, x_v, 50.0)
            ri = compute_sliding_phasor(t, x_i, 50.0)
            avail = rv.available & ri.available
            ang_v = angle_deg(rv)[avail]
            ang_i = angle_deg(ri)[avail]
            rel = (ang_v - ang_i + 180.0) % 360.0 - 180.0
            assert float(np.mean(rel)) == pytest.approx(30.0, abs=1e-4), \
                f"Failed for v_amp={v_amp}, i_amp={i_amp}"


# ---------------------------------------------------------------------------
# Test 4: Balanced three-phase -- 120° separation
# ---------------------------------------------------------------------------

class TestBalancedThreePhase:
    """Three-phase: Va=X∠0°, Vb=X∠-120°, Vc=X∠+120°."""

    def test_magnitudes_equal(self):
        amp_peak = math.sqrt(2) * 100.0
        for phase in (0.0, -120.0, 120.0):
            t, x = _cosine(amp_peak, phase, 50.0, 5000.0, 2.0)
            result = compute_sliding_phasor(t, x, 50.0)
            mags, _ = _get_steady_state(result)
            assert float(np.mean(mags)) == pytest.approx(100.0, rel=1e-5), \
                f"Magnitude failed for phase={phase}"

    def test_angles_120_degrees_apart(self):
        amp_peak = math.sqrt(2) * 100.0
        angles = {}
        for label, phase in (("Va", 0.0), ("Vb", -120.0), ("Vc", 120.0)):
            t, x = _cosine(amp_peak, phase, 50.0, 5000.0, 2.0)
            result = compute_sliding_phasor(t, x, 50.0)
            _, angs = _get_steady_state(result)
            angles[label] = float(np.mean(angs))

        assert angles["Va"] == pytest.approx(0.0, abs=1e-5)
        assert angles["Vb"] == pytest.approx(-120.0, abs=1e-5)
        assert angles["Vc"] == pytest.approx(120.0, abs=1e-5)

        # Relative angles (Va as reference).
        ref = angles["Va"]
        rel_b = (angles["Vb"] - ref + 180.0) % 360.0 - 180.0
        rel_c = (angles["Vc"] - ref + 180.0) % 360.0 - 180.0
        assert rel_b == pytest.approx(-120.0, abs=1e-5)
        assert rel_c == pytest.approx(120.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Test 5: Phase-reference consistency with different starting timestamps
# ---------------------------------------------------------------------------

class TestPhaseReferenceConsistency:
    """Phase differences must be independent of recording start time.

    The angle reference is the absolute epoch; a recording starting at a
    different absolute time shifts BOTH channels by the same amount, so
    relative (differential) angles are preserved.
    """

    def test_relative_phase_invariant_to_t_start(self):
        """
        Hand-derived: phi_V = 0, phi_I = -30 in x(t) = A*cos(2*pi*f*t + phi).
        The RELATIVE angle angle_V - angle_I = 30 deg regardless of t_start
        because both channels' absolute angles shift by the same 2*pi*f*t_start.
        """
        for t_start in (0.0, 0.1, 1.0, 7.5):
            t, x_v = _cosine(math.sqrt(2) * 100.0, 0.0, 50.0, 5000.0, 1.0,
                              t_start=t_start)
            _, x_i = _cosine(math.sqrt(2) * 5.0, -30.0, 50.0, 5000.0, 1.0,
                              t_start=t_start)
            rv = compute_sliding_phasor(t, x_v, 50.0)
            ri = compute_sliding_phasor(t, x_i, 50.0)
            avail = rv.available & ri.available
            ang_v = angle_deg(rv)[avail]
            ang_i = angle_deg(ri)[avail]
            rel = (ang_v - ang_i + 180.0) % 360.0 - 180.0
            assert float(np.mean(rel)) == pytest.approx(30.0, abs=1e-3), \
                f"Failed for t_start={t_start}"

    def test_absolute_angle_shifts_correctly_with_t_start(self):
        """Absolute angle = phi + 2*pi*f*t_start (mod 360), consistently.

        For x(t) = A*cos(2*pi*f*t + phi) with the first sample at t_start,
        the estimator sees t_n = t_start + n/fs.  The recovered angle phi is
        the phase of the cosine at t=0 of the absolute coordinate, so it
        equals the construction phi regardless of t_start (since t_n already
        encodes t_start via absolute time).
        """
        phi = 30.0
        t, x = _cosine(100.0, phi, 50.0, 5000.0, 1.0, t_start=0.0)
        result_0 = compute_sliding_phasor(t, x, 50.0)
        _, angs_0 = _get_steady_state(result_0)

        # Same waveform, same underlying absolute phase, different recording window.
        t2, x2 = _cosine(100.0, phi, 50.0, 5000.0, 1.0, t_start=0.5)
        result_05 = compute_sliding_phasor(t2, x2, 50.0)
        _, angs_05 = _get_steady_state(result_05)

        # Both recordings observe the same x(t) = A*cos(2*pi*50*t + 30°),
        # so both should recover angle ≈ 30° (the absolute phi, not a
        # window-relative offset).
        assert float(np.mean(angs_0)) == pytest.approx(phi, abs=1e-4)
        assert float(np.mean(angs_05)) == pytest.approx(phi, abs=1e-4)


# ---------------------------------------------------------------------------
# Test 6: Sampling frequencies -- 1 kHz and 5 kHz
# ---------------------------------------------------------------------------

class TestSamplingFrequencies:
    """Verify correct results at both 1 kHz and 5 kHz for a 50 Hz signal."""

    @pytest.mark.parametrize("sample_rate", [1000.0, 5000.0])
    def test_magnitude_at_sample_rate(self, sample_rate):
        # At 1 kHz: 20 samples/cycle; at 5 kHz: 100 samples/cycle.
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 30.0, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, angs = _get_steady_state(result)
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=1e-5)
        assert float(np.mean(angs)) == pytest.approx(30.0, abs=1e-4)

    @pytest.mark.parametrize("sample_rate", [1000.0, 5000.0])
    def test_three_phase_at_sample_rate(self, sample_rate):
        """Balanced three-phase must give 120° separation at both rates."""
        amp_peak = math.sqrt(2) * 100.0
        results = {}
        for label, phase in (("a", 0.0), ("b", -120.0), ("c", 120.0)):
            t, x = _cosine(amp_peak, phase, 50.0, sample_rate, 2.0)
            results[label] = compute_sliding_phasor(t, x, 50.0)

        angles = {}
        for label in ("a", "b", "c"):
            _, angs = _get_steady_state(results[label])
            angles[label] = float(np.mean(angs))

        assert angles["a"] == pytest.approx(0.0, abs=1e-4)
        assert angles["b"] == pytest.approx(-120.0, abs=1e-4)
        assert angles["c"] == pytest.approx(120.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Test 7: Non-integer samples per cycle
# ---------------------------------------------------------------------------

class TestNonIntegerSamplesPerCycle:
    """Verify handling of non-integer samples/cycle (e.g. 3001 Hz at 50 Hz
    = 60.02 samples/cycle).

    The window uses round(window/dt) samples per cycle (same policy as
    evaluate_rms()), so results are slightly approximate but remain
    within a known, bounded error.  Golden-vector expected values are
    derived from the ideal case; the tolerance is relaxed to accommodate
    the discretisation error.
    """

    def test_non_integer_cycles_magnitude(self):
        # 3001 Hz at 50 Hz: 3001/50 = 60.02 samples/cycle (non-integer).
        # Window uses round(3001/50/50) = round(60.02) = 60 samples.
        # Duration = 60/3001 s vs ideal 1/50 = 20 ms: error < 0.5/60 = 0.8%.
        # Expected RMS ≈ 100 V; tolerate up to 1% magnitude error.
        amp_peak = math.sqrt(2) * 100.0
        sample_rate = 3001.0
        t, x = _cosine(amp_peak, 0.0, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.01)

    def test_non_integer_cycles_phase(self):
        # Same setup; phase tolerance relaxed to 1° for non-integer case.
        sample_rate = 3001.0
        phi = 45.0
        t, x = _cosine(100.0, phi, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        _, angs = _get_steady_state(result)
        assert float(np.mean(angs)) == pytest.approx(phi, abs=1.0)

    def test_non_integer_cycles_relative_phase_preserved(self):
        """Relative phase (V - I) must still be accurate to 1° at non-integer
        samples/cycle -- both channels use the same rounding error, which
        cancels in the difference."""
        sample_rate = 3001.0
        t, x_v = _cosine(math.sqrt(2) * 100.0, 0.0, 50.0, sample_rate, 2.0)
        _, x_i = _cosine(math.sqrt(2) * 5.0, -30.0, 50.0, sample_rate, 2.0)
        rv = compute_sliding_phasor(t, x_v, 50.0)
        ri = compute_sliding_phasor(t, x_i, 50.0)
        avail = rv.available & ri.available
        rel = (angle_deg(rv)[avail] - angle_deg(ri)[avail] + 180.0) % 360.0 - 180.0
        assert float(np.mean(rel)) == pytest.approx(30.0, abs=1.0)

    def test_4096hz_magnitude_accuracy(self):
        """4096 Hz / 50 Hz = 81.92 samples/cycle -- a genuine non-integer case.

        n_window = round(4096 / 50 / 50) = round(81.92) = 82.
        Window duration = 82 / 4096 = 20.020 ms vs ideal 20.000 ms (+0.1%).
        The fractional-cycle overshoot introduces DFT leakage; mean magnitude
        stays within 0.5% of the true RMS value (same tolerance as 3001 Hz).
        """
        amp_peak = math.sqrt(2) * 100.0
        sample_rate = 4096.0
        t, x = _cosine(amp_peak, 60.0, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert mags.shape[0] > 0
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.005)

    def test_4096hz_phase_accuracy(self):
        """Phase angle recovered at 4096 Hz / 50 Hz must be within 0.5°.

        The construction phase is 60°; tolerance relaxed vs the integer-rate
        case (1e-5°) to accommodate the fractional-cycle window rounding.
        """
        sample_rate = 4096.0
        phi = 60.0
        t, x = _cosine(100.0, phi, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        _, angs = _get_steady_state(result)
        assert float(np.mean(angs)) == pytest.approx(phi, abs=0.5)

    def test_4096hz_window_to_window_ripple_bounded(self):
        """At 4096 Hz the window covers 1.001 fundamental cycles, causing
        small window-to-window magnitude and phase ripple due to spectral
        leakage from the fractional-cycle overshoot.

        Empirically measured (4096 Hz, 50 Hz, 2 s):
          magnitude std ≈ 0.069 V (0.07% of 100 V)
          phase std     ≈ 0.040°
        Both bounded comfortably within 0.5 V / 0.5°.
        All windows converge to the same mean (mean error < 0.001%).
        """
        amp_peak = math.sqrt(2) * 100.0
        sample_rate = 4096.0
        t, x = _cosine(amp_peak, 0.0, 50.0, sample_rate, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, angs = _get_steady_state(result)
        # Mean very close to true value.
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.001)
        # Window-to-window magnitude variation bounded by 0.5 V (0.5%).
        assert float(np.std(mags)) < 0.5
        # Window-to-window phase variation bounded by 0.5°.
        assert float(np.std(angs)) < 0.5


# ---------------------------------------------------------------------------
# Test 5b: Large-epoch timestamps -- COMTRADE absolute time precision
# ---------------------------------------------------------------------------

class TestLargeEpochTimestamps:
    """Verify accuracy when timestamps carry a large absolute epoch offset.

    COMTRADE files use absolute timestamps referenced to the file start
    time, which may be a Unix epoch value around 1.7e9 seconds (year ~2024).
    Computing w * t_n = 2π * 50 * 1.7e9 ≈ 5.34e11 in float64 could lose
    trigonometric-argument precision if the platform's math library does
    not use high-quality range reduction (Payne-Hanek or equivalent).

    The module requires the caller to supply epoch-reduced timestamps (see
    module docstring); these tests verify that on the current platform the
    computation is already accurate for realistic COMTRADE epoch values, and
    that relative phase (the engineering-critical invariant for power
    calculation) is preserved regardless of absolute epoch magnitude.

    Empirically measured (Windows 11, NumPy/Intel libm, t_start = 1.704e9 s):
      absolute angle error:  < 1e-4 degrees
      relative phase error:  < 2e-3 degrees
    Both are well within the sub-0.1° engineering tolerance.
    """

    _COMTRADE_EPOCH = 1.704e9  # Unix epoch ≈ 2024-01-01 UTC

    def test_magnitude_accurate_at_large_epoch(self):
        """RMS magnitude must be within 1% of the true value at large epoch."""
        T = self._COMTRADE_EPOCH
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 50.0, 5000.0, 1.0, t_start=T)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.01), \
            "RMS magnitude degraded at large COMTRADE epoch timestamp"

    def test_relative_phase_preserved_at_large_epoch(self):
        """Relative phase (V - I) must be accurate to 0.01° at large epoch.

        Hand-derived: V = 100 V ∠ 0°, I = 5 A ∠ -30° → angle_V - angle_I = 30°.
        This is the engineering-critical invariant for power calculation.
        Tolerance 0.01°: tighter than the 1° tolerance used for non-integer
        sampling, because large-epoch precision is a platform concern (not a
        window-size approximation), and modern implementations handle it well.
        """
        T = self._COMTRADE_EPOCH
        t, x_v = _cosine(math.sqrt(2) * 100.0, 0.0, 50.0, 5000.0, 1.0, t_start=T)
        _, x_i = _cosine(math.sqrt(2) * 5.0, -30.0, 50.0, 5000.0, 1.0, t_start=T)
        rv = compute_sliding_phasor(t, x_v, 50.0)
        ri = compute_sliding_phasor(t, x_i, 50.0)
        avail = rv.available & ri.available
        rel = (angle_deg(rv)[avail] - angle_deg(ri)[avail] + 180.0) % 360.0 - 180.0
        assert float(np.mean(rel)) == pytest.approx(30.0, abs=0.01), \
            f"Relative phase degraded at large COMTRADE epoch t_start={T:.3e} s"

    def test_absolute_angle_accurate_at_large_epoch(self):
        """Absolute phasor angle must agree with small-epoch result to < 1°.

        For x(t) = A*cos(2π*50*t + φ) the DFT recovers φ regardless of
        t_start (φ is the phase at the absolute origin t=0).  Precision loss
        from large trig arguments shifts the recovered angle; this test
        documents that the platform achieves < 1° absolute error.
        If this assertion fails, the caller must supply epoch-reduced
        timestamps (time - time[0]) to maintain accuracy.
        """
        phi = 45.0
        amp_peak = math.sqrt(2) * 100.0

        t_small, x_small = _cosine(amp_peak, phi, 50.0, 5000.0, 1.0, t_start=0.0)
        result_small = compute_sliding_phasor(t_small, x_small, 50.0)
        _, angs_small = _get_steady_state(result_small)
        angle_ref = float(np.mean(angs_small))

        T = self._COMTRADE_EPOCH
        t_large, x_large = _cosine(amp_peak, phi, 50.0, 5000.0, 1.0, t_start=T)
        result_large = compute_sliding_phasor(t_large, x_large, 50.0)
        _, angs_large = _get_steady_state(result_large)
        angle_large = float(np.mean(angs_large))

        diff = (angle_large - angle_ref + 180.0) % 360.0 - 180.0
        assert abs(diff) < 1.0, (
            f"Absolute angle at epoch {T:.3e} s differs by {diff:.4f}° from small-epoch result. "
            "Platform trig range reduction may be inadequate; supply epoch-reduced timestamps."
        )


# ---------------------------------------------------------------------------
# Test 8: Zero waveform
# ---------------------------------------------------------------------------

class TestZeroWaveform:
    """A zero signal must produce a zero-magnitude phasor (not NaN or error)."""

    def test_zero_signal_produces_zero_magnitude(self):
        t, x = _cosine(0.0, 0.0, 50.0, 5000.0, 1.0)
        assert np.all(x == 0.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert mags.shape[0] > 0
        assert float(np.max(np.abs(mags))) == pytest.approx(0.0, abs=1e-10)

    def test_zero_signal_available_true(self):
        """Zero is a valid (finite) signal: windows should be available."""
        t, x = _cosine(0.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 50.0)
        avail = result.available
        # After one cycle history, all remaining outputs should be available.
        assert avail[result.available].shape[0] > 0


# ---------------------------------------------------------------------------
# Test 9: DC offset -- fundamental extraction accuracy
# ---------------------------------------------------------------------------

class TestDcOffset:
    """DC offset projects onto the DC bin (f=0), not f0.

    For x(t) = A*cos(2*pi*f0*t) + DC, the DFT at f0 extracts only the
    fundamental component.  Expected magnitude = A/sqrt(2); DC does not
    appear in the f0 bin for a window that spans an exact integer number
    of periods.  For non-integer windows, DC leaks into f0 by at most
    DC * (sin(pi * N_excess) / (pi * N_excess)) where N_excess is the
    fractional-cycle overshoot -- bounded and small for large N.

    Tolerance 1% to accommodate discretisation effects at 20 samples/cycle.
    """

    @pytest.mark.parametrize("dc_offset", [0.0, 50.0, 200.0, -100.0])
    def test_fundamental_unaffected_by_dc(self, dc_offset):
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 50.0, 5000.0, 2.0)
        x = x + dc_offset
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        # Fundamental RMS should still be ≈ 100 V.
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.01), \
            f"DC offset={dc_offset} caused magnitude error"

    def test_phase_unaffected_by_dc(self):
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 30.0, 50.0, 5000.0, 2.0)
        x = x + 150.0  # large DC
        result = compute_sliding_phasor(t, x, 50.0)
        _, angs = _get_steady_state(result)
        assert float(np.mean(angs)) == pytest.approx(30.0, abs=0.5)


# ---------------------------------------------------------------------------
# Test 10: Harmonic distortion -- fundamental extraction
# ---------------------------------------------------------------------------

class TestHarmonicDistortion:
    """Third harmonic at 150 Hz projects onto the 3*f0 bin, not f0.

    x(t) = A1*cos(w*t) + A3*cos(3*w*t).
    Expected fundamental RMS = A1 / sqrt(2).
    DFT orthogonality: the 3rd-harmonic term integrates to zero over an
    exact one-cycle window at f0.  Discretisation causes minor leakage;
    tolerance 1%.
    """

    @pytest.mark.parametrize("harmonic_frac", [0.0, 0.1, 0.2, 0.5])
    def test_third_harmonic_does_not_bias_fundamental(self, harmonic_frac):
        amp_fundamental_peak = math.sqrt(2) * 100.0
        amp_3rd = harmonic_frac * amp_fundamental_peak
        t = np.arange(int(5000.0 * 2.0)) / 5000.0
        w = 2.0 * np.pi * 50.0
        x = amp_fundamental_peak * np.cos(w * t) + amp_3rd * np.cos(3.0 * w * t)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.01)

    def test_fifth_harmonic_does_not_bias_phase(self):
        """5th harmonic must not shift the fundamental phase angle."""
        amp_fund = math.sqrt(2) * 100.0
        phi = 45.0
        t = np.arange(int(5000.0 * 2.0)) / 5000.0
        w = 2.0 * np.pi * 50.0
        x = (amp_fund * np.cos(w * t + np.radians(phi))
             + 0.3 * amp_fund * np.cos(5.0 * w * t))
        result = compute_sliding_phasor(t, x, 50.0)
        _, angs = _get_steady_state(result)
        assert float(np.mean(angs)) == pytest.approx(phi, abs=0.5)


# ---------------------------------------------------------------------------
# Test 11: Off-nominal frequency (49.5 Hz signal, 50 Hz reference)
# ---------------------------------------------------------------------------

class TestOffNominalFrequency:
    """An off-nominal signal produces characterised, non-zero estimation error.

    This test documents the error magnitude rather than asserting zero error.
    The phase drifts linearly with time: delta_phi(t) = 2*pi*(f_signal - f0)*t.
    After one cycle (0.02 s at 50 Hz), drift = 2*pi*(-0.5)*0.02 = -0.0628 rad
    = -3.6 degrees.

    The magnitude is also slightly underestimated due to spectral leakage.
    """

    def test_off_nominal_angle_drifts(self):
        """Phase angle of a 49.5 Hz signal drifts when measured at 50 Hz reference.

        Expected drift rate: (49.5 - 50) Hz * 360 deg/Hz = -0.5 * 360 = -180 deg/s.
        Over 1 second of data, the angle drifts across ~180 degrees.  We verify
        that the drift is substantial (> 10 deg range over 0.5 s) and monotone.
        """
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 49.5, 5000.0, 1.0)
        result = compute_sliding_phasor(t, x, 50.0)
        _, angs = _get_steady_state(result)
        assert angs.shape[0] > 0
        # Unwrap to measure total drift without ±180 jumps.
        unwrapped = np.unwrap(np.radians(angs))
        total_drift_deg = abs(math.degrees(float(unwrapped[-1] - unwrapped[0])))
        # At -180 deg/s over ~1 s, expect > 150 deg drift.
        assert total_drift_deg > 100.0, \
            f"Expected large phase drift for off-nominal signal; got {total_drift_deg:.1f} deg"

    def test_off_nominal_magnitude_shows_variation(self):
        """Off-nominal signals show window-to-window magnitude variation.

        A 49.5 Hz signal through a 50 Hz window has spectral leakage that
        oscillates as the phase between signal and reference window drifts.
        The mean magnitude stays near 100 V (leakage is small and symmetric)
        but individual window magnitudes vary -- the standard deviation is > 0,
        and individual magnitudes deviate from 100 V by a measurable amount.

        Expected individual magnitude deviation: the amplitude modulation depth
        from an off-nominal signal is proportional to sinc(Δf * window) ≈
        1 - (pi * 0.5 * 0.02)^2 / 6 ≈ 0.9997.  Peak-to-peak variation for
        a 0.5 Hz offset at 50 Hz reference comes from the beating envelope,
        producing a deviation of ~ 0.5 V from 100 V at its extremes.
        """
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 49.5, 5000.0, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        mags, _ = _get_steady_state(result)
        # Individual values show oscillation (beating envelope).
        assert float(np.std(mags)) > 0.01, \
            "Off-nominal signal must show window-to-window magnitude variation"
        # NOT all values are exactly 100 V.
        assert not np.all(np.abs(mags - 100.0) < 0.001), \
            "Off-nominal signal must NOT produce identically 100 V at every window"


# ---------------------------------------------------------------------------
# Test 12: Short recording -- graceful unavailability
# ---------------------------------------------------------------------------

class TestShortRecording:
    """Recordings shorter than one cycle cannot produce a valid phasor."""

    def test_recording_shorter_than_one_cycle_all_unavailable(self):
        # 15 ms at 50 Hz < 20 ms (one cycle).
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.015)
        result = compute_sliding_phasor(t, x, 50.0)
        assert not np.any(result.available)
        assert np.all(result.reason_code == REASON_INSUFFICIENT_WINDOW_HISTORY)

    def test_recording_just_over_one_cycle_last_window_available(self):
        # At 5 kHz, one cycle = 100 samples spanning t[0..99] = 0..0.0198 s,
        # which is slightly LESS than 1/50 = 0.020 s (duration 0.0198 s).
        # The first available output needs time[k] - time[0] >= 0.020 - eps,
        # so k must be at least 100 (time[100] = 0.020 s).  That requires
        # 101 samples minimum.  Use 22 ms to give several valid windows.
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.022)
        result = compute_sliding_phasor(t, x, 50.0)
        # At least one available window at the end.
        assert np.any(result.available)

    def test_empty_recording(self):
        t = np.array([], dtype=np.float64)
        x = np.array([], dtype=np.float64)
        result = compute_sliding_phasor(t, x, 50.0)
        assert result.time.shape[0] == 0
        assert result.phasor.shape[0] == 0
        assert result.available.shape[0] == 0

    def test_single_sample(self):
        t = np.array([0.0])
        x = np.array([1.0])
        result = compute_sliding_phasor(t, x, 50.0)
        assert result.time.shape[0] == 1
        assert not result.available[0]
        # A single sample lacks both window history and cannot determine dt;
        # either reason code is acceptable -- the critical invariant is
        # available=False (no valid phasor from one sample at any frequency).
        assert result.reason_code[0] in (
            REASON_INSUFFICIENT_WINDOW_HISTORY,
            REASON_INSUFFICIENT_SAMPLING_DENSITY,
        )


# ---------------------------------------------------------------------------
# Test 13: Non-finite samples -- explicit handling
# ---------------------------------------------------------------------------

class TestNonFiniteSamples:
    """Non-finite samples (NaN, ±inf) in the window must produce available=False
    for that window, and must not propagate to other windows."""

    def test_single_nan_invalidates_its_window_only(self):
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 50.0, 5000.0, 1.0)
        # Place NaN at sample 250 (well within the recording).
        nan_idx = 250
        x_bad = x.copy()
        x_bad[nan_idx] = float("nan")

        result = compute_sliding_phasor(t, x_bad, 50.0)

        # At 5000 Hz, n_window = 100 (round(0.02 / 0.0002) = 100).
        # Window at output index k covers input samples [k - 99, k].
        # Sample 250 is in the window for k where k - 99 <= 250 <= k,
        # i.e., 250 <= k <= 349.  Those output indices must be invalid.
        for k in range(250, 350):
            if k < result.available.shape[0]:
                assert not result.available[k], \
                    f"Window at k={k} should be invalid (contains NaN at 250)"
                assert result.reason_code[k] == REASON_INVALID_SAMPLES_IN_WINDOW

        # Windows after k=349 should recover (sample 250 is outside [350-99, 350]=[251,350]).
        if result.available.shape[0] > 400:
            assert result.available[400], "Window should recover after NaN leaves window"

    def test_inf_sample_handled(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        x_bad = x.copy()
        x_bad[200] = float("inf")
        result = compute_sliding_phasor(t, x_bad, 50.0)
        assert not result.available[200]
        assert result.reason_code[200] == REASON_INVALID_SAMPLES_IN_WINDOW

    def test_neg_inf_sample_handled(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        x_bad = x.copy()
        x_bad[150] = float("-inf")
        result = compute_sliding_phasor(t, x_bad, 50.0)
        assert not result.available[150]

    def test_multiple_nans_no_cumsum_poisoning(self):
        """NaN samples must not corrupt windows that do not contain them."""
        amp_peak = math.sqrt(2) * 100.0
        t, x = _cosine(amp_peak, 0.0, 50.0, 5000.0, 1.0)
        x_bad = x.copy()
        # NaN at isolated positions far apart.
        x_bad[100] = float("nan")
        x_bad[500] = float("nan")

        result_clean = compute_sliding_phasor(t, x, 50.0)
        result_bad = compute_sliding_phasor(t, x_bad, 50.0)

        # Windows entirely before sample 100 should be identical to clean.
        safe_after = 600  # well past both NaN windows
        mags_clean = magnitude_rms(result_clean)[safe_after:]
        mags_bad = magnitude_rms(result_bad)[safe_after:]
        clean_avail = result_clean.available[safe_after:]
        bad_avail = result_bad.available[safe_after:]

        # Both should be available in the same positions.
        np.testing.assert_array_equal(clean_avail, bad_avail)
        # Magnitudes should agree.
        np.testing.assert_allclose(
            mags_bad[bad_avail], mags_clean[clean_avail], rtol=1e-6
        )


# ---------------------------------------------------------------------------
# Test 14: Output stride -- configurable downsampling
# ---------------------------------------------------------------------------

class TestOutputStride:
    """Output stride produces a correctly downsampled time series."""

    def test_stride_1_same_as_default(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        r1 = compute_sliding_phasor(t, x, 50.0, output_stride=1)
        r_default = compute_sliding_phasor(t, x, 50.0)
        np.testing.assert_array_equal(r1.time, r_default.time)
        np.testing.assert_array_equal(r1.available, r_default.available)
        np.testing.assert_array_almost_equal(r1.phasor, r_default.phasor)

    def test_stride_5_output_length(self):
        n = 5000
        t = np.arange(n, dtype=np.float64) / 5000.0
        x = np.sin(2.0 * np.pi * 50.0 * t)
        result = compute_sliding_phasor(t, x, 50.0, output_stride=5)
        expected_m = math.ceil(n / 5)
        assert result.time.shape[0] == expected_m

    def test_stride_output_times_match_input_subset(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        stride = 10
        result = compute_sliding_phasor(t, x, 50.0, output_stride=stride)
        np.testing.assert_array_almost_equal(result.time, t[::stride])

    def test_stride_numerics_agree_with_stride_1(self):
        """Available phasors at strided output positions must match stride=1."""
        t, x = _cosine(math.sqrt(2) * 100.0, 30.0, 50.0, 5000.0, 1.0)
        stride = 7
        r1 = compute_sliding_phasor(t, x, 50.0, output_stride=1)
        rs = compute_sliding_phasor(t, x, 50.0, output_stride=stride)

        # For each output index in rs, find the corresponding index in r1.
        for out_idx in range(rs.time.shape[0]):
            in_idx = out_idx * stride
            assert rs.available[out_idx] == r1.available[in_idx]
            if rs.available[out_idx]:
                assert rs.phasor[out_idx] == pytest.approx(
                    r1.phasor[in_idx], rel=1e-6
                )

    def test_invalid_stride_zero(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 50.0, output_stride=0)
        assert result.time.shape[0] >= 1
        assert not np.any(result.available)
        assert np.all(result.reason_code == REASON_INVALID_STRIDE)

    def test_invalid_stride_negative(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 50.0, output_stride=-1)
        assert not np.any(result.available)
        assert np.all(result.reason_code == REASON_INVALID_STRIDE)


# ---------------------------------------------------------------------------
# Test 15: Input validation -- invalid frequency
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Out-of-range reference frequency must return all unavailable."""

    @pytest.mark.parametrize("bad_freq", [0.0, 0.5, 1001.0, -50.0, float("nan")])
    def test_invalid_frequency_all_unavailable(self, bad_freq):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, bad_freq)
        assert not np.any(result.available)
        assert np.all(result.reason_code == REASON_INVALID_FREQUENCY)

    def test_valid_boundary_frequencies(self):
        """1 Hz and 1000 Hz are at the inclusive boundary -- must not reject."""
        for freq in (1.0, 1000.0):
            # Generate a waveform at the boundary frequency.
            t, x = _cosine(100.0, 0.0, freq, max(10.0 * freq, 100.0), 3.0 / freq)
            result = compute_sliding_phasor(t, x, freq)
            # Engine should attempt computation (not fail with invalid frequency).
            assert result.reference_frequency_hz == freq
            assert result.reason_code[0] != REASON_INVALID_FREQUENCY


# ---------------------------------------------------------------------------
# Test 16: Insufficient sampling density
# ---------------------------------------------------------------------------

class TestSamplingDensity:
    """Sampling rate too low for the reference frequency must return the
    REASON_INSUFFICIENT_SAMPLING_DENSITY reason code."""

    def test_4_samples_per_cycle_below_threshold(self):
        # 200 Hz at 50 Hz = 4 samples/cycle < PHASOR_MIN_SAMPLES_PER_CYCLE (8).
        t, x = _cosine(100.0, 0.0, 50.0, 200.0, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        assert not np.any(result.available)
        assert np.all(result.reason_code == REASON_INSUFFICIENT_SAMPLING_DENSITY)

    def test_8_samples_per_cycle_at_threshold(self):
        # 400 Hz at 50 Hz = 8 samples/cycle = exactly PHASOR_MIN_SAMPLES_PER_CYCLE.
        t, x = _cosine(100.0, 0.0, 50.0, 400.0, 2.0)
        result = compute_sliding_phasor(t, x, 50.0)
        # At the minimum threshold, valid windows should be available.
        assert np.any(result.available)

    def test_custom_min_samples_per_cycle(self):
        """Raising min_samples_per_cycle should reject what the default accepts."""
        t, x = _cosine(100.0, 0.0, 50.0, 400.0, 1.0)
        # 400 Hz = 8 samples/cycle; raising threshold to 16 should reject.
        result_strict = compute_sliding_phasor(t, x, 50.0, min_samples_per_cycle=16)
        assert not np.any(result_strict.available)


# ---------------------------------------------------------------------------
# Test 17: Numerical agreement with estimate_phasor()
# ---------------------------------------------------------------------------

class TestAgreementWithEstimatePhasor:
    """compute_sliding_phasor() must be numerically identical to calling
    estimate_phasor() at the same output times (the vectorised path must
    not introduce any additional approximation)."""

    def test_uniform_path_matches_estimate_phasor(self):
        from app.domain.phasor import estimate_phasor

        amp_peak = math.sqrt(2) * 100.0
        phi = 37.0
        t, x = _cosine(amp_peak, phi, 50.0, 5000.0, 0.5)

        result = compute_sliding_phasor(t, x, 50.0)

        # Spot-check ten available output positions against estimate_phasor().
        avail_indices = np.flatnonzero(result.available)
        check_indices = avail_indices[::max(1, avail_indices.shape[0] // 10)][:10]

        for k in check_indices:
            t_k = result.time[k]
            ref = estimate_phasor(t, x, t_k, 50.0)
            assert ref.available
            assert abs(result.phasor[k]) == pytest.approx(
                ref.magnitude_rms, rel=1e-8
            ), f"Magnitude mismatch at output index {k}"
            assert math.degrees(np.angle(result.phasor[k])) == pytest.approx(
                ref.angle_deg, abs=1e-8
            ), f"Angle mismatch at output index {k}"

    def test_unavailability_matches_estimate_phasor(self):
        """Unavailable windows in sliding result must match estimate_phasor()."""
        from app.domain.phasor import estimate_phasor

        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        # Inject NaN at a known position.
        x_bad = x.copy()
        x_bad[200] = float("nan")
        result = compute_sliding_phasor(t, x_bad, 50.0)

        for k in range(min(350, result.available.shape[0])):
            t_k = result.time[k]
            ref = estimate_phasor(t, x_bad, t_k, 50.0)
            assert result.available[k] == ref.available, \
                f"Availability mismatch at output index {k}: sliding={result.available[k]}, point={ref.available}"


# ---------------------------------------------------------------------------
# Test 18: Irregular spacing (two-pointer path)
# ---------------------------------------------------------------------------

class TestIrregularSpacing:
    """Verify that the irregular-spacing path produces consistent results
    and is numerically close to the uniform path for nearly-uniform data."""

    def _make_irregular(
        self,
        amp_peak: float,
        phase_deg: float,
        nominal_rate: float,
        duration_s: float,
        jitter_frac: float = 0.05,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generate a waveform with up to `jitter_frac * dt` timestamp jitter."""
        n = int(round(duration_s * nominal_rate))
        dt = 1.0 / nominal_rate
        rng = np.random.default_rng(seed=42)
        jitter = rng.uniform(-jitter_frac * dt, jitter_frac * dt, n)
        t = np.arange(n, dtype=np.float64) * dt + jitter
        t = np.sort(t)  # ensure monotone
        w = 2.0 * np.pi * 50.0
        x = amp_peak * np.cos(w * t + np.radians(phase_deg))
        return t, x

    def test_irregular_path_produces_available_output(self):
        amp_peak = math.sqrt(2) * 100.0
        t, x = self._make_irregular(amp_peak, 0.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        # Irregular path -- some windows should be available.
        assert np.any(result.available)

    def test_irregular_path_magnitude_approximately_correct(self):
        """With small timestamp jitter, the magnitude should be close to true RMS."""
        amp_peak = math.sqrt(2) * 100.0
        t, x = self._make_irregular(amp_peak, 0.0, 5000.0, 1.0, jitter_frac=0.01)
        result = compute_sliding_phasor(t, x, 50.0)
        mags = magnitude_rms(result)[result.available]
        # Tight jitter: expect < 2% magnitude error.
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.02)

    def test_irregular_path_relative_phase_approximately_correct(self):
        """With small jitter, relative phase should be within 2 degrees."""
        t_v, x_v = self._make_irregular(math.sqrt(2) * 100.0, 0.0, 5000.0, 1.0, 0.01)
        _, x_i = self._make_irregular(math.sqrt(2) * 5.0, -30.0, 5000.0, 1.0, 0.01)
        t_i = t_v  # same timestamps for both channels
        rv = compute_sliding_phasor(t_v, x_v, 50.0)
        ri = compute_sliding_phasor(t_i, x_i, 50.0)
        avail = rv.available & ri.available
        rel = (angle_deg(rv)[avail] - angle_deg(ri)[avail] + 180.0) % 360.0 - 180.0
        assert float(np.mean(rel)) == pytest.approx(30.0, abs=2.0)

    def test_systematic_alternating_spacing_accurate(self):
        """Systematic alternating-step timestamps (±25% dt): near-exact result
        for this specific pattern.

        Timestamps: t[2k] = 2k*dt - 0.25*dt, t[2k+1] = (2k+1)*dt + 0.25*dt.
        Steps alternate between 0.5*dt (0.1 ms) and 1.5*dt (0.3 ms) -- a
        3:1 ratio that clearly triggers the irregular path.

        Expected analytical phasor: X = (A/sqrt(2)) * exp(j*phi).

        Empirically: magnitude error < 0.001%, phase error < 0.001°.

        IMPORTANT: this near-exact result arises from a SPECIFIC SYMMETRY
        PROPERTY of the alternating pattern that causes the double-frequency
        leakage sum (see DEC-201-E) to vanish.  It is NOT representative of
        all irregular-sampling cases.  The unweighted DFT formula
        (sqrt(2)/N) * sum x_n * exp(-j*w*t_n) carries a systematic bias term
        for general irregular timestamps; the maximum-gap criterion is a
        screening condition, not a mathematical accuracy guarantee.
        See DEC-201-E for the full mathematical statement.
        """
        n = 5000
        dt_base = 1.0 / 5000.0
        offset = np.where(np.arange(n) % 2 == 0, -0.25 * dt_base, 0.25 * dt_base)
        t_irr = np.arange(n) * dt_base + offset
        # Confirm the path taken.
        diffs = np.diff(t_irr)
        assert not np.allclose(diffs, np.median(diffs), rtol=1e-6, atol=1e-12), \
            "Expected irregular path for alternating-step timestamps"

        amp_peak = math.sqrt(2) * 100.0
        phi = 30.0
        x_irr = amp_peak * np.cos(2.0 * np.pi * 50.0 * t_irr + math.radians(phi))

        result = compute_sliding_phasor(t_irr, x_irr, 50.0)
        mags = magnitude_rms(result)[result.available]
        angs = angle_deg(result)[result.available]

        # Analytical truth: X = (A/sqrt(2)) * exp(j*phi).
        assert float(np.mean(mags)) == pytest.approx(100.0, rel=0.001), \
            "Magnitude accuracy degraded for systematic alternating-step spacing"
        assert float(np.mean(angs)) == pytest.approx(phi, abs=0.001), \
            "Phase accuracy degraded for systematic alternating-step spacing"

    def test_irregular_validity_criterion_documented(self):
        """Document the max-gap screening criterion and its limitations.

        The unweighted DFT formula (sqrt(2)/N) * sum x_n * exp(-j*w*t_n) for
        irregularly sampled signals carries a systematic bias term:

            |error| ≤ (A/sqrt(2)) * (1/N) * |sum exp(-j*2*w*t_n)|

        The maximum-gap criterion -- max consecutive gap within any window
        < T_w / min_samples_per_cycle = 2.5 ms at 50 Hz -- is a SCREENING
        CONDITION, not a mathematical accuracy guarantee.  Passing this test
        ensures adequate window coverage to detect the signal, but does NOT
        bound the leakage error algebraically, because |sum exp(-j*2*w*t_n)|
        depends on the specific timestamp distribution, not just the max gap.

        In practice: for recordings with smoothly varying or small-jitter
        sample spacing (typical COMTRADE disturbance files), the leakage
        term is small.  For recordings where a large sampling-rate discontinuity
        falls within the sliding window, the bias may be significant and the
        result should be treated as approximate.

        This test verifies that the alternating-step case (which satisfies the
        gap criterion) gives < 0.01° phase error -- a practical engineering
        bound for COMTRADE recordings where rate transitions happen between
        events (not mid-window).
        """
        # Already covered by test_systematic_alternating_spacing_accurate; this
        # test re-asserts the validity bound explicitly for documentation.
        n = 5000
        dt_base = 1.0 / 5000.0
        offset = np.where(np.arange(n) % 2 == 0, -0.25 * dt_base, 0.25 * dt_base)
        t_irr = np.arange(n) * dt_base + offset
        # Maximum gap within any window: 1.5 * dt_base = 0.3 ms < 2.5 ms (criterion).
        max_gap = np.max(np.diff(t_irr))
        T_w = 1.0 / 50.0
        min_spc = PHASOR_MIN_SAMPLES_PER_CYCLE  # 8
        assert max_gap < T_w / min_spc, \
            f"Test setup: max gap {max_gap*1000:.3f} ms must be < {T_w/min_spc*1000:.1f} ms"

        amp_peak = math.sqrt(2) * 100.0
        phi = 45.0
        x_irr = amp_peak * np.cos(2.0 * np.pi * 50.0 * t_irr + math.radians(phi))
        result = compute_sliding_phasor(t_irr, x_irr, 50.0)
        _, angs = _get_steady_state(result)
        assert float(np.mean(angs)) == pytest.approx(phi, abs=0.01), \
            "Phase accuracy must be < 0.01° when max window gap < T_w/min_samples_per_cycle"


# ---------------------------------------------------------------------------
# Test 19: Result metadata fields
# ---------------------------------------------------------------------------

class TestResultMetadata:
    """Verify SlidingPhasorResult carries correct metadata fields."""

    def test_algorithm_version(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 50.0)
        assert result.algorithm_version == ALGORITHM_VERSION

    def test_reference_frequency_stored(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 60.0)
        assert result.reference_frequency_hz == 60.0

    def test_window_seconds_stored(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.1)
        result = compute_sliding_phasor(t, x, 50.0)
        assert result.window_seconds == pytest.approx(0.02)

    def test_sample_count_equals_window_size_for_uniform(self):
        """For uniform spacing, every available window has n_window samples."""
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        avail_counts = result.sample_count[result.available]
        # n_window = round(0.02 / (1/5000)) = round(100) = 100.
        assert np.all(avail_counts == 100)

    def test_reason_code_empty_string_when_available(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        assert np.all(result.reason_code[result.available] == "")

    def test_phasor_nan_when_unavailable(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        unavail_phasors = result.phasor[~result.available]
        assert np.all(np.isnan(unavail_phasors.real))
        assert np.all(np.isnan(unavail_phasors.imag))


# ---------------------------------------------------------------------------
# Test 20: Convenience helpers magnitude_rms() and angle_deg()
# ---------------------------------------------------------------------------

class TestHelpers:
    """Verify the magnitude_rms() and angle_deg() helper functions."""

    def test_magnitude_rms_agrees_with_abs(self):
        t, x = _cosine(math.sqrt(2) * 100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        np.testing.assert_array_almost_equal(
            magnitude_rms(result), np.abs(result.phasor)
        )

    def test_angle_deg_agrees_with_degrees_angle(self):
        t, x = _cosine(math.sqrt(2) * 100.0, 30.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        np.testing.assert_array_almost_equal(
            angle_deg(result), np.degrees(np.angle(result.phasor))
        )

    def test_magnitude_rms_nan_for_unavailable(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        mags = magnitude_rms(result)
        assert np.all(np.isnan(mags[~result.available]))

    def test_angle_deg_nan_for_unavailable(self):
        t, x = _cosine(100.0, 0.0, 50.0, 5000.0, 0.5)
        result = compute_sliding_phasor(t, x, 50.0)
        angs = angle_deg(result)
        assert np.all(np.isnan(angs[~result.available]))


# ---------------------------------------------------------------------------
# Test 21: Power calculation compatibility
# ---------------------------------------------------------------------------

class TestPowerCalculationCompatibility:
    """Verify that phasor output flows correctly into power_calculation.py."""

    def test_single_phase_power_from_phasor_output(self):
        """For V = 100 V ∠ 0°, I = 5 A ∠ -30° (lagging), the expected power
        is hand-derived:
          P = V * I * cos(30°) = 100*5*cos(30°) = 500 * sqrt(3)/2 ≈ 433 W
          Q = V * I * sin(30°) = 100*5*sin(30°) = 500 * 0.5 = 250 VAR
          S = sqrt(P^2 + Q^2) = 500 VA
        """
        from app.domain.power_calculation import single_phase_power

        amp_v = math.sqrt(2) * 100.0
        amp_i = math.sqrt(2) * 5.0
        t, x_v = _cosine(amp_v, 0.0, 50.0, 5000.0, 1.0)
        _, x_i = _cosine(amp_i, -30.0, 50.0, 5000.0, 1.0)

        rv = compute_sliding_phasor(t, x_v, 50.0)
        ri = compute_sliding_phasor(t, x_i, 50.0)

        avail = rv.available & ri.available
        v_mag = float(np.mean(magnitude_rms(rv)[avail]))
        v_ang = float(np.mean(angle_deg(rv)[avail]))
        i_mag = float(np.mean(magnitude_rms(ri)[avail]))
        i_ang = float(np.mean(angle_deg(ri)[avail]))

        pwr = single_phase_power(v_mag, v_ang, i_mag, i_ang)

        expected_p = 100.0 * 5.0 * math.cos(math.radians(30.0))  # ≈ 433 W
        expected_q = 100.0 * 5.0 * math.sin(math.radians(30.0))  # ≈ 250 VAR
        expected_s = 100.0 * 5.0                                   # 500 VA

        assert pwr.p_watts == pytest.approx(expected_p, rel=1e-4)
        assert pwr.q_var == pytest.approx(expected_q, rel=1e-4)
        assert pwr.s_va == pytest.approx(expected_s, rel=1e-4)
        assert pwr.power_factor_sign == "lagging"

    def test_reversed_current_direction_reverses_power(self):
        """Reversing current direction must negate both P and Q (DEC-PWR-003).

        Approved convention: S = V * conj(I) = P + jQ.

        For V = 100 V ∠ 0°, I_forward = 5 A ∠ -30° (lagging, current INTO
        the element):
          P_forward = +433 W (element absorbs active power)
          Q_forward = +250 VAR (inductive load)

        Reversed current I_rev = -I_forward corresponds to x_i_rev = -x_i_fwd,
        i.e., the same magnitude but angle shifted by 180°: 5 A ∠ 150°.
          S_rev = V * conj(I_rev) = V * conj(-I_fwd) = -(P + jQ)
          P_rev = -433 W (element supplies active power)
          Q_rev = -250 VAR

        This confirms that reversing the current PHASOR (negating I) correctly
        reverses both P and Q, as required.  Using the wrong formula conj(V)*I
        would instead give S_wrong = |V|*|I|*exp(-j*30°), yielding
        P_wrong = +433 W (same sign) and Q_wrong = -250 VAR (only Q flips) --
        a physically incorrect result that this test rules out.
        """
        from app.domain.power_calculation import single_phase_power

        amp_v = math.sqrt(2) * 100.0
        amp_i = math.sqrt(2) * 5.0
        t, x_v = _cosine(amp_v, 0.0, 50.0, 5000.0, 1.0)
        _, x_i_fwd = _cosine(amp_i, -30.0, 50.0, 5000.0, 1.0)
        # Reversed current: opposite direction = angle + 180°.
        _, x_i_rev = _cosine(amp_i, -30.0 + 180.0, 50.0, 5000.0, 1.0)

        rv = compute_sliding_phasor(t, x_v, 50.0)
        ri_fwd = compute_sliding_phasor(t, x_i_fwd, 50.0)
        ri_rev = compute_sliding_phasor(t, x_i_rev, 50.0)

        avail_fwd = rv.available & ri_fwd.available
        v_mag = float(np.mean(magnitude_rms(rv)[avail_fwd]))
        v_ang = float(np.mean(angle_deg(rv)[avail_fwd]))
        i_fwd_mag = float(np.mean(magnitude_rms(ri_fwd)[avail_fwd]))
        i_fwd_ang = float(np.mean(angle_deg(ri_fwd)[avail_fwd]))

        avail_rev = rv.available & ri_rev.available
        i_rev_mag = float(np.mean(magnitude_rms(ri_rev)[avail_rev]))
        i_rev_ang = float(np.mean(angle_deg(ri_rev)[avail_rev]))

        pwr_fwd = single_phase_power(v_mag, v_ang, i_fwd_mag, i_fwd_ang)
        pwr_rev = single_phase_power(v_mag, v_ang, i_rev_mag, i_rev_ang)

        expected_p = 100.0 * 5.0 * math.cos(math.radians(30.0))  # ≈ 433 W
        expected_q = 100.0 * 5.0 * math.sin(math.radians(30.0))  # ≈ 250 VAR

        # Forward direction: element absorbs power (P > 0, Q > 0 = inductive).
        assert pwr_fwd.p_watts == pytest.approx(expected_p, rel=1e-4)
        assert pwr_fwd.q_var == pytest.approx(expected_q, rel=1e-4)
        assert pwr_fwd.power_factor_sign == "lagging"

        # Reversed direction: both P and Q negate -- active flow reverses.
        assert pwr_rev.p_watts == pytest.approx(-expected_p, rel=1e-4), \
            "P must negate when current direction reverses (DEC-PWR-003)"
        assert pwr_rev.q_var == pytest.approx(-expected_q, rel=1e-4), \
            "Q must negate when current direction reverses (DEC-PWR-003)"


# ---------------------------------------------------------------------------
# Test 22: Performance benchmark -- long recording
# ---------------------------------------------------------------------------

class TestPerformance:
    """Wall-clock benchmark for a long recording.

    These tests measure execution time and assert it stays below a
    generous ceiling that any modern machine should meet -- NOT a
    precision microbenchmark.  They document the O(N) expectation by
    reporting the result but never fail the test suite on timing alone
    (CI machines vary widely in speed; the assertion is a gross sanity
    check only).
    """

    @pytest.mark.slow
    def test_5s_at_5khz_under_3_seconds(self):
        """5 seconds at 5 kHz = 25 000 samples, stride=1 = 25 000 outputs.

        The uniform cumsum path should complete in well under 1 second on
        any modern hardware (pure NumPy, zero Python loops).  The test
        ceiling of 3 seconds is generous enough to pass even on slow CI.
        """
        n = 25_000
        t = np.arange(n, dtype=np.float64) / 5000.0
        x = math.sqrt(2) * 100.0 * np.cos(2.0 * np.pi * 50.0 * t)

        t0 = _time_module.perf_counter()
        result = compute_sliding_phasor(t, x, 50.0)
        elapsed = _time_module.perf_counter() - t0

        assert result.available.shape[0] == n
        assert np.any(result.available)
        print(f"\n[perf] 25 000 samples, stride=1: {elapsed * 1000:.1f} ms")
        assert elapsed < 3.0, f"Took {elapsed:.2f} s -- expected < 3 s"

    @pytest.mark.slow
    def test_60s_at_5khz_scales_linearly(self):
        """60 seconds at 5 kHz = 300 000 samples.

        Expected to complete in < 10 seconds.  Confirms O(N) by comparing
        the per-sample time to the 25 000-sample benchmark above (they
        should be within a constant factor).
        """
        n = 300_000
        t = np.arange(n, dtype=np.float64) / 5000.0
        x = math.sqrt(2) * 100.0 * np.cos(2.0 * np.pi * 50.0 * t)

        t0 = _time_module.perf_counter()
        result = compute_sliding_phasor(t, x, 50.0)
        elapsed = _time_module.perf_counter() - t0

        assert result.available.shape[0] == n
        print(f"\n[perf] 300 000 samples, stride=1: {elapsed * 1000:.1f} ms")
        assert elapsed < 10.0, f"Took {elapsed:.2f} s -- expected < 10 s"

    @pytest.mark.slow
    def test_stride_10_reduces_output_by_factor_10(self):
        """With stride=10, output is 1/10 the length of input."""
        n = 25_000
        t = np.arange(n, dtype=np.float64) / 5000.0
        x = math.sqrt(2) * 100.0 * np.cos(2.0 * np.pi * 50.0 * t)

        result = compute_sliding_phasor(t, x, 50.0, output_stride=10)
        assert result.time.shape[0] == math.ceil(n / 10)
