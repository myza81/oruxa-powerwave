"""Unit tests for app.services.waveform_service.resolve_annotation_anchor
(Phase 4F -- Callout annotation anchor resolution, DEC-045).

Builds ActiveSource fixtures directly (not via the COMTRADE parser), same
established pattern as tests/test_cursor_values_service.py, so nearest-
sample index/bounds/tie logic can be tested against precisely known
times/values.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.errors import ChannelNotAnalogError, ChannelNotFoundError, InvalidTimeRangeError
from app.services.waveform_service import (
    REPRESENTATION_FULL_RESOLUTION,
    extract_waveform_range,
    resolve_annotation_anchor,
)


def _active_source(
    *,
    source_id: str = "src-1",
    time: np.ndarray,
    channels: dict[str, np.ndarray],
    digital: dict[str, np.ndarray] | None = None,
) -> ActiveSource:
    now = datetime.now(timezone.utc)
    col_data = {"time": time, **channels}
    digital = digital or {}
    col_data.update(digital)

    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH",
            recorder_name="TEST",
            source_file="synthetic.cfg",
            provider_type="COMTRADE",
            nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(col_data),
        analog_channels=[],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id=source_id,
        workspace_id="ws-1",
        provider_type="COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"),
        created_at=now,
        station_name="SYNTH",
        recorder_name="TEST",
        nominal_frequency=50.0,
        timing_reference="absolute",
        start_time=now,
        trigger_time=now,
        sample_count=len(time),
        duration_seconds=float(time[-1] - time[0]) if len(time) else 0.0,
        elapsed_start_seconds=float(time[0]) if len(time) else 0.0,
        elapsed_end_seconds=float(time[-1]) if len(time) else 0.0,
        sampling_rates=(1.0,),
        samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(name=name, index=i, unit="V", engineering_type="Voltage")
            for i, name in enumerate(channels)
        ],
        digital_channels=[
            DigitalChannelSummary(name=name, index=i, normal_state=0) for i, name in enumerate(digital)
        ],
    )
    return ActiveSource(metadata=metadata, record=record)


def _worked_example_source() -> ActiveSource:
    # Same deterministic fixture as test_cursor_values_service.py's own
    # worked example: times 0.0/0.1/0.2/0.3, values 10/20/30/40.
    return _active_source(
        time=np.array([0.0, 0.1, 0.2, 0.3]),
        channels={"VA": np.array([10.0, 20.0, 30.0, 40.0])},
        digital={"CB_TRIP": np.array([0, 0, 1, 1])},
    )


def _five_khz_source() -> ActiveSource:
    # Section 71's own "5 kHz waveform" fixture.
    n = 5000
    time = np.arange(n, dtype=np.float64) / 5000.0
    values = np.arange(n, dtype=np.float64)
    return _active_source(time=time, channels={"VA": values})


class TestNearestSampleAnchor:
    """Section 6/7 -- anchor snaps to the nearest ACTUAL recorded sample,
    never interpolated, using the exact same nearest-sample/tie-break rule
    as A/B cursor values."""

    def test_click_between_samples_snaps_to_nearest(self):
        active = _worked_example_source()
        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=0.14)
        assert result.sample_index == 1
        assert result.elapsed_seconds == pytest.approx(0.1)
        assert result.value == pytest.approx(20.0)
        assert result.unit == "V"
        assert result.source_id == "src-1"
        assert result.channel_name == "VA"

    def test_exact_sample_match(self):
        active = _worked_example_source()
        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=0.2)
        assert result.sample_index == 2
        assert result.value == pytest.approx(30.0)

    def test_exact_midpoint_tie_prefers_earlier_sample(self):
        # Section 7 of the task: "preserve the established deterministic
        # tie rule, preferably earlier sample if that is current
        # behavior" -- 0.15 is exactly between 0.1 (idx 1) and 0.2 (idx 2).
        active = _worked_example_source()
        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=0.15)
        assert result.sample_index == 1
        assert result.elapsed_seconds == pytest.approx(0.1)
        assert result.value == pytest.approx(20.0)

    def test_five_khz_waveform_click_between_samples(self):
        # Section 71: click approximately between samples on a 5 kHz
        # synthetic waveform; verify exact nearest-sample resolution.
        active = _five_khz_source()
        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=0.50013)
        assert result.sample_index == 2501
        assert result.elapsed_seconds == pytest.approx(0.5002, abs=1e-9)
        assert result.value == pytest.approx(2501.0)


class TestFullResolutionAuthority:
    """Section 16/72 -- the anchor must come from full-resolution source
    data, not a reduced display representation, even for a broad range
    that WOULD be reduced by the display waveform endpoint. The resolved
    anchor may be a sample not literally present in the reduced Plotly
    trace array -- that is correct."""

    def test_anchor_bypasses_min_max_envelope_reduction(self):
        n = 20_000
        time = np.arange(n, dtype=np.float64) / 10_000.0
        values = np.sin(np.arange(n, dtype=np.float64) * 0.7) * 100.0 + np.arange(n, dtype=np.float64) * 0.001
        active = _active_source(time=time, channels={"VA": values})
        approximate_time = 0.50017

        range_result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=50
        )
        assert range_result.representation != REPRESENTATION_FULL_RESOLUTION
        assert approximate_time not in range_result.time.tolist()

        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=approximate_time)

        # The full-resolution nearest sample, independently computed.
        expected_idx = int(np.searchsorted(time, approximate_time, side="left"))
        before, after = time[expected_idx - 1], time[expected_idx]
        if (approximate_time - before) <= (after - approximate_time):
            expected_idx -= 1
        assert result.sample_index == expected_idx
        assert result.value == pytest.approx(float(values[expected_idx]))
        # And the resolved value is not necessarily one the reduced
        # envelope kept, reinforcing the two code paths are independent.
        assert float(values[expected_idx]) not in range_result.values.tolist()


class TestChannelValidation:
    """Section 8 -- analog only this phase; unknown/digital channel names
    are rejected, never silently attached to the wrong trace."""

    def test_unknown_channel_raises_channel_not_found(self):
        active = _worked_example_source()
        with pytest.raises(ChannelNotFoundError):
            resolve_annotation_anchor(active, channel_name="NOPE", approximate_elapsed_seconds=0.1)

    def test_digital_channel_raises_channel_not_analog(self):
        active = _worked_example_source()
        with pytest.raises(ChannelNotAnalogError):
            resolve_annotation_anchor(active, channel_name="CB_TRIP", approximate_elapsed_seconds=0.1)


class TestOutOfBounds:
    """Section 66 -- an out-of-bounds click must be rejected outright, not
    clamped to a boundary sample or otherwise silently approximated."""

    def test_before_source_start_raises_invalid_time_range(self):
        active = _worked_example_source()
        with pytest.raises(InvalidTimeRangeError):
            resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=-1.0)

    def test_after_source_end_raises_invalid_time_range(self):
        active = _worked_example_source()
        with pytest.raises(InvalidTimeRangeError):
            resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=10.0)

    def test_exactly_at_bounds_is_in_bounds(self):
        active = _worked_example_source()
        result = resolve_annotation_anchor(active, channel_name="VA", approximate_elapsed_seconds=0.3)
        assert result.sample_index == 3
        assert result.value == pytest.approx(40.0)


class TestMultiSourceIsolation:
    """Section 4 (shared with A/B cursors) -- each source's own native
    time array is searched independently."""

    def test_two_sources_same_channel_name_resolve_independently(self):
        fine = _five_khz_source()
        coarse = _active_source(
            source_id="src-coarse",
            time=np.arange(1000, dtype=np.float64) / 1000.0,
            channels={"VA": np.arange(1000, dtype=np.float64)},
        )
        approximate_time = 0.50013
        fine_result = resolve_annotation_anchor(fine, channel_name="VA", approximate_elapsed_seconds=approximate_time)
        coarse_result = resolve_annotation_anchor(
            coarse, channel_name="VA", approximate_elapsed_seconds=approximate_time
        )
        assert fine_result.source_id == "src-1"
        assert coarse_result.source_id == "src-coarse"
        assert fine_result.sample_index == 2501
        assert coarse_result.sample_index == 500
