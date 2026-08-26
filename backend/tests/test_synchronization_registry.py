"""Tests for app.services.synchronization_registry.SynchronizationRegistry
(Slice 1 of waveform time synchronization)."""

from __future__ import annotations

from app.services.synchronization_registry import SynchronizationRegistry


class TestGetOffset:
    def test_unconfigured_source_defaults_to_zero(self):
        registry = SynchronizationRegistry()
        assert registry.get_offset("ws-1", "src-a") == 0.0

    def test_set_then_get_round_trips(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", -0.0185)
        assert registry.get_offset("ws-1", "src-a") == -0.0185

    def test_offsets_are_scoped_per_workspace(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.5)
        assert registry.get_offset("ws-2", "src-a") == 0.0


class TestResetOffset:
    def test_reset_clears_a_configured_offset(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.5)
        assert registry.reset_offset("ws-1", "src-a") is True
        assert registry.get_offset("ws-1", "src-a") == 0.0

    def test_reset_is_idempotent_for_an_unconfigured_source(self):
        registry = SynchronizationRegistry()
        assert registry.reset_offset("ws-1", "src-a") is False


class TestListForWorkspace:
    def test_lists_only_explicitly_configured_offsets(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.5)
        registry.set_offset("ws-1", "src-b", -0.2)
        registry.set_offset("ws-2", "src-c", 1.0)
        assert registry.list_for_workspace("ws-1") == {"src-a": 0.5, "src-b": -0.2}

    def test_empty_workspace_lists_nothing(self):
        registry = SynchronizationRegistry()
        assert registry.list_for_workspace("ws-1") == {}


class TestRemoveSource:
    def test_removes_only_the_named_source(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.5)
        registry.set_offset("ws-1", "src-b", -0.2)
        assert registry.remove_source("ws-1", "src-a") is True
        assert registry.get_offset("ws-1", "src-a") == 0.0
        assert registry.get_offset("ws-1", "src-b") == -0.2

    def test_idempotent_for_an_unknown_source(self):
        registry = SynchronizationRegistry()
        assert registry.remove_source("ws-1", "src-a") is False


class TestRemoveWorkspace:
    def test_clears_every_offset_owned_by_the_workspace(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.5)
        registry.set_offset("ws-1", "src-b", -0.2)
        registry.set_offset("ws-2", "src-c", 1.0)
        removed = registry.remove_workspace("ws-1")
        assert removed == 2
        assert registry.list_for_workspace("ws-1") == {}
        assert registry.get_offset("ws-2", "src-c") == 1.0  # other workspace untouched

    def test_idempotent_for_an_empty_workspace(self):
        registry = SynchronizationRegistry()
        assert registry.remove_workspace("ws-1") == 0


def test_count_reflects_total_configured_offsets_across_workspaces():
    registry = SynchronizationRegistry()
    registry.set_offset("ws-1", "src-a", 0.5)
    registry.set_offset("ws-2", "src-b", 0.5)
    assert registry.count() == 2
