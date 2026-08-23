"""Tests for app.services.voltage_group_config_registry (Slice 3 of
DEC-050): storage CRUD and workspace isolation -- registry-level only,
no MeasurementGroupRegistry/kind-validation involved (see
test_voltage_group_config_service.py for that layer).
"""

from __future__ import annotations

from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_AUTO, VoltageBaseConfiguration
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


def _config(measurement_group_id="mg-1", workspace_id="ws-1", nominal_voltage_ll_kv=275.0) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id=measurement_group_id, workspace_id=workspace_id,
        nominal_voltage_ll_kv=nominal_voltage_ll_kv, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO, reference_override=None,
    )


class TestBasicCrud:
    def test_upsert_and_get(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a"))
        assert registry.get("ws-1", "mg-a") is not None
        assert registry.get("ws-1", "unknown") is None

    def test_upsert_replaces_entirely(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a", nominal_voltage_ll_kv=275.0))
        registry.upsert(_config("mg-a", nominal_voltage_ll_kv=132.0))
        assert registry.get("ws-1", "mg-a").nominal_voltage_ll_kv == 132.0

    def test_list_for_workspace_is_scoped(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a", workspace_id="ws-1"))
        registry.upsert(_config("mg-b", workspace_id="ws-2"))
        assert [c.measurement_group_id for c in registry.list_for_workspace("ws-1")] == ["mg-a"]

    def test_delete_is_idempotent(self):
        registry = VoltageGroupConfigRegistry()
        assert registry.delete("ws-1", "does-not-exist") is False
        registry.upsert(_config("mg-a"))
        assert registry.delete("ws-1", "mg-a") is True
        assert registry.get("ws-1", "mg-a") is None
        assert registry.delete("ws-1", "mg-a") is False

    def test_count(self):
        registry = VoltageGroupConfigRegistry()
        assert registry.count() == 0
        registry.upsert(_config("mg-a"))
        registry.upsert(_config("mg-b", workspace_id="ws-2"))
        assert registry.count() == 2


class TestWorkspaceIsolation:
    def test_same_group_id_in_two_workspaces_stays_independent(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-1", workspace_id="ws-a", nominal_voltage_ll_kv=275.0))
        registry.upsert(_config("mg-1", workspace_id="ws-b", nominal_voltage_ll_kv=132.0))
        assert registry.get("ws-a", "mg-1").nominal_voltage_ll_kv == 275.0
        assert registry.get("ws-b", "mg-1").nominal_voltage_ll_kv == 132.0

    def test_remove_workspace_clears_only_that_workspace(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-1", workspace_id="ws-1"))
        registry.upsert(_config("mg-2", workspace_id="ws-1"))
        registry.upsert(_config("mg-3", workspace_id="ws-2"))
        removed = registry.remove_workspace("ws-1")
        assert removed == 2
        assert registry.list_for_workspace("ws-1") == []
        assert [c.measurement_group_id for c in registry.list_for_workspace("ws-2")] == ["mg-3"]

    def test_remove_workspace_is_idempotent(self):
        registry = VoltageGroupConfigRegistry()
        assert registry.remove_workspace("ws-empty") == 0


class TestCopyOnBoundary:
    """Robustness follow-up (post-Codex-review of the sibling Current
    registry, applied here too): the registry must own its stored
    state -- mutating an object on either side of `upsert()`/`get()`/
    `list_for_workspace()` must never reach back into registry-owned
    state, the same guarantee `MeasurementGroupRegistry` and
    `CurrentGroupConfigRegistry` already provide for their own types."""

    def test_mutating_the_object_passed_to_upsert_does_not_affect_the_registry(self):
        registry = VoltageGroupConfigRegistry()
        config = _config("mg-a", nominal_voltage_ll_kv=275.0)
        registry.upsert(config)
        config.nominal_voltage_ll_kv = 999.0
        assert registry.get("ws-1", "mg-a").nominal_voltage_ll_kv == 275.0

    def test_mutating_a_get_result_does_not_affect_the_registry(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a", nominal_voltage_ll_kv=275.0))
        fetched = registry.get("ws-1", "mg-a")
        fetched.nominal_voltage_ll_kv = 999.0
        assert registry.get("ws-1", "mg-a").nominal_voltage_ll_kv == 275.0

    def test_mutating_a_list_for_workspace_result_does_not_affect_the_registry(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a", nominal_voltage_ll_kv=275.0))
        [listed] = registry.list_for_workspace("ws-1")
        listed.nominal_voltage_ll_kv = 999.0
        assert registry.get("ws-1", "mg-a").nominal_voltage_ll_kv == 275.0

    def test_successive_get_calls_return_independent_objects(self):
        registry = VoltageGroupConfigRegistry()
        registry.upsert(_config("mg-a", nominal_voltage_ll_kv=275.0))
        first = registry.get("ws-1", "mg-a")
        second = registry.get("ws-1", "mg-a")
        assert first is not second
        first.nominal_voltage_ll_kv = 999.0
        assert second.nominal_voltage_ll_kv == 275.0

    def test_upsert_does_not_store_the_callers_own_reference(self):
        registry = VoltageGroupConfigRegistry()
        config = _config("mg-a", nominal_voltage_ll_kv=275.0)
        registry.upsert(config)
        assert registry.get("ws-1", "mg-a") is not config
