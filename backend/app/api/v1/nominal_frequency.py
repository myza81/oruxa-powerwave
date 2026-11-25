"""NF-1: additive REST contract for a recording's nominal frequency (Auto / Manual).

The value is decided by the NF-1 service layer, reached only through `app.services.nominal_frequency_access`, the
release-gated accessor (NF-3B). Until the engineering consumers are migrated, a manual value stored here does NOT change any
calculation, so no user-facing control may present it as doing so. While the server-side release gate is closed (the default
and the only state in a deployed build) `PUT mode=manual` is refused with 409 `manual_nominal_frequency_disabled`, `PUT
mode=auto` still works, and `GET` always reports the Auto resolution.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.nominal_frequency import NominalFrequencyOut, NominalFrequencyUpdateRequest
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError, InvalidNominalFrequencyError
from app.services.nominal_frequency_access import NominalFrequencyAccess

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["nominal-frequency"])

_STATUS_BY_ERROR_CODE = {
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_nominal_frequency": status.HTTP_400_BAD_REQUEST,
    "manual_nominal_frequency_disabled": status.HTTP_409_CONFLICT,
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


def _access(request: Request) -> NominalFrequencyAccess:
    return request.app.state.nominal_frequency_access


@router.get("/sources/{source_id}/nominal-frequency", response_model=NominalFrequencyOut)
def get_nominal_frequency(workspace_id: str, source_id: str, request: Request) -> NominalFrequencyOut:
    """The recording's effective nominal frequency with its origin, the imported value, what Auto gives and any
    manual value. Never changes anything."""
    workspace_id = _validate_workspace_id(workspace_id)
    access = _access(request)
    try:
        result = access.effective(workspace_id, source_id)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return NominalFrequencyOut.from_domain(source_id, result, manual_override_enabled=access.manual_override_enabled)


@router.put("/sources/{source_id}/nominal-frequency", response_model=NominalFrequencyOut)
def put_nominal_frequency(
    workspace_id: str, source_id: str, body: NominalFrequencyUpdateRequest, request: Request,
) -> NominalFrequencyOut:
    """Store a manual value for this recording (`mode: manual`, `value_hz`) or return it to Auto (`mode: auto`).
    The imported value and provenance are never modified; only the engineer's value is stored."""
    workspace_id = _validate_workspace_id(workspace_id)
    access = _access(request)
    try:
        if body.mode == "auto":
            if body.value_hz is not None:
                raise InvalidNominalFrequencyError("value_hz must not be supplied when mode is 'auto'.")
            result = access.reset_to_auto(workspace_id, source_id)
        else:
            if body.value_hz is None and access.manual_override_enabled:
                raise InvalidNominalFrequencyError("value_hz is required when mode is 'manual'.")
            # In order: the recording exists (404), the release gate is open (409; while closed the body is not examined
            # further, so a closed gate reveals nothing about validation), the value is valid (400).
            result = access.set_manual(workspace_id, source_id, body.value_hz)
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return NominalFrequencyOut.from_domain(source_id, result, manual_override_enabled=access.manual_override_enabled)
