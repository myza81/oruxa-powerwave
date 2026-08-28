"""In-memory, ephemeral, workspace-scoped synchronization-state registry
(Slice 1: per-source MANUAL alignment offsets; Slice 2: event origin
`t0_workspace_time`, now Time-Group-scoped -- see
docs/project-memory/DECISIONS.md's "Timestamp-Based Initial Alignment
and Time Groups" entry).

A sibling registry to `WorkspaceRegistry`/`PerUnitRegistry` (same
`threading.Lock` + `dict[key, T]` shape -- see those modules' own
docstrings for the shared locking-policy rationale, unchanged here).

Two independent stores live here, each with its own natural key shape:

- `_offsets`, keyed by `(workspace_id, source_id)` -- this is, and has
  always been, the source's own MANUAL correction only
  (`manual_alignment_offset_s` in the new three-part model:
  `timestamp_placement_offset_s` (derived, `app.domain.time_grouping`,
  never stored here) + `manual_alignment_offset_s` (THIS store,
  unchanged storage/semantics from Slice 1) =
  `effective_alignment_offset_s` (derived at read time,
  `app.services.synchronization_service`)). Only NON-ZERO/explicitly-set
  offsets are stored: an unconfigured source has no entry at all, and
  `get_offset()` returns `0.0` for it -- this keeps "every source starts
  with no manual correction" free (no need to pre-populate an entry per
  source on upload) and makes "reset" a plain delete, mirroring
  `PerUnitRegistry.delete()`'s own idempotent-clear convention.
- `_t0`, keyed by `(workspace_id, time_group_key)` -- Slice 2's own
  event origin is one instant per COHERENT TIME DOMAIN (Time-Group
  architecture's own governing principle: "one waveform panel = one
  coherent time domain," never one shared instant across independent,
  unrelated time groups). `time_group_key` is a Time Group's own
  `group_id` (itself always the group's current origin source_id -- see
  `app.domain.time_grouping`'s own docstring for why groups are never
  given a separate, hardcoded identifier). `None`/absent for a given key
  means "no event origin selected yet for that time group," exactly
  like an unconfigured source's offset defaulting to `0.0` -- both are
  "nothing stored yet, resolve to the default" rather than a sentinel
  value stored explicitly.

This registry stores and serves these scalar values only -- it has no
opinion on which source is a time group's own origin (that is a derived
fact, computed on demand by `app.domain.time_grouping.derive_time_groups`
from `WorkspaceRegistry`'s own source metadata; see
`app.services.synchronization_service`) and it never touches waveform
data itself (see that module's own docstring for the full
request/response conversion flow, which lives entirely in the frontend
per DEC-042's own "presentation-layer transform, not a backend
authority" precedent).

**These two stores are deliberately independent, never bundled behind
one combined clear operation except at full workspace teardown** (Slice
2 task section 14: "synchronization reset and t=0 reset are
independent"). `remove_workspace()` below clears ONLY `_offsets` (used
by both "Reset All" alignment offsets AND, together with
`clear_all_t0_for_workspace()`, by the full workspace-lifecycle teardown
-- see `app.services.synchronization_service.reset_all_alignment_offsets()`
vs. `remove_workspace_synchronization_state()` for which call site uses
which combination).
"""

from __future__ import annotations

import threading


class SynchronizationRegistry:
    """Thread-safe, in-memory store of `manual_alignment_offset_s`
    (float) keyed by `(workspace_id, source_id)`, plus
    `t0_workspace_time` (float or absent) keyed by `(workspace_id,
    time_group_key)` -- see this module's own docstring for why these
    are two independent stores."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._offsets: dict[tuple[str, str], float] = {}
        self._t0: dict[tuple[str, str], float] = {}

    def get_offset(self, workspace_id: str, source_id: str) -> float:
        """Returns the stored offset, or `0.0` for an unconfigured/
        unknown source -- never `None`, since "no offset set" and "offset
        explicitly reset to zero" are the same observable state (a source
        with no synchronization state is, by definition, unshifted)."""
        with self._lock:
            return self._offsets.get((workspace_id, source_id), 0.0)

    def set_offset(self, workspace_id: str, source_id: str, alignment_offset_s: float) -> None:
        """Create-or-replace this source's own offset. Storing exactly
        `0.0` is equivalent to `reset_offset()` (both leave `get_offset()`
        returning `0.0`), but is intentionally NOT special-cased into a
        delete here -- the caller (app.services.synchronization_service)
        decides that policy; this layer is a plain key-value store."""
        with self._lock:
            self._offsets[(workspace_id, source_id)] = alignment_offset_s

    def reset_offset(self, workspace_id: str, source_id: str) -> bool:
        """Clears this source's own offset. Idempotent (returns `False`,
        not an error, for an already-unconfigured/unknown source_id) --
        matching this codebase's own established idempotent-DELETE
        convention (`PerUnitRegistry.delete()`)."""
        with self._lock:
            return self._offsets.pop((workspace_id, source_id), None) is not None

    def list_for_workspace(self, workspace_id: str) -> dict[str, float]:
        """Every EXPLICITLY-configured (non-default) offset in this
        workspace, `source_id -> alignment_offset_s`. A source with no
        entry here still has an effective offset of `0.0` via
        `get_offset()` -- callers building a full per-source view must
        still iterate the workspace's own real source list (see
        app.services.synchronization_service.list_source_alignments),
        never assume this dict alone is the complete source set."""
        with self._lock:
            return {sid: offset for (wid, sid), offset in self._offsets.items() if wid == workspace_id}

    def remove_source(self, workspace_id: str, source_id: str) -> bool:
        """Source-removal lifecycle hook (Slice 1 task section 10:
        "removing a source removes its synchronization state"). Identical
        behaviour to `reset_offset()` -- kept as a separate, semantically
        distinct entry point (mirroring `PerUnitRegistry.delete()` vs.
        its own callers) so a source-removal call site reads as removal,
        not as an engineer-initiated reset.

        Deliberately touches ONLY this source's own offset, never `_t0`
        (Slice 2 task section 15: "removing a non-reference source should
        not clear t=0... removing whichever source originally helped
        select t=0 should also not clear t=0, because t0 is a workspace
        coordinate once defined"). Time-Group architecture note: `_t0`
        IS now keyed in part by a source_id (a time group's own
        `origin_source_id`, see this module's own top-of-file
        docstring) -- removing a source that happens to BE some group's
        current origin does not retroactively delete that group's own
        t0 entry here; it simply becomes unreachable under the group's
        NEXT-recomputed `group_id` (a different member may now be
        earliest) until the engineer sets a new t0 for the
        now-differently-keyed group. This is a deliberate, documented
        consequence of groups being recomputed fresh rather than
        permanently assigned (task section 23), not a leak: the
        orphaned entry is still eventually cleared by
        `clear_all_t0_for_workspace()` at full workspace teardown."""
        with self._lock:
            return self._offsets.pop((workspace_id, source_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Reset All" alignment-offsets counterpart -- releases every
        offset this workspace owns. Deliberately touches ONLY `_offsets`,
        never `_t0` (Slice 2 task section 14: "synchronization reset and
        t=0 reset are independent") -- resetting every source to zero and
        deleting every stored offset entry are the same observable state,
        so `reset_all_alignment_offsets()` reuses this method rather than
        duplicating it (see app.services.synchronization_service), and
        that reuse is exactly why this method must never also touch
        `_t0`. Full workspace-lifecycle teardown ("Start New Workspace")
        needs BOTH this method AND `clear_all_t0_for_workspace()` called
        together -- see
        `app.services.synchronization_service.remove_workspace_synchronization_state()`,
        the one place that combination is made, deliberately not here."""
        with self._lock:
            keys = [key for key in self._offsets if key[0] == workspace_id]
            for key in keys:
                del self._offsets[key]
            return len(keys)

    def count(self) -> int:
        """Total configured (non-default) alignment offsets across every
        workspace -- `_t0` is intentionally not included; it has no
        directly analogous "how many are configured" caller today."""
        with self._lock:
            return len(self._offsets)

    # ------------------------------------------------------------
    # Slice 2: event origin (t0), Time-Group-scoped
    # ------------------------------------------------------------

    def get_t0(self, workspace_id: str, time_group_key: str) -> float | None:
        """Returns the stored event origin for THIS time group only, or
        `None` if this group has never had one selected (or it was
        cleared) -- never `0.0` as a silent default, unlike
        `get_offset()`'s own "unconfigured means zero" convention: an
        offset of `0.0` and "no offset configured" are the same
        observable state, but a workspace-time instant of exactly `0.0`
        is a perfectly legitimate, deliberately-chosen event origin,
        indistinguishable from "none selected" if this also defaulted to
        `0.0`. Setting t0 in one time group never touches another
        group's own key (Time-Group architecture's own governing
        principle: independent coherent time domains, task section 24)."""
        with self._lock:
            return self._t0.get((workspace_id, time_group_key))

    def set_t0(self, workspace_id: str, time_group_key: str, t0_workspace_time: float) -> None:
        """Create-or-replace THIS time group's own event origin."""
        with self._lock:
            self._t0[(workspace_id, time_group_key)] = t0_workspace_time

    def clear_t0(self, workspace_id: str, time_group_key: str) -> bool:
        """Removes THIS time group's own event origin ("Clear t=0",
        Slice 2 task section 13). Idempotent (returns `False`, not an
        error, if no event origin was ever set for this group) -- same
        established idempotent-DELETE convention as `reset_offset()`.
        Deliberately touches ONLY `_t0`, never `_offsets` (task section
        13: "Clear t=0 ... preserve all source synchronization
        offsets"), and ONLY this one group's own key, never another
        group's."""
        with self._lock:
            return self._t0.pop((workspace_id, time_group_key), None) is not None

    def clear_all_t0_for_workspace(self, workspace_id: str) -> int:
        """Full workspace-lifecycle teardown counterpart to
        `remove_workspace()` below -- releases EVERY time group's own
        event origin in this workspace at once (there is no longer a
        single `workspace_id`-only key to pop, now that t0 is
        Time-Group-scoped). Returns the count cleared, for
        logging/testing only, mirroring `remove_workspace()`'s own
        return-count convention."""
        with self._lock:
            keys = [key for key in self._t0 if key[0] == workspace_id]
            for key in keys:
                del self._t0[key]
            return len(keys)
