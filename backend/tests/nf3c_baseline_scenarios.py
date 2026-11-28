"""Scenario runner for the NF-3C pre-migration characterisation baseline (closes NF-3B handover gaps G-1 and G-2).

Not a test module (no `test_` prefix). Same discipline as `nf3b_baseline_scenarios.py`: the committed outcomes were generated ONCE
from the unmodified NF-3B tree (`6794150`) before any NF-3C consumer change, and record what the code DID, defects included. They
are not engineering oracles. Where NF-3C changes a behaviour on purpose, the change is listed in `nf3c_approved_changes.py` with
its reason; everything not listed must stay exactly as frozen here.

Groups
* `compliance_measurement_http`  (G-2) the real HTTP endpoint with valid, assumed and unusable declarations: status and payload.
* `oscillation_representation_http`  the wire shape of `POST .../oscillation-analysis/representation` per recording class, so the
  schema and the origin value set can be compared before and after (client compatibility).
* `ben_import_supplied_http`  (G-1) a real BEN upload with an upload-supplied frequency, an explicit 50, and none (assumed): the NF-1
  resolution, the source summary, the oscillation representation and event detection as they behave today.
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

from tests.nf3b_baseline_scenarios import HTTP_RECORDINGS, WS, _json_or_text, _round_tree, build_comtrade

BEN_FIXTURE = Path(__file__).parent / "fixtures" / "ben" / "synthetic_fast.ben"

#: recordings of the NF-3B HTTP set plus the two unusable kinds it lacked (infinity and 0.5 Hz)
RECORDINGS = dict(HTTP_RECORDINGS) | {"declared_inf": (5000.0, 50.0, "inf"), "declared_0_5": (5000.0, 50.0, "0.5")}
QUANTITIES = ("phase_a_lg_rms", "phase_ab_ll_rms", "positive_sequence_rms")


def _upload(client, ws: str, key: str, fs: float, f_sig: float, lf: str) -> str | None:
    cfg, dat = build_comtrade(fs, f_sig, lf)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        response = client.post(f"/api/v1/workspaces/{ws}/sources", files={
            "cfg_file": (f"{key}.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": (f"{key}.dat", io.BytesIO(dat), "application/octet-stream")})
    return response.json().get("source_id") if response.status_code == 201 else None


def _snapshot(response) -> dict:
    body = _json_or_text(response) if response.status_code != 500 else "Internal Server Error"
    return {"status": response.status_code, "body": _round_tree(body) if isinstance(body, (dict, list)) else body}


def run_compliance_measurement_http(client) -> dict:
    out: dict = {}
    for key, (fs, f_sig, lf) in RECORDINGS.items():
        ws = f"{WS}-cm-{key}"
        entry: dict = {}
        sid = _upload(client, ws, key, fs, f_sig, lf)
        if sid is None:
            out[key] = {"upload": "refused"}
            continue
        groups = client.get(f"/api/v1/workspaces/{ws}/compliance/voltage/measurement-groups").json()
        entry["groups"] = [{"display_name": g["display_name"], "status": g["status"]} for g in groups]
        if groups:
            for quantity in QUANTITIES:
                entry[quantity] = _snapshot(client.get(
                    f"/api/v1/workspaces/{ws}/compliance/voltage/measurement",
                    params={"measurement_group_id": groups[-1]["id"], "quantity_id": quantity}))
        out[key] = entry
    return out


def _add_reference(client, ws: str) -> None:
    """One active phase-to-ground RMS Reference in kV (no per-unit base needed), exactly as the readiness API tests create one."""
    body = {
        "name": "Ref", "category": "grid_requirement",
        "assessment_definition": {"representation": "phase_ground_rms", "phase_treatment": "each_phase", "member": None},
        "unit": "kV", "display_start_time": 0, "display_end_time": 1, "evaluation_start_time": 0, "evaluation_end_time": 1, "tolerance": 0,
        "lower_boundary": {"segments": [{"start_time": 0, "end_time": 1, "start_value": 0.9, "end_value": 0.9, "segment_type": "constant"}]},
        "upper_boundary": None, "metadata": {},
    }
    profile = client.post(f"/api/v1/workspaces/{ws}/reference-profiles", json=body)
    client.post(f"/api/v1/workspaces/{ws}/reference-layers", json={"profile_id": profile.json()["id"], "visible": True})


def run_compliance_readiness_http(client) -> dict:
    """Readiness (read-only) and prepare (creates the shared RMS channels) per recording class: statuses, payloads, and the frequency stored
    in every channel that prepare created."""
    out: dict = {}
    for key, (fs, f_sig, lf) in RECORDINGS.items():
        ws = f"{WS}-cr-{key}"
        sid = _upload(client, ws, key, fs, f_sig, lf)
        if sid is None:
            out[key] = {"upload": "refused"}
            continue
        groups = client.get(f"/api/v1/workspaces/{ws}/compliance/voltage/measurement-groups").json()
        _add_reference(client, ws)
        entry: dict = {}
        if groups:
            gid = groups[-1]["id"]
            entry["readiness"] = _snapshot(client.get(f"/api/v1/workspaces/{ws}/compliance/voltage/readiness", params={"measurement_group_id": gid}))
            entry["prepare"] = _snapshot(client.post(f"/api/v1/workspaces/{ws}/compliance/voltage/prepare", json={"measurement_group_id": gid}))
            channels = client.get(f"/api/v1/workspaces/{ws}/calculated-channels")
            entry["created_channel_parameters"] = (
                sorted(({"operation": c["operation"], "nominal_frequency_hz": c["parameters"].get("nominal_frequency_hz")} for c in channels.json()),
                       key=lambda c: (c["operation"], str(c["nominal_frequency_hz"]))) if channels.status_code == 200 else channels.status_code)
            entry["readiness_after_prepare"] = _snapshot(client.get(
                f"/api/v1/workspaces/{ws}/compliance/voltage/readiness", params={"measurement_group_id": gid}))
        out[key] = entry
    return out


def run_oscillation_representation_http(client) -> dict:
    out: dict = {}
    for key, (fs, f_sig, lf) in RECORDINGS.items():
        ws = f"{WS}-osc-{key}"
        sid = _upload(client, ws, key, fs, f_sig, lf)
        if sid is None:
            out[key] = {"upload": "refused"}
            continue
        out[key] = _snapshot(client.post(f"/api/v1/workspaces/{ws}/oscillation-analysis/representation", json={
            "input": {"kind": "source", "source_id": sid, "channel_name": "ALPHA1_IA"}, "representation": "rms_magnitude"}))
    return out


#: BEN uploads: (label, the `nominal_frequency_hz` form value or None for "not supplied")
BEN_CASES = {"supplied_60": "60", "supplied_50_explicit": "50", "not_supplied_assumed": None}


def run_ben_import_supplied_http(client) -> dict:
    ben = BEN_FIXTURE.read_bytes()
    out: dict = {}
    for label, value in BEN_CASES.items():
        ws = f"{WS}-ben-{label}"
        response = client.post(f"/api/v1/workspaces/{ws}/sources", files={"ben_file": ("r.ben", io.BytesIO(ben), "application/octet-stream")},
                               data={} if value is None else {"nominal_frequency_hz": value})
        entry: dict = {"upload_status": response.status_code}
        if response.status_code == 201:
            sid = response.json()["source_id"]
            channels = client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/channels").json()
            name = channels["analog_channels"][0]["name"]
            entry["source_summary_nominal_frequency"] = channels["source"].get("nominal_frequency")
            entry["nominal_frequency_endpoint"] = _round_tree(
                client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency").json(),
                ("mode", "effective_hz", "usable", "origin", "auto_origin", "imported_text"))
            entry["oscillation_representation"] = _snapshot(client.post(
                f"/api/v1/workspaces/{ws}/oscillation-analysis/representation",
                json={"input": {"kind": "source", "source_id": sid, "channel_name": name}, "representation": "rms_magnitude"}))
            entry["detect_event"] = _snapshot(client.post(
                f"/api/v1/workspaces/{ws}/synchronization/detect-event", json={"source_id": sid, "channel_name": name}))
        out[label] = entry
    return out


def run_all(client) -> dict:
    return {
        "compliance_measurement_http": run_compliance_measurement_http(client),
        "compliance_readiness_http": run_compliance_readiness_http(client),
        "oscillation_representation_http": run_oscillation_representation_http(client),
        "ben_import_supplied_http": run_ben_import_supplied_http(client),
    }
