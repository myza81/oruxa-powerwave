"""In-memory, ephemeral, workspace-scoped Event Reconstruction registry
(DEC-123/DEC-124).

A sibling of `SynchronizationRegistry`/`PerUnitRegistry` (same
`threading.Lock` + dict shape). It stores one
`EventReconstructionDefinition` per workspace -- analysis state only:
selected members (membership fingerprint, confirmed source ids, manual
correction) and the reference member. Never source data, never rewritten
timestamps, never channel presentation, and never anything belonging to
`SynchronizationRegistry`.

Whether a member is still current or stale is NOT stored here: it is
derived on every read by app.services.event_reconstruction_service from
the workspace's current Time Groups, so a source change can never leave
a stale flag out of date.
"""

from __future__ import annotations

import threading

from app.domain.event_reconstruction import EventReconstructionDefinition


class EventReconstructionRegistry:
    """Thread-safe store of one `EventReconstructionDefinition` per
    `workspace_id`. Definitions are frozen dataclasses, so returning the
    stored object never exposes mutable internals."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._definitions: dict[str, EventReconstructionDefinition] = {}

    def get(self, workspace_id: str) -> EventReconstructionDefinition | None:
        with self._lock:
            return self._definitions.get(workspace_id)

    def put(self, workspace_id: str, definition: EventReconstructionDefinition) -> None:
        """Create-or-replace this workspace's definition."""
        with self._lock:
            self._definitions[workspace_id] = definition

    def remove_workspace(self, workspace_id: str) -> bool:
        """Clears this workspace's definition. Idempotent: `False`, not
        an error, when none exists. Used both for an explicit "clear
        reconstruction" and for workspace teardown."""
        with self._lock:
            return self._definitions.pop(workspace_id, None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._definitions)
