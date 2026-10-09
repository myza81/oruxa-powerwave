"""Oscillation Analysis -- STFT spectrogram (DEC-176 [APPROVED]). Deterministic
synthetic signals with known time-frequency behaviour, plus numerical parity
with an independently constructed `scipy.signal.spectrogram` (SciPy is a
dev-only reference; production uses NumPy). The tests inspect the matrix
directly -- the product only draws it; it classifies nothing."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy import signal as sp_signal

from app.domain.calculated_channel import ChannelRef
from app.domain.spectral_estimation import choose_segmentation, welch_psd
from app.domain.spectrogram_estimation import (
    MIN_STFT_SAMPLES,
    MIN_TIME_SLICES,
    TARGET_TIME_SLICES,
    choose_stft_geometry,
    peak_hold_rows,
    stft_psd,
)
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_spectrogram_service import MAX_MATRIX_CELLS, compute_spectrogram
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_oscillation_representation import WS, _active, _sine, _time, _upload  # noqa: F401


@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _add(registries, x, t, name="X", **kw):
    registries[0].add(_active("src", t, {name: x}, types={name: "Frequency"}, **kw))


def _gram_service(registries, name="X", *, representation="native", start=None, end=None, f_min=0.1, f_max=20.0):
    source_registry, calc_registry = registries
    t = source_registry.get(WS, "src").record.waveform_data["time"].to_numpy()
    return compute_spectrogram(
        workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name=name),
        representation=representation, signal_revision="rev-1",
        window_start_s=float(t[0]) if start is None else start, window_end_s=float(t[-1]) if end is None else end,
        f_min_hz=f_min, f_max_hz=f_max, source_registry=source_registry, calc_registry=calc_registry,
    )


def _domain(x, fs, f_min):
    return stft_psd(x, fs, choose_stft_geometry(x.size, fs, f_min))


def _track(result, hz):
    """Per-column power near `hz`: the maximum over the rows within one row spacing of it."""
    f = np.asarray(result["frequencies_hz"])
    near = np.abs(f - hz) <= 1.01 * (f[1] - f[0])
    return np.asarray(result["psd"])[near, :].max(axis=0)


def _track_domain(gram, hz):
    f = gram.frequencies_hz
    near = np.abs(f - hz) <= 1.01 * (f[1] - f[0])
    return gram.psd[near, :].max(axis=0)


# ------------------------------------------------- numerical correctness ----

class TestAgainstScipyReference:
    @pytest.mark.parametrize("fs,duration,f_min", [
        (1000.0, 60.0, 0.5), (50.0, 160.0, 0.1), (200.0, 37.3, 0.25), (333.0, 40.0, 0.0), (5000.0, 30.0, 1.0),
    ])
    def test_matches_scipy_spectrogram_for_the_same_parameters(self, fs, duration, f_min):
        t = np.arange(int(fs * duration)) / fs
        rng = np.random.default_rng(11)
        x = 3 * np.sin(2 * np.pi * 4.2 * t) + 0.7 * np.sin(2 * np.pi * 11.0 * t) + rng.normal(0, 0.5, t.size) + 12.0
        geometry = choose_stft_geometry(x.size, fs, f_min)
        ours = stft_psd(x, fs, geometry)
        # SciPy's conventions differ only in defaults: its `noverlap` default is nperseg // 8 and its
        # `mode` default is 'psd' with `scaling='density'`; everything is set explicitly here. SciPy
        # stamps a column at (start + nperseg / 2) / fs -- the same slice-centre convention.
        f_ref, t_ref, p_ref = sp_signal.spectrogram(
            x, fs=fs, window="hann", nperseg=geometry.nperseg, noverlap=geometry.noverlap, nfft=geometry.nperseg,
            detrend="constant", return_onesided=True, scaling="density", mode="psd",
        )
        assert p_ref.shape == ours.psd.shape
        np.testing.assert_allclose(ours.frequencies_hz, f_ref, rtol=0, atol=1e-9)
        np.testing.assert_allclose(ours.times_s, t_ref, rtol=0, atol=1e-9)
        np.testing.assert_allclose(ours.psd, p_ref, rtol=1e-9, atol=1e-18)

    def test_mean_over_slices_equals_the_welch_psd_of_the_same_geometry(self):
        fs = 200.0
        t = np.arange(int(fs * 50)) / fs
        x = np.random.default_rng(3).normal(0, 1, t.size) + np.sin(2 * np.pi * 6 * t)
        geometry = choose_stft_geometry(x.size, fs, 1.0)
        seg = choose_segmentation(x.size, fs, 1.0)
        # Identical geometry: same nperseg and 50 % overlap, so the slice mean IS the Welch average.
        assert (geometry.nperseg, geometry.noverlap, geometry.slice_count) == (seg.nperseg, seg.noverlap, seg.segment_count)
        welch = welch_psd(x, fs, seg)
        gram = stft_psd(x, fs, geometry)
        np.testing.assert_allclose(gram.psd.mean(axis=1), welch.psd, rtol=1e-9, atol=1e-18)

    def test_columns_are_stamped_at_the_slice_centre(self):
        fs = 100.0
        x = np.random.default_rng(1).normal(size=6000)
        g = choose_stft_geometry(x.size, fs, 0.5)
        gram = stft_psd(x, fs, g)
        assert gram.times_s[0] == pytest.approx(g.nperseg / 2 / fs)
        assert np.diff(gram.times_s) == pytest.approx(g.hop_s)


class TestWindowPolicy:
    def test_two_cycles_of_the_minimum_frequency_when_enough_slices_fit(self):
        g = choose_stft_geometry(160 * 50, 50.0, 0.5)  # wants 4 s of a 160 s window
        assert g.window_s == pytest.approx(4.0) and g.limited_by == "none"
        assert g.slice_count >= TARGET_TIME_SLICES and g.noverlap == g.nperseg // 2

    def test_window_is_shortened_to_keep_time_resolution(self):
        g = choose_stft_geometry(5001, 1000.0, 0.1)  # wants 20 s of a 5 s window
        assert g.limited_by == "time_resolution" and g.slice_count >= TARGET_TIME_SLICES
        assert g.window_s < g.target_window_s and g.window_s < 1.2  # about T / 4.5
        assert g.bin_spacing_hz == pytest.approx(1.0 / g.window_s)

    def test_zero_minimum_uses_a_fraction_of_the_window(self):
        g = choose_stft_geometry(9000, 1000.0, 0.0)
        assert g.window_s == pytest.approx(9.0 / 4.5, rel=0.02) and g.slice_count >= TARGET_TIME_SLICES

    def test_very_short_window_has_too_few_slices_but_does_not_raise(self):
        g = choose_stft_geometry(20, 100.0, 1.0)
        assert g.slice_count < MIN_TIME_SLICES and g.nperseg >= 1

    def test_minimum_samples_floor(self):
        g = choose_stft_geometry(60, 100.0, 5.0)
        assert g.nperseg >= MIN_STFT_SAMPLES


# ----------------------------------------------------- synthetic signals ----

FS = 50.0


def _t(duration=160.0, fs=FS):
    return np.arange(int(fs * duration)) / fs


class TestSyntheticSignals:
    def test_stationary_single_frequency_is_a_constant_ridge(self):
        t = _t()
        gram = _domain(np.sin(2 * np.pi * 2.0 * t), FS, 0.2)
        ridge = gram.frequencies_hz[np.argmax(gram.psd, axis=0)]
        assert np.all(np.abs(ridge - 2.0) <= gram.geometry.bin_spacing_hz)
        track = _track_domain(gram, 2.0)
        assert track.max() / track.min() < 1.3  # the same power in every slice

    def test_two_stationary_frequencies_give_two_ridges(self):
        t = _t()
        gram = _domain(np.sin(2 * np.pi * 1.0 * t) + 0.5 * np.sin(2 * np.pi * 3.5 * t), FS, 0.2)
        mean_rows = gram.psd.mean(axis=1)
        top2 = sorted(gram.frequencies_hz[np.argsort(mean_rows)[-4:]])
        assert any(abs(f - 1.0) <= 0.3 for f in top2) and any(abs(f - 3.5) <= 0.3 for f in top2)
        assert _track_domain(gram, 1.0).min() > 20 * np.median(gram.psd)
        assert _track_domain(gram, 3.5).min() > 20 * np.median(gram.psd)

    def test_component_present_only_in_the_first_half(self):
        t = _t()
        x = np.sin(2 * np.pi * 2.0 * t) * (t < 80.0) + 0.01 * np.random.default_rng(0).normal(size=t.size)
        gram = _domain(x, FS, 0.2)
        track = _track_domain(gram, 2.0)
        early, late = track[gram.times_s < 70], track[gram.times_s > 90]
        assert early.min() > 1000 * late.max()

    def test_component_appearing_after_a_disturbance(self):
        t = _t()
        x = 0.01 * np.random.default_rng(1).normal(size=t.size) + np.sin(2 * np.pi * 4.95 * t) * (t >= 60.0)
        gram = _domain(x, FS, 0.5)
        track = _track_domain(gram, 4.95)
        before, after = track[gram.times_s < 55], track[gram.times_s > 70]
        assert after.min() > 1000 * before.max()
        first_visible = gram.times_s[np.argmax(track > 0.01 * track.max())]
        assert abs(first_visible - 60.0) <= gram.geometry.window_s  # onset located to within one window

    def test_exponentially_decaying_ringdown_fades_monotonically(self):
        t = _t()
        x = np.where(t >= 40.0, np.exp(-(t - 40.0) / 25.0) * np.sin(2 * np.pi * 1.5 * t), 0.0)
        gram = _domain(x, FS, 0.5)
        track = _track_domain(gram, 1.5)
        after = track[gram.times_s > 45.0]
        assert np.all(np.diff(after) < 0)  # strictly fading
        assert track[gram.times_s < 35.0].max() < 1e-6 * after[0]

    def test_intermittent_burst_is_confined_to_its_slices(self):
        t = _t()
        x = np.sin(2 * np.pi * 3.0 * t) * (((t > 30) & (t < 50)) | ((t > 100) & (t < 120)))
        gram = _domain(x, FS, 0.5)
        track = _track_domain(gram, 3.0)
        centres = gram.times_s
        inside = ((centres > 35) & (centres < 45)) | ((centres > 105) & (centres < 115))
        outside = (centres < 25) | ((centres > 55) & (centres < 95)) | (centres > 125)
        assert track[inside].min() > 1e4 * track[outside].max()

    def test_frequency_ramp_moves_the_ridge_with_time(self):
        t = _t()
        x = np.sin(2 * np.pi * (1.0 * t + 0.5 * (4.0 / 160.0) * t ** 2))  # 1 Hz -> 5 Hz
        gram = _domain(x, FS, 0.5)
        ridge = gram.frequencies_hz[np.argmax(gram.psd, axis=0)]
        assert ridge[-1] - ridge[0] > 2.5
        assert np.all(np.diff(ridge) >= -gram.geometry.bin_spacing_hz)  # moves up, never back
        expected = 1.0 + 4.0 * gram.times_s / 160.0
        assert np.all(np.abs(ridge - expected) <= 2 * gram.geometry.bin_spacing_hz + 0.1)

    def test_constant_signal_has_no_power(self):
        gram = _domain(np.full(8000, 7.0), FS, 0.5)
        assert np.all(gram.psd == 0.0) and np.all(np.isfinite(gram.psd))

    def test_noise_only_has_no_persistent_ridge(self):
        x = np.random.default_rng(5).normal(size=8000)
        gram = _domain(x, FS, 0.5)
        mean_rows = gram.psd[1:].mean(axis=1)
        assert mean_rows.max() / np.median(mean_rows) < 3.0  # flat across frequency

    def test_step_and_recovery_do_not_hide_the_post_event_oscillation_in_db(self):
        """Real-event-like: a large near-DC step/recovery with a 4.95 Hz (frequency/MW-like) oscillation
        after it, plus a weaker 1.15 Hz MW-like component. Both ridges must be recoverable from the matrix on a
        dB scale although the event energy is orders of magnitude larger in absolute terms."""
        t = _t(120.0)
        rng = np.random.default_rng(9)
        recovery = np.where(t >= 30.0, -50.0 * (1 - np.exp(-(t - 30.0) / 4.0)) * np.exp(-(t - 30.0) / 60.0), 0.0)
        osc = np.where(t >= 30.0, np.exp(-(t - 30.0) / 30.0), 0.0) * (0.3 * np.sin(2 * np.pi * 4.95 * t) + 0.1 * np.sin(2 * np.pi * 1.15 * t))
        x = recovery + osc + 0.01 * rng.normal(size=t.size)
        gram = _domain(x, FS, 0.5)
        db = 10 * np.log10(np.maximum(gram.psd, gram.psd.max() * 1e-10))
        track495, track115 = _track_domain(gram, 4.95), _track_domain(gram, 1.15)
        floor = np.median(gram.psd[(gram.frequencies_hz > 8)])
        after = (gram.times_s > 40) & (gram.times_s < 80)  # the ringdown is still well above the floor here
        before = gram.times_s < 25
        assert track495[after].min() > 100 * floor and track115[after].min() > 10 * floor
        assert track495[before].max() < 0.1 * track495[after].min()
        assert gram.psd.max() > 1e2 * track495.max()  # the event energy dominates in absolute terms ...
        assert db.max() - 10 * np.log10(track495[after].min()) < 80  # ... yet stays inside an 80 dB range


class TestTransportReduction:
    def test_peak_hold_keeps_a_narrow_ridge_and_never_averages_it_away(self):
        f = np.arange(10, dtype=float)
        psd = np.zeros((10, 4))
        psd[7, :] = 5.0
        rf, rp = peak_hold_rows(f, psd, 4)
        assert rp.shape == (3, 4) and rp.max() == 5.0
        assert rf.tolist() == [1.5, 5.5, 8.5]

    def test_factor_one_is_the_identity(self):
        f, p = np.arange(5.0), np.ones((5, 2))
        rf, rp = peak_hold_rows(f, p, 1)
        assert rf is f and rp is p


# ----------------------------------------------------------- the service ----

class TestService:
    def test_ok_result_carries_matrix_geometry_and_setup_identity(self, registries):
        t = _t()
        _add(registries, np.sin(2 * np.pi * 2.0 * t), t)
        r = _gram_service(registries, f_min=0.5, f_max=10.0)
        assert r["status"] == "ok" and r["reason_code"] is None
        assert r["setup"] == {"representation": "native", "signal_revision": "rev-1", "window_start_s": 0.0,
                              "window_end_s": pytest.approx(t[-1]), "frequency_min_hz": 0.5, "frequency_max_hz": 10.0}
        st, fr, m = r["stft"], r["frequency"], r["matrix"]
        assert st["time_stamp"] == "window_centre" and st["zero_padding"] is False and st["window"] == "hann"
        assert st["window_s"] == pytest.approx(4.0) and st["hop_s"] == pytest.approx(2.0)
        assert st["bin_spacing_hz"] == pytest.approx(0.25) and st["overlap_fraction"] == 0.5
        assert len(r["times_s"]) == m["columns"] == st["slice_count"]
        assert len(r["frequencies_hz"]) == m["rows"] == fr["row_count"]
        assert len(r["psd"]) == m["rows"] and len(r["psd"][0]) == m["columns"]
        assert m["cells"] == m["rows"] * m["columns"] <= MAX_MATRIX_CELLS and fr["row_decimation_factor"] == 1
        assert r["times_s"][0] == pytest.approx(2.0)  # first slice centre = window / 2 after the first sample
        assert fr["returned_min_hz"] >= 0.5 - 1e-9 and fr["returned_max_hz"] <= 10.0 + 1e-9
        assert r["signal"]["psd_unit"] is None or r["signal"]["psd_unit"].endswith("²/Hz")

    def test_wire_values_are_the_domain_values_to_six_digits(self, registries):
        t = _t()
        x = np.sin(2 * np.pi * 2.0 * t) + 0.1 * np.random.default_rng(2).normal(size=t.size)
        _add(registries, x, t)
        r = _gram_service(registries, f_min=0.5, f_max=10.0)
        gram = stft_psd(x, FS, choose_stft_geometry(x.size, FS, 0.5))
        keep = (gram.frequencies_hz >= 0.5 - 1e-9) & (gram.frequencies_hz <= 10.0 + 1e-9)
        np.testing.assert_allclose(r["psd"], gram.psd[keep], rtol=1e-5, atol=0)
        np.testing.assert_allclose(r["frequencies_hz"], gram.frequencies_hz[keep], rtol=1e-12)
        np.testing.assert_allclose(r["times_s"], gram.times_s, rtol=1e-12)

    def test_requested_band_filters_the_rows(self, registries):
        t = _t()
        _add(registries, np.sin(2 * np.pi * 2.0 * t) + np.sin(2 * np.pi * 8.0 * t), t)
        r = _gram_service(registries, f_min=1.0, f_max=4.0)
        f = np.asarray(r["frequencies_hz"])
        assert f.min() >= 1.0 - 1e-9 and f.max() <= 4.0 + 1e-9
        assert abs(f[np.argmax(np.asarray(r["psd"]).mean(axis=1))] - 2.0) <= r["stft"]["bin_spacing_hz"]
        assert r["frequency"]["requested_min_hz"] == 1.0 and r["frequency"]["requested_max_hz"] == 4.0

    def test_a_window_inside_the_recording_uses_source_time(self, registries):
        t = _t() + 100.0  # source time does not start at 0
        _add(registries, np.sin(2 * np.pi * 2.0 * t), t)
        r = _gram_service(registries, start=120.0, end=200.0, f_min=0.5, f_max=10.0)
        assert r["window"]["start_s"] == pytest.approx(120.0)
        assert 120.0 < r["times_s"][0] and r["times_s"][-1] < 200.0

    def test_too_short_window_is_a_valid_unavailable_result(self, registries):
        t = _time(100.0, 0.6)  # 60 samples
        _add(registries, np.sin(2 * np.pi * 5.0 * t), t)
        r = _gram_service(registries, f_min=0.5, f_max=20.0)
        assert r["status"] == "unavailable" and r["reason_code"] == "window_too_short"
        assert "too short to provide useful time-frequency resolution" in r["message"]
        assert "Frequency Spectrum remains available" in r["message"]
        assert r["psd"] == [] and r["times_s"] == [] and r["matrix"] is None
        assert r["window"]["sample_count"] == 60 and r["signal"]["source_id"] == "src"

    def test_window_holding_less_than_one_cycle_of_the_minimum_frequency_is_unavailable(self, registries):
        t = _time(1000.0, 5.0)
        _add(registries, np.sin(2 * np.pi * 5.0 * t), t)
        r = _gram_service(registries, f_min=0.1, f_max=2.0)  # the 8-slice window (~1 s) holds 0.1 cycle of 0.1 Hz
        assert r["status"] == "unavailable" and r["reason_code"] == "window_too_short"
        assert "cycle(s) of the lowest requested frequency" in r["message"]

    def test_band_too_coarse_for_the_window_is_unavailable_with_the_reason(self, registries):
        t = _time(1000.0, 5.0)
        _add(registries, np.sin(2 * np.pi * 5.0 * t), t)
        r = _gram_service(registries, f_min=0.0, f_max=1.5)  # ~1 Hz row spacing: two rows in the band
        assert r["status"] == "unavailable" and r["reason_code"] == "frequency_resolution_too_coarse"
        assert r["stft"]["bin_spacing_hz"] > 0.5  # the actual resolution is still reported

    def test_shortened_window_warns_honestly(self, registries):
        t = _time(200.0, 30.0)
        _add(registries, np.sin(2 * np.pi * 5.0 * t), t)
        r = _gram_service(registries, f_min=0.2, f_max=20.0)  # wants 10 s of a 30 s window
        assert r["status"] == "ok" and r["stft"]["limited_by"] == "time_resolution"
        codes = [w["code"] for w in r["warnings"]]
        assert "window_shortened_for_time_resolution" in codes
        hint = next(w["message"] for w in r["warnings"] if w["code"] == "window_shortened_for_time_resolution")
        assert "raise the minimum analysis frequency" in hint
        assert r["stft"]["slice_count"] >= TARGET_TIME_SLICES

    def test_wide_band_is_peak_held_to_the_cell_cap_and_says_so(self, registries):
        fs = 2000.0
        t = np.arange(int(fs * 120)) / fs
        _add(registries, np.sin(2 * np.pi * 120.0 * t), t)
        r = _gram_service(registries, f_min=1.0, f_max=900.0)
        f = r["frequency"]
        assert r["status"] == "ok" and r["matrix"]["cells"] <= MAX_MATRIX_CELLS
        assert f["row_decimation_factor"] > 1 and f["source_row_count"] > f["row_count"]
        assert "frequency_rows_reduced" in [w["code"] for w in r["warnings"]]
        message = next(w["message"] for w in r["warnings"] if w["code"] == "frequency_rows_reduced")
        assert f"Display frequency rows reduced {f['row_decimation_factor']}× using peak-hold" in message
        assert "narrow the frequency band for full resolution" in message
        # the 120 Hz ridge survives the reduction
        grid = np.asarray(r["frequencies_hz"])
        mean = np.asarray(r["psd"]).mean(axis=1)
        assert abs(grid[np.argmax(mean)] - 120.0) <= 2 * (grid[1] - grid[0])

    def test_nan_in_the_window_is_refused_like_the_spectrum(self, registries):
        t = _t()
        x = np.sin(2 * np.pi * 2.0 * t)
        x[100] = np.nan
        _add(registries, x, t)
        with pytest.raises(ImportServiceError) as exc:
            _gram_service(registries, f_min=0.5, f_max=10.0)
        assert exc.value.code == "non_finite_samples"

    def test_invalid_requests_are_the_spectrums_errors(self, registries):
        t = _t()
        _add(registries, np.sin(2 * np.pi * 2.0 * t), t)
        for kw, code in (({"start": 50.0, "end": 10.0}, "invalid_analysis_window"),
                         ({"start": -5.0, "end": 100.0}, "invalid_analysis_window"),
                         ({"f_max": 30.0}, "invalid_frequency_range"),
                         ({"f_min": 5.0, "f_max": 2.0}, "invalid_frequency_range")):
            with pytest.raises(ImportServiceError) as exc:
                _gram_service(registries, **kw)
            assert exc.value.code == code
        with pytest.raises(ImportServiceError) as exc:
            _gram_service(registries, representation="envelope")
        assert exc.value.code == "unsupported_representation"

    def test_raw_voltage_requested_as_native_is_refused(self, registries):
        t = _time(2000.0, 20.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, 50.0)}))
        with pytest.raises(ImportServiceError) as exc:
            _gram_service(registries, name="IA", representation="native", f_min=0.5, f_max=10.0)
        assert exc.value.code == "representation_mismatch"


class TestRmsDerivedSpectrogram:
    def test_rms_modulation_ridge_appears_after_the_disturbance_with_the_rms_warnings(self, registries):
        fs, f0, fm = 1000.0, 50.0, 5.0
        t = _time(fs, 60.0)
        depth = 0.1 * (t >= 30.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, f0, amplitude=1.0, mod_hz=fm, depth=depth)}))
        r = _gram_service(registries, name="IA", representation="rms_magnitude", start=1.0, end=59.0, f_min=1.0, f_max=30.0)
        assert r["status"] == "ok" and r["representation"]["type"] == "rms_magnitude"
        assert r["representation"]["nominal_frequency_hz"] == 50.0
        assert "rms_rolloff" in [w["code"] for w in r["warnings"]]  # f_max above the -3 dB frequency
        f, times = np.asarray(r["frequencies_hz"]), np.asarray(r["times_s"])
        near = np.abs(f - fm) <= 1.01 * (f[1] - f[0])
        track = np.asarray(r["psd"])[near].max(axis=0)
        assert track[times > 40].min() > 100 * track[times < 25].max()

    def test_rms_band_reaching_the_nominal_frequency_is_invalid(self, registries):
        t = _time(2000.0, 20.0)
        registries[0].add(_active("src", t, {"IA": _sine(t, 50.0)}))
        with pytest.raises(ImportServiceError) as exc:
            _gram_service(registries, name="IA", representation="rms_magnitude", start=0.5, end=19.5, f_min=1.0, f_max=50.0)
        assert exc.value.code == "invalid_frequency_range"


class TestSpectrumIsUnchangedByTheSharedPath:
    def test_spectrum_and_spectrogram_agree_on_the_window_and_representation(self, registries):
        from app.services.oscillation_spectrum_service import compute_spectrum

        t = _t()
        _add(registries, np.sin(2 * np.pi * 2.0 * t), t)
        gram = _gram_service(registries, f_min=0.5, f_max=10.0)
        spec = compute_spectrum(
            workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name="X"),
            representation="native", window_start_s=0.0, window_end_s=float(t[-1]), f_min_hz=0.5, f_max_hz=10.0,
            source_registry=registries[0], calc_registry=registries[1],
        )
        assert gram["window"] == spec["window"] and gram["signal"] == spec["signal"]
        assert gram["representation"] == spec["representation"]


# -------------------------------------------------------------------- API ----

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


class TestApi:
    BASE = "/api/v1/workspaces/{ws}/oscillation-analysis/spectrogram"

    def _body(self, sid, **kw):
        body = {"input": {"kind": "source", "source_id": sid, "channel_name": "IA"}, "representation": "rms_magnitude",
                "signal_revision": "r1", "window_start_s": 0.2, "window_end_s": 29.9,
                "frequency_min_hz": 1.0, "frequency_max_hz": 15.0}
        body.update(kw)
        return body

    def test_endpoint_returns_the_matrix_and_the_setup_identity(self, client):
        sid = _upload(client, "w1", duration=30.0, fs=500.0, fm=5.0, depth=0.1)
        r = client.post(self.BASE.format(ws="w1"), json=self._body(sid))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok" and body["setup"]["signal_revision"] == "r1"
        assert body["setup"]["window_start_s"] == 0.2 and body["setup"]["frequency_max_hz"] == 15.0
        assert len(body["psd"]) == len(body["frequencies_hz"]) and len(body["psd"][0]) == len(body["times_s"])
        assert not any(k in body for k in ("values", "time", "samples", "detection"))
        assert client.get("/api/v1/workspaces/w1/calculated-channels").json() == []

    def test_too_short_is_200_unavailable_and_errors_carry_a_code(self, client):
        sid = _upload(client, "w2", duration=1.0, fs=500.0)
        base = self.BASE.format(ws="w2")
        r = client.post(base, json=self._body(sid, window_end_s=0.9))
        assert r.status_code == 200 and r.json()["status"] == "unavailable"
        r = client.post(base, json=self._body(sid, window_start_s=3.0, window_end_s=1.0))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_analysis_window"
        r = client.post(base, json=self._body(sid, window_end_s=0.9, frequency_max_hz=60.0))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_frequency_range"
        r = client.post(base, json=self._body(sid, window_end_s=0.9, representation="native"))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "representation_mismatch"
        assert client.post(base, json=self._body("nope")).status_code == 404
