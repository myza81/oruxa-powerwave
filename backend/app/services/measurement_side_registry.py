"""In-memory, ephemeral, workspace-scoped store for D5A-2B2A measurement-side CONFIGURATION.

Holds only what an engineer decided, never the recording's own evidence (that stays on the source's
channels, untouched) and never a per-bay copy of the Level 1 default:

* a Level 1 correction per `(workspace_id, source_id)`;
* a Level 2 override per `(workspace_id, engineering_context_id)`.

Same lifetime and keying as the other sibling registries (no persistence; cleared with the workspace, the
source, or the bay it belongs to). Records are frozen, so nothing aliases a caller's object.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecordingSideCorrection:
    side: str
    note: str | None
    set_at: datetime


@dataclass(frozen=True, slots=True)
class BaySideOverride:
    side: str
    set_at: datetime


class MeasurementSideRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording: dict[tuple[str, str], RecordingSideCorrection] = {}
        self._bay: dict[tuple[str, str], BaySideOverride] = {}

    # ---- Level 1 ----
    def get_recording(self, workspace_id: str, source_id: str) -> RecordingSideCorrection | None:
        with self._lock:
            return self._recording.get((workspace_id, source_id))

    def set_recording(self, workspace_id: str, source_id: str, correction: RecordingSideCorrection) -> None:
        with self._lock:
            self._recording[(workspace_id, source_id)] = correction

    def clear_recording(self, workspace_id: str, source_id: str) -> bool:
        with self._lock:
            return self._recording.pop((workspace_id, source_id), None) is not None

    # ---- Level 2 ----
    def get_bay(self, workspace_id: str, context_id: str) -> BaySideOverride | None:
        with self._lock:
            return self._bay.get((workspace_id, context_id))

    def set_bay(self, workspace_id: str, context_id: str, override: BaySideOverride) -> None:
        with self._lock:
            self._bay[(workspace_id, context_id)] = override

    def clear_bay(self, workspace_id: str, context_id: str) -> bool:
        with self._lock:
            return self._bay.pop((workspace_id, context_id), None) is not None

    def bay_context_ids(self, workspace_id: str) -> list[str]:
        with self._lock:
            return [cid for (wid, cid) in self._bay if wid == workspace_id]

    # ---- lifecycle ----
    def remove_source(self, workspace_id: str, source_id: str) -> bool:
        return self.clear_recording(workspace_id, source_id)

    def remove_workspace(self, workspace_id: str) -> int:
        with self._lock:
            recording = [k for k in self._recording if k[0] == workspace_id]
            bay = [k for k in self._bay if k[0] == workspace_id]
            for key in recording:
                del self._recording[key]
            for key in bay:
                del self._bay[key]
            return len(recording) + len(bay)

    def count(self) -> int:
        with self._lock:
            return len(self._recording) + len(self._bay)
