"""Unit tests for app.services.waveform_service.resolve_peak_value
(Phase 4G -- Maximum/Minimum Peak annotations, DEC-046).

Builds ActiveSource fixtures directly, same established pattern as
tests/test_annotation_anchor_service.py.
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
from app.services.errors import ChannelNotAnalogError, ChannelNotFoundError
from app.services.waveform_service import extract_waveform_range, resolve_peak_value, REPRESENTATION_FULL_RESOLUTION


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
            AnalogChannelSummary(name=name, index=i, unit="MW", engineering_type="Power")
            for i, name in enumerate(channels)
        ],
        digital_channels=[
            DigitalChannelSummary(name=name, index=i, normal_state=0) for i, name in enumerate(digital)
        ],
    )
    return ActiveSource(metadata=metadata, record=record)


class TestWindowedPeak:
    """Section 51: the peak must reflect only the requested interval, not
    the whole record's global extremum."""

    def test_local_max_within_viewport_not_global_max(self):
        # global max at t=1.0 -> 100; viewport 2..3 -> local max 70 at t=2.4
        time = np.array([0.0, 1.0, 2.0, 2.4, 2.8, 3.0, 4.0])
        values = np.array([0.0, 100.0, 50.0, 70.0, 60.0, 65.0, 10.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=2.0, end_time=3.0)

        assert result.available is True
        assert result.value == pytest.approx(70.0)
        assert result.elapsed_seconds == pytest.approx(2.4)
        assert result.sample_index == 3
        assert result.unit == "MW"

    def test_local_min_within_viewport(self):
        time = np.array([0.0, 1.0, 2.0, 2.4, 2.8, 3.0, 4.0])
        values = np.array([0.0, -100.0, -50.0, -70.0, -60.0, -65.0, -10.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="min", start_time=2.0, end_time=3.0)

        assert result.available is True
        assert result.value == pytest.approx(-70.0)
        assert result.elapsed_seconds == pytest.approx(2.4)


class TestTieRule:
    """Section 13/50/76 -- exact ties select the EARLIEST sample."""

    def test_max_tie_selects_earliest(self):
        time = np.array([1.2, 1.5, 1.8])
        values = np.array([100.0, 100.0, 100.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=1.0, end_time=2.0)

        assert result.elapsed_seconds == pytest.approx(1.2)
        assert result.sample_index == 0

    def test_regression_window_tie_max(self):
        # Section 50: [1, 5, 3, 5, 2] -> value=5, sample=first 5 (index 1)
        time = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        values = np.array([1.0, 5.0, 3.0, 5.0, 2.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=0.0, end_time=0.4)

        assert result.value == pytest.approx(5.0)
        assert result.sample_index == 1
        assert result.elapsed_seconds == pytest.approx(0.1)

    def test_regression_window_tie_min(self):
        # Section 50: [-2, -7, -3, -7] -> value=-7, sample=first -7 (index 1)
        time = np.array([0.0, 0.1, 0.2, 0.3])
        values = np.array([-2.0, -7.0, -3.0, -7.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="min", start_time=0.0, end_time=0.3)

        assert result.value == pytest.approx(-7.0)
        assert result.sample_index == 1


class TestRangeClipping:
    """Section 11 -- clip safely to the source's own bounds; never invent
    samples for a viewport that extends past this source's duration."""

    def test_viewport_wider_than_source_clips_to_intersection(self):
        time = np.array([0.0, 0.5, 1.0])
        values = np.array([10.0, 40.0, 20.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=-100.0, end_time=100.0)

        assert result.available is True
        assert result.value == pytest.approx(40.0)
        assert result.sample_index == 1

    def test_boundary_inclusive_at_both_ends(self):
        time = np.array([0.0, 0.1, 0.2])
        values = np.array([5.0, 1.0, 9.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=0.0, end_time=0.2)

        assert result.value == pytest.approx(9.0)
        assert result.sample_index == 2


class TestNoDataRange:
    """Section 12/14 -- no valid samples in the intersection means
    `available=False`, never a fabricated/clamped peak."""

    def test_viewport_entirely_outside_source_bounds_is_unavailable(self):
        time = np.array([0.0, 0.1, 0.2])
        values = np.array([5.0, 1.0, 9.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=5.0, end_time=6.0)

        assert result.available is False
        assert result.sample_index is None
        assert result.elapsed_seconds is None
        assert result.value is None
        assert result.unit is None

    def test_all_nan_in_interval_is_unavailable(self):
        time = np.array([0.0, 0.1, 0.2])
        values = np.array([np.nan, np.nan, np.nan])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=0.0, end_time=0.2)

        assert result.available is False


class TestNonFiniteHandling:
    """Section 14 -- NaN/inf samples are ignored, never selected as a peak."""

    def test_nan_never_wins_max(self):
        time = np.array([0.0, 0.1, 0.2, 0.3])
        values = np.array([10.0, np.nan, 30.0, 20.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=0.0, end_time=0.3)

        assert result.value == pytest.approx(30.0)
        assert result.sample_index == 2

    def test_inf_never_wins_max(self):
        time = np.array([0.0, 0.1, 0.2])
        values = np.array([10.0, np.inf, 5.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="max", start_time=0.0, end_time=0.2)

        assert result.value == pytest.approx(10.0)
        assert result.sample_index == 0

    def test_negative_inf_never_wins_min(self):
        time = np.array([0.0, 0.1, 0.2])
        values = np.array([10.0, -np.inf, 5.0])
        active = _active_source(time=time, channels={"MW1": values})

        result = resolve_peak_value(active, channel_name="MW1", mode="min", start_time=0.0, end_time=0.2)

        assert result.value == pytest.approx(5.0)
        assert result.sample_index == 2


class TestChannelValidation:
    def test_unknown_channel_raises_channel_not_found(self):
        active = _active_source(time=np.array([0.0, 0.1]), channels={"MW1": np.array([1.0, 2.0])})
        with pytest.raises(ChannelNotFoundError):
            resolve_peak_value(active, channel_name="NOPE", mode="max", start_time=0.0, end_time=0.1)

    def test_digital_channel_raises_channel_not_analog(self):
        active = _active_source(
            time=np.array([0.0, 0.1]),
            channels={"MW1": np.array([1.0, 2.0])},
            digital={"CB_TRIP": np.array([0, 1])},
        )
        with pytest.raises(ChannelNotAnalogError):
            resolve_peak_value(active, channel_name="CB_TRIP", mode="max", start_time=0.0, end_time=0.1)


class TestFullResolutionAuthority:
    """Section 8/49/70/74 -- peak must come from full-resolution source
    data, not the reduced display envelope, even for a broad range that
    WOULD be reduced by the display waveform endpoint."""

    def test_peak_bypasses_min_max_envelope_reduction(self):
        n = 20_000
        time = np.arange(n, dtype=np.float64) / 10_000.0
        rng = np.random.default_rng(42)
        values = rng.normal(size=n) * 10.0
        # plant a true max at a sample deliberately unlikely to survive
        # min/max envelope reduction at a coarse budget
        true_max_idx = 12345
        values[true_max_idx] = 99999.0
        active = _active_source(time=time, channels={"MW1": values})

        range_result = extract_waveform_range(active, channel_name="MW1", start_time=None, end_time=None, point_budget=50)
        assert range_result.representation != REPRESENTATION_FULL_RESOLUTION

        result = resolve_peak_value(
            active, channel_name="MW1", mode="max", start_time=float(time[0]), end_time=float(time[-1])
        )
        assert result.value == pytest.approx(99999.0)
        assert result.sample_index == true_max_idx


class TestMultiSourceIsolation:
    def test_two_sources_resolve_independently(self):
        a = _active_source(source_id="src-a", time=np.array([0.0, 1.0]), channels={"MW1": np.array([5.0, 50.0])})
        b = _active_source(source_id="src-b", time=np.array([0.0, 1.0]), channels={"MW1": np.array([500.0, 5.0])})

        result_a = resolve_peak_value(a, channel_name="MW1", mode="max", start_time=0.0, end_time=1.0)
        result_b = resolve_peak_value(b, channel_name="MW1", mode="max", start_time=0.0, end_time=1.0)

        assert result_a.value == pytest.approx(50.0)
        assert result_b.value == pytest.approx(500.0)
