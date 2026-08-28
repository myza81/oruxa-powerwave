"""Service-layer (ActiveSource/WorkspaceRegistry-aware) tests for Time
Groups -- app.services.synchronization_service.list_time_groups() and
the group-scoping this feature adds to t0/detect-event. See
test_time_grouping_domain.py for the pure derivation-rule coverage this
builds on, and test_synchronization_service.py/
test_synchronization_t0_service.py for the single-group-workspace
regression coverage (Slice 1/2 backward compatibility).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    detect_event_candidate,
    get_t0,
    list_time_groups,
    set_t0,
)
from app.services.workspace_registry import WorkspaceRegistry

F0 = 50.0
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _source(
    source_id: str, *, workspace_id: str = "ws-1", timing_reference: str = "absolute",
    start_time: datetime | None = T0, sample_rate_hz: float = 20.0,
    values: np.ndarray | None = None, elapsed_start: float = 0.0, elapsed_end: float = 1.0,
) -> ActiveSource:
    n = int(round((elapsed_end - elapsed_start) * sample_rate_hz)) + 1
    time = np.linspace(elapsed_start, elapsed_end, n)
    channel_values = values if values is not None else np.zeros(n)
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=F0,
        ),
        waveform_data=pd.DataFrame({"time": time, "VA": channel_values}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[sample_rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=start_time or T0, trigger_time=start_time or T0),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=T0,
        station_name="Station", recorder_name="Recorder", nominal_frequency=F0,
        timing_reference=timing_reference, start_time=start_time, trigger_time=start_time,
        sample_count=n, duration_seconds=elapsed_end - elapsed_start,
        elapsed_start_seconds=elapsed_start, elapsed_end_seconds=elapsed_end,
        sampling_rates=(sample_rate_hz,), samples_per_rate=(n,),
        analog_channels=[AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


@pytest.fixture
def source_registry():
    return WorkspaceRegistry()


@pytest.fixture
def sync_registry():
    return SynchronizationRegistry()


class TestListTimeGroups:
    def test_empty_workspace_has_no_groups(self, source_registry):
        assert list_time_groups(workspace_id="ws-1", source_registry=source_registry) == []

    def test_mixed_workspace_matches_domain_layer_default(self, source_registry):
        """Task section 32/38's own worked example, exercised through
        the full ActiveSource-aware service layer."""
        source_registry.add(_source("A", start_time=T0))
        source_registry.add(_source("B", start_time=T0 + timedelta(milliseconds=500)))
        source_registry.add(_source("C", timing_reference="relative_elapsed", start_time=None))
        source_registry.add(_source("D", timing_reference="relative_elapsed", start_time=None))

        groups = list_time_groups(workspace_id="ws-1", source_registry=source_registry)
        assert len(groups) == 3
        by_id = {g.group_id: g for g in groups}
        assert set(by_id["A"].source_ids) == {"A", "B"}
        assert by_id["C"].source_ids == ["C"]
        assert by_id["D"].source_ids == ["D"]


class TestDifferentSamplingRatesShareAGroup:
    """Task section 16/38: sampling rate must never block grouping."""

    def test_10khz_and_5khz_sources_share_a_group_when_timing_allows(self, source_registry):
        source_registry.add(_source("A", start_time=T0, sample_rate_hz=10_000.0))
        source_registry.add(_source("B", start_time=T0 + timedelta(milliseconds=100), sample_rate_hz=5_000.0))
        groups = list_time_groups(workspace_id="ws-1", source_registry=source_registry)
        assert len(groups) == 1
        assert set(groups[0].source_ids) == {"A", "B"}
        # Native arrays are untouched -- no resampling occurred.
        active_a = source_registry.get("ws-1", "A")
        active_b = source_registry.get("ws-1", "B")
        assert active_a.record.waveform_data["time"].shape[0] == 10_001
        assert active_b.record.waveform_data["time"].shape[0] == 5_001


class TestGroupScopedT0Independence:
    """Task section 24/38: setting t0 in Group 1 must not affect Group
    2, exercised end-to-end through get_t0()/set_t0() (source-resolved),
    not just the raw registry."""

    def test_two_unrelated_groups_in_one_workspace_have_independent_t0(self, source_registry, sync_registry):
        source_registry.add(_source("A", start_time=T0))  # Group "A"
        source_registry.add(_source("C", timing_reference="relative_elapsed", start_time=None))  # Group "C"

        set_t0(workspace_id="ws-1", source_id="A", t0_workspace_time=0.5, registry=sync_registry, source_registry=source_registry)
        set_t0(workspace_id="ws-1", source_id="C", t0_workspace_time=99.0, registry=sync_registry, source_registry=source_registry)

        assert get_t0(workspace_id="ws-1", source_id="A", registry=sync_registry, source_registry=source_registry).t0_workspace_time == 0.5
        assert get_t0(workspace_id="ws-1", source_id="C", registry=sync_registry, source_registry=source_registry).t0_workspace_time == 99.0

    def test_a_second_absolute_source_added_to_group_a_still_resolves_the_same_t0(self, source_registry, sync_registry):
        """Adding a NEW, later-overlapping source to an existing group
        (without changing who its own origin is) must not orphan that
        group's already-set t0."""
        source_registry.add(_source("A", start_time=T0))
        set_t0(workspace_id="ws-1", source_id="A", t0_workspace_time=0.5, registry=sync_registry, source_registry=source_registry)

        source_registry.add(_source("B", start_time=T0 + timedelta(milliseconds=100)))  # joins A's own group; A remains the origin (earliest)
        assert get_t0(workspace_id="ws-1", source_id="B", registry=sync_registry, source_registry=source_registry).t0_workspace_time == 0.5


class TestSourceRemovalRecomputesGroups:
    def test_removing_a_source_shrinks_its_own_group_on_next_call(self, source_registry):
        source_registry.add(_source("A", start_time=T0))
        source_registry.add(_source("B", start_time=T0 + timedelta(milliseconds=100)))
        assert len(list_time_groups(workspace_id="ws-1", source_registry=source_registry)[0].source_ids) == 2

        source_registry.remove("ws-1", "B")
        groups = list_time_groups(workspace_id="ws-1", source_registry=source_registry)
        assert len(groups) == 1
        assert groups[0].source_ids == ["A"]

    def test_removing_the_origin_source_promotes_the_next_earliest(self, source_registry):
        source_registry.add(_source("A", start_time=T0))
        source_registry.add(_source("B", start_time=T0 + timedelta(milliseconds=100)))
        groups = list_time_groups(workspace_id="ws-1", source_registry=source_registry)
        assert groups[0].origin_source_id == "A"

        source_registry.remove("ws-1", "A")
        groups = list_time_groups(workspace_id="ws-1", source_registry=source_registry)
        assert len(groups) == 1
        assert groups[0].origin_source_id == "B"


class TestDetectEventUsesEffectiveOffsetWithinItsOwnGroup:
    """Task section 26: the candidate is composed into workspace time
    using the source's EFFECTIVE offset (timestamp placement + manual),
    and never influenced by an unrelated group's own state."""

    def test_candidate_workspace_time_reflects_timestamp_placement(self, source_registry, sync_registry):
        t = np.arange(0.0, 2.0, 1.0 / 5000.0)
        amplitude = np.full_like(t, 100.0)
        amplitude[t >= 1.0] = 50.0
        values = amplitude * np.sin(2.0 * np.pi * F0 * t)

        origin = _source("A", start_time=T0, sample_rate_hz=5000.0, elapsed_start=0.0, elapsed_end=1.9998)
        origin.record.waveform_data = pd.DataFrame({"time": t, "VA": values})
        member = _source("B", start_time=T0 + timedelta(milliseconds=401), sample_rate_hz=5000.0, elapsed_start=0.0, elapsed_end=1.9998)
        member.record.waveform_data = pd.DataFrame({"time": t, "VA": values})
        source_registry.add(origin)
        source_registry.add(member)

        view = detect_event_candidate(
            workspace_id="ws-1", source_id="B", channel_name="VA", sensitivity="normal",
            search_start_time=None, search_end_time=None,
            source_registry=source_registry, synchronization_registry=sync_registry,
        )
        assert view.found is True
        # B's own timestamp placement is +0.401s relative to A (the
        # group's origin) -- candidate_workspace_time must include it,
        # not just the (zero, unset) manual correction.
        assert view.candidate_workspace_time == pytest.approx(view.candidate_source_time + 0.401, abs=1e-6)
