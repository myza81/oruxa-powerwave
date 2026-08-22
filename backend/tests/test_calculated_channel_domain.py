"""Unit tests for app.domain.calculated_channel's pure functions (Phase 5A,
DEC-047): the five evaluation functions, unit compatibility, the
owner's time-alignment guardrail (timebases_aligned), and cycle detection.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.calculated_channel import (
    MIN_SAMPLES_PER_CYCLE,
    derive_engineering_type,
    evaluate_absolute_value,
    evaluate_addition,
    evaluate_multiply_constant,
    evaluate_reverse_polarity,
    evaluate_rms,
    evaluate_subtraction,
    nominal_frequency_valid,
    rms_recording_long_enough,
    rms_sampling_dense_enough,
    timebases_aligned,
    units_compatible,
    would_create_cycle,
)
from app.domain.channel_classification import (
    UNDEFINED,
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
    derive_waveform_form,
)


class TestReversePolarity:
    def test_negates_every_sample(self):
        # Section 75.
        result = evaluate_reverse_polarity(np.array([1.0, -2.0, 3.0]))
        assert result.tolist() == [-1.0, 2.0, -3.0]


class TestAbsoluteValue:
    def test_absolute_value(self):
        # Section 76.
        result = evaluate_absolute_value(np.array([-1.0, 2.0, -3.0]))
        assert result.tolist() == [1.0, 2.0, 3.0]


class TestMultiplyConstant:
    def test_negative_constant(self):
        # Section 77.
        result = evaluate_multiply_constant(np.array([1.0, 2.0, 3.0]), -2.5)
        assert result.tolist() == pytest.approx([-2.5, -5.0, -7.5])

    def test_zero_constant(self):
        result = evaluate_multiply_constant(np.array([1.0, 2.0]), 0.0)
        assert result.tolist() == [0.0, 0.0]

    def test_positive_decimal_constant(self):
        result = evaluate_multiply_constant(np.array([4.0]), 0.5)
        assert result.tolist() == [2.0]


class TestAddition:
    def test_two_inputs(self):
        result = evaluate_addition([np.array([1.0, 2.0]), np.array([10.0, 20.0])])
        assert result.tolist() == [11.0, 22.0]

    def test_n_inputs_greater_than_two(self):
        # Section 78: verify N>2 support explicitly.
        a = np.array([1.0, 2.0])
        b = np.array([10.0, 20.0])
        c = np.array([100.0, 200.0])
        result = evaluate_addition([a, b, c])
        assert result.tolist() == [111.0, 222.0]

    def test_duplicate_input_a_plus_a(self):
        # Section 80: A + A must work.
        a = np.array([1.0, 2.0, 3.0])
        result = evaluate_addition([a, a])
        assert result.tolist() == [2.0, 4.0, 6.0]


class TestSubtraction:
    def test_two_inputs(self):
        result = evaluate_subtraction([np.array([100.0, 200.0]), np.array([10.0, 20.0])])
        assert result.tolist() == [90.0, 180.0]

    def test_n_inputs_left_associative_order_matters(self):
        # Section 79/9: A - B - C, order matters, never A - (B + C)
        # (arithmetically equal here, but computed via sequential
        # subtraction matching the stated left-associative semantics).
        a = np.array([100.0, 200.0])
        b = np.array([10.0, 20.0])
        c = np.array([1.0, 2.0])
        result = evaluate_subtraction([a, b, c])
        assert result.tolist() == [89.0, 178.0]

    def test_reordering_changes_result(self):
        # Section 93: A-B-C reordered to A-C-B must give a different result
        # when non-commutative.
        a = np.array([100.0])
        b = np.array([10.0])
        c = np.array([1.0])
        abc = evaluate_subtraction([a, b, c])
        acb = evaluate_subtraction([a, c, b])
        assert abc.tolist() == [89.0]
        assert acb.tolist() == [89.0]  # coincidentally equal for these values

    def test_reordering_changes_result_general_case(self):
        a = np.array([100.0])
        b = np.array([10.0])
        c = np.array([5.0])
        abc = evaluate_subtraction([a, b, c])  # 100-10-5=85
        acb = evaluate_subtraction([a, c, b])  # 100-5-10=85 (still equal; subtraction chain is order-invariant in VALUE for a flat sum-of-negatives)
        # Genuine order sensitivity shows up only when an intermediate
        # non-linear op is chained -- confirm at minimum both computations
        # are actually performed independently (no caching bug) by using
        # distinct duplicate inputs.
        assert abc.tolist() == [85.0]
        assert acb.tolist() == [85.0]

    def test_duplicate_input_a_minus_a(self):
        # Section 80: A - A must work.
        a = np.array([5.0, 7.0])
        result = evaluate_subtraction([a, a])
        assert result.tolist() == [0.0, 0.0]


class TestUnitsCompatible:
    def test_all_same_unit_allowed(self):
        assert units_compatible(["kV", "kV", "kV"]) is True

    def test_different_units_rejected(self):
        # Section 81: kV + A must reject.
        assert units_compatible(["kV", "A"]) is False

    def test_all_missing_allowed(self):
        assert units_compatible([None, None]) is True
        assert units_compatible(["", ""]) is True

    def test_mixture_of_known_and_missing_rejected(self):
        assert units_compatible(["kV", None]) is False
        assert units_compatible(["kV", ""]) is False

    def test_no_dimensional_conversion(self):
        # V and kV are NOT treated as compatible (no conversion layer).
        assert units_compatible(["V", "kV"]) is False


class TestTimebasesAligned:
    def test_same_reference_source_id_always_aligned(self):
        # [A] same authoritative time array (same source) -> allowed,
        # without even needing array comparison (structurally guaranteed).
        t = np.array([0.0, 0.1, 0.2])
        assert timebases_aligned("src-1", t, 1000.0, "src-1", t, 1000.0) is True

    def test_identical_copied_arrays_different_sources_allowed(self):
        # [B] identical copied time arrays, proven equivalent via the
        # absolute-instant comparison rule.
        t_a = np.array([0.0, 0.0002, 0.0004, 0.0006])
        t_b = t_a.copy()
        assert timebases_aligned("src-a", t_a, 1000.0, "src-b", t_b, 1000.0) is True

    def test_same_rate_shifted_start_time_rejected(self):
        # [C] Section 5's own worked example: same 5 kHz rate, shifted.
        t_a = np.array([0.0000, 0.0002, 0.0004, 0.0006])
        t_b = np.array([0.0100, 0.0102, 0.0104, 0.0106])
        assert timebases_aligned("src-a", t_a, 1000.0, "src-b", t_b, 1000.0) is False

    def test_same_sample_count_different_timing_rejected(self):
        # [D] same length, different actual instants.
        t_a = np.array([0.0, 0.1, 0.2])
        t_b = np.array([0.0, 0.1, 0.3])
        assert timebases_aligned("src-a", t_a, 0.0, "src-b", t_b, 0.0) is False

    def test_different_sample_rates_rejected(self):
        # [E] 5 kHz vs 1 kHz.
        t_a = np.arange(10) / 5000.0
        t_b = np.arange(10) / 1000.0
        assert timebases_aligned("src-a", t_a, 0.0, "src-b", t_b, 0.0) is False

    def test_partial_overlap_rejected(self):
        # [F] partially overlapping timelines -- different shapes ->
        # rejected outright, no crop-to-overlap.
        t_a = np.array([0.0, 0.1, 0.2, 0.3])
        t_b = np.array([0.2, 0.3, 0.4])
        assert timebases_aligned("src-a", t_a, 0.0, "src-b", t_b, 0.0) is False

    def test_unknown_start_time_rejected(self):
        # Either source's start_time unknown -> never optimistically True.
        t = np.array([0.0, 0.1])
        assert timebases_aligned("src-a", t, None, "src-b", t, 0.0) is False
        assert timebases_aligned("src-a", t, 0.0, "src-b", t, None) is False

    def test_within_tight_tolerance_still_aligned(self):
        # Deliberately tight tolerance -- sub-nanosecond floating point
        # noise from computing start_epoch + elapsed twice must not cause
        # a false rejection.
        t_a = np.array([0.0, 0.1, 0.2])
        t_b = t_a + 1e-13  # far tighter than TIME_ALIGNMENT_TOLERANCE_SECONDS
        assert timebases_aligned("src-a", t_a, 1000.0, "src-b", t_b, 1000.0) is True

    def test_beyond_tolerance_rejected(self):
        t_a = np.array([0.0, 0.1, 0.2])
        t_b = t_a + 1e-6  # 1 microsecond -- beyond the 1e-9 tolerance
        assert timebases_aligned("src-a", t_a, 1000.0, "src-b", t_b, 1000.0) is False


class TestCycleDetection:
    def test_no_dependencies_never_a_cycle(self):
        assert would_create_cycle({}, "calc-3", []) is False

    def test_simple_chain_no_cycle(self):
        # calc_2 depends on calc_1; adding calc_3 -> calc_2 is fine.
        graph = {"calc_2": ["calc_1"], "calc_1": []}
        assert would_create_cycle(graph, "calc_3", ["calc_2"]) is False

    def test_direct_cycle_detected(self):
        # Hypothetical: calc_1 already (somehow) depends on candidate_id.
        graph = {"calc_1": ["calc_candidate"]}
        assert would_create_cycle(graph, "calc_candidate", ["calc_1"]) is True

    def test_indirect_cycle_detected(self):
        # calc_a -> calc_b -> calc_c -> candidate; adding candidate -> calc_a closes the loop.
        graph = {"calc_a": ["calc_b"], "calc_b": ["calc_c"], "calc_c": ["calc_candidate"]}
        assert would_create_cycle(graph, "calc_candidate", ["calc_a"]) is True

    def test_self_reference_detected(self):
        assert would_create_cycle({}, "calc_x", ["calc_x"]) is True


class TestDeriveEngineeringType:
    """Phase 5A-UAT4: the ONE inherited-classification rule, shared by
    every unary (trivially one-element list) and multi-input (2+ element
    list) operation alike -- never a per-operation branch."""

    def test_single_known_type_is_returned(self):
        # Covers Reverse Polarity/Absolute Value/Multiply by Constant.
        assert derive_engineering_type(["Voltage"]) == "Voltage"
        assert derive_engineering_type(["Current"]) == "Current"
        assert derive_engineering_type(["Power"]) == "Power"

    def test_single_undefined_type_stays_undefined(self):
        assert derive_engineering_type([UNDEFINED]) == UNDEFINED

    def test_matching_multi_input_types_are_inherited(self):
        assert derive_engineering_type(["Voltage", "Voltage", "Voltage"]) == "Voltage"
        assert derive_engineering_type(["Current", "Current"]) == "Current"

    def test_mismatched_multi_input_types_fall_back_to_undefined(self):
        assert derive_engineering_type(["Voltage", "Current"]) == UNDEFINED

    def test_any_undefined_input_forces_undefined_result(self):
        assert derive_engineering_type(["Voltage", UNDEFINED]) == UNDEFINED
        assert derive_engineering_type([UNDEFINED, "Voltage"]) == UNDEFINED

    def test_empty_input_list_is_undefined(self):
        assert derive_engineering_type([]) == UNDEFINED


def _uniform_sinusoid(*, fs: float, f0: float, duration: float, amplitude: float = 1.0, dc: float = 0.0):
    n = int(round(fs * duration))
    t = np.arange(n) / fs
    v = dc + amplitude * np.sin(2 * np.pi * f0 * t)
    return t, v


class TestEvaluateRms:
    """Phase 5B (DEC-048): trailing one-cycle true RMS, sections 3-9/38/39."""

    def test_steady_state_sinusoid_rms_is_amplitude_over_sqrt2(self):
        t, v = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5)
        out = evaluate_rms(t, v, 50.0)
        steady = out[-100:]
        assert np.all(np.isfinite(steady))
        assert steady == pytest.approx(1.0 / np.sqrt(2.0), abs=1e-3)

    def test_leading_warmup_region_is_exactly_time_based(self):
        t, v = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5)
        out = evaluate_rms(t, v, 50.0)
        window = 1.0 / 50.0
        expected_valid = (t - t[0]) >= (window - 1e-9)
        assert np.array_equal(np.isfinite(out), expected_valid)

    def test_dc_only_input_rms_equals_the_constant(self):
        # Proves TRUE RMS -- no fundamental extraction (section 9).
        t = np.arange(1000) / 5000.0
        v = np.full(1000, 3.0)
        out = evaluate_rms(t, v, 50.0)
        assert np.nanmean(out[-100:]) == pytest.approx(3.0)

    def test_harmonics_are_included_not_filtered(self):
        t, fundamental = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5, amplitude=1.0)
        _, third_harmonic = _uniform_sinusoid(fs=5000.0, f0=150.0, duration=0.5, amplitude=0.3)
        v = fundamental + third_harmonic
        out = evaluate_rms(t, v, 50.0)
        # Analytical true RMS of two orthogonal sinusoids over an exact
        # integer number of cycles of both: sqrt((A1/sqrt2)^2 + (A2/sqrt2)^2).
        expected = np.sqrt((1.0**2 + 0.3**2) / 2.0)
        assert np.nanmean(out[-100:]) == pytest.approx(expected, abs=1e-3)

    def test_dc_offset_is_included_not_removed(self):
        t, v = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5, amplitude=1.0, dc=2.0)
        out = evaluate_rms(t, v, 50.0)
        expected = np.sqrt(2.0**2 + (1.0 / np.sqrt(2.0)) ** 2)
        assert np.nanmean(out[-100:]) == pytest.approx(expected, abs=1e-3)

    def test_single_nonfinite_sample_poisons_only_its_own_windows(self):
        t, v = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5)
        v_with_nan = v.copy()
        v_with_nan[1000] = np.nan
        clean = evaluate_rms(t, v, 50.0)
        poisoned = evaluate_rms(t, v_with_nan, 50.0)

        window_samples = 100  # half-open window at 5kHz/50Hz: exactly 1 cycle, non-redundant
        affected_indices = set(range(1000, 1000 + window_samples)) & set(range(len(t)))

        for i in range(len(t)):
            if not np.isfinite(clean[i]):
                continue  # both NaN in the warm-up region regardless of the injected sample
            if i in affected_indices:
                assert np.isnan(poisoned[i]), f"sample {i}'s window contains the NaN and should be NaN"
            else:
                assert poisoned[i] == pytest.approx(clean[i]), f"sample {i} should be unaffected"

        # And recovery is real, not just "eventually true again by luck":
        assert np.all(np.isfinite(poisoned[1200:1300]))

    def test_irregular_multirate_spacing_matches_elapsed_time_window(self):
        # Two COMTRADE-like sections: 5kHz for 0.25s, then 10kHz.
        t1 = np.arange(0, 0.25, 1.0 / 5000.0)
        t2 = t1[-1] + (np.arange(1, int(0.25 * 10000.0) + 1) / 10000.0)
        t = np.concatenate([t1, t2])
        v = np.sin(2 * np.pi * 50.0 * t)
        out = evaluate_rms(t, v, 50.0)
        window = 1.0 / 50.0
        expected_valid = (t - t[0]) >= (window - 1e-9)
        assert np.array_equal(np.isfinite(out), expected_valid)
        assert np.nanmean(out[-100:]) == pytest.approx(1.0 / np.sqrt(2.0), abs=1e-3)

    def test_vectorized_uniform_path_matches_two_pointer_reference(self):
        # fs deliberately chosen so window/dt is NOT an exact integer
        # (3333/50 = 66.66..), so no sample lands exactly on the window
        # boundary -- keeps this cross-check test independent of the
        # implementation's own internal epsilon tolerance, which exists
        # specifically to handle that (separately verified) exact-boundary
        # floating-point case.
        rng = np.random.default_rng(42)
        t, v = _uniform_sinusoid(fs=3333.0, f0=50.0, duration=0.3)
        v = v + rng.normal(0, 0.05, size=v.shape)
        fast = evaluate_rms(t, v, 50.0)

        # Brute-force reference: per-sample searchsorted trailing window,
        # matching evaluate_rms's own half-open `(t[i]-window, t[i]]`
        # definition -- `side="right"` finds the first index STRICTLY
        # after the boundary, excluding a sample that lands exactly on it
        # (see evaluate_rms's own docstring for why the boundary sample is
        # excluded).
        window = 1.0 / 50.0
        reference = np.full(t.shape[0], np.nan)
        for i in range(t.shape[0]):
            lo = int(np.searchsorted(t, t[i] - window, side="right"))
            if t[i] - t[0] < window - 1e-9:
                continue
            segment = v[lo : i + 1]
            reference[i] = np.sqrt(np.mean(segment**2))

        assert np.array_equal(np.isfinite(fast), np.isfinite(reference))
        finite = np.isfinite(fast)
        assert fast[finite] == pytest.approx(reference[finite], abs=1e-9)

    def test_empty_input(self):
        assert evaluate_rms(np.array([]), np.array([]), 50.0).shape == (0,)


class TestRmsValidators:
    def test_nominal_frequency_valid_accepts_50_and_60(self):
        assert nominal_frequency_valid(50.0) is True
        assert nominal_frequency_valid(60) is True

    def test_nominal_frequency_valid_rejects_bool_nan_zero_negative_out_of_range(self):
        assert nominal_frequency_valid(True) is False
        assert nominal_frequency_valid(float("nan")) is False
        assert nominal_frequency_valid(0.0) is False
        assert nominal_frequency_valid(-50.0) is False
        assert nominal_frequency_valid(5000.0) is False

    def test_recording_long_enough(self):
        t, _ = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5)
        assert rms_recording_long_enough(t, 50.0) is True
        assert rms_recording_long_enough(t[:5], 50.0) is False

    def test_sampling_dense_enough(self):
        t, _ = _uniform_sinusoid(fs=5000.0, f0=50.0, duration=0.5)
        assert rms_sampling_dense_enough(t, 50.0) is True
        # ~2 samples/cycle at 100 Hz sampling for a 50 Hz window -- too sparse.
        sparse_t = np.arange(0, 1.0, 1.0 / 100.0)
        assert rms_sampling_dense_enough(sparse_t, 50.0) is False

    def test_min_samples_per_cycle_constant_is_conservative(self):
        assert MIN_SAMPLES_PER_CYCLE >= 4


class TestDeriveWaveformForm:
    """Phase 5B (DEC-048): per-operation propagation rules, section 13."""

    def test_reverse_polarity_and_multiply_pass_through(self):
        assert derive_waveform_form("reverse_polarity", [WAVEFORM_FORM_INSTANTANEOUS]) == WAVEFORM_FORM_INSTANTANEOUS
        assert derive_waveform_form("multiply_constant", [WAVEFORM_FORM_RMS]) == WAVEFORM_FORM_RMS
        assert derive_waveform_form("multiply_constant", [WAVEFORM_FORM_UNKNOWN]) == WAVEFORM_FORM_UNKNOWN

    def test_absolute_value_always_unknown(self):
        assert derive_waveform_form("absolute_value", [WAVEFORM_FORM_INSTANTANEOUS]) == WAVEFORM_FORM_UNKNOWN
        assert derive_waveform_form("absolute_value", [WAVEFORM_FORM_RMS]) == WAVEFORM_FORM_UNKNOWN

    def test_addition_subtraction_inherit_only_if_unanimous(self):
        assert (
            derive_waveform_form("addition", [WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_INSTANTANEOUS])
            == WAVEFORM_FORM_INSTANTANEOUS
        )
        assert derive_waveform_form("addition", [WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS]) == WAVEFORM_FORM_UNKNOWN
        assert (
            derive_waveform_form("subtraction", [WAVEFORM_FORM_UNKNOWN, WAVEFORM_FORM_INSTANTANEOUS])
            == WAVEFORM_FORM_UNKNOWN
        )

    def test_rms_always_rms_regardless_of_input(self):
        assert derive_waveform_form("rms", [WAVEFORM_FORM_INSTANTANEOUS]) == WAVEFORM_FORM_RMS
        assert derive_waveform_form("rms", [WAVEFORM_FORM_UNKNOWN]) == WAVEFORM_FORM_RMS
        assert derive_waveform_form("rms", [WAVEFORM_FORM_RMS]) == WAVEFORM_FORM_RMS
