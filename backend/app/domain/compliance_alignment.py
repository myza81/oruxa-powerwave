"""Compliance -- Event Alignment (DEC-170). Pure, framework-free domain layer.

> Compliance Event Alignment is an assessment-local horizontal offset between
> the selected measurement and the Reference Layers. It is NOT Waveform t0.

The Reference Profile has its own event-relative time axis (its disturbance is
at `t = 0`). A measured recording has its own recording time. Compliance
aligns the two with ONE local number per selected measurement context:

```text
comparison_time = measurement_time - measurement_event_origin_s
```

`measurement_event_origin_s` is the recording time of the disturbance the
engineer marked as "Reference t = 0". Example: the event is at recording time
0.550 s; after "Set as Reference t=0" the plotted measurement shifts so that
0.550 s -> 0.000 s (offset = -0.550 s).

**Ownership (frozen).** Waveform t0 / Time Groups / Cursor A / playback /
source synchronization own Waveform display behaviour only; this alignment owns
the Compliance comparison offset only; the Reference Profile owns its own
reference-relative axis. Nothing here reads or writes any Waveform state, and
no recording timestamp is ever modified -- only the x coordinates of the
measured traces are offset when they are compared. Reference Layers never move.

"Not aligned" (no alignment stored) is distinct from an explicit origin of 0.0:
the former means the engineer has not positioned the disturbance yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: The fixed step of "Shift Earlier" / "Shift Later" (seconds): 1 ms. Visible in
#: the UI; never a hidden increment.
FINE_SHIFT_STEP_S = 0.001


@dataclass(frozen=True, slots=True)
class ComplianceAlignment:
    """The one alignment of a workspace's selected measurement context
    (a Bay / Measurement Group). `source_id` is the recording whose own time
    axis `measurement_event_origin_s` is expressed on."""

    workspace_id: str
    measurement_group_id: str
    source_id: str
    measurement_event_origin_s: float


def alignment_offset_s(origin_s: float) -> float:
    """The amount ADDED to a measurement time to get comparison time."""
    return -origin_s


def comparison_time(measurement_time_s: float, origin_s: float) -> float:
    return measurement_time_s - origin_s


def require_finite_origin(origin_s: float) -> float:
    if isinstance(origin_s, bool) or not isinstance(origin_s, (int, float)) or not math.isfinite(origin_s):
        raise ValueError("The event origin must be a finite number of seconds.")
    return float(origin_s)


def snap_to_sample(times: np.ndarray, requested_s: float) -> float:
    """Deterministic nearest-sample rule: the actual recorded sample time
    closest to `requested_s`; an exact tie goes to the EARLIER sample. The
    stored origin is therefore always a real measurement timestamp, never a
    pixel approximation."""
    if times.size == 0:
        raise ValueError("The measurement has no samples to align to.")
    index = int(np.searchsorted(times, requested_s, side="left"))
    if index <= 0:
        return float(times[0])
    if index >= times.size:
        return float(times[-1])
    before, after = float(times[index - 1]), float(times[index])
    return before if (requested_s - before) <= (after - requested_s) else after
