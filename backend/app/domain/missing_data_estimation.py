"""Missing-data estimation engine for calculated channels (DEC-084 Calc
Slice 2, `null_policy = estimate_missing_data`).

A pure, framework-free, NumPy-based module -- no registry access, no
HTTP-mappable errors, no frontend concerns (matches the domain/ layer
contract already established by app.domain.calculated_channel's own
module docstring). Every function here is calculation-local and
non-mutating: each `estimate_*` function returns a NEW array (`values.
copy()` up front, then selective in-place writes on that copy only) and
never writes into its own `values`/`time` input arrays -- the caller's
retained source/calculated-channel arrays are always safe to pass in
directly (app.services.calculated_channel_service is the one caller,
applying this independently per input, per DEC-084 point 7/9-10/section
10 of this task).

Gap definition (section 5): one or more CONSECUTIVE non-finite samples
(NaN, +Inf, or -Inf -- section 14, all treated identically as "missing")
form one contiguous gap, `[start, end]` inclusive. A gap is eligible for
estimation only when its length (`end - start + 1`) is `<= max_gap_value`
samples (this slice's only supported `max_gap_unit`, "samples" --
app.domain.calculated_channel.MAX_GAP_UNIT_SAMPLES); an oversized gap is
left entirely as NaN -- never partially filled (section 12).

Each `estimate_*` function reads its NEIGHBOR/bracket values from the
ORIGINAL input `values` array, never from its own partially-filled output
-- so one gap's estimate is never built from another gap's own estimated
values within the same call (section 9's "always base estimates on the
original calculation-local input array" principle, made explicit for
Local Mean by section 28's own test requirement).
"""

from __future__ import annotations

import numpy as np

from app.domain.calculated_channel import (
    ESTIMATION_METHOD_HOLD_LAST,
    ESTIMATION_METHOD_LINEAR,
    ESTIMATION_METHOD_LOCAL_MEAN,
    ESTIMATION_METHOD_NEAREST,
)


def find_gaps(values: np.ndarray) -> list[tuple[int, int]]:
    """Every contiguous run of non-finite (NaN/+Inf/-Inf, section 14)
    samples in `values`, as inclusive `(start_index, end_index)` pairs, in
    ascending order. `[]` when every sample is finite.

    Fully vectorized (section 21: designed for 100k-1M sample arrays) --
    one boolean mask, one `np.diff` over a zero-padded version of it to
    find rising/falling edges, and one `np.flatnonzero` each for starts
    and ends. No per-sample Python loop; each `estimate_*` function below
    then iterates once per GAP (not per sample), which section 21
    explicitly accepts ("Per-gap iteration is acceptable").
    """
    n = values.shape[0]
    if n == 0:
        return []
    non_finite = ~np.isfinite(values)
    if not non_finite.any():
        return []
    padded = np.concatenate(([False], non_finite, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def estimate_hold_last(values: np.ndarray, max_gap_value: int) -> np.ndarray:
    """Section 6: fill each eligible gap with the single finite sample
    immediately before it (`values[start - 1]`, never anything from
    inside the gap). A beginning gap (`start == 0`, no previous finite
    sample at all) is left NaN -- no backward fill, ever."""
    out = values.copy()
    for start, end in find_gaps(values):
        if (end - start + 1) > max_gap_value:
            continue
        if start == 0:
            continue
        out[start:end + 1] = values[start - 1]
    return out


def estimate_nearest(values: np.ndarray, max_gap_value: int) -> np.ndarray:
    """Section 7: fill each sample of an eligible gap with whichever
    bracketing finite sample (immediately before / immediately after the
    gap) is closer by SAMPLE-INDEX distance; an exact tie deterministically
    resolves to the PREVIOUS sample (`dist_prev <= dist_next`). A
    beginning gap (no previous bracket) uses the following sample for
    every position; an ending gap (no following bracket) uses the
    preceding sample for every position; a gap with neither bracket (the
    whole array non-finite) is left NaN. Vectorized per gap via
    `np.where` over the gap's own index range -- never a per-sample
    Python loop."""
    out = values.copy()
    n = values.shape[0]
    for start, end in find_gaps(values):
        if (end - start + 1) > max_gap_value:
            continue
        has_prev = start > 0
        has_next = end < n - 1
        if not has_prev and not has_next:
            continue
        if has_prev and has_next:
            prev_val = values[start - 1]
            next_val = values[end + 1]
            idx = np.arange(start, end + 1)
            dist_prev = idx - (start - 1)
            dist_next = (end + 1) - idx
            out[start:end + 1] = np.where(dist_prev <= dist_next, prev_val, next_val)
        elif has_prev:
            out[start:end + 1] = values[start - 1]
        else:
            out[start:end + 1] = values[end + 1]
    return out


def estimate_linear(time: np.ndarray, values: np.ndarray, max_gap_value: int) -> np.ndarray:
    """Section 8: linear interpolation using the ALIGNED `time` array's
    actual coordinates (never sample index, never assumed-uniform
    spacing). Requires a finite sample immediately before AND immediately
    after the gap -- a beginning or ending gap is left NaN (no
    extrapolation, ever). The two bracketing timestamps must themselves
    be finite and strictly increasing; if not, the gap is left NaN rather
    than raising a domain error -- this is a per-gap DATA-QUALITY
    condition on the two bracketing samples, not a structural precondition
    like DEC-047 alignment (which is already proven true for the whole
    array before this function is ever called), so it is handled the same
    conservative "leave NaN" way every other ineligible gap already is,
    rather than aborting the whole calculated-channel creation over one
    gap."""
    out = values.copy()
    n = values.shape[0]
    for start, end in find_gaps(values):
        if (end - start + 1) > max_gap_value:
            continue
        if start == 0 or end == n - 1:
            continue
        t0, t1 = time[start - 1], time[end + 1]
        if not (np.isfinite(t0) and np.isfinite(t1) and t1 > t0):
            continue
        v0, v1 = values[start - 1], values[end + 1]
        idx = np.arange(start, end + 1)
        out[idx] = v0 + (v1 - v0) * (time[idx] - t0) / (t1 - t0)
    return out


def estimate_local_mean(values: np.ndarray, max_gap_value: int, local_mean_radius: int) -> np.ndarray:
    """Section 9: fill each eligible gap with the mean of its finite
    neighbor samples -- up to `local_mean_radius` samples immediately
    before the gap, and up to `local_mean_radius` samples immediately
    after it (an edge gap simply has fewer, or zero, on the short side).
    Non-finite neighbor samples are excluded, never counted; a gap with
    ZERO finite neighbors on either side is left entirely NaN. Neighbor
    windows are always sliced from the ORIGINAL `values` (never from this
    function's own `out`), so a later gap's neighbor mean never includes
    an earlier gap's own estimated fill within the same call (section 9's
    "original calculation-local input array" rule / section 28's explicit
    multi-gap-independence test)."""
    out = values.copy()
    n = values.shape[0]
    for start, end in find_gaps(values):
        if (end - start + 1) > max_gap_value:
            continue
        before = values[max(0, start - local_mean_radius):start]
        after = values[end + 1:min(n, end + 1 + local_mean_radius)]
        neighbors = np.concatenate([before, after])
        finite_neighbors = neighbors[np.isfinite(neighbors)]
        if finite_neighbors.size == 0:
            continue
        out[start:end + 1] = float(np.mean(finite_neighbors))
    return out


def apply_estimation(
    *,
    time: np.ndarray,
    values: np.ndarray,
    estimation_method: str,
    max_gap_value: int,
    local_mean_radius: int | None = None,
) -> np.ndarray:
    """The one dispatch point app.services.calculated_channel_service
    calls per input (section 10: independent per-input estimation) --
    picks the right `estimate_*` function above by `estimation_method`.
    Callers are expected to have already validated `estimation_method`/
    `max_gap_value`/`local_mean_radius` (see app.domain.calculated_channel's
    own `*_valid()` predicates and `UNIMPLEMENTED_ESTIMATION_METHODS`) --
    the `ValueError` below is a defensive "should never happen" guard,
    never a normal/expected control-flow path, exactly like
    `ChannelRef.__post_init__`'s own unknown-`kind` guard."""
    if estimation_method == ESTIMATION_METHOD_HOLD_LAST:
        return estimate_hold_last(values, max_gap_value)
    if estimation_method == ESTIMATION_METHOD_NEAREST:
        return estimate_nearest(values, max_gap_value)
    if estimation_method == ESTIMATION_METHOD_LINEAR:
        return estimate_linear(time, values, max_gap_value)
    if estimation_method == ESTIMATION_METHOD_LOCAL_MEAN:
        return estimate_local_mean(values, max_gap_value, local_mean_radius)
    raise ValueError(f"Unsupported/unimplemented estimation method: {estimation_method!r}.")
