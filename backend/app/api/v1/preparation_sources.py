"""Slice 1 CSV preparation-source API (DEC-072).

A deliberately separate, smaller router from `app.api.v1.sources` -- a
preparation source is not a `SourceMetadata`/`ActiveSource` (it has no
parsed `DisturbanceRecord`, no channels, no waveform data), so it gets
its own resource path rather than being force-fitted into the existing
COMTRADE-shaped `.../sources` contract. This is also why the Workspace
Sidebar's own channel-selection source list (which reads only
`GET .../sources`) never sees a CSV preparation row at all -- a real,
structural reason a `Needs Preparation` source cannot be selected for
waveform display, not merely a UI convention (see this slice's own
guardrail: "a Needs Preparation CSV must never reach normal waveform
loading").

Only `.csv` is accepted in Slice 1 -- Excel is Slice 2 scope.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import Settings
from app.schemas.preparation_session import PreparationSessionSummaryOut
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.preparation_import_service import import_csv_preparation_source
from app.services.preparation_session_registry import PreparationSessionRegistry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/preparation-sources", tags=["preparation-sources"]
)

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_preparation_session_registry(request: Request) -> PreparationSessionRegistry:
    return request.app.state.preparation_session_registry


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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PreparationSessionSummaryOut)
async def upload_csv_preparation_source(
    workspace_id: str,
    csv_file: UploadFile = File(..., description="Raw CSV file to accept as preparation input"),
    settings: Settings = Depends(get_settings_dep),
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSessionSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)

    try:
        summary = await import_csv_preparation_source(
            workspace_id=workspace_id,
            csv_upload=csv_file,
            max_total_bytes=settings.max_event_upload_size_bytes,
            registry=registry,
        )
    except ImportServiceError as exc:
        logger.info("CSV preparation upload rejected (%s): %s", exc.code, exc.message)
        raise _http_error(exc) from exc
    except Exception:
        logger.exception(
            "Unexpected error accepting CSV preparation source for workspace %s", workspace_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="Upload failed unexpectedly.").model_dump(),
        )

    return PreparationSessionSummaryOut.from_domain(summary)


@router.get("", response_model=list[PreparationSessionSummaryOut])
def list_preparation_sources(
    workspace_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> list[PreparationSessionSummaryOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    sessions = registry.list_for_workspace(workspace_id)
    return [PreparationSessionSummaryOut.from_domain(s.summary) for s in sessions]


@router.get("/{source_id}", response_model=PreparationSessionSummaryOut)
def get_preparation_source(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> PreparationSessionSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No preparation source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return PreparationSessionSummaryOut.from_domain(session.summary)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preparation_source(
    workspace_id: str,
    source_id: str,
    registry: PreparationSessionRegistry = Depends(get_preparation_session_registry),
) -> None:
    """Release one preparation session's raw bytes.

    A preparation session has no dependents in Slice 1 (no calculated
    channels, no measurement groups, no synchronization state can ever
    reference it -- those all require a real `SourceMetadata`/
    `ActiveSource`), so this is a plain single-registry removal, unlike
    `app.api.v1.sources.delete_source`'s own multi-registry cascade.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    session = registry.get(workspace_id, source_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No preparation source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    registry.remove(workspace_id, source_id)
