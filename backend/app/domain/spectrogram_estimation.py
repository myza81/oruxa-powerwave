"""Oscillation Analysis -- short-time Fourier transform spectrogram (DEC-176
[APPROVED]).

Adds the TIME dimension to the Welch spectrum (DEC-174): a one-sided PSD per
overlapping time slice, answering "when does a frequency component occur?".
Evidence only -- nothing here classifies a component.

Same conventions as `app.domain.spectral_estimation` (the accepted Welch
estimator, which this module imports from but never alters):

- window        Hann (periodic / DFT-even form, `scipy.signal.get_window("hann")`)
- detrend       `constant` -- each slice's mean is removed before windowing
- overlap       50 % (`noverlap = nperseg // 2`)
- scaling       `density` -- one-sided `unit^2 / Hz` (all bins but DC and, for an
                even `nperseg`, Nyquist doubled), identical to a single Welch
                periodogram. The mean over all slices therefore EQUALS the Welch
                PSD of the same geometry (tested).
- nfft          `nperseg` -- NO zero-padding, so the row spacing `fs / nperseg`
                is the true frequency grid of one slice
- slices        only complete slices; the unused tail is reported (as SciPy)
- time stamp    the CENTRE of each slice, `t_first + (start + nperseg / 2) / fs`
                (SciPy's `spectrogram` convention)

**Window-length policy** (`choose_stft_geometry`, deterministic, Phase 1). A
longer window resolves low frequencies better but blurs *when* things happen.
The rule starts from the Welch target and then protects time resolution:

1. target  = `2 / f_min` seconds (two cycles of the lowest requested frequency),
             or `T / 4.5` when `f_min = 0`;
2. cap     = the longest window that still yields at least
             `TARGET_TIME_SLICES` (8) slices at 50 % overlap (about `T / 4.5`);
3. window  = min(target, cap), never below `MIN_STFT_SAMPLES` (16) samples and
             never longer than the data;
4. usable  = the window must still hold at least `MIN_WINDOW_CYCLES_OF_MIN_FREQUENCY`
             (1) cycle of `f_min`, else the service reports the spectrogram
             unavailable (a very short recording).

Where the cap shortens the window the frequency resolution is coarser than the
Welch spectrum's; the service reports that as a warning, never silently.

Zero framework dependencies (domain layer). NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.domain.spectral_estimation import (
    FALLBACK_WINDOW_DIVISOR,
    SEGMENT_CYCLES_OF_MIN_FREQUENCY,
    WELCH_DETREND,
    WELCH_OVERLAP_FRACTION,
    WELCH_SCALING,
    WELCH_WINDOW,
    hann_window,
)

STFT_WINDOW = WELCH_WINDOW
STFT_DETREND = WELCH_DETREND
STFT_SCALING = WELCH_SCALING
STFT_OVERLAP_FRACTION = WELCH_OVERLAP_FRACTION
STFT_CYCLES_OF_MIN_FREQUENCY = SEGMENT_CYCLES_OF_MIN_FREQUENCY

#: The window is shortened until at least this many time slices fit.
TARGET_TIME_SLICES = 8
#: Fewer slices than this is not a time-frequency picture (reported unavailable).
MIN_TIME_SLICES = 3
#: Fewer samples per slice cannot form a meaningful periodogram.
MIN_STFT_SAMPLES = 16
#: Fewer frequency rows inside the requested band is not a spectrogram.
MIN_FREQUENCY_ROWS = 3
#: A slice shorter than this many cycles of the lowest requested frequency cannot
#: show that frequency at all (the time-resolution cap may shorten the window
#: below the preferred two cycles, but not below one).
MIN_WINDOW_CYCLES_OF_MIN_FREQUENCY = 1.0
#: Slices transformed per batch -- bounds the working memory for long records.
_CHUNK_SLICES = 256

LIMITED_BY_NONE = "none"
LIMITED_BY_TIME_RESOLUTION = "time_resolution"
LIMITED_BY_MINIMUM_SAMPLES = "minimum_samples"
LIMITED_BY_DATA = "data_length"


@dataclass(frozen=True, slots=True)
class StftGeometry:
    """The slice geometry for one analysis window."""

    nperseg: int
    noverlap: int
    hop: int
    slice_count: int
    window_s: float
    hop_s: float
    bin_spacing_hz: float
    target_window_s: float
    #: Why the window is shorter than the target (or `none`).
    limited_by: str
    unused_tail_samples: int


@dataclass(frozen=True, slots=True)
class Spectrogram:
    frequencies_hz: np.ndarray  # (rows,) one-sided slice grid, fs / nperseg apart
    times_s: np.ndarray  # (columns,) slice-centre times relative to the first sample
    psd: np.ndarray  # (rows, columns) unit^2 / Hz
    geometry: StftGeometry


def target_window_seconds(duration_s: float, f_min_hz: float) -> float:
    if f_min_hz > 0:
        return STFT_CYCLES_OF_MIN_FREQUENCY / f_min_hz
    return duration_s / FALLBACK_WINDOW_DIVISOR


def slice_count_for(sample_count: int, nperseg: int, noverlap: int) -> int:
    if sample_count < nperseg:
        return 0
    return (sample_count - noverlap) // (nperseg - noverlap)


def choose_stft_geometry(sample_count: int, fs_hz: float, f_min_hz: float) -> StftGeometry:
    """Deterministic STFT geometry for `sample_count` samples at `fs_hz`.
    Never raises for a short window -- the caller judges `slice_count`."""
    if not (math.isfinite(fs_hz) and fs_hz > 0):
        raise ValueError("The sampling rate must be positive.")
    if f_min_hz < 0 or not math.isfinite(f_min_hz):
        raise ValueError("The minimum frequency must not be negative.")
    if sample_count < 2:
        raise ValueError("The window holds fewer than two samples.")
    duration_s = sample_count / fs_hz
    target_s = target_window_seconds(duration_s, f_min_hz)
    target_samples = max(int(round(target_s * fs_hz)), MIN_STFT_SAMPLES)
    nperseg = min(target_samples, sample_count)
    limited_by = LIMITED_BY_DATA if target_samples > sample_count else LIMITED_BY_NONE

    def slices(length: int) -> int:
        return slice_count_for(sample_count, length, int(length * STFT_OVERLAP_FRACTION))

    if slices(nperseg) < TARGET_TIME_SLICES:
        # The longest window that still gives TARGET_TIME_SLICES slices.
        shorter = min(nperseg, int(sample_count / (1.0 + (TARGET_TIME_SLICES - 1) * STFT_OVERLAP_FRACTION)) + 1)
        while shorter > MIN_STFT_SAMPLES and slices(shorter) < TARGET_TIME_SLICES:
            shorter -= 1
        if shorter < MIN_STFT_SAMPLES:
            shorter = min(MIN_STFT_SAMPLES, sample_count)
        if shorter < nperseg:
            nperseg = shorter
            limited_by = LIMITED_BY_MINIMUM_SAMPLES if slices(nperseg) < TARGET_TIME_SLICES else LIMITED_BY_TIME_RESOLUTION
    noverlap = int(nperseg * STFT_OVERLAP_FRACTION)
    hop = nperseg - noverlap
    count = slice_count_for(sample_count, nperseg, noverlap)
    used = noverlap + count * hop if count else 0
    return StftGeometry(
        nperseg=nperseg, noverlap=noverlap, hop=hop, slice_count=count, window_s=nperseg / fs_hz, hop_s=hop / fs_hz,
        bin_spacing_hz=fs_hz / nperseg, target_window_s=target_s, limited_by=limited_by,
        unused_tail_samples=sample_count - used if count else sample_count,
    )


def stft_psd(values: np.ndarray, fs_hz: float, geometry: StftGeometry) -> Spectrogram:
    """One-sided PSD (density) of every complete slice of a finite, uniformly
    sampled series. Output units are `unit^2 / Hz`; times are slice centres
    relative to the first sample."""
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("The STFT needs a one-dimensional series of finite samples.")
    n, hop = geometry.nperseg, geometry.hop
    if geometry.slice_count < 1 or x.size < n:
        raise ValueError("The window does not hold one complete STFT slice.")
    window = hann_window(n)
    norm = fs_hz * float(np.sum(window ** 2))
    starts = np.arange(geometry.slice_count) * hop
    view = np.lib.stride_tricks.sliding_window_view(x, n)
    columns = np.empty((n // 2 + 1, geometry.slice_count), dtype=np.float64)
    for first in range(0, geometry.slice_count, _CHUNK_SLICES):
        chunk = view[starts[first:first + _CHUNK_SLICES]]
        chunk = chunk - chunk.mean(axis=1, keepdims=True)  # constant detrend
        spectrum = np.fft.rfft(chunk * window, n=n, axis=1)
        power = (spectrum.real ** 2 + spectrum.imag ** 2) / norm
        if n % 2:
            power[:, 1:] *= 2.0
        else:
            power[:, 1:-1] *= 2.0
        columns[:, first:first + chunk.shape[0]] = power.T
    return Spectrogram(
        frequencies_hz=np.fft.rfftfreq(n, d=1.0 / fs_hz), times_s=(starts + n / 2.0) / fs_hz, psd=columns,
        geometry=geometry,
    )


def peak_hold_rows(frequencies_hz: np.ndarray, psd: np.ndarray, factor: int) -> tuple[np.ndarray, np.ndarray]:
    """Reduce the frequency rows by `factor` for transport: each group of
    `factor` ADJACENT rows becomes one row holding the group's MAXIMUM (so a
    narrow ridge is never averaged away) at the group's mean frequency. Time is
    untouched. `factor = 1` returns the inputs."""
    if factor <= 1:
        return frequencies_hz, psd
    edges = np.arange(0, psd.shape[0], factor)
    counts = np.diff(np.append(edges, psd.shape[0]))
    return np.add.reduceat(frequencies_hz, edges) / counts, np.maximum.reduceat(psd, edges, axis=0)
