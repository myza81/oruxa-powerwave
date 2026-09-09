"""Tests for app.domain.missing_data_estimation (DEC-084 Calc Slice 2) --
the pure gap-detection/estimation engine, independent of any calculated-
channel orchestration (see tests/test_calculated_channel_service.py and
tests/test_calculated_channel_api.py for the through-create_calculated_
channel/through-the-API coverage)."""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.missing_data_estimation import (
    apply_estimation,
    estimate_hold_last,
    estimate_linear,
    estimate_local_mean,
    estimate_nearest,
    find_gaps,
)


class TestFindGaps:
    def test_no_gaps(self):
        assert find_gaps(np.array([1.0, 2.0, 3.0])) == []

    def test_empty_array(self):
        assert find_gaps(np.array([])) == []

    def test_single_cell_gap(self):
        assert find_gaps(np.array([1.0, np.nan, 3.0])) == [(1, 1)]

    def test_multi_cell_gap(self):
        # This task's own section 5 example: [10, 11, NaN, NaN, 14].
        assert find_gaps(np.array([10.0, 11.0, np.nan, np.nan, 14.0])) == [(2, 3)]

    def test_beginning_gap(self):
        assert find_gaps(np.array([np.nan, 2.0, 3.0])) == [(0, 0)]

    def test_ending_gap(self):
        assert find_gaps(np.array([1.0, 2.0, np.nan])) == [(2, 2)]

    def test_entire_array_is_one_gap(self):
        assert find_gaps(np.array([np.nan, np.nan])) == [(0, 1)]

    def test_multiple_separate_gaps(self):
        values = np.array([1.0, np.nan, 3.0, np.nan, np.nan, 6.0])
        assert find_gaps(values) == [(1, 1), (3, 4)]

    def test_treats_positive_and_negative_infinity_as_non_finite(self):
        assert find_gaps(np.array([1.0, np.inf, -np.inf, 4.0])) == [(1, 2)]


class TestEstimateHoldLast:
    """Section 6."""

    def test_multi_cell_gap_example_from_spec(self):
        result = estimate_hold_last(np.array([10.0, 11.0, np.nan, np.nan, 14.0]), max_gap_value=3)
        assert result.tolist() == [10.0, 11.0, 11.0, 11.0, 14.0]

    def test_single_cell_gap(self):
        result = estimate_hold_last(np.array([1.0, np.nan, 3.0]), max_gap_value=1)
        assert result.tolist() == [1.0, 1.0, 3.0]

    def test_beginning_gap_has_no_previous_sample_stays_nan(self):
        result = estimate_hold_last(np.array([np.nan, 2.0, 3.0]), max_gap_value=1)
        assert np.isnan(result[0])
        assert result[1:].tolist() == [2.0, 3.0]

    def test_ending_gap_may_be_filled(self):
        result = estimate_hold_last(np.array([1.0, 2.0, np.nan]), max_gap_value=1)
        assert result.tolist() == [1.0, 2.0, 2.0]

    def test_oversized_gap_stays_entirely_nan_no_partial_fill(self):
        values = np.array([1.0, np.nan, np.nan, np.nan, np.nan, 6.0])
        result = estimate_hold_last(values, max_gap_value=3)  # gap length 4 > 3
        assert np.all(np.isnan(result[1:5]))
        assert result[0] == 1.0
        assert result[5] == 6.0

    def test_mixed_eligible_and_ineligible_gaps(self):
        # gap A length 2 (eligible), gap B length 5 (ineligible), max_gap=3.
        values = np.array([1.0, np.nan, np.nan, 4.0, np.nan, np.nan, np.nan, np.nan, np.nan, 10.0])
        result = estimate_hold_last(values, max_gap_value=3)
        assert result[1:3].tolist() == [1.0, 1.0]
        assert np.all(np.isnan(result[4:9]))

    def test_positive_and_negative_infinity_treated_as_missing(self):
        result = estimate_hold_last(np.array([1.0, np.inf, -np.inf, 4.0]), max_gap_value=2)
        assert result.tolist() == [1.0, 1.0, 1.0, 4.0]
        assert np.all(np.isfinite(result))

    def test_source_array_unchanged(self):
        values = np.array([1.0, np.nan, 3.0])
        estimate_hold_last(values, max_gap_value=1)
        assert np.isnan(values[1])


class TestEstimateNearest:
    """Section 7."""

    def test_interior_gap_example_from_spec(self):
        result = estimate_nearest(np.array([10.0, np.nan, np.nan, 40.0]), max_gap_value=2)
        assert result.tolist() == [10.0, 10.0, 40.0, 40.0]

    def test_equidistant_ties_break_to_previous_sample(self):
        result = estimate_nearest(np.array([10.0, np.nan, 40.0]), max_gap_value=1)
        assert result.tolist() == [10.0, 10.0, 40.0]

    def test_beginning_gap_uses_following_finite_sample(self):
        result = estimate_nearest(np.array([np.nan, np.nan, 30.0]), max_gap_value=2)
        assert result.tolist() == [30.0, 30.0, 30.0]

    def test_ending_gap_uses_preceding_finite_sample(self):
        result = estimate_nearest(np.array([10.0, np.nan, np.nan]), max_gap_value=2)
        assert result.tolist() == [10.0, 10.0, 10.0]

    def test_oversized_gap_stays_nan(self):
        values = np.array([1.0, np.nan, np.nan, np.nan, np.nan, 6.0])
        result = estimate_nearest(values, max_gap_value=3)
        assert np.all(np.isnan(result[1:5]))

    def test_whole_array_non_finite_has_no_bracket_stays_nan(self):
        result = estimate_nearest(np.array([np.nan, np.nan]), max_gap_value=5)
        assert np.all(np.isnan(result))

    def test_infinity_treated_as_missing(self):
        result = estimate_nearest(np.array([10.0, np.inf, 40.0]), max_gap_value=1)
        assert result.tolist() == [10.0, 10.0, 40.0]

    def test_source_array_unchanged(self):
        values = np.array([10.0, np.nan, 40.0])
        estimate_nearest(values, max_gap_value=1)
        assert np.isnan(values[1])


class TestEstimateLinear:
    """Section 8."""

    def test_uniform_time_spacing(self):
        time = np.array([0.0, 1.0, 2.0, 3.0])
        values = np.array([10.0, np.nan, np.nan, 40.0])
        result = estimate_linear(time, values, max_gap_value=2)
        assert result.tolist() == pytest.approx([10.0, 20.0, 30.0, 40.0])

    def test_non_uniform_time_spacing_uses_actual_time_not_sample_index(self):
        # This task's own section 8 example: time = [0.0, 1.0, 3.0].
        time = np.array([0.0, 1.0, 3.0])
        values = np.array([10.0, np.nan, 40.0])
        result = estimate_linear(time, values, max_gap_value=1)
        # t=1.0 is 1/3 of the way from t=0.0 to t=3.0, never the sample-
        # index midpoint (which would incorrectly give 25.0).
        assert result[1] == pytest.approx(20.0)
        assert result[1] != pytest.approx(25.0)

    def test_beginning_gap_never_extrapolated(self):
        time = np.array([0.0, 1.0, 2.0])
        values = np.array([np.nan, 20.0, 30.0])
        result = estimate_linear(time, values, max_gap_value=1)
        assert np.isnan(result[0])

    def test_ending_gap_never_extrapolated(self):
        time = np.array([0.0, 1.0, 2.0])
        values = np.array([10.0, 20.0, np.nan])
        result = estimate_linear(time, values, max_gap_value=1)
        assert np.isnan(result[2])

    def test_invalid_non_increasing_bracket_leaves_gap_nan(self):
        # The bracketing samples themselves (time[0]=5.0, time[2]=1.0) are
        # deliberately non-increasing -- a synthetic/defensive case (a
        # real aligned `time` array is always monotonic non-decreasing),
        # exercising this function's own explicit t1 > t0 guard directly.
        time = np.array([5.0, 3.0, 1.0])
        values = np.array([10.0, np.nan, 40.0])
        result = estimate_linear(time, values, max_gap_value=1)
        assert np.isnan(result[1])

    def test_non_finite_bracket_timestamp_leaves_gap_nan(self):
        time = np.array([np.nan, 1.0, 2.0])
        values = np.array([10.0, np.nan, 40.0])
        result = estimate_linear(time, values, max_gap_value=1)
        assert np.isnan(result[1])

    def test_oversized_gap_stays_nan(self):
        time = np.arange(6, dtype=np.float64)
        values = np.array([1.0, np.nan, np.nan, np.nan, np.nan, 6.0])
        result = estimate_linear(time, values, max_gap_value=3)
        assert np.all(np.isnan(result[1:5]))

    def test_source_arrays_unchanged(self):
        time = np.array([0.0, 1.0, 2.0])
        values = np.array([10.0, np.nan, 30.0])
        estimate_linear(time, values, max_gap_value=1)
        assert np.isnan(values[1])


class TestEstimateLocalMean:
    """Section 9."""

    def test_symmetric_neighbors_example_from_spec(self):
        values = np.array([10.0, 12.0, np.nan, np.nan, 20.0, 22.0])
        result = estimate_local_mean(values, max_gap_value=2, local_mean_radius=2)
        assert result.tolist() == [10.0, 12.0, 16.0, 16.0, 20.0, 22.0]

    def test_edge_gap_uses_available_side_only(self):
        values = np.array([np.nan, np.nan, 10.0, 20.0])
        result = estimate_local_mean(values, max_gap_value=2, local_mean_radius=2)
        # No samples before index 0 -- neighbors are only [10.0, 20.0].
        assert result.tolist() == [15.0, 15.0, 10.0, 20.0]

    def test_neighbors_containing_nan_are_excluded(self):
        # gap (3,4)'s own before-window (radius 2) reaches back into
        # index 1, which is a DIFFERENT gap's own NaN -- must be excluded
        # from the mean, never treated as a valid neighbor value.
        values = np.array([5.0, np.nan, 10.0, np.nan, np.nan, 20.0])
        result = estimate_local_mean(values, max_gap_value=2, local_mean_radius=2)
        assert result[3] == pytest.approx(15.0)
        assert result[4] == pytest.approx(15.0)

    def test_zero_finite_neighbors_leaves_gap_nan(self):
        values = np.array([np.nan, np.nan, np.nan])
        result = estimate_local_mean(values, max_gap_value=3, local_mean_radius=1)
        assert np.all(np.isnan(result))

    def test_radius_one(self):
        values = np.array([10.0, np.nan, 30.0])
        result = estimate_local_mean(values, max_gap_value=1, local_mean_radius=1)
        assert result[1] == pytest.approx(20.0)

    def test_radius_greater_than_gap_length(self):
        values = np.array([10.0, 12.0, 14.0, np.nan, 20.0, 22.0, 24.0])
        result = estimate_local_mean(values, max_gap_value=1, local_mean_radius=5)
        assert result[3] == pytest.approx(np.mean([10.0, 12.0, 14.0, 20.0, 22.0, 24.0]))

    def test_multiple_gaps_one_gaps_estimate_never_used_as_anothers_neighbor(self):
        # gap1 = index 1, gap2 = index 4; radius=3 makes gap2's own
        # "before" window reach back into index 1 -- which must still
        # read as NaN (excluded), never gap1's own already-computed fill,
        # proving neighbor windows are sliced from the ORIGINAL array.
        values = np.array([10.0, np.nan, 30.0, 40.0, np.nan, 60.0])
        result = estimate_local_mean(values, max_gap_value=1, local_mean_radius=3)
        assert result[1] == pytest.approx((10.0 + 30.0 + 40.0) / 3.0)
        assert result[4] == pytest.approx((30.0 + 40.0 + 60.0) / 3.0)

    def test_infinity_treated_as_missing_and_excluded_from_mean(self):
        values = np.array([10.0, np.inf, 30.0])
        result = estimate_local_mean(values, max_gap_value=1, local_mean_radius=1)
        assert result[1] == pytest.approx(20.0)

    def test_source_array_unchanged(self):
        values = np.array([10.0, np.nan, 30.0])
        estimate_local_mean(values, max_gap_value=1, local_mean_radius=1)
        assert np.isnan(values[1])


class TestApplyEstimation:
    """The one dispatch point app.services.calculated_channel_service
    calls per input."""

    def test_dispatches_hold_last(self):
        time = np.arange(3, dtype=np.float64)
        values = np.array([1.0, np.nan, 3.0])
        result = apply_estimation(time=time, values=values, estimation_method="hold_last", max_gap_value=1)
        assert result.tolist() == [1.0, 1.0, 3.0]

    def test_dispatches_nearest(self):
        time = np.arange(3, dtype=np.float64)
        values = np.array([10.0, np.nan, 40.0])
        result = apply_estimation(time=time, values=values, estimation_method="nearest", max_gap_value=1)
        assert result.tolist() == [10.0, 10.0, 40.0]

    def test_dispatches_linear_using_time_not_index(self):
        time = np.array([0.0, 1.0, 3.0])
        values = np.array([10.0, np.nan, 40.0])
        result = apply_estimation(time=time, values=values, estimation_method="linear", max_gap_value=1)
        assert result[1] == pytest.approx(20.0)

    def test_dispatches_local_mean(self):
        time = np.arange(3, dtype=np.float64)
        values = np.array([10.0, np.nan, 30.0])
        result = apply_estimation(
            time=time, values=values, estimation_method="local_mean", max_gap_value=1, local_mean_radius=1,
        )
        assert result[1] == pytest.approx(20.0)

    def test_unsupported_method_raises_value_error(self):
        # Defensive-only guard -- callers are expected to have already
        # rejected "pchip"/unknown methods via app.domain.calculated_
        # channel's own validation predicates before ever reaching here.
        time = np.arange(3, dtype=np.float64)
        values = np.array([10.0, np.nan, 30.0])
        with pytest.raises(ValueError):
            apply_estimation(time=time, values=values, estimation_method="pchip", max_gap_value=1)
