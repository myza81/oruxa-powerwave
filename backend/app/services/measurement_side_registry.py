"""In-memory, ephemeral, workspace-scoped store for D5A-2B2A measurement-side CONFIGURATION.

Holds only what an engineer decided, never the recording's own evidence (that stays on the source's
channels, untouched) and never a per-bay copy of the Level 1 default:

* a Level 1 correction per `(workspace_id, source_id)`;
* a Level 2 override per `(workspace_id, engineering_context_id, source_id)`.

A bay (Engineering Context) may contain channels of several recordings, each possibly on a different side.
A Level 2 setting therefore belongs to the bay *within one recording* -- it never reinterprets another
recording's channels of the same bay.

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
        self._bay: dict[tuple[str, str, str], BaySideOverride] = {}

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

    # ---- Level 2 (bay within one recording) ----
    def get_bay(self, workspace_id: str, context_id: str, source_id: str) -> BaySideOverride | None:
        with self._lock:
            return self._bay.get((workspace_id, context_id, source_id))

    def set_bay(self, workspace_id: str, context_id: str, source_id: str, override: BaySideOverride) -> None:
        with self._lock:
            self._bay[(workspace_id, context_id, source_id)] = override

    def clear_bay(self, workspace_id: str, context_id: str, source_id: str) -> bool:
        with self._lock:
            return self._bay.pop((workspace_id, context_id, source_id), None) is not None

    def clear_context(self, workspace_id: str, context_id: str) -> int:
        """Every recording's override of this bay (the bay itself was deleted)."""
        with self._lock:
            keys = [k for k in self._bay if k[0] == workspace_id and k[1] == context_id]
            for key in keys:
                del self._bay[key]
            return len(keys)

    def bay_keys(self, workspace_id: str) -> list[tuple[str, str]]:
        """(context_id, source_id) of every stored override in this workspace."""
        with self._lock:
            return [(cid, sid) for (wid, cid, sid) in self._bay if wid == workspace_id]

    # ---- lifecycle ----
    def remove_source(self, workspace_id: str, source_id: str) -> bool:
        """The recording's correction and every bay override that was scoped to this recording."""
        with self._lock:
            removed = self._recording.pop((workspace_id, source_id), None) is not None
            keys = [k for k in self._bay if k[0] == workspace_id and k[2] == source_id]
            for key in keys:
                del self._bay[key]
            return removed or bool(keys)

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
