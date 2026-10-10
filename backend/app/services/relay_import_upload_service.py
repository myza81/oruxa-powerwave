"""Relay-setting file upload: bounded, in-memory, minimal inspection only.

Relay Import Slice 3. This module only answers "is this a plausible
relay-setting file of a supported format, and how big is it?". It does
NOT extract settings, identify a relay, or build a RawRelayDocument --
those are later slices.

Raw-file lifecycle: the upload is read into a bounded in-memory ``bytes``
value, inspected, and dropped when this function returns; nothing is
written by this code to any directory, the database, or StorageBackend.
The framework's own multipart spool (an OS temp file past a small
threshold) is closed in the ``finally`` block here as well as by
Starlette at request end.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import UploadFile

from app.domain.relay_import.raw_document import SourceFormat
from app.services.errors import EmptyFileError, InvalidFileError, UnsupportedFileTypeError
from app.services.upload_utils import read_bounded

#: Accepted extensions -> format. Adding Excel/CSV/XML/OEM later means a new
#: entry here plus a format-specific inspector below; the endpoint is unchanged.
SUPPORTED_EXTENSIONS: dict[str, SourceFormat] = {".pdf": SourceFormat.PDF}

_MAX_FILENAME_CHARS = 255
# PDF 32000-1 7.5.2 / 7.5.5: the header must appear within the first 1024
# bytes and the %%EOF marker within the last 1024 bytes. Tolerate a little
# trailing padding that real-world writers add.
_PDF_HEADER = b"%PDF-"
_PDF_HEADER_WINDOW = 1024
_PDF_EOF = b"%%EOF"
_PDF_EOF_WINDOW = 2048


@dataclass(frozen=True)
class RelayUploadInspection:
    filename: str
    source_format: SourceFormat
    size_bytes: int


def safe_display_filename(raw: str | None) -> str:
    """Base name only (browsers/clients may send a full path), length-capped."""
    if not raw:
        return ""
    name = PureWindowsPath(PurePosixPath(raw).name).name
    return name[:_MAX_FILENAME_CHARS]


def _inspect_pdf(data: bytes) -> None:
    if _PDF_HEADER not in data[:_PDF_HEADER_WINDOW]:
        raise InvalidFileError("The file is not a readable PDF (missing PDF header).")
    if _PDF_EOF not in data[-_PDF_EOF_WINDOW:]:
        raise InvalidFileError("The PDF appears to be incomplete or corrupted (missing end marker).")


_INSPECTORS = {SourceFormat.PDF: _inspect_pdf}


async def inspect_relay_setting_upload(upload: UploadFile, *, max_bytes: int) -> RelayUploadInspection:
    filename = safe_display_filename(upload.filename)
    try:
        if not filename:
            raise UnsupportedFileTypeError("The relay setting file must have a filename.")
        suffix = PurePosixPath(filename).suffix.lower()
        source_format = SUPPORTED_EXTENSIONS.get(suffix)
        if source_format is None:
            raise UnsupportedFileTypeError(
                "Unsupported file type. Only PDF relay setting files are supported at present."
            )
        data = await read_bounded(upload, max_bytes=max_bytes, already_read=0)
        if not data:
            raise EmptyFileError("The file is empty.")
        _INSPECTORS[source_format](data)
        return RelayUploadInspection(filename=filename, source_format=source_format, size_bytes=len(data))
    finally:
        await upload.close()
