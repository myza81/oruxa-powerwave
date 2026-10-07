"""Compliance & Capability -- Voltage Measurement REST exposure (Slice
2 + the 2026-09-20 Bay/Measurement Group UAT correction + the
2026-09-23 group-discovery/bootstrap UAT correction). Thin translation
only -- every endpoint calls straight into `app.services.compliance_
measurement_service`, an already-tested service function; no new domain
semantics live here.

Deliberately its OWN router/file, never added to `app.api.v1.
engineering_contexts` OR to `app.api.v1.measurement_groups` -- Compliance
is architecturally independent of Analysis/Engineering Context
(DEC-100), and none of the endpoints below accept or resolve an
`engineering_context_id`. `GET .../compliance/voltage/measurement-groups`
reuses the EXISTING `MeasurementGroupRegistry.list_for_workspace()`
(already present at the service layer, just not previously exposed
workspace-wide over REST -- `app.api.v1.measurement_groups`'s own
router is source-scoped, `.../sources/{source_id}/measurement-groups`,
for its CRUD/configuration purpose) -- this is a lean, read-only,
Voltage-only view for the Bay picker, not a second Measurement Group
model (task section 1/6). It returns EVERY Voltage-kind group
regardless of status (2026-09-23 correction) -- see this module's own
`list_compliance_voltage_measurement_groups()` docstring for why.
Materializing those groups in the first place (bootstrap/discovery) is
NOT this router's job -- the existing, unchanged `POST .../sources/
{source_id}/measurement-groups/suggest` endpoint remains the sole
detection trigger; the frontend's own `wwComplianceLoadGroups()` now
calls it for every not-yet-attempted loaded source before listing
groups, mirroring the Analysis workspace's own proven bootstrap pattern
(`wwAnalysisDiscoverUncoveredSources()`) rather than requiring a visit
to another page first. `GET .../compliance/voltage/measurement` still
REQUIRES an explicit `measurement_group_id` query param -- role
resolution is scoped to that one group's own membership, never the
whole workspace (see DEC-102).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.compliance import (
    ComplianceBaseOut,
    ComplianceCreatedChannelOut,
    ComplianceEventAlignmentOut,
    ComplianceEventAlignmentSetRequest,
    ComplianceMeasurementTraceOut,
    ComplianceMeasurementTracesOut,
    ComplianceMemberReadinessOut,
    ComplianceSkippedReferenceOut,
    ComplianceMeasurementGroupOut,
    CompliancePreparationStepOut,
    CompliancePrepareOut,
    CompliancePrepareRequest,
    ComplianceReadinessOut,
    ComplianceReferenceReadinessOut,
    ComplianceRequirementOut,
    ComplianceResolvedRoleOut,
    ComplianceVoltageMeasurementOut,
    ComplianceVoltageQuantityOut,
)
from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.phase_display import PhaseDisplayOut
from app.schemas.source import ErrorOut
from app.domain.compliance_alignment import FINE_SHIFT_STEP_S
from app.services.compliance_alignment_service import (
    AlignmentView,
    clear_alignment,
    current_alignment,
    get_alignment,
    set_alignment,
    view_of,
)
from app.services.compliance_series import Registries
from app.services.compliance_trace_service import build_measurement_traces
from app.services.compliance_readiness_service import (
    PreparationOutcome,
    ReadinessResult,
    evaluate_readiness,
    prepare_measurement,
)
from app.services.compliance_measurement_service import (
    ComplianceVoltageMeasurementResult,
    ROLE_DISPLAY_NAME,
    evaluate_voltage_measurement,
    list_compliance_voltage_groups,
    list_voltage_quantities,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import ImportServiceError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["compliance"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "unknown_compliance_quantity": status.HTTP_400_BAD_REQUEST,
    "invalid_compliance_alignment": status.HTTP_400_BAD_REQUEST,
    "measurement_group_not_found": status.HTTP_404_NOT_FOUND,
    "compliance_measurement_group_not_voltage_kind": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_measurement_group_registry(request: Request) -> MeasurementGroupRegistry:
    return request.app.state.measurement_group_registry


def get_voltage_group_config_registry(request: Request) -> VoltageGroupConfigRegistry:
    return request.app.state.voltage_group_config_registry


def get_current_group_config_registry(request: Request) -> CurrentGroupConfigRegistry:
    return request.app.state.current_group_config_registry


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


def _result_to_out(result: ComplianceVoltageMeasurementResult, *, measurement_group_id: str) -> ComplianceVoltageMeasurementOut:
    resolved_roles = [
        ComplianceResolvedRoleOut(
            role=role, display_name=ROLE_DISPLAY_NAME[role],
            channel_ref=ChannelRefOut.from_domain(entry.channel_ref), channel_name=entry.channel_name,
        )
        for role, entry in result.resolved_roles.items()
    ]
    base = (
        ComplianceBaseOut(
            nominal_voltage_ll_kv=result.base.nominal_voltage_ll_kv,
            effective_reference=result.base.effective_reference,
            assessment_unit=result.base.assessment_unit,
        )
        if result.base is not None else None
    )
    return ComplianceVoltageMeasurementOut(
        status=result.status,
        measurement_group_id=measurement_group_id,
        quantity_id=result.quantity.id,
        quantity_display_label=result.quantity.display_label,
        voltage_representation=result.quantity.voltage_representation,
        resolved_roles=resolved_roles,
        used_direct_pair=result.used_direct_pair,
        input_type=result.input_type,
        value_representation=result.value_representation,
        base=base,
        assessment_unit=result.assessment_unit,
        missing=[ROLE_DISPLAY_NAME[role] for role in result.missing],
        message=result.message,
        phase_display=PhaseDisplayOut.from_domain(result.phase_display),
    )


@router.get("/compliance/voltage/quantities", response_model=list[ComplianceVoltageQuantityOut])
def list_compliance_voltage_quantities(workspace_id: str) -> list[ComplianceVoltageQuantityOut]:
    _validate_workspace_id(workspace_id)
    return [
        ComplianceVoltageQuantityOut(id=q.id, display_label=q.display_label, voltage_representation=q.voltage_representation)
        for q in list_voltage_quantities()
    ]


@router.get("/compliance/voltage/measurement-groups", response_model=list[ComplianceMeasurementGroupOut])
def list_compliance_voltage_measurement_groups(workspace_id: str, request: Request) -> list[ComplianceMeasurementGroupOut]:
    """The Bay/Measurement Group picker's own candidate list -- EVERY
    Voltage-kind group in the workspace, of any status (2026-09-23 UAT
    correction: `needs_review` groups are no longer excluded at this
    layer -- each returned entry's own `status` field lets the frontend
    distinguish usable from review-required, rather than a review-
    required workspace silently looking identical to a genuinely empty
    one). Stable `id` is always the real `measurement_group_id`."""
    workspace_id = _validate_workspace_id(workspace_id)
    groups = list_compliance_voltage_groups(
        workspace_id=workspace_id, group_registry=get_measurement_group_registry(request)
    )
    return [ComplianceMeasurementGroupOut(id=g.id, display_name=g.display_name, status=g.status, source_id=g.source_id) for g in groups]


@router.get("/compliance/voltage/measurement", response_model=ComplianceVoltageMeasurementOut)
def get_compliance_voltage_measurement(
    workspace_id: str,
    measurement_group_id: str,
    quantity_id: str,
    request: Request,
) -> ComplianceVoltageMeasurementOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = evaluate_voltage_measurement(
            workspace_id=workspace_id,
            measurement_group_id=measurement_group_id,
            quantity_id=quantity_id,
            source_registry=get_workspace_registry(request),
            group_registry=get_measurement_group_registry(request),
            voltage_config_registry=get_voltage_group_config_registry(request),
            current_config_registry=get_current_group_config_registry(request),
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _result_to_out(result, measurement_group_id=measurement_group_id)


def _alignment_out(view: AlignmentView) -> ComplianceEventAlignmentOut:
    return ComplianceEventAlignmentOut(
        measurement_group_id=view.measurement_group_id, aligned=view.aligned,
        measurement_event_origin_s=view.measurement_event_origin_s, alignment_offset_s=view.alignment_offset_s,
        fine_shift_step_s=FINE_SHIFT_STEP_S, source_id=view.source_id,
    )


def _readiness_to_out(result: ReadinessResult) -> ComplianceReadinessOut:
    return ComplianceReadinessOut(
        measurement_group_id=result.measurement_group_id,
        status=result.status,
        references=[
            ComplianceReferenceReadinessOut(
                layer_id=r.layer_id, profile_id=r.profile_id, profile_name=r.profile_name,
                requirement=ComplianceRequirementOut(
                    representation=r.requirement.representation, phase_treatment=r.requirement.phase_treatment,
                    member=r.requirement.member, unit=r.requirement.unit,
                    required_members=list(r.requirement.required_members), requires_rms=r.requirement.requires_rms,
                    requires_per_unit=r.requirement.requires_per_unit, unresolved_reason=r.requirement.unresolved_reason,
                ),
                status=r.status, message=r.message,
                members=[
                    ComplianceMemberReadinessOut(
                        member=m.member, state=m.state, message=m.message, channel_name=m.channel_name,
                        calculated_channel_id=m.calculated_channel_id,
                    )
                    for m in r.members
                ],
                unit_state=r.unit_state, unit_message=r.unit_message,
            )
            for r in result.references
        ],
        steps=[
            CompliancePreparationStepOut(kind=st.kind, description=st.description, executable=st.executable, reason=st.reason)
            for st in result.steps
        ],
        needs_base=result.needs_base,
        base=(
            ComplianceBaseOut(
                nominal_voltage_ll_kv=result.base.nominal_voltage_ll_kv,
                effective_reference=result.base.effective_reference, assessment_unit=result.base.assessment_unit,
            )
            if result.base is not None else None
        ),
        phase_display=PhaseDisplayOut.from_domain(result.phase_display),
    )


def _readiness_deps(request: Request) -> dict:
    state = request.app.state
    return dict(
        source_registry=state.workspace_registry, group_registry=state.measurement_group_registry,
        voltage_config_registry=state.voltage_group_config_registry,
        current_config_registry=state.current_group_config_registry, calc_registry=state.calculated_channel_registry,
        context_registry=state.engineering_context_registry, layer_registry=state.reference_layer_registry,
        profile_registry=state.reference_profile_registry, per_unit_registry=state.per_unit_registry,
    )


@router.get("/compliance/voltage/readiness", response_model=ComplianceReadinessOut)
def get_compliance_voltage_readiness(workspace_id: str, measurement_group_id: str, request: Request) -> ComplianceReadinessOut:
    """DEC-167: what the active Reference Layer(s) require of the selected
    Measurement Group, and whether the recording can satisfy it. Read-only:
    never creates a channel or a configuration."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = evaluate_readiness(
            workspace_id=workspace_id, measurement_group_id=measurement_group_id, **_readiness_deps(request),
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _readiness_to_out(result)


@router.post("/compliance/voltage/prepare", response_model=CompliancePrepareOut)
def prepare_compliance_voltage_measurement(
    workspace_id: str, body: CompliancePrepareRequest, request: Request,
) -> CompliancePrepareOut:
    """DEC-167: creates ONLY the missing shared resources (RMS / line-line
    calculated channels, through the shared Calculated Channel services),
    reusing equivalents. Never writes a per-unit base."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        outcome: PreparationOutcome = prepare_measurement(
            workspace_id=workspace_id, measurement_group_id=body.measurement_group_id, **_readiness_deps(request),
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return CompliancePrepareOut(
        created=[ComplianceCreatedChannelOut(id=c.id, name=c.name, operation=c.operation) for c in outcome.created],
        readiness=_readiness_to_out(outcome.result),
    )


@router.get("/compliance/voltage/measurement-traces", response_model=ComplianceMeasurementTracesOut)
def get_compliance_voltage_measurement_traces(
    workspace_id: str, measurement_group_id: str, request: Request,
) -> ComplianceMeasurementTracesOut:
    """DEC-169: the measured trace(s) the Comparison Chart plots for every
    READY active Reference of the selected Measurement Group, in the
    Reference's unit and on the workspace's event-relative time axis.
    Read-only; it prepares nothing (readiness / prepare do that)."""
    workspace_id = _validate_workspace_id(workspace_id)
    state = request.app.state
    try:
        readiness = evaluate_readiness(
            workspace_id=workspace_id, measurement_group_id=measurement_group_id, **_readiness_deps(request),
        )
        alignment = view_of(
            current_alignment(
                workspace_id, measurement_group_id, registry=state.compliance_alignment_registry,
                group_registry=state.measurement_group_registry, source_registry=state.workspace_registry,
            ),
            measurement_group_id,
        )
        result = build_measurement_traces(
            workspace_id=workspace_id, measurement_group_id=measurement_group_id, readiness=readiness,
            registries=Registries(
                source=state.workspace_registry, calc=state.calculated_channel_registry,
                per_unit=state.per_unit_registry, group=state.measurement_group_registry,
                voltage_config=state.voltage_group_config_registry, current_config=state.current_group_config_registry,
            ),
            alignment=alignment,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ComplianceMeasurementTracesOut(
        measurement_group_id=measurement_group_id,
        readiness_status=result.readiness_status,
        traces=[
            ComplianceMeasurementTraceOut(
                id=t.id, kind=t.kind, members=list(t.members), unit=t.unit, layer_ids=list(t.layer_ids),
                x=t.x, y=t.y, representation=t.representation, source_id=t.source_id,
            )
            for t in result.traces
        ],
        skipped=[
            ComplianceSkippedReferenceOut(layer_id=k.layer_id, profile_name=k.profile_name, reason=k.reason)
            for k in result.skipped
        ],
        alignment=_alignment_out(result.alignment),
        phase_display=PhaseDisplayOut.from_domain(readiness.phase_display),
    )


@router.get("/compliance/voltage/event-alignment", response_model=ComplianceEventAlignmentOut)
def get_compliance_event_alignment(workspace_id: str, measurement_group_id: str, request: Request) -> ComplianceEventAlignmentOut:
    """DEC-170: the Compliance-local alignment of the selected measurement. Not
    Waveform t0 -- this reads and writes no Waveform / Time Group state."""
    workspace_id = _validate_workspace_id(workspace_id)
    state = request.app.state
    try:
        view = get_alignment(
            workspace_id, measurement_group_id, registry=state.compliance_alignment_registry,
            group_registry=state.measurement_group_registry, source_registry=state.workspace_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _alignment_out(view)


@router.put("/compliance/voltage/event-alignment", response_model=ComplianceEventAlignmentOut)
def put_compliance_event_alignment(
    workspace_id: str, body: ComplianceEventAlignmentSetRequest, request: Request,
) -> ComplianceEventAlignmentOut:
    """Sets the recording time of the disturbance as Reference t = 0 (snapped to
    the nearest actual sample for a point selection; exact for a fine shift)."""
    workspace_id = _validate_workspace_id(workspace_id)
    state = request.app.state
    try:
        view = set_alignment(
            workspace_id, body.measurement_group_id, measurement_event_origin_s=body.measurement_event_origin_s,
            snap=body.snap_to_sample, registry=state.compliance_alignment_registry,
            group_registry=state.measurement_group_registry, source_registry=state.workspace_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _alignment_out(view)


@router.delete("/compliance/voltage/event-alignment", response_model=ComplianceEventAlignmentOut)
def delete_compliance_event_alignment(workspace_id: str, measurement_group_id: str, request: Request) -> ComplianceEventAlignmentOut:
    """Clears the alignment: back to the measurement's own recording time."""
    workspace_id = _validate_workspace_id(workspace_id)
    state = request.app.state
    try:
        view = clear_alignment(
            workspace_id, measurement_group_id, registry=state.compliance_alignment_registry,
            group_registry=state.measurement_group_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _alignment_out(view)
