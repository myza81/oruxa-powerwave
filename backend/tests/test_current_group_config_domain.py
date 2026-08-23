"""Tests for app.domain.current_group_config (Slice 4 of DEC-050): pure
domain validation, equipment-rating Ibase mathematics, and the group-
level resolver -- no registry/service involvement (see
test_current_group_config_service.py for the orchestration layer).
"""

from __future__ import annotations

import math

import pytest

from app.domain.current_group_config import (
    CurrentBaseConfiguration,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    convert_current_to_pu,
    current_base_method_valid,
    equipment_rating_ibase_ka,
    equipment_rating_mva_valid,
    manual_ibase_ka_valid,
    manual_voltage_base_kv_valid,
    resolve_current_base_for_group,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.voltage_group_config import VOLTAGE_REFERENCE_MODE_AUTO, VOLTAGE_REFERENCE_MODE_MANUAL, VoltageBaseConfiguration
from app.domain.voltage_reference import LINE_TO_LINE


def _current_group(group_id="mg-current", status=STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id="src-1", kind=KIND_CURRENT, display_name="TEST CURRENT GROUP",
        status=status,
    )


def _voltage_group(group_id="mg-voltage", status=STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id="src-1", kind=KIND_VOLTAGE, display_name="TEST VOLTAGE GROUP",
        status=status,
    )


def _voltage_config(group_id="mg-voltage", nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO,
                     reference_override=None) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id=group_id, workspace_id="ws-1", nominal_voltage_ll_kv=nominal_voltage_ll_kv,
        reference_mode=reference_mode, reference_override=reference_override,
    )


class TestValidators:
    def test_current_base_method_valid(self):
        assert current_base_method_valid(METHOD_EQUIPMENT_RATING)
        assert current_base_method_valid(METHOD_MANUAL)
        assert current_base_method_valid(METHOD_NONE)
        assert not current_base_method_valid("ct_primary")
        assert not current_base_method_valid("bogus")

    @pytest.mark.parametrize("validator", [equipment_rating_mva_valid, manual_ibase_ka_valid, manual_voltage_base_kv_valid])
    def test_numeric_validators_accept_positive_finite(self, validator):
        assert validator(1000.0)
        assert validator(0.001)

    @pytest.mark.parametrize("validator", [equipment_rating_mva_valid, manual_ibase_ka_valid, manual_voltage_base_kv_valid])
    def test_numeric_validators_reject_bad_values(self, validator):
        for bad in (0.0, -1.0, None, float("nan"), float("inf"), True, False):
            assert not validator(bad)


class TestEquipmentRatingIbaseMath:
    """Task section 5/24 worked examples -- the core engineering formula
    this slice exists to implement: Ibase = Sbase / (sqrt(3) * Vbase_LL)."""

    @pytest.mark.parametrize(
        "mva,kv,expected_ka",
        [
            (1000.0, 500.0, 1.1547),
            (1000.0, 275.0, 2.0995),
            (1000.0, 132.0, 4.3739),
        ],
    )
    def test_worked_examples(self, mva, kv, expected_ka):
        assert equipment_rating_ibase_ka(mva, kv) == pytest.approx(expected_ka, abs=0.001)

    def test_same_sbase_different_vbase_yields_different_ibase(self):
        """Core engineering requirement (task section 11): the same
        equipment Sbase must NOT imply the same Ibase on different
        sides of a transformer."""
        hv_ibase = equipment_rating_ibase_ka(1000.0, 275.0)
        lv_ibase = equipment_rating_ibase_ka(1000.0, 132.0)
        assert hv_ibase != pytest.approx(lv_ibase)
        assert hv_ibase == pytest.approx(2.0995, abs=0.001)
        assert lv_ibase == pytest.approx(4.3739, abs=0.001)


class TestResolveCurrentBaseForGroup:
    def test_voltage_group_is_not_applicable(self):
        resolution = resolve_current_base_for_group(_voltage_group(), None)
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_suggested_group_never_resolves_as_authoritative(self):
        group = _current_group(status=STATUS_SUGGESTED)
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=2.5,
        )
        resolution = resolve_current_base_for_group(group, config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "group_not_confirmed"

    def test_no_configuration_is_base_required(self):
        resolution = resolve_current_base_for_group(_current_group(), None)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "current_base_not_configured"

    def test_method_none_is_base_required(self):
        config = CurrentBaseConfiguration(measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_NONE)
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "current_base_not_configured"

    def test_manual_method_resolves_directly(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=3.5,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.ibase_ka == 3.5
        assert resolution.applicable_voltage_ll_kv is None

    def test_manual_method_without_a_value_is_base_required(self):
        config = CurrentBaseConfiguration(measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL)
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "manual_ibase_not_configured"

    def test_equipment_rating_with_manual_voltage_base(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=500.0, manual_voltage_base_kv=275.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.ibase_ka == pytest.approx(1.0497, abs=0.001)
        assert resolution.applicable_voltage_ll_kv == 275.0

    def test_equipment_rating_without_mva_is_base_required(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            manual_voltage_base_kv=275.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "equipment_rating_not_configured"

    def test_equipment_rating_without_any_voltage_source_is_base_required(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=1000.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "applicable_voltage_base_not_configured"

    def test_equipment_rating_with_linked_voltage_group(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=1000.0, linked_voltage_group_id="mg-voltage",
        )
        resolution = resolve_current_base_for_group(
            _current_group(), config,
            linked_voltage_group=_voltage_group(), linked_voltage_config=_voltage_config(nominal_voltage_ll_kv=275.0),
        )
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.ibase_ka == pytest.approx(2.0995, abs=0.001)
        assert resolution.applicable_voltage_ll_kv == 275.0

    def test_equipment_rating_with_linked_group_missing_its_own_base_is_base_required(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=1000.0, linked_voltage_group_id="mg-voltage",
        )
        resolution = resolve_current_base_for_group(
            _current_group(), config,
            linked_voltage_group=_voltage_group(), linked_voltage_config=_voltage_config(nominal_voltage_ll_kv=None),
        )
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "applicable_voltage_base_not_configured"

    def test_linked_voltage_group_reference_is_irrelevant_to_ibase(self):
        """Task section 14's dedicated invariant: two linked Voltage
        groups sharing the same Vbase_LL but different effective
        reference (LG vs LL) must produce the SAME Ibase -- equipment-
        rated current-base derivation always uses the raw nominal LL
        voltage, never the Voltage group's own reference-aware
        denominator (section 5/13)."""
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_EQUIPMENT_RATING,
            equipment_rating_mva=1000.0, linked_voltage_group_id="mg-voltage",
        )
        lg_config = _voltage_config(nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO)
        ll_config = _voltage_config(
            nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, reference_override=LINE_TO_LINE,
        )
        resolution_lg = resolve_current_base_for_group(
            _current_group(), config, linked_voltage_group=_voltage_group(), linked_voltage_config=lg_config,
        )
        resolution_ll = resolve_current_base_for_group(
            _current_group(), config, linked_voltage_group=_voltage_group(), linked_voltage_config=ll_config,
        )
        assert resolution_lg.status == STATUS_CONFIGURED
        assert resolution_ll.status == STATUS_CONFIGURED
        assert resolution_lg.ibase_ka == pytest.approx(resolution_ll.ibase_ka)
        assert resolution_lg.ibase_ka == pytest.approx(2.0995, abs=0.001)


class TestConvertCurrentToPu:
    def test_ipu_equals_measured_over_ibase(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=2.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert convert_current_to_pu(31.0, "kA", resolution) == pytest.approx(15.5)
        assert convert_current_to_pu(31000.0, "A", resolution) == pytest.approx(15.5)

    def test_returns_none_when_not_configured(self):
        resolution = resolve_current_base_for_group(_current_group(), None)
        assert convert_current_to_pu(31.0, "kA", resolution) is None

    def test_returns_none_for_unrecognized_unit(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=2.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert convert_current_to_pu(31.0, "mA", resolution) is None

    def test_returns_none_for_non_finite_measured_value(self):
        config = CurrentBaseConfiguration(
            measurement_group_id="mg-current", workspace_id="ws-1", method=METHOD_MANUAL, manual_ibase_ka=2.0,
        )
        resolution = resolve_current_base_for_group(_current_group(), config)
        assert convert_current_to_pu(math.nan, "kA", resolution) is None
        assert convert_current_to_pu(None, "kA", resolution) is None
