"""BEN-specific parse errors.

All derive from ``ProviderLoadError`` so ``ProviderManager`` and any
future ingestion caller treat a BEN failure exactly like a COMTRADE one.
Each error names the byte offset involved where one applies, so a
rejected file can be investigated without re-running the parser.
"""

from __future__ import annotations

from app.providers.base import ProviderLoadError


class BenFormatError(ProviderLoadError):
    """The file could not be decoded as a supported BEN record."""

    def __init__(self, message: str, *, offset: int | None = None) -> None:
        self.offset = offset
        if offset is not None:
            message = f"{message} (at byte offset {offset:#x})"
        super().__init__(message)


class BenNotRecognizedError(BenFormatError):
    """The file does not carry the BEN family signature at all."""


class BenUnsupportedVariantError(BenFormatError):
    """A BEN file whose layout or record class has not been validated.

    Raised instead of guessing: an unvalidated layout is never
    interpreted with the SubBen rules.
    """


class BenTruncatedError(BenFormatError):
    """A declared structure extends beyond the end of the file."""


class BenStructureError(BenFormatError):
    """The file's own declarations contradict each other."""
