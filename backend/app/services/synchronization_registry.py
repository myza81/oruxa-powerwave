"""In-memory, ephemeral, workspace-scoped alignment-offset registry
(Slice 1 of waveform time synchronization).

A sibling registry to `WorkspaceRegistry`/`PerUnitRegistry` (same
`threading.Lock` + `dict[(workspace_id, id), T]` shape -- see those
modules' own docstrings for the shared locking-policy rationale,
unchanged here). Keyed by `(workspace_id, source_id)` -- an alignment
offset IS the source's own synchronization metadata, 1:1, exactly like
`PerUnitRegistry`'s own per-source configuration (never a separately
identified "profile").

Only NON-ZERO/explicitly-set offsets are stored: an unconfigured source
has no entry at all, and `get_offset()` returns `0.0` for it -- this
keeps "every source starts unshifted" free (no need to pre-populate an
entry per source on upload) and makes "reset" a plain delete, mirroring
`PerUnitRegistry.delete()`'s own idempotent-clear convention.

This registry stores and serves the scalar offset only -- it has no
opinion on which source is the reference (that is a derived fact,
computed on demand from `WorkspaceRegistry`'s own `created_at` ordering;
see `app.domain.synchronization.reference_source_id_for_workspace` and
`app.services.synchronization_service`) and it never touches waveform
data itself (see that module's own docstring for the full
request/response conversion flow, which lives entirely in the frontend
per DEC-042's own "presentation-layer transform, not a backend
authority" precedent).
"""

from __future__ import annotations

import threading


class SynchronizationRegistry:
    """Thread-safe, in-memory store of `alignment_offset_s` (float)
    keyed by `(workspace_id, source_id)`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._offsets: dict[tuple[str, str], float] = {}

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
        """Source-removal lifecycle hook (task section 10: "removing a
        source removes its synchronization state"). Identical behaviour
        to `reset_offset()` -- kept as a separate, semantically distinct
        entry point (mirroring `PerUnitRegistry.delete()` vs. its own
        callers) so a source-removal call site reads as removal, not as
        an engineer-initiated reset."""
        with self._lock:
            return self._offsets.pop((workspace_id, source_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every offset
        this workspace owns. Also used as "Reset All" alignment offsets
        within a still-live workspace (task section 10): resetting every
        source to zero and deleting every stored entry are the same
        observable state, so `reset_all` reuses this method rather than
        duplicating it (see app.services.synchronization_service)."""
        with self._lock:
            keys = [key for key in self._offsets if key[0] == workspace_id]
            for key in keys:
                del self._offsets[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._offsets)
