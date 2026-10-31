"""Sliding-window fundamental-frequency phasor engine (Slice 2; DEC-201).

Produces a time series of complex RMS fundamental-frequency phasors from
instantaneous voltage or current waveform samples by applying a trailing
one-cycle DFT window across the full input waveform.

## Relationship to estimate_phasor()

This module is the vectorised companion to `app.domain.phasor.estimate_phasor()`.
Both implement the identical estimator formula

    X = (sqrt(2) / N) * sum_n( x_n * exp(-j * 2*pi*f0 * t_n) )

over a trailing one-cycle half-open window `(t - 1/f0, t]`, with the same
RMS normalisation, the same angle-reference convention, and the same
unavailability guardrails. The only distinction is computational:
`estimate_phasor()` evaluates the formula at ONE caller-supplied
`analysis_time`; `compute_sliding_phasor()` evaluates it efficiently at every
output time step, producing arrays rather than scalars.

## RMS normalisation proof (identical to phasor.py)

For a sampled sinusoid x(t) = A*cos(2*pi*f0*t + phi) over N samples spanning
one full fundamental period (discrete orthogonality property):

    Re{X} = (sqrt(2)/N) * sum(x_n*cos(w*t_n)) ~= (A/sqrt(2))*cos(phi)
    Im{X} = -(sqrt(2)/N) * sum(x_n*sin(w*t_n)) ~= (A/sqrt(2))*sin(phi)

so X = (A/sqrt(2)) * exp(j*phi), with |X| = A/sqrt(2) = RMS magnitude and
angle(X) = phi = the sinusoid's own phase at t=0. Never peak amplitude.

## Window timestamp convention

Trailing: the phasor output at time t corresponds to the window
`(t - 1/f0, t]` -- the same half-open trailing convention established by
`evaluate_rms()` and `estimate_phasor()`. Phasor at t uses no future samples.

## Phase-angle reference

Identical to `estimate_phasor()`: t_n MUST be expressed on a source-
independent common time coordinate (absolute epoch, reduced by a fixed per-
request epoch for floating-point precision). This module never constructs
that coordinate -- that is the caller's responsibility, exactly as for
`estimate_phasor()`. A phasor at angle 0 means the waveform reaches its
positive peak exactly at t=0 of the input time coordinate. Cross-channel
phase differences are meaningful only when both channels share the same epoch.

## Algorithms

Two O(N) paths are chosen automatically by inspecting the actual time spacing:

**Uniform spacing** (the common case for a single COMTRADE sampling-rate
section): vectorised cumulative sums of the real (cosine) and imaginary
(sine) projections. Zero Python-level loop; all array arithmetic is in NumPy.
Non-finite input samples are tracked via a separate running count to prevent
NaN poisoning the cumsums -- the same invariant `evaluate_rms()` already
maintains for its own running sum of squares.

**Irregular spacing** (multi-rate or genuinely non-uniform timestamps):
two-pointer sliding window with an incremental complex DFT sum. Still O(N)
total work (each sample enters and leaves the window exactly once), but
involves a Python-level loop over input samples. Carries O(N * machine_eps)
accumulated floating-point error in the incremental sum; for practical
disturbance recordings (up to ~1e6 samples) this is < 1 ppm and negligible.
Documented here as a known limitation -- never hidden from callers.

## Compatibility

Output complex phasors X are compatible with `app.domain.power_calculation`:
pass `abs(X)` as `v_magnitude_rms` or `i_magnitude_rms`, and
`degrees(angle(X))` as the corresponding `_angle_deg` argument to
`single_phase_power()` or `three_phase_power()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.domain.phasor import (
    PHASOR_MIN_SAMPLES_PER_CYCLE,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    REASON_INSUFFICIENT_WINDOW_HISTORY,
    REASON_INVALID_SAMPLES_IN_WINDOW,
    REASON_NO_SAMPLES,
)

#: Bump ONLY when the estimator algorithm / window / normalisation
#: interpretation changes -- not for a refactor.  Independent of
#: phasor.ALGORITHM_VERSION (single-point estimator) since both can
#: evolve separately.
ALGORITHM_VERSION = "sliding_phasor_v1"

#: Reason codes returned for whole-call rejections (not per-window).
REASON_INVALID_FREQUENCY = "invalid_reference_frequency"
REASON_INVALID_STRIDE = "invalid_output_stride"

#: Absorbs floating-point noise at window boundaries -- same purpose as
#: phasor._BOUNDARY_EPS; re-declared here (not imported) following the
#: codebase convention that each module owns its own tiny boundary constant.
_BOUNDARY_EPS = 1e-9

#: Sample-spacing regularity thresholds -- identical to phasor._SPACING_RTOL
#: / _SPACING_ATOL; re-declared here for the same reason.
_SPACING_RTOL = 1e-6
_SPACING_ATOL = 1e-12

_NAN_COMPLEX = complex(float("nan"), float("nan"))


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlidingPhasorResult:
    """Time series of trailing-window phasor estimates.

    All array fields have the same length M (number of output time steps).
    For unavailable windows, `phasor` is ``nan+nan*j`` and `available` is
    ``False``.
    """

    time: np.ndarray
    """float64. Output timestamps (seconds), same coordinate as input time.
    These are a subset of the input time array at every `output_stride`-th
    sample, starting from index 0."""

    phasor: np.ndarray
    """complex128. X = (A/sqrt(2)) * exp(j*phi) for x(t) = A*cos(w*t + phi).
    |X| is the RMS magnitude; angle(X) in radians is the phase phi.
    ``nan+nan*j`` for unavailable windows."""

    available: np.ndarray
    """bool. True when the window produced a valid, finite estimate."""

    reason_code: np.ndarray
    """object dtype (str). Empty string '' when available. One of the
    REASON_* constants from app.domain.phasor (or this module's own
    REASON_INVALID_FREQUENCY / REASON_INVALID_STRIDE) for unavailable
    windows."""

    sample_count: np.ndarray
    """int32. Total samples present in the window (including any non-finite
    ones). 0 when reason_code is REASON_INSUFFICIENT_WINDOW_HISTORY
    (window has not yet accumulated a full cycle of history)."""

    reference_frequency_hz: float
    """Nominal fundamental frequency used for the window (Hz)."""

    window_seconds: float
    """Window duration = 1 / reference_frequency_hz (seconds)."""

    algorithm_version: str = ALGORITHM_VERSION


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_sliding_phasor(
    time: np.ndarray,
    values: np.ndarray,
    reference_frequency_hz: float = 50.0,
    *,
    output_stride: int = 1,
    min_samples_per_cycle: int = PHASOR_MIN_SAMPLES_PER_CYCLE,
) -> SlidingPhasorResult:
    """Compute a time series of complex RMS fundamental-frequency phasors.

    Uses a trailing one-cycle DFT window at each output time step --
    numerically equivalent to calling ``estimate_phasor(time, values, t,
    reference_frequency_hz)`` for every output time ``t``, but O(N) for
    uniform spacing rather than O(N * M).

    Parameters
    ----------
    time:
        1-D float64 array of sample timestamps (seconds). Must be
        monotonic non-decreasing. Must be expressed on a source-independent
        common time coordinate (see module docstring -- this function never
        constructs or resets the coordinate, mirroring ``estimate_phasor()``).
    values:
        1-D array of instantaneous waveform samples (same length as
        ``time``). Non-finite samples are handled explicitly; the window
        containing them is marked unavailable (never silently dropped or
        interpolated).
    reference_frequency_hz:
        Nominal fundamental frequency (Hz). Must be in [1, 1000]. Defaults
        to 50 Hz. This is a fixed reference, not a measured frequency;
        off-nominal signals produce estimation error (see module docstring).
    output_stride:
        Step between output time indices (positive integer, default 1 =
        every input sample). ``output_stride=s`` produces one output phasor
        per s input samples, downsampling the time series by a factor of s.
    min_samples_per_cycle:
        Minimum samples required in a valid window. Windows below this
        threshold return ``available=False`` with
        ``REASON_INSUFFICIENT_SAMPLING_DENSITY``.

    Returns
    -------
    SlidingPhasorResult
        Arrays of length ``M = ceil(N / output_stride)``.  Elements before
        the first complete window (fewer than ``1/f0`` seconds of history)
        have ``available=False`` and
        ``reason_code=REASON_INSUFFICIENT_WINDOW_HISTORY``.  Elements with
        any non-finite sample in their window have
        ``reason_code=REASON_INVALID_SAMPLES_IN_WINDOW``.
    """
    n = time.shape[0]

    # Whole-call validation -- check frequency BEFORE dividing (avoids
    # ZeroDivisionError for f=0 and NaN/inf propagation for bad values).
    if not (isinstance(reference_frequency_hz, (int, float))
            and 1.0 <= reference_frequency_hz <= 1000.0):
        window_seconds = 0.0  # placeholder; never used for a valid result
        if n == 0:
            return _make_empty_result(window_seconds, reference_frequency_hz)
        out_time = time[::output_stride]
        return _make_all_unavailable(
            out_time, window_seconds, reference_frequency_hz, REASON_INVALID_FREQUENCY
        )

    window_seconds = 1.0 / reference_frequency_hz

    if n == 0:
        return _make_empty_result(window_seconds, reference_frequency_hz)

    if not isinstance(output_stride, int) or output_stride < 1:
        out_time = time[:1]
        return _make_all_unavailable(
            out_time, window_seconds, reference_frequency_hz, REASON_INVALID_STRIDE
        )

    out_time_indices = np.arange(0, n, output_stride, dtype=np.intp)

    # Detect spacing uniformity (identical check to evaluate_rms() and
    # estimate_phasor()).
    if n >= 2:
        diffs = np.diff(time)
        uniform = bool(
            np.allclose(diffs, np.median(diffs), rtol=_SPACING_RTOL, atol=_SPACING_ATOL)
        )
    else:
        uniform = True  # single sample -- will be marked insufficient history

    if uniform:
        return _uniform_path(
            time, values, reference_frequency_hz, window_seconds,
            out_time_indices, min_samples_per_cycle,
        )
    return _irregular_path(
        time, values, reference_frequency_hz, window_seconds,
        out_time_indices, min_samples_per_cycle,
    )


# ---------------------------------------------------------------------------
# Convenience helpers for callers
# ---------------------------------------------------------------------------

def magnitude_rms(result: SlidingPhasorResult) -> np.ndarray:
    """RMS magnitude array from a SlidingPhasorResult.

    Returns a float64 array of length M. Unavailable elements are ``nan``.
    Equivalent to ``np.abs(result.phasor)`` but named for clarity.
    """
    return np.abs(result.phasor)


def angle_deg(result: SlidingPhasorResult) -> np.ndarray:
    """Phase angle array (degrees, (-180, 180]) from a SlidingPhasorResult.

    Returns a float64 array of length M. Unavailable elements are ``nan``.
    Equivalent to ``np.degrees(np.angle(result.phasor))`` but named for
    clarity and consistent with ``estimate_phasor()``'s ``angle_deg`` field.
    """
    return np.degrees(np.angle(result.phasor))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_empty_result(window_seconds: float, freq: float) -> SlidingPhasorResult:
    return SlidingPhasorResult(
        time=np.array([], dtype=np.float64),
        phasor=np.array([], dtype=np.complex128),
        available=np.array([], dtype=bool),
        reason_code=np.array([], dtype=object),
        sample_count=np.array([], dtype=np.int32),
        reference_frequency_hz=freq,
        window_seconds=window_seconds,
    )


def _make_all_unavailable(
    out_time: np.ndarray,
    window_seconds: float,
    freq: float,
    reason: str,
) -> SlidingPhasorResult:
    m = out_time.shape[0]
    reason_code = np.empty(m, dtype=object)
    reason_code[:] = reason
    return SlidingPhasorResult(
        time=out_time.astype(np.float64),
        phasor=np.full(m, _NAN_COMPLEX, dtype=np.complex128),
        available=np.zeros(m, dtype=bool),
        reason_code=reason_code,
        sample_count=np.zeros(m, dtype=np.int32),
        reference_frequency_hz=freq,
        window_seconds=window_seconds,
    )


def _uniform_path(
    time: np.ndarray,
    values: np.ndarray,
    reference_frequency_hz: float,
    window_seconds: float,
    out_time_indices: np.ndarray,
    min_samples_per_cycle: int,
) -> SlidingPhasorResult:
    """O(N) cumulative-sum path for uniformly spaced samples.

    Uses the same window-size formula as evaluate_rms(): n_window =
    round(window_seconds / dt).  For non-integer samples per cycle, this
    rounds to the nearest integer -- a window that is off by at most half
    a sample interval from the ideal 1/f0 duration, which produces
    negligible magnitude and phase error (same approximation evaluate_rms()
    already accepts for its own one-cycle window).
    """
    n = time.shape[0]
    dt = float(np.median(np.diff(time))) if n >= 2 else float("inf")
    n_window = max(int(round(window_seconds / dt)), 1)

    m = out_time_indices.shape[0]
    out_time = time[out_time_indices]

    out_phasor = np.full(m, _NAN_COMPLEX, dtype=np.complex128)
    out_available = np.zeros(m, dtype=bool)
    out_reason = np.empty(m, dtype=object)
    out_reason[:] = ""
    out_sample_count = np.zeros(m, dtype=np.int32)

    # Whole-series density check: if no window can ever have enough samples,
    # mark all unavailable immediately (avoids the cumsum work).
    if n_window < min_samples_per_cycle:
        out_reason[:] = REASON_INSUFFICIENT_SAMPLING_DENSITY
        return SlidingPhasorResult(
            time=out_time, phasor=out_phasor, available=out_available,
            reason_code=out_reason, sample_count=out_sample_count,
            reference_frequency_hz=reference_frequency_hz,
            window_seconds=window_seconds,
        )

    # Precompute the DFT projections, zeroing non-finite samples.
    # Non-finite tracking is kept separate from the sum to prevent NaN
    # poisoning the cumsum (the same invariant evaluate_rms() maintains for
    # its running sum of squares -- IEEE 754: NaN - NaN = NaN, so one bad
    # sample would corrupt every subsequent window if accumulated directly).
    w = 2.0 * np.pi * reference_frequency_hz
    angle_arr = w * time
    finite_mask = np.isfinite(values)
    vals_safe = np.where(finite_mask, values.astype(np.float64), 0.0)
    cos_safe = vals_safe * np.cos(angle_arr)
    sin_safe = vals_safe * np.sin(angle_arr)
    nonfinite = (~finite_mask).astype(np.int32)

    # Prefix sums of length n+1: cumcos[i] = sum(cos_safe[0:i]).
    cumcos = np.empty(n + 1, dtype=np.float64)
    cumcos[0] = 0.0
    np.cumsum(cos_safe, out=cumcos[1:])

    cumsin = np.empty(n + 1, dtype=np.float64)
    cumsin[0] = 0.0
    np.cumsum(sin_safe, out=cumsin[1:])

    cumnf = np.empty(n + 1, dtype=np.int32)
    cumnf[0] = 0
    np.cumsum(nonfinite, out=cumnf[1:])

    # Output positions that have a full window of history.
    # Criterion: time[k] - time[0] >= window_seconds - _BOUNDARY_EPS --
    # identical to estimate_phasor()'s own guard: "the recording must contain
    # at least one full cycle of data before analysis_time".  For uniform
    # spacing this fires at k = n_window (not n_window - 1): the window at
    # k = n_window - 1 would span exactly (n_window - 1) * dt < 1/f0 seconds,
    # which means the window START falls before time[0].
    valid_output_mask = (
        (time[out_time_indices] - time[0]) >= (window_seconds - _BOUNDARY_EPS)
    )
    out_reason[~valid_output_mask] = REASON_INSUFFICIENT_WINDOW_HISTORY

    valid_positions = np.flatnonzero(valid_output_mask)
    if valid_positions.shape[0] > 0:
        k = out_time_indices[valid_positions]      # input sample indices
        lo = k - n_window + 1                       # window start (inclusive)

        cos_sum = cumcos[k + 1] - cumcos[lo]
        sin_sum = cumsin[k + 1] - cumsin[lo]
        nf_count = cumnf[k + 1] - cumnf[lo]

        out_sample_count[valid_positions] = n_window

        # Any non-finite sample in the window invalidates the whole window.
        has_nf = nf_count > 0
        if has_nf.any():
            out_reason[valid_positions[has_nf]] = REASON_INVALID_SAMPLES_IN_WINDOW

        # Good (finite) windows.
        good = ~has_nf
        if good.any():
            good_positions = valid_positions[good]
            scale = math.sqrt(2.0) / n_window
            real = scale * cos_sum[good]
            imag = -scale * sin_sum[good]
            out_phasor[good_positions] = (real + 1j * imag).astype(np.complex128)
            out_available[good_positions] = True

    return SlidingPhasorResult(
        time=out_time, phasor=out_phasor, available=out_available,
        reason_code=out_reason, sample_count=out_sample_count,
        reference_frequency_hz=reference_frequency_hz,
        window_seconds=window_seconds,
    )


def _irregular_path(
    time: np.ndarray,
    values: np.ndarray,
    reference_frequency_hz: float,
    window_seconds: float,
    out_time_indices: np.ndarray,
    min_samples_per_cycle: int,
) -> SlidingPhasorResult:
    """Two-pointer incremental path for non-uniformly spaced samples.

    O(N) total work for stride=1: each sample enters and leaves the sliding
    window exactly once.  The incremental DFT sum accumulates O(N *
    machine_epsilon) floating-point error, negligible for practical
    disturbance recordings (< 1 ppm for N <= 1e6 samples).

    This path involves a Python-level loop over input samples and is
    slower than the uniform path for long recordings; it is correct but
    intended only for the genuinely-irregular-spacing case (multi-rate or
    non-uniform COMTRADE files).
    """
    n = time.shape[0]
    m = out_time_indices.shape[0]
    out_time = time[out_time_indices]

    out_phasor = np.full(m, _NAN_COMPLEX, dtype=np.complex128)
    out_available = np.zeros(m, dtype=bool)
    out_reason = np.empty(m, dtype=object)
    out_reason[:] = ""
    out_sample_count = np.zeros(m, dtype=np.int32)

    # Precompute complex DFT kernel once per sample (never re-evaluated when
    # sliding the window, which would make this O(N * N_window)).
    # e_terms[i] = values[i] * exp(-j*w*t[i]) for finite samples, else 0+0j.
    w = 2.0 * np.pi * reference_frequency_hz
    finite_mask = np.isfinite(values)
    vals_safe = np.where(finite_mask, values.astype(np.float64), 0.0)
    e_terms = vals_safe * np.exp(-1j * w * time)

    lo_ptr = 0          # exclusive lower bound of the current window
    e_sum = 0.0 + 0.0j  # running sum of e_terms in [lo_ptr, hi]
    nf_count = 0        # non-finite samples in current window
    n_in_window = 0     # total samples in current window

    out_idx = 0         # current index into output arrays

    for hi in range(n):
        # Add sample hi to the window.
        e_sum += e_terms[hi]
        if not finite_mask[hi]:
            nf_count += 1
        n_in_window += 1

        # Evict samples that have fallen outside the trailing window
        # (time[hi] - window_seconds, time[hi]].
        window_start = time[hi] - window_seconds
        while lo_ptr <= hi and time[lo_ptr] <= window_start + _BOUNDARY_EPS:
            e_sum -= e_terms[lo_ptr]
            if not finite_mask[lo_ptr]:
                nf_count -= 1
            n_in_window -= 1
            lo_ptr += 1

        # Emit output at this input index if it is an output time step.
        if out_idx < m and out_time_indices[out_idx] == hi:
            if time[hi] - time[0] < window_seconds - _BOUNDARY_EPS:
                out_reason[out_idx] = REASON_INSUFFICIENT_WINDOW_HISTORY
            elif nf_count > 0:
                out_sample_count[out_idx] = n_in_window
                out_reason[out_idx] = REASON_INVALID_SAMPLES_IN_WINDOW
            elif n_in_window < min_samples_per_cycle:
                out_sample_count[out_idx] = n_in_window
                out_reason[out_idx] = REASON_INSUFFICIENT_SAMPLING_DENSITY
            else:
                out_sample_count[out_idx] = n_in_window
                scale = math.sqrt(2.0) / n_in_window
                out_phasor[out_idx] = scale * e_sum
                out_available[out_idx] = True
            out_idx += 1

        if out_idx >= m:
            break

    # Remaining output positions that were never reached (e.g. stride jumped
    # past end of recording).
    while out_idx < m:
        out_reason[out_idx] = REASON_INSUFFICIENT_WINDOW_HISTORY
        out_idx += 1

    return SlidingPhasorResult(
        time=out_time, phasor=out_phasor, available=out_available,
        reason_code=out_reason, sample_count=out_sample_count,
        reference_frequency_hz=reference_frequency_hz,
        window_seconds=window_seconds,
    )
