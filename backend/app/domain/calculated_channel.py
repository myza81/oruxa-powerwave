"""Calculated Channels domain model (Phase 5A, DEC-047).

A calculated channel is a workspace-scoped, derived analog channel
produced by applying one of a small set of basic arithmetic operations to
one or more existing analog-like channels (real source channels, or other
calculated channels). This module owns the pure, framework-free pieces:
operation identifiers/arity, the typed channel reference used everywhere
a channel identity is needed (section 57 of the Phase 5A task -- never
string-prefix parsing), the `CalculatedChannel` record itself, the five
evaluation functions, and the timebase/unit compatibility rules. Zero
framework dependencies, per the domain/ layer contract (see
app.domain.source's own module docstring for the same convention).

Orchestration (resolving a `ChannelRef` against the live source/
calculated-channel registries, running the compatibility checks below,
and storing the result) lives in
app.services.calculated_channel_service -- this module never touches a
registry or raises an HTTP-mappable error itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.domain.channel_classification import UNDEFINED, WAVEFORM_FORM_UNKNOWN

OP_REVERSE_POLARITY = "reverse_polarity"
OP_ABSOLUTE_VALUE = "absolute_value"
OP_MULTIPLY_CONSTANT = "multiply_constant"
OP_ADDITION = "addition"
OP_SUBTRACTION = "subtraction"
OP_RMS = "rms"

#: Exactly one channel input (Multiply also takes a scalar `constant`
#: parameter alongside its one channel input -- section 28). RMS
#: (Phase 5B, DEC-048) joins this group: exactly one channel input plus a
#: scalar `nominal_frequency_hz` parameter, the same "1 input + 1 scalar
#: parameter" shape as Multiply by Constant.
UNARY_OPERATIONS = frozenset({OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS})
#: Two or more ordered channel inputs (section 8/30/31 -- never hard-coded
#: to exactly two).
MULTI_OPERATIONS = frozenset({OP_ADDITION, OP_SUBTRACTION})
ALL_OPERATIONS = UNARY_OPERATIONS | MULTI_OPERATIONS

#: Phase 5B (DEC-048) RMS parameters -- see evaluate_rms() below. A soft
#: plausibility bound, NOT a 50/60 Hz whitelist (the owner's spec allows
#: any sensible nominal frequency, defaulting to 50 Hz).
MIN_NOMINAL_FREQUENCY_HZ = 1.0
MAX_NOMINAL_FREQUENCY_HZ = 1000.0
#: Conservative, explicitly revisitable minimum density for a "one-cycle
#: RMS" to be meaningful at all (owner section 41: "do not calculate a
#: misleading RMS from 2-3 points/cycle").
MIN_SAMPLES_PER_CYCLE = 4

#: Deliberately tight -- section 11 of the owner's time-alignment
#: guardrail: "do not use a loose tolerance that could incorrectly treat
#: differently-timed engineering samples as synchronized." Sub-microsecond,
#: far tighter than any realistic sample spacing (even a 1 MHz channel has
#: 1 microsecond spacing), so this only ever absorbs genuine floating-point
#: representation noise from computing `start_epoch + elapsed_seconds`
#: twice, never a real timing difference.
TIME_ALIGNMENT_TOLERANCE_SECONDS = 1e-9

#: Section 35 -- a sensible, generous cap; not a hard product requirement,
#: just guards against a pathological/accidental paste.
MAX_NAME_LENGTH = 120


@dataclass(slots=True, frozen=True)
class ChannelRef:
    """A stable, typed reference to any analog-like channel -- a real
    source channel, or another calculated channel (section 57 of the
    Phase 5A task). Used uniformly for builder inputs, stored
    dependencies, and resolution -- never parsed from a string prefix.
    """

    kind: str  # "source" | "calculated"
    source_id: str | None = None
    channel_name: str | None = None
    calculated_channel_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "source":
            if not self.source_id or not self.channel_name:
                raise ValueError("A 'source' ChannelRef requires both source_id and channel_name.")
        elif self.kind == "calculated":
            if not self.calculated_channel_id:
                raise ValueError("A 'calculated' ChannelRef requires calculated_channel_id.")
        else:
            raise ValueError(f"Unknown ChannelRef kind: {self.kind!r}")


@dataclass(slots=True)
class CalculatedChannel:
    """One evaluated, immutable-after-creation calculated channel (section
    47: no edit-in-place this phase -- create another one instead).

    `time`/`values` are the full-resolution, authoritative result (section
    15/46 -- eager evaluation at creation time, retained here exactly like
    `ActiveSource.record` retains a source's own full-resolution arrays;
    never re-evaluated on a later waveform/cursor/peak request).

    `reference_source_id` is this channel's own timebase identity (section
    9/10 of the owner's time-alignment guardrail) -- the id of whichever
    real source ultimately grounds its (unmodified, inherited) `time`
    array. Every Phase 5A operation only transforms VALUES, never timing,
    so this is always exactly one of its own inputs' `reference_source_id`
    (proven identical to every other input's at creation time -- see
    app.services.calculated_channel_service.create_calculated_channel).
    This is what lets `remove_calculated_channels_for_source()` cascade a
    source removal through an arbitrarily deep calculated-channel chain
    with one flat filter, never a graph walk (section 64).

    `dependency_ids` is this channel's own DIRECT calculated-channel
    dependencies only (never transitive) -- section 23/61: used both for
    the Annotation-List-style human-readable dependency summary and for
    "who depends on me" reverse lookups at delete time (section 25/63).
    """

    id: str
    workspace_id: str
    name: str
    unit: str
    operation: str
    inputs: list[ChannelRef]
    parameters: dict
    dependency_ids: list[str]
    reference_source_id: str
    time: np.ndarray
    values: np.ndarray
    created_at: datetime
    # Phase 5A-UAT4 (DEC-047 clarification): the inherited engineering
    # classification (app.domain.channel_classification.KNOWN_CATEGORIES),
    # computed once at creation time by derive_engineering_type() below --
    # never re-derived from this channel's own (user-editable) `name`.
    engineering_type: str = UNDEFINED
    # Phase 5B (DEC-048): this channel's own waveform-form classification
    # (app.domain.channel_classification.KNOWN_WAVEFORM_FORMS), computed
    # once at creation time by
    # app.domain.channel_classification.derive_waveform_form() -- an RMS
    # channel is always WAVEFORM_FORM_RMS unconditionally (never inherited
    # from its input); every other operation follows its own propagation
    # rule (see derive_waveform_form()'s own docstring). This is the
    # TRUSTED metadata a later RMS-eligibility check reads first, before
    # ever running the algorithmic detector (owner section 11/14).
    waveform_form: str = WAVEFORM_FORM_UNKNOWN


def evaluate_reverse_polarity(values: np.ndarray) -> np.ndarray:
    return -values


def evaluate_absolute_value(values: np.ndarray) -> np.ndarray:
    return np.abs(values)


def evaluate_multiply_constant(values: np.ndarray, constant: float) -> np.ndarray:
    return values * constant


def evaluate_addition(value_arrays: list[np.ndarray]) -> np.ndarray:
    """`input1 + input2 + ... + inputN` (section 30). Order is preserved
    in the stored definition for reproducibility/expression-display/
    naming (section 10) even though addition is itself commutative --
    but the SUM is naturally order-independent regardless."""
    out = value_arrays[0].copy()
    for arr in value_arrays[1:]:
        out = out + arr
    return out


def evaluate_subtraction(value_arrays: list[np.ndarray]) -> np.ndarray:
    """`input1 - input2 - input3 - ... - inputN`, explicitly LEFT-
    ASSOCIATIVE (section 9/31): `A - B - C`, never `A - (B + C)` (though
    arithmetically these happen to coincide -- computed via sequential
    subtraction, matching the stated semantics directly rather than
    relying on that coincidence)."""
    out = value_arrays[0].copy()
    for arr in value_arrays[1:]:
        out = out - arr
    return out


def evaluate_rms(time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float) -> np.ndarray:
    """Trailing one-cycle TRUE RMS (owner sections 3-9): `RMS(t) =
    sqrt(mean(x^2))` over the trailing window `[t - window, t]`, where
    `window = 1 / nominal_frequency_hz`. The ONLY evaluator in this module
    that reads `time` as well as `values` -- a deliberate, narrow
    exception to every other evaluator's pure `values -> values` contract,
    because RMS is inherently a function of elapsed-TIME window
    membership, never a fixed sample count (section 6/7 -- sample spacing
    is not guaranteed uniform across a whole source recording; see
    app.providers.comtrade's own per-row timestamp construction, which
    means a COMTRADE file's declared multi-rate sections do not force a
    single fixed samples-per-cycle count).

    Output has the SAME LENGTH as the input, never cycle-boundary
    downsampled -- see `CalculatedChannel`'s own docstring for why this
    invariant matters (verbatim `time`/`reference_source_id` inheritance,
    calculated-from-calculated support). Before a complete trailing window
    is available (`time[i] - time[0] < window`), the output is NaN
    (section 8: never a partial/shorter window). A window containing ANY
    non-finite input sample also outputs NaN for that window (section 39:
    never silently drop the invalid sample and renormalize over fewer
    samples -- that would silently change the window's own meaning).

    Two algorithms, chosen automatically by inspecting the actual spacing
    of `time` (never assumed from `nominal_frequency_hz` alone):

    - **Near-uniform sample spacing** (the common case for one COMTRADE
      sampling-rate section): a fully vectorized cumulative-sum rolling
      window, O(N), zero Python-level loop -- satisfying the owner's own
      explicit efficiency requirement (section 38: "rolling sum of
      squares... avoid O(N * window_size)").
    - **Genuinely irregular/multi-rate spacing**: an O(N) two-pointer
      sliding window. Correct because `time` is always monotonic
      non-decreasing (COMTRADE per-row timestamps), so the window's own
      lower bound is itself monotonic non-decreasing as the trailing edge
      advances -- this is what makes one forward pass sufficient, rather
      than a per-sample `searchsorted` (a valid, but strictly more
      expensive, O(N log N) fallback).

    Non-finite samples are tracked as a SEPARATE running/cumulative count,
    never accumulated into the running sum-of-squares directly: a naive
    rolling sum that adds a NaN and later "subtracts it back out" is
    broken (IEEE754 `NaN - NaN = NaN`, so one NaN would poison every
    subsequent window forever, not just the windows that actually contain
    it).
    """
    n = time.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return out

    window = 1.0 / nominal_frequency_hz
    finite_mask = np.isfinite(values)
    sq_safe = np.where(finite_mask, values.astype(np.float64) * values.astype(np.float64), 0.0)
    nonfinite_flag = (~finite_mask).astype(np.int64)

    diffs = np.diff(time) if n >= 2 else np.array([], dtype=np.float64)
    uniform = n >= 2 and bool(np.allclose(diffs, np.median(diffs), rtol=1e-6, atol=1e-12))

    # A half-open trailing window, `(t[i] - window, t[i]]` -- excluding the
    # exact left boundary sample, rather than the naively "more inclusive"
    # closed interval `[t[i] - window, t[i]]`. For UNIFORM spacing where
    # `window` happens to be an exact multiple of the sample interval
    # (e.g. exactly 100 samples/cycle at 5 kHz for a 50 Hz window), a
    # closed interval double-counts one sample: the boundary sample at
    # `t[i] - window` and the current sample at `t[i]` are exactly one
    # full period apart and so share the SAME sinusoidal phase, and
    # including both over-weights that phase as the window slides,
    # producing a spurious ~1/N ripple in an otherwise-steady sinusoid's
    # RMS (verified numerically: ripple shrinks linearly as N grows,
    # confirming a discretization artifact of the closed-interval choice,
    # not sensor noise). The half-open interval is exactly one full
    # window's worth of NON-redundant samples (`window / dt` of them,
    # never `+ 1`) and is bit-for-bit ripple-free for a steady nominal-
    # frequency sinusoid -- matching both real digital-relay one-cycle
    # RMS estimator convention and this task's own worked example
    # (section 6: "~100 samples per 20ms" for 5 kHz, not ~101).
    #
    # `_BOUNDARY_EPS` absorbs ordinary floating-point noise in the
    # boundary comparison itself (`t[i] - window` computed by subtraction
    # vs. `t[lo]` computed by the time array's own independent
    # construction can differ by a ULP even when mathematically equal),
    # which would otherwise make the trim fire inconsistently from one
    # sample to the next at an exact cycle boundary and reintroduce the
    # same ripple by a different route.
    _BOUNDARY_EPS = 1e-9

    if uniform:
        dt = float(np.median(diffs))
        window_samples = max(int(round(window / dt)), 1)
        cumsum_sq = np.concatenate(([0.0], np.cumsum(sq_safe)))
        cumsum_nonfinite = np.concatenate(([0], np.cumsum(nonfinite_flag)))

        idx = np.arange(n)
        lo = idx - window_samples + 1
        lo_clipped = np.clip(lo, 0, n)
        count = idx - lo_clipped + 1
        window_sumsq = cumsum_sq[idx + 1] - cumsum_sq[lo_clipped]
        window_nonfinite = cumsum_nonfinite[idx + 1] - cumsum_nonfinite[lo_clipped]

        # Availability is governed by genuinely ELAPSED history, never by
        # `window_samples` alone (section 6/7's own "time-based, not
        # fixed-N" requirement applies even inside this vectorized fast
        # path) -- `lo >= 0` alone would falsely mark one extra leading
        # sample "available" a step early (it has `window_samples` samples
        # accumulated, but they only span `window - dt` of real elapsed
        # time, one sample short of a genuine full window).
        time_available = (time - time[0]) >= (window - _BOUNDARY_EPS)
        available = (lo >= 0) & time_available & (window_nonfinite == 0)

        with np.errstate(invalid="ignore", divide="ignore"):
            rms_values = np.sqrt(window_sumsq / count)
        out[available] = rms_values[available]
        return out

    # Irregular/multi-rate spacing: O(N) two-pointer sliding accumulator.
    lo = 0
    running_sumsq = 0.0
    running_nonfinite = 0
    t0 = time[0]
    for i in range(n):
        while time[lo] <= time[i] - window + _BOUNDARY_EPS:
            running_sumsq -= sq_safe[lo]
            running_nonfinite -= nonfinite_flag[lo]
            lo += 1
        running_sumsq += sq_safe[i]
        running_nonfinite += nonfinite_flag[i]
        if running_nonfinite > 0 or (time[i] - t0) < window - _BOUNDARY_EPS:
            continue
        count = i - lo + 1
        out[i] = np.sqrt(running_sumsq / count)
    return out


def nominal_frequency_valid(nominal_frequency_hz: float) -> bool:
    """Section 30/41: a sensible numeric plausibility bound -- NOT a
    50/60 Hz whitelist. `bool` is explicitly rejected even though Python
    treats it as an `int` subtype (`isinstance(True, int) is True`),
    since a stray boolean in a JSON payload should never silently pass as
    a frequency."""
    return bool(
        isinstance(nominal_frequency_hz, (int, float))
        and not isinstance(nominal_frequency_hz, bool)
        and np.isfinite(nominal_frequency_hz)
        and MIN_NOMINAL_FREQUENCY_HZ <= nominal_frequency_hz <= MAX_NOMINAL_FREQUENCY_HZ
    )


def rms_recording_long_enough(time: np.ndarray, nominal_frequency_hz: float) -> bool:
    """Section 40: True only if the recording spans strictly more than one
    full RMS window -- i.e. at least one output sample would be non-NaN.
    Creation is rejected outright when this is False, rather than
    silently producing an all-NaN channel."""
    if time.shape[0] < 2:
        return False
    window = 1.0 / nominal_frequency_hz
    duration = float(time[-1] - time[0])
    return duration > window


def rms_sampling_dense_enough(time: np.ndarray, nominal_frequency_hz: float) -> bool:
    """Section 41: True only if the median sample spacing implies at least
    MIN_SAMPLES_PER_CYCLE samples within one RMS window -- guards against
    a misleading RMS computed from only 2-3 points per cycle."""
    if time.shape[0] < 2:
        return False
    window = 1.0 / nominal_frequency_hz
    median_dt = float(np.median(np.diff(time)))
    if median_dt <= 0:
        return False
    return (window / median_dt) >= MIN_SAMPLES_PER_CYCLE


def units_compatible(units: list[str | None]) -> bool:
    """Phase 1 unit-compatibility rule (section 32/33): every input's unit
    string must be equal (no dimensional conversion -- `kV` and `V` are
    NOT treated as compatible without a proven existing conversion layer,
    which does not exist in this codebase). Missing units get the
    conservative treatment section 33 asks for: ALL missing -> allowed
    (caller then leaves the output unit blank); a MIXTURE of known and
    missing -> rejected outright, never silently allowed through.
    """
    known = [u for u in units if u]
    if not known:
        return True
    return len(known) == len(units) and len(set(known)) == 1


def derive_engineering_type(input_types: list[str]) -> str:
    """Phase 5A-UAT4: the inherited engineering-classification rule for
    every current Phase 5A operation. Deliberately ONE rule, not five --
    it happens to cover Reverse Polarity/Absolute Value/Multiply by
    Constant (exactly one input, so "the common type" trivially IS that
    input's own type) and Addition/Subtraction (2+ inputs, common type
    required) identically, with no per-operation branching needed.

    Never guesses from a calculated channel's own (user-editable) `name`
    -- the owner's own explicit requirement. Reuses
    app.domain.channel_classification.UNDEFINED as the one shared
    "not confidently known" sentinel, never a second/local definition of
    the same idea; a calculated-from-calculated channel is classified by
    passing its own already-derived `engineering_type` back into this
    function as one of its inputs, so the inheritance rule composes
    correctly through arbitrarily deep chains with no separate
    transitive-propagation logic required.

    Conservative by construction (mirrors classify_analog_channel's own
    "never guess" philosophy): every input must share the exact same
    KNOWN (non-UNDEFINED) type for that type to be inherited; an empty
    list, any UNDEFINED input, or a genuine mismatch (e.g. Voltage
    combined with Current -- unreachable today since units_compatible()
    already rejects that pairing for multi-input operations before this
    is even called, but never assumed here) all conservatively yield
    UNDEFINED rather than a guess.
    """
    if not input_types:
        return UNDEFINED
    first = input_types[0]
    if first == UNDEFINED:
        return UNDEFINED
    if all(t == first for t in input_types):
        return first
    return UNDEFINED


def timebases_aligned(
    ref_a: str,
    elapsed_a: np.ndarray,
    start_epoch_a: float | None,
    ref_b: str,
    elapsed_b: np.ndarray,
    start_epoch_b: float | None,
) -> bool:
    """The owner's explicit time-alignment guardrail, section 1-8: two
    channels may participate in the SAME multi-input calculation only if
    every one of their sample instants is PROVEN to correspond -- same
    sample count and same nominal sampling rate are explicitly
    insufficient (section 5/6/7), and no interpolation/resampling/
    cropping-to-overlap is ever performed to make an otherwise-
    incompatible pair usable (section 8).

    Two fast, honest paths, in order:

    1. **Same `reference_source_id`** -- structurally, PROVABLY aligned,
       not merely assumed (section 3 of the guardrail: "Verify this
       guarantee in the current backend"). Every analog channel of one
       COMTRADE source shares exactly one `waveform_data["time"]` pandas
       column (see app.domain.disturbance_record's own docstring/module
       structure) -- there is no per-channel time array anywhere in this
       codebase's source model. Every Phase 5A operation only transforms
       VALUES, never `time`, so a calculated channel's own `elapsed_time`
       is always numerically IDENTICAL to (never a modified copy of)
       whichever input first established it -- so this identity check is
       sufficient on its own, with no array comparison needed, for any
       two channels (source or calculated) sharing one
       `reference_source_id`.

    2. **Different `reference_source_id`** -- section 4: rejected UNLESS
       the backend can PROVE identical sample instants. "Proof" here means
       comparing true ABSOLUTE instants (`source.start_time + elapsed`),
       not raw elapsed arrays (section 2: "Do not compare merely what is
       visually displayed on the X axis" -- two independently-triggered
       recordings can trivially have numerically identical ELAPSED arrays,
       e.g. both starting at t=0 at the same rate, without representing
       the same physical instants at all). If either source's own
       `start_time` is unknown (`None`), there is nothing to prove
       alignment with, so this returns `False` -- never optimistically
       `True`. Compared with `TIME_ALIGNMENT_TOLERANCE_SECONDS`
       (deliberately tight, sub-microsecond -- section 11), never a loose
       tolerance that could paper over a genuine misalignment.
    """
    if ref_a == ref_b:
        return True
    if start_epoch_a is None or start_epoch_b is None:
        return False
    if elapsed_a.shape != elapsed_b.shape:
        return False
    absolute_a = start_epoch_a + elapsed_a
    absolute_b = start_epoch_b + elapsed_b
    return bool(np.allclose(absolute_a, absolute_b, rtol=0.0, atol=TIME_ALIGNMENT_TOLERANCE_SECONDS))


def would_create_cycle(dependency_map: dict[str, list[str]], candidate_id: str, new_dependency_ids: list[str]) -> bool:
    """True if adding edges `candidate_id -> each of new_dependency_ids`
    would introduce a cycle into `dependency_map` (a directed graph:
    calculated-channel id -> its own DIRECT dependency ids) -- section
    24/85.

    Structurally unreachable via the real one-shot creation API today
    (see `CalculatedChannel`'s own docstring on immutability: every
    referenced dependency must already exist as a stored, immutable
    channel before `candidate_id` is even minted, so no back-edge to a
    not-yet-existing id can ever be formed) -- kept as an explicit,
    correctly-implemented, independently-testable guard for defense in
    depth and for any future mutation path, per the task's own explicit
    instruction ("Even if current UI creation flow makes cycles unlikely,
    backend/domain validation must reject them").

    Plain reachability DFS from the proposed new dependencies back toward
    `candidate_id` -- O(V+E) in the dependency graph, never recursive
    (an explicit stack, so a very deep chain cannot exhaust the Python
    call stack).
    """
    visited: set[str] = set()
    stack = list(new_dependency_ids)
    while stack:
        node = stack.pop()
        if node == candidate_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(dependency_map.get(node, []))
    return False
