"""Oscillation Analysis -- magnitude-squared coherence between the signals of a cross-signal component (DEC-181 [PROPOSAL], building on DEC-171..180).

Question answered: *how consistently are two signals linearly related at the oscillation frequency?*  Supporting evidence next to the
frequency match, temporal overlap, damping, relative phase and mode shape. Nothing here classifies an oscillation (DEC-179 is untouched),
infers causality or direction, or uses AI; coherence is **not** a probability or a confidence.

**Definition.**  ``Cxy(f) = |Sxy(f)|^2 / (Sxx(f) Syy(f))`` with the Welch-averaged auto spectra ``Sxx``, ``Syy`` and cross spectrum ``Sxy``;
``0 <= Cxy <= 1``. The estimator is the accepted DEC-174 Welch recipe on ``numpy.fft.rfft`` (periodic Hann, constant detrend of every segment,
50 % overlap, one-sided, ``nfft = nperseg`` -- no zero-padding) applied to BOTH signals with ONE common segmentation, so it matches
``scipy.signal.coherence`` bin for bin (SciPy is a dev-only reference in ``tests``). The segmentation is the DEC-174 ``f_min = 0`` rule
(a segment of ``window / 4.5``, about eight overlapped segments) reused unchanged -- no second windowing convention.

**One segment is not coherence.** With a single averaged segment ``Cxy`` is identically 1 whatever the signals are. The estimate is therefore
refused (never returned) unless at least ``MIN_SEGMENTS`` overlapped segments are averaged, each at least ``MIN_SEGMENT_CYCLES`` cycles of the
target frequency long, at least ``MIN_SAMPLES_PER_CYCLE`` samples per cycle.

**Chance level (optional evidence, shown separately).** For unrelated Gaussian noise averaged over ``m`` independent segments the coherence has
the distribution ``P(C > c) = (1 - c)^(m - 1)``, so the level exceeded by chance with probability ``alpha`` is ``1 - alpha^(1 / (m - 1))``.
The independent count is the number of NON-overlapped segments, ``(K + 1) // 2`` (conservative for 50 % overlap). It assumes stationary,
independent segments (a ringdown is not stationary, so it is approximate) and says nothing about whether an oscillation is real.

**Common grid.** Signals may differ in sample rate and are never compared by index. Every signal is placed on its WORKSPACE time (the caller adds
the Time Group alignment), low-pass averaged by a boxcar of ``source rate / common rate`` samples when it is decimated, and linearly interpolated onto
one grid ``T0 + k / R`` whose rate ``R = min(source rates, MAX_COMMON_RATE_HZ)`` -- never above any member's own rate, so nothing is up-sampled to
create false detail.

All thresholds are Phase-1 engineering heuristics, not standards. NumPy only.
"""

from __future__ import annotations

import math

import numpy as np

from app.domain import spectral_estimation as se
from app.domain.mode_shape import intersect_episodes

# ---------------------------------------------------------------- Phase-1 heuristics
#: Fewest overlapped Welch segments averaged (7 overlapped = 4 independent).
MIN_SEGMENTS = 7
#: Each segment spans at least this many cycles of the target frequency (otherwise the bin grid cannot resolve it).
MIN_SEGMENT_CYCLES = 1.5
#: Fewest samples per cycle of the target frequency on the common grid.
MIN_SAMPLES_PER_CYCLE = 8.0
#: Cap of the common grid rate (cost only; the oscillation band is far lower).
MAX_COMMON_RATE_HZ = 100.0
#: Significance level of the chance-level threshold.
CHANCE_ALPHA = 0.05
#: The local band around the target frequency is +- this many bins.
LOCAL_BAND_BINS = 1.0

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_UNAVAILABLE = "unavailable"

SAME_VARIABLE = "same_variable"
CROSS_VARIABLE = "cross_variable"

NO_TIME_BASIS_MESSAGE = "coherence unavailable — recordings do not share a compatible aligned time basis"
NO_SEGMENTS_MESSAGE = "Coherence unavailable — insufficient independent segments"


def parameters() -> dict:
    return {
        "definition": "magnitude-squared coherence Cxy = |Sxy|^2 / (Sxx Syy), 0 <= Cxy <= 1 (not a probability or a confidence)",
        "estimator": "Welch: periodic Hann, constant detrend per segment, 50 % overlap, one-sided, no zero-padding, one common segmentation (DEC-174 rule, window / 4.5)",
        "time_basis": "workspace time (source time + effective alignment offset of the signal's Time Group)",
        "resampling": "boxcar anti-alias when decimating, then linear interpolation onto one grid at min(member rates, cap); never up-sampled",
        "min_segments": MIN_SEGMENTS, "min_segment_cycles": MIN_SEGMENT_CYCLES, "min_samples_per_cycle": MIN_SAMPLES_PER_CYCLE,
        "max_common_rate_hz": MAX_COMMON_RATE_HZ, "chance_alpha": CHANCE_ALPHA, "local_band_bins": LOCAL_BAND_BINS,
        "chance_level": "1 - alpha^(1/(m-1)) for m independent (non-overlapped) segments, stationary Gaussian noise; not the probability that an oscillation is real",
        "heuristics": "Phase-1 engineering heuristics, not standards; coherence is evidence only and no oscillation type, cause or direction is inferred",
    }


def _evidence(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


# ---------------------------------------------------------------- estimator ----

def independent_segments(segment_count: int) -> int:
    """Non-overlapped segments among ``segment_count`` 50 %-overlapped ones."""
    return (segment_count + 1) // 2


def chance_level(segment_count: int, alpha: float = CHANCE_ALPHA) -> float | None:
    """Coherence exceeded by unrelated noise with probability ``alpha`` (``None`` when fewer than two independent segments)."""
    m = independent_segments(segment_count)
    if m < 2:
        return None
    return 1.0 - alpha ** (1.0 / (m - 1))


def _spectra(values: np.ndarray, seg: se.Segmentation) -> np.ndarray:
    n, step = seg.nperseg, seg.nperseg - seg.noverlap
    starts = np.arange(seg.segment_count) * step
    segments = np.lib.stride_tricks.sliding_window_view(values, n)[starts]
    segments = segments - segments.mean(axis=1, keepdims=True)          # constant detrend
    return np.fft.rfft(segments * se.hann_window(n), n=n, axis=1)


def welch_coherence(x: np.ndarray, y: np.ndarray, fs_hz: float, seg: se.Segmentation) -> tuple[np.ndarray, np.ndarray]:
    """``(frequencies_hz, coherence)`` of two equally sampled finite series with the common segmentation ``seg``."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.ndim != 1 or x.shape != y.shape or not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        raise ValueError("Coherence needs two equally long one-dimensional series of finite samples.")
    if seg.segment_count < 1 or x.size < seg.nperseg:
        raise ValueError("The window does not hold one complete Welch segment.")
    a, b = _spectra(x, seg), _spectra(y, seg)
    sxx = np.mean(a.real ** 2 + a.imag ** 2, axis=0)
    syy = np.mean(b.real ** 2 + b.imag ** 2, axis=0)
    sxy = np.mean(np.conj(a) * b, axis=0)
    denominator = sxx * syy
    coherence = np.divide(sxy.real ** 2 + sxy.imag ** 2, denominator, out=np.zeros_like(denominator), where=denominator > 0.0)
    return np.fft.rfftfreq(seg.nperseg, d=1.0 / fs_hz), np.clip(coherence, 0.0, 1.0)


# ---------------------------------------------------------------- common grid ----

def _moving_average(values: np.ndarray, length: int) -> np.ndarray:
    n = values.size
    cumulative = np.concatenate([[0.0], np.cumsum(values)])
    idx = np.arange(n)
    half = length // 2
    lo, hi = np.clip(idx - half, 0, n), np.clip(idx + half + 1, 0, n)
    return (cumulative[hi] - cumulative[lo]) / (hi - lo)


def source_rate_hz(t: np.ndarray) -> float:
    return 1.0 / float(np.median(np.diff(t))) if t.size > 1 else 0.0


def to_grid(t: np.ndarray, x: np.ndarray, grid: np.ndarray, rate_hz: float) -> np.ndarray:
    """``x(t)`` on ``grid`` (NaN outside the signal's own time range). A signal faster than 1.5 x the grid rate is first averaged by a boxcar of
    ``source rate / rate`` samples (anti-alias); the interpolation is linear."""
    source = source_rate_hz(t)
    values = np.asarray(x, dtype=float)
    if source > 1.5 * rate_hz:
        values = _moving_average(values, max(2, int(round(source / rate_hz))))
    return np.interp(grid, t, values, left=np.nan, right=np.nan)


# ---------------------------------------------------------------- pair ----

def analyse_pair(x: np.ndarray, y: np.ndarray, fs_hz: float, frequency_hz: float, seg: se.Segmentation | None = None) -> dict:
    """Coherence of two series on one common grid at the target frequency: refusals first (never a misleading ~1), then the target bin,
    the local band and the chance level. ``seg`` overrides the default DEC-174 segmentation (used to test the refusals)."""
    n = int(x.size)
    base = {"samples": n, "sample_rate_hz": fs_hz, "target_frequency_hz": frequency_hz}

    def refuse(code: str, message: str, reason_values: dict | None = None, **extra) -> dict:
        return {**base, **extra, "status": STATUS_INSUFFICIENT, "reason_code": code, "message": message, "reason_values": reason_values or {}}

    if not (math.isfinite(fs_hz) and fs_hz > 0.0):
        return refuse("sampling_unknown", "The sampling rate of the common grid cannot be determined.")
    if fs_hz < MIN_SAMPLES_PER_CYCLE * frequency_hz:
        return refuse("sampling_too_coarse", f"The common grid ({_fmt(fs_hz, 3)} Hz) gives fewer than {_fmt(MIN_SAMPLES_PER_CYCLE, 3)} samples per cycle at {_fmt(frequency_hz, 4)} Hz.")
    if n < se.MIN_SEGMENT_SAMPLES:
        return refuse("too_few_samples", f"{n} samples are common to both signals; at least {se.MIN_SEGMENT_SAMPLES} are needed for a Welch segment.")
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        return refuse("non_finite_samples", "The common interval contains samples that are missing in one of the signals.")
    try:
        seg = seg or se.choose_segmentation(n, fs_hz, 0.0)
    except ValueError as exc:
        return refuse("invalid_segmentation", str(exc))
    geometry = {"segment_count": seg.segment_count, "independent_segment_count": independent_segments(seg.segment_count),
                "segment_s": seg.segment_s, "nperseg": seg.nperseg, "bin_spacing_hz": seg.bin_spacing_hz}
    cycles = seg.segment_s * frequency_hz
    if seg.segment_count < MIN_SEGMENTS:
        return refuse("insufficient_segments", NO_SEGMENTS_MESSAGE + f" ({seg.segment_count} averaged; at least {MIN_SEGMENTS} are needed).",
                      {"segment_count": seg.segment_count, "required_segments": MIN_SEGMENTS}, **geometry)
    if cycles < MIN_SEGMENT_CYCLES:
        duration = n / fs_hz
        return refuse(
            "too_few_cycles",
            f"Coherence unavailable — the shared {_fmt(duration, 3)} s interval is too short to resolve a {_fmt(frequency_hz, 3)} Hz component reliably. "
            f"Each Welch segment contains only {_fmt(cycles, 3)} cycles; at least {_fmt(MIN_SEGMENT_CYCLES, 3)} cycles are required.",
            {"interval_s": duration, "frequency_hz": frequency_hz, "segment_cycles": cycles, "required_segment_cycles": MIN_SEGMENT_CYCLES,
             "segment_s": seg.segment_s}, **geometry)
    freqs, coherence = welch_coherence(x, y, fs_hz, seg)
    nearest = int(np.argmin(np.abs(freqs - frequency_hz)))
    spacing = seg.bin_spacing_hz
    band = (np.abs(freqs - frequency_hz) <= LOCAL_BAND_BINS * spacing * (1 + 1e-9)) & (freqs > 0.0)
    local = coherence[band]
    peak_index = int(np.flatnonzero(band)[int(np.argmax(local))])
    level = chance_level(seg.segment_count)
    value = float(coherence[nearest])
    return {
        **base, **geometry, "status": STATUS_OK, "reason_code": None, "message": None,
        "coherence": value, "coherence_frequency_hz": float(freqs[nearest]), "target_offset_hz": float(freqs[nearest] - frequency_hz),
        "local_peak_coherence": float(coherence[peak_index]), "local_peak_frequency_hz": float(freqs[peak_index]),
        "local_peak_offset_hz": float(freqs[peak_index] - frequency_hz), "local_median_coherence": float(np.median(local)),
        "local_band_bins": int(local.size), "chance_level": level,
        "exceeds_chance_level": bool(level is not None and value > level),
        "local_peak_exceeds_chance_level": bool(level is not None and float(coherence[peak_index]) > level),
    }


# ---------------------------------------------------------------- component ----

def _longest(episodes: list[tuple[float, float]]) -> tuple[float, float] | None:
    return max(episodes, key=lambda iv: iv[1] - iv[0]) if episodes else None


def analyse_component(*, members: list[dict], reference_index: int, frequency_hz: float, phase_by_member: dict[int, float | None] | None = None) -> dict:
    """Coherence of the reference against every other member (``pairs``) and of every other pair (``other_pairs``).

    Each member dict: ``signal_index``, ``label``, ``origin``, ``recording``, ``signal_type``, ``unit``, ``time_group_id``, ``roots``,
    ``t`` (WORKSPACE time, s), ``x`` (samples), ``episodes`` (workspace-time activity intervals; the caller restricts them to the analysis
    window and the data). ``phase_by_member`` carries the Mode Shape relative phase (degrees) of members against the reference, where one exists."""
    phase_by_member = phase_by_member or {}
    by_index = {m["signal_index"]: m for m in members}
    reference = by_index[reference_index]
    cache: dict[tuple[int, float], np.ndarray] = {}
    origin = min(float(m["t"][0]) for m in members)

    def series(member: dict, rate: float) -> np.ndarray:
        key = (member["signal_index"], rate)
        if key not in cache:
            last = max(float(m["t"][-1]) for m in members)
            grid = origin + np.arange(int(math.floor((last - origin) * rate)) + 1) / rate
            cache[key] = to_grid(member["t"], member["x"], grid, rate)
        return cache[key]

    def pair(a: dict, b: dict) -> dict:
        kind = SAME_VARIABLE if (a["signal_type"], a["unit"]) == (b["signal_type"], b["unit"]) else CROSS_VARIABLE
        out = {"reference_signal": a["label"], "reference_index": a["signal_index"], "member_signal": b["label"], "member_index": b["signal_index"],
               "relationship_type": kind, "signal_types": [a["signal_type"], b["signal_type"]], "component_frequency_hz": frequency_hz,
               "relative_phase_deg": phase_by_member.get(b["signal_index"]) if a is reference else None, "common_interval": None, "cycles_used": None,
               "reason_values": {}, "coherence": None, "coherence_frequency_hz": None, "bin_spacing_hz": None, "local_peak_coherence": None,
               "local_peak_frequency_hz": None, "segment_count": None, "chance_level": None, "exceeds_chance_level": None,
               "reasons": [], "warnings": []}

        def done(status: str, code: str | None = None, message: str | None = None, **extra) -> dict:
            out.update(extra)
            out.update(status=status, reason_code=code, message=message)
            return out

        if a["time_group_id"] is None or a["time_group_id"] != b["time_group_id"]:
            return done(STATUS_UNAVAILABLE, "incompatible_time_basis", NO_TIME_BASIS_MESSAGE)
        common = intersect_episodes(a["episodes"], b["episodes"])
        window = _longest(common)
        if window is None:
            return done(STATUS_INSUFFICIENT, "no_common_activity", "The two signals are not active over a shared interval on the common time basis.")
        start, end = window
        if len(common) > 1:
            out["warnings"].append(_evidence(
                "intermittent_activity", f"The signals' shared activity splits into {len(common)} separate episodes; only the longest ({_fmt(end - start, 3)} s) is used "
                "and the episodes are not averaged together.", episodes=len(common)))
        rate = min(source_rate_hz(a["t"]), source_rate_hz(b["t"]), MAX_COMMON_RATE_HZ)
        sa, sb = series(a, rate), series(b, rate)
        i0 = max(0, int(math.ceil((start - origin) * rate - 1e-9)))
        i1 = min(sa.size, int(math.floor((end - origin) * rate + 1e-9)) + 1)
        result = analyse_pair(sa[i0:i1], sb[i0:i1], rate, frequency_hz)
        interval = {"start_s": start, "end_s": end, "duration_s": end - start, "time_basis": "workspace_time"}
        extra = {k: v for k, v in result.items() if k not in ("status", "reason_code", "message")}
        extra.update(common_interval=interval, cycles_used=(end - start) * frequency_hz)
        if result["status"] != STATUS_OK:
            return done(STATUS_INSUFFICIENT, result["reason_code"], result["message"], **extra)
        out.update(extra)
        label_a, label_b = a["label"], b["label"]
        out["reasons"] += [
            _evidence("same_component", f"{label_a} and {label_b} contain the same ~{_fmt(frequency_hz, 3)} Hz component.", frequency_hz=frequency_hz),
            _evidence("common_interval", f"Signals overlap from {_fmt(start, 5)} to {_fmt(end, 5)} s ({_fmt(end - start, 3)} s, {_fmt(extra['cycles_used'], 3)} cycles, workspace time).",
                      duration_s=end - start),
            _evidence("target_coherence", f"Coherence at {_fmt(result['coherence_frequency_hz'], 4)} Hz (the bin nearest {_fmt(frequency_hz, 4)} Hz) is {_fmt(result['coherence'], 3)}.",
                      coherence=result["coherence"]),
            _evidence("averaging", f"{result['segment_count']} Welch segments ({result['independent_segment_count']} independent) of {_fmt(result['segment_s'], 3)} s were averaged; "
                      f"bin spacing {_fmt(result['bin_spacing_hz'], 3)} Hz.", segments=result["segment_count"]),
            _evidence("local_band", f"The local coherence peak is {_fmt(result['local_peak_coherence'], 3)} at {_fmt(result['local_peak_frequency_hz'], 4)} Hz "
                      f"(median {_fmt(result['local_median_coherence'], 3)} over {result['local_band_bins']} bins within ±{_fmt(LOCAL_BAND_BINS, 2)} bin).",
                      peak=result["local_peak_coherence"]),
        ]
        if result["chance_level"] is not None:
            out["reasons"].append(_evidence(
                "chance_level", f"Unrelated noise would reach a coherence of {_fmt(result['chance_level'], 3)} in {_fmt(CHANCE_ALPHA * 100, 2)} % of cases with this many averages "
                "(a 95% null threshold, not the probability that the oscillation is real); the measured value is "
                + ("above" if result["exceeds_chance_level"] else "not above") + " it.", chance_level=result["chance_level"]))
        if kind == CROSS_VARIABLE:
            out["warnings"].append(_evidence(
                "cross_variable", f"{label_a} ({a['signal_type']}) and {label_b} ({b['signal_type']}) are different physical quantities; their coherence is supporting "
                "dynamic evidence, not same-variable mode-shape evidence."))
        if set(a["roots"]) & set(b["roots"]):
            out["warnings"].append(_evidence(
                "shared_measurement_provenance", f"{label_a} and {label_b} share a source measurement; their coherence is not independent evidence."))
        phase = out["relative_phase_deg"]
        if phase is not None and not result["exceeds_chance_level"]:
            out["warnings"].append(_evidence(
                "phase_with_low_coherence", "Relative phase is available, but cross-spectral coherence at the component frequency is low (not above the 95% null threshold); "
                "interpret phase cautiously.", phase_deg=phase, coherence=result["coherence"]))
        return done(STATUS_OK)

    others = sorted((m for m in members if m["signal_index"] != reference_index), key=lambda m: m["signal_index"])
    pairs = [pair(reference, m) for m in others]
    other_pairs = [pair(a, b) for i, a in enumerate(others) for b in others[i + 1:]]
    limitations = [
        _evidence("no_causality", "Coherence measures linear association at a frequency; it does not identify causality or direction."),
        _evidence("not_inter_area_proof", "High coherence does not prove an inter-area mode."),
        _evidence("stationarity", "The Welch average and its 95% null threshold assume a stationary signal; a decaying ringdown is not stationary, so coherence is indicative."),
    ]
    if any(p["relationship_type"] == CROSS_VARIABLE for p in pairs + other_pairs):
        limitations.append(_evidence("cross_variable_scope", "Cross-variable coherence (for example MW with frequency) is supporting dynamic evidence and is not the same as same-variable mode-shape evidence."))
    return {"reference": {"signal_index": reference["signal_index"], "label": reference["label"]}, "pairs": pairs, "other_pairs": other_pairs, "limitations": limitations}
