"""API response DTOs for CSV/Excel preparation sources (Slice 1, DEC-072).

Deliberately excludes the raw file bytes, mirroring
`app.schemas.source`'s own "never return the heavy payload" convention.
`file_format` is uppercased at the domain layer already (`"CSV"`),
matching `SourceSummaryOut.provider_type`'s existing `"COMTRADE"`
convention exactly -- the Recording Events table's File Format column
reads both through the same display path on the frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.preparation_session import PreparationSessionSummary


class PreparationSessionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    workspace_id: str
    file_format: str
    original_filename: str
    file_size_bytes: int
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, summary: PreparationSessionSummary) -> "PreparationSessionSummaryOut":
        return cls(
            source_id=summary.source_id,
            workspace_id=summary.workspace_id,
            file_format=summary.source_format,
            original_filename=summary.original_filename,
            file_size_bytes=summary.original_byte_size,
            status=summary.status,
            created_at=summary.created_at,
        )
