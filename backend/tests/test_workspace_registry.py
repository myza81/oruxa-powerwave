"""Unit tests for the in-memory, ephemeral workspace/source registry."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.workspace_registry import WorkspaceRegistry


def _metadata(workspace_id: str, source_id: str) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        workspace_id=workspace_id,
        provider_type="COMTRADE",
        original_filenames=("a.cfg", "a.dat"),
        created_at=datetime.now(timezone.utc),
        station_name="STATION",
        recorder_name="DEV",
        nominal_frequency=50.0,
        timing_reference="absolute",
        start_time=None,
        trigger_time=None,
        sample_count=10,
        duration_seconds=1.0,
        sampling_rates=(1000.0,),
        samples_per_rate=(10,),
    )


def _record() -> DisturbanceRecord:
    """A minimal but structurally valid DisturbanceRecord for registry tests.

    These tests only exercise WorkspaceRegistry's own keying/ownership/
    cleanup logic -- the record's actual contents are irrelevant to that,
    so this is deliberately the smallest valid record, not a realistic one
    (see tests/test_waveform_service.py / test_waveform_api.py for tests
    that exercise real waveform data).
    """
    now = datetime.now(timezone.utc)
    return DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="STATION",
            recorder_name="DEV",
            source_file="a.cfg",
            provider_type="COMTRADE",
            nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": np.array([0.0, 0.001]), "VA": np.array([1.0, 2.0])}),
        analog_channels=[],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1000.0], samples_per_rate=[2]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )


def _source(workspace_id: str, source_id: str) -> ActiveSource:
    return ActiveSource(metadata=_metadata(workspace_id, source_id), record=_record())


def test_add_and_get_round_trip():
    registry = WorkspaceRegistry()
    source = _source("ws-1", "src-1")

    registry.add(source)

    assert registry.get("ws-1", "src-1") is source


def test_get_unknown_returns_none():
    registry = WorkspaceRegistry()

    assert registry.get("ws-1", "does-not-exist") is None


def test_workspaces_are_isolated_from_each_other():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-1", "src-1"))
    registry.add(_source("ws-2", "src-1"))  # same source_id, different workspace

    # Same source_id but different workspace_id must not collide.
    assert registry.get("ws-1", "src-1").metadata.workspace_id == "ws-1"
    assert registry.get("ws-2", "src-1").metadata.workspace_id == "ws-2"
    assert registry.get("ws-1", "src-1") is not registry.get("ws-2", "src-1")


def test_list_for_workspace_only_returns_that_workspaces_sources():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-1", "src-1"))
    registry.add(_source("ws-1", "src-2"))
    registry.add(_source("ws-2", "src-3"))

    listed = registry.list_for_workspace("ws-1")

    assert {s.metadata.source_id for s in listed} == {"src-1", "src-2"}


def test_list_for_unknown_workspace_returns_empty():
    registry = WorkspaceRegistry()

    assert registry.list_for_workspace("nonexistent") == []


def test_remove_releases_ownership_and_prevents_later_access():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-1", "src-1"))

    removed = registry.remove("ws-1", "src-1")

    assert removed is True
    assert registry.get("ws-1", "src-1") is None
    assert registry.list_for_workspace("ws-1") == []


def test_remove_unknown_returns_false():
    registry = WorkspaceRegistry()

    assert registry.remove("ws-1", "does-not-exist") is False


def test_count_reflects_current_entries():
    registry = WorkspaceRegistry()
    assert registry.count() == 0

    registry.add(_source("ws-1", "src-1"))
    registry.add(_source("ws-1", "src-2"))
    assert registry.count() == 2

    registry.remove("ws-1", "src-1")
    assert registry.count() == 1


def test_remove_workspace_releases_every_source_it_owns():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-1", "src-1"))
    registry.add(_source("ws-1", "src-2"))
    registry.add(_source("ws-1", "src-3"))

    removed_count = registry.remove_workspace("ws-1")

    assert removed_count == 3
    assert registry.list_for_workspace("ws-1") == []
    assert registry.get("ws-1", "src-1") is None
    assert registry.get("ws-1", "src-2") is None
    assert registry.get("ws-1", "src-3") is None
    assert registry.count() == 0


def test_remove_workspace_leaves_other_workspaces_untouched():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-1", "src-1"))
    registry.add(_source("ws-2", "src-1"))
    registry.add(_source("ws-2", "src-2"))

    registry.remove_workspace("ws-1")

    assert registry.list_for_workspace("ws-1") == []
    assert {s.metadata.source_id for s in registry.list_for_workspace("ws-2")} == {"src-1", "src-2"}
    assert registry.count() == 2


def test_remove_workspace_unknown_is_a_safe_no_op():
    registry = WorkspaceRegistry()
    registry.add(_source("ws-2", "src-1"))

    removed_count = registry.remove_workspace("does-not-exist")

    assert removed_count == 0
    assert registry.count() == 1


def test_remove_workspace_already_empty_is_a_safe_no_op():
    registry = WorkspaceRegistry()

    assert registry.remove_workspace("ws-1") == 0
