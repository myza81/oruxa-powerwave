"""Scenario runner for the frozen nominal-frequency consumer baseline (NF-3B).

Not a test module (no `test_` prefix, same convention as `rms_baseline_scenarios.py` and `comtrade_frequency_scenarios.py`).
Two callers share it so the scenarios can never drift apart:

* `tests/fixtures/nf3b_baselines/generate_nf3b_baselines.py` runs every scenario ONCE and freezes the outcome in
  `tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json`. The committed file was generated against the PRISTINE NF-3A
  production tree (`c70182c`), before NF-3B changed anything.
* `tests/test_nf3b_frozen_baselines.py` re-runs the same scenarios against the code under test.

What this freezes is CURRENT BEHAVIOUR, defects included. It is a characterisation baseline, never an engineering oracle:
the values here are what the code did on that day, not what is correct (the correct values are the independent
closed-form oracles in `test_nf3b_independent_oracles.py`). Where the two differ, the baseline records the existing defect
(for example a 60 Hz recording's power channel computed with a 50 Hz window) so a later migration slice can show exactly what
it changed.

Groups: (K) engine kernels on exactly known signals, (I) in-process service consumers, (H) the HTTP consumers on real
uploaded recordings, (O) oscillation multi-recording frequency selection. The RMS service/eligibility/creation behaviour
(including the eligibility HTTP 500) is already frozen by the R0 baseline (`rms_golden/service_behaviour_baseline.json`) and the
COMTRADE importer behaviour by the R1A baseline; neither is repeated here.
"""

from __future__ import annotations

import dataclasses
import io
import math
import re
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tests.nf3c_access_support import access_for
from app.domain.calculated_channel import (
    OP_ACTIVE_POWER, OP_APPARENT_POWER, OP_REACTIVE_POWER, ChannelRef, evaluate_power_channel,
    evaluate_rms, evaluate_three_phase_power_channel,
)
from app.domain.channel_classification import WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.event_detection import detect_event_onset
from app.domain.metadata import RecordingMetadata
from app.domain.overcurrent import estimate_trailing_rms_at_time
from app.domain.phasor import estimate_phasor
from app.domain.rms_detector import classify_waveform_form
from app.domain.sliding_phasor import compute_sliding_phasor
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation

WS = "ws-nf3b"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
AMP = 100.0
EXPECTED_RMS = AMP / math.sqrt(2.0)

#: What an invalid or out-of-range recording-level value looks like to an engine function.
INVALID_NOMINAL = (0.0, -50.0, float("nan"), float("inf"), float("-inf"), 0.5, 1001.0)
#: (sampling rate, signal frequency, nominal frequency): integer and NON-integer samples per cycle.
#: 4096 Hz gives 81.92 (50 Hz) and 68.27 (60 Hz) samples per cycle; 4800 Hz gives 96 and 80.
KERNEL_GRID = tuple((fs, f_sig, f_nom) for fs in (4800.0, 4096.0) for f_sig in (50.0, 60.0) for f_nom in (50.0, 60.0))


# ------------------------------------------------------------------------------------------------ normalisation
def num(value) -> float | str | None:
    """12 significant digits (a different libm cannot change the frozen file); non-finite values as text."""
    if value is None:
        return None
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return float(f"{value:.12g}")


def stats(array, mask=None) -> dict:
    a = np.asarray(array, dtype=np.float64)
    if mask is not None:
        a = a[mask]
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return {"count": int(a.size), "finite": 0, "mean": None, "min": None, "max": None}
    return {"count": int(a.size), "finite": int(finite.size), "mean": num(finite.mean()), "min": num(finite.min()), "max": num(finite.max())}


def outcome(fn) -> dict:
    """What a call did: its summary, or the exception CLASS (never the message text, which is not part of the contract)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return {"returns": fn()}
    except Exception as exc:                                              # noqa: BLE001 - the baseline records any failure
        return {"raises": type(exc).__name__}


def _tag(value: float) -> str:
    return "nan" if math.isnan(value) else repr(float(value))


def signal(f_sig: float, fs: float, seconds: float, phase_deg: float = 0.0, amp: float = AMP):
    n = int(round(fs * seconds)) + 1
    t = np.arange(n) / fs
    return t, amp * np.cos(2 * np.pi * f_sig * t + math.radians(phase_deg))


def steady(t: np.ndarray, f_nom: float, cycles: float = 2.0) -> np.ndarray:
    return t >= cycles / f_nom + 1e-9


# ------------------------------------------------------------------------------------------------ (K) engine kernels
def _rms_summary(t, x, f_nom):
    out = evaluate_rms(t, x, f_nom)
    return stats(out, steady(t, f_nom) & np.isfinite(out)) | {"nan_count": int(np.isnan(out).sum())}


def _sliding_summary(t, x, f_nom):
    res = compute_sliding_phasor(t, x, f_nom)
    m = res.available
    mag = np.abs(res.phasor[m])
    ang = np.degrees(np.angle(res.phasor[m]))
    return {"available": int(m.sum()), "magnitude": stats(mag), "angle_deg": stats(ang)}


def _point_summary(t, x, f_nom):
    est = estimate_phasor(t, x, 0.3, f_nom)
    return {"available": est.available, "magnitude_rms": num(est.magnitude_rms), "angle_deg": num(est.angle_deg),
            "reason_code": est.reason_code, "sample_count": est.sample_count}


def _overcurrent_summary(t, x, f_nom):
    est = estimate_trailing_rms_at_time(t, x, 0.3, f_nom)
    return {"available": est.available, "value": num(est.value), "reason_code": est.reason_code, "sample_count": est.sample_count}


def _detector_summary(t, x, f_nom):
    return classify_waveform_form(t, x, f_nom)


def _step_signal(f_sig: float, fs: float):
    """A 1 s record whose amplitude doubles at 0.5 s: the detector has a real change to find."""
    n = int(round(fs * 1.0)) + 1
    t = np.arange(n) / fs
    amp = np.where(t < 0.5, AMP, 2.0 * AMP)
    return t, amp * np.cos(2 * np.pi * f_sig * t)


def _event_summary(t, x, f_nom):
    r = detect_event_onset(t, x, nominal_frequency_hz=f_nom)
    return {"found": r.found, "reason": r.reason, "candidate_source_time": num(r.candidate_source_time),
            "baseline_rms": num(r.baseline_rms), "changed_rms": num(r.changed_rms), "quality": r.quality}


def _power_summary(op, t, v, i, f_nom):
    kwargs = {} if f_nom is None else {"nominal_frequency_hz": f_nom}
    out = evaluate_power_channel(op, t, v, 1.0, i, 1.0, **kwargs)
    ok = np.isfinite(out)
    return stats(out, ok & (t >= 0.1))


def _three_phase_summary(op, t, v, i, f_nom):
    kwargs = {} if f_nom is None else {"nominal_frequency_hz": f_nom}
    shifted = [np.interp(t - k / 3.0 / 50.0, t, v, left=0.0) for k in (0, 1, 2)]       # fixed shape; frequency-independent
    ishift = [np.interp(t - k / 3.0 / 50.0, t, i, left=0.0) for k in (0, 1, 2)]
    out = evaluate_three_phase_power_channel(
        op, t, shifted[0], 1.0, ishift[0], 1.0, shifted[1], 1.0, ishift[1], 1.0, shifted[2], 1.0, ishift[2], 1.0, **kwargs)
    return stats(out, np.isfinite(out) & (t >= 0.1))


def run_kernel_scenarios() -> dict:
    out: dict = {"grid": {}, "power": {}, "invalid": {}}
    for fs, f_sig, f_nom in KERNEL_GRID:
        key = f"fs{int(fs)}_signal{int(f_sig)}_nominal{int(f_nom)}"
        t, x = signal(f_sig, fs, 0.5, 30.0)
        ts, xs = _step_signal(f_sig, fs)
        out["grid"][key] = {
            "samples_per_cycle_at_nominal": num(fs / f_nom),
            "rms_trailing": outcome(lambda: _rms_summary(t, x, f_nom)),
            "sliding_phasor": outcome(lambda: _sliding_summary(t, x, f_nom)),
            "phasor_point": outcome(lambda: _point_summary(t, x, f_nom)),
            "overcurrent_rms_point": outcome(lambda: _overcurrent_summary(t, x, f_nom)),
            "waveform_form_detector": outcome(lambda: _detector_summary(t, x, f_nom)),
            "event_onset_detector": outcome(lambda: _event_summary(ts, xs, f_nom)),
        }
    # Power (V 100 kV pk, I 1 kA pk, current lagging 30 degrees). `default` = the window the production service uses today,
    # which is the domain default of 50 Hz because the service passes no frequency (NF-3A defect D-A).
    for fs in (4800.0, 4096.0):
        for f_sig in (50.0, 60.0):
            t, v = signal(f_sig, fs, 0.5, 0.0, 100e3)
            _, i = signal(f_sig, fs, 0.5, -30.0, 1e3)
            for window in (None, 50.0, 60.0):
                key = f"fs{int(fs)}_signal{int(f_sig)}_window{'default' if window is None else int(window)}"
                out["power"][key] = {
                    "single_phase": {op: outcome(lambda op=op: _power_summary(op, t, v, i, window))
                                     for op in (OP_ACTIVE_POWER, OP_REACTIVE_POWER, OP_APPARENT_POWER)},
                    "three_phase_active": outcome(lambda: _three_phase_summary(OP_ACTIVE_POWER, t, v, i, window)),
                }
    # Invalid and unavailable nominal frequencies handed to the raw engine functions.
    t, x = signal(50.0, 4800.0, 0.5, 30.0)
    ts, xs = _step_signal(50.0, 4800.0)
    _, i = signal(50.0, 4800.0, 0.5, -30.0)
    for bad in INVALID_NOMINAL:
        out["invalid"][_tag(bad)] = {
            "rms_trailing": outcome(lambda: _rms_summary(t, x, bad)),
            "sliding_phasor": outcome(lambda: _sliding_summary(t, x, bad)),
            "phasor_point": outcome(lambda: _point_summary(t, x, bad)),
            "overcurrent_rms_point": outcome(lambda: _overcurrent_summary(t, x, bad)),
            "waveform_form_detector": outcome(lambda: _detector_summary(t, x, bad)),
            "event_onset_detector": outcome(lambda: _event_summary(ts, xs, bad)),
            "power_active": outcome(lambda: _power_summary(OP_ACTIVE_POWER, t, x, i, bad)),
        }
    return out


# ------------------------------------------------------------------------------------------------ (I) in-process consumers
#: key -> (declared nominal frequency, preparation provenance, signal frequency)
RECORDING_SPECS = {
    "declared_50": (50.0, {"source_format": "COMTRADE"}, 50.0),
    "declared_60": (60.0, {"source_format": "COMTRADE"}, 60.0),
    "assumed_50": (50.0, {"source_format": "COMTRADE", "nominal_frequency_assumed": True}, 50.0),
    "assumed_default_on_60hz_signal": (50.0, {"source_format": "COMTRADE", "nominal_frequency_assumed": True}, 60.0),
    "declared_50_on_60hz_signal": (50.0, {"source_format": "COMTRADE"}, 60.0),
    "declared_zero": (0.0, {"source_format": "COMTRADE"}, 50.0),
    "declared_negative_50": (-50.0, {"source_format": "COMTRADE"}, 50.0),
    "declared_nan": (float("nan"), {"source_format": "COMTRADE"}, 50.0),
    "declared_inf": (float("inf"), {"source_format": "COMTRADE"}, 50.0),
    "declared_1001": (1001.0, {"source_format": "COMTRADE"}, 50.0),
    "declared_0_5": (0.5, {"source_format": "COMTRADE"}, 50.0),
}


def build_source(source_id: str, nominal, provenance, f_sig: float, *, fs: float = 4800.0, seconds: float = 1.0,
                 with_voltage: bool = True) -> ActiveSource:
    """An in-memory recording: a voltage and a current (current lagging 30 degrees) at `f_sig`, declared `nominal`."""
    t = np.arange(int(round(fs * seconds)) + 1) / fs
    channels = {"VA": 100e3 * np.cos(2 * np.pi * f_sig * t), "IA": 1e3 * np.cos(2 * np.pi * f_sig * t - math.radians(30.0))}
    if not with_voltage:
        channels.pop("VA")
    record = DisturbanceRecord(
        metadata=RecordingMetadata(station_name="S", recorder_name="R", source_file="s.cfg", provider_type="COMTRADE",
                                   nominal_frequency=nominal),
        waveform_data=pd.DataFrame({"time": t, **channels}), analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(t)]),
        timing_info=TimingInformation(start_time=START, trigger_time=START),
    )
    units = {"VA": "V", "IA": "A"}
    types = {"VA": "Voltage", "IA": "Current"}
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE", original_filenames=("s.cfg", "s.dat"), created_at=START,
        station_name="S", recorder_name="R", nominal_frequency=nominal, timing_reference="absolute", start_time=START,
        trigger_time=START, sample_count=len(t), duration_seconds=float(t[-1] - t[0]), elapsed_start_seconds=float(t[0]),
        elapsed_end_seconds=float(t[-1]), sampling_rates=(1.0,), samples_per_rate=(len(t),),
        analog_channels=[AnalogChannelSummary(name=n, index=k, unit=units[n], engineering_type=types[n],
                                              waveform_form=WAVEFORM_FORM_UNKNOWN) for k, n in enumerate(channels)],
        digital_channels=[], preparation_provenance=dict(provenance),
    )
    return ActiveSource(metadata=metadata, record=record)


def _service_failure(exc: BaseException) -> dict:
    return {"raises": type(exc).__name__, "code": getattr(exc, "code", None)}


def run_inprocess_scenarios() -> dict:
    from app.services.calculated_channel_registry import CalculatedChannelRegistry
    from app.services.calculated_channel_service import create_calculated_channel
    from app.services.compliance_measurement_service import _classify_input_type
    from app.services.compliance_readiness_service import _nominal_frequency_for
    from app.services.oscillation_representation_service import derive_analysis_representation
    from app.services.synchronization_registry import SynchronizationRegistry
    from app.services.synchronization_service import detect_event_candidate
    from app.services.nominal_frequency_access import NominalFrequencyAccess
    from app.services.nominal_frequency_registry import NominalFrequencyRegistry
    from app.services.workspace_registry import WorkspaceRegistry

    out: dict = {}
    for key, (nominal, provenance, f_sig) in RECORDING_SPECS.items():
        sources, calcs = WorkspaceRegistry(), CalculatedChannelRegistry()
        sources.add(build_source("src", nominal, provenance, f_sig))
        v_ref = ChannelRef(kind="source", source_id="src", channel_name="VA")
        i_ref = ChannelRef(kind="source", source_id="src", channel_name="IA")
        entry: dict = {}

        # C-04 compliance readiness: the declared value, validated or None
        # NF-3C: the consumers ask the central accessor (gate closed: Auto only); the recorded representation is unchanged.
        access = NominalFrequencyAccess(sources, NominalFrequencyRegistry(), manual_override_enabled=False)
        nominal_for = _nominal_frequency_for(i_ref, workspace_id=WS, frequency_access=access, calc_registry=calcs)
        entry["compliance_readiness_nominal_for"] = num(nominal_for.hz if nominal_for is not None and nominal_for.usable else None)
        # C-05 compliance measurement: the form classification of an unlabelled channel
        entry["compliance_measurement_input_type"] = outcome(lambda: _classify_input_type(
            i_ref, workspace_id=WS, source_registry=sources, frequency_access=access))

        # C-06 oscillation representation: value, origin label and verdict
        def representation():
            r = derive_analysis_representation(
                workspace_id=WS, input_ref=i_ref, representation="rms_magnitude", source_registry=sources, frequency_access=access_for(sources), calc_registry=calcs)
            return {"status": r.status, "reason_code": r.reason_code, "nominal_frequency_hz": num(r.nominal_frequency_hz),
                    "nominal_frequency_origin": r.nominal_frequency_origin}
        entry["oscillation_representation"] = outcome(representation)

        # C-03 event-onset detection through the service view (echoes the declared value)
        def detection():
            v = detect_event_candidate(workspace_id=WS, source_id="src", channel_name="IA", sensitivity="normal",
                                       search_start_time=None, search_end_time=None, source_registry=sources,
                                       synchronization_registry=SynchronizationRegistry(), frequency_access=access)
            return {"found": v.found, "reason": v.reason, "nominal_frequency_hz": num(v.nominal_frequency_hz),
                    "candidate_source_time": num(v.candidate_source_time)}
        entry["event_detection_view"] = outcome(detection)

        # C-11 to C-13 power channels: what the service creates, with the value it stores and how it behaves
        for op in (OP_ACTIVE_POWER, OP_REACTIVE_POWER):
            def power(op=op):
                try:
                    channel = create_calculated_channel(
                        workspace_id=WS, name=f"{op}-{key}", operation=op, inputs=[v_ref, i_ref], parameters={},
                        source_registry=sources, calc_registry=calcs)
                except Exception as exc:                                  # noqa: BLE001
                    return _service_failure(exc)
                values = np.asarray(channel.values, dtype=np.float64)
                t = np.asarray(channel.time, dtype=np.float64)
                return {"unit": channel.unit, "parameters": _plain(channel.parameters),
                        "values": stats(values, np.isfinite(values) & (t >= 0.1))}
            entry[f"power_channel_{op}"] = outcome(power)
        out[key] = entry
    return out


def _plain(obj):
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, float):
        return num(obj)
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return repr(obj)


# ------------------------------------------------------------------------------------------------ (H) HTTP consumers
#: key -> (sampling rate, signal frequency, the text written on the COMTRADE `lf` line). 5000 Hz has an exact 200 us period in the
#: ASCII file (a 60 Hz cycle is 83.33 samples); 4096 Hz does not (244.140625 us is written as 244.1), so the existing
#: `irregular_sampling_not_supported` refusal is frozen for it rather than a number.
HTTP_RECORDINGS = {
    "r50": (5000.0, 50.0, "50"),
    "r60": (5000.0, 60.0, "60"),
    "r50_fs4096": (4096.0, 50.0, "50"),
    "r60_fs4096": (4096.0, 60.0, "60"),
    "assumed_50": (5000.0, 50.0, "abc"),
    "assumed_on_60hz_signal": (5000.0, 60.0, "abc"),
    "declared_50_on_60hz_signal": (5000.0, 60.0, "50"),
    "declared_zero": (5000.0, 50.0, "0"),
    "declared_negative_50": (5000.0, 50.0, "-50"),
    "declared_nan": (5000.0, 50.0, "nan"),
    "declared_1001": (5000.0, 50.0, "1001"),
}

_HTTP_CHANNELS = (("ALPHA1_VA", "V", 0.0), ("ALPHA1_VB", "V", -120.0), ("ALPHA1_VC", "V", 120.0), ("ALPHA1_IA", "A", -30.0))


def build_comtrade(fs: float, f_sig: float, lf_text: str, seconds: float = 1.0) -> tuple[bytes, bytes]:
    n = int(round(fs * seconds))
    dt_us = 1_000_000.0 / fs
    cfg = ["NF3BSTA,NF3BDEV,1999", f"{len(_HTTP_CHANNELS)},{len(_HTTP_CHANNELS)}A,0D"]
    for k, (name, unit, _p) in enumerate(_HTTP_CHANNELS, start=1):
        cfg.append(f"{k},{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,S")
    cfg += [lf_text, "1", f"{fs},{n}", "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0"]
    t = np.arange(n) / fs
    amp = {"V": 100.0 * math.sqrt(2.0), "A": 10.0 * math.sqrt(2.0)}
    values = [amp[unit] * np.cos(2.0 * np.pi * f_sig * t + math.radians(p)) for _n, unit, p in _HTTP_CHANNELS]
    rows = [",".join([str(r + 1), f"{r * dt_us:.1f}"] + [f"{values[c][r]:.6f}" for c in range(len(values))]) for r in range(n)]
    return ("\n".join(cfg) + "\n").encode("ascii"), ("\n".join(rows) + "\n").encode("ascii")


def _json_or_text(response):
    try:
        return response.json()
    except ValueError:
        return response.text


_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32}")


def _round_tree(obj, keep: tuple[str, ...] | None = None):
    if isinstance(obj, dict):
        return {k: _round_tree(v) for k, v in sorted(obj.items()) if keep is None or k in keep}
    if isinstance(obj, list):
        return [_round_tree(v) for v in obj]
    if isinstance(obj, float):
        return num(obj)
    if isinstance(obj, str):
        return _ID.sub("<id>", obj)               # generated identifiers differ per run and are not behaviour
    return obj


def run_http_scenarios(client) -> dict:
    base = f"/api/v1/workspaces/{WS}"
    out: dict = {}
    for key, (fs, f_sig, lf_text) in HTTP_RECORDINGS.items():
        cfg, dat = build_comtrade(fs, f_sig, lf_text)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            up = client.post(f"{base}/sources", files={"cfg_file": (f"{key}.cfg", io.BytesIO(cfg), "application/octet-stream"),
                                                       "dat_file": (f"{key}.dat", io.BytesIO(dat), "application/octet-stream")})
        entry: dict = {"upload_status": up.status_code}
        if up.status_code != 201:
            out[key] = entry
            continue
        sid = up.json()["source_id"]
        for context in client.get(f"{base}/engineering-contexts").json():          # discovery would collide with ours
            client.delete(f"{base}/engineering-contexts/{context['id']}")

        entry["nominal_frequency_endpoint"] = _round_tree(client.get(f"{base}/sources/{sid}/nominal-frequency").json(),
                                                          ("mode", "effective_hz", "usable", "origin", "imported_text", "auto_origin"))
        ch = client.get(f"{base}/sources/{sid}/channels")
        entry["source_summary_nominal_frequency"] = (
            _round_tree(ch.json().get("source", {}).get("nominal_frequency")) if ch.status_code == 200 else ch.status_code)

        det = client.post(f"{base}/synchronization/detect-event", json={"source_id": sid, "channel_name": "ALPHA1_VA"})
        entry["detect_event"] = {"status": det.status_code, "body": _round_tree(_json_or_text(det) if det.status_code != 500 else "500",
                                                                                 None)}

        def ref(name):
            return {"kind": "source", "source_id": sid, "channel_name": name}

        ctx = client.post(f"{base}/engineering-contexts", json={"display_name": "Alpha 1", "status": "manual", "members": [
            {"channel_ref": ref("ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": ref("ALPHA1_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": ref("ALPHA1_VC"), "phase": "C", "phase_source": "engineer_confirmed"},
            {"channel_ref": ref("ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}]})
        entry["context_status"] = ctx.status_code
        if ctx.status_code == 201:
            cid = ctx.json()["id"]
            ph = client.get(f"{base}/engineering-contexts/{cid}/phasor",
                            params={"analysis_kind": "phasor", "mode": "voltage_three_phase", "analysis_time": 0.5})
            body = _json_or_text(ph) if ph.status_code != 500 else "500"
            entry["phasor_voltage_three_phase"] = {"status": ph.status_code, "body": _round_tree(body, None) if isinstance(body, dict) else body}
            oc = client.get(f"{base}/engineering-contexts/{cid}/overcurrent", params={
                "phase": "A", "analysis_time": 0.5, "characteristic_id": "iec_standard_inverse", "tms": 0.1,
                "pickup_current_secondary": 1.0, "recording_basis": "secondary"})
            body = _json_or_text(oc) if oc.status_code != 500 else "500"
            entry["overcurrent_phase_a"] = {"status": oc.status_code, "body": _round_tree(body, None) if isinstance(body, dict) else body}
        entry["power_channels"] = {}
        for op in (OP_ACTIVE_POWER, OP_REACTIVE_POWER):
            response = client.post(f"{base}/calculated-channels", json={
                "operation": op, "name": f"{op}-{key}", "inputs": [ref("ALPHA1_VA"), ref("ALPHA1_IA")], "parameters": {}})
            record = {"status": response.status_code}
            body = _json_or_text(response) if response.status_code != 500 else "500"
            if response.status_code == 201:
                channel = client.app.state.calculated_channel_registry.get(WS, body["id"])
                values = np.asarray(channel.values, dtype=np.float64)
                t = np.asarray(channel.time, dtype=np.float64)
                record |= {"parameters": _plain(channel.parameters), "unit": channel.unit,
                           "values": stats(values, np.isfinite(values) & (t >= 0.1))}
            else:
                record["error"] = body if isinstance(body, str) else _round_tree(body.get("detail"))
            entry["power_channels"][op] = record
        out[key] = entry
    return out


# ------------------------------------------------------------------------------------------------ (O) oscillation selection
def run_oscillation_selection_scenarios() -> dict:
    """Multi-recording frequency selection in `classify_component` (NF-3A C-08 / defect D-D): the frequency used for the
    sub-synchronous comparison is the FIRST member's value (else the 50 Hz constant), so the verdict depends on member order."""
    from tests.test_oscillation_classification import _interpret, _sig

    def one(members, frequency):
        signals = [_sig(i, f"S{i}", frequency, signal_type="Voltage", recording=f"r{i}", nominal=nom, nominal_assumed=assumed)
                   for i, (nom, assumed) in enumerate(members)]
        result = _interpret(signals)
        if len(result) != 1:
            return {"components": len(result)}
        r = result[0]
        codes = lambda items: sorted(i["code"] for i in items)           # noqa: E731
        return {
            "probable_type": (r.get("probable_type") or {}).get("code"),
            "descriptors": codes(r.get("descriptors", [])),
            "supporting": codes(r.get("supporting_evidence", [])),
            "limiting": codes(r.get("limiting_evidence", [])),
            "nominal_values_in_evidence": sorted({
                str(num(e.get("values", {}).get("nominal_frequency_hz"))) for k in ("supporting_evidence", "limiting_evidence", "descriptors")
                for e in r.get(k, []) if e.get("values", {}).get("nominal_frequency_hz") is not None}),
        }

    cases = {
        "all_50": [(50.0, False), (50.0, False)],
        "all_60": [(60.0, False), (60.0, False)],
        "first_50_second_60": [(50.0, False), (60.0, False)],
        "first_60_second_50": [(60.0, False), (50.0, False)],
        "first_missing_second_60": [(None, False), (60.0, False)],
        "none_declared": [(None, False), (None, False)],
        "one_assumed_flag": [(50.0, True), (50.0, False)],
        "first_assumed_second_manual_like_60": [(50.0, True), (60.0, False)],
    }
    out = {}
    for frequency in (45.0, 55.0, 4.0):                       # below both, between 50 and 60, a low electromechanical value
        out[f"component_{frequency:g}hz"] = {name: outcome(lambda m=m: one(m, frequency)) for name, m in cases.items()}
    return out


# ------------------------------------------------------------------------------------------------ (P) power prerequisite gates
#: (sampling rate, duration): chosen around the two thresholds the power channels' prerequisite gates apply with a hard-coded
#: 50 Hz (NF-3A C-11): a recording must span MORE than one window (1/f) and give at least 4 samples per window. At 50 Hz that is
#: duration > 0.02 s and a rate of at least 200 Hz; at 60 Hz it would be 0.01667 s and 240 Hz. A gate quietly moved to 60 Hz (or
#: to the recording's own frequency) flips exactly the cases between the two thresholds.
POWER_GATE_CASES = {
    "short_0_018s_between_the_60hz_and_50hz_window": (5000.0, 0.018),
    "short_0_0150s_shorter_than_both_windows": (5000.0, 0.015),
    "long_0_0215s_longer_than_both": (5000.0, 0.0215),
    "sparse_220hz_between_the_50hz_and_60hz_density": (220.0, 0.5),
    "sparse_190hz_below_both": (190.0, 0.5),
    "dense_5khz": (5000.0, 0.5),
}


def run_power_gate_scenarios() -> dict:
    from app.services.calculated_channel_registry import CalculatedChannelRegistry
    from app.services.calculated_channel_service import create_calculated_channel
    from app.services.workspace_registry import WorkspaceRegistry

    out: dict = {}
    for name, (fs, seconds) in POWER_GATE_CASES.items():
        out[name] = {}
        for nominal, f_sig in ((50.0, 50.0), (60.0, 60.0)):
            sources, calcs = WorkspaceRegistry(), CalculatedChannelRegistry()
            sources.add(build_source("src", nominal, {"source_format": "COMTRADE"}, f_sig, fs=fs, seconds=seconds))

            def create():
                try:
                    channel = create_calculated_channel(
                        workspace_id=WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
                        inputs=[ChannelRef(kind="source", source_id="src", channel_name="VA"), ChannelRef(kind="source", source_id="src", channel_name="IA")])
                except Exception as exc:                                  # noqa: BLE001
                    return _service_failure(exc)
                values = np.asarray(channel.values, dtype=np.float64)
                return {"created": True, "parameters": _plain(channel.parameters), "finite_samples": int(np.isfinite(values).sum())}
            out[name][f"recording_{int(nominal)}hz"] = outcome(create)
    return out


def run_all(client) -> dict:
    return {
        "kernels": run_kernel_scenarios(),
        "in_process": run_inprocess_scenarios(),
        "http": run_http_scenarios(client),
        "oscillation_selection": run_oscillation_selection_scenarios(),
        "power_gate": run_power_gate_scenarios(),
    }
