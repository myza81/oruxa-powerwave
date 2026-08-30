"""Preparation Session domain model (CSV/Excel ingestion Slice 1, DEC-072).

A `PreparationSession` represents one uploaded CSV/Excel file that has
been accepted as *raw, immutable, temporary* preparation input -- it is
deliberately NOT a `DisturbanceRecord` and never becomes one in this
slice. See docs/project-memory/CSV_EXCEL_INGESTION_ARCHITECTURE.md and
docs/project-memory/DECISIONS.md's DEC-072 for the approved architecture
this implements:

    External CSV/Excel
            |
    Temporary immutable raw source   <- PreparationSession (this module)
            |
    Preparation Session
            |
    Working Dataset                  <- NOT built yet (Slice 4)
            |
    Readiness Validation             <- NOT built yet (Slice 9)
            |
    Canonical DisturbanceRecord      <- NOT produced by this slice at all
            |
    Existing Powerwave behavior unchanged

Slice 1 scope only (deliberately minimal -- see this module's own
docstring history in git for the full guardrail list): identity,
original filename, format, byte size, the raw bytes themselves, status,
and creation time. Does NOT model header mappings, column mappings,
edits/overlays, time-axis interpretation, or readiness findings -- those
are later slices' own domain concepts and must not be speculatively
added here.

Zero framework dependencies, matching every other `app.domain` module's
own layering contract (see `app.domain.source`'s own module docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Slice 1 supports CSV only. Excel is Slice 2 -- this constant is a
#: closed set deliberately, unlike the time-axis format list (which
#: DEC-072 point 6 keeps permanently open): a preparation *source
#: format* is a small, enumerable, provider-registration-style concept,
#: not an open-ended interpretation question.
FORMAT_CSV = "CSV"
KNOWN_PREPARATION_FORMATS = (FORMAT_CSV,)

#: The only status a Slice 1 preparation session can ever have. Later
#: slices add more (e.g. once a Readiness Validator exists) -- this is
#: not meant to be a complete lifecycle enum yet.
STATUS_NEEDS_PREPARATION = "needs_preparation"
KNOWN_PREPARATION_STATUSES = (STATUS_NEEDS_PREPARATION,)


def preparation_format_valid(source_format: str) -> bool:
    return source_format in KNOWN_PREPARATION_FORMATS


@dataclass(slots=True)
class PreparationSessionSummary:
    """Everything the preparation-sources list/detail API needs.

    Deliberately excludes the raw file bytes -- mirrors
    `app.domain.source.SourceMetadata`'s own "metadata never carries the
    heavy payload" convention.
    """

    source_id: str
    workspace_id: str
    original_filename: str
    source_format: str
    original_byte_size: int
    status: str
    created_at: datetime


@dataclass(slots=True)
class PreparationSession:
    """Everything the in-memory registry owns for one CSV preparation
    source: the lightweight summary plus the immutable raw bytes.

    Mirrors `app.domain.source.ActiveSource`'s summary+payload
    composition exactly, at Slice 1's much smaller scale (raw bytes
    only, not a parsed record). `raw_bytes` is held in memory only, for
    the lifetime of the active preparation session -- never written to
    disk, never mutated after creation, and released the moment its
    owning source/workspace is removed (see
    `app.services.preparation_session_registry.PreparationSessionRegistry`).
    This satisfies DEC-072 point 1 (temporary preparation retention is
    permitted; durable retention is not) without touching
    `StorageBackend` at all -- see that registry's own module docstring
    for why.
    """

    summary: PreparationSessionSummary
    raw_bytes: bytes
