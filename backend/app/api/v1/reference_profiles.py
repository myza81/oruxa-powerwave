"""Compliance & Capability -- Reference Profiles / Reference Layers /
Comparison Chart REST exposure (Slice 3). Thin translation only -- every
endpoint calls straight into `app.services.reference_profile_service`;
no new domain semantics live here.

**Every endpoint in this router is usable in a workspace that has never
had a source uploaded** -- the mid-conversation product requirement this
slice was amended to satisfy ("Reference Layers must work without an
uploaded recording"). None of these routes accept or resolve a
`source_id`, a `measurement_group_id`, or an Engineering Context id; the
only optional Measurement concept anywhere here is the `quantity_id`
query parameter on the two GET endpoints that report compatibility
(`list_reference_layers`/`get_comparison_chart`), used purely to
classify each active layer's compatibility against whatever the
Compliance page's own Measurement section currently has selected --
never required, and its absence is `not_yet_applicable`, never
`incompatible` (see `app.services.reference_profile_service.
compute_layer_compatibility()`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.reference_profile import (
    ComparisonChartOut,
    ReferenceLayerCreateRequest,
    ReferenceLayerOut,
    ReferenceLayerUpdateRequest,
    ReferenceProfileImportRequest,
    ReferenceProfileOut,
    ReferenceProfileWriteRequest,
)
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.reference_layer_registry import ReferenceLayerRegistry
from app.services.reference_profile_registry import ReferenceProfileRegistry
from app.services.reference_profile_service import (
    ReferenceProfileEntry,
    add_layer,
    build_comparison_chart,
    compute_layer_compatibility,
    create_custom_profile,
    delete_custom_profile,
    duplicate_profile,
    export_profile,
    get_profile_entry_or_404,
    import_profile,
    list_layers_for_workspace,
    list_profiles_for_workspace,
    remove_layer,
    set_layer_visibility,
    update_custom_profile,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["reference-profiles"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "reference_profile_not_found": status.HTTP_404_NOT_FOUND,
    "reference_profile_already_exists": status.HTTP_400_BAD_REQUEST,
    "reference_profile_is_built_in": status.HTTP_400_BAD_REQUEST,
    "reference_profile_invalid": status.HTTP_400_BAD_REQUEST,
    "unsupported_reference_profile_schema_version": status.HTTP_400_BAD_REQUEST,
    "reference_layer_not_found": status.HTTP_404_NOT_FOUND,
    "reference_layer_already_exists": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_reference_profile_registry(request: Request) -> ReferenceProfileRegistry:
    return request.app.state.reference_profile_registry


def get_reference_layer_registry(request: Request) -> ReferenceLayerRegistry:
    return request.app.state.reference_layer_registry


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    detail = ErrorOut(code=exc.code, message=exc.message).model_dump()
    # Task section 13: "Validation errors identify the offending row/
    # field" -- ReferenceProfileValidationServiceError carries this on
    # top of the shared code/message shape every other endpoint already
    # returns; added here (not on the shared ErrorOut schema itself, to
    # avoid touching every other router's response shape) so a
    # table-first editor UI can highlight the exact segment row.
    reason_code = getattr(exc, "reason_code", None)
    if reason_code is not None:
        detail["reason_code"] = reason_code
        detail["boundary"] = getattr(exc, "boundary", None)
        detail["segment_index"] = getattr(exc, "segment_index", None)
        detail["field_name"] = getattr(exc, "field_name", None)
    return HTTPException(status_code=status_code, detail=detail)


# ---------------------------------------------------------------------
# Reference Profiles
# ---------------------------------------------------------------------

@router.get("/reference-profiles", response_model=list[ReferenceProfileOut])
def list_reference_profiles(
    workspace_id: str,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> list[ReferenceProfileOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    entries = list_profiles_for_workspace(workspace_id, custom_registry=registry)
    return [ReferenceProfileOut.from_entry(entry) for entry in entries]


@router.get("/reference-profiles/{profile_id}", response_model=ReferenceProfileOut)
def get_reference_profile(
    workspace_id: str,
    profile_id: str,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> ReferenceProfileOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        entry = get_profile_entry_or_404(workspace_id, profile_id, custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReferenceProfileOut.from_entry(entry)


@router.post("/reference-profiles", status_code=status.HTTP_201_CREATED, response_model=ReferenceProfileOut)
def create_reference_profile(
    workspace_id: str,
    body: ReferenceProfileWriteRequest,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> ReferenceProfileOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = create_custom_profile(workspace_id, body.to_domain(profile_id=""), custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReferenceProfileOut.from_entry(ReferenceProfileEntry(profile=profile, source="custom"))


@router.put("/reference-profiles/{profile_id}", response_model=ReferenceProfileOut)
def update_reference_profile(
    workspace_id: str,
    profile_id: str,
    body: ReferenceProfileWriteRequest,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> ReferenceProfileOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = update_custom_profile(workspace_id, profile_id, body.to_domain(profile_id=profile_id), custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReferenceProfileOut.from_entry(ReferenceProfileEntry(profile=profile, source="custom"))


@router.post("/reference-profiles/{profile_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=ReferenceProfileOut)
def duplicate_reference_profile(
    workspace_id: str,
    profile_id: str,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> ReferenceProfileOut:
    """Works for a built-in OR a custom source profile (task section 8)
    -- always produces a brand-new, independent custom profile."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = duplicate_profile(workspace_id, profile_id, custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReferenceProfileOut.from_entry(ReferenceProfileEntry(profile=profile, source="custom"))


@router.delete("/reference-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference_profile(
    workspace_id: str,
    profile_id: str,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> None:
    """Rejects a built-in target (`reference_profile_is_built_in`).
    Cascades: every active layer in this workspace referencing the
    deleted custom profile is removed too -- see
    `app.services.reference_profile_service.delete_custom_profile()`'s
    own docstring for why (task section 10's own guardrail is the
    REVERSE direction: removing a LAYER never deletes the profile)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        delete_custom_profile(workspace_id, profile_id, custom_registry=registry, layer_registry=layer_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/reference-profiles/{profile_id}/export")
def export_reference_profile(
    workspace_id: str,
    profile_id: str,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> dict:
    """Task section 17's stable versioned export schema
    (`{"schema_version": 1, "profile": {...}}`) -- returned verbatim, not
    wrapped in `ReferenceProfileOut`, since a re-`import` must round-trip
    through the exact shape `app.domain.reference_profile.
    profile_from_json_dict()` accepts."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        return export_profile(workspace_id, profile_id, custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/reference-profiles/import", status_code=status.HTTP_201_CREATED, response_model=ReferenceProfileOut)
def import_reference_profile(
    workspace_id: str,
    body: ReferenceProfileImportRequest,
    registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
) -> ReferenceProfileOut:
    """Task section 17: parse -> validate schema -> validate domain ->
    create a NEW custom session profile. An unsupported/missing
    `schema_version`, or any structurally invalid `profile` body, fails
    explicitly (400) -- never silently coerced."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        profile = import_profile(workspace_id, body.to_envelope(), custom_registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return ReferenceProfileOut.from_entry(ReferenceProfileEntry(profile=profile, source="custom"))


# ---------------------------------------------------------------------
# Reference Layers
# ---------------------------------------------------------------------

@router.get("/reference-layers", response_model=list[ReferenceLayerOut])
def list_reference_layers(
    workspace_id: str,
    quantity_id: str | None = None,
    profile_registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> list[ReferenceLayerOut]:
    """`quantity_id` is OPTIONAL -- its absence reports every active
    layer's compatibility as `not_yet_applicable`, never `incompatible`
    (mid-conversation amendment). Skips (never crashes on) a layer whose
    own profile has vanished, matching `build_comparison_chart()`'s own
    resilience."""
    workspace_id = _validate_workspace_id(workspace_id)
    layers = list_layers_for_workspace(workspace_id, layer_registry=layer_registry)
    out: list[ReferenceLayerOut] = []
    for layer in layers:
        try:
            entry = get_profile_entry_or_404(workspace_id, layer.profile_id, custom_registry=profile_registry)
        except ImportServiceError:
            continue
        layer_status, reason = compute_layer_compatibility(entry.profile, selected_quantity_id=quantity_id)
        out.append(ReferenceLayerOut.from_domain(layer, entry, compatibility_status=layer_status, compatibility_reason=reason))
    return out


@router.get("/reference-layers/chart-data", response_model=ComparisonChartOut)
def get_comparison_chart(
    workspace_id: str,
    quantity_id: str | None = None,
    profile_registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> ComparisonChartOut:
    """Static reference-curve rendering only (task section 14/18) -- no
    measured waveform, no evaluation. `quantity_id` is OPTIONAL, exactly
    like `list_reference_layers()`; the chart's own x/y axes are derived
    entirely from the active, VISIBLE layers' own profiles (mid-
    conversation amendment), never from a recording."""
    workspace_id = _validate_workspace_id(workspace_id)
    chart = build_comparison_chart(
        workspace_id, custom_registry=profile_registry, layer_registry=layer_registry, selected_quantity_id=quantity_id,
    )
    return ComparisonChartOut.from_domain(chart)


@router.post("/reference-layers", status_code=status.HTTP_201_CREATED, response_model=ReferenceLayerOut)
def create_reference_layer(
    workspace_id: str,
    body: ReferenceLayerCreateRequest,
    quantity_id: str | None = None,
    profile_registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> ReferenceLayerOut:
    """No maximum active-layer count is enforced (task section 11).
    `quantity_id` is optional -- passed only so the immediate response
    reflects the Compliance page's own currently-selected Measurement,
    if any (the frontend still refetches the full layer list after every
    mutation, matching this codebase's established convention; this is a
    convenience, not the source of truth)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        layer = add_layer(
            workspace_id, body.profile_id, visible=body.visible, custom_registry=profile_registry, layer_registry=layer_registry,
        )
        entry = get_profile_entry_or_404(workspace_id, layer.profile_id, custom_registry=profile_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    layer_status, reason = compute_layer_compatibility(entry.profile, selected_quantity_id=quantity_id)
    return ReferenceLayerOut.from_domain(layer, entry, compatibility_status=layer_status, compatibility_reason=reason)


@router.patch("/reference-layers/{layer_id}", response_model=ReferenceLayerOut)
def update_reference_layer(
    workspace_id: str,
    layer_id: str,
    body: ReferenceLayerUpdateRequest,
    quantity_id: str | None = None,
    profile_registry: ReferenceProfileRegistry = Depends(get_reference_profile_registry),
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> ReferenceLayerOut:
    """The only mutable field on an active layer is `visible` (task
    section 10's own visibility checkbox)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        layer = set_layer_visibility(workspace_id, layer_id, body.visible, layer_registry=layer_registry)
        entry = get_profile_entry_or_404(workspace_id, layer.profile_id, custom_registry=profile_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    layer_status, reason = compute_layer_compatibility(entry.profile, selected_quantity_id=quantity_id)
    return ReferenceLayerOut.from_domain(layer, entry, compatibility_status=layer_status, compatibility_reason=reason)


@router.delete("/reference-layers/{layer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference_layer(
    workspace_id: str,
    layer_id: str,
    layer_registry: ReferenceLayerRegistry = Depends(get_reference_layer_registry),
) -> None:
    """Never touches the referenced profile (task section 10)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        remove_layer(workspace_id, layer_id, layer_registry=layer_registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
