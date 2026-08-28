"""Tests for the Slice 2 (t0) additions to
app.services.synchronization_service -- validation, and the
independence guarantees between t0 and per-source alignment offsets
(task sections 11/14/15), now Time-Group-scoped (`source_id` resolves
WHICH group's own t0 is being addressed -- see
app.services.synchronization_service's own module docstring).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.errors import InvalidT0Error, SourceNotFoundError
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    clear_t0,
    get_t0,
    remove_source_alignment,
    remove_workspace_synchronization_state,
    reset_all_alignment_offsets,
    set_t0,
)
from app.services.workspace_registry import WorkspaceRegistry

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _active_source(source_id: str, workspace_id: str = "ws-1") -> ActiveSource:
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": [0.0, 0.25, 0.5, 0.75]}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=T0, trigger_time=T0),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=T0,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=T0, trigger_time=T0,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=[], digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


@pytest.fixture
def registry():
    return SynchronizationRegistry()


@pytest.fixture
def source_registry():
    reg = WorkspaceRegistry()
    reg.add(_active_source("src-a", "ws-1"))
    return reg


class TestGetSetT0:
    def test_get_when_unset_is_none(self, registry, source_registry):
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time is None

    def test_set_then_get_round_trips(self, registry, source_registry):
        view = set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.512345, registry=registry, source_registry=source_registry)
        assert view.t0_workspace_time == 0.512345
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time == 0.512345

    def test_set_replaces_an_existing_t0(self, registry, source_registry):
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.5, registry=registry, source_registry=source_registry)
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.7, registry=registry, source_registry=source_registry)
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time == 0.7

    def test_unknown_source_raises_source_not_found(self, registry, source_registry):
        """Time-Group task: t0 is now resolved THROUGH a source_id (to
        know which group is meant) -- an unknown source_id cannot be
        resolved to any group at all, unlike Slice 2's own original
        "no source required" design (which predates Time Groups
        existing in the first place)."""
        with pytest.raises(SourceNotFoundError):
            set_t0(workspace_id="ws-1", source_id="nope", t0_workspace_time=0.0, registry=registry, source_registry=source_registry)
        with pytest.raises(SourceNotFoundError):
            get_t0(workspace_id="ws-1", source_id="nope", registry=registry, source_registry=source_registry)
        with pytest.raises(SourceNotFoundError):
            clear_t0(workspace_id="ws-1", source_id="nope", registry=registry, source_registry=source_registry)

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_t0_raises(self, registry, source_registry, bad_value):
        with pytest.raises(InvalidT0Error):
            set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=bad_value, registry=registry, source_registry=source_registry)

    def test_precision_is_preserved(self, registry, source_registry):
        precise = 0.5123456789
        view = set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=precise, registry=registry, source_registry=source_registry)
        assert view.t0_workspace_time == precise

    def test_view_echoes_back_the_resolved_time_group_id(self, registry, source_registry):
        """A singleton source is its own group's origin -- group_id ==
        source_id, task's own "no separate hardcoded ID scheme" rule."""
        view = set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.5, registry=registry, source_registry=source_registry)
        assert view.time_group_id == "src-a"


class TestClearT0:
    def test_clear_removes_t0(self, registry, source_registry):
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.5, registry=registry, source_registry=source_registry)
        clear_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry)
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time is None

    def test_clear_is_idempotent(self, registry, source_registry):
        clear_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry)  # no error


class TestIndependenceFromSynchronizationOffsets:
    def test_reset_all_alignment_offsets_leaves_t0_unchanged(self, registry, source_registry):
        """Task section 14: "Synchronization reset and t=0 reset are
        independent" -- the CORE regression this slice must never
        break."""
        registry.set_offset("ws-1", "src-a", 0.4)
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.512345, registry=registry, source_registry=source_registry)
        reset_all_alignment_offsets(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.0
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time == 0.512345

    def test_clear_t0_leaves_offsets_unchanged(self, registry, source_registry):
        """Task section 13: "Do not make Clear t=0 equivalent to
        synchronization Reset All"."""
        registry.set_offset("ws-1", "src-a", 0.401)
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.5, registry=registry, source_registry=source_registry)
        clear_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry)
        assert registry.get_offset("ws-1", "src-a") == 0.401

    def test_remove_source_alignment_leaves_t0_unchanged(self, registry, source_registry):
        """Task section 15: removing a source's own manual OFFSET entry
        (not the source itself from source_registry, since t0 now needs
        a resolvable source_id to be READ back) must not clear t0."""
        registry.set_offset("ws-1", "src-a", 0.401)
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.512345, registry=registry, source_registry=source_registry)
        remove_source_alignment(workspace_id="ws-1", source_id="src-a", registry=registry)
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time == 0.512345

    def test_setting_a_new_offset_after_t0_leaves_t0_unchanged(self, registry, source_registry):
        """Task section 12: fine-adjusting a source offset after t0 is
        already defined must not move t0."""
        set_t0(workspace_id="ws-1", source_id="src-a", t0_workspace_time=0.5, registry=registry, source_registry=source_registry)
        registry.set_offset("ws-1", "src-a", 0.401)
        registry.set_offset("ws-1", "src-a", 0.405)  # a later fine-adjustment
        assert get_t0(workspace_id="ws-1", source_id="src-a", registry=registry, source_registry=source_registry).t0_workspace_time == 0.5


class TestFullWorkspaceLifecycleTeardown:
    def test_clears_both_offsets_and_t0(self, registry, source_registry):
        registry.set_offset("ws-1", "src-a", 0.4)
        registry.set_t0("ws-1", "src-a", 0.5)
        remove_workspace_synchronization_state(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.0
        assert registry.get_t0("ws-1", "src-a") is None

    def test_does_not_affect_other_workspaces(self, registry):
        registry.set_offset("ws-1", "src-a", 0.4)
        registry.set_t0("ws-1", "src-a", 0.5)
        registry.set_offset("ws-2", "src-c", 0.2)
        registry.set_t0("ws-2", "src-c", 0.3)
        remove_workspace_synchronization_state(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-2", "src-c") == 0.2
        assert registry.get_t0("ws-2", "src-c") == 0.3
