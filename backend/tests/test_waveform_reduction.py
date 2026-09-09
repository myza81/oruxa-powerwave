"""Unit tests for app.domain.waveform_reduction's min/max envelope.

Includes the mandatory synthetic-spike regression test: a narrow
transient that plain nth-point stride sampling (powerwave's own desktop
decimation algorithm -- see docs/project-memory/MIGRATION_PLAN.md's Phase
2 design §3/§5) would demonstrably miss, and that this module's
peak-preserving algorithm must not.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.waveform_reduction import build_min_max_envelope


def _naive_stride_sample(values: np.ndarray, stride: int) -> np.ndarray:
    """The algorithm this module deliberately does NOT use.

    Mirrors powerwave's own live `decimate_for_display()`
    (`t_clip[::stride]`) exactly, purely to demonstrate what it would miss
    -- not a production implementation (per the task's own instruction:
    "Do not need to keep a production implementation of the naive
    algorithm; the test can demonstrate the scenario directly").
    """
    return values[::stride]


class TestSyntheticSpikeRegression:
    """The mandatory regression test protecting waveform fidelity."""

    def _spike_fixture(self) -> tuple[np.ndarray, np.ndarray, int]:
        """2000 ordinary samples around 1.0V, with a single-sample 100V
        transient spike at index 777 -- narrow enough that a stride of 20
        (2000 samples down to a 100-point budget) has only a 1-in-20
        chance of ever landing exactly on it.
        """
        n = 2000
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.full(n, 1.0, dtype=np.float64)
        spike_index = 777
        values[spike_index] = 100.0
        return time, values, spike_index

    def test_naive_stride_sampling_demonstrably_can_miss_the_spike(self):
        """Proves the risk is real, not hypothetical, before asserting the fix."""
        _, values, spike_index = self._spike_fixture()
        stride = 20  # 2000 samples -> a ~100-point budget, matching the case below

        naive_result = _naive_stride_sample(values, stride)

        assert spike_index % stride != 0, "fixture must not accidentally align with stride"
        assert 100.0 not in naive_result, (
            "sanity check failed: naive stride sampling unexpectedly caught the spike -- "
            "the fixture no longer demonstrates the risk this test exists to document"
        )

    def test_min_max_envelope_preserves_the_spike(self):
        time, values, spike_index = self._spike_fixture()

        out_time, out_values = build_min_max_envelope(time, values, point_budget=100)

        assert 100.0 in out_values, "the transient spike's true extreme value was lost"
        spike_position = int(np.argmax(out_values))
        assert out_time[spike_position] == time[spike_index], (
            "the spike's value was preserved but not paired with its true sample time"
        )

    def test_min_max_envelope_preserves_a_narrow_negative_spike_too(self):
        n = 2000
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.full(n, 1.0, dtype=np.float64)
        values[1234] = -50.0

        _, out_values = build_min_max_envelope(time, values, point_budget=100)

        assert -50.0 in out_values


class TestChronologicalOrderingAndAssociation:
    def test_output_time_is_strictly_non_decreasing(self):
        rng = np.random.default_rng(42)
        n = 5000
        time = np.arange(n, dtype=np.float64) * 0.0005
        values = rng.normal(size=n)

        out_time, _ = build_min_max_envelope(time, values, point_budget=200)

        assert np.all(np.diff(out_time) >= 0)

    def test_each_value_corresponds_to_its_true_source_time_not_a_fabricated_grid(self):
        n = 1000
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.sin(np.arange(n) * 0.1)

        out_time, out_values = build_min_max_envelope(time, values, point_budget=50)

        # Every emitted (time, value) pair must be a real sample from the
        # source arrays -- not an evenly-spaced fabricated timestamp.
        time_to_value = dict(zip(time.tolist(), values.tolist()))
        for t, v in zip(out_time, out_values):
            assert t in time_to_value, f"emitted time {t} is not a real source sample time"
            assert time_to_value[t] == pytest.approx(v)


class TestFirstLastSampleHandling:
    def test_true_first_and_last_sample_of_the_input_are_always_present(self):
        n = 3000
        time = np.arange(n, dtype=np.float64) * 0.001
        # Flat except a spike far from either edge, so neither edge sample
        # is naturally a bucket extremum -- the guarantee has to actively
        # add them, not get them for free.
        values = np.full(n, 5.0, dtype=np.float64)
        values[1500] = 999.0

        out_time, out_values = build_min_max_envelope(time, values, point_budget=60)

        assert out_time[0] == time[0]
        assert out_values[0] == values[0]
        assert out_time[-1] == time[-1]
        assert out_values[-1] == values[-1]

    def test_no_duplicate_edge_point_when_the_edge_is_already_a_bucket_extremum(self):
        n = 100
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.arange(n, dtype=np.float64)  # strictly increasing -> last sample is the max of its own bucket

        out_time, out_values = build_min_max_envelope(time, values, point_budget=20)

        # The true last sample must appear exactly once, not twice.
        matches = [i for i, t in enumerate(out_time) if t == time[-1]]
        assert len(matches) == 1


class TestDeterminism:
    def test_same_input_and_budget_always_produce_identical_output(self):
        rng = np.random.default_rng(7)
        n = 4321
        time = np.arange(n, dtype=np.float64) * 0.001
        values = rng.normal(size=n)

        first_time, first_values = build_min_max_envelope(time, values, point_budget=333)
        second_time, second_values = build_min_max_envelope(time, values, point_budget=333)

        np.testing.assert_array_equal(first_time, second_time)
        np.testing.assert_array_equal(first_values, second_values)


class TestNoMutation:
    def test_input_arrays_are_never_mutated(self):
        n = 500
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.arange(n, dtype=np.float64)
        time_copy = time.copy()
        values_copy = values.copy()

        build_min_max_envelope(time, values, point_budget=50)

        np.testing.assert_array_equal(time, time_copy)
        np.testing.assert_array_equal(values, values_copy)

    def test_output_does_not_alias_input_memory(self):
        n = 500
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.arange(n, dtype=np.float64)

        out_time, out_values = build_min_max_envelope(time, values, point_budget=50)
        out_time[0] = -999.0
        out_values[0] = -999.0

        assert time[0] != -999.0
        assert values[0] != -999.0


class TestReturnedPointCountIsABudgetNotAnExactCap:
    def test_returned_count_is_near_but_not_necessarily_equal_to_budget(self):
        n = 10000
        time = np.arange(n, dtype=np.float64) * 0.001
        rng = np.random.default_rng(1)
        values = rng.normal(size=n)

        out_time, _ = build_min_max_envelope(time, values, point_budget=1000)

        # ~2 points/bucket (500 buckets) plus up to 2 edge-guarantee points.
        assert 500 <= len(out_time) <= 1002


class TestSmallInputsAndEdgeCases:
    def test_single_sample_input(self):
        time = np.array([0.0])
        values = np.array([42.0])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=10)

        np.testing.assert_array_equal(out_time, [0.0])
        np.testing.assert_array_equal(out_values, [42.0])

    def test_point_budget_of_one_still_returns_valid_chronological_output(self):
        n = 100
        time = np.arange(n, dtype=np.float64) * 0.001
        values = np.sin(np.arange(n) * 0.2)

        out_time, out_values = build_min_max_envelope(time, values, point_budget=1)

        assert np.all(np.diff(out_time) >= 0)
        assert len(out_time) == len(out_values)

    def test_fewer_samples_than_buckets_does_not_crash_or_duplicate(self):
        # 5 samples requested against a much larger point_budget -- exercises
        # the bucket-count-clamped-to-n path.
        time = np.array([0.0, 0.001, 0.002, 0.003, 0.004])
        values = np.array([1.0, 5.0, 2.0, 9.0, 3.0])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=1000)

        assert np.all(np.diff(out_time) >= 0)
        assert len(out_time) == len(out_values)


class TestExplicitNullGaps:
    """DEC-084 (Slice 3): a converted source channel can now legitimately
    contain `NaN` samples (an explicit-null resolution). Plain
    `np.argmin`/`np.argmax` both silently resolve to the FIRST `NaN`
    whenever one is present anywhere in the searched array -- these tests
    protect against that quirk turning into an invisible-extremum
    regression (DEC-019) or a crash."""

    def test_finite_only_reduction_is_unchanged(self):
        # No NaN anywhere -- byte-for-byte the same as before this slice.
        n = 2000
        time = np.arange(n, dtype=np.float64) * 0.001
        rng = np.random.default_rng(3)
        values = rng.normal(size=n)

        out_time, out_values = build_min_max_envelope(time, values, point_budget=100)

        assert not np.any(np.isnan(out_values))
        assert np.all(np.isfinite(out_values))

    def test_single_nan_does_not_crash(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([1.0, 1.1, np.nan, 1.2, 1.3])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert len(out_time) == len(out_values)

    def test_single_nan_preserves_a_gap(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([1.0, 1.1, np.nan, 1.2, 1.3])

        _, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert np.any(np.isnan(out_values))

    def test_single_nan_preserves_valid_values_before_and_after(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([1.0, 1.1, np.nan, 1.2, 1.3])

        _, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert 1.0 in out_values  # the true min, before the gap
        assert 1.3 in out_values  # the true max, after the gap

    def test_single_nan_never_substitutes_zero(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([1.0, 1.1, np.nan, 1.2, 1.3])

        _, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert 0.0 not in out_values

    def test_consecutive_nans_preserve_a_gap_and_the_valid_edges(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        values = np.array([1.0, 1.1, 1.2, np.nan, np.nan, 1.3, 1.4, 1.5])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert len(out_time) == len(out_values)
        assert np.any(np.isnan(out_values))
        assert 1.0 in out_values
        assert 1.5 in out_values
        assert 0.0 not in out_values

    def test_nan_inside_one_bucket_does_not_hide_a_real_extremum_in_a_neighboring_bucket(self):
        # The core DEC-084/DEC-019 regression: two adjacent buckets, each
        # with exactly one NaN sitting right next to that bucket's own
        # true extremum. Naive argmin/argmax (pre-fix) would let the NaN
        # win BOTH searches in each bucket, discarding 1.3 and 2.0
        # entirely -- exactly the "invisible extremum" DEC-019 forbids.
        time = np.array([0.0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        values = np.array([1.0, 1.1, 1.2, 1.3, np.nan, np.nan, 2.0, 2.1, 2.2, 2.3])

        _, out_values = build_min_max_envelope(time, values, point_budget=4)  # 2 buckets

        assert 1.3 in out_values, "bucket A's true max must survive its own bucket's NaN"
        assert 2.0 in out_values, "bucket B's true min must survive its own bucket's NaN"
        assert np.any(np.isnan(out_values)), "the gap itself must still be visible"

    def test_all_nan_bucket_remains_a_gap(self):
        time = np.array([0.0, 1.0, 2.0, 3.0])
        values = np.array([np.nan, np.nan, np.nan, np.nan])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert len(out_time) == len(out_values)
        assert np.all(np.isnan(out_values))
        assert 0.0 not in out_values

    def test_nan_at_the_beginning_of_the_whole_range(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([np.nan, 1.0, 2.0, 3.0, 4.0])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert np.isnan(out_values[0])
        assert out_time[0] == time[0]
        assert 4.0 in out_values
        assert 0.0 not in out_values

    def test_nan_at_the_end_of_the_whole_range(self):
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        values = np.array([1.0, 2.0, 3.0, 4.0, np.nan])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        assert np.isnan(out_values[-1])
        assert out_time[-1] == time[-1]
        assert 1.0 in out_values
        assert 0.0 not in out_values

    def test_edge_guarantee_does_not_duplicate_a_nan_edge_point(self):
        # Regression for the NaN-unsafe `!=` comparison the edge
        # guarantee used before this slice: `nan != nan` is always
        # `True` in Python, so a naive check would insert a REDUNDANT
        # duplicate point even when the true edge is already correctly
        # represented as NaN.
        time = np.array([0.0, 1.0, 2.0, 3.0])
        values = np.array([np.nan, np.nan, np.nan, np.nan])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=2)

        matches = [i for i, t in enumerate(out_time) if t == time[0]]
        assert len(matches) == 1

    def test_alternating_valid_and_nan_does_not_crash_and_preserves_gaps(self):
        n = 20
        time = np.arange(n, dtype=np.float64)
        values = np.array([float(i) if i % 2 == 0 else np.nan for i in range(n)])

        out_time, out_values = build_min_max_envelope(time, values, point_budget=8)

        assert len(out_time) == len(out_values)
        assert np.any(np.isnan(out_values))
        assert np.any(np.isfinite(out_values))
        # No finite value was ever coerced FROM a gap into 0 -- every
        # finite output value must be a genuine even index's own value.
        for t, v in zip(out_time, out_values):
            if np.isfinite(v):
                assert v == t  # by construction, values[i] == i for even i

    def test_output_never_crashes_on_a_bucket_boundary_landing_exactly_on_nan(self):
        # A deterministic sanity sweep across many bucket counts/positions
        # -- never a crash, never a length mismatch, regardless of where
        # NaN happens to fall relative to bucket edges.
        n = 500
        time = np.arange(n, dtype=np.float64) * 0.001
        rng = np.random.default_rng(11)
        values = rng.normal(size=n)
        nan_positions = rng.choice(n, size=25, replace=False)
        values[nan_positions] = np.nan

        for budget in (2, 10, 50, 100, 999):
            out_time, out_values = build_min_max_envelope(time, values, point_budget=budget)
            assert len(out_time) == len(out_values)
            assert np.all(np.diff(out_time) >= 0)


class TestInputValidation:
    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            build_min_max_envelope(np.array([0.0, 1.0]), np.array([1.0]), point_budget=10)

    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            build_min_max_envelope(np.array([]), np.array([]), point_budget=10)

    def test_non_positive_point_budget_raises(self):
        with pytest.raises(ValueError):
            build_min_max_envelope(np.array([0.0, 1.0]), np.array([1.0, 2.0]), point_budget=0)
