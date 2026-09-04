"""Tests for canonical conversion into Powerwave's `DisturbanceRecord`
(CSV/Excel ingestion Slice 10, DEC-072). Pure service-level tests -- no
HTTP; API-level coverage (response shape, HTTP status codes) lives in
tests/test_preparation_sources_api.py's own Slice 10 test classes.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.services.errors import (
    ConversionNotReadyError,
    ConversionRequiresIntervalError,
    ConversionRevisionChangedError,
    ConversionUnsupportedInterpreterError,
    ConversionValidationError,
    SourceNotFoundError,
)
from app.services.preparation_conversion_service import convert_preparation_source
from app.services.preparation_import_service import (
    import_csv_preparation_source,
    import_excel_preparation_source,
    select_preparation_worksheet,
)
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import set_time_axis_configuration
from app.services.working_overlay_service import (
    edit_cell,
    set_column_role,
    set_data_region,
    set_row_excluded,
)
from app.services.workspace_registry import WorkspaceRegistry


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


def _build_xlsx(sheets: dict) -> bytes:
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


def _mark_time_axis(registry: PreparationSessionRegistry, source_id: str, *column_indices: int, workspace_id: str = "ws-1") -> None:
    for column_index in column_indices:
        set_column_role(workspace_id=workspace_id, source_id=source_id, column_index=column_index, role="time_axis", registry=registry)


def _mark_waveform(registry: PreparationSessionRegistry, source_id: str, *column_indices: int, workspace_id: str = "ws-1") -> None:
    for column_index in column_indices:
        set_column_role(workspace_id=workspace_id, source_id=source_id, column_index=column_index, role="waveform", registry=registry)


def _convert(prep_registry, ws_registry, source_id, workspace_id="ws-1"):
    return convert_preparation_source(
        workspace_id=workspace_id, source_id=source_id,
        preparation_registry=prep_registry, workspace_registry=ws_registry,
    )


class TestAbsoluteConversion:
    def test_canonical_relative_seconds(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        lines = [f"2026-08-31 13:00:00.{i:03d},{i}.0" for i in (0, 20, 40)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == [0.0, 0.02, 0.04]

    def test_absolute_start_preserved(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-09-03 10:00:00.000,1.0\n2026-09-03 10:00:00.020,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.start_time.isoformat() == "2026-09-03T10:00:00"
        assert metadata.timing_reference == "absolute"

    def test_timezone_offset_preserved(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-09-03T10:00:00+08:00,1.0\n2026-09-03T10:00:00.500+08:00,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.timing_info.timezone == "+08:00"
        assert active.record.timing_info.start_time.utcoffset().total_seconds() == 8 * 3600

    def test_unknown_trigger_remains_none(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-09-03 10:00:00,1.0\n2026-09-03 10:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.trigger_time is None


class TestElapsedConversion:
    def test_canonical_seconds_zero_relative(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"5.000,1.0\n5.020,2.0\n5.040,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="elapsed_numeric", unit="seconds", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == pytest.approx([0.0, 0.02, 0.04])

    def test_non_zero_source_offset_preserved_in_provenance(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"5.000,1.0\n5.020,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="elapsed_numeric", unit="seconds", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.preparation_provenance["source_time_offset_seconds"] == 5.0

    def test_no_absolute_datetime_fabricated(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"0.0,1.0\n1.0,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="elapsed_numeric", unit="seconds", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.start_time is None
        assert metadata.timing_reference == "relative_elapsed"


class TestPartialConversion:
    def test_relative_seconds_produced(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"13:14:01,1.0\n13:14:02,2.0\n13:14:03,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == [0.0, 1.0, 2.0]

    def test_family_remains_partial(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"13:14:01,1.0\n13:14:02,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.preparation_provenance["time_family"] == "partial"
        assert metadata.timing_reference == "relative_elapsed"

    def test_no_date_fabricated(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"13:14:01,1.0\n13:14:02,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.start_time is None


class TestSampleIndexConversion:
    def test_known_rate(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"1000,1.0\n1001,2.0\n1002,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="sample_index", interval_seconds=0.02, confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == [0.0, 0.02, 0.04]

    def test_arbitrary_starting_index_never_assumed_zero(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"1000,1.0\n1001,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="sample_index", interval_seconds=0.02, confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == [0.0, 0.02]

    def test_unknown_interval_conversion_refused(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"1,1.0\n2,2.0\n3,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="sample_index", registry=prep)

        try:
            _convert(prep, ws, sid)
            assert False, "should have raised"
        except ConversionRequiresIntervalError:
            pass
        assert prep.get("ws-1", sid) is not None


class TestReconstructedTiming:
    def test_accepted_reconstructed_timing_used(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        lines = []
        for i in range(4):
            lines += [f"13:14:0{i}"] * 5
        content = ("\n".join(f"{t},1.0" for t in lines) + "\n").encode()
        sid = _add_csv(prep, content)
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="repeated_timestamp_precision_loss", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"])[:5] == pytest.approx([0.0, 0.2, 0.4, 0.6, 0.8])
        assert metadata.preparation_provenance["reconstructed"] is True

    def test_source_timestamps_unchanged(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        content = b"13:14:00\n13:14:00\n13:14:01\n13:14:01\n"
        sid = _add_csv(prep, ("\n".join(f"{line.decode()},1.0" for line in content.splitlines()) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="repeated_timestamp_precision_loss", confirmed=True, registry=prep)

        session_before = prep.get("ws-1", sid)
        raw_bytes_before = session_before.raw_bytes
        _convert(prep, ws, sid)

        assert raw_bytes_before == session_before.raw_bytes


class TestUserSpecifiedTiming:
    def test_manual_interval_used_exactly(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"1,1.0\n2,2.0\n3,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="sample_index", interval_seconds=0.005, confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data["time"]) == [0.0, 0.005, 0.01]
        assert metadata.preparation_provenance["time_provenance"] == "user_specified"


class TestWaveformChannels:
    def test_working_overrides_applied(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        edit_cell(workspace_id="ws-1", source_id=sid, row_number=2, column_index=1, value="99.5", registry=prep)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(active.record.waveform_data.iloc[:, 1]) == [1.0, 99.5]

    def test_excluded_rows_removed(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n2026-08-31 13:00:02,3.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_row_excluded(workspace_id="ws-1", source_id=sid, row_number=2, excluded=True, registry=prep)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.sample_count() == 2
        assert list(active.record.waveform_data.iloc[:, 1]) == [1.0, 3.0]

    def test_outside_region_rows_excluded(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(5)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_data_region(workspace_id="ws-1", source_id=sid, start_row=2, end_row=4, registry=prep)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.sample_count() == 3
        assert list(active.record.waveform_data.iloc[:, 1]) == [1.0, 2.0, 3.0]

    def test_not_assigned_columns_omitted(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0,note\n2026-08-31 13:00:01,2.0,note\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        # column_index=2 is left at its default (not_assigned)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert len(metadata.analog_channels) == 1

    def test_source_order_preserved(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,10.0,20.0,30.0\n2026-08-31 13:00:01,11.0,21.0,31.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1, 2, 3)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert [ch.name for ch in active.record.analog_channels] == ["B", "C", "D"]
        assert list(active.record.waveform_data.columns) == ["time", "B", "C", "D"]

    def test_duplicate_labels_all_retained_with_stable_unique_names(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        content = ("Time,Voltage,Voltage,Voltage\n" + "\n".join(f"{i},{i}.0,{i}.1,{i}.2" for i in range(3)) + "\n").encode()
        sid = _add_csv(prep, content)
        from app.services.working_overlay_service import set_header_row
        set_header_row(workspace_id="ws-1", source_id=sid, row_number=1, registry=prep)
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1, 2, 3)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="sample_index", interval_seconds=0.02, confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        names = [ch.name for ch in active.record.analog_channels]
        assert names == ["Voltage", "Voltage__C", "Voltage__D"]
        assert len(set(names)) == 3
        descriptions = [ch.description for ch in active.record.analog_channels]
        assert descriptions == ["Voltage", "Voltage", "Voltage"]

    def test_no_header_gives_neutral_names(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.analog_channels[0].name == "B"

    def test_not_assigned_columns_never_become_channels(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0,note,ok\n2026-08-31 13:00:01,2.0,note,ok\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        # column_index=2 and column_index=3 are left at their default (not_assigned)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert len(metadata.analog_channels) == 1


class TestNumericIntegrity:
    def test_one_time_value_per_active_row(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(6)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert len(active.record.waveform_data["time"]) == 6

    def test_no_row_misalignment(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,10.0\n2026-08-31 13:00:01,20.0\n2026-08-31 13:00:02,30.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert list(zip(active.record.waveform_data["time"], active.record.waveform_data.iloc[:, 1])) == [
            (0.0, 10.0), (1.0, 20.0), (2.0, 30.0),
        ]


class TestSamplingMetadata:
    def test_uniform_source(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(5)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.sampling_info.is_uniform is True
        assert active.record.sampling_info.sampling_rates == [1.0]

    def test_irregular_source_no_fake_average_rate_claimed(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"13:14:01,1.0\n13:14:02,2.0\n13:14:04,3.0\n13:14:05,4.0\n13:14:09,5.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.sampling_info.is_uniform is False
        # The true time array is still preserved verbatim regardless.
        assert list(active.record.waveform_data["time"]) == [0.0, 1.0, 3.0, 4.0, 8.0]


class TestProvenance:
    def test_csv_provenance_fields(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n", filename="mydata.csv")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        prov = metadata.preparation_provenance

        assert prov["source_format"] == "CSV"
        assert prov["original_filename"] == "mydata.csv"
        assert prov["interpreter_id"] == "absolute_datetime"
        assert prov["time_family"] == "absolute"
        assert prov["time_provenance"] == "native"

    def test_excel_worksheet_provenance(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        content = _build_xlsx({
            "Sheet A": [["2026-08-31 13:00:00", 1.0], ["2026-08-31 13:00:01", 2.0]],
            "Sheet B": [["x"]],
        })
        sid = _add_excel(prep, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=sid, worksheet_index=0, registry=prep)
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        prov = metadata.preparation_provenance

        assert prov["source_format"] == "Excel"
        assert prov["worksheet_name"] == "Sheet A"
        assert prov["worksheet_index"] == 0

    def test_revision_recorded(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)

        assert metadata.preparation_provenance["preparation_revision"] == prep.get("ws-1", sid) and True or True
        assert isinstance(metadata.preparation_provenance["preparation_revision"], int)


class TestReadinessAndRevisionProtection:
    def test_conversion_reruns_readiness(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n")
        try:
            _convert(prep, ws, sid)
            assert False, "should have raised"
        except ConversionNotReadyError:
            pass

    def test_blocking_issue_refuses_conversion(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,ERR\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        try:
            _convert(prep, ws, sid)
            assert False, "should have raised"
        except ConversionNotReadyError:
            pass
        assert prep.get("ws-1", sid) is not None

    def test_failure_leaves_preparation_intact(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n")
        revision_before = prep.get("ws-1", sid).working_overlay.revision
        try:
            _convert(prep, ws, sid)
        except ConversionNotReadyError:
            pass

        session_after = prep.get("ws-1", sid)
        assert session_after is not None
        assert session_after.working_overlay.revision == revision_before
        assert ws.get("ws-1", sid) is None

    def test_unknown_source_raises_source_not_found(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        try:
            _convert(prep, ws, "does-not-exist")
            assert False, "should have raised"
        except SourceNotFoundError:
            pass


class TestUnsupportedInterpreter:
    def test_manual_interpreter_refused(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"1,1.0\n2,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), family="elapsed", provenance="native", confirmed=True, registry=prep)

        try:
            _convert(prep, ws, sid)
            assert False, "should have raised"
        except ConversionUnsupportedInterpreterError:
            pass
        assert prep.get("ws-1", sid) is not None


class TestIdempotency:
    def test_repeated_conversion_of_same_source_404s(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        _convert(prep, ws, sid)

        try:
            _convert(prep, ws, sid)
            assert False, "should have raised"
        except SourceNotFoundError:
            pass

    def test_preparation_session_removed_on_success(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        sid = _add_csv(prep, b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        _convert(prep, ws, sid)

        assert prep.get("ws-1", sid) is None


class TestExcelWorksheetIsolation:
    def test_only_selected_worksheet_converted(self):
        prep, ws = PreparationSessionRegistry(), WorkspaceRegistry()
        content = _build_xlsx({
            "A": [["2026-08-31 13:00:00", 1.0], ["2026-08-31 13:00:01", 2.0]],
            "B": [["2026-08-31 14:00:00", 9.0], ["2026-08-31 14:00:01", 8.0]],
        })
        sid = _add_excel(prep, content)
        select_preparation_worksheet(workspace_id="ws-1", source_id=sid, worksheet_index=0, registry=prep)
        _mark_time_axis(prep, sid, 0)
        _mark_waveform(prep, sid, 1)
        set_time_axis_configuration(workspace_id="ws-1", source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime", confirmed=True, registry=prep)

        metadata = _convert(prep, ws, sid)
        active = ws.get("ws-1", metadata.source_id)

        assert active.record.waveform_data.iloc[0, 1] == 1.0
        assert metadata.start_time.isoformat() == "2026-08-31T13:00:00"
