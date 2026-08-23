"""Tests for app.services.current_group_config_service (Slice 4 of
DEC-050): the orchestration layer enforcing "current configuration only
applies to a kind='current' group", link validation for
`linked_voltage_group_id`, and the internal configure/resolve operations
task section 8/15 requires.
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.current_group_config import (
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import (
    resolve_group_current_base,
    set_current_base_equipment_rating,
    set_current_base_manual,
    set_current_base_none,
)
from app.services.errors import (
    AmbiguousCurrentVoltageSourceError,
    CurrentConfigurationNotApplicableError,
    InvalidEquipmentRatingValueError,
    InvalidLinkedVoltageGroupError,
    InvalidManualCurrentBaseValueError,
    InvalidManualVoltageBaseValueError,
    MeasurementGroupNotFoundError,
    MissingCurrentVoltageSourceError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base


def _group(group_id, kind, source_id="src-1", status=STATUS_CONFIRMED, channel_names=("A", "B", "C")) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id=source_id, kind=kind, display_name=group_id.upper(),
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=status,
    )


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    registry = MeasurementGroupRegistry()
    registry.add(_group("mg-current", KIND_CURRENT, channel_names=("IR", "IY", "IB")))
    registry.add(_group("mg-voltage", KIND_VOLTAGE, channel_names=("VR", "VY", "VB")))
    registry.add(_group("mg-voltage-other-source", KIND_VOLTAGE, source_id="src-2", channel_names=("VR2", "VY2", "VB2")))
    return registry


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


@pytest.fixture
def current_config_registry() -> CurrentGroupConfigRegistry:
    return CurrentGroupConfigRegistry()


class TestSetCurrentBaseEquipmentRating:
    def test_configures_with_a_manual_voltage_base(self, group_registry, voltage_config_registry, current_config_registry):
        config = set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert config.method == METHOD_EQUIPMENT_RATING
        assert config.equipment_rating_mva == 1000.0
        assert config.manual_voltage_base_kv == 275.0
        assert config.linked_voltage_group_id is None
        assert config.manual_ibase_ka is None

    def test_configures_with_a_linked_voltage_group(self, group_registry, voltage_config_registry, current_config_registry):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        config = set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-voltage",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert config.linked_voltage_group_id == "mg-voltage"
        assert config.manual_voltage_base_kv is None

    def test_switching_from_manual_ibase_clears_it(self, group_registry, voltage_config_registry, current_config_registry):
        set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.5,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        config = set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert config.manual_ibase_ka is None

    def test_rejects_a_voltage_group(self, group_registry, voltage_config_registry, current_config_registry):
        with pytest.raises(CurrentConfigurationNotApplicableError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-voltage", equipment_rating_mva=1000.0,
                manual_voltage_base_kv=275.0,
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )
        assert current_config_registry.get("ws-1", "mg-voltage") is None

    def test_rejects_invalid_equipment_rating(self, group_registry, voltage_config_registry, current_config_registry):
        for bad_value in (0.0, -1.0, None, float("nan")):
            with pytest.raises(InvalidEquipmentRatingValueError):
                set_current_base_equipment_rating(
                    workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=bad_value,
                    manual_voltage_base_kv=275.0,
                    group_registry=group_registry, current_config_registry=current_config_registry,
                    voltage_config_registry=voltage_config_registry,
                )

    def test_rejects_invalid_manual_voltage_base(self, group_registry, voltage_config_registry, current_config_registry):
        for bad_value in (0.0, -1.0, float("nan")):
            with pytest.raises(InvalidManualVoltageBaseValueError):
                set_current_base_equipment_rating(
                    workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                    manual_voltage_base_kv=bad_value,
                    group_registry=group_registry, current_config_registry=current_config_registry,
                    voltage_config_registry=voltage_config_registry,
                )

    def test_rejects_ambiguous_dual_voltage_source(self, group_registry, voltage_config_registry, current_config_registry):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        with pytest.raises(AmbiguousCurrentVoltageSourceError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                linked_voltage_group_id="mg-voltage", manual_voltage_base_kv=275.0,
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )
        assert current_config_registry.get("ws-1", "mg-current") is None

    def test_rejects_missing_voltage_source(self, group_registry, voltage_config_registry, current_config_registry):
        with pytest.raises(MissingCurrentVoltageSourceError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )

    def test_rejects_a_linked_group_that_does_not_exist(self, group_registry, voltage_config_registry, current_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                linked_voltage_group_id="does-not-exist",
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )

    def test_rejects_a_linked_group_from_a_different_source(self, group_registry, voltage_config_registry, current_config_registry):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage-other-source", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        with pytest.raises(InvalidLinkedVoltageGroupError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                linked_voltage_group_id="mg-voltage-other-source",
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )

    def test_rejects_a_linked_group_of_the_wrong_kind(self, group_registry, voltage_config_registry, current_config_registry):
        group_registry.add(_group("mg-current-2", KIND_CURRENT, channel_names=("IR2", "IY2", "IB2")))
        with pytest.raises(InvalidLinkedVoltageGroupError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                linked_voltage_group_id="mg-current-2",
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )

    def test_rejects_a_linked_group_with_no_usable_vbase(self, group_registry, voltage_config_registry, current_config_registry):
        # mg-voltage exists but has never been configured with a base.
        with pytest.raises(InvalidLinkedVoltageGroupError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
                linked_voltage_group_id="mg-voltage",
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )

    def test_unknown_group_raises_not_found(self, group_registry, voltage_config_registry, current_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            set_current_base_equipment_rating(
                workspace_id="ws-1", measurement_group_id="does-not-exist", equipment_rating_mva=1000.0,
                manual_voltage_base_kv=275.0,
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )


class TestSetCurrentBaseManual:
    def test_configures_a_fresh_group(self, group_registry, current_config_registry):
        config = set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.5,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        assert config.method == METHOD_MANUAL
        assert config.manual_ibase_ka == 2.5

    def test_mutating_the_returned_configuration_does_not_affect_the_registry(self, group_registry, current_config_registry):
        """Slice 4 robustness follow-up: the object a setter returns is a
        value, not a live handle into registry state -- mutating it
        afterward must never leak back into what `resolve_group_current_base()`
        (or any other reader) later sees."""
        config = set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.5,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        config.manual_ibase_ka = 999.0
        assert current_config_registry.get("ws-1", "mg-current").manual_ibase_ka == 2.5

    def test_does_not_require_sbase_or_voltage_source(self, group_registry, current_config_registry):
        # Absence of a raised error IS the assertion here (task section 6).
        config = set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.5,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        assert config.equipment_rating_mva is None
        assert config.linked_voltage_group_id is None
        assert config.manual_voltage_base_kv is None

    def test_switching_from_equipment_rating_clears_those_fields(self, group_registry, voltage_config_registry, current_config_registry):
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        config = set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=2.5,
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        assert config.equipment_rating_mva is None
        assert config.manual_voltage_base_kv is None

    def test_rejects_a_voltage_group(self, group_registry, current_config_registry):
        with pytest.raises(CurrentConfigurationNotApplicableError):
            set_current_base_manual(
                workspace_id="ws-1", measurement_group_id="mg-voltage", manual_ibase_ka=2.5,
                group_registry=group_registry, current_config_registry=current_config_registry,
            )

    def test_rejects_invalid_values(self, group_registry, current_config_registry):
        for bad_value in (0.0, -1.0, None, float("nan")):
            with pytest.raises(InvalidManualCurrentBaseValueError):
                set_current_base_manual(
                    workspace_id="ws-1", measurement_group_id="mg-current", manual_ibase_ka=bad_value,
                    group_registry=group_registry, current_config_registry=current_config_registry,
                )


class TestSetCurrentBaseNone:
    def test_clears_all_fields(self, group_registry, voltage_config_registry, current_config_registry):
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=1000.0,
            manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        config = set_current_base_none(
            workspace_id="ws-1", measurement_group_id="mg-current",
            group_registry=group_registry, current_config_registry=current_config_registry,
        )
        assert config.method == METHOD_NONE
        assert config.equipment_rating_mva is None
        assert config.linked_voltage_group_id is None
        assert config.manual_voltage_base_kv is None
        assert config.manual_ibase_ka is None

    def test_rejects_a_voltage_group(self, group_registry, current_config_registry):
        with pytest.raises(CurrentConfigurationNotApplicableError):
            set_current_base_none(
                workspace_id="ws-1", measurement_group_id="mg-voltage",
                group_registry=group_registry, current_config_registry=current_config_registry,
            )


class TestResolveGroupCurrentBase:
    def test_full_equipment_rating_pipeline_with_linked_group(self, group_registry, voltage_config_registry, current_config_registry):
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
        resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-current",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.ibase_ka == pytest.approx(2.0995, abs=0.001)

    def test_manual_vbase_fallback_pipeline(self, group_registry, voltage_config_registry, current_config_registry):
        """Task section 12: a Current group with NO corresponding
        Voltage group in the recording must still resolve correctly via
        a manual applicable Vbase."""
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-current", equipment_rating_mva=500.0,
            manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-current",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.ibase_ka == pytest.approx(1.0497, abs=0.001)

    def test_voltage_group_resolves_as_not_applicable_not_an_error(self, group_registry, voltage_config_registry, current_config_registry):
        resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-voltage",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_unconfigured_current_group_is_base_required(self, group_registry, voltage_config_registry, current_config_registry):
        resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-current",
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert resolution.status == STATUS_BASE_REQUIRED

    def test_unknown_group_raises_not_found(self, group_registry, voltage_config_registry, current_config_registry):
        with pytest.raises(MeasurementGroupNotFoundError):
            resolve_group_current_base(
                workspace_id="ws-1", measurement_group_id="does-not-exist",
                group_registry=group_registry, current_config_registry=current_config_registry,
                voltage_config_registry=voltage_config_registry,
            )


class TestIndependentCurrentGroupsInOneSource:
    """Task section 10/11/25: one source containing multiple current
    measurement groups (e.g. a transformer's HV and LV sides) must
    support fully independent CurrentBaseConfigurations -- no source-
    wide leakage, and the same Sbase on both sides must NOT imply the
    same Ibase."""

    @pytest.fixture
    def multi_group_registry(self) -> MeasurementGroupRegistry:
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-ibt-hv-current", KIND_CURRENT, channel_names=("IBT1 HV IR", "IBT1 HV IY", "IBT1 HV IB")))
        registry.add(_group("mg-ibt-lv-current", KIND_CURRENT, channel_names=("IBT1 LV IR", "IBT1 LV IY", "IBT1 LV IB")))
        registry.add(_group("mg-275kv-line-current", KIND_CURRENT, channel_names=("275KV LINE A IR", "275KV LINE A IY", "275KV LINE A IB")))
        registry.add(_group("mg-132kv-line-current", KIND_CURRENT, channel_names=("132KV LINE A IR", "132KV LINE A IY", "132KV LINE A IB")))
        registry.add(_group("mg-hv-bus-voltage", KIND_VOLTAGE, channel_names=("275KV BUS VR", "275KV BUS VY", "275KV BUS VB")))
        registry.add(_group("mg-lv-bus-voltage", KIND_VOLTAGE, channel_names=("132KV BUS VR", "132KV BUS VY", "132KV BUS VB")))
        return registry

    def test_hv_and_lv_sides_of_the_same_transformer_resolve_independently(
        self, multi_group_registry, voltage_config_registry, current_config_registry
    ):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-hv-bus-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=multi_group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-lv-bus-voltage", nominal_voltage_ll_kv=132.0,
            group_registry=multi_group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-ibt-hv-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-hv-bus-voltage",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-ibt-lv-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-lv-bus-voltage",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )

        hv_resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-ibt-hv-current",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        lv_resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-ibt-lv-current",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )

        assert hv_resolution.status == STATUS_CONFIGURED
        assert lv_resolution.status == STATUS_CONFIGURED
        assert hv_resolution.ibase_ka == pytest.approx(2.0995, abs=0.001)
        assert lv_resolution.ibase_ka == pytest.approx(4.3739, abs=0.001)
        # Same Sbase on both sides must NOT imply the same Ibase.
        assert hv_resolution.ibase_ka != pytest.approx(lv_resolution.ibase_ka)

    def test_four_independent_current_groups_do_not_leak_configuration(
        self, multi_group_registry, voltage_config_registry, current_config_registry
    ):
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id="mg-hv-bus-voltage", nominal_voltage_ll_kv=275.0,
            group_registry=multi_group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_current_base_equipment_rating(
            workspace_id="ws-1", measurement_group_id="mg-ibt-hv-current", equipment_rating_mva=1000.0,
            linked_voltage_group_id="mg-hv-bus-voltage",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        set_current_base_manual(
            workspace_id="ws-1", measurement_group_id="mg-275kv-line-current", manual_ibase_ka=1.2,
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
        )
        set_current_base_none(
            workspace_id="ws-1", measurement_group_id="mg-132kv-line-current",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
        )
        # mg-ibt-lv-current is left entirely unconfigured.

        assert current_config_registry.get("ws-1", "mg-ibt-hv-current").method == METHOD_EQUIPMENT_RATING
        assert current_config_registry.get("ws-1", "mg-275kv-line-current").method == METHOD_MANUAL
        assert current_config_registry.get("ws-1", "mg-132kv-line-current").method == METHOD_NONE
        assert current_config_registry.get("ws-1", "mg-ibt-lv-current") is None

        lv_resolution = resolve_group_current_base(
            workspace_id="ws-1", measurement_group_id="mg-ibt-lv-current",
            group_registry=multi_group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        assert lv_resolution.status == STATUS_BASE_REQUIRED
