"""In-memory, ephemeral, workspace-scoped Calculated Channel registry
(Phase 5A, DEC-047).

Deliberately a SEPARATE registry object from `WorkspaceRegistry`
(app.services.workspace_registry), not a field bolted onto it -- source
metadata/records and calculated-channel definitions are different kinds
of workspace-owned resources with different lifecycles (a calculated
channel additionally depends on OTHER calculated channels and must be
cascade-cleaned when its own grounding source is removed -- see
app.services.calculated_channel_service.remove_calculated_channels_for_source).
Mirrors `WorkspaceRegistry`'s own exact shape (`add`/`get`/
`list_for_workspace`/`remove`/`remove_workspace`/`count`, same
`(workspace_id, id)` keying, same lock-scoping policy) rather than
inventing a second registry convention -- see that module's own
docstring for the full locking-policy rationale, unchanged here.

Wired into `app.state.calculated_channel_registry` in app.main, and into
`DELETE /api/v1/workspaces/{workspace_id}`'s existing "one lifecycle hook
to plug into" (see app.api.v1.workspaces's own module docstring, which
explicitly anticipated calculated channels as a future workspace-owned
resource) -- so "Start New Workspace" clears calculated channels through
the SAME endpoint it always used, never a second whole-workspace-reset
path.
"""

from __future__ import annotations

import threading

from app.domain.calculated_channel import CalculatedChannel


class CalculatedChannelRegistry:
    """Thread-safe, in-memory store of CalculatedChannel keyed by
    (workspace_id, calculated_channel_id). See module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[tuple[str, str], CalculatedChannel] = {}

    def add(self, channel: CalculatedChannel) -> None:
        with self._lock:
            self._channels[(channel.workspace_id, channel.id)] = channel

    def get(self, workspace_id: str, calculated_channel_id: str) -> CalculatedChannel | None:
        with self._lock:
            return self._channels.get((workspace_id, calculated_channel_id))

    def list_for_workspace(self, workspace_id: str) -> list[CalculatedChannel]:
        with self._lock:
            return [
                channel
                for (wid, _cid), channel in self._channels.items()
                if wid == workspace_id
            ]

    def remove(self, workspace_id: str, calculated_channel_id: str) -> bool:
        with self._lock:
            return self._channels.pop((workspace_id, calculated_channel_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every calculated
        channel owned by `workspace_id` (definition + its retained
        full-resolution arrays), dropping this process's only reference to
        them so they become eligible for normal garbage collection. Safe
        and idempotent for a workspace with no calculated channels."""
        with self._lock:
            keys = [key for key in self._channels if key[0] == workspace_id]
            for key in keys:
                del self._channels[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._channels)
