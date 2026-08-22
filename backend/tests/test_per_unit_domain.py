"""Unit tests for app.domain.per_unit's pure functions (Phase 5C, DEC-049):
base validators, voltage/current base derivation (including the
Sbase/Vbase_LL current-base formula and its LN->LL sqrt(3) normalization),
the per-channel eligibility+resolution decision, value/array conversion,
and the calculated-channel per-unit-profile inheritance rule (decision 6).
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
    VOLTAGE_BASIS_LINE_TO_LINE,
    VOLTAGE_BASIS_LINE_TO_NEUTRAL,
    PerUnitBaseProfile,
    apparent_power_base_valid,
    apply_per_unit_to_array,
    apply_per_unit_to_value,
    convert_array_to_pu,
    convert_value_to_pu,
    derive_per_unit_profile_id,
    direct_current_base_valid,
    resolve_current_base_amps,
    resolve_per_unit,
    voltage_base_ll_volts,
    voltage_base_valid,
    voltage_base_volts,
)


def _profile(**overrides) -> PerUnitBaseProfile:
    defaults = dict(
        id="pu-1",
        workspace_id="ws-1",
        name="275 kV",
        voltage_base_value=None,
        voltage_base_unit=None,
        voltage_basis=VOLTAGE_BASIS_LINE_TO_LINE,
        apparent_power_base_value=None,
        apparent_power_base_unit=None,
        current_base_mode=CURRENT_BASE_MODE_NONE,
        direct_current_base_value=None,
        direct_current_base_unit=None,
    )
    defaults.update(overrides)
    return PerUnitBaseProfile(**defaults)


class TestValidators:
    def test_voltage_base_valid_accepts_positive_finite_known_unit(self):
        assert voltage_base_valid(275.0, "kV") is True
        assert voltage_base_valid(275.0, "kv") is True

    def test_voltage_base_valid_rejects_missing_or_bad_values(self):
        assert voltage_base_valid(None, "kV") is False
        assert voltage_base_valid(275.0, None) is False
        assert voltage_base_valid(0.0, "kV") is False
        assert voltage_base_valid(-1.0, "kV") is False
        assert voltage_base_valid(float("nan"), "kV") is False
        assert voltage_base_valid(True, "kV") is False  # bool must never pass as a number
        assert voltage_base_valid(275.0, "ohm") is False

    def test_apparent_power_base_valid(self):
        assert apparent_power_base_valid(500.0, "MVA") is True
        assert apparent_power_base_valid(500.0, "kVA") is False  # only MVA is recognized

    def test_direct_current_base_valid(self):
        assert direct_current_base_valid(1.2, "kA") is True
        assert direct_current_base_valid(1.2, "mA") is False


class TestVoltageBaseVolts:
    def test_converts_kv_to_volts(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        assert voltage_base_volts(profile) == pytest.approx(275_000.0)

    def test_none_when_not_configured(self):
        assert voltage_base_volts(_profile()) is None


class TestVoltageBaseLLVolts:
    def test_line_to_line_is_unchanged(self):
        profile = _profile(
            voltage_base_value=275.0, voltage_base_unit="kV", voltage_basis=VOLTAGE_BASIS_LINE_TO_LINE
        )
        assert voltage_base_ll_volts(profile) == pytest.approx(275_000.0)

    def test_line_to_neutral_is_normalized_by_sqrt_3(self):
        profile = _profile(
            voltage_base_value=100.0, voltage_base_unit="kV", voltage_basis=VOLTAGE_BASIS_LINE_TO_NEUTRAL
        )
        assert voltage_base_ll_volts(profile) == pytest.approx(100_000.0 * 1.7320508075688772)


class TestResolveCurrentBaseAmps:
    def test_none_mode_is_unconfigured(self):
        amps, reason = resolve_current_base_amps(_profile(current_base_mode=CURRENT_BASE_MODE_NONE))
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_direct_mode_reads_direct_fields(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DIRECT,
            direct_current_base_value=1.5, direct_current_base_unit="kA",
        )
        amps, reason = resolve_current_base_amps(profile)
        assert amps == pytest.approx(1500.0)
        assert reason is None

    def test_direct_mode_unconfigured_without_valid_fields(self):
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DIRECT)
        amps, reason = resolve_current_base_amps(profile)
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_derived_mode_requires_both_vbase_and_sbase(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=275.0, voltage_base_unit="kV",
        )
        amps, reason = resolve_current_base_amps(profile)
        assert amps is None
        assert reason == "current_base_not_configured"

    def test_derived_mode_computes_ibase_from_sbase_and_vbase_ll(self):
        # Ibase = Sbase / (sqrt(3) * Vbase_LL) -- section 16's own formula.
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=275.0, voltage_base_unit="kV", voltage_basis=VOLTAGE_BASIS_LINE_TO_LINE,
            apparent_power_base_value=500.0, apparent_power_base_unit="MVA",
        )
        amps, reason = resolve_current_base_amps(profile)
        assert reason is None
        expected = 500_000_000.0 / (1.7320508075688772 * 275_000.0)
        assert amps == pytest.approx(expected)

    def test_derived_mode_normalizes_line_to_neutral_vbase_first(self):
        ln_profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=100.0, voltage_base_unit="kV", voltage_basis=VOLTAGE_BASIS_LINE_TO_NEUTRAL,
            apparent_power_base_value=500.0, apparent_power_base_unit="MVA",
        )
        ll_profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=100.0 * 1.7320508075688772, voltage_base_unit="kV",
            voltage_basis=VOLTAGE_BASIS_LINE_TO_LINE,
            apparent_power_base_value=500.0, apparent_power_base_unit="MVA",
        )
        ln_amps, _ = resolve_current_base_amps(ln_profile)
        ll_amps, _ = resolve_current_base_amps(ll_profile)
        assert ln_amps == pytest.approx(ll_amps)


class TestResolvePerUnit:
    def test_non_voltage_current_type_is_not_applicable(self):
        resolution = resolve_per_unit(FREQUENCY, _profile(voltage_base_value=275.0, voltage_base_unit="kV"))
        assert resolution.status == STATUS_NOT_APPLICABLE

    def test_no_profile_is_base_required(self):
        resolution = resolve_per_unit(VOLTAGE, None)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "no_profile_assigned"

    def test_voltage_profile_without_voltage_base_is_base_required(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_base_not_configured"

    def test_voltage_profile_with_base_is_configured(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(275_000.0)
        assert resolution.base_unit == "V"
        assert resolution.profile_id == "pu-1"

    def test_current_profile_with_derived_base_is_configured(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED,
            voltage_base_value=275.0, voltage_base_unit="kV",
            apparent_power_base_value=500.0, apparent_power_base_unit="MVA",
        )
        resolution = resolve_per_unit(CURRENT, profile)
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_unit == "A"

    def test_current_profile_without_current_base_is_base_required(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(CURRENT, profile)
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "current_base_not_configured"


class TestConvertValueToPu:
    def test_direct_division_never_applies_sqrt_3(self):
        # Decision 3: even a line-to-neutral-basis profile divides a
        # measured voltage directly by its own declared base -- sqrt(3)
        # is only ever used internally to derive Ibase.
        profile = _profile(
            voltage_base_value=100.0, voltage_base_unit="kV", voltage_basis=VOLTAGE_BASIS_LINE_TO_NEUTRAL
        )
        resolution = resolve_per_unit(VOLTAGE, profile)
        result = convert_value_to_pu(105_000.0, "V", resolution, VOLTAGE)
        assert result == pytest.approx(1.05)

    def test_scales_measured_unit_before_dividing(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(VOLTAGE, profile)
        result = convert_value_to_pu(280.0, "kV", resolution, VOLTAGE)
        assert result == pytest.approx(280.0 / 275.0)

    def test_returns_none_for_unrecognized_measured_unit(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert convert_value_to_pu(280.0, "ohm", resolution, VOLTAGE) is None

    def test_returns_none_when_not_configured(self):
        resolution = resolve_per_unit(VOLTAGE, _profile())
        assert convert_value_to_pu(280.0, "kV", resolution, VOLTAGE) is None

    def test_returns_none_for_non_finite_value(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(VOLTAGE, profile)
        assert convert_value_to_pu(float("nan"), "kV", resolution, VOLTAGE) is None


class TestConvertArrayToPu:
    def test_converts_array_and_preserves_nan(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
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
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
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
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
        resolution = resolve_per_unit(VOLTAGE, profile)
        value, unit, status = apply_per_unit_to_value(280.0, "ohm", VOLTAGE, resolution)
        assert (value, unit) == (280.0, "ohm")
        assert status == STATUS_BASE_REQUIRED

    def test_not_applicable_passes_through_unchanged(self):
        resolution = resolve_per_unit(FREQUENCY, _profile(voltage_base_value=275.0, voltage_base_unit="kV"))
        value, unit, status = apply_per_unit_to_value(50.0, "Hz", FREQUENCY, resolution)
        assert (value, unit) == (50.0, "Hz")
        assert status == STATUS_NOT_APPLICABLE


class TestApplyPerUnitToArray:
    def test_configured_converts_array(self):
        profile = _profile(voltage_base_value=275.0, voltage_base_unit="kV")
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
        assert derive_per_unit_profile_id(operation, ["profile-a"]) == "profile-a"

    @pytest.mark.parametrize("operation", [OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS])
    def test_unary_operations_inherit_none_verbatim(self, operation):
        assert derive_per_unit_profile_id(operation, [None]) is None

    def test_addition_inherits_when_all_inputs_match(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["profile-a", "profile-a"]) == "profile-a"

    def test_addition_does_not_inherit_when_inputs_differ(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["profile-a", "profile-b"]) is None

    def test_addition_does_not_inherit_when_any_input_is_none(self):
        assert derive_per_unit_profile_id(OP_ADDITION, ["profile-a", None]) is None
        assert derive_per_unit_profile_id(OP_ADDITION, [None, "profile-a"]) is None

    def test_subtraction_follows_the_same_rule_as_addition(self):
        assert derive_per_unit_profile_id(OP_SUBTRACTION, ["profile-a", "profile-a", "profile-a"]) == "profile-a"
        assert derive_per_unit_profile_id(OP_SUBTRACTION, ["profile-a", "profile-b"]) is None

    def test_empty_inputs_is_none(self):
        assert derive_per_unit_profile_id(OP_ADDITION, []) is None
        assert derive_per_unit_profile_id(OP_REVERSE_POLARITY, []) is None
