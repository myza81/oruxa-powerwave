"""D5A-2A: read-only authoritative CT/VT context and authority diagnostics for protection analyses.

`GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/protection-instrument-context`

Never converts, persists or overrides anything. The legacy request parameters
(`recording_basis`, `impedance_basis`, `vt_*`, `ct_*`) are accepted only so they can be
compared with Recording Details; they are echoed back verbatim.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.protection_instrument_context import ProtectionInstrumentContextOut
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import ImportServiceError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.protection_context_report_service import (
    InvalidProtectionContextRequest,
    build_protection_context_report,
)
from app.services.protection_instrument_diagnostics import RequestAssumptions
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["protection-instrument-context"])


def _state(request: Request):
    return request.app.state


@router.get(
    "/engineering-contexts/{engineering_context_id}/protection-instrument-context",
    response_model=ProtectionInstrumentContextOut,
)
def get_protection_instrument_context(
    workspace_id: str,
    engineering_context_id: str,
    request: Request,
    analysis: Literal["overcurrent", "impedance", "distance_protection"],
    phase: Literal["A", "B", "C"] | None = None,
    loop: Literal["AB", "BC", "CA"] | None = None,
    recording_basis: str | None = None,
    impedance_basis: str | None = None,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
) -> ProtectionInstrumentContextOut:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    state = _state(request)
    context_registry: EngineeringContextRegistry = state.engineering_context_registry
    source_registry: WorkspaceRegistry = state.workspace_registry
    calc_registry: CalculatedChannelRegistry = state.calculated_channel_registry
    group_registry: MeasurementGroupRegistry = state.measurement_group_registry
    voltage_registry: VoltageGroupConfigRegistry = state.voltage_group_config_registry
    current_registry: CurrentGroupConfigRegistry = state.current_group_config_registry
    try:
        report = build_protection_context_report(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis=analysis,
            phase=phase, loop=loop,
            request=RequestAssumptions(
                recording_basis=recording_basis, impedance_basis=impedance_basis, vt_primary=vt_primary,
                vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            ),
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_registry, current_config_registry=current_registry,
        )
    except InvalidProtectionContextRequest as exc:
        raise HTTPException(
            status_code=422,
            detail=ErrorOut(code="invalid_protection_context_request", message=str(exc)).model_dump(),
        ) from exc
    except ImportServiceError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "engineering_context_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump()) from exc
    return ProtectionInstrumentContextOut.from_report(report)
