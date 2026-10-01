"""Event Reconstruction domain model (DEC-123, DEC-124, DEC-128).

Event Reconstruction is the one application function where an engineer
deliberately places several independently imported recordings on one
reconstruction timeline.

**Atomic member = one imported record (DEC-128).** A record is one
`SourceMetadata` (`source_id`): one upload -- a COMTRADE CFG+DAT pair, a
BEN file or a converted CSV/Excel file -- i.e. one logical event (DEC-032).
Waveform Time Groups are NOT an input: two records whose recorded times
overlap, even identically, remain two independent members. Waveform keeps
its own Time Group model unchanged.

Coordinates (all in seconds; absolute time enters exactly ONCE, in
`recorded_placement_s`):

- `source_elapsed` -- a source's own native ELAPSED time
  (`waveform_data["time"]`, immutable), never an absolute timestamp.
  `source_elapsed = 0` is the source's recorded `start_time`; it may be
  negative for pre-trigger samples.
- `origin_start(r)` -- record r's recorded absolute start (its source's
  `start_time`), normalized to a comparable instant.
- `within_record_offset_s(s)` -- where a constituent source sits inside
  its own record. Every import produces exactly one source per record
  today, so it is 0; it is the explicit place a future multi-source
  record would carry its internal placement. Waveform's Synchronise
  Sources corrections relate DIFFERENT records, so they are never applied
  here -- the Event Reconstruction correction is that cross-record layer.
- `recorded_placement_s(r, ref) = origin_start(r) - origin_start(ref)` --
  the only use of recorded absolute time, an exact `datetime` difference.
- `correction_s(r)` -- the engineer's Event Reconstruction correction for
  record r: a property of that record's clock, stored independently of
  which record is the reference.
- `reconstruction_offset_s(r, ref) = recorded_placement_s(r, ref)
  + correction_s(r) - correction_s(ref)`.
- `total_reconstruction_offset_s(s) = within_record_offset_s(s)
  + reconstruction_offset_s(record(s), ref)`.
- `reconstruction_x = source_elapsed + total_reconstruction_offset_s(s)`.
  0 is the reference record's recorded start (after the reference's own
  correction). With every correction 0, reconstruction time t is exactly
  the absolute instant `origin_start(ref) + t`.

Reference switching: for any two records,
`offset(a, ref) - offset(b, ref) = recorded_placement_s(a, b) + c_a - c_b`
-- the reference cancels out. Choosing a different reference only moves
where 0 is; no stored value changes and no record moves relative to
another.

Member identity is the record id itself (stable, upload-assigned). A
stored member whose record no longer exists is stale; its correction is
kept but never applied, and never moved to another record.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from app.domain.synchronization import alignment_offset_valid
from app.domain.time_grouping import (
    TIME_REFERENCE_ELAPSED_ONLY,
    TIME_REFERENCE_RECORDED_ABSOLUTE,
    TIME_REFERENCE_TIME_OF_DAY,
    timestamp_placement_offset_s,
)

#: Interval comparisons are made on float seconds derived from exact
#: `datetime` arithmetic plus float corrections. Endpoints closer than
#: this are treated as equal -- the same sub-microsecond tolerance
#: app.domain.calculated_channel uses for "the same sample instant".
INTERVAL_TOLERANCE_S: float = 1e-9

REASON_NO_ABSOLUTE_TIME_REFERENCE = "no_absolute_time_reference"
REASON_TIME_OF_DAY_NOT_SUPPORTED = "time_of_day_not_supported"
REASON_UNKNOWN_TIME_REFERENCE = "unknown_time_reference"

_REASON_MESSAGES = {
    REASON_NO_ABSOLUTE_TIME_REFERENCE: (
        "This record has only elapsed or sample-index time, with no recorded absolute start, "
        "so it cannot be placed on a reconstruction timeline."
    ),
    REASON_TIME_OF_DAY_NOT_SUPPORTED: (
        "This record has a time of day but no calendar date. Time-of-day records are not "
        "supported by Event Reconstruction yet."
    ),
    REASON_UNKNOWN_TIME_REFERENCE: "This record's time reference is not recognized.",
}


@dataclass(frozen=True, slots=True)
class ReconstructionEligibility:
    eligible: bool
    reason_code: str | None = None
    reason_message: str | None = None


def reconstruction_eligibility(time_reference_type: str) -> ReconstructionEligibility:
    """V1 eligibility, decided only by the record's existing time
    reference type (never by sampling rate, duration or channel content).
    No absolute date or anchor is ever invented for a record that lacks
    one."""
    if time_reference_type == TIME_REFERENCE_RECORDED_ABSOLUTE:
        return ReconstructionEligibility(eligible=True)
    if time_reference_type == TIME_REFERENCE_TIME_OF_DAY:
        reason = REASON_TIME_OF_DAY_NOT_SUPPORTED
    elif time_reference_type == TIME_REFERENCE_ELAPSED_ONLY:
        reason = REASON_NO_ABSOLUTE_TIME_REFERENCE
    else:
        reason = REASON_UNKNOWN_TIME_REFERENCE
    return ReconstructionEligibility(eligible=False, reason_code=reason, reason_message=_REASON_MESSAGES[reason])


def correction_valid(correction_s: float) -> bool:
    """A correction is a finite real number of seconds, with no magnitude
    bound and no rounding (sub-millisecond values are meaningful for
    high-rate records) -- the same rule as a Synchronise Sources offset."""
    return alignment_offset_valid(correction_s)


@dataclass(frozen=True, slots=True)
class ReconstructionMember:
    """One selected record. `record_id` is the record's stable identity
    (its `source_id`); `source_ids` are its constituent sources (today
    always `(record_id,)`)."""

    record_id: str
    source_ids: tuple[str, ...]
    correction_s: float = 0.0


@dataclass(frozen=True, slots=True)
class EventReconstructionDefinition:
    """A workspace's reconstruction: its member records in selection order
    and the reference record. Holds analysis state only -- never source
    data, rewritten timestamps or channel presentation."""

    members: tuple[ReconstructionMember, ...]
    reference_record_id: str

    def member(self, record_id: str) -> ReconstructionMember | None:
        for member in self.members:
            if member.record_id == record_id:
                return member
        return None

    def with_correction(self, record_id: str, correction_s: float) -> "EventReconstructionDefinition":
        return replace(
            self,
            members=tuple(
                replace(m, correction_s=correction_s) if m.record_id == record_id else m for m in self.members
            ),
        )

    def with_reference(self, record_id: str) -> "EventReconstructionDefinition":
        return replace(self, reference_record_id=record_id)


def recorded_placement_s(*, record_origin_start: datetime, reference_origin_start: datetime) -> float:
    """Seconds from the reference record's recorded start to this
    record's, via exact `datetime` subtraction (timezone-normalized by the
    shared timestamp helper)."""
    return timestamp_placement_offset_s(source_start_time=record_origin_start, origin_start_time=reference_origin_start)


def reconstruction_offset_s(*, recorded_placement_s: float, correction_s: float, reference_correction_s: float) -> float:
    """Shift from a record's own time to reconstruction time."""
    return recorded_placement_s + correction_s - reference_correction_s


def total_reconstruction_offset_s(*, within_record_offset_s: float, reconstruction_record_offset_s: float) -> float:
    """The ONE additive offset that places a source's own elapsed time on
    the reconstruction timeline:

        reconstruction_x_s = source_elapsed_s + total_reconstruction_offset_s

    `within_record_offset_s` is where the source sits inside its own
    record (0 for every single-source record). `reconstruction_record_
    offset_s` is `reconstruction_offset_s()` of its record (recorded-start
    difference to the reference + Event Reconstruction corrections).
    Absolute time enters only once, inside the latter."""
    return within_record_offset_s + reconstruction_record_offset_s


RELATIONSHIP_FULL_OVERLAP = "full_overlap"
RELATIONSHIP_PARTIAL_OVERLAP = "partial_overlap"
RELATIONSHIP_TOUCHING = "touching"
RELATIONSHIP_GAP = "gap"


@dataclass(frozen=True, slots=True)
class IntervalRelationship:
    """`full_overlap` means one interval contains the other. `gap_s` is
    the separation for `gap` (0 otherwise); `overlap_s` the shared
    duration for an overlap (0 otherwise)."""

    kind: str
    gap_s: float = 0.0
    overlap_s: float = 0.0


def classify_interval_relationship(
    a_start: float, a_end: float, b_start: float, b_end: float, *, tolerance_s: float = INTERVAL_TOLERANCE_S
) -> IntervalRelationship:
    separation = max(a_start, b_start) - min(a_end, b_end)
    if separation > tolerance_s:
        return IntervalRelationship(kind=RELATIONSHIP_GAP, gap_s=separation)
    if separation >= -tolerance_s:
        return IntervalRelationship(kind=RELATIONSHIP_TOUCHING)
    a_contains_b = a_start <= b_start + tolerance_s and a_end >= b_end - tolerance_s
    b_contains_a = b_start <= a_start + tolerance_s and b_end >= a_end - tolerance_s
    kind = RELATIONSHIP_FULL_OVERLAP if (a_contains_b or b_contains_a) else RELATIONSHIP_PARTIAL_OVERLAP
    return IntervalRelationship(kind=kind, overlap_s=-separation)


@dataclass(frozen=True, slots=True)
class LargeGap:
    """An uncovered stretch of the reconstruction timeline at least the
    warning threshold long. `before_key` is the interval whose end starts
    the gap (the latest-ending interval so far); `after_key` the interval
    whose start ends it."""

    before_key: str
    after_key: str
    gap_s: float
    threshold_s: float


def large_gaps(
    intervals: Sequence[tuple[str, float, float]], *, threshold_s: float,
    tolerance_s: float = INTERVAL_TOLERANCE_S,
) -> list[LargeGap]:
    """Gaps in the union of `(key, start, end)` intervals that are
    `>= threshold_s` (within `tolerance_s`, so a gap of nominally exactly
    the threshold is never missed through float rounding). The threshold
    has no default here: it is configuration
    (`Settings.event_reconstruction_large_gap_warning_s`). Only real holes in the timeline
    count: a member bridged by another overlapping member produces no
    warning. Advisory only -- callers must never reject on it."""
    if not math.isfinite(threshold_s) or threshold_s <= 0:
        raise ValueError("threshold_s must be a positive finite number of seconds.")
    ordered = sorted(intervals, key=lambda item: (item[1], item[2], item[0]))
    warnings: list[LargeGap] = []
    if not ordered:
        return warnings
    covered_key, _, covered_end = ordered[0]
    for key, start, end in ordered[1:]:
        gap = start - covered_end
        if gap >= threshold_s - tolerance_s:
            warnings.append(LargeGap(before_key=covered_key, after_key=key, gap_s=gap, threshold_s=threshold_s))
        if end > covered_end:
            covered_key, covered_end = key, end
    return warnings
