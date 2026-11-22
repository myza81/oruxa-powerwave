"""In-memory, ephemeral, workspace-scoped store for measurement-side CONFIGURATION (D5A-2B2A, D5A-UI-002).

Holds only what an engineer decided, never the recording's own evidence (that stays on the source's
channels, untouched) and never a per-group copy of the Level 1 default:

* a Level 1 correction per `(workspace_id, source_id)`;
* a Level 2 override per `(workspace_id, source_id, measurement_group_id)` -- one value for the whole Voltage or
  Current Measurement Group. The Voltage and the Current group of one bay are separate groups, so they are
  separate entries; nothing here is shared by an Engineering Context.

Same lifetime and keying as the other sibling registries (no persistence; cleared with the workspace, the
source, or the group it belongs to). Records are frozen, so nothing aliases a caller's object.
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
class GroupSideOverride:
    side: str
    set_at: datetime


class MeasurementSideRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording: dict[tuple[str, str], RecordingSideCorrection] = {}
        self._group: dict[tuple[str, str, str], GroupSideOverride] = {}

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

    # ---- Level 2 (one Measurement Group of one recording) ----
    def get_group(self, workspace_id: str, source_id: str, group_id: str) -> GroupSideOverride | None:
        with self._lock:
            return self._group.get((workspace_id, source_id, group_id))

    def set_group(self, workspace_id: str, source_id: str, group_id: str, override: GroupSideOverride) -> None:
        with self._lock:
            self._group[(workspace_id, source_id, group_id)] = override

    def clear_group(self, workspace_id: str, source_id: str, group_id: str) -> bool:
        with self._lock:
            return self._group.pop((workspace_id, source_id, group_id), None) is not None

    def group_keys(self, workspace_id: str) -> list[tuple[str, str]]:
        """(source_id, group_id) of every stored override in this workspace."""
        with self._lock:
            return [(sid, gid) for (wid, sid, gid) in self._group if wid == workspace_id]

    # ---- lifecycle ----
    def remove_source(self, workspace_id: str, source_id: str) -> bool:
        """The recording's correction and every group override that was scoped to this recording."""
        with self._lock:
            removed = self._recording.pop((workspace_id, source_id), None) is not None
            keys = [k for k in self._group if k[0] == workspace_id and k[1] == source_id]
            for key in keys:
                del self._group[key]
            return removed or bool(keys)

    def remove_workspace(self, workspace_id: str) -> int:
        with self._lock:
            recording = [k for k in self._recording if k[0] == workspace_id]
            group = [k for k in self._group if k[0] == workspace_id]
            for key in recording:
                del self._recording[key]
            for key in group:
                del self._group[key]
            return len(recording) + len(group)

    def count(self) -> int:
        with self._lock:
            return len(self._recording) + len(self._group)
