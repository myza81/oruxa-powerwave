"""Sampling and timing descriptors.

Ported near-verbatim from powerwave's app/models/timing.py (commit 3156392).

CSV/Excel ingestion Slice 10 (DEC-072) hardening: `TimingInformation.
start_time`/`.trigger_time` are now `datetime | None` (were both
required `datetime`). This is the ONE canonical-model change Slice 10
needed -- a converted CSV/Excel source may genuinely have no absolute
start (elapsed/partial/sample-index timing) and CSV/Excel recordings
essentially never carry a trigger timestamp at all, and the task's own
explicit "no fake dates, no sentinel timestamps" rule forbids inventing
a placeholder value merely to satisfy a required-field type. This is
NOT a new concept introduced here: `app.domain.source.SourceMetadata.
start_time`/`.trigger_time` were ALREADY `datetime | None` since Phase
5B (DEC-048's own forward-compatibility field), and the entire
downstream consumption chain (`app.domain.time_grouping.
derive_time_groups()`/`timestamp_placement_offset_s()`,
`app.services.calculated_channel_service`) already explicitly branches
on `start_time is None` -- this change simply lets `TimingInformation`
(the one remaining required-`datetime` link in that chain) carry the
same honest optionality all the way from a `DisturbanceRecord` through
to `SourceMetadata`, instead of forcing a real `DisturbanceRecord` to
lie about having an absolute start it does not have.

COMTRADE is completely UNCHANGED by this: `app.providers.comtrade`
always parses a real `start_time`/`trigger_time` from the CFG file's
own required timestamp lines, so `ComtradeProvider` never constructs a
`TimingInformation` with either field `None` -- see
`tests/test_disturbance_record_domain.py`'s own COMTRADE regression
coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SamplingInformation:
    """Describes the sampling structure of a disturbance recording.

    Supports COMTRADE multi-rate recordings via parallel lists:
    sampling_rates[i] is the rate (Hz) for the section with samples_per_rate[i]
    samples.

    `is_uniform` (Slice 10, DEC-072) -- additive, defaults `True` for
    100% backward compatibility with every existing COMTRADE record
    (which is always uniformly sampled within each declared rate
    section). `False` marks a genuinely IRREGULAR canonical time axis
    (a converted CSV/Excel source whose interpreted timing does not
    fit within Slice 10's own uniform-interval tolerance) -- in that
    case `sampling_rates`/`samples_per_rate` still carry a best-effort
    NOMINAL single-section summary (for display only, e.g. "≈50 Hz"),
    but the AUTHORITATIVE per-sample timing remains `waveform_data
    ["time"]` (already the existing precedent -- see `DisturbanceRecord.
    duration_seconds()`'s own "prefer the time column when present"
    rule) -- this field exists so nothing downstream has to (falsely)
    infer uniformity from `sampling_rates` alone.
    """

    sampling_rates: list[float]
    samples_per_rate: list[int]

    samples_per_cycle: float | None = None
    nominal_frequency: float | None = None
    is_uniform: bool = True


@dataclass(slots=True)
class TimingInformation:
    """Time references for a disturbance recording.

    timing_reference is "absolute" when start_time/trigger_time are real
    recording timestamps, and "relative_elapsed" when waveform_data["time"]
    is the authoritative duration axis and start_time is only a
    compatibility anchor.

    `start_time`/`trigger_time` are `None` (Slice 10, DEC-072) exactly
    when genuinely unknown -- never a fabricated placeholder (no
    `1970-01-01`, no `2000-01-01`, never `trigger_time = start_time`
    merely to have a value). `trigger_time` in particular stays `None`
    for every CSV/Excel-converted source today, since that format
    family carries no trigger concept at all.
    """

    start_time: datetime | None
    trigger_time: datetime | None

    time_multiplier: float = 1.0
    timezone: str | None = None
    timing_reference: str = "absolute"
    time_axis_unit: str | None = None
    #: Time of Day (CSV/Excel ingestion, additive): seconds-since-
    #: midnight clock position corresponding to this recording's own
    #: elapsed=0 origin, for a `timing_reference="time_of_day"` source
    #: ONLY -- the date-neutral counterpart of `start_time`, used solely
    #: for Time-of-Day-vs-Time-of-Day overlap/placement in
    #: `app.domain.time_grouping`. Never combined with a real calendar
    #: date, never promoted to `start_time`, and always `None` for every
    #: other `timing_reference` value (including every existing COMTRADE
    #: recording, which is completely unaffected by this field).
    time_of_day_reference_seconds: float | None = None


@dataclass(slots=True)
class DisturbanceInformation:
    """Optional engineering context and classification for a disturbance event."""

    event_type: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)
