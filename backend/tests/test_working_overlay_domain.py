"""Domain-level tests for the Working Dataset overlay (Slices 4-5, DEC-072).

Pure data-structure tests -- no registry, no CSV/Excel I/O, no HTTP.
"""

from __future__ import annotations

from app.domain.time_axis import (
    FAMILY_ABSOLUTE,
    INTERPRETER_ID_MANUAL,
    PROVENANCE_NATIVE,
    TimeAxisConfiguration,
)
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_UNDEFINED,
    ENGINEERING_QUANTITY_VOLTAGE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
)
from app.domain.working_overlay import (
    END_MODE_SOURCE_END,
    END_MODE_SPECIFIC,
    MAX_OPERATION_HISTORY,
    OVERRIDE_KIND_CLEAR,
    OVERRIDE_KIND_EDIT,
    ROLE_NOT_ASSIGNED,
    ROLE_TIME_AXIS,
    ROLE_WAVEFORM,
    WorkingOverlay,
    cell_key,
    clear_header_row,
    clear_time_axis_configuration,
    column_key,
    redo,
    reset_all,
    reset_cell,
    reset_column_engineering_quantity,
    reset_column_role,
    reset_data_region,
    reset_column_measured_unit,
    row_key,
    set_cell_value,
    set_column_engineering_quantity,
    set_column_measured_unit,
    set_column_role,
    set_data_region,
    set_header_row,
    set_row_excluded,
    set_time_axis_configuration,
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
    """UAT fix (2026-09-04) -- exactly three roles now exist:
    `ROLE_NOT_ASSIGNED` (the sparse default, never stored explicitly),
    `ROLE_TIME_AXIS`, and `ROLE_WAVEFORM`. See
    app.domain.working_overlay's own module docstring for why the
    earlier five-role model (and Slice 4's own separate boolean
    `set_column_ignored`/`ignored_columns`) was retired rather than kept
    as a compatibility alias."""

    def test_assign_each_known_non_default_role(self):
        overlay = WorkingOverlay()
        for i, role in enumerate([ROLE_WAVEFORM, ROLE_TIME_AXIS]):
            key = column_key(None, i)
            set_column_role(overlay, key, role)
            assert overlay.column_roles[key] == role

    def test_not_assigned_role_is_never_stored_explicitly(self):
        # Absence IS the default -- app.domain.working_overlay's own
        # "do NOT automatically classify columns" guardrail, made
        # concrete: setting ROLE_NOT_ASSIGNED removes any entry rather
        # than writing "not_assigned" into the dict.
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_role(overlay, key, ROLE_WAVEFORM)

        set_column_role(overlay, key, ROLE_NOT_ASSIGNED)

        assert key not in overlay.column_roles

    def test_reset_column_role_removes_the_entry(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)
        set_column_role(overlay, key, ROLE_WAVEFORM)

        removed = reset_column_role(overlay, key)

        assert removed is True
        assert key not in overlay.column_roles

    def test_reset_column_role_with_no_role_is_a_safe_no_op(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)

        removed = reset_column_role(overlay, key)

        assert removed is False
        assert overlay.revision == 0

    def test_reset_from_a_role_returns_to_not_assigned_not_some_other_state(self):
        overlay = WorkingOverlay()
        key = column_key(None, 2)
        set_column_role(overlay, key, ROLE_TIME_AXIS)

        reset_column_role(overlay, key)

        assert key not in overlay.column_roles  # absence == ROLE_NOT_ASSIGNED

    def test_multiple_time_axis_columns_are_allowed(self):
        overlay = WorkingOverlay()
        set_column_role(overlay, column_key(None, 0), ROLE_TIME_AXIS)
        set_column_role(overlay, column_key(None, 1), ROLE_TIME_AXIS)

        assert overlay.column_roles[column_key(None, 0)] == ROLE_TIME_AXIS
        assert overlay.column_roles[column_key(None, 1)] == ROLE_TIME_AXIS

    def test_worksheet_index_keeps_roles_isolated(self):
        overlay = WorkingOverlay()
        set_column_role(overlay, column_key(0, 0), ROLE_WAVEFORM)
        set_column_role(overlay, column_key(1, 0), ROLE_TIME_AXIS)

        assert overlay.column_roles[column_key(0, 0)] == ROLE_WAVEFORM
        assert overlay.column_roles[column_key(1, 0)] == ROLE_TIME_AXIS

    def test_changing_role_away_from_waveform_never_touches_engineering_quantity(self):
        # DEC-077, task section J's own chosen behavior: the domain-level
        # set_column_role() is a pure, single-field mutation -- it never
        # reaches into column_engineering_quantities at all (clearing on
        # role-change-away is a documented non-behavior, not merely
        # untested).
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_role(overlay, key, ROLE_WAVEFORM)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_VOLTAGE)

        set_column_role(overlay, key, ROLE_TIME_AXIS)

        assert overlay.column_engineering_quantities[key] == ENGINEERING_QUANTITY_VOLTAGE


class TestColumnEngineeringQuantities:
    """DEC-077: CSV/Excel Engineering Quantity metadata. Mirrors
    TestColumnRoles's own structure -- the SAME sparse "absence is the
    default" convention, the SAME undo/redo/revision participation."""

    def test_assign_each_known_non_default_quantity(self):
        overlay = WorkingOverlay()
        for i, quantity in enumerate([ENGINEERING_QUANTITY_VOLTAGE, ENGINEERING_QUANTITY_VOLTAGE_ANGLE]):
            key = column_key(None, i)
            set_column_engineering_quantity(overlay, key, quantity)
            assert overlay.column_engineering_quantities[key] == quantity

    def test_undefined_quantity_is_never_stored_explicitly(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_VOLTAGE)

        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_UNDEFINED)

        assert key not in overlay.column_engineering_quantities

    def test_reset_removes_the_entry(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_CURRENT)

        removed = reset_column_engineering_quantity(overlay, key)

        assert removed is True
        assert key not in overlay.column_engineering_quantities

    def test_reset_with_no_quantity_is_a_safe_no_op(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)

        removed = reset_column_engineering_quantity(overlay, key)

        assert removed is False
        assert overlay.revision == 0

    def test_worksheet_index_keeps_quantities_isolated(self):
        overlay = WorkingOverlay()
        set_column_engineering_quantity(overlay, column_key(0, 0), ENGINEERING_QUANTITY_VOLTAGE)
        set_column_engineering_quantity(overlay, column_key(1, 0), ENGINEERING_QUANTITY_CURRENT)

        assert overlay.column_engineering_quantities[column_key(0, 0)] == ENGINEERING_QUANTITY_VOLTAGE
        assert overlay.column_engineering_quantities[column_key(1, 0)] == ENGINEERING_QUANTITY_CURRENT

    def test_revision_increments(self):
        overlay = WorkingOverlay()
        set_column_engineering_quantity(overlay, column_key(None, 0), ENGINEERING_QUANTITY_VOLTAGE)
        assert overlay.revision == 1

    def test_undo_reverts_a_quantity_assignment(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_VOLTAGE)

        undone = undo(overlay)

        assert undone is True
        assert key not in overlay.column_engineering_quantities

    def test_redo_reapplies_a_quantity_assignment(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_VOLTAGE)
        undo(overlay)

        redone = redo(overlay)

        assert redone is True
        assert overlay.column_engineering_quantities[key] == ENGINEERING_QUANTITY_VOLTAGE

    def test_reset_all_clears_engineering_quantities_too(self):
        overlay = WorkingOverlay()
        set_column_engineering_quantity(overlay, column_key(None, 0), ENGINEERING_QUANTITY_VOLTAGE)

        reset_all(overlay)

        assert overlay.column_engineering_quantities == {}

    def test_undo_after_reset_all_restores_engineering_quantities(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_engineering_quantity(overlay, key, ENGINEERING_QUANTITY_VOLTAGE)
        reset_all(overlay)

        undo(overlay)

        assert overlay.column_engineering_quantities[key] == ENGINEERING_QUANTITY_VOLTAGE


class TestColumnMeasuredUnits:
    """Measured Unit enhancement (DEC-080). Mirrors
    TestColumnEngineeringQuantities's own structure -- the SAME sparse
    "absence is the default" convention, the SAME undo/redo/revision
    participation, and the SAME "not cleared merely because role later
    moves away from ROLE_WAVEFORM" policy."""

    def test_assign_each_known_non_default_unit(self):
        overlay = WorkingOverlay()
        for i, unit in enumerate(["kV", "kA"]):
            key = column_key(None, i)
            set_column_measured_unit(overlay, key, unit)
            assert overlay.column_measured_units[key] == unit

    def test_blank_unit_is_never_stored_explicitly(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_measured_unit(overlay, key, "kV")

        set_column_measured_unit(overlay, key, "")

        assert key not in overlay.column_measured_units

    def test_reset_removes_the_entry(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)
        set_column_measured_unit(overlay, key, "A")

        removed = reset_column_measured_unit(overlay, key)

        assert removed is True
        assert key not in overlay.column_measured_units

    def test_reset_with_no_unit_is_a_safe_no_op(self):
        overlay = WorkingOverlay()
        key = column_key(None, 1)

        removed = reset_column_measured_unit(overlay, key)

        assert removed is False
        assert overlay.revision == 0

    def test_worksheet_index_keeps_units_isolated(self):
        overlay = WorkingOverlay()
        set_column_measured_unit(overlay, column_key(0, 0), "kV")
        set_column_measured_unit(overlay, column_key(1, 0), "kA")

        assert overlay.column_measured_units[column_key(0, 0)] == "kV"
        assert overlay.column_measured_units[column_key(1, 0)] == "kA"

    def test_revision_increments(self):
        overlay = WorkingOverlay()
        set_column_measured_unit(overlay, column_key(None, 0), "kV")
        assert overlay.revision == 1

    def test_undo_reverts_a_unit_assignment(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_measured_unit(overlay, key, "kV")

        undone = undo(overlay)

        assert undone is True
        assert key not in overlay.column_measured_units

    def test_redo_reapplies_a_unit_assignment(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_measured_unit(overlay, key, "kV")
        undo(overlay)

        redone = redo(overlay)

        assert redone is True
        assert overlay.column_measured_units[key] == "kV"

    def test_reset_all_clears_measured_units_too(self):
        overlay = WorkingOverlay()
        set_column_measured_unit(overlay, column_key(None, 0), "kV")

        reset_all(overlay)

        assert overlay.column_measured_units == {}

    def test_undo_after_reset_all_restores_measured_units(self):
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_measured_unit(overlay, key, "kV")
        reset_all(overlay)

        undo(overlay)

        assert overlay.column_measured_units[key] == "kV"

    def test_role_change_away_from_waveform_does_not_clear_measured_unit(self):
        """Task section K: same policy as Engineering Quantity -- the
        unit is ignored, not cleared, so it survives a round trip back
        to Waveform."""
        overlay = WorkingOverlay()
        key = column_key(None, 0)
        set_column_role(overlay, key, ROLE_WAVEFORM)
        set_column_measured_unit(overlay, key, "kV")

        set_column_role(overlay, key, ROLE_TIME_AXIS)

        assert overlay.column_measured_units[key] == "kV"


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

    def test_set_data_region_defaults_to_specific_end_mode(self):
        # Backward compatibility: every pre-refinement positional call
        # site (no end_mode argument at all) must keep producing exactly
        # the original Slice 5 shape.
        overlay = WorkingOverlay()

        set_data_region(overlay, None, 4, 5000)

        assert overlay.data_region[None].end_mode == END_MODE_SPECIFIC

    def test_source_end_mode_stores_no_numeric_end_row(self):
        overlay = WorkingOverlay()

        set_data_region(overlay, None, 4, None, end_mode=END_MODE_SOURCE_END)

        region = overlay.data_region[None]
        assert region.start_row == 4
        assert region.end_mode == END_MODE_SOURCE_END
        assert region.end_row is None

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

    def test_switching_from_specific_to_source_end_replaces_the_whole_region(self):
        overlay = WorkingOverlay()
        set_data_region(overlay, None, 4, 100)

        set_data_region(overlay, None, 4, None, end_mode=END_MODE_SOURCE_END)

        region = overlay.data_region[None]
        assert region.end_mode == END_MODE_SOURCE_END
        assert region.end_row is None

    def test_undo_redo_across_end_mode_change(self):
        # WorkingOperation.before/after already stores the whole frozen
        # DataRegion object, so an end-mode change reverts exactly like
        # any other data-region change -- no domain code change needed
        # to support this; this test exists to prove it.
        overlay = WorkingOverlay()
        set_data_region(overlay, None, 2, None, end_mode=END_MODE_SOURCE_END)
        set_data_region(overlay, None, 2, 1000, end_mode=END_MODE_SPECIFIC)

        undo(overlay)
        region_after_undo = overlay.data_region[None]
        assert region_after_undo.end_mode == END_MODE_SOURCE_END
        assert region_after_undo.end_row is None

        redo(overlay)
        region_after_redo = overlay.data_region[None]
        assert region_after_redo.end_mode == END_MODE_SPECIFIC
        assert region_after_redo.end_row == 1000


class TestTimeAxis:
    def _configuration(self, column_indices=(0,), *, confirmed=False):
        return TimeAxisConfiguration(
            column_indices=column_indices,
            family=FAMILY_ABSOLUTE,
            provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
            confirmed=confirmed,
        )

    def test_set_time_axis_configuration(self):
        overlay = WorkingOverlay()

        set_time_axis_configuration(overlay, None, self._configuration())

        assert overlay.time_axis[None].column_indices == (0,)
        assert overlay.time_axis[None].family == FAMILY_ABSOLUTE

    def test_set_replaces_the_whole_configuration(self):
        overlay = WorkingOverlay()
        set_time_axis_configuration(overlay, None, self._configuration((0,)))

        set_time_axis_configuration(overlay, None, self._configuration((0, 1)))

        assert overlay.time_axis[None].column_indices == (0, 1)

    def test_clear_time_axis_configuration(self):
        overlay = WorkingOverlay()
        set_time_axis_configuration(overlay, None, self._configuration())

        was_cleared = clear_time_axis_configuration(overlay, None)

        assert was_cleared is True
        assert None not in overlay.time_axis

    def test_clear_with_none_set_is_a_safe_no_op(self):
        overlay = WorkingOverlay()

        was_cleared = clear_time_axis_configuration(overlay, None)

        assert was_cleared is False
        assert overlay.revision == 0

    def test_time_axis_is_worksheet_scoped(self):
        overlay = WorkingOverlay()
        set_time_axis_configuration(overlay, 0, self._configuration((0,)))
        set_time_axis_configuration(overlay, 1, self._configuration((2,)))

        assert overlay.time_axis[0].column_indices == (0,)
        assert overlay.time_axis[1].column_indices == (2,)

    def test_multiple_time_axis_columns_are_representable(self):
        overlay = WorkingOverlay()

        set_time_axis_configuration(overlay, None, self._configuration((0, 1, 2)))

        assert overlay.time_axis[None].column_indices == (0, 1, 2)

    def test_undo_redo_across_configuration_change(self):
        overlay = WorkingOverlay()
        set_time_axis_configuration(overlay, None, self._configuration((0,), confirmed=False))
        set_time_axis_configuration(overlay, None, self._configuration((0,), confirmed=True))

        undo(overlay)
        assert overlay.time_axis[None].confirmed is False

        redo(overlay)
        assert overlay.time_axis[None].confirmed is True

    def test_undo_across_clear_restores_the_configuration(self):
        overlay = WorkingOverlay()
        set_time_axis_configuration(overlay, None, self._configuration())
        clear_time_axis_configuration(overlay, None)

        undo(overlay)

        assert overlay.time_axis[None].column_indices == (0,)


class TestResetAll:
    def test_clears_every_collection(self):
        overlay = WorkingOverlay()
        set_cell_value(overlay, cell_key(None, 1, 0), "x")
        set_row_excluded(overlay, row_key(None, 2), True)
        set_column_role(overlay, column_key(None, 1), ROLE_WAVEFORM)
        set_header_row(overlay, None, 3)
        set_data_region(overlay, None, 4, 100)
        set_time_axis_configuration(
            overlay, None,
            TimeAxisConfiguration(
                column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
                interpreter_id=INTERPRETER_ID_MANUAL,
            ),
        )

        reset_all(overlay)

        assert overlay.cell_overrides == {}
        assert overlay.excluded_rows == set()
        assert overlay.column_roles == {}
        assert overlay.header_row == {}
        assert overlay.data_region == {}
        assert overlay.time_axis == {}

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

        set_column_role(overlay, column_key(None, 0), ROLE_WAVEFORM)
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
        set_column_role(overlay, key, ROLE_WAVEFORM)

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
        set_column_role(overlay, column_key(None, 1), ROLE_WAVEFORM)
        set_header_row(overlay, None, 3)
        set_data_region(overlay, None, 4, 100)
        reset_all(overlay)

        undo(overlay)

        assert overlay.cell_overrides[cell_key(None, 1, 0)].value == "x"
        assert row_key(None, 2) in overlay.excluded_rows
        assert overlay.column_roles[column_key(None, 1)] == ROLE_WAVEFORM
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
            "cell_overrides", "excluded_rows", "column_roles", "column_engineering_quantities",
            "column_measured_units", "header_row", "data_region", "time_axis",
        }
        assert len(op.before["cell_overrides"]) == 5
