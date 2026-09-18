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

**Overcurrent Analysis v1** adds the second Analysis-menu analyzer,
following the identical nested/selected-time/never-persisted shape:
`GET .../engineering-contexts/{id}/overcurrent` (the calculation
endpoint), plus two workspace-scoped (not context-nested) metadata
endpoints that depend on nothing context-specific --
`GET .../overcurrent-characteristics` (the supported IEC IDMT curve
registry) and `GET .../overcurrent-curve` (curve geometry for one
characteristic/TMS pair, fetched only when those settings change, never
per Playback tick). See `app.services.overcurrent_analysis_service`'s
own docstring and docs/project-memory/OVERCURRENT_ANALYSIS.md for the
full architecture.
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
from app.domain.distance_protection import ZoneSettings
from app.domain.phasor import ManualPhasorRoleInput, PhasorAnalysisResult, PhasorDiagramResult
from app.schemas.analysis_input_resolution import AnalysisInputResolutionOut, RoleSpecOut
from app.schemas.distance_protection_analysis import (
    DistanceAnalysisResultOut,
    DistanceLocusOut,
    DistanceLocusPointOut,
    ManualDistanceResultOut,
    ZoneResultOut,
)
from app.schemas.impedance_analysis import (
    ImpedanceAnalysisResultOut,
    ImpedanceLocusOut,
    ImpedanceLocusPointOut,
    ManualImpedanceResultOut,
)
from app.schemas.overcurrent_analysis import (
    OvercurrentAnalysisResultOut,
    OvercurrentCharacteristicOut,
    OvercurrentCharacteristicsOut,
    OvercurrentCurveOut,
    OvercurrentCurvePointOut,
    OvercurrentManualAnalysisResultOut,
)
from app.schemas.phasor_analysis import (
    PhasorAnalysisResultOut,
    PhasorDiagramResultOut,
    PhasorDiagramRoleResultOut,
    PhasorManualDiagramResultOut,
    PhasorRoleResultOut,
)
from app.schemas.sequence_components_analysis import (
    SequenceAnalysisResultOut,
    SequenceFamilyResultOut,
    SequenceManualResultOut,
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
from app.services.distance_protection_analysis_service import compute_distance_analysis, compute_distance_locus, compute_distance_manual
from app.services.errors import ImportServiceError
from app.services.impedance_analysis_service import compute_impedance_analysis, compute_impedance_locus, compute_impedance_manual
from app.services.overcurrent_analysis_service import (
    CurveComputationError,
    compute_idmt_curve,
    compute_overcurrent_analysis,
    compute_overcurrent_manual_analysis,
    list_known_characteristics,
)
from app.services.phasor_analysis_service import compute_phasor_analysis, compute_phasor_diagram, compute_phasor_manual_diagram
from app.services.sequence_components_analysis_service import compute_sequence_analysis, compute_sequence_manual
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


def _phasor_manual_diagram_result_to_out(result) -> PhasorManualDiagramResultOut:
    return PhasorManualDiagramResultOut(
        status=result.status, algorithm_version=result.algorithm_version,
        roles={
            role_key: PhasorDiagramRoleResultOut(
                status=role.status,
                channel_ref=None,
                magnitude_rms=role.magnitude_rms, unit=role.unit,
                angle_deg_absolute=role.angle_deg_absolute, angle_deg_relative=role.angle_deg_relative,
                reason_code=role.reason_code,
            )
            for role_key, role in result.roles.items()
        },
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/phasor-manual", response_model=PhasorManualDiagramResultOut)
def get_phasor_manual_diagram(
    workspace_id: str,
    voltage_basis: str,
    current_basis: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    va_enabled: bool = False, va_magnitude: float | None = None, va_unit: str = "V", va_angle_deg: float = 0.0,
    vb_enabled: bool = False, vb_magnitude: float | None = None, vb_unit: str = "V", vb_angle_deg: float = 0.0,
    vc_enabled: bool = False, vc_magnitude: float | None = None, vc_unit: str = "V", vc_angle_deg: float = 0.0,
    ia_enabled: bool = False, ia_magnitude: float | None = None, ia_unit: str = "A", ia_angle_deg: float = 0.0,
    ib_enabled: bool = False, ib_magnitude: float | None = None, ib_unit: str = "A", ib_angle_deg: float = 0.0,
    ic_enabled: bool = False, ic_magnitude: float | None = None, ic_unit: str = "A", ic_angle_deg: float = 0.0,
) -> PhasorManualDiagramResultOut:
    """Manual Input / Calculator mode (Analysis Input Source = 'manual',
    see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- Phasor's own
    standalone engineering-calculator path, alongside the existing
    recording- and Playback-driven `.../phasor-diagram` endpoint above.
    Workspace-scoped only -- no Engineering Context, channel, waveform,
    or Playback state is involved at all; every one of the six roles
    (Va/Vb/Vc/Ia/Ib/Ic) is independently optional (`*_enabled=False` or
    a missing magnitude simply reports that role as `missing`, never
    blocking the other five). `voltage_basis`/`current_basis` are
    genuinely independent of each other (task's own hard requirement) --
    an invalid Voltage basis or VT/PT ratio only ever affects the three
    Voltage roles, never Current, and vice versa for CT. Never
    persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    role_inputs = {
        "Va": ManualPhasorRoleInput(enabled=va_enabled, magnitude=va_magnitude, unit=va_unit, angle_deg=va_angle_deg),
        "Vb": ManualPhasorRoleInput(enabled=vb_enabled, magnitude=vb_magnitude, unit=vb_unit, angle_deg=vb_angle_deg),
        "Vc": ManualPhasorRoleInput(enabled=vc_enabled, magnitude=vc_magnitude, unit=vc_unit, angle_deg=vc_angle_deg),
        "Ia": ManualPhasorRoleInput(enabled=ia_enabled, magnitude=ia_magnitude, unit=ia_unit, angle_deg=ia_angle_deg),
        "Ib": ManualPhasorRoleInput(enabled=ib_enabled, magnitude=ib_magnitude, unit=ib_unit, angle_deg=ib_angle_deg),
        "Ic": ManualPhasorRoleInput(enabled=ic_enabled, magnitude=ic_magnitude, unit=ic_unit, angle_deg=ic_angle_deg),
    }
    result = compute_phasor_manual_diagram(
        voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        role_inputs=role_inputs,
    )
    return _phasor_manual_diagram_result_to_out(result)


# ---------------------------------------------------------------------------
# Overcurrent Analysis v1 -- the second Analysis-menu consumer (Phasor
# remains the first). See app.services.overcurrent_analysis_service's own
# docstring for the full estimation/guardrail architecture and
# docs/project-memory/OVERCURRENT_ANALYSIS.md for the feature record; this
# router only exposes it, exactly mirroring the Phasor endpoints above.
# ---------------------------------------------------------------------------


@router.get("/overcurrent-characteristics", response_model=OvercurrentCharacteristicsOut)
def get_overcurrent_characteristics() -> OvercurrentCharacteristicsOut:
    """Static configuration metadata -- every IEC IDMT characteristic
    this slice supports, with its own defining constants. Not nested
    under one Engineering Context (unlike every other endpoint in this
    router) since it depends on nothing workspace/context-specific --
    the frontend fetches it once, never on every analysis_time or Playback-tick change."""
    characteristics = list_known_characteristics()
    return OvercurrentCharacteristicsOut(
        characteristics=[
            OvercurrentCharacteristicOut(
                id=c.id, family=c.family, display_name=c.display_name,
                k=c.constants.k, alpha=c.constants.alpha, c=c.constants.c, source=c.source,
            )
            for c in characteristics
        ]
    )


@router.get("/overcurrent-curve", response_model=OvercurrentCurveOut)
def get_overcurrent_curve(characteristic_id: str, tms: float) -> OvercurrentCurveOut:
    """The characteristic curve itself -- depends only on `characteristic_
    id`/`tms`, never `analysis_time` -- the frontend recomputes this ONLY
    when those settings change, never on every Playback tick (owner
    instruction: "avoid shipping thousands of redundant curve points on
    every Playback tick")."""
    try:
        points = compute_idmt_curve(characteristic_id, tms)
    except CurveComputationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return OvercurrentCurveOut(
        characteristic_id=characteristic_id, tms=tms,
        points=[OvercurrentCurvePointOut(multiple_of_pickup=m, operating_time_seconds=t) for m, t in points],
    )


def _overcurrent_manual_result_to_out(result) -> OvercurrentManualAnalysisResultOut:
    return OvercurrentManualAnalysisResultOut(
        status=result.status, characteristic_id=result.characteristic_id, tms=result.tms,
        pickup_current_secondary=result.pickup_current_secondary, input_basis=result.input_basis,
        ct_primary=result.ct_primary, ct_secondary=result.ct_secondary, algorithm_version=result.algorithm_version,
        input_current=result.input_current, input_current_unit=result.input_current_unit,
        relay_secondary_current=result.relay_secondary_current, multiple_of_pickup=result.multiple_of_pickup,
        expected_operating_time_seconds=result.expected_operating_time_seconds,
        reason_code=result.reason_code, message=result.message,
    )


@router.get("/overcurrent-manual", response_model=OvercurrentManualAnalysisResultOut)
def get_overcurrent_manual_analysis(
    workspace_id: str,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    input_current: float,
    input_current_unit: str,
    recording_basis: str,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
) -> OvercurrentManualAnalysisResultOut:
    """Manual Input / Calculator mode (Analysis Input Source = 'manual',
    see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- the SECOND
    Analysis Input Source Overcurrent v1 supports, alongside the existing
    recording- and Playback-driven `.../overcurrent` endpoint above. Workspace-
    scoped only (like `.../overcurrent-characteristics`/`.../overcurrent-
    curve`) -- no Engineering Context, channel, waveform, or Playback
    state is involved at all; this is a standalone hypothetical/test
    current value evaluated against the SAME relay settings.
    `recording_basis` here describes the MANUALLY ENTERED value's own
    basis (never inferred by the caller) -- reusing the identical query-
    parameter name/vocabulary `.../overcurrent` already uses for the same
    underlying concept, so a frontend client can share its own basis-
    handling code between the two endpoints. `recording_basis='primary'`
    additionally requires `ct_primary`/`ct_secondary` (both > 0), exactly
    like `.../overcurrent`. Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    result = compute_overcurrent_manual_analysis(
        characteristic_id=characteristic_id, tms=tms, pickup_current_secondary=pickup_current_secondary,
        input_current=input_current, input_current_unit=input_current_unit, input_basis=recording_basis,
        ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    return _overcurrent_manual_result_to_out(result)


def _overcurrent_result_to_out(result) -> OvercurrentAnalysisResultOut:
    return OvercurrentAnalysisResultOut(
        status=result.status, engineering_context_id=result.engineering_context_id, phase=result.phase,
        analysis_time=result.analysis_time, characteristic_id=result.characteristic_id, tms=result.tms,
        pickup_current_secondary=result.pickup_current_secondary, recording_basis=result.recording_basis,
        ct_primary=result.ct_primary, ct_secondary=result.ct_secondary,
        reference_frequency_hz=result.reference_frequency_hz, window_seconds=result.window_seconds,
        algorithm_version=result.algorithm_version,
        channel_ref=ChannelRefOut.from_domain(result.channel_ref) if result.channel_ref is not None else None,
        measured_rms_current=result.measured_rms_current, measured_rms_current_unit=result.measured_rms_current_unit,
        relay_secondary_current=result.relay_secondary_current, multiple_of_pickup=result.multiple_of_pickup,
        expected_operating_time_seconds=result.expected_operating_time_seconds,
        above_pickup_duration_seconds=result.above_pickup_duration_seconds,
        threshold_exceeded=result.threshold_exceeded,
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/overcurrent", response_model=OvercurrentAnalysisResultOut)
def get_overcurrent_analysis(
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    analysis_time: float,
    characteristic_id: str,
    tms: float,
    pickup_current_secondary: float,
    recording_basis: str,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OvercurrentAnalysisResultOut:
    """Read-only, selected-time-only Overcurrent Analysis (v1). Calls the
    input resolver first (unchanged) for the ONE current phase requested
    -- if it does not reach `resolved`, its own status/reason/message is
    returned verbatim, no estimation is attempted. `analysis_time` is
    elapsed seconds since the resolved role's own source start (identical
    convention to `.../phasor`). `pickup_current_secondary` is always
    relay-secondary amperes; `recording_basis="primary"` additionally
    requires `ct_primary`/`ct_secondary` (both > 0) to convert the
    recorded current to a relay-equivalent secondary value.
    `reference_frequency_hz` is an optional explicit override; omitted,
    uses the resolved role's own source-declared nominal frequency.
    `expected_operating_time_seconds` is `None` whenever the current is at
    or below pickup -- never a fabricated value. `threshold_exceeded` is
    a qualified characteristic-analysis observation only -- see
    `app.domain.overcurrent`'s own module footer for the explicit
    non-emulation boundary this must never be presented as crossing.
    Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = compute_overcurrent_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            phase=phase, analysis_time=analysis_time, characteristic_id=characteristic_id, tms=tms,
            pickup_current_secondary=pickup_current_secondary, recording_basis=recording_basis,
            ct_primary=ct_primary, ct_secondary=ct_secondary, reference_frequency_hz_override=reference_frequency_hz,
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _overcurrent_result_to_out(result)


# ---------------------------------------------------------------------------
# Impedance Locus v1 -- the THIRD Analysis-menu analyzer (Phasor,
# Overcurrent, then Impedance Locus). See `app.services.impedance_
# analysis_service`'s own docstring and docs/project-memory/
# IMPEDANCE_LOCUS_ANALYSIS.md for the full architecture; this router only
# exposes it, mirroring the Phasor/Overcurrent endpoints above exactly.
# ---------------------------------------------------------------------------


def _impedance_result_to_out(result) -> ImpedanceAnalysisResultOut:
    return ImpedanceAnalysisResultOut(
        status=result.status, engineering_context_id=result.engineering_context_id, phase=result.phase,
        analysis_time=result.analysis_time, recording_basis=result.recording_basis, impedance_basis=result.impedance_basis,
        vt_primary=result.vt_primary, vt_secondary=result.vt_secondary, ct_primary=result.ct_primary, ct_secondary=result.ct_secondary,
        reference_frequency_hz=result.reference_frequency_hz, window_seconds=result.window_seconds,
        algorithm_version=result.algorithm_version,
        voltage_channel_ref=ChannelRefOut.from_domain(result.voltage_channel_ref) if result.voltage_channel_ref is not None else None,
        voltage_magnitude_rms=result.voltage_magnitude_rms, voltage_unit=result.voltage_unit,
        current_channel_ref=ChannelRefOut.from_domain(result.current_channel_ref) if result.current_channel_ref is not None else None,
        current_magnitude_rms=result.current_magnitude_rms, current_unit=result.current_unit,
        resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
        magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg,
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/impedance", response_model=ImpedanceAnalysisResultOut)
def get_impedance_analysis(
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    analysis_time: float,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> ImpedanceAnalysisResultOut:
    """Read-only, selected-time-only Impedance Locus (v1) for ONE phase
    (`Za`/`Zb`/`Zc`). Reuses the existing, unchanged `compute_phasor_
    diagram()` to resolve Voltage/Current -- never a second phasor
    estimator. `Z = V/I` via direct phasor division (`R = |Z|cos(theta)`,
    `X = |Z|sin(theta)`), never an RMS-scalar approximation.
    `recording_basis` is the basis the resolved channels' own values
    already represent; `impedance_basis` is the INDEPENDENT desired
    output basis -- `vt_primary`/`vt_secondary`/`ct_primary`/
    `ct_secondary` are required only when the two differ. Reports
    `needs_configuration`/`current_too_small` (never an unbounded `|Z|`)
    whenever the resolved current is below the numerical-validity floor.
    This is measurement/visualization only -- NOT Distance Protection
    (no zones/mho/quadrilateral/fault-loop logic exists here). Never
    persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = compute_impedance_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, phase=phase, analysis_time=analysis_time,
            reference_frequency_hz_override=reference_frequency_hz,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _impedance_result_to_out(result)


@router.get("/engineering-contexts/{engineering_context_id}/impedance-locus", response_model=ImpedanceLocusOut)
def get_impedance_locus(
    workspace_id: str,
    engineering_context_id: str,
    phase: str,
    start_time: float,
    end_time: float,
    point_count: int,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> ImpedanceLocusOut:
    """The static impedance locus/trajectory over `[start_time, end_time]`
    (task's own section 18-19) -- `point_count` evenly-sampled points
    (clamped to `impedance_analysis_service.MAX_LOCUS_POINTS`), each an
    independent selected-time Impedance calculation. Deterministic and
    Playback-speed-independent: the frontend fetches this ONLY on a
    context/phase/settings/time-range change, never on every Playback
    tick (mirrors `.../overcurrent-curve`'s own caching precedent). A
    point outside the recording's own valid window is still returned,
    with whatever `status`/`reason_code` it naturally produces -- the
    caller renders only `computed` points as the path."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        points = compute_impedance_locus(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, phase=phase,
            start_time=start_time, end_time=end_time, point_count=point_count,
            reference_frequency_hz_override=reference_frequency_hz,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ImpedanceLocusOut(
        engineering_context_id=engineering_context_id, phase=phase,
        points=[
            ImpedanceLocusPointOut(
                analysis_time=p.analysis_time, status=p.status, resistance_ohm=p.resistance_ohm, reactance_ohm=p.reactance_ohm,
                magnitude_ohm=p.magnitude_ohm, angle_deg=p.angle_deg, reason_code=p.reason_code,
            )
            for p in points
        ],
    )


def _impedance_manual_result_to_out(result) -> ManualImpedanceResultOut:
    return ManualImpedanceResultOut(
        status=result.status, phase_label=result.phase_label, impedance_basis=result.impedance_basis,
        algorithm_version=result.algorithm_version,
        voltage_magnitude_secondary=result.voltage_magnitude_secondary, current_magnitude_secondary=result.current_magnitude_secondary,
        resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
        magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg,
        reason_code=result.reason_code, message=result.message,
    )


@router.get("/impedance-manual", response_model=ManualImpedanceResultOut)
def get_impedance_manual(
    workspace_id: str,
    phase_label: str,
    voltage_basis: str,
    current_basis: str,
    impedance_basis: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    voltage_enabled: bool = False, voltage_magnitude: float | None = None, voltage_unit: str = "V", voltage_angle_deg: float = 0.0,
    current_enabled: bool = False, current_magnitude: float | None = None, current_unit: str = "A", current_angle_deg: float = 0.0,
) -> ManualImpedanceResultOut:
    """Manual Input / Calculator mode (Analysis Input Source = 'manual',
    see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- Impedance's own
    standalone engineering-calculator path. Workspace-scoped only -- no
    Engineering Context, channel, waveform, or Playback state is involved
    at all. `voltage_basis`/`current_basis` are genuinely independent
    INPUT bases (reusing the identical Manual Phasor normalization via
    `convert_manual_magnitude_to_secondary()`); `impedance_basis` is a
    THIRD, independent OUTPUT basis for the calculated impedance (task's
    own section 11 -- e.g. Voltage entered Primary, Current entered
    Secondary, Impedance requested Primary is a valid combination). Never
    persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    voltage_input = ManualPhasorRoleInput(enabled=voltage_enabled, magnitude=voltage_magnitude, unit=voltage_unit, angle_deg=voltage_angle_deg)
    current_input = ManualPhasorRoleInput(enabled=current_enabled, magnitude=current_magnitude, unit=current_unit, angle_deg=current_angle_deg)
    result = compute_impedance_manual(
        phase_label=phase_label, voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary, impedance_basis=impedance_basis,
        voltage_input=voltage_input, current_input=current_input,
    )
    return _impedance_manual_result_to_out(result)


# ---------------------------------------------------------------------------
# Sequence Components v1 -- the FOURTH Analysis-menu analyzer (Phasor,
# Overcurrent, Impedance Locus, then Sequence Components). See
# `app.services.sequence_components_analysis_service`'s own docstring and
# docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md for the full
# architecture; this router only exposes it, mirroring the Impedance Locus
# endpoints above exactly.
# ---------------------------------------------------------------------------


def _sequence_family_result_to_out(result) -> SequenceFamilyResultOut:
    return SequenceFamilyResultOut(
        status=result.status,
        zero_sequence_magnitude=result.zero_sequence_magnitude, zero_sequence_angle_deg=result.zero_sequence_angle_deg,
        positive_sequence_magnitude=result.positive_sequence_magnitude, positive_sequence_angle_deg=result.positive_sequence_angle_deg,
        negative_sequence_magnitude=result.negative_sequence_magnitude, negative_sequence_angle_deg=result.negative_sequence_angle_deg,
        negative_sequence_ratio_percent=result.negative_sequence_ratio_percent, zero_sequence_ratio_percent=result.zero_sequence_ratio_percent,
        unit=result.unit,
        phase_a_channel_ref=ChannelRefOut.from_domain(result.phase_a_channel_ref) if result.phase_a_channel_ref is not None else None,
        phase_b_channel_ref=ChannelRefOut.from_domain(result.phase_b_channel_ref) if result.phase_b_channel_ref is not None else None,
        phase_c_channel_ref=ChannelRefOut.from_domain(result.phase_c_channel_ref) if result.phase_c_channel_ref is not None else None,
        reason_code=result.reason_code, message=result.message,
    )


def _sequence_result_to_out(result) -> SequenceAnalysisResultOut:
    return SequenceAnalysisResultOut(
        status=result.status, engineering_context_id=result.engineering_context_id, analysis_time=result.analysis_time,
        reference_frequency_hz=result.reference_frequency_hz, window_seconds=result.window_seconds,
        algorithm_version=result.algorithm_version,
        voltage_sequences=_sequence_family_result_to_out(result.voltage_sequences),
        current_sequences=_sequence_family_result_to_out(result.current_sequences),
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/sequence-components", response_model=SequenceAnalysisResultOut)
def get_sequence_components_analysis(
    workspace_id: str,
    engineering_context_id: str,
    analysis_time: float,
    reference_frequency_hz: float | None = None,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> SequenceAnalysisResultOut:
    """Read-only, selected-time-only positive/negative/zero-sequence
    Voltage and Current, for one Engineering Context. Reuses the
    existing, unchanged `compute_phasor_diagram()` to resolve Va/Vb/Vc
    and Ia/Ib/Ic -- never a second phasor estimator. Voltage and Current
    are evaluated fully independently, each requiring its own complete
    three-phase set (`needs_configuration`/`missing`/`ambiguous`/
    `not_eligible` otherwise, per that family alone -- one family's own
    incompleteness never blocks the other). Calculation and
    visualization only -- no unbalance limits, negative-sequence relay
    interpretation, or fault classification exist here. Never
    persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        result = compute_sequence_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reference_frequency_hz_override=reference_frequency_hz,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _sequence_result_to_out(result)


@router.get("/sequence-components-manual", response_model=SequenceManualResultOut)
def get_sequence_components_manual(
    workspace_id: str,
    voltage_basis: str,
    current_basis: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    va_enabled: bool = False, va_magnitude: float | None = None, va_unit: str = "V", va_angle_deg: float = 0.0,
    vb_enabled: bool = False, vb_magnitude: float | None = None, vb_unit: str = "V", vb_angle_deg: float = 0.0,
    vc_enabled: bool = False, vc_magnitude: float | None = None, vc_unit: str = "V", vc_angle_deg: float = 0.0,
    ia_enabled: bool = False, ia_magnitude: float | None = None, ia_unit: str = "A", ia_angle_deg: float = 0.0,
    ib_enabled: bool = False, ib_magnitude: float | None = None, ib_unit: str = "A", ib_angle_deg: float = 0.0,
    ic_enabled: bool = False, ic_magnitude: float | None = None, ic_unit: str = "A", ic_angle_deg: float = 0.0,
) -> SequenceManualResultOut:
    """Manual Input / Calculator mode (Analysis Input Source = 'manual',
    see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- Sequence
    Components' own standalone engineering-calculator path. Workspace-
    scoped only -- no Engineering Context, channel, waveform, or Playback
    state is involved at all. Reuses the identical six-role
    (Va/Vb/Vc/Ia/Ib/Ic), two-independent-basis (`voltage_basis`/
    `current_basis`, each with its own VT/CT ratio) Manual Phasor
    normalization -- never a duplicated conversion formula. Each family
    still requires all three of its own phases to be entered and valid
    before a sequence result is computed; an incomplete family reports
    `missing`/`needs_configuration` without blocking the other family.
    Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    role_inputs = {
        "Va": ManualPhasorRoleInput(enabled=va_enabled, magnitude=va_magnitude, unit=va_unit, angle_deg=va_angle_deg),
        "Vb": ManualPhasorRoleInput(enabled=vb_enabled, magnitude=vb_magnitude, unit=vb_unit, angle_deg=vb_angle_deg),
        "Vc": ManualPhasorRoleInput(enabled=vc_enabled, magnitude=vc_magnitude, unit=vc_unit, angle_deg=vc_angle_deg),
        "Ia": ManualPhasorRoleInput(enabled=ia_enabled, magnitude=ia_magnitude, unit=ia_unit, angle_deg=ia_angle_deg),
        "Ib": ManualPhasorRoleInput(enabled=ib_enabled, magnitude=ib_magnitude, unit=ib_unit, angle_deg=ib_angle_deg),
        "Ic": ManualPhasorRoleInput(enabled=ic_enabled, magnitude=ic_magnitude, unit=ic_unit, angle_deg=ic_angle_deg),
    }
    result = compute_sequence_manual(
        voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        role_inputs=role_inputs,
    )
    return SequenceManualResultOut(
        status=result.status, algorithm_version=result.algorithm_version,
        voltage_sequences=_sequence_family_result_to_out(result.voltage_sequences),
        current_sequences=_sequence_family_result_to_out(result.current_sequences),
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


# ---------------------------------------------------------------------------
# Distance Protection v1 -- the FIFTH Analysis-menu analyzer (Phasor,
# Overcurrent, Impedance Locus, Sequence Components, then Distance
# Protection). See `app.services.distance_protection_analysis_service`'s
# own docstring and docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md
# for the full architecture; this router only exposes it, mirroring the
# Impedance Locus endpoints above exactly (loop-impedance current point,
# a static locus/trajectory, and a standalone Manual path), extended with
# the three independent zone results Impedance Locus itself never has.
#
# `Operated`/`Not Operated` (`ZoneResultOut.state`) is PURE geometric
# element state -- it never means a relay tripped, a breaker opened, or
# full relay logic completed. `delay_s` is configuration information
# only -- v1 never accumulates it, never declares it elapsed, never
# asserts a trip from it.
# ---------------------------------------------------------------------------


def _zone_settings(
    enabled: bool, reach_ohm: float | None, reactive_reach_ohm: float | None,
    resistive_reach_forward_ohm: float | None, resistive_reach_reverse_ohm: float | None,
    characteristic_angle_deg: float, delay_s: float,
) -> ZoneSettings:
    return ZoneSettings(
        enabled=enabled, reach_ohm=reach_ohm, reactive_reach_ohm=reactive_reach_ohm,
        resistive_reach_forward_ohm=resistive_reach_forward_ohm, resistive_reach_reverse_ohm=resistive_reach_reverse_ohm,
        characteristic_angle_deg=characteristic_angle_deg, delay_s=delay_s,
    )


def _zone_result_to_out(result) -> ZoneResultOut:
    return ZoneResultOut(zone_key=result.zone_key, enabled=result.enabled, state=result.state, delay_s=result.delay_s)


def _distance_result_to_out(result) -> DistanceAnalysisResultOut:
    return DistanceAnalysisResultOut(
        status=result.status, engineering_context_id=result.engineering_context_id, loop=result.loop,
        analysis_time=result.analysis_time, recording_basis=result.recording_basis, impedance_basis=result.impedance_basis,
        vt_primary=result.vt_primary, vt_secondary=result.vt_secondary, ct_primary=result.ct_primary, ct_secondary=result.ct_secondary,
        reference_frequency_hz=result.reference_frequency_hz, window_seconds=result.window_seconds,
        algorithm_version=result.algorithm_version,
        v1_channel_ref=ChannelRefOut.from_domain(result.v1_channel_ref) if result.v1_channel_ref is not None else None,
        v2_channel_ref=ChannelRefOut.from_domain(result.v2_channel_ref) if result.v2_channel_ref is not None else None,
        i1_channel_ref=ChannelRefOut.from_domain(result.i1_channel_ref) if result.i1_channel_ref is not None else None,
        i2_channel_ref=ChannelRefOut.from_domain(result.i2_channel_ref) if result.i2_channel_ref is not None else None,
        voltage_unit=result.voltage_unit, current_unit=result.current_unit,
        resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
        magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg,
        characteristic=result.characteristic,
        zone1=_zone_result_to_out(result.zone1) if result.zone1 is not None else None,
        zone2=_zone_result_to_out(result.zone2) if result.zone2 is not None else None,
        zone3=_zone_result_to_out(result.zone3) if result.zone3 is not None else None,
        warnings=result.warnings, reason_code=result.reason_code, message=result.message,
    )


@router.get("/engineering-contexts/{engineering_context_id}/distance-protection", response_model=DistanceAnalysisResultOut)
def get_distance_protection_analysis(
    workspace_id: str,
    engineering_context_id: str,
    loop: str,
    analysis_time: float,
    recording_basis: str,
    impedance_basis: str,
    characteristic: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz: float | None = None,
    zone1_enabled: bool = False, zone1_reach_ohm: float | None = None, zone1_reactive_reach_ohm: float | None = None,
    zone1_resistive_reach_forward_ohm: float | None = None, zone1_resistive_reach_reverse_ohm: float | None = None,
    zone1_characteristic_angle_deg: float = 90.0, zone1_delay_s: float = 0.0,
    zone2_enabled: bool = False, zone2_reach_ohm: float | None = None, zone2_reactive_reach_ohm: float | None = None,
    zone2_resistive_reach_forward_ohm: float | None = None, zone2_resistive_reach_reverse_ohm: float | None = None,
    zone2_characteristic_angle_deg: float = 90.0, zone2_delay_s: float = 0.0,
    zone3_enabled: bool = False, zone3_reach_ohm: float | None = None, zone3_reactive_reach_ohm: float | None = None,
    zone3_resistive_reach_forward_ohm: float | None = None, zone3_resistive_reach_reverse_ohm: float | None = None,
    zone3_characteristic_angle_deg: float = 90.0, zone3_delay_s: float = 0.0,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> DistanceAnalysisResultOut:
    """Read-only, selected-time-only Distance Protection (v1) for ONE
    fault loop (`AB`/`BC`/`CA`). Reuses the existing, unchanged
    `compute_phasor_diagram()` to resolve the loop's two Voltage and two
    Current roles -- never a second phasor estimator. Fault-loop
    impedance uses full complex phasor subtraction (`Zab=(Va-Vb)/(Ia-Ib)`
    etc.), never a phase-impedance or scalar-RMS approximation. Zones 1-3
    are evaluated fully independently -- more than one MAY legitimately
    report `operated` simultaneously. `Operated`/`Not Operated` is PURE
    geometric element state -- it never means a relay tripped, a breaker
    opened, or full relay logic completed; `delay_s` is configuration
    information only, never accumulated or used to assert a trip. This
    is a SEPARATE analyzer from Impedance Locus -- it never mutates or
    depends on any Impedance Locus state. Never persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    zone1 = _zone_settings(zone1_enabled, zone1_reach_ohm, zone1_reactive_reach_ohm, zone1_resistive_reach_forward_ohm, zone1_resistive_reach_reverse_ohm, zone1_characteristic_angle_deg, zone1_delay_s)
    zone2 = _zone_settings(zone2_enabled, zone2_reach_ohm, zone2_reactive_reach_ohm, zone2_resistive_reach_forward_ohm, zone2_resistive_reach_reverse_ohm, zone2_characteristic_angle_deg, zone2_delay_s)
    zone3 = _zone_settings(zone3_enabled, zone3_reach_ohm, zone3_reactive_reach_ohm, zone3_resistive_reach_forward_ohm, zone3_resistive_reach_reverse_ohm, zone3_characteristic_angle_deg, zone3_delay_s)
    try:
        result = compute_distance_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            reference_frequency_hz_override=reference_frequency_hz,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zone1=zone1, zone2=zone2, zone3=zone3,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return _distance_result_to_out(result)


@router.get("/engineering-contexts/{engineering_context_id}/distance-protection-locus", response_model=DistanceLocusOut)
def get_distance_protection_locus(
    workspace_id: str,
    engineering_context_id: str,
    loop: str,
    start_time: float,
    end_time: float,
    point_count: int,
    recording_basis: str,
    impedance_basis: str,
    characteristic: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    reference_frequency_hz: float | None = None,
    zone1_enabled: bool = False, zone1_reach_ohm: float | None = None, zone1_reactive_reach_ohm: float | None = None,
    zone1_resistive_reach_forward_ohm: float | None = None, zone1_resistive_reach_reverse_ohm: float | None = None,
    zone1_characteristic_angle_deg: float = 90.0, zone1_delay_s: float = 0.0,
    zone2_enabled: bool = False, zone2_reach_ohm: float | None = None, zone2_reactive_reach_ohm: float | None = None,
    zone2_resistive_reach_forward_ohm: float | None = None, zone2_resistive_reach_reverse_ohm: float | None = None,
    zone2_characteristic_angle_deg: float = 90.0, zone2_delay_s: float = 0.0,
    zone3_enabled: bool = False, zone3_reach_ohm: float | None = None, zone3_reactive_reach_ohm: float | None = None,
    zone3_resistive_reach_forward_ohm: float | None = None, zone3_resistive_reach_reverse_ohm: float | None = None,
    zone3_characteristic_angle_deg: float = 90.0, zone3_delay_s: float = 0.0,
    context_registry: EngineeringContextRegistry = Depends(get_engineering_context_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> DistanceLocusOut:
    """The static loop-impedance locus/trajectory over `[start_time,
    end_time]` -- `point_count` evenly-sampled points (clamped to
    `distance_protection_analysis_service.MAX_LOCUS_POINTS`), each an
    independent selected-time Distance Protection calculation.
    Deterministic and Playback-speed-independent: the frontend fetches
    this ONLY on a context/loop/settings/time-range change, never on
    every Playback tick (mirrors `.../impedance-locus`'s own caching
    precedent exactly). Locus points intentionally carry NO zone state
    -- only the current Playback-driven point (from `.../distance-
    protection`) drives Operated/Not-Operated. A point outside the
    recording's own valid window is still returned, with whatever
    `status`/`reason_code` it naturally produces -- the caller renders
    only `computed` points as the visible trail."""
    workspace_id = _validate_workspace_id(workspace_id)
    zone1 = _zone_settings(zone1_enabled, zone1_reach_ohm, zone1_reactive_reach_ohm, zone1_resistive_reach_forward_ohm, zone1_resistive_reach_reverse_ohm, zone1_characteristic_angle_deg, zone1_delay_s)
    zone2 = _zone_settings(zone2_enabled, zone2_reach_ohm, zone2_reactive_reach_ohm, zone2_resistive_reach_forward_ohm, zone2_resistive_reach_reverse_ohm, zone2_characteristic_angle_deg, zone2_delay_s)
    zone3 = _zone_settings(zone3_enabled, zone3_reach_ohm, zone3_reactive_reach_ohm, zone3_resistive_reach_forward_ohm, zone3_resistive_reach_reverse_ohm, zone3_characteristic_angle_deg, zone3_delay_s)
    try:
        points = compute_distance_locus(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, loop=loop,
            start_time=start_time, end_time=end_time, point_count=point_count,
            reference_frequency_hz_override=reference_frequency_hz,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zone1=zone1, zone2=zone2, zone3=zone3,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return DistanceLocusOut(
        engineering_context_id=engineering_context_id, loop=loop,
        points=[
            DistanceLocusPointOut(
                analysis_time=p.analysis_time, status=p.status, resistance_ohm=p.resistance_ohm, reactance_ohm=p.reactance_ohm,
                magnitude_ohm=p.magnitude_ohm, angle_deg=p.angle_deg, reason_code=p.reason_code,
            )
            for p in points
        ],
    )


def _distance_manual_result_to_out(result) -> ManualDistanceResultOut:
    return ManualDistanceResultOut(
        status=result.status, loop_label=result.loop_label, impedance_basis=result.impedance_basis,
        algorithm_version=result.algorithm_version,
        v1_magnitude_secondary=result.v1_magnitude_secondary, v2_magnitude_secondary=result.v2_magnitude_secondary,
        i1_magnitude_secondary=result.i1_magnitude_secondary, i2_magnitude_secondary=result.i2_magnitude_secondary,
        resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
        magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg,
        characteristic=result.characteristic,
        zone1=_zone_result_to_out(result.zone1) if result.zone1 is not None else None,
        zone2=_zone_result_to_out(result.zone2) if result.zone2 is not None else None,
        zone3=_zone_result_to_out(result.zone3) if result.zone3 is not None else None,
        reason_code=result.reason_code, message=result.message,
    )


@router.get("/distance-protection-manual", response_model=ManualDistanceResultOut)
def get_distance_protection_manual(
    workspace_id: str,
    loop_label: str,
    voltage_basis: str,
    current_basis: str,
    impedance_basis: str,
    characteristic: str,
    vt_primary: float | None = None,
    vt_secondary: float | None = None,
    ct_primary: float | None = None,
    ct_secondary: float | None = None,
    v1_enabled: bool = False, v1_magnitude: float | None = None, v1_unit: str = "V", v1_angle_deg: float = 0.0,
    v2_enabled: bool = False, v2_magnitude: float | None = None, v2_unit: str = "V", v2_angle_deg: float = 0.0,
    i1_enabled: bool = False, i1_magnitude: float | None = None, i1_unit: str = "A", i1_angle_deg: float = 0.0,
    i2_enabled: bool = False, i2_magnitude: float | None = None, i2_unit: str = "A", i2_angle_deg: float = 0.0,
    zone1_enabled: bool = False, zone1_reach_ohm: float | None = None, zone1_reactive_reach_ohm: float | None = None,
    zone1_resistive_reach_forward_ohm: float | None = None, zone1_resistive_reach_reverse_ohm: float | None = None,
    zone1_characteristic_angle_deg: float = 90.0, zone1_delay_s: float = 0.0,
    zone2_enabled: bool = False, zone2_reach_ohm: float | None = None, zone2_reactive_reach_ohm: float | None = None,
    zone2_resistive_reach_forward_ohm: float | None = None, zone2_resistive_reach_reverse_ohm: float | None = None,
    zone2_characteristic_angle_deg: float = 90.0, zone2_delay_s: float = 0.0,
    zone3_enabled: bool = False, zone3_reach_ohm: float | None = None, zone3_reactive_reach_ohm: float | None = None,
    zone3_resistive_reach_forward_ohm: float | None = None, zone3_resistive_reach_reverse_ohm: float | None = None,
    zone3_characteristic_angle_deg: float = 90.0, zone3_delay_s: float = 0.0,
) -> ManualDistanceResultOut:
    """Manual Input / Calculator mode (Analysis Input Source = 'manual',
    see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) -- Distance
    Protection's own standalone engineering-calculator path.
    Workspace-scoped only -- no Engineering Context, channel, waveform,
    or Playback state is involved at all. Reuses the identical Manual
    Phasor normalization (`convert_manual_magnitude_to_secondary()`) for
    each of the loop's two Voltage and two Current legs -- never a
    duplicated conversion formula. `loop_label` (`AB`/`BC`/`CA`) is
    carried through purely for display; only the two relevant phase
    legs need be entered (e.g. `AB` never requires phase C). Never
    persisted."""
    workspace_id = _validate_workspace_id(workspace_id)
    v1_input = ManualPhasorRoleInput(enabled=v1_enabled, magnitude=v1_magnitude, unit=v1_unit, angle_deg=v1_angle_deg)
    v2_input = ManualPhasorRoleInput(enabled=v2_enabled, magnitude=v2_magnitude, unit=v2_unit, angle_deg=v2_angle_deg)
    i1_input = ManualPhasorRoleInput(enabled=i1_enabled, magnitude=i1_magnitude, unit=i1_unit, angle_deg=i1_angle_deg)
    i2_input = ManualPhasorRoleInput(enabled=i2_enabled, magnitude=i2_magnitude, unit=i2_unit, angle_deg=i2_angle_deg)
    zone1 = _zone_settings(zone1_enabled, zone1_reach_ohm, zone1_reactive_reach_ohm, zone1_resistive_reach_forward_ohm, zone1_resistive_reach_reverse_ohm, zone1_characteristic_angle_deg, zone1_delay_s)
    zone2 = _zone_settings(zone2_enabled, zone2_reach_ohm, zone2_reactive_reach_ohm, zone2_resistive_reach_forward_ohm, zone2_resistive_reach_reverse_ohm, zone2_characteristic_angle_deg, zone2_delay_s)
    zone3 = _zone_settings(zone3_enabled, zone3_reach_ohm, zone3_reactive_reach_ohm, zone3_resistive_reach_forward_ohm, zone3_resistive_reach_reverse_ohm, zone3_characteristic_angle_deg, zone3_delay_s)
    result = compute_distance_manual(
        loop_label=loop_label, voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary, impedance_basis=impedance_basis,
        characteristic=characteristic, zone1=zone1, zone2=zone2, zone3=zone3,
        v1_input=v1_input, v2_input=v2_input, i1_input=i1_input, i2_input=i2_input,
    )
    return _distance_manual_result_to_out(result)
