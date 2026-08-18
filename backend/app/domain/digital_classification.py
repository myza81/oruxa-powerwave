"""Digital channel presentation-group classification (Phase 4A).

Reusable domain knowledge, not a UI display trick -- lives here (same
rationale as `channel_classification.py`'s analog classifier) so both the
Recordings/Waveform frontend and any future consumer share exactly one
implementation.

Owner-specified classification precedence (exact, not inferred):

1. If the channel name contains "spare" (case-insensitive, anywhere in the
   name) -> SPARE. This takes precedence over the data-derived tiers below
   -- a channel named "Spare Trip" is SPARE even if its recorded values
   include a high state.
2. Else if the channel was high/non-zero at least once anywhere in the
   FULL recording (not just a viewport) -> TRIGGERED. A channel that is
   high for the entire record (never transitions) still qualifies -- the
   owner's own definition is "has been high at least once," not "contains
   a 0->1 transition."
3. Else -> NEVER_TRIGGERED.

This function is deliberately pure and stateless: it takes already-parsed
values, never touches I/O, so it stays trivially testable and reusable
regardless of where the full-record digital sample array actually lives
(currently `DisturbanceRecord.waveform_data`, see
`app/services/import_service.py`'s own call site, which runs this once per
digital channel at import time -- not re-scanned per request/render).
"""

from __future__ import annotations

from typing import Iterable

SPARE = "spare"
TRIGGERED = "triggered"
NEVER_TRIGGERED = "never_triggered"

# Stable, ordered group list -- Triggered first, Never Triggered second,
# Spare always last, per the owner's explicit vertical-order requirement.
# Useful for tests and for any consumer that wants a deterministic group
# list rather than deriving one from whatever happens to appear in a
# specific recording.
KNOWN_GROUPS = (TRIGGERED, NEVER_TRIGGERED, SPARE)


def classify_digital_channel(*, name: str, values: Iterable[int]) -> str:
    """Return one of KNOWN_GROUPS for a digital channel.

    `values` is the channel's full-record sample sequence (raw COMTRADE
    digital state, `int8` 0/1 as parsed -- see
    `app/providers/comtrade.py`'s digital extraction, which deliberately
    does NOT apply normal-state inversion, so a "1" here always means the
    raw recorded high state). Any non-zero value counts as high --
    tolerant of any not-strictly-0/1 value without guessing further
    semantics for it (the owner's own instruction: preserve truthful state
    interpretation, do not silently reclassify unexpected data).

    Never raises for a well-formed `values` iterable; an empty sequence is
    treated as "never high" (falls through to NEVER_TRIGGERED unless the
    name itself qualifies as Spare).
    """
    if "spare" in name.lower():
        return SPARE
    if any(value != 0 for value in values):
        return TRIGGERED
    return NEVER_TRIGGERED
