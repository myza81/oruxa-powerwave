"""Oscillation Analysis -- Welch PSD / Frequency Spectrum (DEC-174
[PROPOSAL]). Deterministic synthetic signals with known spectra, plus
bin-for-bin parity with an independently constructed `scipy.signal.welch`
(SciPy is a dev-only reference; production uses NumPy). The tests inspect PSD
maxima directly -- there is no peak detection in the product."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy import signal as sp_signal

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import WAVEFORM_FORM_RMS
from app.domain.spectral_estimation import (
    FALLBACK_WINDOW_DIVISOR,
    MIN_SEGMENT_SAMPLES,
    choose_segmentation,
    hann_window,
    welch_psd,
)
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_spectrum_service import compute_spectrum
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_oscillation_representation import WS, _active, _comtrade, _sine, _time, _upload  # noqa: F401


def _x_type():
    return {"X": "Frequency"}


@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _spectrum(registries, name="X", *, representation="native", start=None, end=None, f_min=0.0, f_max=20.0):
    source_registry, calc_registry = registries
    active = source_registry.get(WS, "src")
    t = active.record.waveform_data["time"].to_numpy()
    return compute_spectrum(
        workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name=name),
        representation=representation,
        window_start_s=float(t[0]) if start is None else start, window_end_s=float(t[-1]) if end is None else end,
        f_min_hz=f_min, f_max_hz=f_max, source_registry=source_registry, calc_registry=calc_registry,
    )


def _add(registries, x, t, **kw):
    registries[0].add(_active("src", t, {"X": x}, types=_x_type(), **kw))


def _peak_hz(result):
    return result["frequencies_hz"][int(np.argmax(result["psd"]))]


def _psd_at(result, hz):
    f = np.asarray(result["frequencies_hz"])
    return result["psd"][int(np.argmin(np.abs(f - hz)))]


# ------------------------------------------------- numerical correctness ----

class TestAgainstScipyReference:
    @pytest.mark.parametrize("fs,duration,f_min", [
        (1000.0, 10.0, 0.5), (5000.0, 20.0, 1.0), (200.0, 7.3, 0.0), (1000.0, 3.0, 0.1), (333.0, 12.0, 0.25),
    ])
    def test_matches_scipy_welch_for_the_same_parameters(self, fs, duration, f_min):
        t = np.arange(int(fs * duration)) / fs
        rng = np.random.default_rng(7)
        x = 3 * np.sin(2 * np.pi * 4.2 * t) + 0.7 * np.sin(2 * np.pi * 11.0 * t) + rng.normal(0, 0.5, t.size) + 12.0
        seg = choose_segmentation(x.size, fs, f_min)
        ours = welch_psd(x, fs, seg)
        f_ref, p_ref = sp_signal.welch(
            x, fs=fs, window="hann", nperseg=seg.nperseg, noverlap=seg.noverlap, nfft=seg.nperseg,
            detrend="constant", return_onesided=True, scaling="density", average="mean",
        )
        np.testing.assert_allclose(ours.frequencies_hz, f_ref, rtol=0, atol=1e-9)
        np.testing.assert_allclose(ours.psd, p_ref, rtol=1e-9, atol=1e-18)

    def test_segment_geometry_and_count_match_scipy(self):
        fs, n = 1000.0, 10_000
        seg = choose_segmentation(n, fs, 0.5)  # 2 / 0.5 = 4 s -> 4000 samples
        assert seg.nperseg == 4000 and seg.noverlap == 2000
        assert seg.segment_s == pytest.approx(4.0) and seg.bin_spacing_hz == pytest.approx(0.25)
        assert seg.segment_count == 4  # (10000 - 2000) // 2000
        # SciPy's own segment bookkeeping for the same call
        step = seg.nperseg - seg.noverlap
        assert (n - seg.noverlap) // step == seg.segment_count

    def test_hann_window_is_scipys_periodic_hann(self):
        np.testing.assert_allclose(hann_window(64), sp_signal.get_window("hann", 64), atol=1e-15)

    def test_density_scaling_preserves_variance_parseval(self):
        """Integral of the one-sided PSD ~ variance of the (mean-removed) signal."""
        fs = 1000.0
        t = np.arange(20_000) / fs
        x = 2.0 * np.sin(2 * np.pi * 5.0 * t) + 10.0
        res = welch_psd(x, fs, choose_segmentation(x.size, fs, 1.0))
        assert np.trapezoid(res.psd, res.frequencies_hz) == pytest.approx(np.var(x), rel=0.02)  # 2^2 / 2


class TestSegmentRule:
    def test_two_cycles_of_the_minimum_frequency(self):
        seg = choose_segmentation(50_000, 1000.0, 0.2)  # 2 / 0.2 = 10 s
        assert seg.segment_s == pytest.approx(10.0) and seg.target_segment_s == pytest.approx(10.0)
        assert not seg.clamped_to_window

    def test_target_longer_than_window_clamps_to_one_segment(self):
        seg = choose_segmentation(5000, 1000.0, 0.1)  # wants 20 s, window is 5 s
        assert seg.clamped_to_window and seg.nperseg == 5000 and seg.segment_count == 1
        assert seg.bin_spacing_hz == pytest.approx(0.2)

    def test_zero_minimum_uses_a_window_fraction_without_dividing_by_zero(self):
        n, fs = 9000, 1000.0
        seg = choose_segmentation(n, fs, 0.0)
        assert seg.segment_s == pytest.approx(n / fs / FALLBACK_WINDOW_DIVISOR)
        assert seg.segment_count >= 7

    def test_too_few_samples_raise(self):
        with pytest.raises(ValueError):
            choose_segmentation(MIN_SEGMENT_SAMPLES - 1, 100.0, 1.0)

    def test_deterministic(self):
        assert choose_segmentation(12345, 977.0, 0.3) == choose_segmentation(12345, 977.0, 0.3)


# ------------------------------------------------------ synthetic signals ----

class TestSyntheticSignals:
    FS = 200.0

    def _t(self, duration=60.0):
        return _time(self.FS, duration)

    def test_a_pure_5hz_peaks_at_5hz(self, registries):
        t = self._t()
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=1.0, f_max=30.0)
        assert abs(_peak_hz(r) - 5.0) <= r["welch"]["bin_spacing_hz"]
        # amplitude 1 -> power 0.5; Hann scaling puts that power inside a bin or two
        total = np.trapezoid(r["psd"], r["frequencies_hz"])
        assert total == pytest.approx(0.5, rel=0.05)

    def test_b_pure_10hz_peaks_at_10hz(self, registries):
        t = self._t()
        _add(registries, np.sin(2 * np.pi * 10 * t), t)
        r = _spectrum(registries, f_min=1.0, f_max=30.0)
        assert abs(_peak_hz(r) - 10.0) <= r["welch"]["bin_spacing_hz"]

    def test_c_mixed_signal_contains_both_with_5hz_stronger(self, registries):
        t = self._t()
        _add(registries, 2 * np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 12 * t), t)
        r = _spectrum(registries, f_min=1.0, f_max=30.0)
        p5, p12 = _psd_at(r, 5.0), _psd_at(r, 12.0)
        floor = float(np.median(r["psd"]))
        assert p5 > p12 > 100 * floor
        # power ratio (2/0.5)^2 = 16 (Hann leakage keeps it near, not exact)
        assert p5 / p12 == pytest.approx(16.0, rel=0.25)
        assert abs(_peak_hz(r) - 5.0) <= r["welch"]["bin_spacing_hz"]

    def test_d_seeded_noise_keeps_the_component_apparent(self, registries):
        t = self._t(120.0)
        rng = np.random.default_rng(2026)
        _add(registries, np.sin(2 * np.pi * 7 * t) + rng.normal(0, 1.0, t.size), t)
        r = _spectrum(registries, f_min=1.0, f_max=30.0)
        assert abs(_peak_hz(r) - 7.0) <= r["welch"]["bin_spacing_hz"]
        assert _psd_at(r, 7.0) > 10 * float(np.median(r["psd"]))

    def test_f_constant_signal_has_no_oscillatory_content(self, registries):
        t = self._t(30.0)
        _add(registries, np.full(t.size, 42.0), t)
        r = _spectrum(registries, f_min=0.0, f_max=30.0)
        assert r["frequency"]["returned_min_hz"] == 0.0  # DC bin is returned...
        assert max(r["psd"]) < 1e-20  # ...and is numerically zero after detrending

    def test_dc_offset_does_not_leak_into_the_band(self, registries):
        t = self._t()
        _add(registries, 1000.0 + np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=0.0, f_max=30.0)
        assert abs(_peak_hz(r) - 5.0) <= r["welch"]["bin_spacing_hz"]
        assert r["psd"][0] < 1e-3 * max(r["psd"])

    def test_h_requested_frequency_range_bounds_the_arrays(self, registries):
        t = self._t()
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=3.0, f_max=8.0)
        f = np.asarray(r["frequencies_hz"])
        assert f.min() >= 3.0 - 1e-9 and f.max() <= 8.0 + 1e-9
        assert r["frequency"]["returned_min_hz"] == pytest.approx(f.min())
        assert r["frequency"]["returned_max_hz"] == pytest.approx(f.max())
        assert r["frequency"]["bin_count"] == f.size == len(r["psd"])
        assert len(f) < r["welch"]["nperseg"] // 2 + 1  # band-limited, not the whole spectrum

    def test_analysis_window_selects_samples(self, registries):
        t = self._t(60.0)
        x = np.where(t < 30, np.sin(2 * np.pi * 5 * t), np.sin(2 * np.pi * 10 * t))
        _add(registries, x, t)
        first = _spectrum(registries, start=0.0, end=29.9, f_min=1.0, f_max=30.0)
        second = _spectrum(registries, start=30.1, end=59.9, f_min=1.0, f_max=30.0)
        assert abs(_peak_hz(first) - 5.0) <= first["welch"]["bin_spacing_hz"]
        assert abs(_peak_hz(second) - 10.0) <= second["welch"]["bin_spacing_hz"]
        assert first["window"]["sample_count"] == pytest.approx(29.9 * self.FS + 1, abs=1)


# ---------------------------------------------------- metadata / warnings ----

class TestMetadataAndWarnings:
    FS = 200.0

    def test_resolution_concepts_are_reported_separately(self, registries):
        t = _time(self.FS, 10.0)
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=0.5, f_max=20.0)  # segment 4 s, window 10 s
        w, win = r["welch"], r["window"]
        assert win["duration_s"] == pytest.approx(10.0 - 1 / self.FS)
        assert win["basic_resolution_hz"] == pytest.approx(1 / win["duration_s"])
        assert w["segment_s"] == pytest.approx(4.0) and w["bin_spacing_hz"] == pytest.approx(0.25)
        assert w["bin_spacing_hz"] == pytest.approx(self.FS / w["nperseg"])
        assert w["bin_spacing_hz"] != pytest.approx(win["basic_resolution_hz"])
        assert w["overlap_fraction"] == 0.5 and w["overlap_samples"] == w["nperseg"] // 2
        assert w["segment_count"] == 4
        assert (w["detrend"], w["window"], w["scaling"], w["average"]) == ("constant", "hann", "density", "mean")
        assert w["zero_padding"] is False and w["nfft"] == w["nperseg"]
        assert r["representation"]["type"] == "native"
        assert r["signal"]["psd_unit"] == "A²/Hz" and r["signal"]["unit"] == "A"
        assert r["warnings"] == []

    def test_g_short_window_warns_single_segment_and_insufficient_window(self, registries):
        t = _time(self.FS, 5.0)
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=0.1, f_max=20.0)  # wants 20 s of a 5 s window
        codes = {w["code"] for w in r["warnings"]}
        assert {"insufficient_window_for_min_frequency", "single_segment", "min_frequency_below_bin_spacing"} <= codes
        assert r["welch"]["segment_count"] == 1
        assert r["frequency"]["returned_min_hz"] > 0.1  # first bin is honestly above the request

    def test_few_segments_is_limited_averaging_not_single(self, registries):
        t = _time(self.FS, 12.0)
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=0.5, f_max=20.0)  # 4 s segments in 12 s -> 5 segments
        assert r["welch"]["segment_count"] == 5 and r["warnings"] == []
        r = _spectrum(registries, start=0.0, end=4.0, f_min=0.5, f_max=20.0)
        assert r["welch"]["segment_count"] == 1
        r = _spectrum(registries, start=0.0, end=7.0, f_min=0.5, f_max=20.0)  # 1401 samples, 800/seg -> 2
        assert r["welch"]["segment_count"] == 2
        assert "few_segments" in {w["code"] for w in r["warnings"]}

    def test_f_min_zero_is_valid_and_includes_dc(self, registries):
        t = _time(self.FS, 20.0)
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        r = _spectrum(registries, f_min=0.0, f_max=20.0)
        assert r["frequencies_hz"][0] == 0.0
        assert r["welch"]["segment_rule"].startswith("window / 4.5")
        assert r["welch"]["segment_count"] >= 7

    def test_compact_payload_is_band_limited(self, registries):
        fs = 5000.0
        t = _time(fs, 40.0)
        _add(registries, np.sin(2 * np.pi * 1.3 * t), t)
        r = _spectrum(registries, f_min=0.1, f_max=2.0)
        # 2 / 0.1 Hz = 20 s = 100 000 samples per segment; 200 000 samples -> 3 segments of 50 % overlap.
        assert r["welch"]["nperseg"] == 100_000 and r["welch"]["segment_count"] == 3
        assert r["frequency"]["bin_count"] == 39  # 0.05 Hz spacing, 0.10 .. 2.00 Hz
        assert len(r["psd"]) == 39  # the 50 001-bin full spectrum is never sent


# ----------------------------------------------------------------- errors ----

class TestErrors:
    def _setup(self, registries):
        t = _time(200.0, 20.0)
        _add(registries, np.sin(2 * np.pi * 5 * t), t)

    @pytest.mark.parametrize("kwargs,code", [
        (dict(start=5.0, end=5.0), "invalid_analysis_window"),
        (dict(start=8.0, end=3.0), "invalid_analysis_window"),
        (dict(start=-5.0, end=10.0), "invalid_analysis_window"),
        (dict(start=0.0, end=500.0), "invalid_analysis_window"),
        (dict(f_min=-1.0), "invalid_frequency_range"),
        (dict(f_min=10.0, f_max=10.0), "invalid_frequency_range"),
        (dict(f_max=150.0), "invalid_frequency_range"),
        (dict(f_max=float("nan")), "invalid_frequency_range"),
        (dict(start=1.0, end=1.01), "insufficient_samples"),
    ])
    def test_invalid_requests_are_rejected_independently_of_the_frontend(self, registries, kwargs, code):
        self._setup(registries)
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, **kwargs)
        assert exc.value.code == code

    def test_unknown_representation(self, registries):
        self._setup(registries)
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, representation="envelope")
        assert exc.value.code == "unsupported_representation"

    def test_non_finite_samples_are_refused_not_interpolated(self, registries):
        t = _time(200.0, 20.0)
        x = np.sin(2 * np.pi * 5 * t)
        x[1000] = np.nan
        _add(registries, x, t)
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries)
        assert exc.value.code == "non_finite_samples"

    def test_non_uniform_sampling_is_refused(self, registries):
        t = _time(200.0, 20.0)
        t[2000:] += 0.02
        _add(registries, np.sin(2 * np.pi * 5 * t), t)
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries)
        assert exc.value.code == "non_uniform_sampling"

    def test_missing_signal(self, registries):
        self._setup(registries)
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, name="NOPE")
        assert exc.value.code in ("channel_not_found", "channel_not_analog")

    def test_raw_instantaneous_current_cannot_be_analysed_as_recorded(self, registries):
        t = _time(5000.0, 2.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, amplitude=100.0)}))
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, name="IA", representation="native")
        assert exc.value.code == "representation_mismatch"

    def test_unavailable_rms_representation_is_an_error_not_an_empty_spectrum(self, registries):
        t = _time(5000.0, 0.01)
        registries[0].add(_active("src", t, {"IA": _sine(t)}))
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, name="IA", representation="rms_magnitude", f_max=10.0)
        assert exc.value.code == "representation_unavailable"


# ---------------------------------------------------- RMS representation ----

class TestRmsDerivedSpectrum:
    def test_e_rms_modulation_shows_5hz_with_known_rolloff(self, registries):
        fs, f0, fm, depth = 2000.0, 50.0, 5.0, 0.1
        t = _time(fs, 60.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, f0, amplitude=1.0, mod_hz=fm, depth=depth)}))
        r = _spectrum(registries, name="IA", representation="rms_magnitude", start=1.0, f_min=1.0, f_max=20.0)
        assert r["representation"]["type"] == "rms_magnitude"
        assert r["representation"]["nominal_frequency_hz"] == 50.0
        assert abs(_peak_hz(r) - fm) <= r["welch"]["bin_spacing_hz"]
        # The spectral power of a 5 Hz ripple of amplitude m*h/sqrt(2) (RMS of a unit-amplitude carrier
        # is 1/sqrt2): P = (depth * h / sqrt(2))^2 / 2, with h = |sinc(fm/f0)| the documented roll-off.
        h = abs(math.sin(math.pi * fm / f0) / (math.pi * fm / f0))
        expected_power = (depth * h / math.sqrt(2)) ** 2 / 2
        band = (np.asarray(r["frequencies_hz"]) > fm - 2.5) & (np.asarray(r["frequencies_hz"]) < fm + 2.5)
        power = np.trapezoid(np.asarray(r["psd"])[band], np.asarray(r["frequencies_hz"])[band])
        assert power == pytest.approx(expected_power, rel=0.05)
        # No compensation: amplitudes are as the RMS window leaves them (not divided by h).
        assert power != pytest.approx((depth / math.sqrt(2)) ** 2 / 2, rel=0.01)

    def test_rms_window_is_the_representations_usable_range(self, registries):
        t = _time(2000.0, 10.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, 50.0)}))
        with pytest.raises(ImportServiceError) as exc:  # first 20 ms is boundary loss
            _spectrum(registries, name="IA", representation="rms_magnitude", start=0.0, end=9.0, f_max=10.0)
        assert exc.value.code == "invalid_analysis_window"
        r = _spectrum(registries, name="IA", representation="rms_magnitude", start=0.5, end=9.5, f_min=0.5, f_max=10.0)
        assert r["window"]["start_s"] == pytest.approx(0.5)

    def test_rolloff_warning_and_bandwidth_limit(self, registries):
        t = _time(2000.0, 20.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, 50.0)}))
        r = _spectrum(registries, name="IA", representation="rms_magnitude", start=0.5, end=19.5, f_min=1.0, f_max=30.0)
        roll = [w for w in r["warnings"] if w["code"] == "rms_rolloff"]
        assert roll and "not corrected" in roll[0]["message"]
        with pytest.raises(ImportServiceError) as exc:
            _spectrum(registries, name="IA", representation="rms_magnitude", start=0.5, end=19.5, f_min=1.0, f_max=50.0)
        assert exc.value.code == "invalid_frequency_range"

    def test_already_rms_calculated_style_channel_is_native(self, registries):
        t = _time(200.0, 30.0)
        registries[0].add(_active("src", t, {"IA": 1 + 0.1 * np.sin(2 * np.pi * 3 * t)}, forms={"IA": WAVEFORM_FORM_RMS}))
        r = _spectrum(registries, name="IA", representation="native", f_min=0.5, f_max=20.0)
        assert abs(_peak_hz(r) - 3.0) <= r["welch"]["bin_spacing_hz"]


# -------------------------------------------------------------------- API ----

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


class TestApi:
    BASE = "/api/v1/workspaces/{ws}/oscillation-analysis/spectrum"

    def _body(self, sid, **kw):
        body = {"input": {"kind": "source", "source_id": sid, "channel_name": "IA"}, "representation": "rms_magnitude",
                "signal_revision": "r1", "window_start_s": 0.2, "window_end_s": 4.9,
                "frequency_min_hz": 1.0, "frequency_max_hz": 15.0}
        body.update(kw)
        return body

    def test_spectrum_endpoint_returns_compact_result_and_parameters(self, client):
        sid = _upload(client, "w1", duration=5.0, fm=5.0, depth=0.1)
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok" and body["representation"]["type"] == "rms_magnitude"
        assert body["signal"]["name"] == "IA" and body["signal"]["source_recording"] == "e.cfg"
        assert len(body["frequencies_hz"]) == len(body["psd"]) == body["frequency"]["bin_count"]
        assert abs(body["frequencies_hz"][int(np.argmax(body["psd"]))] - 5.0) <= body["welch"]["bin_spacing_hz"]
        assert not any(k in body for k in ("values", "time", "samples"))
        assert client.get("/api/v1/workspaces/w1/calculated-channels").json() == []

    def test_error_responses_carry_a_code(self, client):
        sid = _upload(client, "w2", duration=5.0)
        base = self.BASE.format(ws="w2")
        r = client.post(base, json=self._body(sid, window_start_s=3.0, window_end_s=1.0))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_analysis_window"
        r = client.post(base, json=self._body(sid, frequency_max_hz=60.0))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_frequency_range"
        r = client.post(base, json=self._body(sid, representation="native"))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "representation_mismatch"
        r = client.post(base, json=self._body("nope"))
        assert r.status_code == 404
        r = client.post(base, json=self._body(sid, representation="envelope"))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "unsupported_representation"

    def test_detection_block_is_serialised_and_absence_is_not_an_error(self, client):
        """DEC-175 [PROPOSAL]: candidate detection rides on the spectrum response."""
        sid = _upload(client, "w3", duration=5.0, fm=5.0, depth=0.1)
        body = client.post(self.BASE.format(ws="w3"), json=self._body(sid)).json()
        det = body["detection"]
        assert det["status"] in ("candidates_found", "no_candidate")
        assert {"candidates", "not_promoted", "no_candidate_reasons", "low_frequency", "parameters", "counts"} <= set(det)
        assert det["parameters"]["minimum_observed_cycles"] == 2.0
        # a flat band is still a successful spectrum with an explained "no candidate"
        flat = client.post(self.BASE.format(ws="w3"), json=self._body(sid, frequency_min_hz=12.0, frequency_max_hz=14.0))
        assert flat.status_code == 200 and "detection" in flat.json()
