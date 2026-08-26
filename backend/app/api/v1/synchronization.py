"""Slice 1 waveform time-synchronization API.

Source-scoped, mirroring `app.api.v1.per_unit`'s own shape: `GET
.../synchronization/sources` lists every real source currently in the
workspace (offset or not), `PUT .../sources/{source_id}` sets one
source's own alignment offset, `DELETE .../sources/{source_id}` resets
it to `0`, and `DELETE .../sources` resets every source's offset in the
workspace at once ("Reset All"). See
app.services.synchronization_service's own module docstring for why this
router never touches waveform/cursor/digital-waveform data itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.source import ErrorOut
from app.schemas.synchronization import SourceAlignmentOut, SourceAlignmentUpdateRequest
from app.services.errors import ImportServiceError
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    get_source_alignment,
    list_source_alignments,
    reset_all_alignment_offsets,
    reset_source_alignment_offset,
    set_source_alignment_offset,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/synchronization", tags=["synchronization"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_alignment_offset": status.HTTP_400_BAD_REQUEST,
    "reference_source_alignment_not_allowed": status.HTTP_409_CONFLICT,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_synchronization_registry(request: Request) -> SynchronizationRegistry:
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


@router.get("/sources", response_model=list[SourceAlignmentOut])
def list_sources(
    workspace_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[SourceAlignmentOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    views = list_source_alignments(workspace_id=workspace_id, registry=registry, source_registry=source_registry)
    return [SourceAlignmentOut.from_view(v) for v in views]


@router.delete("/sources", status_code=status.HTTP_204_NO_CONTENT)
def reset_all_sources(
    workspace_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> None:
    """"Reset All" -- every source's own alignment offset in this
    workspace returns to `0`. Idempotent (a workspace with no
    synchronization state yet is a successful no-op)."""
    workspace_id = _validate_workspace_id(workspace_id)
    reset_all_alignment_offsets(workspace_id=workspace_id, registry=registry)


@router.get("/sources/{source_id}", response_model=SourceAlignmentOut)
def get_source(
    workspace_id: str,
    source_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceAlignmentOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = get_source_alignment(workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return SourceAlignmentOut.from_view(view)


@router.put("/sources/{source_id}", response_model=SourceAlignmentOut)
def put_source(
    workspace_id: str,
    source_id: str,
    body: SourceAlignmentUpdateRequest,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceAlignmentOut:
    """404 `source_not_found` if `source_id` does not exist in this
    workspace; 400 `invalid_alignment_offset` for a non-finite value; 409
    `reference_source_alignment_not_allowed` for a non-zero offset on the
    current reference source."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_source_alignment_offset(
            workspace_id=workspace_id, source_id=source_id, alignment_offset_s=body.alignment_offset_s,
            registry=registry, source_registry=source_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return SourceAlignmentOut.from_view(view)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_source(
    workspace_id: str,
    source_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> None:
    """Resets ONE source's own alignment offset to `0`. 404s if
    `source_id` does not exist in this workspace; idempotent for an
    already-unshifted source."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        reset_source_alignment_offset(workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
