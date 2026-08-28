"""Tests for app.services.synchronization_service (Slice 1 of waveform
time synchronization, now Time-Group-aware) -- the orchestration layer
above SynchronizationRegistry that resolves each source's own CURRENT
time group and enforces that group's own origin's "manual offset
always 0" invariant. Mirrors test_measurement_group_service.py's own
lightweight ActiveSource fixture.

Sources in this file's own fixtures are given CLOSE/overlapping
`start_time`s (a fraction of a second apart) so they land in the SAME
time group by default -- preserving Slice 1's own original test intent
(two sources, one origin/reference, one freely adjustable) now expressed
through the new timestamp-based grouping rule rather than plain upload
order. See test_time_grouping_service.py for dedicated multi-group
coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.errors import InvalidAlignmentOffsetError, ReferenceSourceAlignmentError, SourceNotFoundError
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    get_source_alignment,
    list_source_alignments,
    remove_source_alignment,
    remove_workspace_synchronization_state,
    reset_all_alignment_offsets,
    reset_source_alignment_offset,
    set_source_alignment_offset,
)
from app.services.workspace_registry import WorkspaceRegistry


def _active_source(source_id: str, workspace_id: str, created_at: datetime, *, start_time: datetime | None = None) -> ActiveSource:
    start_time = start_time if start_time is not None else created_at
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": [0.0, 0.25, 0.5, 0.75]}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=start_time, trigger_time=start_time),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=created_at,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start_time, trigger_time=start_time,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=[], digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _t(offset_seconds: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)


@pytest.fixture
def source_registry():
    return WorkspaceRegistry()


@pytest.fixture
def registry():
    return SynchronizationRegistry()


class TestListSourceAlignments:
    def test_every_source_appears_offset_or_not(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        registry.set_offset("ws-1", "src-b", -0.0185)
        views = {v.source_id: v for v in list_source_alignments(workspace_id="ws-1", registry=registry, source_registry=source_registry)}
        assert views["src-a"].effective_alignment_offset_s == 0.0
        assert views["src-a"].is_reference is True
        assert views["src-b"].manual_alignment_offset_s == -0.0185
        # effective = timestamp placement (+0.1s, src-b starts 0.1s after
        # the group's own origin, src-a) + manual correction (-0.0185s).
        assert views["src-b"].effective_alignment_offset_s == pytest.approx(0.1 - 0.0185)
        assert views["src-b"].is_reference is False
        assert views["src-a"].time_group_id == views["src-b"].time_group_id == "src-a"


class TestGetSourceAlignment:
    def test_unknown_source_raises(self, source_registry, registry):
        with pytest.raises(SourceNotFoundError):
            get_source_alignment(workspace_id="ws-1", source_id="nope", registry=registry, source_registry=source_registry)


class TestSetSourceAlignmentOffset:
    def test_sets_a_non_reference_source(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        view = set_source_alignment_offset(
            workspace_id="ws-1", source_id="src-b", alignment_offset_s=-0.0185, registry=registry, source_registry=source_registry
        )
        assert view.manual_alignment_offset_s == -0.0185
        assert registry.get_offset("ws-1", "src-b") == -0.0185

    def test_unknown_source_raises(self, source_registry, registry):
        with pytest.raises(SourceNotFoundError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="nope", alignment_offset_s=0.1, registry=registry, source_registry=source_registry
            )

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_offset_raises(self, source_registry, registry, bad_value):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        with pytest.raises(InvalidAlignmentOffsetError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="src-b", alignment_offset_s=bad_value, registry=registry, source_registry=source_registry
            )

    def test_non_zero_offset_on_reference_source_raises(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        with pytest.raises(ReferenceSourceAlignmentError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="src-a", alignment_offset_s=0.5, registry=registry, source_registry=source_registry
            )

    def test_zero_offset_on_reference_source_is_a_harmless_no_op(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        view = set_source_alignment_offset(
            workspace_id="ws-1", source_id="src-a", alignment_offset_s=0.0, registry=registry, source_registry=source_registry
        )
        assert view.effective_alignment_offset_s == 0.0
        assert view.is_reference is True

    def test_setting_exactly_zero_clears_the_stored_entry(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        set_source_alignment_offset(workspace_id="ws-1", source_id="src-b", alignment_offset_s=0.02, registry=registry, source_registry=source_registry)
        set_source_alignment_offset(workspace_id="ws-1", source_id="src-b", alignment_offset_s=0.0, registry=registry, source_registry=source_registry)
        assert registry.list_for_workspace("ws-1") == {}


class TestResetSourceAlignmentOffset:
    def test_resets_manual_correction_only_timestamp_placement_remains(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(0.1)))
        registry.set_offset("ws-1", "src-b", 0.5)
        view = reset_source_alignment_offset(workspace_id="ws-1", source_id="src-b", registry=registry, source_registry=source_registry)
        assert view.manual_alignment_offset_s == 0.0
        # Task section 21: "Reset ... returns the source to its
        # recorded-timestamp position" -- NOT to a plain zero shift.
        assert view.timestamp_placement_offset_s == pytest.approx(0.1)
        assert view.effective_alignment_offset_s == pytest.approx(0.1)

    def test_unknown_source_raises(self, source_registry, registry):
        with pytest.raises(SourceNotFoundError):
            reset_source_alignment_offset(workspace_id="ws-1", source_id="nope", registry=registry, source_registry=source_registry)


class TestResetAllAlignmentOffsets:
    def test_clears_every_source_in_workspace(self, registry):
        registry.set_offset("ws-1", "src-a", 0.1)
        registry.set_offset("ws-1", "src-b", -0.2)
        registry.set_offset("ws-2", "src-c", 1.0)
        cleared = reset_all_alignment_offsets(workspace_id="ws-1", registry=registry)
        assert cleared == 2
        assert registry.list_for_workspace("ws-1") == {}
        assert registry.get_offset("ws-2", "src-c") == 1.0


class TestLifecycleHooks:
    def test_remove_source_alignment(self, registry):
        registry.set_offset("ws-1", "src-a", 0.5)
        remove_source_alignment(workspace_id="ws-1", source_id="src-a", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.0

    def test_remove_workspace_synchronization_state(self, registry):
        """Full workspace-lifecycle teardown clears BOTH manual offsets
        and every time group's own t0 -- see
        test_synchronization_t0_service.py for t0-specific coverage of
        this same function."""
        registry.set_offset("ws-1", "src-a", 0.5)
        registry.set_offset("ws-1", "src-b", -0.2)
        registry.set_t0("ws-1", "src-a", 0.512345)
        registry.set_t0("ws-1", "src-c", 1.0)  # a different time group in the SAME workspace
        remove_workspace_synchronization_state(workspace_id="ws-1", registry=registry)
        assert registry.list_for_workspace("ws-1") == {}
        assert registry.get_t0("ws-1", "src-a") is None
        assert registry.get_t0("ws-1", "src-c") is None
