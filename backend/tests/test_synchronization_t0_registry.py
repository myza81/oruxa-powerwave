"""Tests for the Slice 2 (t0) additions to
app.services.synchronization_registry.SynchronizationRegistry -- the
independence guarantees between the pre-existing per-source offset store
and the t0 store (now Time-Group-scoped, keyed by `(workspace_id,
time_group_key)` -- see "Timestamp-Based Initial Alignment and Time
Groups" in docs/project-memory/DECISIONS.md) are the load-bearing
behaviour here.
"""

from __future__ import annotations

from app.services.synchronization_registry import SynchronizationRegistry

GROUP_A = "grp-a"
GROUP_B = "grp-b"


class TestGetT0:
    def test_no_t0_selected_returns_none(self):
        registry = SynchronizationRegistry()
        assert registry.get_t0("ws-1", GROUP_A) is None

    def test_set_then_get_round_trips(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.512345)
        assert registry.get_t0("ws-1", GROUP_A) == 0.512345

    def test_t0_is_scoped_per_workspace(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        assert registry.get_t0("ws-2", GROUP_A) is None

    def test_a_t0_of_exactly_zero_is_distinguishable_from_unset(self):
        """A workspace-time instant of 0.0 is a legitimate, deliberately
        chosen event origin -- get_t0() must return 0.0 (not None) once
        explicitly set to it."""
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.0)
        assert registry.get_t0("ws-1", GROUP_A) == 0.0
        assert registry.get_t0("ws-1", GROUP_A) is not None


class TestClearT0:
    def test_clear_removes_a_set_t0(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        assert registry.clear_t0("ws-1", GROUP_A) is True
        assert registry.get_t0("ws-1", GROUP_A) is None

    def test_clear_is_idempotent_when_unset(self):
        registry = SynchronizationRegistry()
        assert registry.clear_t0("ws-1", GROUP_A) is False


class TestT0IsScopedPerTimeGroup:
    """Task section 24/38's own core requirement: "setting t0 in Group 1
    does not affect Group 2" -- the central new guarantee this slice
    adds on top of Slice 2's existing per-workspace independence."""

    def test_setting_t0_in_one_group_does_not_affect_another(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.set_t0("ws-1", GROUP_B, 1.5)
        assert registry.get_t0("ws-1", GROUP_A) == 0.5
        assert registry.get_t0("ws-1", GROUP_B) == 1.5

    def test_clearing_t0_in_one_group_does_not_affect_another(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.set_t0("ws-1", GROUP_B, 1.5)
        registry.clear_t0("ws-1", GROUP_A)
        assert registry.get_t0("ws-1", GROUP_A) is None
        assert registry.get_t0("ws-1", GROUP_B) == 1.5

    def test_clear_all_t0_for_workspace_clears_every_group(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.set_t0("ws-1", GROUP_B, 1.5)
        registry.set_t0("ws-2", GROUP_A, 9.0)  # a different workspace -- must survive
        cleared = registry.clear_all_t0_for_workspace("ws-1")
        assert cleared == 2
        assert registry.get_t0("ws-1", GROUP_A) is None
        assert registry.get_t0("ws-1", GROUP_B) is None
        assert registry.get_t0("ws-2", GROUP_A) == 9.0

    def test_clear_all_t0_for_workspace_is_idempotent(self):
        registry = SynchronizationRegistry()
        assert registry.clear_all_t0_for_workspace("ws-empty") == 0


class TestIndependenceFromOffsets:
    """Task section 11/14: t0 and per-source alignment offsets are
    separate concepts -- neither store's mutating methods may leak into
    the other."""

    def test_set_offset_never_touches_t0(self):
        registry = SynchronizationRegistry()
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.set_offset("ws-1", "src-a", 0.2)
        assert registry.get_t0("ws-1", GROUP_A) == 0.5

    def test_reset_offset_never_touches_t0(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.reset_offset("ws-1", "src-a")
        assert registry.get_t0("ws-1", GROUP_A) == 0.5

    def test_remove_source_never_touches_t0(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.remove_source("ws-1", "src-a")
        assert registry.get_t0("ws-1", GROUP_A) == 0.5

    def test_remove_workspace_offsets_only_never_touches_t0(self):
        """remove_workspace() -- used by "Reset All" -- must leave t0
        completely untouched (task section 14: independent operations)."""
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_offset("ws-1", "src-b", -0.1)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        removed = registry.remove_workspace("ws-1")
        assert removed == 2
        assert registry.list_for_workspace("ws-1") == {}
        assert registry.get_t0("ws-1", GROUP_A) == 0.5

    def test_set_t0_never_touches_offsets(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        assert registry.get_offset("ws-1", "src-a") == 0.2

    def test_clear_t0_never_touches_offsets(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        registry.clear_t0("ws-1", GROUP_A)
        assert registry.get_offset("ws-1", "src-a") == 0.2

    def test_count_excludes_t0(self):
        registry = SynchronizationRegistry()
        registry.set_offset("ws-1", "src-a", 0.2)
        registry.set_t0("ws-1", GROUP_A, 0.5)
        assert registry.count() == 1


def test_precision_is_preserved_to_sub_millisecond_scale():
    registry = SynchronizationRegistry()
    precise = 0.5123456789
    registry.set_t0("ws-1", GROUP_A, precise)
    assert registry.get_t0("ws-1", GROUP_A) == precise
