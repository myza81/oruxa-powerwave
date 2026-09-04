"""Tests for app.domain.channel_classification.classify_analog_channel.

Per the classification governance in that module: an unknown channel must
never be silently forced into an incorrect type.
"""

from __future__ import annotations

import pytest

from app.domain.channel_classification import (
    CURRENT,
    ENGINEERING_QUANTITY_ACTIVE_POWER,
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_FREQUENCY,
    ENGINEERING_QUANTITY_REACTIVE_POWER,
    ENGINEERING_QUANTITY_ROCOF,
    ENGINEERING_QUANTITY_UNDEFINED,
    ENGINEERING_QUANTITY_VOLTAGE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    FREQUENCY,
    KNOWN_ENGINEERING_QUANTITIES,
    POWER,
    ROCOF,
    UNDEFINED,
    VOLTAGE,
    broad_engineering_type,
    canonical_engineering_quantity,
    classify_analog_channel,
    encode_engineering_quantity_and_unit_suffix,
    encode_engineering_quantity_suffix,
    measured_unit_valid_for_quantity,
    parse_engineering_quantity_and_unit_suffix,
    parse_engineering_quantity_suffix,
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

    @pytest.mark.parametrize(
        "parameter_type,expected",
        [
            ("voltage angle", VOLTAGE),
            ("VOLTAGE ANGLE", VOLTAGE),
            ("current angle", CURRENT),
            ("active power", POWER),
            ("reactive power", POWER),
        ],
    )
    def test_richer_engineering_quantity_parameter_types_resolve_broad_type(self, parameter_type, expected):
        # Engineering Quantity enhancement (DEC-077): the richer values
        # the Data Preparation Workspace now writes into parameter_type
        # still resolve via this SAME Tier-1 map, never a second
        # classifier.
        assert classify_analog_channel(parameter_type=parameter_type, unit="Hz") == expected


class TestEngineeringQuantityBroadCompatibilityMapping:
    """DEC-077 task section C/AH: every Engineering Quantity maps to
    exactly one broad engineering_type, and existing plain values are
    completely unaffected."""

    @pytest.mark.parametrize(
        "quantity,expected_broad",
        [
            (ENGINEERING_QUANTITY_VOLTAGE, VOLTAGE),
            (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, VOLTAGE),
            (ENGINEERING_QUANTITY_CURRENT, CURRENT),
            (ENGINEERING_QUANTITY_CURRENT_ANGLE, CURRENT),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, POWER),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, POWER),
            (ENGINEERING_QUANTITY_FREQUENCY, FREQUENCY),
            (ENGINEERING_QUANTITY_ROCOF, ROCOF),
            (ENGINEERING_QUANTITY_UNDEFINED, UNDEFINED),
        ],
    )
    def test_broad_engineering_type_mapping(self, quantity, expected_broad):
        assert broad_engineering_type(quantity) == expected_broad

    def test_unrecognized_quantity_maps_to_undefined_never_raises(self):
        assert broad_engineering_type("Impedance") == UNDEFINED

    def test_known_engineering_quantities_is_the_closed_nine_value_set(self):
        assert set(KNOWN_ENGINEERING_QUANTITIES) == {
            "Voltage", "Voltage Angle", "Current", "Current Angle",
            "Active Power", "Reactive Power", "Frequency", "ROCOF", "Undefined",
        }


class TestCanonicalEngineeringQuantity:
    """DEC-077: the STRICT (not broad-compatibility) lookup that restores
    the rich value itself from AnalogChannel.parameter_type."""

    @pytest.mark.parametrize(
        "parameter_type,expected",
        [
            ("Voltage", ENGINEERING_QUANTITY_VOLTAGE),
            ("voltage", ENGINEERING_QUANTITY_VOLTAGE),
            ("VOLTAGE", ENGINEERING_QUANTITY_VOLTAGE),
            ("Voltage Angle", ENGINEERING_QUANTITY_VOLTAGE_ANGLE),
            ("current angle", ENGINEERING_QUANTITY_CURRENT_ANGLE),
            ("Active Power", ENGINEERING_QUANTITY_ACTIVE_POWER),
            ("Reactive Power", ENGINEERING_QUANTITY_REACTIVE_POWER),
            ("Frequency", ENGINEERING_QUANTITY_FREQUENCY),
            ("ROCOF", ENGINEERING_QUANTITY_ROCOF),
            ("rocof", ENGINEERING_QUANTITY_ROCOF),
        ],
    )
    def test_exact_canonical_quantity_restored(self, parameter_type, expected):
        assert canonical_engineering_quantity(parameter_type) == expected

    def test_none_is_undefined(self):
        assert canonical_engineering_quantity(None) == UNDEFINED

    def test_empty_string_is_undefined(self):
        assert canonical_engineering_quantity("") == UNDEFINED

    @pytest.mark.parametrize("parameter_type", ["mw", "mvar", "unknown", "digital"])
    def test_legacy_broad_only_parameter_types_do_not_restore_a_rich_quantity(self, parameter_type):
        # "mw"/"mvar" resolve a broad Power engineering_type (see
        # TestParameterTypeBasedClassification above) but are NOT
        # themselves one of the nine canonical Engineering Quantity
        # strings -- the richer field stays Undefined for them.
        assert canonical_engineering_quantity(parameter_type) == UNDEFINED


class TestEngineeringQuantitySuffixParser:
    """DEC-077 task sections N-T, AM: the strict, exact-match-only export
    label suffix grammar."""

    @pytest.mark.parametrize(
        "label,expected_base,expected_quantity",
        [
            ("CBDK_V1 Magnitude (Voltage)", "CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE),
            ("CBDK_V1 Angle (Voltage Angle)", "CBDK_V1 Angle", ENGINEERING_QUANTITY_VOLTAGE_ANGLE),
            ("CBDK_I1 Magnitude (Current)", "CBDK_I1 Magnitude", ENGINEERING_QUANTITY_CURRENT),
            ("CBDK_I1 Angle (Current Angle)", "CBDK_I1 Angle", ENGINEERING_QUANTITY_CURRENT_ANGLE),
            ("P (Active Power)", "P", ENGINEERING_QUANTITY_ACTIVE_POWER),
            ("Q (Reactive Power)", "Q", ENGINEERING_QUANTITY_REACTIVE_POWER),
            ("System Frequency (Frequency)", "System Frequency", ENGINEERING_QUANTITY_FREQUENCY),
            ("df/dt (ROCOF)", "df/dt", ENGINEERING_QUANTITY_ROCOF),
            ("Voltage Sensor (voltage)", "Voltage Sensor", ENGINEERING_QUANTITY_VOLTAGE),  # case-insensitive
        ],
    )
    def test_recognized_suffix_parses(self, label, expected_base, expected_quantity):
        assert parse_engineering_quantity_suffix(label) == (expected_base, expected_quantity)

    @pytest.mark.parametrize(
        "label",
        [
            "Time (s)",  # task section T: never confused with Configured Time's own suffix
            "Voltage Sensor",  # no parenthesis at all
            "Voltage Sensor (Undefined)",  # Undefined is never a valid suffix to restore
            "Angle Sensor",
            "Current Status",
            "Power Quality",
            "Phase A",
            "Line 1 (North)",  # unrelated parenthetical content
            "V1",
            "I1",
        ],
    )
    def test_unrecognized_or_absent_suffix_leaves_label_unchanged(self, label):
        assert parse_engineering_quantity_suffix(label) == (label, None)


class TestEngineeringQuantitySuffixEncoder:
    """DEC-077 task sections N/O/P: the exporter's own inverse operation."""

    def test_known_quantity_appends_suffix(self):
        assert encode_engineering_quantity_suffix("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE) == (
            "CBDK_V1 Magnitude (Voltage)"
        )

    def test_undefined_leaves_label_unchanged_no_noisy_suffix(self):
        assert encode_engineering_quantity_suffix("ABC", ENGINEERING_QUANTITY_UNDEFINED) == "ABC"

    def test_unrecognized_quantity_string_leaves_label_unchanged(self):
        assert encode_engineering_quantity_suffix("ABC", "Impedance") == "ABC"

    def test_reexporting_an_already_suffixed_label_does_not_duplicate(self):
        once = encode_engineering_quantity_suffix("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE)
        twice = encode_engineering_quantity_suffix(once, ENGINEERING_QUANTITY_VOLTAGE)
        assert once == "CBDK_V1 Magnitude (Voltage)"
        assert twice == "CBDK_V1 Magnitude (Voltage)"

    def test_round_trip_stable_through_parse_and_encode(self):
        exported = encode_engineering_quantity_suffix("df/dt", ENGINEERING_QUANTITY_ROCOF)
        base, restored_quantity = parse_engineering_quantity_suffix(exported)
        re_exported = encode_engineering_quantity_suffix(base, restored_quantity)
        assert exported == re_exported == "df/dt (ROCOF)"
        assert classify_analog_channel(parameter_type="", unit="") == UNDEFINED


class TestMeasuredUnitValidation:
    """Measured Unit enhancement (DEC-080), task section AG: the closed,
    quantity-dependent controlled unit list."""

    @pytest.mark.parametrize(
        "quantity,unit",
        [
            (ENGINEERING_QUANTITY_VOLTAGE, "V"),
            (ENGINEERING_QUANTITY_VOLTAGE, "kV"),
            (ENGINEERING_QUANTITY_CURRENT, "A"),
            (ENGINEERING_QUANTITY_CURRENT, "kA"),
            (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, "deg"),
            (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, "rad"),
            (ENGINEERING_QUANTITY_CURRENT_ANGLE, "deg"),
            (ENGINEERING_QUANTITY_CURRENT_ANGLE, "rad"),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, "W"),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, "kW"),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, "MW"),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, "GW"),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, "var"),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, "kvar"),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, "Mvar"),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, "Gvar"),
            (ENGINEERING_QUANTITY_FREQUENCY, "Hz"),
            (ENGINEERING_QUANTITY_ROCOF, "Hz/s"),
        ],
    )
    def test_valid_quantity_unit_pairs(self, quantity, unit):
        assert measured_unit_valid_for_quantity(quantity, unit) is True

    @pytest.mark.parametrize(
        "quantity,unit",
        [
            (ENGINEERING_QUANTITY_VOLTAGE, "MW"),
            (ENGINEERING_QUANTITY_CURRENT, "kV"),
            (ENGINEERING_QUANTITY_FREQUENCY, "A"),
            (ENGINEERING_QUANTITY_ROCOF, "Hz"),
            (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, "kV"),
            (ENGINEERING_QUANTITY_ACTIVE_POWER, "Mvar"),
            (ENGINEERING_QUANTITY_REACTIVE_POWER, "MW"),
        ],
    )
    def test_invalid_quantity_unit_pairs(self, quantity, unit):
        assert measured_unit_valid_for_quantity(quantity, unit) is False

    @pytest.mark.parametrize(
        "quantity",
        list(KNOWN_ENGINEERING_QUANTITIES),
    )
    def test_blank_is_always_valid(self, quantity):
        assert measured_unit_valid_for_quantity(quantity, "") is True

    def test_undefined_quantity_only_accepts_blank(self):
        assert measured_unit_valid_for_quantity(ENGINEERING_QUANTITY_UNDEFINED, "") is True
        assert measured_unit_valid_for_quantity(ENGINEERING_QUANTITY_UNDEFINED, "V") is False

    def test_unrecognized_quantity_only_accepts_blank(self):
        assert measured_unit_valid_for_quantity("Impedance", "") is True
        assert measured_unit_valid_for_quantity("Impedance", "ohm") is False


class TestEngineeringQuantityAndUnitSuffixParser:
    """Measured Unit enhancement (DEC-080), task sections S/T/AQ/AR: the
    combined quantity+unit grammar, with quantity-only backward
    compatibility."""

    @pytest.mark.parametrize(
        "label,expected_base,expected_quantity,expected_unit",
        [
            ("CBDK_V1 Magnitude (Voltage) [kV]", "CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE, "kV"),
            ("CBDK_V1 Angle (Voltage Angle) [deg]", "CBDK_V1 Angle", ENGINEERING_QUANTITY_VOLTAGE_ANGLE, "deg"),
            ("CBDK_I1 Magnitude (Current) [A]", "CBDK_I1 Magnitude", ENGINEERING_QUANTITY_CURRENT, "A"),
            ("CBDK_I1 Angle (Current Angle) [deg]", "CBDK_I1 Angle", ENGINEERING_QUANTITY_CURRENT_ANGLE, "deg"),
            ("P (Active Power) [MW]", "P", ENGINEERING_QUANTITY_ACTIVE_POWER, "MW"),
            ("Q (Reactive Power) [Mvar]", "Q", ENGINEERING_QUANTITY_REACTIVE_POWER, "Mvar"),
            ("System Frequency (Frequency) [Hz]", "System Frequency", ENGINEERING_QUANTITY_FREQUENCY, "Hz"),
            ("df/dt (ROCOF) [Hz/s]", "df/dt", ENGINEERING_QUANTITY_ROCOF, "Hz/s"),
            # case-insensitive parse, canonical-cased result (task section S)
            ("VA (voltage) [kv]", "VA", ENGINEERING_QUANTITY_VOLTAGE, "kV"),
        ],
    )
    def test_recognized_quantity_and_unit_suffix_parses(self, label, expected_base, expected_quantity, expected_unit):
        assert parse_engineering_quantity_and_unit_suffix(label) == (expected_base, expected_quantity, expected_unit)

    def test_backward_compatible_quantity_only_suffix(self):
        """DEC-077 files with no unit suffix at all (task section T/AR)."""
        assert parse_engineering_quantity_and_unit_suffix("VA (Voltage)") == ("VA", ENGINEERING_QUANTITY_VOLTAGE, None)

    @pytest.mark.parametrize(
        "label",
        [
            "Time (s)",  # never misinterpreted as a quantity/unit suffix (task section W)
            "Transformer [HV]",  # bare bracket, no quantity parenthesis at all
            "Line (North) [A]",  # not a recognized quantity
            "Voltage [estimated]",  # bare bracket, no quantity parenthesis at all
            "VA (Voltage) [XX]",  # recognized quantity, but XX is not a valid unit for it
            "P (Active Power) [kV]",  # recognized quantity, but kV is invalid for Active Power
        ],
    )
    def test_unrecognized_or_invalid_bracket_never_matches(self, label):
        assert parse_engineering_quantity_and_unit_suffix(label) == (label, None, None)


class TestEngineeringQuantityAndUnitSuffixEncoder:
    """Measured Unit enhancement (DEC-080), task sections P/Q/U/V: the
    exporter's own inverse operation."""

    @pytest.mark.parametrize(
        "label,quantity,unit,expected",
        [
            ("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE, "kV", "CBDK_V1 Magnitude (Voltage) [kV]"),
            ("CBDK_V1 Angle", ENGINEERING_QUANTITY_VOLTAGE_ANGLE, "deg", "CBDK_V1 Angle (Voltage Angle) [deg]"),
            ("CBDK_I1 Magnitude", ENGINEERING_QUANTITY_CURRENT, "A", "CBDK_I1 Magnitude (Current) [A]"),
            ("CBDK_I1 Angle", ENGINEERING_QUANTITY_CURRENT_ANGLE, "deg", "CBDK_I1 Angle (Current Angle) [deg]"),
            ("P", ENGINEERING_QUANTITY_ACTIVE_POWER, "MW", "P (Active Power) [MW]"),
            ("Q", ENGINEERING_QUANTITY_REACTIVE_POWER, "Mvar", "Q (Reactive Power) [Mvar]"),
            ("System Frequency", ENGINEERING_QUANTITY_FREQUENCY, "Hz", "System Frequency (Frequency) [Hz]"),
            ("df/dt", ENGINEERING_QUANTITY_ROCOF, "Hz/s", "df/dt (ROCOF) [Hz/s]"),
        ],
    )
    def test_known_quantity_and_unit_appends_full_suffix(self, label, quantity, unit, expected):
        assert encode_engineering_quantity_and_unit_suffix(label, quantity, unit) == expected

    def test_blank_unit_omits_bracket_never_appends_empty_brackets(self):
        assert (
            encode_engineering_quantity_and_unit_suffix("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE, "")
            == "CBDK_V1 Magnitude (Voltage)"
        )
        assert (
            encode_engineering_quantity_and_unit_suffix("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE, None)
            == "CBDK_V1 Magnitude (Voltage)"
        )

    def test_undefined_quantity_and_blank_unit_leaves_label_unchanged(self):
        assert encode_engineering_quantity_and_unit_suffix("ABC", ENGINEERING_QUANTITY_UNDEFINED, "") == "ABC"

    def test_reexporting_an_already_suffixed_label_does_not_duplicate(self):
        once = encode_engineering_quantity_and_unit_suffix("CBDK_V1 Magnitude", ENGINEERING_QUANTITY_VOLTAGE, "kV")
        twice = encode_engineering_quantity_and_unit_suffix(once, ENGINEERING_QUANTITY_VOLTAGE, "kV")
        assert once == "CBDK_V1 Magnitude (Voltage) [kV]"
        assert twice == "CBDK_V1 Magnitude (Voltage) [kV]"
        assert "[kV] [kV]" not in twice
        assert "(Voltage) (Voltage)" not in twice

    def test_round_trip_stable_export_reupload_reexport(self):
        exported = encode_engineering_quantity_and_unit_suffix("VA", ENGINEERING_QUANTITY_VOLTAGE, "kV")
        base, restored_quantity, restored_unit = parse_engineering_quantity_and_unit_suffix(exported)
        re_exported = encode_engineering_quantity_and_unit_suffix(base, restored_quantity, restored_unit)
        assert exported == re_exported == "VA (Voltage) [kV]"

    def test_backward_compatible_quantity_only_round_trip_stays_quantity_only(self):
        """A DEC-077-only export (no unit) with a still-blank unit
        re-exports identically, never gaining a spurious bracket (task
        section AR)."""
        exported = encode_engineering_quantity_and_unit_suffix("VA", ENGINEERING_QUANTITY_VOLTAGE, None)
        assert exported == "VA (Voltage)"
        base, restored_quantity, restored_unit = parse_engineering_quantity_and_unit_suffix(exported)
        assert restored_unit is None
        re_exported = encode_engineering_quantity_and_unit_suffix(base, restored_quantity, restored_unit)
        assert re_exported == "VA (Voltage)"
