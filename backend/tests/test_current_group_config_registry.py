"""Tests for app.services.current_group_config_registry (Slice 4 of
DEC-050): storage CRUD and workspace isolation -- registry-level only,
no MeasurementGroupRegistry/kind-validation involved (see
test_current_group_config_service.py for that layer).
"""

from __future__ import annotations

from app.domain.current_group_config import METHOD_MANUAL, CurrentBaseConfiguration
from app.services.current_group_config_registry import CurrentGroupConfigRegistry


def _config(measurement_group_id="mg-1", workspace_id="ws-1", manual_ibase_ka=2.0) -> CurrentBaseConfiguration:
    return CurrentBaseConfiguration(
        measurement_group_id=measurement_group_id, workspace_id=workspace_id, method=METHOD_MANUAL,
        manual_ibase_ka=manual_ibase_ka,
    )


class TestBasicCrud:
    def test_upsert_and_get(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a"))
        assert registry.get("ws-1", "mg-a") is not None
        assert registry.get("ws-1", "unknown") is None

    def test_upsert_replaces_entirely(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a", manual_ibase_ka=2.0))
        registry.upsert(_config("mg-a", manual_ibase_ka=4.0))
        assert registry.get("ws-1", "mg-a").manual_ibase_ka == 4.0

    def test_list_for_workspace_is_scoped(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a", workspace_id="ws-1"))
        registry.upsert(_config("mg-b", workspace_id="ws-2"))
        assert [c.measurement_group_id for c in registry.list_for_workspace("ws-1")] == ["mg-a"]

    def test_delete_is_idempotent(self):
        registry = CurrentGroupConfigRegistry()
        assert registry.delete("ws-1", "does-not-exist") is False
        registry.upsert(_config("mg-a"))
        assert registry.delete("ws-1", "mg-a") is True
        assert registry.get("ws-1", "mg-a") is None
        assert registry.delete("ws-1", "mg-a") is False

    def test_count(self):
        registry = CurrentGroupConfigRegistry()
        assert registry.count() == 0
        registry.upsert(_config("mg-a"))
        registry.upsert(_config("mg-b", workspace_id="ws-2"))
        assert registry.count() == 2


class TestWorkspaceIsolation:
    def test_same_group_id_in_two_workspaces_stays_independent(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-1", workspace_id="ws-a", manual_ibase_ka=2.0))
        registry.upsert(_config("mg-1", workspace_id="ws-b", manual_ibase_ka=4.0))
        assert registry.get("ws-a", "mg-1").manual_ibase_ka == 2.0
        assert registry.get("ws-b", "mg-1").manual_ibase_ka == 4.0

    def test_remove_workspace_clears_only_that_workspace(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-1", workspace_id="ws-1"))
        registry.upsert(_config("mg-2", workspace_id="ws-1"))
        registry.upsert(_config("mg-3", workspace_id="ws-2"))
        removed = registry.remove_workspace("ws-1")
        assert removed == 2
        assert registry.list_for_workspace("ws-1") == []
        assert [c.measurement_group_id for c in registry.list_for_workspace("ws-2")] == ["mg-3"]

    def test_remove_workspace_is_idempotent(self):
        registry = CurrentGroupConfigRegistry()
        assert registry.remove_workspace("ws-empty") == 0


class TestCopyOnBoundary:
    """Slice 4 robustness follow-up (post-Codex-review): the registry
    must own its stored state -- mutating an object on either side of
    `upsert()`/`get()`/`list_for_workspace()` must never reach back into
    registry-owned state, the same guarantee `MeasurementGroupRegistry`
    already provides for `MeasurementGroup`."""

    def test_mutating_the_object_passed_to_upsert_does_not_affect_the_registry(self):
        registry = CurrentGroupConfigRegistry()
        config = _config("mg-a", manual_ibase_ka=2.0)
        registry.upsert(config)
        config.manual_ibase_ka = 999.0
        assert registry.get("ws-1", "mg-a").manual_ibase_ka == 2.0

    def test_mutating_a_get_result_does_not_affect_the_registry(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a", manual_ibase_ka=2.0))
        fetched = registry.get("ws-1", "mg-a")
        fetched.manual_ibase_ka = 999.0
        assert registry.get("ws-1", "mg-a").manual_ibase_ka == 2.0

    def test_mutating_a_list_for_workspace_result_does_not_affect_the_registry(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a", manual_ibase_ka=2.0))
        [listed] = registry.list_for_workspace("ws-1")
        listed.manual_ibase_ka = 999.0
        assert registry.get("ws-1", "mg-a").manual_ibase_ka == 2.0

    def test_successive_get_calls_return_independent_objects(self):
        registry = CurrentGroupConfigRegistry()
        registry.upsert(_config("mg-a", manual_ibase_ka=2.0))
        first = registry.get("ws-1", "mg-a")
        second = registry.get("ws-1", "mg-a")
        assert first is not second
        first.manual_ibase_ka = 999.0
        assert second.manual_ibase_ka == 2.0

    def test_upsert_does_not_store_the_callers_own_reference(self):
        registry = CurrentGroupConfigRegistry()
        config = _config("mg-a", manual_ibase_ka=2.0)
        registry.upsert(config)
        assert registry.get("ws-1", "mg-a") is not config
