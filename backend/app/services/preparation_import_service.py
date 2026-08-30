"""CSV preparation-source import orchestration (Slice 1, DEC-072).

Owns the upload -> validate -> accept-as-raw -> registry lifecycle for a
CSV preparation source. Deliberately the narrowest possible slice:

    External CSV
        |
    Temporary immutable raw source   <- this module's own job, nothing more
        |
    Preparation Session

This module does NOT parse the CSV's tabular structure at all -- no
header detection, no delimiter interpretation beyond what the upload
itself already required, no column/time-axis inspection, no
`DisturbanceRecord` construction. "Safe acceptance" here means exactly:
a real filename with a `.csv` extension, a non-empty upload, and a size
within the configured limit -- the same three checks
`app.services.import_service.import_comtrade_source` already applies to
COMTRADE, reusing the exact same generic helpers
(`app.services.upload_utils`) rather than a second implementation.

Never writes to StorageBackend or any persistent location -- the raw
bytes are held only in the caller-supplied
`PreparationSessionRegistry`'s in-memory store (see that module's own
docstring for why, and for the DEC-015/DEC-072 boundary this respects).
"""

from __future__ import annotations

import uuid

from fastapi import UploadFile

from app.domain.preparation_session import (
    FORMAT_CSV,
    STATUS_NEEDS_PREPARATION,
    PreparationSession,
    PreparationSessionSummary,
)
from app.domain.source import utc_now
from app.services.errors import InvalidFileError, UploadTooLargeError
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.upload_utils import read_bounded, validate_suffix

_CSV_SUFFIXES = {".csv"}


async def import_csv_preparation_source(
    *,
    workspace_id: str,
    csv_upload: UploadFile,
    max_total_bytes: int,
    registry: PreparationSessionRegistry,
) -> PreparationSessionSummary:
    """Validate and accept one CSV file as raw, immutable preparation input.

    Raises app.services.errors.ImportServiceError subclasses on any
    failure (unsupported_file_type / invalid_file / upload_too_large --
    the exact same codes and HTTP mapping COMTRADE upload already uses;
    no new error taxonomy is introduced for Slice 1, per DEC-072's own
    "Readiness Issue model is Slice 6 scope, not Slice 1" guardrail).
    """
    filename = validate_suffix(csv_upload.filename, _CSV_SUFFIXES, "CSV")

    known_size = csv_upload.size or 0
    if known_size > max_total_bytes:
        raise UploadTooLargeError(
            f"Upload size ({known_size} bytes) exceeds the "
            f"{max_total_bytes // (1024 * 1024)} MB limit."
        )

    raw_bytes = await read_bounded(csv_upload, max_bytes=max_total_bytes, already_read=0)
    if not raw_bytes:
        raise InvalidFileError("CSV file is empty.")

    source_id = str(uuid.uuid4())
    summary = PreparationSessionSummary(
        source_id=source_id,
        workspace_id=workspace_id,
        original_filename=filename,
        source_format=FORMAT_CSV,
        original_byte_size=len(raw_bytes),
        status=STATUS_NEEDS_PREPARATION,
        created_at=utc_now(),
    )
    registry.add(PreparationSession(summary=summary, raw_bytes=raw_bytes))
    return summary
