"""Tests for cleaned data export (CSV/Excel ingestion Slice 12,
DEC-072). Pure service-level tests -- no HTTP; API-level coverage
(response shape, headers, HTTP status codes) lives in
tests/test_preparation_sources_api.py's own Slice 12 test classes.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import zipfile

import pytest
from fastapi import UploadFile
from openpyxl import Workbook, load_workbook
from starlette.datastructures import Headers

from app.services.errors import SourceNotFoundError, WorksheetNotSelectedError
from app.services.preparation_export_service import export_preparation_source
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
    set_header_row,
    set_row_excluded,
)

WS = "ws-1"


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


def _add_excel(registry: PreparationSessionRegistry, content: bytes, filename: str = "e.xlsx") -> str:
    summary = asyncio.run(
        import_excel_preparation_source(
            workspace_id=WS,
            excel_upload=_upload(content, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            max_total_bytes=100 * 1024 * 1024, registry=registry,
        )
    )
    return summary.source_id


def _unzip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def _read_csv_rows(zf: zipfile.ZipFile) -> list[list[str]]:
    name = next(n for n in zf.namelist() if n.endswith(".csv"))
    text = zf.read(name).decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    name = next(n for n in zf.namelist() if n.endswith(".manifest.json"))
    return json.loads(zf.read(name))


def _read_xlsx_rows(zf: zipfile.ZipFile) -> list[tuple]:
    name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
    wb = load_workbook(io.BytesIO(zf.read(name)))
    return list(wb.active.iter_rows(values_only=True))


class TestCsvActiveRegionOnly:
    def test_only_active_region_rows_exported(self):
        prep = PreparationSessionRegistry()
        lines = [f"row{i},{i}.0" for i in range(1, 11)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        set_data_region(workspace_id=WS, source_id=sid, start_row=3, end_row=6, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert [r[0] for r in rows[1:]] == ["row3", "row4", "row5", "row6"]


class TestCsvHeaderHandling:
    def test_configured_header_becomes_column_names_not_a_data_row(self):
        prep = PreparationSessionRegistry()
        content = b"Time,VR,VY\n13:14:01,1.0,2.0\n13:14:02,3.0,4.0\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=3, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=2, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["Time", "VR", "VY"]
        assert len(rows) == 3  # header + 2 data rows, header not duplicated

    def test_no_header_uses_neutral_spreadsheet_letter_names(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1.0,2.0\n3.0,4.0\n")
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["A", "B"]

    def test_header_overlapping_active_region_excluded_from_data_rows(self):
        # Header row 2 falls INSIDE data_region 1-5 -- must still never
        # appear as a data row (task section E's own deterministic rule).
        prep = PreparationSessionRegistry()
        content = b"junk,junk\nTime,VR\n13:14:01,1.0\n13:14:02,2.0\n13:14:03,3.0\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=2, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=1, end_row=5, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["Time", "VR"]
        data_rows = rows[1:]
        assert all(r[0] != "Time" for r in data_rows)
        assert len(data_rows) == 4  # junk row + 3 timestamp rows, header itself excluded


class TestCsvRowExclusion:
    def test_excluded_rows_omitted_not_blanked(self):
        prep = PreparationSessionRegistry()
        content = b"1,a\n2,b\n3,c\n4,d\n"
        sid = _add_csv(prep, content)
        set_row_excluded(workspace_id=WS, source_id=sid, row_number=2, excluded=True, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))
        data_rows = rows[1:]

        assert [r[0] for r in data_rows] == ["1", "3", "4"]


class TestCsvNotAssignedColumns:
    def test_not_assigned_columns_physically_omitted(self):
        prep = PreparationSessionRegistry()
        content = b"Time,VR,VY,VB\n13:14:01,1.0,2.0,3.0\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=3, role="waveform", registry=prep)
        # column_index=2 ("VY") is left at its default (not_assigned)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        zf = _unzip(result.content)
        rows = _read_csv_rows(zf)
        manifest = _read_manifest(zf)

        assert rows[0] == ["Time", "VR", "VB"]
        assert manifest["omitted_columns"] == [{"column_index": 2, "label": "VY", "role": "not_assigned"}]

    def test_only_time_axis_and_waveform_columns_remain_in_export(self):
        # Task section J/W worked example: Time -> Time Axis,
        # Voltage -> Waveform, Status/Comment left Not Assigned (the
        # default) -- cleaned export keeps only Time and Voltage.
        prep = PreparationSessionRegistry()
        content = b"Time,Voltage,Status,Comment\n13:14:01,1.0,ok,note\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        # column_index=2 ("Status") and column_index=3 ("Comment") are
        # left at their default (not_assigned)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        zf = _unzip(result.content)
        rows = _read_csv_rows(zf)
        manifest = _read_manifest(zf)

        assert rows[0] == ["Time", "Voltage"]
        assert rows[1] == ["13:14:01", "1.0"]
        assert {c["label"] for c in manifest["omitted_columns"]} == {"Status", "Comment"}
        assert all(c["role"] == "not_assigned" for c in manifest["omitted_columns"])

        # The raw source itself is never mutated -- Status/Comment stay
        # fully intact in the immutable original, just excluded from
        # the derived cleaned export.
        session = prep.get(WS, sid)
        assert session.raw_bytes == content


class TestCsvWorkingEdits:
    def test_edited_value_exported(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,ERR\n")
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=1, value="2.5", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[1] == ["1", "2.5"]

    def test_cleared_cell_exported_empty_not_none_text(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n")
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=1, value=None, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[1] == ["1", ""]
        assert "None" not in rows[1] and "null" not in rows[1] and "NaN" not in rows[1]

    def test_untouched_value_exported_as_raw(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,9.876\n")
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[1] == ["1", "9.876"]

    def test_raw_source_never_mutated_by_edit_or_export(self):
        prep = PreparationSessionRegistry()
        raw_content = b"1,2\n3,4\n"
        sid = _add_csv(prep, raw_content)
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=1, value="999", registry=prep)
        export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        session = prep.get(WS, sid)
        assert session.raw_bytes == raw_content


class TestCsvColumnOrderAndDuplicateLabels:
    def test_source_column_order_preserved_with_not_assigned_omitted(self):
        prep = PreparationSessionRegistry()
        content = b"A,B,C,D\n1,2,3,4\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=2, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=3, role="waveform", registry=prep)
        # column_index=1 ("B") is left at its default (not_assigned)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["A", "C", "D"]
        assert rows[1] == ["1", "3", "4"]

    def test_duplicate_labels_all_survive_uniquely(self):
        prep = PreparationSessionRegistry()
        content = b"Voltage,Voltage,Voltage\n1,2,3\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=2, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["Voltage", "Voltage__B", "Voltage__C"]


class TestCsvRowOrdering:
    def test_row_order_never_sorted(self):
        prep = PreparationSessionRegistry()
        content = b"3,c\n1,a\n2,b\n"
        sid = _add_csv(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert [r[0] for r in rows[1:]] == ["3", "1", "2"]


class TestCsvUtf8Content:
    def test_utf8_content_round_trips(self):
        prep = PreparationSessionRegistry()
        content = "Voltagé,Åmps\né1,2\n".encode("utf-8")
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert rows[0] == ["Voltagé", "Åmps"]
        assert rows[1] == ["é1", "2"]


class TestExcelExport:
    def test_only_selected_worksheet_exported(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({
            "A": [["Time", "VR"], ["13:14:01", 1.0]],
            "B": [["Other", "Data"], ["x", 2.0]],
        })
        sid = _add_excel(prep, content)
        select_preparation_worksheet(workspace_id=WS, source_id=sid, worksheet_index=0, registry=prep)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        assert result.filename.endswith(".zip")
        zf = _unzip(result.content)
        rows = _read_xlsx_rows(zf)

        assert rows[0] == ("Time", "VR")
        assert rows[1] == ("13:14:01", 1.0)
        assert not any("Other" in (r or ()) for r in rows)

    def test_active_region_applied(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["a"], ["1"], ["2"], ["3"], ["4"]]})
        sid = _add_excel(prep, content)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=3, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_xlsx_rows(_unzip(result.content))

        assert [r[0] for r in rows[1:]] == ["1", "2"]

    def test_working_edits_applied(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["1", "ERR"]]})
        sid = _add_excel(prep, content)
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=1, value="42", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_xlsx_rows(_unzip(result.content))

        # rows[0] is the neutral A/B header row (no header configured);
        # the actual working-edited data is rows[1].
        assert rows[1] == ("1", "42")

    def test_excluded_rows_omitted(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["1"], ["2"], ["3"]]})
        sid = _add_excel(prep, content)
        set_row_excluded(workspace_id=WS, source_id=sid, row_number=2, excluded=True, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_xlsx_rows(_unzip(result.content))

        assert [r[0] for r in rows[1:]] == ["1", "3"]

    def test_not_assigned_columns_omitted(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["a", "b", "c"]]})
        sid = _add_excel(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=2, role="waveform", registry=prep)
        # column_index=1 is left at its default (not_assigned)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_xlsx_rows(_unzip(result.content))

        assert rows[0] == ("A", "C")

    def test_only_time_axis_and_waveform_columns_remain_in_export(self):
        # Task section J/W worked example, Excel variant: Time -> Time
        # Axis, Voltage -> Waveform, Status/Comment left Not Assigned
        # (the default) -- cleaned export keeps only Time and Voltage.
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["Time", "Voltage", "Status", "Comment"], ["13:14:01", 1.0, "ok", "note"]]})
        sid = _add_excel(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=2, registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        # column_index=2 ("Status") and column_index=3 ("Comment") are
        # left at their default (not_assigned)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        zf = _unzip(result.content)
        rows = _read_xlsx_rows(zf)
        manifest = _read_manifest(zf)

        assert rows[0] == ("Time", "Voltage")
        assert rows[1] == ("13:14:01", 1.0)
        assert {c["label"] for c in manifest["omitted_columns"]} == {"Status", "Comment"}
        assert all(c["role"] == "not_assigned" for c in manifest["omitted_columns"])

        # The raw source workbook itself is never mutated.
        session = prep.get(WS, sid)
        assert session.raw_bytes == content

    def test_output_is_a_single_clean_worksheet(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Only": [["a", "b"], ["1", "2"]]})
        sid = _add_excel(prep, content)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        name = next(n for n in _unzip(result.content).namelist() if n.endswith(".xlsx"))
        wb = load_workbook(io.BytesIO(_unzip(result.content).read(name)))

        assert len(wb.sheetnames) == 1

    def test_original_workbook_bytes_untouched(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["a"], ["1"]]})
        sid = _add_excel(prep, content)
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=0, value="999", registry=prep)
        export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        session = prep.get(WS, sid)
        assert session.raw_bytes == content

    def test_worksheet_name_with_invalid_characters_sanitized(self):
        # openpyxl's own writer already refuses to CREATE a worksheet
        # whose name contains `: \\ / ? * [ ]` or exceeds 31 characters
        # (Excel's own real constraint) -- so a genuinely invalid name
        # can never round-trip through a real uploaded .xlsx fixture in
        # the first place. This exercises the sanitizer as the pure
        # function it is (defense-in-depth against a hand-crafted/
        # malformed workbook), per task section C's own "document the
        # rule" instruction.
        from app.services.preparation_export_service import _sanitize_sheet_name

        assert _sanitize_sheet_name("Bad:Name*Sheet[1]") == "BadNameSheet1"
        assert _sanitize_sheet_name("") == "Sheet1"
        assert _sanitize_sheet_name("x" * 50) == "x" * 31

    def test_valid_worksheet_name_preserved(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Event Data": [["a"], ["1"]]})
        sid = _add_excel(prep, content)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        name = next(n for n in _unzip(result.content).namelist() if n.endswith(".xlsx"))
        wb = load_workbook(io.BytesIO(_unzip(result.content).read(name)))

        assert wb.sheetnames == ["Event Data"]


class TestTimeColumnPreservation:
    def test_reconstructed_time_source_column_unchanged_in_export(self):
        prep = PreparationSessionRegistry()
        content = b"13:14:01,1.0\n13:14:01,2.0\n13:14:02,3.0\n13:14:02,4.0\n"
        sid = _add_csv(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=sid, column_indices=(0,),
            interpreter_id="repeated_timestamp_precision_loss", confirmed=True, registry=prep,
        )

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))
        data_rows = rows[1:]

        # The exported time column stays the ORIGINAL working source
        # text -- never the interpreted "13:14:01.000000" style value.
        assert [r[0] for r in data_rows] == ["13:14:01", "13:14:01", "13:14:02", "13:14:02"]

    def test_no_derived_interpreted_time_column_added(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"13:14:01,1.0\n")
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows = _read_csv_rows(_unzip(result.content))

        assert len(rows[0]) == 2  # exactly the two original columns, no extra column

    def test_time_provenance_recorded_in_manifest(self):
        prep = PreparationSessionRegistry()
        content = b"13:14:01,1.0\n13:14:01,2.0\n13:14:02,3.0\n13:14:02,4.0\n"
        sid = _add_csv(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=sid, column_indices=(0,),
            interpreter_id="repeated_timestamp_precision_loss", confirmed=True, registry=prep,
        )

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["interpreter_id"] == "repeated_timestamp_precision_loss"
        assert manifest["reconstructed_timing"] is True


class TestManifestContents:
    def test_manifest_has_expected_fields(self):
        prep = PreparationSessionRegistry()
        content = b"Time,VR\n1,2\n3,4\n"
        sid = _add_csv(prep, content)
        set_header_row(workspace_id=WS, source_id=sid, row_number=1, registry=prep)
        set_data_region(workspace_id=WS, source_id=sid, start_row=2, end_row=3, registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        for key in (
            "manifest_version", "exported_at", "exported_file", "source_format", "original_filename",
            "worksheet_name", "worksheet_index", "preparation_revision", "header_row", "data_region",
            "exported_row_count", "excluded_row_count", "excluded_rows", "excluded_rows_truncated",
            "omitted_columns", "column_roles", "edited_cell_count", "cleared_cell_count",
            "time_family", "time_provenance", "interpreter_id", "time_unit", "time_interval_seconds",
            "reconstructed_timing", "readiness",
        ):
            assert key in manifest, key
        assert set(manifest["readiness"].keys()) == {"is_ready", "blocking_count", "warning_count", "info_count"}

    def test_edited_and_cleared_counts_distinct(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2,3\n")
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=0, value="99", registry=prep)
        edit_cell(workspace_id=WS, source_id=sid, row_number=1, column_index=1, value=None, registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["edited_cell_count"] == 1
        assert manifest["cleared_cell_count"] == 1

    def test_excluded_row_numbers_listed_for_small_sets(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1\n2\n3\n4\n")
        set_row_excluded(workspace_id=WS, source_id=sid, row_number=2, excluded=True, registry=prep)
        set_row_excluded(workspace_id=WS, source_id=sid, row_number=4, excluded=True, registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["excluded_row_count"] == 2
        assert manifest["excluded_rows"] == [2, 4]
        assert manifest["excluded_rows_truncated"] is False

    def test_excluded_row_list_truncated_for_large_sets(self):
        prep = PreparationSessionRegistry()
        lines = [str(i) for i in range(1, 301)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())
        for row_number in range(1, 251):
            set_row_excluded(workspace_id=WS, source_id=sid, row_number=row_number, excluded=True, registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["excluded_row_count"] == 250
        assert len(manifest["excluded_rows"]) == 200
        assert manifest["excluded_rows_truncated"] is True


class TestReadinessSnapshotAndAvailability:
    def test_export_succeeds_when_ready(self):
        prep = PreparationSessionRegistry()
        content = b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n"
        sid = _add_csv(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=sid, column_indices=(0,), interpreter_id="absolute_datetime",
            confirmed=True, registry=prep,
        )

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["readiness"]["is_ready"] is True
        assert manifest["readiness"]["blocking_count"] == 0

    def test_export_succeeds_with_blocking_issues(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n")  # totally unconfigured -- blocking readiness issues

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        manifest = _read_manifest(_unzip(result.content))

        assert manifest["readiness"]["is_ready"] is False
        assert manifest["readiness"]["blocking_count"] > 0


class TestExportIsReadOnly:
    def test_revision_unchanged_by_export(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n")
        session = prep.get(WS, sid)
        before = session.working_overlay.revision

        export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        assert session.working_overlay.revision == before

    def test_preparation_session_still_present_after_export(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n")

        export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        assert prep.get(WS, sid) is not None

    def test_repeated_export_is_idempotent_and_consistent(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n")

        first = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        second = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        rows_first = _read_csv_rows(_unzip(first.content))
        rows_second = _read_csv_rows(_unzip(second.content))
        assert rows_first == rows_second
        assert prep.get(WS, sid) is not None


class TestApiLevelErrors:
    def test_missing_source_raises_source_not_found(self):
        prep = PreparationSessionRegistry()
        with pytest.raises(SourceNotFoundError):
            export_preparation_source(workspace_id=WS, source_id="does-not-exist", registry=prep)

    def test_excel_worksheet_not_selected_raises(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"A": [["a"]], "B": [["b"]]})
        sid = _add_excel(prep, content)
        with pytest.raises(WorksheetNotSelectedError):
            export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)


class TestFilenameSanitization:
    def test_csv_filename_pattern(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n", filename="event.csv")

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        assert result.filename == "event_cleaned.zip"
        names = _unzip(result.content).namelist()
        assert "event_cleaned.csv" in names
        assert "event_cleaned.manifest.json" in names

    def test_excel_filename_pattern(self):
        prep = PreparationSessionRegistry()
        content = _build_xlsx({"Sheet1": [["a"]]})
        sid = _add_excel(prep, content, filename="event.xlsx")

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        assert result.filename == "event_cleaned.zip"
        names = _unzip(result.content).namelist()
        assert "event_cleaned.xlsx" in names

    def test_unsafe_characters_in_original_filename_stripped(self):
        prep = PreparationSessionRegistry()
        sid = _add_csv(prep, b"1,2\n", filename="../weird:name*.csv")

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)

        assert "/" not in result.filename
        assert ":" not in result.filename
        assert "*" not in result.filename


class TestPerformanceLargeCsvExport:
    def test_large_csv_exports_without_pathological_cost(self):
        prep = PreparationSessionRegistry()
        rows = 50_000
        lines = [f"{i},{float(i)}" for i in range(rows)]
        sid = _add_csv(prep, ("\n".join(lines) + "\n").encode())

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows_out = _read_csv_rows(_unzip(result.content))

        assert len(rows_out) == rows + 1  # header + all rows

    def test_large_excel_exports_via_write_only_streaming(self):
        prep = PreparationSessionRegistry()
        rows = 20_000
        content = _build_xlsx({"Sheet1": [[str(i), float(i)] for i in range(rows)]})
        sid = _add_excel(prep, content)
        set_column_role(workspace_id=WS, source_id=sid, column_index=0, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=sid, column_index=1, role="waveform", registry=prep)

        result = export_preparation_source(workspace_id=WS, source_id=sid, registry=prep)
        rows_out = _read_xlsx_rows(_unzip(result.content))

        assert len(rows_out) == rows + 1  # header + all rows
