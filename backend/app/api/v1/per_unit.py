"""Phase 5C Per-Unit Base Profile API (DEC-049).

Workspace-scoped, mirroring app.api.v1.calculated_channels's own
conventions (`_validate_workspace_id`/`_http_error`/
`_STATUS_BY_ERROR_CODE`, duplicated per-module rather than shared, same
documented reason: avoiding a circular import between routers).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.per_unit import (
    ChannelAlreadyAssignedConflictOut,
    ChannelAlreadyAssignedErrorOut,
    PerUnitProfileCreateRequest,
    PerUnitProfileOut,
    PerUnitProfileUpdateRequest,
)
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ChannelAlreadyAssignedError, ImportServiceError
from app.services.per_unit_registry import PerUnitRegistry
from app.services.per_unit_service import (
    create_per_unit_profile,
    delete_per_unit_profile,
    update_per_unit_profile,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/per-unit", tags=["per-unit"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "invalid_per_unit_base": status.HTTP_400_BAD_REQUEST,
    "per_unit_profile_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_channel_assignment": status.HTTP_400_BAD_REQUEST,
    "channel_already_assigned": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    if isinstance(exc, ChannelAlreadyAssignedError):
        detail = ChannelAlreadyAssignedErrorOut(
            message=exc.message,
            conflicts=[
                ChannelAlreadyAssignedConflictOut(
                    channel=ChannelRefOut.from_domain(c["channel"]),
                    profile_id=c["profile_id"],
                    profile_name=c["profile_name"],
                )
                for c in exc.conflicts
            ],
        )
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail.model_dump())
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


@router.get("/profiles", response_model=list[PerUnitProfileOut])
def list_profiles(
    workspace_id: str,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
) -> list[PerUnitProfileOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    return [PerUnitProfileOut.from_domain(p) for p in registry.list_for_workspace(workspace_id)]


@router.post("/profiles", status_code=status.HTTP_201_CREATED, response_model=PerUnitProfileOut)
def create_profile(
    workspace_id: str,
    body: PerUnitProfileCreateRequest,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
) -> PerUnitProfileOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = create_per_unit_profile(
            workspace_id=workspace_id,
            name=body.name,
            voltage_base_value=body.voltage_base_value,
            voltage_base_unit=body.voltage_base_unit,
            voltage_basis=body.voltage_basis,
            apparent_power_base_value=body.apparent_power_base_value,
            apparent_power_base_unit=body.apparent_power_base_unit,
            current_base_mode=body.current_base_mode,
            direct_current_base_value=body.direct_current_base_value,
            direct_current_base_unit=body.direct_current_base_unit,
            registry=registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return PerUnitProfileOut.from_domain(profile)


@router.put("/profiles/{profile_id}", response_model=PerUnitProfileOut)
def put_profile(
    workspace_id: str,
    profile_id: str,
    body: PerUnitProfileUpdateRequest,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> PerUnitProfileOut:
    """Decision 4: rejects with `channel_already_assigned` (structured
    conflict details) unless `reassign_conflicting=true` is explicitly
    set. Decision 7: any resulting profile change cascades through the
    calculated-channel inheritance recompute engine before returning."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = update_per_unit_profile(
            workspace_id=workspace_id,
            profile_id=profile_id,
            name=body.name,
            voltage_base_value=body.voltage_base_value,
            voltage_base_unit=body.voltage_base_unit,
            voltage_basis=body.voltage_basis,
            apparent_power_base_value=body.apparent_power_base_value,
            apparent_power_base_unit=body.apparent_power_base_unit,
            current_base_mode=body.current_base_mode,
            direct_current_base_value=body.direct_current_base_value,
            direct_current_base_unit=body.direct_current_base_unit,
            assigned_channels=[ref.to_domain() for ref in body.assigned_channels],
            reassign_conflicting=body.reassign_conflicting,
            registry=registry,
            calc_registry=calc_registry,
            source_registry=source_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return PerUnitProfileOut.from_domain(profile)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    workspace_id: str,
    profile_id: str,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> None:
    """Clears `profile_id` to `None` for every channel that pointed at
    it, preserving each one's own `mode` (decision 7), then runs the
    recompute cascade."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        delete_per_unit_profile(
            workspace_id=workspace_id, profile_id=profile_id, registry=registry, calc_registry=calc_registry
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
