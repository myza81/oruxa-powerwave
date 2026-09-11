"""Analysis Guardrail Slice 1: thin, workspace-scoped REST exposure of
`app.services.engineering_context_service`. No new domain semantics, no
new validation: every mutating endpoint below calls straight into an
existing, already-tested service function.

Router prefix is workspace-scoped only (unlike
`app.api.v1.measurement_groups`'s own source-scoped shape) -- an
Engineering Context is not owned by any one source (it may span
several), so its identity is only ever meaningful within its own
`workspace_id`. The one source-scoped exception is the detection
trigger (`POST .../sources/{source_id}/engineering-contexts/suggest`),
since automatic detection is deliberately single-source-only (see
`app.domain.engineering_context_detection`'s own module docstring) --
the resulting contexts are still stored workspace-scoped like any other.

`POST .../suggest` is invoked ONLY explicitly, never automatically --
no upload trigger, no trigger on any other endpoint in this router,
mirroring `app.api.v1.measurement_groups`'s own established policy.

This slice deliberately exposes NO `/analysis/...` resolver endpoint --
context/phase metadata only, per the owner's own explicit scope
boundary for this slice.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.engineering_context import (
    EngineeringContextCreateRequest,
    EngineeringContextMemberIn,
    EngineeringContextMemberOut,
    EngineeringContextMemberPhaseUpdateRequest,
    EngineeringContextOut,
    EngineeringContextUpdateRequest,
    SuggestEngineeringContextsRequest,
)
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.engineering_context_service import (
    create_context,
    delete_context,
    generate_suggested_contexts_for_source,
    get_context,
    list_contexts_for_workspace,
    update_context_membership,
    update_context_metadata,
    update_member_phase,
)
from app.services.errors import ImportServiceError
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["engineering-contexts"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "engineering_context_not_found": status.HTTP_404_NOT_FOUND,
    "engineering_context_already_exists": status.HTTP_409_CONFLICT,
    "invalid_engineering_context_status": status.HTTP_400_BAD_REQUEST,
    "invalid_phase": status.HTTP_400_BAD_REQUEST,
    "invalid_phase_source": status.HTTP_400_BAD_REQUEST,
    "engineering_context_channel_not_found": status.HTTP_400_BAD_REQUEST,
    "channel_already_in_context": status.HTTP_409_CONFLICT,
    "duplicate_channel_reference_in_context": status.HTTP_400_BAD_REQUEST,
    "phase_assignment_locked": status.HTTP_409_CONFLICT,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_engineering_context_registry(request: Request) -> EngineeringContextRegistry:
    return request.app.state.engineering_context_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


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


def _members_from_in(members: list[EngineeringContextMemberIn]) -> list[EngineeringContextMember]:
    return [
        EngineeringContextMember(
            channel_ref=m.channel_ref.to_domain(),
            phase=m.phase,
            phase_source=m.phase_source,
            original_phase_label=m.original_phase_label,
        )
        for m in members
    ]


def _context_to_out(context: EngineeringContext) -> EngineeringContextOut:
    return EngineeringContextOut(
        id=context.id,
        workspace_id=context.workspace_id,
        display_name=context.display_name,
        members=[
            EngineeringContextMemberOut(
                channel_ref=_channel_ref_out(m.channel_ref),
                phase=m.phase,
                phase_source=m.phase_source,
                original_phase_label=m.original_phase_label,
            )
            for m in context.members
        ],
        status=context.status,
        created_at=context.created_at,
    )


def _channel_ref_out(ref: ChannelRef) -> ChannelRefOut:
    return ChannelRefOut.from_domain(ref)


@router.get("/engineering-contexts", response_model=list[EngineeringContextOut])
def list_engineering_contexts(
    workspace_id: str,
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
) -> list[EngineeringContextOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    return [_context_to_out(c) for c in list_contexts_for_workspace(workspace_id, registry=registry)]


@router.post("/engineering-contexts", response_model=EngineeringContextOut, status_code=status.HTTP_201_CREATED)
def create_engineering_context(
    workspace_id: str,
    body: EngineeringContextCreateRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> EngineeringContextOut:
    """Manual context creation -- the engineer-authored path for a bay
    the automatic detector did not (or could not, e.g. a genuinely
    multi-source bay) suggest on its own."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        context = create_context(
            workspace_id=workspace_id, display_name=body.display_name,
            members=_members_from_in(body.members), status=body.status,
            registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _context_to_out(context)


@router.post("/sources/{source_id}/engineering-contexts/suggest", response_model=list[EngineeringContextOut])
def suggest_engineering_contexts(
    workspace_id: str,
    source_id: str,
    body: SuggestEngineeringContextsRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> list[EngineeringContextOut]:
    """Explicit, user-triggered ONLY -- never invoked automatically.
    Single-source detection (see `app.domain.engineering_context_
    detection`'s own module docstring for why); the resulting contexts
    are still stored workspace-scoped and may later be manually extended
    to span other sources via `PATCH .../engineering-contexts/{id}`.
    Returns exactly the NEWLY created contexts; an empty list means
    nothing new was found to suggest, never an error."""
    del body
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        new_contexts = generate_suggested_contexts_for_source(
            workspace_id=workspace_id, source_id=source_id, registry=registry,
            source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return [_context_to_out(c) for c in new_contexts]


@router.get("/engineering-contexts/{engineering_context_id}", response_model=EngineeringContextOut)
def get_engineering_context(
    workspace_id: str,
    engineering_context_id: str,
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
) -> EngineeringContextOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        context = get_context(workspace_id, engineering_context_id, registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _context_to_out(context)


@router.patch("/engineering-contexts/{engineering_context_id}", response_model=EngineeringContextOut)
def update_engineering_context(
    workspace_id: str,
    engineering_context_id: str,
    body: EngineeringContextUpdateRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> EngineeringContextOut:
    """Partial update -- `display_name`/`status` via
    `update_context_metadata()`, `members` (full replace) via
    `update_context_membership()`. This is how a `suggested` context is
    promoted to `confirmed`, and the primary way an engineer corrects
    membership (adding a channel from a second source, per the owner's
    own multi-source-bay example, is just a normal membership PATCH)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        if body.display_name is not None or body.status is not None:
            update_context_metadata(
                workspace_id=workspace_id, engineering_context_id=engineering_context_id, registry=registry,
                display_name=body.display_name, status=body.status,
            )
        if body.members is not None:
            update_context_membership(
                workspace_id=workspace_id, engineering_context_id=engineering_context_id,
                members=_members_from_in(body.members),
                registry=registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
            )
        context = get_context(workspace_id, engineering_context_id, registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _context_to_out(context)


@router.patch("/engineering-contexts/{engineering_context_id}/member-phase", response_model=EngineeringContextOut)
def update_engineering_context_member_phase(
    workspace_id: str,
    engineering_context_id: str,
    body: EngineeringContextMemberPhaseUpdateRequest,
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
) -> EngineeringContextOut:
    """The dedicated manual phase-correction path -- corrects ONE
    member's own phase without resending the whole membership list.
    Always persisted as `phase_source="engineer_confirmed"` (see
    `update_member_phase()`'s own docstring)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        context = update_member_phase(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            channel_ref=body.channel_ref.to_domain(), phase=body.phase,
            original_phase_label=body.original_phase_label, registry=registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _context_to_out(context)


@router.delete("/engineering-contexts/{engineering_context_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_engineering_context(
    workspace_id: str,
    engineering_context_id: str,
    registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
) -> None:
    """Idempotent -- a context that does not exist at all is a
    successful no-op, matching `delete_context()`'s own contract."""
    workspace_id = _validate_workspace_id(workspace_id)
    delete_context(workspace_id, engineering_context_id, registry=registry)
