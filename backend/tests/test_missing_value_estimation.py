"""Missing-value fill/estimation enhancement (owner UAT, 2026-09-10) --
extends DEC-084's original three resolution paths (Mark as Null / Fill
Manually / Not Assigned) with a fourth (Estimate Missing Value, single-
cell AND bulk) and a bulk-only fifth (Constant Value fill), for
`waveform_value_missing`/`waveform_value_invalid` cells only.

Pure service-level tests -- no HTTP; mirrors
tests/test_preparation_conversion_service.py's/
tests/test_preparation_export_service.py's own local-helper convention
rather than cross-importing test helpers.
"""

from __future__ import annotations

import asyncio
import io
import math

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.domain.missing_data_estimation import ESTIMATION_METHOD_HOLD_LAST, ESTIMATION_METHOD_LINEAR, ESTIMATION_METHOD_LOCAL_MEAN
from app.domain.working_overlay import OVERRIDE_KIND_CONSTANT_FILL, OVERRIDE_KIND_ESTIMATED
from app.services.errors import InvalidEstimationConfigurationError, InvalidFillTargetError
from app.services.preparation_conversion_service import convert_preparation_source
from app.services.preparation_export_service import EXPORT_MODE_DATA_ONLY, export_preparation_source
from app.services.preparation_import_service import import_csv_preparation_source
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import set_time_axis_configuration
from app.services.working_overlay_service import (
    apply_bulk_constant_fill,
    apply_estimate,
    edit_cell,
    preview_bulk_constant_fill,
    preview_estimate,
    redo_working_change,
    reset_all_working_changes,
    set_column_role,
    undo_working_change,
)
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"
MISSING = "waveform_value_missing"
INVALID = "waveform_value_invalid"


def _upload(content: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


def _add_csv(registry: PreparationSessionRegistry, content: bytes, filename: str = "e.csv") -> str:
    summary = asyncio.run(
        import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content, filename, "text/csv"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


def _mark_time_axis(registry, source_id, *column_indices) -> None:
    for column_index in column_indices:
        set_column_role(workspace_id=WS, source_id=source_id, column_index=column_index, role="time_axis", registry=registry)


def _mark_waveform(registry, source_id, *column_indices) -> None:
    for column_index in column_indices:
        set_column_role(workspace_id=WS, source_id=source_id, column_index=column_index, role="waveform", registry=registry)


def _confirm_absolute(registry, source_id, *, column_index=0) -> None:
    set_time_axis_configuration(
        workspace_id=WS, source_id=source_id, column_indices=(column_index,),
        interpreter_id="absolute_datetime", options={}, confirmed=True, registry=registry,
    )


def _gap_source(registry, *, missing_rows=(4, 5, 6), start_hour=13) -> str:
    """10 rows, 1 second apart, VA (column 1) blank at `missing_rows`
    (0-based row index within the 10) -- ready, Waveform-role, absolute
    Time Axis already confirmed."""
    lines = []
    for i in range(10):
        val = "" if i in missing_rows else f"{float(i)}"
        lines.append(f"2026-08-31 {start_hour}:00:{i:02d},{val}")
    sid = _add_csv(registry, ("\n".join(lines) + "\n").encode())
    _mark_time_axis(registry, sid, 0)
    _mark_waveform(registry, sid, 1)
    _confirm_absolute(registry, sid)
    return sid


def _mixed_gap_source(registry, *, start_hour=13) -> str:
    """10 rows, 1 second apart. Row 5 (1-based) blank, row 6 unparseable
    text ("abc"), row 7 blank -- one CONTIGUOUS non-finite gap that mixes
    `waveform_value_missing` (rows 5, 7) and `waveform_value_invalid`
    (row 6). Bracketed by row 4 = 3.0 and row 8 = 7.0, so Linear
    interpolation across the full 3-row gap yields 4.0 / 5.0 / 6.0."""
    lines = []
    for i in range(10):
        if i == 4:
            val = ""
        elif i == 5:
            val = "abc"
        elif i == 6:
            val = ""
        else:
            val = f"{float(i)}"
        lines.append(f"2026-08-31 {start_hour}:00:{i:02d},{val}")
    sid = _add_csv(registry, ("\n".join(lines) + "\n").encode())
    _mark_time_axis(registry, sid, 0)
    _mark_waveform(registry, sid, 1)
    _confirm_absolute(registry, sid)
    return sid


class TestSharedEstimationPolicyModule:
    """Owner hardening pass (2026-09-10): the method/max-gap/local-mean-
    radius constants and `*_valid()` predicates now live natively in
    `app.domain.missing_data_estimation` (the neutral, calculated-
    channel-agnostic shared home) -- `app.domain.calculated_channel`
    re-exports the SAME objects unchanged for its own pre-existing
    callers, but `app.services.working_overlay_service` (Data
    Preparation) must import directly from the shared module, never from
    the Calculated Channel domain."""

    def test_calculated_channel_reexports_the_same_objects_not_a_copy(self):
        import app.domain.calculated_channel as calc
        import app.domain.missing_data_estimation as shared

        for name in (
            "ESTIMATION_METHOD_HOLD_LAST", "ESTIMATION_METHOD_NEAREST", "ESTIMATION_METHOD_LINEAR",
            "ESTIMATION_METHOD_LOCAL_MEAN", "ESTIMATION_METHOD_PCHIP", "ALL_ESTIMATION_METHODS",
            "UNIMPLEMENTED_ESTIMATION_METHODS", "MAX_GAP_UNIT_SAMPLES", "ALL_MAX_GAP_UNITS",
            "estimation_method_valid", "max_gap_value_valid", "max_gap_unit_valid", "local_mean_radius_valid",
        ):
            assert getattr(calc, name) is getattr(shared, name), f"{name} is no longer the same object"

    def test_working_overlay_service_does_not_import_from_calculated_channel_domain(self):
        import inspect
        import app.services.working_overlay_service as wos

        source = inspect.getsource(wos)
        assert "from app.domain.calculated_channel import" not in source
        assert "from app.domain.missing_data_estimation import" in source


class TestSingleCellGapEstimation:
    """Task section 5's own recommendation B: clicking ANY cell inside a
    contiguous gap resolves the WHOLE gap, not just that one cell."""

    def test_clicking_the_middle_of_a_three_row_gap_resolves_all_three(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))  # rows 5,6,7 (1-based) blank

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=6, registry=prep,
        )
        # A single-cell target request always matches just the ONE clicked
        # cell (N); the true affected scope is the full resolved gap (M).
        assert preview.matching_count == 1
        assert preview.affected_count == 3
        assert preview.eligible_count == 3
        assert preview.unresolved_count == 0

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=6, registry=prep,
        )
        assert result.applied_count == 3

        session = prep.get(WS, sid)
        for row_number, expected in ((5, "4.0"), (6, "5.0"), (7, "6.0")):
            override = session.working_overlay.cell_overrides[(None, row_number, 1)]
            assert override.kind == OVERRIDE_KIND_ESTIMATED
            assert float(override.value) == pytest.approx(float(expected))
            assert override.estimation_method == ESTIMATION_METHOD_LINEAR
            assert override.max_gap_value == 3

    def test_one_gap_estimate_is_exactly_one_undo(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=6, registry=prep,
        )
        session = prep.get(WS, sid)
        assert all((None, rn, 1) in session.working_overlay.cell_overrides for rn in (5, 6, 7))

        assert undo_working_change(workspace_id=WS, source_id=sid, registry=prep).can_redo is True
        assert all((None, rn, 1) not in session.working_overlay.cell_overrides for rn in (5, 6, 7))

        redo_working_change(workspace_id=WS, source_id=sid, registry=prep)
        assert all((None, rn, 1) in session.working_overlay.cell_overrides for rn in (5, 6, 7))


class TestOversizedGap:
    def test_gap_larger_than_max_gap_value_remains_entirely_unresolved(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))  # a 3-row gap

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=2, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert preview.matching_count == 3
        assert preview.eligible_count == 0
        assert preview.unresolved_count == 3

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=2, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert result.applied_count == 0
        session = prep.get(WS, sid)
        assert all((None, rn, 1) not in session.working_overlay.cell_overrides for rn in (5, 6, 7))

        # No partial fill -- NOT even the edge samples of the too-large gap.
        result2 = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert result2.applied_count == 3


class TestConstantFill:
    def test_fills_every_eligible_cell_with_the_same_constant(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))

        preview = preview_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, registry=prep)
        assert preview.eligible_count == 3

        result = apply_bulk_constant_fill(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, constant_value=0.0, registry=prep,
        )
        assert result.applied_count == 3
        session = prep.get(WS, sid)
        for rn in (5, 6, 7):
            override = session.working_overlay.cell_overrides[(None, rn, 1)]
            assert override.kind == OVERRIDE_KIND_CONSTANT_FILL
            assert override.value == "0.0"
            # Never carries estimation metadata -- distinct from an estimate.
            assert override.estimation_method is None

    def test_non_finite_constant_value_rejected(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        with pytest.raises(InvalidEstimationConfigurationError):
            apply_bulk_constant_fill(
                workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
                constant_value=math.nan, registry=prep,
            )

    def test_one_bulk_fill_is_exactly_one_undo(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))
        apply_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, constant_value=1.0, registry=prep)
        session = prep.get(WS, sid)
        assert sum(1 for k in session.working_overlay.cell_overrides if k[2] == 1) == 3
        undo_working_change(workspace_id=WS, source_id=sid, registry=prep)
        assert sum(1 for k in session.working_overlay.cell_overrides if k[2] == 1) == 0


class TestInvalidWaveformValue:
    def test_unparseable_text_cell_is_estimable(self):
        prep = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{'ERR' if i == 5 else float(i)}" for i in range(10)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        _confirm_absolute(prep, sid)

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=INVALID,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=1, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert preview.matching_count == 1
        assert preview.eligible_count == 1

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=INVALID,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=1, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert result.applied_count == 1
        session = prep.get(WS, sid)
        override = session.working_overlay.cell_overrides[(None, 6, 1)]
        assert float(override.value) == pytest.approx(5.0)  # bracketed by row5=4.0, row7=6.0


class TestTimeAxisGuardrail:
    def test_time_axis_column_has_zero_eligible_cells(self):
        # Mirrors eligible_bulk_null_rows()'s own established precedent
        # (reused here unchanged): a non-Waveform column -- Time Axis
        # included -- is never a special-cased error, it naturally
        # reports zero eligible cells, since waveform_value_missing/
        # waveform_value_invalid are only ever produced for Waveform-role
        # columns in the first place (this is what backend-enforces the
        # Time-Axis guardrail structurally).
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=0, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert preview.matching_count == 0
        assert preview.eligible_count == 0

    def test_time_value_missing_issue_code_rejected(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        with pytest.raises(InvalidFillTargetError):
            preview_estimate(
                workspace_id=WS, source_id=sid, column_index=1, issue_code="time_value_missing",
                method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
                local_mean_radius=None, target_row_number=None, registry=prep,
            )

    def test_not_assigned_column_has_zero_eligible_cells(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,\n2026-08-31 13:00:01,1.0\n")
        _mark_time_axis(prep, sid, 0)
        # column 1 left `not_assigned` -- never marked waveform.
        _confirm_absolute(prep, sid)
        preview = preview_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, registry=prep)
        assert preview.eligible_count == 0


class TestUnimplementedAndInvalidConfiguration:
    def test_pchip_rejected(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        with pytest.raises(InvalidEstimationConfigurationError):
            preview_estimate(
                workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
                method="pchip", max_gap_value=3, max_gap_unit="samples",
                local_mean_radius=None, target_row_number=None, registry=prep,
            )

    def test_local_mean_requires_radius(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        with pytest.raises(InvalidEstimationConfigurationError):
            preview_estimate(
                workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
                method=ESTIMATION_METHOD_LOCAL_MEAN, max_gap_value=3, max_gap_unit="samples",
                local_mean_radius=None, target_row_number=None, registry=prep,
            )

    def test_non_samples_max_gap_unit_rejected(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        with pytest.raises(InvalidEstimationConfigurationError):
            preview_estimate(
                workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
                method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="milliseconds",
                local_mean_radius=None, target_row_number=None, registry=prep,
            )

    def test_linear_without_resolved_time_axis_rejected(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"a,\nb,1.0\nc,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        # Time Axis deliberately left unconfigured.
        with pytest.raises(InvalidEstimationConfigurationError):
            preview_estimate(
                workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
                method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
                local_mean_radius=None, target_row_number=None, registry=prep,
            )


class TestValidAndManuallyFixedCellsUntouched:
    def test_bulk_estimate_never_touches_valid_cells(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        session = prep.get(WS, sid)
        # Only the one originally-blank cell (row 5) was ever written.
        assert list(session.working_overlay.cell_overrides.keys()) == [(None, 5, 1)]

    def test_manually_fixed_cell_is_excluded_from_bulk_scope(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5))  # rows 5, 6 blank
        # The engineer manually fixes row 5 before running bulk estimate.
        edit_cell(workspace_id=WS, source_id=sid, row_number=5, column_index=1, value="99.0", registry=prep)

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert preview.matching_count == 1  # only row 6 remains unresolved

        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        session = prep.get(WS, sid)
        # Row 5's manual edit is completely untouched.
        assert session.working_overlay.cell_overrides[(None, 5, 1)].value == "99.0"


class TestPreviewApplyStaleness:
    def test_apply_recomputes_eligibility_never_trusts_a_stale_preview(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5))  # rows 5, 6 blank

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert preview.matching_count == 2

        # Between preview and apply, the engineer manually repairs row 5.
        edit_cell(workspace_id=WS, source_id=sid, row_number=5, column_index=1, value="42.0", registry=prep)

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        # The FRESH scope is just row 6 now -- never the stale 2 from preview.
        assert result.matching_count == 1
        assert result.applied_count == 1
        session = prep.get(WS, sid)
        assert session.working_overlay.cell_overrides[(None, 5, 1)].value == "42.0"  # untouched manual repair


class TestResetAll:
    def test_reset_all_restores_original_unresolved_state(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5, 6))
        apply_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, constant_value=0.0, registry=prep)
        session = prep.get(WS, sid)
        assert len(session.working_overlay.cell_overrides) == 3
        summary_before = build_issue_summary(workspace_id=WS, source_id=sid, registry=prep)
        assert summary_before.blocking_count == 0

        reset_all_working_changes(workspace_id=WS, source_id=sid, registry=prep)
        assert len(session.working_overlay.cell_overrides) == 0

        # The 3 cells are unresolved (blocking) again.
        summary_after = build_issue_summary(workspace_id=WS, source_id=sid, registry=prep)
        assert summary_after.blocking_count > 0


class TestReadinessAndExportAndConversion:
    def test_estimated_and_constant_filled_cells_are_readiness_resolved(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 5))  # rows 5, 6 blank
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=5, registry=prep,
        )
        summary = build_issue_summary(workspace_id=WS, source_id=sid, registry=prep)
        assert summary.blocking_count == 0

    def test_cleaned_export_contains_the_estimated_numeric_value_not_a_blank(self):
        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep, mode=EXPORT_MODE_DATA_ONLY)
        import csv as csv_module
        rows = list(csv_module.reader(io.StringIO(result.content.decode("utf-8"))))
        # Row 5 (0-based data row 4, header at row 0) carries the estimated value (hold-last of row 4 = 3.0).
        assert rows[5][1] == "3.0"

    def test_conversion_treats_estimated_value_as_an_ordinary_finite_sample_never_a_gap(self):
        prep = PreparationSessionRegistry()
        ws_registry = WorkspaceRegistry()
        sid = _gap_source(prep, missing_rows=(4,))
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        metadata = convert_preparation_source(
            workspace_id=WS, source_id=sid, preparation_registry=prep, workspace_registry=ws_registry,
        )
        active = ws_registry.get(WS, metadata.source_id)
        column_name = active.record.analog_channel_names()[0]
        values = list(active.record.waveform_data[column_name])
        assert all(math.isfinite(v) for v in values)  # never NaN/None -- no waveform gap


class TestModifiedCellVisualState:
    def test_estimated_and_constant_fill_are_distinguishable_in_the_preview(self):
        from app.services.preparation_preview_service import preview_preparation_source

        prep = PreparationSessionRegistry()
        sid = _gap_source(prep, missing_rows=(4, 8))  # rows 5 and 9 blank, independent gaps
        apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_HOLD_LAST, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=5, registry=prep,
        )
        apply_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, constant_value=0.0, registry=prep)

        preview = preview_preparation_source(workspace_id=WS, source_id=sid, offset=0, limit=20, registry=prep)
        modified_by_row = {row.row_number: row.modified_cells for row in preview.rows if row.modified_cells}
        estimated_cell = next(c for c in modified_by_row[5] if c.column_index == 1)
        filled_cell = next(c for c in modified_by_row[9] if c.column_index == 1)
        assert estimated_cell.is_estimated is True
        assert estimated_cell.is_constant_fill is False
        assert filled_cell.is_constant_fill is True
        assert filled_cell.is_estimated is False


class TestMixedMissingAndInvalidGap:
    """Owner hardening pass (2026-09-10): a contiguous non-finite gap that
    mixes `waveform_value_missing` and `waveform_value_invalid` members
    (e.g. blank / unparseable-text / blank) is ONE mathematical unit for
    estimation -- selecting or scoping from EITHER issue type must
    resolve the WHOLE gap, never leave a partial hole. Constant Value, by
    contrast, is not gap-based and stays strictly scoped to the requested
    issue type."""

    def test_single_cell_linear_from_first_blank_resolves_the_full_mixed_gap(self):
        prep = PreparationSessionRegistry()
        sid = _mixed_gap_source(prep)  # rows 5 (blank), 6 (invalid "abc"), 7 (blank)

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=5, registry=prep,
        )
        # Only ONE cell (row 5) was actually clicked/requested...
        assert preview.matching_count == 1
        # ...but the true affected scope is the full 3-row mixed gap.
        assert preview.affected_count == 3
        assert preview.eligible_count == 3
        assert preview.unresolved_count == 0

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=5, registry=prep,
        )
        assert result.matching_count == 1
        assert result.affected_count == 3
        assert result.applied_count == 3

        session = prep.get(WS, sid)
        for row_number, expected in ((5, 4.0), (6, 5.0), (7, 6.0)):
            override = session.working_overlay.cell_overrides[(None, row_number, 1)]
            assert override.kind == OVERRIDE_KIND_ESTIMATED
            assert float(override.value) == pytest.approx(expected)

        # ONE grouped history action -- a single Undo restores blank/invalid/blank exactly.
        assert undo_working_change(workspace_id=WS, source_id=sid, registry=prep).can_redo is True
        assert all((None, rn, 1) not in session.working_overlay.cell_overrides for rn in (5, 6, 7))
        summary = build_issue_summary(workspace_id=WS, source_id=sid, registry=prep)
        # Still blocking -- row 6 is unresolved-invalid again, rows 5/7 unresolved-missing again.
        assert summary.blocking_count > 0

    def test_bulk_estimate_from_missing_group_reports_matching_and_affected_counts(self):
        prep = PreparationSessionRegistry()
        sid = _mixed_gap_source(prep)  # rows 5 (blank), 6 (invalid), 7 (blank)

        preview = preview_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        # Bulk scoped to the MISSING issue type alone would match just rows 5 & 7...
        assert preview.matching_count == 2
        # ...but the algorithmic gap-based scope is the full 3-row mixed gap.
        assert preview.affected_count == 3

        result = apply_estimate(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING,
            method=ESTIMATION_METHOD_LINEAR, max_gap_value=3, max_gap_unit="samples",
            local_mean_radius=None, target_row_number=None, registry=prep,
        )
        assert result.matching_count == 2
        assert result.affected_count == 3
        assert result.applied_count == 3
        session = prep.get(WS, sid)
        assert all((None, rn, 1) in session.working_overlay.cell_overrides for rn in (5, 6, 7))

    def test_constant_value_from_missing_group_does_not_fill_the_invalid_member(self):
        prep = PreparationSessionRegistry()
        sid = _mixed_gap_source(prep)  # rows 5 (blank), 6 (invalid), 7 (blank)

        preview = preview_bulk_constant_fill(workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, registry=prep)
        # Strictly issue-scoped -- NOT gap-based -- so only rows 5 & 7.
        assert preview.eligible_count == 2

        result = apply_bulk_constant_fill(
            workspace_id=WS, source_id=sid, column_index=1, issue_code=MISSING, constant_value=0.0, registry=prep,
        )
        assert result.applied_count == 2
        session = prep.get(WS, sid)
        for rn in (5, 7):
            override = session.working_overlay.cell_overrides[(None, rn, 1)]
            assert override.kind == OVERRIDE_KIND_CONSTANT_FILL

        # Row 6 (invalid, "abc") is NOT touched -- locks the gap-based-
        # estimation vs issue-scoped-constant-fill distinction.
        assert (None, 6, 1) not in session.working_overlay.cell_overrides
        summary = build_issue_summary(workspace_id=WS, source_id=sid, registry=prep)
        assert summary.blocking_count > 0  # row 6 still blocking
