"""D5A-2B2A: additive REST contract for the unified measurement-side configuration (Recording Details).

Level 1 (recording) and Level 2 (bay) configuration plus the shared per-channel resolution. Every response
is derived on demand from the shared resolver in `app.services.measurement_side_service`; nothing here
converts a value, touches Per-Unit, or changes any analysis result.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.schemas.measurement_side import (
    BayMeasurementSideOut,
    BaySideUpdateRequest,
    ChannelMeasurementSideOut,
    RecordingMeasurementSideOut,
    RecordingSideUpdateRequest,
    WorkspaceMeasurementSideOut,
)
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.measurement_side_service import (
    SideAuthority,
    build_bay_view,
    build_recording_view,
    build_workspace_views,
    resolve_effective_measurement_side,
    set_bay_side,
    set_recording_side,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["measurement-side"])

_STATUS_BY_ERROR_CODE = {
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "engineering_context_not_found": status.HTTP_404_NOT_FOUND,
    "bay_membership_unconfirmed": status.HTTP_409_CONFLICT,
    "bay_has_no_measurement_channels": status.HTTP_409_CONFLICT,
}


def _deps(request: Request) -> SideAuthority:
    return SideAuthority.from_app_state(request.app.state)


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


@router.get("/measurement-side", response_model=WorkspaceMeasurementSideOut)
def get_workspace_measurement_side(workspace_id: str, request: Request) -> WorkspaceMeasurementSideOut:
    """Every recording's Level 1 state and every bay's Level 2 state (no per-channel detail)."""
    workspace_id = _validate_workspace_id(workspace_id)
    recordings, bays = build_workspace_views(workspace_id, deps=_deps(request))
    return WorkspaceMeasurementSideOut(
        workspace_id=workspace_id,
        recordings=[RecordingMeasurementSideOut.from_view(v, include_channels=False) for v in recordings],
        bays=[BayMeasurementSideOut.from_view(v, include_channels=False) for v in bays],
    )


@router.get("/sources/{source_id}/measurement-side", response_model=RecordingMeasurementSideOut)
def get_recording_measurement_side(workspace_id: str, source_id: str, request: Request) -> RecordingMeasurementSideOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = build_recording_view(workspace_id, source_id, deps=_deps(request))
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return RecordingMeasurementSideOut.from_view(view, include_channels=True)


@router.put("/sources/{source_id}/measurement-side", response_model=RecordingMeasurementSideOut)
def put_recording_measurement_side(
    workspace_id: str, source_id: str, body: RecordingSideUpdateRequest, request: Request,
) -> RecordingMeasurementSideOut:
    """Level 1: correct (or, with `side: null`, un-correct) the recording-wide side. The recording's own
    per-channel declarations are retained and reported; only the engineer's value is stored."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_recording_side(workspace_id, source_id, body.side, body.note, deps=_deps(request))
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return RecordingMeasurementSideOut.from_view(view, include_channels=True)


@router.get("/measurement-side/channel", response_model=ChannelMeasurementSideOut)
def get_channel_measurement_side(
    workspace_id: str, request: Request, source_id: str = Query(...), channel_name: str = Query(...),
) -> ChannelMeasurementSideOut:
    """The shared resolver for one channel. Never an error for an unresolvable channel: it reports
    `effective_side: "unknown"`, `usable: false` and why."""
    workspace_id = _validate_workspace_id(workspace_id)
    resolution = resolve_effective_measurement_side(workspace_id, source_id, channel_name, deps=_deps(request))
    return ChannelMeasurementSideOut.from_domain(resolution)


@router.get("/engineering-contexts/{engineering_context_id}/measurement-side", response_model=BayMeasurementSideOut)
def get_bay_measurement_side(workspace_id: str, engineering_context_id: str, request: Request) -> BayMeasurementSideOut:
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = build_bay_view(workspace_id, engineering_context_id, deps=_deps(request))
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return BayMeasurementSideOut.from_view(view, include_channels=True)


@router.put("/engineering-contexts/{engineering_context_id}/measurement-side", response_model=BayMeasurementSideOut)
def put_bay_measurement_side(
    workspace_id: str, engineering_context_id: str, body: BaySideUpdateRequest, request: Request,
) -> BayMeasurementSideOut:
    """Level 2: one Primary/Secondary choice for the whole bay. Choosing the side the bay already inherits
    from its recording clears the override, so the bay follows the recording again."""
    workspace_id = _validate_workspace_id(workspace_id)
    try:
        view = set_bay_side(workspace_id, engineering_context_id, body.side, deps=_deps(request))
    except ImportServiceError as exc:
        raise _http_error(exc) from exc
    return BayMeasurementSideOut.from_view(view, include_channels=True)
