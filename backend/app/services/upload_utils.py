"""Shared, format-agnostic upload helpers.

Extracted from `app.services.import_service` (Slice 1, CSV/Excel
ingestion) unchanged in behavior -- these two functions never contained
any COMTRADE-specific logic; they were simply generic "read this upload
bounded" / "check this filename's suffix" utilities that happened to
live in the COMTRADE import module before a second provider existed.
`app.services.import_service` and `app.services.preparation_import_service`
both import from here now, so there is exactly one implementation of
each, never two that could silently drift apart.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.services.errors import UnsupportedFileTypeError, UploadTooLargeError

_READ_CHUNK_BYTES = 1024 * 1024  # 1 MiB


async def read_bounded(upload: UploadFile, *, max_bytes: int, already_read: int) -> bytes:
    """Read *upload* fully, aborting as soon as the combined total would exceed max_bytes.

    Does not trust upload.size alone (a caller may already have used it
    as a fast pre-check, but a missing/zero Content-Length can leave it
    unset) -- this is the authoritative check, based on bytes actually
    read.
    """
    chunks: list[bytes] = []
    total = already_read
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(
                f"Combined upload size exceeds the {max_bytes // (1024 * 1024)} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def validate_suffix(filename: str | None, allowed: set[str], role: str) -> str:
    if not filename:
        raise UnsupportedFileTypeError(f"{role} file must have a filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise UnsupportedFileTypeError(
            f"{role} file '{filename}' has an unsupported extension "
            f"(expected one of {sorted(allowed)})."
        )
    return filename
