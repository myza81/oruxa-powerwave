"""Oscillation Analysis -- deterministic candidate detection over a Welch PSD
(DEC-175 [PROPOSAL]).

Input: the band-limited `(frequency, PSD)` bins that `spectral_estimation`
already produced. Nothing here re-estimates a spectrum, reads samples, uses
statistics beyond the arithmetic below, or classifies an oscillation's type.
Every statement in a result is a measured condition of the supplied arrays.

**Algorithm** (`detect_candidates`)

0. *DC bin excluded.* A Welch segment's mean is removed, so the 0 Hz bin is zero by
   construction. It is not spectral evidence and, left in, would make the first
   non-zero bin look like a peak rising out of a dip.
1. *Plateau-aware local maxima.* Consecutive bins with exactly the same PSD
   are collapsed into one *run*. A run is a local maximum when both neighbouring
   runs are strictly lower. Its frequency is the midpoint of the run's first and
   last bin (a tie is one peak, never two); its PSD is the run's value. The
   first and last run have a neighbour on one side only: they are *band-edge*
   maxima, whose shape cannot be observed (see 5).
2. *Prominence* (topographic, as `scipy.signal.peak_prominences`, evaluated on
   `10 log10(PSD)`; SciPy is a development-test reference only). For a peak:
   walk left and right until a strictly higher bin or the end of the band; the
   *left base* and *right base* are the lowest PSD values in those two
   stretches; the *reference level* is the HIGHER of the two bases;
   `prominence_db = 10 log10(peak_psd / reference_psd)`. Using the higher base
   means a peak is only as prominent as the lowest pass that connects it to
   anything higher -- a ripple on the shoulder of a larger peak, or on a
   decaying skirt, gets the depth of its own dip, not the depth of the distant
   floor. PSD ratios are unit independent. Computed in O(N) (monotonic stacks).
3. *Observed cycles.* `cycles_observed = frequency_hz * analysis_window_duration`.
   The ENGINEERING GUIDELINE (not a standard) is `MIN_OBSERVED_CYCLES = 2`, the
   same figure as the setup page's `recommendedMinObservedCycles` and the
   Welch segment rule; it gives one low-frequency limit `f_cut = 2 / T`.
4. *Acceptance* (all must hold): a local maximum, not a band-edge maximum,
   `cycles_observed >= 2`, `prominence_db >= required_db` where
   `required_db = max(MIN_PROMINENCE_DB, NOISE_ALLOWANCE_SIGMAS * 4.343 / sqrt(K))`
   for K averaged Welch segments (the floor alone when K is unknown). The second
   term stops the large scatter of a lightly averaged PSD from passing noise
   ripple as a peak; it is reported with every result.
5. *Rejections are reported, not hidden.* A local maximum below `f_cut` is
   `insufficient_evidence` (`below_min_cycles`): the window does not contain
   enough cycles to establish it as oscillatory -- NOT a claim that it is a
   transient. A band-edge maximum outside the low-frequency region is
   `insufficient_evidence` (`band_edge`); a candidate within
   `BOUNDARY_GUARD_BINS` of the edge is kept with a `near_band_edge` warning.
   Low-prominence maxima are only counted.
6. *Ranking* is by prominence (descending), then PSD, then lower frequency --
   never by absolute PSD alone. The full accepted list is returned; callers
   decide how many to show.
7. *Low-frequency region.* Bins below `f_cut` are summarised (peak PSD there,
   its share of the band's total power, and whether it is the largest PSD in
   the whole band), so the UI can say that strong energy exists there without
   calling it an oscillation.

The numeric thresholds are Phase-1 engineering heuristics, named below, not
universal standards.

Zero framework dependencies (domain layer). NumPy only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.domain.oscillation_representation import rms_envelope_response, rms_half_power_frequency_hz

# ---------------------------------------------------------------- Phase-1 heuristics
#: Observation guideline: a component needs at least this many cycles in the
#: analysis window to be promoted. An application guideline, not a standard.
MIN_OBSERVED_CYCLES = 2.0
#: A peak must stand at least this far above its reference level (ratio of PSD,
#: dB). A Phase-1 heuristic chosen to keep noise-like ripple out of the result.
MIN_PROMINENCE_DB = 6.0
#: Averaging a Welch PSD over K segments leaves its log-level scatter at about
#: `4.343 / sqrt(K)` dB (K = 1 gives the periodogram's 5.6 dB). Pure noise
#: produces spurious peaks up to roughly 5-9 times that scatter (measured on
#: seeded white noise), so the required prominence is raised to this multiple
#: of the scatter when few segments were averaged. A Phase-1 heuristic.
NOISE_ALLOWANCE_SIGMAS = 8.0
_DB_PER_NEPER_10 = 10.0 / math.log(10.0)  # 4.343
#: Accepted peaks within this many bins of either band edge carry a warning.
BOUNDARY_GUARD_BINS = 2
#: Candidates shown by default (the complete accepted list is still returned).
MAX_REPORTED_CANDIDATES = 5
#: Insufficient-evidence entries shown by default.
MAX_REPORTED_NOT_PROMOTED = 3
#: Segment counts below this carry a `limited_averaging` warning.
MIN_AVERAGED_SEGMENTS = 4
#: A PSD below `max(PSD) * this` (-100 dB) is treated as this level. Recorded signals
#: cannot carry more dynamic range (16-bit data is ~96 dB), so anything beneath is
#: floating-point round-off in the transform, not spectrum: it must not yield peaks
#: (a numerically zero leakage floor ripples by many dB) or an infinite prominence.
PSD_RELATIVE_FLOOR = 1e-10
#: Float slack on the cycle comparison (a bin sitting exactly on 2/T passes).
_CYCLE_TOLERANCE = 1e-9

ASSESSMENT_CANDIDATE = "candidate"
ASSESSMENT_INSUFFICIENT = "insufficient_evidence"

STATUS_FOUND = "candidates_found"
STATUS_NONE = "no_candidate"


@dataclass(frozen=True, slots=True)
class Peak:
    """A local maximum of the PSD, before acceptance rules."""

    first_index: int
    last_index: int
    frequency_hz: float
    psd: float
    prominence_db: float
    base_psd: float
    left_base_hz: float | None
    right_base_hz: float | None
    band_edge: str | None  # "lower" | "upper" | None


@dataclass(slots=True)
class Detection:
    """Complete deterministic result (the wire shape is built from it)."""

    status: str
    candidates: list[dict] = field(default_factory=list)
    not_promoted: list[dict] = field(default_factory=list)
    no_candidate_reasons: list[dict] = field(default_factory=list)
    low_frequency: dict | None = None
    parameters: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


def _runs(psd: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start and end (inclusive) index of every maximal run of equal values."""
    change = np.flatnonzero(psd[1:] != psd[:-1]) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change - 1, [psd.size - 1]))
    return starts, ends


def _side_minima(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every position `i` of a sequence with no equal neighbours: the lowest
    value, and where, over `(j, i]` with `j` the nearest strictly higher
    element to the left (the whole prefix when there is none). O(N)."""
    seq = values.tolist()  # plain floats: the scan below is the hot loop
    n = len(seq)
    mins = [0.0] * n
    where = [0] * n
    stack_value: list[float] = []
    stack_min: list[float] = []
    stack_where: list[int] = []
    for i, v in enumerate(seq):
        seg_min, seg_at = v, i
        while stack_value and stack_value[-1] <= v:
            stack_value.pop()
            m = stack_min.pop()
            a = stack_where.pop()
            if m < seg_min:
                seg_min, seg_at = m, a
        stack_value.append(v)
        stack_min.append(seg_min)
        stack_where.append(seg_at)
        mins[i], where[i] = seg_min, seg_at
    return np.asarray(mins), np.asarray(where, dtype=np.intp)


def find_peaks(frequencies_hz: np.ndarray, psd: np.ndarray) -> list[Peak]:
    """All local maxima (including band-edge ones) with their prominence."""
    return _scan_peaks(frequencies_hz, psd, None)[0]


def _scan_peaks(frequencies_hz: np.ndarray, psd: np.ndarray, keep_min_db: float | None) -> tuple[list[Peak], int]:
    """`(peaks, total_local_maxima)`. With `keep_min_db`, only peaks at least that
    prominent (and every band-edge maximum) are materialised; the count is of all."""
    f = np.asarray(frequencies_hz, dtype=np.float64)
    p = np.asarray(psd, dtype=np.float64)
    if f.ndim != 1 or p.shape != f.shape:
        raise ValueError("Frequencies and PSD must be one-dimensional arrays of the same length.")
    if p.size < 2 or not (np.all(np.isfinite(f)) and np.all(np.isfinite(p))):
        return [], 0
    top = float(np.max(p))
    if not top > 0:
        return [], 0
    p = np.maximum(p, top * PSD_RELATIVE_FLOOR)
    starts, ends = _runs(p)
    level = p[starts]
    n = level.size
    if n < 2:
        return [], 0
    db = 10.0 * np.log10(level)

    rising = np.empty(n, dtype=bool)  # strictly higher than the previous run (True at the start)
    rising[0] = True
    rising[1:] = level[1:] > level[:-1]
    lower_next = np.empty(n, dtype=bool)
    lower_next[-1] = True
    lower_next[:-1] = level[:-1] > level[1:]
    is_peak = rising & lower_next
    # Prominence only depends on the alternating maxima/minima: scan those, not every bin.
    is_valley = np.empty(n, dtype=bool)
    is_valley[0] = level[0] < level[1]
    is_valley[-1] = level[-1] < level[-2]
    is_valley[1:-1] = (level[1:-1] < level[:-2]) & (level[1:-1] < level[2:])
    turning = np.flatnonzero(is_peak | is_valley)
    t_db = db[turning]
    left_min, left_at = _side_minima(t_db)
    rev_min, rev_at = _side_minima(t_db[::-1])
    right_min, right_at = rev_min[::-1], (turning.size - 1 - rev_at)[::-1]
    position = {int(r): k for k, r in enumerate(turning)}

    peak_runs = np.flatnonzero(is_peak)
    total = int(peak_runs.size)
    peaks: list[Peak] = []
    for r in peak_runs.tolist():
        k = position[r]
        edge = "lower" if r == 0 else "upper" if r == n - 1 else None
        if edge == "lower":
            base_db, base_run = float(right_min[k]), int(turning[right_at[k]])
            left_base, right_base = None, float(f[starts[base_run]])
        elif edge == "upper":  # only the observed side counts
            base_db, base_run = float(left_min[k]), int(turning[left_at[k]])
            left_base, right_base = float(f[starts[base_run]]), None
        else:
            base_db = max(float(left_min[k]), float(right_min[k]))
            left_base = float(f[starts[int(turning[left_at[k]])]])
            right_base = float(f[starts[int(turning[right_at[k]])]])
        prominence = float(db[r]) - base_db
        if keep_min_db is not None and edge is None and prominence < keep_min_db:
            continue
        peaks.append(Peak(
            first_index=int(starts[r]), last_index=int(ends[r]),
            frequency_hz=float(0.5 * (f[starts[r]] + f[ends[r]])), psd=float(level[r]),
            prominence_db=prominence, base_psd=float(10.0 ** (base_db / 10.0)),
            left_base_hz=left_base, right_base_hz=right_base, band_edge=edge,
        ))
    return peaks, total


def noise_allowance_db(segment_count: int | None) -> float:
    """Prominence that noise ripple alone is allowed to reach for `segment_count`
    averaged segments; 0 when the count is unknown."""
    if not segment_count or segment_count < 1:
        return 0.0
    return NOISE_ALLOWANCE_SIGMAS * _DB_PER_NEPER_10 / math.sqrt(segment_count)


def low_frequency_cutoff_hz(window_duration_s: float) -> float:
    """`f_cut = MIN_OBSERVED_CYCLES / T`: the lowest frequency with enough cycles."""
    return MIN_OBSERVED_CYCLES / window_duration_s


def _low_frequency_summary(f: np.ndarray, p: np.ndarray, cutoff_hz: float) -> dict | None:
    below = f < cutoff_hz * (1.0 - _CYCLE_TOLERANCE)
    if not np.any(below):
        return None
    total = float(np.sum(p))
    idx = int(np.argmax(np.where(below, p, -np.inf)))
    dominant = float(p[idx]) >= float(np.max(p))
    return {
        "cutoff_hz": cutoff_hz,
        "bin_count": int(np.count_nonzero(below)),
        "peak_frequency_hz": float(f[idx]),
        "peak_psd": float(p[idx]),
        "power_fraction": float(np.sum(p[below]) / total) if total > 0 else 0.0,
        "dominant": bool(dominant),
        "message": (
            f"Strong spectral energy exists below {_fmt(cutoff_hz)} Hz, the minimum frequency supported by the available "
            f"observation window ({_fmt(MIN_OBSERVED_CYCLES)} cycles in {_fmt(MIN_OBSERVED_CYCLES / cutoff_hz)} s). It is not "
            "automatically classified as an oscillation."
            if dominant else
            f"The spectrum has bins below {_fmt(cutoff_hz)} Hz, the minimum frequency supported by the available "
            f"observation window ({_fmt(MIN_OBSERVED_CYCLES)} cycles in {_fmt(MIN_OBSERVED_CYCLES / cutoff_hz)} s); "
            "components there are not promoted as oscillations."
        ),
    }


def _reasons(peak: Peak, cycles: float, cutoff_hz: float, edge_distance_bins: int, required_db: float,
             segment_count: int | None) -> list[dict]:
    plateau = peak.last_index - peak.first_index + 1
    reasons = [{
        "code": "local_peak",
        "message": (
            "Distinct local PSD peak" if plateau == 1
            else f"Distinct local PSD peak (a plateau of {plateau} equal bins; frequency is its centre)"
        ),
        "values": {"plateau_bins": plateau},
    }, {
        "code": "prominence",
        "message": f"{peak.prominence_db:.1f} dB above the surrounding spectral level (at least {required_db:.1f} dB required"
        + (f" for {segment_count} averaged segment(s))" if segment_count else ")"),
        "values": {"prominence_db": peak.prominence_db, "required_db": required_db, "base_psd": peak.base_psd},
    }, {
        "code": "cycles_observed",
        "message": f"{cycles:.1f} cycles observed in the selected window (guideline minimum {_fmt(MIN_OBSERVED_CYCLES)})",
        "values": {"cycles_observed": cycles, "minimum_cycles": MIN_OBSERVED_CYCLES},
    }, {
        "code": "outside_low_frequency_region",
        "message": f"Peak is above the low-frequency uncertainty limit of {_fmt(cutoff_hz)} Hz",
        "values": {"frequency_hz": peak.frequency_hz, "cutoff_hz": cutoff_hz},
    }]
    if edge_distance_bins > BOUNDARY_GUARD_BINS:
        reasons.append({
            "code": "away_from_band_edge",
            "message": f"Peak is {edge_distance_bins} bins from the nearest edge of the requested band",
            "values": {"edge_distance_bins": edge_distance_bins, "guard_bins": BOUNDARY_GUARD_BINS},
        })
    return reasons


def detect_candidates(
    frequencies_hz: np.ndarray,
    psd: np.ndarray,
    *,
    window_duration_s: float,
    segment_count: int | None = None,
    rms_nominal_frequency_hz: float | None = None,
    signal_variation_negligible: bool = False,
    min_prominence_db: float = MIN_PROMINENCE_DB,
) -> Detection:
    """Deterministic candidate detection over one Welch PSD (see module docstring)."""
    f = np.asarray(frequencies_hz, dtype=np.float64)
    p = np.asarray(psd, dtype=np.float64)
    if not (math.isfinite(window_duration_s) and window_duration_s > 0):
        raise ValueError("The analysis window duration must be positive.")
    # The DC bin is zero by construction (each Welch segment's mean is removed): it is not spectral
    # evidence and, left in, makes the first non-zero bin look like a peak rising out of a dip.
    has_dc = bool(f.size and f[0] <= 0.0)
    if has_dc:
        f, p = f[1:], p[1:]
    cutoff = low_frequency_cutoff_hz(window_duration_s)
    required_db = max(min_prominence_db, noise_allowance_db(segment_count))
    parameters = {
        "minimum_observed_cycles": MIN_OBSERVED_CYCLES,
        "minimum_prominence_db": min_prominence_db,
        "noise_allowance_db": noise_allowance_db(segment_count),
        "required_prominence_db": required_db,
        "low_frequency_cutoff_hz": cutoff,
        "boundary_guard_bins": BOUNDARY_GUARD_BINS,
        "window_duration_s": window_duration_s,
        "dc_bin_excluded": has_dc,
        "basis": "Phase-1 engineering heuristics (DEC-175 proposal); the cycle figure is an application guideline, not a standard.",
    }
    det = Detection(status=STATUS_NONE, parameters=parameters)

    if signal_variation_negligible or f.size < 3 or not np.any(p > 0):
        det.no_candidate_reasons.append({
            "code": "no_spectral_content",
            "message": "The signal shows no variation over the selected window, so its spectrum holds no component to assess."
            if signal_variation_negligible else
            "The returned band holds too few bins with spectral content to assess.",
            "values": {},
        })
        return det

    det.low_frequency = _low_frequency_summary(f, p, cutoff)
    peaks, total_maxima = _scan_peaks(f, p, required_db)
    n = f.size
    cycle_ok_from = cutoff * (1.0 - _CYCLE_TOLERANCE)

    accepted: list[tuple[Peak, float, int]] = []
    for peak in peaks:
        cycles = peak.frequency_hz * window_duration_s
        if peak.prominence_db < required_db:  # only a band-edge maximum can get here
            continue
        if peak.frequency_hz < cycle_ok_from:
            det.not_promoted.append(_not_promoted(
                peak, cycles, "below_min_cycles",
                f"{peak.frequency_hz:.4g} Hz is below {_fmt(cutoff)} Hz: only {cycles:.2f} cycles fit in the "
                f"{_fmt(window_duration_s)} s window (guideline minimum {_fmt(MIN_OBSERVED_CYCLES)}), so it cannot be "
                "established as oscillatory.",
                {"cutoff_hz": cutoff, "minimum_cycles": MIN_OBSERVED_CYCLES},
            ))
            continue
        if peak.band_edge:
            det.not_promoted.append(_not_promoted(
                peak, cycles, "band_edge",
                f"The spectral maximum at {peak.frequency_hz:.4g} Hz lies at the {peak.band_edge} edge of the analysed band; "
                "its full peak shape cannot be observed, so it is not promoted. Energy at and beyond the edge (trend, event "
                "response, slow recovery or a component outside the band) cannot be resolved here; widen the band to assess it.",
                {"band_edge": peak.band_edge},
            ))
            continue
        edge_distance = min(peak.first_index, n - 1 - peak.last_index)
        accepted.append((peak, cycles, edge_distance))

    ranked = sorted(accepted, key=lambda a: (-a[0].prominence_db, -a[0].psd, a[0].frequency_hz))
    for rank, (peak, cycles, edge_distance) in enumerate(ranked, start=1):
        warnings: list[dict] = []
        if edge_distance <= BOUNDARY_GUARD_BINS:
            warnings.append({
                "code": "near_band_edge",
                "message": f"Peak is only {edge_distance} bin(s) from an edge of the requested band; its surroundings are partly unobserved.",
                "values": {"edge_distance_bins": edge_distance},
            })
        if segment_count is not None and segment_count < MIN_AVERAGED_SEGMENTS:
            warnings.append({
                "code": "limited_averaging",
                "message": f"Only {segment_count} Welch segment(s) were averaged (fewer than {MIN_AVERAGED_SEGMENTS}); "
                "a PSD peak of this size is less certain.",
                "values": {"segment_count": segment_count},
            })
        if rms_nominal_frequency_hz:
            half_power = rms_half_power_frequency_hz(rms_nominal_frequency_hz)
            if peak.frequency_hz > half_power:
                loss = 100.0 * (1.0 - rms_envelope_response(peak.frequency_hz, rms_nominal_frequency_hz))
                warnings.append({
                    "code": "rms_representation_attenuation",
                    "message": f"This frequency is above the -3 dB frequency {_fmt(half_power)} Hz of the RMS magnitude "
                    f"representation; the amplitude of an oscillation here is attenuated by about {loss:.0f} %. The PSD is not corrected.",
                    "values": {"attenuation_percent": loss, "half_power_hz": half_power},
                })
        det.candidates.append({
            "rank": rank,
            "frequency_hz": peak.frequency_hz,
            "period_s": 1.0 / peak.frequency_hz if peak.frequency_hz > 0 else None,
            "psd": peak.psd,
            "prominence_db": peak.prominence_db,
            "cycles_observed": cycles,
            "base_psd": peak.base_psd,
            "left_base_hz": peak.left_base_hz,
            "right_base_hz": peak.right_base_hz,
            "assessment": ASSESSMENT_CANDIDATE,
            "reasons": _reasons(peak, cycles, cutoff, edge_distance, required_db, segment_count),
            "warnings": warnings,
        })

    det.not_promoted.sort(key=lambda e: (-e["prominence_db"], e["frequency_hz"]))
    det.counts = {
        "local_maxima": total_maxima, "accepted": len(det.candidates), "not_promoted": len(det.not_promoted),
        "below_prominence_threshold": total_maxima - len(peaks),
    }
    if det.candidates:
        det.status = STATUS_FOUND
        return det

    # ---- explain the absence of a candidate from measured facts only
    if f[-1] < cycle_ok_from:
        det.no_candidate_reasons.append({
            "code": "band_below_min_cycles",
            "message": f"The whole requested band lies below {_fmt(cutoff)} Hz; the {_fmt(window_duration_s)} s window holds "
            f"fewer than {_fmt(MIN_OBSERVED_CYCLES)} cycles of any frequency in it.",
            "values": {"cutoff_hz": cutoff},
        })
    if det.low_frequency and det.low_frequency["dominant"]:
        det.no_candidate_reasons.append({
            "code": "low_frequency_dominant",
            "message": det.low_frequency["message"],
            "values": {"cutoff_hz": cutoff},
        })
    if any(e["reason_code"] == "band_edge" for e in det.not_promoted):
        det.no_candidate_reasons.append({
            "code": "peak_at_band_edge",
            "message": "The largest remaining spectral maximum lies at an edge of the requested band.",
            "values": {},
        })
    if det.counts["below_prominence_threshold"] > 0 or not det.no_candidate_reasons:
        top = max((pk.prominence_db for pk in peaks if not pk.band_edge), default=None)
        det.no_candidate_reasons.append({
            "code": "no_prominent_peak",
            "message": (
                f"The spectrum contains no local peak at least {_fmt(required_db)} dB above its surroundings"
                + (f" (the most prominent is {top:.1f} dB)." if top is not None else " (it has no interior local maximum).")
            ),
            "values": {"required_db": required_db, "max_prominence_db": top},
        })
    return det


def _not_promoted(peak: Peak, cycles: float, code: str, message: str, values: dict) -> dict:
    return {
        "frequency_hz": peak.frequency_hz,
        "period_s": 1.0 / peak.frequency_hz if peak.frequency_hz > 0 else None,
        "psd": peak.psd,
        "prominence_db": peak.prominence_db,
        "cycles_observed": cycles,
        "assessment": ASSESSMENT_INSUFFICIENT,
        "reason_code": code,
        "reasons": [{"code": code, "message": message, "values": values}],
        "warnings": [],
    }
