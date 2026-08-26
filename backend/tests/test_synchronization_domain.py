"""Pure domain tests for app.domain.synchronization (Slice 1 of waveform
time synchronization)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.domain.synchronization import (
    alignment_offset_valid,
    reference_source_id_for_workspace,
    source_time_to_workspace_time,
    workspace_time_to_source_time,
)


class TestScalarConversion:
    def test_positive_offset(self):
        assert source_time_to_workspace_time(1.0, 0.5) == pytest.approx(1.5)
        assert workspace_time_to_source_time(1.5, 0.5) == pytest.approx(1.0)

    def test_negative_offset(self):
        assert source_time_to_workspace_time(1.0, -0.0185) == pytest.approx(0.9815)
        assert workspace_time_to_source_time(0.9815, -0.0185) == pytest.approx(1.0)

    def test_zero_offset(self):
        assert source_time_to_workspace_time(3.25, 0.0) == pytest.approx(3.25)
        assert workspace_time_to_source_time(3.25, 0.0) == pytest.approx(3.25)

    def test_round_trip_is_exact_for_any_offset(self):
        for source_time, offset in [(0.0, 0.0072), (10.0, -0.0185), (-5.0, 1.5)]:
            workspace_time = source_time_to_workspace_time(source_time, offset)
            assert workspace_time_to_source_time(workspace_time, offset) == pytest.approx(source_time)


class TestArrayConversion:
    def test_array_shift_matches_scalar_elementwise(self):
        native = np.array([0.0, 0.001, 0.002])
        shifted = source_time_to_workspace_time(native, -0.018)
        np.testing.assert_allclose(shifted, np.array([-0.018, -0.017, -0.016]))

    def test_array_round_trip(self):
        native = np.linspace(0.0, 1.0, 50)
        offset = 0.0072
        workspace = source_time_to_workspace_time(native, offset)
        back = workspace_time_to_source_time(workspace, offset)
        np.testing.assert_allclose(back, native)

    def test_sampling_rate_independence(self):
        """Two different-rate sources' own native time arrays each shift
        independently and correctly -- no resampling/interpolation
        anywhere in this pure arithmetic (task's own "Sampling-Rate
        Rule")."""
        source_a = np.arange(0.0, 1.0, 1.0 / 10_000.0)  # 10 kHz
        source_b = np.arange(0.0, 1.0, 1.0 / 2_000.0)  # 2 kHz
        shifted_a = source_time_to_workspace_time(source_a, 0.01)
        shifted_b = source_time_to_workspace_time(source_b, -0.02)
        assert shifted_a.shape == source_a.shape
        assert shifted_b.shape == source_b.shape
        np.testing.assert_allclose(shifted_a, source_a + 0.01)
        np.testing.assert_allclose(shifted_b, source_b - 0.02)


class TestAlignmentOffsetValid:
    @pytest.mark.parametrize("value", [0.0, -0.0185, 1234.5, -1e6])
    def test_finite_numbers_are_valid(self, value):
        assert alignment_offset_valid(value) is True

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_is_invalid(self, value):
        assert alignment_offset_valid(value) is False

    def test_bool_is_rejected_even_though_python_treats_it_as_an_int(self):
        assert alignment_offset_valid(True) is False
        assert alignment_offset_valid(False) is False

    @pytest.mark.parametrize("value", [None, "0.5", [0.5]])
    def test_non_numeric_is_invalid(self, value):
        assert alignment_offset_valid(value) is False


def _t(offset_minutes: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


class TestReferenceSourceIdForWorkspace:
    def test_empty_workspace_has_no_reference(self):
        assert reference_source_id_for_workspace([]) is None

    def test_single_source_is_the_reference(self):
        assert reference_source_id_for_workspace([("src-a", _t(0))]) == "src-a"

    def test_earliest_created_at_wins_regardless_of_list_order(self):
        sources = [("src-b", _t(5)), ("src-a", _t(0)), ("src-c", _t(10))]
        assert reference_source_id_for_workspace(sources) == "src-a"

    def test_tie_breaks_on_source_id_ascending(self):
        sources = [("src-z", _t(0)), ("src-a", _t(0))]
        assert reference_source_id_for_workspace(sources) == "src-a"
