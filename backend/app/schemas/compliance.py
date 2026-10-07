"""Pydantic response schemas for Compliance & Capability -- Voltage
Measurement (Slice 2 + the 2026-09-20 Bay/Measurement Group UAT
correction). Thin translation only -- see `app.services.compliance_
measurement_service` for the actual resolution logic these mirror."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.phase_display import PhaseDisplayOut


class ComplianceVoltageQuantityOut(BaseModel):
    id: str
    display_label: str
    voltage_representation: str


class ComplianceMeasurementGroupOut(BaseModel):
    """One candidate for the Bay/Measurement Group picker -- `id` is the
    stable `measurement_group_id` (task section 6: durable identity, not
    display-name matching); `display_name` is human-friendly only."""

    id: str
    display_name: str
    status: str
    #: The Measurement Group's own source (DEC-167): lets the UI open the
    #: EXISTING group editor ("Configure Base") on the right recording.
    source_id: str | None = None


class ComplianceResolvedRoleOut(BaseModel):
    """`role` is canonical (A/B/C/AB/BC/CA) and `display_name` its stable
    canonical API label ("Va"). DEC-118: the UI spells the role through the
    response's `phase_display`, never from `display_name`."""

    role: str
    display_name: str
    channel_ref: ChannelRefOut
    channel_name: str


class ComplianceBaseOut(BaseModel):
    nominal_voltage_ll_kv: float
    effective_reference: str
    assessment_unit: str


class ComplianceVoltageMeasurementOut(BaseModel):
    status: str
    measurement_group_id: str
    quantity_id: str
    quantity_display_label: str
    voltage_representation: str
    resolved_roles: list[ComplianceResolvedRoleOut] = []
    used_direct_pair: bool = False
    input_type: str | None = None
    value_representation: str | None = None
    base: ComplianceBaseOut | None = None
    assessment_unit: str = "engineering_unit"
    missing: list[str] = []
    message: str | None = None
    phase_display: PhaseDisplayOut


class ComplianceRequirementOut(BaseModel):
    """What one Reference imposes on the measurement (DEC-167) -- derived
    from the Reference, read-only in the UI."""

    representation: str
    phase_treatment: str
    member: str | None = None
    unit: str
    required_members: list[str]
    requires_rms: bool
    requires_per_unit: bool
    unresolved_reason: str | None = None


class CompliancePreparationStepOut(BaseModel):
    kind: str  # "rms" | "line_to_line"
    description: str
    executable: bool
    reason: str | None = None


class ComplianceMemberReadinessOut(BaseModel):
    member: str  # canonical A/B/C, AB/BC/CA, or "1" (positive sequence)
    state: str
    message: str | None = None
    channel_name: str | None = None
    calculated_channel_id: str | None = None


class ComplianceReferenceReadinessOut(BaseModel):
    layer_id: str
    profile_id: str
    profile_name: str
    requirement: ComplianceRequirementOut
    status: str  # "ready" | "action_required" | "incompatible"
    message: str | None = None
    members: list[ComplianceMemberReadinessOut]
    unit_state: str  # "not_required" | "ready" | "action_required"
    unit_message: str | None = None


class ComplianceReadinessOut(BaseModel):
    measurement_group_id: str
    status: str  # "ready" | "action_required" | "incompatible" | "no_reference"
    references: list[ComplianceReferenceReadinessOut]
    steps: list[CompliancePreparationStepOut]
    needs_base: bool
    base: ComplianceBaseOut | None = None
    phase_display: PhaseDisplayOut


class CompliancePrepareRequest(BaseModel):
    measurement_group_id: str


class ComplianceCreatedChannelOut(BaseModel):
    id: str
    name: str
    operation: str


class CompliancePrepareOut(BaseModel):
    created: list[ComplianceCreatedChannelOut]
    readiness: ComplianceReadinessOut


class ComplianceMeasurementTraceOut(BaseModel):
    """One plottable measured trace. `kind`/`members`/`layer_ids` are the
    stable identity the chart carries (never parsed from a legend name);
    `members` are canonical (AB, A, ...) and spelled by the frontend in the
    group's own phase convention."""

    id: str
    kind: str  # "member" | "minimum" | "maximum"
    members: list[str]
    unit: str
    layer_ids: list[str]
    x: list[float]
    y: list[float | None]
    representation: str
    source_id: str


class ComplianceEventAlignmentOut(BaseModel):
    """DEC-170: the Compliance-local alignment of the selected measurement --
    NOT Waveform t0. `comparison_time = measurement_time - measurement_event_origin_s`;
    `alignment_offset_s` (= -origin) is what is added to a measurement time."""

    measurement_group_id: str
    aligned: bool
    measurement_event_origin_s: float | None = None
    alignment_offset_s: float | None = None
    reference_position_s: float = 0.0
    fine_shift_step_s: float
    source_id: str | None = None


class ComplianceEventAlignmentSetRequest(BaseModel):
    measurement_group_id: str
    measurement_event_origin_s: float
    #: True: snap to the nearest actual sample (point selection); False: keep the
    #: exact value (fine shift).
    snap_to_sample: bool = True


class ComplianceSkippedReferenceOut(BaseModel):
    layer_id: str
    profile_name: str
    reason: str


class ComplianceMeasurementTracesOut(BaseModel):
    measurement_group_id: str
    readiness_status: str
    traces: list[ComplianceMeasurementTraceOut]
    skipped: list[ComplianceSkippedReferenceOut]
    alignment: ComplianceEventAlignmentOut
    phase_display: PhaseDisplayOut
