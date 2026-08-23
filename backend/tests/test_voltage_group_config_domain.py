"""Tests for app.domain.voltage_group_config (Slice 3 of DEC-050): pure
validators, the group-scoped effective-reference resolver, the
corrected voltage PU base resolver, and the value-conversion function --
no registry, no service, no I/O.

The worked numeric examples here are the exact ones from
PER_UNIT_MEASUREMENT_MODEL.md section 8 and this task's own spec: a
nominal 275 kV system's healthy phase-to-ground voltage (~158.77 kV)
must resolve to ~1.0 pu, not the old, incorrect ~0.577 pu.
"""

from __future__ import annotations

import math

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.voltage_group_config import (
    SQRT_3,
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    VOLTAGE_REFERENCE_MODE_AUTO,
    VOLTAGE_REFERENCE_MODE_MANUAL,
    VoltageBaseConfiguration,
    convert_voltage_to_pu,
    resolve_effective_voltage_reference_for_group,
    resolve_voltage_base_for_group,
    voltage_base_valid,
    voltage_reference_mode_valid,
    voltage_reference_value_valid,
)
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE, REASON_MANUAL_OVERRIDE


def _group(group_id="mg-1", kind=KIND_VOLTAGE, status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB")) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id="ws-1", source_id="src-1", kind=kind, display_name="TEST GROUP",
        channel_refs=[ChannelRef(kind="source", source_id="src-1", channel_name=n) for n in channel_names],
        status=status,
    )


def _config(nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO, reference_override=None) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(
        measurement_group_id="mg-1", workspace_id="ws-1", nominal_voltage_ll_kv=nominal_voltage_ll_kv,
        reference_mode=reference_mode, reference_override=reference_override,
    )


class TestValidators:
    def test_voltage_base_valid_accepts_positive_finite(self):
        assert voltage_base_valid(275.0) is True
        assert voltage_base_valid(0.001) is True

    def test_voltage_base_valid_rejects_none_zero_negative_nan_bool(self):
        assert voltage_base_valid(None) is False
        assert voltage_base_valid(0.0) is False
        assert voltage_base_valid(-275.0) is False
        assert voltage_base_valid(float("nan")) is False
        assert voltage_base_valid(float("inf")) is False
        assert voltage_base_valid(True) is False  # bool is technically an int -- must still be rejected

    def test_voltage_reference_mode_valid(self):
        assert voltage_reference_mode_valid("auto") is True
        assert voltage_reference_mode_valid("manual") is True
        assert voltage_reference_mode_valid("bogus") is False

    def test_voltage_reference_value_valid(self):
        assert voltage_reference_value_valid(LINE_TO_GROUND) is True
        assert voltage_reference_value_valid(LINE_TO_LINE) is True
        assert voltage_reference_value_valid("bogus") is False


class TestGroupScopedReferenceResolution:
    """Section 8: detection must run against the GROUP's own channels,
    never a whole source's channel list."""

    def test_auto_mode_detects_from_the_groups_own_channels(self):
        group = _group(channel_names=("NORTH BUS VR", "NORTH BUS VY", "NORTH BUS VB"))
        result = resolve_effective_voltage_reference_for_group(group, None)
        assert result.reference == LINE_TO_GROUND

    def test_two_groups_in_the_same_source_resolve_independently(self):
        # The core Slice 3 requirement (section 8/16): one group's own
        # phase-to-phase channels must never influence another group's
        # own phase-to-ground channels, even in the same source.
        lg_group = _group(group_id="mg-lg", channel_names=("275KV BUS VR", "275KV BUS VY", "275KV BUS VB"))
        ll_group = _group(group_id="mg-ll", channel_names=("132KV BUS VRY", "132KV BUS VYB", "132KV BUS VBR"))
        assert resolve_effective_voltage_reference_for_group(lg_group, None).reference == LINE_TO_GROUND
        assert resolve_effective_voltage_reference_for_group(ll_group, None).reference == LINE_TO_LINE

    def test_manual_mode_never_runs_detection(self):
        group = _group(channel_names=("VRY", "VYB", "VBR"))  # would auto-detect as LL
        config = _config(reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, reference_override=LINE_TO_GROUND)
        result = resolve_effective_voltage_reference_for_group(group, config)
        assert result.reference == LINE_TO_GROUND
        assert result.reason == REASON_MANUAL_OVERRIDE

    def test_auto_mode_ignores_a_stale_reference_override_field(self):
        # Even if reference_override happens to be set, auto mode must
        # never read it -- only reference_mode=="manual" does.
        group = _group(channel_names=("VR", "VY", "VB"))
        config = _config(reference_mode=VOLTAGE_REFERENCE_MODE_AUTO, reference_override=LINE_TO_LINE)
        result = resolve_effective_voltage_reference_for_group(group, config)
        assert result.reference == LINE_TO_GROUND

    def test_conflicting_evidence_within_the_group_is_unresolved(self):
        group = _group(channel_names=("VR", "VAB"))
        result = resolve_effective_voltage_reference_for_group(group, None)
        assert result.reference is None


class TestVoltageBaseResolutionMathematics:
    """The exact worked examples from the task/canonical document."""

    def test_275kv_line_to_ground_resolves_to_approximately_one_pu(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.effective_reference == LINE_TO_GROUND
        expected_denominator = 275.0 / SQRT_3
        assert resolution.denominator_kv == pytest.approx(expected_denominator, rel=1e-9)
        assert resolution.denominator_kv == pytest.approx(158.77, abs=0.01)

        measured_phase_ground_kv = 158.77  # "healthy" phase-ground voltage on a 275 kV system
        pu = convert_voltage_to_pu(measured_phase_ground_kv, "kV", resolution)
        assert pu == pytest.approx(1.0, abs=0.001)

    def test_275kv_line_to_line_resolves_to_exactly_one_pu(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VRY", "VYB", "VBR"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.effective_reference == LINE_TO_LINE
        assert resolution.denominator_kv == pytest.approx(275.0, rel=1e-9)

        pu = convert_voltage_to_pu(275.0, "kV", resolution)
        assert pu == pytest.approx(1.0, abs=1e-9)

    def test_132kv_line_to_ground_resolves_to_approximately_one_pu(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=132.0)
        resolution = resolve_voltage_base_for_group(group, config)
        expected_denominator = 132.0 / SQRT_3
        assert resolution.denominator_kv == pytest.approx(expected_denominator, rel=1e-9)
        assert resolution.denominator_kv == pytest.approx(76.21, abs=0.01)
        pu = convert_voltage_to_pu(expected_denominator, "kV", resolution)
        assert pu == pytest.approx(1.0, abs=1e-9)

    def test_voltage_sag_on_a_line_to_ground_group(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        applicable_phase_base = resolution.denominator_kv
        sagged_measurement = 0.70 * applicable_phase_base
        pu = convert_voltage_to_pu(sagged_measurement, "kV", resolution)
        assert pu == pytest.approx(0.70, abs=1e-9)

    def test_measured_value_in_volts_is_correctly_scaled_against_a_kv_base(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VRY", "VYB", "VBR"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        pu = convert_voltage_to_pu(275_000.0, "V", resolution)  # same 275 kV, expressed in V
        assert pu == pytest.approx(1.0, abs=1e-9)

    def test_two_groups_in_one_source_resolve_independently_275_and_132(self):
        group_275 = _group(group_id="mg-275", status=STATUS_CONFIRMED, channel_names=("275KV BUS VR", "275KV BUS VY", "275KV BUS VB"))
        config_275 = VoltageBaseConfiguration(measurement_group_id="mg-275", workspace_id="ws-1", nominal_voltage_ll_kv=275.0)
        group_132 = _group(group_id="mg-132", status=STATUS_CONFIRMED, channel_names=("132KV BUS VR", "132KV BUS VY", "132KV BUS VB"))
        config_132 = VoltageBaseConfiguration(measurement_group_id="mg-132", workspace_id="ws-1", nominal_voltage_ll_kv=132.0)

        resolution_275 = resolve_voltage_base_for_group(group_275, config_275)
        resolution_132 = resolve_voltage_base_for_group(group_132, config_132)

        assert resolution_275.denominator_kv == pytest.approx(158.77, abs=0.01)
        assert resolution_132.denominator_kv == pytest.approx(76.21, abs=0.01)
        # Neither resolution leaks the other group's own base value.
        assert resolution_275.denominator_kv != resolution_132.denominator_kv

    def test_one_lg_group_and_one_ll_group_in_one_source(self):
        lg_group = _group(group_id="mg-lg", status=STATUS_CONFIRMED, channel_names=("BUS1 VR", "BUS1 VY", "BUS1 VB"))
        lg_config = VoltageBaseConfiguration(measurement_group_id="mg-lg", workspace_id="ws-1", nominal_voltage_ll_kv=275.0)
        ll_group = _group(group_id="mg-ll", status=STATUS_CONFIRMED, channel_names=("BUS2 VRY", "BUS2 VYB", "BUS2 VBR"))
        ll_config = VoltageBaseConfiguration(measurement_group_id="mg-ll", workspace_id="ws-1", nominal_voltage_ll_kv=275.0)

        lg_resolution = resolve_voltage_base_for_group(lg_group, lg_config)
        ll_resolution = resolve_voltage_base_for_group(ll_group, ll_config)

        assert lg_resolution.effective_reference == LINE_TO_GROUND
        assert lg_resolution.denominator_kv == pytest.approx(158.77, abs=0.01)
        assert ll_resolution.effective_reference == LINE_TO_LINE
        assert ll_resolution.denominator_kv == pytest.approx(275.0, abs=1e-9)


class TestManualOverrideChangesTheDenominator:
    def test_auto_lg_then_manual_ll_changes_the_denominator(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))  # auto-detects LG
        auto_config = _config(nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO)
        auto_resolution = resolve_voltage_base_for_group(group, auto_config)
        assert auto_resolution.effective_reference == LINE_TO_GROUND
        assert auto_resolution.denominator_kv == pytest.approx(158.77, abs=0.01)

        manual_config = _config(nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, reference_override=LINE_TO_LINE)
        manual_resolution = resolve_voltage_base_for_group(group, manual_config)
        assert manual_resolution.effective_reference == LINE_TO_LINE
        assert manual_resolution.denominator_kv == pytest.approx(275.0, abs=1e-9)

    def test_return_to_auto_restores_the_detected_behaviour(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        # Simulate "Return to Auto": reference_mode flipped back, override cleared.
        restored_config = _config(nominal_voltage_ll_kv=275.0, reference_mode=VOLTAGE_REFERENCE_MODE_AUTO, reference_override=None)
        resolution = resolve_voltage_base_for_group(group, restored_config)
        assert resolution.effective_reference == LINE_TO_GROUND
        assert resolution.denominator_kv == pytest.approx(158.77, abs=0.01)


class TestAuthoritativeStatusGate:
    """Section 9/25: only confirmed/manual groups may resolve a real
    denominator -- suggested/needs_review must never silently become
    authoritative for PU conversion."""

    def test_suggested_group_is_base_required_even_with_a_valid_configuration(self):
        group = _group(status=STATUS_SUGGESTED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "group_not_confirmed"
        assert resolution.denominator_kv is None

    def test_needs_review_group_is_base_required_even_with_a_valid_configuration(self):
        group = _group(status=STATUS_NEEDS_REVIEW, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "group_not_confirmed"

    def test_confirmed_group_resolves(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        assert resolve_voltage_base_for_group(group, config).status == STATUS_CONFIGURED

    def test_manual_group_resolves(self):
        group = _group(status=STATUS_MANUAL, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=275.0)
        assert resolve_voltage_base_for_group(group, config).status == STATUS_CONFIGURED


class TestNotApplicableAndBaseRequired:
    def test_current_group_is_not_applicable(self):
        group = _group(kind=KIND_CURRENT, status=STATUS_CONFIRMED, channel_names=("IR", "IY", "IB"))
        resolution = resolve_voltage_base_for_group(group, None)
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_unconfigured_group_is_base_required(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        resolution = resolve_voltage_base_for_group(group, None)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_base_not_configured"

    def test_invalid_base_value_is_base_required(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        config = _config(nominal_voltage_ll_kv=None)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_base_not_configured"

    def test_ambiguous_reference_never_silently_resolves_a_denominator(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VAB"))  # conflicting evidence
        config = _config(nominal_voltage_ll_kv=275.0)
        resolution = resolve_voltage_base_for_group(group, config)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_reference_undetermined"
        assert resolution.denominator_kv is None


class TestConvertVoltageToPu:
    def test_returns_none_when_resolution_is_not_configured(self):
        group = _group(status=STATUS_SUGGESTED, channel_names=("VR", "VY", "VB"))
        resolution = resolve_voltage_base_for_group(group, _config(nominal_voltage_ll_kv=275.0))
        assert convert_voltage_to_pu(158.77, "kV", resolution) is None

    def test_returns_none_for_unrecognized_unit(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        resolution = resolve_voltage_base_for_group(group, _config(nominal_voltage_ll_kv=275.0))
        assert convert_voltage_to_pu(158.77, "MW", resolution) is None

    def test_returns_none_for_non_finite_measured_value(self):
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        resolution = resolve_voltage_base_for_group(group, _config(nominal_voltage_ll_kv=275.0))
        assert convert_voltage_to_pu(float("nan"), "kV", resolution) is None
        assert convert_voltage_to_pu(None, "kV", resolution) is None

    def test_never_mutates_the_measured_value_itself(self):
        # The conversion is a pure function -- the same input always
        # produces the same output, and no shared state is written.
        group = _group(status=STATUS_CONFIRMED, channel_names=("VR", "VY", "VB"))
        resolution = resolve_voltage_base_for_group(group, _config(nominal_voltage_ll_kv=275.0))
        measured = 158.77
        first = convert_voltage_to_pu(measured, "kV", resolution)
        second = convert_voltage_to_pu(measured, "kV", resolution)
        assert first == second
        assert measured == 158.77  # untouched
