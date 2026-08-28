"""Waveform time-synchronization API (Slice 1: per-source manual
alignment offsets; Slice 2: event origin `t0`, now Time-Group-scoped;
Timestamp-Based Initial Alignment and Time Groups: `GET
.../time-groups`).

Source-scoped, mirroring `app.api.v1.per_unit`'s own shape: `GET
.../synchronization/sources` lists every real source currently in the
workspace (offset or not; now also carries each source's own
`time_group_id`/`timestamp_placement_offset_s`/`manual_alignment_offset_s`
alongside the EFFECTIVE `alignment_offset_s`), `PUT .../sources/{source_id}`
sets one source's own MANUAL correction, `DELETE .../sources/{source_id}`
resets it to `0`, and `DELETE .../sources` resets every source's manual
correction in the workspace at once ("Reset All"). `GET/PUT/DELETE
.../t0` is Slice 2's own addition, now Time-Group-scoped -- each request
carries a `source_id` (query param for GET/DELETE, body field for PUT)
purely to resolve WHICH time group's own event origin is meant (see
app.services.synchronization_service's own module docstring for why).
`GET .../time-groups` is this feature's own new addition -- lists every
current Time Group (task section 9) in the workspace. See
app.services.synchronization_service's own module docstring for why
this router never touches waveform/cursor/digital-waveform data itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.event_detection import DetectEventOut, DetectEventRequest
from app.schemas.source import ErrorOut
from app.schemas.synchronization import SourceAlignmentOut, SourceAlignmentUpdateRequest, T0Out, T0UpdateRequest, TimeGroupOut
from app.services.errors import ImportServiceError
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    clear_t0,
    detect_event_candidate,
    get_source_alignment,
    get_t0,
    list_source_alignments,
    list_time_groups,
    reset_all_alignment_offsets,
    reset_source_alignment_offset,
    set_source_alignment_offset,
    set_t0,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/synchronization", tags=["synchronization"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_alignment_offset": status.HTTP_400_BAD_REQUEST,
    "reference_source_alignment_not_allowed": status.HTTP_409_CONFLICT,
    "invalid_t0": status.HTTP_400_BAD_REQUEST,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "invalid_sensitivity": status.HTTP_400_BAD_REQUEST,
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


@router.get("/t0", response_model=T0Out)
def get_workspace_t0(
    workspace_id: str,
    source_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> T0Out:
    """`t0_workspace_time: null` when no event origin has been selected
    yet for `source_id`'s own CURRENT time group -- never a 404 for
    "not yet selected" (Slice 2's own established convention, mirroring
    how an unconfigured source's alignment offset reads as `0` rather
    than 404ing). `source_id` (task section 24) resolves WHICH group's
    t0 is being read -- 404 `source_not_found` if it does not exist in
    this workspace."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = get_t0(workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return T0Out.from_view(view)


@router.put("/t0", response_model=T0Out)
def put_workspace_t0(
    workspace_id: str,
    body: T0UpdateRequest,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> T0Out:
    """Sets the event origin for WHICHEVER time group `body.source_id`
    currently belongs to (task section 24 -- t0 remains one value per
    coherent time domain, never per-source; `source_id` here only
    resolves which group is meant). 400 `invalid_t0` for a non-finite
    value; 404 `source_not_found` for an unknown `source_id`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_t0(
            workspace_id=workspace_id, source_id=body.source_id, t0_workspace_time=body.t0_workspace_time,
            registry=registry, source_registry=source_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return T0Out.from_view(view)


@router.delete("/t0", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace_t0(
    workspace_id: str,
    source_id: str,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> None:
    """"Clear t=0" (Slice 2 task section 13) -- removes ONLY the event
    origin for `source_id`'s own CURRENT time group; every OTHER time
    group's own t0, and every source's own manual alignment offset in
    ANY group, is untouched. Idempotent (a group with no event origin
    set is a successful no-op)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        clear_t0(workspace_id=workspace_id, source_id=source_id, registry=registry, source_registry=source_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/time-groups", response_model=list[TimeGroupOut])
def get_time_groups(
    workspace_id: str,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[TimeGroupOut]:
    """Every current Time Group in this workspace (task section 9) --
    "one waveform panel = one coherent time domain." Recomputed fresh
    from the current source set on every call (never cached/persisted),
    exactly like every other derived-fact endpoint in this API."""
    workspace_id = _validate_workspace_id(workspace_id)
    groups = list_time_groups(workspace_id=workspace_id, source_registry=source_registry)
    return [TimeGroupOut.from_group(g) for g in groups]


@router.post("/detect-event", response_model=DetectEventOut)
def detect_event(
    workspace_id: str,
    body: DetectEventRequest,
    registry: SynchronizationRegistry = Depends(get_synchronization_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> DetectEventOut:
    """Slice 3: assisted event-origin detection (task section 26).
    Advisory only -- this NEVER sets `t0` itself; a `found=True` result
    is only ever a suggestion the frontend previews on the waveform and
    the engineer separately accepts via the existing `PUT .../t0` above
    (task section 14: "do not create a second t0 implementation"). 404
    `source_not_found`/`channel_not_found`, 400 `channel_not_analog`/
    `invalid_sensitivity`."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = detect_event_candidate(
            workspace_id=workspace_id,
            source_id=body.source_id,
            channel_name=body.channel_name,
            sensitivity=body.sensitivity,
            search_start_time=body.search_start_time,
            search_end_time=body.search_end_time,
            source_registry=source_registry,
            synchronization_registry=registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return DetectEventOut.from_view(view)
