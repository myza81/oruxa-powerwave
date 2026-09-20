"""Compliance & Capability -- Voltage Measurement REST exposure (Slice
2). Thin translation only -- every endpoint calls straight into
`app.services.compliance_measurement_service`, an already-tested
service function; no new domain semantics live here.

Deliberately its OWN router/file, never added to `app.api.v1.
engineering_contexts` -- Compliance is architecturally independent of
Analysis/Engineering Context (DEC-100), and neither endpoint below
accepts or resolves an `engineering_context_id`; both are purely
workspace-scoped, mirroring `GET .../overcurrent-characteristics`'s own
"no context needed" shape rather than the context-nested analyzer
endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.compliance import (
    ComplianceBaseOut,
    ComplianceResolvedRoleOut,
    ComplianceVoltageMeasurementOut,
    ComplianceVoltageQuantityOut,
)
from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.source import ErrorOut
from app.services.compliance_measurement_service import (
    ComplianceVoltageMeasurementResult,
    ROLE_DISPLAY_NAME,
    evaluate_voltage_measurement,
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


def _result_to_out(result: ComplianceVoltageMeasurementResult) -> ComplianceVoltageMeasurementOut:
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
    )


@router.get("/compliance/voltage/quantities", response_model=list[ComplianceVoltageQuantityOut])
def list_compliance_voltage_quantities(workspace_id: str) -> list[ComplianceVoltageQuantityOut]:
    _validate_workspace_id(workspace_id)
    return [
        ComplianceVoltageQuantityOut(id=q.id, display_label=q.display_label, voltage_representation=q.voltage_representation)
        for q in list_voltage_quantities()
    ]


@router.get("/compliance/voltage/measurement", response_model=ComplianceVoltageMeasurementOut)
def get_compliance_voltage_measurement(
    workspace_id: str,
    quantity_id: str,
    request: Request,
) -> ComplianceVoltageMeasurementOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = evaluate_voltage_measurement(
            workspace_id=workspace_id,
            quantity_id=quantity_id,
            source_registry=get_workspace_registry(request),
            group_registry=get_measurement_group_registry(request),
            voltage_config_registry=get_voltage_group_config_registry(request),
            current_config_registry=get_current_group_config_registry(request),
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _result_to_out(result)
