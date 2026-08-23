"""DEC-050 Slice 6: thin, source-scoped REST exposure of the already-
approved Slice 1/3/4 Measurement Group / Voltage / Current base
configuration services -- the minimum API surface the new frontend
configuration workspace needs. No new domain semantics, no new
validation, no new conversion math: every mutating endpoint below calls
straight into an existing, already-tested service function; every
read endpoint calls straight into
`app.services.measurement_group_view_service` (itself a pure
composition of existing pure domain resolvers).

Router prefix mirrors `app.api.v1.sources`'s own source-scoped shape --
a Measurement Group's identity is only ever meaningful within its own
`workspace_id`/`source_id` (canonical document section 18); every
lookup below validates a requested `measurement_group_id` actually
belongs to the `source_id` in the URL before touching it, so a group
from one source/workspace can never be read, mutated, or linked-to
through a different one's URL.

Slice 2's grouping detector is invoked ONLY by `POST .../suggest`,
never automatically -- no upload trigger, no trigger on any other
endpoint in this router (task section 20).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import METHOD_EQUIPMENT_RATING, METHOD_MANUAL
from app.domain.measurement_group import MeasurementGroup
from app.schemas.calculated_channel import ChannelRefIn, ChannelRefOut
from app.schemas.measurement_group import (
    CurrentGroupConfigOut,
    CurrentGroupConfigUpdateRequest,
    MeasurementGroupCreateRequest,
    MeasurementGroupOut,
    MeasurementGroupUpdateRequest,
    SuggestGroupsRequest,
    VoltageGroupConfigOut,
    VoltageGroupConfigUpdateRequest,
)
from app.schemas.source import ErrorOut
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import (
    set_current_base_equipment_rating,
    set_current_base_manual,
    set_current_base_none,
)
from app.services.errors import ImportServiceError, SourceNotFoundError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_service import (
    create_group,
    delete_group,
    generate_suggested_groups_for_source,
    update_group_membership,
    update_group_metadata,
)
from app.services.measurement_group_view_service import MeasurementGroupView, build_group_view, build_group_views_for_source
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import (
    return_voltage_reference_to_auto,
    set_manual_voltage_reference,
    set_voltage_base,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups",
    tags=["measurement-groups"],
)

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "measurement_group_not_found": status.HTTP_404_NOT_FOUND,
    "measurement_group_already_exists": status.HTTP_409_CONFLICT,
    "invalid_measurement_group_kind": status.HTTP_400_BAD_REQUEST,
    "invalid_measurement_group_status": status.HTTP_400_BAD_REQUEST,
    "unsupported_channel_reference_kind": status.HTTP_400_BAD_REQUEST,
    "channel_wrong_source": status.HTTP_400_BAD_REQUEST,
    "channel_wrong_engineering_type": status.HTTP_400_BAD_REQUEST,
    "channel_already_grouped": status.HTTP_409_CONFLICT,
    "duplicate_channel_reference": status.HTTP_400_BAD_REQUEST,
    "voltage_configuration_not_applicable": status.HTTP_400_BAD_REQUEST,
    "invalid_voltage_base_value": status.HTTP_400_BAD_REQUEST,
    "invalid_voltage_reference_override": status.HTTP_400_BAD_REQUEST,
    "current_configuration_not_applicable": status.HTTP_400_BAD_REQUEST,
    "invalid_equipment_rating_value": status.HTTP_400_BAD_REQUEST,
    "invalid_manual_current_base_value": status.HTTP_400_BAD_REQUEST,
    "invalid_manual_voltage_base_value": status.HTTP_400_BAD_REQUEST,
    "ambiguous_current_voltage_source": status.HTTP_400_BAD_REQUEST,
    "missing_current_voltage_source": status.HTTP_400_BAD_REQUEST,
    "invalid_linked_voltage_group": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


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


def _require_source(source_registry: WorkspaceRegistry, workspace_id: str, source_id: str) -> None:
    if source_registry.get(workspace_id, source_id) is None:
        raise _http_error(SourceNotFoundError(f"No source '{source_id}' in this workspace."))


def _get_group_in_source_or_404(
    group_registry: MeasurementGroupRegistry, workspace_id: str, source_id: str, measurement_group_id: str
) -> MeasurementGroup:
    """The one place every group-scoped endpoint below confirms a
    requested `measurement_group_id` actually belongs to THIS
    `source_id` -- a group from a different source (even in the same
    workspace) is treated exactly like "does not exist", never
    partially exposed or silently redirected (task section 36)."""
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None or group.source_id != source_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="measurement_group_not_found",
                message=f"No measurement group '{measurement_group_id}' in this source.",
            ).model_dump(),
        )
    return group


def _channel_refs_from_in(refs: list[ChannelRefIn]) -> list[ChannelRef]:
    return [
        ChannelRef(kind=ref.kind, source_id=ref.source_id, channel_name=ref.channel_name, calculated_channel_id=ref.calculated_channel_id)
        for ref in refs
    ]


def _view_to_out(view: MeasurementGroupView) -> MeasurementGroupOut:
    group = view.group
    voltage_config_out = (
        VoltageGroupConfigOut(
            nominal_voltage_ll_kv=view.voltage_config.nominal_voltage_ll_kv,
            reference_mode=view.voltage_config.reference_mode,
            reference_override=view.voltage_config.reference_override,
            effective_reference=view.voltage_config.effective_reference,
            evidence_names=view.voltage_config.evidence_names,
            detection_reason=view.voltage_config.detection_reason,
        )
        if view.voltage_config is not None
        else None
    )
    current_config_out = (
        CurrentGroupConfigOut(
            method=view.current_config.method,
            equipment_rating_mva=view.current_config.equipment_rating_mva,
            linked_voltage_group_id=view.current_config.linked_voltage_group_id,
            manual_voltage_base_kv=view.current_config.manual_voltage_base_kv,
            manual_ibase_ka=view.current_config.manual_ibase_ka,
            resolved_ibase_ka=view.current_config.resolved_ibase_ka,
            applicable_voltage_ll_kv=view.current_config.applicable_voltage_ll_kv,
        )
        if view.current_config is not None
        else None
    )
    return MeasurementGroupOut(
        id=group.id, workspace_id=group.workspace_id, source_id=group.source_id, kind=group.kind,
        display_name=group.display_name,
        channel_refs=[ChannelRefOut.from_domain(ref) for ref in group.channel_refs],
        status=group.status, created_at=group.created_at,
        voltage_config=voltage_config_out, current_config=current_config_out,
        pu_status=view.pu_status, pu_reason=view.pu_reason,
    )


@router.get("", response_model=list[MeasurementGroupOut])
def list_groups(
    workspace_id: str,
    source_id: str,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> list[MeasurementGroupOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    _require_source(source_registry, workspace_id, source_id)
    views = build_group_views_for_source(
        workspace_id=workspace_id, source_id=source_id, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
    return [_view_to_out(v) for v in views]


@router.post("", response_model=MeasurementGroupOut, status_code=status.HTTP_201_CREATED)
def create_measurement_group(
    workspace_id: str,
    source_id: str,
    body: MeasurementGroupCreateRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> MeasurementGroupOut:
    """Manual group creation -- the one safe, already-fully-validated
    group-edit action Slice 6 exposes beyond configuration itself (task
    section 19: move/split/merge remain deferred)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        group = create_group(
            workspace_id=workspace_id, source_id=source_id, kind=body.kind, display_name=body.display_name,
            channel_refs=_channel_refs_from_in(body.channel_refs),
            status=body.status, registry=group_registry, source_registry=source_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    return _view_to_out(view)


@router.post("/suggest", response_model=list[MeasurementGroupOut])
def suggest_groups(
    workspace_id: str,
    source_id: str,
    body: SuggestGroupsRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> list[MeasurementGroupOut]:
    """Explicit, user-triggered ONLY (task section 20) -- never invoked
    by any other endpoint, upload, or display request in this codebase.
    Returns exactly the NEWLY created `suggested`/`needs_review` groups
    (idempotent, additive-only -- `generate_suggested_groups_for_source()`'s
    own contract); an empty list means nothing new was found to
    suggest, never an error."""
    del body
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        new_groups = generate_suggested_groups_for_source(
            workspace_id=workspace_id, source_id=source_id, registry=group_registry, source_registry=source_registry
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    views = [
        build_group_view(
            g, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        for g in new_groups
    ]
    return [_view_to_out(v) for v in views]


@router.get("/{measurement_group_id}", response_model=MeasurementGroupOut)
def get_measurement_group(
    workspace_id: str,
    source_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> MeasurementGroupOut:
    workspace_id = _validate_workspace_id(workspace_id)
    group = _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    return _view_to_out(view)


@router.patch("/{measurement_group_id}", response_model=MeasurementGroupOut)
def update_measurement_group(
    workspace_id: str,
    source_id: str,
    measurement_group_id: str,
    body: MeasurementGroupUpdateRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> MeasurementGroupOut:
    """Partial update -- `display_name`/`status` via
    `update_group_metadata()`, `channel_refs` (full replace) via
    `update_group_membership()`. This is how a `suggested` group is
    promoted to `confirmed` (setting `status`), and the ONLY way this
    router lets an engineer correct membership -- move/split/merge as
    distinct operations remain deferred (task section 19)."""
    workspace_id = _validate_workspace_id(workspace_id)
    _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    try:
        if body.display_name is not None or body.status is not None:
            update_group_metadata(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id, registry=group_registry,
                display_name=body.display_name, status=body.status,
            )
        if body.channel_refs is not None:
            update_group_membership(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                channel_refs=_channel_refs_from_in(body.channel_refs),
                registry=group_registry, source_registry=source_registry,
            )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    group = _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    return _view_to_out(view)


@router.delete("/{measurement_group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_measurement_group(
    workspace_id: str,
    source_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> None:
    """Idempotent. A group that exists but belongs to a DIFFERENT
    source is rejected with 404 (never silently deleted through the
    wrong URL); a group that simply does not exist at all is a
    successful no-op, matching `delete_group()`'s own idempotent
    contract."""
    workspace_id = _validate_workspace_id(workspace_id)
    existing = group_registry.get(workspace_id, measurement_group_id)
    if existing is not None and existing.source_id != source_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="measurement_group_not_found",
                message=f"No measurement group '{measurement_group_id}' in this source.",
            ).model_dump(),
        )
    delete_group(
        workspace_id, measurement_group_id, registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )


@router.put("/{measurement_group_id}/voltage-config", response_model=MeasurementGroupOut)
def put_voltage_config(
    workspace_id: str,
    source_id: str,
    measurement_group_id: str,
    body: VoltageGroupConfigUpdateRequest,
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> MeasurementGroupOut:
    """Combines Slice 3's THREE independent setters
    (`set_voltage_base`/`set_manual_voltage_reference`/
    `return_voltage_reference_to_auto`) behind one form-shaped PUT, so
    the frontend's single "Nominal voltage + Reference" form can Save
    once -- no validation is duplicated here, each call goes straight
    into its own already-tested setter. `KIND_VOLTAGE`-only (Slice 3's
    own `VoltageConfigurationNotApplicableError` rejects a Current
    group id, translated to 400 below)."""
    workspace_id = _validate_workspace_id(workspace_id)
    _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    try:
        if body.nominal_voltage_ll_kv is not None:
            set_voltage_base(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                nominal_voltage_ll_kv=body.nominal_voltage_ll_kv,
                group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            )
        if body.reference_mode == "manual":
            set_manual_voltage_reference(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                reference=body.reference_override,
                group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            )
        else:
            return_voltage_reference_to_auto(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    group = _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    return _view_to_out(view)


@router.put("/{measurement_group_id}/current-config", response_model=MeasurementGroupOut)
def put_current_config(
    workspace_id: str,
    source_id: str,
    measurement_group_id: str,
    body: CurrentGroupConfigUpdateRequest,
    group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> MeasurementGroupOut:
    """Dispatches to exactly one of Slice 4's three method setters based
    on `body.method` -- `KIND_CURRENT`-only. Cross-source/wrong-kind
    linked-Voltage-group validation happens entirely inside
    `set_current_base_equipment_rating()` (`InvalidLinkedVoltageGroupError`/
    `MeasurementGroupNotFoundError`, translated below) -- never
    re-validated at this layer."""
    workspace_id = _validate_workspace_id(workspace_id)
    _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    try:
        if body.method == METHOD_EQUIPMENT_RATING:
            set_current_base_equipment_rating(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                equipment_rating_mva=body.equipment_rating_mva,
                linked_voltage_group_id=body.linked_voltage_group_id,
                manual_voltage_base_kv=body.manual_voltage_base_kv,
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )
        elif body.method == METHOD_MANUAL:
            set_current_base_manual(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                manual_ibase_ka=body.manual_ibase_ka,
                group_registry=group_registry, current_config_registry=current_config_registry,
            )
        else:  # METHOD_NONE
            set_current_base_none(
                workspace_id=workspace_id, measurement_group_id=measurement_group_id,
                group_registry=group_registry, current_config_registry=current_config_registry,
            )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    group = _get_group_in_source_or_404(group_registry, workspace_id, source_id, measurement_group_id)
    view = build_group_view(
        group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    return _view_to_out(view)
