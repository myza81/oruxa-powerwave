"""Unit tests for app.domain.per_unit's pure functions (Phase 5C,
DEC-049; source-bound redesign following owner UAT): base validators,
voltage/current base derivation (including the Sbase/Vbase_LL current-
base formula and its live voltage-reference dependency), the per-channel
eligibility+resolution decision, value/array conversion, and the
calculated-channel per-unit-profile inheritance rule (decision 6,
unchanged by this redesign).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.calculated_channel import (
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
)
from app.domain.channel_classification import CURRENT, FREQUENCY, VOLTAGE
from app.domain.per_unit import (
    CURRENT_BASE_MODE_DERIVED,
    CURRENT_BASE_MODE_DIRECT,
    CURRENT_BASE_MODE_NONE,
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    VOLTAGE_REFERENCE_MODE_AUTO,
    VOLTAGE_REFERENCE_MODE_MANUAL,
    PerUnitBaseProfile,
    apparent_power_base_valid,
    apply_per_unit_to_array,
    apply_per_unit_to_value,
    convert_array_to_pu,
    convert_value_to_pu,
    derive_per_unit_profile_id,
    direct_current_base_valid,
    resolve_current_base_amps,
    resolve_effective_voltage_reference,
    resolve_per_unit,
    voltage_base_ll_volts,
    voltage_base_valid,
    voltage_base_volts,
)
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE, REASON_MANUAL_OVERRIDE


def _profile(**overrides) -> PerUnitBaseProfile:
    defaults = dict(
        source_id="src-1",
        workspace_id="ws-1",
        voltage_base_value=None,
        voltage_reference_mode=VOLTAGE_REFERENCE_MODE_AUTO,
        voltage_reference_override=None,
        apparent_power_base_value=None,
        current_base_mode=CURRENT_BASE_MODE_NONE,
        direct_current_base_value=None,
    )
    defaults.update(overrides)
    return PerUnitBaseProfile(**defaults)


class TestValidators:
    def test_voltage_base_valid_accepts_positive_finite_canonical_kv(self):
        assert voltage_base_valid(275.0) is True

    def test_voltage_base_valid_rejects_missing_or_bad_values(self):
        assert voltage_base_valid(None) is False
        assert voltage_base_valid(0.0) is False
        assert voltage_base_valid(-1.0) is False
        assert voltage_base_valid(float("nan")) is False
        assert voltage_base_valid(True) is False  # bool must never pass as a number

    def test_apparent_power_base_valid(self):
        assert apparent_power_base_valid(500.0) is True
        assert apparent_power_base_valid(None) is False

    def test_direct_current_base_valid(self):
        assert direct_current_base_valid(1.2) is True
        assert direct_current_base_valid(-1.0) is False


class TestVoltageBaseVolts:
    def test_converts_canonical_kv_to_volts(self):
        profile = _profile(voltage_base_value=275.0)
        assert voltage_base_volts(profile) == pytest.approx(275_000.0)

    def test_none_when_not_configured(self):
        assert voltage_base_volts(_profile()) is None


class TestResolveEffectiveVoltageReference:
    def test_manual_mode_returns_the_override_verbatim(self):
        profile = _profile(voltage_reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, voltage_reference_override=LINE_TO_LINE)
        detection = resolve_effective_voltage_reference(profile, ["VR", "VY", "VB"])  # would auto-detect LG
        assert detection.reference == LINE_TO_LINE
        assert detection.reason == REASON_MANUAL_OVERRIDE
        assert detection.evidence_names == []

    def test_auto_mode_reruns_detection_from_current_channel_names(self):
        profile = _profile(voltage_reference_mode=VOLTAGE_REFERENCE_MODE_AUTO)
        detection = resolve_effective_voltage_reference(profile, ["VRY", "VYB", "VBR"])
        assert detection.reference == LINE_TO_LINE

    def test_none_profile_behaves_like_auto_mode(self):
        detection = resolve_effective_voltage_reference(None, ["VA", "VB", "VC"])
        assert detection.reference == LINE_TO_GROUND


class TestVoltageBaseLLVolts:
    def test_line_to_line_reference_is_unchanged(self):
        profile = _profile(voltage_base_value=275.0)
        assert voltage_base_ll_volts(profile, LINE_TO_LINE) == pytest.approx(275_000.0)

    def test_line_to_ground_reference_is_normalized_by_sqrt_3(self):
        profile = _profile(voltage_base_value=100.0)
        assert voltage_base_ll_volts(profile, LINE_TO_GROUND) == pytest.approx(100_000.0 * 1.7320508075688772)

    def test_unresolved_reference_never_applies_sqrt_3_unconfirmed(self):
        # resolve_current_base_amps() already gates on a KNOWN reference
        # before ever calling this -- but as a defense-in-depth default,
        # an unconfirmed reference must never silently apply sqrt(3).
        profile = _profile(voltage_base_value=100.0)
        assert voltage_base_ll_volts(profile, None) == pytest.approx(100_000.0)


class TestResolveCurrentBaseAmps:
    def test_none_mode_is_unconfigured(self):
        amps, reason = resolve_current_base_amps(_profile(current_base_mode=CURRENT_BASE_MODE_NONE), LINE_TO_LINE)
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_direct_mode_reads_canonical_ka(self):
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DIRECT, direct_current_base_value=1.5)
        amps, reason = resolve_current_base_amps(profile, None)  # reference irrelevant for direct mode
        assert amps == pytest.approx(1500.0)
        assert reason is None

    def test_direct_mode_unconfigured_without_valid_value(self):
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DIRECT)
        amps, reason = resolve_current_base_amps(profile, LINE_TO_LINE)
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_derived_mode_requires_a_resolved_voltage_reference(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=275.0, apparent_power_base_value=500.0,
        )
        amps, reason = resolve_current_base_amps(profile, None)  # ambiguous/undetermined reference
        assert amps is None
        assert reason == "voltage_reference_undetermined"

    def test_derived_mode_requires_both_vbase_and_sbase(self):
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0)
        amps, reason = resolve_current_base_amps(profile, LINE_TO_LINE)
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_derived_mode_computes_ibase_from_sbase_and_vbase_ll(self):
        # Ibase = Sbase / (sqrt(3) * Vbase_LL) -- the proven, unchanged formula.
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0, apparent_power_base_value=500.0)
        amps, reason = resolve_current_base_amps(profile, LINE_TO_LINE)
        assert reason is None
        expected = 500_000_000.0 / (1.7320508075688772 * 275_000.0)
        assert amps == pytest.approx(expected)

    def test_derived_mode_normalizes_line_to_ground_vbase_first(self):
        lg_profile = _profile(current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=100.0, apparent_power_base_value=500.0)
        ll_profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=100.0 * 1.7320508075688772, apparent_power_base_value=500.0,
        )
        lg_amps, _ = resolve_current_base_amps(lg_profile, LINE_TO_GROUND)
        ll_amps, _ = resolve_current_base_amps(ll_profile, LINE_TO_LINE)
        assert lg_amps == pytest.approx(ll_amps)


class TestResolvePerUnit:
    def test_non_voltage_current_type_is_not_applicable(self):
        resolution = resolve_per_unit(FREQUENCY, _profile(voltage_base_value=275.0))
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_no_configuration_is_base_required(self):
        resolution = resolve_per_unit(VOLTAGE, None)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "not_configured"

    def test_voltage_without_base_is_base_required(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_base_not_configured"

    def test_voltage_with_base_is_configured(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(275_000.0)
        assert resolution.base_unit == "V"
        assert resolution.profile_id == "src-1"

    def test_current_with_derived_base_and_detectable_reference_is_configured(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0, apparent_power_base_value=500.0,
        )
        resolution = resolve_per_unit(CURRENT, profile, voltage_channel_names=["VAB", "VBC", "VCA"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_unit == "A"

    def test_current_with_derived_base_and_undetectable_reference_is_base_required(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0, apparent_power_base_value=500.0,
        )
        resolution = resolve_per_unit(CURRENT, profile, voltage_channel_names=["CH1", "CH2"])
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_reference_undetermined"

    def test_current_without_current_base_is_base_required(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(CURRENT, profile, voltage_channel_names=["VA", "VB", "VC"])
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "current_base_not_configured"


class TestConvertValueToPu:
    def test_direct_division_never_applies_sqrt_3(self):
        # Decision 3: even a line-to-ground-reference source divides a
        # measured voltage directly by its own declared base -- sqrt(3)
        # is only ever used internally to derive Ibase.
        profile = _profile(voltage_base_value=100.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        result = convert_value_to_pu(105_000.0, "V", resolution, VOLTAGE)
        assert result == pytest.approx(1.05)

    def test_scales_measured_unit_before_dividing(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        result = convert_value_to_pu(280.0, "kV", resolution, VOLTAGE)
        assert result == pytest.approx(280.0 / 275.0)

    def test_returns_none_for_unrecognized_measured_unit(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert convert_value_to_pu(280.0, "ohm", resolution, VOLTAGE) is None

    def test_returns_none_when_not_configured(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        assert convert_value_to_pu(280.0, "kV", resolution, VOLTAGE) is None

    def test_returns_none_for_non_finite_value(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert convert_value_to_pu(float("nan"), "kV", resolution, VOLTAGE) is None


class TestConvertArrayToPu:
    def test_converts_array_and_preserves_nan(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        arr = np.array([275.0, 550.0, np.nan])
        out = convert_array_to_pu(arr, "kV", resolution, VOLTAGE)
        assert out[0] == pytest.approx(1.0)
        assert out[1] == pytest.approx(2.0)
        assert np.isnan(out[2])

    def test_returns_none_when_not_configured(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        assert convert_array_to_pu(np.array([1.0, 2.0]), "kV", resolution, VOLTAGE) is None


class TestApplyPerUnitToValue:
    def test_none_resolution_passes_through_unchanged_with_none_status(self):
        value, unit, status = apply_per_unit_to_value(280.0, "kV", VOLTAGE, None)
        assert (value, unit, status) == (280.0, "kV", None)

    def test_configured_converts_and_reports_status(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        value, unit, status = apply_per_unit_to_value(275.0, "kV", VOLTAGE, resolution)
        assert value == pytest.approx(1.0)
        assert unit == "pu"
        assert status == STATUS_CONFIGURED

    def test_base_required_passes_through_engineering_value(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        value, unit, status = apply_per_unit_to_value(280.0, "kV", VOLTAGE, resolution)
        assert (value, unit) == (280.0, "kV")
        assert status == STATUS_BASE_REQUIRED

    def test_configured_but_unrecognized_measured_unit_falls_back_to_base_required(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        value, unit, status = apply_per_unit_to_value(280.0, "ohm", VOLTAGE, resolution)
        assert (value, unit) == (280.0, "ohm")
        assert status == STATUS_BASE_REQUIRED

    def test_not_applicable_passes_through_unchanged(self):
        resolution = resolve_per_unit(FREQUENCY, _profile(voltage_base_value=275.0))
        value, unit, status = apply_per_unit_to_value(50.0, "Hz", FREQUENCY, resolution)
        assert (value, unit) == (50.0, "Hz")
        assert status == STATUS_NOT_APPLICABLE

    def test_cursor_batch_status_is_independent_of_which_cursor_is_present(self):
        # Regression: A/B batch endpoints must report the SAME status
        # for a channel regardless of whether cursor A or B (or neither)
        # actually has a value -- status is derived from the measured
        # unit, never from value presence.
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        _, _, status_with_value = apply_per_unit_to_value(275.0, "kV", VOLTAGE, resolution)
        _, _, status_without_value = apply_per_unit_to_value(None, "kV", VOLTAGE, resolution)
        assert status_with_value == status_without_value == STATUS_CONFIGURED


class TestApplyPerUnitToArray:
    def test_configured_converts_array(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile)
        arr = np.array([275.0, 550.0])
        values, unit, status = apply_per_unit_to_array(arr, "kV", VOLTAGE, resolution)
        assert values[0] == pytest.approx(1.0)
        assert values[1] == pytest.approx(2.0)
        assert unit == "pu"
        assert status == STATUS_CONFIGURED

    def test_base_required_passes_through_original_array(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        arr = np.array([275.0, 550.0])
        values, unit, status = apply_per_unit_to_array(arr, "kV", VOLTAGE, resolution)
        assert values is arr
        assert unit == "kV"
        assert status == STATUS_BASE_REQUIRED


class TestDerivePerUnitProfileId:
    @pytest.mark.parametrize("operation", [OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS])
    def test_unary_operations_inherit_verbatim(self, operation):
        assert derive_per_unit_profile_id(operation, ["src-a"]) == "src-a"

    @pytest.mark.parametrize("operation", [OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS])
    def test_unary_operations_inherit_none_verbatim(self, operation):
        assert derive_per_unit_profile_id(operation, [None]) is None

    def test_addition_inherits_when_all_inputs_match(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["src-a", "src-a"]) == "src-a"

    def test_addition_does_not_inherit_when_inputs_differ(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["src-a", "src-b"]) is None

    def test_addition_does_not_inherit_when_any_input_is_none(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["src-a", None]) is None
        assert derive_per_unit_profile_id(OP_ADDITION, [None, "src-a"]) is None

    def test_subtraction_follows_the_same_rule_as_addition(self):
        assert derive_per_unit_profile_id(OP_SUBTRACTION, ["src-a", "src-a", "src-a"]) == "src-a"
        assert derive_per_unit_profile_id(OP_SUBTRACTION, ["src-a", "src-b"]) is None

    def test_empty_inputs_is_none(self):
        assert derive_per_unit_profile_id(OP_ADDITION, []) is None
        assert derive_per_unit_profile_id(OP_REVERSE_POLARITY, []) is None
