"""Relay Import response schema: safe metadata and extraction counts only.

No document content, no manufacturer/model, no engineering values (Slice 3/4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RelayImportUploadOut(BaseModel):
    filename: str
    source_format: str
    size_bytes: int
    status: Literal["accepted"]
    #: text_extracted | no_extractable_text | encrypted (unreadable is a 400)
    extraction_status: Literal["text_extracted", "no_extractable_text", "encrypted"]
    page_count: int
    pages_with_text: int
    raw_entry_count: int
    section_count: int
    extraction_warnings: list[str]
