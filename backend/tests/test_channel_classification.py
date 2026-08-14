"""Tests for app.domain.channel_classification.classify_analog_channel.

Per the classification governance in that module: an unknown channel must
never be silently forced into an incorrect type.
"""

from __future__ import annotations

import pytest

from app.domain.channel_classification import (
    CURRENT,
    FREQUENCY,
    POWER,
    ROCOF,
    UNDEFINED,
    VOLTAGE,
    classify_analog_channel,
)


class TestUnitBasedClassification:
    @pytest.mark.parametrize("unit", ["V", "v", "kV", "KV", "mV", "MV"])
    def test_voltage_units(self, unit):
        assert classify_analog_channel(parameter_type=None, unit=unit) == VOLTAGE

    @pytest.mark.parametrize("unit", ["A", "a", "kA", "mA"])
    def test_current_units(self, unit):
        assert classify_analog_channel(parameter_type=None, unit=unit) == CURRENT

    @pytest.mark.parametrize("unit", ["Hz", "HZ", "hz", "kHz"])
    def test_frequency_units(self, unit):
        assert classify_analog_channel(parameter_type=None, unit=unit) == FREQUENCY

    @pytest.mark.parametrize(
        "unit", ["W", "kW", "MW", "VAR", "var", "kVAR", "MVAR", "VA", "kVA", "MVA"]
    )
    def test_power_units_real_reactive_and_apparent(self, unit):
        assert classify_analog_channel(parameter_type=None, unit=unit) == POWER

    def test_case_and_prefix_normalization_do_not_change_category(self):
        # "mV" and "MV" both mean Voltage for classification purposes --
        # this module does not decode the multiplier, only the unit family.
        assert (
            classify_analog_channel(parameter_type=None, unit="mV")
            == classify_analog_channel(parameter_type=None, unit="MV")
            == VOLTAGE
        )


class TestUndefinedFallback:
    @pytest.mark.parametrize(
        "unit",
        [
            None,
            "",
            "   ",
            "Ohm",
            "deg",
            "%",
            "pu",
            "count",
            "VAB",  # not a recognized unit token
        ],
    )
    def test_unrecognized_or_missing_unit_is_undefined(self, unit):
        assert classify_analog_channel(parameter_type=None, unit=unit) == UNDEFINED

    def test_ambiguous_channel_is_never_guessed_into_a_real_category(self):
        """The whole point of this classifier: when in doubt, Undefined."""
        result = classify_analog_channel(parameter_type=None, unit="widgets")
        assert result == UNDEFINED
        assert result != VOLTAGE
        assert result != CURRENT


class TestParameterTypeTakesPriorityOverUnit:
    """Tier 1 (explicit metadata) wins even when it disagrees with tier 2
    (unit) -- explicit classification is more reliable than inference.
    Dormant for COMTRADE today (see the module docstring) but real,
    tested code for Phase 1.5 providers that do set parameter_type.
    """

    @pytest.mark.parametrize(
        "parameter_type,expected",
        [
            ("voltage", VOLTAGE),
            ("VOLTAGE", VOLTAGE),
            ("current", CURRENT),
            ("frequency", FREQUENCY),
            ("rocof", ROCOF),
            ("mw", POWER),
            ("mvar", POWER),
            ("unknown", UNDEFINED),
        ],
    )
    def test_recognized_parameter_type_values(self, parameter_type, expected):
        # Deliberately mismatched unit to prove parameter_type wins.
        assert (
            classify_analog_channel(parameter_type=parameter_type, unit="Hz") == expected
        )

    def test_unrecognized_parameter_type_falls_back_to_unit(self):
        assert (
            classify_analog_channel(parameter_type="digital", unit="V") == VOLTAGE
        )

    def test_no_parameter_type_falls_back_to_unit(self):
        assert classify_analog_channel(parameter_type=None, unit="A") == CURRENT

    def test_neither_signal_present_is_undefined(self):
        assert classify_analog_channel(parameter_type=None, unit=None) == UNDEFINED
        assert classify_analog_channel(parameter_type="", unit="") == UNDEFINED
