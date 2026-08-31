"""Domain-level tests for the Working Dataset overlay (Slices 4-5, DEC-072).

Pure data-structure tests -- no registry, no CSV/Excel I/O, no HTTP.
"""

from __future__ import annotations

from app.domain.working_overlay import (
    MAX_OPERATION_HISTORY,
    OVERRIDE_KIND_CLEAR,
    OVERRIDE_KIND_EDIT,
    ROLE_IGNORE,
    ROLE_METADATA,
    ROLE_QUALITY_STATUS,
    ROLE_TIME_AXIS,
    ROLE_UNKNOWN,
    ROLE_WAVEFORM,
    WorkingOverlay,
    cell_key,
    clear_header_row,
    column_key,
    redo,
    reset_all,
    reset_cell,
    reset_column_role,
    reset_data_region,
    row_key,
    set_cell_value,
    set_column_role,
    set_data_region,
    set_header_row,
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


class TestColumnRoles:
    """Slice 5 -- supersedes Slice 4's own boolean `set_column_ignored`/
    `ignored_columns` (retired; see app.domain.working_overlay's own
    module docstring). `ROLE_IGNORE` is now the sole representation of
    "ignored," exercised here alongside every other role."""

    def test_assign_each_known_role(self):
        overlay = WorkingOverlay()
        for i, role in enumerate([ROLE_WAVEFORM, ROLE_TIME_AXIS, ROLE_METADATA, ROLE_QUALITY_STATUS, ROLE_IGNORE]):
            key = column_key(None, i)
            set_column_role(overlay, key, role)
            assert overlay.column_roles[key] == role

    def test_unknown_role_is_never_stored_explicitly(self):
        # Absence IS the default -- app.domain.working_overlay's own
        # "do NOT automatically classify columns" guardrail, made
        # concrete: setting ROLE_UNKNOWN removes any entry rather than
        # writing "unknown" into the dict.
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_role(overlay, key, ROLE_WAVEFORM)

        set_column_role(overlay, key, ROLE_UNKNOWN)

        assert key not in overlay.column_roles

    def test_reset_column_role_removes_the_entry(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)
        set_column_role(overlay, key, ROLE_METADATA)

        removed = reset_column_role(overlay, key)

        assert removed is True
        assert key not in overlay.column_roles

    def test_reset_column_role_with_no_role_is_a_safe_no_op(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)

        removed = reset_column_role(overlay, key)

        assert removed is False
        assert overlay.revision == 0

    def test_reset_from_ignore_returns_to_unknown_not_some_other_state(self):
        overlay = WorkingOverlay()
        key = column_key(None, 2)
        set_column_role(overlay, key, ROLE_IGNORE)

        reset_column_role(overlay, key)

        assert key not in overlay.column_roles  # absence == ROLE_UNKNOWN

    def test_multiple_time_axis_columns_are_allowed(self):
        overlay = WorkingOverlay()
        set_column_role(overlay, column_key(None, 0), ROLE_TIME_AXIS)
        set_column_role(overlay, column_key(None, 1), ROLE_TIME_AXIS)

        assert overlay.column_roles[column_key(None, 0)] == ROLE_TIME_AXIS
        assert overlay.column_roles[column_key(None, 1)] == ROLE_TIME_AXIS

    def test_worksheet_index_keeps_roles_isolated(self):
        overlay = WorkingOverlay()
        set_column_role(overlay, column_key(0, 0), ROLE_WAVEFORM)
        set_column_role(overlay, column_key(1, 0), ROLE_METADATA)

        assert overlay.column_roles[column_key(0, 0)] == ROLE_WAVEFORM
        assert overlay.column_roles[column_key(1, 0)] == ROLE_METADATA


class TestHeaderRow:
    def test_set_header_row(self):
        overlay = WorkingOverlay()

        set_header_row(overlay, None, 3)

        assert overlay.header_row[None] == 3

    def test_clear_header_row(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, None, 3)

        cleared = clear_header_row(overlay, None)

        assert cleared is True
        assert None not in overlay.header_row

    def test_clear_header_row_with_none_selected_is_a_safe_no_op(self):
        overlay = WorkingOverlay()

        cleared = clear_header_row(overlay, None)

        assert cleared is False
        assert overlay.revision == 0

    def test_header_row_is_worksheet_scoped(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, 0, 2)
        set_header_row(overlay, 1, 5)

        assert overlay.header_row[0] == 2
        assert overlay.header_row[1] == 5

    def test_clearing_header_never_touches_column_roles(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, None, 3)
        set_column_role(overlay, column_key(None, 0), ROLE_WAVEFORM)

        clear_header_row(overlay, None)

        assert overlay.column_roles[column_key(None, 0)] == ROLE_WAVEFORM


class TestDataRegion:
    def test_set_data_region(self):
        overlay = WorkingOverlay()

        set_data_region(overlay, None, 4, 5000)

        assert overlay.data_region[None].start_row == 4
        assert overlay.data_region[None].end_row == 5000

    def test_reset_data_region(self):
        overlay = WorkingOverlay()
        set_data_region(overlay, None, 4, 5000)

        was_reset = reset_data_region(overlay, None)

        assert was_reset is True
        assert None not in overlay.data_region

    def test_reset_data_region_with_none_set_is_a_safe_no_op(self):
        overlay = WorkingOverlay()

        was_reset = reset_data_region(overlay, None)

        assert was_reset is False
        assert overlay.revision == 0

    def test_data_region_is_worksheet_scoped(self):
        overlay = WorkingOverlay()
        set_data_region(overlay, 0, 2, 10)
        set_data_region(overlay, 1, 5, 20)

        assert overlay.data_region[0].start_row == 2
        assert overlay.data_region[1].start_row == 5

    def test_start_equal_to_end_is_representable(self):
        overlay = WorkingOverlay()

        set_data_region(overlay, None, 7, 7)

        assert overlay.data_region[None].start_row == 7
        assert overlay.data_region[None].end_row == 7


class TestResetAll:
    def test_clears_every_collection(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        set_row_excluded(overlay, row_key(None, 2), True)
        set_column_role(overlay, column_key(None, 1), ROLE_IGNORE)
        set_header_row(overlay, None, 3)
        set_data_region(overlay, None, 4, 100)

        reset_all(overlay)

        assert overlay.cell_overrides == {}
        assert overlay.excluded_rows == set()
        assert overlay.column_roles == {}
        assert overlay.header_row == {}
        assert overlay.data_region == {}

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

        set_column_role(overlay, column_key(None, 0), ROLE_IGNORE)
        assert overlay.revision == 3

        set_header_row(overlay, None, 1)
        assert overlay.revision == 4

        set_data_region(overlay, None, 2, 10)
        assert overlay.revision == 5

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

    def test_undo_column_role(self):
        overlay = WorkingOverlay()
        key = column_key(None, 2)
        set_column_role(overlay, key, ROLE_IGNORE)

        undo(overlay)

        assert key not in overlay.column_roles

    def test_undo_header_row(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, None, 3)

        undo(overlay)

        assert None not in overlay.header_row

    def test_undo_clear_header_row_restores_it(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, None, 3)
        clear_header_row(overlay, None)

        undo(overlay)

        assert overlay.header_row[None] == 3

    def test_undo_data_region(self):
        overlay = WorkingOverlay()
        set_data_region(overlay, None, 4, 100)

        undo(overlay)

        assert None not in overlay.data_region

    def test_undo_reset_all_restores_everything(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        set_row_excluded(overlay, row_key(None, 2), True)
        set_column_role(overlay, column_key(None, 1), ROLE_IGNORE)
        set_header_row(overlay, None, 3)
        set_data_region(overlay, None, 4, 100)
        reset_all(overlay)

        undo(overlay)

        assert overlay.cell_overrides[cell_key(None, 1, 0)].value == "x"
        assert row_key(None, 2) in overlay.excluded_rows
        assert overlay.column_roles[column_key(None, 1)] == ROLE_IGNORE
        assert overlay.header_row[None] == 3
        assert overlay.data_region[None].start_row == 4
        assert overlay.data_region[None].end_row == 100

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

    def test_redo_reapplies_an_undone_header_selection(self):
        overlay = WorkingOverlay()
        set_header_row(overlay, None, 3)
        undo(overlay)

        assert redo(overlay) is True
        assert overlay.header_row[None] == 3

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
        # A reset_all snapshot is bounded by edit/mapping count, not by
        # any simulated "dataset size" -- confirmed here by checking the
        # snapshot only ever contains the overlay's own five
        # collections, never anything proportional to row/column counts
        # that don't even exist in this pure-domain test.
        overlay = WorkingOverlay()
        for i in range(5):
            set_cell_value(overlay, cell_key(None, i, 0), str(i))
        reset_all(overlay)

        op = overlay.history[-1]
        assert set(op.before.keys()) == {
            "cell_overrides", "excluded_rows", "column_roles", "header_row", "data_region",
        }
        assert len(op.before["cell_overrides"]) == 5
