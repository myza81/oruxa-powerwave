"""Oscillation Analysis -- cross-signal evidence (DEC-178 [APPROVED]).

Question answered: *is the same oscillatory component supported by more than one signal
and / or recording?*  A deterministic grouping of the accepted DEC-175 candidates of several
signals, with the per-signal evidence kept intact. This is the evidence layer BEFORE any
oscillation-type classification: nothing here says inter-area / local / SSO / forced, and
there is no AI, no confidence score and no probability.

**Matching rule.** Candidate frequencies are located on each signal's own Welch grid, so the
same physical component can differ by up to one bin of the coarser grid. Two candidates of
DIFFERENT signals match when
``|f_a - f_b| <= MATCH_RESOLUTION_FACTOR x max(bin_spacing_a, bin_spacing_b)`` (factor 1; a
frequency-independent number such as +-0.1 Hz is never used). A signal contributes at most one
candidate to a group.

**Grouping (greedy, order-independent of the input order).** Candidates are taken strongest
first (prominence, then lower frequency, then signal index). Each unassigned candidate seeds a
group; from every other signal the unassigned candidate nearest the seed that matches it joins.
Every member is therefore within one tolerance of the seed (and within two of any other member).

**Representative frequency.** The prominence-weighted mean (prominence in dB) of the members'
frequencies -- simple and transparent; every original frequency, the spread and the tolerance
stay in the result.

**Independence.** Observing a component in a raw channel and in a calculated channel derived from
it is NOT two measurements. Each signal carries its *lineage roots* (the raw source channels it is
ultimately computed from); members whose roots intersect are one measurement, and the result says
``Observed in N signals across M recordings`` plus the number of distinct measurements, never
"independently confirmed".

**Temporal evidence (optional).** Where an STFT track exists for a member, its *active interval* is
the span of slices whose power at the candidate frequency is at least ``ACTIVE_TRACK_FRACTION`` of
the track maximum. Intervals are compared on the WORKSPACE time basis (source time + the
alignment offset), never by column index, so different STFT resolutions and recordings compare
correctly. Grouping never requires it.

**Damping comparison (optional).** Behaviours (decaying / approximately sustained / growing) are
compared; for two decaying members the decay rates are compared by ratio. Differences only warn;
they never prevent grouping.

All tolerances here are Phase-1 engineering heuristics, not standards. NumPy only.
"""

from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------- Phase-1 heuristics
#: Candidates of two signals match within this multiple of the coarser Welch bin spacing.
MATCH_RESOLUTION_FACTOR = 1.0
_TOLERANCE_SLACK = 1e-9
#: A STFT slice is "active" when the candidate's track power is at least this fraction of the track maximum (-10 dB).
ACTIVE_TRACK_FRACTION = 0.1
#: Two decaying members differ "materially" when their decay rates differ by more than this ratio.
DECAY_RATE_RATIO_LIMIT = 2.0
#: Decay rates below this magnitude (1/s) are treated as zero in the ratio test.
DECAY_RATE_FLOOR = 1e-3

ORIGIN_RAW = "raw"
ORIGIN_CALCULATED = "calculated"


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}g}"


def _evidence(code: str, message: str, **values) -> dict:
    return {"code": code, "message": message, "values": values}


def match_tolerance_hz(bin_a: float, bin_b: float) -> float:
    """The documented matching tolerance for two signals' Welch grids."""
    return MATCH_RESOLUTION_FACTOR * max(bin_a, bin_b)


def frequencies_match(f_a: float, bin_a: float, f_b: float, bin_b: float) -> bool:
    tolerance = match_tolerance_hz(bin_a, bin_b)
    return abs(f_a - f_b) <= tolerance * (1.0 + _TOLERANCE_SLACK) + 1e-12


def active_interval(
    times_s: np.ndarray, frequencies_hz: np.ndarray, psd: np.ndarray, frequency_hz: float, window_s: float,
) -> dict:
    """The active interval of one candidate from an STFT matrix (`psd[row][column]`, linear PSD,
    columns stamped at slice centres in source time). The track is the maximum over the rows within
    one row spacing of the candidate frequency; the interval spans the first to the last active
    slice, each slice taken as its window `[t - window/2, t + window/2]`."""
    times = np.asarray(times_s, dtype=float)
    freqs = np.asarray(frequencies_hz, dtype=float)
    matrix = np.asarray(psd, dtype=float)
    if times.size == 0 or freqs.size == 0 or matrix.size == 0:
        return {"status": "unavailable"}
    spacing = float(freqs[1] - freqs[0]) if freqs.size > 1 else float("inf")
    near = np.abs(freqs - frequency_hz) <= 1.01 * spacing
    if not np.any(near):
        return {"status": "unavailable"}
    track = matrix[near, :].max(axis=0)
    peak = float(track.max())
    if not peak > 0.0:
        return {"status": "unavailable"}
    active = np.flatnonzero(track >= ACTIVE_TRACK_FRACTION * peak)
    first, last = int(active[0]), int(active[-1])
    return {
        "status": "ok",
        "start_s": float(times[first] - window_s / 2.0), "end_s": float(times[last] + window_s / 2.0),
        "active_slices": int(active.size), "slice_count": int(times.size),
        "active_fraction": float(active.size / times.size), "active_threshold": ACTIVE_TRACK_FRACTION,
    }


def _components_of_shared_roots(signals: list[dict], members: list[dict]) -> int:
    """Number of distinct measurements among the members: signals whose lineage roots intersect are one."""
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if set(signals[members[i]["signal_index"]]["lineage_roots"]) & set(signals[members[j]["signal_index"]]["lineage_roots"]):
                parent[find(i)] = find(j)
    return len({find(i) for i in range(len(members))})


def _member(signal: dict, candidate: dict) -> dict:
    damping = (signal.get("damping") or {}).get(candidate["rank"])
    temporal = (signal.get("temporal") or {}).get(candidate["rank"])
    return {
        "signal_index": signal["index"], "label": signal["label"], "rank": candidate["rank"],
        "frequency_hz": candidate["frequency_hz"], "prominence_db": candidate["prominence_db"],
        "cycles_observed": candidate["cycles_observed"], "bin_spacing_hz": signal["bin_spacing_hz"],
        "damping": damping, "temporal": temporal,
    }


def _damping_comparison(members: list[dict]) -> tuple[list[dict], list[dict], dict]:
    reasons, warnings = [], []
    available = [m for m in members if m["damping"] and m["damping"]["status"] == "available"]
    summary = {"available": len(available), "members": len(members)}
    if len(members) < 2:
        return reasons, warnings, summary
    if len(available) < 2:
        reasons.append(_evidence(
            "damping_not_compared",
            f"Damping was available for {len(available)} of {len(members)} members, so it is not compared.",
            available=len(available), members=len(members)))
        return reasons, warnings, summary
    behaviours = sorted({m["damping"]["behaviour"] for m in available})
    summary["behaviours"] = behaviours
    consistent = True
    if len(behaviours) > 1:
        consistent = False
        warnings.append(_evidence(
            "damping_behaviour_differs",
            "Damping behaviour differs between members: " + ", ".join(
                f"{m['label']} {m['damping']['behaviour'].replace('_', ' ')}" for m in available) + ".",
            behaviours=",".join(behaviours)))
    decaying = [m for m in available if m["damping"]["behaviour"] == "decaying"]
    if len(decaying) >= 2:
        rates = [m["damping"]["decay_rate_per_s"] for m in decaying]
        hi, lo = max(rates), max(min(rates), DECAY_RATE_FLOOR)
        ratio = hi / lo
        summary["decay_rate_ratio"] = ratio
        if ratio > DECAY_RATE_RATIO_LIMIT:
            consistent = False
            warnings.append(_evidence(
                "decay_rates_differ_materially",
                f"Decay rates differ by a factor of {_fmt(ratio, 3)} ({', '.join(f'{_fmt(r, 3)} s⁻¹' for r in rates)}; "
                f"heuristic limit {_fmt(DECAY_RATE_RATIO_LIMIT, 3)}).", ratio=ratio, limit=DECAY_RATE_RATIO_LIMIT))
    if consistent:
        reasons.append(_evidence(
            "damping_consistent",
            f"Damping behaviour is broadly compatible across {len(available)} members ({behaviours[0].replace('_', ' ')}).",
            members=len(available), behaviour=behaviours[0]))
    return reasons, warnings, summary


def _temporal_comparison(members: list[dict], signals: list[dict]) -> tuple[list[dict], list[dict], dict]:
    reasons, warnings = [], []
    if len(members) < 2:
        return reasons, warnings, {}
    intervals = []
    for m in members:
        t = m["temporal"]
        if t and t.get("status") == "ok":
            offset = signals[m["signal_index"]]["offset_s"]
            intervals.append((t["start_s"] + offset, t["end_s"] + offset, m))
    summary = {"members_with_evidence": len(intervals), "members": len(members)}
    if len(intervals) < len(members):
        warnings.append(_evidence(
            "limited_temporal_evidence",
            f"Time-frequency evidence exists for {len(intervals)} of {len(members)} members (the spectrogram was unavailable for the others).",
            with_evidence=len(intervals), members=len(members)))
    if len(intervals) < 2:
        return reasons, warnings, summary
    start, end = max(i[0] for i in intervals), min(i[1] for i in intervals)
    shortest = min(i[1] - i[0] for i in intervals)
    overlap = max(0.0, end - start)
    summary.update(overlap_s=overlap, overlap_start_workspace_s=start if overlap > 0 else None,
                   overlap_end_workspace_s=end if overlap > 0 else None,
                   overlap_fraction_of_shortest=(overlap / shortest) if shortest > 0 else 0.0)
    if overlap > 0:
        reasons.append(_evidence(
            "temporal_overlap",
            f"Activity overlaps in time for {_fmt(overlap, 3)} s ({overlap / shortest:.0%} of the shortest active interval), "
            "compared on the workspace time basis.", overlap_s=overlap, fraction_of_shortest=overlap / shortest))
    else:
        warnings.append(_evidence(
            "no_temporal_overlap", "The members' active intervals do not overlap in time (workspace time basis).",
            members=len(intervals)))
    return reasons, warnings, summary


def group_components(signals: list[dict]) -> list[dict]:
    """Group the accepted candidates of `signals` into cross-signal components.

    Each signal dict: `index`, `label`, `signal_type`, `recording`, `origin`, `lineage_roots`, `offset_s`,
    `bin_spacing_hz`, `candidates` (DEC-175 wire candidates), optional `damping` / `temporal` maps keyed by candidate rank.
    Signals that could not be analysed are simply absent from the grouping (the caller reports them)."""
    pool: list[tuple[dict, dict]] = [(s, c) for s in signals for c in s["candidates"]]
    pool.sort(key=lambda sc: (-sc[1]["prominence_db"], sc[1]["frequency_hz"], sc[0]["index"]))
    used: set[tuple[int, int]] = set()
    components: list[dict] = []
    for seed_signal, seed in pool:
        if (seed_signal["index"], seed["rank"]) in used:
            continue
        used.add((seed_signal["index"], seed["rank"]))
        members = [_member(seed_signal, seed)]
        for other in signals:
            if other["index"] == seed_signal["index"]:
                continue
            matches = [c for c in other["candidates"] if (other["index"], c["rank"]) not in used
                       and frequencies_match(seed["frequency_hz"], seed_signal["bin_spacing_hz"], c["frequency_hz"], other["bin_spacing_hz"])]
            if matches:
                best = min(matches, key=lambda c: (abs(c["frequency_hz"] - seed["frequency_hz"]), c["rank"]))
                used.add((other["index"], best["rank"]))
                members.append(_member(other, best))
        members.sort(key=lambda m: m["signal_index"])
        components.append(_build_component(members, signals))
    components.sort(key=lambda c: (-c["signal_count"], -c["max_prominence_db"], c["representative_frequency_hz"]))
    for number, component in enumerate(components, start=1):
        component["id"] = number
    return components


def _build_component(members: list[dict], signals: list[dict]) -> dict:
    freqs = [m["frequency_hz"] for m in members]
    weights = [max(m["prominence_db"], 1e-9) for m in members]
    representative = sum(f * w for f, w in zip(freqs, weights)) / sum(weights)
    spread = max(freqs) - min(freqs)
    meta = [signals[m["signal_index"]] for m in members]
    tolerance = max((match_tolerance_hz(a["bin_spacing_hz"], b["bin_spacing_hz"]) for a in meta for b in meta), default=0.0)
    types = sorted({s["signal_type"] for s in meta})
    recording_ids = {s["recording"] for s in meta}
    recordings = sorted({s.get("recording_label", s["recording"]) for s in meta})
    distinct = _components_of_shared_roots(signals, members)
    reasons: list[dict] = []
    warnings: list[dict] = []
    summary: dict = {}
    if len(members) == 1:
        reasons.append(_evidence(
            "single_signal_only",
            f"Observed in one signal only ({members[0]['label']}); no matching candidate was found in the other compared signals "
            "(this does not make it a false detection).", signal=members[0]["label"]))
    else:
        reasons.append(_evidence(
            "observed_in", f"Observed in {len(members)} signals across {len(recording_ids)} recording{'s' if len(recording_ids) != 1 else ''}"
            + (f" ({distinct} distinct measurement{'s' if distinct != 1 else ''})." if distinct != len(members) else "."),
            signals=len(members), recordings=len(recordings), distinct_measurements=distinct))
        reasons.append(_evidence(
            "frequency_match",
            f"Candidate frequencies agree within the Welch resolution: spread {_fmt(spread, 3)} Hz, tolerance {_fmt(tolerance, 3)} Hz "
            f"({_fmt(MATCH_RESOLUTION_FACTOR, 2)} × the coarser bin spacing).", spread_hz=spread, tolerance_hz=tolerance))
        if len(types) > 1:
            reasons.append(_evidence("multiple_signal_types", f"Detected in {len(types)} signal types: {', '.join(types)}.", types=",".join(types)))
        if len(recording_ids) > 1:
            reasons.append(_evidence("multiple_recordings", f"Detected in {len(recording_ids)} recordings.", recordings=len(recording_ids)))
        if distinct < len(members):
            warnings.append(_evidence(
                "derived_from_same_source",
                f"{len(members)} signals share only {distinct} distinct source measurement{'s' if distinct != 1 else ''} (a calculated channel "
                "derived from another member is not independent evidence).", members=len(members), distinct_measurements=distinct))
        r, w, temporal = _temporal_comparison(members, signals)
        reasons += r
        warnings += w
        summary["temporal"] = temporal
        r, w, damping = _damping_comparison(members)
        reasons += r
        warnings += w
        summary["damping"] = damping
    return {
        "representative_frequency_hz": representative, "representative_rule": "prominence-weighted mean of the members' frequencies",
        "frequency_spread_hz": spread, "match_tolerance_hz": tolerance, "signal_count": len(members),
        "recording_count": len(recording_ids), "distinct_measurement_count": distinct, "signal_types": types,
        "recordings": recordings, "max_prominence_db": max(m["prominence_db"] for m in members),
        "members": members, "reasons": reasons, "warnings": warnings, "evidence": summary,
    }
