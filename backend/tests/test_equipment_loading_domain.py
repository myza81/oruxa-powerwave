"""Pure tests for app.domain.equipment_loading -- the balanced three-phase
Equipment Loading -> equivalent primary current conversion used by
Overcurrent Manual Input's Equipment Loading input method."""

from __future__ import annotations

import math

import pytest

from app.domain.equipment_loading import (
    actual_loading_mva,
    equipment_loading_to_primary_current,
    positive_finite,
    three_phase_line_current_a,
)


class TestActualLoading:
    def test_percentage_of_rating(self):
        assert actual_loading_mva(141.0, 150.0) == pytest.approx(211.5)
        assert actual_loading_mva(100.0, 100.0) == pytest.approx(100.0)
        assert actual_loading_mva(100.0, 50.0) == pytest.approx(50.0)

    def test_loading_above_100_percent_is_supported(self):
        assert actual_loading_mva(100.0, 250.0) == pytest.approx(250.0)


class TestThreePhaseLineCurrent:
    def test_formula_s_over_root3_v_in_amperes(self):
        # 100 MVA at 132 kV: 100e6 / (sqrt(3) * 132e3) A
        assert three_phase_line_current_a(100.0, 132.0) == pytest.approx(100e6 / (math.sqrt(3) * 132e3), rel=1e-12)

    def test_known_values(self):
        assert three_phase_line_current_a(1000.0, 500.0) == pytest.approx(1154.7005, rel=1e-6)
        assert three_phase_line_current_a(1000.0, 132.0) == pytest.approx(4373.87, rel=1e-5)


class TestReferenceCase:
    """Owner's reference case: 141 MVA, 150 %, 132 kV, CT 800/1 A."""

    def test_141_mva_150_percent_132_kv(self):
        result = equipment_loading_to_primary_current(141.0, 150.0, 132.0)
        assert result.actual_loading_mva == pytest.approx(211.5, rel=1e-12)
        assert result.primary_current_a == pytest.approx(925.07, abs=0.01)
        assert round(result.primary_current_a, 1) == 925.1
        # The CT ratio is NOT applied here (input conversion only); the
        # Overcurrent pipeline applies it. 800/1 gives ~1.156 A secondary.
        assert result.primary_current_a * 1.0 / 800.0 == pytest.approx(1.156, abs=0.0005)

    def test_inputs_are_echoed(self):
        result = equipment_loading_to_primary_current(141.0, 150.0, 132.0)
        assert (result.equipment_rating_mva, result.loading_percent, result.system_voltage_kv) == (141.0, 150.0, 132.0)

    def test_current_scales_linearly_with_loading(self):
        at_100 = equipment_loading_to_primary_current(141.0, 100.0, 132.0).primary_current_a
        at_150 = equipment_loading_to_primary_current(141.0, 150.0, 132.0).primary_current_a
        assert at_150 == pytest.approx(1.5 * at_100, rel=1e-12)


class TestPositiveFinite:
    @pytest.mark.parametrize("value", [0.0, -1.0, -0.001, math.nan, math.inf, -math.inf])
    def test_rejects(self, value):
        assert positive_finite(value) is False

    @pytest.mark.parametrize("value", [1e-9, 1.0, 150.0, 1000.0])
    def test_accepts(self, value):
        assert positive_finite(value) is True
