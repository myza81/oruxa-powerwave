"""Oscillation Analysis -- analysis-representation REST exposure (DEC-173
[APPROVED]). Thin translation only: one stateless, side-effect-free POST
into `app.services.oscillation_representation_service`. Deliberately its own
router; it creates no calculated channel and stores nothing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.oscillation import (
    OscillationRepresentationOut,
    OscillationRepresentationRequest,
    OscillationSpectrumOut,
    OscillationSpectrumRequest,
)
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_representation_service import derive_analysis_representation, describe
from app.services.oscillation_spectrum_service import compute_spectrum
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/oscillation-analysis", tags=["oscillation-analysis"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "calculated_channel_not_found": status.HTTP_404_NOT_FOUND,
    "unsupported_representation": status.HTTP_400_BAD_REQUEST,
    "invalid_analysis_window": status.HTTP_400_BAD_REQUEST,
    "invalid_frequency_range": status.HTTP_400_BAD_REQUEST,
    "representation_unavailable": status.HTTP_409_CONFLICT,
    "representation_mismatch": status.HTTP_409_CONFLICT,
    "insufficient_samples": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "non_finite_samples": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "non_uniform_sampling": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_welch_configuration": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


@router.post("/representation", response_model=OscillationRepresentationOut)
def get_analysis_representation(
    workspace_id: str,
    body: OscillationRepresentationRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationRepresentationOut:
    """Describes (and proves derivable) the analysis representation of one
    signal. Computed on demand from the full-resolution record; nothing is
    persisted and no samples are returned."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = derive_analysis_representation(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationRepresentationOut(**describe(result))


@router.post("/spectrum", response_model=OscillationSpectrumOut)
def get_frequency_spectrum(
    workspace_id: str,
    body: OscillationSpectrumRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationSpectrumOut:
    """Welch PSD of one signal over the selected window and frequency range
    (DEC-174 [PROPOSAL]). The signal is resolved from workspace state and the
    PSD computed on demand; only the compact band-limited spectrum and the
    exact parameters used are returned. Nothing is stored."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = compute_spectrum(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            window_start_s=body.window_start_s, window_end_s=body.window_end_s,
            f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationSpectrumOut(**result)
