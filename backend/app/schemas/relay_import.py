"""Relay Import response schema: safe metadata, extraction counts, the relay
identification verdict (Slice 5) and an interpretation summary (Slice 6).

No document content, no evidence text and no engineering values: the
interpretation summary is counts and fixed phrases only.
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
    #: Slice 5. ``None`` when no text could be read (nothing to identify).
    #: Identified != interpreted: no setting has been read as an engineering value.
    identification_status: Literal["identified", "ambiguous", "unknown"] | None = None
    manufacturer: str | None = None
    relay_family: str | None = None
    model: str | None = None
    profile_id: str | None = None
    #: Categorical, not a probability: high | medium | low | none.
    confidence: Literal["high", "medium", "low", "none"] | None = None
    identification_warnings: list[str] = []
    #: Slice 6. ``None`` when no text could be read. ``not_supported`` for every
    #: relay without an interpretation profile. Interpreted != applied: nothing
    #: is written to the Distance Protection form.
    interpretation_status: Literal["interpreted", "incomplete", "not_supported", "failed"] | None = None
    #: Version of the interpretation profile that ran (an explicit, per-relay-template id).
    profile_version: str | None = None
    mapped_setting_count: int = 0
    #: Rest on profile knowledge the sheet does not state; confirmation recommended.
    inferred_setting_count: int = 0
    unresolved_setting_count: int = 0
    #: Distance-related settings retained raw, not interpreted by this profile version.
    not_interpreted_setting_count: int = 0
    zone_count: int = 0
    interpretation_warnings: list[str] = []
