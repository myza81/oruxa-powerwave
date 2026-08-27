"""Pure domain tests for Slice 3's assisted event-origin detector
(app.domain.event_detection.detect_event_onset). Synthetic waveforms
only -- this module has no concept of sources/workspaces, so no
COMTRADE fixtures are needed here (see test_event_detection_service.py/
test_synchronization_detect_event_api.py for the source/workspace-aware
layers built on top of this one).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.event_detection import (
    DIRECTION_DECREASE,
    DIRECTION_INCREASE,
    QUALITY_MODERATE,
    QUALITY_STRONG,
    QUALITY_WEAK,
    detect_event_onset,
)

F0 = 50.0


def _sine(t: np.ndarray, amplitude, f0: float = F0) -> np.ndarray:
    return amplitude * np.sin(2.0 * np.pi * f0 * t)


def _step_waveform(*, duration_s: float, fs: float, event_time_s: float, pre_amplitude: float, post_amplitude: float, f0: float = F0):
    t = np.arange(0.0, duration_s, 1.0 / fs)
    amplitude = np.full_like(t, pre_amplitude)
    amplitude[t >= event_time_s] = post_amplitude
    return t, _sine(t, amplitude, f0)


class TestStrongDisturbance:
    """Task section 33: "stable pre-event sinusoid -> clear sustained
    magnitude reduction... detector should propose near the known event
    time within a technically justified tolerance."""

    def test_sustained_voltage_dip_is_found_near_the_true_onset(self):
        t, values = _step_waveform(duration_s=2.0, fs=5000.0, event_time_s=1.0, pre_amplitude=100.0, post_amplitude=50.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")

        assert result.found is True
        assert result.direction == DIRECTION_DECREASE
        assert result.quality == QUALITY_STRONG
        # One RMS window (1/f0 = 20 ms) is the technically-justified
        # tolerance -- the trailing-window detector cannot possibly
        # report the onset before enough post-event samples have entered
        # the window to move the ratio past threshold.
        assert abs(result.candidate_source_time - 1.0) < (1.0 / F0)
        assert result.baseline_rms == pytest.approx(100.0 / np.sqrt(2), rel=0.02)
        assert result.changed_rms == pytest.approx(50.0 / np.sqrt(2), rel=0.05)
        assert result.change_ratio == pytest.approx(0.5, abs=0.02)
        assert result.detector_method == "rms_sustained_change"


class TestCurrentRise:
    """Task section 33: current-rise events must be found too -- the
    detector must never assume only a voltage-drop shape."""

    def test_sustained_current_rise_is_found(self):
        t, values = _step_waveform(duration_s=2.0, fs=5000.0, event_time_s=1.0, pre_amplitude=10.0, post_amplitude=15.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")

        assert result.found is True
        assert result.direction == DIRECTION_INCREASE
        assert result.change_ratio == pytest.approx(1.5, abs=0.02)
        assert abs(result.candidate_source_time - 1.0) < (1.0 / F0)


class TestMildDisturbance:
    """Task section 33: a smaller sustained change's outcome legitimately
    depends on sensitivity -- documented here rather than asserting one
    single "correct" answer."""

    def _mild_dip_waveform(self):
        return _step_waveform(duration_s=2.0, fs=5000.0, event_time_s=1.0, pre_amplitude=100.0, post_amplitude=88.0)

    def test_normal_sensitivity_finds_it_as_weak_quality(self):
        t, values = self._mild_dip_waveform()
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is True
        assert result.quality == QUALITY_WEAK

    def test_conservative_sensitivity_does_not_find_it(self):
        """A 12% dip does not clear Conservative's 20% trigger band --
        Conservative is deliberately less sensitive, not merely stricter
        quality labeling."""
        t, values = self._mild_dip_waveform()
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="conservative")
        assert result.found is False

    def test_sensitive_sensitivity_finds_it(self):
        t, values = self._mild_dip_waveform()
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="sensitive")
        assert result.found is True


class TestSingleSampleSpike:
    """Task section 33/9: "must not be interpreted as a sustained event."""

    def test_single_sample_spike_is_not_a_candidate(self):
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        values = _sine(t, 100.0)
        values[int(1.0 * 5000.0)] = 5000.0  # one wildly out-of-range sample
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is False
        assert result.reason == "No clear disturbance onset detected."


class TestSteadyWaveform:
    """Task section 28/33: a clean steady sinusoid must return "no clear
    event," never an arbitrary candidate manufactured on request."""

    def test_steady_sinusoid_returns_no_clear_event(self):
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        values = _sine(t, 100.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is False
        assert result.reason == "No clear disturbance onset detected."
        assert result.candidate_source_time is None
        assert result.quality is None


class TestNoise:
    """Task section 33: realistic noise around a sinusoid, with no real
    disturbance, must not produce a false confident event."""

    def test_noisy_steady_sinusoid_does_not_false_trigger(self):
        rng = np.random.default_rng(20260827)
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        values = _sine(t, 100.0) + rng.normal(0.0, 3.0, t.shape[0])
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is False


class TestSamplingRateIndependence:
    """Task section 33: equivalent synthetic events at 1/5/10 kHz should
    produce comparable event-time estimates -- the persistence/baseline
    windows are duration-based (seconds), never a fixed sample count, so
    this must hold regardless of native sampling rate."""

    @pytest.mark.parametrize("fs", [1000.0, 5000.0, 10000.0])
    def test_comparable_candidate_time_across_sampling_rates(self, fs):
        t, values = _step_waveform(duration_s=2.0, fs=fs, event_time_s=1.0, pre_amplitude=100.0, post_amplitude=50.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is True
        assert abs(result.candidate_source_time - 1.0) < (1.0 / F0)


class TestMultiRateSpacing:
    """Task section 20: a genuinely irregular/multi-rate `time` array
    (two different native sampling-rate sections concatenated, the real
    COMTRADE multi-rate shape) must still be handled correctly --
    evaluate_rms() already proved this for RMS itself (DEC-048); this
    confirms the detector built on top of it inherits that guarantee."""

    def test_event_found_across_a_sampling_rate_boundary(self):
        t1 = np.arange(0.0, 1.0, 1.0 / 1000.0)
        t2 = np.arange(1.0, 2.0, 1.0 / 5000.0)
        t = np.concatenate([t1, t2])
        amplitude = np.full_like(t, 100.0)
        amplitude[t >= 1.2] = 40.0
        values = _sine(t, amplitude)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is True
        assert abs(result.candidate_source_time - 1.2) < (2.0 / F0)


class TestBadData:
    def test_empty_arrays(self):
        result = detect_event_onset(np.array([]), np.array([]), nominal_frequency_hz=F0)
        assert result.found is False
        assert result.reason == "No samples available to analyse."

    def test_mismatched_lengths(self):
        result = detect_event_onset(np.array([0.0, 0.1]), np.array([1.0]), nominal_frequency_hz=F0)
        assert result.found is False

    def test_all_nan_values(self):
        t = np.arange(0.0, 1.0, 1.0 / 1000.0)
        values = np.full_like(t, np.nan)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0)
        assert result.found is False

    def test_non_monotonic_time_is_rejected_safely(self):
        t = np.array([0.0, 0.1, 0.05, 0.2, 0.3])
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = detect_event_onset(t, values, nominal_frequency_hz=F0)
        assert result.found is False
        assert "not monotonic" in result.reason

    def test_duplicated_timestamps_do_not_crash(self):
        t = np.sort(np.concatenate([np.arange(0.0, 1.0, 0.001), [1.0, 1.0, 1.0]]))
        values = _sine(t, 100.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0)  # must not raise
        assert isinstance(result.found, bool)

    def test_too_short_recording(self):
        t = np.array([0.0, 0.001])
        values = np.array([1.0, 2.0])
        result = detect_event_onset(t, values, nominal_frequency_hz=F0)
        assert result.found is False

    def test_insufficient_pre_event_baseline(self):
        """A recording barely longer than one RMS window has almost no
        leading history to build a baseline from."""
        t = np.arange(0.0, 1.0 / F0 * 1.5, 1.0 / 5000.0)
        values = _sine(t, 100.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0)
        assert result.found is False

    def test_invalid_nominal_frequency_is_rejected(self):
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        values = _sine(t, 100.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=float("nan"))
        assert result.found is False

    def test_unknown_sensitivity_falls_back_to_normal(self):
        """The service layer is the one that validates/rejects an
        unrecognised sensitivity string with a proper API error -- this
        domain function itself degrades gracefully rather than raising,
        consistent with never crashing the workspace (task section 29)."""
        t, values = _step_waveform(duration_s=2.0, fs=5000.0, event_time_s=1.0, pre_amplitude=100.0, post_amplitude=50.0)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="not-a-real-tier")
        assert result.found is True  # behaves exactly like "normal"


class TestFirstOnsetSelection:
    """Task section 6: "identify FIRST sustained significant change" --
    a second, later disturbance must not shadow an earlier one."""

    def test_reports_the_earlier_of_two_disturbances(self):
        t = np.arange(0.0, 3.0, 1.0 / 5000.0)
        amplitude = np.full_like(t, 100.0)
        amplitude[(t >= 1.0)] = 50.0
        amplitude[(t >= 2.0)] = 100.0  # recovers, then...
        amplitude[(t >= 2.2)] = 20.0  # ...a second, larger disturbance
        values = _sine(t, amplitude)
        result = detect_event_onset(t, values, nominal_frequency_hz=F0, sensitivity="normal")
        assert result.found is True
        assert abs(result.candidate_source_time - 1.0) < (1.0 / F0)
