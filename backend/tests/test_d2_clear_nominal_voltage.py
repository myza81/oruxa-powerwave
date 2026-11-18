"""RD-1 Slice D2 — clear_nominal_voltage contract.

10 tests covering:
  - Registry: update_nominal flag clears and preserves fields (3)
  - Service: clear_nominal_voltage validation and state transitions (5)
  - API: clear_nominal_voltage route behaviour (2)
"""

from __future__ import annotations

import pytest

from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.domain.base_authority import (
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_AUTO,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import update_voltage_configuration
from app.services.errors import InvalidVoltageBaseValueError
from app.domain.measurement_group import MeasurementGroup, KIND_VOLTAGE, STATUS_CONFIRMED
from app.services.measurement_group_registry import MeasurementGroupRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def voltage_registry_with_manual_kv() -> VoltageGroupConfigRegistry:
    """Voltage registry pre-populated with a manual 275 kV configuration."""
    reg = VoltageGroupConfigRegistry()
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g-vlt", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
        base_authority=BASE_AUTHORITY_MANUAL,
        reference_mode="manual",
        reference_override="line_to_ground",
        base_reference_side="primary",
        secondary_voltage_ll_v=63509.0,
        manual_conflict_detected=True,
        manual_conflict_detail="auto detected 66 kV",
    )
    reg.upsert(cfg)
    return reg


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    reg = MeasurementGroupRegistry()
    group = MeasurementGroup(
        id="g-vlt", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, display_name="VLT1",
        channel_refs=[], status=STATUS_CONFIRMED,
    )
    reg.add(group)
    return reg


# ---------------------------------------------------------------------------
# 1. Registry: update_nominal flag (3 tests)
# ---------------------------------------------------------------------------

def test_registry_update_nominal_clears_kv():
    """update_nominal=True with nominal_voltage_ll_kv=None explicitly sets kV to None."""
    reg = VoltageGroupConfigRegistry()
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
    )
    reg.upsert(cfg)
    result = reg.update_fields("ws1", "g1", update_nominal=True, nominal_voltage_ll_kv=None)
    assert result.nominal_voltage_ll_kv is None


def test_registry_update_nominal_preserves_secondary():
    """update_nominal=True must NOT touch secondary_voltage_ll_v."""
    reg = VoltageGroupConfigRegistry()
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
        secondary_voltage_ll_v=63509.0,
    )
    reg.upsert(cfg)
    result = reg.update_fields("ws1", "g1", update_nominal=True, nominal_voltage_ll_kv=None)
    assert result.secondary_voltage_ll_v == pytest.approx(63509.0)


def test_registry_update_nominal_false_preserves_existing_kv():
    """update_nominal=False (default) with nominal=None does not modify existing kV."""
    reg = VoltageGroupConfigRegistry()
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=132.0,
    )
    reg.upsert(cfg)
    result = reg.update_fields("ws1", "g1", nominal_voltage_ll_kv=None)
    assert result.nominal_voltage_ll_kv == pytest.approx(132.0)


# ---------------------------------------------------------------------------
# 2. Service: clear_nominal_voltage logic (5 tests)
# ---------------------------------------------------------------------------

def test_service_clear_nominal_sets_needs_review(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """clear_nominal_voltage=True sets base_authority to needs_review."""
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="manual",
        reference_override="line_to_ground",
        base_reference_side="primary",
    )
    assert result.base_authority == BASE_AUTHORITY_NEEDS_REVIEW
    assert result.nominal_voltage_ll_kv is None


def test_service_clear_nominal_preserves_reference_mode(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """clear_nominal_voltage preserves the reference_mode/override passed in the call."""
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="manual",
        reference_override="line_to_ground",
    )
    assert result.reference_mode == "manual"
    assert result.reference_override == "line_to_ground"


def test_service_clear_nominal_preserves_secondary_voltage(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """clear_nominal_voltage must NOT clear secondary_voltage_ll_v (Gate 1)."""
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="manual",
        reference_override="line_to_ground",
    )
    assert result.secondary_voltage_ll_v == pytest.approx(63509.0)


def test_service_clear_nominal_clears_conflict_flag(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """clear_nominal_voltage clears the manual_conflict flag."""
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="manual",
        reference_override="line_to_ground",
    )
    assert result.manual_conflict_detected is False
    assert result.manual_conflict_detail is None


def test_service_clear_nominal_combined_with_kv_raises(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """clear_nominal_voltage=True combined with nominal_voltage_ll_kv must raise 422."""
    with pytest.raises(InvalidVoltageBaseValueError, match="clear_nominal_voltage"):
        update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="g-vlt",
            group_registry=group_registry,
            voltage_config_registry=voltage_registry_with_manual_kv,
            clear_nominal_voltage=True,
            nominal_voltage_ll_kv=275.0,
            reference_mode="auto",
        )


# ---------------------------------------------------------------------------
# 3. API route: clear_nominal_voltage (2 tests)
# ---------------------------------------------------------------------------

def test_api_clear_nominal_voltage_integration(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """End-to-end: clear_nominal_voltage via service layer clears kV and sets needs_review."""
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="auto",
    )
    assert result.nominal_voltage_ll_kv is None
    assert result.base_authority == BASE_AUTHORITY_NEEDS_REVIEW
    assert result.manual_conflict_detected is False
    # secondary_voltage_ll_v preserved (Gate 1)
    assert result.secondary_voltage_ll_v == pytest.approx(63509.0)


def test_api_set_kv_after_clear_restores_manual(
    group_registry: MeasurementGroupRegistry,
    voltage_registry_with_manual_kv: VoltageGroupConfigRegistry,
):
    """After a clear, setting a new kV atomically restores base_authority=manual."""
    update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        clear_nominal_voltage=True,
        reference_mode="auto",
    )
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry,
        voltage_config_registry=voltage_registry_with_manual_kv,
        nominal_voltage_ll_kv=132.0,
        reference_mode="auto",
    )
    assert result.nominal_voltage_ll_kv == pytest.approx(132.0)
    assert result.base_authority == BASE_AUTHORITY_MANUAL
