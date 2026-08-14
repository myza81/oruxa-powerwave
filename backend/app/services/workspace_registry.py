"""In-memory, ephemeral workspace/source metadata registry.

This is Phase 1's entire "persistence" layer, and deliberately so: the
owner decided oruxa_powerwave must not persistently retain uploaded
disturbance-record files (see docs/project-memory/MIGRATION_PLAN.md's
Critical New Storage Decision, recorded this phase). Nothing here writes to
disk, a database, or StorageBackend -- entries live only in this process's
memory for the life of the workspace, and are gone on process restart.
That's intentional: "session ends -> server-side event-record data
released" is the target lifecycle, not a limitation to work around.

State is scoped by (workspace_id, source_id), never a bare process-global
"current record" -- see DECISIONS.md DEC-012. One WorkspaceRegistry
instance is created per process (app.state.workspace_registry, wired in
app.main) and injected via FastAPI's dependency system, mirroring the
existing app.state.storage pattern.

Known Phase 1 limitations, explicitly out of scope per
docs/project-memory/MIGRATION_PLAN.md Sec 28 ("workspace lifecycle
management" is deferred):
  - No automatic expiry/TTL -- entries live until explicitly DELETEd or the
    process restarts.
  - Single-process only -- does not survive a multi-worker deployment
    (each worker would have its own registry). Acceptable for the Phase 1
    MVP; revisit if/when this ships behind more than one worker process.
"""

from __future__ import annotations

import threading

from app.domain.source import SourceMetadata


class WorkspaceRegistry:
    """Thread-safe, in-memory store of SourceMetadata keyed by (workspace_id, source_id)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[tuple[str, str], SourceMetadata] = {}

    def add(self, source: SourceMetadata) -> None:
        with self._lock:
            self._sources[(source.workspace_id, source.source_id)] = source

    def get(self, workspace_id: str, source_id: str) -> SourceMetadata | None:
        with self._lock:
            return self._sources.get((workspace_id, source_id))

    def list_for_workspace(self, workspace_id: str) -> list[SourceMetadata]:
        with self._lock:
            return [
                source
                for (wid, _sid), source in self._sources.items()
                if wid == workspace_id
            ]

    def remove(self, workspace_id: str, source_id: str) -> bool:
        """Release a source's metadata. Returns True if it existed."""
        with self._lock:
            return self._sources.pop((workspace_id, source_id), None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._sources)
