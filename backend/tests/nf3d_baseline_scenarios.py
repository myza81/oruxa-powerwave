"""Scenario runner for the NF-3D pre-migration characterisation baseline (phasor family and overcurrent).

Not a test module. Same discipline as the NF-3B/NF-3C runners: the committed outcomes were generated ONCE from the unmodified NF-3C tree
(`446b566`) before any NF-3D change and record what the code DID, defects included. They are not engineering oracles; the independent
closed-form and direct-DFT oracles are in `test_nf3d_independent_oracles.py`. Where NF-3D changes a behaviour on purpose, the change is an
explicit entry in `nf3c_approved_changes.py` (the NF-3D section) and everything else must stay exactly as frozen here.

The recording: a three-phase bay (VA/VB/VC 100 V rms balanced, IA/IB/IC) with a REPRESENTATIVE FAULT. Pre-fault load 1 A rms lagging 30 deg
(IA at 0.3 s). From 0.5 s phase A steps to 10 A rms lagging 75 deg WITH the decaying DC offset a real fault has (time constant 50 ms), so
a window just after the onset (0.52 s) contains the DC component and one later (0.8 s) is essentially settled. Sampling 5000 Hz (100
samples per 50 Hz cycle, 83.33 per 60 Hz cycle: non-integer) and 4000 Hz (80 and 66.67). A 4096 Hz ASCII file is refused as irregularly
sampled (timestamps written to 0.1 us): that existing limitation is frozen, not worked around.

Surfaces: input-readiness, phasor (voltage three-phase, current phase A), phasor diagram, overcurrent (two times), impedance, impedance locus,
sequence components, distance protection, the line-to-line readiness, and explicit-override cases (valid, unsupported by sampling, invalid).
"""

from __future__ import annotations

import io
import math
import warnings

import numpy as np

from tests.nf3b_baseline_scenarios import WS, _json_or_text, _round_tree

#: key -> (sampling rate, signal frequency, text of the COMTRADE `lf` line)
RECORDINGS = {
    "r50": (5000.0, 50.0, "50"),                          # 100 samples/cycle
    "r60": (5000.0, 60.0, "60"),                          # 83.33: non-integer
    "r50_fs4000": (4000.0, 50.0, "50"),                   # 80
    "r60_fs4000": (4000.0, 60.0, "60"),                   # 66.67: non-integer
    "r60_fs4096": (4096.0, 60.0, "60"),                   # irregular timestamps: refused before any frequency is used
    "assumed_50": (5000.0, 50.0, "abc"),
    "assumed_on_60hz_signal": (5000.0, 60.0, "abc"),
    "declared_50_on_60hz_signal": (5000.0, 60.0, "50"),
    "declared_zero": (5000.0, 50.0, "0"),
    "declared_nan": (5000.0, 50.0, "nan"),
    "declared_inf": (5000.0, 50.0, "inf"),
    "declared_negative_50": (5000.0, 50.0, "-50"),
    "declared_0_5": (5000.0, 50.0, "0.5"),
    "declared_1001": (5000.0, 50.0, "1001"),
}
CHANNELS = ("VA", "VB", "VC", "IA", "IB", "IC")
PRE_FAULT_S, FAULT_S, SETTLED_S = 0.3, 0.52, 0.8
V_RMS, I_PRE_RMS, I_FAULT_RMS = 100.0, 1.0, 10.0
PRE_FAULT_LAG_DEG, FAULT_LAG_DEG, DC_TAU_S, FAULT_ONSET_S = 30.0, 75.0, 0.05, 0.5


def fault_signals(fs: float, f: float, seconds: float = 1.0):
    """(time array, {channel: samples}) -- the exact signals written to the file and used by the oracles."""
    n = int(round(fs * seconds))
    t = np.arange(n) / fs
    w = 2.0 * np.pi * f * t
    rad = math.radians
    out = {}
    for name, shift in (("VA", 0.0), ("VB", -120.0), ("VC", 120.0)):
        out[name] = V_RMS * math.sqrt(2.0) * np.cos(w + rad(shift))
    for name, shift in (("IA", 0.0), ("IB", -120.0), ("IC", 120.0)):
        out[name] = I_PRE_RMS * math.sqrt(2.0) * np.cos(w + rad(shift) - rad(PRE_FAULT_LAG_DEG))
    after = t >= FAULT_ONSET_S
    phi = rad(FAULT_LAG_DEG)
    fault = I_FAULT_RMS * math.sqrt(2.0) * (np.cos(w - phi) - math.cos(-phi) * np.exp(-(t - FAULT_ONSET_S) / DC_TAU_S))
    out["IA"] = np.where(after, fault, out["IA"])
    return t, out


def build_comtrade(fs: float, f: float, lf_text: str, seconds: float = 1.0) -> tuple[bytes, bytes]:
    t, signals = fault_signals(fs, f, seconds)
    n = len(t)
    dt_us = 1_000_000.0 / fs
    cfg = ["NF3DSTA,NF3DDEV,1999", f"{len(CHANNELS)},{len(CHANNELS)}A,0D"]
    for k, name in enumerate(CHANNELS, start=1):
        unit = "V" if name.startswith("V") else "A"
        cfg.append(f"{k},ALPHA1_{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,S")
    cfg += [lf_text, "1", f"{fs},{n}", "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0"]
    rows = [",".join([str(r + 1), f"{r * dt_us:.1f}"] + [f"{signals[c][r]:.6f}" for c in CHANNELS]) for r in range(n)]
    return ("\n".join(cfg) + "\n").encode("ascii"), ("\n".join(rows) + "\n").encode("ascii")


def _snap(response) -> dict:
    body = _json_or_text(response) if response.status_code != 500 else "Internal Server Error"
    return {"status": response.status_code, "body": _round_tree(body) if isinstance(body, (dict, list)) else body}


def upload(client, ws: str, key: str, fs: float, f: float, lf: str) -> str | None:
    cfg, dat = build_comtrade(fs, f, lf)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = client.post(f"/api/v1/workspaces/{ws}/sources", files={
            "cfg_file": (f"{key}.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": (f"{key}.dat", io.BytesIO(dat), "application/octet-stream")})
    if r.status_code != 201:
        return None
    sid = r.json()["source_id"]
    for context in client.get(f"/api/v1/workspaces/{ws}/engineering-contexts").json():          # upload-time discovery would collide
        client.delete(f"/api/v1/workspaces/{ws}/engineering-contexts/{context['id']}")
    return sid


def context(client, ws: str, sid: str) -> str:
    members = [{"channel_ref": {"kind": "source", "source_id": sid, "channel_name": f"ALPHA1_{n}"}, "phase": n[1], "phase_source": "engineer_confirmed"}
               for n in CHANNELS]
    r = client.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "Bay 1", "status": "manual", "members": members})
    assert r.status_code == 201, r.text
    return r.json()["id"]


OVERCURRENT = {"phase": "A", "characteristic_id": "iec_standard_inverse", "tms": 0.1, "pickup_current_secondary": 1.0, "recording_basis": "secondary"}
ZONE = {"zone1_enabled": True, "zone1_reach_ohm": 10.0, "zone1_characteristic_angle_deg": 0.0, "zone1_delay_s": 0.0}


def surfaces(client, ws: str, cid: str, **extra) -> dict:
    """Every NF-3D endpoint once, with `extra` (an explicit reference_frequency_hz override or nothing)."""
    base = f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}"
    g = lambda path, **params: _snap(client.get(f"{base}/{path}", params={**params, **extra}))      # noqa: E731
    return {
        "phasor_voltage_three_phase": g("phasor", analysis_kind="phasor", mode="voltage_three_phase", analysis_time=PRE_FAULT_S),
        "phasor_current_phase_a_fault": g("phasor", analysis_kind="phasor", mode="current_phase_a", analysis_time=FAULT_S),
        "phasor_diagram_fault": g("phasor-diagram", analysis_time=FAULT_S),
        "overcurrent_pre_fault": g("overcurrent", analysis_time=PRE_FAULT_S, **OVERCURRENT),
        "overcurrent_fault": g("overcurrent", analysis_time=FAULT_S, **OVERCURRENT),
        "overcurrent_settled": g("overcurrent", analysis_time=SETTLED_S, **OVERCURRENT),
        "impedance_a": g("impedance", phase="A", analysis_time=FAULT_S, impedance_basis="secondary"),
        "impedance_locus_a": g("impedance-locus", phase="A", start_time=0.4, end_time=0.8, point_count=5, impedance_basis="secondary"),
        "sequence_components": g("sequence-components", analysis_time=FAULT_S),
        "distance_ab": g("distance-protection", loop="AB", analysis_time=FAULT_S, impedance_basis="secondary", characteristic="mho", **ZONE),
    }


def readiness(client, ws: str, cid: str) -> dict:
    base = f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}"
    out = {
        "input_readiness_phasor": _snap(client.get(f"{base}/input-readiness", params={"analysis_kind": "phasor", "mode": "voltage_three_phase"})),
        "input_readiness_overcurrent": _snap(client.get(f"{base}/input-readiness", params={"analysis_kind": "overcurrent", "mode": "current_phase_a"})),
        "line_to_line_readiness": _snap(client.get(f"/api/v1/workspaces/{ws}/calculated-channels/line-to-line-voltage/readiness")),
    }
    return out


def run_recordings(client) -> dict:
    out: dict = {}
    for key, (fs, f, lf) in RECORDINGS.items():
        ws = f"{WS}-d-{key}"
        sid = upload(client, ws, key, fs, f, lf)
        if sid is None:
            out[key] = {"upload": "refused"}
            continue
        cid = context(client, ws, sid)
        entry = {"nominal_frequency_endpoint": _round_tree(client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency").json(),
                                                           ("mode", "effective_hz", "usable", "origin"))}
        entry |= readiness(client, ws, cid)
        entry |= surfaces(client, ws, cid)
        out[key] = entry
    return out


#: explicit `reference_frequency_hz` override cases, on a 50 Hz recording at 5 kHz: valid and equal, valid and different (a 60 Hz window on a
#: 50 Hz signal), valid but unsupported by the sampling (1000 Hz gives 5 samples per cycle), and invalid values. An override has always won
#: over the recording's declaration; these freeze that, including on an unusable recording.
OVERRIDES = {
    "r50": ("r50", {"reference_frequency_hz": 50.0}),
    "r50_override_60": ("r50", {"reference_frequency_hz": 60.0}),
    "r50_override_1000_unsupported_by_sampling": ("r50", {"reference_frequency_hz": 1000.0}),
    "r50_override_zero": ("r50", {"reference_frequency_hz": 0.0}),
    "r50_override_negative": ("r50", {"reference_frequency_hz": -50.0}),
    "r50_override_1001": ("r50", {"reference_frequency_hz": 1001.0}),
    "declared_zero_with_override_50": ("declared_zero", {"reference_frequency_hz": 50.0}),
    "declared_nan_with_override_50": ("declared_nan", {"reference_frequency_hz": 50.0}),
}


def run_overrides(client) -> dict:
    out: dict = {}
    for label, (key, extra) in OVERRIDES.items():
        fs, f, lf = RECORDINGS[key]
        ws = f"{WS}-o-{label}"
        sid = upload(client, ws, key, fs, f, lf)
        cid = context(client, ws, sid)
        out[label] = surfaces(client, ws, cid, **extra)
    return out


def run_two_recordings(client) -> dict:
    """Voltage from one recording and current from another (a context may span recordings): agreeing, differing and one unusable."""
    out: dict = {}
    for label, (a, b) in {"agree_50_50": ("r50", "r50"), "differ_50_60": ("r50", "r60"), "one_unusable": ("r50", "declared_zero"),
                          "assumed_with_declared_50": ("assumed_50", "r50")}.items():
        ws = f"{WS}-m-{label}"
        sids = {}
        for role, key in (("V", a), ("I", b)):
            fs, f, lf = RECORDINGS[key]
            sids[role] = upload(client, ws, f"{key}-{role}", fs, f, lf)
        members = [{"channel_ref": {"kind": "source", "source_id": sids["V" if n.startswith("V") else "I"], "channel_name": f"ALPHA1_{n}"},
                    "phase": n[1], "phase_source": "engineer_confirmed"} for n in CHANNELS]
        r = client.post(f"/api/v1/workspaces/{ws}/engineering-contexts", json={"display_name": "Bay 1", "status": "manual", "members": members})
        if r.status_code != 201:
            out[label] = {"context": _snap(r)}
            continue
        cid = r.json()["id"]
        base = f"/api/v1/workspaces/{ws}/engineering-contexts/{cid}"
        out[label] = {
            "phasor_voltage_three_phase": _snap(client.get(f"{base}/phasor", params={"analysis_kind": "phasor", "mode": "voltage_three_phase", "analysis_time": PRE_FAULT_S})),
            "phasor_diagram_fault": _snap(client.get(f"{base}/phasor-diagram", params={"analysis_time": FAULT_S})),
            "overcurrent_fault": _snap(client.get(f"{base}/overcurrent", params={"analysis_time": FAULT_S, **OVERCURRENT})),
            "sequence_components": _snap(client.get(f"{base}/sequence-components", params={"analysis_time": FAULT_S})),
        }
    return out


def run_all(client) -> dict:
    return {"recordings": run_recordings(client), "overrides": run_overrides(client), "two_recordings": run_two_recordings(client)}
