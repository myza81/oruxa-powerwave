"""Unit tests for app.services.waveform_service.extract_cursor_values /
_nearest_sample_index (Phase 4C1 -- instantaneous A/B cursor values).

Builds ActiveSource fixtures directly (not via the COMTRADE parser), same
established pattern as tests/test_waveform_service.py, so nearest-sample
index/bounds/tie logic can be tested against precisely known times/values.
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
from app.services.waveform_service import (
    REPRESENTATION_FULL_RESOLUTION,
    _nearest_sample_index,
    extract_cursor_values,
    extract_waveform_range,
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


# Section 41's own deterministic fixture: times 0.0/0.1/0.2/0.3, values 10/20/30/40.
def _worked_example_source() -> ActiveSource:
    return _active_source(
        time=np.array([0.0, 0.1, 0.2, 0.3]),
        channels={"VA": np.array([10.0, 20.0, 30.0, 40.0])},
    )


class TestNearestSampleIndex:
    """Section 41 -- nearest sample, exactly the task's own worked example."""

    def test_cursor_0_14_snaps_to_0_1_value_20(self):
        active = _worked_example_source()
        time_full = active.record.waveform_data["time"].to_numpy()
        idx = _nearest_sample_index(time_full, 0.14)
        assert idx == 1
        assert time_full[idx] == pytest.approx(0.1)

    def test_cursor_0_18_snaps_to_0_2_value_30(self):
        active = _worked_example_source()
        time_full = active.record.waveform_data["time"].to_numpy()
        idx = _nearest_sample_index(time_full, 0.18)
        assert idx == 2
        assert time_full[idx] == pytest.approx(0.2)

    def test_exact_sample_match_returns_that_exact_sample(self):
        active = _worked_example_source()
        time_full = active.record.waveform_data["time"].to_numpy()
        assert _nearest_sample_index(time_full, 0.2) == 2

    def test_first_and_last_sample_bounds(self):
        active = _worked_example_source()
        time_full = active.record.waveform_data["time"].to_numpy()
        assert _nearest_sample_index(time_full, 0.0) == 0
        assert _nearest_sample_index(time_full, 0.3) == 3


class TestTieBehaviour:
    """Section 42 -- exact midpoint (0.15, exactly between 0.1 and 0.2)
    deterministically resolves to the EARLIER sample (index 1, value 0.1),
    documented and regression-guarded here per that section's own
    explicit instruction."""

    def test_exact_midpoint_prefers_earlier_sample(self):
        active = _worked_example_source()
        time_full = active.record.waveform_data["time"].to_numpy()
        idx = _nearest_sample_index(time_full, 0.15)
        assert idx == 1
        assert time_full[idx] == pytest.approx(0.1)

    def test_result_earlier_sample_value_is_20(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=0.15, cursor_b_time=None)
        assert result.channels[0].a_value == pytest.approx(20.0)


class TestBoundsBehaviour:
    """Section 12 -- outside a source's true bounds returns no measurement,
    NEVER clamped to the boundary sample."""

    def test_cursor_before_source_start_returns_none(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=-1.0, cursor_b_time=None)
        assert result.cursor_a.sample_time is None
        assert result.channels[0].a_value is None

    def test_cursor_after_source_end_returns_none(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=10.0, cursor_b_time=None)
        assert result.cursor_a.sample_time is None
        assert result.channels[0].a_value is None
        # requested_time itself is preserved even when out of bounds -- the
        # frontend/caller may still want to know what was asked for.
        assert result.cursor_a.requested_time == pytest.approx(10.0)

    def test_cursor_exactly_at_bounds_is_in_bounds(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=0.3, cursor_b_time=None)
        assert result.cursor_a.sample_time == pytest.approx(0.3)
        assert result.channels[0].a_value == pytest.approx(40.0)


class TestFullResolutionAuthority:
    """Section 43 -- the critical engineering-integrity test: cursor values
    must reflect the true full-resolution sample, never a reduced/
    downsampled display representation, even when the identical range
    WOULD be reduced by the display waveform endpoint."""

    def test_cursor_value_matches_full_resolution_even_when_display_range_is_reduced(self):
        # More than the display full-resolution threshold -- request a
        # tiny point_budget so
        # extract_waveform_range is FORCED to build a min/max envelope
        # (a real reduced display representation), then confirm the
        # cursor's own value still comes from the true raw sample, not
        # from any point that envelope kept.
        n = 20_000
        time = np.arange(n, dtype=np.float64) / 10_000.0  # 0.0 .. 0.9999
        # A distinctive, non-monotonic signal so the envelope's kept
        # min/max points are very unlikely to coincide with an arbitrary
        # interior sample by chance.
        values = np.sin(np.arange(n, dtype=np.float64) * 0.7) * 100.0 + np.arange(n, dtype=np.float64) * 0.001
        active = _active_source(time=time, channels={"VA": values})

        # An interior time deliberately not aligned to any "nice" envelope
        # bucket boundary.
        cursor_time = 0.50017

        range_result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=50
        )
        assert range_result.representation != REPRESENTATION_FULL_RESOLUTION
        # None of the (much sparser) displayed/reduced points is exactly at
        # cursor_time -- confirms this really is a reduced representation,
        # not a coincidentally-identical one.
        assert cursor_time not in range_result.time.tolist()

        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=cursor_time, cursor_b_time=None)

        true_idx = _nearest_sample_index(time, cursor_time)
        assert result.channels[0].a_value == pytest.approx(float(values[true_idx]))
        # And that true value is generally NOT one of the envelope's own
        # (min/max, not nearest-sample) kept values, reinforcing that the
        # two code paths are genuinely independent.
        assert float(values[true_idx]) not in range_result.values.tolist()


class TestMultiRateSources:
    """Section 4/47 -- each source's own native time array is searched
    independently; no shared/assumed sample index across sources."""

    def test_fine_and_coarse_rate_sources_each_use_their_own_time_array(self):
        fine = _active_source(
            source_id="src-fine",
            time=np.arange(5000, dtype=np.float64) / 5000.0,  # 5000 Hz
            channels={"VA": np.arange(5000, dtype=np.float64)},
        )
        coarse = _active_source(
            source_id="src-coarse",
            time=np.arange(1000, dtype=np.float64) / 1000.0,  # 1000 Hz
            channels={"VA": np.arange(1000, dtype=np.float64)},
        )

        cursor_time = 0.50013
        fine_result = extract_cursor_values(fine, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=cursor_time, cursor_b_time=None)
        coarse_result = extract_cursor_values(
            coarse, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=cursor_time, cursor_b_time=None
        )

        # Fine source: nearest sample of 0.50013*5000=2500.65 -> index 2501 (0.5002s)
        assert fine_result.cursor_a.sample_time == pytest.approx(0.5002, abs=1e-9)
        assert fine_result.channels[0].a_value == pytest.approx(2501.0)
        # Coarse source: nearest sample of 0.50013*1000=500.13 -> index 500 (0.5s)
        assert coarse_result.cursor_a.sample_time == pytest.approx(0.5, abs=1e-9)
        assert coarse_result.channels[0].a_value == pytest.approx(500.0)


class TestBatchedIndexReuse:
    """Section 10 -- one index lookup per cursor per source, reused by
    every requested channel (never re-searched per channel)."""

    def test_multiple_channels_share_the_same_two_resolved_indices(self):
        time = np.array([0.0, 0.1, 0.2, 0.3])
        active = _active_source(
            time=time,
            channels={
                "VA": np.array([10.0, 20.0, 30.0, 40.0]),
                "VB": np.array([100.0, 200.0, 300.0, 400.0]),
                "IA": np.array([1.0, 2.0, 3.0, 4.0]),
            },
        )
        result = extract_cursor_values(
            active, analog_channel_names=["VA", "VB", "IA"], digital_channel_names=[], cursor_a_time=0.14, cursor_b_time=0.18
        )
        assert len(result.channels) == 3
        by_name = {c.channel_name: c for c in result.channels}
        # All three channels resolve to the SAME index-1 (A) / index-2 (B)
        # per the shared time array -- proportional relationship confirms
        # each channel's own value array was read at the identical index.
        assert by_name["VA"].a_value == pytest.approx(20.0)
        assert by_name["VB"].a_value == pytest.approx(200.0)
        assert by_name["IA"].a_value == pytest.approx(2.0)
        assert by_name["VA"].b_value == pytest.approx(30.0)
        assert by_name["VB"].b_value == pytest.approx(300.0)
        assert by_name["IA"].b_value == pytest.approx(3.0)


class TestUnknownChannelHandling:
    """Unknown/non-analog channel names are silently skipped, not raised --
    see extract_cursor_values's own docstring for why (never blank the
    whole batch for one bad name during live dragging)."""

    def test_unknown_channel_name_is_omitted_not_raised(self):
        active = _worked_example_source()
        result = extract_cursor_values(
            active, analog_channel_names=["VA", "DOES_NOT_EXIST"], digital_channel_names=[], cursor_a_time=0.1, cursor_b_time=None
        )
        assert len(result.channels) == 1
        assert result.channels[0].channel_name == "VA"

    def test_digital_channel_name_is_omitted_not_raised(self):
        active = _active_source(
            time=np.array([0.0, 0.1, 0.2, 0.3]),
            channels={"VA": np.array([10.0, 20.0, 30.0, 40.0])},
            digital={"BRK_A": np.array([0, 0, 1, 1], dtype=np.int8)},
        )
        result = extract_cursor_values(
            active, analog_channel_names=["VA", "BRK_A"], digital_channel_names=[], cursor_a_time=0.1, cursor_b_time=None
        )
        assert len(result.channels) == 1
        assert result.channels[0].channel_name == "VA"


class TestBothCursorsIndependentlyOptional:
    def test_only_cursor_a_supplied(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=0.1, cursor_b_time=None)
        assert result.cursor_a is not None
        assert result.cursor_b is None
        assert result.channels[0].a_value == pytest.approx(20.0)
        assert result.channels[0].b_value is None

    def test_only_cursor_b_supplied(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=None, cursor_b_time=0.2)
        assert result.cursor_a is None
        assert result.cursor_b is not None
        assert result.channels[0].a_value is None
        assert result.channels[0].b_value == pytest.approx(30.0)

    def test_neither_cursor_supplied_still_returns_channels_with_null_values(self):
        active = _worked_example_source()
        result = extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=None, cursor_b_time=None)
        assert result.cursor_a is None
        assert result.cursor_b is None
        assert result.channels[0].a_value is None
        assert result.channels[0].b_value is None


class TestNoMutation:
    """Section 40 -- read-only analysis; the source record is untouched."""

    def test_original_waveform_data_is_unchanged_after_repeated_calls(self):
        active = _worked_example_source()
        before = active.record.waveform_data.copy(deep=True)
        extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=0.14, cursor_b_time=0.18)
        extract_cursor_values(active, analog_channel_names=["VA"], digital_channel_names=[], cursor_a_time=0.29, cursor_b_time=0.01)
        pd.testing.assert_frame_equal(active.record.waveform_data, before)


# ============================================================================
# Phase 4C2 -- digital A/B cursor state. Digital channels live in the SAME
# waveform_data DataFrame, sharing the SAME "time" column as analog
# channels (confirmed via app.providers.comtrade._build_dataframe) -- so
# every test below exercises the identical _nearest_sample_index() path,
# just reading a digital column and asserting an int state instead of a
# float value.
# ============================================================================


class TestDigitalStaticState:
    """Section 35 -- deterministic fixture: times 0.0/0.1/0.2/0.3, digital
    states 0/0/1/1. Every cursor point lands exactly on a real sample."""

    def _fixture(self) -> ActiveSource:
        return _active_source(
            time=np.array([0.0, 0.1, 0.2, 0.3]),
            channels={},
            digital={"BRK": np.array([0, 0, 1, 1], dtype=np.int8)},
        )

    def test_each_exact_sample_returns_its_own_recorded_state(self):
        active = self._fixture()
        for t, expected in [(0.0, 0), (0.1, 0), (0.2, 1), (0.3, 1)]:
            result = extract_cursor_values(
                active, analog_channel_names=[], digital_channel_names=["BRK"],
                cursor_a_time=t, cursor_b_time=None,
            )
            assert result.digital_channels[0].a_state == expected, f"t={t}"

    def test_state_is_plain_int_not_float_or_bool(self):
        active = self._fixture()
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=0.2, cursor_b_time=None,
        )
        state = result.digital_channels[0].a_state
        assert type(state) is int
        assert state == 1


class TestDigitalTransitions:
    """Section 36 -- sparse transitions interpreted correctly: 0 until
    0.5, 1 from 0.5 until 1.0, 0 from 1.0 onward. Built as a dense
    per-sample array (0.01s step) since that is how digital channels are
    ACTUALLY retained internally (see extract_cursor_values's own
    docstring) -- not a second, transition-interval-search
    implementation. Section 6's exact-transition-timestamp rule ("state
    at T = the NEW state beginning at T") falls out for free: the
    recorded sample AT t=0.50 already holds the new state 1, and AT
    t=1.00 already holds the new (falling-edge) state 0, by construction
    of how the source data itself is built."""

    def _fixture(self) -> ActiveSource:
        time = np.arange(151, dtype=np.float64) * 0.01  # 0.00 .. 1.50
        state = np.where((time >= 0.5) & (time < 1.0), 1, 0).astype(np.int8)
        return _active_source(time=time, channels={}, digital={"BRK": state})

    def test_worked_examples_from_the_task_spec(self):
        active = self._fixture()
        for t, expected in [(0.49, 0), (0.50, 1), (0.75, 1), (1.00, 0), (1.20, 0)]:
            result = extract_cursor_values(
                active, analog_channel_names=[], digital_channel_names=["BRK"],
                cursor_a_time=t, cursor_b_time=None,
            )
            assert result.digital_channels[0].a_state == expected, f"t={t}"

    def test_rising_edge_exact_timestamp_reads_the_new_state(self):
        """Section 6, explicit: cursor exactly AT a rising transition
        (0 -> 1 at t=0.500) reads 1, the NEW state, never the old one."""
        active = self._fixture()
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=0.500, cursor_b_time=None,
        )
        assert result.digital_channels[0].a_state == 1

    def test_falling_edge_exact_timestamp_reads_the_new_state(self):
        """Same rule, falling edge (1 -> 0 at t=1.000) reads 0."""
        active = self._fixture()
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=1.000, cursor_b_time=None,
        )
        assert result.digital_channels[0].a_state == 0


class TestDigitalOutsideBounds:
    """Section 37 -- cursor time outside this source's own bounds returns
    `None`, NEVER the last/first recorded state."""

    def test_cursor_beyond_source_end_returns_none_not_last_state(self):
        active = _active_source(
            time=np.array([0.0, 0.5, 1.0]),
            channels={},
            digital={"BRK": np.array([0, 1, 0], dtype=np.int8)},
        )
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=None, cursor_b_time=1.5,
        )
        assert result.digital_channels[0].b_state is None
        assert result.cursor_b.sample_time is None


class TestDigitalBatchedWithAnalog:
    """Section 16/17 -- a single request covering BOTH analog and digital
    channels for one source shares the SAME two resolved indices; never a
    second index computation for digital."""

    def test_analog_and_digital_channels_share_the_same_resolved_indices(self):
        time = np.array([0.0, 0.1, 0.2, 0.3])
        active = _active_source(
            time=time,
            channels={"VA": np.array([10.0, 20.0, 30.0, 40.0])},
            digital={"BRK": np.array([0, 0, 1, 1], dtype=np.int8)},
        )
        result = extract_cursor_values(
            active, analog_channel_names=["VA"], digital_channel_names=["BRK"],
            cursor_a_time=0.14, cursor_b_time=0.18,
        )
        # cursor_a=0.14 -> nearest index 1 (t=0.1); cursor_b=0.18 -> nearest index 2 (t=0.2)
        assert result.channels[0].a_value == pytest.approx(20.0)
        assert result.channels[0].b_value == pytest.approx(30.0)
        assert result.digital_channels[0].a_state == 0
        assert result.digital_channels[0].b_state == 1


class TestDigitalUnknownChannelHandling:
    """Unknown/wrong-kind digital channel names are silently skipped, not
    raised -- symmetric with TestUnknownChannelHandling's analog case."""

    def test_unknown_digital_channel_name_is_omitted_not_raised(self):
        active = _active_source(
            time=np.array([0.0, 0.1]), channels={}, digital={"BRK": np.array([0, 1], dtype=np.int8)},
        )
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK", "DOES_NOT_EXIST"],
            cursor_a_time=0.1, cursor_b_time=None,
        )
        assert len(result.digital_channels) == 1
        assert result.digital_channels[0].channel_name == "BRK"

    def test_analog_channel_name_passed_as_digital_is_omitted_not_raised(self):
        active = _active_source(
            time=np.array([0.0, 0.1]),
            channels={"VA": np.array([10.0, 20.0])},
            digital={"BRK": np.array([0, 1], dtype=np.int8)},
        )
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["VA", "BRK"],
            cursor_a_time=0.1, cursor_b_time=None,
        )
        assert len(result.digital_channels) == 1
        assert result.digital_channels[0].channel_name == "BRK"


class TestDigitalSourceIsolation:
    """Section 45 -- two sources with the SAME digital channel name but
    DIFFERENT recorded states never collide; each source's own time array
    and own state array are looked up completely independently."""

    def test_same_channel_name_two_sources_different_states_no_collision(self):
        source_a = _active_source(
            source_id="src-a", time=np.array([0.0, 0.1]), channels={},
            digital={"TRIP": np.array([0, 0], dtype=np.int8)},
        )
        source_b = _active_source(
            source_id="src-b", time=np.array([0.0, 0.1]), channels={},
            digital={"TRIP": np.array([1, 1], dtype=np.int8)},
        )

        result_a = extract_cursor_values(
            source_a, analog_channel_names=[], digital_channel_names=["TRIP"],
            cursor_a_time=0.1, cursor_b_time=None,
        )
        result_b = extract_cursor_values(
            source_b, analog_channel_names=[], digital_channel_names=["TRIP"],
            cursor_a_time=0.1, cursor_b_time=None,
        )

        assert result_a.source_id == "src-a"
        assert result_b.source_id == "src-b"
        assert result_a.digital_channels[0].a_state == 0
        assert result_b.digital_channels[0].a_state == 1


class TestDigitalClassificationPreservation:
    """Section 46/28 -- cursor measurement never reads/depends on/mutates
    `normal_state` or `classification`; both are untouched by the call."""

    def test_classification_and_normal_state_unchanged_after_call(self):
        active = _active_source(
            time=np.array([0.0, 0.1]), channels={}, digital={"BRK": np.array([0, 1], dtype=np.int8)},
        )
        before = (active.metadata.digital_channels[0].classification, active.metadata.digital_channels[0].normal_state)
        extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=0.1, cursor_b_time=None,
        )
        after = (active.metadata.digital_channels[0].classification, active.metadata.digital_channels[0].normal_state)
        assert before == after

    def test_state_1_is_returned_regardless_of_configured_normal_state(self):
        """Section 28: a channel configured with normal_state=1 whose
        recorded value is 1 must still report a_state=1 -- never inverted
        or reinterpreted relative to what "normal" means for that
        channel."""
        now_time = np.array([0.0, 0.1])
        active = _active_source(time=now_time, channels={}, digital={"BRK": np.array([1, 1], dtype=np.int8)})
        # Directly override normal_state to 1 post-construction -- proves
        # the extraction path never reads it either way.
        active.metadata.digital_channels[0].normal_state = 1
        result = extract_cursor_values(
            active, analog_channel_names=[], digital_channel_names=["BRK"],
            cursor_a_time=0.0, cursor_b_time=None,
        )
        assert result.digital_channels[0].a_state == 1
