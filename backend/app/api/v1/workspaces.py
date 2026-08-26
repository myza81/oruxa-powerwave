"""Phase 1 whole-workspace lifecycle API.

Distinct from app.api.v1.sources's per-source DELETE: this endpoint is the
backend counterpart of the frontend's "Start new workspace" action -- see
docs/project-memory/DECISIONS.md DEC-018. Removing one source ("Remove")
and discarding an entire workspace ("Start new workspace") are different
operations with different blast radius; conflating them into a frontend
loop of per-source DELETEs would put whole-workspace cleanup semantics in
the client instead of the backend. This endpoint establishes that boundary
in the backend now, before a workspace owns more than source records (see
docs/project-memory/MIGRATION_PLAN.md's Phase 1 workspace-reset record) --
any future workspace-owned resource (synchronization state, calculated
channels, measurements, ...) has one lifecycle hook to plug into, not one
per resource type.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import remove_workspace_synchronization_state
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


def get_measurement_group_registry(request: Request) -> MeasurementGroupRegistry:
    return request.app.state.measurement_group_registry


def get_voltage_group_config_registry(request: Request) -> VoltageGroupConfigRegistry:
    return request.app.state.voltage_group_config_registry


def get_current_group_config_registry(request: Request) -> CurrentGroupConfigRegistry:
    return request.app.state.current_group_config_registry


def get_synchronization_registry(request: Request) -> SynchronizationRegistry:
    return request.app.state.synchronization_registry


def _validate_workspace_id(workspace_id: str) -> str:
    # Same shape check as app.api.v1.sources -- never used as a filesystem
    # path, so this guards against a blank/whitespace-only id, not path
    # traversal.
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> None:
    """Release every source this workspace owns.

    Idempotent and safe for an unknown or already-empty ``workspace_id``:
    a workspace is never explicitly "created" server-side (see
    app.api.v1.sources -- it comes into existence the moment a source is
    uploaded under it), so there is no meaningful "workspace not found"
    error to raise here. Deleting nothing is a successful no-op, matching
    standard idempotent-DELETE semantics.

    Phase 5A (DEC-047, section 66): this is the "one lifecycle hook to
    plug into" this module's own docstring already anticipated -- Start
    New Workspace also releases every calculated channel this workspace
    owns, via the same idempotent pattern.

    Phase 5C (DEC-049): also releases every per-unit base profile and
    channel-assignment record this workspace owns, the same way.

    Slice 1 (DEC-050): also releases every measurement group this
    workspace owns -- internal scaffolding, not yet visible through any
    API response, but its lifecycle must not outlive the workspace it
    belongs to (workspace isolation).

    Slice 3 (DEC-050): also releases every Voltage group's own base
    configuration this workspace owns, the same way.

    Slice 4 (DEC-050): also releases every Current group's own base
    configuration this workspace owns, the same way.

    Slice 1 of waveform time synchronization: also releases every
    source's own manual alignment offset this workspace owns, the same
    way (task section 10: "workspace reset/new workspace" must clear
    all synchronization state).

    Slice 2 of waveform time synchronization: also releases this
    workspace's own single event origin (t0), the same way (task
    section 15: "t=0 is workspace-scoped state. It must be cleared when
    starting a new workspace; deleting/resetting the workspace").
    """
    workspace_id = _validate_workspace_id(workspace_id)
    registry.remove_workspace(workspace_id)
    calc_registry.remove_workspace(workspace_id)
    per_unit_registry.remove_workspace(workspace_id)
    measurement_group_registry.remove_workspace(workspace_id)
    voltage_group_config_registry.remove_workspace(workspace_id)
    current_group_config_registry.remove_workspace(workspace_id)
    remove_workspace_synchronization_state(workspace_id=workspace_id, registry=synchronization_registry)
