"""Structured service errors.

Originally "import errors" only (Phase 1); Phase 2A extends the same
taxonomy/base class to app.services.waveform_service's errors too, rather
than inventing a parallel hierarchy -- both are ImportServiceError
subclasses so app.api.v1.sources's single `_http_error()` mapping and
`_STATUS_BY_ERROR_CODE` table keep working unchanged for both.

Maps to the error taxonomy in docs/project-memory/MIGRATION_PLAN.md Sec 9,
extended with `upload_too_large` (not anticipated in the original Phase 0
taxonomy; added here to satisfy the size-limit requirement introduced for
this implementation task -- see docs/project-memory/MIGRATION_PLAN.md's
Phase 1 update).

Every error carries a `code` and a user-safe `message`. Internal exception
detail (the original traceback) is logged server-side by the API layer,
never included in the response body -- see
docs/project-memory/POWERWAVE_DISCOVERY.md's finding that powerwave's own
COMTRADE path leaks raw exception text, which this migration explicitly
does not preserve (docs/project-memory/MIGRATION_PLAN.md Sec 15).
"""

from __future__ import annotations


class ImportServiceError(Exception):
    """Base class for all structured import-service errors."""

    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileTypeError(ImportServiceError):
    code = "unsupported_file_type"


class InvalidFileError(ImportServiceError):
    code = "invalid_file"


class ParseError(ImportServiceError):
    code = "parse_error"


class MissingCompanionFileError(ImportServiceError):
    code = "missing_companion_file"


class UnsupportedComtradeVariantError(ImportServiceError):
    code = "unsupported_comtrade_variant"


class UploadTooLargeError(ImportServiceError):
    code = "upload_too_large"


class InvalidWorkspaceError(ImportServiceError):
    code = "invalid_workspace"


class SourceNotFoundError(ImportServiceError):
    code = "source_not_found"


class ChannelNotFoundError(ImportServiceError):
    """Requested channel name does not exist on this source (Phase 2A)."""

    code = "channel_not_found"


class ChannelNotAnalogError(ImportServiceError):
    """Requested channel exists but is digital, not analog (Phase 2A).

    The waveform endpoint only serves analog channels in Phase 2A -- see
    docs/project-memory/MIGRATION_PLAN.md's Phase 2 design, "No digital
    waveform implementation" (deliberately deferred, not an oversight).
    """

    code = "channel_not_analog"


class InvalidTimeRangeError(ImportServiceError):
    """start_time/end_time are malformed (e.g. start_time > end_time)."""

    code = "invalid_time_range"
