"""Golden/unit tests for the pure Overcurrent Analysis v1 domain module
(`app.domain.overcurrent`) -- IEC IDMT curve evaluation, the selected-
time trailing RMS estimator, CT conversion, settings validation, and the
continuous above-pickup duration measurement. See
docs/project-memory/OVERCURRENT_ANALYSIS.md for the feature record and
this project's own implementation report for the exact IEC 60255-151
sources the k/alpha constants were cross-verified against.

Expected IDMT values below are independently computed from the closed-
form formula `t = TMS * k / (M**alpha - 1)` (c=0 for all three IEC
curves), never re-derived from the implementation under test.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.domain.overcurrent import (
    IEC_EXTREMELY_INVERSE,
    IEC_STANDARD_INVERSE,
    IEC_VERY_INVERSE,
    REASON_ANALYSIS_TIME_OUT_OF_RANGE,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    REASON_INSUFFICIENT_WINDOW_HISTORY,
    REASON_NO_SAMPLES,
    RECORDING_BASIS_PRIMARY,
    RECORDING_BASIS_SECONDARY,
    continuous_duration_above_pickup,
    convert_array_to_relay_secondary,
    convert_to_relay_secondary,
    ct_values_valid,
    estimate_trailing_rms_at_time,
    evaluate_idmt_operating_time,
    generate_idmt_curve_points,
    get_characteristic,
    known_characteristics,
    pickup_valid,
    solve_multiple_of_pickup_for_operating_time,
    tms_valid,
)


class TestKnownCharacteristicsRegistry:
    def test_exactly_three_iec_idmt_characteristics(self):
        ids = {c.id for c in known_characteristics()}
        assert ids == {"iec_standard_inverse", "iec_very_inverse", "iec_extremely_inverse"}

    def test_get_characteristic_unknown_id_returns_none(self):
        assert get_characteristic("iec_long_time_inverse") is None
        assert get_characteristic("ansi_moderately_inverse") is None

    def test_constants_match_iec_60255_151_table(self):
        assert IEC_STANDARD_INVERSE.constants.k == pytest.approx(0.14)
        assert IEC_STANDARD_INVERSE.constants.alpha == pytest.approx(0.02)
        assert IEC_VERY_INVERSE.constants.k == pytest.approx(13.5)
        assert IEC_VERY_INVERSE.constants.alpha == pytest.approx(1.0)
        assert IEC_EXTREMELY_INVERSE.constants.k == pytest.approx(80.0)
        assert IEC_EXTREMELY_INVERSE.constants.alpha == pytest.approx(2.0)
        for c in known_characteristics():
            assert c.constants.c == 0.0
            assert c.family == "iec_idmt"


class TestIdmtOperatingTime:
    def test_standard_inverse_worked_example(self):
        """Independently-sourced worked example (11 kV feeder, pickup 100
        A primary, fault current 2000 A primary -> M=20, TMS=0.10,
        Standard Inverse): t ~= 0.2267 s."""
        t = evaluate_idmt_operating_time(IEC_STANDARD_INVERSE.constants, tms=0.10, multiple_of_pickup=20.0)
        assert t == pytest.approx(0.226736, rel=1e-4)

    def test_very_inverse_at_m_equals_2(self):
        # t = TMS * k / (M - 1) = 1.0 * 13.5 / (2 - 1) = 13.5
        t = evaluate_idmt_operating_time(IEC_VERY_INVERSE.constants, tms=1.0, multiple_of_pickup=2.0)
        assert t == pytest.approx(13.5)

    def test_extremely_inverse_at_m_equals_2(self):
        # t = TMS * k / (M^2 - 1) = 1.0 * 80 / (4 - 1) = 26.6667
        t = evaluate_idmt_operating_time(IEC_EXTREMELY_INVERSE.constants, tms=1.0, multiple_of_pickup=2.0)
        assert t == pytest.approx(80.0 / 3.0, rel=1e-9)

    @pytest.mark.parametrize("characteristic", [IEC_STANDARD_INVERSE, IEC_VERY_INVERSE, IEC_EXTREMELY_INVERSE])
    @pytest.mark.parametrize("m", [0.0, 0.5, 1.0])
    def test_m_at_or_below_1_is_never_a_finite_time(self, characteristic, m):
        """Owner instruction: M<=1 must never produce Infinity/NaN/0 --
        it must be an explicit `None`."""
        t = evaluate_idmt_operating_time(characteristic.constants, tms=0.5, multiple_of_pickup=m)
        assert t is None

    def test_tms_scales_linearly(self):
        t_baseline = evaluate_idmt_operating_time(IEC_STANDARD_INVERSE.constants, tms=0.1, multiple_of_pickup=5.0)
        t_doubled = evaluate_idmt_operating_time(IEC_STANDARD_INVERSE.constants, tms=0.2, multiple_of_pickup=5.0)
        assert t_doubled == pytest.approx(t_baseline * 2.0, rel=1e-9)

    @pytest.mark.parametrize(
        "characteristic,m,expected",
        [
            (IEC_STANDARD_INVERSE, 2.0, 0.14 / (2.0 ** 0.02 - 1.0)),
            (IEC_STANDARD_INVERSE, 10.0, 0.14 / (10.0 ** 0.02 - 1.0)),
            (IEC_VERY_INVERSE, 5.0, 13.5 / (5.0 - 1.0)),
            (IEC_VERY_INVERSE, 10.0, 13.5 / (10.0 - 1.0)),
            (IEC_EXTREMELY_INVERSE, 5.0, 80.0 / (25.0 - 1.0)),
            (IEC_EXTREMELY_INVERSE, 10.0, 80.0 / (100.0 - 1.0)),
        ],
    )
    def test_several_known_pickup_multiples(self, characteristic, m, expected):
        t = evaluate_idmt_operating_time(characteristic.constants, tms=1.0, multiple_of_pickup=m)
        assert t == pytest.approx(expected, rel=1e-9)

    @pytest.mark.parametrize("tms", [0.025, 0.1, 0.5, 1.0, 1.2])
    def test_several_tms_values(self, tms):
        t = evaluate_idmt_operating_time(IEC_STANDARD_INVERSE.constants, tms=tms, multiple_of_pickup=3.0)
        assert t == pytest.approx(tms * (0.14 / (3.0 ** 0.02 - 1.0)), rel=1e-9)


class TestSolveMultipleOfPickupForOperatingTime:
    """2026-09-12 chart-viewport-alignment UAT follow-up: the exact
    algebraic inverse of `evaluate_idmt_operating_time()`, used so the
    Overcurrent chart's visible curve segment can enter/exit exactly at
    the current chart viewport's own Y boundaries rather than at
    whatever coarse pre-sampled point happens to fall inside it. See
    `solve_multiple_of_pickup_for_operating_time()`'s own docstring."""

    @pytest.mark.parametrize("characteristic", [IEC_STANDARD_INVERSE, IEC_VERY_INVERSE, IEC_EXTREMELY_INVERSE])
    @pytest.mark.parametrize("tms", [0.025, 0.1, 0.5, 1.0, 1.2])
    @pytest.mark.parametrize("target_t", [1000.0, 500.0, 100.0, 10.0, 1.0])
    def test_round_trips_exactly_through_the_forward_formula(self, characteristic, tms, target_t):
        """`evaluate_idmt_operating_time(inverse(t)) == t` to tight
        floating-point tolerance, for every characteristic/TMS/target-
        time combination the task's own final-report table asks for."""
        m = solve_multiple_of_pickup_for_operating_time(characteristic.constants, tms, target_t)
        assert m is not None
        assert m > 1.0
        assert math.isfinite(m)
        recovered_t = evaluate_idmt_operating_time(characteristic.constants, tms, m)
        assert recovered_t is not None
        assert recovered_t == pytest.approx(target_t, rel=1e-9)

    def test_standard_inverse_worked_example_inverted(self):
        """Same worked example as `TestIdmtOperatingTime` above, solved
        in the other direction: M=20, TMS=0.10 -> t~=0.226736 -> solving
        for M given that t must recover ~20.0."""
        m = solve_multiple_of_pickup_for_operating_time(IEC_STANDARD_INVERSE.constants, tms=0.10, operating_time_seconds=0.226736)
        assert m == pytest.approx(20.0, rel=1e-4)

    @pytest.mark.parametrize("bad_t", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_positive_or_non_finite_operating_time(self, bad_t):
        assert solve_multiple_of_pickup_for_operating_time(IEC_STANDARD_INVERSE.constants, tms=0.1, operating_time_seconds=bad_t) is None

    @pytest.mark.parametrize("bad_tms", [0.0, -0.5, float("nan"), float("inf")])
    def test_rejects_non_positive_or_non_finite_tms(self, bad_tms):
        assert solve_multiple_of_pickup_for_operating_time(IEC_STANDARD_INVERSE.constants, tms=bad_tms, operating_time_seconds=10.0) is None

    def test_never_returns_nan_or_infinity(self):
        for characteristic in (IEC_STANDARD_INVERSE, IEC_VERY_INVERSE, IEC_EXTREMELY_INVERSE):
            for bad_t in (0.0, -5.0, float("nan"), float("inf")):
                m = solve_multiple_of_pickup_for_operating_time(characteristic.constants, tms=0.5, operating_time_seconds=bad_t)
                assert m is None or math.isfinite(m)


class TestIdmtCurvePoints:
    def test_curve_is_monotonically_decreasing_with_m(self):
        points = generate_idmt_curve_points(IEC_STANDARD_INVERSE.constants, tms=0.2)
        times = [t for _m, t in points]
        assert all(earlier > later for earlier, later in zip(times, times[1:]))

    def test_curve_never_includes_m_at_or_below_1(self):
        points = generate_idmt_curve_points(IEC_STANDARD_INVERSE.constants, tms=0.2, m_min=1.01)
        assert all(m > 1.0 for m, _t in points)

    def test_curve_point_count_respects_num_points(self):
        points = generate_idmt_curve_points(IEC_VERY_INVERSE.constants, tms=0.2, num_points=25)
        assert len(points) == 25

    def test_default_domain_covers_the_full_200x_display_bound(self):
        """2026-09-12 chart-viewport UAT follow-up: the default curve
        request must span the full supported DISPLAY domain (frontend
        absolute chart bound, 200x pickup) in one fetch, so a chart
        zoom/pan viewport change never needs to re-fetch curve data."""
        points = generate_idmt_curve_points(IEC_STANDARD_INVERSE.constants, tms=0.2)
        m_values = [m for m, _t in points]
        assert max(m_values) == pytest.approx(200.0, rel=1e-6)
        assert min(m_values) == pytest.approx(1.01, rel=1e-6)
        assert len(points) == 90


class TestSettingsValidation:
    @pytest.mark.parametrize("tms", [0.025, 0.1, 1.0, 1.2])
    def test_tms_valid_within_range(self, tms):
        assert tms_valid(tms) is True

    @pytest.mark.parametrize("tms", [0.0, -0.1, 0.024, 1.21, 100.0, float("inf"), float("nan")])
    def test_tms_invalid_outside_range(self, tms):
        assert tms_valid(tms) is False

    @pytest.mark.parametrize("pickup", [0.01, 1.0, 1000.0])
    def test_pickup_valid_positive(self, pickup):
        assert pickup_valid(pickup) is True

    @pytest.mark.parametrize("pickup", [0.0, -1.0, float("inf"), float("nan")])
    def test_pickup_invalid(self, pickup):
        assert pickup_valid(pickup) is False

    def test_ct_values_valid_both_positive(self):
        assert ct_values_valid(1000.0, 1.0) is True

    @pytest.mark.parametrize("primary,secondary", [(0.0, 1.0), (1000.0, 0.0), (-1000.0, 1.0), (1000.0, -1.0)])
    def test_ct_values_invalid(self, primary, secondary):
        assert ct_values_valid(primary, secondary) is False


class TestCtConversion:
    def test_primary_to_secondary_conversion(self):
        # CT 1000:1 -- 4200 A primary -> 4.2 A secondary.
        relay_current = convert_to_relay_secondary(
            4200.0, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1000.0, ct_secondary=1.0,
            measured_unit="A",
        )
        assert relay_current == pytest.approx(4.2)

    def test_secondary_recording_passes_through_unchanged(self):
        relay_current = convert_to_relay_secondary(
            4.2, recording_basis=RECORDING_BASIS_SECONDARY, ct_primary=None, ct_secondary=None,
            measured_unit="A",
        )
        assert relay_current == pytest.approx(4.2)

    def test_kA_primary_recording_is_normalized_before_ct_ratio(self):
        """The trigger bug: 2.4 kA primary through a 1200:1 CT must
        become 2.0 A secondary, not 0.002 A (which is what a raw
        `2.4 * (1/1200)` -- treating "2.4" as if it were already
        amperes -- would incorrectly produce)."""
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="kA",
        )
        assert relay_current == pytest.approx(2.0)

    def test_kA_secondary_recording_is_normalized_to_amperes(self):
        """A `secondary` recording declared in kA must still be
        normalized to amperes -- 2.4 kA secondary is 2400 A, never the
        raw number 2.4 treated as if it were already amperes."""
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_SECONDARY, ct_primary=None, ct_secondary=None,
            measured_unit="kA",
        )
        assert relay_current == pytest.approx(2400.0)

    def test_case_variant_kA_alias_is_also_normalized(self):
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="KA",
        )
        assert relay_current == pytest.approx(2.0)

    def test_unsupported_unit_returns_none_never_assumes_amperes(self):
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="furlongs",
        )
        assert relay_current is None

    def test_blank_unit_returns_none(self):
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_SECONDARY, ct_primary=None, ct_secondary=None,
            measured_unit="",
        )
        assert relay_current is None

    def test_none_unit_returns_none(self):
        relay_current = convert_to_relay_secondary(
            2.4, recording_basis=RECORDING_BASIS_SECONDARY, ct_primary=None, ct_secondary=None,
            measured_unit=None,
        )
        assert relay_current is None


class TestArrayCtConversion:
    def test_kA_primary_array_is_normalized_before_ct_ratio(self):
        values = np.array([1.0, 2.0, 2.4])
        relay_values = convert_array_to_relay_secondary(
            values, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="kA",
        )
        np.testing.assert_allclose(relay_values, [1000.0 / 1200.0, 2000.0 / 1200.0, 2400.0 / 1200.0])

    def test_secondary_array_normalized_to_amperes_no_ct_ratio(self):
        values = np.array([1.0, 2.4])
        relay_values = convert_array_to_relay_secondary(
            values, recording_basis=RECORDING_BASIS_SECONDARY, ct_primary=None, ct_secondary=None,
            measured_unit="kA",
        )
        np.testing.assert_allclose(relay_values, [1000.0, 2400.0])

    def test_never_mutates_input_array(self):
        values = np.array([1.0, 2.0, 2.4])
        original = values.copy()
        convert_array_to_relay_secondary(
            values, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="kA",
        )
        np.testing.assert_array_equal(values, original)

    def test_unsupported_unit_returns_none(self):
        values = np.array([1.0, 2.0])
        relay_values = convert_array_to_relay_secondary(
            values, recording_basis=RECORDING_BASIS_PRIMARY, ct_primary=1200.0, ct_secondary=1.0,
            measured_unit="furlongs",
        )
        assert relay_values is None


def _sine_samples(*, amp_rms, freq_hz, sample_rate_hz, duration_s, phase_deg=0.0):
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n) / sample_rate_hz
    amp_peak = amp_rms * np.sqrt(2.0)
    values = amp_peak * np.cos(2.0 * np.pi * freq_hz * t + np.radians(phase_deg))
    return t, values


class TestTrailingRmsAtTime:
    def test_clean_sinusoid_recovers_known_rms(self):
        """Same proof shape as `test_phasor_domain.py::TestRmsNormalization`
        -- x(t) = sqrt(2)*40*cos(2*pi*50*t) -> ~40 A RMS, never the 56.57 A
        peak."""
        t, v = _sine_samples(amp_rms=40.0, freq_hz=50.0, sample_rate_hz=5000.0, duration_s=2.0)
        est = estimate_trailing_rms_at_time(t, v, analysis_time=1.5, reference_frequency_hz=50.0)
        assert est.available is True
        assert est.value == pytest.approx(40.0, rel=1e-3)

    def test_insufficient_window_history_near_recording_start(self):
        t, v = _sine_samples(amp_rms=10.0, freq_hz=50.0, sample_rate_hz=5000.0, duration_s=1.0)
        est = estimate_trailing_rms_at_time(t, v, analysis_time=0.005, reference_frequency_hz=50.0)
        assert est.available is False
        assert est.reason_code == REASON_INSUFFICIENT_WINDOW_HISTORY

    def test_analysis_time_out_of_range(self):
        t, v = _sine_samples(amp_rms=10.0, freq_hz=50.0, sample_rate_hz=5000.0, duration_s=1.0)
        est = estimate_trailing_rms_at_time(t, v, analysis_time=5.0, reference_frequency_hz=50.0)
        assert est.available is False
        assert est.reason_code == REASON_ANALYSIS_TIME_OUT_OF_RANGE

    def test_no_samples(self):
        est = estimate_trailing_rms_at_time(
            np.array([], dtype=np.float64), np.array([], dtype=np.float64),
            analysis_time=1.0, reference_frequency_hz=50.0,
        )
        assert est.available is False
        assert est.reason_code == REASON_NO_SAMPLES

    def test_insufficient_sampling_density(self):
        # Only 3 samples/cycle at 50 Hz (150 Hz sample rate) -- below the
        # OVERCURRENT_MIN_SAMPLES_PER_CYCLE=4 floor.
        t, v = _sine_samples(amp_rms=10.0, freq_hz=50.0, sample_rate_hz=150.0, duration_s=2.0)
        est = estimate_trailing_rms_at_time(t, v, analysis_time=1.0, reference_frequency_hz=50.0)
        assert est.available is False
        assert est.reason_code == REASON_INSUFFICIENT_SAMPLING_DENSITY


class TestContinuousDurationAbovePickup:
    def _step_current(self, *, jump_at, level_before, level_after, sample_rate_hz=5000.0, duration_s=3.0, freq_hz=50.0):
        """A synthetic current that is a small (below-pickup) sinusoid
        before `jump_at`, then a large (above-pickup) sinusoid after --
        RMS envelope should read ~level_before, then ~level_after, once
        each trailing window has fully slid past the step."""
        n = int(round(duration_s * sample_rate_hz))
        t = np.arange(n) / sample_rate_hz
        amp_before = level_before * np.sqrt(2.0)
        amp_after = level_after * np.sqrt(2.0)
        amp = np.where(t < jump_at, amp_before, amp_after)
        v = amp * np.cos(2.0 * np.pi * freq_hz * t)
        return t, v

    def test_deterministic_duration_when_seeking_directly_into_the_event(self):
        """Owner instruction: seeking directly to a point in the recording
        must calculate the correct event-derived duration -- never
        dependent on 'how long Play has been pressed'. Called fresh, with
        no prior call, directly at a time well after the jump."""
        t, v = self._step_current(jump_at=1.0, level_before=0.5, level_after=5.0)
        pickup = 1.0  # well above level_before, well below level_after
        result = continuous_duration_above_pickup(t, v, analysis_time=2.0, reference_frequency_hz=50.0, pickup_current_secondary=pickup)
        assert result.available is True
        # Duration since the jump (~1.0s) to analysis_time (2.0s) is ~1.0s,
        # allowing ~one window's worth of slew for the RMS envelope itself
        # to rise past pickup.
        assert result.duration_seconds == pytest.approx(1.0, abs=0.03)

    def test_reset_to_zero_when_current_drops_back_below_pickup(self):
        t, v = self._step_current(jump_at=1.0, level_before=5.0, level_after=0.5)
        pickup = 1.0  # below level_before (was above), above level_after (now below)
        result = continuous_duration_above_pickup(t, v, analysis_time=2.0, reference_frequency_hz=50.0, pickup_current_secondary=pickup)
        assert result.available is True
        assert result.duration_seconds == pytest.approx(0.0, abs=1e-6)

    def test_playback_speed_never_affects_the_result(self):
        """The function has no notion of wall-clock/speed at all -- calling
        it twice with the SAME analysis_time must be bit-for-bit
        identical regardless of anything resembling 'how it was reached'."""
        t, v = self._step_current(jump_at=1.0, level_before=0.5, level_after=5.0)
        r1 = continuous_duration_above_pickup(t, v, analysis_time=2.5, reference_frequency_hz=50.0, pickup_current_secondary=1.0)
        r2 = continuous_duration_above_pickup(t, v, analysis_time=2.5, reference_frequency_hz=50.0, pickup_current_secondary=1.0)
        assert r1.duration_seconds == r2.duration_seconds

    def test_duration_grows_monotonically_while_sustained_above_pickup(self):
        t, v = self._step_current(jump_at=1.0, level_before=0.5, level_after=5.0)
        d_early = continuous_duration_above_pickup(t, v, analysis_time=1.5, reference_frequency_hz=50.0, pickup_current_secondary=1.0).duration_seconds
        d_late = continuous_duration_above_pickup(t, v, analysis_time=2.5, reference_frequency_hz=50.0, pickup_current_secondary=1.0).duration_seconds
        assert d_late > d_early
