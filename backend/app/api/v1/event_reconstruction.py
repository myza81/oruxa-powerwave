"""Event Reconstruction API (DEC-123, DEC-124, DEC-128).

`GET .../records` lists every workspace record (one imported recording =
one record, DEC-128) with its V1 eligibility. `GET/PUT/DELETE
.../definition` reads, creates/replaces and clears the workspace's
reconstruction. `PUT .../definition/reference` changes the reference
record, and `PUT/DELETE .../definition/records/{record_id}/correction`
sets or resets one record's manual correction. Every response that
changes state returns the full reconstruction, recomputed against the
current records.

This router never touches waveform data, Waveform Time Groups or the
Synchronise Sources state -- see app.services.event_reconstruction_service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.event_reconstruction import (
    ReconstructionCorrectionRequest,
    ReconstructionDefinitionRequest,
    ReconstructionOut,
    ReconstructionRecordOut,
    ReconstructionReferenceRequest,
)
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import (
    clear_reconstruction,
    get_reconstruction,
    list_reconstruction_records,
    reset_member_correction,
    set_member_correction,
    set_reconstruction_definition,
    set_reconstruction_reference,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/event-reconstruction", tags=["event-reconstruction"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "record_not_eligible": status.HTTP_400_BAD_REQUEST,
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


def get_large_gap_warning_threshold_s(request: Request) -> float:
    """The effective threshold, from central configuration
    (`Settings.event_reconstruction_large_gap_warning_s`)."""
    return request.app.state.settings.event_reconstruction_large_gap_warning_s


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


@router.get("/records", response_model=list[ReconstructionRecordOut])
def get_records(
    workspace_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[ReconstructionRecordOut]:
    """Every workspace record, eligible or not, with its reason code when
    ineligible (`no_absolute_time_reference`, `time_of_day_not_supported`)."""
    workspace_id = _validate_workspace_id(workspace_id)
    views = list_reconstruction_records(workspace_id=workspace_id, registry=registry, source_registry=source_registry)
    return [ReconstructionRecordOut.from_view(v) for v in views]


@router.get("/definition", response_model=ReconstructionOut)
def get_definition(
    workspace_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    large_gap_threshold_s: float = Depends(get_large_gap_warning_threshold_s),
) -> ReconstructionOut:
    """`defined: false` when none exists -- never a 404 for a read."""
    workspace_id = _validate_workspace_id(workspace_id)
    view = get_reconstruction(
        workspace_id=workspace_id, registry=registry, source_registry=source_registry,
        large_gap_threshold_s=large_gap_threshold_s,
    )
    return ReconstructionOut.from_view(view)


@router.put("/definition", response_model=ReconstructionOut)
def put_definition(
    workspace_id: str,
    body: ReconstructionDefinitionRequest,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    large_gap_threshold_s: float = Depends(get_large_gap_warning_threshold_s),
) -> ReconstructionOut:
    """Create or replace. 400 `invalid_reconstruction_definition` (no
    record), `duplicate_reconstruction_member`, `record_not_eligible`,
    `reconstruction_reference_not_member`; 404 `source_not_found`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_reconstruction_definition(
            workspace_id=workspace_id, record_ids=body.record_ids, reference_record_id=body.reference_record_id,
            registry=registry, source_registry=source_registry, large_gap_threshold_s=large_gap_threshold_s,
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
    large_gap_threshold_s: float = Depends(get_large_gap_warning_threshold_s),
) -> ReconstructionOut:
    """404 `reconstruction_not_defined`/`reconstruction_member_not_found`;
    409 `reconstruction_member_stale`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_reconstruction_reference(
            workspace_id=workspace_id, record_id=body.record_id, registry=registry,
            source_registry=source_registry, large_gap_threshold_s=large_gap_threshold_s,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)


@router.put("/definition/records/{record_id}/correction", response_model=ReconstructionOut)
def put_record_correction(
    workspace_id: str,
    record_id: str,
    body: ReconstructionCorrectionRequest,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    large_gap_threshold_s: float = Depends(get_large_gap_warning_threshold_s),
) -> ReconstructionOut:
    """400 `invalid_reconstruction_correction`; 404
    `reconstruction_not_defined`/`reconstruction_member_not_found`; 409
    `reconstruction_member_stale`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_member_correction(
            workspace_id=workspace_id, record_id=record_id, correction_s=body.correction_s, registry=registry,
            source_registry=source_registry, large_gap_threshold_s=large_gap_threshold_s,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)


@router.delete("/definition/records/{record_id}/correction", response_model=ReconstructionOut)
def delete_record_correction(
    workspace_id: str,
    record_id: str,
    registry: EventReconstructionRegistry = Depends(get_event_reconstruction_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    large_gap_threshold_s: float = Depends(get_large_gap_warning_threshold_s),
) -> ReconstructionOut:
    """Correction back to 0 (recorded-timestamp placement); same errors
    as the PUT, without the validation one."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = reset_member_correction(
            workspace_id=workspace_id, record_id=record_id, registry=registry,
            source_registry=source_registry, large_gap_threshold_s=large_gap_threshold_s,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReconstructionOut.from_view(view)
