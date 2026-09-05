"""Service-level tests for Time-Axis interpretation FRAMEWORK
orchestration (Slice 7, DEC-072).

Covers validation, worksheet resolution, column-role relationship
enforcement, and registry resolution/fallback -- the pure domain-level
shapes themselves are already covered by tests/test_time_axis_domain.py
and tests/test_working_overlay_domain.py's own TestTimeAxis class.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.domain.time_axis import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
    DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED,
    DIAGNOSTIC_CADENCE_NOT_RELIABLE,
    DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_ABSOLUTE_DATETIME,
    INTERPRETER_ID_ELAPSED_NUMERIC,
    INTERPRETER_ID_MANUAL,
    INTERPRETER_ID_REPEATED_TIMESTAMP,
    INTERPRETER_ID_SAMPLE_INDEX,
    INTERPRETER_ID_SPLIT_DATE_TIME,
    INTERPRETER_ID_UNSUPPORTED,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
    STATUS_CONFIRMED,
    STATUS_DETECTED,
    STATUS_INDEX_FALLBACK,
    STATUS_NEEDS_ATTENTION,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNCONFIGURED,
    STATUS_UNSUPPORTED,
)
from app.services.errors import (
    InvalidTimeAxisConfigurationError,
    InvalidWorkingCoordinateError,
    SourceNotFoundError,
    UnknownTimeAxisInterpreterError,
    WorksheetNotSelectedError,
)
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_preview_service import preview_preparation_source
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import (
    _INTERPRETERS,
    build_configured_time_values,
    clear_time_axis_configuration,
    configured_time_for_preview_page,
    get_time_axis_summary,
    interpret_time_axis,
    list_time_axis_interpreters,
    resolve_interpreter,
    set_time_axis_configuration,
)
from app.services.working_overlay_service import (
    redo_working_change,
    reset_all_working_changes,
    set_column_role,
    set_data_region,
    set_header_row,
    set_row_excluded,
    undo_working_change,
)


def _upload(content: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


def _add_csv(registry: PreparationSessionRegistry, content: bytes, workspace_id: str = "ws-1", filename: str = "e.csv") -> str:
    summary = asyncio.run(
        import_csv_preparation_source(
            workspace_id=workspace_id, csv_upload=_upload(content, filename, "text/csv"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


def _build_xlsx(sheets: dict | None = None) -> bytes:
    if sheets is None:
        sheets = {"Sheet1": [["a", "b"], [1, 2]]}
    workbook = Workbook()
    names = list(sheets.keys())
    workbook.active.title = names[0]
    for row in sheets[names[0]]:
        workbook.active.append(row)
    for name in names[1:]:
        ws = workbook.create_sheet(name)
        for row in sheets[name]:
            ws.append(row)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _add_excel(registry: PreparationSessionRegistry, content: bytes, workspace_id: str = "ws-1", filename: str = "e.xlsx") -> str:
    summary = asyncio.run(
        import_excel_preparation_source(
            workspace_id=workspace_id,
            excel_upload=_upload(content, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


def _mark_time_axis(registry: PreparationSessionRegistry, source_id: str, *column_indices: int) -> None:
    for column_index in column_indices:
        set_column_role(
            workspace_id="ws-1", source_id=source_id, column_index=column_index, role="time_axis", registry=registry,
        )


def _mark_waveform(registry: PreparationSessionRegistry, source_id: str, *column_indices: int) -> None:
    for column_index in column_indices:
        set_column_role(
            workspace_id="ws-1", source_id=source_id, column_index=column_index, role="waveform", registry=registry,
        )


class TestGetTimeAxisSummaryUnconfigured:
    def test_unconfigured_source_is_unconfigured(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        result = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert result.status == STATUS_UNCONFIGURED
        assert result.column_indices == ()

    def test_unknown_source_raises(self):
        registry = PreparationSessionRegistry()

        with pytest.raises(SourceNotFoundError):
            get_time_axis_summary(workspace_id="ws-1", source_id="nope", registry=registry)


class TestSetTimeAxisConfiguration:
    def test_configure_one_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.column_indices == (0,)
        assert result.interpreter_id == INTERPRETER_ID_MANUAL

    def test_configure_multiple_columns(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b,c\n1,2,3\n")
        _mark_time_axis(registry, source_id, 0, 1)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
        )

        assert result.column_indices == (0, 1)

    def test_confirmed_configuration_is_confirmed_status(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED

    def test_sample_index_with_index_only_provenance_is_index_fallback(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_INDEX_ONLY, registry=registry,
        )

        assert result.status == STATUS_INDEX_FALLBACK

    def test_empty_column_indices_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(),
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
            )

    def test_duplicate_column_indices_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0, 0),
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
            )

    def test_out_of_bounds_column_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        with pytest.raises(InvalidWorkingCoordinateError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(99,),
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
            )

    def test_column_without_time_axis_role_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        # column 0 has no role assigned at all -- not Time Axis

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
            )

    def test_unknown_family_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                family="not_a_real_family", provenance=PROVENANCE_NATIVE, registry=registry,
            )

    def test_unknown_provenance_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                family=FAMILY_ABSOLUTE, provenance="inferred", registry=registry,
            )

    def test_non_positive_interval_seconds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_INDEX_ONLY,
                interval_seconds=0.0, registry=registry,
            )

    def test_unknown_interpreter_id_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(UnknownTimeAxisInterpreterError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
                interpreter_id="does_not_exist", registry=registry,
            )


class TestColumnRoleStaleness:
    def test_role_change_away_from_time_axis_makes_configuration_unsupported(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confirmed=True, registry=registry,
        )

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        result = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result.status == STATUS_UNSUPPORTED

    def test_configuration_itself_is_not_mutated_by_a_role_change(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
        )

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        session = registry.get("ws-1", source_id)
        stored = session.working_overlay.time_axis[None]
        assert stored.column_indices == (0,)
        assert stored.family == FAMILY_ABSOLUTE


class TestClearTimeAxisConfiguration:
    def test_clear_reverts_to_unconfigured(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
        )

        result = clear_time_axis_configuration(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert result.status == STATUS_UNCONFIGURED

    def test_clear_with_none_set_is_a_safe_no_op(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")

        result = clear_time_axis_configuration(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert result.status == STATUS_UNCONFIGURED


class TestExcelWorksheetIsolation:
    def test_configuration_is_scoped_to_the_selected_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["a", "b"], [1, 2]], "B": [["c", "d"], [3, 4]]})
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, registry=registry,
        )

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_sheet_b = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert result_sheet_b.status == STATUS_UNCONFIGURED

    def test_no_worksheet_selected_raises(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["a"]], "B": [["b"]]})
        source_id = _add_excel(registry, content)

        with pytest.raises(WorksheetNotSelectedError):
            get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)


class TestRegistryResolution:
    def test_list_interpreters_includes_manual_and_unsupported(self):
        ids = list_time_axis_interpreters()

        assert INTERPRETER_ID_MANUAL in ids
        assert INTERPRETER_ID_UNSUPPORTED in ids

    def test_resolve_explicit_interpreter_id(self):
        interpreter = resolve_interpreter(column_count=1, requested_interpreter_id=INTERPRETER_ID_MANUAL)

        assert interpreter.interpreter_id == INTERPRETER_ID_MANUAL

    def test_resolve_unknown_explicit_interpreter_id_raises(self):
        with pytest.raises(UnknownTimeAxisInterpreterError):
            resolve_interpreter(column_count=1, requested_interpreter_id="ghost")

    def test_resolve_with_no_accepting_real_interpreter_falls_back_to_unsupported(self, monkeypatch):
        class _NeverAccepts:
            interpreter_id = "fake"
            needs_sample_data = False

            def accepts(self, *, column_count: int) -> bool:
                return False

            def build_configuration(self, **kwargs):
                raise AssertionError("should never be reached")

        # Every OTHER real interpreter must also be removed for this to
        # genuinely test "nothing accepts" -- `manual` accepts any
        # column_count>=1 and every Slice 8A/8B real interpreter also
        # accepts a 1-column request, so all of them have to be out of
        # the way, not just `manual`.
        monkeypatch.setitem(_INTERPRETERS, "fake", _NeverAccepts())
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_MANUAL)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_ABSOLUTE_DATETIME)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_SPLIT_DATE_TIME)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_ELAPSED_NUMERIC)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_SAMPLE_INDEX)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_REPEATED_TIMESTAMP)

        interpreter = resolve_interpreter(column_count=1, requested_interpreter_id=None)

        assert interpreter.interpreter_id == INTERPRETER_ID_UNSUPPORTED

    def test_manual_is_preferred_over_a_real_interpreter_when_none_requested(self):
        # Task's own "avoid a misleading Auto Detect" guardrail: omitting
        # interpreter_id must never silently land on absolute_datetime/
        # split_date_time, even though both also accept this column count.
        interpreter = resolve_interpreter(column_count=1, requested_interpreter_id=None)

        assert interpreter.interpreter_id == INTERPRETER_ID_MANUAL


# ---- CSV/Excel ingestion Slice 8A (DEC-072): deterministic absolute-time
# interpreters -- service-layer wiring (sample fetching, family/provenance
# override, ambiguous-confirm rejection, live diagnostics on GET, undo/
# redo, Excel isolation, data preservation). Pure parsing/detection logic
# is covered by tests/test_time_axis_interpreters.py. Every fixture below
# is headerless (no `set_header_row()` call) so row 1 is genuine sample
# data -- this matters here specifically because a header label like "t"
# would otherwise be sampled as an unparseable value.


class TestAbsoluteDatetimeSetAndGet:
    def test_unambiguous_iso_column_is_detected_native(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n2026-08-31 13:09:45.505\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_NATIVE
        assert result.options["date_order"] == "ymd"

    def test_caller_supplied_family_is_overridden_by_detection(self):
        # The interpreter's own name IS the family it produces -- a
        # caller-supplied family is only ever a hint, never trusted
        # blindly for a sample interpreter.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family="elapsed", provenance="index_only",
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_NATIVE

    def test_ambiguous_date_order_reports_review_required(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44\n03/04/2026 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.status == STATUS_REVIEW_REQUIRED
        codes = [d.code for d in result.diagnostics]
        assert DIAGNOSTIC_AMBIGUOUS_DATE_ORDER in codes

    def test_confirming_while_ambiguous_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44\n03/04/2026 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
            )

    def test_explicit_date_order_resolves_ambiguity_and_allows_confirm(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44\n03/04/2026 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, options={"date_order": "dmy"},
            confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.options["date_order"] == "dmy"

    def test_unparseable_column_reports_needs_attention(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"not-a-date\nalso-not-a-date\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.status == STATUS_NEEDS_ATTENTION

    def test_time_only_column_reports_partial_family(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:09:44.305\n13:09:45.000\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.family == FAMILY_PARTIAL

    def test_diagnostics_recomputed_live_on_every_get(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44\n03/04/2026 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        first = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        second = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert first.status == second.status == STATUS_REVIEW_REQUIRED

    def test_preview_supported_true_for_a_sample_interpreter(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert result.preview_supported is True

    def test_wrong_column_count_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44,x\n")
        _mark_time_axis(registry, source_id, 0, 1)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
                interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
            )


class TestSplitDateTimeSetAndGet:
    def test_valid_split_date_time(self):
        registry = PreparationSessionRegistry()
        # Chronologically ascending -- avoids also exercising Slice 8D's
        # own backward-time detection, covered by its own tests.
        source_id = _add_csv(registry, b"30/08/2026,13:09:44.305\n31/08/2026,13:09:45.505\n")
        _mark_time_axis(registry, source_id, 0, 1)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.family == FAMILY_ABSOLUTE
        assert result.column_indices == (0, 1)

    def test_wrong_column_count_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"31/08/2026\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, registry=registry,
            )


class TestTwoDigitYearUatFixServiceLevel:
    """UAT fix (2026-09-04): the exact owner-reported source shape,
    exercised through the real service (not just the pure interpreter
    functions already covered in test_time_axis_interpreters.py) --
    confirms readiness blocks the unresolved ambiguity and clears once
    the engineer explicitly picks a date order, and that neither the
    raw source nor the working overlay's own cell values are ever
    touched merely by that choice (task sections I/J)."""

    def test_owner_scenario_blocks_readiness_until_date_order_chosen(self):
        from app.services.preparation_issue_service import build_issue_summary

        registry = PreparationSessionRegistry()
        content = (
            b"3/6/26,18:04:00.000,1.0\n"
            b"3/6/26,18:04:00.020,2.0\n"
            b"3/6/26,18:04:00.040,3.0\n"
        )
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0, 1)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=2, role="waveform", registry=registry)

        detected = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, registry=registry,
        )
        assert detected.status == STATUS_REVIEW_REQUIRED
        assert any(d.code == DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in detected.diagnostics)

        before_issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert before_issues.is_ready is False
        assert any(i.code == "time_axis_unresolved" for i in before_issues.issues if i.severity == "blocking")

        raw_bytes_before = registry.get("ws-1", source_id).raw_bytes
        overlay_before = dict(registry.get("ws-1", source_id).working_overlay.cell_overrides)

        resolved = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": "dmy"},
            confirmed=True, registry=registry,
        )
        assert resolved.status == STATUS_CONFIRMED
        assert resolved.provenance == PROVENANCE_USER_SPECIFIED
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in resolved.diagnostics)

        after_issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after_issues.is_ready is True
        assert after_issues.blocking_count == 0

        session = registry.get("ws-1", source_id)
        assert session.raw_bytes == raw_bytes_before
        assert session.working_overlay.cell_overrides == overlay_before

    def test_dmy_and_mdy_choices_produce_the_correct_distinct_interpretations(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"3/6/26,18:04:00.000\n")
        _mark_time_axis(registry, source_id, 0, 1)

        dmy_preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": "dmy"}, registry=registry,
        )
        assert dmy_preview.preview_rows[0].interpreted == "2026-06-03T18:04:00"

        mdy_preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": "mdy"}, registry=registry,
        )
        assert mdy_preview.preview_rows[0].interpreted == "2026-03-06T18:04:00"

        resolved = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": "mdy"},
            confirmed=True, registry=registry,
        )
        assert resolved.status == STATUS_CONFIRMED
        assert resolved.options["date_order"] == "mdy"


class TestConfirmationPolicy:
    """UAT fix (2026-09-04): "Confirmed" was shown as a generic
    checkbox for EVERY sample-interpreter result, confusing the
    engineer about what was actually being accepted. Investigation
    (task section A) found the BACKEND policy already correctly
    implements the desired UX rule end to end -- `app.domain.time_axis.
    resolve_status()`'s rule 5 is the ONLY route to `review_required`
    that is gated on `confirmed`; every other route (ambiguous date
    order, missing elapsed unit, unreliable cadence) is resolved by its
    OWN dedicated choice (date_order/unit/interval), never the generic
    flag, and `set_time_axis_configuration(confirmed=False)` already
    reaches `is_ready=True` for all of them. This class is regression
    coverage LOCKING IN that pre-existing backend behavior (zero backend
    code changed by this fix) -- the actual fix is frontend-only:
    conditionally hiding the checkbox to match this already-correct
    policy. See `frontend/index.html`'s own
    `wwDataPrepTimeAxisRequiresExplicitConfirmation()` for the mirrored
    frontend-side rule."""

    def test_native_unambiguous_high_confidence_saved_without_confirmed(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305,1.0\n2026-08-31 13:09:45.505,2.0\n")
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.provenance == PROVENANCE_NATIVE
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True
        assert issues.blocking_count == 0

    def test_ambiguous_date_order_unresolved_blocks_readiness(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"3/6/26,18:04:00.000,1.0\n3/6/26,18:04:00.020,2.0\n")
        _mark_time_axis(registry, source_id, 0, 1)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=2, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, confirmed=False, registry=registry,
        )

        assert result.status == STATUS_REVIEW_REQUIRED
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is False
        assert any(i.code == "time_axis_unresolved" for i in issues.issues if i.severity == "blocking")

    @pytest.mark.parametrize("date_order,expected_iso", [("dmy", "2026-06-03T18:04:00"), ("mdy", "2026-03-06T18:04:00")])
    def test_explicit_date_order_choice_accepted_without_confirmed_flag(self, date_order, expected_iso):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"3/6/26,18:04:00.000,1.0\n3/6/26,18:04:00.020,2.0\n")
        _mark_time_axis(registry, source_id, 0, 1)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=2, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": date_order},
            confirmed=False, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert all(d.code != DIAGNOSTIC_AMBIGUOUS_DATE_ORDER for d in result.diagnostics)
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": date_order}, registry=registry,
        )
        assert preview.preview_rows[0].interpreted == expected_iso

    def test_reconstructed_suggestion_without_confirmation_stays_blocking(self):
        registry = PreparationSessionRegistry()
        lines = []
        for i in range(4):
            lines += [f"13:14:0{i}"] * 5
        content = ("\n".join(f"{t},1.0" for t in lines) + "\n").encode()
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=False, registry=registry,
        )

        assert result.status == STATUS_REVIEW_REQUIRED
        assert result.provenance == PROVENANCE_RECONSTRUCTED
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is False
        assert any(i.code == "time_axis_unresolved" for i in issues.issues if i.severity == "blocking")

    def test_reconstructed_suggestion_with_explicit_confirmation_becomes_usable(self):
        registry = PreparationSessionRegistry()
        lines = []
        for i in range(4):
            lines += [f"13:14:0{i}"] * 5
        content = ("\n".join(f"{t},1.0" for t in lines) + "\n").encode()
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True

    def test_user_entered_sample_index_interval_accepted_without_confirmed_flag(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1,1.0\n2,2.0\n3,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, interval_seconds=0.02,
            confirmed=False, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True

    def test_user_entered_elapsed_unit_accepted_without_confirmed_flag(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0.0,1.0\n0.02,2.0\n")
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="seconds",
            confirmed=False, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.provenance == PROVENANCE_USER_SPECIFIED
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True

    def test_partial_family_native_reading_does_not_require_confirmation(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:01,1.0\n13:14:02,2.0\n")
        _mark_time_axis(registry, source_id, 0)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="waveform", registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False, registry=registry,
        )

        assert result.family == FAMILY_PARTIAL
        assert result.provenance == PROVENANCE_NATIVE
        issues = build_issue_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert issues.is_ready is True


class TestInterpretTimeAxisDryRun:
    def test_dry_run_does_not_store_anything(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n")
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert preview.family == FAMILY_ABSOLUTE
        assert preview.preview_rows
        summary = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.status == STATUS_UNCONFIGURED

    def test_dry_run_preview_rows_are_bounded(self):
        registry = PreparationSessionRegistry()
        lines = "\n".join(f"2026-08-31 13:09:{i:02d}" for i in range(40))
        source_id = _add_csv(registry, (lines + "\n").encode())
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert len(preview.preview_rows) <= 20

    def test_dry_run_rejects_manual(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"x\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            interpret_time_axis(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_MANUAL, registry=registry,
            )

    def test_dry_run_rejects_unsupported(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"x\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            interpret_time_axis(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_UNSUPPORTED, registry=registry,
            )

    def test_dry_run_requires_time_axis_role(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44\n")

        with pytest.raises(InvalidTimeAxisConfigurationError):
            interpret_time_axis(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
            )

    def test_dry_run_with_explicit_date_order_shows_resolved_preview(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44\n03/04/2026 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)

        ambiguous_preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )
        assert ambiguous_preview.resolved_options["date_order"] == "auto"
        assert all(r.interpreted is None for r in ambiguous_preview.preview_rows)

        resolved_preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, options={"date_order": "dmy"}, registry=registry,
        )
        assert resolved_preview.resolved_options["date_order"] == "dmy"
        assert all(r.interpreted is not None for r in resolved_preview.preview_rows)


class TestAbsoluteDatetimeUndoRedo:
    def test_undo_reverts_configuration_and_redo_reapplies_it(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_DETECTED

    def test_reset_all_clears_absolute_datetime_configuration(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44.305\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED


class TestAbsoluteDatetimeExcelWorksheetIsolation:
    def test_configuration_and_detection_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({
            "A": [["2026-08-31 13:09:44.305"], ["2026-08-31 13:09:45.505"]],
            "B": [["not-a-date"]],
        })
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        _mark_time_axis(registry, source_id, 0)
        result_a = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )
        assert result_a.status == STATUS_DETECTED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_b = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_b.status == STATUS_UNCONFIGURED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        result_a_again = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_a_again.status == STATUS_DETECTED


class TestAbsoluteDatetimeDataPreservation:
    def test_invalid_time_row_is_retained_in_the_working_view(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44\ngarbage\n2026-08-31 13:09:46\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        raw_values = [row.cells[0] for row in preview.rows]
        assert raw_values == ["2026-08-31 13:09:44", "garbage", "2026-08-31 13:09:46"]

    def test_row_order_is_never_changed_by_detection(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:46\n2026-08-31 13:09:44\n2026-08-31 13:09:45\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        raw_values = [row.cells[0] for row in preview.rows]
        assert raw_values == ["2026-08-31 13:09:46", "2026-08-31 13:09:44", "2026-08-31 13:09:45"]

    def test_excluded_rows_are_not_sampled_but_remain_in_the_working_view(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:09:44\ngarbage\n")
        _mark_time_axis(registry, source_id, 0)
        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=2, excluded=True, registry=registry)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        # The excluded "garbage" row is skipped for detection -- only the
        # one valid ISO row remains, so detection is clean.
        assert result.status == STATUS_DETECTED
        assert result.diagnostics == []

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert [row.cells[0] for row in preview.rows] == ["2026-08-31 13:09:44", "garbage"]
        assert preview.rows[1].excluded is True


# ---- CSV/Excel ingestion Slice 8B (DEC-072): elapsed numeric time +
# sample index -- service-layer wiring. Pure detection/preview logic is
# covered by tests/test_time_axis_interpreters.py. Every fixture below
# is headerless so row 1 is genuine sample data. ----


class TestElapsedNumericSetAndGet:
    def test_no_unit_is_review_required(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        assert result.status == STATUS_REVIEW_REQUIRED
        assert result.family == FAMILY_ELAPSED

    def test_confirming_without_a_unit_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, confirmed=True, registry=registry,
            )

    def test_valid_unit_resolves_and_allows_confirm(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED
        assert result.unit == "seconds"

    def test_invalid_unit_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n1\n2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="fortnights",
                interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
            )

    # Enhancement (fixed-duration elapsed units): minutes/hours/days/weeks
    # are now valid, end to end through the real service-layer validation
    # (not just the pure interpreter function -- see
    # test_time_axis_interpreters.py's own TestElapsedNumericUnits for
    # that level).
    @pytest.mark.parametrize("unit", ["minutes", "hours", "days", "weeks"])
    def test_new_fixed_duration_units_accepted(self, unit):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n1\n2\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit=unit,
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED
        assert result.unit == unit

    # Enhancement scope boundary (task section R): months/years must
    # stay rejected -- no fixed-seconds factor exists for either, and
    # this task deliberately does not invent an approximation (e.g.
    # "30 days") for them.
    @pytest.mark.parametrize("unit", ["months", "years"])
    def test_calendar_units_remain_rejected(self, unit):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n1\n2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit=unit,
                interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
            )

    def test_manual_interpreter_unit_field_stays_open_ended(self):
        # The elapsed_numeric-specific unit-set validation must never
        # leak into `manual`'s own deliberately open-ended `unit` field.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"a,b\n1,2\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            family="elapsed", provenance="native", unit="fortnights", registry=registry,
        )

        assert result.unit == "fortnights"

    def test_backward_value_reports_needs_attention(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n2\n1\n3\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        assert result.status == STATUS_NEEDS_ATTENTION

    def test_diagnostics_recomputed_live_on_every_get(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        first = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        second = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert first.status == second.status == STATUS_REVIEW_REQUIRED

    def test_wrong_column_count_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0,x\n1,y\n")
        _mark_time_axis(registry, source_id, 0, 1)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
                interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
            )


class TestSampleIndexSetAndGet:
    def test_index_only_is_a_valid_complete_state(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert result.status == STATUS_INDEX_FALLBACK
        assert result.provenance == "index_only"
        assert result.diagnostics == []

    def test_index_only_can_be_confirmed_immediately(self):
        # Not an error, not ambiguous -- confirmable right away, unlike
        # elapsed_numeric's own missing-unit case.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, confirmed=True, registry=registry,
        )

        assert result.confirmed is True

    def test_known_interval_seconds_is_user_specified(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1001\n1002\n1003\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.0002,
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert result.status == STATUS_DETECTED
        assert result.provenance == "user_specified"
        assert result.interval_seconds == 0.0002

    def test_non_positive_interval_seconds_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.0,
                interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
            )

    def test_gap_is_reported_but_still_index_fallback_status(self):
        # index_fallback fires unconditionally on family=sample_index +
        # provenance=index_only, regardless of any OTHER diagnostic --
        # the diagnostic is still attached and inspectable either way.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n5\n6\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert result.status == STATUS_INDEX_FALLBACK
        codes = [d.code for d in result.diagnostics]
        assert "sample_index_gap" in codes

    def test_starting_index_is_never_assumed(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1001\n1002\n1003\n")
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert result.diagnostics == []  # no gap/backward false positive for a non-zero/non-one start


class TestElapsedAndSampleIndexInterpretDryRun:
    def test_dry_run_elapsed_does_not_store_anything(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="seconds", registry=registry,
        )

        assert preview.family == FAMILY_ELAPSED
        assert preview.resolved_unit == "seconds"
        assert preview.preview_rows
        summary = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.status == STATUS_UNCONFIGURED

    def test_dry_run_elapsed_invalid_unit_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n1\n2\n")
        _mark_time_axis(registry, source_id, 0)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            interpret_time_axis(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="fortnights", registry=registry,
            )

    def test_dry_run_index_only(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert preview.family == FAMILY_SAMPLE_INDEX
        assert preview.provenance == "index_only"
        assert all(r.interpreted is None for r in preview.preview_rows)

    def test_dry_run_index_with_rate(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1001\n1002\n1003\n")
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.0002,
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert preview.resolved_interval_seconds == 0.0002
        assert all(r.interpreted is not None for r in preview.preview_rows)


class TestElapsedAndSampleIndexUndoRedo:
    def test_elapsed_configuration_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        after_redo = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after_redo.unit == "seconds"

    def test_index_only_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_INDEX_FALLBACK

    def test_rate_configuration_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1001\n1002\n1003\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.0002,
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).interval_seconds is None

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).interval_seconds == 0.0002

    def test_clear_reverts_to_unconfigured(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n0.001\n0.002\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        clear_time_axis_configuration(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED


class TestElapsedAndSampleIndexExcelWorksheetIsolation:
    def test_elapsed_configuration_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({
            "A": [["0"], ["0.001"], ["0.002"]],
            "B": [["not-numeric"]],
        })
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        _mark_time_axis(registry, source_id, 0)
        result_a = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )
        assert result_a.status == STATUS_REVIEW_REQUIRED or result_a.status == STATUS_DETECTED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_b = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_b.status == STATUS_UNCONFIGURED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        result_a_again = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_a_again.unit == "seconds"


class TestElapsedAndSampleIndexDataPreservation:
    def test_original_numeric_values_never_overwritten(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n10\n20\n30\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="milliseconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert [row.cells[0] for row in preview.rows] == ["0", "10", "20", "30"]

    def test_rows_never_reordered_for_backward_elapsed_time(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0\n2\n1\n3\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), unit="seconds",
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert [row.cells[0] for row in preview.rows] == ["0", "2", "1", "3"]

    def test_sample_index_gap_never_synthesizes_a_row(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n3\n5\n6\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert [row.cells[0] for row in preview.rows] == ["1", "2", "3", "5", "6"]

    def test_repeated_sample_index_rows_never_collapsed(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1\n2\n2\n3\n")
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert [row.cells[0] for row in preview.rows] == ["1", "2", "2", "3"]


# ---- CSV/Excel ingestion Slice 8C (DEC-072): repeated timestamp /
# precision-loss reconstruction -- service-layer wiring. Pure detection/
# preview logic is covered by tests/test_time_axis_interpreters.py.
# Every fixture below is headerless. ----


def _repeated_timestamp_csv(pattern: list[int], base_hour: str = "13:14:0") -> bytes:
    lines = []
    for i, count in enumerate(pattern):
        for _ in range(count):
            lines.append(f"{base_hour}{i}")
    return ("\n".join(lines) + "\n").encode()


class TestRepeatedTimestampSetAndGet:
    def test_high_confidence_suggestion_is_review_required_until_confirmed(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert result.status == STATUS_REVIEW_REQUIRED
        assert result.provenance == PROVENANCE_RECONSTRUCTED
        assert result.confidence == CONFIDENCE_HIGH
        assert result.interval_seconds == pytest.approx(0.2)

    def test_confirming_a_high_confidence_suggestion_succeeds(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        assert result.status == STATUS_CONFIRMED
        assert result.provenance == PROVENANCE_RECONSTRUCTED

    def test_low_confidence_confirm_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 2, 8, 4]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )
        assert result.status == STATUS_REVIEW_REQUIRED
        assert result.confidence == CONFIDENCE_LOW

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
            )

    def test_manual_interval_override_uses_user_specified_provenance(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 2, 8, 4]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.25,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        assert result.provenance == PROVENANCE_USER_SPECIFIED
        assert result.interval_seconds == 0.25
        # confirmed=true succeeds even though the underlying data is
        # still irregular -- the WARNING-level finding about that stays
        # surfaced regardless (matches every other interpreter's own
        # "confirmed never suppresses a real warning" precedent).
        assert result.status == STATUS_NEEDS_ATTENTION

    def test_manual_sampling_rate_converted_by_caller(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        rate_hz = 4
        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=1 / rate_hz,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert result.interval_seconds == pytest.approx(0.25)
        assert result.provenance == PROVENANCE_USER_SPECIFIED

    def test_custom_anchor_offset_is_stored_in_options(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, options={"anchor_offset_seconds": 0.1},
            registry=registry,
        )

        assert result.options["anchor_offset_seconds"] == 0.1

    def test_diagnostics_recomputed_live_on_every_get(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        first = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        second = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert first.status == second.status == STATUS_REVIEW_REQUIRED
        assert first.interval_seconds == second.interval_seconds

    def test_absolute_datetime_source_supported(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(
            registry,
            _repeated_timestamp_csv([5, 5, 5, 5], base_hour="2026-09-02 13:14:0"),
        )
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert result.family == FAMILY_ABSOLUTE
        assert result.provenance == PROVENANCE_RECONSTRUCTED

    def test_partial_time_only_source_stays_partial(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        result = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert result.family == FAMILY_PARTIAL

    def test_wrong_column_count_is_rejected(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:01,x\n13:14:02,y\n")
        _mark_time_axis(registry, source_id, 0, 1)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            set_time_axis_configuration(
                workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
                interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
            )


class TestRepeatedTimestampInterpretDryRun:
    def test_dry_run_does_not_store_anything(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert preview.confidence == CONFIDENCE_HIGH
        assert preview.resolved_interval_seconds == pytest.approx(0.2)
        assert preview.preview_rows
        summary = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.status == STATUS_UNCONFIGURED

    def test_dry_run_high_confidence_suggestion(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        codes = [d.code for d in preview.diagnostics]
        assert DIAGNOSTIC_REPEATED_TIMESTAMP_DETECTED in codes
        assert DIAGNOSTIC_ANCHOR_ASSUMPTION_REQUIRED in codes
        assert all(r.interpreted is not None for r in preview.preview_rows)

    def test_dry_run_low_confidence_fallback(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 2, 8, 4]))
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert preview.confidence == CONFIDENCE_LOW
        assert preview.resolved_interval_seconds is None
        codes = [d.code for d in preview.diagnostics]
        assert DIAGNOSTIC_CADENCE_NOT_RELIABLE in codes
        assert all(r.interpreted is None for r in preview.preview_rows)

    def test_dry_run_manual_override(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 2, 8, 4]))
        _mark_time_axis(registry, source_id, 0)

        preview = interpret_time_axis(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.25,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        assert preview.resolved_interval_seconds == 0.25
        assert all(r.interpreted is not None for r in preview.preview_rows)

    def test_dry_run_requires_time_axis_role(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))

        with pytest.raises(InvalidTimeAxisConfigurationError):
            interpret_time_axis(
                workspace_id="ws-1", source_id=source_id, column_indices=(0,),
                interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
            )


class TestRepeatedTimestampUndoRedo:
    def test_accepted_reconstruction_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_CONFIRMED

    def test_anchor_change_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, options={"anchor_offset_seconds": 0.1},
            registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        after_undo = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after_undo.options.get("anchor_offset_seconds") == 0.0

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        after_redo = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after_redo.options.get("anchor_offset_seconds") == 0.1

    def test_manual_timing_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interval_seconds=0.25,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        summary = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert summary.interval_seconds == 0.25
        assert summary.provenance == PROVENANCE_USER_SPECIFIED

    def test_sample_index_fallback_undo_redo(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, registry=registry,
        )

        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_INDEX_FALLBACK

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        after_undo = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after_undo.interpreter_id == INTERPRETER_ID_REPEATED_TIMESTAMP

    def test_clear_reverts_to_unconfigured(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        clear_time_axis_configuration(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry).status == STATUS_UNCONFIGURED


class TestRepeatedTimestampExcelWorksheetIsolation:
    def test_isolated_per_worksheet(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({
            "A": [[v] for v in ["13:14:01"] * 5 + ["13:14:02"] * 5 + ["13:14:03"] * 5 + ["13:14:04"] * 5],
            "B": [["not-a-time"]],
        })
        source_id = _add_excel(registry, content)

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        _mark_time_axis(registry, source_id, 0)
        result_a = set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, registry=registry,
        )
        assert result_a.status == STATUS_REVIEW_REQUIRED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        result_b = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_b.status == STATUS_UNCONFIGURED

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        result_a_again = get_time_axis_summary(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert result_a_again.interval_seconds == pytest.approx(0.2)


class TestRepeatedTimestampDataPreservation:
    def test_original_timestamps_never_overwritten(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=25, registry=registry)
        values = [row.cells[0] for row in preview.rows]
        assert values == (
            ["13:14:00"] * 5 + ["13:14:01"] * 5 + ["13:14:02"] * 5 + ["13:14:03"] * 5
        )

    def test_identical_and_distinct_rows_all_preserved_no_row_count_change(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        before = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=25, registry=registry)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )
        after = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=25, registry=registry)

        assert before.total_row_count == after.total_row_count == 20

    def test_no_row_reordering(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, _repeated_timestamp_csv([5, 5, 5, 5]))
        _mark_time_axis(registry, source_id, 0)

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=25, registry=registry)
        row_numbers = [row.row_number for row in preview.rows]
        assert row_numbers == sorted(row_numbers)


class TestConfiguredTimeAbsolute:
    """UAT enhancement (2026-09-04, DEC-075): Data Preview's own
    "Configured Time" column. Task section V's own worked example."""

    def test_ambiguous_date_order_resolved_shows_iso_timestamps(self):
        registry = PreparationSessionRegistry()
        content = b"Date,Time,Voltage\n3/6/26,18:04:00.000,1.0\n3/6/26,18:04:00.020,2.0\n3/6/26,18:04:00.040,3.0\n"
        source_id = _add_csv(registry, content)
        set_header_row(workspace_id="ws-1", source_id=source_id, row_number=1, registry=registry)
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=4, registry=registry)
        _mark_time_axis(registry, source_id, 0, 1)
        _mark_waveform(registry, source_id, 2)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, options={"date_order": "dmy"}, confirmed=True,
            registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.column_name == "Time"
        assert computed.family == FAMILY_ABSOLUTE
        assert computed.values_by_row_number == {
            2: "2026-06-03T18:04:00.000", 3: "2026-06-03T18:04:00.020", 4: "2026-06-03T18:04:00.040",
        }
        # The header row itself never gets a derived value.
        assert 1 not in computed.values_by_row_number

    def test_original_source_columns_remain_untouched(self):
        registry = PreparationSessionRegistry()
        content = b"2026-08-31 13:00:00,1.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )

        build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        session = registry.get("ws-1", source_id)
        assert session.raw_bytes == content
        assert session.working_overlay.cell_overrides == {}
        # The preview's own raw/working column view is unaffected --
        # the Time Axis source column(s) are still exactly present.
        preview = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        assert preview.rows[0].cells[0] == "2026-08-31 13:00:00"


class TestConfiguredTimeMinuteResolutionAndAmPmHour:
    """Enhancement (minute/AM-PM-hour absolute time support): the exact
    owner-reported bug, verified end to end through configuration ->
    Configured Time preview, not just the pure interpreter function."""

    def test_reported_24h_minute_resolution_after_explicit_date_order(self):
        registry = PreparationSessionRegistry()
        content = b"3/6/2026 17:25,1.0\n3/6/2026 17:26,2.0\n3/6/2026 17:27,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, options={"date_order": "dmy"}, confirmed=True,
            registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.family == FAMILY_ABSOLUTE
        assert computed.values_by_row_number == {
            1: "2026-06-03T17:25:00.000", 2: "2026-06-03T17:26:00.000", 3: "2026-06-03T17:27:00.000",
        }

    def test_explicit_am_pm_hour_only(self):
        registry = PreparationSessionRegistry()
        content = b"2026-06-03 1pm,1.0\n2026-06-03 2pm,2.0\n2026-06-03 3pm,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.values_by_row_number == {
            1: "2026-06-03T13:00:00.000", 2: "2026-06-03T14:00:00.000", 3: "2026-06-03T15:00:00.000",
        }


class TestConfiguredTimeElapsed:
    def test_relative_to_first_active_row(self):
        # Task section W's own worked example.
        registry = PreparationSessionRegistry()
        content = b"5.000,1.0\n5.020,2.0\n5.040,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="seconds", confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.column_name == "Time (s)"
        assert computed.values_by_row_number == {1: "0.000", 2: "0.020", 3: "0.040"}

    def test_minutes_unit_normalizes_to_canonical_seconds(self):
        # Enhancement (fixed-duration elapsed units), task section U/X:
        # 1 elapsed minute apart -> exactly 60.000 canonical seconds
        # apart -- never approximated, never coupled to any calendar.
        registry = PreparationSessionRegistry()
        content = b"0,1.0\n1,2.0\n2,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="minutes", confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.values_by_row_number == {1: "0.000", 2: "60.000", 3: "120.000"}


class TestConfiguredTimeSampleIndex:
    def test_known_interval_produces_relative_seconds(self):
        # Task section X's own worked example.
        registry = PreparationSessionRegistry()
        content = b"100,1.0\n101,2.0\n102,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, interval_seconds=0.02, confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.values_by_row_number == {1: "0.000", 2: "0.020", 3: "0.040"}

    def test_without_interval_derived_column_absent(self):
        registry = PreparationSessionRegistry()
        content = b"100,1.0\n101,2.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, interval_seconds=None, confirmed=False, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed is None


class TestConfiguredTimeReconstructed:
    def test_unconfirmed_reconstruction_shows_no_derived_column(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i // 2:02d},{i}.0" for i in range(6)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=False, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed is None

    def test_accepted_reconstruction_shows_resolved_cadence(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i // 2:02d},{i}.0" for i in range(6)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed is not None
        values = list(computed.values_by_row_number.values())
        assert len(set(values)) == len(values)  # no longer all-identical coarse timestamps


class TestConfiguredTimePartial:
    def test_time_only_column_no_fabricated_date(self):
        registry = PreparationSessionRegistry()
        content = b"18:04:00.000,1.0\n18:04:00.020,2.0\n18:04:00.040,3.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )

        computed = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert computed.column_name == "Time (s)"
        assert computed.family == FAMILY_PARTIAL
        assert computed.values_by_row_number == {1: "0.000", 2: "0.020", 3: "0.040"}
        assert all("T" not in v for v in computed.values_by_row_number.values())


class TestConfiguredTimeUnresolvedStates:
    def test_unconfigured_time_axis_has_no_derived_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1,2\n")

        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is None

    def test_manual_interpreter_has_no_derived_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,), interpreter_id=INTERPRETER_ID_MANUAL,
            family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE, confirmed=True, registry=registry,
        )

        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is None

    def test_unresolved_ambiguity_has_no_derived_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44,1\n03/04/2026 13:09:45,2\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is None


class TestConfiguredTimePaging:
    """Task section M/Z's own critical guardrail: relative time must
    always be anchored to the TRUE first active row of the dataset,
    never merely the first row of whatever preview page is requested."""

    def test_later_page_does_not_reset_relative_time_to_zero(self):
        registry = PreparationSessionRegistry()
        rows = 500
        lines = [f"{i},{float(i)}" for i in range(rows)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, interval_seconds=0.02, confirmed=True, registry=registry,
        )

        page1 = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=0, limit=10, registry=registry)
        result1 = configured_time_for_preview_page(
            workspace_id="ws-1", source_id=source_id, page_rows=page1.rows, registry=registry,
        )
        page2 = preview_preparation_source(workspace_id="ws-1", source_id=source_id, offset=200, limit=10, registry=registry)
        result2 = configured_time_for_preview_page(
            workspace_id="ws-1", source_id=source_id, page_rows=page2.rows, registry=registry,
        )

        _, _, values1 = result1
        _, _, values2 = result2
        assert values1[0] == "0.000"
        # Row 201 (0-based offset 200) is 200 samples past the first
        # active row -- 200 * 0.02 = 4.000, NEVER reset to "0.000".
        assert values2[0] == "4.000"

    def test_excluded_row_never_shifts_other_rows_own_values(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(5)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )
        before = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=3, excluded=True, registry=registry)
        after = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert 3 not in after.values_by_row_number
        # Row 4's own value is unchanged by row 3's exclusion -- never
        # silently re-indexed/compressed (task section N).
        assert after.values_by_row_number[4] == before.values_by_row_number[4]


class TestConfiguredTimeStateRefresh:
    def test_save_produces_a_derived_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1\n")
        _mark_time_axis(registry, source_id, 0)
        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is None

        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )

        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is not None

    def test_clear_removes_the_derived_column(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )
        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is not None

        clear_time_axis_configuration(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry) is None

    def test_source_cell_override_updates_derived_values(self):
        from app.services.working_overlay_service import edit_cell

        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )
        before = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert before.values_by_row_number[1] == "2026-08-31T13:00:00.000"

        edit_cell(workspace_id="ws-1", source_id=source_id, row_number=1, column_index=0, value="2026-08-31 14:00:00", registry=registry)

        after = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert after.values_by_row_number[1] == "2026-08-31T14:00:00.000"


class TestConfiguredTimeConsistencyWithExport:
    """Task section U: preview's own configured time, cleaned export's
    own configured time, and canonical conversion's own canonical time
    must all agree for the same preparation revision."""

    def test_absolute_matches_export_and_conversion(self):
        from app.services.preparation_export_service import EXPORT_MODE_WITH_PROVENANCE, export_preparation_source
        from app.services.preparation_conversion_service import convert_preparation_source
        from app.services.workspace_registry import WorkspaceRegistry
        import io as _io
        import zipfile as _zipfile

        registry = PreparationSessionRegistry()
        content = b"2026-08-31 13:00:00.000,1.0\n2026-08-31 13:00:00.020,2.0\n"
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )

        preview_values = build_configured_time_values(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert preview_values.values_by_row_number[2] == "2026-08-31T13:00:00.020"

        export_result = export_preparation_source(
            workspace_id="ws-1", source_id=source_id, registry=registry, mode=EXPORT_MODE_WITH_PROVENANCE,
        )
        zf = _zipfile.ZipFile(_io.BytesIO(export_result.content))
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        export_rows = zf.read(csv_name).decode("utf-8").strip().splitlines()
        assert export_rows[2] == "2026-08-31T13:00:00.020,2.0"

        workspace_registry = WorkspaceRegistry()
        metadata = convert_preparation_source(
            workspace_id="ws-1", source_id=source_id, preparation_registry=registry, workspace_registry=workspace_registry,
        )
        active = workspace_registry.get("ws-1", metadata.source_id)
        # Canonical time is relative-seconds-from-first-row; the preview/
        # export's own second row (0.020s after the first) must agree.
        assert active.record.waveform_data["time"].iloc[1] == pytest.approx(0.020)
