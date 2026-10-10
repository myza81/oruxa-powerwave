"""Oscillation Analysis -- magnitude-squared coherence (DEC-181 [PROPOSAL]).

Domain tests check the estimator against `scipy.signal.coherence` (a dev-only reference; production is NumPy-only) and feed synthetic signals of known
relationship; service / API tests run the real chain, the synchronization model and the Time Groups. Coherence is evidence only: nothing here
classifies an oscillation, infers causality or states a probability.

Stated tolerances: estimator vs SciPy 1e-9 | identical signals 1 - 1e-9 | sinusoid + weak noise >= 0.99 | unrelated noise < 0.6.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy import signal as sp_signal

from app.domain import coherence as co
from app.domain import spectral_estimation as se
from app.domain.calculated_channel import OP_REVERSE_POLARITY, ChannelRef
from app.main import create_app
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import ImportServiceError
from app.services.oscillation_coherence_service import compute_coherence
from tests.test_oscillation_mode_shape import F, WS, Env, _entry, _ring, _source, _srv_t

FS = 20.0


def _t(duration=120.0, fs=FS, t0=0.0):
    return t0 + np.arange(int(round(duration * fs))) / fs


def _sin(t, f=F, phase_deg=0.0, amplitude=1.0, alpha=0.0, t_on=0.0):
    tau = np.clip(t - t_on, 0, None)
    return amplitude * np.exp(-alpha * tau) * np.cos(2 * np.pi * f * tau + np.deg2rad(phase_deg)) * (t >= t_on)


def _noise(n, sigma, seed):
    return np.random.default_rng(seed).normal(0.0, sigma, n)


def _pair(x, y, fs=FS, f=F):
    return co.analyse_pair(np.asarray(x), np.asarray(y), fs, f)


def _cm(index, t, x, *, episodes=None, tg="g", quantity=("Active Power", "MW"), roots=None, origin="raw", label=None):
    return {"signal_index": index, "label": label or f"S{index}", "origin": origin, "recording": f"rec{index}", "signal_type": quantity[0],
            "unit": quantity[1], "time_group_id": tg, "roots": frozenset(roots or {f"rec{index}::S{index}"}), "t": t, "x": x,
            "episodes": episodes or [(float(t[0]), float(t[-1]))]}


# ------------------------------------------------------------------ estimator ----

class TestEstimator:
    @pytest.mark.parametrize("fs, n", [(20.0, 2400), (50.0, 8000), (25.0, 3001)])
    def test_matches_scipy_coherence_bin_for_bin(self, fs, n):
        rng = np.random.default_rng(n)
        common = rng.normal(size=n)
        x = common + 0.7 * rng.normal(size=n)
        y = np.roll(common, 3) * 0.8 + 0.9 * rng.normal(size=n)
        seg = se.choose_segmentation(n, fs, 0.0)
        freqs, mine = co.welch_coherence(x, y, fs, seg)
        ref_f, ref = sp_signal.coherence(x, y, fs=fs, window="hann", nperseg=seg.nperseg, noverlap=seg.noverlap, detrend="constant")
        np.testing.assert_allclose(freqs, ref_f, atol=1e-12)
        np.testing.assert_allclose(mine, ref, atol=1e-9)
        assert mine.min() >= 0.0 and mine.max() <= 1.0

    def test_identical_signals_are_perfectly_coherent(self):
        t = _t()
        x = _sin(t) + _noise(t.size, 0.3, 1)
        seg = se.choose_segmentation(t.size, FS, 0.0)
        _, c = co.welch_coherence(x, x, FS, seg)
        assert np.all(c > 1 - 1e-9)

    def test_a_known_phase_shift_does_not_reduce_coherence(self):
        t = _t()
        r = _pair(_sin(t) + _noise(t.size, 0.05, 2), _sin(t, phase_deg=137.0, amplitude=0.6) + _noise(t.size, 0.05, 3))
        assert r["status"] == co.STATUS_OK and r["coherence"] > 0.99

    def test_sinusoid_in_independent_noise(self):
        t = _t()
        r = _pair(_sin(t) + _noise(t.size, 5.0, 4), _sin(t, phase_deg=40.0) + _noise(t.size, 5.0, 5))
        assert 0.4 < r["coherence"] < 0.97 and r["exceeds_chance_level"]

    def test_unrelated_noise_is_low(self):
        t = _t()
        r = _pair(_noise(t.size, 1.0, 6), _noise(t.size, 1.0, 7))
        assert r["status"] == co.STATUS_OK and r["coherence"] < 0.6 and r["local_median_coherence"] < 0.6

    def test_different_frequencies_have_low_coherence_at_the_target(self):
        t = _t()
        r = _pair(_sin(t, 0.4) + _noise(t.size, 0.05, 8), _sin(t, 0.9) + _noise(t.size, 0.05, 9))
        assert r["coherence"] < r["chance_level"] and not r["exceeds_chance_level"]       # what unrelated signals give with 8 averages

    def test_one_shared_mode_and_one_unshared_mode(self):
        t = _t()
        x = _sin(t, 0.4) + _sin(t, 1.15, 17.0) + _noise(t.size, 0.1, 10)
        y = _sin(t, 0.4, 100.0) + _sin(t, 1.6, 5.0) + _noise(t.size, 0.1, 11)
        seg = se.choose_segmentation(t.size, FS, 0.0)
        f, c = co.welch_coherence(x, y, FS, seg)
        at = lambda hz: float(c[int(np.argmin(np.abs(f - hz)))])
        assert at(0.4) > 0.95 and at(1.15) < 0.5

    def test_decaying_ringdown_and_sustained_oscillation(self):
        t = _t()
        ring = _pair(_sin(t, alpha=0.01) + _noise(t.size, 0.01, 12), _sin(t, phase_deg=60.0, amplitude=0.7, alpha=0.01) + _noise(t.size, 0.01, 13))
        sustained = _pair(_sin(t) + _noise(t.size, 0.01, 14), _sin(t, phase_deg=200.0) + _noise(t.size, 0.01, 15))
        assert ring["coherence"] > 0.9 and sustained["coherence"] > 0.99

    def test_the_target_bin_and_local_band_are_reported_not_hidden(self):
        t = _t()
        r = _pair(_sin(t, 0.41) + _noise(t.size, 0.05, 16), _sin(t, 0.41, 30.0) + _noise(t.size, 0.05, 17), f=0.40)
        spacing = r["bin_spacing_hz"]
        assert spacing == pytest.approx(FS / r["nperseg"])
        assert abs(r["coherence_frequency_hz"] - 0.40) <= spacing / 2 + 1e-9 and r["target_frequency_hz"] == 0.40
        assert r["target_offset_hz"] == pytest.approx(r["coherence_frequency_hz"] - 0.40)
        assert r["local_peak_coherence"] >= r["coherence"] >= 0.0 and abs(r["local_peak_offset_hz"]) <= spacing + 1e-9
        assert r["local_band_bins"] >= 2

    def test_chance_level_formula(self):
        assert co.independent_segments(8) == 4 and co.independent_segments(7) == 4 and co.independent_segments(1) == 1
        assert co.chance_level(8) == pytest.approx(1 - 0.05 ** (1 / 3))
        assert co.chance_level(15) == pytest.approx(1 - 0.05 ** (1 / 7))
        assert co.chance_level(1) is None and co.chance_level(2) is None            # one independent segment: no meaningful level
        # the level falls as more segments are averaged
        assert co.chance_level(30) < co.chance_level(8)


class TestRefusals:
    """A refusal is a result with no coherence number, never a misleading ~1."""

    def _forced(self, n, nperseg, noverlap, fs=FS):
        count = se.segment_count_for(n, nperseg, noverlap)
        return se.Segmentation(nperseg=nperseg, noverlap=noverlap, segment_count=count, segment_s=nperseg / fs, bin_spacing_hz=fs / nperseg,
                               target_segment_s=nperseg / fs, clamped_to_window=False, unused_tail_samples=0)

    @pytest.mark.parametrize("nperseg, label", [(2400, "one segment"), (1200, "three segments of half the window")])
    def test_one_or_few_segments_are_refused(self, nperseg, label):
        t = _t()
        x, y = _noise(t.size, 1, 21), _noise(t.size, 1, 22)
        seg = self._forced(t.size, nperseg, nperseg // 2 if nperseg < t.size else 0)
        r = co.analyse_pair(x, y, FS, F, seg)
        assert r["status"] == co.STATUS_INSUFFICIENT and r["reason_code"] == "insufficient_segments", label
        assert "insufficient independent segments" in r["message"] and "coherence" not in r

    def test_two_segments_are_refused(self):
        t = _t()
        seg = self._forced(t.size, 1200, 0)
        assert seg.segment_count == 2
        r = co.analyse_pair(_sin(t), _sin(t), FS, F, seg)
        assert r["status"] == co.STATUS_INSUFFICIENT and "coherence" not in r

    def test_identical_one_segment_signals_would_have_been_one_and_are_refused_anyway(self):
        t = _t(30.0)
        seg = self._forced(t.size, t.size, 0)
        assert seg.segment_count == 1
        _, c = co.welch_coherence(_noise(t.size, 1, 1), _noise(t.size, 1, 2), FS, seg)
        assert np.all(c > 1 - 1e-9)                                                # the trap: unrelated noise looks perfect with one segment
        r = co.analyse_pair(_noise(t.size, 1, 1), _noise(t.size, 1, 2), FS, F, seg)
        assert r["status"] == co.STATUS_INSUFFICIENT

    def test_too_few_cycles(self):
        t = _t(10.0)
        r = _pair(_sin(t), _sin(t))
        assert r["status"] == co.STATUS_INSUFFICIENT and r["reason_code"] == "too_few_cycles" and "coherence" not in r

    def test_too_few_cycles_message_is_engineer_facing_and_dynamic(self):
        for duration, f in [(10.0, 0.4), (20.0, 0.25)]:
            t = _t(duration)
            r = _pair(_sin(t, f), _sin(t, f), f=f)
            assert r["reason_code"] == "too_few_cycles"
            cycles = r["reason_values"]["segment_cycles"]
            assert r["message"] == (
                f"Coherence unavailable — the shared {duration:.3g} s interval is too short to resolve a {f:.3g} Hz component reliably. "
                f"Each Welch segment contains only {cycles:.3g} cycles; at least 1.5 cycles are required.")
            assert r["reason_values"]["required_segment_cycles"] == co.MIN_SEGMENT_CYCLES and r["reason_values"]["interval_s"] == pytest.approx(duration)

    def test_too_few_samples(self):
        r = co.analyse_pair(np.zeros(5), np.zeros(5), FS, F)
        assert r["status"] == co.STATUS_INSUFFICIENT and r["reason_code"] == "too_few_samples"

    def test_too_few_segments_for_a_short_window(self):
        t = _t(1.5)                                                                 # 30 samples at 2 Hz: eight-sample segments, fewer than 7 of them
        r = co.analyse_pair(_sin(t, 2.0), _sin(t, 2.0), FS, 2.0)
        assert r["status"] == co.STATUS_INSUFFICIENT and r["reason_code"] == "insufficient_segments"

    def test_sampling_too_coarse(self):
        t = _t(400.0, 2.0)
        r = co.analyse_pair(_sin(t, 0.4), _sin(t, 0.4), 2.0, 0.4)
        assert r["status"] == co.STATUS_INSUFFICIENT and r["reason_code"] == "sampling_too_coarse"

    def test_missing_samples_are_refused(self):
        t = _t()
        x = _sin(t)
        y = x.copy()
        y[10] = np.nan
        assert co.analyse_pair(x, y, FS, F)["reason_code"] == "non_finite_samples"


# ------------------------------------------------------------------ grid ----

class TestCommonGrid:
    def test_nothing_is_upsampled_and_the_rate_is_the_slowest(self):
        a, b = _t(60, 20.0), _t(60, 25.0)
        members = [_cm(0, a, _sin(a)), _cm(1, b, _sin(b, phase_deg=30.0))]
        out = co.analyse_component(members=members, reference_index=0, frequency_hz=F)
        assert out["pairs"][0]["sample_rate_hz"] == pytest.approx(20.0, rel=1e-3)

    def test_the_rate_is_capped_for_cost(self):
        t = _t(30.0, 500.0)
        out = co.analyse_component(members=[_cm(0, t, _sin(t)), _cm(1, t, _sin(t, phase_deg=30.0))], reference_index=0, frequency_hz=F)
        assert out["pairs"][0]["sample_rate_hz"] == pytest.approx(co.MAX_COMMON_RATE_HZ, rel=1e-3)

    def test_decimation_keeps_the_oscillation(self):
        t = _t(120.0, 500.0)
        x = _sin(t, amplitude=2.0) + 0.5 * np.cos(2 * np.pi * 61.0 * t)             # high-frequency content must not alias into the band
        grid = np.arange(0, 119.0, 1 / 50.0)
        g = co.to_grid(t, x, grid, 50.0)
        assert np.max(np.abs(g - _sin(grid, amplitude=2.0))) < 0.15

    def test_different_sample_rates_give_the_same_coherence(self):
        ta, tb = _t(120.0, 20.0), _t(120.0, 25.0)
        out = co.analyse_component(members=[_cm(0, ta, _sin(ta) + _noise(ta.size, 0.05, 31)), _cm(1, tb, _sin(tb, phase_deg=80.0) + _noise(tb.size, 0.05, 32))],
                                   reference_index=0, frequency_hz=F)
        p = out["pairs"][0]
        assert p["status"] == co.STATUS_OK and p["coherence"] > 0.97


# ------------------------------------------------------------------ component ----

class TestComponent:
    def _three(self, t):
        return [_cm(0, t, _sin(t) + _noise(t.size, 0.05, 41)), _cm(1, t, _sin(t, phase_deg=120.0, amplitude=0.7) + _noise(t.size, 0.05, 42)),
                _cm(2, t, _sin(t, phase_deg=10.0, amplitude=0.4) + _noise(t.size, 0.05, 43))]

    def test_reference_against_each_member_and_the_remaining_pairs_are_kept(self):
        out = co.analyse_component(members=self._three(_t()), reference_index=0, frequency_hz=F)
        assert out["reference"] == {"signal_index": 0, "label": "S0"}
        assert [p["member_index"] for p in out["pairs"]] == [1, 2] and [(p["reference_index"], p["member_index"]) for p in out["other_pairs"]] == [(1, 2)]
        assert all(p["status"] == co.STATUS_OK and p["coherence"] > 0.95 for p in out["pairs"] + out["other_pairs"])

    def test_same_variable_and_cross_variable_are_distinguished(self):
        t = _t()
        members = [_cm(0, t, _sin(t) + _noise(t.size, 0.05, 44)), _cm(1, t, _sin(t, phase_deg=30.0) + _noise(t.size, 0.05, 45)),
                   _cm(2, t, _sin(t, phase_deg=80.0, amplitude=0.02) + _noise(t.size, 0.001, 46), quantity=("Frequency", "Hz"))]
        out = co.analyse_component(members=members, reference_index=0, frequency_hz=F)
        kinds = {p["member_index"]: p["relationship_type"] for p in out["pairs"]}
        assert kinds == {1: co.SAME_VARIABLE, 2: co.CROSS_VARIABLE}
        cross = next(p for p in out["pairs"] if p["member_index"] == 2)
        assert cross["status"] == co.STATUS_OK and "cross_variable" in [w["code"] for w in cross["warnings"]]
        assert "cross_variable" not in [w["code"] for w in next(p for p in out["pairs"] if p["member_index"] == 1)["warnings"]]
        assert "cross_variable_scope" in [e["code"] for e in out["limitations"]]

    def test_the_common_interval_is_the_longest_shared_episode(self):
        t = _t(160.0)
        a = _cm(0, t, _sin(t), episodes=[(10.0, 150.0)])
        b = _cm(1, t, _sin(t, phase_deg=50.0), episodes=[(40.0, 160.0)])
        p = co.analyse_component(members=[a, b], reference_index=0, frequency_hz=F)["pairs"][0]
        assert (p["common_interval"]["start_s"], p["common_interval"]["end_s"]) == (40.0, 150.0)
        assert p["cycles_used"] == pytest.approx(110.0 * F) and p["common_interval"]["time_basis"] == "workspace_time"

    def test_separated_bursts_are_not_averaged(self):
        t = _t(240.0)
        episodes = [(10.0, 60.0), (120.0, 230.0)]
        gate = ((t >= 10) & (t <= 60)) | ((t >= 120) & (t <= 230))
        p = co.analyse_component(members=[_cm(0, t, _sin(t) * gate, episodes=episodes), _cm(1, t, _sin(t, phase_deg=70.0) * gate, episodes=episodes)],
                                 reference_index=0, frequency_hz=F)["pairs"][0]
        assert p["common_interval"]["start_s"] == 120.0 and p["common_interval"]["end_s"] == 230.0
        assert "intermittent_activity" in [w["code"] for w in p["warnings"]] and p["coherence"] > 0.95

    def test_non_overlapping_episodes_are_refused(self):
        t = _t(240.0)
        p = co.analyse_component(members=[_cm(0, t, _sin(t), episodes=[(0.0, 80.0)]), _cm(1, t, _sin(t), episodes=[(120.0, 230.0)])],
                                 reference_index=0, frequency_hz=F)["pairs"][0]
        assert p["status"] == co.STATUS_INSUFFICIENT and p["reason_code"] == "no_common_activity" and p["coherence"] is None

    def test_a_short_common_interval_is_refused_rather_than_reported(self):
        t = _t(120.0)
        p = co.analyse_component(members=[_cm(0, t, _sin(t), episodes=[(10.0, 22.0)]), _cm(1, t, _sin(t, phase_deg=50.0), episodes=[(10.0, 22.0)])],
                                 reference_index=0, frequency_hz=F)["pairs"][0]
        assert p["status"] == co.STATUS_INSUFFICIENT and p["coherence"] is None

    def test_different_time_groups_are_not_compared(self):
        t = _t()
        p = co.analyse_component(members=[_cm(0, t, _sin(t), tg="A"), _cm(1, t, _sin(t, phase_deg=30.0), tg="B")], reference_index=0, frequency_hz=F)["pairs"][0]
        assert p["status"] == co.STATUS_UNAVAILABLE and p["reason_code"] == "incompatible_time_basis"
        assert p["message"] == co.NO_TIME_BASIS_MESSAGE and p["coherence"] is None

    def test_shared_provenance_is_flagged(self):
        t = _t()
        p = co.analyse_component(members=[_cm(0, t, _sin(t), roots={"src::P"}), _cm(1, t, -_sin(t), roots={"src::P"}, origin="calculated")],
                                 reference_index=0, frequency_hz=F)["pairs"][0]
        assert p["coherence"] > 0.999 and "shared_measurement_provenance" in [w["code"] for w in p["warnings"]]

    def test_phase_with_low_coherence_warns_but_does_not_invalidate(self):
        t = _t()
        weak = [_cm(0, t, _noise(t.size, 1, 51)), _cm(1, t, _noise(t.size, 1, 52))]
        p = co.analyse_component(members=weak, reference_index=0, frequency_hz=F, phase_by_member={1: 172.0})["pairs"][0]
        warning = next(w for w in p["warnings"] if w["code"] == "phase_with_low_coherence")
        assert "Relative phase is available, but cross-spectral coherence at the component frequency is low" in warning["message"]
        assert p["relative_phase_deg"] == 172.0                                      # the phase itself is left as it was
        strong = [_cm(0, t, _sin(t) + _noise(t.size, 0.05, 53)), _cm(1, t, _sin(t, phase_deg=172.0) + _noise(t.size, 0.05, 54))]
        q = co.analyse_component(members=strong, reference_index=0, frequency_hz=F, phase_by_member={1: 172.0})["pairs"][0]
        assert "phase_with_low_coherence" not in [w["code"] for w in q["warnings"]]

    def test_why_and_limitations_are_deterministic_text(self):
        t = _t()
        out = co.analyse_component(members=self._three(t)[:2], reference_index=0, frequency_hz=F)
        text = " ".join(r["message"] for r in out["pairs"][0]["reasons"])
        for needle in ("S0 and S1 contain the same ~0.4 Hz component", "Signals overlap from", "Coherence at", "Welch segments", "local coherence peak",
                       "chance level, not the probability that the oscillation is real"):
            assert needle in text, needle
        limits = " ".join(e["message"] for e in out["limitations"])
        assert "does not identify causality or direction" in limits and "does not prove an inter-area mode" in limits
        blob = str(out).lower()
        for word in ("confidence", "confirmed", "inter-area confirmed", "causes"):
            assert word not in blob.replace("does not identify causality", "")

    @pytest.mark.parametrize("count, fs, duration", [(2, 50.0, 160.0), (5, 50.0, 160.0), (8, 50.0, 160.0), (8, 500.0, 160.0)])
    def test_performance(self, count, fs, duration):
        t = _t(duration, fs)
        members = [_cm(i, t, _sin(t, phase_deg=20.0 * i, alpha=0.005) + _noise(t.size, 0.05, 60 + i)) for i in range(count)]
        started = time.perf_counter()
        out = co.analyse_component(members=members, reference_index=0, frequency_hz=F)
        elapsed = time.perf_counter() - started
        assert all(p["status"] == co.STATUS_OK for p in out["pairs"])
        assert elapsed < (2.0 if fs <= 50 else 8.0), elapsed
        print(f"\n[perf] coherence {count} signals x {duration:.0f} s @ {fs:.0f} Hz: {elapsed * 1000:.0f} ms ({len(out['pairs'])} reference pairs + {len(out['other_pairs'])} other)")


# ------------------------------------------------------------------ service ----

def _slow(t, f=F, phase=0.0, amp=4.0, seed=0, **kw):
    """A slowly decaying ringdown (alpha 0.01 /s): a long enough common interval for a coherence estimate."""
    return _ring(t, f, phase, amp, alpha=0.01, seed=seed, **kw)


@pytest.fixture
def env():
    return Env()


def _run(env, entries, component=None):
    return compute_coherence(workspace_id=WS, entries=entries, f_min_hz=0.1, f_max_hz=5.0, component_frequency_hz=component,
                             source_registry=env.sources, calc_registry=env.calc, sync_registry=env.sync)


class TestService:
    def _two_mw(self, env, alpha=0.01, phase=172.0):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"POWER A": _ring(t, F, 0.0, 4.0, alpha=alpha, seed=1)}, {"POWER A": "Active Power"}))
        env.sources.add(_source("recB", t, {"POWER B": _ring(t, F, phase, 3.1, alpha=alpha, seed=2)}, {"POWER B": "Active Power"}))
        return _run(env, [_entry("recA", "POWER A"), _entry("recB", "POWER B")])

    def test_owner_style_pair_with_a_long_enough_interval(self, env):
        out = self._two_mw(env)
        assert out["status"] == "ok" and len(out["components"]) == 1
        comp = out["components"][0]
        assert comp["reference_rule"] == "mode_shape_reference" and comp["reference"]["label"] in ("POWER A", "POWER B")
        p = comp["pairs"][0]
        assert p["status"] == "ok" and p["relationship_type"] == "same_variable" and p["coherence"] > 0.95
        assert abs(p["coherence_frequency_hz"] - comp["component_frequency_hz"]) <= p["bin_spacing_hz"]
        assert p["segment_count"] >= co.MIN_SEGMENTS and p["common_interval"]["duration_s"] > 60.0 and p["exceeds_chance_level"]
        assert p["relative_phase_deg"] is not None and abs(abs(p["relative_phase_deg"]) - 172.0) < 2.0       # the mode-shape phase, unchanged
        assert "phase_with_low_coherence" not in [w["code"] for w in p["warnings"]]

    def test_a_fast_ringdown_has_too_short_an_interval_and_is_refused(self, env):
        """The owner's real case had a short active interval: a conservative refusal, never a meaningless number."""
        out = self._two_mw(env, alpha=0.075)
        p = out["components"][0]["pairs"][0]
        assert p["status"] == "insufficient_evidence" and p["coherence"] is None and p["message"]
        assert p["reason_code"] in ("too_few_cycles", "insufficient_segments")

    def test_mw_and_frequency_pairs_keep_their_relationship_type(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"MW1": _slow(t, seed=3), "MW2": _slow(t, phase=120.0, amp=3.0, seed=4),
                                           "FQ1": _slow(t, phase=80.0, amp=0.05, seed=5, noise=0.0005)},
                                {"MW1": "Active Power", "MW2": "Active Power", "FQ1": "Frequency"}))
        out = _run(env, [_entry("rec", "MW1"), _entry("rec", "MW2"), _entry("rec", "FQ1")])
        comp = out["components"][0]
        kinds = {p["member_signal"]: p["relationship_type"] for p in comp["pairs"]}
        assert kinds == {"MW2": "same_variable", "FQ1": "cross_variable"} or kinds == {"MW1": "same_variable", "FQ1": "cross_variable"}
        assert comp["cross_variable"] is not None
        assert all(p["status"] == "ok" for p in comp["pairs"])

    def test_the_reference_falls_back_to_prominence_when_there_is_no_mode_shape(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"MW": _slow(t, seed=6), "FQ": _slow(t, phase=80.0, amp=0.05, seed=7, noise=0.0005)},
                                {"MW": "Active Power", "FQ": "Frequency"}))
        comp = _run(env, [_entry("rec", "MW"), _entry("rec", "FQ")])["components"][0]
        assert comp["reference_rule"] == "highest_candidate_prominence" and comp["pairs"][0]["relationship_type"] == "cross_variable"
        assert comp["pairs"][0]["relative_phase_deg"] is None                       # no same-variable mode shape exists

    def test_time_alignment_regression_manual_offset_moves_the_common_interval(self, env):
        """B rings from 50 s, A from 30 s (source time). Un-aligned the common interval starts at ~50 s; a manual offset of -20 s
        on B (through the existing synchronization model) makes both start together, so the interval starts at ~30 s."""
        t = _srv_t()
        env.sources.add(_source("recA", t, {"P": _slow(t, seed=8, t_on=30.0)}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": _slow(t, phase=90.0, seed=9, t_on=50.0)}, {"P": "Active Power"}))
        entries = [_entry("recA", "P", label="A"), _entry("recB", "P", label="B")]
        before = _run(env, entries)["components"][0]["pairs"][0]
        env.sync.set_offset(WS, "recB", -20.0)
        after = _run(env, entries)["components"][0]["pairs"][0]
        assert before["status"] == "ok" and after["status"] == "ok"
        assert before["common_interval"]["start_s"] == pytest.approx(50.0, abs=4.0)
        assert after["common_interval"]["start_s"] == pytest.approx(30.0, abs=4.0)
        assert after["common_interval"]["duration_s"] > before["common_interval"]["duration_s"]

    def test_the_browser_offset_is_ignored(self, env):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"P": _slow(t, seed=10)}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": _slow(t, phase=30.0, seed=11)}, {"P": "Active Power"}))
        forged = [{**_entry("recA", "P", label="A"), "offset_s": 0.0}, {**_entry("recB", "P", label="B"), "offset_s": 99.0}]
        p = _run(env, forged)["components"][0]["pairs"][0]
        assert p["status"] == "ok" and p["coherence"] > 0.95

    def test_recordings_in_different_time_groups_are_not_compared(self, env):
        from datetime import timedelta
        from tests.test_oscillation_representation import START
        t = _srv_t()
        env.sources.add(_source("recA", t, {"P": _slow(t, seed=12)}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": _slow(t, phase=60.0, seed=13)}, {"P": "Active Power"}, start=START + timedelta(days=3)))
        p = _run(env, [_entry("recA", "P", label="A"), _entry("recB", "P", label="B")])["components"][0]["pairs"][0]
        assert p["status"] == "unavailable" and p["reason_code"] == "incompatible_time_basis" and p["message"] == co.NO_TIME_BASIS_MESSAGE
        assert p["coherence"] is None

    def test_raw_and_calculated_copy_share_provenance(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"P": _slow(t, seed=14)}, {"P": "Active Power"}))
        neg = create_calculated_channel(workspace_id=WS, name="-P", operation=OP_REVERSE_POLARITY,
                                        inputs=[ChannelRef(kind="source", source_id="rec", channel_name="P")], parameters={},
                                        source_registry=env.sources, calc_registry=env.calc)
        out = _run(env, [_entry("rec", "P"), _entry("rec", "-P", kind="calculated", calc_id=neg.id)])
        p = out["components"][0]["pairs"][0]
        assert p["status"] == "ok" and p["coherence"] > 0.99 and "shared_measurement_provenance" in [w["code"] for w in p["warnings"]]

    def test_component_filter_no_components_and_validation(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"A": _slow(t, seed=15), "B": _slow(t, phase=40.0, seed=16)}, {"A": "Active Power", "B": "Active Power"}))
        entries = [_entry("rec", "A"), _entry("rec", "B")]
        assert len(_run(env, entries, component=0.4)["components"]) == 1
        assert _run(env, entries, component=3.3)["components"] == []
        rng = np.random.default_rng(3)
        env.sources.add(_source("noise", t, {"X": rng.normal(size=t.size), "Y": rng.normal(size=t.size)}, {"X": "Active Power", "Y": "Active Power"}))
        assert _run(env, [_entry("noise", "X"), _entry("noise", "Y")])["status"] == "no_components"
        with pytest.raises(ImportServiceError):
            _run(env, [_entry("rec", "A")])

    def test_nothing_is_classified(self, env):
        text = str(self._two_mw(env)).lower().replace("does not prove an inter-area mode", "").replace("not a probability or a confidence", "")
        for word in ("inter-area", "local mode", " sso ", "confidence", "probable"):
            assert word not in text

    @pytest.mark.parametrize("count", [2, 5, 8])
    def test_service_cost(self, env, count):
        t = _srv_t()
        channels = {f"P{i}": _slow(t, phase=25.0 * i, amp=3.0 + 0.1 * i, seed=70 + i) for i in range(count)}
        env.sources.add(_source("rec", t, channels, {k: "Active Power" for k in channels}))
        out = _run(env, [_entry("rec", k) for k in channels])
        comp = out["components"][0]
        assert len(comp["pairs"]) == count - 1 and all(p["status"] == "ok" for p in comp["pairs"])
        assert out["timings_ms"]["coherence"] < 3000.0
        print(f"\n[perf] service {count} signals: analysis {out['timings_ms']['signal_analysis']:.0f} ms, coherence incl. mode-shape reference {out['timings_ms']['coherence']:.0f} ms")


class TestApi:
    URL = "/api/v1/workspaces/{ws}/oscillation-analysis/coherence"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def test_validation_and_unknown_signals(self, client):
        url = self.URL.format(ws="w1")
        sig = {"input": {"kind": "source", "source_id": "nope", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 10}
        assert client.post(url, json={"signals": [sig], "frequency_min_hz": 0.1, "frequency_max_hz": 5}).status_code == 422
        r = client.post(url, json={"signals": [sig, {**sig, "input": {"kind": "source", "source_id": "nope", "channel_name": "B"}}],
                                   "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "no_components" and body["parameters"]["min_segments"] == co.MIN_SEGMENTS
        assert "not a probability" in body["parameters"]["definition"]

    def test_the_api_returns_the_numerical_evidence(self, client):
        t = _srv_t()
        registry = client.app.state.workspace_registry
        registry.add(_source("recA", t, {"P": _slow(t, seed=41)}, {"P": "Active Power"}))
        registry.add(_source("recB", t, {"P": _slow(t, phase=172.0, amp=3.0, seed=42)}, {"P": "Active Power"}))
        sig = lambda src: {"input": {"kind": "source", "source_id": src, "channel_name": "P"}, "representation": "native",
                           "window_start_s": 0.0, "window_end_s": 159.98, "label": src}
        r = client.post(self.URL.format(ws=WS), json={"signals": [sig("recA"), sig("recB")], "frequency_min_hz": 0.1, "frequency_max_hz": 5.0, "offset_s": 99.0})
        assert r.status_code == 200, r.text
        comp = r.json()["components"][0]
        p = comp["pairs"][0]
        assert p["status"] == "ok" and 0.0 <= p["coherence"] <= 1.0 and p["chance_level"] is not None
        assert set(p) >= {"coherence_frequency_hz", "bin_spacing_hz", "local_peak_coherence", "local_peak_frequency_hz", "segment_count", "common_interval", "reasons", "warnings"}
        assert comp["limitations"]
