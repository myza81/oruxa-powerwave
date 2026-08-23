"""Tests for app.services.voltage_group_config_service (Slice 3 of
DEC-050): the orchestration layer enforcing "voltage configuration only
applies to a kind='voltage' group" and providing the internal
configure/override/resolve operations section 13 requires.
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.voltage_group_config import (
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    VOLTAGE_REFERENCE_MODE_AUTO,
    VOLTAGE_REFERENCE_MODE_MANUAL,
)
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE
from app.services.errors import (
    InvalidVoltageBaseValueError,
    InvalidVoltageReferenceOverrideError,
    MeasurementGroupNotFoundError,
    VoltageConfigurationNotApplicableError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import (
    get_effective_voltage_reference,
    resolve_group_voltage_base,
    return_voltage_reference_to_auto,
    set_manual_voltage_reference,
    set_voltage_base,
)


def _group(group_id="mg-1", kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB")) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id="src-1", kind=kind, display_name="TEST GROUP",
        channel_refs=[ChannelRef(kind="source", source_id="src-1", channel_name=n) for n in channel_names],
        status=status,
    )


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    registry = MeasurementGroupRegistry()
    registry.add(_group("mg-voltage", kind=KIND_VOLTAGE, status=STATUS_CONFIRMED))
    registry.add(_group("mg-current", kind=KIND_CURRENT, status=STATUS_CONFIRMED, channel_names=("IR", "IY", "IB")))
    return registry


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


class TestSetVoltageBase:
    def test_configures_a_fresh_group(self, group_registry, voltage_config_registry):
        config = set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        assert config.nominal_voltage_ll_kv == 275.0
        assert config.reference_mode == VOLTAGE_REFERENCE_MODE_AUTO
        assert voltage_config_registry.get("ws-1", "mg-voltage").nominal_voltage_ll_kv == 275.0

    def test_mutating_the_returned_configuration_does_not_affect_the_registry(self, group_registry, voltage_config_registry):
        """Robustness follow-up: the object a setter returns is a value,
        not a live handle into registry state -- mutating it afterward
        must never leak back into what `resolve_group_voltage_base()`
        (or any other reader) later sees."""
        config = set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        config.nominal_voltage_ll_kv = 999.0
        assert voltage_config_registry.get("ws-1", "mg-voltage").nominal_voltage_ll_kv == 275.0

    def test_reconfiguring_preserves_an_existing_manual_override(self, group_registry, voltage_config_registry):
        set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        set_manual_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage", reference=LINE_TO_LINE,
                                      group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        # Changing just the base value must not silently reset the mode.
        config = set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=132.0,
                                   group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert config.nominal_voltage_ll_kv == 132.0
        assert config.reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL
        assert config.reference_override == LINE_TO_LINE

    def test_rejects_a_current_group(self, group_registry, voltage_config_registry):
        with pytest.raises(VoltageConfigurationNotApplicableError):
            set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-current", nominal_voltage_ll_kv=275.0,
                              group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert voltage_config_registry.get("ws-1", "mg-current") is None

    def test_rejects_invalid_values(self, group_registry, voltage_config_registry):
        for bad_value in (0.0, -1.0, None, float("nan")):
            with pytest.raises(InvalidVoltageBaseValueError):
                set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=bad_value,
                                  group_registry=group_registry, voltage_config_registry=voltage_config_registry)

    def test_unknown_group_raises_not_found(self, group_registry, voltage_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            set_voltage_base(workspace_id="ws-1", measurement_group_id="does-not-exist", nominal_voltage_ll_kv=275.0,
                              group_registry=group_registry, voltage_config_registry=voltage_config_registry)


class TestManualOverrideAndReturnToAuto:
    def test_set_manual_voltage_reference(self, group_registry, voltage_config_registry):
        config = set_manual_voltage_reference(
            workspace_id="ws-1", measurement_group_id="mg-voltage", reference=LINE_TO_LINE,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        assert config.reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL
        assert config.reference_override == LINE_TO_LINE

    def test_rejects_invalid_reference_value(self, group_registry, voltage_config_registry):
        with pytest.raises(InvalidVoltageReferenceOverrideError):
            set_manual_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage", reference="bogus",
                                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)

    def test_rejects_a_current_group(self, group_registry, voltage_config_registry):
        with pytest.raises(VoltageConfigurationNotApplicableError):
            set_manual_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-current", reference=LINE_TO_LINE,
                                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)

    def test_return_to_auto_clears_the_override_entirely(self, group_registry, voltage_config_registry):
        set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        set_manual_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage", reference=LINE_TO_LINE,
                                      group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        config = return_voltage_reference_to_auto(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                    group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert config.reference_mode == VOLTAGE_REFERENCE_MODE_AUTO
        assert config.reference_override is None
        # The nominal base value itself must survive the mode change.
        assert config.nominal_voltage_ll_kv == 275.0

    def test_return_to_auto_on_a_never_configured_group_defaults_cleanly(self, group_registry, voltage_config_registry):
        config = return_voltage_reference_to_auto(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                    group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert config.reference_mode == VOLTAGE_REFERENCE_MODE_AUTO
        assert config.reference_override is None


class TestGetEffectiveVoltageReference:
    def test_auto_result_reflects_the_groups_own_channels(self, group_registry, voltage_config_registry):
        result = get_effective_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                   group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert result.reference == LINE_TO_GROUND

    def test_manual_override_reflected_immediately(self, group_registry, voltage_config_registry):
        set_manual_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage", reference=LINE_TO_LINE,
                                      group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        result = get_effective_voltage_reference(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                   group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert result.reference == LINE_TO_LINE

    def test_unknown_group_raises_not_found(self, group_registry, voltage_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            get_effective_voltage_reference(workspace_id="ws-1", measurement_group_id="does-not-exist",
                                             group_registry=group_registry, voltage_config_registry=voltage_config_registry)


class TestResolveGroupVoltageBase:
    def test_full_pipeline_resolves_correctly(self, group_registry, voltage_config_registry):
        set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        resolution = resolve_group_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                  group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.effective_reference == LINE_TO_GROUND
        assert resolution.denominator_kv == pytest.approx(158.77, abs=0.01)

    def test_current_group_resolves_as_not_applicable_not_an_error(self, group_registry, voltage_config_registry):
        # Deliberately asymmetric with the mutators above -- see
        # resolve_group_voltage_base()'s own docstring.
        resolution = resolve_group_voltage_base(workspace_id="ws-1", measurement_group_id="mg-current",
                                                  group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_unconfigured_voltage_group_is_base_required(self, group_registry, voltage_config_registry):
        resolution = resolve_group_voltage_base(workspace_id="ws-1", measurement_group_id="mg-voltage",
                                                  group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert resolution.status == STATUS_BASE_REQUIRED

    def test_unknown_group_raises_not_found(self, group_registry, voltage_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            resolve_group_voltage_base(workspace_id="ws-1", measurement_group_id="does-not-exist",
                                        group_registry=group_registry, voltage_config_registry=voltage_config_registry)

    def test_suggested_group_never_resolves_as_authoritative(self, group_registry, voltage_config_registry):
        group_registry.add(_group("mg-suggested", status=STATUS_SUGGESTED, channel_names=("OTHER VA", "OTHER VB", "OTHER VC")))
        set_voltage_base(workspace_id="ws-1", measurement_group_id="mg-suggested", nominal_voltage_ll_kv=275.0,
                          group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        resolution = resolve_group_voltage_base(workspace_id="ws-1", measurement_group_id="mg-suggested",
                                                  group_registry=group_registry, voltage_config_registry=voltage_config_registry)
        assert resolution.status == STATUS_BASE_REQUIRED
