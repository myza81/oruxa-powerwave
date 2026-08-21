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

OP_REVERSE_POLARITY = "reverse_polarity"
OP_ABSOLUTE_VALUE = "absolute_value"
OP_MULTIPLY_CONSTANT = "multiply_constant"
OP_ADDITION = "addition"
OP_SUBTRACTION = "subtraction"

#: Exactly one channel input (Multiply also takes a scalar `constant`
#: parameter alongside its one channel input -- section 28).
UNARY_OPERATIONS = frozenset({OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT})
#: Two or more ordered channel inputs (section 8/30/31 -- never hard-coded
#: to exactly two).
MULTI_OPERATIONS = frozenset({OP_ADDITION, OP_SUBTRACTION})
ALL_OPERATIONS = UNARY_OPERATIONS | MULTI_OPERATIONS

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
