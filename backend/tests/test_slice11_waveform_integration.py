"""CSV/Excel ingestion Slice 11 (DEC-072): existing-waveform-integration
verification. Proves a Slice-10-converted CSV/Excel `ActiveSource`
behaves like any other Powerwave source across Time Groups,
synchronization, calculated channels, and the waveform range/cursor
pipeline -- reusing every one of those EXISTING services unmodified
(aside from the two `Conversion*`-unrelated defects this slice's own
audit found and fixed in `app.domain.time_grouping`/
`app.services.calculated_channel_service`; see those modules' own
docstrings and `tests/test_time_grouping_domain.py`/
`test_calculated_channel_service.py` for the dedicated regression
coverage of the fix itself). Zero new production feature is added here.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io

import numpy as np
import pandas as pd
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.domain.calculated_channel import ChannelRef, OP_ADDITION
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel, remove_calculated_channels_for_source
from app.services.errors import IncompatibleTimeBaseError, ReferenceSourceAlignmentError, SourceNotFoundError
from app.services.preparation_conversion_service import convert_preparation_source
from app.services.preparation_import_service import import_csv_preparation_source
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import get_source_alignment, list_time_groups, set_source_alignment_offset
from app.services.time_axis_service import set_time_axis_configuration
from app.services.waveform_service import extract_cursor_values, extract_waveform_range
from app.services.working_overlay_service import set_column_role
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"


def _upload(content: bytes, filename: str = "e.csv") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": "text/csv"}))


def _convert_csv(*, content: bytes, interpreter_id: str = "absolute_datetime", interval_seconds: float | None = None,
                  unit: str | None = None, filename: str = "e.csv") -> tuple[SourceMetadata, WorkspaceRegistry]:
    """Uploads, configures, and converts one CSV source end to end --
    column 0 is Time Axis, column 1 is the sole Waveform Channel."""
    prep = PreparationSessionRegistry()
    ws = WorkspaceRegistry()
    summary = asyncio.run(
        import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content, filename),
            max_total_bytes=100 * 1024 * 1024, registry=prep,
        )
    )
    source_id = summary.source_id
    set_column_role(workspace_id=WS, source_id=source_id, column_index=0, role="time_axis", registry=prep)
    set_column_role(workspace_id=WS, source_id=source_id, column_index=1, role="waveform", registry=prep)
    set_time_axis_configuration(
        workspace_id=WS, source_id=source_id, column_indices=(0,), interpreter_id=interpreter_id,
        unit=unit, interval_seconds=interval_seconds, confirmed=True, registry=prep,
    )
    metadata = convert_preparation_source(
        workspace_id=WS, source_id=source_id, preparation_registry=prep, workspace_registry=ws,
    )
    return metadata, ws


def _convert_second_csv_into(ws: WorkspaceRegistry, *, content: bytes, interpreter_id: str = "absolute_datetime",
                              filename: str = "b.csv") -> SourceMetadata:
    """Converts a SECOND CSV source into an ALREADY-EXISTING workspace
    registry (mirrors `test_two_elapsed_sources_each_get_their_own_
    singleton`'s own established pattern above) -- `_convert_csv()`
    itself always creates a brand-new `WorkspaceRegistry`, so a
    multi-source Time Group/synchronization test needs this instead."""
    prep2 = PreparationSessionRegistry()
    summary = asyncio.run(import_csv_preparation_source(
        workspace_id=WS, csv_upload=_upload(content, filename), max_total_bytes=10_000_000, registry=prep2,
    ))
    set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
    set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
    set_time_axis_configuration(
        workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
        interpreter_id=interpreter_id, confirmed=True, registry=prep2,
    )
    return convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)


def _comtrade_like_source(*, source_id: str, start_time: dt.datetime, time: np.ndarray, values: np.ndarray,
                           trigger_time: dt.datetime | None = None) -> ActiveSource:
    """A synthetic, COMTRADE-shaped `ActiveSource` -- mirrors
    `test_calculated_channel_service.py`'s own established
    `_active_source()` helper pattern (a real parsed COMTRADE fixture
    would exercise the identical downstream code path, since nothing
    below ever branches on `provider_type`)."""
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH", recorder_name="TEST", source_file="synthetic.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": time, "VA": values}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0 / (time[1] - time[0])], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=start_time, trigger_time=trigger_time),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"), created_at=dt.datetime.now(dt.timezone.utc),
        station_name="SYNTH", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start_time, trigger_time=trigger_time,
        sample_count=len(time), duration_seconds=float(time[-1] - time[0]),
        elapsed_start_seconds=float(time[0]), elapsed_end_seconds=float(time[-1]),
        sampling_rates=(1.0 / (time[1] - time[0]),), samples_per_rate=(len(time),),
        analog_channels=[AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


class TestConvertedWaveformBaseline:
    def test_channel_listing_order_and_range_fetch(self):
        content = b"2026-08-31 13:00:00,10.0,20.0\n2026-08-31 13:00:01,11.0,21.0\n2026-08-31 13:00:02,12.0,22.0\n"
        prep = PreparationSessionRegistry()
        ws = WorkspaceRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content), max_total_bytes=10_000_000, registry=prep,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=2, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep,
        )
        metadata = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)
        active = ws.get(WS, metadata.source_id)

        assert [ch.name for ch in metadata.analog_channels] == ["B", "C"]

        result = extract_waveform_range(active, channel_name="B", start_time=None, end_time=None, point_budget=1000)
        assert list(result.time) == [0.0, 1.0, 2.0]
        assert list(result.values) == [10.0, 11.0, 12.0]

    def test_bounded_range_fetch_excludes_outside_window(self):
        lines = [f"2026-08-31 13:00:{i:02d},{i}.0" for i in range(10)]
        metadata, ws = _convert_csv(content=("\n".join(lines) + "\n").encode())
        active = ws.get(WS, metadata.source_id)

        result = extract_waveform_range(active, channel_name="B", start_time=2.0, end_time=4.0, point_budget=1000)
        assert list(result.time) == [2.0, 3.0, 4.0]

    def test_cursor_values_at_exact_sample(self):
        content = b"2026-08-31 13:00:00,10.0\n2026-08-31 13:00:01,11.0\n2026-08-31 13:00:02,12.0\n"
        metadata, ws = _convert_csv(content=content)
        active = ws.get(WS, metadata.source_id)

        result = extract_cursor_values(
            active, analog_channel_names=["B"], digital_channel_names=[],
            cursor_a_time=1.0, cursor_b_time=None,
        )
        assert result.cursor_a.sample_time == 1.0
        assert result.channels[0].a_value == 11.0


class TestMultipleConvertedSources:
    def test_csv_plus_csv_independent(self):
        meta_a, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        prep2 = PreparationSessionRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"2026-08-31 14:00:00,9.0\n2026-08-31 14:00:01,8.0\n", "b.csv"),
            max_total_bytes=10_000_000, registry=prep2,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep2,
        )
        meta_b = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)

        assert ws.get(WS, meta_a.source_id) is not None
        assert ws.get(WS, meta_b.source_id) is not None
        assert meta_a.source_id != meta_b.source_id
        # Both keep their own independent channel name "B" without collision.
        assert meta_a.analog_channels[0].name == "B"
        assert meta_b.analog_channels[0].name == "B"

    def test_removing_one_converted_source_leaves_the_other_intact(self):
        meta_a, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        prep2 = PreparationSessionRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"2026-08-31 14:00:00,9.0\n2026-08-31 14:00:01,8.0\n", "b.csv"),
            max_total_bytes=10_000_000, registry=prep2,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep2,
        )
        meta_b = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)

        ws.remove(WS, meta_a.source_id)

        assert ws.get(WS, meta_a.source_id) is None
        assert ws.get(WS, meta_b.source_id) is not None


class TestComtradeCoexistence:
    def test_comtrade_source_completely_unaffected_by_a_converted_csv_source(self):
        comtrade = _comtrade_like_source(
            source_id="comtrade-1", start_time=dt.datetime(2026, 8, 31, 13, 0, 0),
            time=np.array([0.0, 0.02, 0.04]), values=np.array([1.0, 2.0, 3.0]),
            trigger_time=dt.datetime(2026, 8, 31, 13, 0, 0, 10000),
        )
        meta_csv, ws = _convert_csv(content=b"2026-08-31 13:00:00,10.0\n2026-08-31 13:00:01,11.0\n")
        ws.add(comtrade)

        fetched_comtrade = ws.get(WS, "comtrade-1")
        assert fetched_comtrade.metadata.trigger_time == dt.datetime(2026, 8, 31, 13, 0, 0, 10000)
        assert fetched_comtrade.metadata.timing_reference == "absolute"
        result = extract_waveform_range(fetched_comtrade, channel_name="VA", start_time=None, end_time=None, point_budget=100)
        assert list(result.values) == [1.0, 2.0, 3.0]


class TestTimeGroupIntegration:
    def test_absolute_plus_absolute_overlapping_share_a_group(self):
        comtrade = _comtrade_like_source(
            source_id="comtrade-1", start_time=dt.datetime(2026, 8, 31, 13, 0, 0),
            time=np.array([0.0, 1.0, 2.0]), values=np.array([1.0, 2.0, 3.0]),
        )
        meta_csv, ws = _convert_csv(content=b"2026-08-31 13:00:00,10.0\n2026-08-31 13:00:01,11.0\n")
        ws.add(comtrade)

        groups = list_time_groups(workspace_id=WS, source_registry=ws)
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"comtrade-1", meta_csv.source_id}

    def test_absolute_plus_elapsed_stay_separate(self):
        comtrade = _comtrade_like_source(
            source_id="comtrade-1", start_time=dt.datetime(2026, 8, 31, 13, 0, 0),
            time=np.array([0.0, 1.0, 2.0]), values=np.array([1.0, 2.0, 3.0]),
        )
        meta_csv, ws = _convert_csv(content=b"5.0,10.0\n6.0,11.0\n", interpreter_id="elapsed_numeric", unit="seconds")
        ws.add(comtrade)

        groups = list_time_groups(workspace_id=WS, source_registry=ws)
        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert "comtrade-1" in group_ids
        assert meta_csv.source_id in group_ids
        elapsed_group = next(g for g in groups if g.group_id == meta_csv.source_id)
        assert elapsed_group.time_reference_type == "elapsed_only"
        assert elapsed_group.source_ids == [meta_csv.source_id]

    def test_two_elapsed_sources_each_get_their_own_singleton(self):
        meta_a, ws = _convert_csv(content=b"5.0,10.0\n6.0,11.0\n", interpreter_id="elapsed_numeric", unit="seconds")
        prep2 = PreparationSessionRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"5.0,9.0\n6.0,8.0\n", "b.csv"),
            max_total_bytes=10_000_000, registry=prep2,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="elapsed_numeric", unit="seconds", confirmed=True, registry=prep2,
        )
        meta_b = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)

        groups = list_time_groups(workspace_id=WS, source_registry=ws)
        assert len(groups) == 2
        assert all(g.time_reference_type == "elapsed_only" for g in groups)
        assert all(len(g.source_ids) == 1 for g in groups)

    def test_partial_family_source_gets_its_own_time_of_day_group(self):
        # Time of Day (additive): a FAMILY_PARTIAL source is now its own
        # distinct `time_reference_type`, never lumped into
        # `elapsed_only` -- this is what lets two such sources
        # auto-synchronize with EACH OTHER by clock-time overlap (see
        # TestTimeOfDaySynchronization below), which `elapsed_only`
        # never could.
        metadata, ws = _convert_csv(content=b"13:14:01,1.0\n13:14:02,2.0\n")
        groups = list_time_groups(workspace_id=WS, source_registry=ws)
        assert len(groups) == 1
        assert groups[0].time_reference_type == "time_of_day"
        assert metadata.timing_reference == "time_of_day"

    def test_two_overlapping_time_of_day_sources_share_a_group(self):
        # Task's own Case 6, exercised end to end through real CSV
        # upload -> Time Axis configuration -> canonical conversion ->
        # Time Group derivation. A=18:04:00->18:04:10s, B starts 5s
        # later and overlaps.
        meta_a, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:10,2.0\n", interpreter_id="time_of_day")
        meta_b = _convert_second_csv_into(ws, content=b"18:04:05,10.0\n18:04:15,20.0\n", interpreter_id="time_of_day")

        groups = list_time_groups(workspace_id=WS, source_registry=ws)

        assert len(groups) == 1
        assert groups[0].time_reference_type == "time_of_day"
        assert set(groups[0].source_ids) == {meta_a.source_id, meta_b.source_id}

    def test_two_non_overlapping_time_of_day_sources_stay_separate(self):
        # Task's own Case 7: A=18:04:00->18:04:10, B=19:00:00->19:00:10.
        meta_a, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:10,2.0\n", interpreter_id="time_of_day")
        meta_b = _convert_second_csv_into(ws, content=b"19:00:00,10.0\n19:00:10,20.0\n", interpreter_id="time_of_day")

        groups = list_time_groups(workspace_id=WS, source_registry=ws)

        assert len(groups) == 2
        group_ids = {g.group_id for g in groups}
        assert group_ids == {meta_a.source_id, meta_b.source_id}
        assert all(g.time_reference_type == "time_of_day" for g in groups)

    def test_absolute_and_time_of_day_never_share_a_group_end_to_end(self):
        # Task's own Case 5 / governing rule, exercised end to end:
        # Event A is a real Absolute DateTime recording at
        # 2026-06-03 18:04:00; Event B is a Time of Day recording at the
        # SAME clock time with no date. They must never be synchronized
        # merely because their clock portions look similar.
        meta_a, ws = _convert_csv(content=b"2026-06-03 18:04:00,1.0\n2026-06-03 18:04:10,2.0\n")
        meta_b = _convert_second_csv_into(ws, content=b"18:04:00,10.0\n18:04:10,20.0\n", interpreter_id="time_of_day")

        groups = list_time_groups(workspace_id=WS, source_registry=ws)

        assert len(groups) == 2
        by_id = {g.group_id: g for g in groups}
        assert by_id[meta_a.source_id].time_reference_type == "recorded_absolute"
        assert by_id[meta_a.source_id].source_ids == [meta_a.source_id]
        assert by_id[meta_b.source_id].time_reference_type == "time_of_day"
        assert by_id[meta_b.source_id].source_ids == [meta_b.source_id]

    def test_two_time_of_day_sources_crossing_the_same_midnight_still_overlap(self):
        # Task's own Case 9. A: 23:59:58 -> 00:00:04 (crosses midnight).
        # B: 23:59:59 -> 00:00:02 (also crosses the SAME midnight).
        meta_a, ws = _convert_csv(
            content=b"23:59:58,1.0\n23:59:59,2.0\n00:00:00,3.0\n00:00:04,4.0\n", interpreter_id="time_of_day",
        )
        meta_b = _convert_second_csv_into(
            ws, content=b"23:59:59,10.0\n00:00:00,20.0\n00:00:02,30.0\n", interpreter_id="time_of_day",
        )

        groups = list_time_groups(workspace_id=WS, source_registry=ws)

        assert len(groups) == 1
        assert set(groups[0].source_ids) == {meta_a.source_id, meta_b.source_id}


class TestTimeOfDayChannelsApiSchema:
    """Time of Day presentation completion (additive): the frontend
    needs `time_of_day_reference_seconds` from the `GET .../channels`
    response (`TimebaseOut`) to derive its own clock-time display for
    the waveform axis/cursor/ruler -- this locks in that a real
    converted Time of Day source's own metadata reaches that schema."""

    def test_timebase_exposes_time_of_day_reference_seconds(self):
        from app.schemas.source import SourceChannelsOut

        metadata, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:00.020000,2.0\n", interpreter_id="time_of_day")

        out = SourceChannelsOut.from_domain(metadata)

        assert out.timebase.timing_reference == "time_of_day"
        assert out.timebase.time_of_day_reference_seconds == pytest.approx(18 * 3600 + 4 * 60)

    def test_absolute_source_leaves_it_none(self):
        from app.schemas.source import SourceChannelsOut

        metadata, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")

        out = SourceChannelsOut.from_domain(metadata)

        assert out.timebase.time_of_day_reference_seconds is None


class TestSynchronizationIntegration:
    def test_converted_absolute_source_alignment_view_has_no_exceptions(self):
        metadata, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        sync_registry = SynchronizationRegistry()
        view = get_source_alignment(workspace_id=WS, source_id=metadata.source_id, registry=sync_registry, source_registry=ws)
        assert view.is_reference is True
        assert view.timestamp_placement_offset_s == 0.0

    def test_reference_source_manual_offset_rejected_matches_comtrade_behavior(self):
        metadata, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        sync_registry = SynchronizationRegistry()
        with pytest.raises(ReferenceSourceAlignmentError):
            set_source_alignment_offset(
                workspace_id=WS, source_id=metadata.source_id, alignment_offset_s=1.5,
                registry=sync_registry, source_registry=ws,
            )

    def test_non_absolute_source_is_always_its_own_reference(self):
        metadata, ws = _convert_csv(content=b"5.0,1.0\n6.0,2.0\n", interpreter_id="elapsed_numeric", unit="seconds")
        sync_registry = SynchronizationRegistry()
        view = get_source_alignment(workspace_id=WS, source_id=metadata.source_id, registry=sync_registry, source_registry=ws)
        assert view.is_reference is True
        assert view.effective_alignment_offset_s == 0.0

    def test_optional_trigger_time_none_does_not_raise(self):
        metadata, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        assert metadata.trigger_time is None
        sync_registry = SynchronizationRegistry()
        # Exercises the full alignment-view composition path with a None
        # trigger_time on the converted source -- must not raise.
        view = get_source_alignment(workspace_id=WS, source_id=metadata.source_id, registry=sync_registry, source_registry=ws)
        assert view.source_id == metadata.source_id


class TestTimeOfDaySynchronization:
    """Full synchronization-service integration for the new Time of Day
    bucket -- `get_source_alignment()`'s own `timestamp_placement_offset_s`
    composition, computed via the date-neutral
    `time_of_day_placement_offset_s()` path (never the `datetime`-based
    one, which would be meaningless here since `start_time` is always
    `None` for a Time of Day source)."""

    def test_origin_source_has_zero_placement(self):
        meta_a, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:10,2.0\n", interpreter_id="time_of_day")
        sync_registry = SynchronizationRegistry()
        view = get_source_alignment(workspace_id=WS, source_id=meta_a.source_id, registry=sync_registry, source_registry=ws)
        assert view.is_reference is True
        assert view.timestamp_placement_offset_s == pytest.approx(0.0)

    def test_later_source_gets_correct_clock_time_placement(self):
        # A starts at 18:04:00, B starts 5s later at 18:04:05 -- B's own
        # placement must be +5s, computed purely from clock time, never
        # from an invented calendar date.
        meta_a, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:10,2.0\n", interpreter_id="time_of_day")
        meta_b = _convert_second_csv_into(ws, content=b"18:04:05,10.0\n18:04:15,20.0\n", interpreter_id="time_of_day")
        sync_registry = SynchronizationRegistry()

        view_a = get_source_alignment(workspace_id=WS, source_id=meta_a.source_id, registry=sync_registry, source_registry=ws)
        view_b = get_source_alignment(workspace_id=WS, source_id=meta_b.source_id, registry=sync_registry, source_registry=ws)

        assert view_a.is_reference is True
        assert view_b.is_reference is False
        assert view_b.timestamp_placement_offset_s == pytest.approx(5.0)

    def test_reference_source_manual_offset_rejected(self):
        meta_a, ws = _convert_csv(content=b"18:04:00,1.0\n18:04:10,2.0\n", interpreter_id="time_of_day")
        _convert_second_csv_into(ws, content=b"18:04:05,10.0\n18:04:15,20.0\n", interpreter_id="time_of_day")
        sync_registry = SynchronizationRegistry()
        with pytest.raises(ReferenceSourceAlignmentError):
            set_source_alignment_offset(
                workspace_id=WS, source_id=meta_a.source_id, alignment_offset_s=1.5,
                registry=sync_registry, source_registry=ws,
            )


class TestCalculatedChannelsSameSourceConvertedCsv:
    def test_addition_on_two_converted_waveform_channels(self):
        content = b"2026-08-31 13:00:00,1.0,10.0\n2026-08-31 13:00:01,2.0,20.0\n"
        prep = PreparationSessionRegistry()
        ws = WorkspaceRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content), max_total_bytes=10_000_000, registry=prep,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=2, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep,
        )
        metadata = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)
        calc_registry = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS, name="B+C", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="B"),
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="C"),
            ],
            parameters={}, source_registry=ws, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [11.0, 22.0]


class TestCalculatedChannelsCrossSource:
    def test_two_converted_absolute_sources_with_identical_true_timing_align(self):
        meta_a, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        prep2 = PreparationSessionRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"2026-08-31 13:00:00,10.0\n2026-08-31 13:00:01,20.0\n", "b.csv"),
            max_total_bytes=10_000_000, registry=prep2,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep2,
        )
        meta_b = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)
        calc_registry = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS, name="A+B", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id=meta_a.source_id, channel_name="B"),
                ChannelRef(kind="source", source_id=meta_b.source_id, channel_name="B"),
            ],
            parameters={}, source_registry=ws, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [11.0, 22.0]

    def test_elapsed_csv_and_absolute_comtrade_rejected_never_resampled(self):
        comtrade = _comtrade_like_source(
            source_id="comtrade-1", start_time=dt.datetime(2026, 8, 31, 13, 0, 0),
            time=np.array([0.0, 1.0]), values=np.array([1.0, 2.0]),
        )
        metadata, ws = _convert_csv(content=b"5.0,10.0\n6.0,20.0\n", interpreter_id="elapsed_numeric", unit="seconds")
        ws.add(comtrade)
        calc_registry = CalculatedChannelRegistry()

        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="comtrade-1", channel_name="VA"),
                    ChannelRef(kind="source", source_id=metadata.source_id, channel_name="B"),
                ],
                parameters={}, source_registry=ws, calc_registry=calc_registry,
            )
        # No resampling / synthetic channel was ever created as a side effect.
        assert calc_registry.list_for_workspace(WS) == []

    def test_two_absolute_csv_sources_with_different_start_times_rejected(self):
        meta_a, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        prep2 = PreparationSessionRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"2026-08-31 14:00:00,10.0\n2026-08-31 14:00:01,20.0\n", "b.csv"),
            max_total_bytes=10_000_000, registry=prep2,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep2)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep2)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep2,
        )
        meta_b = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep2, workspace_registry=ws)
        calc_registry = CalculatedChannelRegistry()

        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id=meta_a.source_id, channel_name="B"),
                    ChannelRef(kind="source", source_id=meta_b.source_id, channel_name="B"),
                ],
                parameters={}, source_registry=ws, calc_registry=calc_registry,
            )


class TestIrregularTimingDownstream:
    def test_range_fetch_preserves_true_irregular_time_array(self):
        content = b"13:14:01,1.0\n13:14:02,2.0\n13:14:04,3.0\n13:14:05,4.0\n13:14:09,5.0\n"
        metadata, ws = _convert_csv(content=content)
        active = ws.get(WS, metadata.source_id)

        assert active.record.sampling_info.is_uniform is False
        result = extract_waveform_range(active, channel_name="B", start_time=None, end_time=None, point_budget=1000)
        assert list(result.time) == [0.0, 1.0, 3.0, 4.0, 8.0]

    def test_same_source_calculated_channel_still_works_on_irregular_timing(self):
        content = b"13:14:01,1.0,10.0\n13:14:02,2.0,20.0\n13:14:04,3.0,30.0\n"
        prep = PreparationSessionRegistry()
        ws = WorkspaceRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content), max_total_bytes=10_000_000, registry=prep,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=2, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep,
        )
        metadata = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)
        calc_registry = CalculatedChannelRegistry()

        channel = create_calculated_channel(
            workspace_id=WS, name="B+C", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="B"),
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="C"),
            ],
            parameters={}, source_registry=ws, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [11.0, 22.0, 33.0]
        # No fabricated uniform rate downstream: the calculated channel's
        # own time array is the SAME true irregular one, untouched.
        assert channel.time.tolist() == [0.0, 1.0, 3.0]


class TestProvenanceSurvivesRegistration:
    def test_preparation_provenance_intact_after_workspace_registry_round_trip(self):
        metadata, ws = _convert_csv(content=b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n")
        refetched = ws.get(WS, metadata.source_id)

        provenance = refetched.metadata.preparation_provenance
        assert provenance is not None
        for key in (
            "source_format", "original_filename", "worksheet_index", "preparation_revision",
            "time_family", "time_provenance", "interpreter_id", "reconstructed", "nominal_frequency_assumed",
        ):
            assert key in provenance


class TestLifecycleAndIdempotency:
    def test_convert_open_remove_reopen_is_coherent(self):
        prep = PreparationSessionRegistry()
        ws = WorkspaceRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(b"2026-08-31 13:00:00,1.0\n2026-08-31 13:00:01,2.0\n"),
            max_total_bytes=10_000_000, registry=prep,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep,
        )
        metadata = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)

        # Preparation source is gone (converted); canonical source is open-able.
        assert prep.get(WS, summary.source_id) is None
        assert ws.get(WS, metadata.source_id) is not None

        ws.remove(WS, metadata.source_id)
        assert ws.get(WS, metadata.source_id) is None

        # Re-converting the (already-removed) preparation source 404s --
        # no orphaned/duplicate registry state was left behind.
        with pytest.raises(SourceNotFoundError):
            convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)

    def test_removing_a_converted_source_cascades_its_calculated_channels(self):
        content = b"2026-08-31 13:00:00,1.0,10.0\n2026-08-31 13:00:01,2.0,20.0\n"
        prep = PreparationSessionRegistry()
        ws = WorkspaceRegistry()
        summary = asyncio.run(import_csv_preparation_source(
            workspace_id=WS, csv_upload=_upload(content), max_total_bytes=10_000_000, registry=prep,
        ))
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=0, role="time_axis", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=1, role="waveform", registry=prep)
        set_column_role(workspace_id=WS, source_id=summary.source_id, column_index=2, role="waveform", registry=prep)
        set_time_axis_configuration(
            workspace_id=WS, source_id=summary.source_id, column_indices=(0,),
            interpreter_id="absolute_datetime", confirmed=True, registry=prep,
        )
        metadata = convert_preparation_source(workspace_id=WS, source_id=summary.source_id, preparation_registry=prep, workspace_registry=ws)
        calc_registry = CalculatedChannelRegistry()
        create_calculated_channel(
            workspace_id=WS, name="B+C", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="B"),
                ChannelRef(kind="source", source_id=metadata.source_id, channel_name="C"),
            ],
            parameters={}, source_registry=ws, calc_registry=calc_registry,
        )
        assert len(calc_registry.list_for_workspace(WS)) == 1

        ws.remove(WS, metadata.source_id)
        removed_ids = remove_calculated_channels_for_source(workspace_id=WS, source_id=metadata.source_id, calc_registry=calc_registry)

        assert len(removed_ids) == 1
        assert calc_registry.list_for_workspace(WS) == []


class TestPerformanceBoundedRangeFetch:
    def test_large_converted_source_range_fetch_is_bounded_not_full_dataset(self):
        rows = 50_000
        base = dt.datetime(2026, 1, 1, 0, 0, 0)
        lines = [f"{(base + dt.timedelta(milliseconds=20 * i)).isoformat()},{float(i)}" for i in range(rows)]
        content = ("\n".join(lines) + "\n").encode()
        started = dt.datetime.now()
        metadata, ws = _convert_csv(content=content)
        conversion_seconds = (dt.datetime.now() - started).total_seconds()
        active = ws.get(WS, metadata.source_id)

        assert active.record.sample_count() == rows
        # A normal zoomed-in display request must NOT be handed the
        # entire 50,000-sample dataset -- the existing min/max-envelope
        # reduction (app.domain.waveform_reduction, format-agnostic,
        # unmodified by Slice 10/11) must still engage exactly as it
        # does for a large COMTRADE record.
        result = extract_waveform_range(active, channel_name="B", start_time=None, end_time=None, point_budget=2000)
        assert result.representation == "min_max_envelope"
        assert len(result.time) < rows
        assert conversion_seconds < 15.0
