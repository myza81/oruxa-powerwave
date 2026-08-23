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
