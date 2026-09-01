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
    DIAGNOSTIC_AMBIGUOUS_DATE_ORDER,
    FAMILY_ABSOLUTE,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_ABSOLUTE_DATETIME,
    INTERPRETER_ID_MANUAL,
    INTERPRETER_ID_SPLIT_DATE_TIME,
    INTERPRETER_ID_UNSUPPORTED,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
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
from app.services.preparation_preview_service import preview_preparation_source
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import (
    _INTERPRETERS,
    clear_time_axis_configuration,
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
        # column_count>=1 and Slice 8A's own absolute_datetime/
        # split_date_time also accept 1/2 columns respectively, so all
        # three have to be out of the way, not just `manual`.
        monkeypatch.setitem(_INTERPRETERS, "fake", _NeverAccepts())
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_MANUAL)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_ABSOLUTE_DATETIME)
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_SPLIT_DATE_TIME)

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
        source_id = _add_csv(registry, b"31/08/2026,13:09:44.305\n30/08/2026,13:09:45.505\n")
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
