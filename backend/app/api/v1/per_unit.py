"""Phase 5C Per-Unit Base configuration API (DEC-049; source-bound
redesign following owner UAT).

Source-scoped: `GET .../per-unit/sources` lists every real source
currently in the workspace (configured or not -- section 1's own "show
each loaded source/file automatically" requirement), and
`PUT/DELETE .../per-unit/sources/{source_id}` create/replace/clear ONE
source's own configuration. No separate profile identity, no
channel-assignment endpoint -- every eligible channel of a source uses
its own source's configuration automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.per_unit import PerUnitCoverageOut, SourcePerUnitConfigOut, SourcePerUnitConfigUpdateRequest
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import ImportServiceError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_coverage_service import build_per_unit_coverage_summary
from app.services.per_unit_registry import PerUnitRegistry
from app.services.per_unit_service import (
    delete_source_per_unit_config,
    get_source_per_unit_config,
    list_source_per_unit_configs,
    upsert_source_per_unit_config,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/per-unit", tags=["per-unit"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "invalid_per_unit_base": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


# Slice 2 (Per-Unit Settings hierarchy, coverage): mirrors
# app.api.v1.measurement_groups's own identically-named getters verbatim
# -- this codebase's established pattern is a small, router-local getter
# per registry rather than a shared cross-router import (see that
# module's own `get_workspace_registry`, duplicated rather than
# imported, for precedent).
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


@router.get("/sources", response_model=list[SourcePerUnitConfigOut])
def list_sources(
    workspace_id: str,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[SourcePerUnitConfigOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    views = list_source_per_unit_configs(workspace_id=workspace_id, registry=registry, source_registry=source_registry)
    return [SourcePerUnitConfigOut.from_view(v) for v in views]


@router.get("/sources/{source_id}", response_model=SourcePerUnitConfigOut)
def get_source(
    workspace_id: str,
    source_id: str,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourcePerUnitConfigOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = get_source_per_unit_config(
            workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return SourcePerUnitConfigOut.from_view(view)


@router.put("/sources/{source_id}", response_model=SourcePerUnitConfigOut)
def put_source(
    workspace_id: str,
    source_id: str,
    body: SourcePerUnitConfigUpdateRequest,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> SourcePerUnitConfigOut:
    """Section 1/14: create-or-replace this ONE source's own
    configuration. 404 `source_not_found` if `source_id` does not exist
    in this workspace. Runs the calculated-channel inheritance-recompute
    cascade before returning (decision 7, unchanged)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = upsert_source_per_unit_config(
            workspace_id=workspace_id,
            source_id=source_id,
            voltage_base_value=body.voltage_base_value,
            voltage_reference_mode=body.voltage_reference_mode,
            voltage_reference_override=body.voltage_reference_override,
            current_base_mode=body.current_base_mode,
            apparent_power_base_value=body.apparent_power_base_value,
            direct_current_base_value=body.direct_current_base_value,
            registry=registry,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return SourcePerUnitConfigOut.from_view(view)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    workspace_id: str,
    source_id: str,
    registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> None:
    """Idempotent -- clearing an unconfigured source's configuration is
    a successful no-op, matching this codebase's own established
    idempotent-DELETE convention."""
    workspace_id = _validate_workspace_id(workspace_id)
    delete_source_per_unit_config(
        workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry, calc_registry=calc_registry
    )


@router.get("/sources/{source_id}/coverage", response_model=PerUnitCoverageOut)
def get_source_coverage(
    workspace_id: str,
    source_id: str,
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> PerUnitCoverageOut:
    """Per-Unit Settings hierarchy, Slice 2: one source's own Per-Unit
    coverage breakdown -- how many applicable Voltage/Current channels
    are covered by a Measurement Group, how many fall to Source Default,
    and how many currently need configuration. Read-only, derived fresh
    per request from already-existing metadata/registry state (see
    app.services.per_unit_coverage_service) -- never persisted, never
    mutates anything. 404 `source_not_found` if `source_id` does not
    exist in this workspace."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        summary = build_per_unit_coverage_summary(
            workspace_id=workspace_id,
            source_id=source_id,
            source_registry=source_registry,
            per_unit_registry=per_unit_registry,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return PerUnitCoverageOut.from_summary(summary)
