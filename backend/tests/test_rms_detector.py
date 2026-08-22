"""Unit tests for app.domain.rms_detector (Phase 5B, DEC-048): the
algorithmic waveform-form eligibility FALLBACK -- only ever consulted
when trusted metadata is absent (see calculated_channel_service.
check_rms_eligibility).
"""

from __future__ import annotations

import numpy as np

from app.domain.rms_detector import (
    LIKELY_INSTANTANEOUS,
    LIKELY_MAGNITUDE_OR_RMS,
    UNCERTAIN,
    classify_waveform_form,
)


def _sinusoid(*, fs: float, f0: float, duration: float, amplitude: float = 1.0, dc: float = 0.0):
    n = int(round(fs * duration))
    t = np.arange(n) / fs
    return t, dc + amplitude * np.sin(2 * np.pi * f0 * t)


class TestClassifyWaveformForm:
    def test_pure_50hz_sinusoid_is_likely_instantaneous(self):
        t, v = _sinusoid(fs=5000.0, f0=50.0, duration=1.0)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_pure_60hz_sinusoid_at_60hz_nominal_is_likely_instantaneous(self):
        t, v = _sinusoid(fs=6000.0, f0=60.0, duration=1.0)
        assert classify_waveform_form(t, v, 60.0) == LIKELY_INSTANTANEOUS

    def test_slowly_varying_positive_magnitude_series_is_likely_magnitude_or_rms(self):
        t, v = _sinusoid(fs=5000.0, f0=2.0, duration=1.0, amplitude=0.1, dc=1.0)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_MAGNITUDE_OR_RMS

    def test_near_constant_series_is_never_confidently_instantaneous(self):
        # Owner section 27: a Frequency-like near-constant signal should
        # "typically" read as magnitude-like OR uncertain -- never
        # confidently declared suitable for RMS just because it's numeric.
        rng = np.random.default_rng(7)
        t = np.arange(2000) / 5000.0
        v = 50.02 + rng.normal(0, 1e-4, size=t.shape[0])
        assert classify_waveform_form(t, v, 50.0) in (LIKELY_MAGNITUDE_OR_RMS, UNCERTAIN)

    def test_random_noise_is_uncertain_not_confidently_wrong(self):
        rng = np.random.default_rng(3)
        t = np.arange(5000) / 5000.0
        v = rng.normal(0, 1.0, size=t.shape[0])
        assert classify_waveform_form(t, v, 50.0) in (UNCERTAIN, LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS)
        # Never crash, never raise -- the only hard requirement for noise.

    def test_too_short_slice_is_uncertain(self):
        t, v = _sinusoid(fs=5000.0, f0=50.0, duration=0.01)  # far under 3 cycles
        assert classify_waveform_form(t, v, 50.0) == UNCERTAIN

    def test_representative_slice_is_capped_not_full_record(self):
        # A long recording where the signal changes character after 1s --
        # only the capped leading slice should drive the result.
        t1, v1 = _sinusoid(fs=5000.0, f0=50.0, duration=1.0)
        t2 = t1[-1] + 1.0 / 5000.0 + np.arange(5000) / 5000.0
        v2 = np.full(5000, 3.0)  # magnitude-like tail, should be ignored
        t = np.concatenate([t1, t2])
        v = np.concatenate([v1, v2])
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_all_nonfinite_input_is_uncertain_not_a_crash(self):
        t = np.arange(2000) / 5000.0
        v = np.full(2000, np.nan)
        assert classify_waveform_form(t, v, 50.0) == UNCERTAIN

    def test_empty_input_is_uncertain_not_a_crash(self):
        assert classify_waveform_form(np.array([]), np.array([]), 50.0) == UNCERTAIN

    def test_harmonics_still_classified_instantaneous(self):
        t, fundamental = _sinusoid(fs=5000.0, f0=50.0, duration=1.0, amplitude=1.0)
        _, third_harmonic = _sinusoid(fs=5000.0, f0=150.0, duration=1.0, amplitude=0.3)
        v = fundamental + third_harmonic
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS
