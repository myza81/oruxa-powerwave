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
from app.services.per_unit_registry import PerUnitRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


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
    """
    workspace_id = _validate_workspace_id(workspace_id)
    registry.remove_workspace(workspace_id)
    calc_registry.remove_workspace(workspace_id)
    per_unit_registry.remove_workspace(workspace_id)
