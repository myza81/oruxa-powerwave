"""Waveform time-synchronization domain model (Slice 1: per-source manual
alignment; Slice 2: one workspace-wide event origin, `t0`).

Manual, per-source visual alignment (Slice 1) -- see
docs/project-memory/DECISIONS.md's DEC-036 addendum ("this is
synchronization-ready: a future phase can introduce an alignment offset
between source-native bounds and aligned workspace bounds") for the prior
decision that slice implements. Slice 2 adds a manually-selected common
event origin (`t0_workspace_time`) on top of that -- see the Slice 2
task's own "Explicit Non-Goals" list for what is deliberately still NOT
built here (no automatic `t=0`/trigger/correlation/threshold detection,
no clock-drift/timezone correction, no event grouping, no resampling).

Core mapping (kept in this one pure, framework-free module so there is
exactly one authoritative definition -- see
app.services.synchronization_service for the thin registry-backed
wrappers every caller actually uses):

    workspace_time = source_time + alignment_offset_s
    source_time    = workspace_time - alignment_offset_s

    event_time     = workspace_time - t0_workspace_time
    workspace_time = event_time + t0_workspace_time

Composed (source <-> event, never a third independently-coded formula --
every caller composes the two pairs above rather than a caller doing its
own arithmetic):

    event_time  = source_time + alignment_offset_s - t0_workspace_time
    source_time = event_time + t0_workspace_time - alignment_offset_s

`source_time` is a source's own original/native elapsed time (the
`waveform_data["time"]` column app.domain.disturbance_record already
owns) -- never altered by this module. `alignment_offset_s` is
per-source synchronization metadata (Slice 1). `t0_workspace_time` is
ONE manually-selected workspace-time instant, shared by the whole
workspace, never per-source (Slice 2 task section 4: "this is one common
event origin for the workspace," not one t0 per source) --
app.services.synchronization_registry stores it keyed by `workspace_id`
alone, not `(workspace_id, source_id)`. `workspace_time` is the
synchronized/display time coordinate before an event origin exists;
`event_time` is the engineer-facing coordinate once one is selected.
Works identically for a scalar `float` or a `numpy.ndarray` -- plain
arithmetic, no branching on type needed.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np


def source_time_to_workspace_time(source_time, alignment_offset_s: float):
    """`workspace_time = source_time + alignment_offset_s`. `source_time`
    may be a scalar or a numpy array; the returned value has the same
    shape."""
    return source_time + alignment_offset_s


def workspace_time_to_source_time(workspace_time, alignment_offset_s: float):
    """`source_time = workspace_time - alignment_offset_s` -- the inverse
    of `source_time_to_workspace_time`. This is the mapping every
    workspace/display time must go through before it is used to query
    source-native data (a fetch range, a cursor time, ...)."""
    return workspace_time - alignment_offset_s


def workspace_time_to_event_time(workspace_time, t0_workspace_time: float):
    """`event_time = workspace_time - t0_workspace_time` -- Slice 2's own
    addition. `workspace_time` may be a scalar or a numpy array; the
    returned value has the same shape."""
    return workspace_time - t0_workspace_time


def event_time_to_workspace_time(event_time, t0_workspace_time: float):
    """`workspace_time = event_time + t0_workspace_time` -- the inverse
    of `workspace_time_to_event_time`. This is the mapping every
    event-relative display time must go through before it is used as a
    workspace-time coordinate (which itself still needs
    `workspace_time_to_source_time()` before it can query source-native
    data -- never skip straight from event time to a source-native
    query, see this module's own composed-mapping note above)."""
    return event_time + t0_workspace_time


def alignment_offset_valid(alignment_offset_s: float) -> bool:
    """A submitted alignment offset must be a finite real number of
    seconds. No magnitude bound is imposed here -- an engineer manually
    aligning two independently-triggered recordings may legitimately need
    an offset larger than either recording's own duration (e.g. two
    events recorded on unsynchronized clocks); this module only rejects
    what can never be a genuine offset (NaN/Infinity/non-numeric),
    exactly like `app.domain.calculated_channel.nominal_frequency_valid`'s
    own `bool`-rejection precedent.

    Slice 2 reuses this SAME predicate for `t0_workspace_time` validation
    (app.services.synchronization_service.set_t0) rather than duplicating
    an identical "finite real number of seconds" rule under a second
    name -- a workspace-time event origin has exactly the same validity
    shape as a per-source offset, just a different meaning. The two stay
    independently distinguishable at the API layer via distinct error
    codes (`invalid_alignment_offset` vs `invalid_t0`), never by having
    two copies of this check that could quietly drift apart."""
    return bool(
        isinstance(alignment_offset_s, (int, float))
        and not isinstance(alignment_offset_s, bool)
        and np.isfinite(alignment_offset_s)
    )


def reference_source_id_for_workspace(sources: list[tuple[str, datetime]]) -> str | None:
    """Slice 1's deterministic reference-source rule (task section 9):
    "the first participating source becomes the reference" -- no explicit
    reference-selector UI exists yet, so this is the smallest
    deterministic rule available. `sources` is `[(source_id, created_at),
    ...]` for every source currently in the workspace (order-independent
    -- this always resolves by the EARLIEST `created_at`, never by
    caller-supplied list order, so it stays correct regardless of
    `WorkspaceRegistry.list_for_workspace()`'s own iteration order).
    Ties (identical `created_at`, structurally possible if two uploads
    land in the same process tick) break on `source_id` ascending, purely
    for determinism -- never meaningful ordering information.

    Returns `None` for an empty workspace (no reference exists yet)."""
    if not sources:
        return None
    return min(sources, key=lambda pair: (pair[1], pair[0]))[0]
