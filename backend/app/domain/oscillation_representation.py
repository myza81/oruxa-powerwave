"""Oscillation Analysis -- analysis representations of raw V/I waveforms
(DEC-173 [APPROVED]).

A raw instantaneous AC waveform `x(t) = A(t) sin(2 pi f0 t + phi)` carries the
50/60 Hz carrier. Oscillation Analysis studies the slow changes of `A(t)`,
so a raw V/I channel must first become an *amplitude* series. The only
representation implemented is `rms_magnitude`: the project's EXISTING
trailing one-cycle true RMS, `app.domain.calculated_channel.evaluate_rms`
-- called, never re-implemented. This module adds only what a *consumer* of
that series needs to know and the engine does not state:

- where the derived series is valid (the leading one-cycle boundary loss);
- the time-axis convention (output stays on the source time stamps; being a
  trailing window it lags the signal by half a cycle);
- the effective bandwidth of the representation (below).

The derived series is analysis-internal: nothing here stores or registers a
calculated channel.

**Effective bandwidth (mathematical, not empirical).** With a trailing
window of length `T = 1/f0`, `mean_window(x^2)` filters the instantaneous
power `A^2 (1 - cos 2 theta) / 2` with a rectangular (boxcar) window whose
magnitude response is `|sinc(f T)| = |sin(pi f T) / (pi f T)|`. The
double-frequency term sits exactly on a null (2 f0). For a small amplitude
modulation `A = A0 (1 + m cos 2 pi fm t)`, `A^2` has a component `2 m` at
`fm`, so the recovered envelope modulation is attenuated by the same
`|sinc(fm / f0)|` (the square root linearises for small `m`). Consequences:

- `-3 dB` at `fm ~ 0.443 f0` (about 22 Hz at 50 Hz, 27 Hz at 60 Hz);
- first null at `fm = f0` and side lobes above it (peak ~21 %), where the
  response is not monotonic and modulation is no longer recovered
  faithfully -- the RMS representation is NOT valid at or above `f0`;
- the sample rate is irrelevant to this limit: a 5 kHz record gives a 5 kHz
  output series, but its bandwidth is still bounded by `f0`, not `fs / 2`;
- the window is linear phase, so the delay is a constant `T / 2` for every
  modulation frequency (no distortion, only a shift).

Zero framework dependencies (domain layer). NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.domain.calculated_channel import (
    evaluate_rms,
    nominal_frequency_valid,
    rms_recording_long_enough,
    rms_sampling_dense_enough,
)

REPRESENTATION_RMS_MAGNITUDE = "rms_magnitude"
IMPLEMENTED_REPRESENTATIONS = (REPRESENTATION_RMS_MAGNITUDE,)

#: The derived series has one value per source sample (the engine never
#: downsamples), so its reporting rate equals the source sampling rate.
REPORTING_EVERY_SOURCE_SAMPLE = "every_source_sample"
#: `evaluate_rms` is a trailing window `(t - T, t]`.
WINDOW_ALIGNMENT_TRAILING = "trailing"


def _half_power_ratio() -> float:
    """x such that sin(pi x) / (pi x) = 1 / sqrt(2), on the main lobe
    (0 < x < 1). Solved by bisection so the constant is derived, not typed."""
    target = 1.0 / math.sqrt(2.0)
    lo, hi = 1e-9, 1.0 - 1e-9
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if math.sin(math.pi * mid) / (math.pi * mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


HALF_POWER_RATIO = _half_power_ratio()  # ~0.4429


def rms_envelope_response(modulation_hz: float, nominal_frequency_hz: float) -> float:
    """Amplitude ratio (0..1) with which a small envelope modulation at
    `modulation_hz` survives a one-cycle trailing RMS: |sinc(fm / f0)|."""
    x = abs(modulation_hz) / nominal_frequency_hz
    if x == 0.0:
        return 1.0
    return abs(math.sin(math.pi * x) / (math.pi * x))


def rms_half_power_frequency_hz(nominal_frequency_hz: float) -> float:
    """The -3 dB modulation frequency of the RMS representation."""
    return HALF_POWER_RATIO * nominal_frequency_hz


def rms_bandwidth_limit_hz(nominal_frequency_hz: float) -> float:
    """First null of the RMS window response (= the nominal frequency).
    Modulation at or above this is not recovered; it plays the role Nyquist
    plays for a plain sampled signal."""
    return float(nominal_frequency_hz)


@dataclass(frozen=True, slots=True)
class DerivedMagnitude:
    """The analysis-ready magnitude series, still on the source time axis.

    `values` has the SAME length as `time`; samples before the first
    complete window (and any window touching a non-finite input) are NaN.
    `valid_*` describe the finite span that downstream analysis may use.
    """

    representation: str
    time: np.ndarray
    values: np.ndarray
    nominal_frequency_hz: float
    window_s: float
    group_delay_s: float
    valid_count: int
    first_valid_index: int | None
    last_valid_index: int | None


def representation_unavailable_reason(time: np.ndarray, nominal_frequency_hz: float) -> tuple[str, str] | None:
    """`(code, message)` when the RMS representation cannot be formed safely
    from this time axis, else None. These are the engine's own hard
    data-quality guards (also enforced when creating an RMS calculated
    channel), reused rather than restated."""
    if not nominal_frequency_valid(nominal_frequency_hz):
        return ("invalid_nominal_frequency", "The recording's nominal frequency is missing or outside a sensible range.")
    if not rms_recording_long_enough(time, nominal_frequency_hz):
        return ("recording_too_short", "The recording is shorter than one complete RMS window (one nominal cycle).")
    if not rms_sampling_dense_enough(time, nominal_frequency_hz):
        return (
            "sampling_too_sparse",
            "The sample rate is too low relative to one nominal cycle to form a meaningful RMS magnitude.",
        )
    return None


def derive_rms_magnitude(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> DerivedMagnitude:
    """Reuses `evaluate_rms` unchanged. Callers must have checked
    `representation_unavailable_reason()` first."""
    rms = evaluate_rms(time, values, nominal_frequency_hz)
    finite = np.flatnonzero(np.isfinite(rms))
    window_s = 1.0 / nominal_frequency_hz
    return DerivedMagnitude(
        representation=REPRESENTATION_RMS_MAGNITUDE,
        time=time,
        values=rms,
        nominal_frequency_hz=float(nominal_frequency_hz),
        window_s=window_s,
        group_delay_s=window_s / 2.0,
        valid_count=int(finite.size),
        first_valid_index=int(finite[0]) if finite.size else None,
        last_valid_index=int(finite[-1]) if finite.size else None,
    )
