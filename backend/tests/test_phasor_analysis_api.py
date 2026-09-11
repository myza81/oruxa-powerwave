"""API-level tests for the Phasor Analysis Slice 1 read-only, selected-
time endpoint (`GET .../engineering-contexts/{id}/phasor`). Exercises
the real FastAPI app end-to-end, including a real ASCII-COMTRADE upload
carrying a known, hand-computed three-phase sinusoid -- see
test_phasor_analysis_service.py for the already-proven service-layer
behaviour (multi-source/frequency-conflict/waveform-form matrix) this
router only exposes.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _build_ascii_comtrade(
    *, station: str, channels: list[tuple[str, str, float, float]], sample_rate_hz: float, duration_s: float,
    nominal_frequency_hz: float = 50.0,
) -> tuple[bytes, bytes]:
    """Builds a minimal, hand-written ASCII COMTRADE cfg/dat pair
    carrying a real, known sinusoid -- `channels` is `(name, unit,
    amp_peak, phase_deg)`. `a=1.0, b=0.0` for every channel, so the
    written raw sample values ARE the engineering values directly (no
    scale/offset indirection to account for)."""
    n = int(round(duration_s * sample_rate_hz))
    dt_us = 1_000_000.0 / sample_rate_hz
    lines_cfg = [f"{station},PHASOR_DEV,1999", f"{len(channels)},{len(channels)}A,0D"]
    for i, (name, unit, _amp, _phase) in enumerate(channels, start=1):
        lines_cfg.append(f"{i},{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,P")
    lines_cfg.append(str(nominal_frequency_hz))
    lines_cfg.append("1")
    lines_cfg.append(f"{sample_rate_hz},{n}")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("ASCII")
    lines_cfg.append("1.0")
    cfg_text = "\n".join(lines_cfg) + "\n"

    t = np.arange(n) / sample_rate_hz
    values = [
        amp * np.cos(2.0 * np.pi * nominal_frequency_hz * t + np.radians(phase_deg))
        for _name, _unit, amp, phase_deg in channels
    ]
    lines_dat = []
    for row in range(n):
        parts = [str(row + 1), f"{row * dt_us:.1f}"] + [f"{values[c][row]:.6f}" for c in range(len(channels))]
        lines_dat.append(",".join(parts))
    dat_text = "\n".join(lines_dat) + "\n"
    return cfg_text.encode("ascii"), dat_text.encode("ascii")


def _upload_sine_source(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="phasor_ascii"):
    cfg, dat = _build_ascii_comtrade(
        station="PHASORSTA", channels=channels, sample_rate_hz=sample_rate_hz, duration_s=duration_s,
        nominal_frequency_hz=nominal_frequency_hz,
    )
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/engineering-contexts"


def _ref(source_id, name):
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _create_context(client, workspace_id, members, display_name="Alpha 1"):
    resp = client.post(_contexts_url(workspace_id), json={"display_name": display_name, "status": "manual", "members": members})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _phasor(client, workspace_id, context_id, *, analysis_kind, mode, analysis_time, reference_frequency_hz=None):
    params = {"analysis_kind": analysis_kind, "mode": mode, "analysis_time": analysis_time}
    if reference_frequency_hz is not None:
        params["reference_frequency_hz"] = reference_frequency_hz
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/phasor", params=params)


class TestComputedThroughRealUpload:
    def test_balanced_three_phase_voltage_via_http(self, client):
        source_id = _upload_sine_source(
            client, "ws-1",
            channels=[("ALPHA1_VA", "V", 100.0 * math.sqrt(2), 0.0), ("ALPHA1_VB", "V", 100.0 * math.sqrt(2), -120.0), ("ALPHA1_VC", "V", 100.0 * math.sqrt(2), 120.0)],
        )
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_VC"), "phase": "C", "phase_source": "engineer_confirmed"},
        ])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="phasor", mode="voltage_three_phase", analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["algorithm_version"] == "phasor_estimator_v1"
        assert body["reference_frequency_hz"] == pytest.approx(50.0)
        assert body["window_seconds"] == pytest.approx(0.02)
        va, vb, vc = body["roles"]["Va"], body["roles"]["Vb"], body["roles"]["Vc"]
        assert va["magnitude_rms"] == pytest.approx(100.0, rel=1e-3)
        assert va["angle_deg_absolute"] == pytest.approx(0.0, abs=1e-2)
        assert vb["angle_deg_relative"] == pytest.approx(-120.0, abs=1e-2)
        assert vc["angle_deg_relative"] == pytest.approx(120.0, abs=1e-2)
        assert va["unit"] == "V"
        assert va["channel_ref"]["channel_name"] == "ALPHA1_VA"

    def test_single_phase_current_via_http(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 40.0 * math.sqrt(2), 45.0)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="phasor", mode="current_phase_a", analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        ia = body["roles"]["Ia"]
        assert ia["magnitude_rms"] == pytest.approx(40.0, rel=1e-3)
        assert ia["angle_deg_absolute"] == pytest.approx(45.0, abs=1e-2)
        assert ia["angle_deg_relative"] is None
        assert ia["unit"] == "A"


class TestEdgeBehaviorViaHttp:
    def test_insufficient_window_history_at_recording_start(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A"}])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="phasor", mode="voltage_phase_a", analysis_time=0.001)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["role_reasons"]["Va"] == "insufficient_window_history"

    def test_explicit_reference_frequency_override(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0)], nominal_frequency_hz=50.0)
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A"}])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="phasor", mode="voltage_phase_a", analysis_time=1.5, reference_frequency_hz=50.0)
        assert resp.status_code == 200, resp.text
        assert resp.json()["reference_frequency_hz"] == pytest.approx(50.0)


class TestResolverPassThroughViaHttp:
    def test_ambiguous_context_never_computes(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0), ("BRAVO1_VA", "V", 100.0, 10.0)])
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "BRAVO1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
        ])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="phasor", mode="voltage_phase_a", analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ambiguous"
        assert body["roles"] == {}


class TestErrorsViaHttp:
    def test_unknown_context_404s(self, client):
        resp = _phasor(client, "ws-1", "ec-missing", analysis_kind="phasor", mode="voltage_phase_a", analysis_time=1.5)
        assert resp.status_code == 404

    def test_unknown_requirement_400s(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A"}])
        resp = _phasor(client, "ws-1", context["id"], analysis_kind="distance", mode="phase_a", analysis_time=1.5)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unknown_analysis_requirement"
