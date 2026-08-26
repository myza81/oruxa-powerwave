"""Tests for the Slice 2 (t0) additions to
app.services.synchronization_service -- validation, and the
independence guarantees between t0 and per-source alignment offsets
(task sections 11/14/15).
"""

from __future__ import annotations

import pytest

from app.services.errors import InvalidT0Error
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    clear_t0,
    get_t0,
    remove_source_alignment,
    remove_workspace_synchronization_state,
    reset_all_alignment_offsets,
    set_t0,
)


@pytest.fixture
def registry():
    return SynchronizationRegistry()


class TestGetSetT0:
    def test_get_when_unset_is_none(self, registry):
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time is None

    def test_set_then_get_round_trips(self, registry):
        view = set_t0(workspace_id="ws-1", t0_workspace_time=0.512345, registry=registry)
        assert view.t0_workspace_time == 0.512345
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time == 0.512345

    def test_set_replaces_an_existing_t0(self, registry):
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.7, registry=registry)
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time == 0.7

    def test_set_does_not_require_any_source_to_exist(self, registry):
        """t0 is a pure workspace-time coordinate -- set_t0() takes no
        source_registry/source_id at all."""
        view = set_t0(workspace_id="ws-1", t0_workspace_time=0.0, registry=registry)
        assert view.t0_workspace_time == 0.0

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_t0_raises(self, registry, bad_value):
        with pytest.raises(InvalidT0Error):
            set_t0(workspace_id="ws-1", t0_workspace_time=bad_value, registry=registry)

    def test_precision_is_preserved(self, registry):
        precise = 0.5123456789
        view = set_t0(workspace_id="ws-1", t0_workspace_time=precise, registry=registry)
        assert view.t0_workspace_time == precise


class TestClearT0:
    def test_clear_removes_t0(self, registry):
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        clear_t0(workspace_id="ws-1", registry=registry)
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time is None

    def test_clear_is_idempotent(self, registry):
        clear_t0(workspace_id="ws-1", registry=registry)  # no error


class TestIndependenceFromSynchronizationOffsets:
    def test_reset_all_alignment_offsets_leaves_t0_unchanged(self, registry):
        """Task section 14: "Synchronization reset and t=0 reset are
        independent" -- the CORE regression this slice must never
        break."""
        registry.set_offset("ws-1", "src-a", 0.4)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.512345, registry=registry)
        reset_all_alignment_offsets(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.0
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time == 0.512345

    def test_clear_t0_leaves_offsets_unchanged(self, registry):
        """Task section 13: "Do not make Clear t=0 equivalent to
        synchronization Reset All"."""
        registry.set_offset("ws-1", "src-a", 0.401)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        clear_t0(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.401

    def test_remove_source_alignment_leaves_t0_unchanged(self, registry):
        """Task section 15: removing a source (even the one whose cursor
        originally helped select t=0) must not clear t0."""
        registry.set_offset("ws-1", "src-b", 0.401)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.512345, registry=registry)
        remove_source_alignment(workspace_id="ws-1", source_id="src-b", registry=registry)
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time == 0.512345

    def test_setting_a_new_offset_after_t0_leaves_t0_unchanged(self, registry):
        """Task section 12: fine-adjusting a source offset after t0 is
        already defined must not move t0."""
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        registry.set_offset("ws-1", "src-b", 0.401)
        registry.set_offset("ws-1", "src-b", 0.405)  # a later fine-adjustment
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time == 0.5


class TestFullWorkspaceLifecycleTeardown:
    def test_clears_both_offsets_and_t0(self, registry):
        registry.set_offset("ws-1", "src-a", 0.4)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        remove_workspace_synchronization_state(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-1", "src-a") == 0.0
        assert get_t0(workspace_id="ws-1", registry=registry).t0_workspace_time is None

    def test_does_not_affect_other_workspaces(self, registry):
        registry.set_offset("ws-1", "src-a", 0.4)
        set_t0(workspace_id="ws-1", t0_workspace_time=0.5, registry=registry)
        registry.set_offset("ws-2", "src-c", 0.2)
        set_t0(workspace_id="ws-2", t0_workspace_time=0.3, registry=registry)
        remove_workspace_synchronization_state(workspace_id="ws-1", registry=registry)
        assert registry.get_offset("ws-2", "src-c") == 0.2
        assert get_t0(workspace_id="ws-2", registry=registry).t0_workspace_time == 0.3
