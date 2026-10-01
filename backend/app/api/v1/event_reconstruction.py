"""Event Reconstruction API (DEC-123/DEC-124).

`GET .../time-groups` lists every current Time Group with its V1
eligibility. `GET/PUT/DELETE .../definition` reads, creates/replaces
(also re-confirms) and clears the workspace's reconstruction. `PUT
.../definition/reference` changes the reference member, and `PUT/DELETE
.../definition/members/{member_id}/correction` sets or resets one
member's manual correction. Every response that changes state returns
the full reconstruction, recomputed against the current Time Groups.

This router never touches waveform data, Time Group membership or the
Synchronise Sources state -- see app.services.event_reconstruction_service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.event_reconstruction import (
    ReconstructionCorrectionRequest,
    ReconstructionDefinitionRequest,
    ReconstructionOut,
    ReconstructionReferenceRequest,
    ReconstructionTimeGroupOut,
)
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import (
    clear_reconstruction,
    get_reconstruction,
    list_reconstruction_time_groups,
    reset_member_correction,
    set_member_correction,
    set_reconstruction_definition,
    set_reconstruction_reference,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/event-reconstruction", tags=["event-reconstruction"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "time_group_not_found": status.HTTP_404_NOT_FOUND,
    "time_group_not_eligible": status.HTTP_400_BAD_REQUEST,
    "invalid_reconstruction_definition": status.HTTP_400_BAD_REQUEST,
    "duplicate_reconstruction_member": status.HTTP_400_BAD_REQUEST,
    "reconstruction_reference_not_member": status.HTTP_400_BAD_REQUEST,
    "reconstruction_not_defined": status.HTTP_404_NOT_FOUND,
    "reconstruction_member_not_found": status.HTTP_404_NOT_FOUND,
    "reconstruction_member_stale": status.HTTP_409_CONFLICT,
    "invalid_reconstruction_correction": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_event_reconstruction_registry(request: Request) -> EventReconstructionRegistry:
    return request.app.state.event_reconstruction_registry


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_synchronization_registry(request: Request) -> SynchronizationRegistry:
    """Read-only use: effective within-group placement for group extents."""
    return request.app.state.synchronization_registry


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


@router.get("/time-groups", response_model=list[ReconstructionTimeGroupOut])
def get_time_groups(
    workspace_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> list[ReconstructionTimeGroupOut]:
    """Every current Time Group, eligible or not, with its reason code
    when ineligible (`no_absolute_time_reference`,
    `time_of_day_not_supported`)."""
    workspace_id = _validate_workspace_id(workspace_id)
    views = list_reconstruction_time_groups(
        workspace_id=workspace_id, registry=registry, source_registry=source_registry,
        synchronization_registry=synchronization_registry,
    )
    return [ReconstructionTimeGroupOut.from_view(v) for v in views]


@router.get("/definition", response_model=ReconstructionOut)
def get_definition(
    workspace_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> ReconstructionOut:
    """`defined: false` when none exists -- never a 404 for a read."""
    workspace_id = _validate_workspace_id(workspace_id)
    view = get_reconstruction(
        workspace_id=workspace_id, registry=registry, source_registry=source_registry,
        synchronization_registry=synchronization_registry,
    )
    return ReconstructionOut.from_view(view)


@router.put("/definition", response_model=ReconstructionOut)
def put_definition(
    workspace_id: str,
    body: ReconstructionDefinitionRequest,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> ReconstructionOut:
    """Create, replace or re-confirm. 400 `invalid_reconstruction_definition`
    (no group), `duplicate_reconstruction_member`, `time_group_not_eligible`,
    `reconstruction_reference_not_member`; 404 `time_group_not_found`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_reconstruction_definition(
            workspace_id=workspace_id, group_ids=body.group_ids, reference_group_id=body.reference_group_id,
            registry=registry, source_registry=source_registry, synchronization_registry=synchronization_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)


@router.delete("/definition", status_code=status.HTTP_204_NO_CONTENT)
def delete_definition(
    workspace_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
) -> None:
    """Clear the reconstruction. Idempotent."""
    workspace_id = _validate_workspace_id(workspace_id)
    clear_reconstruction(workspace_id=workspace_id, registry=registry)


@router.put("/definition/reference", response_model=ReconstructionOut)
def put_reference(
    workspace_id: str,
    body: ReconstructionReferenceRequest,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> ReconstructionOut:
    """404 `reconstruction_not_defined`/`reconstruction_member_not_found`;
    409 `reconstruction_member_stale`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_reconstruction_reference(
            workspace_id=workspace_id, member_id=body.member_id, registry=registry,
            source_registry=source_registry, synchronization_registry=synchronization_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)


@router.put("/definition/members/{member_id}/correction", response_model=ReconstructionOut)
def put_member_correction(
    workspace_id: str,
    member_id: str,
    body: ReconstructionCorrectionRequest,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> ReconstructionOut:
    """400 `invalid_reconstruction_correction`; 404
    `reconstruction_not_defined`/`reconstruction_member_not_found`; 409
    `reconstruction_member_stale`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_member_correction(
            workspace_id=workspace_id, member_id=member_id, correction_s=body.correction_s, registry=registry,
            source_registry=source_registry, synchronization_registry=synchronization_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)


@router.delete("/definition/members/{member_id}/correction", response_model=ReconstructionOut)
def delete_member_correction(
    workspace_id: str,
    member_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> ReconstructionOut:
    """Correction back to 0 (recorded-timestamp placement); same errors
    as the PUT, without the validation one."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = reset_member_correction(
            workspace_id=workspace_id, member_id=member_id, registry=registry,
            source_registry=source_registry, synchronization_registry=synchronization_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)
