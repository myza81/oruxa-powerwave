"""Pydantic request/response schemas for Compliance & Capability --
Reference Profiles / Reference Layers / Comparison Chart (Slice 3;
Assessment Definition, Slice 4/DEC-110). Thin translation only -- see
`app.services.reference_profile_service` for the actual orchestration
these mirror, and `app.domain.reference_profile`/`app.domain.
assessment_definition` for the domain objects `to_domain()`/
`from_domain()` convert to and from.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.domain.assessment_definition import AssessmentDefinition
from app.domain.reference_layer import ReferenceLayer
from app.domain.reference_profile import (
    BoundaryPoint,
    BoundarySegment,
    ReferenceBoundary,
    ReferenceProfile,
    ReferenceProfileMetadata,
)
from app.services.reference_profile_service import (
    ComparisonChart,
    ComparisonChartTrace,
    ReferenceProfileEntry,
)


class BoundarySegmentIn(BaseModel):
    start_time: float
    end_time: float
    start_value: float
    end_value: float
    segment_type: str

    def to_domain(self) -> BoundarySegment:
        return BoundarySegment(
            start_time=self.start_time, end_time=self.end_time,
            start_value=self.start_value, end_value=self.end_value, segment_type=self.segment_type,
        )


class BoundarySegmentOut(BaseModel):
    start_time: float
    end_time: float
    start_value: float
    end_value: float
    segment_type: str

    @classmethod
    def from_domain(cls, segment: BoundarySegment) -> "BoundarySegmentOut":
        return cls(
            start_time=segment.start_time, end_time=segment.end_time,
            start_value=segment.start_value, end_value=segment.end_value, segment_type=segment.segment_type,
        )


class ReferenceBoundaryIn(BaseModel):
    segments: list[BoundarySegmentIn]

    def to_domain(self) -> ReferenceBoundary:
        return ReferenceBoundary(segments=tuple(s.to_domain() for s in self.segments))


class ReferenceBoundaryOut(BaseModel):
    segments: list[BoundarySegmentOut]

    @classmethod
    def from_domain(cls, boundary: ReferenceBoundary) -> "ReferenceBoundaryOut":
        return cls(segments=[BoundarySegmentOut.from_domain(s) for s in boundary.segments])


class ReferenceProfileMetadataIn(BaseModel):
    brand: str | None = None
    equipment_type: str | None = None
    model: str | None = None
    firmware_hardware: str | None = None
    source_document: str | None = None
    source_revision: str | None = None
    project: str | None = None
    plant: str | None = None
    notes: str | None = None

    def to_domain(self) -> ReferenceProfileMetadata:
        # `built_in`/`verified` are never accepted from a create/update
        # request body -- the service layer decides `built_in` (always
        # False for anything created/updated/imported through this API);
        # `verified` is reserved for a future authoritative-source
        # workflow and stays False unless a later slice adds one.
        return ReferenceProfileMetadata(
            brand=self.brand, equipment_type=self.equipment_type, model=self.model,
            firmware_hardware=self.firmware_hardware, source_document=self.source_document,
            source_revision=self.source_revision, project=self.project, plant=self.plant, notes=self.notes,
        )


class ReferenceProfileMetadataOut(BaseModel):
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

    @classmethod
    def from_domain(cls, metadata: ReferenceProfileMetadata) -> "ReferenceProfileMetadataOut":
        return cls(
            brand=metadata.brand, equipment_type=metadata.equipment_type, model=metadata.model,
            firmware_hardware=metadata.firmware_hardware, source_document=metadata.source_document,
            source_revision=metadata.source_revision, project=metadata.project, plant=metadata.plant,
            notes=metadata.notes, built_in=metadata.built_in, verified=metadata.verified,
        )


class AssessmentDefinitionIn(BaseModel):
    """DEC-110: HOW a measured voltage should be derived for a future
    comparison -- separate from the reference boundary/curve itself
    (`ReferenceProfileWriteRequest`'s own fields). Every field defaults
    to its own `unspecified`/`None` state -- `AssessmentDefinitionIn()`
    (all defaults) is the fully-unspecified state, always valid on its
    own (task section 8: never guess)."""

    quantity_family: str = "voltage"
    representation: str = "unspecified"
    phase_treatment: str = "unspecified"
    member: str | None = None
    measurement_location: str = "unspecified"
    provenance: str = "unspecified"

    def to_domain(self) -> AssessmentDefinition:
        # `legacy_quantity_hint` is never accepted from a create/update
        # request body -- it is an audit trail the MIGRATION path alone
        # populates (v1 import, or the legacy-mapping helper); a
        # from-scratch write through this API has no legacy value to
        # preserve.
        return AssessmentDefinition(
            quantity_family=self.quantity_family, representation=self.representation,
            phase_treatment=self.phase_treatment, member=self.member,
            measurement_location=self.measurement_location, provenance=self.provenance,
        )


class AssessmentDefinitionOut(BaseModel):
    quantity_family: str
    representation: str
    phase_treatment: str
    member: str | None = None
    measurement_location: str
    provenance: str
    legacy_quantity_hint: str | None = None

    @classmethod
    def from_domain(cls, definition: AssessmentDefinition) -> "AssessmentDefinitionOut":
        return cls(
            quantity_family=definition.quantity_family, representation=definition.representation,
            phase_treatment=definition.phase_treatment, member=definition.member,
            measurement_location=definition.measurement_location, provenance=definition.provenance,
            legacy_quantity_hint=definition.legacy_quantity_hint,
        )


class ReferenceProfileWriteRequest(BaseModel):
    """Shared shape for both create and update (full replace, mirrors
    `MeasurementGroupRegistry.update()`'s own convention -- there is no
    partial-patch concept at this layer)."""

    name: str
    category: str
    assessment_definition: AssessmentDefinitionIn = AssessmentDefinitionIn()
    unit: str
    display_start_time: float
    display_end_time: float
    evaluation_start_time: float
    evaluation_end_time: float
    tolerance: float
    lower_boundary: ReferenceBoundaryIn | None = None
    upper_boundary: ReferenceBoundaryIn | None = None
    metadata: ReferenceProfileMetadataIn = ReferenceProfileMetadataIn()

    def to_domain(self, *, profile_id: str) -> ReferenceProfile:
        return ReferenceProfile(
            id=profile_id,
            name=self.name,
            category=self.category,
            assessment_definition=self.assessment_definition.to_domain(),
            unit=self.unit,
            display_start_time=self.display_start_time,
            display_end_time=self.display_end_time,
            evaluation_start_time=self.evaluation_start_time,
            evaluation_end_time=self.evaluation_end_time,
            tolerance=self.tolerance,
            lower_boundary=self.lower_boundary.to_domain() if self.lower_boundary is not None else None,
            upper_boundary=self.upper_boundary.to_domain() if self.upper_boundary is not None else None,
            metadata=self.metadata.to_domain(),
        )


class ReferenceProfileOut(BaseModel):
    id: str
    source: str  # "built_in" | "custom"
    name: str
    category: str
    assessment_definition: AssessmentDefinitionOut
    unit: str
    display_start_time: float
    display_end_time: float
    evaluation_start_time: float
    evaluation_end_time: float
    tolerance: float
    lower_boundary: ReferenceBoundaryOut | None = None
    upper_boundary: ReferenceBoundaryOut | None = None
    metadata: ReferenceProfileMetadataOut

    @classmethod
    def from_entry(cls, entry: ReferenceProfileEntry) -> "ReferenceProfileOut":
        profile = entry.profile
        return cls(
            id=profile.id,
            source=entry.source,
            name=profile.name,
            category=profile.category,
            assessment_definition=AssessmentDefinitionOut.from_domain(profile.assessment_definition),
            unit=profile.unit,
            display_start_time=profile.display_start_time,
            display_end_time=profile.display_end_time,
            evaluation_start_time=profile.evaluation_start_time,
            evaluation_end_time=profile.evaluation_end_time,
            tolerance=profile.tolerance,
            lower_boundary=ReferenceBoundaryOut.from_domain(profile.lower_boundary) if profile.lower_boundary is not None else None,
            upper_boundary=ReferenceBoundaryOut.from_domain(profile.upper_boundary) if profile.upper_boundary is not None else None,
            metadata=ReferenceProfileMetadataOut.from_domain(profile.metadata),
        )


class ReferenceProfileImportRequest(BaseModel):
    """Accepts the raw versioned export envelope verbatim (`{"schema_
    version": 1 | 2, "profile": {...}}` -- `1` is a read-only migration
    path, DEC-110) -- deliberately loose (`profile` stays an untyped
    dict) so the ONE structural/domain validation path lives in
    `app.domain.reference_profile.profile_from_json_dict()`, never
    duplicated as a second, parallel Pydantic shape that could silently
    drift from it."""

    schema_version: int | None = None
    profile: dict[str, Any] | None = None

    def to_envelope(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "profile": self.profile}


class ReferenceLayerCompatibilityOut(BaseModel):
    status: str  # "compatible" | "not_yet_applicable" | "incompatible"
    reason: str | None = None


class ReferenceLayerOut(BaseModel):
    id: str
    profile_id: str
    visible: bool
    order: int
    profile: ReferenceProfileOut
    compatibility: ReferenceLayerCompatibilityOut

    @classmethod
    def from_domain(
        cls, layer: ReferenceLayer, profile_entry: ReferenceProfileEntry, *,
        compatibility_status: str, compatibility_reason: str | None,
    ) -> "ReferenceLayerOut":
        return cls(
            id=layer.id, profile_id=layer.profile_id, visible=layer.visible, order=layer.order,
            profile=ReferenceProfileOut.from_entry(profile_entry),
            compatibility=ReferenceLayerCompatibilityOut(status=compatibility_status, reason=compatibility_reason),
        )


class ReferenceLayerCreateRequest(BaseModel):
    profile_id: str
    visible: bool = True


class ReferenceLayerUpdateRequest(BaseModel):
    visible: bool


class ComparisonChartPointOut(BaseModel):
    t: float
    v: float | None

    @classmethod
    def from_domain(cls, point: BoundaryPoint) -> "ComparisonChartPointOut":
        return cls(t=point.time, v=point.value)


class ComparisonChartTraceOut(BaseModel):
    layer_id: str
    profile_id: str
    profile_name: str
    category: str
    boundary: str  # "lower" | "upper"
    unit: str
    visible: bool
    on_axis: bool
    compatibility: ReferenceLayerCompatibilityOut
    points: list[ComparisonChartPointOut]

    @classmethod
    def from_domain(cls, trace: ComparisonChartTrace) -> "ComparisonChartTraceOut":
        return cls(
            layer_id=trace.layer_id, profile_id=trace.profile_id, profile_name=trace.profile_name,
            category=trace.category, boundary=trace.boundary, unit=trace.unit, visible=trace.visible,
            on_axis=trace.on_axis,
            compatibility=ReferenceLayerCompatibilityOut(status=trace.compatibility_status, reason=trace.compatibility_reason),
            points=[ComparisonChartPointOut.from_domain(p) for p in trace.points],
        )


class ComparisonChartOut(BaseModel):
    traces: list[ComparisonChartTraceOut]
    axis_unit: str | None
    x_min: float | None
    x_max: float | None
    unit_groups: dict[str, list[str]]

    @classmethod
    def from_domain(cls, chart: ComparisonChart) -> "ComparisonChartOut":
        return cls(
            traces=[ComparisonChartTraceOut.from_domain(t) for t in chart.traces],
            axis_unit=chart.axis_unit, x_min=chart.x_min, x_max=chart.x_max, unit_groups=chart.unit_groups,
        )
