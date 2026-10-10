"""Oscillation Analysis -- mode shape / relative phase evidence (DEC-180 [PROPOSAL], building on DEC-171..179).

Question answered: *how do the signals that share one cross-signal oscillation component (DEC-178) move relative to one
another in amplitude and phase?*  This is the evidence layer BEFORE any use in classification: nothing here says
inter-area / local / SSO / forced, there is no AI, no probability and no confidence score. DEC-179 is not touched.

**Estimator (sinusoidal least-squares projection).** Over one common physical interval and at one common frequency ``f``
each member is fitted by ordinary least squares with

    x(t) = e^(-alpha tau) [a cos(w tau) + b sin(w tau)] + c0 + c1 (tau - D/2) / D,      w = 2 pi f,  tau = t - t_start

so the constant and a linear trend are removed identically for every member (no filter, hence no filter-induced relative
phase shift). Writing the oscillation as ``A cos(w tau + phi)``:

    A = sqrt(a^2 + b^2),        phi = atan2(-b, a)

**Ringdown.** A decaying (or growing) component is not a constant-amplitude sinusoid; fitting one biases the phase and
participation toward whichever cycles are largest. The model therefore carries a single exponential envelope rate ``alpha``
per member (found by a one-dimensional search, each trial being a linear least-squares problem; ``alpha`` never changes the
phase reference, only the amplitude shape). ``A`` is then the amplitude AT THE START OF THE COMMON INTERVAL, the same instant
for every member, so members with different damping are compared like for like. The rate used is reported.

**Phase convention.** ``tau`` is the shared WORKSPACE time (source time + the effective alignment offset of the signal's
Time Group), so every member is referred to the same instant. The reported phase of a member is
``wrap(phi_member - phi_reference)`` in ``[-180, +180)`` degrees: **positive = the member LEADS the reference** (its cosine
peaks earlier), negative = it lags, and the reference is exactly 0. The difference is always taken with circular
arithmetic (``wrap``), never ordinary subtraction.

**Common frequency.** One frequency for all members of a quantity group: the DEC-178 representative frequency, refined
jointly (a bounded search of +-one match tolerance maximising the sum of the members' normalised fitted power), because the
Welch grid is coarse relative to the phase resolution needed. Each member's own candidate frequency is kept; members are
never fitted at different frequencies and then compared.

**Common interval.** The intersection of the members' STFT activity (the DEC-178 activity rule, restricted to one contiguous
episode), each member's analysis window and its data range, on workspace time. If the intersection splits into separate
episodes only the longest one is used (bursts are never averaged together).

**Stability.** The common interval is split into equal sub-windows (each at least ``MIN_SUBWINDOW_CYCLES`` long); the
relative phase in each is estimated the same way; the circular mean, circular spread and largest deviation are reported.

Every threshold below is a Phase-1 engineering heuristic, not a standard. NumPy only (no SciPy).
"""

from __future__ import annotations

import math

import numpy as np

from app.domain import cross_signal_evidence as cs

# ---------------------------------------------------------------- Phase-1 heuristics
#: Fewest oscillation cycles the common interval must contain.
MIN_COMMON_CYCLES = 3.0
#: Fewest samples per oscillation cycle (a sinusoid is not resolved below this).
MIN_SAMPLES_PER_CYCLE = 4.0
#: Fewest samples in the fit.
MIN_FIT_SAMPLES = 24
#: Envelope search: ``|alpha| <= ENVELOPE_RANGE / interval`` (the envelope may change by at most e^ENVELOPE_RANGE over the interval),
#: on a coarse then a fine grid, with the search sub-sampled to at most FIT_SEARCH_MAX_SAMPLES samples.
ENVELOPE_RANGE = 8.0
ENVELOPE_COARSE_POINTS = 17
ENVELOPE_FINE_POINTS = 9
FIT_SEARCH_MAX_SAMPLES = 600
#: A search sub-samples a member by an integer stride but never below this many samples per oscillation cycle.
SEARCH_MIN_SAMPLES_PER_CYCLE = 8.0
#: Fitted-sinusoid power over residual power (2 = 3 dB). The residual holds noise, other modes and the unmodelled envelope.
MIN_FIT_POWER_RATIO = 2.0
#: Sub-windows used for the phase-stability check, each at least this many cycles long, and the fewest valid ones needed.
STABILITY_SUBWINDOWS = 4
MIN_SUBWINDOW_CYCLES = 1.5
MIN_VALID_SUBWINDOWS = 2
#: A relative phase is "stable" when no valid sub-window deviates from the circular mean by more than this.
STABLE_MAX_DEVIATION_DEG = 30.0
#: Descriptive bands (degrees): within this of 0 = approximately in phase; within this of 180 = approximately anti-phase.
IN_PHASE_BAND_DEG = 30.0
ANTI_PHASE_BAND_DEG = 30.0
#: Joint frequency refinement: +-RANGE x match tolerance, coarse then fine grid, at most this many samples per member.
FREQUENCY_SEARCH_RANGE_FACTOR = 1.0
FREQUENCY_COARSE_POINTS = 13
FREQUENCY_FINE_POINTS = 9
FREQUENCY_SEARCH_MAX_SAMPLES = 600
#: A neighbouring component closer than this multiple of the projection resolution (1 / interval) contaminates the fit.
NEIGHBOUR_RESOLUTION_FACTOR = 1.0
#: Slices are active at this fraction of the track maximum (the DEC-178 rule, imported so the two cannot drift).
ACTIVE_TRACK_FRACTION = cs.ACTIVE_TRACK_FRACTION
#: The time-resolved restriction of an STFT episode keeps samples whose one-cycle envelope is at least this fraction of the episode
#: maximum -- the same -10 dB (power) rule expressed as an amplitude -- and trims this many periods inward at interior edges.
ENVELOPE_ACTIVE_AMPLITUDE_FRACTION = math.sqrt(cs.ACTIVE_TRACK_FRACTION)
EDGE_TRIM_PERIODS = 0.5

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_UNAVAILABLE = "unavailable"

PATTERN_IN_PHASE = "in_phase"
PATTERN_ANTI_PHASE = "anti_phase"
PATTERN_INTERMEDIATE = "intermediate"
PATTERN_MIXED = "mixed"
PATTERN_UNSTABLE = "unstable"
PATTERN_UNAVAILABLE = "unavailable"
PATTERN_LABELS = {
    PATTERN_IN_PHASE: "Approximately in phase",
    PATTERN_ANTI_PHASE: "Approximately anti-phase",
    PATTERN_INTERMEDIATE: "Intermediate phase separation",
    PATTERN_MIXED: "Mixed phase relationships",
    PATTERN_UNSTABLE: "Phase relationship not stable across the interval",
    PATTERN_UNAVAILABLE: "Phase evidence unavailable",
}

NO_TIME_BASIS_MESSAGE = "phase comparison unavailable — recordings do not share a compatible aligned time basis"


def parameters() -> dict:
    return {
        "estimator": "sinusoidal least-squares projection: exp(-alpha t) (a cos(wt) + b sin(wt)) + offset + linear trend, one common frequency and interval; "
                     "amplitude is referred to the start of the common interval",
        "phase_convention": "relative phase = wrap(phi_member - phi_reference) in [-180, +180) degrees; positive = the member leads the reference",
        "time_basis": "workspace time (source time + effective alignment offset of the signal's Time Group)",
        "reference_rule": "within each comparable quantity group, the valid member with the highest candidate prominence is 0 degrees",
        "amplitude_normalisation": "relative amplitude = A / max(A) within the comparable quantity group only",
        "grouping": "members are compared only within the same engineering type and unit; different quantities are never merged",
        "min_common_cycles": MIN_COMMON_CYCLES, "min_samples_per_cycle": MIN_SAMPLES_PER_CYCLE, "min_fit_samples": MIN_FIT_SAMPLES,
        "min_fit_power_ratio": MIN_FIT_POWER_RATIO, "stability_subwindows": STABILITY_SUBWINDOWS,
        "min_subwindow_cycles": MIN_SUBWINDOW_CYCLES, "stable_max_deviation_deg": STABLE_MAX_DEVIATION_DEG,
        "in_phase_band_deg": IN_PHASE_BAND_DEG, "anti_phase_band_deg": ANTI_PHASE_BAND_DEG,
        "active_track_fraction": ACTIVE_TRACK_FRACTION,
        "heuristics": "Phase-1 engineering heuristics, not standards; relative phase is evidence only and no oscillation type is inferred",
    }


# ------------------------------------------------------------------ helpers ----

def wrap_deg(angle_deg):
    """Canonical wrapping into ``[-180, +180)`` (works on scalars and arrays)."""
    return (np.asarray(angle_deg, dtype=float) + 180.0) % 360.0 - 180.0


def circular_difference_deg(a_deg: float, b_deg: float) -> float:
    """``a - b`` wrapped into ``[-180, +180)`` -- the only way two phases are subtracted."""
    return float(wrap_deg(a_deg - b_deg))


def circular_stats(angles_deg) -> dict:
    """Circular mean, circular standard deviation (``sqrt(-2 ln R)``) and largest deviation from the mean, in degrees."""
    a = np.deg2rad(np.asarray(angles_deg, dtype=float))
    z = np.exp(1j * a).mean()
    r = float(abs(z))
    mean = float(np.rad2deg(np.angle(z))) if r > 1e-12 else float("nan")
    spread = float(np.rad2deg(math.sqrt(-2.0 * math.log(r)))) if 0.0 < r < 1.0 else (0.0 if r >= 1.0 else float("inf"))
    deviation = float(np.max(np.abs(wrap_deg(np.rad2deg(a) - mean)))) if r > 1e-12 else float("inf")
    return {"mean_deg": float(wrap_deg(mean)) if r > 1e-12 else None, "spread_deg": spread, "max_deviation_deg": deviation, "resultant_length": r}


def _evidence(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


def design(tau: np.ndarray, f_hz: float, span_s: float, alpha: float = 0.0) -> np.ndarray:
    w = 2.0 * math.pi * f_hz
    envelope = np.exp(-alpha * tau) if alpha else 1.0
    return np.column_stack([envelope * np.cos(w * tau), envelope * np.sin(w * tau), np.ones_like(tau), (tau - span_s / 2.0) / span_s])


def _solve(tau: np.ndarray, y: np.ndarray, f_hz: float, span_s: float, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = design(tau, f_hz, span_s, alpha)
    try:                                                    # 4 x 4 normal equations: same solution, far cheaper than a full lstsq
        coef = np.linalg.solve(m.T @ m, m.T @ y)
    except np.linalg.LinAlgError:
        coef, *_ = np.linalg.lstsq(m, y, rcond=None)
    return coef, m, y - m @ coef


def _search_stride(t: np.ndarray, f_hz: float, cap: int) -> int:
    """Integer sub-sampling stride for a parameter SEARCH: at most ``cap`` samples, at least ``SEARCH_MIN_SAMPLES_PER_CYCLE`` per cycle."""
    n = t.size
    if n < 2 or not t[-1] > t[0]:
        return 1
    rate = (n - 1) / float(t[-1] - t[0])
    return max(1, min(n // cap, int(rate / (SEARCH_MIN_SAMPLES_PER_CYCLE * f_hz))))


def fit_sinusoid(t: np.ndarray, x: np.ndarray, f_hz: float, t_start: float, span_s: float, alpha: float | None = 0.0) -> dict:
    """Least-squares projection of ``x(t)`` onto the common-frequency model; ``phase_rad`` refers to ``tau = t - t_start`` and
    ``amplitude`` to ``tau = 0``. ``alpha`` is the envelope rate (1/s, positive = decaying): a number fixes it, ``None`` searches it."""
    tau = np.asarray(t, dtype=float) - t_start
    y = np.asarray(x, dtype=float)
    if alpha is None:
        stride = _search_stride(tau, f_hz, FIT_SEARCH_MAX_SAMPLES)
        ts, ys = tau[::stride], y[::stride]
        limit = ENVELOPE_RANGE / span_s

        def best(grid: np.ndarray) -> float:
            cost = [float(np.sum(_solve(ts, ys, f_hz, span_s, a)[2] ** 2)) for a in grid]
            return float(grid[int(np.argmin(cost))])

        coarse = np.linspace(-limit, limit, ENVELOPE_COARSE_POINTS)
        centre = best(coarse)
        step = float(coarse[1] - coarse[0])
        alpha = best(np.linspace(centre - step, centre + step, ENVELOPE_FINE_POINTS))
    coef, m, resid = _solve(tau, y, f_hz, span_s, alpha)
    n = y.size
    a, b = float(coef[0]), float(coef[1])
    amplitude = math.hypot(a, b)
    resid_var = float(np.sum(resid ** 2) / max(n - 4, 1))
    oscillation = m[:, :2] @ coef[:2]
    signal_power = float(np.mean(oscillation ** 2))
    ratio = (signal_power / resid_var) if resid_var > 0.0 else float("inf")
    sigma_phase = (math.sqrt(resid_var) / (math.sqrt(signal_power) * math.sqrt(n))) if signal_power > 0.0 and n > 0 else float("inf")
    return {
        "amplitude": amplitude, "phase_rad": math.atan2(-b, a), "n": int(n), "residual_rms": math.sqrt(resid_var),
        "power_ratio": ratio, "phase_sigma_deg": math.degrees(sigma_phase), "envelope_rate_per_s": float(alpha),
    }


def refine_frequency(series: list[tuple[np.ndarray, np.ndarray]], f_center: float, half_range_hz: float, t_start: float, span_s: float) -> dict:
    """Common frequency maximising the sum of the members' normalised fitted power over ``f_center +- half_range_hz``
    (coarse grid, then a fine grid around the best coarse point). The members are sub-sampled for the search only."""
    prepared = []
    for t, x in series:
        stride = _search_stride(t, f_center, FREQUENCY_SEARCH_MAX_SAMPLES)
        prepared.append((t[::stride], x[::stride]))
    lo, hi = max(f_center - half_range_hz, 1e-6), f_center + half_range_hz

    def best_of(grid: np.ndarray) -> tuple[float, int]:
        power = np.array([[fit_sinusoid(t, x, f, t_start, span_s)["amplitude"] ** 2 for f in grid] for t, x in prepared])
        peak = power.max(axis=1, keepdims=True)
        peak[peak <= 0.0] = 1.0
        score = (power / peak).sum(axis=0)
        return float(grid[int(np.argmax(score))]), int(np.argmax(score))

    coarse = np.linspace(lo, hi, FREQUENCY_COARSE_POINTS)
    f_coarse, index = best_of(coarse)
    step = float(coarse[1] - coarse[0])
    fine = np.linspace(max(f_coarse - step, 1e-6), f_coarse + step, FREQUENCY_FINE_POINTS)
    f_best, _ = best_of(fine)
    at_edge = index in (0, FREQUENCY_COARSE_POINTS - 1)
    return {"frequency_hz": f_best, "search_low_hz": lo, "search_high_hz": hi, "at_search_edge": bool(at_edge)}


# ------------------------------------------------------------------ time -----

def track_activity(times_s, frequencies_hz, psd, frequency_hz: float) -> dict | None:
    """Per-slice activity of one candidate's STFT track (the DEC-178 rule: at least ``ACTIVE_TRACK_FRACTION`` of the track maximum)."""
    times = np.asarray(times_s, dtype=float)
    freqs = np.asarray(frequencies_hz, dtype=float)
    matrix = np.asarray(psd, dtype=float)
    if times.size == 0 or freqs.size == 0 or matrix.size == 0:
        return None
    spacing = float(freqs[1] - freqs[0]) if freqs.size > 1 else float("inf")
    near = np.abs(freqs - frequency_hz) <= 1.01 * spacing
    if not np.any(near):
        return None
    track = matrix[near, :].max(axis=0)
    peak = float(track.max())
    if not peak > 0.0:
        return None
    hop = float(np.median(np.diff(times))) if times.size > 1 else 0.0
    return {"times_s": times, "active": track >= ACTIVE_TRACK_FRACTION * peak, "hop_s": hop}


def activity_episodes(activity: dict, offset_s: float) -> list[tuple[float, float]]:
    """Contiguous runs of active slices as workspace-time intervals (slice centres padded by half a hop)."""
    times, active, half = activity["times_s"], activity["active"], activity["hop_s"] / 2.0
    runs: list[tuple[float, float]] = []
    start = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        if start is not None and (not on or i == len(active) - 1):
            last = i if on else i - 1
            runs.append((float(times[start] - half + offset_s), float(times[last] + half + offset_s)))
            start = None
    return runs


def refine_episode(t: np.ndarray, x: np.ndarray, f_hz: float, episode: tuple[float, float]) -> list[tuple[float, float]]:
    """Restrict one STFT episode to where the component is actually active. The STFT windows are long at low frequency (tens of
    seconds), so its active span reaches well before an onset; fitting there would fit noise. The envelope is the one-cycle moving
    average of the complex demodulation ``x e^(-i w t)`` (a boxcar with a null at ``f``, so a baseline or step is rejected);
    contiguous runs at or above ``ENVELOPE_ACTIVE_AMPLITUDE_FRACTION`` of the episode maximum are kept, trimmed ``EDGE_TRIM_PERIODS``
    periods inward wherever the run edge is interior to the episode. Several runs mean an intermittent component."""
    start, end = episode
    n = t.size
    if n < 8 or not end > start:
        return []
    fs = (n - 1) / float(t[-1] - t[0])
    h = max(4, int(round(fs / f_hz))) // 2
    z = x * np.exp(-2j * math.pi * f_hz * (t - t[0]))
    c = np.concatenate([[0.0 + 0.0j], np.cumsum(z)])
    idx = np.arange(n)
    lo, hi = np.clip(idx - h, 0, n), np.clip(idx + h + 1, 0, n)
    amplitude = 2.0 * np.abs((c[hi] - c[lo]) / (hi - lo))
    inside = (t >= start) & (t <= end)
    if not inside.any():
        return []
    peak = float(amplitude[inside].max())
    if not peak > 0.0:
        return []
    active = inside & (amplitude >= ENVELOPE_ACTIVE_AMPLITUDE_FRACTION * peak)
    trim = EDGE_TRIM_PERIODS / f_hz
    runs, i = [], 0
    while i < n:
        if not active[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and active[j + 1]:
            j += 1
        a, b = float(t[i]), float(t[j])
        a = a if a <= start + 1.0 / fs else a + trim          # a run edge at the episode boundary is not trimmed
        b = b if b >= end - 1.0 / fs else b - trim
        if b > a:
            runs.append((max(a, start), min(b, end)))
        i = j + 1
    return runs


def intersect_episodes(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                out.append((s, e))
    return sorted(out)


# ------------------------------------------------------------------ pattern --

def band_of(phase_deg: float) -> str:
    magnitude = abs(float(phase_deg))
    if magnitude <= IN_PHASE_BAND_DEG:
        return PATTERN_IN_PHASE
    if 180.0 - magnitude <= ANTI_PHASE_BAND_DEG:
        return PATTERN_ANTI_PHASE
    return PATTERN_INTERMEDIATE


def _roots_components(members: list[dict]) -> list[int]:
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if set(members[i]["roots"]) & set(members[j]["roots"]):
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(members))]


def describe_pattern(reference: dict | None, valid: list[dict]) -> dict:
    """Descriptive pattern of the independent members against the reference. Never a classification."""
    if reference is None:
        return {"code": PATTERN_UNAVAILABLE, "label": PATTERN_LABELS[PATTERN_UNAVAILABLE], "member_bands": {}}
    others = [m for m in valid if m is not reference and not (set(m["roots"]) & set(reference["roots"]))]
    if not others:
        return {"code": PATTERN_UNAVAILABLE, "label": PATTERN_LABELS[PATTERN_UNAVAILABLE], "member_bands": {},
                "reason": "no member is an independent measurement from the reference"}
    if any(m["stability"] and m["stability"]["status"] == "unstable" for m in others):
        return {"code": PATTERN_UNSTABLE, "label": PATTERN_LABELS[PATTERN_UNSTABLE], "member_bands": {}}
    bands = {m["signal_index"]: band_of(m["phase_deg"]) for m in others}
    kinds = set(bands.values())
    code = kinds.pop() if len(kinds) == 1 else PATTERN_MIXED
    return {"code": code, "label": PATTERN_LABELS[code], "member_bands": bands}


# ------------------------------------------------------------------ group ----

def _member_out(m: dict) -> dict:
    keys = ("signal_index", "label", "recording", "origin", "signal_type", "unit", "time_group_id", "candidate_frequency_hz",
            "prominence_db", "status", "reason_code", "message", "amplitude", "relative_amplitude", "phase_deg",
            "phase_uncertainty_deg", "fit_power_ratio", "envelope_rate_per_s", "samples_used", "is_reference", "phase_stability", "reasons", "warnings")
    return {k: m.get(k) for k in keys}


def _blank_member(raw: dict) -> dict:
    return {**raw, "status": STATUS_OK, "reason_code": None, "message": None, "amplitude": None, "relative_amplitude": None,
            "phase_deg": None, "phase_uncertainty_deg": None, "fit_power_ratio": None, "envelope_rate_per_s": None, "samples_used": None, "is_reference": False,
            "phase_stability": None, "reasons": [], "warnings": list(raw.get("warnings", [])), "stability": None}


def unavailable_group(quantity_type: str, unit: str | None, raw_members: list[dict], *, code: str, message: str, comparable: bool = True) -> dict:
    """A group whose phases cannot be given (incompatible time basis, unknown quantity, ...): no number is produced."""
    members = []
    for raw in raw_members:
        m = _blank_member(raw)
        m.update(status=STATUS_UNAVAILABLE, reason_code=code, message=message)
        members.append(_member_out(m))
    return {
        "quantity_type": quantity_type, "unit": unit, "comparable": comparable, "status": STATUS_UNAVAILABLE, "reason_code": code,
        "message": message, "projection_frequency_hz": None, "frequency_refinement": None, "common_interval": None, "cycles_used": None,
        "reference": None, "distinct_measurement_count": len(set(_roots_components(raw_members))) if raw_members else 0,
        "members": members, "phase_pattern": {"code": PATTERN_UNAVAILABLE, "label": PATTERN_LABELS[PATTERN_UNAVAILABLE], "member_bands": {}},
        "reasons": [], "limitations": [_evidence(code, message)],
    }


def analyse_quantity_group(
    *,
    quantity_type: str,
    unit: str | None,
    members: list[dict],
    representative_frequency_hz: float,
    tolerance_hz: float,
    neighbour_frequencies_hz: list[float],
    excluded_members: list[dict] | None = None,
) -> dict:
    """Mode shape of ONE comparable quantity group on one time basis.

    Each member dict: `signal_index`, `label`, `recording`, `origin`, `signal_type`, `unit`, `time_group_id`, `roots`,
    `candidate_frequency_hz`, `prominence_db`, `t` (WORKSPACE time, s), `x` (samples), `episodes` (workspace-time intervals the
    member is active in, already clipped to its analysis window and data), optional `warnings`.
    `excluded_members` are in this quantity group but on another time basis (reported unavailable)."""
    f_rep = representative_frequency_hz
    reasons: list[dict] = []
    limitations: list[dict] = []
    ms = [_blank_member(m) for m in members]
    unavailable_tail = []
    for raw in excluded_members or []:
        m = _blank_member(raw)
        code, text = raw.get("reason_code", "incompatible_time_basis"), raw.get("message", NO_TIME_BASIS_MESSAGE)
        m.update(status=STATUS_UNAVAILABLE, reason_code=code, message=text)
        unavailable_tail.append(_member_out(m))
        limitations.append(_evidence(code, f"{raw['label']}: {text}" + ("" if text.endswith(".") else "."), signal=raw["label"]))

    def finish(status: str, code: str | None, message: str | None, **extra) -> dict:
        reference = next((m for m in ms if m["is_reference"]), None)
        valid = [m for m in ms if m["status"] == STATUS_OK and m["phase_deg"] is not None]
        group = {
            "quantity_type": quantity_type, "unit": unit, "comparable": True, "status": status, "reason_code": code, "message": message,
            "projection_frequency_hz": extra.get("projection_frequency_hz"), "frequency_refinement": extra.get("frequency_refinement"),
            "common_interval": extra.get("common_interval"), "cycles_used": extra.get("cycles_used"),
            "reference": {"signal_index": reference["signal_index"], "label": reference["label"]} if reference else None,
            "distinct_measurement_count": len(set(_roots_components(ms))) if ms else 0,
            "members": [_member_out(m) for m in ms] + unavailable_tail,
            "phase_pattern": describe_pattern(reference, valid) if status == STATUS_OK else
            {"code": PATTERN_UNAVAILABLE, "label": PATTERN_LABELS[PATTERN_UNAVAILABLE], "member_bands": {}},
            "reasons": reasons, "limitations": limitations,
        }
        limitations.append(_evidence(
            "station_metadata_not_area_evidence",
            "Recording and station names do not establish that the signals represent different grid areas."))
        limitations.append(_evidence(
            "phase_alone_not_confirmation", "Relative phase alone does not confirm an inter-area mode; it is evidence for a later interpretation."))
        return group

    def fail(code: str, message: str, **extra) -> dict:
        limitations.append(_evidence(code, message))
        for m in ms:
            if m["status"] == STATUS_OK:
                m.update(status=STATUS_INSUFFICIENT, reason_code=code, message=message)
        return finish(STATUS_INSUFFICIENT, code, message, **extra)

    if len(ms) < 2:
        return fail("needs_two_comparable_signals", f"At least two {quantity_type} signals on one aligned time basis are needed for a relative phase.")

    # --- common interval ---------------------------------------------------------------------------------------------
    common = ms[0]["episodes"]
    for m in ms[1:]:
        common = intersect_episodes(common, m["episodes"])
    if not common:
        return fail("no_common_activity", "The members are not active over a shared interval on the common time basis.")
    start, end = max(common, key=lambda iv: iv[1] - iv[0])
    duration = end - start
    if len(common) > 1:
        limitations.append(_evidence(
            "intermittent_activity",
            f"The members' shared activity splits into {len(common)} separate episodes; only the longest ({_fmt(duration, 3)} s) is used and the "
            "episodes are not averaged together.", episodes=len(common)))
    cycles = duration * f_rep
    interval = {"start_s": start, "end_s": end, "duration_s": duration, "time_basis": "workspace_time"}
    if cycles < MIN_COMMON_CYCLES:
        return fail("too_few_cycles", f"The common interval ({_fmt(duration, 3)} s) holds {_fmt(cycles, 3)} cycles at {_fmt(f_rep, 4)} Hz; "
                    f"at least {_fmt(MIN_COMMON_CYCLES, 3)} are needed.", common_interval=interval, cycles_used=cycles)

    # --- samples ------------------------------------------------------------------------------------------------------
    for m in ms:
        sel = (m["t"] >= start) & (m["t"] <= end)
        m["ts"], m["xs"] = m["t"][sel], m["x"][sel]
        m["samples_used"] = int(m["ts"].size)
        rate = (m["ts"].size - 1) / duration if m["ts"].size > 1 and duration > 0 else 0.0
        if m["ts"].size < MIN_FIT_SAMPLES:
            m.update(status=STATUS_INSUFFICIENT, reason_code="too_few_samples",
                     message=f"{m['ts'].size} samples in the common interval; at least {MIN_FIT_SAMPLES} are needed.")
        elif rate < MIN_SAMPLES_PER_CYCLE * f_rep:
            m.update(status=STATUS_INSUFFICIENT, reason_code="sampling_too_coarse",
                     message=f"{_fmt(rate, 3)} samples/s resolves fewer than {_fmt(MIN_SAMPLES_PER_CYCLE, 3)} samples per cycle at {_fmt(f_rep, 4)} Hz.")
    live = [m for m in ms if m["status"] == STATUS_OK]
    if len(live) < 2:
        return fail("insufficient_samples", "Fewer than two members have enough samples in the common interval.",
                    common_interval=interval, cycles_used=cycles)

    # --- common frequency ---------------------------------------------------------------------------------------------
    refinement = refine_frequency([(m["ts"], m["xs"]) for m in live], f_rep, FREQUENCY_SEARCH_RANGE_FACTOR * tolerance_hz, start, duration)
    f_use = refinement["frequency_hz"]
    cands = [m["candidate_frequency_hz"] for m in ms]
    refinement = {**refinement, "representative_frequency_hz": f_rep, "member_frequency_spread_hz": max(cands) - min(cands),
                  "member_candidate_frequencies_hz": cands}
    if refinement["at_search_edge"]:
        limitations.append(_evidence(
            "frequency_at_search_edge", "The refined common frequency lies at the edge of its search range; the true frequency may differ from the grouped candidates."))
    cycles = duration * f_use
    reasons.append(_evidence(
        "common_frequency", f"All members are projected at one common frequency of {_fmt(f_use, 5)} Hz (representative {_fmt(f_rep, 5)} Hz; "
        f"member candidates {', '.join(_fmt(c, 4) for c in cands)} Hz).", frequency_hz=f_use))
    resolution = 1.0 / duration
    for other in neighbour_frequencies_hz:
        if abs(other - f_use) < NEIGHBOUR_RESOLUTION_FACTOR * resolution:
            limitations.append(_evidence(
                "neighbouring_component",
                f"Another component at {_fmt(other, 4)} Hz lies within the {_fmt(resolution, 3)} Hz projection resolution of this interval and may bias the phase.",
                other_frequency_hz=other))

    # --- fits ----------------------------------------------------------------------------------------------------------
    for m in live:
        fit = fit_sinusoid(m["ts"], m["xs"], f_use, start, duration, alpha=None)
        m["fit"] = fit
        m["amplitude"], m["phase_abs_rad"] = fit["amplitude"], fit["phase_rad"]
        m["fit_power_ratio"], m["phase_uncertainty_deg"] = fit["power_ratio"], fit["phase_sigma_deg"]
        m["envelope_rate_per_s"] = fit["envelope_rate_per_s"]
        if fit["power_ratio"] < MIN_FIT_POWER_RATIO:
            m.update(status=STATUS_INSUFFICIENT, reason_code="weak_component",
                     message=f"The fitted oscillation is only {_fmt(fit['power_ratio'], 3)}× the residual power (needs {_fmt(MIN_FIT_POWER_RATIO, 3)}×).",
                     phase_uncertainty_deg=None)
    valid = [m for m in live if m["status"] == STATUS_OK]
    common_blocks = dict(projection_frequency_hz=f_use, frequency_refinement=refinement, common_interval=interval, cycles_used=cycles)
    if len(valid) < 2:
        return fail("insufficient_valid_members", "Fewer than two members show the component clearly enough in the common interval.", **common_blocks)

    # --- reference, relative amplitude, relative phase -----------------------------------------------------------------
    reference = sorted(valid, key=lambda m: (-m["prominence_db"], m["origin"] != "raw", m["signal_index"]))[0]
    reference["is_reference"] = True
    top = max(m["amplitude"] for m in valid)
    for m in valid:
        m["relative_amplitude"] = m["amplitude"] / top if top > 0 else None
        m["phase_deg"] = 0.0 if m is reference else circular_difference_deg(math.degrees(m["phase_abs_rad"]), math.degrees(reference["phase_abs_rad"]))
    reasons.append(_evidence(
        "reference_signal", f"{reference['label']} is the phase reference (0°): the valid member with the highest candidate prominence "
        f"({_fmt(reference['prominence_db'], 3)} dB).", reference=reference["label"]))
    reasons.append(_evidence(
        "common_interval", f"Phase was estimated over one common interval of {_fmt(duration, 3)} s ({_fmt(cycles, 3)} cycles, workspace time "
        f"{_fmt(start, 5)} to {_fmt(end, 5)} s).", duration_s=duration, cycles=cycles))

    # --- stability ----------------------------------------------------------------------------------------------------
    k = int(min(STABILITY_SUBWINDOWS, math.floor(cycles / MIN_SUBWINDOW_CYCLES)))
    edges = np.linspace(start, end, k + 1) if k >= 1 else np.array([start, end])

    def sub_fits(member: dict) -> list[dict | None]:
        out = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (member["ts"] >= lo) & (member["ts"] <= hi)
            ok = int(sel.sum()) >= MIN_FIT_SAMPLES // 2
            fit = fit_sinusoid(member["ts"][sel], member["xs"][sel], f_use, start, duration, alpha=member["fit"]["envelope_rate_per_s"]) if ok else None
            out.append(fit if fit is not None and fit["power_ratio"] >= MIN_FIT_POWER_RATIO else None)
        return out

    reference_sub = sub_fits(reference) if k >= MIN_VALID_SUBWINDOWS else []
    for m in valid:
        if m is reference:
            continue
        if k < MIN_VALID_SUBWINDOWS:
            m["stability"] = {"status": "unavailable", "valid_subwindows": 0, "subwindows": k,
                              "message": "The common interval is too short for a sub-window stability check."}
            m["warnings"].append(_evidence("stability_unavailable", m["stability"]["message"]))
            m["phase_stability"] = m["stability"]
            continue
        diffs = [circular_difference_deg(math.degrees(f_m["phase_rad"]), math.degrees(f_r["phase_rad"]))
                 for f_m, f_r in zip(sub_fits(m), reference_sub) if f_m is not None and f_r is not None]
        if len(diffs) < MIN_VALID_SUBWINDOWS:
            m["stability"] = {"status": "unavailable", "valid_subwindows": len(diffs), "subwindows": k,
                              "message": f"Only {len(diffs)} of {k} sub-windows show both signals clearly."}
            m["warnings"].append(_evidence("stability_unavailable", m["stability"]["message"]))
        else:
            stats = circular_stats(diffs)
            stable = stats["max_deviation_deg"] <= STABLE_MAX_DEVIATION_DEG
            m["stability"] = {"status": "stable" if stable else "unstable", "valid_subwindows": len(diffs), "subwindows": k,
                              "circular_mean_deg": stats["mean_deg"], "circular_spread_deg": stats["spread_deg"],
                              "max_deviation_deg": stats["max_deviation_deg"], "subwindow_phase_deg": diffs,
                              "message": (f"Phase separation stayed within ±{_fmt(stats['max_deviation_deg'], 2)}° of its circular mean across {len(diffs)} sub-windows."
                                          if stable else
                                          f"Phase separation varied by up to {_fmt(stats['max_deviation_deg'], 2)}° from its circular mean across {len(diffs)} sub-windows "
                                          f"(limit {_fmt(STABLE_MAX_DEVIATION_DEG, 3)}°).")}
            if not stable:
                m["warnings"].append(_evidence("phase_unstable", m["stability"]["message"], max_deviation_deg=stats["max_deviation_deg"]))
        m["phase_stability"] = m["stability"]

    # --- provenance ---------------------------------------------------------------------------------------------------
    comps = _roots_components(valid)
    for i, m in enumerate(valid):
        twins = [valid[j]["label"] for j in range(len(valid)) if j != i and comps[j] == comps[i]]
        if twins:
            m["warnings"].append(_evidence(
                "shared_measurement_provenance",
                f"{m['label']} shares its source measurement with {', '.join(twins)}; it is not independent spatial evidence.", shared_with=",".join(twins)))
    distinct = len(set(comps))
    if distinct < len(valid):
        limitations.append(_evidence(
            "shared_measurement_provenance",
            f"{len(valid)} signals are only {distinct} distinct source measurement{'s' if distinct != 1 else ''}; copies of one measurement are not "
            "counted as separate spatial participation.", members=len(valid), distinct_measurements=distinct))
    group = finish(STATUS_OK, None, None, **common_blocks)
    pattern = group["phase_pattern"]
    for m in valid:
        if m is reference:
            continue
        side = "leads" if m["phase_deg"] > 0 else "lags" if m["phase_deg"] < 0 else "coincides with"
        stability = m.get("stability")
        tail = f" {stability['message']}" if stability and stability.get("status") in ("stable", "unstable") else ""
        reasons.append(_evidence(
            "relative_phase", f"{m['label']} is {_fmt(m['phase_deg'], 4)}° from the reference ({side} it).{tail}",
            signal=m["label"], phase_deg=m["phase_deg"]))
    if pattern["code"] == PATTERN_UNAVAILABLE and pattern.get("reason"):
        limitations.append(_evidence("pattern_unavailable", f"No phase pattern is given: {pattern['reason']}."))
    return group
