"""Analysis Guardrail Slice 1/2: thin, workspace-scoped REST exposure of
`app.services.engineering_context_service` and (Slice 2)
`app.services.analysis_input_resolution_service`. No new domain
semantics, no new validation: every endpoint below calls straight into
an existing, already-tested service function.

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

**Slice 2** adds one read-only endpoint: `GET .../engineering-contexts/
{id}/input-resolution`. Deliberately nested under one Engineering
Context (not a new top-level `/analysis/...` router) -- the resolution
result's entire input is "this context, this requirement," so this
mirrors `app.api.v1.measurement_groups`'s own precedent of nesting a
resource's derived views (`.../voltage-config`/`.../current-config`)
under its own id rather than inventing a parallel top-level route
family. That endpoint resolves WHICH channels satisfy an analysis
mode's required roles; it never calculates anything.

**Phasor Analysis Slice 1** adds a second, equally read-only endpoint,
nested the same way: `GET .../engineering-contexts/{id}/phasor`. This
is the first (and, in this slice, only) actual CALCULATION endpoint in
this codebase -- selected-time only, engineering units only, never
persisted. See `app.services.phasor_analysis_service`'s own docstring
for the full estimation/guardrail architecture; this router only
exposes it.
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
from app.domain.analysis_input_resolution import AnalysisInputResolution
from app.domain.analysis_requirements import get_requirement
from app.domain.phasor import PhasorAnalysisResult, PhasorDiagramResult
from app.schemas.analysis_input_resolution import AnalysisInputResolutionOut, RoleSpecOut
from app.schemas.phasor_analysis import (
    PhasorAnalysisResultOut,
    PhasorDiagramResultOut,
    PhasorDiagramRoleResultOut,
    PhasorRoleResultOut,
)
from app.schemas.source import ErrorOut
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
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
from app.services.phasor_analysis_service import compute_phasor_analysis, compute_phasor_diagram
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
    "unknown_analysis_requirement": status.HTTP_400_BAD_REQUEST,
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


def _resolution_to_out(result: AnalysisInputResolution) -> AnalysisInputResolutionOut:
    requirement = get_requirement(result.analysis_kind, result.mode)
    role_specs = (
        [
            RoleSpecOut(role_key=role.role_key, engineering_type=role.engineering_type, phase=role.phase, representation=role.representation)
            for role in requirement.required_roles
        ]
        if requirement is not None
        else []
    )
    return AnalysisInputResolutionOut(
        status=result.status, analysis_kind=result.analysis_kind, mode=result.mode,
        engineering_context_id=result.engineering_context_id, required_roles=result.required_roles,
        required_role_specs=role_specs,
        resolved_roles={key: ChannelRefOut.from_domain(ref) for key, ref in result.resolved_roles.items()},
        missing_roles=result.missing_roles, missing_role_reasons=result.missing_role_reasons,
        ambiguous_roles={
            key: [ChannelRefOut.from_domain(ref) for ref in refs] for key, refs in result.ambiguous_roles.items()
        },
        numerically_ready=result.numerically_ready, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/input-resolution", response_model=AnalysisInputResolutionOut)
def get_input_resolution(
    workspace_id: str,
    engineering_context_id: str,
    analysis_kind: str,
    mode: str,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> AnalysisInputResolutionOut:
    """Read-only. Given `analysis_kind`/`mode` (query parameters --
    identify one `app.domain.analysis_requirements.AnalysisRequirement`)
    and one Engineering Context, returns which channels Powerwave
    automatically resolves for each required role -- never a channel
    picker's worth of raw candidates, never a calculation. Always
    derived fresh from current context/channel state; nothing here is
    persisted or cached."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = resolve_analysis_inputs(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            analysis_kind=analysis_kind, mode=mode,
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _resolution_to_out(result)


def _phasor_result_to_out(result: PhasorAnalysisResult) -> PhasorAnalysisResultOut:
    return PhasorAnalysisResultOut(
        status=result.status, analysis_kind=result.analysis_kind, mode=result.mode,
        engineering_context_id=result.engineering_context_id, analysis_time=result.analysis_time,
        reference_frequency_hz=result.reference_frequency_hz, window_seconds=result.window_seconds,
        algorithm_version=result.algorithm_version,
        roles={
            role_key: PhasorRoleResultOut(
                channel_ref=ChannelRefOut.from_domain(role.channel_ref), magnitude_rms=role.magnitude_rms,
                unit=role.unit, angle_deg_absolute=role.angle_deg_absolute, angle_deg_relative=role.angle_deg_relative,
            )
            for role_key, role in result.roles.items()
        },
        warnings=result.warnings, role_reasons=result.role_reasons,
        reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/phasor", response_model=PhasorAnalysisResultOut)
def get_phasor_analysis(
    workspace_id: str,
    engineering_context_id: str,
    analysis_kind: str,
    mode: str,
    analysis_time: float,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> PhasorAnalysisResultOut:
    """Read-only, selected-time-only Phasor Analysis (Slice 1). Calls
    the input resolver first (unchanged) -- if it does not reach
    `resolved`, its own status/reason/message is returned verbatim, no
    estimation is attempted. `analysis_time` is elapsed seconds since
    the start of whichever resolved role's source grounds the FIRST
    required role (see `app.services.phasor_analysis_service`'s own
    docstring for the exact multi-source semantics).
    `reference_frequency_hz` is an optional explicit override; omitted,
    every resolved role's own source must declare the SAME nominal
    frequency or the result is `needs_configuration` /
    `reference_frequency_conflict`. Engineering units only -- no
    `unit_mode`/Per-Unit parameter in this slice. Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = compute_phasor_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            analysis_kind=analysis_kind, mode=mode, analysis_time=analysis_time,
            reference_frequency_hz_override=reference_frequency_hz,
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _phasor_result_to_out(result)


def _phasor_diagram_result_to_out(result: PhasorDiagramResult) -> PhasorDiagramResultOut:
    return PhasorDiagramResultOut(
        status=result.status, engineering_context_id=result.engineering_context_id,
        analysis_time=result.analysis_time, reference_frequency_hz=result.reference_frequency_hz,
        window_seconds=result.window_seconds, algorithm_version=result.algorithm_version,
        roles={
            role_key: PhasorDiagramRoleResultOut(
                status=role.status,
                channel_ref=ChannelRefOut.from_domain(role.channel_ref) if role.channel_ref is not None else None,
                magnitude_rms=role.magnitude_rms, unit=role.unit,
                angle_deg_absolute=role.angle_deg_absolute, angle_deg_relative=role.angle_deg_relative,
                reason_code=role.reason_code,
            )
            for role_key, role in result.roles.items()
        },
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/phasor-diagram", response_model=PhasorDiagramResultOut)
def get_phasor_diagram(
    workspace_id: str,
    engineering_context_id: str,
    analysis_time: float,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> PhasorDiagramResultOut:
    """Read-only, selected-time-only, bay-centric Phasor Diagram
    aggregation (Phasor UAT redesign; see
    docs/project-memory/PHASOR_ANALYSIS.md's own "Bay-centric Phasor
    Diagram" section). Resolves and estimates ALL SIX supported roles
    (Va/Vb/Vc/Ia/Ib/Ic) for one Engineering Context independently -- a
    partial bay (e.g. only Va+Ia) is a normal, useful result, never a
    whole-request failure. `status` is only ever `needs_configuration`
    when the roles present cannot be meaningfully drawn TOGETHER
    (conflicting declared nominal frequencies, or a proven timebase
    incompatibility) -- one role being individually missing/ambiguous/
    ineligible never blocks any other role's own result, see each
    role's own `status` for that. No `unit_mode`/Per-Unit parameter in
    this slice. Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = compute_phasor_diagram(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            analysis_time=analysis_time, reference_frequency_hz_override=reference_frequency_hz,
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _phasor_diagram_result_to_out(result)
