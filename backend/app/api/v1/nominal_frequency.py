"""NF-1: additive REST contract for a recording's nominal frequency (Auto / Manual).

Foundation only: the value is decided by `app.services.nominal_frequency_service` and nothing else yet reads it.
Until the engineering consumers are migrated, a manual value stored here does NOT change any calculation, so no
user-facing control may present it as doing so.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.nominal_frequency import NominalFrequencyOut, NominalFrequencyUpdateRequest
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError, InvalidNominalFrequencyError
from app.services.nominal_frequency_service import (
    effective_nominal_frequency,
    reset_nominal_frequency_to_auto,
    set_manual_nominal_frequency,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["nominal-frequency"])

_STATUS_BY_ERROR_CODE = {
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_nominal_frequency": status.HTTP_400_BAD_REQUEST,
}


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=ErrorOut(code=exc.code, message=str(exc)).model_dump())


def _deps(request: Request):
    return request.app.state.workspace_registry, request.app.state.nominal_frequency_registry


@router.get("/sources/{source_id}/nominal-frequency", response_model=NominalFrequencyOut)
def get_nominal_frequency(workspace_id: str, source_id: str, request: Request) -> NominalFrequencyOut:
    """The recording's effective nominal frequency with its origin, the imported value, what Auto gives and any
    manual value. Never changes anything."""
    workspace_id = _validate_workspace_id(workspace_id)
    source_registry, registry = _deps(request)
    try:
        result = effective_nominal_frequency(workspace_id, source_id, source_registry=source_registry, registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return NominalFrequencyOut.from_domain(source_id, result)


@router.put("/sources/{source_id}/nominal-frequency", response_model=NominalFrequencyOut)
def put_nominal_frequency(
    workspace_id: str, source_id: str, body: NominalFrequencyUpdateRequest, request: Request,
) -> NominalFrequencyOut:
    """Store a manual value for this recording (`mode: manual`, `value_hz`) or return it to Auto (`mode: auto`).
    The imported value and provenance are never modified; only the engineer's value is stored."""
    workspace_id = _validate_workspace_id(workspace_id)
    source_registry, registry = _deps(request)
    try:
        if body.mode == "auto":
            if body.value_hz is not None:
                raise InvalidNominalFrequencyError("value_hz must not be supplied when mode is 'auto'.")
            result = reset_nominal_frequency_to_auto(
                workspace_id, source_id, source_registry=source_registry, registry=registry)
        else:
            if body.value_hz is None:
                raise InvalidNominalFrequencyError("value_hz is required when mode is 'manual'.")
            result = set_manual_nominal_frequency(
                workspace_id, source_id, body.value_hz, source_registry=source_registry, registry=registry)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return NominalFrequencyOut.from_domain(source_id, result)
