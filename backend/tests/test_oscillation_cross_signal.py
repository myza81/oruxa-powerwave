"""Oscillation Analysis -- cross-signal evidence (DEC-178 [APPROVED]).

Domain tests use hand-built candidates (so tolerances and boundaries are exact); service / API tests
run the real Welch + DEC-175 + STFT + DEC-177 chain on synthetic signals with known content.
Nothing here classifies an oscillation.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain import cross_signal_evidence as cs
from app.domain.calculated_channel import OP_REVERSE_POLARITY, ChannelRef
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import ImportServiceError
from app.services.oscillation_cross_signal_service import MAX_SIGNALS, compute_cross_signal
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_oscillation_damping import ring
from tests.test_oscillation_representation import WS, _active


# ------------------------------------------------------------------ domain ----

def _cand(freq, prominence=20.0, rank=1, cycles=50.0):
    return {"rank": rank, "frequency_hz": freq, "prominence_db": prominence, "cycles_observed": cycles, "psd": 1.0}


def _sig(index, label, candidates, *, bin_hz=0.05, recording="r1", signal_type="Frequency", roots=None, offset=0.0,
         damping=None, temporal=None, origin="raw"):
    return {"index": index, "label": label, "signal_type": signal_type, "recording": recording, "origin": origin,
            "lineage_roots": roots if roots is not None else [f"{recording}::{label}"], "offset_s": offset,
            "bin_spacing_hz": bin_hz, "candidates": candidates, "damping": damping or {}, "temporal": temporal or {}}


def _dmp(behaviour="decaying", alpha=0.2, zeta=0.03, status="available"):
    return {"status": status, "behaviour": behaviour, "decay_rate_per_s": alpha, "damping_ratio": zeta, "reason_code": None, "message": ""}


class TestMatchingRule:
    def test_tolerance_is_the_coarser_bin_spacing_not_a_fixed_number(self):
        assert cs.match_tolerance_hz(0.05, 0.2) == pytest.approx(0.2)
        assert cs.match_tolerance_hz(0.5, 0.5) == pytest.approx(0.5)      # a coarse grid tolerates more than a fixed +-0.1 Hz

    def test_just_inside_and_just_outside_the_boundary(self):
        assert cs.frequencies_match(4.95, 0.1, 5.05, 0.1)                 # exactly one bin apart: inside
        assert cs.frequencies_match(4.95, 0.1, 4.95 + 0.1 * 1.000000001, 0.1)
        assert not cs.frequencies_match(4.95, 0.1, 5.0501, 0.1)           # a hair beyond: outside
        assert cs.frequencies_match(4.95, 0.05, 5.15, 0.2)                # the coarser grid of the pair sets the tolerance
        assert not cs.frequencies_match(4.95, 0.05, 5.2, 0.05)

    def test_grouping_uses_the_boundary(self):
        inside = cs.group_components([_sig(0, "F", [_cand(4.95)], bin_hz=0.1), _sig(1, "P", [_cand(5.05)], bin_hz=0.1, signal_type="Active Power")])
        outside = cs.group_components([_sig(0, "F", [_cand(4.95)], bin_hz=0.1), _sig(1, "P", [_cand(5.06)], bin_hz=0.1, signal_type="Active Power")])
        assert [c["signal_count"] for c in inside] == [2]
        assert sorted(c["signal_count"] for c in outside) == [1, 1]


class TestGrouping:
    def test_same_mode_in_two_signal_types(self):
        groups = cs.group_components([
            _sig(0, "FREQ", [_cand(4.95, 25.0)], signal_type="Frequency"),
            _sig(1, "MW", [_cand(4.95, 20.0), _cand(1.15, 15.0, rank=2)], signal_type="Active Power"),
        ])
        by = {round(g["representative_frequency_hz"], 2): g for g in groups}
        both, low = by[4.95], by[1.15]
        assert both["signal_count"] == 2 and both["signal_types"] == ["Active Power", "Frequency"]
        assert {r["code"] for r in both["reasons"]} >= {"observed_in", "frequency_match", "multiple_signal_types"}
        assert "Observed in 2 signals across 1 recording." in [r["message"] for r in both["reasons"]]
        # 1.15 Hz has no match elsewhere: its own group, explained, never called false
        assert low["signal_count"] == 1 and low["reasons"][0]["code"] == "single_signal_only"
        assert "one signal only" in low["reasons"][0]["message"] and "false" in low["reasons"][0]["message"]

    def test_same_mode_across_two_recordings(self):
        g = cs.group_components([_sig(0, "F", [_cand(2.0)], recording="rA"), _sig(1, "F", [_cand(2.0)], recording="rB")])[0]
        assert g["recording_count"] == 2 and {r["code"] for r in g["reasons"]} >= {"multiple_recordings"}
        assert g["distinct_measurement_count"] == 2

    def test_two_separate_modes_stay_separate(self):
        groups = cs.group_components([_sig(0, "A", [_cand(1.15, 20, 1), _cand(4.95, 18, 2)]),
                                      _sig(1, "B", [_cand(1.15, 22, 1), _cand(4.95, 19, 2)], recording="r2")])
        assert sorted(round(g["representative_frequency_hz"], 2) for g in groups) == [1.15, 4.95]
        assert all(g["signal_count"] == 2 for g in groups)

    def test_a_signal_contributes_one_candidate_per_group_and_the_nearest_one(self):
        groups = cs.group_components([_sig(0, "A", [_cand(5.0)]), _sig(1, "B", [_cand(4.95, 30, 1), _cand(5.05, 20, 2)], bin_hz=0.1)])
        big = max(groups, key=lambda g: g["signal_count"])
        assert big["signal_count"] == 2 and len(groups) == 2
        assert sorted(m["frequency_hz"] for g in groups for m in g["members"]) == [4.95, 5.0, 5.05]

    def test_result_does_not_depend_on_the_input_order(self):
        a = _sig(0, "F", [_cand(4.95, 25.0)])
        b = _sig(1, "P", [_cand(5.0, 20.0)], recording="r2", bin_hz=0.1)
        one = cs.group_components([a, b])
        two = cs.group_components([b, a])
        assert [(g["representative_frequency_hz"], g["signal_count"]) for g in one] == [(g["representative_frequency_hz"], g["signal_count"]) for g in two]

    def test_representative_frequency_is_the_prominence_weighted_mean_and_originals_are_kept(self):
        g = cs.group_components([_sig(0, "F", [_cand(4.90, 30.0)], bin_hz=0.1), _sig(1, "P", [_cand(5.0, 10.0)], bin_hz=0.1, recording="r2")])[0]
        assert g["representative_frequency_hz"] == pytest.approx((4.90 * 30 + 5.0 * 10) / 40)
        assert [m["frequency_hz"] for m in g["members"]] == [4.90, 5.0]
        assert g["frequency_spread_hz"] == pytest.approx(0.1) and g["match_tolerance_hz"] == pytest.approx(0.1)

    def test_signal_types_and_origin_are_preserved_per_member(self):
        g = cs.group_components([_sig(0, "F", [_cand(3.0)], signal_type="Frequency"), _sig(1, "Q", [_cand(3.0)], signal_type="Reactive Power", recording="r2")])[0]
        assert g["signal_types"] == ["Frequency", "Reactive Power"]
        assert {m["label"] for m in g["members"]} == {"F", "Q"}


class TestIndependence:
    def test_raw_plus_derived_copy_is_not_two_measurements(self):
        raw = _sig(0, "P", [_cand(3.0)], signal_type="Active Power", roots=["r1::P"])
        derived = _sig(1, "-P", [_cand(3.0)], signal_type="Active Power", roots=["r1::P"], origin="calculated")
        g = cs.group_components([raw, derived])[0]
        assert g["signal_count"] == 2 and g["distinct_measurement_count"] == 1
        assert any(w["code"] == "derived_from_same_source" for w in g["warnings"])
        text = " ".join(r["message"] for r in g["reasons"]).lower()
        assert "independent" not in text and "confirm" not in text
        assert "1 distinct measurement" in text

    def test_three_signals_two_measurements(self):
        g = cs.group_components([_sig(0, "P", [_cand(3.0)], roots=["r::P"]), _sig(1, "-P", [_cand(3.0)], roots=["r::P"]),
                                 _sig(2, "F", [_cand(3.0)], roots=["r::F"], signal_type="Frequency")])[0]
        assert g["signal_count"] == 3 and g["distinct_measurement_count"] == 2


class TestDampingConsistency:
    def _pair(self, a, b):
        return cs.group_components([_sig(0, "F", [_cand(3.0)], damping={1: a}), _sig(1, "P", [_cand(3.0)], damping={1: b}, recording="r2")])[0]

    def test_agreement(self):
        g = self._pair(_dmp(alpha=0.20), _dmp(alpha=0.25))
        assert "damping_consistent" in [r["code"] for r in g["reasons"]] and not [w for w in g["warnings"] if w["code"].startswith("damp")]

    def test_behaviour_disagreement_warns_but_still_groups(self):
        g = self._pair(_dmp(), _dmp(behaviour="approximately_sustained", alpha=0.0, zeta=None))
        assert g["signal_count"] == 2 and "damping_behaviour_differs" in [w["code"] for w in g["warnings"]]
        assert "damping_consistent" not in [r["code"] for r in g["reasons"]]

    def test_material_rate_difference_warns(self):
        g = self._pair(_dmp(alpha=0.1), _dmp(alpha=0.5))
        assert g["signal_count"] == 2 and "decay_rates_differ_materially" in [w["code"] for w in g["warnings"]]
        assert g["evidence"]["damping"]["decay_rate_ratio"] == pytest.approx(5.0)

    def test_rate_ratio_boundary(self):
        assert "decay_rates_differ_materially" not in [w["code"] for w in self._pair(_dmp(alpha=0.1), _dmp(alpha=0.2))["warnings"]]
        assert "decay_rates_differ_materially" in [w["code"] for w in self._pair(_dmp(alpha=0.1), _dmp(alpha=0.2001))["warnings"]]

    def test_missing_damping_in_one_signal_is_not_compared(self):
        g = self._pair(_dmp(), _dmp(status="insufficient_evidence", behaviour=None, alpha=None, zeta=None))
        assert "damping_not_compared" in [r["code"] for r in g["reasons"]] and g["signal_count"] == 2
        assert g["evidence"]["damping"]["available"] == 1

    def test_no_damping_at_all_is_fine(self):
        assert cs.group_components([_sig(0, "F", [_cand(3.0)]), _sig(1, "P", [_cand(3.0)], recording="r2")])[0]["signal_count"] == 2


def _matrix(times, freqs, f, active_from, active_to):
    psd = np.full((len(freqs), len(times)), 1e-9)
    row = int(np.argmin(np.abs(freqs - f)))
    for j, t in enumerate(times):
        if active_from <= t <= active_to:
            psd[row, j] = 1.0
    return psd


class TestTemporalEvidence:
    def test_active_interval_from_the_stft_track(self):
        times = np.arange(5.0, 100.0, 10.0)
        freqs = np.arange(0.0, 10.0, 0.25)
        t = cs.active_interval(times, freqs, _matrix(times, freqs, 5.0, 40.0, 70.0), 5.0, 10.0)
        assert t["status"] == "ok" and t["start_s"] == pytest.approx(40.0) and t["end_s"] == pytest.approx(70.0)
        assert t["active_slices"] == 3 and t["slice_count"] == 10
        assert cs.active_interval(times, freqs, np.zeros((len(freqs), len(times))), 5.0, 10.0)["status"] == "unavailable"

    def _two(self, win_a, win_b, off_b=0.0):
        ta = np.arange(2.0, 100.0, 4.0)       # fine STFT (4 s hop)
        tb = np.arange(10.0, 100.0, 20.0)     # coarse STFT (20 s hop)
        fa, fb = np.arange(0.0, 10.0, 0.1), np.arange(0.0, 10.0, 0.5)
        a = cs.active_interval(ta, fa, _matrix(ta, fa, 5.0, *win_a), 5.0, 4.0)
        b = cs.active_interval(tb, fb, _matrix(tb, fb, 5.0, *win_b), 5.0, 20.0)
        return cs.group_components([_sig(0, "F", [_cand(5.0)], temporal={1: a}),
                                    _sig(1, "P", [_cand(5.0)], bin_hz=0.5, recording="r2", offset=off_b, temporal={1: b})])[0]

    def test_overlap_with_different_stft_resolutions(self):
        g = self._two((30.0, 60.0), (30.0, 70.0))
        assert "temporal_overlap" in [r["code"] for r in g["reasons"]]
        assert g["evidence"]["temporal"]["overlap_s"] > 20

    def test_no_overlap(self):
        g = self._two((0.0, 20.0), (70.0, 95.0))
        assert "no_temporal_overlap" in [w["code"] for w in g["warnings"]] and g["signal_count"] == 2

    def test_alignment_offset_is_applied_before_comparing(self):
        assert "no_temporal_overlap" in [w["code"] for w in self._two((0.0, 20.0), (0.0, 25.0), off_b=60.0)["warnings"]]
        assert "temporal_overlap" in [r["code"] for r in self._two((0.0, 20.0), (60.0, 85.0), off_b=-60.0)["reasons"]]

    def test_missing_temporal_evidence_is_limited_not_fatal(self):
        g = cs.group_components([_sig(0, "F", [_cand(5.0)], temporal={1: {"status": "ok", "start_s": 0.0, "end_s": 50.0}}),
                                 _sig(1, "P", [_cand(5.0)], recording="r2")])[0]
        assert g["signal_count"] == 2 and "limited_temporal_evidence" in [w["code"] for w in g["warnings"]]


# ------------------------------------------------------------- service ----

FS = 50.0


def _t(duration=160.0):
    return np.arange(int(FS * duration)) / FS


def _event(seed, modes, noise=0.01, step=40.0):
    t = _t()
    x = step * np.where(t > 30.0, 1 - np.exp(-(t - 30.0) / 15.0), 0.0) + np.random.default_rng(seed).normal(0, noise, t.size)
    for f, z, a in modes:
        x = x + ring(t, f, z, amplitude=a, t_on=30.0)[0]
    return t, x


@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _entry(source_id, name, *, offset=0.0, label=None, start=0.0, end=159.98, representation="native", kind="source", calc_id=None):
    ref = ChannelRef(kind="source", source_id=source_id, channel_name=name) if kind == "source" else ChannelRef(kind="calculated", calculated_channel_id=calc_id)
    return {"input_ref": ref, "representation": representation, "signal_revision": "r", "window_start_s": start, "window_end_s": end,
            "offset_s": offset, "label": label or name}


def _run(registries, entries, f_min=0.1, f_max=10.0):
    return compute_cross_signal(workspace_id=WS, entries=entries, f_min_hz=f_min, f_max_hz=f_max,
                                source_registry=registries[0], calc_registry=registries[1])


class TestService:
    def _owner_case(self, registries):
        """The owner's real event: 4.95 Hz in frequency and MW, 1.15 Hz in MW only."""
        t, freq = _event(1, [(4.95, 0.01, 0.4)], step=0.5)
        _, mw = _event(2, [(4.95, 0.01, 0.4), (1.15, 0.02, 1.0)])
        registries[0].add(_active("src", t, {"FREQ": freq, "MW": mw}, types={"FREQ": "Frequency", "MW": "Active Power"}))
        return _run(registries, [_entry("src", "FREQ"), _entry("src", "MW")])

    def test_owner_real_event_case(self, registries):
        out = self._owner_case(registries)
        assert out["status"] == "ok" and [s["status"] for s in out["signals"]] == ["ok", "ok"]
        by = {round(c["representative_frequency_hz"]): c for c in out["components"]}
        five, one = by[5], by[1]
        assert five["signal_count"] == 2 and five["signal_types"] == ["Active Power", "Frequency"]
        assert one["signal_count"] == 1 and one["members"][0]["label"] == "MW"
        codes = [r["code"] for r in five["reasons"]]
        assert {"observed_in", "frequency_match", "multiple_signal_types", "temporal_overlap"} <= set(codes)
        assert all(m["damping"] is not None for m in five["members"])           # available per signal, shown independently
        assert all(m["temporal"]["status"] == "ok" for m in five["members"])
        assert one["reasons"][0]["code"] == "single_signal_only"

    def test_same_mode_across_two_recordings(self, registries):
        t, a = _event(3, [(2.6, 0.02, 0.8)])
        _, b = _event(4, [(2.6, 0.02, 0.8)])
        registries[0].add(_active("rA", t, {"P": a}, types={"P": "Active Power"}))
        registries[0].add(_active("rB", t, {"P": b}, types={"P": "Active Power"}))
        out = _run(registries, [_entry("rA", "P", label="P (A)"), _entry("rB", "P", label="P (B)")])
        comp = out["components"][0]
        assert comp["signal_count"] == 2 and comp["recording_count"] == 2 and comp["distinct_measurement_count"] == 2

    def test_raw_plus_calculated_copy_is_disclosed_as_one_measurement(self, registries):
        t, p = _event(5, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p}, types={"P": "Active Power"}))
        neg = create_calculated_channel(workspace_id=WS, name="-P", operation=OP_REVERSE_POLARITY,
                                        inputs=[ChannelRef(kind="source", source_id="src", channel_name="P")], parameters={},
                                        source_registry=registries[0], calc_registry=registries[1])
        out = _run(registries, [_entry("src", "P"), _entry("src", "-P", kind="calculated", calc_id=neg.id)])
        comp = out["components"][0]
        assert comp["signal_count"] == 2 and comp["distinct_measurement_count"] == 1
        assert out["signals"][1]["origin"] == "calculated" and out["signals"][1]["signal_type"] == out["signals"][0]["signal_type"]
        assert any(w["code"] == "derived_from_same_source" for w in comp["warnings"])

    def test_a_calculated_channel_created_after_the_first_comparison_joins_the_next(self, registries):
        t, p = _event(6, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p, "Q": p * 0.5}, types={"P": "Active Power", "Q": "Reactive Power"}))
        first = _run(registries, [_entry("src", "P"), _entry("src", "Q")])
        assert first["components"][0]["signal_count"] == 2
        neg = create_calculated_channel(workspace_id=WS, name="-P", operation=OP_REVERSE_POLARITY,
                                        inputs=[ChannelRef(kind="source", source_id="src", channel_name="P")], parameters={},
                                        source_registry=registries[0], calc_registry=registries[1])
        second = _run(registries, [_entry("src", "P"), _entry("src", "Q"), _entry("src", "-P", kind="calculated", calc_id=neg.id)])
        assert second["components"][0]["signal_count"] == 3 and second["components"][0]["distinct_measurement_count"] == 2

    def test_an_unanalysable_signal_is_excluded_and_the_rest_still_compare(self, registries):
        t, p = _event(7, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p, "Q": p}, types={"P": "Active Power", "Q": "Active Power"}))
        out = _run(registries, [_entry("src", "P"), _entry("src", "Q", start=-500.0, end=100.0)])
        assert out["signals"][1]["status"] == "excluded" and out["signals"][1]["reason_code"] == "invalid_analysis_window"
        assert out["components"] and out["components"][0]["signal_count"] == 1

    def test_no_candidates_anywhere_is_an_explained_success(self, registries):
        t = _t()
        rng = np.random.default_rng(9)
        registries[0].add(_active("src", t, {"A": rng.normal(size=t.size), "B": rng.normal(size=t.size)}))
        out = _run(registries, [_entry("src", "A"), _entry("src", "B")])
        assert out["status"] == "no_components" and out["components"] == [] and out["message"]

    def test_input_validation(self, registries):
        t, p = _event(8, [(3.2, 0.02, 0.8)])
        registries[0].add(_active("src", t, {"P": p}))
        with pytest.raises(ImportServiceError):
            _run(registries, [_entry("src", "P"), _entry("src", "P")])
        with pytest.raises(ImportServiceError):
            _run(registries, [_entry("src", "P")] + [_entry("src", f"X{i}") for i in range(MAX_SIGNALS)])

    def test_nothing_is_classified(self, registries):
        out = self._owner_case(registries)
        text = str(out).lower()
        for word in ("inter-area", "local mode", "sso", "forced", "classification", "confirmed", "confidence"):
            assert word not in text.replace("no oscillation type is inferred", "")

    @pytest.mark.parametrize("count", [2, 5, 20])
    def test_grouping_is_cheap(self, count):
        """Grouping alone (domain) over 2 / 5 / 20 candidate-bearing signals; the per-signal analysis is the existing cost."""
        rng = np.random.default_rng(count)
        signals = [_sig(i, f"S{i}", [_cand(1.15 + rng.normal(0, 0.01), 20, 1), _cand(4.95 + rng.normal(0, 0.01), 18, 2),
                                    _cand(2.6, 15, 3)], recording=f"r{i % 4}") for i in range(count)]
        started = time.perf_counter()
        groups = cs.group_components(signals)
        assert time.perf_counter() - started < 0.2
        assert sum(g["signal_count"] for g in groups) == 3 * count


class TestApi:
    BASE = "/api/v1/workspaces/{ws}/oscillation-analysis/cross-signal"

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def test_validation_errors_and_shape(self, client):
        base = self.BASE.format(ws="w1")
        r = client.post(base, json={"signals": [{"input": {"kind": "source", "source_id": "x", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 1}],
                                    "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert r.status_code == 422                                        # at least two signals
        sig = {"input": {"kind": "source", "source_id": "nope", "channel_name": "A"}, "window_start_s": 0, "window_end_s": 10}
        r = client.post(base, json={"signals": [sig, {**sig, "input": {"kind": "source", "source_id": "nope", "channel_name": "B"}}],
                                    "frequency_min_hz": 0.1, "frequency_max_hz": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "no_components" and [s["status"] for s in body["signals"]] == ["excluded", "excluded"]
        assert body["parameters"]["match_resolution_factor"] == 1.0
