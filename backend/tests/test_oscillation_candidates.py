"""Oscillation Analysis -- deterministic candidate detection over the Welch PSD
(DEC-175 [PROPOSAL]). Domain tests use hand-built PSD arrays (exact control of
plateaus, thresholds and edges); service tests push synthetic signals through
the unchanged Welch pipeline. SciPy is a dev-only independent reference for
peak finding and prominence; production uses NumPy."""

from __future__ import annotations

import re
import time as _time_module
from pathlib import Path

import numpy as np
import pytest
from scipy import signal as sp_signal

from app.domain.oscillation_peaks import (
    ASSESSMENT_CANDIDATE,
    ASSESSMENT_INSUFFICIENT,
    BOUNDARY_GUARD_BINS,
    MAX_REPORTED_CANDIDATES,
    MIN_AVERAGED_SEGMENTS,
    MIN_OBSERVED_CYCLES,
    MIN_PROMINENCE_DB,
    NOISE_ALLOWANCE_SIGMAS,
    STATUS_FOUND,
    STATUS_NONE,
    detect_candidates,
    find_peaks,
    low_frequency_cutoff_hz,
    noise_allowance_db,
)
from app.domain.spectral_estimation import choose_segmentation, welch_psd
from tests.test_oscillation_representation import _active, _sine, _time
from tests.test_oscillation_spectrum import _add, _spectrum, registries  # noqa: F401


def _grid(n, df=0.05, start=0.05):
    return start + df * np.arange(n)


def _db(ratio):
    return 10.0 * np.log10(ratio)


def _codes(items):
    return [i["code"] for i in items]


# ------------------------------------------------------------ peak finding ----

class TestPeakFindingAgainstScipy:
    def test_interior_peaks_and_prominence_match_scipy(self):
        rng = np.random.default_rng(7)
        for _ in range(40):
            psd = np.exp(rng.normal(0, 1.5, 300))  # distinct values, many peaks
            f = _grid(psd.size)
            mine = [p for p in find_peaks(f, psd) if p.band_edge is None]
            idx, _ = sp_signal.find_peaks(_db(psd))
            ref_prom = sp_signal.peak_prominences(_db(psd), idx)[0]
            assert [p.first_index for p in mine] == idx.tolist()
            np.testing.assert_allclose([p.prominence_db for p in mine], ref_prom, rtol=1e-9, atol=1e-9)

    def test_prominence_uses_the_higher_base_not_the_distant_floor(self):
        # a ripple on the shoulder of a big peak: its depth is the dip next to it, not the far floor
        psd = np.array([1.0, 2.0, 100.0, 40.0, 50.0, 30.0, 1.0, 0.5])
        peaks = {p.first_index: p for p in find_peaks(_grid(psd.size), psd)}
        assert peaks[4].prominence_db == pytest.approx(_db(50.0 / 40.0))
        # the big peak is only as prominent as the higher of its two bases (left 1.0, right 0.5)
        assert peaks[2].prominence_db == pytest.approx(_db(100.0 / 1.0))

    def test_linear_time_on_a_wide_spectrum(self):
        rng = np.random.default_rng(1)
        psd = np.exp(rng.normal(0, 1.0, 200_000))
        start = _time_module.perf_counter()
        find_peaks(_grid(psd.size), psd)
        assert _time_module.perf_counter() - start < 5.0  # O(N); a quadratic scan would take minutes


class TestPlateausAndAdjacentBins:
    def test_tied_bins_are_one_peak_at_their_centre(self):
        psd = np.array([1.0, 2.0, 9.0, 9.0, 2.0, 1.0, 0.8, 0.5])
        f = _grid(psd.size)
        peaks = [p for p in find_peaks(f, psd) if p.band_edge is None]
        assert len(peaks) == 1
        assert (peaks[0].first_index, peaks[0].last_index) == (2, 3)
        assert peaks[0].frequency_hz == pytest.approx(0.5 * (f[2] + f[3]))

    def test_one_smooth_lobe_is_one_candidate(self):
        f = _grid(80)
        psd = 1e-6 + np.exp(-0.5 * ((f - 2.0) / 0.12) ** 2)
        det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20)
        assert [c["rank"] for c in det.candidates] == [1]
        assert det.candidates[0]["frequency_hz"] == pytest.approx(2.0, abs=0.05)

    def test_flat_spectrum_has_no_peak(self):
        assert find_peaks(_grid(50), np.ones(50)) == []

    def test_zero_psd_is_handled(self):
        assert find_peaks(_grid(10), np.zeros(10)) == []


# ------------------------------------------------------- acceptance rules ----

def _spectrum_with_peak(height_ratio, *, index=20, n=40, df=0.05):
    psd = np.ones(n)
    psd[index] = height_ratio
    return _grid(n, df, df), psd


class TestAcceptanceThresholds:
    def test_prominence_threshold_boundary(self):
        base = 10 ** (MIN_PROMINENCE_DB / 10)  # exactly the threshold
        f, below = _spectrum_with_peak(base * 0.99)
        _, above = _spectrum_with_peak(base * 1.01)
        assert detect_candidates(f, below, window_duration_s=100.0).status == STATUS_NONE
        det = detect_candidates(f, above, window_duration_s=100.0)
        assert det.status == STATUS_FOUND
        assert det.candidates[0]["prominence_db"] == pytest.approx(MIN_PROMINENCE_DB, abs=0.1)

    def test_few_segments_raise_the_required_prominence(self):
        ratio = 10 ** (12.0 / 10)  # 12 dB: passes the floor, not a 3-segment noise allowance
        f, psd = _spectrum_with_peak(ratio)
        assert noise_allowance_db(3) == pytest.approx(NOISE_ALLOWANCE_SIGMAS * 4.343 / np.sqrt(3), rel=1e-3)
        many = detect_candidates(f, psd, window_duration_s=100.0, segment_count=40)
        few = detect_candidates(f, psd, window_duration_s=100.0, segment_count=3)
        assert many.status == STATUS_FOUND and few.status == STATUS_NONE
        assert few.parameters["required_prominence_db"] > 12.0
        assert any(r["code"] == "no_prominent_peak" for r in few.no_candidate_reasons)

    def test_two_cycle_boundary_uses_one_rule(self):
        f = _grid(40, 0.05, 0.05)
        psd = np.ones(40)
        psd[1] = 100.0  # 0.10 Hz: exactly 2 cycles in a 20 s window
        at = detect_candidates(f, psd, window_duration_s=20.0)
        assert low_frequency_cutoff_hz(20.0) == pytest.approx(0.10)
        assert at.candidates and at.candidates[0]["cycles_observed"] == pytest.approx(2.0)
        short = detect_candidates(f, psd, window_duration_s=19.9)  # 1.99 cycles
        assert short.status == STATUS_NONE
        np_ = short.not_promoted[0]
        assert np_["reason_code"] == "below_min_cycles" and np_["assessment"] == ASSESSMENT_INSUFFICIENT
        assert np_["cycles_observed"] < MIN_OBSERVED_CYCLES

    def test_band_edge_peak_is_not_promoted_and_says_why(self):
        for index in (0, 39):
            f, psd = _spectrum_with_peak(1000.0, index=index)
            det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20)
            assert det.status == STATUS_NONE
            assert [e["reason_code"] for e in det.not_promoted] == ["band_edge"]
            assert any(r["code"] == "peak_at_band_edge" for r in det.no_candidate_reasons)

    def test_peak_near_the_edge_is_kept_with_a_warning(self):
        f, psd = _spectrum_with_peak(1000.0, index=BOUNDARY_GUARD_BINS)
        det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20)
        assert det.status == STATUS_FOUND
        assert "near_band_edge" in _codes(det.candidates[0]["warnings"])
        f, psd = _spectrum_with_peak(1000.0, index=BOUNDARY_GUARD_BINS + 1)
        clear = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20).candidates[0]
        assert "near_band_edge" not in _codes(clear["warnings"])
        assert "away_from_band_edge" in _codes(clear["reasons"])

    def test_dc_bin_is_not_spectral_evidence(self):
        f = np.concatenate(([0.0], _grid(39)))
        psd = np.concatenate(([0.0], np.linspace(10.0, 1.0, 39)))  # decays from the first non-zero bin
        det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20)
        assert det.status == STATUS_NONE and det.parameters["dc_bin_excluded"] is True
        assert [e["reason_code"] for e in det.not_promoted] == ["band_edge"]


class TestNumericalFloor:
    def test_round_off_ripple_far_below_the_strongest_bin_is_not_a_peak(self):
        # Observed on a bin-aligned sinusoid in 16-bit data: the leakage floor is numerically zero
        # (1e-37 .. 1e-16) and ripples by tens of dB. That is round-off, not spectrum.
        f = _grid(7, 0.25, 0.5)
        psd = np.array([3.3e-3, 8.3e-4, 6.9e-37, 1.35e-16, 5.4e-16, 1.35e-16, 1.5e-37])
        det = detect_candidates(f, psd, window_duration_s=20.0, segment_count=9)
        assert det.status == STATUS_NONE and not det.candidates
        assert [e["reason_code"] for e in det.not_promoted] == ["band_edge"]
        assert det.not_promoted[0]["prominence_db"] <= 100.0 + 1e-9  # capped by the documented floor

    def test_a_real_component_within_the_dynamic_range_is_kept(self):
        psd = np.full(60, 1e-8)
        psd[30] = 1e-4  # 40 dB over the floor, 40 dB below the strongest bin
        psd[5] = 1.0
        det = detect_candidates(_grid(60), psd, window_duration_s=100.0, segment_count=40)
        assert sorted(round(c["prominence_db"]) for c in det.candidates) == [40, 80]


class TestRankingAndStructure:
    def test_ranked_by_prominence_not_by_absolute_psd(self):
        psd = np.ones(60)
        psd[0:30] = 500.0
        psd[15] = 5000.0  # PSD 5000 but only 10 dB over its 500 surroundings
        psd[45] = 60.0    # PSD 60, 17.8 dB over a floor of 1
        f = _grid(60)
        det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=40)
        assert [c["psd"] for c in det.candidates] == [60.0, 5000.0]
        assert det.candidates[0]["prominence_db"] > det.candidates[1]["prominence_db"]
        assert det.candidates[0]["psd"] < det.candidates[1]["psd"]

    def test_ordering_and_deterministic_ties(self):
        psd = np.ones(80)
        psd[15], psd[35], psd[60] = 50.0, 100.0, 50.0  # 35 first; 15 vs 60 tie -> lower frequency
        a = detect_candidates(_grid(80), psd, window_duration_s=100.0, segment_count=40)
        b = detect_candidates(_grid(80), psd, window_duration_s=100.0, segment_count=40)
        assert [c["rank"] for c in a.candidates] == [1, 2, 3]
        freqs = [c["frequency_hz"] for c in a.candidates]
        assert freqs[0] == pytest.approx(_grid(80)[35]) and freqs[1] < freqs[2]
        assert a.candidates == b.candidates

    def test_every_candidate_carries_measured_evidence(self):
        f, psd = _spectrum_with_peak(1000.0)
        c = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20).candidates[0]
        assert c["assessment"] == ASSESSMENT_CANDIDATE
        assert c["period_s"] == pytest.approx(1.0 / c["frequency_hz"])
        assert c["cycles_observed"] == pytest.approx(c["frequency_hz"] * 100.0)
        assert c["prominence_db"] == pytest.approx(30.0)
        assert _codes(c["reasons"]) == ["local_peak", "prominence", "cycles_observed", "outside_low_frequency_region", "away_from_band_edge"]
        text = " ".join(r["message"] for r in c["reasons"])
        assert "30.0 dB" in text and f"{c['cycles_observed']:.1f} cycles" in text
        assert not re.search(r"confiden|probabilit|%", text)

    def test_limited_averaging_warning(self):
        f, psd = _spectrum_with_peak(1e6)
        c = detect_candidates(f, psd, window_duration_s=100.0, segment_count=MIN_AVERAGED_SEGMENTS - 1).candidates[0]
        assert "limited_averaging" in _codes(c["warnings"])

    def test_rms_representation_attenuation_warning(self):
        f = _grid(100, 0.5, 0.5)
        psd = np.ones(100)
        psd[19], psd[49] = 1e4, 1e4  # 10 Hz and 25 Hz
        det = detect_candidates(f, psd, window_duration_s=100.0, segment_count=20, rms_nominal_frequency_hz=50.0)
        by_f = {round(c["frequency_hz"]): c for c in det.candidates}
        assert "rms_representation_attenuation" not in _codes(by_f[10]["warnings"])
        warn = [w for w in by_f[25]["warnings"] if w["code"] == "rms_representation_attenuation"][0]
        assert warn["values"]["attenuation_percent"] > 29.0
        # the PSD itself is returned as computed (no inverse-sinc compensation)
        assert by_f[25]["psd"] == pytest.approx(1e4)

    def test_complete_list_is_returned_internally(self):
        psd = np.ones(300)
        psd[10:290:20] = 100.0
        det = detect_candidates(_grid(300), psd, window_duration_s=100.0, segment_count=40)
        assert len(det.candidates) == 14 > MAX_REPORTED_CANDIDATES

    def test_constant_signal_and_empty_spectrum(self):
        det = detect_candidates(_grid(40), np.full(40, 1e-30), window_duration_s=10.0, signal_variation_negligible=True)
        assert det.status == STATUS_NONE and _codes(det.no_candidate_reasons) == ["no_spectral_content"]
        det = detect_candidates(_grid(40), np.zeros(40), window_duration_s=10.0)
        assert _codes(det.no_candidate_reasons) == ["no_spectral_content"]

    def test_whole_band_below_two_cycles(self):
        f = _grid(10, 0.01, 0.01)  # 0.01-0.10 Hz in a 10 s window: cutoff 0.2 Hz
        psd = np.ones(10)
        psd[5] = 100.0
        det = detect_candidates(f, psd, window_duration_s=10.0)
        assert det.status == STATUS_NONE
        assert "band_below_min_cycles" in _codes(det.no_candidate_reasons)
        assert det.not_promoted[0]["reason_code"] == "below_min_cycles"

    def test_low_frequency_region_is_explained_not_promoted(self):
        f = _grid(60, 0.01, 0.01)  # 0.01-0.60 Hz, cutoff 0.2 Hz (T = 10 s)
        psd = np.where(f < 0.2, 1000.0 / (f / 0.01), 1.0)
        det = detect_candidates(f, psd, window_duration_s=10.0)
        assert det.low_frequency and det.low_frequency["dominant"] is True
        assert det.low_frequency["cutoff_hz"] == pytest.approx(0.2)
        assert "not automatically classified as an oscillation" in det.low_frequency["message"]
        assert "transient" not in det.low_frequency["message"].lower()

    def test_one_cutoff_rule_matches_the_frontend_guideline(self):
        html = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
        match = re.search(r"recommendedMinObservedCycles:\s*([0-9.]+)", html)
        assert match and float(match.group(1)) == MIN_OBSERVED_CYCLES


# -------------------------------------------- synthetic signals, full path ----

FS = 50.0


def _detect(registries, x, t, *, f_min=0.1, f_max=10.0, name="X", **kw):
    _add(registries, x, t)
    return _spectrum(registries, name=name, f_min=f_min, f_max=f_max, **kw)


class TestSyntheticSignals:
    def _t(self, duration=120.0):
        return _time(FS, duration)

    def _freqs(self, r):
        return [c["frequency_hz"] for c in r["detection"]["candidates"]]

    def test_single_clean_sinusoid(self, registries):
        t = self._t()
        r = _detect(registries, np.sin(2 * np.pi * 1.35 * t), t)
        d = r["detection"]
        assert d["status"] == STATUS_FOUND and len(d["candidates"]) == 1
        c = d["candidates"][0]
        assert abs(c["frequency_hz"] - 1.35) <= r["welch"]["bin_spacing_hz"]
        assert c["period_s"] == pytest.approx(1 / c["frequency_hz"])
        assert c["cycles_observed"] == pytest.approx(c["frequency_hz"] * r["window"]["duration_s"])
        assert not d["not_promoted"]

    def test_two_simultaneous_oscillations(self, registries):
        t = self._t()
        r = _detect(registries, np.sin(2 * np.pi * 0.8 * t) + 0.7 * np.sin(2 * np.pi * 2.6 * t), t)
        found = sorted(self._freqs(r))
        spacing = r["welch"]["bin_spacing_hz"]
        assert len(found) == 2 and abs(found[0] - 0.8) <= spacing and abs(found[1] - 2.6) <= spacing

    def test_oscillation_plus_noise(self, registries):
        t = self._t()
        rng = np.random.default_rng(11)
        r = _detect(registries, np.sin(2 * np.pi * 1.35 * t) + rng.normal(0, 1.0, t.size), t)
        freqs = self._freqs(r)
        assert freqs and abs(freqs[0] - 1.35) <= r["welch"]["bin_spacing_hz"]
        assert len(freqs) <= 2  # noise ripple does not flood the result

    @pytest.mark.parametrize("seed", range(8))
    def test_pure_noise_yields_no_candidates(self, registries, seed):
        t = self._t()
        r = _detect(registries, np.random.default_rng(100 + seed).normal(0, 1.0, t.size), t)
        assert r["detection"]["status"] == STATUS_NONE
        assert r["detection"]["no_candidate_reasons"]

    def test_constant_signal(self, registries):
        t = self._t()
        r = _detect(registries, np.full(t.size, 5.0), t)
        assert r["status"] == "ok"  # the spectrum succeeded; interpretation found nothing
        assert r["detection"]["status"] == STATUS_NONE
        assert _codes(r["detection"]["no_candidate_reasons"]) == ["no_spectral_content"]

    def test_slow_trend_is_not_an_oscillation(self, registries):
        t = self._t()
        for f_min in (0.1, 0.0):
            r = _spectrum_for(registries, 0.01 * t, t, f_min)
            assert r["detection"]["status"] == STATUS_NONE, f_min

    def test_step_and_recovery_are_not_oscillations(self, registries):
        t = self._t()
        step = np.where(t > 30, 1.0, 0.0)
        recovery = np.where(t > 30, 1 - np.exp(-(t - 30) / 20), 0.0)
        for x in (step, recovery):
            for f_min in (0.1, 0.0):
                r = _spectrum_for(registries, x, t, f_min)
                assert r["detection"]["status"] == STATUS_NONE
                assert [e["reason_code"] for e in r["detection"]["not_promoted"]] == ["band_edge"]

    @pytest.mark.parametrize("f_min", [0.1, 0.0, 0.05])
    def test_disturbance_plus_ringdown_finds_the_oscillation_not_the_event(self, registries, f_min):
        t = self._t()
        event = 40.0 * np.where(t > 30, 1 - np.exp(-(t - 30) / 20), 0.0)  # large near-DC response
        ring = np.where(t > 30, np.exp(-(t - 30) / 15) * np.sin(2 * np.pi * 0.7 * (t - 30)), 0.0)
        rng = np.random.default_rng(5)
        r = _spectrum_for(registries, event + ring + 0.01 * rng.normal(size=t.size), t, f_min, f_max=5.0)
        d = r["detection"]
        top_psd_hz = r["frequencies_hz"][int(np.argmax(r["psd"]))]
        assert top_psd_hz < 0.3  # the event's low-frequency energy has the largest PSD...
        assert d["status"] == STATUS_FOUND  # ...but is not declared the oscillation
        assert abs(d["candidates"][0]["frequency_hz"] - 0.7) <= r["welch"]["bin_spacing_hz"]
        assert all(c["frequency_hz"] > 0.3 for c in d["candidates"])
        assert d["not_promoted"] and d["not_promoted"][0]["reason_code"] == "band_edge"

    def test_below_two_cycles_is_not_promoted(self, registries):
        # a sinusoid of exactly one cycle in a 30 s window, single Welch segment
        t = _time(FS, 30.0)
        r1 = _spectrum_for(registries, np.sin(2 * np.pi * (FS / 1500) * t), t, 0.01, f_max=2.0)
        assert r1["welch"]["segment_count"] == 1 and r1["welch"]["bin_spacing_hz"] == pytest.approx(FS / 1500)
        d = r1["detection"]
        assert d["status"] == STATUS_NONE
        assert d["not_promoted"][0]["cycles_observed"] == pytest.approx(1.0, abs=0.01)
        assert d["not_promoted"][0]["cycles_observed"] < MIN_OBSERVED_CYCLES
        assert d["not_promoted"][0]["reason_code"] == "below_min_cycles"
        assert "band_below_min_cycles" not in _codes(d["no_candidate_reasons"])  # the band reaches 2 Hz

    def test_sinusoid_at_the_requested_band_edge(self, registries):
        t = self._t()
        r = _detect(registries, np.sin(2 * np.pi * 5.0 * t), t, f_min=0.5, f_max=5.0)
        assert r["detection"]["status"] == STATUS_NONE
        assert r["detection"]["not_promoted"][0]["reason_code"] == "band_edge"
        wide = _spectrum(registries, f_min=0.5, f_max=8.0)
        assert wide["detection"]["status"] == STATUS_FOUND

    def test_rms_derived_candidate_carries_the_representation_warning(self, registries):
        fs, f0, fm = 2000.0, 50.0, 25.0
        t = _time(fs, 120.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, f0, amplitude=1.0, mod_hz=fm, depth=0.2)}))
        r = _spectrum(registries, name="IA", representation="rms_magnitude", start=1.0, f_min=1.0, f_max=30.0)
        c = r["detection"]["candidates"][0]
        assert abs(c["frequency_hz"] - fm) <= r["welch"]["bin_spacing_hz"]
        assert "rms_representation_attenuation" in _codes(c["warnings"])
        assert "rms_rolloff" in _codes(r["warnings"])

    def test_welch_output_is_unchanged_by_detection(self, registries):
        t = self._t(60.0)
        x = np.sin(2 * np.pi * 1.35 * t)
        r = _detect(registries, x, t)
        seg = choose_segmentation(x.size, FS, 0.1)
        ref = welch_psd(x, FS, seg)
        keep = (ref.frequencies_hz >= 0.1 - 1e-9) & (ref.frequencies_hz <= 10.0 + 1e-9)
        np.testing.assert_allclose(r["psd"], ref.psd[keep], rtol=1e-9, atol=0)

    def test_wide_spectrum_detection_latency_is_small(self, registries):
        fs, duration = 2000.0, 60.0
        t = _time(fs, duration)
        rng = np.random.default_rng(3)
        _add(registries, np.sin(2 * np.pi * 7 * t) + rng.normal(0, 1, t.size), t)
        r = _spectrum(registries, f_min=0.0, f_max=1000.0)
        assert r["frequency"]["bin_count"] > 10_000
        f, p = np.asarray(r["frequencies_hz"]), np.asarray(r["psd"])
        start = _time_module.perf_counter()
        detect_candidates(f, p, window_duration_s=duration, segment_count=r["welch"]["segment_count"])
        assert _time_module.perf_counter() - start < 1.0


def _spectrum_for(registries, x, t, f_min, *, f_max=10.0):
    registries[0].add(_active("src", t, {"X": x}, types={"X": "Frequency"}))
    return _spectrum(registries, f_min=f_min, f_max=f_max)


class TestApiShape:
    def test_detection_block_is_in_the_response_model(self):
        from app.schemas.oscillation import DetectionOut, OscillationSpectrumOut
        assert "detection" in OscillationSpectrumOut.model_fields
        assert {"status", "candidates", "not_promoted", "no_candidate_reasons", "low_frequency"} <= set(DetectionOut.model_fields)
