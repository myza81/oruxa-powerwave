"""RMS waveform-form eligibility detector (Phase 5B, DEC-048).

Purpose: "does this signal look like an instantaneous AC waveform
suitable for RMS?" -- NOT "can we prove this signal is specifically
RMS?" (owner section 15). This is the algorithmic FALLBACK, only ever
run when a channel's own trusted `waveform_form` metadata is
`"unknown"` (see app.services.calculated_channel_service.
check_rms_eligibility) -- explicit trusted metadata always wins over
this detector, and is never second-guessed by it.

Zero framework dependencies, per the domain/ layer contract (matches
app.domain.calculated_channel's own convention). Numpy-only -- this
project has no scipy dependency (backend/requirements.txt pins only
numpy/pandas among array libraries), so every indicator below is a
plain numpy computation, never a full FFT (owner section 16/18:
"prefer a lightweight targeted frequency test rather than a full FFT").

Combines five cheap, independent indicators (owner section 17) into a
transparent VOTE COUNT, never a fabricated precision score (owner
section 45: no "87.42% instantaneous"). Only the resulting 3-way
category is ever meant to reach a user-facing surface.
"""

from __future__ import annotations

import numpy as np

LIKELY_INSTANTANEOUS = "likely_instantaneous"
LIKELY_MAGNITUDE_OR_RMS = "likely_magnitude_or_rms"
UNCERTAIN = "uncertain"

#: Representative-slice cap (owner section 16: "up to ~0.5-1 second where
#: available... capped sample count"). Chosen as an upper bound on
#: ELAPSED TIME, not directly on sample count -- consistent with this
#: whole feature's own "time-based, not fixed-N" principle.
MAX_SLICE_SECONDS = 1.0
#: Below this many cycles of data, there is not enough signal for any
#: indicator below to be meaningful -- return UNCERTAIN immediately
#: rather than let a tiny slice produce a spurious confident vote.
MIN_CYCLES_FOR_DETECTION = 3

#: Vote thresholds -- deliberately simple fixed cutoffs, not fitted
#: coefficients (there is no labeled training set for this project, and
#: the owner explicitly warns against a falsely precise score).
_BIPOLAR_INSTANTANEOUS = 0.5
_BIPOLAR_MAGNITUDE = 0.05
_ZERO_CROSSING_RATIO_INSTANTANEOUS = 0.7
_ZERO_CROSSING_CV_INSTANTANEOUS = 0.3
_ZERO_CROSSING_RATIO_MAGNITUDE = 0.1
_F0_CORRELATION_INSTANTANEOUS = 0.6
_F0_CORRELATION_MAGNITUDE = 0.15
_PERIODICITY_DIP_INSTANTANEOUS = 0.5
_PERIODICITY_DIP_MAGNITUDE = 0.1
_SMOOTHNESS_RATIO_INSTANTANEOUS = 0.3
_SMOOTHNESS_RATIO_MAGNITUDE = 0.85

#: A category needs at least this many indicator votes, and ZERO votes
#: for the opposing category, to be reported with confidence (owner
#: section 19/20: "treat as one score component only" -- no single
#: indicator is ever authoritative on its own).
_MIN_VOTES_FOR_CONFIDENT_CATEGORY = 4


def _representative_slice(time: np.ndarray, values: np.ndarray, max_seconds: float) -> tuple[np.ndarray, np.ndarray]:
    """The first `max_seconds` of the record (owner section 16), capped.
    Deliberately the simplest possible deterministic choice -- a
    steady-state-seeking midpoint heuristic was considered and rejected
    for this phase as unnecessary added complexity for a lightweight
    eligibility check, not a measurement."""
    if time.shape[0] == 0:
        return time, values
    cutoff = time[0] + max_seconds
    end_index = int(np.searchsorted(time, cutoff, side="right"))
    end_index = max(end_index, min(2, time.shape[0]))
    return time[:end_index], values[:end_index]


def _bipolarity_score(values: np.ndarray) -> float:
    positive_fraction = float(np.mean(values > 0))
    negative_fraction = float(np.mean(values < 0))
    return 2.0 * min(positive_fraction, negative_fraction)


def _zero_crossing_indicators(values: np.ndarray, expected_crossings: float) -> tuple[float, float]:
    """Returns (crossing_ratio, coefficient_of_variation_of_gaps). A
    crossing is a strict sign change (a run of exact zeros neither
    creates nor breaks one). CV is `inf` when fewer than 2 gaps exist."""
    signs = np.sign(values)
    nonzero = signs[signs != 0]
    if nonzero.shape[0] < 2:
        return 0.0, float("inf")
    crossing_indices = np.flatnonzero(np.diff(nonzero) != 0)
    crossing_count = crossing_indices.shape[0]
    ratio = crossing_count / expected_crossings if expected_crossings > 0 else 0.0
    if crossing_indices.shape[0] < 2:
        return ratio, float("inf")
    gaps = np.diff(crossing_indices).astype(np.float64)
    mean_gap = float(np.mean(gaps))
    if mean_gap <= 0:
        return ratio, float("inf")
    cv = float(np.std(gaps) / mean_gap)
    return ratio, cv


def _targeted_frequency_correlation(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> float:
    """Single-bin DFT magnitude at `nominal_frequency_hz`, normalized by
    the slice's own RMS (owner section 18: "targeted correlation... not a
    full FFT"). A pure sinusoid at f0 yields a ratio near
    sqrt(2) (~1.41); heavily distorted/DC/off-frequency signals yield a
    much smaller ratio."""
    n = values.shape[0]
    if n == 0:
        return 0.0
    signal_rms = float(np.sqrt(np.mean(values.astype(np.float64) ** 2)))
    if signal_rms <= 0:
        return 0.0
    angle = 2.0 * np.pi * nominal_frequency_hz * time
    cos_component = float(np.sum(values * np.cos(angle)))
    sin_component = float(np.sum(values * np.sin(angle)))
    magnitude = (2.0 / n) * np.sqrt(cos_component**2 + sin_component**2)
    return magnitude / signal_rms


def _periodicity_dip(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> float:
    """Pearson correlation of the slice against itself shifted by one full
    cycle, minus the same at a half-cycle shift (owner section 18/21). A
    real sinusoid dips sharply at the half-cycle offset (correlates
    negatively) and recovers at the full cycle -- a smooth/already-RMS
    signal shows little difference between the two lags."""
    n = values.shape[0]
    if n < 4:
        return 0.0
    median_dt = float(np.median(np.diff(time))) if n >= 2 else 0.0
    if median_dt <= 0:
        return 0.0
    full_lag = max(int(round((1.0 / nominal_frequency_hz) / median_dt)), 1)
    half_lag = max(full_lag // 2, 1)
    if full_lag >= n or half_lag >= n:
        return 0.0

    def _corr(lag: int) -> float:
        a = values[:-lag]
        b = values[lag:]
        if a.shape[0] < 2 or np.std(a) == 0 or np.std(b) == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    return _corr(full_lag) - _corr(half_lag)


def _smoothness_ratio(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> float:
    """Reuses evaluate_rms() itself on the representative slice (no second
    implementation, owner section 21) to compare raw vs. trial-RMS
    roughness. Ratio near 0 -> RMS massively smoothed the signal (strong
    instantaneous-AC evidence); ratio near 1 -> RMS barely changed an
    already-smooth signal (magnitude/RMS-like evidence)."""
    from app.domain.calculated_channel import evaluate_rms

    trial = evaluate_rms(time, values, nominal_frequency_hz)
    valid = trial[np.isfinite(trial)]
    if valid.shape[0] < 2:
        return 1.0

    def _roughness(x: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        if rms <= 0:
            return 0.0
        return float(np.mean(np.abs(np.diff(x)))) / rms

    raw_roughness = _roughness(values)
    trial_roughness = _roughness(valid)
    if raw_roughness <= 0:
        return 1.0
    return trial_roughness / raw_roughness


def classify_waveform_form(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> str:
    """Returns one of LIKELY_INSTANTANEOUS / LIKELY_MAGNITUDE_OR_RMS /
    UNCERTAIN for the given full-resolution channel data (owner sections
    15-24). Only ever consulted when trusted waveform-form metadata is
    absent/unknown -- see this module's own docstring.

    Cheap by construction: operates on a capped representative slice
    (`MAX_SLICE_SECONDS`), never the whole record, and every indicator is
    an O(N) numpy computation with no FFT.
    """
    finite_mask = np.isfinite(values)
    time = time[finite_mask]
    values = values[finite_mask]
    if time.shape[0] < 2:
        return UNCERTAIN

    slice_time, slice_values = _representative_slice(time, values, MAX_SLICE_SECONDS)
    duration = float(slice_time[-1] - slice_time[0])
    min_duration = MIN_CYCLES_FOR_DETECTION / nominal_frequency_hz
    if duration < min_duration:
        return UNCERTAIN

    instantaneous_votes = 0
    magnitude_votes = 0

    bipolar = _bipolarity_score(slice_values)
    if bipolar >= _BIPOLAR_INSTANTANEOUS:
        instantaneous_votes += 1
    elif bipolar <= _BIPOLAR_MAGNITUDE:
        magnitude_votes += 1

    expected_crossings = 2.0 * nominal_frequency_hz * duration
    crossing_ratio, crossing_cv = _zero_crossing_indicators(slice_values, expected_crossings)
    if crossing_ratio >= _ZERO_CROSSING_RATIO_INSTANTANEOUS and crossing_cv < _ZERO_CROSSING_CV_INSTANTANEOUS:
        instantaneous_votes += 1
    elif crossing_ratio <= _ZERO_CROSSING_RATIO_MAGNITUDE:
        magnitude_votes += 1

    f0_ratio = _targeted_frequency_correlation(slice_time, slice_values, nominal_frequency_hz)
    if f0_ratio >= _F0_CORRELATION_INSTANTANEOUS:
        instantaneous_votes += 1
    elif f0_ratio <= _F0_CORRELATION_MAGNITUDE:
        magnitude_votes += 1

    dip = _periodicity_dip(slice_time, slice_values, nominal_frequency_hz)
    if dip >= _PERIODICITY_DIP_INSTANTANEOUS:
        instantaneous_votes += 1
    elif dip <= _PERIODICITY_DIP_MAGNITUDE:
        magnitude_votes += 1

    smoothness = _smoothness_ratio(slice_time, slice_values, nominal_frequency_hz)
    if smoothness <= _SMOOTHNESS_RATIO_INSTANTANEOUS:
        instantaneous_votes += 1
    elif smoothness >= _SMOOTHNESS_RATIO_MAGNITUDE:
        magnitude_votes += 1

    if instantaneous_votes >= _MIN_VOTES_FOR_CONFIDENT_CATEGORY and magnitude_votes == 0:
        return LIKELY_INSTANTANEOUS
    if magnitude_votes >= _MIN_VOTES_FOR_CONFIDENT_CATEGORY and instantaneous_votes == 0:
        return LIKELY_MAGNITUDE_OR_RMS
    return UNCERTAIN
