"""The NF-3D baseline comparison ignores the angle of a numerically negligible sequence phasor, and nothing else.

On Linux CI the frozen `zero_sequence_angle_deg` of a balanced set (zero-sequence magnitude 2.4e-10 on a 100 scale) came out as 179.995457043 instead of
the Windows-frozen 179.994321303: the angle of a phasor that is only round-off is decided by the last bits of its real and imaginary parts. The
comparison (`_same_with_noise_floor`, test infrastructure only) skips such an angle ONLY when both the expected and the actual magnitude are at or below
`NOISE_FLOOR` of the positive-sequence magnitude, which is the established relative tolerance of `_same` itself (1e-9). These tests pin that it still reports a changed magnitude (always compared), a meaningful
angle regression, a one-sided collapse to noise, and that the tolerances of `_same` itself are not relaxed. No frozen data or product code is involved.
"""

from __future__ import annotations

import copy

import pytest

from tests.test_nf3b_frozen_baselines import REL, _same
from tests.test_nf3d_pre_migration_baseline import NOISE_FLOOR, _negligible_angles, _same_with_noise_floor

# the numbers observed on the Linux CI runner against the Windows-frozen baseline
FROZEN_ZERO_ANGLE, LINUX_ZERO_ANGLE = 179.994321303, 179.995457043
FROZEN_ZERO_MAGNITUDE = 2.38969734065e-10
# the 4 kHz record: the case that a floor of 1e-10 did NOT cover (zero sequence 3.7e-10 of the positive sequence)
FS4000_ZERO_MAGNITUDE, FS4000_FROZEN_ANGLE, FS4000_LINUX_ANGLE = 3.71343e-08, 2.19264400541e-05, 2.92352552702e-05


def sequences(*, positive=100.0, zero=FROZEN_ZERO_MAGNITUDE, zero_angle=FROZEN_ZERO_ANGLE, negative=1.0e-9, negative_angle=10.0,
              positive_angle=-2.5):
    return {
        "positive_sequence_magnitude": positive, "positive_sequence_angle_deg": positive_angle,
        "negative_sequence_magnitude": negative, "negative_sequence_angle_deg": negative_angle,
        "zero_sequence_magnitude": zero, "zero_sequence_angle_deg": zero_angle,
        "zero_sequence_ratio_percent": zero / positive * 100.0 if positive else 0.0, "unit": "V", "status": "computed",
    }


def compare(expected, actual):
    return _same_with_noise_floor(expected, actual, "seq")


class TestWhatIsTolerated:
    def test_the_floor_is_the_comparisons_own_established_relative_tolerance_not_a_new_number(self):
        assert NOISE_FLOOR == REL == 1e-9                          # `_same` compares floats with rel_tol = 1e-9

    def test_the_4khz_record_observed_on_linux_is_tolerated(self):
        assert compare(sequences(zero=FS4000_ZERO_MAGNITUDE, zero_angle=FS4000_FROZEN_ANGLE),
                       sequences(zero=FS4000_ZERO_MAGNITUDE, zero_angle=FS4000_LINUX_ANGLE)) == []

    def test_a_phasor_a_decade_above_the_floor_is_compared(self):
        problems = compare(sequences(zero=1e-8, zero_angle=1.0), sequences(zero=1e-8, zero_angle=2.0))       # ratio 1e-10 <= floor: skipped
        assert problems == []
        problems = compare(sequences(zero=1e-6, zero_angle=1.0), sequences(zero=1e-6, zero_angle=2.0))       # ratio 1e-8 > floor: compared
        assert any("zero_sequence_angle_deg" in p for p in problems)

    def test_the_angle_difference_observed_on_linux_is_tolerated(self):
        assert compare(sequences(), sequences(zero_angle=LINUX_ZERO_ANGLE)) == []

    @pytest.mark.parametrize("angle", [-179.9, 0.0, 20.3697561161, -123.164660778, 2.92352552702e-05])
    def test_any_angle_of_a_negligible_phasor_is_tolerated(self, angle):
        assert compare(sequences(), sequences(zero_angle=angle)) == []

    def test_a_negligible_phasor_on_the_current_side_too(self):
        wrapper = lambda s: {"body": {"voltage_sequences": sequences(), "current_sequences": s}}      # noqa: E731
        assert compare(wrapper(sequences(positive=10.0, zero=1e-12)), wrapper(sequences(positive=10.0, zero=1e-12, zero_angle=-3.0))) == []

    def test_it_applies_inside_nested_dicts_and_lists_of_a_real_baseline_shape(self):
        shape = lambda a: {"recordings": {"r50": {"sequence_components": {"body": {"voltage_sequences": sequences(zero_angle=a)}}}},     # noqa: E731
                           "list": [{"body": {"voltage_sequences": sequences(zero_angle=a)}}]}
        assert compare(shape(FROZEN_ZERO_ANGLE), shape(LINUX_ZERO_ANGLE)) == []


class TestWhatIsStillDetected:
    def test_the_magnitude_of_a_negligible_phasor_is_still_compared(self):
        problems = compare(sequences(), sequences(zero=5.0e-10, zero_angle=LINUX_ZERO_ANGLE))
        assert any("zero_sequence_magnitude" in p for p in problems)
        assert not any("zero_sequence_angle_deg" in p for p in problems)             # still negligible on both sides: only the magnitude is reported

    def test_a_zero_sequence_that_became_meaningful_is_reported_in_magnitude_and_angle(self):
        problems = compare(sequences(), sequences(zero=3.0, zero_angle=LINUX_ZERO_ANGLE))
        assert any("zero_sequence_magnitude" in p for p in problems)
        assert any("zero_sequence_angle_deg" in p for p in problems)

    def test_a_zero_sequence_that_collapsed_to_noise_is_reported_in_magnitude_and_angle(self):
        problems = compare(sequences(zero=3.0, zero_angle=45.0), sequences(zero_angle=LINUX_ZERO_ANGLE))
        assert any("zero_sequence_magnitude" in p for p in problems)
        assert any("zero_sequence_angle_deg" in p for p in problems)

    def test_the_angle_of_a_meaningful_phasor_is_still_compared_with_the_original_tolerance(self):
        problems = compare(sequences(), sequences(positive_angle=-2.5 + 1e-6))
        assert [p for p in problems if "positive_sequence_angle_deg" in p]
        assert compare(sequences(), sequences(positive_angle=-2.5 + 1e-12)) == []        # inside `_same`'s own tolerance

    def test_a_meaningful_nonzero_negative_sequence_angle_is_compared(self):
        problems = compare(sequences(negative=2.0, negative_angle=10.0), sequences(negative=2.0, negative_angle=11.0))
        assert any("negative_sequence_angle_deg" in p for p in problems)

    def test_the_boundary_is_exactly_the_floor_times_the_scale(self):
        at = NOISE_FLOOR * 100.0
        assert compare(sequences(zero=at, zero_angle=1.0), sequences(zero=at, zero_angle=2.0)) == []
        above = at * 1.1
        assert any("zero_sequence_angle_deg" in p for p in compare(sequences(zero=above, zero_angle=1.0), sequences(zero=above, zero_angle=2.0)))

    def test_one_side_above_the_floor_is_enough_to_compare_the_angle(self):
        above = NOISE_FLOOR * 100.0 * 1.1
        problems = compare(sequences(zero=NOISE_FLOOR * 100.0, zero_angle=1.0), sequences(zero=above, zero_angle=2.0))
        assert any("zero_sequence_angle_deg" in p for p in problems)

    def test_the_floor_is_relative_to_the_scale_of_the_set(self):
        # the same absolute magnitude is negligible against a 1e6 positive sequence and meaningful against a 1e-6 one
        assert compare(sequences(positive=1e6, zero=5e-5, zero_angle=1.0), sequences(positive=1e6, zero=5e-5, zero_angle=2.0)) == []
        assert any("zero_sequence_angle_deg" in p
                   for p in compare(sequences(positive=1e-6, zero=1e-12, zero_angle=1.0), sequences(positive=1e-6, zero=1e-12, zero_angle=2.0)))

    def test_a_set_without_a_positive_sequence_magnitude_has_no_scale_so_nothing_is_skipped(self):
        bare = lambda a: {"zero_sequence_magnitude": FROZEN_ZERO_MAGNITUDE, "zero_sequence_angle_deg": a}      # noqa: E731
        assert any("zero_sequence_angle_deg" in p for p in compare(bare(FROZEN_ZERO_ANGLE), bare(LINUX_ZERO_ANGLE)))

    def test_only_sequence_component_angles_are_ever_skipped(self):
        other = lambda a: {"positive_sequence_magnitude": 100.0, "phasor_angle_deg": a, "phasor_magnitude": 1e-12}      # noqa: E731
        assert any("phasor_angle_deg" in p for p in compare(other(1.0), other(2.0)))

    def test_non_numeric_magnitudes_never_skip(self):
        expected, actual = sequences(), sequences(zero_angle=LINUX_ZERO_ANGLE)
        expected["zero_sequence_magnitude"] = None
        assert "zero_sequence_angle_deg" not in _negligible_angles(expected, actual)
        assert any("zero_sequence_angle_deg" in p for p in compare(expected, actual))

    def test_keys_that_appear_or_disappear_are_still_reported(self):
        expected, actual = sequences(), sequences()
        del actual["zero_sequence_angle_deg"]
        assert compare(expected, actual) != []
        extra = copy.deepcopy(expected)
        extra["new_field"] = 1
        assert any("new_field" in p for p in compare(expected, extra))


class TestTheGlobalToleranceIsNotRelaxed:
    def test_the_original_comparison_still_reports_the_observed_difference(self):
        problems = _same(sequences(), sequences(zero_angle=LINUX_ZERO_ANGLE), "seq")
        assert any("zero_sequence_angle_deg" in p for p in problems)

    def test_the_noise_floor_comparison_agrees_with_the_original_when_nothing_is_negligible(self):
        a, b = sequences(zero=1.5, zero_angle=30.0), sequences(zero=1.5, zero_angle=30.001)
        assert sorted(compare(a, b)) == sorted(_same(a, b, "seq")) != []
        assert compare(a, copy.deepcopy(a)) == _same(a, copy.deepcopy(a), "seq") == []
