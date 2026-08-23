"""In-memory, ephemeral, workspace-scoped Voltage Measurement Group base
configuration registry (Slice 3 of DEC-050's measurement-group-aware
Per-Unit redesign).

Mirrors `PerUnitRegistry`'s own exact shape (`upsert`/`get`/`delete`/
`list_for_workspace`/`remove_workspace`/`count`, same `(workspace_id,
id)` keying, same lock-scoping policy) rather than inventing a new
registry convention -- here keyed by `(workspace_id,
measurement_group_id)` since a `VoltageBaseConfiguration` is owned 1:1
by its measurement group, the same "configuration IS the owner's own
configuration" relationship `PerUnitRegistry` already established for
`source_id`.

A separate, sibling registry from `MeasurementGroupRegistry` itself
(never a field on `MeasurementGroup`) -- see
`app.domain.voltage_group_config`'s own module docstring for why: a
Current-kind group must never carry a Voltage-only field, and this
registry structurally guarantees that (a Current group's id simply
never has an entry here, enforced by the service layer refusing to
`upsert()` one -- see `app.services.voltage_group_config_service`).

Lifecycle: removing this configuration when its owning `MeasurementGroup`
is deleted (individually, via source removal, or via workspace removal)
is the caller's responsibility, mirroring exactly how
`per_unit_registry.delete()`/`remove_workspace()` are driven from
`app.api.v1.sources`/`app.api.v1.workspaces` today -- see
`app.services.measurement_group_service`'s own updated
`delete_group()`/`remove_measurement_groups_for_source()` and
`app.main`'s lifespan wiring for the workspace-removal path.
"""

from __future__ import annotations

import threading

from app.domain.voltage_group_config import VoltageBaseConfiguration


class VoltageGroupConfigRegistry:
    """Thread-safe, in-memory store of VoltageBaseConfiguration keyed by
    (workspace_id, measurement_group_id). See module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[tuple[str, str], VoltageBaseConfiguration] = {}

    def upsert(self, config: VoltageBaseConfiguration) -> None:
        """Create-or-replace this group's own configuration entirely --
        no partial-update concept at this layer (the service layer
        reads-modifies-writes a full object for each of its own
        distinct operations), mirroring `PerUnitRegistry.upsert()`'s own
        full-replace convention."""
        with self._lock:
            self._configs[(config.workspace_id, config.measurement_group_id)] = config

    def get(self, workspace_id: str, measurement_group_id: str) -> VoltageBaseConfiguration | None:
        with self._lock:
            return self._configs.get((workspace_id, measurement_group_id))

    def list_for_workspace(self, workspace_id: str) -> list[VoltageBaseConfiguration]:
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
        workspace with no voltage-group configurations."""
        with self._lock:
            keys = [key for key in self._configs if key[0] == workspace_id]
            for key in keys:
                del self._configs[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._configs)
