"""Phase 1/2A COMTRADE source/channel/waveform API.

Domain-oriented, versioned, and deliberately small -- see
docs/project-memory/MIGRATION_PLAN.md Sec 7 (API contract) and Sec 8
(response-size discipline). The source/channel endpoints (upload, list,
get, delete, channels) never return waveform arrays, exactly as Phase 1
established. The Phase 2A addition, GET .../waveform, is the one
deliberate exception -- and even there, the response is always bounded
(full-resolution only when the requested range's raw sample count is
already <= the request's point_budget; a peak-preserving display
representation otherwise) -- see app.services.waveform_service.

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

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from app.config import Settings
from app.domain.source import ActiveSource
from app.schemas.cursor_values import CursorValuesOut, CursorValuesRequest
from app.schemas.digital_waveform import DigitalWaveformBatchOut, DigitalWaveformOut
from app.schemas.source import ErrorOut, SourceChannelsOut, SourceSummaryOut
from app.schemas.waveform import WaveformRangeOut
from app.services.errors import ImportServiceError
from app.services.import_service import import_comtrade_source
from app.services.waveform_service import (
    DEFAULT_POINT_BUDGET,
    extract_cursor_values,
    extract_digital_waveform,
    extract_waveform_range,
)
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
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "channel_not_digital": status.HTTP_400_BAD_REQUEST,
    "invalid_time_range": status.HTTP_400_BAD_REQUEST,
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
    return [SourceSummaryOut.from_domain(s.metadata) for s in sources]


def _get_or_404(registry: WorkspaceRegistry, workspace_id: str, source_id: str) -> ActiveSource:
    active = registry.get(workspace_id, source_id)
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return active


@router.get("/{source_id}", response_model=SourceSummaryOut)
def get_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    return SourceSummaryOut.from_domain(active.metadata)


@router.get("/{source_id}/channels", response_model=SourceChannelsOut)
def get_source_channels(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceChannelsOut:
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    return SourceChannelsOut.from_domain(active.metadata)


@router.get("/{source_id}/waveform", response_model=WaveformRangeOut)
def get_source_waveform(
    workspace_id: str,
    source_id: str,
    channel_name: str = Query(..., description="Analog channel name, as returned by GET .../channels."),
    start_time: float | None = Query(
        None, description="Elapsed seconds on the source's native time axis. Omit for the record start."
    ),
    end_time: float | None = Query(
        None, description="Elapsed seconds on the source's native time axis. Omit for the record end."
    ),
    point_budget: int = Query(
        DEFAULT_POINT_BUDGET,
        gt=0,
        description=(
            "Display-response budget, not an engineering-resolution setting. "
            "If the requested range has <= point_budget raw samples, the full-resolution "
            "range is returned unchanged; otherwise a peak-preserving min/max envelope is "
            "returned instead -- see app.domain.waveform_reduction."
        ),
    ),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> WaveformRangeOut:
    """Phase 2A waveform range endpoint -- see docs/project-memory/MIGRATION_PLAN.md's
    Phase 2A implementation record for the full API contract and its rationale.

    Analog channels only in Phase 2A (digital waveform delivery is
    deliberately deferred -- see app.services.errors.ChannelNotAnalogError).
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    try:
        result = extract_waveform_range(
            active,
            channel_name=channel_name,
            start_time=start_time,
            end_time=end_time,
            point_budget=point_budget,
        )
    except ImportServiceError as exc:
        logger.info(
            "Waveform range request rejected (%s) for workspace %s source %s: %s",
            exc.code,
            workspace_id,
            source_id,
            exc.message,
        )
        raise _http_error(exc) from exc
    return WaveformRangeOut.from_result(result)


@router.get("/{source_id}/digital-waveform", response_model=DigitalWaveformBatchOut)
def get_source_digital_waveform(
    workspace_id: str,
    source_id: str,
    channel_names: list[str] = Query(
        ...,
        description=(
            "One or more digital channel names, as returned by GET .../channels "
            "(repeat the query parameter for a batch: "
            "?channel_names=A&channel_names=B). Batched deliberately -- a "
            "source may carry hundreds of digital channels, and N separate "
            "requests for N channels would be wasteful (see "
            "docs/project-memory/MIGRATION_PLAN.md's Phase 4A record)."
        ),
    ),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> DigitalWaveformBatchOut:
    """Phase 4A batched digital-waveform endpoint.

    Digital channels only (mirrors GET .../waveform's analog-only
    contract, symmetrically) -- see
    app.services.errors.ChannelNotDigitalError. Always returns the full
    record's transition list per channel; no start_time/end_time/
    point_budget parameters -- see extract_digital_waveform's own
    docstring for why.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    results: list[DigitalWaveformOut] = []
    for channel_name in channel_names:
        try:
            result = extract_digital_waveform(active, channel_name=channel_name)
        except ImportServiceError as exc:
            logger.info(
                "Digital waveform request rejected (%s) for workspace %s source %s "
                "channel %s: %s",
                exc.code,
                workspace_id,
                source_id,
                channel_name,
                exc.message,
            )
            raise _http_error(exc) from exc
        results.append(DigitalWaveformOut.from_result(result))
    return DigitalWaveformBatchOut(channels=results)


@router.post("/{source_id}/cursor-values", response_model=CursorValuesOut)
def get_source_cursor_values(
    workspace_id: str,
    source_id: str,
    body: CursorValuesRequest,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> CursorValuesOut:
    """Phase 4C1 batched A/B instantaneous-value endpoint.

    One request per source (never per channel -- section 8/9): every
    channel in `body.channel_names` is resolved against the SAME two
    already-computed nearest-sample indices (see
    app.services.waveform_service.extract_cursor_values's own docstring).
    POST (not GET) because the request body naturally carries a channel
    list alongside two independent optional cursor times -- the same
    shape choice this project already made for multipart uploads, just
    JSON here since there is no file involved.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    result = extract_cursor_values(
        active,
        channel_names=body.channel_names,
        cursor_a_time=body.cursor_a_time,
        cursor_b_time=body.cursor_b_time,
    )
    return CursorValuesOut.from_result(result)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> None:
    workspace_id = _validate_workspace_id(workspace_id)
    _get_or_404(registry, workspace_id, source_id)
    registry.remove(workspace_id, source_id)
