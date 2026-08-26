"""Tests for app.services.synchronization_service (Slice 1 of waveform
time synchronization) -- the orchestration layer above
SynchronizationRegistry that resolves the current reference source and
enforces its own "offset always 0" invariant. Mirrors
test_measurement_group_service.py's own lightweight ActiveSource fixture.
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
    remove_workspace_alignment,
    reset_all_alignment_offsets,
    reset_source_alignment_offset,
    resolve_reference_source_id,
    set_source_alignment_offset,
)
from app.services.workspace_registry import WorkspaceRegistry


def _active_source(source_id: str, workspace_id: str, created_at: datetime) -> ActiveSource:
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": [0.0, 0.25, 0.5, 0.75]}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=created_at, trigger_time=created_at),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=created_at,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=created_at, trigger_time=created_at,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=[], digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _t(offset_minutes: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


@pytest.fixture
def source_registry():
    return WorkspaceRegistry()


@pytest.fixture
def registry():
    return SynchronizationRegistry()


class TestResolveReferenceSourceId:
    def test_no_sources_has_no_reference(self, source_registry):
        assert resolve_reference_source_id(workspace_id="ws-1", source_registry=source_registry) is None

    def test_first_uploaded_source_is_the_reference(self, source_registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        assert resolve_reference_source_id(workspace_id="ws-1", source_registry=source_registry) == "src-a"


class TestListSourceAlignments:
    def test_every_source_appears_offset_or_not(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        registry.set_offset("ws-1", "src-b", -0.0185)
        views = {v.source_id: v for v in list_source_alignments(workspace_id="ws-1", registry=registry, source_registry=source_registry)}
        assert views["src-a"].alignment_offset_s == 0.0
        assert views["src-a"].is_reference is True
        assert views["src-b"].alignment_offset_s == -0.0185
        assert views["src-b"].is_reference is False


class TestGetSourceAlignment:
    def test_unknown_source_raises(self, source_registry, registry):
        with pytest.raises(SourceNotFoundError):
            get_source_alignment(workspace_id="ws-1", source_id="nope", registry=registry, source_registry=source_registry)


class TestSetSourceAlignmentOffset:
    def test_sets_a_non_reference_source(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        view = set_source_alignment_offset(
            workspace_id="ws-1", source_id="src-b", alignment_offset_s=-0.0185, registry=registry, source_registry=source_registry
        )
        assert view.alignment_offset_s == -0.0185
        assert registry.get_offset("ws-1", "src-b") == -0.0185

    def test_unknown_source_raises(self, source_registry, registry):
        with pytest.raises(SourceNotFoundError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="nope", alignment_offset_s=0.1, registry=registry, source_registry=source_registry
            )

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_offset_raises(self, source_registry, registry, bad_value):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        with pytest.raises(InvalidAlignmentOffsetError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="src-b", alignment_offset_s=bad_value, registry=registry, source_registry=source_registry
            )

    def test_non_zero_offset_on_reference_source_raises(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        with pytest.raises(ReferenceSourceAlignmentError):
            set_source_alignment_offset(
                workspace_id="ws-1", source_id="src-a", alignment_offset_s=0.5, registry=registry, source_registry=source_registry
            )

    def test_zero_offset_on_reference_source_is_a_harmless_no_op(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        view = set_source_alignment_offset(
            workspace_id="ws-1", source_id="src-a", alignment_offset_s=0.0, registry=registry, source_registry=source_registry
        )
        assert view.alignment_offset_s == 0.0
        assert view.is_reference is True

    def test_setting_exactly_zero_clears_the_stored_entry(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        set_source_alignment_offset(workspace_id="ws-1", source_id="src-b", alignment_offset_s=0.02, registry=registry, source_registry=source_registry)
        set_source_alignment_offset(workspace_id="ws-1", source_id="src-b", alignment_offset_s=0.0, registry=registry, source_registry=source_registry)
        assert registry.list_for_workspace("ws-1") == {}


class TestResetSourceAlignmentOffset:
    def test_resets_to_zero(self, source_registry, registry):
        source_registry.add(_active_source("src-a", "ws-1", _t(0)))
        source_registry.add(_active_source("src-b", "ws-1", _t(5)))
        registry.set_offset("ws-1", "src-b", 0.5)
        view = reset_source_alignment_offset(workspace_id="ws-1", source_id="src-b", registry=registry, source_registry=source_registry)
        assert view.alignment_offset_s == 0.0

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

    def test_remove_workspace_alignment(self, registry):
        registry.set_offset("ws-1", "src-a", 0.5)
        registry.set_offset("ws-1", "src-b", -0.2)
        remove_workspace_alignment(workspace_id="ws-1", registry=registry)
        assert registry.list_for_workspace("ws-1") == {}
