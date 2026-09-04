"""Unit tests for app.services.table_service (Canonical Table View, DEC-079).

Builds ActiveSource fixtures directly (the same convention
tests/test_waveform_service.py already established) so pagination/
column/value correctness can be tested against precisely known sample
counts -- parser-level correctness (a real COMTRADE upload) and
CSV/Excel-conversion agreement are covered separately (see
test_table_api.py / test_table_export_agreement.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.table_service import (
    COLUMN_KIND_ANALOG,
    COLUMN_KIND_DIGITAL,
    COLUMN_KIND_TIME,
    TABLE_DEFAULT_LIMIT,
    TABLE_MAX_LIMIT,
    build_table_columns,
    fetch_table_rows,
)


def _active_source(
    *,
    n: int = 10,
    time: np.ndarray | None = None,
    rate_hz: float = 50.0,
    timing_reference: str = "absolute",
    start_time: datetime | None = None,
    analog: list[AnalogChannelSummary] | None = None,
    digital: list[DigitalChannelSummary] | None = None,
    extra_columns: dict[str, np.ndarray] | None = None,
    source_id: str = "src-1",
    sampling_rates: tuple[float, ...] | None = None,
    samples_per_rate: tuple[int, ...] | None = None,
) -> ActiveSource:
    if time is None:
        time = np.arange(n, dtype=np.float64) / rate_hz
    else:
        n = len(time)
    if start_time is None:
        start_time = datetime(2026, 3, 6, 10, 0, 0, tzinfo=timezone.utc)

    if analog is None:
        analog = [AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")]
    if digital is None:
        digital = [DigitalChannelSummary(name="BRK_A", index=0, normal_state=0)]

    data = {"time": time}
    for ch in analog:
        data[ch.name] = np.arange(n, dtype=np.float64) * 10.0
    for ch in digital:
        data[ch.name] = np.zeros(n, dtype=np.int8)
    if extra_columns:
        data.update(extra_columns)

    rates = sampling_rates or (rate_hz,)
    counts = samples_per_rate or (n,)

    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH", recorder_name="TEST", source_file="synthetic.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(data),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=list(rates), samples_per_rate=list(counts)),
        timing_info=TimingInformation(
            start_time=start_time if timing_reference == "absolute" else None,
            trigger_time=None,
        ),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id="ws-1", provider_type="COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"), created_at=start_time or datetime.now(timezone.utc),
        station_name="SYNTH", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference=timing_reference,
        start_time=start_time if timing_reference == "absolute" else None,
        trigger_time=None,
        sample_count=n, duration_seconds=float(time[-1] - time[0]) if n else 0.0,
        elapsed_start_seconds=float(time[0]) if n else 0.0, elapsed_end_seconds=float(time[-1]) if n else 0.0,
        sampling_rates=tuple(rates), samples_per_rate=tuple(counts),
        analog_channels=analog, digital_channels=digital,
    )
    return ActiveSource(metadata=metadata, record=record)


class TestBasicPage:
    def test_correct_rows_and_totals(self):
        active = _active_source(n=10)

        result = fetch_table_rows(active, offset=0, limit=5)

        assert result.total_row_count == 10
        assert result.returned_row_count == 5
        assert len(result.rows) == 5

    def test_columns_match_channels_time_first(self):
        active = _active_source(n=3)

        result = fetch_table_rows(active, offset=0, limit=3)

        keys = [c.key for c in result.columns]
        assert keys[0] == "time"
        assert "VA" in keys
        assert "BRK_A" in keys

    def test_exact_values_not_reduced(self):
        active = _active_source(n=10, timing_reference="relative_elapsed")

        result = fetch_table_rows(active, offset=0, limit=10)

        # VA is a deterministic ramp (0, 10, 20, ...) -- exact values,
        # never a min/max envelope or any other reduction.
        va_index = [c.key for c in result.columns].index("VA")
        assert [row[va_index] for row in result.rows] == [float(i * 10) for i in range(10)]

    def test_column_order_matches_canonical_channel_order(self):
        analog = [
            AnalogChannelSummary(name="VC", index=0, unit="V", engineering_type="Voltage"),
            AnalogChannelSummary(name="VA", index=1, unit="V", engineering_type="Voltage"),
        ]
        active = _active_source(n=2, analog=analog, digital=[])

        columns = build_table_columns(active)

        assert [c.key for c in columns] == ["time", "VC", "VA"]  # never re-sorted alphabetically


class TestFirstLastPartialPage:
    def test_first_page(self):
        active = _active_source(n=25)

        result = fetch_table_rows(active, offset=0, limit=10)

        assert result.returned_row_count == 10
        assert result.total_row_count == 25

    def test_last_page_partial(self):
        active = _active_source(n=25)

        result = fetch_table_rows(active, offset=20, limit=10)

        assert result.returned_row_count == 5  # 25 - 20
        assert result.total_row_count == 25

    def test_offset_beyond_total_yields_empty_page_not_error(self):
        active = _active_source(n=10)

        result = fetch_table_rows(active, offset=1000, limit=10)

        assert result.returned_row_count == 0
        assert result.total_row_count == 10
        assert result.rows == []

    def test_offset_beyond_total_reports_correct_columns_even_when_empty(self):
        active = _active_source(n=10)

        result = fetch_table_rows(active, offset=1000, limit=10)

        assert len(result.columns) == 3  # time, VA, BRK_A


class TestDifferentSourcesIndependent:
    def test_two_sources_return_independent_rows(self):
        source_a = _active_source(n=5, source_id="src-a", analog=[AnalogChannelSummary(name="V_A", index=0, unit="V", engineering_type="Voltage")])
        source_b = _active_source(n=8, source_id="src-b", analog=[AnalogChannelSummary(name="V_B", index=0, unit="V", engineering_type="Voltage")])

        result_a = fetch_table_rows(source_a, offset=0, limit=100)
        result_b = fetch_table_rows(source_b, offset=0, limit=100)

        assert result_a.total_row_count == 5
        assert result_b.total_row_count == 8
        assert [c.key for c in result_a.columns] != [c.key for c in result_b.columns]
        # No merging: source A's rows never appear in source B's response.
        assert result_a.source_id == "src-a"
        assert result_b.source_id == "src-b"


class TestIrregularTime:
    def test_exact_irregular_timestamps_preserved(self):
        time = np.array([0.000, 0.020, 0.041, 0.060], dtype=np.float64)
        active = _active_source(time=time, timing_reference="relative_elapsed")

        result = fetch_table_rows(active, offset=0, limit=10)

        time_index = 0
        assert [row[time_index] for row in result.rows] == ["0.000", "0.020", "0.041", "0.060"]


class TestMultiRateCanonicalTime:
    def test_multi_rate_segments_already_unified_one_time_array(self):
        # Segment 1: 5 samples @ 1000 Hz (0.001s steps); segment 2: 5
        # samples @ 2000 Hz (0.0005s steps), continuing from where
        # segment 1 left off -- exactly how app.providers.comtrade
        # already unifies a multi-rate COMTRADE record into ONE
        # waveform_data/time array at import time (no per-segment
        # fragmentation for this module to reconcile).
        seg1 = np.arange(5, dtype=np.float64) * 0.001
        seg2 = seg1[-1] + 0.0005 + np.arange(5, dtype=np.float64) * 0.0005
        time = np.concatenate([seg1, seg2])
        active = _active_source(
            time=time, timing_reference="relative_elapsed",
            sampling_rates=(1000.0, 2000.0), samples_per_rate=(5, 5),
        )

        result = fetch_table_rows(active, offset=0, limit=10)

        time_index = 0
        actual = [row[time_index] for row in result.rows]
        expected = [f"{t:.3f}" for t in time]
        assert actual == expected
        assert result.total_row_count == 10


class TestEngineeringQuantity:
    def test_metadata_preserved_in_columns(self):
        analog = [
            AnalogChannelSummary(name="V1", index=0, unit="V", engineering_type="Voltage", engineering_quantity="Voltage"),
            AnalogChannelSummary(name="V1 Angle", index=1, unit="", engineering_type="Voltage", engineering_quantity="Voltage Angle"),
        ]
        active = _active_source(n=3, analog=analog, digital=[])

        columns = build_table_columns(active)

        by_key = {c.key: c for c in columns}
        assert by_key["V1"].engineering_quantity == "Voltage"
        assert by_key["V1 Angle"].engineering_quantity == "Voltage Angle"
        # Angle channels are never collapsed to only the broad type --
        # richer metadata is preserved verbatim (task section 22).
        assert by_key["V1 Angle"].engineering_type == "Voltage"

    def test_undefined_quantity_is_valid(self):
        analog = [AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")]  # no quantity set
        active = _active_source(n=2, analog=analog, digital=[])

        columns = build_table_columns(active)

        assert columns[1].engineering_quantity == "Undefined"

    def test_unit_never_invented_from_quantity(self):
        # CSV/Excel quantity = Voltage but unit stays "" (DEC-077's own
        # conversion-gap finding) -- Table View must never invent "kV".
        analog = [AnalogChannelSummary(name="V1", index=0, unit="", engineering_type="Voltage", engineering_quantity="Voltage")]
        active = _active_source(n=2, analog=analog, digital=[])

        columns = build_table_columns(active)

        assert columns[1].unit == ""


class TestAngleChannelsUnchanged:
    def test_angle_values_returned_verbatim(self):
        analog = [AnalogChannelSummary(name="V1 Angle", index=0, unit="", engineering_type="Voltage", engineering_quantity="Voltage Angle")]
        active = _active_source(n=3, analog=analog, digital=[])

        result = fetch_table_rows(active, offset=0, limit=3)

        angle_index = [c.key for c in result.columns].index("V1 Angle")
        # The deterministic ramp fixture (0, 10, 20) -- no scaling,
        # no degree/radian conversion, no secondary-axis-related logic.
        assert [row[angle_index] for row in result.rows] == [0.0, 10.0, 20.0]


class TestDigitalChannels:
    def test_digital_columns_included_by_default(self):
        active = _active_source(n=3)

        columns = build_table_columns(active)

        digital_cols = [c for c in columns if c.kind == COLUMN_KIND_DIGITAL]
        assert len(digital_cols) == 1
        assert digital_cols[0].key == "BRK_A"

    def test_digital_values_are_ints(self):
        active = _active_source(n=3)

        result = fetch_table_rows(active, offset=0, limit=3)

        digital_index = [c.key for c in result.columns].index("BRK_A")
        for row in result.rows:
            assert isinstance(row[digital_index], int)


class TestMissingValues:
    def test_nan_becomes_none_never_zero(self):
        analog = [AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")]
        active = _active_source(n=3, analog=analog, digital=[])
        active.record.waveform_data.loc[1, "VA"] = float("nan")

        result = fetch_table_rows(active, offset=0, limit=3)

        va_index = [c.key for c in result.columns].index("VA")
        assert result.rows[1][va_index] is None
        assert result.rows[0][va_index] == 0.0  # untouched neighbor, never coerced


class TestTimeColumnLabel:
    def test_absolute_label_is_time(self):
        active = _active_source(n=2, timing_reference="absolute")
        assert build_table_columns(active)[0].label == "Time"

    def test_relative_label_is_time_seconds(self):
        active = _active_source(n=2, timing_reference="relative_elapsed")
        assert build_table_columns(active)[0].label == "Time (s)"

    def test_absolute_reference_but_no_start_time_falls_back_to_relative(self):
        active = _active_source(n=2, timing_reference="absolute")
        active.metadata.start_time = None
        assert build_table_columns(active)[0].label == "Time (s)"

    def test_absolute_time_format_matches_dec074_convention(self):
        start = datetime(2026, 3, 6, 18, 4, 0, tzinfo=timezone.utc)
        time = np.array([0.0, 0.02], dtype=np.float64)
        active = _active_source(time=time, timing_reference="absolute", start_time=start)

        result = fetch_table_rows(active, offset=0, limit=2)

        assert result.rows[0][0] == "2026-03-06T18:04:00.000+00:00"
        assert result.rows[1][0] == "2026-03-06T18:04:00.020+00:00"


class TestPaginationBounds:
    def test_default_and_max_limit_constants_match_data_prep_convention(self):
        assert TABLE_DEFAULT_LIMIT == 200
        assert TABLE_MAX_LIMIT == 1000
