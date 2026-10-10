"""Relay Import Slice 3: ephemeral relay-setting file upload.

Accepts one file, validates and minimally inspects it, returns basic
metadata, and retains nothing -- no database, no StorageBackend, no
registry, no persistent directory. It deliberately takes no workspace id:
nothing about the upload is workspace state. Extraction, relay
identification and interpretation are later slices.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import Settings
from app.schemas.relay_import import RelayImportUploadOut
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.relay_import_upload_service import inspect_relay_setting_upload

logger = logging.getLogger(__name__)

RELAY_IMPORT_UPLOAD_PATH = "/api/v1/relay-import/upload"

router = APIRouter(prefix="/api/v1/relay-import", tags=["relay-import"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "empty_file": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/upload", response_model=RelayImportUploadOut)
async def upload_relay_setting_file(
    file: UploadFile = File(..., description="Relay setting file (PDF)"),
    settings: Settings = Depends(get_settings_dep),
) -> RelayImportUploadOut:
    try:
        result = await inspect_relay_setting_upload(
            file, max_bytes=settings.max_relay_import_upload_size_bytes
        )
    except ImportServiceError as exc:
        # Code only: never the filename or any content.
        logger.info("Relay-setting upload rejected (%s)", exc.code)
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    except Exception:
        logger.exception("Unexpected error inspecting a relay-setting upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="The file could not be processed.").model_dump(),
        )
    return RelayImportUploadOut(
        filename=result.filename,
        source_format=result.source_format.value,
        size_bytes=result.size_bytes,
        status="accepted",
    )
