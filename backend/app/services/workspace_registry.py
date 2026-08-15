"""In-memory, ephemeral workspace/source registry.

This is Phase 1's entire "persistence" layer, and deliberately so: the
owner decided oruxa_powerwave must not persistently retain uploaded
disturbance-record *files* (see docs/project-memory/MIGRATION_PLAN.md's
Critical New Storage Decision, recorded that phase; unaffected by Phase
2A below). Nothing here writes to disk, a database, or StorageBackend --
entries live only in this process's memory for the life of the workspace,
and are gone on process restart. That's intentional: "session ends ->
server-side event-record data released" is the target lifecycle, not a
limitation to work around.

Phase 2A update (DEC-019): this registry now stores `ActiveSource`
(app.domain.source), not bare `SourceMetadata` -- it pairs the same
lightweight metadata Phase 1 always served with the authoritative,
full-resolution `DisturbanceRecord` a waveform range request needs, so
that request never has to re-parse the COMTRADE file. The *keying,
ownership, and cleanup model below did not need to change at all* for
this -- `remove()`/`remove_workspace()` already correctly drop the only
reference this process holds to whatever object is stored per
`(workspace_id, source_id)`, whether that object is metadata alone or
metadata-plus-record. See app.domain.source.ActiveSource's own docstring.

State is scoped by (workspace_id, source_id), never a bare process-global
"current record" -- see DECISIONS.md DEC-012. One WorkspaceRegistry
instance is created per process (app.state.workspace_registry, wired in
app.main) and injected via FastAPI's dependency system, mirroring the
existing app.state.storage pattern.

Known Phase 1 limitations, explicitly out of scope per
docs/project-memory/MIGRATION_PLAN.md Sec 28 ("workspace lifecycle
management" is deferred):
  - No automatic expiry/TTL for an *abandoned* workspace (browser tab closed,
    network lost, no reset ever clicked) -- those entries live until the
    process restarts. Explicit cleanup, via either a single source's DELETE
    or the whole workspace's DELETE, is immediate and does not wait for a
    restart -- see DEC-018 (docs/project-memory/DECISIONS.md).
  - Single-process only -- does not survive a multi-worker deployment
    (each worker would have its own registry). Acceptable for the Phase 1
    MVP; revisit if/when this ships behind more than one worker process.
"""

from __future__ import annotations

import threading

from app.domain.source import ActiveSource


class WorkspaceRegistry:
    """Thread-safe, in-memory store of ActiveSource keyed by (workspace_id, source_id).

    Locking policy (Phase 2A, unchanged pattern from Phase 1, just now
    guarding a larger stored value): the lock is held only long enough to
    read or mutate the dict itself. Callers that need to do real work
    against a retrieved `ActiveSource` (e.g. app.services.waveform_service
    extracting/reducing a range) do so *after* `get()` has returned and
    released the lock -- a slow waveform computation must never hold this
    lock and block unrelated requests. If a concurrent `remove()`/
    `remove_workspace()` happens after a caller's `get()` already returned
    a reference, that caller's in-flight work safely continues against the
    object it already holds (ordinary Python reference semantics -- the
    dict entry being dropped does not affect an already-retrieved
    reference); a *subsequent* `get()` for the same key correctly sees it
    gone.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[tuple[str, str], ActiveSource] = {}

    def add(self, source: ActiveSource) -> None:
        with self._lock:
            self._sources[(source.metadata.workspace_id, source.metadata.source_id)] = source

    def get(self, workspace_id: str, source_id: str) -> ActiveSource | None:
        with self._lock:
            return self._sources.get((workspace_id, source_id))

    def list_for_workspace(self, workspace_id: str) -> list[ActiveSource]:
        with self._lock:
            return [
                source
                for (wid, _sid), source in self._sources.items()
                if wid == workspace_id
            ]

    def remove(self, workspace_id: str, source_id: str) -> bool:
        """Release a source (metadata + its authoritative record). Returns True if it existed."""
        with self._lock:
            return self._sources.pop((workspace_id, source_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """Release every source owned by ``workspace_id``.

        This is the backend counterpart of the frontend's "Start new
        workspace" action (DEC-018) -- a distinct, whole-workspace operation
        from ``remove()``'s single-source scope. Deleting the dict entries
        drops the only references this process holds to those
        ``ActiveSource`` objects -- since Phase 2A (DEC-019), that includes
        each source's full-resolution ``DisturbanceRecord``, not just its
        lightweight metadata -- making them eligible for normal Python
        garbage collection; no separate "release" step is needed beyond
        that. Safe and idempotent for a workspace with no sources (an
        already-empty or entirely unknown ``workspace_id``): there is
        nothing to raise an error about, since a workspace is never
        explicitly "created" server-side in the first place (see
        app.api.v1.sources) -- it is just a key that may or may not have
        entries under it. Returns the number of sources actually removed,
        for logging/testing, not for any success/failure branching by the
        caller.
        """
        with self._lock:
            keys = [key for key in self._sources if key[0] == workspace_id]
            for key in keys:
                del self._sources[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._sources)
