"""Working Dataset overlay domain model (CSV/Excel ingestion Slices 4-5, DEC-072).

The first slice where the user may modify what the preparation preview
*shows* -- never the raw source itself:

    Immutable raw source (PreparationSession.raw_bytes, untouched)
            +
    Sparse working overlay (this module -- proportional to edit count,
    never a second copy of the dataset)
            =
    Working view (app.services.preparation_preview_service applies this
    overlay to a raw page at read time, never persists a merged copy)

This module owns ONLY the overlay's own pure data structures and
mutation logic -- never raw-source I/O (no CSV/Excel reading here at
all), never HTTP-mappable errors (that's
app.services.working_overlay_service's job), and never any semantic
interpretation of a value (no type coercion, no time-axis meaning -- a
working cell value is always a plain string, or `None` for an explicit
clear; see `CellOverride`'s own docstring for why).

Coordinate identity (task's own explicit "stable identity" requirement):
a `(worksheet_index, row_number, column_index)` tuple, where
`worksheet_index` is `None` for CSV (which has no worksheet dimension at
all) and the Slice 2 0-based worksheet index for Excel -- the SAME
tuple shape for both formats, so the rest of this module needs no
per-format branching. `row_number` is 1-based (matches
`app.services.preparation_preview_service.PreviewRow.row_number`);
`column_index` is 0-based (matches the same module's own column
positions). Row exclusion and column roles use the analogous
`(worksheet_index, row_number)` / `(worksheet_index, column_index)`
shapes. Header row and data region are scoped one level coarser still --
just `worksheet_index` alone (`None` for CSV, a real index for Excel) --
since both are source/worksheet-wide settings, not per-row/per-column
data. None of these ever renumber -- excluding row 2 of 4 never turns
row 3 into row 2 (task's own explicit "provenance" requirement).

Slice 5 adds structure/semantic mapping state to this SAME overlay
(rather than a second, separate model) so it participates in the exact
same bounded operation history / undo-redo / revision-counter mechanism
Slice 4 already built, per that slice's own explicit "ideally the same
history model" preference:

- `header_row: dict[worksheet_index_or_None, int]` -- which raw row (if
  any) supplies working column labels for that worksheet/source. Absent
  key means "no header selected," never a fabricated `0`/`1`.
- `data_region: dict[worksheet_index_or_None, DataRegion]` -- the
  inclusive raw row range currently treated as the active dataset.
  Absent key means "the entire source is active" (Slice 4's own
  existing default, preserved unless the user narrows it) -- this
  module never invents a default range value to store.
- `column_roles: dict[ColumnKey, str]` -- one of `KNOWN_COLUMN_ROLES`
  per column that has been explicitly classified; an absent entry means
  `ROLE_NOT_ASSIGNED` (task's own explicit "do NOT automatically
  classify columns" -- absence IS the default, never written).

**UAT fix (2026-09-04, DEC-072): the column-role model is simplified to
exactly THREE roles.** Owner-approved: Powerwave only ever needs to
know "which column(s) define the time axis" and "which column(s) are
waveform channels" -- everything else is `not_assigned`, a single
neutral default, never classified further. The earlier five-role model
(`unknown`/`waveform`/`time_axis`/`metadata`/`quality_status`/`ignore`)
is retired -- `metadata`/`quality_status` asked the engineer to make a
distinction Powerwave never actually used, and `unknown`/`ignore` were
already two names for functionally the same "not analysed by
Powerwave" state (the ONLY difference being whether Slice 12's cleaned
export kept the column or physically omitted it -- see that module's
own docstring for why Slice 12 now omits `not_assigned` uniformly).
Slice 4's own separate `ignored_columns: set[ColumnKey]` field remains
retired (unchanged from before this fix) -- `not_assigned` (the sparse
default) is the single authoritative "not analysed, not exported"
representation; there is no longer a separate explicit "ignore" action
at all, since it is now indistinguishable from simply never assigning
a role. `app.services.working_overlay_service.set_column_ignored()`
and its own `PUT .../working/columns/{column_index}` boolean-ignore API
route are retired for the same reason (a `PreparationSession` is
temporary, in-memory, owner-approved-clean-migration state -- see task
section T -- so no compatibility alias was preserved for a concept that
no longer exists).

A later owner-UAT refinement (post-Slice-6) adds an END-MODE to
`DataRegion` (`END_MODE_SOURCE_END`/`END_MODE_SPECIFIC`) so a region's
own upper bound can float with the source/worksheet's own end rather
than always requiring a manually-found numeric row -- see `DataRegion`'s
own docstring. This stays a single, dataset-wide boundary per
worksheet/source exactly as before; there is still no per-column end.

Slice 7 (DEC-072, `docs/project-memory/CSV_EXCEL_TIME_INTERPRETATION.md`)
adds ONE more sparse, worksheet-scoped dict, `time_axis: dict[
worksheet_index_or_None, app.domain.time_axis.TimeAxisConfiguration]`
-- the exact same pattern as `header_row`/`data_region`, participating
in the exact same undo/redo history and revision counter with zero new
mechanism. This module stores `TimeAxisConfiguration` opaquely (as a
frozen value object it merely records/restores, exactly like
`DataRegion`) and never itself interprets what a configuration means --
see `app.domain.time_axis`'s own module docstring for the full
framework design.

Undo/redo (task's own "if it fits naturally... do not fake by
snapshotting the entire dataset"): implemented here as a bounded
operation history. Every recorded `WorkingOperation` carries only the
`before`/`after` state of the ONE thing it changed -- a single
`CellOverride` (or `None`), a single `bool`, a single role string (or
`None`), a single header row number (or `None`), a single `DataRegion`
(or `None`), or (for `reset_all` only) a snapshot of the overlay's own
five collections, whose size is proportional to the number of
edits/mappings made so far, never to the raw dataset's row/column
count. This is why undo/redo stays compatible with "overlay scales with
edits, not with dataset size" even though `reset_all` is technically a
whole-overlay operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.domain.channel_classification import ENGINEERING_QUANTITY_UNDEFINED

#: Measured Unit enhancement (DEC-080): "blank" is this field's own
#: sparse-default sentinel, distinct from Engineering Quantity's
#: "Undefined" -- see `column_measured_units`'s own docstring below.
MEASURED_UNIT_BLANK = ""

if TYPE_CHECKING:
    from app.domain.time_axis import TimeAxisConfiguration

OVERRIDE_KIND_EDIT = "edit"
OVERRIDE_KIND_CLEAR = "clear"

#: A generous sanity bound against a pathological/accidental paste --
#: never an engineering-content validation (task's own "do not infer
#: engineering types" guardrail). Enforced by
#: app.services.working_overlay_service, not by this module's own
#: mutation functions (which stay pure and never raise).
MAX_CELL_VALUE_LENGTH = 10_000

#: A bounded history, per task's own "a bounded history is acceptable"
#: allowance -- oldest entries are dropped once exceeded, never an
#: unbounded growth tied to session lifetime.
MAX_OPERATION_HISTORY = 200

# (worksheet_index_or_None, row_number, column_index)
CellKey = tuple
# (worksheet_index_or_None, row_number)
RowKey = tuple
# (worksheet_index_or_None, column_index)
ColumnKey = tuple
# worksheet_index_or_None -- header_row/data_region are scoped this
# coarsely (one entry per worksheet/source, not per row or column).
WorksheetScope = object  # documents intent only; always an int | None in practice

#: Slice 5 (DEC-072) column semantic-role model, simplified by the
#: 2026-09-04 UAT fix to exactly three roles -- Powerwave only needs to
#: know "which column(s) define the time axis" and "which column(s) are
#: waveform channels"; everything else is `ROLE_NOT_ASSIGNED`.
#: `ROLE_NOT_ASSIGNED` is the implicit default for any column with no
#: `column_roles` entry -- never written explicitly by this module's own
#: functions (task's own "do NOT automatically classify columns"
#: guardrail: absence IS not-assigned, not a stored value chosen by
#: code). The earlier `unknown`/`metadata`/`quality_status`/`ignore`
#: roles are retired (see this module's own docstring above for why).
ROLE_NOT_ASSIGNED = "not_assigned"
ROLE_WAVEFORM = "waveform"
ROLE_TIME_AXIS = "time_axis"
KNOWN_COLUMN_ROLES = (
    ROLE_NOT_ASSIGNED,
    ROLE_TIME_AXIS,
    ROLE_WAVEFORM,
)

#: Data-region end-mode refinement (owner UAT, post-Slice-6): the owner
#: found manually looking up the true last data row of a large source
#: "unnecessarily burdensome" -- `END_MODE_SOURCE_END` lets a region's
#: own upper bound FLOAT with the source/worksheet's own end rather than
#: requiring a guessed numeric value. `END_MODE_SPECIFIC` is the
#: original Slice 5 behavior (an explicit numeric `end_row`) --
#: `DataRegion.end_row` is `None` for `END_MODE_SOURCE_END` (there is no
#: stored numeric end to speak of; never a resolved/guessed value cached
#: here) and a real row number for `END_MODE_SPECIFIC`. This is still
#: ONE dataset-wide boundary per worksheet/source -- never a per-column
#: end (task's own explicit "do NOT implement per-column data-region
#: ends" guardrail; every active column shares the exact same row
#: coordinates).
END_MODE_SOURCE_END = "source_end"
END_MODE_SPECIFIC = "specific"
KNOWN_END_MODES = (END_MODE_SOURCE_END, END_MODE_SPECIFIC)


def cell_key(worksheet_index: int | None, row_number: int, column_index: int) -> CellKey:
    return (worksheet_index, row_number, column_index)


def row_key(worksheet_index: int | None, row_number: int) -> RowKey:
    return (worksheet_index, row_number)


def column_key(worksheet_index: int | None, column_index: int) -> ColumnKey:
    return (worksheet_index, column_index)


@dataclass(slots=True, frozen=True)
class CellOverride:
    """One cell's working override.

    `value` is ALWAYS a plain string when `kind == OVERRIDE_KIND_EDIT` --
    a deliberate simplification (task's own "do not automatically infer
    engineering types... a string-preserving working overlay is
    acceptable"): whatever native type the RAW cell had (Excel numbers/
    booleans/dates, CSV's own always-string cells), an EDITED working
    value is always the string the user typed, verbatim. `value` is
    always `None` when `kind == OVERRIDE_KIND_CLEAR` -- a clear is a
    distinct, explicit "this cell has no working value" action, never
    conflated with an edit to an empty string (task's own "Clear cell...
    different from setting \"\"" requirement) even though both currently
    render identically (blank) in the preview.
    """

    kind: str  # OVERRIDE_KIND_EDIT | OVERRIDE_KIND_CLEAR
    value: str | None


@dataclass(slots=True, frozen=True)
class DataRegion:
    """The inclusive raw row range currently treated as this worksheet/
    source's active working dataset (Slice 5; end-mode added by a later
    owner UAT refinement). `start_row` is an original raw row number
    (1-based) -- never a re-derived position, and setting it never
    physically removes/renumbers rows outside the range (task's own
    "reversible... rows outside remain preserved" requirement).

    `end_mode` is one of `KNOWN_END_MODES`:
    - `END_MODE_SOURCE_END`: the region's own upper bound FLOATS with
      the source/worksheet's own end -- `end_row` is `None` here; there
      is no stored numeric value, deliberately never a resolved/guessed
      one either (task's own explicit "Rows 2-end is not the same as
      storing a guessed numeric last-data row" distinction). The
      ACTUAL resolved boundary (used only to compute each row's own
      `in_active_region` flag) is derived at preview-read time from
      whatever this source/worksheet's own already-known row total is
      (exact for CSV, best-effort or unknown for Excel) -- see
      `app.services.preparation_preview_service._apply_structure_mapping`.
    - `END_MODE_SPECIFIC`: the original Slice 5 behavior -- `end_row` is
      a real, explicit raw row number the user chose after inspecting
      the tail of the source themselves.
    """

    start_row: int
    end_mode: str
    end_row: int | None


@dataclass(slots=True)
class WorkingOperation:
    """One undoable/redoable mutation.

    `kind` is `"cell"` / `"row"` / `"column_role"` / `"header"` /
    `"data_region"` / `"time_axis"` / `"reset_all"`. `key` is the
    affected `CellKey`/`RowKey`/`ColumnKey`, or the bare
    `worksheet_index` (an `int | None`) for `"header"`/`"data_region"`/
    `"time_axis"`, or `None` for `reset_all`. `before`/`after` hold
    whatever this module's own
    `_apply_state()` needs to reverse/reapply the operation -- see this
    module's own docstring for why this stays O(edit count), never
    O(dataset size).
    """

    kind: str
    key: CellKey | RowKey | ColumnKey | int | None
    before: object
    after: object


@dataclass(slots=True)
class WorkingOverlay:
    """Everything Slices 4-5 add to one `PreparationSession`.

    Lives as a plain attribute on `PreparationSession` -- no new
    registry, no new lifecycle: created with the session, mutated in
    place by this module's own functions, and released the instant its
    owning `PreparationSession` is (source DELETE, workspace DELETE, or
    process restart) -- see `app.services.preparation_session_registry`'s
    own docstring, unaffected by this addition.
    """

    cell_overrides: dict[CellKey, CellOverride] = field(default_factory=dict)
    excluded_rows: set[RowKey] = field(default_factory=set)
    column_roles: dict[ColumnKey, str] = field(default_factory=dict)
    # Engineering Quantity enhancement (DEC-077): sparse, same "absence is
    # the default (Undefined)" convention as column_roles above -- never
    # cleared merely because a column's role later moves away from
    # ROLE_WAVEFORM (see set_column_role()'s own docstring for why: the
    # quantity is simply IGNORED, not read, by every downstream consumer
    # for a non-Waveform column, so a stale-but-unused stored value is
    # harmless and preserves the user's prior selection if they switch
    # back). Keyed by the SAME ColumnKey column_roles uses.
    column_engineering_quantities: dict[ColumnKey, str] = field(default_factory=dict)
    # Measured Unit enhancement (DEC-080): a SEPARATE sparse dict from
    # column_engineering_quantities above -- Quantity and Unit are
    # independent concepts (task section C), so they get independent
    # storage rather than one combined value. Same "absence is the
    # default (blank)" convention, same "not cleared merely because role
    # later moves away from ROLE_WAVEFORM" policy (task section K mirrors
    # Engineering Quantity's own policy exactly -- see set_column_role()'s
    # docstring). Keyed by the SAME ColumnKey the other two use.
    column_measured_units: dict[ColumnKey, str] = field(default_factory=dict)
    header_row: dict[object, int] = field(default_factory=dict)
    data_region: dict[object, DataRegion] = field(default_factory=dict)
    time_axis: dict[object, "TimeAxisConfiguration"] = field(default_factory=dict)
    revision: int = 0
    history: list[WorkingOperation] = field(default_factory=list)
    redo_stack: list[WorkingOperation] = field(default_factory=list)


def _record(overlay: WorkingOverlay, kind: str, key, before, after) -> None:
    overlay.history.append(WorkingOperation(kind=kind, key=key, before=before, after=after))
    if len(overlay.history) > MAX_OPERATION_HISTORY:
        overlay.history.pop(0)
    # A fresh operation always invalidates whatever was previously
    # undone -- the standard undo/redo convention (redoing after a new,
    # different edit would silently resurrect an abandoned branch of
    # history otherwise).
    overlay.redo_stack.clear()
    overlay.revision += 1


def set_cell_value(overlay: WorkingOverlay, key: CellKey, value: str | None) -> None:
    """Set (or overwrite) one cell's working value. `value=None` means
    an explicit CLEAR; any string (including `""`) means an EDIT to
    that exact string -- see `CellOverride`'s own docstring for why
    these stay distinct kinds despite rendering identically today.
    """
    before = overlay.cell_overrides.get(key)
    after = (
        CellOverride(kind=OVERRIDE_KIND_CLEAR, value=None)
        if value is None
        else CellOverride(kind=OVERRIDE_KIND_EDIT, value=value)
    )
    overlay.cell_overrides[key] = after
    _record(overlay, "cell", key, before, after)


def reset_cell(overlay: WorkingOverlay, key: CellKey) -> bool:
    """Remove a cell's override entirely -- the working value reverts
    to the raw value exactly (no residual state). Returns `False`
    (a safe no-op, no history entry recorded) if the cell had no
    override to begin with."""
    if key not in overlay.cell_overrides:
        return False
    before = overlay.cell_overrides.pop(key)
    _record(overlay, "cell", key, before, None)
    return True


def set_row_excluded(overlay: WorkingOverlay, key: RowKey, excluded: bool) -> None:
    before = key in overlay.excluded_rows
    if excluded:
        overlay.excluded_rows.add(key)
    else:
        overlay.excluded_rows.discard(key)
    _record(overlay, "row", key, before, excluded)


def set_column_role(overlay: WorkingOverlay, key: ColumnKey, role: str) -> None:
    """Set one column's semantic role (Slice 5). `role == ROLE_NOT_ASSIGNED`
    removes any stored entry rather than writing the default explicitly
    -- `column_roles` stays sparse (only classified columns appear),
    matching this module's own "absence is the default" convention
    used by `cell_overrides`/`excluded_rows` already. Role VALIDITY
    (must be one of `KNOWN_COLUMN_ROLES`) is enforced by
    `app.services.working_overlay_service`, not here -- this function
    stays pure and never raises, matching every other mutation function
    in this module.
    """
    before = overlay.column_roles.get(key)
    if role == ROLE_NOT_ASSIGNED:
        overlay.column_roles.pop(key, None)
        after = None
    else:
        overlay.column_roles[key] = role
        after = role
    _record(overlay, "column_role", key, before, after)


def reset_column_role(overlay: WorkingOverlay, key: ColumnKey) -> bool:
    """Equivalent to `set_column_role(overlay, key, ROLE_NOT_ASSIGNED)`
    but matches `reset_cell`'s own "return whether anything actually
    changed" signature, and records a no-op-free history entry only
    when there was something to reset."""
    if key not in overlay.column_roles:
        return False
    before = overlay.column_roles.pop(key)
    _record(overlay, "column_role", key, before, None)
    return True


def set_column_engineering_quantity(overlay: WorkingOverlay, key: ColumnKey, engineering_quantity: str) -> None:
    """Set one column's Engineering Quantity (DEC-077). `engineering_
    quantity == ENGINEERING_QUANTITY_UNDEFINED` removes any stored entry
    rather than writing the default explicitly -- `column_engineering_
    quantities` stays sparse, matching `column_roles`'s own "absence is
    the default" convention. Value validity (must be one of
    `app.domain.channel_classification.KNOWN_ENGINEERING_QUANTITIES`) is
    enforced by `app.services.working_overlay_service`, not here -- this
    function stays pure and never raises, matching every other mutation
    function in this module."""
    before = overlay.column_engineering_quantities.get(key)
    if engineering_quantity == ENGINEERING_QUANTITY_UNDEFINED:
        overlay.column_engineering_quantities.pop(key, None)
        after = None
    else:
        overlay.column_engineering_quantities[key] = engineering_quantity
        after = engineering_quantity
    _record(overlay, "column_engineering_quantity", key, before, after)


def reset_column_engineering_quantity(overlay: WorkingOverlay, key: ColumnKey) -> bool:
    """Equivalent to `set_column_engineering_quantity(overlay, key,
    ENGINEERING_QUANTITY_UNDEFINED)` but matches `reset_column_role()`'s
    own "return whether anything actually changed" signature."""
    if key not in overlay.column_engineering_quantities:
        return False
    before = overlay.column_engineering_quantities.pop(key)
    _record(overlay, "column_engineering_quantity", key, before, None)
    return True


def set_column_measured_unit(overlay: WorkingOverlay, key: ColumnKey, measured_unit: str) -> None:
    """Set one column's Measured Unit (DEC-080). `measured_unit ==
    MEASURED_UNIT_BLANK` (`""`) removes any stored entry rather than
    writing the default explicitly -- `column_measured_units` stays
    sparse, matching `column_engineering_quantities`'s own "absence is
    the default" convention. Value validity (must be a member of
    `app.domain.channel_classification.MEASURED_UNIT_OPTIONS` for the
    column's CURRENT engineering quantity) is enforced by
    `app.services.working_overlay_service`, not here -- this function
    stays pure and never raises, matching every other mutation function
    in this module."""
    before = overlay.column_measured_units.get(key)
    if measured_unit == MEASURED_UNIT_BLANK:
        overlay.column_measured_units.pop(key, None)
        after = None
    else:
        overlay.column_measured_units[key] = measured_unit
        after = measured_unit
    _record(overlay, "column_measured_unit", key, before, after)


def reset_column_measured_unit(overlay: WorkingOverlay, key: ColumnKey) -> bool:
    """Equivalent to `set_column_measured_unit(overlay, key,
    MEASURED_UNIT_BLANK)` but matches `reset_column_engineering_quantity()`'s
    own "return whether anything actually changed" signature."""
    if key not in overlay.column_measured_units:
        return False
    before = overlay.column_measured_units.pop(key)
    _record(overlay, "column_measured_unit", key, before, None)
    return True


def set_header_row(overlay: WorkingOverlay, worksheet_index: int | None, row_number: int) -> None:
    """Select which raw row supplies working column labels for this
    worksheet/source (Slice 5). Does not touch `column_roles` or any
    other state -- header selection and column classification are
    deliberately independent (task's own "editing header text must not
    automatically change role" principle, extended to header
    SELECTION itself)."""
    before = overlay.header_row.get(worksheet_index)
    overlay.header_row[worksheet_index] = row_number
    _record(overlay, "header", worksheet_index, before, row_number)


def clear_header_row(overlay: WorkingOverlay, worksheet_index: int | None) -> bool:
    """Remove the header-row selection for this worksheet/source --
    working column labels revert to the neutral spreadsheet-letter
    fallback. Column role assignments are left completely untouched
    (task's own explicit "do not silently wipe role mappings" default;
    no coupling exists between the two in this implementation, so there
    is nothing to reconcile)."""
    if worksheet_index not in overlay.header_row:
        return False
    before = overlay.header_row.pop(worksheet_index)
    _record(overlay, "header", worksheet_index, before, None)
    return True


def set_data_region(
    overlay: WorkingOverlay,
    worksheet_index: int | None,
    start_row: int,
    end_row: int | None,
    end_mode: str = END_MODE_SPECIFIC,
) -> None:
    """Narrow the active working dataset for this worksheet/source
    (Slice 5; `end_mode` added by a later owner UAT refinement).
    `end_mode` defaults to `END_MODE_SPECIFIC` so every pre-refinement
    caller (positional `(overlay, worksheet_index, start_row, end_row)`)
    keeps working completely unchanged -- this default is a real
    backward-compatibility guarantee, not an arbitrary choice. Range
    VALIDITY (`start_row <= end_row` for `END_MODE_SPECIFIC`, both
    within this source's own known dimensions) is enforced by
    `app.services.working_overlay_service`, not here -- this function
    stays pure and never raises, matching every other mutation function
    in this module. `undo`/`redo` need no changes at all to support the
    new mode: `WorkingOperation.before`/`after` already stores the
    whole (frozen) `DataRegion` object, so an end-mode change reverts
    exactly like any other data-region change always has.
    """
    before = overlay.data_region.get(worksheet_index)
    after = DataRegion(start_row=start_row, end_mode=end_mode, end_row=end_row)
    overlay.data_region[worksheet_index] = after
    _record(overlay, "data_region", worksheet_index, before, after)


def reset_data_region(overlay: WorkingOverlay, worksheet_index: int | None) -> bool:
    """Remove the data-region narrowing for this worksheet/source --
    the ENTIRE source range becomes active again (Slice 4/5's own
    documented default), not a fabricated "everything from row 1"
    value stored in the overlay itself."""
    if worksheet_index not in overlay.data_region:
        return False
    before = overlay.data_region.pop(worksheet_index)
    _record(overlay, "data_region", worksheet_index, before, None)
    return True


def set_time_axis_configuration(
    overlay: WorkingOverlay, worksheet_index: int | None, configuration: "TimeAxisConfiguration",
) -> None:
    """Store (or replace) this worksheet/source's own time-axis
    configuration (Slice 7). Column-role compatibility and every other
    validity check are enforced by `app.services.time_axis_service`,
    not here -- this function stays pure and never raises, matching
    every other mutation function in this module. `configuration` is
    always the whole, already-fully-built (frozen) object -- never
    partially merged with whatever was stored before."""
    before = overlay.time_axis.get(worksheet_index)
    overlay.time_axis[worksheet_index] = configuration
    _record(overlay, "time_axis", worksheet_index, before, configuration)


def clear_time_axis_configuration(overlay: WorkingOverlay, worksheet_index: int | None) -> bool:
    """Remove the time-axis configuration for this worksheet/source --
    returns to `unconfigured` (Slice 7). Returns `False` (a safe no-op)
    if none was set."""
    if worksheet_index not in overlay.time_axis:
        return False
    before = overlay.time_axis.pop(worksheet_index)
    _record(overlay, "time_axis", worksheet_index, before, None)
    return True


def reset_all(overlay: WorkingOverlay) -> None:
    """Clear every cell override, row exclusion, column role, header
    selection, data-region narrowing, and time-axis configuration --
    the raw preview returns to exactly its original, unconfigured state
    (Slice 5's own "Reset All returns the preparation session to the
    original raw/unconfigured state" requirement, extended by Slice 7 to
    cover its own new state). The `before` snapshot recorded here is
    bounded by the number of edits/mappings made so far (never the raw
    dataset's own size), preserving undo support for this operation
    too."""
    before = {
        "cell_overrides": dict(overlay.cell_overrides),
        "excluded_rows": set(overlay.excluded_rows),
        "column_roles": dict(overlay.column_roles),
        "column_engineering_quantities": dict(overlay.column_engineering_quantities),
        "column_measured_units": dict(overlay.column_measured_units),
        "header_row": dict(overlay.header_row),
        "data_region": dict(overlay.data_region),
        "time_axis": dict(overlay.time_axis),
    }
    overlay.cell_overrides.clear()
    overlay.excluded_rows.clear()
    overlay.column_roles.clear()
    overlay.column_engineering_quantities.clear()
    overlay.column_measured_units.clear()
    overlay.header_row.clear()
    overlay.data_region.clear()
    overlay.time_axis.clear()
    _record(overlay, "reset_all", None, before, None)


def _apply_state(overlay: WorkingOverlay, kind: str, key, state) -> None:
    if kind == "cell":
        if state is None:
            overlay.cell_overrides.pop(key, None)
        else:
            overlay.cell_overrides[key] = state
    elif kind == "row":
        if state:
            overlay.excluded_rows.add(key)
        else:
            overlay.excluded_rows.discard(key)
    elif kind == "column_role":
        if state is None:
            overlay.column_roles.pop(key, None)
        else:
            overlay.column_roles[key] = state
    elif kind == "column_engineering_quantity":
        if state is None:
            overlay.column_engineering_quantities.pop(key, None)
        else:
            overlay.column_engineering_quantities[key] = state
    elif kind == "column_measured_unit":
        if state is None:
            overlay.column_measured_units.pop(key, None)
        else:
            overlay.column_measured_units[key] = state
    elif kind == "header":
        if state is None:
            overlay.header_row.pop(key, None)
        else:
            overlay.header_row[key] = state
    elif kind == "data_region":
        if state is None:
            overlay.data_region.pop(key, None)
        else:
            overlay.data_region[key] = state
    elif kind == "time_axis":
        if state is None:
            overlay.time_axis.pop(key, None)
        else:
            overlay.time_axis[key] = state
    elif kind == "reset_all":
        if state is None:
            overlay.cell_overrides.clear()
            overlay.excluded_rows.clear()
            overlay.column_roles.clear()
            overlay.column_engineering_quantities.clear()
            overlay.column_measured_units.clear()
            overlay.header_row.clear()
            overlay.data_region.clear()
            overlay.time_axis.clear()
        else:
            overlay.cell_overrides = dict(state["cell_overrides"])
            overlay.excluded_rows = set(state["excluded_rows"])
            overlay.column_roles = dict(state["column_roles"])
            overlay.column_engineering_quantities = dict(state["column_engineering_quantities"])
            overlay.column_measured_units = dict(state.get("column_measured_units", {}))
            overlay.header_row = dict(state["header_row"])
            overlay.data_region = dict(state["data_region"])
            overlay.time_axis = dict(state["time_axis"])


def undo(overlay: WorkingOverlay) -> bool:
    """Revert the most recent operation (of any kind). Returns `False`
    (safe no-op) if there is nothing to undo."""
    if not overlay.history:
        return False
    op = overlay.history.pop()
    _apply_state(overlay, op.kind, op.key, op.before)
    overlay.redo_stack.append(op)
    overlay.revision += 1
    return True


def redo(overlay: WorkingOverlay) -> bool:
    """Reapply the most recently undone operation. Returns `False`
    (safe no-op) if there is nothing to redo."""
    if not overlay.redo_stack:
        return False
    op = overlay.redo_stack.pop()
    _apply_state(overlay, op.kind, op.key, op.after)
    overlay.history.append(op)
    overlay.revision += 1
    return True
