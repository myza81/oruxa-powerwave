"""Unit tests for app.services.waveform_service.extract_waveform_range.

Builds ActiveSource fixtures directly (not via the COMTRADE parser) so
range-extraction/point-budget logic can be tested against precisely known
sample counts and values -- parser-level correctness is covered separately
by tests/test_comtrade_parity.py and tests/test_waveform_api.py (which
exercises the real end-to-end upload -> waveform flow).
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
    REPRESENTATION_MIN_MAX_ENVELOPE,
    extract_waveform_range,
)


def _active_source(n: int = 10_000, rate_hz: float = 10_000.0) -> ActiveSource:
    """A synthetic analog+digital source with `n` samples at `rate_hz`.

    VA is a deterministic ramp (0..n-1) so exact expected values at any
    index/time are trivial to hand-compute in assertions -- the point of
    these tests is range/index correctness, not signal realism.
    """
    time = np.arange(n, dtype=np.float64) / rate_hz
    va = np.arange(n, dtype=np.float64)
    brk = np.zeros(n, dtype=np.int8)
    now = datetime.now(timezone.utc)

    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH",
            recorder_name="TEST",
            source_file="synthetic.cfg",
            provider_type="COMTRADE",
            nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": time, "VA": va, "BRK_A": brk}),
        analog_channels=[],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id="src-1",
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
        sample_count=n,
        duration_seconds=float(time[-1] - time[0]),
        elapsed_start_seconds=float(time[0]),
        elapsed_end_seconds=float(time[-1]),
        sampling_rates=(rate_hz,),
        samples_per_rate=(n,),
        analog_channels=[AnalogChannelSummary(name="VA", index=1, unit="V", engineering_type="Voltage")],
        digital_channels=[DigitalChannelSummary(name="BRK_A", index=1, normal_state=0)],
    )
    return ActiveSource(metadata=metadata, record=record)


class TestFullRecordRequest:
    def test_no_range_supplied_returns_entire_record(self):
        active = _active_source(n=100, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=10_000
        )

        assert result.original_sample_count == 100
        assert result.representation == REPRESENTATION_FULL_RESOLUTION
        assert result.time[0] == pytest.approx(0.0)
        assert result.time[-1] == pytest.approx(0.099)
        assert result.values[0] == 0.0
        assert result.values[-1] == 99.0

    def test_whole_record_first_and_last_sample_are_exact(self):
        active = _active_source(n=5001, rate_hz=5000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=10_000
        )

        assert result.original_sample_count == 5001
        assert result.values[0] == 0.0
        assert result.values[-1] == 5000.0
        assert result.time[0] == 0.0
        assert result.time[-1] == pytest.approx(5000 / 5000.0)


class TestExactRangeExtraction:
    def test_partial_overlap_returns_only_samples_in_range(self):
        active = _active_source(n=1000, rate_hz=1000.0)  # time = index / 1000

        result = extract_waveform_range(
            active, channel_name="VA", start_time=0.100, end_time=0.199, point_budget=10_000
        )

        # index 100..199 inclusive at both boundaries (boundary-inclusive semantics)
        assert result.original_sample_count == 100
        assert result.values[0] == 100.0
        assert result.values[-1] == 199.0

    def test_boundary_inclusive_at_exact_sample_times(self):
        active = _active_source(n=1000, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=0.5, end_time=0.5, point_budget=10_000
        )

        assert result.original_sample_count == 1
        assert result.values[0] == 500.0

    def test_range_entirely_before_record_returns_empty_defined_behavior(self):
        active = _active_source(n=1000, rate_hz=1000.0)  # record spans [0.0, 0.999]

        result = extract_waveform_range(
            active, channel_name="VA", start_time=-5.0, end_time=-1.0, point_budget=10_000
        )

        assert result.original_sample_count == 0
        assert result.representation == REPRESENTATION_FULL_RESOLUTION
        assert list(result.time) == []
        assert list(result.values) == []

    def test_range_entirely_after_record_returns_empty_defined_behavior(self):
        active = _active_source(n=1000, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=100.0, end_time=200.0, point_budget=10_000
        )

        assert result.original_sample_count == 0

    def test_omitting_only_start_time_defaults_to_record_start(self):
        active = _active_source(n=1000, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=0.099, point_budget=10_000
        )

        assert result.start_time == 0.0
        assert result.values[0] == 0.0
        assert result.values[-1] == 99.0

    def test_omitting_only_end_time_defaults_to_record_end(self):
        active = _active_source(n=1000, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=0.900, end_time=None, point_budget=10_000
        )

        assert result.end_time == pytest.approx(0.999)
        assert result.values[-1] == 999.0


class TestInvalidTimeRange:
    def test_start_after_end_raises(self):
        active = _active_source(n=100, rate_hz=1000.0)

        with pytest.raises(InvalidTimeRangeError):
            extract_waveform_range(
                active, channel_name="VA", start_time=0.5, end_time=0.1, point_budget=10_000
            )


class TestChannelIdentity:
    def test_unknown_channel_raises_channel_not_found(self):
        active = _active_source()

        with pytest.raises(ChannelNotFoundError):
            extract_waveform_range(
                active, channel_name="NOPE", start_time=None, end_time=None, point_budget=10_000
            )

    def test_digital_channel_raises_channel_not_analog(self):
        active = _active_source()

        with pytest.raises(ChannelNotAnalogError):
            extract_waveform_range(
                active, channel_name="BRK_A", start_time=None, end_time=None, point_budget=10_000
            )

    def test_unit_matches_the_channels_summary(self):
        active = _active_source()

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=10_000
        )

        assert result.unit == "V"


class TestPointBudgetSemantics:
    def test_budget_greater_than_or_equal_to_sample_count_returns_full_resolution(self):
        active = _active_source(n=500, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=500
        )

        assert result.representation == REPRESENTATION_FULL_RESOLUTION
        assert result.original_sample_count == 500
        assert len(result.time) == 500

    def test_budget_smaller_than_sample_count_returns_display_representation(self):
        active = _active_source(n=5000, rate_hz=1000.0)

        result = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=100
        )

        assert result.representation == REPRESENTATION_MIN_MAX_ENVELOPE
        assert result.original_sample_count == 5000
        assert len(result.time) < 5000


class TestZoomFidelity:
    """docs/project-memory/MIGRATION_PLAN.md's Phase 2 design §12/§17/§19:
    a wide request may be reduced, but a narrower request over the same
    event must reveal progressively finer real data, and a sufficiently
    narrow range must expose true full-resolution samples again.
    """

    def test_wide_request_is_reduced_narrower_request_is_more_detailed(self):
        active = _active_source(n=100_000, rate_hz=100_000.0)  # spans [0.0, ~1.0)
        budget = 500

        wide = extract_waveform_range(
            active, channel_name="VA", start_time=None, end_time=None, point_budget=budget
        )
        narrow = extract_waveform_range(
            active, channel_name="VA", start_time=0.4, end_time=0.5, point_budget=budget
        )

        assert wide.representation == REPRESENTATION_MIN_MAX_ENVELOPE
        assert narrow.representation == REPRESENTATION_MIN_MAX_ENVELOPE
        # Same point budget, but the narrow request's raw samples span a
        # much smaller time window -- its average inter-sample spacing in
        # the *response* must be finer (smaller) than the wide request's.
        wide_avg_spacing = (wide.time[-1] - wide.time[0]) / max(1, len(wide.time) - 1)
        narrow_avg_spacing = (narrow.time[-1] - narrow.time[0]) / max(1, len(narrow.time) - 1)
        assert narrow_avg_spacing < wide_avg_spacing

    def test_narrow_enough_range_returns_true_full_resolution_samples(self):
        active = _active_source(n=100_000, rate_hz=100_000.0)
        budget = 500

        # A 400-sample-wide slice at the same budget used above now fits
        # entirely under the budget -- no reduction should be applied.
        very_narrow = extract_waveform_range(
            active, channel_name="VA", start_time=0.40000, end_time=0.40399, point_budget=budget
        )

        assert very_narrow.representation == REPRESENTATION_FULL_RESOLUTION
        assert very_narrow.original_sample_count == len(very_narrow.time)


class TestNoMutationOfAuthoritativeData:
    def test_waveform_data_dataframe_is_unchanged_after_extraction(self):
        active = _active_source(n=1000, rate_hz=1000.0)
        original_values = active.record.waveform_data["VA"].to_numpy().copy()

        extract_waveform_range(
            active, channel_name="VA", start_time=0.1, end_time=0.5, point_budget=10
        )

        np.testing.assert_array_equal(active.record.waveform_data["VA"].to_numpy(), original_values)
