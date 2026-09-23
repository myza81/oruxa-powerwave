"""Compliance & Capability -- Reference Profile domain model (Slice 3;
see docs/project-memory/COMPLIANCE_CAPABILITY.md). Pure, framework-free
domain layer -- no registry access, no waveform fetch, matching this
codebase's established `app.domain` layer contract.

**Deliberately generic, not Grid-Code-specific** (task section 3): a
`ReferenceProfile` is a reusable engineering curve description (grid
requirement, equipment capability, project requirement, or an ad-hoc
custom reference) -- never a "Malaysia Grid Code" or any other named
official requirement baked into this module. See
`app.domain.reference_profile_builtins` for why zero production built-in
profiles ship with this slice.

**A profile is a portable value object, not workspace-owned state** --
unlike `app.domain.measurement_group.MeasurementGroup` (which directly
claims ownership of specific channel references within one workspace),
a `ReferenceProfile` owns nothing workspace-specific: no channel refs, no
source binding. This is exactly what makes JSON export/import (task
section 17) and a workspace-agnostic built-in catalogue possible without
stripping/rewriting fields. Workspace scoping for CUSTOM profiles is
purely a registry-key concern (`app.services.reference_profile_registry`),
never a field on this dataclass.

**Boundary/segment semantics (task section 4/5) are FROZEN by this task**:

- A boundary (`lower_boundary`/`upper_boundary`) is an ORDERED set of
  segments, each with explicit `start_time`/`end_time`/`start_value`/
  `end_value`/`segment_type` (`"constant"` or `"linear"`). Either
  boundary may be absent, but never both (task section 4 -- "may be
  lower-only, upper-only, or both -- never require both", which implies
  a profile with neither boundary present is meaningless and rejected).
- Negative time, gaps between segments, and value discontinuities at a
  shared time are all explicitly ALLOWED -- there is no forced overall
  monotonicity of time across a boundary's own segments beyond what is
  needed to detect overlap (validation sorts by `start_time` internally
  purely to check adjacency; it never reorders or mutates any segment's
  own stored values).
- **Right-continuity** (task section 5, frozen): at a discontinuity
  (`segment[i].end_time == segment[i+1].start_time` with different
  values), the ACTIVE value at that instant belongs to the NEW
  (following) segment. `boundary_to_render_points()` renders this
  automatically -- emitting both segments' own endpoints in time order
  naturally produces a vertical connector between them, with no special-
  cased "which segment wins" branch needed at render time (evaluation
  time, later, is a different question and is explicitly NOT decided by
  this module).
- A genuine GAP (`segment[i+1].start_time > segment[i].end_time`) gets
  NO connector and NO reference claim across the gap -- rendered as an
  explicit line break (a `None`-valued `BoundaryPoint`), never a
  straight line silently bridging two unrelated segments.
- Overlapping segments within the SAME boundary
  (`segment[i+1].start_time < segment[i].end_time`, once sorted) are
  rejected outright -- never silently resolved by picking one.

**Never silently repair bad data** (task section 4's own explicit
instruction): `validate_reference_profile()` raises
`ReferenceProfileValidationError` (carrying a stable `reason_code` plus,
where applicable, `segment_index`/`field_name` so a table-first editor
UI can highlight the exact offending row/field, task section 13) on any
structural violation -- non-finite numbers, `end_time <= start_time`,
overlapping segments, a malformed segment type, an unknown category/unit,
or a missing boundary. It never coerces, clamps, or reorders a value to
make it "work".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Profile categories (task section 3) -- deliberately generic, never a
#: named grid code or OEM baked in as a "kind".
CATEGORY_GRID_REQUIREMENT = "grid_requirement"
CATEGORY_EQUIPMENT_CAPABILITY = "equipment_capability"
CATEGORY_PROJECT_REQUIREMENT = "project_requirement"
CATEGORY_CUSTOM_REFERENCE = "custom_reference"
KNOWN_CATEGORIES = (
    CATEGORY_GRID_REQUIREMENT,
    CATEGORY_EQUIPMENT_CAPABILITY,
    CATEGORY_PROJECT_REQUIREMENT,
    CATEGORY_CUSTOM_REFERENCE,
)

#: v1 segment types (task section 4) -- explicit vocabulary, never a
#: free-form string.
SEGMENT_TYPE_CONSTANT = "constant"
SEGMENT_TYPE_LINEAR = "linear"
KNOWN_SEGMENT_TYPES = (SEGMENT_TYPE_CONSTANT, SEGMENT_TYPE_LINEAR)

#: Boundary kind vocabulary -- used by callers (service/API layer) to
#: label which boundary a rendered trace/compatibility message refers
#: to; not stored on `BoundarySegment`/`ReferenceBoundary` themselves.
BOUNDARY_LOWER = "lower"
BOUNDARY_UPPER = "upper"

#: v1 supported units (task section 7 -- "Support at least pu, V, kV").
#: Deliberately closed: no arbitrary unit accepted, since nothing in
#: this slice performs unit conversion (task section 7/14's own explicit
#: "do not invent unit conversion in this slice").
UNIT_PER_UNIT = "pu"
UNIT_VOLT = "V"
UNIT_KILOVOLT = "kV"
KNOWN_UNITS = (UNIT_PER_UNIT, UNIT_VOLT, UNIT_KILOVOLT)


class ReferenceProfileValidationError(ValueError):
    """Raised by `validate_reference_profile()` when a profile's own data
    is structurally invalid. `reason_code` is a stable machine-readable
    identifier (never a generic "invalid"); `segment_index`/`field_name`
    are populated wherever the violation traces to one specific
    segment/field, so a table-first editor can highlight the exact
    offending row (task section 13)."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        boundary: str | None = None,
        segment_index: int | None = None,
        field_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
        self.boundary = boundary
        self.segment_index = segment_index
        self.field_name = field_name


@dataclass(frozen=True, slots=True)
class BoundarySegment:
    """One ordered piece of a boundary curve. `start_time`/`end_time` are
    relative seconds (negative allowed -- pre-trigger). `segment_type`
    `"constant"` requires `start_value == end_value` (a genuine ramp must
    be declared `"linear"`, never a mislabeled `"constant"`)."""

    start_time: float
    end_time: float
    start_value: float
    end_value: float
    segment_type: str


@dataclass(frozen=True, slots=True)
class ReferenceBoundary:
    """An ordered set of segments forming one side (lower or upper) of a
    profile's engineering boundary. Stored in whatever order the caller
    supplied -- `validate_reference_profile()`/`boundary_to_render_points()`
    sort a local copy by `start_time` for adjacency/overlap checks and
    rendering, but never mutate or reorder the stored tuple itself."""

    segments: tuple[BoundarySegment, ...]


@dataclass(frozen=True, slots=True)
class ReferenceProfileMetadata:
    """Optional descriptive metadata (task section 3 -- SUPPORT, not
    require, every field). A closed set of named fields rather than an
    open dict: every field this task names is first-class, typed, and
    documented, instead of an unvalidated free-form bag."""

    brand: str | None = None
    equipment_type: str | None = None
    model: str | None = None
    firmware_hardware: str | None = None
    source_document: str | None = None
    source_revision: str | None = None
    project: str | None = None
    plant: str | None = None
    notes: str | None = None
    built_in: bool = False
    verified: bool = False


@dataclass(frozen=True, slots=True)
class ReferenceProfile:
    """The generic reference-profile domain model (task section 3).
    `evaluation_quantity` is expected to be one of the existing canonical
    Voltage assessment quantity ids from
    `app.domain.compliance_measurement.VOLTAGE_QUANTITIES` (e.g.
    `"phase_a_lg_rms"`) -- this module does not import or enforce that
    catalogue directly (it has zero dependency on the Compliance
    Measurement feature area), the SERVICE layer is responsible for that
    cross-check, mirroring how `app.domain.compliance_measurement` itself
    has zero dependency on Engineering Context (DEC-101)."""

    id: str
    name: str
    category: str
    evaluation_quantity: str
    unit: str
    display_start_time: float
    display_end_time: float
    evaluation_start_time: float
    evaluation_end_time: float
    tolerance: float
    lower_boundary: ReferenceBoundary | None
    upper_boundary: ReferenceBoundary | None
    metadata: ReferenceProfileMetadata


def _require_finite(value: float, *, field_name: str, boundary: str | None = None, segment_index: int | None = None) -> None:
    if not math.isfinite(value):
        raise ReferenceProfileValidationError(
            f"{field_name} must be a finite number (got {value!r}).",
            reason_code="non_finite_value", boundary=boundary, segment_index=segment_index, field_name=field_name,
        )


def _validate_segment(segment: BoundarySegment, index: int, *, boundary: str) -> None:
    _require_finite(segment.start_time, field_name="start_time", boundary=boundary, segment_index=index)
    _require_finite(segment.end_time, field_name="end_time", boundary=boundary, segment_index=index)
    _require_finite(segment.start_value, field_name="start_value", boundary=boundary, segment_index=index)
    _require_finite(segment.end_value, field_name="end_value", boundary=boundary, segment_index=index)
    if segment.segment_type not in KNOWN_SEGMENT_TYPES:
        raise ReferenceProfileValidationError(
            f"Segment {index} ({boundary}): unknown segment type {segment.segment_type!r} "
            f"(must be one of {KNOWN_SEGMENT_TYPES}).",
            reason_code="malformed_segment_type", boundary=boundary, segment_index=index, field_name="segment_type",
        )
    if segment.end_time <= segment.start_time:
        raise ReferenceProfileValidationError(
            f"Segment {index} ({boundary}): end_time ({segment.end_time}) must be greater than "
            f"start_time ({segment.start_time}).",
            reason_code="invalid_segment_time_range", boundary=boundary, segment_index=index, field_name="end_time",
        )
    if segment.segment_type == SEGMENT_TYPE_CONSTANT and segment.start_value != segment.end_value:
        raise ReferenceProfileValidationError(
            f"Segment {index} ({boundary}): a 'constant' segment must have equal start_value and "
            f"end_value (got {segment.start_value} -> {segment.end_value}); use 'linear' for a ramp.",
            reason_code="constant_segment_value_mismatch", boundary=boundary, segment_index=index, field_name="end_value",
        )


def _validate_boundary(boundary_obj: ReferenceBoundary, *, boundary: str) -> None:
    if not boundary_obj.segments:
        raise ReferenceProfileValidationError(
            f"The {boundary} boundary must contain at least one segment.",
            reason_code="empty_boundary", boundary=boundary,
        )
    for index, segment in enumerate(boundary_obj.segments):
        _validate_segment(segment, index, boundary=boundary)
    ordered = sorted(enumerate(boundary_obj.segments), key=lambda pair: pair[1].start_time)
    for i in range(1, len(ordered)):
        prev_index, previous = ordered[i - 1]
        cur_index, current = ordered[i]
        if current.start_time < previous.end_time:
            raise ReferenceProfileValidationError(
                f"Segment {cur_index} ({boundary}, start {current.start_time}) overlaps segment "
                f"{prev_index} (end {previous.end_time}); overlapping segments within the same "
                "boundary are not allowed.",
                reason_code="overlapping_segments", boundary=boundary, segment_index=cur_index, field_name="start_time",
            )


def validate_reference_profile(profile: ReferenceProfile) -> None:
    """Raises `ReferenceProfileValidationError` on the first structural
    violation found. Called by the service layer before every create/
    update/import -- never bypassable, never partially applied (a
    rejected profile leaves whatever the caller already had completely
    untouched, matching every other registry's own create/update
    contract in this codebase)."""
    if not profile.name or not profile.name.strip():
        raise ReferenceProfileValidationError("Profile name must not be blank.", reason_code="blank_name", field_name="name")
    if profile.category not in KNOWN_CATEGORIES:
        raise ReferenceProfileValidationError(
            f"Unknown category {profile.category!r} (must be one of {KNOWN_CATEGORIES}).",
            reason_code="unknown_category", field_name="category",
        )
    if not profile.evaluation_quantity or not profile.evaluation_quantity.strip():
        raise ReferenceProfileValidationError(
            "evaluation_quantity must not be blank.", reason_code="blank_evaluation_quantity", field_name="evaluation_quantity",
        )
    if profile.unit not in KNOWN_UNITS:
        raise ReferenceProfileValidationError(
            f"Unsupported unit {profile.unit!r} (must be one of {KNOWN_UNITS}).",
            reason_code="unsupported_unit", field_name="unit",
        )

    for field_name, value in (
        ("display_start_time", profile.display_start_time),
        ("display_end_time", profile.display_end_time),
        ("evaluation_start_time", profile.evaluation_start_time),
        ("evaluation_end_time", profile.evaluation_end_time),
        ("tolerance", profile.tolerance),
    ):
        _require_finite(value, field_name=field_name)

    if profile.display_end_time <= profile.display_start_time:
        raise ReferenceProfileValidationError(
            f"display_end_time ({profile.display_end_time}) must be greater than "
            f"display_start_time ({profile.display_start_time}).",
            reason_code="invalid_display_window", field_name="display_end_time",
        )
    if profile.evaluation_end_time <= profile.evaluation_start_time:
        raise ReferenceProfileValidationError(
            f"evaluation_end_time ({profile.evaluation_end_time}) must be greater than "
            f"evaluation_start_time ({profile.evaluation_start_time}).",
            reason_code="invalid_evaluation_window", field_name="evaluation_end_time",
        )
    if profile.tolerance < 0:
        raise ReferenceProfileValidationError(
            f"tolerance must not be negative (got {profile.tolerance}).",
            reason_code="negative_tolerance", field_name="tolerance",
        )

    if profile.lower_boundary is None and profile.upper_boundary is None:
        raise ReferenceProfileValidationError(
            "A reference profile must define at least a lower or an upper boundary.",
            reason_code="no_boundary_defined",
        )
    if profile.lower_boundary is not None:
        _validate_boundary(profile.lower_boundary, boundary=BOUNDARY_LOWER)
    if profile.upper_boundary is not None:
        _validate_boundary(profile.upper_boundary, boundary=BOUNDARY_UPPER)


@dataclass(frozen=True, slots=True)
class BoundaryPoint:
    """One point of a render-ready polyline. `value is None` marks a
    genuine gap -- the caller (JSON encoder -> Plotly) must render this
    as a line break, never interpolate across it."""

    time: float
    value: float | None


#: Task section 17: "JSON export uses a stable versioned schema (example:
#: {"schema_version": 1, "profile": {...}})". `SCHEMA_VERSION` is the ONE
#: version this module currently writes/accepts; a future incompatible
#: shape change bumps this and adds the old value to
#: `SUPPORTED_SCHEMA_VERSIONS` only if a compatible reader is written --
#: an unrecognized version is always rejected explicitly, never silently
#: coerced (task section 17's own explicit instruction).
SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION,)


class UnsupportedReferenceProfileSchemaVersionError(ValueError):
    """Raised by `profile_from_json_dict()` when `schema_version` is
    missing or not one of `SUPPORTED_SCHEMA_VERSIONS` -- kept as a
    distinct exception type from `ReferenceProfileValidationError`
    (task section 17: "malformed/unsupported versions fail explicitly")
    so the service/API layer can report a dedicated, unambiguous error
    code rather than a generic validation failure."""

    def __init__(self, message: str, *, schema_version: object) -> None:
        super().__init__(message)
        self.message = message
        self.schema_version = schema_version


def _segment_from_dict(data: object, index: int, *, boundary: str) -> BoundarySegment:
    if not isinstance(data, dict):
        raise ReferenceProfileValidationError(
            f"Segment {index} ({boundary}) must be an object.",
            reason_code="malformed_segment", boundary=boundary, segment_index=index,
        )
    try:
        return BoundarySegment(
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            start_value=float(data["start_value"]),
            end_value=float(data["end_value"]),
            segment_type=str(data["segment_type"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceProfileValidationError(
            f"Segment {index} ({boundary}) is malformed: {exc}",
            reason_code="malformed_segment", boundary=boundary, segment_index=index,
        ) from exc


def _boundary_from_dict(data: object, *, boundary: str) -> ReferenceBoundary | None:
    if data is None:
        return None
    segments_data = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments_data, list):
        raise ReferenceProfileValidationError(
            f"The {boundary} boundary must be an object with a 'segments' list.",
            reason_code="malformed_boundary", boundary=boundary,
        )
    return ReferenceBoundary(segments=tuple(
        _segment_from_dict(seg, i, boundary=boundary) for i, seg in enumerate(segments_data)
    ))


def _metadata_from_dict(data: object) -> ReferenceProfileMetadata:
    data = data if isinstance(data, dict) else {}
    return ReferenceProfileMetadata(
        brand=data.get("brand"),
        equipment_type=data.get("equipment_type"),
        model=data.get("model"),
        firmware_hardware=data.get("firmware_hardware"),
        source_document=data.get("source_document"),
        source_revision=data.get("source_revision"),
        project=data.get("project"),
        plant=data.get("plant"),
        notes=data.get("notes"),
        built_in=bool(data.get("built_in", False)),
        verified=bool(data.get("verified", False)),
    )


def profile_from_json_dict(envelope: object, *, profile_id: str) -> ReferenceProfile:
    """Parses a versioned export envelope (`{"schema_version": ...,
    "profile": {...}}`) into a `ReferenceProfile`, then validates it via
    `validate_reference_profile()` -- never returns a structurally
    invalid profile. `profile_id` is always supplied by the caller
    (never trusted from the file itself) -- an IMPORT always mints a
    fresh id for a new custom session profile (task section 17), and
    built-in loading passes its own stable, file-derived id the same
    way; an id is registry/workspace identity, never portable curve
    data.

    Raises `UnsupportedReferenceProfileSchemaVersionError` for a missing/
    unrecognized `schema_version`, or `ReferenceProfileValidationError`
    for any other malformed/invalid content -- never silently coerces a
    malformed value (task section 17)."""
    if not isinstance(envelope, dict):
        raise ReferenceProfileValidationError("Top-level JSON must be an object.", reason_code="malformed_envelope")
    schema_version = envelope.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedReferenceProfileSchemaVersionError(
            f"Unsupported reference profile schema_version {schema_version!r} "
            f"(supported: {SUPPORTED_SCHEMA_VERSIONS}).",
            schema_version=schema_version,
        )
    data = envelope.get("profile")
    if not isinstance(data, dict):
        raise ReferenceProfileValidationError("Missing or malformed 'profile' object.", reason_code="malformed_envelope")
    try:
        profile = ReferenceProfile(
            id=profile_id,
            name=str(data["name"]),
            category=str(data["category"]),
            evaluation_quantity=str(data["evaluation_quantity"]),
            unit=str(data["unit"]),
            display_start_time=float(data["display_start_time"]),
            display_end_time=float(data["display_end_time"]),
            evaluation_start_time=float(data["evaluation_start_time"]),
            evaluation_end_time=float(data["evaluation_end_time"]),
            tolerance=float(data["tolerance"]),
            lower_boundary=_boundary_from_dict(data.get("lower_boundary"), boundary=BOUNDARY_LOWER),
            upper_boundary=_boundary_from_dict(data.get("upper_boundary"), boundary=BOUNDARY_UPPER),
            metadata=_metadata_from_dict(data.get("metadata")),
        )
    except ReferenceProfileValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceProfileValidationError(f"Profile data is malformed: {exc}", reason_code="malformed_profile") from exc
    validate_reference_profile(profile)
    return profile


def _boundary_to_dict(boundary: ReferenceBoundary | None) -> dict | None:
    if boundary is None:
        return None
    return {
        "segments": [
            {
                "start_time": s.start_time, "end_time": s.end_time,
                "start_value": s.start_value, "end_value": s.end_value,
                "segment_type": s.segment_type,
            }
            for s in boundary.segments
        ]
    }


def _metadata_to_dict(metadata: ReferenceProfileMetadata) -> dict:
    return {
        "brand": metadata.brand,
        "equipment_type": metadata.equipment_type,
        "model": metadata.model,
        "firmware_hardware": metadata.firmware_hardware,
        "source_document": metadata.source_document,
        "source_revision": metadata.source_revision,
        "project": metadata.project,
        "plant": metadata.plant,
        "notes": metadata.notes,
        "built_in": metadata.built_in,
        "verified": metadata.verified,
    }


def profile_to_json_dict(profile: ReferenceProfile) -> dict:
    """The inverse of `profile_from_json_dict()` -- task section 17's
    stable versioned export schema. Deliberately omits `id` from the
    inner `"profile"` object -- an id is workspace/registry-assigned
    identity, not portable curve data; re-import always mints a fresh
    one (see `profile_from_json_dict()`'s own docstring)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": {
            "name": profile.name,
            "category": profile.category,
            "evaluation_quantity": profile.evaluation_quantity,
            "unit": profile.unit,
            "display_start_time": profile.display_start_time,
            "display_end_time": profile.display_end_time,
            "evaluation_start_time": profile.evaluation_start_time,
            "evaluation_end_time": profile.evaluation_end_time,
            "tolerance": profile.tolerance,
            "lower_boundary": _boundary_to_dict(profile.lower_boundary),
            "upper_boundary": _boundary_to_dict(profile.upper_boundary),
            "metadata": _metadata_to_dict(profile.metadata),
        },
    }


def boundary_to_render_points(boundary: ReferenceBoundary) -> list[BoundaryPoint]:
    """Pure, deterministic transform from a validated boundary's own
    segments to a flat, time-ordered polyline ready for direct plotting.

    Right-continuity discontinuity connectors fall out naturally: two
    adjacent segments sharing a time instant simply both emit their own
    endpoint at that instant (previous segment's `end_value` then next
    segment's `start_value`), which a line renderer draws as a vertical
    connector with no special-cased branch. A genuine gap
    (`next.start_time > previous.end_time`) inserts one `BoundaryPoint`
    with `value=None`, breaking the line -- no connector, no reference
    claim across time the profile says nothing about.

    Assumes `boundary` has already passed `validate_reference_profile()`
    (overlap is not re-checked here)."""
    if not boundary.segments:
        return []
    ordered = sorted(boundary.segments, key=lambda s: s.start_time)
    points: list[BoundaryPoint] = []
    previous: BoundarySegment | None = None
    for segment in ordered:
        if previous is not None and segment.start_time > previous.end_time:
            points.append(BoundaryPoint(time=previous.end_time, value=None))
        points.append(BoundaryPoint(time=segment.start_time, value=segment.start_value))
        points.append(BoundaryPoint(time=segment.end_time, value=segment.end_value))
        previous = segment
    return points
