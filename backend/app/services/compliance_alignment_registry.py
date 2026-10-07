"""In-memory, ephemeral, workspace-scoped store for the Compliance Event
Alignment (DEC-170). Mirrors the other workspace registries' shape
(`ReferenceLayerRegistry`, `MeasurementGroupRegistry`): thread-safe,
`(workspace_id)`-keyed, cleared by `DELETE /api/v1/workspaces/{id}` ("Start New
Workspace") and never persisted.

One alignment per workspace: it belongs to the currently selected Compliance
measurement context, so setting it for another Bay / Measurement Group REPLACES
it (the old timestamp may not apply to the new recording's time base). It is
deliberately NOT part of `SynchronizationRegistry` -- Compliance alignment and
Waveform t0 share no state.
"""

from __future__ import annotations

import threading

from app.domain.compliance_alignment import ComplianceAlignment


class ComplianceAlignmentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_workspace: dict[str, ComplianceAlignment] = {}

    def get(self, workspace_id: str) -> ComplianceAlignment | None:
        with self._lock:
            return self._by_workspace.get(workspace_id)

    def set(self, alignment: ComplianceAlignment) -> None:
        with self._lock:
            self._by_workspace[alignment.workspace_id] = alignment

    def clear(self, workspace_id: str) -> bool:
        with self._lock:
            return self._by_workspace.pop(workspace_id, None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        return 1 if self.clear(workspace_id) else 0

    def count(self) -> int:
        with self._lock:
            return len(self._by_workspace)
