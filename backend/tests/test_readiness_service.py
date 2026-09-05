"""Tests for the Full Powerwave Readiness Validator (CSV/Excel ingestion
Slice 9, DEC-072). Pure service-level tests -- no HTTP; API-level
readiness coverage (is_ready/counts/location on the wire) lives in
tests/test_preparation_sources_api.py's own Slice 9 test classes.
"""

from __future__ import annotations

import asyncio
import io

from fastapi import UploadFile
from openpyxl import Workbook
from starlette.datastructures import Headers

from app.domain.preparation_issue import (
    ISSUE_PARTIAL_TIME_REFERENCE,
    ISSUE_RECONSTRUCTED_TIME,
    ISSUE_SAMPLE_INDEX_FALLBACK,
    ISSUE_TIME_AXIS_UNCONFIGURED,
    ISSUE_TIME_AXIS_UNRESOLVED,
    ISSUE_TIME_AXIS_UNSUPPORTED,
    ISSUE_TIME_VALUE_INVALID,
    ISSUE_TIME_VALUE_MISSING,
    ISSUE_USER_SPECIFIED_TIME,
    ISSUE_WAVEFORM_CHANNEL_MISSING,
    ISSUE_WAVEFORM_VALUE_INVALID,
    ISSUE_WAVEFORM_VALUE_MISSING,
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
)
from app.services.preparation_import_service import import_csv_preparation_source, import_excel_preparation_source
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import set_time_axis_configuration
from app.services.working_overlay_service import (
    redo_working_change,
    reset_all_working_changes,
    set_column_engineering_quantity,
    set_column_role,
    set_data_region,
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


def _issues(registry: PreparationSessionRegistry, source_id: str, workspace_id: str = "ws-1"):
    return build_issue_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)


def _codes(summary):
    return {i.code for i in summary.issues}


def _by_code(summary, code):
    return next(i for i in summary.issues if i.code == code)


# A stable, ready-except-for-whatever-is-under-test baseline: an
# absolute-datetime column confirmed clean, plus a numeric waveform
# column -- most tests below start from this and break exactly ONE
# thing.
def _ready_source(registry: PreparationSessionRegistry, *, rows: int = 5) -> str:
    lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(rows)]
    source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
    _mark_time_axis(registry, source_id, 0)
    _mark_waveform(registry, source_id, 1)
    set_time_axis_configuration(
        workspace_id="ws-1", source_id=source_id, column_indices=(0,),
        interpreter_id="absolute_datetime", confirmed=True, registry=registry,
    )
    return source_id


class TestStructureBlocking:
    def test_no_time_axis_columns_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1,2\n3,4\n")
        _mark_waveform(registry, source_id, 0, 1)

        summary = _issues(registry, source_id)

        assert ISSUE_TIME_AXIS_UNCONFIGURED in _codes(summary)
        assert summary.is_ready is False

    def test_no_waveform_channels_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1\n")
        _mark_time_axis(registry, source_id, 0)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)

        assert ISSUE_WAVEFORM_CHANNEL_MISSING in _codes(summary)
        assert summary.is_ready is False

    def test_stale_time_axis_role_reference_is_unsupported_and_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="waveform", registry=registry)

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_AXIS_UNSUPPORTED in _codes(summary)
        assert summary.is_ready is False

    def test_fully_ready_source_has_zero_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)

        summary = _issues(registry, source_id)

        assert summary.blocking_count == 0
        assert summary.is_ready is True

    def test_many_not_assigned_columns_never_block_or_warn(self):
        # UAT fix (2026-09-04) Section X regression: 10 total columns
        # (1 Time Axis, 2 Waveform, 7 left at their default Not
        # Assigned) -- readiness must be True, and none of the 7
        # unassigned columns may produce a blocking, warning, or info
        # finding merely for being Not Assigned.
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d}," + ",".join(str(i + j) for j in range(9)) for i in range(5)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1, 2)
        # column_index 3-9 (7 columns) are left at their default (not_assigned)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)

        assert summary.is_ready is True
        assert summary.blocking_count == 0
        # None of the 7 not_assigned columns (3-9) contribute any finding
        # at all -- every issue present, if any, locates to the time
        # axis or one of the two waveform columns only.
        for issue in summary.issues:
            assert issue.location is None or issue.location.column_index in (None, 0, 1, 2)
        assert "column_roles_unassigned" not in _codes(summary)


class TestTimeAxisBlocking:
    def test_unresolved_ambiguous_date_order_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"01/02/2026 13:09:44,1.0\n03/04/2026 13:09:45,2.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_AXIS_UNRESOLVED in _codes(summary)
        assert summary.is_ready is False

    def test_unsupported_interpreter_state_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=0, role="not_assigned", registry=registry)

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_AXIS_UNSUPPORTED in _codes(summary)

    def test_missing_time_value_across_full_region_is_blocking(self):
        registry = PreparationSessionRegistry()
        # Row 4 (0-indexed within the 8-row body) has NO time value at
        # all -- well outside the interpreter's own bounded 50-row
        # sample would still catch this on a small file, so use a
        # value the bounded sample WOULD still see to prove the
        # dedicated full-region path (not the interpreter's own
        # sample-based diagnostic) is what is firing.
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[4] = ",5.0"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_VALUE_MISSING in _codes(summary)
        assert summary.is_ready is False

    def test_invalid_time_value_within_the_bounded_sample_still_blocks(self):
        # A bad value the interpreter's OWN bounded sample already sees
        # reports blocking via ITS OWN diagnostic code
        # (`mixed_datetime_format`/`unparseable_datetime`) -- readiness
        # does not need a second, redundant `time_value_invalid` finding
        # for the exact same row to correctly block.
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[5] = "not-a-date,6.0"
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.is_ready is False
        assert summary.blocking_count > 0

    def test_invalid_time_value_beyond_the_bounded_sample_is_caught_by_full_region_scan(self):
        # The first 50+ rows are clean and consistent (the interpreter's
        # OWN bounded sample reports family=absolute/confidence=high,
        # zero diagnostics) -- only a full-active-region scan can ever
        # see the single bad row planted well past that sample window.
        registry = PreparationSessionRegistry()
        rows = 200
        lines = [f"2026-08-31 13:{(i // 60):02d}:{(i % 60):02d},{i}.0" for i in range(rows)]
        lines[120] = "not-a-date,120.0"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_VALUE_INVALID in _codes(summary)
        invalid = _by_code(summary, ISSUE_TIME_VALUE_INVALID)
        assert invalid.location.row_number == 121
        assert invalid.severity == SEVERITY_BLOCKING
        assert summary.is_ready is False

    def test_backward_time_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:01.500,1.0\n13:14:01.600,2.0\n13:14:01.400,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="time_of_day", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert "time_goes_backward" in _codes(summary)
        assert _by_code(summary, "time_goes_backward").severity == SEVERITY_BLOCKING
        assert summary.is_ready is False

    def test_reset_suspicion_is_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:30,1.0\n13:14:31,2.0\n00:00:00,3.0\n00:00:01,4.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="time_of_day", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert "timestamp_reset_suspected" in _codes(summary)
        assert _by_code(summary, "timestamp_reset_suspected").severity == SEVERITY_BLOCKING


class TestMinuteResolutionReadiness:
    """Enhancement (minute/AM-PM-hour absolute time support), task
    section T/AF: a valid, strictly-increasing minute-resolution
    absolute timeline is Ready like any other resolved absolute
    timeline -- no special warning solely because seconds were
    omitted, and readiness policy for an unresolved date order is
    unchanged."""

    def test_unambiguous_minute_resolution_timeline_is_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"31/08/2026 17:25,1.0\n31/08/2026 17:26,2.0\n31/08/2026 17:27,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.is_ready is True
        assert summary.blocking_count == 0

    def test_ambiguous_minute_resolution_date_order_still_blocks(self):
        # The exact owner-reported example -- minute resolution parsing
        # now succeeds, but ambiguous DMY/MDY must still block readiness
        # until the user explicitly resolves it (unchanged policy).
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"3/6/2026 17:25,1.0\n3/6/2026 17:26,2.0\n3/6/2026 17:27,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_AXIS_UNRESOLVED in _codes(summary)
        assert summary.is_ready is False

    def test_ambiguous_minute_resolution_resolved_by_explicit_date_order_is_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"3/6/2026 17:25,1.0\n3/6/2026 17:26,2.0\n3/6/2026 17:27,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", options={"date_order": "dmy"}, confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.is_ready is True

    def test_explicit_am_pm_hour_only_timeline_is_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-06-03 1pm,1.0\n2026-06-03 2pm,2.0\n2026-06-03 3pm,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.is_ready is True


class TestTimeAxisWarnings:
    def test_reconstructed_accepted_is_warning_and_ready(self):
        registry = PreparationSessionRegistry()
        lines = []
        for i in range(4):
            lines += [f"13:14:0{i}"] * 5
        source_id = _add_csv(registry, ("\n".join(f"{t},1.0" for t in lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="repeated_timestamp_precision_loss", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_RECONSTRUCTED_TIME in _codes(summary)
        assert _by_code(summary, ISSUE_RECONSTRUCTED_TIME).severity == SEVERITY_WARNING
        assert summary.blocking_count == 0
        assert summary.is_ready is True

    def test_user_specified_timing_is_warning_and_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1,1.0\n2,2.0\n3,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="sample_index", interval_seconds=0.01, confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_USER_SPECIFIED_TIME in _codes(summary)
        assert summary.is_ready is True

    def test_sample_index_fallback_is_warning_and_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"1,1.0\n2,2.0\n3,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="sample_index", registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_SAMPLE_INDEX_FALLBACK in _codes(summary)
        assert summary.blocking_count == 0
        assert summary.is_ready is True

    def test_partial_timing_is_warning_and_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:01,1.0\n13:14:02,2.0\n13:14:03,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="time_of_day", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_PARTIAL_TIME_REFERENCE in _codes(summary)
        assert summary.is_ready is True

    def test_large_time_gap_is_warning_not_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"13:14:01,1.0\n13:14:02,2.0\n13:20:00,3.0\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="time_of_day", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert _by_code(summary, "large_time_gap").severity == SEVERITY_WARNING

    def test_cadence_not_reliable_with_sample_index_fallback_is_not_blocking(self):
        # An engineer who declines an unreliable repeated-timestamp
        # reconstruction can always fall back to plain, numeric Sample
        # Index instead -- readiness follows the ACTIVE configuration
        # (sample_index), never the abandoned repeated-timestamp one.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, "\n".join(f"{i},1.0" for i in range(1, 20)).encode() + b"\n")
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="sample_index", registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.blocking_count == 0
        assert summary.is_ready is True

    def test_cadence_not_reliable_unresolved_is_blocking(self):
        registry = PreparationSessionRegistry()
        lines = []
        pattern = [5, 2, 8, 4]
        for i, count in enumerate(pattern):
            lines += [f"13:14:0{i}"] * count
        source_id = _add_csv(registry, ("\n".join(f"{t},1.0" for t in lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="repeated_timestamp_precision_loss", registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_TIME_AXIS_UNRESOLVED in _codes(summary)
        assert summary.is_ready is False


class TestWaveformValues:
    def test_all_numeric_is_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)

        summary = _issues(registry, source_id)
        assert summary.is_ready is True

    def test_blank_cell_is_blocking(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[3] = "2026-08-31 13:00:03,"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_MISSING in _codes(summary)
        assert summary.is_ready is False

    def test_err_value_is_blocking_and_preserved(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,ERR"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        invalid = _by_code(summary, ISSUE_WAVEFORM_VALUE_INVALID)
        assert invalid.details["sample_value"] == "ERR"
        assert invalid.severity == SEVERITY_BLOCKING

    def test_na_value_is_blocking(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,N/A"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID in _codes(summary)

    def test_hash_value_error_is_blocking(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,#VALUE!"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID in _codes(summary)

    def test_malformed_numeric_string_is_blocking(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,12.3?"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID in _codes(summary)

    def test_excluded_bad_row_does_not_block(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,ERR"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )
        set_row_excluded(workspace_id="ws-1", source_id=source_id, row_number=3, excluded=True, registry=registry)

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID not in _codes(summary)
        assert summary.is_ready is True

    def test_bad_value_outside_data_region_does_not_block(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[0] = "2026-08-31 13:00:00,ERR"  # row 1 -- pushed out of region below
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )
        set_data_region(workspace_id="ws-1", source_id=source_id, start_row=2, end_row=8, registry=registry)

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID not in _codes(summary)

    def test_bad_value_in_not_assigned_column_does_not_block_waveform_readiness(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0,note{i}" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,3.0,ERR"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        # column_index=2 is left at its default (not_assigned)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.is_ready is True


class TestDataPreservation:
    def test_original_values_never_overwritten_by_readiness_check(self):
        registry = PreparationSessionRegistry()
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(8)]
        lines[2] = "2026-08-31 13:00:02,ERR"
        content = ("\n".join(lines) + "\n").encode()
        source_id = _add_csv(registry, content)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        _issues(registry, source_id)  # readiness evaluated

        session = registry.get("ws-1", source_id)
        assert session.raw_bytes == content
        assert session.working_overlay.cell_overrides == {}


class TestRevisionBehavior:
    def test_readiness_reflects_current_revision(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-08-31 13:00:00,1.0\n")
        _mark_time_axis(registry, source_id, 0)

        before = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_CHANNEL_MISSING in _codes(before)

        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )
        after = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_CHANNEL_MISSING not in _codes(after)
        assert after.evaluated_revision > before.evaluated_revision
        assert after.is_ready is True

    def test_mutation_invalidates_readiness_automatically(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        assert _issues(registry, source_id).is_ready is True

        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="not_assigned", registry=registry)

        assert _issues(registry, source_id).is_ready is False

    def test_undo_restores_prior_readiness(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="not_assigned", registry=registry)
        assert _issues(registry, source_id).is_ready is False

        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert _issues(registry, source_id).is_ready is True

    def test_redo_reapplies_readiness_change(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        set_column_role(workspace_id="ws-1", source_id=source_id, column_index=1, role="not_assigned", registry=registry)
        undo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)
        assert _issues(registry, source_id).is_ready is True

        redo_working_change(workspace_id="ws-1", source_id=source_id, registry=registry)

        assert _issues(registry, source_id).is_ready is False

    def test_reset_all_returns_to_unconfigured_blocking(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        assert _issues(registry, source_id).is_ready is True

        reset_all_working_changes(workspace_id="ws-1", source_id=source_id, registry=registry)

        summary = _issues(registry, source_id)
        assert summary.is_ready is False
        assert ISSUE_TIME_AXIS_UNCONFIGURED in _codes(summary)
        assert ISSUE_WAVEFORM_CHANNEL_MISSING in _codes(summary)


class TestExcelWorksheetIsolation:
    def test_only_selected_worksheet_is_validated(self):
        registry = PreparationSessionRegistry()
        content = _build_xlsx({
            "A": [["2026-08-31 13:00:00", 1.0], ["2026-08-31 13:00:01", 2.0]],
            "B": [["not-a-date", "ERR"]],
        })
        source_id = _add_excel(registry, content)

        from app.services.preparation_import_service import select_preparation_worksheet

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=0, registry=registry)
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary_a = _issues(registry, source_id)
        assert summary_a.is_ready is True

        select_preparation_worksheet(workspace_id="ws-1", source_id=source_id, worksheet_index=1, registry=registry)
        summary_b = _issues(registry, source_id)
        assert summary_b.is_ready is False
        assert ISSUE_TIME_AXIS_UNCONFIGURED in _codes(summary_b)


class TestPerformanceStreaming:
    def test_readiness_scans_entire_active_region_not_just_bounded_sample(self):
        # A "bad" row well beyond the interpreter's own bounded 50-row
        # sample must still be caught -- proving the full-region scan,
        # not the sample-based diagnostic, is what is running.
        registry = PreparationSessionRegistry()
        rows = 500
        lines = [f"2026-08-31 13:{(i // 60):02d}:{(i % 60):02d},{i}.0" for i in range(rows)]
        lines[300] = lines[300].split(",")[0] + ",ERR"
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert ISSUE_WAVEFORM_VALUE_INVALID in _codes(summary)
        invalid = _by_code(summary, ISSUE_WAVEFORM_VALUE_INVALID)
        assert invalid.location.row_number == 301

    def test_large_synthetic_source_handled_without_full_duplication(self):
        # A large-ish CSV -- readiness must complete without materializing
        # a full second copy of the dataset (the streaming iterator is
        # what makes this practical; this test's own purpose is a smoke
        # check that it completes correctly at this scale, not a strict
        # timing/memory assertion).
        registry = PreparationSessionRegistry()
        rows = 20_000
        lines = [f"2026-08-31 13:{(i // 60) % 60:02d}:{(i % 60):02d}.{i % 1000:03d},{i}.0" for i in range(rows)]
        source_id = _add_csv(registry, ("\n".join(lines) + "\n").encode())
        _mark_time_axis(registry, source_id, 0)
        _mark_waveform(registry, source_id, 1)
        set_time_axis_configuration(
            workspace_id="ws-1", source_id=source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=registry,
        )

        summary = _issues(registry, source_id)
        assert summary.blocking_count == 0
        assert summary.is_ready is True


class TestEngineeringQuantityNeverBlocksReadiness:
    """DEC-077, task section AD: Engineering Quantity is initially
    optional -- a Waveform column left at the "Undefined" default (never
    selected) is still Powerwave Ready, exactly as before this
    enhancement. Explicitly selecting a quantity must not introduce a
    NEW blocking condition either."""

    def test_undefined_engineering_quantity_is_still_ready(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)

        summary = _issues(registry, source_id)

        assert summary.blocking_count == 0
        assert summary.is_ready is True

    def test_explicit_engineering_quantity_selection_does_not_change_readiness(self):
        registry = PreparationSessionRegistry()
        source_id = _ready_source(registry)
        set_column_engineering_quantity(
            workspace_id="ws-1", source_id=source_id, column_index=1,
            engineering_quantity="Voltage", registry=registry,
        )

        summary = _issues(registry, source_id)

        assert summary.blocking_count == 0
        assert summary.is_ready is True
