"""Oscillation Analysis -- raw V/I -> RMS magnitude representation (DEC-173
[APPROVED]). Deterministic synthetic waveforms with a known envelope; no
FFT/PSD is used or implemented -- the derived magnitude is compared with the
analytic envelope in the time domain."""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import OP_RMS, OP_REVERSE_POLARITY, ChannelRef
from app.domain.channel_classification import WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS, WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.oscillation_representation import (
    HALF_POWER_RATIO,
    REPRESENTATION_RMS_MAGNITUDE,
    derive_rms_magnitude,
    representation_unavailable_reason,
    rms_bandwidth_limit_hz,
    rms_envelope_response,
    rms_half_power_frequency_hz,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import ChannelNotFoundError
from app.services.oscillation_representation_service import (
    NOMINAL_FREQUENCY_ASSUMED_DEFAULT,
    NOMINAL_FREQUENCY_RECORDING_METADATA,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    UnsupportedRepresentationError,
    derive_analysis_representation,
    describe,
)
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _time(fs: float, duration: float) -> np.ndarray:
    return np.arange(int(round(fs * duration))) / fs


def _sine(t, f0=50.0, amplitude=1.0, mod_hz=0.0, depth=0.0):
    return amplitude * (1.0 + depth * np.sin(2 * np.pi * mod_hz * t)) * np.sin(2 * np.pi * f0 * t)


def _active(source_id, time, channels, *, f0=50.0, types=None, forms=None, provenance=None) -> ActiveSource:
    types = types or {}
    forms = forms or {}
    record = DisturbanceRecord(
        metadata=RecordingMetadata(station_name="S", recorder_name="R", source_file="s.cfg",
                                   provider_type="COMTRADE", nominal_frequency=f0),
        waveform_data=pd.DataFrame({"time": time, **channels}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=START, trigger_time=START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE", original_filenames=("s.cfg", "s.dat"),
        created_at=START, station_name="S", recorder_name="R", nominal_frequency=f0,
        timing_reference="absolute", start_time=START, trigger_time=START, sample_count=len(time),
        duration_seconds=float(time[-1] - time[0]), elapsed_start_seconds=float(time[0]),
        elapsed_end_seconds=float(time[-1]), sampling_rates=(1.0,), samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(name=n, index=i, unit="A", engineering_type=types.get(n, "Current"),
                                 waveform_form=forms.get(n, WAVEFORM_FORM_UNKNOWN))
            for i, n in enumerate(channels)
        ],
        digital_channels=[], preparation_provenance=provenance,
    )
    return ActiveSource(metadata=metadata, record=record)


@pytest.fixture
def registries():
    return WorkspaceRegistry(), CalculatedChannelRegistry()


def _ready(registries, channel_name="IA", representation=REPRESENTATION_RMS_MAGNITUDE):
    source_registry, calc_registry = registries
    return derive_analysis_representation(
        workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src", channel_name=channel_name),
        representation=representation, source_registry=source_registry, calc_registry=calc_registry,
    )


class TestEngineReuseAndSynthetic:
    @pytest.mark.parametrize("f0", [50.0, 60.0])
    @pytest.mark.parametrize("fs", [1000.0, 2000.0, 4000.0, 5000.0, 10000.0])
    def test_constant_amplitude_gives_constant_magnitude(self, fs, f0):
        t = _time(fs, 1.0)
        d = derive_rms_magnitude(t, _sine(t, f0, amplitude=100.0), f0)
        valid = d.values[np.isfinite(d.values)]
        # Samples/cycle may be non-integer (e.g. 60 Hz at 5 kHz = 83.33): the
        # engine rounds its window to whole samples, so allow that residue.
        spp = fs / f0
        tolerance = 0.02 if abs(spp - round(spp)) > 1e-9 else 1e-9
        assert np.max(np.abs(valid / (100.0 / math.sqrt(2)) - 1.0)) < max(tolerance, 1e-9)

    def test_modulated_amplitude_recovers_5hz_envelope(self):
        fs, f0, fm, depth = 5000.0, 50.0, 5.0, 0.1
        t = _time(fs, 2.0)
        d = derive_rms_magnitude(t, _sine(t, f0, mod_hz=fm, depth=depth), f0)
        ok = np.isfinite(d.values)
        normalised = d.values[ok] * math.sqrt(2) - 1.0  # envelope deviation from unity
        # Analytic expectation: attenuation |sinc(fm/f0)| and the T/2 trailing delay.
        h = rms_envelope_response(fm, f0)
        assert abs(h - 0.9836) < 1e-3
        tt = t[ok]
        # Amplitude and delay of the recovered 5 Hz ripple, by projection onto
        # sin/cos at fm (a time-domain fit; no spectrum is computed).
        a = 2 * np.mean(normalised * np.sin(2 * np.pi * fm * tt))
        b = 2 * np.mean(normalised * np.cos(2 * np.pi * fm * tt))
        assert math.hypot(a, b) == pytest.approx(depth * h, abs=3e-3)
        delay = -math.atan2(b, a) / (2 * np.pi * fm)  # phase lag -> seconds
        assert delay == pytest.approx(d.group_delay_s, abs=5e-4)
        # Pointwise vs the first-order model. The residual is the second-order
        # (depth^2 / 2 = 0.005) term of sqrt(mean(A^2)), not an algorithm error.
        expected = depth * h * np.sin(2 * np.pi * fm * (tt - d.group_delay_s))
        assert np.max(np.abs(normalised - expected)) < depth**2
        # Independent of the analytic model: ~20 zero crossings in 2 s of a 5 Hz ripple.
        centred = normalised - normalised.mean()
        crossings = int(np.count_nonzero(np.diff(np.signbit(centred).astype(int))))
        assert 19 <= crossings <= 21

    def test_boundary_loss_is_exactly_one_nominal_cycle_at_the_start_only(self):
        fs, f0 = 5000.0, 50.0
        t = _time(fs, 0.5)
        d = derive_rms_magnitude(t, _sine(t, f0), f0)
        assert d.window_s == pytest.approx(0.02)
        assert d.first_valid_index == 100  # window_samples = fs / f0
        assert d.last_valid_index == len(t) - 1  # no loss at the end
        assert t[d.first_valid_index] - t[0] == pytest.approx(0.02)
        assert d.valid_count == len(t) - 100
        assert d.group_delay_s == pytest.approx(0.01)
        assert d.time is t  # stays on the source time axis, not resampled

    def test_output_is_one_value_per_source_sample(self):
        t = _time(2000.0, 0.3)
        d = derive_rms_magnitude(t, _sine(t), 50.0)
        assert d.values.shape == t.shape

    def test_unavailable_when_recording_shorter_than_one_cycle(self):
        t = _time(5000.0, 0.015)
        assert representation_unavailable_reason(t, 50.0)[0] == "recording_too_short"

    def test_unavailable_when_sampling_too_sparse(self):
        t = _time(150.0, 1.0)  # 3 samples/cycle at 50 Hz
        assert representation_unavailable_reason(t, 50.0)[0] == "sampling_too_sparse"

    def test_unavailable_for_invalid_nominal_frequency(self):
        assert representation_unavailable_reason(_time(5000.0, 1.0), float("nan"))[0] == "invalid_nominal_frequency"

    def test_nonfinite_samples_only_remove_the_windows_that_contain_them(self):
        t = _time(5000.0, 1.0)
        x = _sine(t)
        x[2500] = np.nan
        d = derive_rms_magnitude(t, x, 50.0)
        assert np.isnan(d.values[2500]) and np.isnan(d.values[2599])
        assert np.isfinite(d.values[2600]) and np.isfinite(d.values[2499])


class TestBandwidthModel:
    def test_half_power_constant(self):
        assert HALF_POWER_RATIO == pytest.approx(0.44294, abs=1e-4)
        assert rms_half_power_frequency_hz(50.0) == pytest.approx(22.147, abs=5e-3)
        assert rms_half_power_frequency_hz(60.0) == pytest.approx(26.576, abs=5e-3)
        assert rms_envelope_response(rms_half_power_frequency_hz(50.0), 50.0) == pytest.approx(1 / math.sqrt(2), abs=1e-6)

    def test_response_has_null_at_nominal_and_limit_equals_nominal(self):
        assert rms_envelope_response(50.0, 50.0) < 1e-12
        assert rms_envelope_response(0.0, 50.0) == 1.0
        assert rms_bandwidth_limit_hz(60.0) == 60.0

    @pytest.mark.parametrize("fm", [2.0, 10.0, 20.0, 30.0])
    def test_measured_attenuation_matches_model(self, fm):
        """Empirical amplitude of the recovered ripple vs |sinc(fm/f0)| --
        the basis of the documented bandwidth."""
        fs, f0, depth = 10000.0, 50.0, 0.05
        t = _time(fs, 4.0)
        d = derive_rms_magnitude(t, _sine(t, f0, mod_hz=fm, depth=depth), f0)
        ok = np.isfinite(d.values)
        ripple = d.values[ok] * math.sqrt(2) - 1.0
        # Least-squares amplitude at fm (projection on sin/cos; no spectrum computed).
        tt = t[ok]
        a = 2 * np.mean(ripple * np.sin(2 * np.pi * fm * tt))
        b = 2 * np.mean(ripple * np.cos(2 * np.pi * fm * tt))
        measured = math.hypot(a, b) / depth
        assert measured == pytest.approx(rms_envelope_response(fm, f0), abs=0.02)


class TestService:
    def test_raw_unknown_form_instantaneous_current_is_ready_and_nothing_is_persisted(self, registries):
        source_registry, calc_registry = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t, amplitude=100.0)}))
        result = _ready(registries)
        assert result.status == STATUS_READY
        assert result.nominal_frequency_origin == NOMINAL_FREQUENCY_RECORDING_METADATA
        info = describe(result)
        assert info["source_sample_count"] == 5000
        assert info["derived_sample_count"] == 4900
        assert info["source_sample_rate_hz"] == pytest.approx(5000.0)
        assert info["representation_sample_rate_hz"] == pytest.approx(5000.0)
        assert info["reporting"] == "every_source_sample"
        assert info["boundary_loss_start_s"] == pytest.approx(0.02)
        assert info["boundary_loss_end_s"] == pytest.approx(0.0)
        assert info["valid_start_s"] == pytest.approx(0.02)
        assert info["valid_end_s"] == pytest.approx(t[-1])
        assert info["bandwidth_half_power_hz"] == pytest.approx(22.147, abs=5e-3)
        assert info["bandwidth_limit_hz"] == 50.0
        assert "values" not in info and "time" not in info
        assert calc_registry.list_for_workspace(WS) == []

    def test_nominal_frequency_comes_from_the_recording_60hz(self, registries):
        source_registry, _ = registries
        t = _time(6000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t, 60.0)}, f0=60.0))
        info = describe(_ready(registries))
        assert info["nominal_frequency_hz"] == 60.0
        assert info["window_s"] == pytest.approx(1 / 60.0)
        assert info["bandwidth_limit_hz"] == 60.0

    def test_assumed_default_nominal_frequency_is_surfaced(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t)}, provenance={"nominal_frequency_assumed": True}))
        assert _ready(registries).nominal_frequency_origin == NOMINAL_FREQUENCY_ASSUMED_DEFAULT

    def test_trusted_instantaneous_form_skips_the_detector(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": 0.0 * t + 1.0}, forms={"IA": WAVEFORM_FORM_INSTANTANEOUS}))
        assert _ready(registries).status == STATUS_READY

    def test_already_rms_channel_is_not_rms_d_again(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": 0.0 * t + 1.0}, forms={"IA": WAVEFORM_FORM_RMS}))
        result = _ready(registries)
        assert (result.status, result.reason_code) == (STATUS_UNAVAILABLE, "already_magnitude")

    def test_detected_magnitude_like_channel_is_unavailable(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": 100.0 + 5.0 * np.sin(2 * np.pi * 3 * t)}))
        assert _ready(registries).status == STATUS_UNAVAILABLE

    def test_non_voltage_current_is_unavailable(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"F": _sine(t)}, types={"F": "Frequency"}))
        assert _ready(registries, "F").reason_code == "not_voltage_or_current"

    def test_short_recording_is_unavailable_with_reason(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 0.015)
        source_registry.add(_active("src", t, {"IA": _sine(t)}, forms={"IA": WAVEFORM_FORM_INSTANTANEOUS}))
        assert _ready(registries).reason_code == "recording_too_short"

    def test_calculated_instantaneous_channel_is_ready(self, registries):
        source_registry, calc_registry = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t)}))
        neg = create_calculated_channel(
            workspace_id=WS, name="-IA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="IA")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        result = derive_analysis_representation(
            workspace_id=WS, input_ref=ChannelRef(kind="calculated", calculated_channel_id=neg.id),
            representation=REPRESENTATION_RMS_MAGNITUDE, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert result.status == STATUS_READY
        assert len(calc_registry.list_for_workspace(WS)) == 1  # only the one the test made

    def test_calculated_rms_channel_is_already_magnitude(self, registries):
        source_registry, calc_registry = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t)}))
        rms = create_calculated_channel(
            workspace_id=WS, name="RMS (IA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="IA")],
            parameters={"nominal_frequency_hz": 50.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        result = derive_analysis_representation(
            workspace_id=WS, input_ref=ChannelRef(kind="calculated", calculated_channel_id=rms.id),
            representation=REPRESENTATION_RMS_MAGNITUDE, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert result.reason_code == "already_magnitude"

    def test_unknown_representation_and_missing_channel_raise(self, registries):
        source_registry, _ = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t)}))
        with pytest.raises(UnsupportedRepresentationError):
            _ready(registries, representation="positive_sequence")
        with pytest.raises(ChannelNotFoundError):
            _ready(registries, "NOPE")

    def test_derived_series_matches_the_calculated_channel_engine_exactly(self, registries):
        """No duplicate algorithm: the derived series is bit-identical to the
        RMS calculated channel the Calculated Channels feature would create."""
        source_registry, calc_registry = registries
        t = _time(5000.0, 1.0)
        source_registry.add(_active("src", t, {"IA": _sine(t, mod_hz=5.0, depth=0.1)}))
        result = _ready(registries)
        rms = create_calculated_channel(
            workspace_id=WS, name="RMS (IA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src", channel_name="IA")],
            parameters={"nominal_frequency_hz": 50.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        np.testing.assert_array_equal(result.derived.values, rms.values)


# ---------------------------------------------------------------- API ----

def _comtrade(fs=5000.0, f0=50.0, duration=1.0, depth=0.1, fm=5.0):
    n = int(round(fs * duration))
    cfg = ["S,D,1999", "1,1A,0D", "1,IA,A,,A,1.0,0.0,0,-999999,999999,1.0,1.0,P", "50", "1", f"{fs},{n}",
           "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0"]
    dat = []
    for i in range(n):
        ti = i / fs
        dat.append(f"{i + 1},{round(i * 1_000_000.0 / fs)},"
                   f"{100.0 * (1 + depth * math.sin(2 * math.pi * fm * ti)) * math.sin(2 * math.pi * f0 * ti):.6f}")
    return ("\r\n".join(cfg) + "\r\n").encode(), ("\r\n".join(dat) + "\r\n").encode()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _upload(client, ws, **kw):
    cfg, dat = _comtrade(**kw)
    r = client.post(f"/api/v1/workspaces/{ws}/sources", files={
        "cfg_file": ("e.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("e.dat", io.BytesIO(dat), "application/octet-stream"),
    })
    assert r.status_code == 201, r.text
    return r.json()["source_id"]


class TestApi:
    def test_representation_endpoint_describes_without_creating_a_channel(self, client):
        sid = _upload(client, "w1")
        r = client.post("/api/v1/workspaces/w1/oscillation-analysis/representation",
                        json={"input": {"kind": "source", "source_id": sid, "channel_name": "IA"}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ready"
        assert body["representation"] == "rms_magnitude"
        assert body["nominal_frequency_hz"] == 50.0
        assert body["source_sample_count"] == 5000
        assert body["derived_sample_count"] == 4900
        assert body["window_alignment"] == "trailing"
        assert body["valid_start_s"] == pytest.approx(0.02)
        assert not any(k in body for k in ("values", "time", "samples"))
        assert client.get("/api/v1/workspaces/w1/calculated-channels").json() == []

    def test_unavailable_is_a_200_with_a_reason(self, client):
        sid = _upload(client, "w2", duration=0.01)
        r = client.post("/api/v1/workspaces/w2/oscillation-analysis/representation",
                        json={"input": {"kind": "source", "source_id": sid, "channel_name": "IA"}})
        assert r.status_code == 200
        assert r.json()["status"] == "unavailable" and r.json()["reason_code"]

    def test_errors(self, client):
        sid = _upload(client, "w3")
        base = "/api/v1/workspaces/w3/oscillation-analysis/representation"
        assert client.post(base, json={"input": {"kind": "source", "source_id": "nope", "channel_name": "IA"}}).status_code == 404
        assert client.post(base, json={"input": {"kind": "source", "source_id": sid, "channel_name": "ZZ"}}).status_code == 404
        r = client.post(base, json={"input": {"kind": "source", "source_id": sid, "channel_name": "IA"},
                                    "representation": "envelope"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "unsupported_representation"
