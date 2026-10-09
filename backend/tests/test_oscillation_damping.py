"""Oscillation Analysis -- ringdown damping estimation (DEC-177 [APPROVED]).

Deterministic synthetic signals with ANALYTICALLY KNOWN decay: the estimate is compared
with the injected value under explicit tolerances (stated per test). The domain tests call
`estimate_damping` directly; the service/API tests go through the same Welch spectrum and
DEC-175 detection the product uses, so the candidate frequencies are the detector's.

Conventions under test: alpha = -sigma [1/s] with amplitude ~ exp(-alpha t) (alpha > 0
decays); zeta = alpha / sqrt(alpha^2 + omega^2) with omega = 2 pi f_damped.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import damping_estimation as de
from app.domain.calculated_channel import ChannelRef
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_damping_service import compute_damping
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_oscillation_representation import WS, _active, _upload  # noqa: F401

FS = 50.0


def _t(duration=160.0, fs=FS):
    return np.arange(int(round(fs * duration))) / fs


def ring(t, f, zeta, amplitude=1.0, t_on=0.0):
    """`A exp(-alpha (t - t_on)) cos(2 pi f (t - t_on))` for t >= t_on, with `f` the DAMPED frequency
    and `alpha = zeta * omega_n`, so the injected damping ratio is exactly `zeta`. Returns (x, alpha)."""
    omega_d = 2 * math.pi * f
    alpha = zeta * omega_d / math.sqrt(1 - zeta ** 2)
    tau = np.clip(t - t_on, 0, None)
    return amplitude * np.exp(-alpha * tau) * np.cos(omega_d * tau) * (t >= t_on), alpha


def _estimate(x, f, *, fs=FS, others=None, psd=None, t0=0.0):
    return de.estimate_damping(de.window_spectrum(t0, x, fs), f, psd, others, "MW")


def _rel(estimate, truth):
    return abs(estimate - truth) / abs(truth)


# ---------------------------------------------------------------- model / conventions ----

class TestConventions:
    def test_decay_rate_and_damping_ratio_formulas(self):
        t = _t()
        x, alpha = ring(t, 1.15, 0.05, t_on=30.0)
        r = _estimate(x, 1.15)
        omega = 2 * math.pi * r["frequency"]["used_hz"]
        assert r["status"] == "available" and r["behaviour"] == "decaying"
        assert r["decay_rate_per_s"] == pytest.approx(alpha, rel=0.01)           # alpha > 0 means decay
        assert r["damping_ratio"] == pytest.approx(r["decay_rate_per_s"] / math.hypot(r["decay_rate_per_s"], omega), rel=1e-12)
        assert r["time_constant_s"] == pytest.approx(1 / r["decay_rate_per_s"])

    def test_candidate_frequency_is_preserved_and_refinement_is_separate(self):
        t = _t()
        x, _ = ring(t, 1.17, 0.05, t_on=30.0)
        r = _estimate(x, 1.15)                       # the spectral bin is 20 mHz off the true damped frequency
        f = r["frequency"]
        assert f["candidate_hz"] == 1.15 and f["source"] == "fitted"
        assert abs(f["fitted_hz"] - 1.17) < 1e-3 and abs(f["fitted_hz"] - f["candidate_hz"]) <= r["filter"]["bandwidth_fwhm_hz"] / 2
        assert r["candidate_frequency_hz"] == 1.15

    def test_result_is_deterministic(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=30.0)
        x = x + np.random.default_rng(5).normal(0, 0.01, t.size)
        assert _estimate(x, 1.15) == _estimate(x, 1.15)


# ---------------------------------------------------------------- clean known decay ----

class TestCleanKnownDecay:
    @pytest.mark.parametrize("f", [0.6, 1.15, 2.5, 4.95, 8.0])
    @pytest.mark.parametrize("zeta", [0.02, 0.05, 0.10])
    def test_recovers_injected_decay_rate_and_damping_ratio(self, f, zeta):
        """Tolerance: 2 % relative on the decay rate and on zeta for noise-free exponentials."""
        t = _t()
        x, alpha = ring(t, f, zeta, t_on=25.0)
        r = _estimate(x, f)
        assert r["status"] == "available", r["message"]
        assert _rel(r["decay_rate_per_s"], alpha) < 0.02
        assert _rel(r["damping_ratio"], zeta) < 0.02
        assert r["fit"]["cycles_used"] >= de.MIN_FIT_CYCLES
        assert r["fit_quality"]["r_squared"] > 0.999

    def test_fit_interval_is_reported_and_starts_after_the_onset_transient(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=30.0)
        fit = _estimate(x, 1.15)["fit"]
        assert fit["start_s"] > 30.0 + r_guard(1.15) * 0.99     # filter-transient guard after the envelope peak
        assert fit["end_s"] <= 160.0 and fit["rule"] == "after_envelope_peak"
        assert fit["duration_s"] == pytest.approx(fit["end_s"] - fit["start_s"])

    def test_event_origin_is_not_assumed_to_be_the_ringdown_onset(self):
        """No t=0 knowledge reaches the estimator: an onset late in the record is found from the signal."""
        t = _t()
        x, alpha = ring(t, 1.15, 0.05, t_on=90.0)
        r = _estimate(x, 1.15, t0=-30.0)
        assert r["status"] == "available" and r["fit"]["start_s"] > 90.0 - 30.0
        assert _rel(r["decay_rate_per_s"], alpha) < 0.02


def r_guard(f):
    bw = max(de.BANDWIDTH_FRACTION * f, de.MIN_BANDWIDTH_HZ)
    sigma_t = 1 / (2 * math.pi * bw / de.FWHM_PER_SIGMA)
    return de.EDGE_GUARD_SIGMAS * sigma_t


# ---------------------------------------------------------------- sustained / growing ----

class TestSustainedAndGrowing:
    def test_sustained_oscillation(self):
        t = _t()
        r = _estimate(np.cos(2 * np.pi * 1.15 * t), 1.15)
        assert r["status"] == "available" and r["behaviour"] == "approximately_sustained"
        assert abs(r["decay_rate_per_s"]) < 1e-3
        assert r["damping_ratio"] is None             # not a ringdown decay: no damping ratio is manufactured
        assert any(e["code"] == "damping_ratio_not_reported" for e in r["reasons"])

    def test_sustained_oscillation_with_noise(self):
        t = _t()
        x = np.cos(2 * np.pi * 1.15 * t) + np.random.default_rng(2).normal(0, 0.1, t.size)
        r = _estimate(x, 1.15)
        assert r["behaviour"] == "approximately_sustained" and r["damping_ratio"] is None

    def test_growing_oscillation(self):
        """Tolerance: 5 % on the growth rate."""
        t = _t(80.0)
        rate = 0.04
        x = 0.05 * np.exp(rate * t) * np.cos(2 * np.pi * 1.15 * t)
        r = _estimate(x, 1.15)
        assert r["status"] == "available" and r["behaviour"] == "growing"
        assert r["decay_rate_per_s"] == pytest.approx(-rate, rel=0.05)      # alpha < 0: growth
        assert r["damping_ratio"] is None
        assert r["envelope_change"]["change_percent"] > 100
        assert r["fit"]["rule"] == "active_run_around_peak"


# ---------------------------------------------------------------- disturbance / trend ----

class TestDisturbanceRemoval:
    def test_step_and_recovery_much_larger_than_the_oscillation(self):
        """KEY ACCEPTANCE: a 50-unit step with a 6 s recovery, a 0.3-unit ringdown (167x smaller).
        Tolerance: 5 % noise-free, 20 % with 0.005 white noise (about 7 cycles of data are usable)."""
        t = _t()
        step = 50.0 * np.exp(-np.clip(t - 30.0, 0, None) / 6.0) * (t >= 30.0)
        ring_x, alpha = ring(t, 1.15, 0.06, amplitude=0.3, t_on=30.0)
        clean = _estimate(step + ring_x, 1.15)
        assert clean["status"] == "available"
        assert _rel(clean["decay_rate_per_s"], alpha) < 0.05 and _rel(clean["damping_ratio"], 0.06) < 0.05
        assert clean["fit"]["start_s"] > 30.0 + r_guard(1.15) * 0.99
        noisy = _estimate(step + ring_x + np.random.default_rng(3).normal(0, 0.005, t.size), 1.15)
        assert noisy["status"] == "available"
        assert _rel(noisy["decay_rate_per_s"], alpha) < 0.20 and _rel(noisy["damping_ratio"], 0.06) < 0.20

    def test_slow_ramp_and_offset_do_not_change_the_estimate(self):
        t = _t()
        x, alpha = ring(t, 1.15, 0.05, t_on=30.0)
        r = _estimate(x + 40.0 + 0.2 * t, 1.15)
        assert r["status"] == "available" and _rel(r["decay_rate_per_s"], alpha) < 0.03

    def test_recovery_alone_is_not_a_ringdown(self):
        t = _t()
        step = 50.0 * np.exp(-np.clip(t - 30.0, 0, None) / 6.0) * (t >= 30.0)
        r = _estimate(step + np.random.default_rng(1).normal(0, 0.005, t.size), 1.15)
        assert r["status"] == "insufficient_evidence" and r["damping_ratio"] is None


# ---------------------------------------------------------------- multiple modes ----

class TestMultipleModes:
    def test_two_simultaneous_modes_with_different_damping(self):
        """Tolerance: 4 % each (noise-free); the strong neighbour must not corrupt the weak mode."""
        t = _t()
        a, alpha_a = ring(t, 1.15, 0.05, amplitude=1.0, t_on=25.0)
        b, alpha_b = ring(t, 4.95, 0.02, amplitude=0.1, t_on=25.0)       # 10x weaker, much less damped
        x = a + b
        ra = _estimate(x, 1.15, others=[(4.95, 0.01)], psd=1.0)
        rb = _estimate(x, 4.95, others=[(1.15, 1.0)], psd=0.01)
        assert ra["status"] == rb["status"] == "available"
        assert _rel(ra["decay_rate_per_s"], alpha_a) < 0.04 and _rel(rb["decay_rate_per_s"], alpha_b) < 0.04
        assert _rel(ra["damping_ratio"], 0.05) < 0.04 and _rel(rb["damping_ratio"], 0.02) < 0.04
        assert ra["decay_rate_per_s"] != pytest.approx(rb["decay_rate_per_s"], rel=0.2)

    def test_bandwidth_narrows_for_a_close_neighbour_and_leakage_is_reported(self):
        t = _t()
        a, _ = ring(t, 1.0, 0.03, t_on=20.0)
        b, _ = ring(t, 1.5, 0.03, amplitude=0.5, t_on=20.0)
        r = _estimate(a + b, 1.0, others=[(1.5, 0.25)], psd=1.0)
        assert r["filter"]["bandwidth_fwhm_hz"] < de.BANDWIDTH_FRACTION * 1.0 + 1e-9
        assert r["filter"]["neighbour_leakage"] is not None

    def test_an_inseparable_stronger_neighbour_is_refused(self):
        t = _t()
        a, _ = ring(t, 1.0, 0.03, amplitude=0.1, t_on=20.0)
        b, _ = ring(t, 1.1, 0.03, amplitude=1.0, t_on=20.0)
        r = _estimate(a + b, 1.0, others=[(1.1, 100.0)], psd=1.0)
        assert r["status"] == "insufficient_evidence" and r["reason_code"] == "component_not_isolated"
        assert r["damping_ratio"] is None


# ---------------------------------------------------------------- noise ----

class TestNoise:
    def test_moderate_noise(self):
        """Tolerance: 10 % on zeta at an amplitude-to-noise ratio of about 50."""
        t = _t()
        x, _ = ring(t, 1.15, 0.03, t_on=20.0)
        r = _estimate(x + np.random.default_rng(7).normal(0, 0.02, t.size), 1.15)
        assert r["status"] == "available" and _rel(r["damping_ratio"], 0.03) < 0.10
        assert r["background"]["level"] > 0

    def test_strong_noise_never_yields_a_misleading_ratio(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=30.0)
        r = _estimate(x + np.random.default_rng(11).normal(0, 1.0, t.size), 1.15)
        if r["status"] == "available":
            assert _rel(r["damping_ratio"], 0.05) < 0.5      # an estimate, if made, is not wild
        else:
            assert r["damping_ratio"] is None and r["decay_rate_per_s"] is None

    def test_candidate_near_the_noise_floor_is_insufficient_evidence(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, amplitude=0.06, t_on=30.0)
        r = _estimate(x + np.random.default_rng(13).normal(0, 0.1, t.size), 1.15)
        assert r["status"] == "insufficient_evidence" and r["damping_ratio"] is None
        assert r["reasons"] and r["message"]

    def test_pure_noise_is_not_damped(self):
        t = _t()
        r = _estimate(np.random.default_rng(17).normal(0, 1.0, t.size), 1.15)
        assert r["status"] == "insufficient_evidence" and r["reason_code"] == "near_noise_floor"


# ---------------------------------------------------------------- unsupported shapes ----

class TestEvidenceRules:
    def test_short_ringdown_late_in_the_record(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=150.0)
        r = _estimate(x, 1.15)
        assert r["status"] == "insufficient_evidence" and r["reason_code"] == "ringdown_interval_too_short"
        assert r["damping_ratio"] is None

    def test_a_short_record_cannot_hold_enough_cycles(self):
        t = _t(8.0)
        x, _ = ring(t, 1.15, 0.05, t_on=0.5)
        r = _estimate(x, 1.15)
        assert r["status"] == "insufficient_evidence" and "cycles" in r["message"]

    def test_intermittent_bursts(self):
        t = _t()
        x = np.cos(2 * np.pi * 1.15 * t) * (((t > 20) & (t < 35)) | ((t > 80) & (t < 95)))
        r = _estimate(x, 1.15)
        assert r["status"] == "insufficient_evidence" and r["reason_code"] == "intermittent_component"
        assert r["damping_ratio"] is None

    def test_constant_amplitude_for_a_limited_interval_is_not_exponential(self):
        t = _t()
        r = _estimate(np.cos(2 * np.pi * 1.15 * t) * ((t > 40) & (t < 70)), 1.15)
        assert r["status"] == "insufficient_evidence" and r["damping_ratio"] is None
        assert r["reason_code"] in ("envelope_scatter_too_high", "fit_quality_too_low", "envelope_not_monotonic")

    def test_frequency_too_close_to_nyquist_is_not_applicable(self):
        t = _t()
        r = _estimate(np.cos(2 * np.pi * 24.9 * t), 24.9)
        assert r["status"] == "not_applicable" and r["reason_code"] == "near_nyquist" and r["damping_ratio"] is None

    def test_frequency_too_close_to_zero_is_not_applicable(self):
        t = _t()
        r = _estimate(np.cos(2 * np.pi * 0.1 * t), 0.1)
        assert r["status"] == "not_applicable" and r["reason_code"] == "near_zero_frequency"

    def test_low_frequency_near_the_analysis_boundary_is_handled_without_error(self):
        t = _t()
        x, alpha = ring(t, 0.3, 0.05, t_on=10.0)
        r = _estimate(x, 0.3)
        assert r["status"] in ("available", "insufficient_evidence")
        if r["status"] == "available":
            assert _rel(r["decay_rate_per_s"], alpha) < 0.10

    def test_every_negative_result_carries_a_reason(self):
        t = _t()
        for x, f in ((np.zeros(t.size) + 1e-30, 1.15), (np.random.default_rng(1).normal(size=t.size), 2.0)):
            r = _estimate(x, f)
            assert r["status"] != "available" and r["reasons"] and r["reasons"][0]["message"]


# ---------------------------------------------------------------- evidence arrays ----

class TestEvidence:
    def test_thinned_envelope_and_fitted_curve(self):
        t = _t(600.0)
        x, _ = ring(t, 1.15, 0.01, t_on=30.0)
        ev = _estimate(x, 1.15)["evidence"]
        assert len(ev["times_s"]) == len(ev["envelope"]) <= de.EVIDENCE_MAX_POINTS
        assert len(ev["fitted_envelope"]) == len(ev["times_s"])
        inside = [i for i, v in enumerate(ev["fitted_envelope"]) if v is not None]
        assert inside and ev["times_s"][inside[0]] >= ev["fit_start_s"] - ev["stride"] * 0.1
        assert ev["valid_start_s"] < ev["fit_start_s"] <= ev["fit_end_s"] <= ev["valid_end_s"]

    def test_why_interval_is_the_fit_interval_and_messages_carry_no_source_times(self):
        """Regression (owner UAT): the Why showed 28.16-42.93 s (source time) beside a Fit interval of 36.36-51.13 s (Time Group display
        time) -- the SAME interval on two time bases. Reasons now carry their times only in `values` (source time, == `fit`), never inside
        the message, so the page can show one basis everywhere."""
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=30.0)
        r = _estimate(x, 1.15, t0=8.2)                      # a time origin that is not zero, as a shifted source would have
        by_code = {e["code"]: e for e in r["reasons"]}
        for code in ("candidate_active", "fit_interval"):
            assert by_code[code]["values"]["start_s"] == pytest.approx(r["fit"]["start_s"])
            assert by_code[code]["values"]["end_s"] == pytest.approx(r["fit"]["end_s"])
            for key in ("start_s", "end_s"):
                assert f"{r['fit'][key]:.4g}" not in by_code[code]["message"]      # no absolute time inside the message
        assert "3×" in by_code["candidate_active"]["message"]

    def test_why_statements_come_from_measured_values(self):
        t = _t()
        x, _ = ring(t, 1.15, 0.05, t_on=30.0)
        r = _estimate(x, 1.15)
        codes = {e["code"] for e in r["reasons"]}
        assert {"candidate_active", "cycles_used", "envelope_change", "exponential_fit", "decay_rate", "damping_ratio", "isolation"} <= codes
        change = next(e for e in r["reasons"] if e["code"] == "envelope_change")
        assert change["values"]["change_percent"] == pytest.approx(r["envelope_change"]["change_percent"])
        assert "decreased" in change["message"] and "MW" in change["message"]


# ---------------------------------------------------------------- service / API ----

@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _service(registries, name="X", *, representation="native", f_min=0.1, f_max=10.0, start=None, end=None, selection=None):
    source_registry, calc_registry = registries
    t = source_registry.get(WS, "src").record.waveform_data["time"].to_numpy()
    return compute_damping(
        workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name=name),
        representation=representation, signal_revision="rev-1",
        window_start_s=float(t[0]) if start is None else start, window_end_s=float(t[-1]) if end is None else end,
        f_min_hz=f_min, f_max_hz=f_max, candidate_frequencies_hz=selection,
        source_registry=source_registry, calc_registry=calc_registry,
    )


def _add(registries, x, t, name="X", **kw):
    registries[0].add(_active("src", t, {name: x}, types={name: "Power"}, **kw))


class TestService:
    def _event(self, noise=0.01, seed=21):
        """Generator-trip-like record (160 s, 50 Hz): a 50-unit event response rising from t = 30 s
        (50x the largest oscillation), a 1.15 Hz ringdown (amplitude 1.0, zeta 2 %) and a 4.95 Hz one
        (amplitude 0.4, zeta 1 %) -- the two frequencies of the owner's MW UAT."""
        t = _t()
        event = 50.0 * np.where(t > 30.0, 1 - np.exp(-(t - 30.0) / 15.0), 0.0)
        a, alpha_a = ring(t, 1.15, 0.02, amplitude=1.0, t_on=30.0)
        b, alpha_b = ring(t, 4.95, 0.01, amplitude=0.4, t_on=30.0)
        return t, event + a + b + np.random.default_rng(seed).normal(0, noise, t.size), (alpha_a, alpha_b)

    def test_real_event_like_two_candidates_get_independent_results(self, registries):
        """Tolerance: 8 % on the decay rate and on zeta of each mode (injected: alpha 0.1445 / 0.3110 1/s,
        zeta 2 % / 1 %), through the detector's own (bin-quantised) candidate frequencies."""
        t, x, (alpha_a, alpha_b) = self._event()
        _add(registries, x, t)
        out = _service(registries)
        assert out["status"] == "ok" and out["setup"]["signal_revision"] == "rev-1"
        low = next(r for r in out["results"] if abs(r["candidate_frequency_hz"] - 1.15) < 0.15)
        high = next(r for r in out["results"] if abs(r["candidate_frequency_hz"] - 4.95) < 0.15)
        assert low["status"] == high["status"] == "available"
        assert _rel(low["decay_rate_per_s"], alpha_a) < 0.08 and _rel(high["decay_rate_per_s"], alpha_b) < 0.08
        assert _rel(low["damping_ratio"], 0.02) < 0.08 and _rel(high["damping_ratio"], 0.01) < 0.08
        assert low["rank"] != high["rank"] and low["fit"] != high["fit"]
        assert out["parameters"]["decay_rate_convention"].startswith("alpha = -sigma")

    def test_candidates_are_the_detectors_and_selection_must_match(self, registries):
        t, x, _ = self._event()
        _add(registries, x, t)
        everything = _service(registries)
        one = _service(registries, selection=[everything["results"][0]["candidate_frequency_hz"]])
        assert len(one["results"]) == 1 and one["results"][0]["rank"] == everything["results"][0]["rank"]
        with pytest.raises(ImportServiceError) as exc:
            _service(registries, selection=[3.33])
        assert exc.value.code == "candidate_mismatch"

    def test_no_candidate_is_an_explained_success(self, registries):
        t = _t()
        _add(registries, np.random.default_rng(4).normal(0, 1, t.size), t)
        out = _service(registries)
        assert out["status"] == "no_candidates" and out["results"] == [] and out["message"]

    def test_invalid_setup_is_revalidated(self, registries):
        t, x, _ = self._event()
        _add(registries, x, t)
        with pytest.raises(ImportServiceError) as exc:
            _service(registries, start=-500.0, end=100.0)
        assert exc.value.code == "invalid_analysis_window"
        with pytest.raises(ImportServiceError) as exc:
            _service(registries, f_max=60.0)
        assert exc.value.code == "invalid_frequency_range"

    def test_a_short_window_keeps_the_candidate_and_reports_insufficient_evidence(self, registries):
        t, x, _ = self._event()
        _add(registries, x, t)
        out = _service(registries, start=0.0, end=33.0, f_min=0.5)      # ends 3 s into the ringdown
        assert out["status"] == "ok" and len(out["results"]) == 1
        r = out["results"][0]
        assert abs(r["candidate_frequency_hz"] - 4.95) < 0.15           # the spectral candidate is preserved
        assert r["status"] == "insufficient_evidence" and r["reason_code"] == "ringdown_interval_too_short"
        assert r["damping_ratio"] is None and r["decay_rate_per_s"] is None and r["reasons"]

    def test_rms_derived_representation(self, registries):
        """A 3 Hz ringdown of the amplitude of a 50 Hz current. RMS keeps the decay rate (a constant gain
        only scales the amplitude); the DEC-173 roll-off caveat is carried forward above the -3 dB frequency."""
        fs = 1000.0
        t = _t(80.0, fs)
        mod, alpha = ring(t, 3.0, 0.04, amplitude=0.2, t_on=20.0)
        i_inst = (1.0 + mod) * np.sin(2 * np.pi * 50.0 * t)
        registries[0].add(_active("src", t, {"IA": i_inst}, types={"IA": "Current"}))
        out = _service(registries, name="IA", representation="rms_magnitude", f_min=0.2, f_max=12.0, start=1.0, end=79.0)
        r = min(out["results"], key=lambda c: abs(c["candidate_frequency_hz"] - 3.0))
        assert abs(r["candidate_frequency_hz"] - 3.0) < 0.3 and r["status"] == "available"
        assert _rel(r["decay_rate_per_s"], alpha) < 0.06
        assert out["representation"]["type"] == "rms_magnitude"

    def test_rms_rolloff_warning_is_carried_forward(self, registries):
        fs = 1000.0
        t = _t(80.0, fs)
        mod, _ = ring(t, 25.0, 0.04, amplitude=0.2, t_on=20.0)
        registries[0].add(_active("src", t, {"IA": (1.0 + mod) * np.sin(2 * np.pi * 50.0 * t)}, types={"IA": "Current"}))
        out = _service(registries, name="IA", representation="rms_magnitude", f_min=1.0, f_max=30.0, start=1.0, end=79.0)
        assert any(w["code"] == "rms_rolloff" for w in out["warnings"])
        assert out["results"] and any(
            w["code"] == "rms_representation_attenuation" for w in out["results"][0]["warnings"]
        )

    def test_performance_is_small_next_to_the_spectrum(self, registries):
        """5 kHz x 160 s with five candidates (measured numbers are recorded in DEC-177)."""
        fs = 5000.0
        t = np.arange(int(fs * 160)) / fs
        x = np.zeros(t.size)
        for f, z in ((1.15, 0.05), (2.3, 0.04), (3.4, 0.03), (4.6, 0.04), (5.9, 0.05)):
            x += ring(t, f, z, amplitude=0.3, t_on=30.0)[0]
        ws = de.window_spectrum(0.0, x, fs)
        started = time.perf_counter()
        for f in (1.15, 2.3, 3.4, 4.6, 5.9):
            de.estimate_damping(ws, f, 1.0, [], "")
        assert time.perf_counter() - started < 3.0


class TestApi:
    BASE = "/api/v1/workspaces/{ws}/oscillation-analysis/damping"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def _body(self, sid, **kw):
        body = {"input": {"kind": "source", "source_id": sid, "channel_name": "IA"}, "representation": "rms_magnitude",
                "signal_revision": "r1", "window_start_s": 0.5, "window_end_s": 4.9,
                "frequency_min_hz": 1.0, "frequency_max_hz": 15.0}
        body.update(kw)
        return body

    def test_endpoint_shape_and_error_codes(self, client):
        sid = _upload(client, "w1", duration=5.0, fm=5.0, depth=0.1)
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] in ("ok", "no_candidates") and body["setup"]["signal_revision"] == "r1"
        assert body["signal"]["name"] == "IA" and "decay_rate_convention" in body["parameters"]
        for cand in body["results"]:
            assert cand["status"] in ("available", "insufficient_evidence", "not_applicable")
            assert cand["candidate_frequency_hz"] > 0 and isinstance(cand["reasons"], list)
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid, candidate_frequencies_hz=[7.77]))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "candidate_mismatch"
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid, window_start_s=3.0, window_end_s=1.0))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_analysis_window"
        r = client.post(self.BASE.format(ws="w1"), json=self._body("nope"))
        assert r.status_code == 404
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid, representation="native"))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "representation_mismatch"
        assert client.get("/api/v1/workspaces/w1/calculated-channels").json() == []
