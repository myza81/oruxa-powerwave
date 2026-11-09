"""Tests for waveform_evidence.py (Slice 6A prototype).

Covers 18 waveform test categories plus integration tests with
voltage_hypothesis.evaluate_voltage_hypotheses().

All waveforms are synthetic (numpy-generated). Values are in kV throughout.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.waveform_evidence import (
    LINE_TO_GROUND,
    LINE_TO_LINE,
    SQRT_2,
    SQRT_3,
    WaveformEvidence,
    corroborate_hypothesis,
    extract_waveform_evidence,
)

# ---------------------------------------------------------------------------
# Synthetic waveform helpers
# ---------------------------------------------------------------------------

SAMPLE_RATE = 1600.0   # 32 samples/cycle at 50 Hz
FREQ_HZ = 50.0


def _sine_kv(
    nominal_ll_kv: float,
    duration_s: float,
    phase_deg: float = 0.0,
    amplitude_factor: float = 1.0,
    sample_rate: float = SAMPLE_RATE,
    freq_hz: float = FREQ_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (time, voltage_kv) for a sinusoidal L-G voltage.

    ``nominal_ll_kv`` is the system line-to-line voltage.  The resulting
    waveform has an L-G RMS of ``amplitude_factor × nominal_ll_kv / √3``.
    """
    rms_lg = nominal_ll_kv / SQRT_3 * amplitude_factor
    peak = rms_lg * SQRT_2
    t = np.arange(0, duration_s, 1.0 / sample_rate)
    v = peak * np.sin(2 * np.pi * freq_hz * t + math.radians(phase_deg))
    return t, v


def _three_phase(
    nominal_ll_kv: float,
    duration_s: float,
    sample_rate: float = SAMPLE_RATE,
    freq_hz: float = FREQ_HZ,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return balanced three-phase dict {VA, VB, VC} → (time, values_kv)."""
    ta, va = _sine_kv(nominal_ll_kv, duration_s, 0.0, sample_rate=sample_rate, freq_hz=freq_hz)
    _, vb = _sine_kv(nominal_ll_kv, duration_s, -120.0, sample_rate=sample_rate, freq_hz=freq_hz)
    _, vc = _sine_kv(nominal_ll_kv, duration_s, 120.0, sample_rate=sample_rate, freq_hz=freq_hz)
    return {"VA": (ta, va), "VB": (ta, vb), "VC": (ta, vc)}


def _rms_lg(nominal_ll_kv: float, factor: float = 1.0) -> float:
    """Expected L-G RMS (kV) for a system at factor × nominal."""
    return nominal_ll_kv / SQRT_3 * factor


# ---------------------------------------------------------------------------
# Category 1 — PULU 275 kV L-G stable (1.023 pu)
# ---------------------------------------------------------------------------

class TestPulu275kvLgStable:
    """Cat 1 — 275 kV L-L at 1.023 pu; 10-cycle stable; L-G RMS ≈ 162.42 kV."""

    PU = 1.023
    NOM_LL = 275.0
    DURATION = 0.2  # 10 cycles

    def setup_method(self):
        t, v = _sine_kv(self.NOM_LL, self.DURATION, amplitude_factor=self.PU)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_state_all_stable(self):
        assert self.evidence.recording_state == "all_stable"

    def test_suitable_for_corroboration(self):
        assert self.evidence.suitable_for_corroboration is True

    def test_no_onset(self):
        assert self.evidence.has_disturbance_onset is False

    def test_stable_window_exists(self):
        assert self.evidence.best_stable_window is not None

    def test_stable_rms_approx_1023pu(self):
        # Measured RMS ≈ 1.023 × 275/√3 ≈ 162.42 kV
        expected_rms = _rms_lg(self.NOM_LL, self.PU)
        obs = self.evidence.best_stable_window.mean_rms_kv
        assert abs(obs - expected_rms) / expected_rms < 0.005, (
            f"Observed {obs:.4f} kV, expected {expected_rms:.4f} kV"
        )

    def test_corroboration_275kv_corroborated(self):
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"
        assert c.ratio is not None
        assert 0.90 <= c.ratio <= 1.10

    def test_corroboration_ratio_near_pu(self):
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.ratio is not None
        assert abs(c.ratio - self.PU) < 0.01, (
            f"Ratio {c.ratio:.4f} differs from expected pu {self.PU}"
        )


# ---------------------------------------------------------------------------
# Category 2 — SGT1 132 kV L-G stable (nominal 1.0 pu)
# ---------------------------------------------------------------------------

class TestSgt1132kvLgStable:
    """Cat 2 — 132 kV L-L, nominal L-G RMS = 132/√3 ≈ 76.21 kV."""

    NOM_LL = 132.0
    DURATION = 0.2

    def setup_method(self):
        t, v = _sine_kv(self.NOM_LL, self.DURATION)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_state_all_stable(self):
        assert self.evidence.recording_state == "all_stable"

    def test_stable_rms_approx_nominal_lg(self):
        expected = _rms_lg(self.NOM_LL)
        obs = self.evidence.best_stable_window.mean_rms_kv
        assert abs(obs - expected) / expected < 0.005

    def test_corroboration_132kv_corroborated(self):
        c = corroborate_hypothesis(132.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"

    def test_corroboration_275kv_magnitude_disagreement(self):
        # 275 kV expected ≈ 158.8 kV, but observed ≈ 76.2 kV → ratio ≈ 0.48 → magnitude_disagreement
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "magnitude_disagreement"
        assert c.notable_magnitude_gap is True


# ---------------------------------------------------------------------------
# Category 3 — 76.2 kV VT phase-winding (Hypothesis B corroboration)
# ---------------------------------------------------------------------------

class TestVtWinding76kv:
    """Cat 3 — VT phase-winding 76.2 kV recorded; actual system = 132 kV (√3 × 76.2).

    Corroborate_hypothesis for Hyp B: candidate_ll = 132.0 kV.
    Expected L-G = 132/√3 ≈ 76.21 kV.  Observed ≈ 76.2 kV → corroborated.
    """

    PHASE_WINDING_KV = 76.21   # = 132 / √3
    DURATION = 0.2

    def setup_method(self):
        # Create a channel recording at exactly 76.21 kV RMS
        rms = self.PHASE_WINDING_KV
        peak = rms * SQRT_2
        t = np.arange(0, self.DURATION, 1.0 / SAMPLE_RATE)
        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_stable_rms_approx_phase_winding(self):
        obs = self.evidence.best_stable_window.mean_rms_kv
        assert abs(obs - self.PHASE_WINDING_KV) / self.PHASE_WINDING_KV < 0.005

    def test_corroboration_132kv_hyp_b(self):
        # Hypothesis B: candidate_ll=132.0 kV, expected L-G = 132/√3 ≈ 76.21 kV
        c = corroborate_hypothesis(132.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated", f"Ratio={c.ratio:.3f}"

    def test_corroboration_76kv_as_candidate_ll_magnitude_disagreement(self):
        # If we mistakenly treat 76.2 kV as the candidate L-L voltage:
        # expected L-G = 76.2/√3 ≈ 44.0 kV, but observed = 76.2 kV → ratio ≈ 1.73 → magnitude_disagreement
        c = corroborate_hypothesis(76.21, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "magnitude_disagreement"
        assert c.notable_magnitude_gap is True


# ---------------------------------------------------------------------------
# Category 4 — Ambiguous 132 kV resolved by waveform (Hyp A vs 228.6 kV)
# ---------------------------------------------------------------------------

class TestAmbiguous132kvVs228kv:
    """Cat 4 — primary_ratio=132.0 on L-G: ambiguous between 132 kV (Hyp A) and
    228.6 kV (Hyp B, since 132×√3=228.6≈230 kV).  Waveform at 76.2 kV L-G RMS
    corroborates Hyp A and contradicts Hyp B.
    """

    OBSERVED_LG_RMS = 76.21   # = 132 / √3

    def setup_method(self):
        # Waveform at 132/√3 kV L-G RMS
        rms = self.OBSERVED_LG_RMS
        peak = rms * SQRT_2
        t = np.arange(0, 0.2, 1.0 / SAMPLE_RATE)
        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_corroboration_132kv_hyp_a_corroborated(self):
        # Hyp A: candidate=132 kV, expected L-G = 132/√3 = 76.21, observed=76.21 → ratio≈1.0
        c = corroborate_hypothesis(132.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"
        assert 0.95 <= c.ratio <= 1.05

    def test_corroboration_228kv_hyp_b_magnitude_disagreement(self):
        # Hyp B: candidate=228.6 kV, expected L-G = 228.6/√3 = 132.0 kV, observed=76.21 kV
        # ratio = 76.21/132.0 ≈ 0.577 → magnitude_disagreement with notable gap
        hyp_b_candidate = 132.0 * SQRT_3   # ≈ 228.6 kV
        c = corroborate_hypothesis(hyp_b_candidate, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "magnitude_disagreement"
        assert c.ratio is not None and c.ratio < 0.65
        assert c.notable_magnitude_gap is True

    def test_corroboration_ratio_values(self):
        # Verify the ratio arithmetic is correct
        c_a = corroborate_hypothesis(132.0, LINE_TO_GROUND, self.evidence)
        hyp_b_candidate = 132.0 * SQRT_3
        c_b = corroborate_hypothesis(hyp_b_candidate, LINE_TO_GROUND, self.evidence)
        # Hyp B ratio ≈ Hyp A expected / Hyp B expected = (132/√3) / (228.6/√3) = 132/228.6 ≈ 0.577
        expected_ratio_b = (132.0 / SQRT_3) / (hyp_b_candidate / SQRT_3)
        assert c_b.ratio is not None
        assert abs(c_b.ratio - expected_ratio_b) < 0.01


# ---------------------------------------------------------------------------
# Category 5 — Ambiguous 230 kV vs 398 kV resolved by waveform
# ---------------------------------------------------------------------------

class TestAmbiguous230kvVs398kv:
    """Cat 5 — primary_ratio=230.0 on L-G channels; Hyp A=230 kV, Hyp B=230×√3≈398.4 kV.
    Waveform at 230/√3 ≈ 132.8 kV L-G → corroborates Hyp A, contradicts Hyp B.
    """

    CANDIDATE_A = 230.0        # kV
    CANDIDATE_B = 230.0 * SQRT_3  # ≈ 398.4 kV

    def setup_method(self):
        # Waveform at 230/√3 kV L-G RMS
        rms = self.CANDIDATE_A / SQRT_3
        peak = rms * SQRT_2
        t = np.arange(0, 0.2, 1.0 / SAMPLE_RATE)
        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_corroboration_230kv_corroborated(self):
        c = corroborate_hypothesis(self.CANDIDATE_A, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"

    def test_corroboration_398kv_magnitude_disagreement(self):
        # expected = 398.4/√3 = 230.0 kV, observed = 132.8 kV → ratio ≈ 0.577 → magnitude_disagreement
        c = corroborate_hypothesis(self.CANDIDATE_B, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "magnitude_disagreement"
        assert c.notable_magnitude_gap is True


# ---------------------------------------------------------------------------
# Category 6 — Healthy stable three-phase recording (all_stable)
# ---------------------------------------------------------------------------

class TestHealthyStablePrefault:
    """Cat 6 — 10-cycle balanced three-phase at 132 kV, no disturbance → all_stable."""

    NOM_LL = 132.0

    def setup_method(self):
        channels = _three_phase(self.NOM_LL, 0.2)
        self.evidence = extract_waveform_evidence(channels)

    def test_state_all_stable(self):
        assert self.evidence.recording_state == "all_stable"

    def test_suitable_for_corroboration(self):
        assert self.evidence.suitable_for_corroboration is True

    def test_phase_balance_ok(self):
        assert self.evidence.phase_magnitude_balance_ok is True

    def test_phase_unbalance_small(self):
        assert self.evidence.phase_unbalance_pct is not None
        assert self.evidence.phase_unbalance_pct < 5.0

    def test_all_three_phases_in_window(self):
        bw = self.evidence.best_stable_window
        assert bw is not None
        assert len(bw.rms_per_channel) == 3

    def test_no_onset(self):
        assert self.evidence.has_disturbance_onset is False


# ---------------------------------------------------------------------------
# Category 7 — Ramping voltage (no stable window → disturbed_no_prefault)
# ---------------------------------------------------------------------------

class TestSustainedVoltageRamp:
    """Cat 7 — Voltage amplitude increases 10 % per cycle (10 distinct levels: 0.5→1.5×).
    Each cycle has a different peak amplitude, so no 5-consecutive-cycle window is
    stable (CV ≈ 20 %).  suitable_for_corroboration must be False.
    """

    NOM_LL = 132.0

    def setup_method(self):
        # Apply a step-change amplitude per cycle so cycle-level RMS varies by ~10 %/cycle
        # Amplitudes: 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4 × nominal
        base_rms = self.NOM_LL / SQRT_3
        peak_nominal = base_rms * SQRT_2
        CYCLES = 10
        samples_per_cycle = int(SAMPLE_RATE / FREQ_HZ)
        total = CYCLES * samples_per_cycle
        t = np.arange(0, total) / SAMPLE_RATE
        v = np.zeros(total)
        for k in range(CYCLES):
            amp = 0.5 + k * 0.1
            sl = slice(k * samples_per_cycle, (k + 1) * samples_per_cycle)
            v[sl] = amp * peak_nominal * np.sin(2 * np.pi * FREQ_HZ * t[sl])
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_no_stable_window(self):
        # With a linear ramp in amplitude, the CV within any 5-cycle window exceeds threshold
        assert self.evidence.best_stable_window is None

    def test_not_suitable(self):
        assert self.evidence.suitable_for_corroboration is False

    def test_recording_state_disturbed(self):
        assert self.evidence.recording_state in (
            "disturbed_no_prefault", "insufficient_data"
        )

    def test_corroboration_indeterminate(self):
        c = corroborate_hypothesis(132.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "indeterminate"


# ---------------------------------------------------------------------------
# Category 8 — Severe fault (10-cycle prefault + near-zero collapse)
# ---------------------------------------------------------------------------

class TestSevereFaultRecording:
    """Cat 8 — 10 cycles nominal prefault, then voltage collapses to near zero.
    State must be stable_prefault; prefault window is marked is_prefault=True.
    """

    NOM_LL = 275.0
    PREFAULT_CYCLES = 10
    FAULT_CYCLES = 5

    def setup_method(self):
        total = (self.PREFAULT_CYCLES + self.FAULT_CYCLES) / FREQ_HZ
        t_all = np.arange(0, total, 1.0 / SAMPLE_RATE)
        rms_lg = self.NOM_LL / SQRT_3
        peak = rms_lg * SQRT_2
        prefault_samples = int(self.PREFAULT_CYCLES / FREQ_HZ * SAMPLE_RATE)

        v = peak * np.sin(2 * np.pi * FREQ_HZ * t_all)
        v[prefault_samples:] = 0.0  # Fault: voltage collapses
        self.t = t_all
        self.v = v
        self.evidence = extract_waveform_evidence({"VA": (t_all, v)})

    def test_state_stable_prefault(self):
        assert self.evidence.recording_state == "stable_prefault"

    def test_suitable_for_corroboration(self):
        assert self.evidence.suitable_for_corroboration is True

    def test_onset_detected(self):
        assert self.evidence.has_disturbance_onset is True
        assert self.evidence.onset_time_s is not None

    def test_stable_window_is_prefault(self):
        bw = self.evidence.best_stable_window
        assert bw is not None
        assert bw.is_prefault is True

    def test_stable_window_before_onset(self):
        bw = self.evidence.best_stable_window
        onset = self.evidence.onset_time_s
        assert bw is not None and onset is not None
        assert bw.end_s <= onset + 0.001  # Allow for window edge rounding

    def test_prefault_rms_approx_nominal(self):
        bw = self.evidence.best_stable_window
        assert bw is not None
        expected = self.NOM_LL / SQRT_3
        assert abs(bw.mean_rms_kv - expected) / expected < 0.01

    def test_corroboration_275kv_corroborated(self):
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"


# ---------------------------------------------------------------------------
# Category 9 — Single-phase fault (unbalanced three-phase)
# ---------------------------------------------------------------------------

class TestSinglePhaseFault:
    """Cat 9 — VA drops to 0.5 pu; VB and VC normal.
    phase_magnitude_balance_ok must be False.
    """

    NOM_LL = 132.0

    def setup_method(self):
        t = np.arange(0, 0.2, 1.0 / SAMPLE_RATE)
        rms_nom = self.NOM_LL / SQRT_3
        peak_nom = rms_nom * SQRT_2

        va = 0.5 * peak_nom * np.sin(2 * np.pi * FREQ_HZ * t)
        vb = peak_nom * np.sin(2 * np.pi * FREQ_HZ * t - 2 * math.pi / 3)
        vc = peak_nom * np.sin(2 * np.pi * FREQ_HZ * t + 2 * math.pi / 3)
        self.evidence = extract_waveform_evidence({"VA": (t, va), "VB": (t, vb), "VC": (t, vc)})

    def test_phase_balance_not_ok(self):
        assert self.evidence.phase_magnitude_balance_ok is False

    def test_unbalance_exceeds_threshold(self):
        # VA at 0.5 pu, VB/VC at 1.0 pu → mean ≈ 0.833 × nominal, max_dev ≈ 0.333 → unbalance ≈ 40%
        assert self.evidence.phase_unbalance_pct is not None
        assert self.evidence.phase_unbalance_pct > 25.0

    def test_stable_window_exists(self):
        # Fault is constant (not varying), so a stable window should be found
        # The extractor finds stability based on RMS variation, not absolute level
        assert self.evidence.best_stable_window is not None

    def test_suitable_for_corroboration_true(self):
        # Even though unbalanced, stable RMS can still be used for corroboration
        # (with caveat that mean is affected by the faulted phase)
        assert self.evidence.suitable_for_corroboration is True


# ---------------------------------------------------------------------------
# Category 10 — Recording starts after fault (disturbed_no_prefault)
# ---------------------------------------------------------------------------

class TestRecordingStartsAfterFault:
    """Cat 10 — Entire recording has highly variable amplitude (randomly changing
    each cycle), simulating a recording captured entirely during a fault with no
    stable prefault reference.  No stable window should be found.
    """

    NOM_LL = 275.0

    def setup_method(self):
        # Apply random cycle amplitudes (between 0.1 and 1.5 × nominal) so that
        # no 5-cycle window can be stable.
        base_rms = self.NOM_LL / SQRT_3
        peak_nominal = base_rms * SQRT_2
        CYCLES = 10
        samples_per_cycle = int(SAMPLE_RATE / FREQ_HZ)
        total = CYCLES * samples_per_cycle
        t = np.arange(0, total) / SAMPLE_RATE
        v = np.zeros(total)
        # Use a fixed seed for reproducibility; ensure large variance cycle-to-cycle
        rng = np.random.default_rng(seed=42)
        amplitudes = [0.3, 1.2, 0.5, 0.9, 0.2, 1.1, 0.7, 0.4, 1.3, 0.1]
        for k, amp in enumerate(amplitudes):
            sl = slice(k * samples_per_cycle, (k + 1) * samples_per_cycle)
            v[sl] = amp * peak_nominal * np.sin(2 * np.pi * FREQ_HZ * t[sl])
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_no_suitable_corroboration(self):
        assert self.evidence.suitable_for_corroboration is False

    def test_recording_state_disturbed(self):
        assert self.evidence.recording_state in (
            "disturbed_no_prefault", "insufficient_data"
        )

    def test_corroboration_indeterminate(self):
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "indeterminate"


# ---------------------------------------------------------------------------
# Category 11 — Switching transient (brief disturbance, stable before and after)
# ---------------------------------------------------------------------------

class TestSwitchingTransient:
    """Cat 11 — 7 cycles stable, 1-cycle spike (2× amplitude), then 10 cycles stable.
    The prefault stable window (7 cycles) must be detected.
    """

    NOM_LL = 132.0
    PREFAULT_CYCLES = 7
    SPIKE_CYCLES = 1
    POSTFAULT_CYCLES = 10

    def setup_method(self):
        total = (self.PREFAULT_CYCLES + self.SPIKE_CYCLES + self.POSTFAULT_CYCLES) / FREQ_HZ
        t = np.arange(0, total, 1.0 / SAMPLE_RATE)
        rms_lg = self.NOM_LL / SQRT_3
        peak = rms_lg * SQRT_2

        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        # Apply 2× spike to the spike region
        pre_s = int(self.PREFAULT_CYCLES / FREQ_HZ * SAMPLE_RATE)
        spike_s = int(self.SPIKE_CYCLES / FREQ_HZ * SAMPLE_RATE)
        v[pre_s: pre_s + spike_s] *= 2.5  # Spike up

        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_stable_window_found(self):
        assert self.evidence.best_stable_window is not None

    def test_suitable_for_corroboration(self):
        # Either stable_prefault (onset detected) or all_stable
        assert self.evidence.suitable_for_corroboration is True

    def test_state_valid(self):
        assert self.evidence.recording_state in ("stable_prefault", "all_stable")


# ---------------------------------------------------------------------------
# Category 12 — Clipped waveform (flat-top)
# ---------------------------------------------------------------------------

class TestHarmonicDistortedClipped:
    """Cat 12 — Severely clipped sinusoid (clipped at 70% of peak).
    'clipping_detected' limitation expected.
    """

    NOM_LL = 132.0

    def setup_method(self):
        t = np.arange(0, 0.2, 1.0 / SAMPLE_RATE)
        rms_lg = self.NOM_LL / SQRT_3
        peak = rms_lg * SQRT_2
        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        # Clip at 70% of peak
        clip_level = 0.70 * peak
        v = np.clip(v, -clip_level, clip_level)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_clipping_detected_in_limitations(self):
        assert "clipping_detected" in self.evidence.limitations

    def test_stable_window_still_found(self):
        # Clipped signal has stable RMS, so a stable window should still be found
        assert self.evidence.best_stable_window is not None


# ---------------------------------------------------------------------------
# Category 13 — Single channel (no three-phase balance check)
# ---------------------------------------------------------------------------

class TestIncompletePhaseSingleChannel:
    """Cat 13 — Only one voltage channel available; balance check skipped."""

    def setup_method(self):
        t, v = _sine_kv(275.0, 0.2)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_single_phase_limitation(self):
        assert "single_phase_no_balance_check" in self.evidence.limitations

    def test_phase_balance_none(self):
        # Only one channel; balance cannot be computed
        assert self.evidence.phase_magnitude_balance_ok is None
        assert self.evidence.phase_unbalance_pct is None


# ---------------------------------------------------------------------------
# Category 14 — PS marker independence (waveform only, no COMTRADE PS flag)
# ---------------------------------------------------------------------------

class TestUnknownPsMarker:
    """Cat 14 — Waveform evidence is computed from waveform data only.
    The PS (primary/secondary) marker from COMTRADE is not used here.
    Test verifies the same corroboration result regardless of channel names.
    """

    NOM_LL = 275.0

    def test_channel_name_does_not_affect_corroboration(self):
        t, v = _sine_kv(self.NOM_LL, 0.2)
        evidence_a = extract_waveform_evidence({"VA": (t, v)})
        evidence_b = extract_waveform_evidence({"Some_Random_Name": (t, v)})

        c_a = corroborate_hypothesis(275.0, LINE_TO_GROUND, evidence_a)
        c_b = corroborate_hypothesis(275.0, LINE_TO_GROUND, evidence_b)

        assert c_a.verdict == c_b.verdict == "corroborated"
        # Ratios must be identical (same waveform)
        assert c_a.ratio is not None and c_b.ratio is not None
        assert abs(c_a.ratio - c_b.ratio) < 1e-6


# ---------------------------------------------------------------------------
# Category 15 — Secondary recording (110 V L-G = 0.11 kV)
# ---------------------------------------------------------------------------

class TestSecondaryRecording:
    """Cat 15 — VT secondary at 110 V L-G (= 0.11 kV).
    Candidate L-L = 110×√3/1000 ≈ 0.1905 kV → expected L-G = 0.11 kV → corroborated.
    """

    SECONDARY_LG_KV = 0.11000   # 110 V in kV

    def setup_method(self):
        rms = self.SECONDARY_LG_KV
        peak = rms * SQRT_2
        t = np.arange(0, 0.2, 1.0 / SAMPLE_RATE)
        v = peak * np.sin(2 * np.pi * FREQ_HZ * t)
        self.evidence = extract_waveform_evidence({"VA": (t, v)})

    def test_stable_rms_approx_110v(self):
        bw = self.evidence.best_stable_window
        assert bw is not None
        assert abs(bw.mean_rms_kv - self.SECONDARY_LG_KV) / self.SECONDARY_LG_KV < 0.005

    def test_corroboration_190v_ll_corroborated(self):
        # Candidate L-L ≈ 0.11 × √3 ≈ 0.1905 kV
        candidate_ll = self.SECONDARY_LG_KV * SQRT_3
        c = corroborate_hypothesis(candidate_ll, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "corroborated"
        assert c.ratio is not None and 0.95 <= c.ratio <= 1.05

    def test_corroboration_275kv_magnitude_disagreement(self):
        # 275 kV expected ≈ 158.8 kV, observed = 0.11 kV → ratio ≈ 0.000693 → magnitude_disagreement
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, self.evidence)
        assert c.verdict == "magnitude_disagreement"
        assert c.notable_magnitude_gap is True


# ---------------------------------------------------------------------------
# Category 16 — Multiple voltage groups (independent calls)
# ---------------------------------------------------------------------------

class TestMultipleVoltageGroups:
    """Cat 16 — Two independent calls for 275 kV and 132 kV groups."""

    def test_independent_groups(self):
        t1, v1 = _sine_kv(275.0, 0.2)
        t2, v2 = _sine_kv(132.0, 0.2)

        ev_275 = extract_waveform_evidence({"VA": (t1, v1)})
        ev_132 = extract_waveform_evidence({"VA": (t2, v2)})

        c_275 = corroborate_hypothesis(275.0, LINE_TO_GROUND, ev_275)
        c_132 = corroborate_hypothesis(132.0, LINE_TO_GROUND, ev_132)

        assert c_275.verdict == "corroborated"
        assert c_132.verdict == "corroborated"

        # Cross-check: 275 kV not corroborated by 132 kV waveform
        c_cross = corroborate_hypothesis(275.0, LINE_TO_GROUND, ev_132)
        assert c_cross.verdict == "magnitude_disagreement"


# ---------------------------------------------------------------------------
# Category 17 — Channel name does not affect corroboration
# ---------------------------------------------------------------------------

class TestDuplicateChannelNameEvidence:
    """Cat 17 — Corroboration uses waveform RMS, not channel names.
    Two calls with the same waveform but different channel names give the same result.
    """

    NOM_LL = 275.0

    def test_name_independence(self):
        t, v = _sine_kv(self.NOM_LL, 0.2)

        ev1 = extract_waveform_evidence({"VA_275KV": (t, v)})
        ev2 = extract_waveform_evidence({"VA": (t, v)})

        c1 = corroborate_hypothesis(275.0, LINE_TO_GROUND, ev1)
        c2 = corroborate_hypothesis(275.0, LINE_TO_GROUND, ev2)

        assert c1.verdict == c2.verdict == "corroborated"
        assert c1.ratio == c2.ratio


# ---------------------------------------------------------------------------
# Category 18 — Insufficient samples (< 3 cycles)
# ---------------------------------------------------------------------------

class TestInsufficientSamples:
    """Cat 18 — Very short recording (< 3 cycles) → insufficient_data."""

    def test_one_cycle_recording(self):
        t, v = _sine_kv(275.0, 0.015)  # 0.75 cycles at 50 Hz
        evidence = extract_waveform_evidence({"VA": (t, v)})

        assert evidence.recording_state == "insufficient_data"
        assert evidence.suitable_for_corroboration is False
        assert "insufficient_cycles" in evidence.limitations

    def test_corroboration_indeterminate_on_short_recording(self):
        t, v = _sine_kv(275.0, 0.01)  # 0.5 cycles
        evidence = extract_waveform_evidence({"VA": (t, v)})
        c = corroborate_hypothesis(275.0, LINE_TO_GROUND, evidence)
        assert c.verdict == "indeterminate"


# ---------------------------------------------------------------------------
# Numerical validation — sliding RMS accuracy
# ---------------------------------------------------------------------------

class TestNumericalValidation:
    """Verify that the sliding RMS implementation gives correct values."""

    def test_pure_sine_rms_exact(self):
        """True RMS of sin(ωt) over a full cycle = peak / √2."""
        NOMINAL_LL = 275.0
        rms_expected = NOMINAL_LL / SQRT_3
        t, v = _sine_kv(NOMINAL_LL, 1.0)  # 50 cycles
        evidence = extract_waveform_evidence({"VA": (t, v)})
        assert evidence.best_stable_window is not None
        obs = evidence.best_stable_window.mean_rms_kv
        # Numerical accuracy: within 0.1 % of theoretical
        assert abs(obs - rms_expected) / rms_expected < 0.001, (
            f"RMS error: observed {obs:.6f} kV, expected {rms_expected:.6f} kV"
        )

    def test_1023pu_rms_exact(self):
        """PULU 1.023 pu RMS must match expected value within 0.1 %."""
        PU = 1.023
        NOM_LL = 275.0
        expected = PU * NOM_LL / SQRT_3
        t, v = _sine_kv(NOM_LL, 1.0, amplitude_factor=PU)
        evidence = extract_waveform_evidence({"VA": (t, v)})
        assert evidence.best_stable_window is not None
        obs = evidence.best_stable_window.mean_rms_kv
        assert abs(obs - expected) / expected < 0.001

    def test_132kv_lg_rms(self):
        """132 kV L-L → L-G RMS = 132/√3 ≈ 76.21 kV."""
        NOM_LL = 132.0
        expected = NOM_LL / SQRT_3
        t, v = _sine_kv(NOM_LL, 1.0)
        evidence = extract_waveform_evidence({"VA": (t, v)})
        assert evidence.best_stable_window is not None
        obs = evidence.best_stable_window.mean_rms_kv
        assert abs(obs - expected) / expected < 0.001


# ---------------------------------------------------------------------------
# Integration tests with voltage_hypothesis.evaluate_voltage_hypotheses()
# ---------------------------------------------------------------------------

class TestWaveformResolvesAmbiguity:
    """Integration — 132.0 kV L-G channels are ambiguous without waveform.
    Waveform evidence is an annotation only; it does NOT change the selection
    for an ambiguous metadata result (Slice 6B §2 / DEC-212).
    The waveform can CORROBORATE a resolved hypothesis but cannot independently
    select between competing hypotheses.
    """

    def _make_channels(self):
        from app.domain.auto_base_evidence import ChannelAutoMetadata
        return [
            ChannelAutoMetadata(
                name="VA", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
            ChannelAutoMetadata(
                name="VB", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
            ChannelAutoMetadata(
                name="VC", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
        ]

    def _make_waveform_evidence_at_76kv(self):
        """Stable waveform at 132/√3 ≈ 76.21 kV L-G RMS."""
        t, v = _sine_kv(132.0, 0.2)   # _sine_kv generates L-G RMS = 132/√3
        return extract_waveform_evidence({"VA": (t, v), "VB": (t, v), "VC": (t, v)})

    def test_ambiguous_without_waveform(self):
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses
        channels = self._make_channels()
        result = evaluate_voltage_hypotheses(channels)
        assert result.selected == "ambiguous", (
            f"Expected ambiguous without waveform, got {result.selected}"
        )

    def test_still_ambiguous_with_waveform(self):
        """Waveform cannot independently resolve metadata ambiguity (Slice 6B §2)."""
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses
        channels = self._make_channels()
        wf = self._make_waveform_evidence_at_76kv()
        result = evaluate_voltage_hypotheses(channels, waveform_evidence=wf)
        assert result.selected == "ambiguous", (
            f"Waveform must not independently resolve ambiguous metadata. "
            f"Got: {result.selected}. Provenance: {result.provenance}"
        )

    def test_waveform_corroboration_attached(self):
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses
        channels = self._make_channels()
        wf = self._make_waveform_evidence_at_76kv()
        result = evaluate_voltage_hypotheses(channels, waveform_evidence=wf)
        assert result.waveform_corroboration is not None
        assert len(result.waveform_corroboration) >= 2

    def test_hyp_a_corroborated_hyp_b_magnitude_disagreement(self):
        """Waveform at 76kV corroborates Hyp A (132kV), disagrees with Hyp B (228.6kV).
        Result is still ambiguous — the corroboration is an annotation only."""
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses
        channels = self._make_channels()
        wf = self._make_waveform_evidence_at_76kv()
        result = evaluate_voltage_hypotheses(channels, waveform_evidence=wf)
        assert result.waveform_corroboration is not None
        verdicts = {c.candidate_ll_kv: c.verdict for c in result.waveform_corroboration}
        # Hyp A candidate = 132.0 kV — corroborated
        assert verdicts.get(132.0) == "corroborated"
        # Hyp B candidate ≈ 228.6 kV — magnitude_disagreement (not "inconsistent")
        hyp_b_key = next((k for k in verdicts if abs(k - 132.0 * SQRT_3) < 1.0), None)
        assert hyp_b_key is not None
        assert verdicts[hyp_b_key] == "magnitude_disagreement"
        # Selection is still ambiguous — waveform does not override metadata
        assert result.selected == "ambiguous"


class TestWaveformDoesNotOverrideAmbiguity:
    """Integration — when waveform is indeterminate (disturbed), ambiguous stays ambiguous."""

    def _make_channels(self):
        from app.domain.auto_base_evidence import ChannelAutoMetadata
        return [
            ChannelAutoMetadata(
                name="VA", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
            ChannelAutoMetadata(
                name="VB", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
        ]

    def test_disturbed_waveform_keeps_ambiguous(self):
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses

        # Disturbed waveform: random cycle amplitudes, no stable window
        base_rms = 132.0 / SQRT_3
        peak_nominal = base_rms * SQRT_2
        CYCLES = 10
        sppc = int(SAMPLE_RATE / FREQ_HZ)
        total = CYCLES * sppc
        t = np.arange(0, total) / SAMPLE_RATE
        v = np.zeros(total)
        for k, amp in enumerate([0.3, 1.2, 0.5, 0.9, 0.2, 1.1, 0.7, 0.4, 1.3, 0.1]):
            sl = slice(k * sppc, (k + 1) * sppc)
            v[sl] = amp * peak_nominal * np.sin(2 * np.pi * FREQ_HZ * t[sl])
        disturbed_ev = extract_waveform_evidence({"VA": (t, v)})

        assert disturbed_ev.suitable_for_corroboration is False

        channels = self._make_channels()
        result = evaluate_voltage_hypotheses(channels, waveform_evidence=disturbed_ev)
        assert result.selected == "ambiguous"


class TestPuluFullIntegration:
    """Integration — 275 kV channels, waveform at 1.023 pu.
    Hypothesis A (275 kV) is the only plausible one; waveform corroborates it.
    """

    def test_275kv_resolved_and_corroborated(self):
        from app.domain.auto_base_evidence import ChannelAutoMetadata
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses

        channels = [
            ChannelAutoMetadata(
                name="VA", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=275.0, secondary_ratio=None,
            ),
            ChannelAutoMetadata(
                name="VB", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=275.0, secondary_ratio=None,
            ),
        ]

        t, v = _sine_kv(275.0, 0.2, amplitude_factor=1.023)
        wf = extract_waveform_evidence({"VA": (t, v), "VB": (t, v)})

        result = evaluate_voltage_hypotheses(channels, waveform_evidence=wf)
        assert result.selected == "A"
        assert result.nominal_ll_kv == pytest.approx(275.0, rel=0.001)
        assert result.waveform_corroboration is not None

        corr_a = next(c for c in result.waveform_corroboration
                      if abs(c.candidate_ll_kv - 275.0) < 1.0)
        assert corr_a.verdict == "corroborated"
        assert corr_a.ratio is not None
        assert 0.95 <= corr_a.ratio <= 1.10


# ---------------------------------------------------------------------------
# Existing voltage_hypothesis tests must not be broken
# ---------------------------------------------------------------------------

class TestNoRegressionInVoltageHypothesis:
    """Verify that adding waveform_evidence parameter does not break existing behavior."""

    def test_no_waveform_gives_same_result(self):
        from app.domain.auto_base_evidence import ChannelAutoMetadata
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses

        channels = [
            ChannelAutoMetadata(
                name="VA", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=275.0, secondary_ratio=None,
            ),
        ]
        result_without = evaluate_voltage_hypotheses(channels)
        result_with_none = evaluate_voltage_hypotheses(channels, waveform_evidence=None)

        assert result_without.selected == result_with_none.selected
        assert result_without.nominal_ll_kv == result_with_none.nominal_ll_kv
        assert result_without.waveform_corroboration is None
        assert result_with_none.waveform_corroboration is None

    def test_waveform_corroboration_default_none(self):
        from app.domain.auto_base_evidence import ChannelAutoMetadata
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses

        channels = [
            ChannelAutoMetadata(
                name="VA", engineering_type="voltage", unit="kV",
                measurement_side="primary", primary_ratio=132.0, secondary_ratio=None,
            ),
        ]
        result = evaluate_voltage_hypotheses(channels)
        assert result.waveform_corroboration is None
