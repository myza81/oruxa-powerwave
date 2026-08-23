"""In-memory, ephemeral, workspace-scoped Current Measurement Group base
configuration registry (Slice 4 of DEC-050's measurement-group-aware
Per-Unit redesign).

Mirrors `VoltageGroupConfigRegistry`'s own exact shape (`upsert`/`get`/
`delete`/`list_for_workspace`/`remove_workspace`/`count`, same
`(workspace_id, measurement_group_id)` keying, same lock-scoping policy,
same no-defensive-copy convention since the service layer always
reads-modifies-writes a full object per operation) rather than inventing
a new registry convention -- see that module's own docstring for the
full reasoning, not repeated here.

A separate, sibling registry from `MeasurementGroupRegistry` AND from
`VoltageGroupConfigRegistry` (never a field on either) -- see
`app.domain.current_group_config`'s own module docstring for why: a
Voltage-kind group must never carry a Current-only field, and this
registry structurally guarantees that (a Voltage group's id simply never
has an entry here, enforced by the service layer refusing to `upsert()`
one -- see `app.services.current_group_config_service`).

Lifecycle: removing this configuration when its owning `MeasurementGroup`
is deleted (individually, via source removal, or via workspace removal)
is the caller's responsibility, mirroring exactly how
`voltage_group_config_registry.delete()`/`remove_workspace()` are driven
from `app.services.measurement_group_service`/`app.api.v1.sources`/
`app.api.v1.workspaces` today.
"""

from __future__ import annotations

import threading

from app.domain.current_group_config import CurrentBaseConfiguration


class CurrentGroupConfigRegistry:
    """Thread-safe, in-memory store of CurrentBaseConfiguration keyed by
    (workspace_id, measurement_group_id). See module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[tuple[str, str], CurrentBaseConfiguration] = {}

    def upsert(self, config: CurrentBaseConfiguration) -> None:
        """Create-or-replace this group's own configuration entirely --
        no partial-update concept at this layer, mirroring
        `VoltageGroupConfigRegistry.upsert()`'s own full-replace
        convention."""
        with self._lock:
            self._configs[(config.workspace_id, config.measurement_group_id)] = config

    def get(self, workspace_id: str, measurement_group_id: str) -> CurrentBaseConfiguration | None:
        with self._lock:
            return self._configs.get((workspace_id, measurement_group_id))

    def list_for_workspace(self, workspace_id: str) -> list[CurrentBaseConfiguration]:
        with self._lock:
            return [config for (wid, _gid), config in self._configs.items() if wid == workspace_id]

    def delete(self, workspace_id: str, measurement_group_id: str) -> bool:
        """Idempotent -- returns `False`, not an error, for a group with
        no configuration yet, matching this codebase's own established
        idempotent-DELETE convention."""
        with self._lock:
            return self._configs.pop((workspace_id, measurement_group_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every
        configuration owned by `workspace_id`. Safe and idempotent for a
        workspace with no current-group configurations."""
        with self._lock:
            keys = [key for key in self._configs if key[0] == workspace_id]
            for key in keys:
                del self._configs[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._configs)
