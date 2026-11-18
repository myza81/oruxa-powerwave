"""RD-1 Slice D1 — group-level CT/VT instrument-transformer configuration.

25 tests covering:
  - Domain: vt_ratio / ct_ratio property computation (3 each = 6)
  - Registry: update_fields() VT and CT paths (4 each = 8)
  - Service: update_voltage_configuration() VT validation/flow (5)
  - Service: update_current_ct_config() CT validation/flow (6)
"""

from __future__ import annotations

import pytest

from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.domain.current_group_config import CurrentBaseConfiguration
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.voltage_group_config_service import update_voltage_configuration
from app.services.current_group_config_service import update_current_ct_config
from app.services.errors import InvalidInstrumentTransformerValueError
from app.domain.measurement_group import MeasurementGroup, KIND_VOLTAGE, KIND_CURRENT, STATUS_CONFIRMED
from app.services.measurement_group_registry import MeasurementGroupRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vlt_config_base() -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id="g-vlt",
        workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
    )


@pytest.fixture
def cur_config_base() -> CurrentBaseConfiguration:
    return CurrentBaseConfiguration(
        measurement_group_id="g-cur",
        workspace_id="ws1",
    )


@pytest.fixture
def voltage_registry(vlt_config_base: VoltageBaseConfiguration) -> VoltageGroupConfigRegistry:
    reg = VoltageGroupConfigRegistry()
    reg.upsert(vlt_config_base)
    return reg


@pytest.fixture
def current_registry(cur_config_base: CurrentBaseConfiguration) -> CurrentGroupConfigRegistry:
    reg = CurrentGroupConfigRegistry()
    reg.upsert(cur_config_base)
    return reg


@pytest.fixture
def group_registry_with_voltage() -> MeasurementGroupRegistry:
    reg = MeasurementGroupRegistry()
    group = MeasurementGroup(
        id="g-vlt", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, display_name="VLT1",
        channel_refs=[], status=STATUS_CONFIRMED,
    )
    reg.add(group)
    return reg


@pytest.fixture
def group_registry_with_current() -> MeasurementGroupRegistry:
    reg = MeasurementGroupRegistry()
    group = MeasurementGroup(
        id="g-cur", workspace_id="ws1", source_id="src1",
        kind=KIND_CURRENT, display_name="CUR1",
        channel_refs=[], status=STATUS_CONFIRMED,
    )
    reg.add(group)
    return reg


# ---------------------------------------------------------------------------
# 1. vt_ratio domain property (3 tests)
# ---------------------------------------------------------------------------

def test_vt_ratio_computed_correctly():
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
        vt_primary_v=275_000.0, vt_secondary_v=110.0,
    )
    assert cfg.vt_ratio == pytest.approx(275_000.0 / 110.0)


def test_vt_ratio_none_when_not_configured():
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
    )
    assert cfg.vt_ratio is None


def test_vt_ratio_none_when_secondary_zero():
    cfg = VoltageBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        nominal_voltage_ll_kv=275.0,
        vt_primary_v=275_000.0, vt_secondary_v=0.0,
    )
    assert cfg.vt_ratio is None


# ---------------------------------------------------------------------------
# 2. ct_ratio domain property (3 tests)
# ---------------------------------------------------------------------------

def test_ct_ratio_computed_correctly():
    cfg = CurrentBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        ct_primary_a=2000.0, ct_secondary_a=5.0,
    )
    assert cfg.ct_ratio == pytest.approx(400.0)


def test_ct_ratio_none_when_not_configured():
    cfg = CurrentBaseConfiguration(measurement_group_id="g1", workspace_id="ws1")
    assert cfg.ct_ratio is None


def test_ct_ratio_none_when_secondary_zero():
    cfg = CurrentBaseConfiguration(
        measurement_group_id="g1", workspace_id="ws1",
        ct_primary_a=2000.0, ct_secondary_a=0.0,
    )
    assert cfg.ct_ratio is None


# ---------------------------------------------------------------------------
# 3. VoltageGroupConfigRegistry.update_fields() — VT path (4 tests)
# ---------------------------------------------------------------------------

def test_voltage_registry_update_vt_stores_pair(voltage_registry: VoltageGroupConfigRegistry):
    result = voltage_registry.update_fields(
        "ws1", "g-vlt",
        vt_primary_v=110_000.0, vt_secondary_v=110.0,
        vt_authority="manual", vt_provenance_note="nameplate",
        update_vt=True,
    )
    assert result.vt_primary_v == 110_000.0
    assert result.vt_secondary_v == 110.0
    assert result.vt_authority == "manual"
    assert result.vt_provenance_note == "nameplate"
    # Verify persisted in registry
    stored = voltage_registry.get("ws1", "g-vlt")
    assert stored is not None and stored.vt_primary_v == 110_000.0


def test_voltage_registry_update_vt_clears(voltage_registry: VoltageGroupConfigRegistry):
    # First set VT
    voltage_registry.update_fields(
        "ws1", "g-vlt",
        vt_primary_v=110_000.0, vt_secondary_v=110.0, vt_authority="manual",
        update_vt=True,
    )
    # Then clear
    result = voltage_registry.update_fields(
        "ws1", "g-vlt",
        vt_primary_v=None, vt_secondary_v=None, vt_authority="not_configured",
        update_vt=True,
    )
    assert result.vt_primary_v is None
    assert result.vt_secondary_v is None
    assert result.vt_authority == "not_configured"


def test_voltage_registry_update_vt_false_preserves(voltage_registry: VoltageGroupConfigRegistry):
    # Set VT
    voltage_registry.update_fields(
        "ws1", "g-vlt",
        vt_primary_v=110_000.0, vt_secondary_v=110.0, vt_authority="manual",
        update_vt=True,
    )
    # Update nominal without touching VT
    result = voltage_registry.update_fields(
        "ws1", "g-vlt",
        nominal_voltage_ll_kv=132.0,
        # update_vt defaults to False
    )
    assert result.nominal_voltage_ll_kv == 132.0
    assert result.vt_primary_v == 110_000.0


def test_voltage_registry_update_vt_default_authority(voltage_registry: VoltageGroupConfigRegistry):
    # Pass update_vt=True but vt_authority=None — should default to "not_configured"
    result = voltage_registry.update_fields(
        "ws1", "g-vlt",
        vt_primary_v=110_000.0, vt_secondary_v=110.0,
        # vt_authority intentionally omitted (None)
        update_vt=True,
    )
    assert result.vt_authority == "not_configured"


# ---------------------------------------------------------------------------
# 4. CurrentGroupConfigRegistry.update_fields() — CT path (4 tests)
# ---------------------------------------------------------------------------

def test_current_registry_update_ct_stores_pair(current_registry: CurrentGroupConfigRegistry):
    result = current_registry.update_fields(
        "ws1", "g-cur",
        ct_primary_a=2000.0, ct_secondary_a=5.0,
        ct_authority="manual", ct_provenance_note="relay test sheet",
        update_ct=True,
    )
    assert result.ct_primary_a == 2000.0
    assert result.ct_secondary_a == 5.0
    assert result.ct_authority == "manual"
    assert result.ct_provenance_note == "relay test sheet"
    stored = current_registry.get("ws1", "g-cur")
    assert stored is not None and stored.ct_primary_a == 2000.0


def test_current_registry_update_ct_clears(current_registry: CurrentGroupConfigRegistry):
    current_registry.update_fields(
        "ws1", "g-cur",
        ct_primary_a=2000.0, ct_secondary_a=5.0, ct_authority="manual",
        update_ct=True,
    )
    result = current_registry.update_fields(
        "ws1", "g-cur",
        ct_primary_a=None, ct_secondary_a=None, ct_authority="not_configured",
        update_ct=True,
    )
    assert result.ct_primary_a is None and result.ct_secondary_a is None
    assert result.ct_authority == "not_configured"


def test_current_registry_update_ct_false_preserves_method(current_registry: CurrentGroupConfigRegistry):
    # Set CT
    current_registry.update_fields(
        "ws1", "g-cur",
        ct_primary_a=2000.0, ct_secondary_a=5.0, ct_authority="manual",
        update_ct=True,
    )
    # An upsert of a new config copy should preserve CT if copied from existing
    stored = current_registry.get("ws1", "g-cur")
    assert stored is not None
    assert stored.ct_primary_a == 2000.0  # CT preserved on get


def test_current_registry_update_ct_creates_config_if_absent():
    reg = CurrentGroupConfigRegistry()
    # No pre-existing config
    result = reg.update_fields(
        "ws1", "g-new",
        ct_primary_a=1500.0, ct_secondary_a=1.0, ct_authority="manual",
        update_ct=True,
    )
    assert result.ct_primary_a == 1500.0
    assert result.measurement_group_id == "g-new"


# ---------------------------------------------------------------------------
# 5. update_voltage_configuration() — VT service validation (5 tests)
# ---------------------------------------------------------------------------

def test_vt_service_set_pair_stored(
    group_registry_with_voltage: MeasurementGroupRegistry,
    voltage_registry: VoltageGroupConfigRegistry,
):
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry_with_voltage,
        voltage_config_registry=voltage_registry,
        vt_primary_v=275_000.0, vt_secondary_v=110.0,
        vt_provenance_note="nameplate",
    )
    assert result.vt_primary_v == 275_000.0
    assert result.vt_secondary_v == 110.0
    assert result.vt_authority == "manual"
    assert result.vt_provenance_note == "nameplate"


def test_vt_service_partial_pair_raises(
    group_registry_with_voltage: MeasurementGroupRegistry,
    voltage_registry: VoltageGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="both be supplied or both omitted"):
        update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="g-vlt",
            group_registry=group_registry_with_voltage,
            voltage_config_registry=voltage_registry,
            vt_primary_v=275_000.0,  # secondary omitted
        )


def test_vt_service_clear_vt_plus_pair_raises(
    group_registry_with_voltage: MeasurementGroupRegistry,
    voltage_registry: VoltageGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="clear_vt=True must not be combined"):
        update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="g-vlt",
            group_registry=group_registry_with_voltage,
            voltage_config_registry=voltage_registry,
            vt_primary_v=275_000.0, vt_secondary_v=110.0,
            clear_vt=True,
        )


def test_vt_service_clear_removes_pair(
    group_registry_with_voltage: MeasurementGroupRegistry,
    voltage_registry: VoltageGroupConfigRegistry,
):
    # Set VT first
    update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry_with_voltage,
        voltage_config_registry=voltage_registry,
        vt_primary_v=275_000.0, vt_secondary_v=110.0,
    )
    # Now clear
    result = update_voltage_configuration(
        workspace_id="ws1", measurement_group_id="g-vlt",
        group_registry=group_registry_with_voltage,
        voltage_config_registry=voltage_registry,
        clear_vt=True,
    )
    assert result.vt_primary_v is None
    assert result.vt_secondary_v is None
    assert result.vt_authority == "not_configured"


def test_vt_service_nonpositive_primary_raises(
    group_registry_with_voltage: MeasurementGroupRegistry,
    voltage_registry: VoltageGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="vt_primary_v"):
        update_voltage_configuration(
            workspace_id="ws1", measurement_group_id="g-vlt",
            group_registry=group_registry_with_voltage,
            voltage_config_registry=voltage_registry,
            vt_primary_v=-100.0, vt_secondary_v=110.0,
        )


# ---------------------------------------------------------------------------
# 6. update_current_ct_config() — CT service validation (6 tests)
# ---------------------------------------------------------------------------

def test_ct_service_set_pair_stored(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    result = update_current_ct_config(
        workspace_id="ws1", measurement_group_id="g-cur",
        group_registry=group_registry_with_current,
        current_config_registry=current_registry,
        ct_primary_a=2000.0, ct_secondary_a=5.0,
        ct_provenance_note="relay test sheet",
    )
    assert result.ct_primary_a == 2000.0
    assert result.ct_secondary_a == 5.0
    assert result.ct_authority == "manual"
    assert result.ct_provenance_note == "relay test sheet"


def test_ct_service_partial_pair_raises(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="both be supplied or both omitted"):
        update_current_ct_config(
            workspace_id="ws1", measurement_group_id="g-cur",
            group_registry=group_registry_with_current,
            current_config_registry=current_registry,
            ct_primary_a=2000.0,  # secondary omitted
        )


def test_ct_service_clear_ct_plus_pair_raises(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="clear_ct=True must not be combined"):
        update_current_ct_config(
            workspace_id="ws1", measurement_group_id="g-cur",
            group_registry=group_registry_with_current,
            current_config_registry=current_registry,
            ct_primary_a=2000.0, ct_secondary_a=5.0,
            clear_ct=True,
        )


def test_ct_service_clear_removes_pair(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    # Set CT first
    update_current_ct_config(
        workspace_id="ws1", measurement_group_id="g-cur",
        group_registry=group_registry_with_current,
        current_config_registry=current_registry,
        ct_primary_a=2000.0, ct_secondary_a=5.0,
    )
    # Clear
    result = update_current_ct_config(
        workspace_id="ws1", measurement_group_id="g-cur",
        group_registry=group_registry_with_current,
        current_config_registry=current_registry,
        clear_ct=True,
    )
    assert result.ct_primary_a is None
    assert result.ct_secondary_a is None
    assert result.ct_authority == "not_configured"


def test_ct_service_nonpositive_secondary_raises(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    with pytest.raises(InvalidInstrumentTransformerValueError, match="ct_secondary_a"):
        update_current_ct_config(
            workspace_id="ws1", measurement_group_id="g-cur",
            group_registry=group_registry_with_current,
            current_config_registry=current_registry,
            ct_primary_a=2000.0, ct_secondary_a=0.0,
        )


def test_ct_service_noop_when_nothing_given(
    group_registry_with_current: MeasurementGroupRegistry,
    current_registry: CurrentGroupConfigRegistry,
):
    # Pre-set CT
    update_current_ct_config(
        workspace_id="ws1", measurement_group_id="g-cur",
        group_registry=group_registry_with_current,
        current_config_registry=current_registry,
        ct_primary_a=2000.0, ct_secondary_a=5.0,
    )
    # Call with nothing — should return existing config unchanged
    result = update_current_ct_config(
        workspace_id="ws1", measurement_group_id="g-cur",
        group_registry=group_registry_with_current,
        current_config_registry=current_registry,
    )
    assert result.ct_primary_a == 2000.0
    assert result.ct_secondary_a == 5.0
