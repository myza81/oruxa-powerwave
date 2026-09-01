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
    FAMILY_ABSOLUTE,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_MANUAL,
    INTERPRETER_ID_UNSUPPORTED,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    STATUS_CONFIRMED,
    STATUS_DETECTED,
    STATUS_INDEX_FALLBACK,
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
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import (
    _INTERPRETERS,
    clear_time_axis_configuration,
    get_time_axis_summary,
    list_time_axis_interpreters,
    resolve_interpreter,
    set_time_axis_configuration,
)
from app.services.working_overlay_service import set_column_role


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

            def accepts(self, *, column_count: int) -> bool:
                return False

            def build_configuration(self, **kwargs):
                raise AssertionError("should never be reached")

        monkeypatch.setitem(_INTERPRETERS, "fake", _NeverAccepts())
        monkeypatch.delitem(_INTERPRETERS, INTERPRETER_ID_MANUAL)

        interpreter = resolve_interpreter(column_count=1, requested_interpreter_id=None)

        assert interpreter.interpreter_id == INTERPRETER_ID_UNSUPPORTED
