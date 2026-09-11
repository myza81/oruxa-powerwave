"""Golden-vector tests for app.domain.phasor (Phasor Analysis Slice 1).

Every expected magnitude/angle below is derived independently from
closed-form physics (`Vrms = Vpeak/sqrt(2)`, the known phase of a
constructed `cos(2*pi*f0*t + phi)` waveform, or the closed-form phase-
drift formula for an off-nominal-frequency signal) -- NEVER by running
this module's own estimator and calling the result "expected" (the same
hand-derived-value convention already established in
`test_event_detection_domain.py`).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.phasor import (
    PHASOR_MIN_SAMPLES_PER_CYCLE,
    REASON_ANALYSIS_TIME_OUT_OF_RANGE,
    REASON_INSUFFICIENT_WINDOW_HISTORY,
    REASON_INVALID_SAMPLES_IN_WINDOW,
    REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    _normalize_angle_deg,
    estimate_phasor,
    relative_angle_deg,
)


def _sine(amp_peak: float, phase_deg: float, freq_hz: float, sample_rate_hz: float, duration_s: float) -> tuple[np.ndarray, np.ndarray]:
    """A clean, noise-free sampled sinusoid -- `x(t) = amp_peak *
    cos(2*pi*freq_hz*t + phase_deg)`, uniformly sampled from t=0."""
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n) / sample_rate_hz
    x = amp_peak * np.cos(2.0 * np.pi * freq_hz * t + np.radians(phase_deg))
    return t, x


class TestRmsNormalization:
    """Golden test #1: x(t) = sqrt(2)*100*cos(2*pi*50*t) -> ~100 RMS, never 141.4 (peak)."""

    def test_known_rms_amplitude(self):
        amp_peak = np.sqrt(2) * 100.0
        t, x = _sine(amp_peak, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.2345, reference_frequency_hz=50.0)
        assert result.available
        assert result.magnitude_rms == pytest.approx(100.0, rel=1e-6)
        assert result.magnitude_rms != pytest.approx(141.4, rel=0.05)


class TestKnownAngles:
    """Golden test #2: known phase shifts, sign included."""

    @pytest.mark.parametrize("phase_deg", [30.0, 45.0, 90.0, -30.0, -90.0, 179.0, -179.0])
    def test_angle_matches_known_phase(self, phase_deg):
        t, x = _sine(100.0, phase_deg, 50.0, sample_rate_hz=5000.0, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=50.0)
        assert result.available
        assert result.angle_deg == pytest.approx(_normalize_angle_deg(phase_deg), abs=1e-6)


class TestBalancedThreePhase:
    """Golden test #3: Va=X∠0°, Vb=X∠-120°, Vc=X∠+120° -- verify both
    absolute and Phase-A-relative output."""

    def test_balanced_three_phase_voltage(self):
        f0 = 50.0
        amp_peak = np.sqrt(2) * 100.0
        results = {}
        for label, phase in (("Va", 0.0), ("Vb", -120.0), ("Vc", 120.0)):
            t, x = _sine(amp_peak, phase, f0, sample_rate_hz=5000.0, duration_s=2.0)
            results[label] = estimate_phasor(t, x, analysis_time=1.234, reference_frequency_hz=f0)

        for label in ("Va", "Vb", "Vc"):
            assert results[label].available
            assert results[label].magnitude_rms == pytest.approx(100.0, rel=1e-6)

        assert results["Va"].angle_deg == pytest.approx(0.0, abs=1e-6)
        assert results["Vb"].angle_deg == pytest.approx(-120.0, abs=1e-6)
        assert results["Vc"].angle_deg == pytest.approx(120.0, abs=1e-6)

        ref = results["Va"].angle_deg
        assert relative_angle_deg(results["Va"].angle_deg, ref) == pytest.approx(0.0, abs=1e-6)
        assert relative_angle_deg(results["Vb"].angle_deg, ref) == pytest.approx(-120.0, abs=1e-6)
        assert relative_angle_deg(results["Vc"].angle_deg, ref) == pytest.approx(120.0, abs=1e-6)


class TestBalancedThreePhaseCurrent:
    """Golden test #4: same concept for Current."""

    def test_balanced_three_phase_current(self):
        f0 = 50.0
        amp_peak = np.sqrt(2) * 40.0
        results = {}
        for label, phase in (("Ia", 0.0), ("Ib", -120.0), ("Ic", 120.0)):
            t, x = _sine(amp_peak, phase, f0, sample_rate_hz=5000.0, duration_s=2.0)
            results[label] = estimate_phasor(t, x, analysis_time=1.234, reference_frequency_hz=f0)
        for label, expected_angle in (("Ia", 0.0), ("Ib", -120.0), ("Ic", 120.0)):
            assert results[label].available
            assert results[label].magnitude_rms == pytest.approx(40.0, rel=1e-6)
            assert results[label].angle_deg == pytest.approx(expected_angle, abs=1e-6)


class TestFiftyAndSixtyHertz:
    """Golden test #5/#6: both nominal system frequencies validated explicitly."""

    @pytest.mark.parametrize("f0", [50.0, 60.0])
    def test_known_vectors_at_both_frequencies(self, f0):
        t, x = _sine(np.sqrt(2) * 230.0, 45.0, f0, sample_rate_hz=f0 * 32, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.1, reference_frequency_hz=f0)
        assert result.available
        assert result.magnitude_rms == pytest.approx(230.0, rel=1e-6)
        assert result.angle_deg == pytest.approx(45.0, abs=1e-6)


class TestMovingAnalysisTimeStability:
    """Golden test #7 -- CRITICAL: for a steady nominal-frequency
    sinusoid, absolute angle must remain stable as analysis_time
    advances. This proves the angle reference is the shared, fixed t=0
    origin of the `time` coordinate itself, never reset per sliding
    window (owner's own explicit critical requirement)."""

    def test_angle_stable_across_advancing_analysis_time(self):
        t, x = _sine(100.0, 37.0, 50.0, sample_rate_hz=5000.0, duration_s=3.0)
        angles = []
        for analysis_time in (1.0, 1.1111, 1.5, 1.777, 2.4999):
            result = estimate_phasor(t, x, analysis_time=analysis_time, reference_frequency_hz=50.0)
            assert result.available, analysis_time
            angles.append(result.angle_deg)
        for angle in angles:
            assert angle == pytest.approx(37.0, abs=1e-6)
        # Also directly assert mutual stability (never drifting relative
        # to each other), independent of the hand-derived value above.
        assert max(angles) - min(angles) < 1e-6


class TestOffNominalFrequency:
    """Golden test #8: documents (never hides) the fixed-frequency
    estimator's own expected error/drift -- NOT PMU-class tracking.

    Closed-form prediction: for a true signal at `f_actual` analyzed
    with reference `f0`, the correlation is a windowed AVERAGE of the
    slowly-rotating phase difference `2*pi*(f_actual-f0)*t` across the
    whole window, not merely its value at `analysis_time`. For a window
    of length `T = 1/f0` ending at `analysis_time`, that average phase
    corresponds to evaluating the drift at the window's own MIDPOINT,
    `analysis_time - T/2` (a first-order approximation, accurate to a
    fraction of a degree here) -- so the expected reported angle is
    `phi + 360*(f_actual-f0)*(analysis_time - T/2)`, wrapped to
    `(-180, 180]`. Magnitude error is small (a few tenths of a percent
    at this frequency offset) but non-zero.
    """

    def test_49hz_signal_against_50hz_reference_matches_closed_form_drift(self):
        f0_reference = 50.0
        f_actual = 49.0
        phi_deg = 0.0
        analysis_time = 1.53371
        t, x = _sine(np.sqrt(2) * 100.0, phi_deg, f_actual, sample_rate_hz=5000.0, duration_s=3.0)
        result = estimate_phasor(t, x, analysis_time=analysis_time, reference_frequency_hz=f0_reference)
        assert result.available

        window_center = analysis_time - (1.0 / f0_reference) / 2.0
        expected_drift_deg = _normalize_angle_deg(phi_deg + 360.0 * (f_actual - f0_reference) * window_center)
        assert result.angle_deg == pytest.approx(expected_drift_deg, abs=1.0)
        # Magnitude stays close to correct (small window-mismatch error,
        # not a wild swing) -- documents the estimator degrades gently,
        # not catastrophically, for a 1 Hz offset at 50 Hz nominal.
        assert result.magnitude_rms == pytest.approx(100.0, rel=0.01)

    def test_this_is_not_frequency_tracked(self):
        """A frequency-tracked (PMU-class) estimator would report the
        SAME angle regardless of which reference frequency is supplied,
        because it would measure the true frequency itself. This
        estimator does not -- supplying a different reference frequency
        for the identical off-nominal signal changes the reported
        angle, proving no frequency tracking is occurring."""
        t, x = _sine(100.0, 0.0, 49.0, sample_rate_hz=5000.0, duration_s=3.0)
        at_50 = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=50.0)
        at_49 = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=49.0)
        assert at_50.available and at_49.available
        # Analyzed at its own true frequency: no MEANINGFUL drift (a
        # small residual remains since 5000 Hz / 49 Hz is not an exact
        # integer samples-per-cycle ratio -- a discretization artifact,
        # not phase drift).
        assert abs(at_49.angle_deg) < 0.05
        assert abs(at_50.angle_deg - at_49.angle_deg) > 1.0  # analyzed at nominal: measurable drift


class TestRecordingStart:
    """Golden test #9: insufficient leading history -> explicit
    unavailable, never a shortened/shifted window."""

    def test_insufficient_history_at_recording_start(self):
        t, x = _sine(100.0, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=1.0)
        result = estimate_phasor(t, x, analysis_time=0.01, reference_frequency_hz=50.0)
        assert not result.available
        assert result.reason_code == REASON_INSUFFICIENT_WINDOW_HISTORY

    def test_analysis_time_beyond_recording_end_is_out_of_range(self):
        t, x = _sine(100.0, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=1.0)
        result = estimate_phasor(t, x, analysis_time=5.0, reference_frequency_hz=50.0)
        assert not result.available
        assert result.reason_code == REASON_ANALYSIS_TIME_OUT_OF_RANGE

    def test_exactly_one_window_of_history_is_available(self):
        f0 = 50.0
        t, x = _sine(100.0, 0.0, f0, sample_rate_hz=5000.0, duration_s=1.0)
        result = estimate_phasor(t, x, analysis_time=1.0 / f0, reference_frequency_hz=f0)
        assert result.available


class TestInvalidSamples:
    """Golden test #10: NaN within the exact window -> explicit
    unavailable, never silently dropped."""

    def test_nan_in_window_is_unavailable(self):
        t, x = _sine(100.0, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=2.0)
        x = x.copy()
        # Corrupt one sample inside the window ending at analysis_time=1.5.
        idx = np.searchsorted(t, 1.49)
        x[idx] = np.nan
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=50.0)
        assert not result.available
        assert result.reason_code == REASON_INVALID_SAMPLES_IN_WINDOW

    def test_nan_outside_window_does_not_affect_result(self):
        t, x = _sine(100.0, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=2.0)
        x = x.copy()
        x[0] = np.nan  # far outside the window ending at analysis_time=1.5
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=50.0)
        assert result.available


class TestIrregularSampling:
    """Golden test #11: irregular spacing within the window -> explicit
    unsupported/unavailable, never resampled/interpolated."""

    def test_irregular_spacing_is_unavailable(self):
        f0 = 50.0
        # A dense base grid (5000 Hz -> 100 samples/cycle) with per-sample
        # jitter large enough to break the regularity check, but small
        # enough that the window still contains well over
        # PHASOR_MIN_SAMPLES_PER_CYCLE samples -- otherwise this would
        # (correctly, but not for the reason this test wants to prove)
        # fail on insufficient history/density instead of irregularity.
        rng = np.random.default_rng(1)
        n = int(round(2.0 * 5000.0))
        t = np.arange(n) / 5000.0 + rng.uniform(-1e-5, 1e-5, n)
        t = np.sort(t)
        x = 100.0 * np.cos(2.0 * np.pi * f0 * t)
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=f0)
        assert not result.available
        assert result.reason_code == REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED

    def test_uniform_spacing_is_supported(self):
        t, x = _sine(100.0, 0.0, 50.0, sample_rate_hz=5000.0, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=50.0)
        assert result.available


class TestMinimumSamplingDensityGuardrail:
    def test_below_threshold_rejected(self):
        f0 = 50.0
        spc = PHASOR_MIN_SAMPLES_PER_CYCLE - 1
        t, x = _sine(100.0, 0.0, f0, sample_rate_hz=f0 * spc, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=f0)
        assert not result.available
        assert result.reason_code == REASON_INSUFFICIENT_SAMPLING_DENSITY

    def test_at_threshold_accepted(self):
        f0 = 50.0
        spc = PHASOR_MIN_SAMPLES_PER_CYCLE
        t, x = _sine(100.0, 0.0, f0, sample_rate_hz=f0 * spc, duration_s=2.0)
        result = estimate_phasor(t, x, analysis_time=1.5, reference_frequency_hz=f0)
        assert result.available


class TestSamplingDensityStudy:
    """Golden test #12 -- the empirical evidence behind
    `PHASOR_MIN_SAMPLES_PER_CYCLE`. Explicitly NOT copied from
    `calculated_channel.MIN_SAMPLES_PER_CYCLE` (=4, tuned for a
    *sliding* RMS's own accuracy needs) -- swept independently at
    4/8/16/32 samples/cycle against RMS magnitude, 30 deg / 90 deg
    phase shift, and a realistic (0.2% amplitude) noise floor, using a
    deliberately window-misaligned `analysis_time` (not a multiple of
    the sample interval) so any real edge-discretization error would
    show up.

    **Findings** (see this class's own test bodies for the exact
    reproducible numbers): for a perfectly clean sinusoid, magnitude/
    angle error is already at floating-point noise level (~1e-9 relative)
    at EVERY tested density down to 4 samples/cycle -- the estimator's
    correlation sum is discretely exact for a pure single-frequency
    signal regardless of window-boundary phase, so density alone does
    not explain accuracy for the noise-free case. Under a realistic
    0.2%-amplitude noise floor, however, error scales down roughly with
    `1/sqrt(N)` as density increases (consistent with simple noise-
    averaging): the measured magnitude-error standard deviation at 4
    samples/cycle is roughly double that at 8, which is itself
    materially higher than at 16/32.

    `PHASOR_MIN_SAMPLES_PER_CYCLE = 8` is chosen as a deliberate, DOUBLE
    the bare RMS-precedent minimum, not because 4 is numerically wrong
    for a clean signal, but because it visibly and measurably improves
    robustness margin against realistic sensor/ADC noise while still
    being a very low bar for any real COMTRADE recording to clear (8
    samples/cycle at 50 Hz is only 400 Hz -- this project's own
    performance-baseline fixtures use 5-20 kHz, two to three orders of
    magnitude above this floor). This is an APPLICATION guardrail based
    on this estimator's own measured behavior, not a claimed protection-
    relay industry standard.
    """

    @pytest.mark.parametrize("samples_per_cycle", [4, 8, 16, 32])
    def test_clean_signal_error_is_negligible_at_every_tested_density(self, samples_per_cycle):
        f0 = 50.0
        t, x = _sine(np.sqrt(2) * 100.0, 30.0, f0, sample_rate_hz=f0 * samples_per_cycle, duration_s=3.0)
        # Deliberately NOT a multiple of the sample interval.
        analysis_time = 1.5 + 0.37 / (f0 * samples_per_cycle)
        result = estimate_phasor(t, x, analysis_time=analysis_time, reference_frequency_hz=f0, min_samples_per_cycle=2)
        assert result.available
        assert result.magnitude_rms == pytest.approx(100.0, rel=1e-6)
        assert result.angle_deg == pytest.approx(30.0, abs=1e-6)

    def test_noise_error_decreases_as_density_increases(self):
        f0 = 50.0
        amp_peak = np.sqrt(2) * 100.0
        noise_std = 0.002 * amp_peak  # 0.2% of peak amplitude
        stds_by_density: dict[int, float] = {}
        for samples_per_cycle in (4, 8, 16, 32):
            fs = f0 * samples_per_cycle
            errors = []
            for trial in range(30):
                rng = np.random.default_rng(trial)
                n = int(round(3.0 * fs))
                t = np.arange(n) / fs
                x = amp_peak * np.cos(2.0 * np.pi * f0 * t + np.radians(30.0)) + rng.normal(0.0, noise_std, n)
                analysis_time = 1.5 + trial * 0.7 / fs
                result = estimate_phasor(t, x, analysis_time=analysis_time, reference_frequency_hz=f0, min_samples_per_cycle=2)
                if result.available:
                    errors.append(result.magnitude_rms - 100.0)
            stds_by_density[samples_per_cycle] = float(np.std(errors))

        # Monotonic (or effectively so) improvement with density -- the
        # empirical basis for choosing a threshold stricter than the
        # bare Nyquist-adjacent minimum.
        assert stds_by_density[4] > stds_by_density[8] > stds_by_density[32]
        # 8 samples/cycle materially reduces noise-driven error relative
        # to 4 -- the concrete evidence behind PHASOR_MIN_SAMPLES_PER_CYCLE.
        assert stds_by_density[8] < stds_by_density[4] * 0.75


class TestAngleNormalization:
    def test_wraps_to_positive_180_not_negative(self):
        assert _normalize_angle_deg(180.0) == pytest.approx(180.0)
        assert _normalize_angle_deg(180.0001) == pytest.approx(-179.9999, abs=1e-6)
        assert _normalize_angle_deg(-180.0) == pytest.approx(180.0)
        assert _normalize_angle_deg(540.0) == pytest.approx(180.0)
        assert _normalize_angle_deg(-540.0) == pytest.approx(180.0)
        assert _normalize_angle_deg(0.0) == pytest.approx(0.0)
