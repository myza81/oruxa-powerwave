"""Event Reconstruction domain model (DEC-123, DEC-124).

Event Reconstruction is the one application function where an engineer
deliberately combines several separate, established Waveform Time Groups
onto one reconstruction timeline. Waveform keeps its Time Group
isolation and grouping rules unchanged; this module never derives,
merges or splits Time Groups (that stays `app.domain.time_grouping`'s
job) and never touches source data.

Timing model (two layers, composed at read time, never stored combined):

    source native time                     (waveform_data["time"], immutable)
      + effective_alignment_offset_s       (existing within-group placement
                                            + Synchronise Sources correction,
                                            app.services.synchronization_service,
                                            read only)
      = group time                         (the Time Group's own coordinate;
                                            0 = its origin source's recorded
                                            start instant)
      + reconstruction_offset_s(g, ref)    (this module)
      = reconstruction time                (0 = the reference group's origin
                                            start instant, shifted by the
                                            reference's own correction)

    reconstruction_offset_s(g, ref) = recorded_placement_s(g, ref)
                                      + correction_s(g) - correction_s(ref)

`recorded_placement_s(g, ref)` comes from the two groups' recorded
absolute origin timestamps. `correction_s(g)` is the engineer's manual
Event Reconstruction correction for group g: a property of that group's
clock, stored independently of which group is the reference. Switching
the reference therefore changes no stored value, and every pairwise
relationship `offset(a) - offset(b) = placement(a, b) + c_a - c_b` is
independent of the reference by construction.

Member identity: a Time Group's `group_id` is derived (its current origin
source) and can change when sources are added or removed, so a
reconstruction member is identified by `membership_fingerprint()` of the
group's source ids instead. A stored member whose fingerprint no longer
matches any current Time Group is stale; its correction is never applied
to a differently-composed group.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from app.domain.synchronization import alignment_offset_valid
from app.domain.time_grouping import (
    TIME_REFERENCE_ELAPSED_ONLY,
    TIME_REFERENCE_RECORDED_ABSOLUTE,
    TIME_REFERENCE_TIME_OF_DAY,
    timestamp_placement_offset_s,
)

#: Advisory threshold (seconds) for a large gap in the reconstruction
#: timeline (DEC-124: 1 hour, warning only, never a rejection). The one
#: definition -- every caller passes it through, and the API returns it,
#: so no other layer carries its own copy.
LARGE_GAP_WARNING_THRESHOLD_S: float = 3600.0

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
        "This Time Group has only elapsed or sample-index time, with no recorded absolute start, "
        "so it cannot be placed on a reconstruction timeline."
    ),
    REASON_TIME_OF_DAY_NOT_SUPPORTED: (
        "This Time Group has a time of day but no calendar date. Time-of-day recordings are not "
        "supported by Event Reconstruction yet."
    ),
    REASON_UNKNOWN_TIME_REFERENCE: "This Time Group's time reference is not recognized.",
}


@dataclass(frozen=True, slots=True)
class ReconstructionEligibility:
    eligible: bool
    reason_code: str | None = None
    reason_message: str | None = None


def reconstruction_eligibility(time_reference_type: str) -> ReconstructionEligibility:
    """V1 eligibility, decided only by the Time Group's existing time
    reference type (never by sampling rate, duration or channel content).
    No absolute date or anchor is ever invented for a group that lacks
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


#: Bumped if the fingerprint input ever changes, so an old fingerprint can
#: never be mistaken for a new one.
MEMBERSHIP_FINGERPRINT_VERSION = "tgm1"


def membership_fingerprint(source_ids: Iterable[str]) -> str:
    """Deterministic identity of a Time Group's membership.

    Input: the group's distinct source ids only (stable, upload-assigned
    identifiers), sorted, so member order and duplicates never matter.
    Deliberately excluded: `group_id`/origin (derived, changes with
    membership), timestamps and offsets (not identity), and any
    presentation state (names, colours, zoom). Two groups have the same
    fingerprint exactly when they contain the same sources."""
    canonical = "\n".join(sorted(set(source_ids)))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{MEMBERSHIP_FINGERPRINT_VERSION}-{digest}"


def correction_valid(correction_s: float) -> bool:
    """A correction is a finite real number of seconds, with no magnitude
    bound and no rounding (sub-millisecond values are meaningful for
    high-rate records) -- the same rule as a Synchronise Sources offset."""
    return alignment_offset_valid(correction_s)


@dataclass(frozen=True, slots=True)
class ReconstructionMember:
    """One selected Time Group. `member_id` is its membership fingerprint;
    `source_ids` (sorted) is the membership it was confirmed with;
    `confirmed_group_id` is the Time Group id at confirmation time,
    provenance only."""

    member_id: str
    source_ids: tuple[str, ...]
    confirmed_group_id: str
    correction_s: float = 0.0


@dataclass(frozen=True, slots=True)
class EventReconstructionDefinition:
    """A workspace's reconstruction: its members in selection order and
    the reference member. Holds analysis state only -- never source data,
    rewritten timestamps or channel presentation."""

    members: tuple[ReconstructionMember, ...]
    reference_member_id: str

    def member(self, member_id: str) -> ReconstructionMember | None:
        for member in self.members:
            if member.member_id == member_id:
                return member
        return None

    def with_correction(self, member_id: str, correction_s: float) -> "EventReconstructionDefinition":
        return replace(
            self,
            members=tuple(
                replace(m, correction_s=correction_s) if m.member_id == member_id else m for m in self.members
            ),
        )

    def with_reference(self, member_id: str) -> "EventReconstructionDefinition":
        return replace(self, reference_member_id=member_id)


def recorded_placement_s(*, group_origin_start: datetime, reference_origin_start: datetime) -> float:
    """Seconds from the reference group's recorded origin instant to this
    group's, via exact `datetime` subtraction (timezone-normalized by the
    existing Time Group helper)."""
    return timestamp_placement_offset_s(source_start_time=group_origin_start, origin_start_time=reference_origin_start)


def reconstruction_offset_s(*, recorded_placement_s: float, correction_s: float, reference_correction_s: float) -> float:
    """Shift from a group's own group time to reconstruction time."""
    return recorded_placement_s + correction_s - reference_correction_s


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
    intervals: Sequence[tuple[str, float, float]], *, threshold_s: float = LARGE_GAP_WARNING_THRESHOLD_S,
    tolerance_s: float = INTERVAL_TOLERANCE_S,
) -> list[LargeGap]:
    """Gaps in the union of `(key, start, end)` intervals that are
    `>= threshold_s` (within `tolerance_s`, so a nominal one-hour gap is
    never missed through float rounding). Only real holes in the timeline
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
