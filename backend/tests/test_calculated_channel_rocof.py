"""ROCOF -- Rate of Change of Frequency calculated channel (DEC-190).

Domain tests check `evaluate_rocof()` against analytical or independently
calculated references; service tests cover eligibility, null policy,
smoothing validation and lifecycle; API tests run the real end-to-end flow
(upload -> parse -> retain -> calculate -> waveform -> delete).
"""

from __future__ import annotations

import io
import time as time_module

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import (
    NULL_POLICY_ESTIMATE,
    NULL_POLICY_PROPAGATE,
    NULL_POLICY_REQUIRE_MANUAL,
    NULL_POLICY_ZERO,
    OP_MULTIPLY_CONSTANT,
    OP_ROCOF,
    ChannelRef,
    evaluate_rocof,
    rocof_smoothing_window_valid,
)
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    ROCOF_STATUS_NOT_FREQUENCY,
    ROCOF_STATUS_SUITABLE,
    ROCOF_STATUS_UNCERTAIN,
    check_rocof_eligibility,
    create_calculated_channel,
    delete_calculated_channel,
    remove_calculated_channels_for_source,
)
from app.services.errors import (
    CalculatedChannelHasDependentsError,
    InvalidNullPolicyError,
    InvalidOperationArityError,
    InvalidRocofSmoothingError,
    RequireManualValueNullError,
    RocofInsufficientDataError,
    RocofOverrideRequiredError,
)
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_calculated_channel_service import WS, _active_source

# ---------------------------------------------------------------------------
# Domain: evaluate_rocof()
# ---------------------------------------------------------------------------


def _uniform(duration: float, dt: float) -> np.ndarray:
    return np.arange(0.0, duration + dt / 2, dt)


def _naive_central(t: np.ndarray, f: np.ndarray) -> np.ndarray:
    """The simplified `(f[i+1]-f[i-1])/(t[i+1]-t[i-1])` formula, kept only
    to prove the unequal-spacing formula is genuinely different/better."""
    return (f[2:] - f[:-2]) / (t[2:] - t[:-2])


class TestRocofAnalyticalReferences:
    def test_constant_frequency_gives_zero(self):
        t = _uniform(1.0, 0.01)
        assert np.all(evaluate_rocof(t, np.full_like(t, 50.0)) == 0.0)

    def test_linear_decline_50_to_49_5_in_half_second_is_minus_one_hz_per_second(self):
        t = _uniform(0.5, 0.01)
        f = np.linspace(50.0, 49.5, t.size)
        out = evaluate_rocof(t, f)
        assert out.shape == t.shape
        # every sample -- interior AND both one-sided boundaries
        np.testing.assert_allclose(out, -1.0, rtol=0, atol=1e-9)

    def test_linear_recovery_is_positive(self):
        t = _uniform(0.5, 0.01)
        out = evaluate_rocof(t, np.linspace(49.5, 50.0, t.size))
        assert np.all(out > 0)
        np.testing.assert_allclose(out, 1.0, atol=1e-9)

    def test_quadratic_interior_is_exact(self):
        # f = 50 - 2 t^2  =>  ROCOF = -4 t, and a 3-point central formula
        # is exact for quadratics.
        t = _uniform(1.0, 0.005)
        out = evaluate_rocof(t, 50.0 - 2.0 * t**2)
        np.testing.assert_allclose(out[1:-1], -4.0 * t[1:-1], atol=1e-9)

    def test_nonlinear_disturbance_with_varying_rocof(self):
        # Damped swing: f = 50 - A exp(-t/tau) sin(w t)
        t = _uniform(5.0, 0.002)
        a, tau, w = 0.4, 1.5, 2 * np.pi * 0.8
        f = 50.0 - a * np.exp(-t / tau) * np.sin(w * t)
        exact = -a * np.exp(-t / tau) * (w * np.cos(w * t) - np.sin(w * t) / tau)
        out = evaluate_rocof(t, f)
        np.testing.assert_allclose(out[1:-1], exact[1:-1], atol=2e-4)  # O(h^2) error
        assert out.min() < -1.0 and out.max() > 1.0  # genuinely varying sign/magnitude

    @pytest.mark.parametrize("dt", [0.0002, 0.001, 0.02, 0.1])
    def test_different_sampling_intervals_same_rocof(self, dt):
        t = _uniform(2.0, dt)
        out = evaluate_rocof(t, 50.0 - 0.75 * t)
        np.testing.assert_allclose(out, -0.75, atol=1e-9)


class TestRocofIrregularTimestamps:
    def test_unequal_spacing_formula_exact_for_quadratic_where_naive_is_not(self):
        t = np.array([0.0, 1.0, 4.0, 5.0, 9.0, 10.0, 14.0])
        f = 50.0 + 0.01 * t**2  # ROCOF = 0.02 t
        out = evaluate_rocof(t, f)
        np.testing.assert_allclose(out[1:-1], 0.02 * t[1:-1], atol=1e-12)
        naive = _naive_central(t, f)
        assert np.max(np.abs(naive - 0.02 * t[1:-1])) > 0.01  # the naive form is visibly wrong

    def test_jittered_timestamps_match_independent_reference(self):
        rng = np.random.default_rng(7)
        t = np.cumsum(rng.uniform(0.0005, 0.0015, 4000))
        f = 50.0 + 0.2 * np.sin(2 * np.pi * 0.5 * t) - 0.05 * t**2
        out = evaluate_rocof(t, f)
        reference = np.gradient(f, t)  # NumPy's own non-uniform 2nd-order interior formula
        np.testing.assert_allclose(out[1:-1], reference[1:-1], rtol=1e-9, atol=1e-9)

    def test_uniform_spacing_reduces_to_simple_central_difference(self):
        t = _uniform(1.0, 0.01)
        f = 50.0 + np.sin(3 * t)
        np.testing.assert_allclose(evaluate_rocof(t, f)[1:-1], _naive_central(t, f), atol=1e-12)


class TestRocofInvalidData:
    def test_duplicate_timestamps_are_never_differentiated_across(self):
        t = np.array([0.0, 0.1, 0.2, 0.2, 0.3, 0.4])
        f = np.array([50.0, 49.9, 49.8, 49.8, 49.7, 49.6])
        out = evaluate_rocof(t, f)
        assert np.all(np.isfinite(out)) and not np.any(np.isinf(out))
        np.testing.assert_allclose(out, -1.0, atol=1e-9)

    def test_duplicate_timestamp_with_conflicting_values_does_not_blow_up(self):
        t = np.array([0.0, 0.1, 0.2, 0.2, 0.3, 0.4])
        f = np.array([50.0, 49.9, 49.8, 40.0, 49.7, 49.6])
        out = evaluate_rocof(t, f)
        assert not np.any(np.isinf(out))
        assert np.nanmax(np.abs(out)) < 200  # 10 Hz step is not divided by 0 s

    def test_non_monotonic_timestamps_are_a_break_not_a_derivative(self):
        t = np.array([0.0, 0.1, 0.2, 0.15, 0.25, 0.35, 0.45])
        f = 50.0 - 1.0 * t
        out = evaluate_rocof(t, f)
        assert not np.any(np.isinf(out))
        # Sample 3 (t=0.15) sits after a backwards step; it is differentiated only
        # from its valid forward neighbours, and the backwards interval is unused.
        np.testing.assert_allclose(out[np.isfinite(out)], -1.0, atol=1e-9)

    def test_nan_sample_is_blank_and_neighbours_become_one_sided(self):
        t = _uniform(0.9, 0.1)
        f = 50.0 - 2.0 * t
        f[4] = np.nan
        out = evaluate_rocof(t, f)
        assert np.isnan(out[4])
        assert np.isfinite(out[3]) and np.isfinite(out[5])
        np.testing.assert_allclose(out[np.isfinite(out)], -2.0, atol=1e-9)

    def test_inf_sample_treated_as_invalid(self):
        t = _uniform(0.9, 0.1)
        f = 50.0 - 2.0 * t
        f[4] = np.inf
        out = evaluate_rocof(t, f)
        assert np.isnan(out[4]) and not np.any(np.isinf(out))

    def test_isolated_valid_sample_between_nans_is_blank(self):
        t = _uniform(0.6, 0.1)
        f = 50.0 - t
        f[1] = f[3] = np.nan
        assert np.isnan(evaluate_rocof(t, f)[2])

    def test_non_finite_timestamp_is_blank_without_poisoning_the_rest(self):
        t = _uniform(0.9, 0.1)
        f = 50.0 - 2.0 * t
        t[5] = np.nan
        out = evaluate_rocof(t, f)
        assert np.isnan(out[5])
        np.testing.assert_allclose(out[np.isfinite(out)], -2.0, atol=1e-9)

    def test_recording_gap_is_a_discontinuity(self):
        # 1 Hz/s ramp, a 5 s gap (500x the 0.01 s interval) and a frequency jump of +3 Hz.
        t1 = _uniform(1.0, 0.01)
        t2 = _uniform(1.0, 0.01) + 6.0
        t = np.concatenate([t1, t2])
        f = np.concatenate([50.0 + 1.0 * t1, 55.0 + 1.0 * t2])
        out = evaluate_rocof(t, f)
        np.testing.assert_allclose(out, 1.0, atol=1e-9)  # nothing computed across the gap

    @pytest.mark.parametrize("n", [0, 1, 2])
    def test_very_short_recordings(self, n):
        t = np.array([0.0, 0.1])[:n]
        f = np.array([50.0, 49.9])[:n]
        out = evaluate_rocof(t, f)
        assert out.shape == (n,)
        if n == 2:  # a single usable interval gives the one-sided slope at both ends
            np.testing.assert_allclose(out, -1.0, atol=1e-9)
        else:
            assert out.size == 0 or np.all(np.isnan(out))

    def test_all_invalid_input_is_all_nan(self):
        t = _uniform(0.5, 0.1)
        assert np.all(np.isnan(evaluate_rocof(t, np.full_like(t, np.nan))))

    def test_float32_input(self):
        t = _uniform(0.5, 0.01).astype(np.float32)
        f = np.linspace(50.0, 49.5, t.size).astype(np.float32)
        np.testing.assert_allclose(evaluate_rocof(t, f), -1.0, atol=1e-2)


def _brute_force_window_mean(t: np.ndarray, raw: np.ndarray, window: float) -> np.ndarray:
    """Independent O(N^2) reference of the smoothing contract: symmetric
    window clamped to the nearest end of the contiguous finite segment."""
    out = np.full(t.size, np.nan)
    finite = np.isfinite(raw)
    for i in range(t.size):
        if not finite[i]:
            continue
        lo = i
        while lo > 0 and finite[lo - 1]:
            lo -= 1
        hi = i
        while hi < t.size - 1 and finite[hi + 1]:
            hi += 1
        half = min(window / 2, t[i] - t[lo], t[hi] - t[i])
        sel = (t >= t[i] - half - 1e-9) & (t <= t[i] + half + 1e-9)
        sel[:lo] = False
        sel[hi + 1:] = False
        out[i] = raw[sel].mean()
    return out


class TestRocofSmoothing:
    def test_matches_brute_force_reference_on_irregular_data_with_nans(self):
        rng = np.random.default_rng(3)
        t = np.cumsum(rng.uniform(0.004, 0.006, 600))
        f = 50.0 + 0.3 * np.sin(2 * np.pi * 0.6 * t) + rng.normal(0, 0.002, t.size)
        f[200:204] = np.nan
        f[450] = np.nan
        raw = evaluate_rocof(t, f)
        smoothed = evaluate_rocof(t, f, 0.1)
        reference = _brute_force_window_mean(t, raw, 0.1)
        np.testing.assert_allclose(smoothed, reference, atol=1e-9, equal_nan=True)

    def test_reduces_noise_and_preserves_the_underlying_ramp(self):
        rng = np.random.default_rng(1)
        t = _uniform(5.0, 0.001)
        f = 50.0 - 0.5 * t + rng.normal(0, 0.003, t.size)
        raw = evaluate_rocof(t, f)
        smooth = evaluate_rocof(t, f, 0.5)
        assert np.std(smooth) < 0.1 * np.std(raw)
        np.testing.assert_allclose(np.mean(smooth[1000:-1000]), -0.5, atol=0.01)

    def test_zero_phase_shift(self):
        # A Gaussian ROCOF pulse (frequency = integral of it) stays centred.
        t = _uniform(4.0, 0.002)
        f = 50.0 + 0.5 * np.tanh((t - 2.0) / 0.2)
        raw = evaluate_rocof(t, f)
        smooth = evaluate_rocof(t, f, 0.3)
        assert abs(t[np.argmax(smooth)] - t[np.argmax(raw)]) <= 0.002

    def test_window_clamps_to_zero_width_at_the_recording_edges(self):
        t = _uniform(1.0, 0.01)
        raw = evaluate_rocof(t, 50.0 + np.sin(5 * t))
        smooth = evaluate_rocof(t, 50.0 + np.sin(5 * t), 0.4)
        assert smooth[0] == pytest.approx(raw[0]) and smooth[-1] == pytest.approx(raw[-1])

    def test_never_averages_across_a_gap(self):
        t = np.concatenate([_uniform(1.0, 0.01), _uniform(1.0, 0.01) + 5.0])
        f = np.concatenate([50.0 - 1.0 * t[:101], 60.0 + 2.0 * (t[101:] - 5.0)])
        smooth = evaluate_rocof(t, f, 0.5)
        np.testing.assert_allclose(smooth[:101], -1.0, atol=1e-9)
        np.testing.assert_allclose(smooth[101:], 2.0, atol=1e-9)

    def test_blank_samples_stay_blank(self):
        t = _uniform(1.0, 0.01)
        f = 50.0 - t
        f[50] = np.nan
        smooth = evaluate_rocof(t, f, 0.2)
        assert np.isnan(smooth[50]) and np.isfinite(smooth[49]) and np.isfinite(smooth[51])

    @pytest.mark.parametrize(
        "value,ok",
        [(100, True), (0.5, True), (0, False), (-1, False), (True, False), (None, False), ("100", False), (float("nan"), False), (float("inf"), False)],
    )
    def test_window_validity(self, value, ok):
        assert rocof_smoothing_window_valid(value) is ok


class TestRocofPerformance:
    def test_two_million_samples_raw_and_smoothed(self):
        n = 2_000_000
        t = np.arange(n) * 0.0002  # 5 kHz, 400 s
        f = 50.0 - 0.01 * t
        f[::997] = np.nan
        started = time_module.perf_counter()
        raw = evaluate_rocof(t, f)
        smooth = evaluate_rocof(t, f, 0.2)
        elapsed = time_module.perf_counter() - started
        assert elapsed < 10.0, f"ROCOF over {n} samples took {elapsed:.1f}s"
        # accuracy holds over the whole long record (stable cumulative sums)
        np.testing.assert_allclose(raw[np.isfinite(raw)], -0.01, atol=1e-7)
        np.testing.assert_allclose(smooth[np.isfinite(smooth)], -0.01, atol=1e-7)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _freq_source(
    registries, *, source_id="src1", t=None, f=None, unit="Hz", engineering_type="Frequency", start_time=None
):
    source_registry, _ = registries
    t = _uniform(1.0, 0.01) if t is None else t
    f = (50.0 - 0.5 * t) if f is None else f
    kwargs = {} if start_time is None else {"start_time": start_time}
    source_registry.add(_active_source(
        source_id=source_id, time=t, channels={"F": f}, units={"F": unit},
        engineering_types={"F": engineering_type}, **kwargs,
    ))
    return t, f


def _rocof(registries, *, name="ROCOF (F)", source_id="src1", channel="F", parameters=None, **kwargs):
    source_registry, calc_registry = registries
    return create_calculated_channel(
        workspace_id=WS, name=name, operation=OP_ROCOF,
        inputs=[ChannelRef(kind="source", source_id=source_id, channel_name=channel)],
        parameters=parameters or {}, source_registry=source_registry, calc_registry=calc_registry, **kwargs,
    )


class TestRocofEligibility:
    def test_frequency_is_suitable(self):
        assert check_rocof_eligibility("Frequency").status == ROCOF_STATUS_SUITABLE
        assert not check_rocof_eligibility("Frequency").override_required

    def test_undefined_is_uncertain_and_needs_override(self):
        result = check_rocof_eligibility("Undefined")
        assert result.status == ROCOF_STATUS_UNCERTAIN and result.override_required

    @pytest.mark.parametrize("kind", ["Voltage", "Current", "Power", "ROCOF"])
    def test_known_non_frequency_needs_override(self, kind):
        result = check_rocof_eligibility(kind)
        assert result.status == ROCOF_STATUS_NOT_FREQUENCY and result.override_required
        assert kind in result.reason


class TestRocofCreate:
    def test_creates_hz_per_second_channel_with_documented_parameters(self, registries):
        t, _ = _freq_source(registries)
        channel = _rocof(registries)
        assert channel.unit == "Hz/s"
        assert channel.operation == OP_ROCOF
        assert channel.engineering_type == "ROCOF"
        assert channel.parameters == {
            "method": "nonuniform_central_difference", "boundary": "one_sided_secant",
            "smoothing": "none", "smoothing_window_ms": None,
        }
        np.testing.assert_allclose(channel.values, -0.5, atol=1e-9)
        # time/timebase inherited VERBATIM -> follows the source's sync/global-t0 placement
        np.testing.assert_array_equal(channel.time, t)
        assert channel.reference_source_id == "src1"
        assert channel.voltage_representation is None and channel.phase_member is None

    def test_source_arrays_are_not_mutated(self, registries):
        t, f = _freq_source(registries, f=np.concatenate([[50.0], 50.0 - 0.1 * _uniform(1.0, 0.01)[1:]]))
        source_registry, _ = registries
        before = source_registry.get(WS, "src1").record.waveform_data["F"].to_numpy().copy()
        _rocof(registries)
        np.testing.assert_array_equal(source_registry.get(WS, "src1").record.waveform_data["F"].to_numpy(), before)

    def test_hz_unit_without_engineering_type_still_requires_override_in_service(self, registries):
        # The service trusts the already-classified engineering_type only.
        _freq_source(registries, engineering_type="Undefined")
        with pytest.raises(RocofOverrideRequiredError):
            _rocof(registries)

    def test_override_allows_unidentified_channel_and_output_is_still_rocof(self, registries):
        _freq_source(registries, unit="", engineering_type="Undefined")
        channel = _rocof(registries, override=True)
        assert channel.unit == "Hz/s" and channel.engineering_type == "ROCOF"

    def test_voltage_input_blocked_without_override_allowed_with(self, registries):
        _freq_source(registries, unit="V", engineering_type="Voltage")
        with pytest.raises(RocofOverrideRequiredError):
            _rocof(registries)
        assert _rocof(registries, override=True).unit == "Hz/s"

    def test_calculated_frequency_input_inherits_suitability(self, registries):
        source_registry, calc_registry = registries
        _freq_source(registries)
        scaled = create_calculated_channel(
            workspace_id=WS, name="F x1", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="F")],
            parameters={"constant": 1.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert scaled.engineering_type == "Frequency"
        channel = create_calculated_channel(
            workspace_id=WS, name="ROCOF (F x1)", operation=OP_ROCOF,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=scaled.id)], parameters={},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.dependency_ids == [scaled.id]
        np.testing.assert_allclose(channel.values, -0.5, atol=1e-9)

    def test_rocof_of_rocof_requires_override(self, registries):
        source_registry, calc_registry = registries
        _freq_source(registries)
        first = _rocof(registries)
        with pytest.raises(RocofOverrideRequiredError):
            create_calculated_channel(
                workspace_id=WS, name="ROCOF of ROCOF", operation=OP_ROCOF,
                inputs=[ChannelRef(kind="calculated", calculated_channel_id=first.id)], parameters={},
                source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_exactly_one_input(self, registries):
        source_registry, calc_registry = registries
        _freq_source(registries)
        ref = ChannelRef(kind="source", source_id="src1", channel_name="F")
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="x", operation=OP_ROCOF, inputs=[ref, ref], parameters={},
                source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_too_few_samples_rejected_and_nothing_registered(self, registries):
        _freq_source(registries, t=np.array([0.0, 0.1]), f=np.array([50.0, 49.9]))
        _, calc_registry = registries
        with pytest.raises(RocofInsufficientDataError):
            _rocof(registries)
        assert calc_registry.list_for_workspace(WS) == []

    def test_all_duplicate_timestamps_rejected(self, registries):
        _freq_source(registries, t=np.array([1.0, 1.0, 1.0, 1.0]), f=np.array([50.0, 49.9, 49.8, 49.7]))
        with pytest.raises(RocofInsufficientDataError):
            _rocof(registries)

    def test_irregular_timestamps_through_the_service(self, registries):
        t = np.array([0.0, 1.0, 4.0, 5.0, 9.0, 10.0, 14.0])
        _freq_source(registries, t=t, f=50.0 + 0.01 * t**2)
        np.testing.assert_allclose(_rocof(registries).values[1:-1], 0.02 * t[1:-1], atol=1e-12)


class TestRocofNullPolicy:
    def _with_gap(self, registries):
        t = _uniform(1.0, 0.01)
        f = 50.0 - 0.5 * t
        f[40] = np.nan
        _freq_source(registries, t=t, f=f)

    def test_propagate_leaves_a_blank_sample_and_never_computes_across_it(self, registries):
        self._with_gap(registries)
        channel = _rocof(registries, null_policy=NULL_POLICY_PROPAGATE)
        assert np.isnan(channel.values[40]) and np.isfinite(channel.values[39])
        np.testing.assert_allclose(channel.values[np.isfinite(channel.values)], -0.5, atol=1e-9)

    def test_treat_null_as_zero_is_rejected(self, registries):
        self._with_gap(registries)
        with pytest.raises(InvalidNullPolicyError, match="0 Hz"):
            _rocof(registries, null_policy=NULL_POLICY_ZERO)

    def test_require_manual_value_blocks(self, registries):
        self._with_gap(registries)
        with pytest.raises(RequireManualValueNullError):
            _rocof(registries, null_policy=NULL_POLICY_REQUIRE_MANUAL)

    def test_estimate_fills_the_gap_first(self, registries):
        self._with_gap(registries)
        channel = _rocof(
            registries, null_policy=NULL_POLICY_ESTIMATE, estimation_method="linear",
            max_gap_value=3, max_gap_unit="samples",
        )
        assert np.all(np.isfinite(channel.values))
        np.testing.assert_allclose(channel.values, -0.5, atol=1e-9)


class TestRocofSmoothingParameters:
    def test_moving_average_recorded_and_applied(self, registries):
        rng = np.random.default_rng(5)
        t = _uniform(2.0, 0.001)
        _freq_source(registries, t=t, f=50.0 - 0.5 * t + rng.normal(0, 0.002, t.size))
        raw = _rocof(registries, name="raw")
        smooth = _rocof(registries, name="smooth", parameters={"smoothing": "centered_moving_average", "smoothing_window_ms": 200})
        assert smooth.parameters["smoothing"] == "centered_moving_average"
        assert smooth.parameters["smoothing_window_ms"] == 200.0
        assert raw.parameters["smoothing"] == "none"  # raw vs smoothed stays distinguishable
        assert np.std(smooth.values) < 0.2 * np.std(raw.values)

    @pytest.mark.parametrize(
        "parameters",
        [
            {"smoothing": "median"},
            {"smoothing": ["none"]},
            {"smoothing": "none", "smoothing_window_ms": 100},
            {"smoothing": "centered_moving_average"},
            {"smoothing": "centered_moving_average", "smoothing_window_ms": 0},
            {"smoothing": "centered_moving_average", "smoothing_window_ms": -5},
            {"smoothing": "centered_moving_average", "smoothing_window_ms": "100"},
            {"smoothing": "centered_moving_average", "smoothing_window_ms": True},
            {"smoothing": "centered_moving_average", "smoothing_window_ms": 5},  # < 2 intervals of 10 ms
            {"smoothing": "centered_moving_average", "smoothing_window_ms": 5000},  # > 1 s recording
        ],
    )
    def test_invalid_smoothing_is_rejected_not_ignored(self, registries, parameters):
        _freq_source(registries)
        with pytest.raises(InvalidRocofSmoothingError):
            _rocof(registries, parameters=parameters)


class TestRocofLifecycle:
    def test_delete_blocked_while_dependents_exist_then_allowed(self, registries):
        source_registry, calc_registry = registries
        _freq_source(registries)
        first = _rocof(registries)
        dependent = create_calculated_channel(
            workspace_id=WS, name="|ROCOF|", operation="absolute_value",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=first.id)], parameters={},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert dependent.unit == "Hz/s" and dependent.engineering_type == "ROCOF"
        with pytest.raises(CalculatedChannelHasDependentsError):
            delete_calculated_channel(workspace_id=WS, calculated_channel_id=first.id, calc_registry=calc_registry)
        delete_calculated_channel(workspace_id=WS, calculated_channel_id=dependent.id, calc_registry=calc_registry)
        delete_calculated_channel(workspace_id=WS, calculated_channel_id=first.id, calc_registry=calc_registry)
        assert calc_registry.list_for_workspace(WS) == []

    def test_source_removal_cascades(self, registries):
        _, calc_registry = registries
        _freq_source(registries)
        _rocof(registries)
        removed = remove_calculated_channels_for_source(workspace_id=WS, source_id="src1", calc_registry=calc_registry)
        assert len(removed) == 1 and calc_registry.list_for_workspace(WS) == []

    def test_two_rocof_channels_of_one_source_share_a_timebase(self, registries):
        source_registry, calc_registry = registries
        _freq_source(registries)
        a = _rocof(registries, name="a")
        b = _rocof(registries, name="b", parameters={"smoothing": "centered_moving_average", "smoothing_window_ms": 100})
        assert a.reference_source_id == b.reference_source_id == "src1"
        combined = create_calculated_channel(
            workspace_id=WS, name="a-b", operation="subtraction",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=a.id), ChannelRef(kind="calculated", calculated_channel_id=b.id)],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert combined.unit == "Hz/s"

    def test_no_per_unit_base_is_inherited(self, registries):
        from app.services.per_unit_registry import PerUnitRegistry

        source_registry, calc_registry = registries
        per_unit = PerUnitRegistry()
        _freq_source(registries)
        channel = _rocof(registries, per_unit_registry=per_unit)
        assert per_unit.profile_for_channel(WS, ChannelRef(kind="calculated", calculated_channel_id=channel.id), channel.engineering_type) is None


# ---------------------------------------------------------------------------
# API (end to end through the real COMTRADE provider)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _frequency_comtrade(*, f_values, fs=100.0, unit="Hz", name="FREQ"):
    n = len(f_values)
    cfg = "\r\n".join([
        "SYNTH_STATION,SYNTH_DEV,1999", "1,1A,0D",
        f"1,{name},,,{unit},1.0,0.0,0,-999999,999999,1.0,1.0,P",
        "50", "1", f"{fs},{n}",
        "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ]) + "\r\n"
    dat = "\r\n".join(
        f"{i + 1},{round(i * 1_000_000.0 / fs)},{'nan' if np.isnan(v) else format(v, '.6f')}"
        for i, v in enumerate(f_values)
    ) + "\r\n"
    return cfg.encode("ascii"), dat.encode("ascii")


def _upload_frequency(client, f_values, **kwargs):
    cfg, dat = _frequency_comtrade(f_values=f_values, **kwargs)
    resp = client.post(
        "/api/v1/workspaces/ws-1/sources",
        files={
            "cfg_file": ("freq.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": ("freq.dat", io.BytesIO(dat), "application/octet-stream"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _post_rocof(client, source_id, channel="FREQ", **extra):
    body = {
        "name": "ROCOF (FREQ)", "operation": "rocof",
        "inputs": [{"kind": "source", "source_id": source_id, "channel_name": channel}],
        "parameters": {},
    }
    body.update(extra)
    return client.post("/api/v1/workspaces/ws-1/calculated-channels", json=body)


class TestRocofApi:
    def test_end_to_end_linear_decline_minus_one_hz_per_second(self, client):
        source_id = _upload_frequency(client, list(np.linspace(50.0, 49.5, 51)))  # 0.5 s at 100 Hz
        resp = _post_rocof(client, source_id)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["unit"] == "Hz/s" and body["operation"] == "rocof" and body["engineering_type"] == "ROCOF"
        assert body["parameters"]["smoothing"] == "none"
        assert body["sample_count"] == 51

        wave = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{body['id']}/waveform")
        assert wave.status_code == 200, wave.text
        np.testing.assert_allclose(wave.json()["values"], -1.0, atol=1e-6)

        cursor = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/cursor-values",
            json={"calculated_channel_ids": [body["id"]], "cursor_a_time": 0.25, "cursor_b_time": None},
        )
        assert cursor.status_code == 200, cursor.text
        assert cursor.json()["channels"][0]["a_value"] == pytest.approx(-1.0, abs=1e-6)

        assert client.delete(f"/api/v1/workspaces/ws-1/calculated-channels/{body['id']}").status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/calculated-channels").json() == []

    def test_blank_samples_serialise_as_null_not_a_500(self, client):
        f_values = list(np.linspace(50.0, 49.5, 51))
        f_values[20] = float("nan")
        source_id = _upload_frequency(client, f_values)
        channel = _post_rocof(client, source_id).json()
        wave = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{channel['id']}/waveform")
        assert wave.status_code == 200, wave.text
        assert wave.json()["values"][20] is None

    def test_non_frequency_channel_needs_override(self, client):
        source_id = _upload_frequency(client, list(np.linspace(50.0, 49.5, 51)), unit="V", name="VA")
        blocked = _post_rocof(client, source_id, channel="VA")
        assert blocked.status_code == 400
        assert blocked.json()["detail"]["code"] == "rocof_override_required"
        allowed = _post_rocof(client, source_id, channel="VA", override=True)
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["unit"] == "Hz/s"

    def test_smoothing_parameters_round_trip_and_validation_codes(self, client):
        source_id = _upload_frequency(client, list(np.linspace(50.0, 49.0, 101)))
        ok = _post_rocof(client, source_id, parameters={"smoothing": "centered_moving_average", "smoothing_window_ms": 100})
        assert ok.status_code == 201, ok.text
        assert ok.json()["parameters"]["smoothing_window_ms"] == 100.0
        bad = _post_rocof(client, source_id, name="bad", parameters={"smoothing": "centered_moving_average"})
        assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_rocof_smoothing"

    def test_too_short_recording_code(self, client):
        source_id = _upload_frequency(client, [50.0, 49.9])
        resp = _post_rocof(client, source_id)
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "rocof_insufficient_data"

    def test_source_removal_cascades(self, client):
        source_id = _upload_frequency(client, list(np.linspace(50.0, 49.5, 51)))
        assert _post_rocof(client, source_id).status_code == 201
        assert client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/calculated-channels").json() == []
