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
