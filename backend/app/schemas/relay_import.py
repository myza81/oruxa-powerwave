"""Relay Import response schema: safe metadata, extraction counts, the relay
identification verdict (Slice 5) and an interpretation summary (Slice 6).

No document content, no evidence text and no engineering values: the
interpretation summary is counts and fixed phrases only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReviewSourceOut(BaseModel):
    """Where one interpreted value came from (never a file path)."""

    code: str | None = None
    name: str | None = None
    raw_value: str | None = None
    page: int | None = None
    line: int | None = None
    source_text: str | None = None


class ReviewItemOut(BaseModel):
    key: str
    label: str
    full_label: str
    #: Formatted engineering value with unit; ``None`` when unresolved.
    value_text: str | None = None
    status: Literal["mapped", "inferred", "unresolved"]
    notes: list[str] = []
    raw_value: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    sources: list[ReviewSourceOut] = []


class ReviewGroupOut(BaseModel):
    id: str
    kind: Literal["relay", "transformers", "line", "zone", "compensation"]
    title: str
    state_label: str | None = None
    state_status: Literal["mapped", "inferred", "unresolved"] | None = None
    items: list[ReviewItemOut] = []


class ReviewRawSettingOut(BaseModel):
    code: str | None = None
    name: str | None = None
    raw_value: str | None = None
    page: int | None = None
    line: int | None = None
    reason: str = ""


class ReviewEngineReasonOut(BaseModel):
    zone_ids: list[str] = []
    message: str


class ReviewEngineOut(BaseModel):
    status: Literal["ready", "not_ready"]
    reasons: list[ReviewEngineReasonOut] = []
    warnings: list[str] = []


class ExtractionReviewOut(BaseModel):
    """Slice 7: read-only Extraction Review. Request-scoped and ephemeral: it
    rides in the upload response and is kept only in the browser tab's memory.
    Nothing here is applied to the Distance Protection form."""

    manufacturer: str | None = None
    relay_family: str | None = None
    model: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    zone_count: int
    mapped_count: int
    to_confirm_count: int
    unresolved_count: int
    not_interpreted_count: int
    #: Interpretation quality, separate from engine compatibility.
    interpretation: Literal["reviewable", "incomplete"]
    engine: ReviewEngineOut
    notes: list[str] = []
    groups: list[ReviewGroupOut] = []
    not_interpreted: list[ReviewRawSettingOut] = []
    out_of_scope: list[ReviewRawSettingOut] = []


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
    #: Slice 7. Present only for an ``interpreted`` relay; ``None`` otherwise.
    review: ExtractionReviewOut | None = None
