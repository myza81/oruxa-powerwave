"""Domain-level tests for the Working Dataset overlay (Slice 4, DEC-072).

Pure data-structure tests -- no registry, no CSV/Excel I/O, no HTTP.
"""

from __future__ import annotations

from app.domain.working_overlay import (
    OVERRIDE_KIND_CLEAR,
    OVERRIDE_KIND_EDIT,
    MAX_OPERATION_HISTORY,
    WorkingOverlay,
    cell_key,
    column_key,
    redo,
    reset_all,
    reset_cell,
    row_key,
    set_cell_value,
    set_column_ignored,
    set_row_excluded,
    undo,
)


class TestCellOverrides:
    def test_edit_sets_a_string_override(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)

        set_cell_value(overlay, key, "42")

        assert overlay.cell_overrides[key].kind == OVERRIDE_KIND_EDIT
        assert overlay.cell_overrides[key].value == "42"

    def test_edit_to_empty_string_is_distinct_from_clear(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)

        set_cell_value(overlay, key, "")

        assert overlay.cell_overrides[key].kind == OVERRIDE_KIND_EDIT
        assert overlay.cell_overrides[key].value == ""

    def test_clear_sets_value_none(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)

        set_cell_value(overlay, key, None)

        assert overlay.cell_overrides[key].kind == OVERRIDE_KIND_CLEAR
        assert overlay.cell_overrides[key].value is None

    def test_edit_overwrites_a_previous_edit(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)

        set_cell_value(overlay, key, "first")
        set_cell_value(overlay, key, "second")

        assert overlay.cell_overrides[key].value == "second"

    def test_reset_cell_removes_the_override(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")

        removed = reset_cell(overlay, key)

        assert removed is True
        assert key not in overlay.cell_overrides

    def test_reset_cell_with_no_override_is_a_safe_no_op(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)

        removed = reset_cell(overlay, key)

        assert removed is False
        assert overlay.revision == 0

    def test_worksheet_index_keeps_cells_isolated(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(0, 1, 0), "sheet-a")
        set_cell_value(overlay, cell_key(1, 1, 0), "sheet-b")

        assert overlay.cell_overrides[cell_key(0, 1, 0)].value == "sheet-a"
        assert overlay.cell_overrides[cell_key(1, 1, 0)].value == "sheet-b"


class TestRowExclusion:
    def test_exclude_then_include(self):
        overlay = WorkingOverlay()
        key = row_key(None, 3)

        set_row_excluded(overlay, key, True)
        assert key in overlay.excluded_rows

        set_row_excluded(overlay, key, False)
        assert key not in overlay.excluded_rows

    def test_excluding_an_already_excluded_row_is_idempotent(self):
        overlay = WorkingOverlay()
        key = row_key(None, 3)

        set_row_excluded(overlay, key, True)
        set_row_excluded(overlay, key, True)

        assert overlay.excluded_rows == {key}


class TestColumnIgnore:
    def test_ignore_then_unignore(self):
        overlay = WorkingOverlay()
        key = column_key(None, 2)

        set_column_ignored(overlay, key, True)
        assert key in overlay.ignored_columns

        set_column_ignored(overlay, key, False)
        assert key not in overlay.ignored_columns


class TestResetAll:
    def test_clears_every_collection(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        set_row_excluded(overlay, row_key(None, 2), True)
        set_column_ignored(overlay, column_key(None, 1), True)

        reset_all(overlay)

        assert overlay.cell_overrides == {}
        assert overlay.excluded_rows == set()
        assert overlay.ignored_columns == set()

    def test_reset_all_on_an_empty_overlay_does_not_error(self):
        overlay = WorkingOverlay()

        reset_all(overlay)

        assert overlay.cell_overrides == {}
        assert overlay.revision == 1  # still a recorded operation, just an empty one


class TestRevisionCounter:
    def test_every_mutation_increments_revision(self):
        overlay = WorkingOverlay()
        assert overlay.revision == 0

        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        assert overlay.revision == 1

        set_row_excluded(overlay, row_key(None, 1), True)
        assert overlay.revision == 2

        set_column_ignored(overlay, column_key(None, 0), True)
        assert overlay.revision == 3

    def test_reading_the_overlay_never_changes_the_revision(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        revision = overlay.revision

        _ = overlay.cell_overrides.get(cell_key(None, 1, 0))
        _ = list(overlay.excluded_rows)

        assert overlay.revision == revision


class TestUndoRedo:
    def test_undo_cell_edit_removes_it(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")

        assert undo(overlay) is True

        assert key not in overlay.cell_overrides

    def test_undo_cell_edit_restores_the_prior_override(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "first")
        set_cell_value(overlay, key, "second")

        undo(overlay)

        assert overlay.cell_overrides[key].value == "first"

    def test_undo_reset_cell_restores_the_override(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")
        reset_cell(overlay, key)

        undo(overlay)

        assert overlay.cell_overrides[key].value == "x"

    def test_undo_row_exclusion(self):
        overlay = WorkingOverlay()
        key = row_key(None, 2)
        set_row_excluded(overlay, key, True)

        undo(overlay)

        assert key not in overlay.excluded_rows

    def test_undo_column_ignore(self):
        overlay = WorkingOverlay()
        key = column_key(None, 2)
        set_column_ignored(overlay, key, True)

        undo(overlay)

        assert key not in overlay.ignored_columns

    def test_undo_reset_all_restores_everything(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        set_row_excluded(overlay, row_key(None, 2), True)
        set_column_ignored(overlay, column_key(None, 1), True)
        reset_all(overlay)

        undo(overlay)

        assert overlay.cell_overrides[cell_key(None, 1, 0)].value == "x"
        assert row_key(None, 2) in overlay.excluded_rows
        assert column_key(None, 1) in overlay.ignored_columns

    def test_undo_with_empty_history_is_a_safe_no_op(self):
        overlay = WorkingOverlay()

        assert undo(overlay) is False
        assert overlay.revision == 0

    def test_redo_reapplies_an_undone_edit(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")
        undo(overlay)

        assert redo(overlay) is True

        assert overlay.cell_overrides[key].value == "x"

    def test_redo_with_empty_redo_stack_is_a_safe_no_op(self):
        overlay = WorkingOverlay()

        assert redo(overlay) is False

    def test_a_new_edit_after_undo_clears_the_redo_stack(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")
        undo(overlay)

        set_cell_value(overlay, key, "y")

        assert redo(overlay) is False
        assert overlay.cell_overrides[key].value == "y"

    def test_undo_redo_round_trip_restores_revision_progression(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        set_cell_value(overlay, key, "x")
        revision_after_edit = overlay.revision

        undo(overlay)
        redo(overlay)

        assert overlay.cell_overrides[key].value == "x"
        assert overlay.revision > revision_after_edit  # undo+redo both bump revision, never roll it back

    def test_history_is_bounded(self):
        overlay = WorkingOverlay()
        key = cell_key(None, 1, 0)
        for i in range(MAX_OPERATION_HISTORY + 50):
            set_cell_value(overlay, key, str(i))

        assert len(overlay.history) == MAX_OPERATION_HISTORY

    def test_undo_never_duplicates_the_dataset(self):
        # A reset_all snapshot is bounded by edit count, not by any
        # simulated "dataset size" -- confirmed here by checking the
        # snapshot only ever contains the overlay's own three
        # collections, never anything proportional to row/column counts
        # that don't even exist in this pure-domain test.
        overlay = WorkingOverlay()
        for i in range(5):
            set_cell_value(overlay, cell_key(None, i, 0), str(i))
        reset_all(overlay)

        op = overlay.history[-1]
        assert set(op.before.keys()) == {"cell_overrides", "excluded_rows", "ignored_columns"}
        assert len(op.before["cell_overrides"]) == 5
