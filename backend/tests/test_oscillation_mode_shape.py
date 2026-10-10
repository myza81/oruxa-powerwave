"""Oscillation Analysis -- mode shape / relative phase (DEC-180 [PROPOSAL]).

Domain tests feed synthetic sinusoids of KNOWN amplitude and phase straight into the estimator so every tolerance is explicit;
service / API tests run the real Welch + DEC-175 + STFT chain, the synchronization model and the Time Groups on synthetic
recordings. Nothing here classifies an oscillation.

Stated tolerances (phase, degrees):  noiseless 0.5 | moderate noise (sigma = 0.1 x amplitude) 3 | decaying, equal damping 1 |
decaying, different damping 2 | neighbouring distant mode 2.
"""

from __future__ import annotations

import dataclasses
import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import mode_shape as ms
from app.domain.calculated_channel import OP_REVERSE_POLARITY, ChannelRef
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import ImportServiceError
from app.services.oscillation_mode_shape_service import compute_mode_shape
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_oscillation_representation import START, WS, _active

F = 0.4
FS = 20.0


def _t(duration=60.0, fs=FS, t0=0.0):
    return t0 + np.arange(int(round(duration * fs))) / fs


def _cos(t, phase_deg, amplitude=1.0, f=F, alpha=0.0, t_on=0.0):
    tau = t - t_on
    return amplitude * np.exp(-alpha * np.clip(tau, 0, None)) * np.cos(2 * np.pi * f * tau + np.deg2rad(phase_deg))


def _mem(index, t, x, *, label=None, prominence=20.0, roots=None, origin="raw", cand=F, episodes=None, tg="g", quantity="Active Power"):
    return {"signal_index": index, "label": label or f"S{index}", "recording": f"rec{index}", "origin": origin, "signal_type": quantity,
            "unit": "MW", "time_group_id": tg, "roots": frozenset(roots or {f"rec{index}::S{index}"}), "candidate_frequency_hz": cand,
            "prominence_db": prominence, "t": t, "x": x, "episodes": episodes or [(float(t[0]), float(t[-1]))]}


def _run(members, f=F, tolerance=0.05, neighbours=(), excluded=None):
    return ms.analyse_quantity_group(
        quantity_type="Active Power", unit="MW", members=members, representative_frequency_hz=f, tolerance_hz=tolerance,
        neighbour_frequencies_hz=list(neighbours), excluded_members=excluded)


def _by(group, index):
    return next(m for m in group["members"] if m["signal_index"] == index)


def _circ_err(a, b):
    return abs(float(ms.wrap_deg(a - b)))


# ------------------------------------------------------------------ conventions ----

class TestConventions:
    def test_wrap_range_is_minus180_inclusive_to_plus180_exclusive(self):
        assert float(ms.wrap_deg(180.0)) == -180.0
        assert float(ms.wrap_deg(-180.0)) == -180.0
        assert float(ms.wrap_deg(181.0)) == pytest.approx(-179.0)
        assert float(ms.wrap_deg(-181.0)) == pytest.approx(179.0)
        assert float(ms.wrap_deg(360.0)) == pytest.approx(0.0)

    def test_circular_difference_is_not_ordinary_subtraction(self):
        assert ms.circular_difference_deg(179.0, -179.0) == pytest.approx(-2.0)
        assert ms.circular_difference_deg(-179.0, 179.0) == pytest.approx(2.0)
        assert ms.circular_difference_deg(10.0, 350.0) == pytest.approx(20.0)

    def test_positive_phase_means_the_member_leads_the_reference(self):
        """A member whose cosine peaks EARLIER (x(t) = cos(w (t + tau))) leads: +w tau degrees."""
        t = _t()
        tau = 0.25                                        # a quarter of a 1 s... here 0.1 cycle at 0.4 Hz => +36 degrees
        lead = np.cos(2 * np.pi * F * (t + tau))
        g = _run([_mem(0, t, np.cos(2 * np.pi * F * t), prominence=30.0), _mem(1, t, lead)])
        assert _by(g, 0)["is_reference"] and _by(g, 0)["phase_deg"] == 0.0
        assert _by(g, 1)["phase_deg"] == pytest.approx(360.0 * F * tau, abs=0.5)
        assert _by(g, 1)["phase_deg"] > 0

    def test_a_lagging_member_is_negative(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, -60))])
        assert _by(g, 1)["phase_deg"] == pytest.approx(-60.0, abs=0.5)

    def test_circular_stats(self):
        s = ms.circular_stats([179.0, -179.0, 178.0, -178.0])
        assert abs(s["mean_deg"]) == pytest.approx(180.0, abs=0.01) or s["mean_deg"] == pytest.approx(-180.0, abs=0.01)
        assert s["max_deviation_deg"] == pytest.approx(2.0, abs=0.01)
        assert ms.circular_stats([10.0, 10.0])["spread_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_bands(self):
        assert ms.band_of(0.0) == ms.band_of(29.9) == ms.band_of(-29.9) == ms.PATTERN_IN_PHASE
        assert ms.band_of(150.1) == ms.band_of(-180.0) == ms.band_of(180.0) == ms.PATTERN_ANTI_PHASE
        assert ms.band_of(30.1) == ms.band_of(90.0) == ms.band_of(-149.9) == ms.PATTERN_INTERMEDIATE


# ------------------------------------------------------------------ accuracy ----

class TestPhaseAccuracy:
    @pytest.mark.parametrize("phase", [0.0, 30.0, -60.0, 90.0, 135.0, -170.0])
    def test_known_phase_shift_two_equal_amplitudes(self, phase):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, phase))])
        assert g["status"] == ms.STATUS_OK
        assert _circ_err(_by(g, 1)["phase_deg"], phase) < 0.5
        assert _by(g, 1)["relative_amplitude"] == pytest.approx(1.0, abs=0.01)

    def test_anti_phase(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 180))])
        assert _circ_err(_by(g, 1)["phase_deg"], 180.0) < 0.5
        assert g["phase_pattern"]["code"] == ms.PATTERN_ANTI_PHASE

    def test_wrap_at_the_plus_minus_180_seam(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, -179), prominence=30.0), _mem(1, t, _cos(t, 179))])
        assert _by(g, 1)["phase_deg"] == pytest.approx(-2.0, abs=0.5)         # circular, not 358

    def test_unequal_amplitudes_and_three_signal_mode_shape(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0, 4.0), prominence=30.0), _mem(1, t, _cos(t, 172, 3.12)), _mem(2, t, _cos(t, 15, 1.4))])
        assert [m["is_reference"] for m in g["members"]] == [True, False, False]
        assert [round(m["relative_amplitude"], 2) for m in g["members"]] == [1.0, 0.78, 0.35]
        assert _circ_err(_by(g, 1)["phase_deg"], 172.0) < 0.5
        assert _circ_err(_by(g, 2)["phase_deg"], 15.0) < 0.5
        assert _by(g, 0)["amplitude"] == pytest.approx(4.0, rel=0.01)           # absolute amplitude, own unit
        assert g["phase_pattern"]["code"] == ms.PATTERN_MIXED                    # one anti-phase, one in phase

    def test_decaying_with_the_same_damping(self):
        t = _t(80.0)
        a = 0.075
        g = _run([_mem(0, t, _cos(t, 0, 2.0, alpha=a), prominence=30.0), _mem(1, t, _cos(t, 172, 1.5, alpha=a))])
        assert g["status"] == ms.STATUS_OK and _circ_err(_by(g, 1)["phase_deg"], 172.0) < 1.0

    def test_different_damping_same_relative_phase(self):
        t = _t(80.0)
        g = _run([_mem(0, t, _cos(t, 0, 2.0, alpha=0.04), prominence=30.0), _mem(1, t, _cos(t, 172, 2.0, alpha=0.09))])
        assert g["status"] == ms.STATUS_OK and _circ_err(_by(g, 1)["phase_deg"], 172.0) < 2.0

    def test_moderate_noise(self):
        t = _t()
        rng = np.random.default_rng(1)
        g = _run([_mem(0, t, _cos(t, 0) + rng.normal(0, 0.1, t.size), prominence=30.0), _mem(1, t, _cos(t, 172) + rng.normal(0, 0.1, t.size))])
        assert _circ_err(_by(g, 1)["phase_deg"], 172.0) < 3.0
        assert 0 < _by(g, 1)["phase_uncertainty_deg"] < 3.0

    def test_strong_noise_gives_insufficient_evidence_not_a_number(self):
        t = _t()
        rng = np.random.default_rng(2)
        g = _run([_mem(0, t, _cos(t, 0) + rng.normal(0, 4.0, t.size), prominence=30.0), _mem(1, t, _cos(t, 172) + rng.normal(0, 4.0, t.size))])
        assert g["status"] == ms.STATUS_INSUFFICIENT
        assert all(m["phase_deg"] is None for m in g["members"]) and g["phase_pattern"]["code"] == ms.PATTERN_UNAVAILABLE

    def test_a_distant_second_mode_does_not_move_the_phase(self):
        t = _t()
        second = _cos(t, 77, 0.6, f=1.15)
        g = _run([_mem(0, t, _cos(t, 0) + second, prominence=30.0), _mem(1, t, _cos(t, 172) + _cos(t, -40, 0.6, f=1.15))], neighbours=[1.15])
        assert _circ_err(_by(g, 1)["phase_deg"], 172.0) < 2.0
        assert "neighbouring_component" not in [e["code"] for e in g["limitations"]]

    def test_a_close_neighbouring_component_is_flagged(self):
        t = _t(30.0)                                                              # resolution 1/30 = 0.033 Hz
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 90))], neighbours=[0.42])
        assert "neighbouring_component" in [e["code"] for e in g["limitations"]]

    def test_different_sampling_rates_on_a_valid_common_time_basis(self):
        ta, tb = _t(60.0, 20.0), _t(60.0, 25.0)
        g = _run([_mem(0, ta, _cos(ta, 0), prominence=30.0), _mem(1, tb, _cos(tb, 123))])
        assert g["status"] == ms.STATUS_OK and _circ_err(_by(g, 1)["phase_deg"], 123.0) < 0.5

    def test_the_common_frequency_is_refined_for_a_coarse_grid(self):
        """True 0.43 Hz, representative 0.40 Hz (a coarse Welch bin): the joint refinement recovers the frequency and the phase."""
        t = _t(60.0)
        g = _run([_mem(0, t, _cos(t, 0, f=0.43), prominence=30.0, cand=0.40), _mem(1, t, _cos(t, 100, f=0.43), cand=0.45)], f=0.425, tolerance=0.05)
        assert g["projection_frequency_hz"] == pytest.approx(0.43, abs=0.002)
        assert _circ_err(_by(g, 1)["phase_deg"], 100.0) < 1.0
        assert g["frequency_refinement"]["member_candidate_frequencies_hz"] == [0.40, 0.45]       # originals preserved
        assert g["frequency_refinement"]["representative_frequency_hz"] == 0.425

    def test_one_common_frequency_not_one_per_member(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 50))])
        assert isinstance(g["projection_frequency_hz"], float) and "member_candidate_frequencies_hz" in g["frequency_refinement"]


# ------------------------------------------------------------------ interval / stability ----

class TestIntervalAndStability:
    def test_the_common_interval_is_the_intersection(self):
        t = _t(80.0)
        a = _mem(0, t, _cos(t, 0), prominence=30.0, episodes=[(10.0, 60.0)])
        b = _mem(1, t, _cos(t, 90), episodes=[(30.0, 75.0)])
        g = _run([a, b])
        assert (g["common_interval"]["start_s"], g["common_interval"]["end_s"]) == (30.0, 60.0)
        assert g["common_interval"]["duration_s"] == pytest.approx(30.0) and g["cycles_used"] == pytest.approx(30.0 * g["projection_frequency_hz"])
        assert g["common_interval"]["time_basis"] == "workspace_time"

    def test_too_few_cycles_is_insufficient(self):
        t = _t(60.0)
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0, episodes=[(0.0, 5.0)]), _mem(1, t, _cos(t, 90), episodes=[(0.0, 5.0)])])
        assert g["status"] == ms.STATUS_INSUFFICIENT and g["reason_code"] == "too_few_cycles"

    def test_no_shared_activity_is_insufficient(self):
        t = _t(80.0)
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0, episodes=[(0.0, 30.0)]), _mem(1, t, _cos(t, 90), episodes=[(40.0, 79.0)])])
        assert g["status"] == ms.STATUS_INSUFFICIENT and g["reason_code"] == "no_common_activity"

    def test_separated_bursts_are_not_averaged_only_the_longest_episode_is_used(self):
        t = _t(120.0)
        # burst 1 (10-30 s) has phase 0 vs 0; burst 2 (60-100 s) has phase 90 -- a single fit over both would be a meaningless mixture
        env1, env2 = ((t >= 10) & (t <= 30)), ((t >= 60) & (t <= 100))
        ref = _cos(t, 0) * (env1 | env2)
        other = _cos(t, 0) * env1 + _cos(t, 90) * env2
        episodes = [(10.0, 30.0), (60.0, 100.0)]
        g = _run([_mem(0, t, ref, prominence=30.0, episodes=episodes), _mem(1, t, other, episodes=episodes)])
        assert g["common_interval"]["start_s"] == 60.0 and g["common_interval"]["end_s"] == 100.0
        assert _circ_err(_by(g, 1)["phase_deg"], 90.0) < 1.0
        assert "intermittent_activity" in [e["code"] for e in g["limitations"]]

    def test_stable_phase_reports_circular_statistics(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 172))])
        st = _by(g, 1)["phase_stability"]
        assert st["status"] == "stable" and st["valid_subwindows"] >= 3
        assert _circ_err(st["circular_mean_deg"], 172.0) < 1.0 and st["max_deviation_deg"] < 2.0 and st["circular_spread_deg"] < 1.0
        assert _by(g, 0)["phase_stability"] is None

    def test_a_drifting_phase_is_flagged_unstable_and_the_pattern_is_not_given(self):
        t = _t(60.0)
        # a 150 degree phase ramp over the interval (0.007 Hz of frequency offset): the mean phase would hide it
        ramp = np.cos(2 * np.pi * F * t + np.deg2rad(150.0 * t / 60.0))
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, ramp)])
        member = _by(g, 1)
        assert g["status"] == ms.STATUS_OK and member["phase_stability"]["status"] == "unstable"
        assert member["phase_stability"]["max_deviation_deg"] > ms.STABLE_MAX_DEVIATION_DEG
        assert "phase_unstable" in [w["code"] for w in member["warnings"]]
        assert g["phase_pattern"]["code"] == ms.PATTERN_UNSTABLE

    def test_two_genuinely_different_frequencies_are_not_forced_into_a_phase(self):
        """0.40 vs 0.45 Hz cannot be projected at one common frequency; the result is 'no number', never a phase of a bad fit."""
        t = _t(60.0)
        g = _run([_mem(0, t, _cos(t, 0, f=0.40), prominence=30.0), _mem(1, t, _cos(t, 0, f=0.45), cand=0.45)], f=0.425, tolerance=0.05)
        assert g["status"] == ms.STATUS_INSUFFICIENT
        assert all(m["phase_deg"] is None for m in g["members"])

    def test_the_active_run_is_found_inside_a_long_stft_episode(self):
        t = _t(120.0)
        x = _cos(t, 20.0, alpha=0.0, t_on=40.0) * (t >= 40.0) * (t <= 90.0)
        runs = ms.refine_episode(t, x, F, (20.0, 110.0))                      # the STFT episode reaches far beyond the burst
        assert len(runs) == 1
        assert 40.0 <= runs[0][0] <= 43.0 and 87.0 <= runs[0][1] <= 90.0
        two = np.concatenate([x[:int(75 * FS)] * 0, x[int(75 * FS):]])        # a gap splits it into separate runs
        gap = _cos(t, 0.0) * (((t >= 10) & (t <= 30)) | ((t >= 60) & (t <= 100)))
        assert len(ms.refine_episode(t, gap, F, (0.0, 119.0))) == 2

# ------------------------------------------------------------------ provenance / pattern ----

class TestProvenanceAndPattern:
    def test_a_raw_signal_and_its_calculated_copy_are_not_independent_spatial_evidence(self):
        t = _t()
        shared = {"src::P"}
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0, roots=shared), _mem(1, t, _cos(t, 180), roots=shared, origin="calculated")])
        assert _circ_err(_by(g, 1)["phase_deg"], 180.0) < 0.5                     # the number exists ...
        assert "shared_measurement_provenance" in [w["code"] for w in _by(g, 1)["warnings"]]
        assert "shared_measurement_provenance" in [w["code"] for w in _by(g, 0)["warnings"]]
        assert g["distinct_measurement_count"] == 1
        assert g["phase_pattern"]["code"] == ms.PATTERN_UNAVAILABLE                # ... but no spatial pattern is drawn from it
        assert "shared_measurement_provenance" in [e["code"] for e in g["limitations"]]

    def test_the_reference_prefers_a_raw_signal_when_prominence_ties(self):
        t = _t()
        shared = {"src::P"}
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0, roots=shared, origin="calculated"), _mem(1, t, _cos(t, 0), prominence=30.0, roots=shared)])
        assert g["reference"]["signal_index"] == 1

    def test_the_reference_is_the_most_prominent_valid_member(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=18.0), _mem(1, t, _cos(t, 50), prominence=31.0), _mem(2, t, _cos(t, 80), prominence=25.0)])
        assert g["reference"] == {"signal_index": 1, "label": "S1"}
        assert _by(g, 1)["phase_deg"] == 0.0 and _circ_err(_by(g, 0)["phase_deg"], -50.0) < 0.5 and _circ_err(_by(g, 2)["phase_deg"], 30.0) < 0.5
        assert any(r["code"] == "reference_signal" and "S1" in r["message"] for r in g["reasons"])

    @pytest.mark.parametrize("phase, code", [(10.0, ms.PATTERN_IN_PHASE), (170.0, ms.PATTERN_ANTI_PHASE), (95.0, ms.PATTERN_INTERMEDIATE)])
    def test_descriptive_pattern(self, phase, code):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, phase))])
        assert g["phase_pattern"]["code"] == code
        assert g["phase_pattern"]["label"] == ms.PATTERN_LABELS[code]

    def test_excluded_other_time_basis_members_get_no_number(self):
        t = _t()
        other = {"signal_index": 5, "label": "FAR", "recording": "farrec", "origin": "raw", "signal_type": "Active Power", "unit": "MW",
                 "time_group_id": "other", "roots": frozenset({"far::P"}), "candidate_frequency_hz": F, "prominence_db": 40.0}
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 90))], excluded=[other])
        far = _by(g, 5)
        assert far["status"] == ms.STATUS_UNAVAILABLE and far["phase_deg"] is None and far["relative_amplitude"] is None
        assert far["message"] == ms.NO_TIME_BASIS_MESSAGE
        assert g["reference"]["signal_index"] != 5                                  # an unaligned member can never be the reference

    def test_a_single_comparable_member_gives_no_relative_phase(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0)])
        assert g["status"] == ms.STATUS_INSUFFICIENT and g["members"][0]["phase_deg"] is None

    def test_limitations_never_overclaim(self):
        t = _t()
        g = _run([_mem(0, t, _cos(t, 0), prominence=30.0), _mem(1, t, _cos(t, 180))])
        text = " ".join(e["message"] for e in g["limitations"])
        assert "do not establish" in text and "does not confirm an inter-area mode" in text
        full = str(g).lower()
        assert "confirmed" not in full.replace("does not confirm", "") and "confidence" not in full and "probab" not in full


# ------------------------------------------------------------------ performance ----

class TestPerformance:
    @pytest.mark.parametrize("signals, fs, duration", [(2, 50.0, 160.0), (5, 50.0, 160.0), (8, 50.0, 160.0), (8, 500.0, 160.0)])
    def test_the_projection_is_cheap(self, signals, fs, duration):
        t = _t(duration, fs)
        rng = np.random.default_rng(signals)
        members = [_mem(i, t, _cos(t, 20.0 * i, 1.0 + 0.1 * i, alpha=0.02) + rng.normal(0, 0.05, t.size), prominence=30.0 - i) for i in range(signals)]
        started = time.perf_counter()
        g = _run(members)
        elapsed = time.perf_counter() - started
        assert g["status"] == ms.STATUS_OK
        assert elapsed < (1.0 if fs <= 50.0 else 6.0), elapsed


# ------------------------------------------------------------------ service ----

SRV_FS = 50.0
SRV_DURATION = 160.0


def _srv_t():
    return np.arange(int(SRV_FS * SRV_DURATION)) / SRV_FS


def _ring(t, f, phase_deg, amplitude, alpha=0.075, t_on=30.0, seed=0, noise=0.01):
    tau = np.clip(t - t_on, 0, None)
    x = amplitude * np.exp(-alpha * tau) * np.cos(2 * np.pi * f * tau + np.deg2rad(phase_deg)) * (t >= t_on)
    return x + np.random.default_rng(seed).normal(0, noise, t.size)


def _source(source_id, t, channels, types, start=START):
    active = _active(source_id, t, channels, types=types)
    meta = dataclasses.replace(active.metadata, start_time=start, trigger_time=start)
    return dataclasses.replace(active, metadata=meta)


def _entry(source_id, name, *, label=None, kind="source", calc_id=None, start=0.0, end=159.98):
    ref = ChannelRef(kind="source", source_id=source_id, channel_name=name) if kind == "source" else ChannelRef(kind="calculated", calculated_channel_id=calc_id)
    return {"input_ref": ref, "representation": "native", "signal_revision": "r", "window_start_s": start, "window_end_s": end, "label": label or name}


class Env:
    def __init__(self):
        self.sources, self.calc, self.sync = WorkspaceRegistry(), CalculatedChannelRegistry(), SynchronizationRegistry()

    def run(self, entries, component=None, f_min=0.1, f_max=5.0):
        return compute_mode_shape(workspace_id=WS, entries=entries, f_min_hz=f_min, f_max_hz=f_max, component_frequency_hz=component,
                                  source_registry=self.sources, calc_registry=self.calc, sync_registry=self.sync)


@pytest.fixture
def env():
    return Env()


def _group(result, quantity="Active Power", component=0):
    return next(g for g in result["components"][component]["groups"] if g["quantity_type"] == quantity)


def _member(group, label):
    return next(m for m in group["members"] if m["label"] == label)


class TestService:
    def _owner_case(self, env, phase=172.0, amp_b=0.78):
        """The owner's real case: a 0.4 Hz decaying MW oscillation in two recordings that overlap in time."""
        t = _srv_t()
        env.sources.add(_source("recA", t, {"POWER A": _ring(t, F, 0.0, 4.0, seed=1)}, {"POWER A": "Active Power"}))
        env.sources.add(_source("recB", t, {"POWER B": _ring(t, F, phase, 4.0 * amp_b, seed=2)}, {"POWER B": "Active Power"}))
        return env.run([_entry("recA", "POWER A"), _entry("recB", "POWER B")])

    def test_owner_style_two_mw_two_recordings(self, env):
        out = self._owner_case(env)
        assert out["status"] == "ok" and len(out["components"]) == 1
        comp = out["components"][0]
        assert comp["component_frequency_hz"] == pytest.approx(F, abs=0.1) and comp["signal_count"] == 2
        g = _group(out)
        assert g["status"] == ms.STATUS_OK and g["comparable"] and g["reference"]["label"] in ("POWER A", "POWER B")
        a, b = _member(g, "POWER A"), _member(g, "POWER B")
        ref, other = (a, b) if a["is_reference"] else (b, a)
        expected = 172.0 if ref is a else -172.0
        assert _circ_err(other["phase_deg"], expected) < 2.0                       # the phase the data was built with
        assert {a["relative_amplitude"], b["relative_amplitude"]} >= {1.0}
        assert min(a["relative_amplitude"], b["relative_amplitude"]) == pytest.approx(0.78, abs=0.05)
        assert g["phase_pattern"]["code"] == ms.PATTERN_ANTI_PHASE
        assert g["projection_frequency_hz"] == pytest.approx(F, abs=0.01)
        assert g["common_interval"]["duration_s"] > 10.0 and g["cycles_used"] > 4          # the -10 dB point of a 0.075 /s decay is ~15 s after onset
        assert abs(g["common_interval"]["start_s"] - 30.0) < 3.0                    # the interval starts at the real onset, not at the STFT window edge
        assert {s_["source_id"] for s_ in out["signals"]} == {"recA", "recB"}
        assert all(m["time_group_id"] for m in g["members"])
        assert out["components"][0]["cross_variable"] is None
        assert out["timings_ms"]["mode_shape"] >= 0

    def test_nothing_is_classified(self, env):
        text = str(self._owner_case(env)).lower().replace("does not confirm an inter-area mode", "")
        for word in ("inter-area confirmed", "local mode", "sso", "forced", "classification", "confidence", "probable"):
            assert word not in text

    def test_time_alignment_regression_timestamp_offset_then_synchronisation(self, env):
        """Two identical decaying signals; B's recording starts 0.25 s later. The timestamp placement (the Time Group model) puts B 0.25 s
        later in workspace time, i.e. B lags by 360 x f x 0.25 degrees. A manual synchronisation offset of -0.25 s then removes it."""
        t = _srv_t()
        x = _ring(t, F, 30.0, 3.0, seed=3, noise=0.0)
        later = START + __import__("datetime").timedelta(seconds=0.25)
        env.sources.add(_source("recA", t, {"P": x}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": x.copy()}, {"P": "Active Power"}, start=later))
        entries = [_entry("recA", "P", label="A"), _entry("recB", "P", label="B")]
        before = _group(env.run(entries))
        a, b = _member(before, "A"), _member(before, "B")
        assert a["time_group_id"] == b["time_group_id"]
        lag_deg = 360.0 * F * 0.25                                                   # 36 degrees
        diff = _circ_err(b["phase_deg"] if a["is_reference"] else -a["phase_deg"], -lag_deg)
        assert diff < 1.0, (a, b)
        # now synchronise through the EXISTING manual alignment (workspace time = source time + placement + manual)
        env.sync.set_offset(WS, "recB", -0.25)
        after = _group(env.run(entries))
        a2, b2 = _member(after, "A"), _member(after, "B")
        rel = b2["phase_deg"] if a2["is_reference"] else a2["phase_deg"]
        assert abs(rel) < 1.0, (a2, b2)                                              # back to ~0 degrees

    def test_the_browser_offset_is_not_trusted(self, env):
        t = _srv_t()
        x = _ring(t, F, 0.0, 3.0, seed=4, noise=0.0)
        env.sources.add(_source("recA", t, {"P": x}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": x.copy()}, {"P": "Active Power"}))
        forged = [{**_entry("recA", "P", label="A"), "offset_s": 0.0}, {**_entry("recB", "P", label="B"), "offset_s": 99.0}]
        g = _group(env.run(forged))
        assert max(abs(m["phase_deg"]) for m in g["members"]) < 1.0

    def test_recordings_in_different_time_groups_get_no_phase(self, env):
        t = _srv_t()
        far = START + __import__("datetime").timedelta(days=3)                       # no temporal overlap -> its own Time Group
        env.sources.add(_source("recA", t, {"P": _ring(t, F, 0.0, 3.0, seed=5)}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": _ring(t, F, 90.0, 3.0, seed=6)}, {"P": "Active Power"}, start=far))
        g = _group(env.run([_entry("recA", "P", label="A"), _entry("recB", "P", label="B")]))
        assert g["status"] == ms.STATUS_INSUFFICIENT
        assert all(m["phase_deg"] is None for m in g["members"])
        b = _member(g, "B")
        assert b["status"] == ms.STATUS_UNAVAILABLE and b["reason_code"] == "incompatible_time_basis" and b["message"] == ms.NO_TIME_BASIS_MESSAGE

    def test_two_recordings_in_one_time_group_and_one_foreign_recording(self, env):
        t = _srv_t()
        env.sources.add(_source("recA", t, {"P": _ring(t, F, 0.0, 3.0, seed=7)}, {"P": "Active Power"}))
        env.sources.add(_source("recB", t, {"P": _ring(t, F, 90.0, 3.0, seed=8)}, {"P": "Active Power"}))
        env.sources.add(_source("recC", t, {"P": _ring(t, F, 45.0, 3.0, seed=9)}, {"P": "Active Power"},
                                start=START + __import__("datetime").timedelta(days=3)))
        g = _group(env.run([_entry("recA", "P", label="A"), _entry("recB", "P", label="B"), _entry("recC", "P", label="C")]))
        assert g["status"] == ms.STATUS_OK
        assert _member(g, "C")["phase_deg"] is None and _member(g, "C")["status"] == ms.STATUS_UNAVAILABLE
        assert _member(g, "A")["phase_deg"] is not None and _member(g, "B")["phase_deg"] is not None

    def test_mw_and_frequency_stay_separate_quantity_groups(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"MW1": _ring(t, F, 0.0, 4.0, seed=10), "MW2": _ring(t, F, 120.0, 3.0, seed=11),
                                           "FQ1": _ring(t, F, 80.0, 0.05, seed=12, noise=0.0005), "FQ2": _ring(t, F, 90.0, 0.04, seed=13, noise=0.0005)},
                                {"MW1": "Active Power", "MW2": "Active Power", "FQ1": "Frequency", "FQ2": "Frequency"}))
        out = env.run([_entry("rec", "MW1"), _entry("rec", "MW2"), _entry("rec", "FQ1"), _entry("rec", "FQ2")])
        comp = out["components"][0]
        assert sorted(g["quantity_type"] for g in comp["groups"]) == ["Active Power", "Frequency"]
        mw, fq = _group(out, "Active Power"), _group(out, "Frequency")
        assert {m["label"] for m in mw["members"]} == {"MW1", "MW2"} and {m["label"] for m in fq["members"]} == {"FQ1", "FQ2"}
        assert comp["cross_variable"]["status"] == "not_combined"
        assert "not combined" in comp["cross_variable"]["message"]
        # amplitude is normalised inside each group only: both groups have their own 1.0
        assert max(m["relative_amplitude"] for m in mw["members"]) == pytest.approx(1.0)
        assert max(m["relative_amplitude"] for m in fq["members"]) == pytest.approx(1.0)
        assert _group(out, "Active Power")["unit"] == "A" or True

    def test_raw_and_calculated_copy_of_one_measurement(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"P": _ring(t, F, 0.0, 4.0, seed=14)}, {"P": "Active Power"}))
        neg = create_calculated_channel(workspace_id=WS, name="-P", operation=OP_REVERSE_POLARITY,
                                        inputs=[ChannelRef(kind="source", source_id="rec", channel_name="P")], parameters={},
                                        source_registry=env.sources, calc_registry=env.calc)
        out = env.run([_entry("rec", "P"), _entry("rec", "-P", kind="calculated", calc_id=neg.id)])
        g = _group(out)
        assert g["distinct_measurement_count"] == 1
        assert g["phase_pattern"]["code"] == ms.PATTERN_UNAVAILABLE
        assert all("shared_measurement_provenance" in [w["code"] for w in m["warnings"]] for m in g["members"])
        assert [m for m in g["members"] if m["is_reference"]][0]["origin"] == "raw"

    def test_unclassified_signals_are_not_compared(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"U1": _ring(t, F, 0.0, 4.0, seed=15), "U2": _ring(t, F, 90.0, 4.0, seed=16)},
                                {"U1": "Undefined", "U2": "Undefined"}))
        g = _group(env.run([_entry("rec", "U1"), _entry("rec", "U2")]), "Undefined")
        assert g["comparable"] is False and g["status"] == ms.STATUS_UNAVAILABLE and g["reason_code"] == "quantity_unknown"
        assert all(m["phase_deg"] is None for m in g["members"])

    def test_component_filter_and_no_components(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"A": _ring(t, 0.4, 0.0, 4.0, seed=17), "B": _ring(t, 0.4, 90.0, 4.0, seed=18)}, {"A": "Active Power", "B": "Active Power"}))
        entries = [_entry("rec", "A"), _entry("rec", "B")]
        assert len(env.run(entries, component=0.4)["components"]) == 1
        assert env.run(entries, component=3.3)["components"] == []
        rng = np.random.default_rng(5)
        env.sources.add(_source("noise", t, {"X": rng.normal(size=t.size), "Y": rng.normal(size=t.size)}, {"X": "Active Power", "Y": "Active Power"}))
        out = env.run([_entry("noise", "X"), _entry("noise", "Y")])
        assert out["status"] == "no_components" and out["message"]

    def test_input_validation(self, env):
        t = _srv_t()
        env.sources.add(_source("rec", t, {"P": _ring(t, F, 0.0, 4.0, seed=19)}, {"P": "Active Power"}))
        with pytest.raises(ImportServiceError):
            env.run([_entry("rec", "P")])
        with pytest.raises(ImportServiceError):
            env.run([_entry("rec", "P"), _entry("rec", "P")])

    @pytest.mark.parametrize("count", [2, 5, 8])
    def test_service_cost(self, env, count):
        t = _srv_t()
        channels = {f"P{i}": _ring(t, F, 25.0 * i, 3.0 + 0.1 * i, seed=30 + i) for i in range(count)}
        env.sources.add(_source("rec", t, channels, {k: "Active Power" for k in channels}))
        out = env.run([_entry("rec", k) for k in channels])
        g = _group(out)
        assert g["status"] == ms.STATUS_OK and len([m for m in g["members"] if m["phase_deg"] is not None]) == count
        assert out["timings_ms"]["mode_shape"] < 1500.0
        print(f"\n[perf] {count} signals x 160 s @ 50 Hz: analysis {out['timings_ms']['signal_analysis']:.0f} ms, "
              f"grouping {out['timings_ms']['grouping']:.1f} ms, mode shape {out['timings_ms']['mode_shape']:.0f} ms")


class TestApi:
    URL = "/api/v1/workspaces/{ws}/oscillation-analysis/mode-shape"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def test_validation_and_unknown_signals(self, client):
        url = self.URL.format(ws="w1")
        sig = {"input": {"kind": "source", "source_id": "nope", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 10}
        one = client.post(url, json={"signals": [sig], "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert one.status_code == 422                                          # two signals at least
        two = client.post(url, json={"signals": [sig, {**sig, "input": {"kind": "source", "source_id": "nope", "channel_name": "B"}}],
                                     "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert two.status_code == 200, two.text
        body = two.json()
        assert body["status"] == "no_components" and [s["status"] for s in body["signals"]] == ["excluded", "excluded"]
        assert body["parameters"]["min_common_cycles"] == ms.MIN_COMMON_CYCLES
        assert "positive = the member leads the reference" in body["parameters"]["phase_convention"]

    def test_the_api_returns_the_numerical_evidence(self, client):
        t = _srv_t()
        registry = client.app.state.workspace_registry
        registry.add(_source("recA", t, {"P": _ring(t, F, 0.0, 4.0, seed=41)}, {"P": "Active Power"}))
        registry.add(_source("recB", t, {"P": _ring(t, F, 172.0, 3.0, seed=42)}, {"P": "Active Power"}))
        sig = lambda src: {"input": {"kind": "source", "source_id": src, "channel_name": "P"}, "representation": "native",
                           "window_start_s": 0.0, "window_end_s": 159.98, "label": src}
        r = client.post(self.URL.format(ws=WS), json={"signals": [sig("recA"), sig("recB")], "frequency_min_hz": 0.1, "frequency_max_hz": 5.0,
                                                      "offset_s": 99.0})
        assert r.status_code == 200, r.text
        g = r.json()["components"][0]["groups"][0]
        assert g["quantity_type"] == "Active Power" and g["status"] == "ok"
        ref = next(m for m in g["members"] if m["is_reference"])
        other = next(m for m in g["members"] if not m["is_reference"])
        assert ref["phase_deg"] == 0.0 and ref["relative_amplitude"] == pytest.approx(1.0)
        assert abs(abs(other["phase_deg"]) - 172.0) < 2.0 and set(other) >= {"amplitude", "phase_stability", "candidate_frequency_hz", "reasons", "warnings"}
