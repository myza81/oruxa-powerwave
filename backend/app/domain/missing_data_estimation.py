"""Shared missing-data estimation POLICY (method/max-gap/local-mean-radius
configuration shape) and ENGINE (the actual array-filling math), used by
BOTH calculated-channel `null_policy = estimate_missing_data` (DEC-084
Calc Slice 2) and Data Preparation's own missing-value fill/estimation
enhancement (owner UAT, 2026-09-10, `app.services.working_overlay_service`).

A pure, framework-free, NumPy-based module -- no registry access, no
HTTP-mappable errors, no frontend concerns, and (owner hardening pass,
2026-09-10) no dependency on EITHER of its own two consumers' domain
modules. This is the intentional, neutral home for the configuration
constants/predicates below -- they used to live in
`app.domain.calculated_channel` (re-exported from there unchanged, for
every existing import site), which was the right call while estimation
was calculated-channel-only, but became backwards once Data Preparation
needed the identical configuration shape: Data Preparation has no
legitimate reason to depend on the Calculated Channel domain merely to
learn what a valid `estimation_method`/`max_gap_value` looks like.
Desired shape now:

    Data Preparation ---\\
                          +--> THIS module (shared policy + engine)
    Calculated Channel --/

Every function here is calculation-local and non-mutating: each
`estimate_*` function returns a NEW array (`values.copy()` up front, then
selective in-place writes on that copy only) and never writes into its
own `values`/`time` input arrays -- a caller's retained source/prepared/
calculated-channel arrays are always safe to pass in directly
(`app.services.calculated_channel_service` and
`app.services.working_overlay_service` are its two callers today, each
applying this independently per input/column).

Gap definition (section 5): one or more CONSECUTIVE non-finite samples
(NaN, +Inf, or -Inf -- section 14, all treated identically as "missing")
form one contiguous gap, `[start, end]` inclusive. A gap is eligible for
estimation only when its length (`end - start + 1`) is `<= max_gap_value`
samples (this module's only supported `max_gap_unit`, `MAX_GAP_UNIT_SAMPLES`
below); an oversized gap is left entirely as NaN -- never partially filled
(section 12).

Each `estimate_*` function reads its NEIGHBOR/bracket values from the
ORIGINAL input `values` array, never from its own partially-filled output
-- so one gap's estimate is never built from another gap's own estimated
values within the same call (section 9's "always base estimates on the
original calculation-local input array" principle, made explicit for
Local Mean by section 28's own test requirement).
"""

from __future__ import annotations

import numpy as np

# ---- Missing-data estimation configuration (method/max-gap/local-mean-
# radius shape) -- relocated here (owner hardening pass, 2026-09-10) from
# app.domain.calculated_channel, which now re-exports these SAME names
# unchanged (same objects, same values) for every pre-existing import
# site. See this module's own docstring for the full rationale.

#: valid, valid, gap, valid -> fill with the previous finite sample.
ESTIMATION_METHOD_HOLD_LAST = "hold_last"
#: Fill with the closest finite bracketing sample (sample-index
#: distance); equidistant ties break to the PREVIOUS sample.
ESTIMATION_METHOD_NEAREST = "nearest"
#: Linear interpolation using actual aligned `time` coordinates (never
#: sample index); no extrapolation -- a gap touching either end of the
#: array is never filled.
ESTIMATION_METHOD_LINEAR = "linear"
#: Fill the whole eligible gap with the mean of up to `local_mean_radius`
#: finite samples immediately before and up to `local_mean_radius` finite
#: samples immediately after it.
ESTIMATION_METHOD_LOCAL_MEAN = "local_mean"
#: Shape-preserving cubic interpolation -- recognized as a configuration
#: VALUE for forward compatibility only: no SciPy dependency exists in
#: this codebase and none is added by this module, so selecting it must
#: be rejected outright, never silently downgraded to Linear.
ESTIMATION_METHOD_PCHIP = "pchip"

ALL_ESTIMATION_METHODS = frozenset(
    {
        ESTIMATION_METHOD_HOLD_LAST, ESTIMATION_METHOD_NEAREST,
        ESTIMATION_METHOD_LINEAR, ESTIMATION_METHOD_LOCAL_MEAN, ESTIMATION_METHOD_PCHIP,
    }
)
#: Recognized methods with no working engine yet.
UNIMPLEMENTED_ESTIMATION_METHODS = frozenset({ESTIMATION_METHOD_PCHIP})

#: The only supported `max_gap_unit` so far ("samples" -- no milliseconds/
#: seconds support yet, for either consumer). A single-member set, not a
#: bare string constant, so a future addition only ever needs to grow
#: this set -- every `in ALL_MAX_GAP_UNITS` check keeps working unchanged.
MAX_GAP_UNIT_SAMPLES = "samples"
ALL_MAX_GAP_UNITS = frozenset({MAX_GAP_UNIT_SAMPLES})


def estimation_method_valid(estimation_method) -> bool:
    """True only for one of the five recognized method names (this
    covers BOTH a missing/`None` method and a genuinely unknown string --
    `None not in ALL_ESTIMATION_METHODS` is already `False`, so no
    separate `is None` branch is needed). Whether a recognized method is
    actually IMPLEMENTED yet is a separate question -- see
    `UNIMPLEMENTED_ESTIMATION_METHODS` -- deliberately kept apart so a
    caller can distinguish "not a real method" from "a real method not
    implemented yet" with two different, clearer errors."""
    return estimation_method in ALL_ESTIMATION_METHODS


def max_gap_value_valid(max_gap_value) -> bool:
    """`max_gap_value` must be a positive whole number of samples (this
    module's only supported `max_gap_unit`). `bool` is explicitly
    rejected even though Python treats it as an `int` subtype, and a
    missing (`None`) value is already `False` via the `isinstance`
    check, so "missing" and "invalid" share one predicate."""
    return bool(
        isinstance(max_gap_value, int)
        and not isinstance(max_gap_value, bool)
        and max_gap_value > 0
    )


def max_gap_unit_valid(max_gap_unit) -> bool:
    """True only for `"samples"` (`ALL_MAX_GAP_UNITS`) -- milliseconds/
    seconds are not supported yet."""
    return max_gap_unit in ALL_MAX_GAP_UNITS


def local_mean_radius_valid(local_mean_radius) -> bool:
    """`local_mean_radius` must be a positive whole number of samples
    ("N finite candidate samples before + N ... after") -- same
    `bool`-exclusion/missing-value handling as `max_gap_value_valid`
    above, deliberately mirrored rather than sharing one generic
    "positive int" helper, since the two are independently-named
    configuration concepts that happen to share a validation shape today."""
    return bool(
        isinstance(local_mean_radius, int)
        and not isinstance(local_mean_radius, bool)
        and local_mean_radius > 0
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
