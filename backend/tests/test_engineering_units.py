"""Tests for app.domain.engineering_units -- the shared engineering-unit
domain layer (owner UAT hardening, 2026-09-12; see
docs/project-memory/ENGINEERING_UNITS.md). Triggered by a real
Overcurrent bug: a 2.4 kA primary current through a 1200:1 CT produced
0.002 A instead of 2.0 A because the kA->A conversion never happened.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_ACTIVE_POWER,
    ENGINEERING_QUANTITY_APPARENT_POWER,
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_FREQUENCY,
    ENGINEERING_QUANTITY_REACTIVE_POWER,
    ENGINEERING_QUANTITY_ROCOF,
    ENGINEERING_QUANTITY_UNDEFINED,
    ENGINEERING_QUANTITY_VOLTAGE,
)
from app.domain.engineering_units import (
    CANONICAL_CALCULATION_UNIT,
    NORMALIZATION_ALIAS,
    NORMALIZATION_EXACT,
    NORMALIZATION_UNSUPPORTED,
    convert_array_to_canonical,
    convert_value_to_canonical,
    parse_engineering_unit,
    scale_to_canonical,
)


class TestCanonicalCalculationUnits:
    def test_expected_canonical_units(self):
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_VOLTAGE] == "V"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_CURRENT] == "A"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_ACTIVE_POWER] == "W"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_REACTIVE_POWER] == "var"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_APPARENT_POWER] == "VA"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_FREQUENCY] == "Hz"
        assert CANONICAL_CALCULATION_UNIT[ENGINEERING_QUANTITY_ROCOF] == "Hz/s"

    def test_undefined_quantity_has_no_canonical_unit(self):
        assert ENGINEERING_QUANTITY_UNDEFINED not in CANONICAL_CALCULATION_UNIT


class TestParseEngineeringUnitStatusClassification:
    def test_exact_match_needs_no_correction(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "kA")
        assert parsed.normalization_status == NORMALIZATION_EXACT
        assert parsed.canonical_unit == "kA"
        assert parsed.scale_to_canonical == pytest.approx(1000.0)

    def test_case_variant_is_normalized_alias(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "KA")
        assert parsed.normalization_status == NORMALIZATION_ALIAS
        assert parsed.canonical_unit == "kA"
        assert parsed.scale_to_canonical == pytest.approx(1000.0)

    def test_unsupported_unit_returns_none_scale(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "furlongs")
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED
        assert parsed.canonical_unit is None
        assert parsed.scale_to_canonical is None

    def test_blank_unit_is_unsupported_never_assumed(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "")
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED

    def test_none_unit_is_unsupported_never_assumed(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, None)
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED

    def test_whitespace_only_unit_is_unsupported(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "   ")
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED

    def test_leading_trailing_spaces_are_stripped(self):
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "  kA  ")
        assert parsed.normalization_status == NORMALIZATION_EXACT
        assert parsed.scale_to_canonical == pytest.approx(1000.0)

    def test_unrecognized_quantity_is_unsupported(self):
        parsed = parse_engineering_unit("Impedance", "ohm")
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED
        assert parsed.canonical_calculation_unit is None

    def test_quantity_unit_mismatch_is_unsupported(self):
        """A Voltage-family unit passed for the Current quantity is
        never accepted -- quantity and unit must agree."""
        parsed = parse_engineering_unit(ENGINEERING_QUANTITY_CURRENT, "kV")
        assert parsed.normalization_status == NORMALIZATION_UNSUPPORTED


class TestUnitNormalizationMatrix:
    @pytest.mark.parametrize("unit,expected_scale", [("A", 1.0), ("a", 1.0), ("kA", 1000.0), ("KA", 1000.0), ("ka", 1000.0)])
    def test_current(self, unit, expected_scale):
        assert scale_to_canonical(ENGINEERING_QUANTITY_CURRENT, unit) == pytest.approx(expected_scale)

    @pytest.mark.parametrize(
        "unit,expected_scale",
        [("V", 1.0), ("v", 1.0), ("kV", 1000.0), ("KV", 1000.0), ("kv", 1000.0), ("MV", 1_000_000.0)],
    )
    def test_voltage(self, unit, expected_scale):
        assert scale_to_canonical(ENGINEERING_QUANTITY_VOLTAGE, unit) == pytest.approx(expected_scale)

    @pytest.mark.parametrize(
        "unit,expected_scale",
        [
            ("W", 1.0), ("w", 1.0),
            ("kW", 1_000.0), ("KW", 1_000.0), ("kw", 1_000.0),
            ("MW", 1_000_000.0), ("Mw", 1_000_000.0), ("mw", 1_000_000.0),
            ("GW", 1_000_000_000.0), ("Gw", 1_000_000_000.0), ("gw", 1_000_000_000.0),
        ],
    )
    def test_active_power(self, unit, expected_scale):
        assert scale_to_canonical(ENGINEERING_QUANTITY_ACTIVE_POWER, unit) == pytest.approx(expected_scale)

    @pytest.mark.parametrize(
        "unit,expected_scale",
        [
            ("var", 1.0), ("VAR", 1.0), ("Var", 1.0),
            ("kvar", 1_000.0), ("kVAR", 1_000.0), ("KVAR", 1_000.0),
            ("Mvar", 1_000_000.0), ("MVAR", 1_000_000.0), ("mvar", 1_000_000.0),
            ("Gvar", 1_000_000_000.0), ("GVAR", 1_000_000_000.0),
        ],
    )
    def test_reactive_power(self, unit, expected_scale):
        assert scale_to_canonical(ENGINEERING_QUANTITY_REACTIVE_POWER, unit) == pytest.approx(expected_scale)

    @pytest.mark.parametrize(
        "unit,expected_scale",
        [
            ("VA", 1.0), ("va", 1.0),
            ("kVA", 1_000.0), ("KVA", 1_000.0), ("kva", 1_000.0),
            ("MVA", 1_000_000.0), ("Mva", 1_000_000.0), ("mva", 1_000_000.0),
            ("GVA", 1_000_000_000.0), ("Gva", 1_000_000_000.0), ("gva", 1_000_000_000.0),
        ],
    )
    def test_apparent_power(self, unit, expected_scale):
        assert scale_to_canonical(ENGINEERING_QUANTITY_APPARENT_POWER, unit) == pytest.approx(expected_scale)

    def test_reactive_power_aliases_normalize_to_one_canonical_spelling(self):
        for unit in ("var", "VAR", "Var"):
            assert parse_engineering_unit(ENGINEERING_QUANTITY_REACTIVE_POWER, unit).canonical_unit == "var"
        for unit in ("kvar", "kVAR", "KVAR"):
            assert parse_engineering_unit(ENGINEERING_QUANTITY_REACTIVE_POWER, unit).canonical_unit == "kvar"


class TestScalarConversionGoldenValues:
    """Task's own explicit golden numbers."""

    def test_2_4_kA_to_2400_A(self):
        assert convert_value_to_canonical(2.4, ENGINEERING_QUANTITY_CURRENT, "kA") == pytest.approx(2400.0)

    def test_275_kV_to_275000_V(self):
        assert convert_value_to_canonical(275.0, ENGINEERING_QUANTITY_VOLTAGE, "kV") == pytest.approx(275000.0)

    def test_100_MW_to_1e8_W(self):
        assert convert_value_to_canonical(100.0, ENGINEERING_QUANTITY_ACTIVE_POWER, "MW") == pytest.approx(100_000_000.0)

    def test_35_Mvar_to_3_5e7_var(self):
        assert convert_value_to_canonical(35.0, ENGINEERING_QUANTITY_REACTIVE_POWER, "Mvar") == pytest.approx(35_000_000.0)

    def test_120_MVA_to_1_2e8_VA(self):
        assert convert_value_to_canonical(120.0, ENGINEERING_QUANTITY_APPARENT_POWER, "MVA") == pytest.approx(120_000_000.0)

    def test_500_kVA_to_5e5_VA(self):
        assert convert_value_to_canonical(500.0, ENGINEERING_QUANTITY_APPARENT_POWER, "kVA") == pytest.approx(500_000.0)


class TestScalarConversionGuardrails:
    def test_unsupported_unit_returns_none(self):
        assert convert_value_to_canonical(2.4, ENGINEERING_QUANTITY_CURRENT, "furlongs") is None

    def test_blank_unit_returns_none_never_assumes_amperes(self):
        assert convert_value_to_canonical(2.4, ENGINEERING_QUANTITY_CURRENT, "") is None

    def test_none_value_returns_none(self):
        assert convert_value_to_canonical(None, ENGINEERING_QUANTITY_CURRENT, "A") is None

    def test_nan_value_returns_none(self):
        assert convert_value_to_canonical(float("nan"), ENGINEERING_QUANTITY_CURRENT, "A") is None

    def test_infinite_value_returns_none(self):
        assert convert_value_to_canonical(float("inf"), ENGINEERING_QUANTITY_CURRENT, "A") is None

    def test_quantity_unit_mismatch_returns_none(self):
        assert convert_value_to_canonical(2.4, ENGINEERING_QUANTITY_CURRENT, "kV") is None


class TestArrayConversion:
    def test_scales_every_element(self):
        values = np.array([1.0, 2.0, 2.4])
        result = convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "kA")
        np.testing.assert_allclose(result, [1000.0, 2000.0, 2400.0])

    def test_never_mutates_input_array(self):
        values = np.array([1.0, 2.0, 2.4])
        original = values.copy()
        convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "kA")
        np.testing.assert_array_equal(values, original)

    def test_preserves_nan(self):
        values = np.array([1.0, np.nan, 2.4])
        result = convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "kA")
        assert result[0] == pytest.approx(1000.0)
        assert math.isnan(result[1])
        assert result[2] == pytest.approx(2400.0)

    def test_unsupported_unit_returns_none(self):
        values = np.array([1.0, 2.0])
        assert convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "furlongs") is None

    def test_exact_unit_scale_is_one_values_unchanged_but_still_a_copy(self):
        values = np.array([1.0, 2.0, 3.0])
        result = convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "A")
        np.testing.assert_allclose(result, values)
        assert result is not values


class TestArrayConversionGoldenValues:
    def test_current_array_kA_to_A(self):
        values = np.array([0.5, 1.0, 2.4])
        result = convert_array_to_canonical(values, ENGINEERING_QUANTITY_CURRENT, "kA")
        np.testing.assert_allclose(result, [500.0, 1000.0, 2400.0])
