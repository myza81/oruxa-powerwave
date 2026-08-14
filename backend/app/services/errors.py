"""Structured import errors.

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
