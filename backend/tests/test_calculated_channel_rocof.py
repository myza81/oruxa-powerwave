"""ROCOF -- Rate of Change of Frequency calculated channel (DEC-190).

ROCOF is measured over a configurable CENTERED measurement window T
(100 / 200 / 500 / 1000 / 2000 ms): rolling frequency difference
`[f(t+T/2) - f(t-T/2)] / T` (default) or rolling least-squares slope.
The window is part of the estimate, not a smoothing stage.

Domain tests compare against analytical references (the closed-form
signal evaluated at the window edges) or an independent brute-force
`numpy.polyfit` per window; service tests cover parameters, eligibility,
null policy and lifecycle; API tests run the real end-to-end flow.
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
    ROCOF_METHOD_FREQUENCY_DIFFERENCE as DIFF,
    ROCOF_METHOD_LINEAR_REGRESSION as REG,
    ROCOF_WINDOWS_MS,
    ChannelRef,
    evaluate_rocof,
    rocof_method_valid,
    rocof_window_ms_valid,
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
    InvalidRocofParametersError,
    RequireManualValueNullError,
    RocofInsufficientDataError,
    RocofOverrideRequiredError,
)
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_calculated_channel_service import WS, _active_source

METHODS = [DIFF, REG]
WINDOWS_S = [w / 1000.0 for w in ROCOF_WINDOWS_MS]


def _uniform(duration: float, dt: float) -> np.ndarray:
    return np.arange(0.0, duration + dt / 2, dt)


def _expected_mask(t: np.ndarray, window: float, lo: float | None = None, hi: float | None = None) -> np.ndarray:
    """Samples whose complete centered window lies inside [lo, hi]."""
    lo = t[0] if lo is None else lo
    hi = t[-1] if hi is None else hi
    h = window / 2
    return (t - h >= lo - 1e-9) & (t + h <= hi + 1e-9)


def _brute_regression(t: np.ndarray, f: np.ndarray, i: int, window: float) -> float:
    sel = (t >= t[i] - window / 2 - 1e-9) & (t <= t[i] + window / 2 + 1e-9)
    return float(np.polyfit(t[sel], f[sel], 1)[0])


# ---------------------------------------------------------------------------
# Domain: the measurement window is part of the estimate
# ---------------------------------------------------------------------------


class TestRocofAnalyticalReferences:
    @pytest.mark.parametrize("method", METHODS)
    @pytest.mark.parametrize("window", WINDOWS_S)
    def test_constant_frequency_gives_zero(self, method, window):
        t = _uniform(4.0, 0.01)
        out = evaluate_rocof(t, np.full_like(t, 50.0), window, method)
        ok = _expected_mask(t, window)
        assert np.all(np.isfinite(out[ok])) and np.all(np.abs(out[ok]) < 1e-9)

    @pytest.mark.parametrize("method", METHODS)
    @pytest.mark.parametrize("window", WINDOWS_S)
    def test_linear_decline_every_window_gives_the_same_constant_slope(self, method, window):
        t = _uniform(4.0, 0.01)
        out = evaluate_rocof(t, 50.0 - 1.0 * t, window, method)  # 50 -> 46 Hz, -1 Hz/s
        ok = _expected_mask(t, window)
        np.testing.assert_allclose(out[ok], -1.0, atol=1e-8)
        assert np.all(np.isnan(out[~ok]))  # no shortened window anywhere

    @pytest.mark.parametrize("method", METHODS)
    def test_the_spec_example_50_to_49_5_in_half_a_second(self, method):
        t = _uniform(0.5, 0.005)
        out = evaluate_rocof(t, np.linspace(50.0, 49.5, t.size), 0.2, method)
        np.testing.assert_allclose(out[np.isfinite(out)], -1.0, atol=1e-9)

    @pytest.mark.parametrize("method", METHODS)
    def test_linear_recovery_is_positive(self, method):
        t = _uniform(3.0, 0.01)
        out = evaluate_rocof(t, 49.0 + 0.8 * t, 0.5, method)
        np.testing.assert_allclose(out[np.isfinite(out)], 0.8, atol=1e-8)

    @pytest.mark.parametrize("method", METHODS)
    @pytest.mark.parametrize("window", [0.2, 1.0])
    def test_quadratic_frequency_matches_the_instantaneous_slope(self, method, window):
        # f = 50 - 2 t^2 -> d/dt = -4 t ; both centered estimators are exact for a quadratic.
        t = _uniform(4.0, 0.005)
        out = evaluate_rocof(t, 50.0 - 2.0 * t**2, window, method)
        ok = _expected_mask(t, window)
        np.testing.assert_allclose(out[ok], -4.0 * t[ok], atol=1e-4)

    @pytest.mark.parametrize("dt,window", [(0.0002, 0.1), (0.003, 0.1), (0.03, 0.1), (0.07, 0.2), (0.1, 0.5)])
    def test_different_sampling_intervals_and_off_grid_window_edges(self, dt, window):
        # window edges rarely land on a sample (e.g. dt 30 ms, T/2 = 50 ms): interpolation must be exact for a ramp
        t = _uniform(3.0, dt)
        for method in METHODS:
            out = evaluate_rocof(t, 50.0 - 0.75 * t, window, method)
            ok = _expected_mask(t, window)
            assert ok.sum() > 10
            np.testing.assert_allclose(out[ok], -0.75, atol=1e-8)


class TestRocofWindowGenuinelyMatters:
    @staticmethod
    def _disturbance(t):
        # frequency dips 0.1 Hz over 100 ms then recovers over 100 ms (a short triangular disturbance at t = 2 s)
        return 50.0 - 0.1 * np.clip(1 - np.abs(t - 2.0) / 0.1, 0, None)

    def test_rolling_frequency_difference_equals_the_analytic_edge_difference(self):
        t = _uniform(4.0, 0.001)
        for window in WINDOWS_S:
            out = evaluate_rocof(t, self._disturbance(t), window, DIFF)
            ok = _expected_mask(t, window)
            reference = (self._disturbance(t[ok] + window / 2) - self._disturbance(t[ok] - window / 2)) / window
            np.testing.assert_allclose(out[ok], reference, atol=1e-9)

    @pytest.mark.parametrize("method", METHODS)
    def test_different_windows_give_distinguishable_waveforms_for_a_short_disturbance(self, method):
        t = _uniform(4.0, 0.001)
        f = self._disturbance(t)
        peaks = [np.nanmax(np.abs(evaluate_rocof(t, f, w, method))) for w in WINDOWS_S]
        # 1.0 Hz/s for 100 ms; a longer window averages the same 0.1 Hz step over more time
        assert peaks[0] == pytest.approx(1.0, rel=0.05)
        assert all(a > b * 1.15 for a, b in zip(peaks, peaks[1:])), peaks
        assert peaks[-1] < 0.1 * peaks[0]

    def test_it_is_not_the_adjacent_sample_derivative_nor_a_smoothed_one(self):
        t = _uniform(4.0, 0.01)
        f = self._disturbance(t)
        out = evaluate_rocof(t, f, 0.5, DIFF)
        adjacent = np.gradient(f, t)
        ok = np.isfinite(out)
        assert np.max(np.abs(out[ok] - adjacent[ok])) > 0.5  # clearly different from a sample-spacing derivative
        # and the 500 ms window sees a 0.1 Hz step as at most 0.2 Hz/s
        assert np.nanmax(np.abs(out)) == pytest.approx(0.2, abs=0.01)

    @pytest.mark.parametrize("method", METHODS)
    def test_availability_shrinks_with_the_window(self, method):
        t = _uniform(4.0, 0.01)
        counts = [int(np.isfinite(evaluate_rocof(t, 50 - t, w, method)).sum()) for w in WINDOWS_S]
        assert counts == sorted(counts, reverse=True) and len(set(counts)) == len(counts)


class TestRocofRegressionAgainstReference:
    def test_matches_independent_polyfit_on_irregular_timestamps(self):
        rng = np.random.default_rng(11)
        t = np.cumsum(rng.uniform(0.002, 0.012, 3000))
        f = 50.0 + 0.2 * np.sin(2 * np.pi * 0.7 * t) - 0.05 * t**2
        for window in (0.1, 0.5, 1.0):
            out = evaluate_rocof(t, f, window, REG)
            idx = np.flatnonzero(np.isfinite(out))[::37]
            assert idx.size > 10
            ref = np.array([_brute_regression(t, f, i, window) for i in idx])
            np.testing.assert_allclose(out[idx], ref, rtol=1e-7, atol=1e-8)

    def test_diff_matches_the_analytic_signal_on_irregular_timestamps(self):
        rng = np.random.default_rng(5)
        t = np.cumsum(rng.uniform(0.0005, 0.0015, 6000))
        fn = lambda x: 50.0 + 0.2 * np.sin(2 * np.pi * 0.7 * x) - 0.05 * x**2  # noqa: E731
        out = evaluate_rocof(t, fn(t), 0.5, DIFF)
        ok = np.isfinite(out)
        np.testing.assert_allclose(out[ok], (fn(t[ok] + 0.25) - fn(t[ok] - 0.25)) / 0.5, atol=1e-5)  # linear-interpolation error ~ f''*dt^2/8 per edge

    def test_regression_noise_is_below_difference_noise(self):
        rng = np.random.default_rng(2)
        t = _uniform(20.0, 0.002)
        f = np.round(50.0 - 0.5 * t + rng.normal(0, 0.002, t.size), 3)  # 1 mHz quantised + noise
        for window in (0.2, 1.0):
            d = evaluate_rocof(t, f, window, DIFF)
            r = evaluate_rocof(t, f, window, REG)
            assert np.nanstd(r) < np.nanstd(d)
            np.testing.assert_allclose(np.nanmean(r), -0.5, atol=0.01)

    @pytest.mark.parametrize("method", METHODS)
    def test_noise_falls_as_the_window_grows(self, method):
        rng = np.random.default_rng(4)
        t = _uniform(30.0, 0.005)
        f = np.round(50.0 - 0.3 * t + rng.normal(0, 0.003, t.size), 3)
        stds = [np.nanstd(evaluate_rocof(t, f, w, method)) for w in WINDOWS_S]
        assert all(a > b for a, b in zip(stds, stds[1:])), stds


class TestRocofInvalidDataAndBoundaries:
    @pytest.mark.parametrize("method", METHODS)
    def test_incomplete_edge_windows_are_unavailable_not_shortened(self, method):
        t = _uniform(2.0, 0.01)
        out = evaluate_rocof(t, 50.0 - t, 0.5, method)
        assert np.all(np.isnan(out[t < 0.25 - 1e-9])) and np.all(np.isnan(out[t > 1.75 + 1e-9]))
        assert np.all(np.isfinite(out[(t >= 0.25 - 1e-9) & (t <= 1.75 + 1e-9)]))

    @pytest.mark.parametrize("method", METHODS)
    def test_record_shorter_than_the_window_gives_nothing(self, method):
        t = _uniform(0.4, 0.01)
        assert np.all(np.isnan(evaluate_rocof(t, 50.0 - t, 0.5, method)))

    @pytest.mark.parametrize("method", METHODS)
    def test_record_exactly_one_window_gives_the_centre_sample(self, method):
        t = _uniform(0.5, 0.01)
        out = evaluate_rocof(t, 50.0 - t, 0.5, method)
        assert np.isfinite(out).sum() == 1 and np.isfinite(out[25])

    @pytest.mark.parametrize("method", METHODS)
    def test_recording_gap_is_never_bridged(self, method):
        # 1 Hz/s ramp, a 3 s gap and a +5 Hz jump, then a -2 Hz/s ramp
        t1, t2 = _uniform(3.0, 0.01), _uniform(3.0, 0.01) + 6.0
        t = np.concatenate([t1, t2])
        f = np.concatenate([50.0 + 1.0 * t1, 60.0 - 2.0 * (t2 - 6.0)])
        window = 1.0
        out = evaluate_rocof(t, f, window, method)
        first, second = slice(0, t1.size), slice(t1.size, None)
        np.testing.assert_allclose(out[first][_expected_mask(t1, window)], 1.0, atol=1e-8)
        np.testing.assert_allclose(out[second][_expected_mask(t2, window)], -2.0, atol=1e-8)
        # samples whose window would touch the gap stay unavailable
        expected = np.concatenate([_expected_mask(t1, window), _expected_mask(t2, window)])
        np.testing.assert_array_equal(np.isfinite(out), expected)

    @pytest.mark.parametrize("method", METHODS)
    def test_nan_sample_splits_the_record(self, method):
        t = _uniform(6.0, 0.01)
        f = 50.0 - 0.5 * t
        f[300] = np.nan  # t = 3.0
        out = evaluate_rocof(t, f, 1.0, method)
        expected = _expected_mask(t, 1.0, hi=2.99) | _expected_mask(t, 1.0, lo=3.01)
        np.testing.assert_array_equal(np.isfinite(out), expected)
        assert np.all(np.isnan(out[np.abs(t - 3.0) <= 0.5]))  # every window containing the bad sample
        np.testing.assert_allclose(out[np.isfinite(out)], -0.5, atol=1e-8)

    @pytest.mark.parametrize("method", METHODS)
    def test_inf_and_nonfinite_timestamp_treated_as_invalid(self, method):
        t = _uniform(6.0, 0.01)
        f = 50.0 - 0.5 * t
        f[100] = np.inf
        t2 = t.copy()
        t2[400] = np.nan
        for tt, ff in ((t, f), (t2, 50.0 - 0.5 * t)):
            out = evaluate_rocof(tt, ff, 0.5, method)
            assert not np.any(np.isinf(out))
            np.testing.assert_allclose(out[np.isfinite(out)], -0.5, atol=1e-8)

    @pytest.mark.parametrize("method", METHODS)
    def test_duplicate_and_non_monotonic_timestamps_are_breaks(self, method):
        t = _uniform(6.0, 0.01)
        f = 50.0 - 0.5 * t
        t_dup = t.copy()
        t_dup[300] = t_dup[299]  # duplicate
        t_back = t.copy()
        t_back[300:] -= 0.5  # steps backwards at 300 -> non-monotonic
        for tt in (t_dup, t_back):
            out = evaluate_rocof(tt, 50.0 - 0.5 * tt, 0.5, method)  # frequency follows the (bad) timestamps
            assert not np.any(np.isinf(out)) and np.isfinite(out).any()
            finite = np.isfinite(out)
            # no value is produced for a window that would contain the bad interval
            assert not finite[298:302].any()
            np.testing.assert_allclose(out[finite], -0.5, atol=1e-8)

    @pytest.mark.parametrize("method", METHODS)
    def test_all_invalid_and_tiny_inputs(self, method):
        t = _uniform(2.0, 0.1)
        assert np.all(np.isnan(evaluate_rocof(t, np.full_like(t, np.nan), 0.2, method)))
        assert evaluate_rocof(np.array([0.0]), np.array([50.0]), 0.2, method).shape == (1,)
        assert evaluate_rocof(np.array([]), np.array([]), 0.2, method).shape == (0,)

    @pytest.mark.parametrize("method", METHODS)
    def test_float32_input(self, method):
        t = _uniform(3.0, 0.01).astype(np.float32)
        out = evaluate_rocof(t, (50.0 - 1.0 * t).astype(np.float32), 0.5, method)
        np.testing.assert_allclose(out[np.isfinite(out)], -1.0, atol=2e-2)

    def test_unknown_method_raises(self):
        t = _uniform(2.0, 0.01)
        with pytest.raises(ValueError):
            evaluate_rocof(t, 50 - t, 0.5, "moving_average")

    def test_parameter_validators(self):
        assert [rocof_window_ms_valid(w) for w in (100, 200, 500, 1000, 2000, 500.0)] == [True] * 6
        for bad in (0, 50, 300, 5000, True, None, "500", float("nan")):
            assert rocof_window_ms_valid(bad) is False
        assert rocof_method_valid(DIFF) and rocof_method_valid(REG)
        assert not rocof_method_valid("centered_moving_average") and not rocof_method_valid(None)


class TestRocofPerformance:
    @pytest.mark.parametrize("method", METHODS)
    def test_two_million_samples_every_window(self, method):
        n = 2_000_000
        t = np.arange(n) * 0.0002  # 5 kHz, 400 s
        f = 50.0 - 0.01 * t
        f[::100003] = np.nan
        for window in WINDOWS_S:
            started = time_module.perf_counter()
            out = evaluate_rocof(t, f, window, method)
            elapsed = time_module.perf_counter() - started
            assert elapsed < 15.0, f"{method} {window}s over {n} samples took {elapsed:.1f}s"
            np.testing.assert_allclose(out[np.isfinite(out)], -0.01, atol=1e-7)  # accurate over the whole record


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
    t = _uniform(3.0, 0.01) if t is None else t
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
    def test_defaults_are_rolling_difference_500_ms_centered_and_stored_explicitly(self, registries):
        t, _ = _freq_source(registries)
        channel = _rocof(registries)
        assert channel.unit == "Hz/s" and channel.operation == OP_ROCOF and channel.engineering_type == "ROCOF"
        assert channel.parameters == {
            "method": "rolling_frequency_difference", "window_ms": 500, "alignment": "centered",
            "edge_policy": "unavailable_when_window_incomplete",
        }
        finite = np.isfinite(channel.values)
        np.testing.assert_array_equal(finite, _expected_mask(t, 0.5))
        np.testing.assert_allclose(channel.values[finite], -0.5, atol=1e-9)
        # time/timebase inherited VERBATIM -> follows the source's sync / global-t0 placement
        np.testing.assert_array_equal(channel.time, t)
        assert channel.reference_source_id == "src1"
        assert channel.voltage_representation is None and channel.phase_member is None

    @pytest.mark.parametrize("method", METHODS)
    @pytest.mark.parametrize("window_ms", ROCOF_WINDOWS_MS)
    def test_every_method_and_window_creates_the_expected_channel(self, registries, method, window_ms):
        t, _ = _freq_source(registries, t=_uniform(5.0, 0.01), f=50.0 - 0.5 * _uniform(5.0, 0.01))
        channel = _rocof(registries, parameters={"method": method, "window_ms": window_ms})
        assert channel.parameters["method"] == method and channel.parameters["window_ms"] == window_ms
        finite = np.isfinite(channel.values)
        np.testing.assert_array_equal(finite, _expected_mask(t, window_ms / 1000.0))
        np.testing.assert_allclose(channel.values[finite], -0.5, atol=1e-8)

    def test_window_selection_changes_the_waveform(self, registries):
        t = _uniform(6.0, 0.005)
        f = 50.0 - 0.1 * np.clip(1 - np.abs(t - 3.0) / 0.1, 0, None)
        _freq_source(registries, t=t, f=f)
        a = _rocof(registries, name="a", parameters={"window_ms": 100})
        b = _rocof(registries, name="b", parameters={"window_ms": 1000})
        assert np.nanmax(np.abs(a.values)) > 5 * np.nanmax(np.abs(b.values))

    def test_source_arrays_are_not_mutated(self, registries):
        _freq_source(registries)
        source_registry, _ = registries
        before = source_registry.get(WS, "src1").record.waveform_data["F"].to_numpy().copy()
        _rocof(registries)
        np.testing.assert_array_equal(source_registry.get(WS, "src1").record.waveform_data["F"].to_numpy(), before)

    def test_unidentified_channel_requires_override(self, registries):
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
        np.testing.assert_allclose(channel.values[np.isfinite(channel.values)], -0.5, atol=1e-9)

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

    def test_record_shorter_than_the_window_is_rejected_with_a_clear_reason(self, registries):
        _freq_source(registries, t=_uniform(1.0, 0.01), f=50.0 - _uniform(1.0, 0.01))
        with pytest.raises(RocofInsufficientDataError, match="2000 ms"):
            _rocof(registries, parameters={"window_ms": 2000})

    def test_irregular_timestamps_through_the_service(self, registries):
        rng = np.random.default_rng(1)
        t = np.cumsum(rng.uniform(0.004, 0.006, 1500))
        _freq_source(registries, t=t, f=50.0 - 0.4 * t)
        for method in METHODS:
            ch = _rocof(registries, name=method, parameters={"method": method, "window_ms": 200})
            np.testing.assert_allclose(ch.values[np.isfinite(ch.values)], -0.4, atol=1e-8)


class TestRocofParameterValidation:
    @pytest.mark.parametrize(
        "parameters",
        [
            {"method": "centered_moving_average"},
            {"method": ["rolling_frequency_difference"]},
            {"window_ms": 300},
            {"window_ms": 50},
            {"window_ms": "500"},
            {"window_ms": True},
            {"window_ms": None},
            {"alignment": "trailing"},
        ],
    )
    def test_unsupported_values_are_rejected_not_substituted(self, registries, parameters):
        _freq_source(registries)
        _, calc_registry = registries
        with pytest.raises(InvalidRocofParametersError):
            _rocof(registries, parameters=parameters)
        assert calc_registry.list_for_workspace(WS) == []

    def test_window_shorter_than_two_sample_intervals_is_rejected(self, registries):
        t = _uniform(30.0, 0.1)  # 100 ms sampling: a 100 ms window is one interval
        _freq_source(registries, t=t, f=50.0 - 0.1 * t)
        with pytest.raises(InvalidRocofParametersError, match="at least 2 sample intervals"):
            _rocof(registries, parameters={"window_ms": 100})
        assert _rocof(registries, parameters={"window_ms": 500}).parameters["window_ms"] == 500


class TestRocofNullPolicy:
    def _with_gap(self, registries):
        t = _uniform(3.0, 0.01)
        f = 50.0 - 0.5 * t
        f[150] = np.nan  # t = 1.5
        _freq_source(registries, t=t, f=f)
        return t

    def test_propagate_leaves_the_windows_touching_the_blank_sample_unavailable(self, registries):
        t = self._with_gap(registries)
        channel = _rocof(registries, null_policy=NULL_POLICY_PROPAGATE)
        expected = _expected_mask(t, 0.5, hi=1.49) | _expected_mask(t, 0.5, lo=1.51)
        np.testing.assert_array_equal(np.isfinite(channel.values), expected)
        np.testing.assert_allclose(channel.values[expected], -0.5, atol=1e-9)

    def test_treat_null_as_zero_is_rejected(self, registries):
        self._with_gap(registries)
        with pytest.raises(InvalidNullPolicyError, match="0 Hz"):
            _rocof(registries, null_policy=NULL_POLICY_ZERO)

    def test_require_manual_value_blocks(self, registries):
        self._with_gap(registries)
        with pytest.raises(RequireManualValueNullError):
            _rocof(registries, null_policy=NULL_POLICY_REQUIRE_MANUAL)

    def test_estimate_fills_the_gap_first_so_windows_are_available_across_it(self, registries):
        t = self._with_gap(registries)
        channel = _rocof(
            registries, null_policy=NULL_POLICY_ESTIMATE, estimation_method="linear",
            max_gap_value=3, max_gap_unit="samples",
        )
        np.testing.assert_array_equal(np.isfinite(channel.values), _expected_mask(t, 0.5))
        np.testing.assert_allclose(channel.values[np.isfinite(channel.values)], -0.5, atol=1e-9)


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
        b = _rocof(registries, name="b", parameters={"method": REG, "window_ms": 200})
        assert a.reference_source_id == b.reference_source_id == "src1"
        combined = create_calculated_channel(
            workspace_id=WS, name="a-b", operation="subtraction",
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=a.id), ChannelRef(kind="calculated", calculated_channel_id=b.id)],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert combined.unit == "Hz/s"

    def test_no_per_unit_base_is_inherited(self, registries):
        from app.services.per_unit_registry import PerUnitRegistry

        per_unit = PerUnitRegistry()
        _freq_source(registries)
        channel = _rocof(registries, per_unit_registry=per_unit)
        assert per_unit.profile_for_channel(WS, ChannelRef(kind="calculated", calculated_channel_id=channel.id), channel.engineering_type) is None


# ---------------------------------------------------------------------------
# API (end to end through the real COMTRADE provider)
# ---------------------------------------------------------------------------

SAMPLES = 151  # 1.5 s at 100 Hz, f = 50 - t  ->  -1 Hz/s


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


def _ramp():
    return list(50.0 - np.arange(SAMPLES) / 100.0)


def _post_rocof(client, source_id, channel="FREQ", **extra):
    body = {
        "name": "ROCOF (FREQ)", "operation": "rocof",
        "inputs": [{"kind": "source", "source_id": source_id, "channel_name": channel}],
        "parameters": {},
    }
    body.update(extra)
    return client.post("/api/v1/workspaces/ws-1/calculated-channels", json=body)


class TestRocofApi:
    def test_end_to_end_default_500ms_difference_on_a_minus_one_hz_per_second_ramp(self, client):
        source_id = _upload_frequency(client, _ramp())
        resp = _post_rocof(client, source_id)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["unit"] == "Hz/s" and body["operation"] == "rocof" and body["engineering_type"] == "ROCOF"
        assert body["parameters"] == {
            "method": "rolling_frequency_difference", "window_ms": 500, "alignment": "centered",
            "edge_policy": "unavailable_when_window_incomplete",
        }
        assert body["sample_count"] == SAMPLES

        wave = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{body['id']}/waveform")
        assert wave.status_code == 200, wave.text
        values = wave.json()["values"]
        assert len(values) == SAMPLES
        # 250 ms of an incomplete window at each end -> JSON null (never a 500 / shortened window)
        assert all(v is None for v in values[:25]) and all(v is None for v in values[-25:])
        np.testing.assert_allclose(values[25:-25], -1.0, atol=1e-6)

        cursor = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/cursor-values",
            json={"calculated_channel_ids": [body["id"]], "cursor_a_time": 0.75, "cursor_b_time": None},
        )
        assert cursor.status_code == 200, cursor.text
        assert cursor.json()["channels"][0]["a_value"] == pytest.approx(-1.0, abs=1e-6)

        assert client.delete(f"/api/v1/workspaces/ws-1/calculated-channels/{body['id']}").status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/calculated-channels").json() == []

    def test_regression_method_and_window_round_trip(self, client):
        source_id = _upload_frequency(client, _ramp())
        resp = _post_rocof(client, source_id, parameters={"method": "rolling_linear_regression", "window_ms": 200})
        assert resp.status_code == 201, resp.text
        assert resp.json()["parameters"]["method"] == "rolling_linear_regression"
        wave = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{resp.json()['id']}/waveform").json()
        np.testing.assert_allclose([v for v in wave["values"] if v is not None], -1.0, atol=1e-6)
        assert sum(v is None for v in wave["values"]) == 20  # 100 ms at each end

    def test_blank_samples_serialise_as_null_not_a_500(self, client):
        f_values = _ramp()
        f_values[75] = float("nan")
        source_id = _upload_frequency(client, f_values)
        channel = _post_rocof(client, source_id, parameters={"window_ms": 200}).json()
        wave = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{channel['id']}/waveform")
        assert wave.status_code == 200, wave.text
        assert wave.json()["values"][75] is None and wave.json()["values"][70] is None

    def test_non_frequency_channel_needs_override(self, client):
        source_id = _upload_frequency(client, _ramp(), unit="V", name="VA")
        blocked = _post_rocof(client, source_id, channel="VA")
        assert blocked.status_code == 400 and blocked.json()["detail"]["code"] == "rocof_override_required"
        assert _post_rocof(client, source_id, channel="VA", override=True).status_code == 201

    @pytest.mark.parametrize("parameters", [{"window_ms": 300}, {"method": "moving_average"}, {"alignment": "trailing"}])
    def test_invalid_parameters_code(self, client, parameters):
        source_id = _upload_frequency(client, _ramp())
        bad = _post_rocof(client, source_id, parameters=parameters)
        assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_rocof_parameters"

    def test_window_longer_than_the_record_code(self, client):
        source_id = _upload_frequency(client, _ramp())
        resp = _post_rocof(client, source_id, parameters={"window_ms": 2000})
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "rocof_insufficient_data"

    def test_too_short_recording_code(self, client):
        source_id = _upload_frequency(client, [50.0, 49.9])
        resp = _post_rocof(client, source_id)
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "rocof_insufficient_data"

    def test_source_removal_cascades(self, client):
        source_id = _upload_frequency(client, _ramp())
        assert _post_rocof(client, source_id).status_code == 201
        assert client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/calculated-channels").json() == []
