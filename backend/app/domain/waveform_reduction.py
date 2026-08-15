"""Peak-preserving display reduction for waveform ranges (Phase 2A).

This is explicitly NOT the "decimation" algorithm `powerwave` uses for its
own desktop display (`app/visualization/rendering/downsampling.py`'s
`t_clip[::stride]`) -- that is plain nth-point stride sampling, confirmed
(docs/project-memory/MIGRATION_PLAN.md's Phase 2 design section) capable
of silently dropping a transient spike that falls between kept indices.
For power-system disturbance analysis, an invisible extremum is a real
engineering-integrity risk, not an acceptable display tradeoff -- see
DEC-019.

This module produces a *display representation* only. It never mutates or
returns a view aliasing its input arrays (the caller's authoritative
arrays are always safe from this function); every output array is newly
constructed. Callers must not treat this output as authoritative
engineering data -- see app.services.waveform_service's module docstring
for where the full-resolution/display-representation boundary is drawn.

Terminology: deliberately not "decimated" anywhere in this codebase or its
API surface -- see docs/project-memory/MIGRATION_PLAN.md's Phase 2 design
"Important terminology" note. Use "display representation" / "display
reduction" / "min/max envelope".
"""

from __future__ import annotations

import numpy as np

#: Points emitted per bucket (min + max) before first/last-sample padding
#: and before collapsing a bucket whose min and max are the same sample.
_POINTS_PER_BUCKET = 2


def build_min_max_envelope(
    time: np.ndarray,
    values: np.ndarray,
    point_budget: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a full-resolution (time, values) pair to a peak-preserving envelope.

    Splits the input into ``max(1, point_budget // 2)`` equal-*count*
    (not equal-*time*) buckets -- equal-count buckets need no assumption
    about uniform sample spacing, so they work identically for a
    single-rate or a genuine multi-rate COMTRADE section without any
    special-casing. Within each non-empty bucket, both the minimum and
    maximum sample are kept (a single point if they coincide), emitted in
    chronological order. The record's true first and last sample in the
    input range are always included even if neither happens to be a
    bucket extremum, so a caller can always see exactly where the
    requested range begins and ends.

    This means the returned point count is a *budget*, not a hard cap: it
    can be, and often is, close to but not exactly ``point_budget`` (up to
    ~2 points per bucket, plus up to 2 more for the first/last-sample
    guarantee). Callers must read the actual count off the result, never
    assume it equals ``point_budget``.

    Deterministic: the same input and point_budget always produce the same
    output (no randomness, no dependency on iteration order of anything
    other than the input arrays' own order). Input arrays are assumed
    already time-sorted ascending (true for every COMTRADE record produced
    by app.providers.comtrade); this function does not re-sort.

    Never mutates ``time``/``values`` and never returns a view of them --
    every element of the returned arrays is copied into new arrays.

    Raises ValueError if `time` and `values` have different lengths, if
    either is empty, or if `point_budget` is not a positive integer --
    these are programming-contract violations for this pure function, not
    a request the API layer should be routing through here directly (see
    app.services.waveform_service, which decides *whether* to call this
    function at all before calling it, based on `point_budget` vs sample
    count).
    """
    if time.shape != values.shape:
        raise ValueError(
            f"time and values must have the same shape (got {time.shape} vs {values.shape})"
        )
    n = time.shape[0]
    if n == 0:
        raise ValueError("build_min_max_envelope requires at least one sample")
    if point_budget <= 0:
        raise ValueError(f"point_budget must be positive (got {point_budget})")

    bucket_count = max(1, point_budget // _POINTS_PER_BUCKET)
    # Equal-count bucket edges. min(bucket_count, n) so a tiny range never
    # produces more (empty) buckets than it has samples to fill.
    edges = np.unique(
        np.linspace(0, n, num=min(bucket_count, n) + 1, dtype=np.int64)
    )

    out_time: list[float] = []
    out_values: list[float] = []

    for lo, hi in zip(edges[:-1], edges[1:]):
        bucket_time = time[lo:hi]
        bucket_values = values[lo:hi]
        i_min = int(np.argmin(bucket_values))
        i_max = int(np.argmax(bucket_values))
        if i_min == i_max:
            out_time.append(float(bucket_time[i_min]))
            out_values.append(float(bucket_values[i_min]))
        else:
            first_i, second_i = (i_min, i_max) if i_min < i_max else (i_max, i_min)
            out_time.append(float(bucket_time[first_i]))
            out_values.append(float(bucket_values[first_i]))
            out_time.append(float(bucket_time[second_i]))
            out_values.append(float(bucket_values[second_i]))

    # Guarantee the requested range's true edges are always represented,
    # regardless of whether they happen to be their bucket's extremum --
    # a disturbance analyst needs to see exactly where the visible range
    # starts/ends, not just its peaks.
    if out_time[0] != float(time[0]) or out_values[0] != float(values[0]):
        out_time.insert(0, float(time[0]))
        out_values.insert(0, float(values[0]))
    if out_time[-1] != float(time[-1]) or out_values[-1] != float(values[-1]):
        out_time.append(float(time[-1]))
        out_values.append(float(values[-1]))

    return np.array(out_time, dtype=np.float64), np.array(out_values, dtype=np.float64)
