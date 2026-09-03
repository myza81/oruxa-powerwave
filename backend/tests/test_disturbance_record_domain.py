"""Tests for the Slice 10 (CSV/Excel ingestion, DEC-072) canonical-model
hardening: `TimingInformation.start_time`/`.trigger_time` becoming
`datetime | None`, `SamplingInformation.is_uniform`, and
`DisturbanceRecord.validate()`'s new time-finite/non-decreasing/
sample-count checks.

The most important test class here is `TestComtradeRegressionUnaffected`
-- this hardening must not change ANY observable COMTRADE behavior; a
real COMTRADE record is always finite, non-decreasing, and internally
consistent by construction, so it must continue to `validate()` clean
both before and after this slice.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.providers.comtrade import ComtradeProvider


def _record(
    *,
    time_values: list[float],
    channel_values: list[float] | None = None,
    start_time: dt.datetime | None = dt.datetime(2026, 1, 1, 0, 0, 0),
    trigger_time: dt.datetime | None = dt.datetime(2026, 1, 1, 0, 0, 1),
    sampling_rates: list[float] | None = None,
    samples_per_rate: list[int] | None = None,
) -> DisturbanceRecord:
    channel_values = channel_values if channel_values is not None else [float(i) for i in range(len(time_values))]
    waveform_data = pd.DataFrame({"time": time_values, "CH1": channel_values})
    return DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Test", recorder_name="Test", source_file="test.csv",
            provider_type="csv", nominal_frequency=50.0,
        ),
        waveform_data=waveform_data,
        analog_channels=[AnalogChannel(name="CH1", unit="V", index=0)],
        digital_channels=[],
        sampling_info=SamplingInformation(
            sampling_rates=sampling_rates if sampling_rates is not None else [50.0],
            samples_per_rate=samples_per_rate if samples_per_rate is not None else [len(time_values)],
        ),
        timing_info=TimingInformation(start_time=start_time, trigger_time=trigger_time),
    )


class TestTimingInformationOptionalFields:
    def test_start_time_and_trigger_time_default_to_none(self):
        timing = TimingInformation(start_time=None, trigger_time=None)

        assert timing.start_time is None
        assert timing.trigger_time is None

    def test_still_accepts_real_datetimes_unchanged(self):
        start = dt.datetime(2026, 1, 1)
        trigger = dt.datetime(2026, 1, 1, 0, 0, 1)
        timing = TimingInformation(start_time=start, trigger_time=trigger)

        assert timing.start_time == start
        assert timing.trigger_time == trigger


class TestSamplingInformationIsUniform:
    def test_defaults_to_true(self):
        sampling = SamplingInformation(sampling_rates=[50.0], samples_per_rate=[10])

        assert sampling.is_uniform is True

    def test_can_be_set_false(self):
        sampling = SamplingInformation(sampling_rates=[50.0], samples_per_rate=[10], is_uniform=False)

        assert sampling.is_uniform is False


class TestValidateNoFakeTimestampsRequired:
    def test_both_start_and_trigger_none_does_not_fail_ordering_check(self):
        record = _record(time_values=[0.0, 0.02, 0.04], start_time=None, trigger_time=None)

        assert record.validate() == []

    def test_start_none_trigger_present_does_not_crash(self):
        record = _record(
            time_values=[0.0, 0.02], start_time=None, trigger_time=dt.datetime(2026, 1, 1),
        )

        assert record.validate() == []

    def test_trigger_before_start_still_reported_when_both_known(self):
        record = _record(
            time_values=[0.0, 0.02],
            start_time=dt.datetime(2026, 1, 1, 0, 0, 5),
            trigger_time=dt.datetime(2026, 1, 1, 0, 0, 1),
        )

        errors = record.validate()
        assert any("trigger_time cannot be before start_time" in e for e in errors)


class TestValidateTimeColumnHardening:
    def test_finite_non_decreasing_time_passes(self):
        record = _record(time_values=[0.0, 0.02, 0.04, 0.06])

        assert record.validate() == []

    def test_non_decreasing_allows_exact_repeats(self):
        # Slice 9's own readiness policy allows a WARNING-level repeated
        # value (e.g. repeated_elapsed_time) to reach a Ready/converted
        # source -- validate() must not reject a merely-flat step.
        record = _record(time_values=[0.0, 0.02, 0.02, 0.04])

        assert record.validate() == []

    def test_backward_time_is_reported_never_sorted(self):
        record = _record(time_values=[0.0, 0.04, 0.02, 0.06])

        errors = record.validate()
        assert any("non-decreasing" in e for e in errors)
        # Never silently repaired -- the DataFrame itself is untouched.
        assert list(record.waveform_data["time"]) == [0.0, 0.04, 0.02, 0.06]

    def test_nan_time_value_is_reported(self):
        record = _record(time_values=[0.0, float("nan"), 0.04])

        errors = record.validate()
        assert any("finite" in e for e in errors)

    def test_infinite_time_value_is_reported(self):
        record = _record(time_values=[0.0, float("inf"), 0.04])

        errors = record.validate()
        assert any("finite" in e for e in errors)

    def test_non_numeric_time_column_is_reported(self):
        waveform_data = pd.DataFrame({"time": ["a", "b", "c"], "CH1": [1.0, 2.0, 3.0]})
        record = DisturbanceRecord(
            metadata=RecordingMetadata(
                station_name="Test", recorder_name="Test", source_file="test.csv",
                provider_type="csv", nominal_frequency=50.0,
            ),
            waveform_data=waveform_data,
            analog_channels=[AnalogChannel(name="CH1", unit="V", index=0)],
            digital_channels=[],
            sampling_info=SamplingInformation(sampling_rates=[50.0], samples_per_rate=[3]),
            timing_info=TimingInformation(start_time=None, trigger_time=None),
        )

        errors = record.validate()
        assert any("must be numeric" in e for e in errors)

    def test_single_sample_never_flagged_backward(self):
        record = _record(time_values=[0.0], channel_values=[1.0])

        assert record.validate() == []


class TestValidateSamplingInfoConsistency:
    def test_matching_sample_count_passes(self):
        record = _record(time_values=[0.0, 0.02, 0.04], samples_per_rate=[3])

        assert record.validate() == []

    def test_mismatched_sample_count_is_reported(self):
        record = _record(time_values=[0.0, 0.02, 0.04], samples_per_rate=[5])

        errors = record.validate()
        assert any("samples_per_rate total does not match" in e for e in errors)

    def test_multi_rate_sections_still_supported(self):
        # COMTRADE's own multi-rate support -- two declared sections
        # whose sizes sum correctly must still validate cleanly.
        record = _record(
            time_values=[0.0, 0.01, 0.02, 0.04, 0.06],
            sampling_rates=[100.0, 50.0], samples_per_rate=[3, 2],
        )

        assert record.validate() == []


class TestComtradeRegressionUnaffected:
    """A real, parsed COMTRADE record must continue to validate cleanly
    and keep every pre-existing timing guarantee -- this hardening must
    be invisible to COMTRADE."""

    def test_synth_ascii_record_validates_clean(self, comtrade_fixtures_dir: Path):
        record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_ascii.cfg")

        assert record.validate() == []

    def test_synth_ascii_start_and_trigger_time_are_real_datetimes(self, comtrade_fixtures_dir: Path):
        record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_ascii.cfg")

        assert isinstance(record.timing_info.start_time, dt.datetime)
        assert isinstance(record.timing_info.trigger_time, dt.datetime)

    def test_synth_ascii_sampling_info_is_uniform_by_default(self, comtrade_fixtures_dir: Path):
        record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_ascii.cfg")

        assert record.sampling_info.is_uniform is True

    def test_synth_binary_record_validates_clean(self, comtrade_fixtures_dir: Path):
        record = ComtradeProvider().load(comtrade_fixtures_dir / "synth_binary.cfg")

        assert record.validate() == []
