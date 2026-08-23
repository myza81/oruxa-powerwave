"""Unit tests for app.services.group_aware_per_unit (DEC-050 Slice 5) --
the pure resolver/registry level, without going through the FastAPI app
(see test_group_aware_per_unit_endpoints.py for full live-endpoint
integration coverage).
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, FREQUENCY, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.per_unit import STATUS_BASE_REQUIRED, STATUS_CONFIGURED
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_equipment_rating, set_current_base_manual
from app.services.group_aware_per_unit import resolve_group_aware_per_unit
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772


def _group(group_id, kind, source_id="src-1", channel_names=("A", "B", "C"), status=STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id=source_id, kind=kind, display_name=group_id.upper(),
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=status,
    )


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    registry = MeasurementGroupRegistry()
    registry.add(_group("mg-voltage", KIND_VOLTAGE, channel_names=("VR", "VY", "VB")))
    registry.add(_group("mg-current", KIND_CURRENT, channel_names=("IR", "IY", "IB")))
    return registry


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


@pytest.fixture
def current_config_registry() -> CurrentGroupConfigRegistry:
    return CurrentGroupConfigRegistry()


class TestUngroupedAndIneligibleChannels:
    def test_returns_none_for_a_channel_with_no_group(self, group_registry, voltage_config_registry, current_config_registry):
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="SPARE", engineering_type=VOLTAGE,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_returns_none_for_a_non_voltage_current_type_without_any_lookup(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="VR", engineering_type=FREQUENCY,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None


class TestVoltageGroupResolution:
    def test_configured_voltage_group_resolves_in_volts(self, group_registry, voltage_config_registry, current_config_registry):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="VR", engineering_type=VOLTAGE,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-voltage"
        # LG-detected (VR/VY/VB): denominator is nominal_LL/sqrt(3), in
        # VOLTS (per_unit.PerUnitResolution's own established unit
        # convention, x1000 from the group resolver's own kV).
        assert result.base_amount == pytest.approx((275.0 / SQRT_3) * 1000.0, abs=0.1)
        assert result.base_unit == "V"

    def test_unconfigured_voltage_group_is_base_required(self, group_registry, voltage_config_registry, current_config_registry):
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="VR", engineering_type=VOLTAGE,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED
        assert result.base_amount is None


class TestCurrentGroupResolution:
    def test_manual_current_group_resolves_in_amps(self, group_registry, voltage_config_registry, current_config_registry):
        set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="IR", engineering_type=CURRENT,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.base_amount == pytest.approx(2000.0)
        assert result.base_unit == "A"

    def test_equipment_rating_with_linked_voltage_group_resolves_in_amps(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-voltage",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="IR", engineering_type=CURRENT,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        expected_amps = (1000.0 / (SQRT_3 * 275.0)) * 1000.0
        assert result.base_amount == pytest.approx(expected_amps, rel=1e-6)
        assert result.base_unit == "A"

    def test_current_method_none_is_base_required(self, group_registry, voltage_config_registry, current_config_registry):
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="IR", engineering_type=CURRENT,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED


class TestGroupNotConfirmedGate:
    def test_suggested_current_group_is_base_required_even_with_a_valid_config(
        self, voltage_config_registry, current_config_registry
    ):
        registry = MeasurementGroupRegistry()
        from app.domain.measurement_group import STATUS_SUGGESTED
        registry.add(_group("mg-current-2", KIND_CURRENT, channel_names=("IR2", "IY2", "IB2"), status=STATUS_SUGGESTED))
        set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current-2", manual_ibase_ka=2.0,
            group_registry=registry, current_config_registry=current_config_registry,
        )
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="IR2", engineering_type=CURRENT,
            group_registry=registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED

    def test_suggested_linked_voltage_group_does_not_block_current_resolution(
        self, current_config_registry
    ):
        """Task section 5's explicit rule: only the CURRENT group's own
        status gates authoritative resolution -- a linked Voltage
        group's own status is provenance only."""
        from app.domain.measurement_group import STATUS_SUGGESTED

        group_registry = MeasurementGroupRegistry()
        voltage_config_registry = VoltageGroupConfigRegistry()
        group_registry.add(_group("mg-voltage-suggested", KIND_VOLTAGE, channel_names=("VR", "VY", "VB"), status=STATUS_SUGGESTED))
        group_registry.add(_group("mg-current", KIND_CURRENT, channel_names=("IR", "IY", "IB"), status=STATUS_CONFIRMED))
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage-suggested", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-voltage-suggested",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        result = resolve_group_aware_per_unit(
            workspace_id="ws-1", source_id="src-1", channel_name="IR", engineering_type=CURRENT,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
