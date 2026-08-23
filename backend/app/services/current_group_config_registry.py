"""In-memory, ephemeral, workspace-scoped Current Measurement Group base
configuration registry (Slice 4 of DEC-050's measurement-group-aware
Per-Unit redesign).

Mirrors `VoltageGroupConfigRegistry`'s own exact shape (`upsert`/`get`/
`delete`/`list_for_workspace`/`remove_workspace`/`count`, same
`(workspace_id, measurement_group_id)` keying, same lock-scoping policy)
rather than inventing a new registry convention -- see that module's own
docstring for the full reasoning, not repeated here.

**Copy-on-boundary (Slice 4 robustness follow-up, post-review)**: unlike
`VoltageGroupConfigRegistry` (which still relies on the service layer's
own read-modify-write discipline never leaking a stored reference), this
registry defensively copies `CurrentBaseConfiguration` on every boundary
crossing -- `upsert()` copies the object it is handed before storing it,
and `get()`/`list_for_workspace()` copy the object they return -- the
same "registry owns its own state, never aliases a caller's object"
principle `MeasurementGroupRegistry`'s own `_copy_group()` already
established (see that module's docstring). `CurrentBaseConfiguration`
has no mutable container fields (every field is a plain `str | float |
None`), so a flat `dataclasses.replace()` is a complete, correct copy --
no nested-container special-casing is needed the way
`MeasurementGroupRegistry._copy_group()` needs for its own `channel_refs`
list. This makes the registry robust against a caller mutating an
object after `upsert()`, after `get()`, or after `list_for_workspace()`
-- including a service-layer caller's own local variable returned
onward to ITS OWN caller (e.g. `current_group_config_service.set_current_base_manual()`'s
return value), since that returned object is never the same instance the
registry stored in the first place. This is intentionally scoped
narrowly to `CurrentGroupConfigRegistry` -- `VoltageGroupConfigRegistry`
carries the identical latent weakness but is explicitly out of scope for
this follow-up (see this task's own final report for why it was flagged,
not fixed, here).

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
from dataclasses import replace

from app.domain.current_group_config import CurrentBaseConfiguration


def _copy_config(config: CurrentBaseConfiguration) -> CurrentBaseConfiguration:
    """A flat `replace()` is a complete, independent copy -- every field
    on `CurrentBaseConfiguration` is a plain scalar (`str | float |
    None`), never a mutable container, so there is nothing further to
    deep-copy the way `MeasurementGroupRegistry._copy_config()`'s own
    `channel_refs` list requires."""
    return replace(config)


class CurrentGroupConfigRegistry:
    """Thread-safe, in-memory store of CurrentBaseConfiguration keyed by
    (workspace_id, measurement_group_id). See module docstring for the
    copy-on-boundary guarantee every method below upholds."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[tuple[str, str], CurrentBaseConfiguration] = {}

    def upsert(self, config: CurrentBaseConfiguration) -> None:
        """Create-or-replace this group's own configuration entirely --
        no partial-update concept at this layer, mirroring
        `VoltageGroupConfigRegistry.upsert()`'s own full-replace
        convention. Stores a defensive COPY of `config`, never the
        caller's own object -- the caller mutating its own reference
        after this call returns has no effect on registry state."""
        with self._lock:
            self._configs[(config.workspace_id, config.measurement_group_id)] = _copy_config(config)

    def get(self, workspace_id: str, measurement_group_id: str) -> CurrentBaseConfiguration | None:
        """Returns a defensive COPY of the stored configuration -- the
        caller mutating the returned object has no effect on registry
        state."""
        with self._lock:
            config = self._configs.get((workspace_id, measurement_group_id))
            return _copy_config(config) if config is not None else None

    def list_for_workspace(self, workspace_id: str) -> list[CurrentBaseConfiguration]:
        """Returns defensive COPIES -- same guarantee as `get()`."""
        with self._lock:
            return [_copy_config(config) for (wid, _gid), config in self._configs.items() if wid == workspace_id]

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
