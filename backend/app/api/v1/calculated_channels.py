"""Phase 5A Calculated Channels API (DEC-047).

Workspace-scoped, mirroring app.api.v1.sources's own conventions
(`_validate_workspace_id`/`_http_error`/`_STATUS_BY_ERROR_CODE`,
duplicated per-module rather than shared, matching that module's own
documented reason: avoiding a circular import between routers -- see
app.main's own trailing note). A calculated channel is not owned by any
one source, so its own display/measurement endpoints live under
`/calculated-channels`, workspace-scoped, rather than nested under
`/sources/{source_id}` -- see app.domain.calculated_channel's own module
docstring for why (a calculated channel may combine multiple sources'
worth of proven-aligned inputs, or have none directly, several layers
into a calculated-from-calculated chain).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.calculated_channel import (
    CalculatedAnnotationAnchorOut,
    CalculatedAnnotationAnchorRequest,
    CalculatedChannelCreateRequest,
    CalculatedChannelOut,
    CalculatedCursorValuesOut,
    CalculatedCursorValuesRequest,
    CalculatedCursorValuesItemOut,
    CalculatedPeakBatchOut,
    CalculatedPeakBatchRequest,
    CalculatedPeakResultOut,
    CalculatedWaveformRangeOut,
    RmsEligibilityRequest,
    RmsEligibilityResponse,
)
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    check_rms_eligibility,
    create_calculated_channel,
    delete_calculated_channel,
    extract_calculated_cursor_values,
    extract_calculated_waveform_range,
    resolve_calculated_annotation_anchor,
    resolve_calculated_peak_value,
)
from app.services.errors import ImportServiceError
from app.services.per_unit_registry import PerUnitRegistry
from app.services.per_unit_service import voltage_channel_names_for_source
from app.services.waveform_service import DEFAULT_POINT_BUDGET
from app.services.workspace_registry import WorkspaceRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/calculated-channels", tags=["calculated-channels"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "calculated_channel_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_operation_arity": status.HTTP_400_BAD_REQUEST,
    "invalid_constant": status.HTTP_400_BAD_REQUEST,
    "incompatible_unit": status.HTTP_400_BAD_REQUEST,
    "incompatible_time_base": status.HTTP_400_BAD_REQUEST,
    "duplicate_calculated_channel_name": status.HTTP_400_BAD_REQUEST,
    "invalid_calculated_channel_name": status.HTTP_400_BAD_REQUEST,
    "calculated_channel_has_dependents": status.HTTP_400_BAD_REQUEST,
    "cyclic_dependency": status.HTTP_400_BAD_REQUEST,
    "invalid_calculated_operation": status.HTTP_400_BAD_REQUEST,
    "invalid_time_range": status.HTTP_400_BAD_REQUEST,
    "invalid_nominal_frequency": status.HTTP_400_BAD_REQUEST,
    "rms_recording_too_short": status.HTTP_400_BAD_REQUEST,
    "rms_sampling_too_sparse": status.HTTP_400_BAD_REQUEST,
    "rms_override_required": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


def _resolve_profile_for_calculated_channel(
    per_unit_registry: PerUnitRegistry, workspace_id: str, calculated_channel_id: str
):
    """Phase 5C (DEC-049; source-bound redesign): resolves one calculated
    channel's own currently inherited configuration (or `None`) -- the
    SOURCE whose configuration it inherited from (decision 6/7,
    unchanged), via the calc-only assignment record."""
    source_id = per_unit_registry.profile_for_calculated_channel(workspace_id, calculated_channel_id)
    return per_unit_registry.get(workspace_id, source_id) if source_id else None


def _voltage_channel_names_for_profile(source_registry: WorkspaceRegistry, workspace_id: str, profile) -> list[str]:
    """The Voltage-channel-naming evidence for whichever SOURCE a
    calculated channel's own inherited configuration actually belongs
    to -- only consulted for a CURRENT calculated channel under
    `current_base_mode == "derived"`. Note this is the CONFIGURATION's
    own `source_id`, not necessarily the calculated channel's own
    `reference_source_id` (they usually coincide, but decision 6's
    inheritance composes through calculated-from-calculated chains)."""
    if profile is None:
        return []
    return voltage_channel_names_for_source(source_registry, workspace_id, profile.source_id)


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


def _get_channel_or_404(
    registry: CalculatedChannelRegistry, workspace_id: str, calculated_channel_id: str
):
    channel = registry.get(workspace_id, calculated_channel_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="calculated_channel_not_found",
                message=f"No calculated channel '{calculated_channel_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return channel


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CalculatedChannelOut)
def create_channel(
    workspace_id: str,
    body: CalculatedChannelCreateRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
) -> CalculatedChannelOut:
    """Create + eagerly evaluate one calculated channel (section 46: eager
    evaluation at creation, never re-evaluated on later requests -- see
    app.domain.calculated_channel.CalculatedChannel's own docstring)."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        channel = create_calculated_channel(
            workspace_id=workspace_id,
            name=body.name,
            operation=body.operation,
            inputs=[ref.to_domain() for ref in body.inputs],
            parameters=body.parameters,
            source_registry=source_registry,
            calc_registry=calc_registry,
            override=body.override,
            per_unit_registry=per_unit_registry,
        )
    except ImportServiceError as exc:
        logger.info("Calculated channel creation rejected (%s) for workspace %s: %s", exc.code, workspace_id, exc.message)
        raise _http_error(exc) from exc
    return CalculatedChannelOut.from_domain(channel)


@router.get("", response_model=list[CalculatedChannelOut])
def list_channels(
    workspace_id: str,
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> list[CalculatedChannelOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    channels = calc_registry.list_for_workspace(workspace_id)
    return [CalculatedChannelOut.from_domain(c) for c in channels]


@router.delete("/{calculated_channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    workspace_id: str,
    calculated_channel_id: str,
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
) -> None:
    """Section 25/63: BLOCKED (never a silent cascade) if another
    calculated channel still depends on this one."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        delete_calculated_channel(
            workspace_id=workspace_id, calculated_channel_id=calculated_channel_id, calc_registry=calc_registry,
            per_unit_registry=per_unit_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{calculated_channel_id}/waveform", response_model=CalculatedWaveformRangeOut)
def get_channel_waveform(
    workspace_id: str,
    calculated_channel_id: str,
    start_time: float | None = None,
    end_time: float | None = None,
    point_budget: int = DEFAULT_POINT_BUDGET,
    unit_mode: str = "engineering",
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> CalculatedWaveformRangeOut:
    """Section 48/49: reuses the exact same full-resolution-threshold +
    peak-preserving-reduction pipeline GET .../sources/{id}/waveform
    already uses -- never a separate frontend waveform delivery
    mechanism."""
    workspace_id = _validate_workspace_id(workspace_id)
    channel = _get_channel_or_404(calc_registry, workspace_id, calculated_channel_id)
    per_unit_profile = (
        _resolve_profile_for_calculated_channel(per_unit_registry, workspace_id, calculated_channel_id)
        if unit_mode == "per_unit"
        else None
    )
    result = extract_calculated_waveform_range(
        channel, start_time=start_time, end_time=end_time, point_budget=point_budget,
        unit_mode=unit_mode, per_unit_profile=per_unit_profile,
        voltage_channel_names=_voltage_channel_names_for_profile(source_registry, workspace_id, per_unit_profile),
    )
    return CalculatedWaveformRangeOut.from_result(result)


@router.post("/rms-eligibility", response_model=RmsEligibilityResponse)
def get_rms_eligibility(
    workspace_id: str,
    body: RmsEligibilityRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> RmsEligibilityResponse:
    """A dedicated, stateless, side-effect-free pre-check (Phase 5B,
    DEC-048) -- the Signal Builder calls this on every input/nominal-
    frequency change, independent of Create's own error/success state
    (section 44/62). Mirrors the existing `/cursor-values`/`/peak-values`
    literal-segment-POST shape rather than a create-dry-run flag, so it
    never touches `create_calculated_channel()`'s own atomic all-checks-
    then-write guarantee.

    This is the SAME `check_rms_eligibility()` function
    `create_calculated_channel()` calls internally at actual creation time
    -- the backend never trusts a client-supplied eligibility result
    (section 43), it always re-derives one itself.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        eligibility = check_rms_eligibility(
            workspace_id=workspace_id,
            input_ref=body.input.to_domain(),
            nominal_frequency_hz=body.nominal_frequency_hz,
            source_registry=source_registry,
            calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return RmsEligibilityResponse.from_result(eligibility)


@router.post("/cursor-values", response_model=CalculatedCursorValuesOut)
def get_cursor_values(
    workspace_id: str,
    body: CalculatedCursorValuesRequest,
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> CalculatedCursorValuesOut:
    """Section 54: A/B cursor values for a batch of calculated channels --
    unknown ids are silently skipped (mirrors extract_cursor_values's own
    established resilience philosophy for source channels: one stale id
    must never blank out the rest of the batch)."""
    workspace_id = _validate_workspace_id(workspace_id)
    channels = [
        c for c in (calc_registry.get(workspace_id, cid) for cid in body.calculated_channel_ids) if c is not None
    ]
    per_unit_profiles = None
    voltage_channel_names_by_id = None
    if body.unit_mode == "per_unit":
        per_unit_profiles = {
            c.id: _resolve_profile_for_calculated_channel(per_unit_registry, workspace_id, c.id) for c in channels
        }
        voltage_channel_names_by_id = {
            c.id: _voltage_channel_names_for_profile(source_registry, workspace_id, per_unit_profiles[c.id])
            for c in channels
        }
    results = extract_calculated_cursor_values(
        channels, cursor_a_time=body.cursor_a_time, cursor_b_time=body.cursor_b_time,
        unit_mode=body.unit_mode, per_unit_profiles=per_unit_profiles,
        voltage_channel_names_by_id=voltage_channel_names_by_id,
    )
    return CalculatedCursorValuesOut(channels=[CalculatedCursorValuesItemOut.from_result(r) for r in results])


@router.post("/peak-values", response_model=CalculatedPeakBatchOut)
def get_peak_values(
    workspace_id: str,
    body: CalculatedPeakBatchRequest,
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> CalculatedPeakBatchOut:
    """Section 55: +Peak/-Peak for a batch of calculated channels, mirroring
    the source-channel .../peak-values batch contract (DEC-046) --
    an unknown id degrades that ONE item to `available=False` rather than
    failing the whole batch, same per-item resilience as the source path."""
    workspace_id = _validate_workspace_id(workspace_id)
    if body.start_time > body.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(
                code="invalid_time_range",
                message=f"start_time ({body.start_time}) must not be greater than end_time ({body.end_time}).",
            ).model_dump(),
        )
    results: list[CalculatedPeakResultOut] = []
    for item in body.requests:
        channel = calc_registry.get(workspace_id, item.calculated_channel_id)
        if channel is None:
            results.append(
                CalculatedPeakResultOut(
                    calculated_channel_id=item.calculated_channel_id, mode=item.mode, available=False,
                    sample_index=None, elapsed_seconds=None, value=None, unit=None,
                )
            )
            continue
        per_unit_profile = (
            _resolve_profile_for_calculated_channel(per_unit_registry, workspace_id, item.calculated_channel_id)
            if body.unit_mode == "per_unit"
            else None
        )
        result = resolve_calculated_peak_value(
            channel, mode=item.mode, start_time=body.start_time, end_time=body.end_time,
            unit_mode=body.unit_mode, per_unit_profile=per_unit_profile,
            voltage_channel_names=_voltage_channel_names_for_profile(source_registry, workspace_id, per_unit_profile),
        )
        results.append(CalculatedPeakResultOut.from_result(result))
    return CalculatedPeakBatchOut(start_time=body.start_time, end_time=body.end_time, results=results)


@router.post("/{calculated_channel_id}/annotation-anchor", response_model=CalculatedAnnotationAnchorOut)
def resolve_annotation_anchor(
    workspace_id: str,
    calculated_channel_id: str,
    body: CalculatedAnnotationAnchorRequest,
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> CalculatedAnnotationAnchorOut:
    """Section 56: Callout anchor resolution for a calculated channel --
    reuses the exact same nearest-sample rule
    POST .../sources/{id}/annotation-anchor already uses for source
    channels (DEC-045), just resolved against a calculated channel's own
    retained full-resolution arrays instead of an ActiveSource."""
    workspace_id = _validate_workspace_id(workspace_id)
    channel = _get_channel_or_404(calc_registry, workspace_id, calculated_channel_id)
    per_unit_profile = (
        _resolve_profile_for_calculated_channel(per_unit_registry, workspace_id, calculated_channel_id)
        if body.unit_mode == "per_unit"
        else None
    )
    result = resolve_calculated_annotation_anchor(
        channel, approximate_elapsed_seconds=body.approximate_elapsed_seconds,
        unit_mode=body.unit_mode, per_unit_profile=per_unit_profile,
        voltage_channel_names=_voltage_channel_names_for_profile(source_registry, workspace_id, per_unit_profile),
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(
                code="invalid_time_range",
                message=(
                    f"approximate_elapsed_seconds ({body.approximate_elapsed_seconds}) is outside "
                    "this calculated channel's own recorded time bounds."
                ),
            ).model_dump(),
        )
    return CalculatedAnnotationAnchorOut.from_result(result)
