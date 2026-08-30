"""In-memory, ephemeral registry of CSV/Excel preparation sessions
(Slice 1, DEC-072).

Deliberately mirrors `app.services.workspace_registry.WorkspaceRegistry`
exactly -- same locking policy, same keying, same lifecycle semantics --
because that registry already establishes exactly the pattern DEC-072
point 3 approved for this feature (a hybrid, reference-holding
`PreparationSession`, held only in process memory, never written to
disk). Choosing `StorageBackend`'s dormant `"working"` category instead
was considered and rejected for Slice 1: `StorageBackend` has no delete
capability at all (`write_text`/`write_bytes`/`read_text`/`read_bytes`/
`exists`/`list` only -- see backend/app/storage.py), so using it here
would either need a new deletion capability added to that abstraction
(a bigger change than this slice's own scope) or leave orphaned files
with no cleanup path, which would directly violate the "cleanup occurs
on removal" requirement. An in-memory sibling registry needs neither --
this is the "smallest compatible design" that specific tension leaves
available at this workspace-memory scale (raw CSV bytes only, not a
parsed DataFrame).

Nothing here writes to disk, a database, or StorageBackend -- entries
live only in this process's memory for the life of the active
preparation session, and are gone on process restart. This is the same
"temporary, session-scoped, never durable" guarantee DEC-072 point 1
approved -- explicitly NOT a reopening of DEC-015 (uploaded event files
are never persistently retained): no file is ever written to a
persistent location, and a `PreparationSession` is released exactly when
its owning source or workspace is removed, exactly like
`WorkspaceRegistry` already does for `ActiveSource`.

Known limitation, same as `WorkspaceRegistry`'s own disclosed one: no
automatic TTL/expiry for an abandoned preparation session (browser tab
closed, no explicit remove/workspace-reset ever happens) -- those
entries live until the process restarts. Explicit cleanup (a single
source's DELETE, or the whole workspace's DELETE) is immediate. Single-
process only -- does not survive a multi-worker deployment.
"""

from __future__ import annotations

import threading

from app.domain.preparation_session import PreparationSession


class PreparationSessionRegistry:
    """Thread-safe, in-memory store of PreparationSession keyed by (workspace_id, source_id)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[tuple[str, str], PreparationSession] = {}

    def add(self, session: PreparationSession) -> None:
        with self._lock:
            self._sessions[(session.summary.workspace_id, session.summary.source_id)] = session

    def get(self, workspace_id: str, source_id: str) -> PreparationSession | None:
        with self._lock:
            return self._sessions.get((workspace_id, source_id))

    def list_for_workspace(self, workspace_id: str) -> list[PreparationSession]:
        with self._lock:
            return [
                session
                for (wid, _sid), session in self._sessions.items()
                if wid == workspace_id
            ]

    def remove(self, workspace_id: str, source_id: str) -> bool:
        """Release a preparation session. Returns True if it existed."""
        with self._lock:
            return self._sessions.pop((workspace_id, source_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """Release every preparation session this workspace owns.

        The preparation-source counterpart of the frontend's "Start new
        workspace" action -- wired into the SAME whole-workspace
        lifecycle hook `app.api.v1.workspaces.delete_workspace` already
        uses for every other sibling registry. Safe and idempotent for a
        workspace with no preparation sessions. Returns the number of
        sessions actually removed.
        """
        with self._lock:
            keys = [key for key in self._sessions if key[0] == workspace_id]
            for key in keys:
                del self._sessions[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
