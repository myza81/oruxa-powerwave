"""Working Dataset overlay domain model (CSV/Excel ingestion Slice 4, DEC-072).

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
interpretation of a value (no type coercion, no header/column-role/
time-axis meaning -- a working cell value is always a plain string, or
`None` for an explicit clear; see `CellOverride`'s own docstring for
why).

Coordinate identity (task's own explicit "stable identity" requirement):
a `(worksheet_index, row_number, column_index)` tuple, where
`worksheet_index` is `None` for CSV (which has no worksheet dimension at
all) and the Slice 2 0-based worksheet index for Excel -- the SAME
tuple shape for both formats, so the rest of this module needs no
per-format branching. `row_number` is 1-based (matches
`app.services.preparation_preview_service.PreviewRow.row_number`);
`column_index` is 0-based (matches the same module's own column
positions). Row/column exclusion/ignore use the analogous
`(worksheet_index, row_number)` / `(worksheet_index, column_index)`
shapes. None of these ever renumber -- excluding row 2 of 4 never turns
row 3 into row 2 (task's own explicit "provenance" requirement).

Undo/redo (task's own "implement if it fits naturally... do not fake by
snapshotting the entire dataset"): implemented here as a bounded
operation history. Every recorded `WorkingOperation` carries only the
`before`/`after` state of the ONE thing it changed -- a single
`CellOverride` (or `None`), a single `bool`, or (for `reset_all` only) a
snapshot of the overlay's own three collections, whose size is
proportional to the number of edits made so far, never to the raw
dataset's row/column count. This is why undo/redo stays compatible with
"overlay scales with edits, not with dataset size" even though
`reset_all` is technically a whole-overlay operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(slots=True)
class WorkingOperation:
    """One undoable/redoable mutation.

    `kind` is `"cell"` / `"row"` / `"column"` / `"reset_all"`. `key` is
    the affected `CellKey`/`RowKey`/`ColumnKey`, or `None` for
    `reset_all`. `before`/`after` hold whatever this module's own
    `_apply_state()` needs to reverse/reapply the operation -- see this
    module's own docstring for why this stays O(edit count), never
    O(dataset size).
    """

    kind: str
    key: CellKey | RowKey | ColumnKey | None
    before: object
    after: object


@dataclass(slots=True)
class WorkingOverlay:
    """Everything Slice 4 adds to one `PreparationSession` (Slice 1-3).

    Lives as a plain attribute on `PreparationSession` -- no new
    registry, no new lifecycle: created with the session, mutated in
    place by this module's own functions, and released the instant its
    owning `PreparationSession` is (source DELETE, workspace DELETE, or
    process restart) -- see `app.services.preparation_session_registry`'s
    own docstring, unaffected by this addition.
    """

    cell_overrides: dict[CellKey, CellOverride] = field(default_factory=dict)
    excluded_rows: set[RowKey] = field(default_factory=set)
    ignored_columns: set[ColumnKey] = field(default_factory=set)
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


def set_column_ignored(overlay: WorkingOverlay, key: ColumnKey, ignored: bool) -> None:
    before = key in overlay.ignored_columns
    if ignored:
        overlay.ignored_columns.add(key)
    else:
        overlay.ignored_columns.discard(key)
    _record(overlay, "column", key, before, ignored)


def reset_all(overlay: WorkingOverlay) -> None:
    """Clear every cell override, row exclusion, and column ignore --
    the raw preview returns to exactly its original state. The
    `before` snapshot recorded here is bounded by the number of edits
    made so far (never the raw dataset's own size), preserving undo
    support for this operation too."""
    before = {
        "cell_overrides": dict(overlay.cell_overrides),
        "excluded_rows": set(overlay.excluded_rows),
        "ignored_columns": set(overlay.ignored_columns),
    }
    overlay.cell_overrides.clear()
    overlay.excluded_rows.clear()
    overlay.ignored_columns.clear()
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
    elif kind == "column":
        if state:
            overlay.ignored_columns.add(key)
        else:
            overlay.ignored_columns.discard(key)
    elif kind == "reset_all":
        if state is None:
            overlay.cell_overrides.clear()
            overlay.excluded_rows.clear()
            overlay.ignored_columns.clear()
        else:
            overlay.cell_overrides = dict(state["cell_overrides"])
            overlay.excluded_rows = set(state["excluded_rows"])
            overlay.ignored_columns = set(state["ignored_columns"])


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
