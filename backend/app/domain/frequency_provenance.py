"""NF-3D (owner decision O-6): which recording's nominal-frequency authority supplied the frequency an analysis actually used.

A phasor-family or overcurrent result reports `reference_frequency_hz`. This says where that number came from, in the NF-1 vocabulary
(`recording_metadata`, `import_supplied`, `assumed_default`, `manual`, `unusable`; nothing is added to it):

* the frequency came from the recording(s) that supplied the analysed channels, so each contributing recording is listed with its own origin
  and the revision of the engineer's setting it was resolved with (`recordings`);
* `origin`/`revision` summarise that for the common case: ONE contributing recording, or several that share the same origin (then `origin` is
  that origin and `revision` is None, because revisions are per recording); several recordings with different origins give `origin` None
  and the list is the whole answer;
* an EXPLICIT `reference_frequency_hz` supplied with the request is the caller's own value, not any recording's authority, so a result that used
  one has NO provenance at all (the whole object is None): the absence is the statement, and the echoed `reference_frequency_hz` is the value.

A `manual` origin means "an engineer entered this value in Recording Details". It is never a measured or verified waveform frequency, and no
field here says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class RecordingFrequencyUse:
    source_id: str
    origin: str
    revision: int


@dataclass(frozen=True, slots=True)
class FrequencyProvenance:
    origin: str | None
    revision: int | None
    recordings: tuple[RecordingFrequencyUse, ...]


def provenance_of(recordings: Iterable[RecordingFrequencyUse]) -> FrequencyProvenance | None:
    """The provenance of a frequency taken from `recordings` (de-duplicated by recording, first-mention order). None for no recording."""
    unique: dict[str, RecordingFrequencyUse] = {}
    for use in recordings:
        unique.setdefault(use.source_id, use)
    used = tuple(unique.values())
    if not used:
        return None
    origins = {u.origin for u in used}
    origin = next(iter(origins)) if len(origins) == 1 else None
    revision = used[0].revision if len(used) == 1 else None
    return FrequencyProvenance(origin=origin, revision=revision, recordings=used)
