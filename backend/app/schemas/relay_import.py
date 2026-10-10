"""Relay Import Slice 3 response schema: safe, non-engineering metadata only."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RelayImportUploadOut(BaseModel):
    filename: str
    source_format: str
    size_bytes: int
    status: Literal["accepted"]
