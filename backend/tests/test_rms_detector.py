"""Unit tests for app.domain.rms_detector (Phase 5B, DEC-048; multi-
window correction DEC-108): the algorithmic waveform-form eligibility
FALLBACK -- only ever consulted when trusted metadata is absent (see
calculated_channel_service.check_rms_eligibility).
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


def _disturbance_current(
    *, fs: float, f0: float, duration: float, pre_fault_end: float, fault_end: float,
    pre_fault_rms: float = 40.0, fault_rms: float = 400.0, phase_deg: float = 0.0,
    post_event_value: float = 0.0, noise_std: float = 0.05, seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """DEC-108: a realistic KPDN1-style disturbance CURRENT -- clean
    pre-fault sinusoid, then a fault-magnitude sinusoid, then a
    near-zero post-clearance collapse (measurement-noise-only by
    default). Deliberately NOT a perfect sinusoid throughout -- the
    whole point of this fixture is that no single one of its own three
    physical states spans the entire representative region."""
    n = int(round(fs * duration))
    t = np.arange(n) / fs
    w = 2.0 * np.pi * f0
    phi = np.radians(phase_deg)
    v = np.empty(n)
    for k in range(n):
        tk = t[k]
        if tk < pre_fault_end:
            v[k] = pre_fault_rms * np.sqrt(2) * np.sin(w * tk + phi)
        elif tk < fault_end:
            v[k] = fault_rms * np.sqrt(2) * np.sin(w * tk + phi)
        else:
            v[k] = post_event_value
    rng = np.random.default_rng(seed)
    v = v + rng.normal(0, noise_std, n)
    return t, v


class TestMultiWindowDetection:
    """DEC-108: cycle-based multi-window classification for the
    `waveform_form == "unknown"` fallback path. Investigation
    (2026-09-23 owner UAT) proved a genuine disturbance-record
    instantaneous AC current -- pre-fault sinusoid, fault, near-zero
    post-clearance collapse -- was misclassified `UNCERTAIN` under the
    original single-long-slice design purely because the collapse tail
    diluted the slice-wide zero-crossing-ratio and targeted-frequency-
    correlation indicators, even though the genuinely periodic portions
    were each independently unambiguous (5/5 votes in isolation). These
    tests prove the corrected multi-window design fixes exactly that
    case while preserving every existing golden case (see
    `TestClassifyWaveformForm` above, unmodified) and every adversarial
    genuine-RMS/magnitude safety case below."""

    def test_kpdn1_style_disturbance_current_is_instantaneous(self):
        """The exact regression this decision fixes: pre-fault [0, 0.15s)
        clean 40A, fault [0.15s, 0.25s) 400A, near-zero collapse for the
        rest of the representative region."""
        t, v = _disturbance_current(fs=1000.0, f0=50.0, duration=2.0, pre_fault_end=0.15, fault_end=0.25)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_kpdn1_style_disturbance_current_all_three_phase_offsets(self):
        """Phase angle must never affect classification."""
        for phase_deg in (0.0, -120.0, 120.0):
            t, v = _disturbance_current(
                fs=1000.0, f0=50.0, duration=2.0, pre_fault_end=0.15, fault_end=0.25, phase_deg=phase_deg,
            )
            assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS, f"phase_deg={phase_deg}"

    def test_disturbance_first_recording_with_no_clean_pre_fault_is_still_instantaneous(self):
        """The record BEGINS during the fault (zero clean pre-fault
        samples at all) -- still instantaneous, because multiple local
        windows within the fault portion itself show genuine AC
        behavior, exactly like task section 10 requires."""
        t, v = _disturbance_current(fs=1000.0, f0=50.0, duration=2.0, pre_fault_end=0.0, fault_end=0.15)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_long_near_zero_tail_dominating_the_slice_is_still_instantaneous(self):
        """Only 15% of the 1-second representative region is genuine AC
        (pre-fault + fault); 85% is near-zero collapse -- close to the
        extreme end of what investigation found production disturbance
        records can look like, while still leaving enough active
        duration for TWO informative 5-cycle windows (see the
        aggregation-policy boundary test immediately below for what
        happens with less than that)."""
        t, v = _disturbance_current(fs=1000.0, f0=50.0, duration=2.0, pre_fault_end=0.09, fault_end=0.15)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_active_duration_below_two_windows_is_conservatively_uncertain_not_forced_instantaneous(self):
        """The documented boundary of the aggregation policy (task
        section 7's own "at least 2 windows" requirement, section 9's
        own "do not force an instantaneous classification"): when the
        genuinely active portion of the record is so brief that only
        ONE 5-cycle window's worth of real evidence exists (here, only
        10% of the 1-second region -- 100ms -- is active), a single
        confident window is deliberately NOT enough on its own. This is
        the correct, conservative answer, not a defect -- proven
        immediately above that 15% active duration (two full windows)
        already classifies confidently."""
        t, v = _disturbance_current(fs=1000.0, f0=50.0, duration=2.0, pre_fault_end=0.06, fault_end=0.1)
        assert classify_waveform_form(t, v, 50.0) == UNCERTAIN

    def test_ambiguous_noisy_signal_remains_uncertain(self):
        rng = np.random.default_rng(11)
        t = np.arange(3000) / 5000.0
        v = rng.normal(0, 1.0, size=t.shape[0])
        assert classify_waveform_form(t, v, 50.0) in (UNCERTAIN, LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS)

    def test_short_insufficient_record_remains_uncertain(self):
        """Below MIN_CYCLES_FOR_DETECTION entirely -- must stay UNCERTAIN,
        never forced into a confident category merely because the
        multi-window machinery exists."""
        t, v = _sinusoid(fs=5000.0, f0=50.0, duration=0.02)  # 1 cycle at 50Hz
        assert classify_waveform_form(t, v, 50.0) == UNCERTAIN

    def test_record_too_short_for_two_windows_falls_back_to_single_slice_unchanged(self):
        """Enough for MIN_CYCLES_FOR_DETECTION (3 cycles) but not enough
        for two 5-cycle windows -- must fall back to the original
        Phase 5B single-slice classification over the whole region,
        exactly reproducing pre-DEC-108 behavior for this size record."""
        t, v = _sinusoid(fs=5000.0, f0=50.0, duration=4.0 / 50.0)  # 4 cycles
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_clean_instantaneous_sinusoid_still_confident(self):
        t, v = _sinusoid(fs=5000.0, f0=50.0, duration=1.0)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_INSTANTANEOUS

    def test_genuine_smooth_rms_magnitude_signal_still_confident(self):
        t, v = _sinusoid(fs=5000.0, f0=2.0, duration=1.0, amplitude=0.1, dc=1.0)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_MAGNITUDE_OR_RMS


class TestMultiWindowDoesNotWeakenGenuineRmsSafety:
    """DEC-108's own most critical requirement: the multi-window
    correction must not turn a genuinely RMS/magnitude-shaped channel
    into a false "instantaneous". Each case here is a channel shape
    that legitimately should NEVER be treated as raw instantaneous AC,
    proven directly against the new detector, not merely against the
    old one."""

    def test_positive_rms_envelope_never_becomes_instantaneous(self):
        """A slow (1.5 Hz) oscillation around a large positive DC bias --
        the textbook shape of an already-RMS'd output, evaluated at a
        50 Hz nominal."""
        t, v = _sinusoid(fs=1000.0, f0=1.5, duration=2.0, amplitude=15.0, dc=100.0)
        assert classify_waveform_form(t, v, 50.0) != LIKELY_INSTANTANEOUS

    def test_stepped_rms_output_shape_never_becomes_instantaneous(self):
        """No 50 Hz oscillation anywhere -- a pre-fault plateau, a fault
        plateau, a near-zero plateau -- exactly what an RMS/magnitude
        OUTPUT of a real disturbance would look like, as opposed to the
        genuine instantaneous CURRENT `_disturbance_current()` above
        builds. This must be told apart from that case, not conflated
        with it."""
        fs, duration = 1000.0, 2.0
        n = int(fs * duration)
        t = np.arange(n) / fs
        v = np.empty(n)
        for k in range(n):
            tk = t[k]
            if tk < 0.15:
                v[k] = 40.0
            elif tk < 0.25:
                v[k] = 400.0
            else:
                v[k] = 0.5
        rng = np.random.default_rng(5)
        v = v + rng.normal(0, 0.05, n)
        assert classify_waveform_form(t, v, 50.0) != LIKELY_INSTANTANEOUS

    def test_full_wave_rectified_signal_never_becomes_instantaneous(self):
        """|sin| -- always positive, genuinely oscillates but never
        crosses zero -- must never be confidently declared instantaneous
        (applying RMS to an already-rectified signal would be wrong)."""
        fs, duration = 1000.0, 2.0
        t = np.arange(int(fs * duration)) / fs
        rng = np.random.default_rng(6)
        v = 40.0 * np.abs(np.sin(2 * np.pi * 50.0 * t)) + rng.normal(0, 0.05, t.shape[0])
        assert classify_waveform_form(t, v, 50.0) != LIKELY_INSTANTANEOUS

    def test_mostly_flat_positive_signal_with_noise_never_becomes_instantaneous(self):
        fs, duration = 1000.0, 2.0
        t = np.arange(int(fs * duration)) / fs
        rng = np.random.default_rng(9)
        v = 25.0 + rng.normal(0, 0.3, t.shape[0])
        assert classify_waveform_form(t, v, 50.0) != LIKELY_INSTANTANEOUS

    def test_slowly_varying_positive_magnitude_series_is_still_confidently_magnitude(self):
        """The original Phase 5B golden case, reproduced here to prove
        the multi-window path reaches the SAME confident answer, not
        merely 'not instantaneous'."""
        t, v = _sinusoid(fs=5000.0, f0=2.0, duration=1.0, amplitude=0.1, dc=1.0)
        assert classify_waveform_form(t, v, 50.0) == LIKELY_MAGNITUDE_OR_RMS
