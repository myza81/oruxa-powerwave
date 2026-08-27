"""Unit tests for app.services.synchronization_service.detect_event_candidate
(Slice 3 -- assisted event-origin detection). Builds ActiveSource
fixtures directly, same established pattern as
tests/test_peak_value_service.py/test_annotation_anchor_service.py.
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
from app.services.errors import (
    ChannelNotAnalogError,
    ChannelNotFoundError,
    InvalidDetectionSensitivityError,
    SourceNotFoundError,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import detect_event_candidate
from app.services.workspace_registry import WorkspaceRegistry

F0 = 50.0


def _active_source(
    *,
    source_id: str = "src-1",
    time: np.ndarray,
    channels: dict[str, np.ndarray],
    digital: dict[str, np.ndarray] | None = None,
    nominal_frequency: float = F0,
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
            nominal_frequency=nominal_frequency,
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
        nominal_frequency=nominal_frequency,
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
            AnalogChannelSummary(name=name, index=i, unit="kV", engineering_type="Voltage")
            for i, name in enumerate(channels)
        ],
        digital_channels=[
            DigitalChannelSummary(name=name, index=i, normal_state=0) for i, name in enumerate(digital)
        ],
    )
    return ActiveSource(metadata=metadata, record=record)


def _dip_waveform(*, duration_s: float = 2.0, fs: float = 5000.0, event_time_s: float = 1.0):
    t = np.arange(0.0, duration_s, 1.0 / fs)
    amplitude = np.full_like(t, 100.0)
    amplitude[t >= event_time_s] = 50.0
    return t, amplitude * np.sin(2.0 * np.pi * F0 * t)


@pytest.fixture
def source_registry():
    registry = WorkspaceRegistry()
    time, values = _dip_waveform()
    registry.add(_active_source(time=time, channels={"VA": values}, digital={"52A": np.zeros_like(time, dtype=int)}))
    return registry


@pytest.fixture
def sync_registry():
    return SynchronizationRegistry()


class TestFindsCandidate:
    def test_finds_a_strong_disturbance(self, source_registry, sync_registry):
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        assert view.quality == "strong"
        assert view.channel_unit == "kV"
        assert view.nominal_frequency_hz == F0
        assert view.detector_method == "rms_sustained_change"


class TestAlignmentOffsetComposition:
    """Task section 17: `candidate_workspace_time = candidate_source_time
    + alignment_offset_s` -- exact composition, verified numerically."""

    def test_zero_offset_leaves_workspace_time_equal_to_source_time(self, source_registry, sync_registry):
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.candidate_workspace_time == pytest.approx(view.candidate_source_time)

    def test_nonzero_offset_shifts_workspace_time_by_exactly_the_offset(self, source_registry, sync_registry):
        sync_registry.set_offset("ws-1", "src-1", 0.401)
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        assert view.candidate_workspace_time == pytest.approx(view.candidate_source_time + 0.401)

    def test_worked_example_style_composition(self, sync_registry):
        """Task section 17's own worked example
        (candidate_source_time=0.112, offset=+0.401 ->
        candidate_workspace_time=0.513) uses an event time that would
        fall INSIDE this detector's own pre-event baseline window (task
        section 6: baseline must be established BEFORE measuring
        deviation) -- this test instead places the disturbance safely
        after the baseline window and verifies the exact same additive
        composition the worked example illustrates:
        candidate_workspace_time == candidate_source_time + offset."""
        registry = WorkspaceRegistry()
        t, values = _dip_waveform(event_time_s=1.0)
        registry.add(_active_source(time=t, channels={"VA": values}))
        sync_registry.set_offset("ws-1", "src-1", 0.401)

        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        assert view.candidate_source_time == pytest.approx(1.0, abs=0.02)
        assert view.candidate_workspace_time == pytest.approx(view.candidate_source_time + 0.401)


class TestNotFound:
    def test_missing_source_raises(self, source_registry, sync_registry):
        with pytest.raises(SourceNotFoundError):
            detect_event_candidate(
                workspace_id="ws-1", source_id="no-such-source", channel_name="VA", sensitivity="normal",
                search_start_time=None, search_end_time=None,
                source_registry=source_registry, synchronization_registry=sync_registry,
            )

    def test_missing_channel_raises(self, source_registry, sync_registry):
        with pytest.raises(ChannelNotFoundError):
            detect_event_candidate(
                workspace_id="ws-1", source_id="src-1", channel_name="NOPE", sensitivity="normal",
                search_start_time=None, search_end_time=None,
                source_registry=source_registry, synchronization_registry=sync_registry,
            )

    def test_digital_channel_raises_channel_not_analog(self, source_registry, sync_registry):
        with pytest.raises(ChannelNotAnalogError):
            detect_event_candidate(
                workspace_id="ws-1", source_id="src-1", channel_name="52A", sensitivity="normal",
                search_start_time=None, search_end_time=None,
                source_registry=source_registry, synchronization_registry=sync_registry,
            )

    def test_invalid_sensitivity_raises(self, source_registry, sync_registry):
        with pytest.raises(InvalidDetectionSensitivityError):
            detect_event_candidate(
                workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="extreme",
                search_start_time=None, search_end_time=None,
                source_registry=source_registry, synchronization_registry=sync_registry,
            )


class TestSteadyChannelReturnsNoCandidate:
    def test_no_disturbance_returns_found_false_not_an_error(self, sync_registry):
        registry = WorkspaceRegistry()
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        values = 100.0 * np.sin(2.0 * np.pi * F0 * t)
        registry.add(_active_source(time=t, channels={"VA": values}))

        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=registry, synchronization_registry=sync_registry,
        )
        assert view.found is False
        assert view.candidate_source_time is None
        assert view.candidate_workspace_time is None
        assert view.reason == "No clear disturbance onset detected."


class TestSearchRangeNarrowing:
    """Task section 24's optional narrowing -- restricting the analysed
    slice to before the real disturbance must make it undetectable."""

    def test_narrowing_before_the_disturbance_finds_nothing(self, source_registry, sync_registry):
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=0.0, search_end_time=0.5,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is False

    def test_omitting_range_analyses_whole_record_and_finds_it(self, source_registry, sync_registry):
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True


def _two_event_waveform(*, duration_s: float = 3.0, fs: float = 5000.0, event_a_time_s: float = 1.0, event_b_time_s: float = 2.0):
    """Task section 21's own worked scenario: two genuine, independent
    disturbances in one record -- Event A (a moderate dip, recovering
    afterward) well after the full-record baseline window, then a calm
    stretch, then Event B (a deeper dip that persists to the end). Both
    are individually well clear of any sensitivity tier's trigger band
    when isolated."""
    t = np.arange(0.0, duration_s, 1.0 / fs)
    amplitude = np.full_like(t, 100.0)
    amplitude[(t >= event_a_time_s) & (t < event_a_time_s + 0.5)] = 50.0  # Event A, recovers after 0.5s
    amplitude[t >= event_b_time_s] = 30.0  # Event B, persists
    return t, amplitude * np.sin(2.0 * np.pi * F0 * t)


class TestMultiEventSearchRangeUAT:
    """The owner's own real UAT finding (task section 21): a full-record
    search finds the FIRST qualifying disturbance (Event A), which may
    not be the one the engineer is actually analysing. Restricting the
    search to a viewport around the LATER event (Event B) must find
    that one instead, with Event A entirely excluded from consideration
    -- never a blended/backtracked result."""

    @pytest.fixture
    def two_event_registry(self):
        registry = WorkspaceRegistry()
        t, values = _two_event_waveform()
        registry.add(_active_source(time=t, channels={"VA": values}))
        return registry

    def test_full_recording_selects_the_first_event(self, two_event_registry, sync_registry):
        """Task section G: "Full recording mode selects the first
        qualifying Event A, preserving current semantics.\""""
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=two_event_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        assert abs(view.candidate_source_time - 1.0) < 0.05  # Event A, not Event B

    def test_visible_range_around_event_b_excludes_event_a(self, two_event_registry, sync_registry):
        """Task section G: "Current visible range around Event B
        excludes Event A and detects Event B\" -- the core owner UAT
        acceptance path."""
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=1.7, search_end_time=2.5,
            source_registry=two_event_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        assert abs(view.candidate_source_time - 2.0) < 0.05  # Event B, not Event A

    def test_visible_range_with_no_disturbance_returns_no_event_even_though_one_exists_outside_it(
        self, two_event_registry, sync_registry
    ):
        """Task section I: a quiet sub-range must return "no clear
        event" even though the record genuinely contains a disturbance
        elsewhere -- the detector must never search outside the
        selected range to manufacture a result."""
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=1.6, search_end_time=1.95,  # calm stretch between A and B
            source_registry=two_event_registry, synchronization_registry=sync_registry,
        )
        assert view.found is False
        assert view.reason == "No clear disturbance onset detected."


class TestSourceBoundClipping:
    """Task section D/8: a search range extending beyond the selected
    source's own native coverage must clip safely to the real overlap,
    never request/produce an invalid slice."""

    def test_range_extending_past_source_bounds_clips_safely(self, source_registry, sync_registry):
        """source_registry's own fixture covers [0, 2) s -- request a
        range that starts before it and ends after it."""
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=-5.0, search_end_time=50.0,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True  # equivalent to the full-record result -- clipped to the real overlap, not rejected


class TestTooShortVisibleRange:
    """Task section E: a too-short range must return a clear result,
    never silently fall back to full-record search (that fallback is
    handled entirely at the frontend: this endpoint is never CALLED a
    second time automatically -- see wwHandleDetectEventAnalyseClick()'s
    own single-request contract)."""

    def test_a_few_samples_returns_too_short_not_a_crash(self, source_registry, sync_registry):
        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=1.000, search_end_time=1.001,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is False
        assert "too short" in view.reason.lower()


class TestInsufficientBaselineInVisibleRange:
    """Task section F: zooming so tightly that the visible range leaves
    too little genuine pre-event history to build a trustworthy
    baseline (distinct from TestTooShortVisibleRange's own "not even
    one RMS window" case: this range IS long enough to compute SOME RMS
    values, just not enough of them to satisfy the minimum-cycles
    baseline requirement) -- must not fabricate a baseline."""

    def test_a_sliver_longer_than_one_rms_window_has_no_baseline(self, sync_registry):
        registry = WorkspaceRegistry()
        t, values = _dip_waveform(event_time_s=1.0)
        registry.add(_active_source(time=t, channels={"VA": values}))

        view = detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=1.0, search_end_time=1.021,  # ~1 ms past the 1-cycle RMS warm-up -- too few valid RMS samples for a baseline
            source_registry=registry, synchronization_registry=sync_registry,
        )
        assert view.found is False
        assert "baseline" in view.reason.lower()


class TestDoesNotMutateState:
    """Task section 15/17: detection must never touch t0 or the
    source's own alignment offset -- it only ever READS the offset to
    compose the response."""

    def test_running_detection_never_sets_t0(self, source_registry, sync_registry):
        detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert sync_registry.get_t0("ws-1") is None

    def test_running_detection_never_changes_the_offset(self, source_registry, sync_registry):
        sync_registry.set_offset("ws-1", "src-1", 0.25)
        detect_event_candidate(
            workspace_id="ws-1", source_id="src-1", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert sync_registry.get_offset("ws-1", "src-1") == 0.25
