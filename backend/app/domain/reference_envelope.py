"""Compliance & Capability -- Operating Envelope translation (DEC-166).
Pure, framework-free domain layer.

The Reference Profile editor presents a boundary as an ORDERED LIST OF
POINTS (time, value) that are always connected; the stored domain model
(`app.domain.reference_profile`) keeps its generic segment form. This
module is the one deterministic translation between the two, so the
simplified UI never needs a second boundary representation:

```text
Simplified point list -> points_to_segments() -> ReferenceBoundary (existing model)
ReferenceBoundary     -> segments_to_points() -> point list, ONLY where lossless
```

**Edge geometry is inferred, never chosen by the user.** For adjacent
points `(t0, v0)` and `(t1, v1)`:

- `t1 > t0`, `v1 == v0` -> a horizontal edge -> one `constant` segment.
- `t1 > t0`, `v1 != v0` -> a straight diagonal -> one `linear` segment.
- `t1 == t0`, `v1 != v0` -> a VERTICAL edge. The segment model has no
  zero-length segment, and needs none: a vertical edge is exactly the
  value discontinuity between two time-adjacent segments that share a
  boundary instant (right-continuity, see `app.domain.reference_profile`).
  The stored result for `(0,0),(0.15,0),(0.15,0.9),(3,0.9)` is therefore
  two constant segments, `[0,0.15]@0` and `[0.15,3]@0.9`.
- `t1 < t0` is rejected -- point order carries engineering meaning, so
  input is never silently re-sorted.

**Representability limits (deliberate, documented).** A vertical edge is
carried only BETWEEN two segments, so it needs a connected edge on each
side: a vertical edge as the first or last pair of a boundary is
rejected (it would be a hanging point), as are three or more points at
one instant (one vertical edge per instant). A stored boundary is
convertible back to points (`segments_to_points()`) only when the round
trip reproduces it exactly -- gaps, explicit segment types that differ
from the inferred one (a `linear` segment with equal end values), or
out-of-order storage are NOT flattened; the caller keeps such a profile
on its legacy representation (see `ReferenceProfileOut.point_editable`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.assessment_definition import (
    PHASE_TREATMENT_EACH_PHASE,
    REPRESENTATION_LINE_LINE_RMS,
    AssessmentDefinition,
)
from app.domain.reference_profile import (
    SEGMENT_TYPE_CONSTANT,
    SEGMENT_TYPE_LINEAR,
    UNIT_PER_UNIT,
    BoundarySegment,
    ReferenceBoundary,
)

#: New-profile defaults of the simplified workflow (DEC-166). The editor
#: shows them under "Advanced Settings" -- never hidden.
DEFAULT_UNIT = UNIT_PER_UNIT
DEFAULT_REPRESENTATION = REPRESENTATION_LINE_LINE_RMS
DEFAULT_PHASE_TREATMENT = PHASE_TREATMENT_EACH_PHASE
DEFAULT_EVALUATION_START_TIME = 0.0
DEFAULT_TOLERANCE = 0.0

#: Which side(s) of the boundary(ies) are compliant. Fully determined by
#: which boundaries exist -- there is no "unspecified" state, since an
#: assessment cannot run without knowing the compliant side.
REGION_AT_OR_ABOVE_LOWER = "at_or_above_lower"
REGION_AT_OR_BELOW_UPPER = "at_or_below_upper"
REGION_INSIDE_ENVELOPE = "inside_envelope"


class EnvelopePointError(ValueError):
    """A point list that cannot be translated. `point_index` is the
    zero-based row the problem is anchored to (`None` for a whole-list
    problem), so an editor can highlight it."""

    def __init__(self, message: str, *, reason_code: str, point_index: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
        self.point_index = point_index


@dataclass(frozen=True, slots=True)
class EnvelopePoint:
    time: float
    value: float


def points_to_segments(points: list[EnvelopePoint] | tuple[EnvelopePoint, ...]) -> tuple[BoundarySegment, ...]:
    """Deterministic point-list -> segment translation (see module
    docstring). Raises `EnvelopePointError` on the first violation; never
    sorts, repairs or drops a point."""
    if len(points) < 2:
        raise EnvelopePointError(
            "A boundary needs at least two points to define an edge.", reason_code="too_few_points",
        )
    for index, point in enumerate(points):
        if not (math.isfinite(point.time) and math.isfinite(point.value)):
            raise EnvelopePointError(
                f"Point {index + 1}: time and voltage must be finite numbers.",
                reason_code="non_finite_value", point_index=index,
            )
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        if current.time < previous.time:
            raise EnvelopePointError(
                f"Point {index + 1}: time {current.time:g} s is earlier than the previous point "
                f"({previous.time:g} s); time must not decrease down the list.",
                reason_code="decreasing_time", point_index=index,
            )
        if current.time == previous.time and current.value == previous.value:
            raise EnvelopePointError(
                f"Point {index + 1} duplicates the previous point and adds no geometry.",
                reason_code="duplicate_point", point_index=index,
            )
        if index >= 2 and current.time == previous.time == points[index - 2].time:
            raise EnvelopePointError(
                f"Point {index + 1}: more than two points share t = {current.time:g} s; "
                "one vertical edge per instant.",
                reason_code="multiple_vertical_edges", point_index=index,
            )
    if points[0].time == points[1].time:
        raise EnvelopePointError(
            "The first two points share a time (a vertical edge at the very start); a vertical edge "
            "needs a connected edge on each side. Start with a horizontal or sloping edge.",
            reason_code="leading_vertical_edge", point_index=1,
        )
    if points[-1].time == points[-2].time:
        raise EnvelopePointError(
            "The last two points share a time (a vertical edge at the very end); a vertical edge "
            "needs a connected edge on each side. End with a horizontal or sloping edge.",
            reason_code="trailing_vertical_edge", point_index=len(points) - 1,
        )

    segments: list[BoundarySegment] = []
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        if current.time == previous.time:
            continue  # vertical edge: the discontinuity between neighbouring segments
        segments.append(BoundarySegment(
            start_time=previous.time, end_time=current.time,
            start_value=previous.value, end_value=current.value,
            segment_type=SEGMENT_TYPE_CONSTANT if previous.value == current.value else SEGMENT_TYPE_LINEAR,
        ))
    return tuple(segments)


def _segments_to_points_unchecked(segments: tuple[BoundarySegment, ...]) -> tuple[EnvelopePoint, ...] | None:
    if not segments:
        return None
    points = [EnvelopePoint(segments[0].start_time, segments[0].start_value)]
    for index, segment in enumerate(segments):
        if index > 0:
            previous = segments[index - 1]
            if segment.start_time != previous.end_time:
                return None  # a gap -- no connected point list exists
            if segment.start_value != previous.end_value:
                points.append(EnvelopePoint(segment.start_time, segment.start_value))  # vertical edge
        points.append(EnvelopePoint(segment.end_time, segment.end_value))
    return tuple(points)


def segments_to_points(boundary: ReferenceBoundary) -> tuple[EnvelopePoint, ...] | None:
    """The point list that `points_to_segments()` turns back into EXACTLY
    this boundary, or `None` when no such list exists (gap, overlap,
    unordered storage, or an explicit segment type that differs from the
    inferred one). Lossless by construction: the candidate is accepted
    only after the round trip reproduces the stored segments."""
    points = _segments_to_points_unchecked(boundary.segments)
    if points is None:
        return None
    try:
        round_trip = points_to_segments(points)
    except EnvelopePointError:
        return None
    return points if round_trip == boundary.segments else None


def derive_display_extent(
    lower: ReferenceBoundary | None, upper: ReferenceBoundary | None,
) -> tuple[float, float] | None:
    """Union of the configured boundaries' extents: earliest start to
    latest end. `None` when neither boundary has a segment."""
    segments = [s for boundary in (lower, upper) if boundary is not None for s in boundary.segments]
    if not segments:
        return None
    return min(s.start_time for s in segments), max(s.end_time for s in segments)


def compliance_region(*, has_lower: bool, has_upper: bool) -> str:
    """The compliant region implied by the configured boundaries."""
    if has_lower and has_upper:
        return REGION_INSIDE_ENVELOPE
    if has_lower:
        return REGION_AT_OR_ABOVE_LOWER
    if has_upper:
        return REGION_AT_OR_BELOW_UPPER
    raise ValueError("An operating envelope needs at least one boundary.")


def default_assessment_definition() -> AssessmentDefinition:
    """Assessment Definition of a newly created simplified profile:
    Line-Line RMS, assessed Each Phase. Location/provenance stay
    `unspecified` -- they are no longer part of this workflow and are
    never invented."""
    return AssessmentDefinition(
        representation=DEFAULT_REPRESENTATION, phase_treatment=DEFAULT_PHASE_TREATMENT,
    )


def default_windows(
    lower: ReferenceBoundary | None, upper: ReferenceBoundary | None,
) -> tuple[float, float, float, float] | None:
    """`(display_start, display_end, evaluation_start, evaluation_end)`
    for a new profile: the display window is the derived extent, the
    evaluation window starts at the disturbance reference `t = 0` and
    ends with the display window. `None` when no boundary exists."""
    extent = derive_display_extent(lower, upper)
    if extent is None:
        return None
    display_start, display_end = extent
    return display_start, display_end, DEFAULT_EVALUATION_START_TIME, display_end
