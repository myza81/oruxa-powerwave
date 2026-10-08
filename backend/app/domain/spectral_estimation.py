"""Oscillation Analysis -- Welch power spectral density (DEC-174 [PROPOSAL]).

A one-sided Welch PSD estimate, `scipy.signal.welch`-equivalent for the
parameters fixed below. The project has no SciPy runtime dependency
(`requirements.txt` pins NumPy/pandas only), so the estimator is the standard
Welch recipe on `numpy.fft.rfft`; SciPy is a pinned *dev-only* reference and
`tests/test_oscillation_spectrum.py` proves bin-for-bin parity with
`scipy.signal.welch` for the same parameters.

Fixed Phase-1 parameters (named constants, reported with every result):

- window        Hann (periodic / DFT-even form, i.e. SciPy `get_window("hann")`)
- detrend       `constant` -- each segment's mean is removed before windowing
- overlap       50 % (`noverlap = nperseg // 2`)
- averaging     mean of the per-segment periodograms
- scaling       `density` -- V^2/Hz, one-sided (all bins but DC and, for an
                even `nperseg`, Nyquist are doubled)
- nfft          `nperseg` -- NO zero-padding, so the bin spacing `fs / nperseg`
                is exactly the Welch segment's frequency grid

**Segment length** is derived, never a fixed number of seconds
(`choose_segmentation`): target `2 / f_min` seconds (two cycles of the lowest
requested frequency), or `window / 4.5` seconds (about eight 50 %-overlapped
segments) when `f_min = 0`, rounded to whole samples and clamped to the
window. A window that cannot hold the target yields ONE segment, which is
reported as such -- no averaging happens and none is claimed.

Resolution concepts that must not be conflated:

- `1 / T_window`  -- the basic estimate of the whole analysis window;
- `fs / nperseg`  -- the Welch bin spacing, the grid the PSD is actually on.

Zero framework dependencies (domain layer). NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

WELCH_WINDOW = "hann"
WELCH_DETREND = "constant"
WELCH_AVERAGE = "mean"
WELCH_SCALING = "density"
WELCH_OVERLAP_FRACTION = 0.5

#: Cycles of the lowest requested frequency one Welch segment should span.
SEGMENT_CYCLES_OF_MIN_FREQUENCY = 2.0
#: `f_min = 0` has no period; the segment is chosen so a window holds about
#: eight 50 %-overlapped segments: T = L * (1 + (K - 1) / 2) -> L = T / 4.5.
FALLBACK_WINDOW_DIVISOR = 4.5
#: Fewer samples per segment than this cannot form a meaningful periodogram.
MIN_SEGMENT_SAMPLES = 8
#: Fewer averaged segments than this is reported as limited averaging.
RECOMMENDED_MIN_SEGMENTS = 4


@dataclass(frozen=True, slots=True)
class Segmentation:
    """The Welch segment geometry for one window."""

    nperseg: int
    noverlap: int
    segment_count: int
    segment_s: float
    bin_spacing_hz: float
    target_segment_s: float
    #: True when the segment had to be shortened to fit the window.
    clamped_to_window: bool
    #: Samples at the end that do not fill another segment (dropped, as SciPy).
    unused_tail_samples: int


@dataclass(frozen=True, slots=True)
class WelchPsd:
    frequencies_hz: np.ndarray
    psd: np.ndarray
    segmentation: Segmentation


def target_segment_seconds(window_s: float, f_min_hz: float) -> float:
    if f_min_hz > 0:
        return SEGMENT_CYCLES_OF_MIN_FREQUENCY / f_min_hz
    return window_s / FALLBACK_WINDOW_DIVISOR


def segment_count_for(sample_count: int, nperseg: int, noverlap: int) -> int:
    if sample_count < nperseg:
        return 0
    return (sample_count - noverlap) // (nperseg - noverlap)


def choose_segmentation(sample_count: int, fs_hz: float, f_min_hz: float) -> Segmentation:
    """Deterministic segment geometry for `sample_count` samples at `fs_hz`.
    Raises ValueError when the window cannot hold a minimal segment."""
    if not (math.isfinite(fs_hz) and fs_hz > 0):
        raise ValueError("The sampling rate must be positive.")
    if f_min_hz < 0 or not math.isfinite(f_min_hz):
        raise ValueError("The minimum frequency must not be negative.")
    if sample_count < MIN_SEGMENT_SAMPLES:
        raise ValueError(
            f"The window holds {sample_count} sample(s); at least {MIN_SEGMENT_SAMPLES} are needed for a Welch segment."
        )
    window_s = sample_count / fs_hz
    target_s = target_segment_seconds(window_s, f_min_hz)
    target_samples = max(int(round(target_s * fs_hz)), MIN_SEGMENT_SAMPLES)
    nperseg = min(target_samples, sample_count)
    noverlap = int(nperseg * WELCH_OVERLAP_FRACTION)
    count = segment_count_for(sample_count, nperseg, noverlap)
    used = noverlap + count * (nperseg - noverlap)
    return Segmentation(
        nperseg=nperseg, noverlap=noverlap, segment_count=count, segment_s=nperseg / fs_hz,
        bin_spacing_hz=fs_hz / nperseg, target_segment_s=target_s,
        clamped_to_window=target_samples > sample_count, unused_tail_samples=sample_count - used,
    )


def hann_window(n: int) -> np.ndarray:
    """Periodic Hann (`scipy.signal.get_window("hann", n)`, fftbins=True)."""
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)


def welch_psd(values: np.ndarray, fs_hz: float, seg: Segmentation) -> WelchPsd:
    """One-sided Welch PSD (density) of a finite, uniformly sampled series
    with the constant-detrended, Hann-windowed, 50 %-overlapped segments of
    `seg`. Output units are `unit^2 / Hz`."""
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("Welch PSD needs a one-dimensional series of finite samples.")
    n, step = seg.nperseg, seg.nperseg - seg.noverlap
    if seg.segment_count < 1 or x.size < n:
        raise ValueError("The window does not hold one complete Welch segment.")
    starts = np.arange(seg.segment_count) * step
    segments = np.lib.stride_tricks.sliding_window_view(x, n)[starts]  # (K, n) view copied below
    segments = segments - segments.mean(axis=1, keepdims=True)  # constant detrend
    window = hann_window(n)
    spectrum = np.fft.rfft(segments * window, n=n, axis=1)
    periodograms = (spectrum.real ** 2 + spectrum.imag ** 2) / (fs_hz * np.sum(window ** 2))
    if n % 2:
        periodograms[:, 1:] *= 2.0
    else:
        periodograms[:, 1:-1] *= 2.0
    psd = periodograms.mean(axis=0)
    return WelchPsd(frequencies_hz=np.fft.rfftfreq(n, d=1.0 / fs_hz), psd=psd, segmentation=seg)
