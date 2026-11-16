"""Waveform evidence extractor for voltage hypothesis corroboration (Slice 6A).

Provides a pure-domain, numpy-only component that analyses recorded voltage
waveforms to produce structured evidence suitable for corroborating (or
contradicting) a nominal-voltage hypothesis.

This module is part of the PU-001B / PU-002A design prototype.  It is NOT
wired into the import lifecycle.  The live import path remains unchanged.

Design constraints
------------------
C1  Pure numpy — no I/O, no registry, no framework dependencies.
C2  Replicates the same sliding one-cycle trailing RMS algorithm as
    ``calculated_channel.evaluate_rms()`` via a vectorised cumsum, without
    importing that module (avoids circular imports in the pure-domain layer).
C3  Analysis is capped at ``max_analysis_seconds`` (default 2.0 s) so the
    extractor never stalls on a long recording.
C4  ``suitable_for_corroboration`` is False unless a stable prefault or
    all-stable state is confirmed.  A disturbed recording must NOT be used to
    claim knowledge of nominal operating voltage.
C5  Corroboration thresholds are asymmetric: 90 %–110 % → corroborated;
    < 50 % or > 130 % → inconsistent; outside both bands → indeterminate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SQRT_2: float = math.sqrt(2.0)
SQRT_3: float = math.sqrt(3.0)

# Stable-window detection parameters
_MIN_STABLE_CYCLES_DEFAULT: int = 5
_STABILITY_THRESHOLD_PCT_DEFAULT: float = 5.0   # CV % within a stable window

# Disturbance onset threshold: % change between adjacent one-cycle RMS samples
_ONSET_THRESHOLD_PCT: float = 20.0

# Minimum cycles for a recording to be considered usable at all
_MIN_CYCLES_FOR_USABLE: int = 3

# Clipping indicator: peak/rms ratio below this → possible clipping
_CLIPPING_CREST_LOW: float = 1.25   # healthy sinusoid = √2 ≈ 1.414

# Corroboration thresholds
_CORR_LOW: float = 0.90    # ratio < 0.90 → too low for corroboration
_CORR_HIGH: float = 1.10   # ratio > 1.10 → too high for corroboration
# A wrong hypothesis (e.g. 228.6 kV where 132 kV is correct) gives ratio ≈ 1/√3 ≈ 0.577,
# so the inconsistency threshold must be above 0.577.  0.70 is safe and physically
# excludes anything below 70 % of expected nominal (deeply faulted levels are still
# caught as "indeterminate" because suitable_for_corroboration would be False).
_INCONS_LOW: float = 0.70  # ratio < 0.70 → inconsistent
_INCONS_HIGH: float = 1.30 # ratio > 1.30 → inconsistent

# Three-phase balance threshold
_BALANCE_MAX_UNBALANCE_PCT: float = 10.0

LINE_TO_LINE: str = "line_to_line"
LINE_TO_GROUND: str = "line_to_ground"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChannelRmsSummary:
    """Per-channel summary computed from the best stable window."""
    name: str
    stable_rms_kv: float | None      # Mean RMS (kV) in best stable window; None if no stable window
    rms_variation_pct: float | None  # CV (std/mean × 100) in stable window; None if unavailable
    has_abrupt_onset: bool           # True when a sudden RMS change was detected on this channel
    samples_total: int               # Total samples analysed for this channel


@dataclass(frozen=True, slots=True)
class StableWindowInfo:
    """Description of a continuous stable RMS interval."""
    start_s: float
    end_s: float
    duration_s: float
    duration_cycles: float
    mean_rms_kv: float                                   # Mean across phases and time in this window
    rms_per_channel: tuple[tuple[str, float], ...]       # (name, mean_rms_kv) pairs
    max_variation_pct: float                             # Max CV across all channels in this window
    is_prefault: bool                                    # True when window precedes detected onset


@dataclass(frozen=True, slots=True)
class WaveformEvidence:
    """Structured evidence extracted from one or more voltage waveforms."""

    # Input summary
    channel_names: tuple[str, ...]
    nominal_frequency_hz: float
    duration_analyzed_s: float

    # Per-channel
    channel_summaries: tuple[ChannelRmsSummary, ...]

    # Best stable window found across all channels (None if no stable interval found)
    best_stable_window: StableWindowInfo | None

    # Three-phase balance (None when < 2 channels)
    phase_magnitude_balance_ok: bool | None
    phase_unbalance_pct: float | None   # (max_dev/mean) × 100 based on stable-window RMS

    # Disturbance
    has_disturbance_onset: bool
    onset_time_s: float | None

    # Overall classification
    # "stable_prefault"       — stable window found before detected onset
    # "all_stable"            — no disturbance detected in the analysed window
    # "disturbed_no_prefault" — onset detected before any stable window, or all disturbed
    # "insufficient_data"     — too few cycles to assess
    recording_state: str
    suitable_for_corroboration: bool  # True only for stable_prefault / all_stable

    # Operational limitations detected during analysis
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WaveformCorroboration:
    """Result of comparing a nominal-voltage hypothesis against waveform evidence.

    CRITICAL: This result is meaningful ONLY when
    ``evidence.suitable_for_corroboration`` is True.  When the recording is
    disturbed the verdict will be "indeterminate" regardless of the ratio.

    Verdicts:
        "corroborated"           — ratio in 0.90–1.10 AND recording is suitable.
        "magnitude_disagreement" — ratio outside 0.90–1.10.  Does NOT mean the
                                   hypothesis is wrong — the recording may be a
                                   sustained undervoltage, fault, or other
                                   non-nominal condition.
        "indeterminate"          — insufficient data or recording not suitable.

    The ``notable_magnitude_gap`` flag is set when ratio < 0.70 or > 1.30 and
    provides factual information about the magnitude difference.  It is NOT an
    authority verdict: the engineer must decide the significance.
    """
    candidate_ll_kv: float
    channel_reference: str | None   # LINE_TO_LINE / LINE_TO_GROUND / None
    expected_rms_kv: float          # candidate_ll / √3 for L-G; candidate_ll for L-L
    observed_rms_kv: float | None
    ratio: float | None             # observed / expected; None when no observation
    verdict: str                    # "corroborated" / "magnitude_disagreement" / "indeterminate"
    reason: str
    notable_magnitude_gap: bool = False  # True when ratio < 0.70 or > 1.30


# ---------------------------------------------------------------------------
# Sliding one-cycle RMS (vectorised cumsum — mirrors calculated_channel)
# ---------------------------------------------------------------------------

def _sliding_rms_uniform(values: np.ndarray, window_samples: int) -> np.ndarray:
    """Trailing true RMS using vectorised cumulative sum.

    Replicates the uniform-spacing algorithm in ``calculated_channel.evaluate_rms()``.
    Returns NaN for samples before the first complete window and for windows
    that contain any non-finite value.
    """
    if len(values) < window_samples:
        return np.full(len(values), np.nan)

    sq = values.astype(np.float64) ** 2
    finite = np.isfinite(sq)
    sq_safe = np.where(finite, sq, 0.0)
    nan_flag = (~finite).astype(np.int64)

    cs_sq = np.concatenate([[0.0], np.cumsum(sq_safe)])
    cs_nan = np.concatenate([[0], np.cumsum(nan_flag)])

    W = window_samples
    n = len(values)

    # Window sum for index i (0-based): cs_sq[i+1] - cs_sq[i+1-W]  (trailing window)
    window_sums = cs_sq[W:] - cs_sq[:n - W + 1]  # shape (n - W + 1,)
    nan_counts = cs_nan[W:] - cs_nan[:n - W + 1]

    out = np.full(n, np.nan)
    valid = nan_counts == 0
    out[W - 1:] = np.where(valid, np.sqrt(window_sums / W), np.nan)
    return out


def _window_samples(sample_rate: float, nominal_frequency_hz: float) -> int:
    """Number of samples for one full cycle."""
    return max(2, round(sample_rate / nominal_frequency_hz))


def _infer_sample_rate(time: np.ndarray) -> float | None:
    """Estimate sample rate from median sample spacing. Returns None on failure."""
    if len(time) < 2:
        return None
    diffs = np.diff(time)
    median_dt = float(np.median(diffs))
    if median_dt <= 0:
        return None
    return 1.0 / median_dt


# ---------------------------------------------------------------------------
# Stable-window detection
# ---------------------------------------------------------------------------

def _find_stable_windows(
    rms_series: np.ndarray,
    time: np.ndarray,
    nominal_frequency_hz: float,
    sample_rate: float,
    min_stable_cycles: int,
    stability_threshold_pct: float,
) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx) for stable windows.

    A stable window is a contiguous run of at least ``min_stable_cycles``
    *full-cycle* RMS values whose coefficient of variation is below
    ``stability_threshold_pct`` %.

    The check is performed at **one-cycle resolution**: the RMS series is
    subsampled once per cycle (every ``window_samples`` valid indices) before
    applying the sliding-window CV test.  This prevents a slowly ramping signal
    from appearing "locally stable" because adjacent sample-level values look
    nearly constant even when the amplitude drifts substantially over several
    cycles.
    """
    win_samp = _window_samples(sample_rate, nominal_frequency_hz)
    valid_idx = np.where(np.isfinite(rms_series))[0]
    if len(valid_idx) < win_samp:
        return []

    # Subsample at one-cycle intervals: take every win_samp-th valid index
    cycle_stride = max(1, win_samp)
    cycle_valid_idx = valid_idx[::cycle_stride]
    cycle_vals = rms_series[cycle_valid_idx]

    n_cycle = len(cycle_vals)
    W = min_stable_cycles
    if n_cycle < W:
        return []

    stable_flags = np.zeros(n_cycle, dtype=bool)
    for i in range(W - 1, n_cycle):
        window = cycle_vals[i - W + 1: i + 1]
        mean = float(np.mean(window))
        if mean <= 0:
            continue
        cv = float(np.std(window)) / mean * 100.0
        if cv < stability_threshold_pct:
            stable_flags[i - W + 1: i + 1] = True

    # Find contiguous True runs in cycle-space; map back to rms_series indices
    windows: list[tuple[int, int]] = []
    in_window = False
    start = 0
    for i, flag in enumerate(stable_flags):
        if flag and not in_window:
            start = i
            in_window = True
        elif not flag and in_window:
            windows.append((int(cycle_valid_idx[start]), int(cycle_valid_idx[i - 1])))
            in_window = False
    if in_window:
        windows.append((int(cycle_valid_idx[start]), int(cycle_valid_idx[-1])))

    return windows


def _detect_onset(
    rms_series: np.ndarray,
    time: np.ndarray,
    sample_rate: float,
    nominal_frequency_hz: float,
    threshold_pct: float = _ONSET_THRESHOLD_PCT,
) -> int | None:
    """Return sample index of first abrupt RMS change (cycle-to-cycle), or None.

    Operates at **one-cycle resolution**: compares adjacent one-cycle RMS
    values taken at cycle-spacing intervals.  This avoids false positives from
    sub-cycle variation while still catching genuine fault onsets (which cause
    > 20 % amplitude change between consecutive full-cycle windows).
    """
    win_samp = _window_samples(sample_rate, nominal_frequency_hz)
    valid_idx = np.where(np.isfinite(rms_series))[0]
    if len(valid_idx) < 2:
        return None

    # Subsample at one-cycle intervals
    cycle_stride = max(1, win_samp)
    cycle_valid_idx = valid_idx[::cycle_stride]
    if len(cycle_valid_idx) < 2:
        return None

    cycle_vals = rms_series[cycle_valid_idx]
    diffs = np.abs(np.diff(cycle_vals))
    local_rms = cycle_vals[:-1]

    positive = local_rms > 0
    # Suppress numpy invalid-value warnings for the zero-local_rms case
    with np.errstate(invalid="ignore"):
        rel_change = np.where(positive, diffs / local_rms * 100.0, 0.0)

    hit = np.where(rel_change > threshold_pct)[0]
    if len(hit) == 0:
        return None
    # Return sample index in the full rms_series corresponding to the step
    return int(cycle_valid_idx[hit[0] + 1])


# ---------------------------------------------------------------------------
# Clipping detection
# ---------------------------------------------------------------------------

def _check_clipping(values: np.ndarray, stable_rms_kv: float | None) -> bool:
    """Return True if the crest factor suggests possible signal clipping."""
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return False
    peak = float(np.max(np.abs(finite)))
    if stable_rms_kv is not None and stable_rms_kv > 0:
        crest = peak / (stable_rms_kv * SQRT_2)
        return crest < _CLIPPING_CREST_LOW
    return False


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_waveform_evidence(
    channels: dict[str, tuple[np.ndarray, np.ndarray]],
    nominal_frequency_hz: float = 50.0,
    max_analysis_seconds: float = 2.0,
    min_stable_cycles: int = _MIN_STABLE_CYCLES_DEFAULT,
    stability_threshold_pct: float = _STABILITY_THRESHOLD_PCT_DEFAULT,
) -> WaveformEvidence:
    """Extract waveform evidence from one or more voltage channels.

    Args:
        channels: Mapping from channel name to ``(time_s, values_kv)`` arrays.
                  Values must be in **kV** (the caller is responsible for unit
                  conversion).
        nominal_frequency_hz: Nominal power-system frequency (50 or 60 Hz).
        max_analysis_seconds: Cap on how much of the recording to analyse.
        min_stable_cycles: Minimum consecutive one-cycle windows for a stable
                           interval.
        stability_threshold_pct: CV threshold (%) for stable-interval detection.

    Returns:
        ``WaveformEvidence`` with structured summary and suitability flag.
    """
    if not channels:
        return WaveformEvidence(
            channel_names=(),
            nominal_frequency_hz=nominal_frequency_hz,
            duration_analyzed_s=0.0,
            channel_summaries=(),
            best_stable_window=None,
            phase_magnitude_balance_ok=None,
            phase_unbalance_pct=None,
            has_disturbance_onset=False,
            onset_time_s=None,
            recording_state="insufficient_data",
            suitable_for_corroboration=False,
            limitations=("no_channels",),
        )

    limitations: list[str] = []
    channel_names = tuple(channels.keys())

    # --- Per-channel analysis ---
    per_channel_rms: dict[str, np.ndarray] = {}
    per_channel_time: dict[str, np.ndarray] = {}
    per_channel_sr: dict[str, float] = {}
    per_channel_values: dict[str, np.ndarray] = {}

    for name, (t_raw, v_raw) in channels.items():
        t = np.asarray(t_raw, dtype=np.float64)
        v = np.asarray(v_raw, dtype=np.float64)

        # Cap to max_analysis_seconds
        if len(t) > 0:
            t0 = t[0]
            mask = t - t0 <= max_analysis_seconds
            t = t[mask]
            v = v[mask]

        per_channel_time[name] = t
        per_channel_values[name] = v

        sr = _infer_sample_rate(t)
        if sr is None or sr <= 0:
            per_channel_sr[name] = nominal_frequency_hz * 32.0  # fallback
        else:
            per_channel_sr[name] = sr

        win = _window_samples(per_channel_sr[name], nominal_frequency_hz)
        per_channel_rms[name] = _sliding_rms_uniform(v, win)

    # --- Determine shortest time extent across all channels ---
    max_t = 0.0
    for name, t in per_channel_time.items():
        if len(t) > 0:
            dur = float(t[-1] - t[0])
            if dur > max_t:
                max_t = dur
    duration_analyzed_s = min(max_t, max_analysis_seconds)

    # --- Check minimum cycles ---
    min_cycles_total = duration_analyzed_s * nominal_frequency_hz
    if min_cycles_total < _MIN_CYCLES_FOR_USABLE:
        # Build minimal summaries
        summaries = tuple(
            ChannelRmsSummary(
                name=name,
                stable_rms_kv=None,
                rms_variation_pct=None,
                has_abrupt_onset=False,
                samples_total=len(per_channel_values[name]),
            )
            for name in channel_names
        )
        limitations.append("insufficient_cycles")
        return WaveformEvidence(
            channel_names=channel_names,
            nominal_frequency_hz=nominal_frequency_hz,
            duration_analyzed_s=duration_analyzed_s,
            channel_summaries=summaries,
            best_stable_window=None,
            phase_magnitude_balance_ok=None,
            phase_unbalance_pct=None,
            has_disturbance_onset=False,
            onset_time_s=None,
            recording_state="insufficient_data",
            suitable_for_corroboration=False,
            limitations=tuple(limitations),
        )

    # --- Find stable windows and onset per channel; then aggregate ---
    # Use the first (or most representative) channel for overall onset detection
    # and aggregate stable windows.
    per_ch_stable_wins: dict[str, list[tuple[int, int]]] = {}
    per_ch_onset_idx: dict[str, int | None] = {}

    for name in channel_names:
        rms = per_channel_rms[name]
        t = per_channel_time[name]
        sr = per_channel_sr[name]
        wins = _find_stable_windows(
            rms, t, nominal_frequency_hz, sr,
            min_stable_cycles, stability_threshold_pct,
        )
        per_ch_stable_wins[name] = wins
        per_ch_onset_idx[name] = _detect_onset(rms, t, sr, nominal_frequency_hz)

    # --- Global onset: earliest onset across all channels ---
    global_onset_idx: int | None = None
    global_onset_name: str | None = None
    for name, oi in per_ch_onset_idx.items():
        if oi is not None:
            t_name = per_channel_time[name]
            if global_onset_idx is None or oi < global_onset_idx:
                global_onset_idx = oi
                global_onset_name = name

    global_onset_time: float | None = None
    if global_onset_idx is not None and global_onset_name is not None:
        t_ref = per_channel_time[global_onset_name]
        if global_onset_idx < len(t_ref):
            global_onset_time = float(t_ref[global_onset_idx])

    has_onset = global_onset_time is not None

    # --- Best stable window: prefer the longest prefault window; fall back to any ---
    # Prefault windows take priority over post-fault windows regardless of duration,
    # because a prefault reference is what we need for corroboration.
    best_win_prefault: StableWindowInfo | None = None
    best_win_prefault_dur = 0.0
    best_win_any: StableWindowInfo | None = None
    best_win_any_dur = 0.0

    for name in channel_names:
        wins = per_ch_stable_wins[name]
        t = per_channel_time[name]
        rms = per_channel_rms[name]

        for (si, ei) in wins:
            if si >= len(t) or ei >= len(t):
                continue
            start_t = float(t[si])
            end_t = float(t[ei])
            dur = end_t - start_t
            is_prefault = (not has_onset) or (end_t < global_onset_time)  # type: ignore[operator]

            # Skip if this window would not improve our best in its category
            if is_prefault and dur <= best_win_prefault_dur:
                continue
            if not is_prefault and dur <= best_win_any_dur:
                continue

            # Compute mean RMS and variation in this window for each channel
            rms_per_ch: list[tuple[str, float]] = []
            max_cv = 0.0
            all_ok = True
            for ch_name in channel_names:
                ch_t = per_channel_time[ch_name]
                ch_rms = per_channel_rms[ch_name]
                mask = (ch_t >= start_t) & (ch_t <= end_t)
                win_rms = ch_rms[mask]
                win_rms = win_rms[np.isfinite(win_rms)]
                if len(win_rms) < 2:
                    all_ok = False
                    break
                mean_v = float(np.mean(win_rms))
                std_v = float(np.std(win_rms))
                cv = (std_v / mean_v * 100.0) if mean_v > 0 else 100.0
                max_cv = max(max_cv, cv)
                rms_per_ch.append((ch_name, mean_v))

            if not all_ok or not rms_per_ch:
                continue

            overall_mean = float(np.mean([v for _, v in rms_per_ch]))
            cycles = dur * nominal_frequency_hz

            candidate = StableWindowInfo(
                start_s=start_t,
                end_s=end_t,
                duration_s=dur,
                duration_cycles=cycles,
                mean_rms_kv=overall_mean,
                rms_per_channel=tuple(rms_per_ch),
                max_variation_pct=max_cv,
                is_prefault=is_prefault,
            )
            if is_prefault:
                best_win_prefault = candidate
                best_win_prefault_dur = dur
            else:
                best_win_any = candidate
                best_win_any_dur = dur

    # Prefer the prefault window for corroboration; fall back to any stable window
    best_win: StableWindowInfo | None = (
        best_win_prefault if best_win_prefault is not None else best_win_any
    )

    # --- Per-channel summaries ---
    ch_summaries: list[ChannelRmsSummary] = []
    for name in channel_names:
        t = per_channel_time[name]
        v = per_channel_values[name]
        rms = per_channel_rms[name]
        onset_idx = per_ch_onset_idx[name]
        has_abrupt = onset_idx is not None

        # Stable RMS: use best_stable_window entry for this channel
        stable_rms: float | None = None
        rms_var: float | None = None
        if best_win is not None:
            for ch_name, ch_rms_val in best_win.rms_per_channel:
                if ch_name == name:
                    stable_rms = ch_rms_val
                    # Compute actual variation within this window for this channel
                    mask = (t >= best_win.start_s) & (t <= best_win.end_s)
                    win_rms = rms[mask]
                    win_rms = win_rms[np.isfinite(win_rms)]
                    if len(win_rms) >= 2 and stable_rms and stable_rms > 0:
                        rms_var = float(np.std(win_rms) / stable_rms * 100.0)
                    break

        # Check clipping
        if _check_clipping(v, stable_rms):
            if "clipping_detected" not in limitations:
                limitations.append("clipping_detected")

        ch_summaries.append(ChannelRmsSummary(
            name=name,
            stable_rms_kv=stable_rms,
            rms_variation_pct=rms_var,
            has_abrupt_onset=has_abrupt,
            samples_total=len(v),
        ))

    # --- Single-phase limitation ---
    if len(channel_names) < 2:
        limitations.append("single_phase_no_balance_check")

    # --- Three-phase balance ---
    phase_balance_ok: bool | None = None
    phase_unbalance_pct: float | None = None
    if best_win is not None and len(best_win.rms_per_channel) >= 2:
        rms_vals = [v for _, v in best_win.rms_per_channel]
        mean_r = float(np.mean(rms_vals))
        if mean_r > 0:
            max_dev = float(max(abs(v - mean_r) for v in rms_vals))
            unbal = max_dev / mean_r * 100.0
            phase_unbalance_pct = round(unbal, 2)
            phase_balance_ok = unbal <= _BALANCE_MAX_UNBALANCE_PCT

    # --- Recording state ---
    if best_win is not None and best_win.is_prefault and has_onset:
        recording_state = "stable_prefault"
    elif best_win is not None and not has_onset:
        recording_state = "all_stable"
    else:
        # No prefault stable window found (either no stable window at all, or only post-fault)
        recording_state = "disturbed_no_prefault"
        if "all_disturbed" not in limitations:
            limitations.append("all_disturbed")

    suitable = recording_state in ("stable_prefault", "all_stable")

    return WaveformEvidence(
        channel_names=channel_names,
        nominal_frequency_hz=nominal_frequency_hz,
        duration_analyzed_s=duration_analyzed_s,
        channel_summaries=tuple(ch_summaries),
        best_stable_window=best_win,
        phase_magnitude_balance_ok=phase_balance_ok,
        phase_unbalance_pct=phase_unbalance_pct,
        has_disturbance_onset=has_onset,
        onset_time_s=global_onset_time,
        recording_state=recording_state,
        suitable_for_corroboration=suitable,
        limitations=tuple(limitations),
    )


# ---------------------------------------------------------------------------
# Corroboration
# ---------------------------------------------------------------------------

def corroborate_hypothesis(
    candidate_ll_kv: float,
    channel_reference: str | None,
    evidence: WaveformEvidence,
) -> WaveformCorroboration:
    """Compare a nominal-voltage hypothesis against measured waveform evidence.

    Returns "indeterminate" unless ``evidence.suitable_for_corroboration``
    is True.  A disturbed recording must not be used to infer nominal voltage.

    Thresholds (applied to observed/expected ratio):
        0.90 – 1.10  → "corroborated"
        outside      → "magnitude_disagreement"

    "magnitude_disagreement" does NOT mean the hypothesis is wrong.  The
    recording may be a sustained undervoltage, a fault, a motor start, or
    any other non-nominal condition.  This verdict alone must not reject a
    hypothesis or grant automatic authority to a competing one.

    ``notable_magnitude_gap`` is set True when ratio < 0.70 or > 1.30 as a
    factual observation; engineering judgment is required to interpret it.

    Args:
        candidate_ll_kv: Proposed nominal L-L system voltage (kV).
        channel_reference: "line_to_ground" / "line_to_line" / None.
        evidence: Extracted waveform evidence.
    """
    # Expected L-G or L-L RMS for the candidate
    if channel_reference == LINE_TO_GROUND:
        expected_rms = candidate_ll_kv / SQRT_3
    elif channel_reference == LINE_TO_LINE:
        expected_rms = candidate_ll_kv / SQRT_3  # treat same for corroboration metric
    else:
        expected_rms = candidate_ll_kv / SQRT_3  # default to L-G interpretation

    if not evidence.suitable_for_corroboration:
        return WaveformCorroboration(
            candidate_ll_kv=candidate_ll_kv,
            channel_reference=channel_reference,
            expected_rms_kv=expected_rms,
            observed_rms_kv=None,
            ratio=None,
            verdict="indeterminate",
            reason=(
                f"Recording state '{evidence.recording_state}' — "
                "waveform evidence not suitable for corroboration."
            ),
        )

    if evidence.best_stable_window is None:
        return WaveformCorroboration(
            candidate_ll_kv=candidate_ll_kv,
            channel_reference=channel_reference,
            expected_rms_kv=expected_rms,
            observed_rms_kv=None,
            ratio=None,
            verdict="indeterminate",
            reason="No stable window available; cannot derive observed RMS.",
        )

    # Use mean RMS across all channels in the best stable window
    observed_rms = evidence.best_stable_window.mean_rms_kv

    if expected_rms <= 0:
        return WaveformCorroboration(
            candidate_ll_kv=candidate_ll_kv,
            channel_reference=channel_reference,
            expected_rms_kv=expected_rms,
            observed_rms_kv=observed_rms,
            ratio=None,
            verdict="indeterminate",
            reason=f"Expected RMS {expected_rms:.4g} kV is not positive.",
        )

    ratio = observed_rms / expected_rms
    notable_gap = ratio < _INCONS_LOW or ratio > _INCONS_HIGH

    if _CORR_LOW <= ratio <= _CORR_HIGH:
        verdict = "corroborated"
        reason = (
            f"Observed {observed_rms:.4g} kV / expected {expected_rms:.4g} kV "
            f"= {ratio:.3f} (within ±10 %)."
        )
    else:
        verdict = "magnitude_disagreement"
        reason = (
            f"Observed {observed_rms:.4g} kV / expected {expected_rms:.4g} kV "
            f"= {ratio:.3f} — outside corroboration band (±10 %). "
            f"This does not indicate the hypothesis is wrong; the recording "
            f"may reflect non-nominal operating conditions."
            + (f" Notable gap: ratio < {_INCONS_LOW:.0%}." if ratio < _INCONS_LOW
               else f" Notable gap: ratio > {_INCONS_HIGH:.0%}." if ratio > _INCONS_HIGH
               else "")
        )

    return WaveformCorroboration(
        candidate_ll_kv=candidate_ll_kv,
        channel_reference=channel_reference,
        expected_rms_kv=expected_rms,
        observed_rms_kv=observed_rms,
        ratio=ratio,
        verdict=verdict,
        reason=reason,
        notable_magnitude_gap=notable_gap,
    )
