"""Preparation Session domain model (CSV/Excel ingestion Slices 1-4, DEC-072).

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
    Working Dataset                  <- WorkingOverlay (Slice 4)
            |
    Readiness Validation             <- NOT built yet (Slice 9)
            |
    Canonical DisturbanceRecord      <- NOT produced by this slice at all
            |
    Existing Powerwave behavior unchanged

Slice 1 scope (deliberately minimal -- see this module's own docstring
history in git for the full guardrail list): identity, original
filename, format, byte size, the raw bytes themselves, status, and
creation time.

Slice 2 adds Excel (`.xlsx` only -- see `KNOWN_PREPARATION_FORMATS`'s
own comment) as a second supported format, reusing this SAME
`PreparationSession`/`PreparationSessionSummary` shape rather than a
parallel `ExcelPreparationSession` type (per DEC-072's own architecture:
one preparation-session concept, not one per format) -- plus a small,
read-only `WorksheetInfo` descriptor list and a `selected_worksheet_index`
field, both optional/empty for CSV (which has no worksheet concept at
all -- see `WorksheetInfo`'s own docstring).

Slice 4 adds `PreparationSession.working_overlay` (see
`app.domain.working_overlay.WorkingOverlay`) -- a sparse, edit-count-
proportional overlay of cell edits/clears, row exclusions, and column
ignores, applied to a raw page only at preview-read time
(`app.services.preparation_preview_service`), never merged back into
`raw_bytes` and never a second full copy of the dataset.

None of these slices model header mappings, column-role mappings,
time-axis interpretation, or readiness findings -- those are later
slices' own domain concepts and must not be speculatively added here.

Zero framework dependencies, matching every other `app.domain` module's
own layering contract (see `app.domain.source`'s own module docstring).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.working_overlay import WorkingOverlay

#: A preparation *source format* is a small, enumerable,
#: provider-registration-style concept, not an open-ended interpretation
#: question -- unlike the time-axis format list, which DEC-072 point 6
#: deliberately keeps permanently open. Slice 2 adds Excel, `.xlsx` only:
#: legacy `.xls` would need a separate, unmaintained dependency (`xlrd`
#: 2.x dropped `.xlsx` support entirely and only reads legacy `.xls`) not
#: currently justified -- see CSV_EXCEL_INGESTION_ARCHITECTURE.md.
FORMAT_CSV = "CSV"
FORMAT_EXCEL = "Excel"
KNOWN_PREPARATION_FORMATS = (FORMAT_CSV, FORMAT_EXCEL)

#: The only status a Slice 1 preparation session can ever have. Later
#: slices add more (e.g. once a Readiness Validator exists) -- this is
#: not meant to be a complete lifecycle enum yet.
STATUS_NEEDS_PREPARATION = "needs_preparation"
KNOWN_PREPARATION_STATUSES = (STATUS_NEEDS_PREPARATION,)


def preparation_format_valid(source_format: str) -> bool:
    return source_format in KNOWN_PREPARATION_FORMATS


@dataclass(slots=True)
class WorksheetInfo:
    """One worksheet's own discovered structural identity (Slice 2).

    Read-only, structural metadata ONLY -- never cell values, never a
    header row, never a data region. `index` (0-based, matching workbook
    sheet order) is the stable internal identifier, never `name` alone:
    Excel enforces unique names within one workbook today, but nothing
    in this module relies on that -- `index` is what a future rename-
    tolerant lookup would use (task's own "duplicate sheet names" /
    "prefer an internal descriptor that can preserve sheet_index,
    sheet_name" guidance). `row_count`/`column_count` are best-effort:
    `None` whenever the workbook's own XML doesn't cheaply expose them
    (see `preparation_import_service._discover_worksheets()`'s own
    docstring) -- never worth a full-sheet scan just to populate them.
    """

    index: int
    name: str
    visible: bool
    row_count: int | None = None
    column_count: int | None = None


@dataclass(slots=True)
class PreparationSessionSummary:
    """Everything the preparation-sources list/detail API needs.

    Deliberately excludes the raw file bytes -- mirrors
    `app.domain.source.SourceMetadata`'s own "metadata never carries the
    heavy payload" convention.

    Slice 2: `worksheets`/`selected_worksheet_index` are additive,
    defaulted fields -- empty/`None` for CSV (which has no worksheet
    concept at all; never populated with fake single-sheet metadata just
    to keep a shape uniform, per this slice's own explicit guardrail).
    For Excel, `worksheets` is populated once at upload time (never
    re-discovered later) and `selected_worksheet_index` starts at `0`
    when the workbook has exactly one worksheet (deterministic
    convenience auto-selection -- see `preparation_import_service`'s own
    docstring for the exact rule) or `None` otherwise, until an explicit
    `PATCH .../preparation-sources/{id}` selection is made.
    """

    source_id: str
    workspace_id: str
    original_filename: str
    source_format: str
    original_byte_size: int
    status: str
    created_at: datetime
    worksheets: tuple[WorksheetInfo, ...] = ()
    selected_worksheet_index: int | None = None


@dataclass(slots=True)
class PreparationSession:
    """Everything the in-memory registry owns for one CSV or Excel
    preparation source: the lightweight summary, the immutable raw
    bytes, and (Slice 4) the working overlay layered over them.

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

    Slice 3: `cached_row_count`/`cached_column_count` are a lazy,
    mutated-in-place cache -- CSV has no separate index structure
    (`app.services.preparation_preview_service`'s own docstring for why),
    so its exact row/column totals can only be known by scanning the
    full in-memory text once. The first preview request pays that cost
    and caches the result here; every subsequent request (any page)
    reuses it rather than re-deriving it. Never used for Excel (whose
    row/column counts already live on each `WorksheetInfo`, discovered
    once at upload time in Slice 2) -- always `None` for that format.

    Slice 4: `working_overlay` is created empty alongside the session
    and mutated in place by `app.services.working_overlay_service` --
    never replaced with a new object, so anything already holding a
    reference to it always sees the current state. Released for free
    when this `PreparationSession` itself is (source/workspace DELETE,
    or process restart) -- no separate cleanup step needed.
    """

    summary: PreparationSessionSummary
    raw_bytes: bytes
    cached_row_count: int | None = None
    cached_column_count: int | None = None
    working_overlay: WorkingOverlay = field(default_factory=WorkingOverlay)
