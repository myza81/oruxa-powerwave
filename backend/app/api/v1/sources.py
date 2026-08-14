"""Phase 1 COMTRADE source/channel API.

Domain-oriented, versioned, and deliberately small -- see
docs/project-memory/MIGRATION_PLAN.md Sec 7 (API contract) and Sec 8
(response-size discipline: no waveform arrays are ever returned).

Upload interaction note (docs/project-memory/MIGRATION_PLAN.md Sec 16,
this phase's UAT candidate list): this endpoint takes two explicit named
parts (cfg_file, dat_file) -- Option B from that discussion, the simplest
bounded UI to prove the upload path. Whether the frontend instead
auto-pairs a single multi-file selection by filename stem (Option A)
remains open for hands-on UAT and does not require an API change either
way; both are one multipart POST to this same endpoint.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import Settings
from app.domain.source import SourceMetadata
from app.schemas.source import ErrorOut, SourceChannelsOut, SourceSummaryOut
from app.services.errors import ImportServiceError
from app.services.import_service import import_comtrade_source
from app.services.workspace_registry import WorkspaceRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sources", tags=["sources"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "parse_error": status.HTTP_400_BAD_REQUEST,
    "missing_companion_file": status.HTTP_400_BAD_REQUEST,
    "unsupported_comtrade_variant": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def _validate_workspace_id(workspace_id: str) -> str:
    # Never used as a filesystem path (Phase 1 never persists anything to
    # disk keyed by workspace_id -- see app.services.import_service), so
    # this is a shape check, not a path-traversal guard.
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SourceSummaryOut)
async def upload_comtrade_source(
    workspace_id: str,
    cfg_file: UploadFile = File(..., description="COMTRADE .cfg configuration file"),
    dat_file: UploadFile = File(..., description="COMTRADE .dat data file"),
    settings: Settings = Depends(get_settings_dep),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)

    try:
        source = await import_comtrade_source(
            workspace_id=workspace_id,
            cfg_upload=cfg_file,
            dat_upload=dat_file,
            max_total_bytes=settings.max_event_upload_size_bytes,
            registry=registry,
        )
    except ImportServiceError as exc:
        # exc.message is user-safe by construction (app.services.errors);
        # the original exception, with full detail, is logged here for
        # engineering/debugging -- never returned to the client. See
        # docs/project-memory/MIGRATION_PLAN.md Sec 9 and Sec 31.
        logger.info("COMTRADE import rejected (%s): %s", exc.code, exc.message)
        raise _http_error(exc) from exc
    except Exception:
        logger.exception("Unexpected error importing COMTRADE source for workspace %s", workspace_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="Import failed unexpectedly.").model_dump(),
        )

    return SourceSummaryOut.from_domain(source)


@router.get("", response_model=list[SourceSummaryOut])
def list_sources(
    workspace_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[SourceSummaryOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    sources = registry.list_for_workspace(workspace_id)
    return [SourceSummaryOut.from_domain(s) for s in sources]


def _get_or_404(registry: WorkspaceRegistry, workspace_id: str, source_id: str) -> SourceMetadata:
    source = registry.get(workspace_id, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return source


@router.get("/{source_id}", response_model=SourceSummaryOut)
def get_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)
    source = _get_or_404(registry, workspace_id, source_id)
    return SourceSummaryOut.from_domain(source)


@router.get("/{source_id}/channels", response_model=SourceChannelsOut)
def get_source_channels(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceChannelsOut:
    workspace_id = _validate_workspace_id(workspace_id)
    source = _get_or_404(registry, workspace_id, source_id)
    return SourceChannelsOut.from_domain(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> None:
    workspace_id = _validate_workspace_id(workspace_id)
    _get_or_404(registry, workspace_id, source_id)
    registry.remove(workspace_id, source_id)
