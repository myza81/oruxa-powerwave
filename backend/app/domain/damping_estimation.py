"""Oscillation Analysis -- ringdown damping estimation of one spectral candidate
(DEC-177 [PROPOSAL]).

Question answered: *when a candidate oscillatory component (DEC-175) is excited,
is its amplitude decaying, approximately sustained or growing, how fast, and
how well does an exponential describe it?*  Deterministic and transparent: no
AI, no opaque score, no Prony / Matrix Pencil, no classification of the
oscillation type. Every number in a result is a measured / calculated value.

**Model (Phase-1 baseline).**  ``x(t) = offset/trend + A exp(sigma t) cos(2 pi f t + phi)``.

* Decay-rate convention (used everywhere, names and UI): ``alpha = -sigma`` in
  s^-1, so the amplitude is proportional to ``exp(-alpha t)``. ``alpha > 0``
  decays, ``alpha ~ 0`` is sustained, ``alpha < 0`` grows.
* ``f`` is the DAMPED oscillation frequency in Hz (what a spectrum shows); the
  angular frequency is ``omega = 2 pi f`` rad/s.
* Damping ratio of an under-damped mode, with ``omega`` the damped frequency:
  ``zeta = alpha / sqrt(alpha^2 + omega^2)``  (dimensionless; x 100 for %).
  Reported only for a decaying component.

**Estimator.**  (1) The analysed window is transformed once (``rfft``). (2) For
a candidate, a zero-phase Gaussian band-pass (applied on the positive
frequencies, i.e. FFT-domain isolation) of full-width-at-half-maximum
``B`` around the candidate yields the analytic (complex) narrowband component,
evaluated on a small decimated baseband time grid. Its modulus is the amplitude
envelope ``a(t)`` (signal units, peak amplitude), its phase gives the
instantaneous frequency. A complex exponential is an exact eigenfunction of an
LTI filter, so the filter does not change the decay rate of a ringdown; it
removes the offset, trend and slow event recovery, which have no energy at the
candidate frequency. (3) ``ln a(t)`` is fitted by least squares over a
deterministically selected interval; ``sigma`` is the slope.

**Filter bandwidth rule.**  ``B = max(0.30 f, 0.15 Hz)``, reduced so the nearest
other candidate lies at least 3.5 Gaussian sigmas away and the upper skirt
stays 3.5 sigmas below Nyquist (never below ``0.15 Hz``; a candidate that
cannot be isolated that way is reported). A Gaussian has no side lobes, its
impulse response ``exp(-2 pi^2 s^2 t^2)`` is negligible after ``EDGE_GUARD_SIGMAS``
time-sigmas, and that guard is removed from both ends of the window AND after
the envelope peak (a step or fault disturbs the band like a short, fast-fading
ringdown of the filter itself -- the guard keeps the fit clear of it).

**Fit interval.**  Start = envelope peak + guard (post-excitation); if that
leaves too few cycles (sustained / growing components), the contiguous active
run around the peak. End = where the 1-cycle-smoothed envelope falls below
``max(3 x background, 2 % of the start level)`` or the guarded window ends.
Background = median envelope of the same filter shifted two
bandwidths either side (the lower of the two).

All thresholds are named Phase-1 engineering heuristics, not standards.

Zero framework dependencies (domain layer). NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ------------------------------------------------------------ Phase-1 heuristics
#: FWHM of the Gaussian band as a fraction of the candidate frequency.
BANDWIDTH_FRACTION = 0.30
#: Narrowest band (Hz) -- a narrower filter would smear a short ringdown.
MIN_BANDWIDTH_HZ = 0.15
#: The nearest other candidate / Nyquist / DC must sit at least this many
#: Gaussian sigmas from the band centre.
ISOLATION_SIGMAS = 3.5
#: Window edges and the span after the envelope peak that are not used (filter
#: transients), in time-sigmas of the filter's impulse response.
EDGE_GUARD_SIGMAS = 4.0
#: Spectral support kept for a band (Gaussian sigmas each side of the centre).
BAND_SPAN_SIGMAS = 5.0
#: Baseband samples per spectral bin kept (>= 1 is critical sampling).
BASEBAND_OVERSAMPLE = 4
MIN_BASEBAND_POINTS = 64
#: Envelope smoothing window, in oscillation cycles.
SMOOTH_CYCLES = 1.0
#: Background is measured with the same band centred this many FWHMs away.
NOISE_OFFSET_FWHMS = 2.0
#: The envelope must stay at least this multiple of the background.
MIN_AMPLITUDE_OVER_NOISE = 3.0
#: ...and the fit stops when the envelope drops below this fraction of its start level.
ENVELOPE_FLOOR_FRACTION = 0.02
#: Minimum oscillation cycles in the fit interval.
MIN_FIT_CYCLES = 4.0
#: Minimum envelope samples in the fit interval.
MIN_FIT_SAMPLES = 16
#: Fitted envelope change over the interval within +-this fraction is "approximately sustained".
SUSTAINED_ENVELOPE_CHANGE = 0.10
#: Fit-quality limits (natural-log envelope units; R2 only judged for a non-flat envelope).
MAX_RMS_LOG_RESIDUAL = 0.20
MIN_R_SQUARED = 0.80
#: Fraction of per-cycle envelope steps that must go in the fitted direction (decaying / growing).
MIN_MONOTONIC_FRACTION = 0.75
#: A separate active run (>= this many cycles, >= this fraction of the fit-start level) = intermittent.
INTERMITTENT_MIN_CYCLES = 2.0
INTERMITTENT_FRACTION = 0.5
#: Neighbouring-component leakage (amplitude ratio estimate): warn / refuse.
LEAKAGE_WARNING = 0.05
LEAKAGE_LIMIT = 0.25
#: Phase-slope frequency refinement is accepted when its weighted RMS phase residual is below this (rad).
MAX_PHASE_RESIDUAL_RAD = 0.5
#: Transport: at most this many envelope points per candidate cross the wire.
EVIDENCE_MAX_POINTS = 500

FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))  # 2.3548

STATUS_AVAILABLE = "available"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_NOT_APPLICABLE = "not_applicable"
BEHAVIOUR_DECAYING = "decaying"
BEHAVIOUR_SUSTAINED = "approximately_sustained"
BEHAVIOUR_GROWING = "growing"


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


def _evidence(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


@dataclass(frozen=True, slots=True)
class WindowSpectrum:
    """The one-sided spectrum of the analysed window, computed once and shared by
    every candidate (and by the background estimates)."""

    spectrum: np.ndarray
    n: int
    fs: float
    t_first: float

    @property
    def df(self) -> float:
        return self.fs / self.n

    @property
    def nyquist(self) -> float:
        return self.fs / 2.0

    @property
    def span_s(self) -> float:
        return (self.n - 1) / self.fs


def window_spectrum(t_first: float, x: np.ndarray, fs: float) -> WindowSpectrum:
    x = np.asarray(x, dtype=np.float64)
    return WindowSpectrum(spectrum=np.fft.rfft(x - float(np.mean(x))), n=int(x.size), fs=float(fs), t_first=float(t_first))


@dataclass(frozen=True, slots=True)
class Baseband:
    """Analytic narrowband component on a decimated grid. ``z`` is relative to
    ``reference_hz`` (the frequency of the bin the baseband is shifted by)."""

    tau: np.ndarray  # seconds from the first sample
    z: np.ndarray
    reference_hz: float


def _next_pow2(n: int) -> int:
    return 1 << max(0, (int(n) - 1).bit_length())


def band_baseband(ws: WindowSpectrum, centre_hz: float, sigma_hz: float) -> Baseband | None:
    """Zero-phase Gaussian band-pass around ``centre_hz`` (analytic, gain 1 at the
    centre), decimated to a baseband grid. ``None`` when no spectral bin falls in the band."""
    df = ws.df
    last_bin = ws.n // 2 - (1 if ws.n % 2 == 0 else 0)  # exclude Nyquist (and DC below)
    k_lo = max(1, int(math.ceil((centre_hz - BAND_SPAN_SIGMAS * sigma_hz) / df)))
    k_hi = min(last_bin, int(math.floor((centre_hz + BAND_SPAN_SIGMAS * sigma_hz) / df)))
    if k_hi < k_lo:
        return None
    k = np.arange(k_lo, k_hi + 1)
    weights = np.exp(-0.5 * ((k * df - centre_hz) / sigma_hz) ** 2)
    coeff = 2.0 * weights * ws.spectrum[k_lo:k_hi + 1]
    k0 = int(round(centre_hz / df))
    m = _next_pow2(max(MIN_BASEBAND_POINTS, BASEBAND_OVERSAMPLE * k.size))
    spec = np.zeros(m, dtype=np.complex128)
    spec[(k - k0) % m] = coeff
    z = np.fft.ifft(spec) * (m / ws.n)
    tau = np.arange(m) * (ws.n / ws.fs) / m
    return Baseband(tau=tau, z=z, reference_hz=k0 * df)


def _moving_average(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width)) | 1
    if width == 1:
        return values.copy()
    cum = np.concatenate(([0.0], np.cumsum(values)))
    idx = np.arange(values.size)
    lo = np.clip(idx - width // 2, 0, values.size)
    hi = np.clip(idx + width // 2 + 1, 0, values.size)
    return (cum[hi] - cum[lo]) / (hi - lo)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(first, last) index of every maximal run of True."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), (np.flatnonzero(edges == -1) - 1).tolist()))


def _background(ws: WindowSpectrum, centre_hz: float, sigma_hz: float, bandwidth_hz: float, valid: tuple[float, float]) -> dict:
    """Median envelope of the same band centred either side of the candidate; the lower
    available side (robust to a stronger neighbouring mode and to a localised step)."""
    offset = NOISE_OFFSET_FWHMS * bandwidth_hz
    levels: dict[str, float] = {}
    for side, centre in (("lower", centre_hz - offset), ("upper", centre_hz + offset)):
        if centre - 3.0 * sigma_hz < ws.df or centre + 3.0 * sigma_hz > ws.nyquist - ws.df:
            continue
        base = band_baseband(ws, centre, sigma_hz)
        if base is None:
            continue
        inside = (base.tau >= valid[0]) & (base.tau <= valid[1])
        if np.any(inside):
            levels[side] = float(np.median(np.abs(base.z[inside])))
    if not levels:
        return {"level": None, "sides": []}
    return {"level": min(levels.values()), "sides": sorted(levels)}


def _result(status: str, frequency_hz: float, reason_code: str | None, message: str, **extra) -> dict:
    out = {
        "candidate_frequency_hz": frequency_hz, "status": status, "reason_code": reason_code, "message": message,
        "behaviour": None, "fit": None, "decay_rate_per_s": None, "time_constant_s": None, "damping_ratio": None,
        "frequency": None, "fit_quality": None, "envelope_change": None, "filter": None, "background": None,
        "reasons": [], "warnings": [], "evidence": None,
    }
    out.update(extra)
    return out


def _insufficient(frequency_hz: float, code: str, message: str, **extra) -> dict:
    reasons = extra.pop("reasons", None) or [_evidence(code, message, **extra.pop("values", {}))]
    extra.pop("values", None)
    return _result(STATUS_INSUFFICIENT, frequency_hz, code, message, reasons=reasons, **extra)


def estimate_damping(
    ws: WindowSpectrum, candidate_hz: float, candidate_psd: float | None = None,
    others: list[tuple[float, float]] | None = None, unit: str = "",
) -> dict:
    """The damping result of one candidate. ``others``: ``(frequency_hz, psd)`` of the
    other accepted candidates (isolation + leakage estimate). Never raises for weak data:
    every shortfall is an ``insufficient_evidence`` / ``not_applicable`` result with reasons."""
    f0 = float(candidate_hz)
    nyq = ws.nyquist
    others = [(f, p) for f, p in (others or []) if abs(f - f0) > 1e-12]
    unit_text = f" {unit}" if unit else ""

    # ---- band rule --------------------------------------------------------
    bandwidth = max(BANDWIDTH_FRACTION * f0, MIN_BANDWIDTH_HZ)
    limit_nyq = FWHM_PER_SIGMA * (nyq - f0) / ISOLATION_SIGMAS
    limit_dc = FWHM_PER_SIGMA * f0 / ISOLATION_SIGMAS
    nearest = min(others, key=lambda o: abs(o[0] - f0)) if others else None
    limit_neighbour = FWHM_PER_SIGMA * abs(nearest[0] - f0) / ISOLATION_SIGMAS if nearest else math.inf
    bandwidth = min(bandwidth, limit_nyq, limit_neighbour)
    if limit_nyq < MIN_BANDWIDTH_HZ:
        return _result(
            STATUS_NOT_APPLICABLE, f0, "near_nyquist",
            f"The candidate at {_fmt(f0)} Hz is too close to the Nyquist frequency ({_fmt(nyq)} Hz) of the analysed samples "
            "for the component to be isolated; no damping estimate is made.",
            reasons=[_evidence("near_nyquist", "Too close to the representation's Nyquist frequency to isolate.", nyquist_hz=nyq)],
        )
    if limit_dc < MIN_BANDWIDTH_HZ:
        return _result(
            STATUS_NOT_APPLICABLE, f0, "near_zero_frequency",
            f"The candidate at {_fmt(f0)} Hz is too close to 0 Hz for the component to be isolated from the offset and "
            "slow event recovery; no damping estimate is made.",
            reasons=[_evidence("near_zero_frequency", "Too close to 0 Hz to isolate from the trend.", frequency_hz=f0)],
        )
    bandwidth = max(bandwidth, MIN_BANDWIDTH_HZ)
    sigma_f = bandwidth / FWHM_PER_SIGMA
    sigma_t = 1.0 / (2.0 * math.pi * sigma_f)
    guard = EDGE_GUARD_SIGMAS * sigma_t
    filter_block = {
        "type": "gaussian_bandpass_fft", "zero_phase": True, "centre_hz": f0, "bandwidth_fwhm_hz": bandwidth,
        "sigma_hz": sigma_f, "edge_guard_s": guard, "nearest_other_candidate_hz": nearest[0] if nearest else None,
        "neighbour_leakage": None,
    }

    leakage = 0.0
    warnings: list[dict] = []
    if nearest and candidate_psd and candidate_psd > 0 and nearest[1] > 0:
        d = abs(nearest[0] - f0)
        leakage = math.sqrt(nearest[1] / candidate_psd) * math.exp(-0.5 * (d / sigma_f) ** 2)
        filter_block["neighbour_leakage"] = leakage
        if leakage >= LEAKAGE_LIMIT:
            return _insufficient(
                f0, "component_not_isolated",
                f"The neighbouring component at {_fmt(nearest[0])} Hz is stronger and too close ({_fmt(d)} Hz) to be separated "
                f"from the {_fmt(f0)} Hz candidate (estimated leakage {leakage:.0%} of its amplitude; limit {LEAKAGE_LIMIT:.0%}).",
                filter=filter_block,
            )
        if leakage >= LEAKAGE_WARNING:
            warnings.append(_evidence(
                "neighbouring_component_leakage",
                f"The neighbouring component at {_fmt(nearest[0])} Hz may leak about {leakage:.0%} of its amplitude into this band; "
                "the envelope may show beating.", leakage=leakage, neighbour_hz=nearest[0],
            ))

    valid = (guard, ws.span_s - guard)
    cycle_s = 1.0 / f0
    if valid[1] - valid[0] < MIN_FIT_CYCLES * cycle_s:
        return _insufficient(
            f0, "ringdown_interval_too_short",
            f"After removing {_fmt(guard)} s of filter transient at each end of the window, only "
            f"{_fmt(max(0.0, valid[1] - valid[0]) * f0)} cycles of {_fmt(f0)} Hz remain (at least {_fmt(MIN_FIT_CYCLES)} are needed).",
            filter=filter_block,
        )

    base = band_baseband(ws, f0, sigma_f)
    if base is None:
        return _insufficient(f0, "band_not_resolved", "The analysis window is too short to resolve the candidate band.", filter=filter_block)

    # ---- envelope ---------------------------------------------------------
    inside = (base.tau >= valid[0]) & (base.tau <= valid[1])
    tv = base.tau[inside]
    zv = base.z[inside]
    av = np.abs(zv)
    dt_bb = float(base.tau[1] - base.tau[0])
    smooth_width = max(1, int(round(SMOOTH_CYCLES * cycle_s / dt_bb)))
    sv = _moving_average(np.abs(base.z), smooth_width)[inside]
    if not np.all(np.isfinite(sv)) or float(np.max(sv)) <= 0.0:
        return _insufficient(f0, "no_component_energy", "No signal energy was found in the candidate band.", filter=filter_block)

    background = _background(ws, f0, sigma_f, bandwidth, valid)
    noise = background["level"]
    floor_noise = MIN_AMPLITUDE_OVER_NOISE * noise if noise else 0.0
    background_block = {"level": noise, "sides": background["sides"], "min_amplitude_over_background": MIN_AMPLITUDE_OVER_NOISE}

    def evidence_block(fit: tuple[int, int] | None = None, fitted: np.ndarray | None = None) -> dict:
        stride = max(1, math.ceil(tv.size / EVIDENCE_MAX_POINTS))
        pick = np.arange(0, tv.size, stride)
        times = (ws.t_first + tv[pick]).tolist()
        env = sv[pick].tolist()
        fit_curve = None
        if fit is not None and fitted is not None:
            full = np.full(tv.size, np.nan)
            full[fit[0]:fit[1] + 1] = fitted
            fit_curve = [None if not math.isfinite(v) else float(v) for v in full[pick]]
        return {
            "times_s": times, "envelope": env, "fitted_envelope": fit_curve,
            "valid_start_s": ws.t_first + valid[0], "valid_end_s": ws.t_first + valid[1],
            "fit_start_s": ws.t_first + tv[fit[0]] if fit else None, "fit_end_s": ws.t_first + tv[fit[1]] if fit else None,
            "background_level": noise, "stride": stride,
        }

    # ---- interval selection ----------------------------------------------
    peak = int(np.argmax(sv))
    n_pts = tv.size

    def interval_after_peak():
        start = int(np.searchsorted(tv, tv[peak] + guard))
        if start >= n_pts:
            return None
        level = float(sv[start])
        floor = max(floor_noise, ENVELOPE_FLOOR_FRACTION * level)
        if level < floor_noise or level <= 0:
            return None
        below = np.flatnonzero(sv[start:] < floor)
        end = start + (int(below[0]) - 1 if below.size else n_pts - 1 - start)
        return (start, end, floor) if end > start else None

    def interval_around_peak():
        floor = max(floor_noise, ENVELOPE_FLOOR_FRACTION * float(sv[peak]))
        if float(sv[peak]) < floor_noise or sv[peak] < floor:
            return None
        below_left = np.flatnonzero(sv[:peak + 1] < floor)
        below_right = np.flatnonzero(sv[peak:] < floor)
        start = int(below_left[-1]) + 1 if below_left.size else 0
        end = peak + (int(below_right[0]) - 1 if below_right.size else n_pts - 1 - peak)
        return (start, end, floor) if end > start else None

    def cycles_of(interval) -> float:
        return f0 * float(tv[interval[1]] - tv[interval[0]]) if interval else 0.0

    option_a, option_b = interval_after_peak(), interval_around_peak()
    chosen = None
    rule = None
    if option_a and cycles_of(option_a) >= MIN_FIT_CYCLES:
        chosen, rule = option_a, "after_envelope_peak"
    elif option_b and cycles_of(option_b) >= MIN_FIT_CYCLES:
        chosen, rule = option_b, "active_run_around_peak"
    if chosen is None:
        if option_a is None and option_b is None:
            return _insufficient(
                f0, "near_noise_floor",
                "The candidate band never stands clearly above the local background noise "
                f"(the envelope must stay at least {_fmt(MIN_AMPLITUDE_OVER_NOISE)} x the background), so no ringdown can be fitted.",
                filter=filter_block, background=background_block, warnings=warnings, evidence=evidence_block(),
            )
        best = max(cycles_of(option_a), cycles_of(option_b))
        if noise and float(sv[peak]) < 2.0 * floor_noise:
            return _insufficient(
                f0, "near_noise_floor",
                f"The candidate band peaks at only {float(sv[peak]) / noise:.1f} x the local background noise "
                f"(the envelope must stay at least {_fmt(MIN_AMPLITUDE_OVER_NOISE)} x the background over a usable interval), "
                "so the component remains near the noise floor and no ringdown is fitted.",
                filter=filter_block, background=background_block, warnings=warnings, evidence=evidence_block(),
            )
        return _insufficient(
            f0, "insufficient_cycles",
            f"The longest usable interval holds only {_fmt(best)} cycles of {_fmt(f0)} Hz (at least {_fmt(MIN_FIT_CYCLES)} are needed): "
            "the ringdown interval is too short.",
            filter=filter_block, background=background_block, warnings=warnings, evidence=evidence_block(),
        )
    i_s, i_e, floor = chosen
    n_fit = i_e - i_s + 1
    if n_fit < MIN_FIT_SAMPLES:
        return _insufficient(
            f0, "insufficient_samples", f"Only {n_fit} envelope samples fall in the fit interval (at least {MIN_FIT_SAMPLES} are needed).",
            filter=filter_block, background=background_block, warnings=warnings, evidence=evidence_block((i_s, i_e)),
        )

    # ---- intermittent: another comparable active run outside the fitted one --
    fit_level = float(sv[i_s])
    for first, last in _runs(sv >= floor):
        if first <= i_s <= last or (first <= peak <= last):
            continue
        cycles = f0 * float(tv[last] - tv[first])
        if cycles >= INTERMITTENT_MIN_CYCLES and float(np.mean(sv[first:last + 1])) >= INTERMITTENT_FRACTION * fit_level:
            return _insufficient(
                f0, "intermittent_component",
                f"The {_fmt(f0)} Hz component appears as separate bursts (another {_fmt(cycles)}-cycle burst of comparable amplitude is "
                "separated from the fit interval by a quiet gap), so a single exponential ringdown does not describe it.",
                values={"burst_start_s": ws.t_first + float(tv[first]), "burst_end_s": ws.t_first + float(tv[last]), "burst_cycles": cycles},
                filter=filter_block, background=background_block, warnings=warnings, evidence=evidence_block((i_s, i_e)),
            )

    # ---- exponential fit of the log envelope ------------------------------
    tt = tv[i_s:i_e + 1]
    y = np.log(sv[i_s:i_e + 1])
    t_c = tt - tt[0]
    slope, intercept = np.polyfit(t_c, y, 1)
    fitted_log = intercept + slope * t_c
    sse = float(np.sum((y - fitted_log) ** 2))
    sst = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - sse / sst if sst > 1e-12 else None
    rms_log = math.sqrt(sse / n_fit)
    duration = float(tt[-1] - tt[0])
    log_change = float(slope) * duration
    alpha = -float(slope) + 0.0
    sustained = abs(log_change) < math.log1p(SUSTAINED_ENVELOPE_CHANGE)
    direction = np.sign(slope)
    stride = max(1, int(round(cycle_s / dt_bb)))
    per_cycle = sv[i_s:i_e + 1:stride]
    steps = np.diff(per_cycle)
    monotonic = float(np.mean(np.sign(steps) == direction)) if steps.size >= 3 and not sustained else None

    fitted_env = np.exp(fitted_log)
    start_amp, end_amp = float(fitted_env[0]), float(fitted_env[-1])
    envelope_change = {
        "start_amplitude": start_amp, "end_amplitude": end_amp, "log_change": log_change,
        "change_percent": (end_amp / start_amp - 1.0) * 100.0, "unit": unit or None,
    }
    quality = {
        "r_squared": r_squared, "rms_log_residual": rms_log, "monotonic_fraction": monotonic, "samples": n_fit,
        # Duration x filter bandwidth ~ the number of independent envelope values behind the fit (information only).
        "time_bandwidth_product": duration * bandwidth,
    }
    fit_ev = evidence_block((i_s, i_e), fitted_env)

    # ---- frequency (phase slope; reported separately) ---------------------
    zf = zv[i_s:i_e + 1]
    phase = np.unwrap(np.angle(zf))
    w = np.abs(zf) ** 2
    p_slope, p_icpt = np.polyfit(t_c, phase, 1, w=np.sqrt(w))
    phase_rms = math.sqrt(float(np.sum(w * (phase - (p_icpt + p_slope * t_c)) ** 2) / np.sum(w)))
    f_fit = base.reference_hz + p_slope / (2.0 * math.pi)
    fitted_frequency = None
    frequency_source = "candidate"
    if phase_rms <= MAX_PHASE_RESIDUAL_RAD and abs(f_fit - f0) <= bandwidth / 2.0:
        fitted_frequency, frequency_source = float(f_fit), "fitted"
    else:
        warnings.append(_evidence(
            "frequency_refinement_unreliable",
            f"The phase-slope frequency ({_fmt(f_fit)} Hz) was not used (phase scatter {phase_rms:.2f} rad or farther than "
            f"{_fmt(bandwidth / 2.0)} Hz from the candidate); the candidate frequency is used.", fitted_hz=float(f_fit),
        ))
    f_used = fitted_frequency if fitted_frequency is not None else f0
    cycles_used = f_used * duration
    omega = 2.0 * math.pi * f_used

    frequency_block = {"candidate_hz": f0, "fitted_hz": fitted_frequency, "used_hz": f_used, "source": frequency_source}
    fit_block = {
        "start_s": ws.t_first + float(tt[0]), "end_s": ws.t_first + float(tt[-1]), "duration_s": duration,
        "cycles_used": cycles_used, "samples": n_fit, "rule": rule, "peak_s": ws.t_first + float(tv[peak]),
    }
    background_block["start_amplitude_over_background"] = start_amp / noise if noise else None
    background_block["end_amplitude_over_background"] = end_amp / noise if noise else None
    common = dict(
        fit=fit_block, frequency=frequency_block, fit_quality=quality, envelope_change=envelope_change, filter=filter_block,
        background=background_block, evidence=fit_ev,
    )

    # ---- fit-quality refusal ---------------------------------------------
    problems: list[dict] = []
    if rms_log > MAX_RMS_LOG_RESIDUAL:
        problems.append(_evidence(
            "envelope_scatter_too_high",
            f"The envelope departs from a single exponential by {rms_log:.2f} (RMS, natural-log units; limit {_fmt(MAX_RMS_LOG_RESIDUAL)}).",
            rms_log_residual=rms_log, limit=MAX_RMS_LOG_RESIDUAL))
    if not sustained and r_squared is not None and r_squared < MIN_R_SQUARED:
        problems.append(_evidence(
            "fit_quality_too_low", f"The exponential envelope fit R² = {r_squared:.2f} is below the minimum {_fmt(MIN_R_SQUARED)}.",
            r_squared=r_squared, limit=MIN_R_SQUARED))
    if monotonic is not None and monotonic < MIN_MONOTONIC_FRACTION:
        problems.append(_evidence(
            "envelope_not_monotonic",
            f"Only {monotonic:.0%} of the cycle-to-cycle envelope steps follow the fitted trend (at least {MIN_MONOTONIC_FRACTION:.0%} required).",
            monotonic_fraction=monotonic, limit=MIN_MONOTONIC_FRACTION))
    post_peak_cycles = max(0.0, f0 * (valid[1] - (float(tv[peak]) + guard)))
    if problems and rule == "active_run_around_peak" and post_peak_cycles < MIN_FIT_CYCLES:
        problems.insert(0, _evidence(
            "ringdown_interval_too_short",
            f"Only {_fmt(post_peak_cycles)} cycles remain after the envelope peak and its {_fmt(guard)} s filter guard "
            f"(at least {_fmt(MIN_FIT_CYCLES)} are needed), so the ringdown interval is too short.",
            cycles_after_peak=post_peak_cycles))
    if problems:
        return _insufficient(
            f0, problems[0]["code"], "The envelope does not support an exponential ringdown fit: " + " ".join(p["message"] for p in problems),
            reasons=problems, warnings=warnings, **common,
        )

    # ---- available --------------------------------------------------------
    behaviour = BEHAVIOUR_SUSTAINED if sustained else (BEHAVIOUR_DECAYING if alpha > 0 else BEHAVIOUR_GROWING)
    zeta = alpha / math.sqrt(alpha * alpha + omega * omega) if behaviour == BEHAVIOUR_DECAYING else None
    t0s, t1s = fit_block["start_s"], fit_block["end_s"]
    reasons = [
        # TIME BASES: every absolute time in `values` / `fit` is the signal's SOURCE time; the page shows the Time Group
        # display basis. Messages therefore carry no absolute times -- the page composes them from `values` (DEC-177).
        _evidence("candidate_active",
                  (f"Candidate at {_fmt(f0)} Hz remained at least {_fmt(MIN_AMPLITUDE_OVER_NOISE)}× above the background noise throughout the "
                   "damping fit interval." if noise else
                   f"Candidate at {_fmt(f0)} Hz stayed above {ENVELOPE_FLOOR_FRACTION:.0%} of its fit-start level throughout the damping fit "
                   "interval (no background noise was measurable)."),
                  start_s=t0s, end_s=t1s, background_multiple=MIN_AMPLITUDE_OVER_NOISE if noise else None),
        _evidence("fit_interval", "The exponential damping fit used the fit interval (the same interval).", start_s=t0s, end_s=t1s,
                  duration_s=duration),
        _evidence("cycles_used", f"{_fmt(cycles_used)} cycles of {_fmt(f_used)} Hz were used ({n_fit} envelope samples over {_fmt(duration)} s).",
                  cycles=cycles_used, samples=n_fit, duration_s=duration),
    ]
    change = envelope_change["change_percent"]
    if behaviour == BEHAVIOUR_SUSTAINED:
        reasons.append(_evidence(
            "envelope_change", f"The fitted envelope changed by {change:+.1f} % over {_fmt(duration)} s (within ±{SUSTAINED_ENVELOPE_CHANGE:.0%}): "
            "approximately sustained over this interval.", change_percent=change, duration_s=duration))
    else:
        verb = "decreased" if behaviour == BEHAVIOUR_DECAYING else "increased"
        reasons.append(_evidence(
            "envelope_change", f"Oscillation envelope {verb} by {abs(change):.0f} % over {_fmt(duration)} s "
            f"(from {_fmt(start_amp)} to {_fmt(end_amp)}{unit_text}).", change_percent=change, duration_s=duration))
    r2_text = f"R² = {r_squared:.2f}, " if r_squared is not None and not sustained else ""
    reasons.append(_evidence(
        "exponential_fit", f"Exponential envelope fit: {r2_text}RMS log-envelope scatter {rms_log:.2f}.",
        r_squared=r_squared, rms_log_residual=rms_log))
    rate_word = {BEHAVIOUR_DECAYING: "decay rate", BEHAVIOUR_GROWING: "growth rate", BEHAVIOUR_SUSTAINED: "fitted decay rate"}[behaviour]
    reasons.append(_evidence(
        "decay_rate", f"Estimated {rate_word} = {_fmt(abs(alpha) if behaviour != BEHAVIOUR_SUSTAINED else alpha, 3)} s⁻¹ "
        "(amplitude ∝ e^(−αt), α > 0 decays).", decay_rate_per_s=alpha))
    if zeta is not None:
        reasons.append(_evidence(
            "damping_ratio", f"Damping ratio ζ = α / √(α² + ω²) = {zeta * 100:.2f} % at {_fmt(f_used)} Hz (ω = 2πf).", damping_ratio=zeta))
    else:
        reasons.append(_evidence(
            "damping_ratio_not_reported",
            "A damping ratio is reported only for a decaying component; this behaviour is not a ringdown decay.", behaviour=behaviour))
    reasons.append(_evidence(
        "isolation", f"Component isolated with a zero-phase Gaussian band of {_fmt(bandwidth)} Hz (FWHM); "
        f"{_fmt(guard)} s of filter transient excluded at the window ends and after the envelope peak.",
        bandwidth_hz=bandwidth, edge_guard_s=guard))
    message = {
        BEHAVIOUR_DECAYING: "Decaying", BEHAVIOUR_SUSTAINED: "Approximately sustained", BEHAVIOUR_GROWING: "Growing",
    }[behaviour]
    return _result(
        STATUS_AVAILABLE, f0, None, message, behaviour=behaviour, decay_rate_per_s=alpha,
        time_constant_s=(1.0 / abs(alpha)) if abs(alpha) > 1e-12 else None, damping_ratio=zeta,
        reasons=reasons, warnings=warnings, **common,
    )
