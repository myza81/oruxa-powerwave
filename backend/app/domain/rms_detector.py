"""RMS waveform-form eligibility detector (Phase 5B, DEC-048; multi-
window correction DEC-108).

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

**DEC-108 (2026-09-23): waveform representation is a channel-level
property, but a real DISTURBANCE RECORD is not internally uniform --
it legitimately contains multiple physical states (clean pre-fault,
fault/disturbance, post-clearance near-zero collapse) within the SAME
channel. Investigation proved that evaluating the five indicators once,
over ONE long aggregate slice spanning all of those states, is not
authoritative: a genuinely instantaneous AC current can be voted
`UNCERTAIN` purely because a long near-zero tail dilutes the
slice-wide zero-crossing-ratio and targeted-frequency-correlation
indicators, even though every individual physical state within that
same slice is, on its own, unambiguously instantaneous.

The fix is CYCLE-BASED MULTI-WINDOW classification for the `"unknown"`
fallback path only: the representative region (still capped at
`MAX_SLICE_SECONDS`, unchanged) is tiled with deterministic,
non-overlapping, fixed-size windows (`_WINDOW_CYCLES` cycles each,
derived from `nominal_frequency_hz` -- never a hard-coded millisecond
value), each classified independently via the SAME five indicators and
SAME per-window vote thresholds this module already used for the whole
slice (`_classify_slice()`, unchanged logic, just now callable on a
smaller window). A near-zero-energy window (e.g. a post-clearance
collapse, scale-relative to the region's own overall RMS -- never an
absolute ampere/volt threshold) contributes no vote either way,
matching how a genuinely quiet/uninformative segment should never be
forced into evidence for or against instantaneous. The final
channel-level classification is then a conservative vote ACROSS
windows (`_MIN_WINDOWS_FOR_CONFIDENT_CATEGORY`), not within one -- see
`_classify_windows()`'s own docstring for the exact rule. When too
little data exists for even two windows, this falls back to the
original single-slice classification unchanged, so short-record
behavior (and every existing test covering it) is completely
unaffected.
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

#: DEC-108 -- one classification window's own duration, in CYCLES of
#: `nominal_frequency_hz` (never a hard-coded millisecond value, so a
#: 60 Hz recording gets an equivalently-sized window to a 50 Hz one).
#: Deliberately larger than `MIN_CYCLES_FOR_DETECTION` (3) -- a window
#: exactly at that floor leaves no margin for the per-window indicators
#: themselves to have enough cycles to be meaningful; 5 was the
#: smallest window size investigation confirmed reliably reproduces
#: confident per-window votes on both a clean pre-fault segment and a
#: disturbance-only segment.
_WINDOW_CYCLES = 5
#: DEC-108 -- the channel-level classification needs at least this many
#: INFORMATIVE windows agreeing, with ZERO windows voting the opposing
#: category, mirroring `_MIN_VOTES_FOR_CONFIDENT_CATEGORY`'s own
#: "more than one independent piece of evidence, no opposing evidence"
#: shape one level up (per-window vote -> per-channel window count).
#: A single confident window is deliberately NOT enough on its own --
#: see `_classify_windows()`'s own docstring for why.
_MIN_WINDOWS_FOR_CONFIDENT_CATEGORY = 2
#: DEC-108 -- a window whose own RMS is below this FRACTION of the
#: whole representative region's own RMS is treated as uninformative
#: (contributes no vote either way) -- deliberately SCALE-RELATIVE
#: (never an absolute ampere/volt threshold, which would need per-
#: engineering-quantity tuning and would not generalize). A post-
#: clearance near-zero collapse is the primary case this protects:
#: without it, many small windows of pure measurement noise could
#: accidentally accumulate spurious per-window votes.
_LOW_ENERGY_WINDOW_RATIO = 0.1


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


def _classify_slice(slice_time: np.ndarray, slice_values: np.ndarray, nominal_frequency_hz: float) -> str:
    """The original five-indicator vote logic (Phase 5B, unchanged
    thresholds/behavior) -- extracted verbatim so it can run on EITHER
    one whole representative region (the short-record fallback) OR one
    smaller cycle-window (DEC-108's own multi-window path) with zero
    duplicated logic between the two callers. `slice_time`/
    `slice_values` are assumed already finite-filtered and non-empty by
    the caller."""
    duration = float(slice_time[-1] - slice_time[0]) if slice_time.shape[0] > 1 else 0.0
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


def _classify_windows(slice_time: np.ndarray, slice_values: np.ndarray, nominal_frequency_hz: float) -> str | None:
    """DEC-108's own multi-window aggregation. Tiles `[slice_time[0],
    slice_time[-1]]` with deterministic, non-overlapping, `_WINDOW_
    CYCLES`-cycle windows (fixed stride = window size -- no overlap, no
    randomness, no dependency on where any disturbance/event happens to
    fall) and classifies each independently via `_classify_slice()`,
    the SAME per-window logic/thresholds the whole-slice path already
    used. A window whose own RMS is below `_LOW_ENERGY_WINDOW_RATIO` of
    the WHOLE region's RMS (e.g. a post-clearance near-zero collapse)
    is skipped entirely -- it contributes no vote either way, never
    forced into "confidently something."

    Returns `None` (never a category) when fewer than two windows fit
    in the region at all -- the caller falls back to classifying the
    whole region as one slice, unchanged from the original Phase 5B
    behavior, so short-record behavior is completely unaffected by this
    correction.

    **Aggregation policy, deliberately NOT "any instantaneous window ->
    instantaneous"** (investigation found that rule too permissive --
    even a genuinely magnitude-like/RMS-shaped channel can have one
    small ambiguous sub-window by chance): at least
    `_MIN_WINDOWS_FOR_CONFIDENT_CATEGORY` INFORMATIVE windows must agree
    on the SAME category, with ZERO windows voting the opposing one --
    the identical "more evidence than the alternative, no contradicting
    evidence" shape `_classify_slice()`'s own per-window vote count
    already uses, one level up. Proven directly against adversarial
    genuine-RMS/magnitude fixtures (a slow positive envelope, a stepped
    RMS-output-shaped signal, a full-wave-rectified signal, a mostly-
    flat positive signal with noise) -- none became falsely
    instantaneous under this rule."""
    window_duration = _WINDOW_CYCLES / nominal_frequency_hz
    region_duration = float(slice_time[-1] - slice_time[0])
    n_windows = int(region_duration // window_duration)
    if n_windows < 2:
        return None

    reference_rms = float(np.sqrt(np.mean(slice_values.astype(np.float64) ** 2)))

    instantaneous_windows = 0
    magnitude_windows = 0
    informative_windows = 0
    for i in range(n_windows):
        window_start = slice_time[0] + i * window_duration
        window_end = window_start + window_duration
        window_mask = (slice_time >= window_start) & (slice_time < window_end)
        if np.count_nonzero(window_mask) < 2:
            continue
        window_time = slice_time[window_mask]
        window_values = slice_values[window_mask]

        window_rms = float(np.sqrt(np.mean(window_values.astype(np.float64) ** 2)))
        if reference_rms > 0 and window_rms < _LOW_ENERGY_WINDOW_RATIO * reference_rms:
            continue  # uninformative -- e.g. a post-clearance near-zero collapse

        informative_windows += 1
        window_result = _classify_slice(window_time, window_values, nominal_frequency_hz)
        if window_result == LIKELY_INSTANTANEOUS:
            instantaneous_windows += 1
        elif window_result == LIKELY_MAGNITUDE_OR_RMS:
            magnitude_windows += 1

    if informative_windows == 0:
        return UNCERTAIN  # every window was low-energy -- no evidence either way

    if instantaneous_windows >= _MIN_WINDOWS_FOR_CONFIDENT_CATEGORY and magnitude_windows == 0:
        return LIKELY_INSTANTANEOUS
    if magnitude_windows >= _MIN_WINDOWS_FOR_CONFIDENT_CATEGORY and instantaneous_windows == 0:
        return LIKELY_MAGNITUDE_OR_RMS
    return UNCERTAIN


def classify_waveform_form(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> str:
    """Returns one of LIKELY_INSTANTANEOUS / LIKELY_MAGNITUDE_OR_RMS /
    UNCERTAIN for the given full-resolution channel data (owner sections
    15-24; DEC-108's own multi-window correction). Only ever consulted
    when trusted waveform-form metadata is absent/unknown -- see this
    module's own docstring.

    Cheap by construction: operates on a capped representative slice
    (`MAX_SLICE_SECONDS`, unchanged), never the whole record, and every
    indicator is an O(N) numpy computation with no FFT -- DEC-108's own
    multi-window tiling stays within this SAME capped region, so total
    work remains bounded regardless of the record's own total duration.
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

    windowed_result = _classify_windows(slice_time, slice_values, nominal_frequency_hz)
    if windowed_result is not None:
        return windowed_result

    # Not enough data for two windows -- fall back to the original
    # Phase 5B single-slice classification over the whole region,
    # unchanged.
    return _classify_slice(slice_time, slice_values, nominal_frequency_hz)
