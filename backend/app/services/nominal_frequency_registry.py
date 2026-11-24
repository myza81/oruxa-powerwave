"""In-memory, ephemeral, workspace-scoped store for the engineer's nominal-frequency value per recording (NF-1).

Holds only what an engineer decided: one optional manual frequency per `(workspace_id, source_id)`. The recording's
imported value and provenance stay on the source, untouched; Auto is never stored (see
`app.domain.nominal_frequency`). Same lifetime and keying as `MeasurementSideRegistry`: no persistence, cleared with
the recording or the workspace, records are frozen so nothing aliases a caller's object.

`revision` counts changes of the stored state for a recording (a value set or changed, a value removed). It only moves
forward while the recording exists, so a later cache key or calculation provenance can tell "computed before the
change" from "computed after". Re-storing the identical value, or clearing when nothing is stored, changes nothing and
does not move it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ManualNominalFrequency:
    value_hz: float
    set_at: datetime


class NominalFrequencyRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._manual: dict[tuple[str, str], ManualNominalFrequency] = {}
        self._revision: dict[tuple[str, str], int] = {}

    def get(self, workspace_id: str, source_id: str) -> ManualNominalFrequency | None:
        with self._lock:
            return self._manual.get((workspace_id, source_id))

    def revision(self, workspace_id: str, source_id: str) -> int:
        with self._lock:
            return self._revision.get((workspace_id, source_id), 0)

    def snapshot(self, workspace_id: str, source_id: str) -> tuple[ManualNominalFrequency | None, int]:
        """The stored value and its revision, read together so a response never mixes two states."""
        key = (workspace_id, source_id)
        with self._lock:
            return self._manual.get(key), self._revision.get(key, 0)

    def set(self, workspace_id: str, source_id: str, value_hz: float, set_at: datetime) -> bool:
        """Store the value. Returns True when the stored state changed (and the revision moved)."""
        key = (workspace_id, source_id)
        with self._lock:
            current = self._manual.get(key)
            if current is not None and current.value_hz == value_hz:
                return False
            self._manual[key] = ManualNominalFrequency(value_hz=value_hz, set_at=set_at)
            self._revision[key] = self._revision.get(key, 0) + 1
            return True

    def clear(self, workspace_id: str, source_id: str) -> bool:
        """Return to Auto. Returns True when a value was removed (and the revision moved)."""
        key = (workspace_id, source_id)
        with self._lock:
            if self._manual.pop(key, None) is None:
                return False
            self._revision[key] = self._revision.get(key, 0) + 1
            return True

    # ---- lifecycle ----
    def remove_source(self, workspace_id: str, source_id: str) -> bool:
        key = (workspace_id, source_id)
        with self._lock:
            removed = self._manual.pop(key, None) is not None
            self._revision.pop(key, None)
            return removed

    def remove_workspace(self, workspace_id: str) -> int:
        with self._lock:
            manual = [k for k in self._manual if k[0] == workspace_id]
            revisions = [k for k in self._revision if k[0] == workspace_id]
            for key in manual:
                del self._manual[key]
            for key in revisions:
                del self._revision[key]
            return len(manual)

    def count(self) -> int:
        with self._lock:
            return len(self._manual)
