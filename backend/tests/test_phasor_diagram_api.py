"""API-level tests for the bay-centric Phasor Diagram aggregation
endpoint (`GET .../engineering-contexts/{id}/phasor-diagram`; Phasor
UAT redesign). Exercises the real FastAPI app end-to-end via a real
ASCII-COMTRADE upload -- see test_phasor_diagram_service.py for the
already-proven service-layer behaviour (partial availability, one-bad-
role isolation, whole-result blocking conditions) this router only
exposes.
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


def _upload_sine_source(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="phasor_diagram_ascii"):
    """DEC-104 (2026-09-23): upload now also runs automatic Engineering
    Context discovery, which would otherwise collide with this module's
    own hand-built contexts on the same channels -- clear whatever
    discovery created immediately after upload so every test below
    keeps constructing its own contexts from a clean slate."""
    source_id = _upload_sine_source_without_clearing(
        client, workspace_id, channels=channels, sample_rate_hz=sample_rate_hz,
        duration_s=duration_s, nominal_frequency_hz=nominal_frequency_hz, stem=stem,
    )
    for context in client.get(_contexts_url(workspace_id)).json():
        client.delete(f"{_contexts_url(workspace_id)}/{context['id']}")
    return source_id


def _upload_sine_source_without_clearing(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="phasor_diagram_ascii"):
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


def _phasor_diagram(client, workspace_id, context_id, *, analysis_time, reference_frequency_hz=None):
    params = {"analysis_time": analysis_time}
    if reference_frequency_hz is not None:
        params["reference_frequency_hz"] = reference_frequency_hz
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/phasor-diagram", params=params)


class TestFullBayViaHttp:
    def test_all_six_roles_via_http(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[
            ("ALPHA1_VA", "V", 100.0 * math.sqrt(2), 0.0), ("ALPHA1_VB", "V", 100.0 * math.sqrt(2), -120.0), ("ALPHA1_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("ALPHA1_IA", "A", 40.0 * math.sqrt(2), -30.0), ("ALPHA1_IB", "A", 40.0 * math.sqrt(2), -150.0), ("ALPHA1_IC", "A", 40.0 * math.sqrt(2), 90.0),
        ])
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_VC"), "phase": "C", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_IB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_IC"), "phase": "C", "phase_source": "engineer_confirmed"},
        ])
        resp = _phasor_diagram(client, "ws-1", context["id"], analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert set(body["roles"]) == {"Va", "Vb", "Vc", "Ia", "Ib", "Ic"}
        for role_key in body["roles"]:
            assert body["roles"][role_key]["status"] == "available"
        va, ia = body["roles"]["Va"], body["roles"]["Ia"]
        assert va["magnitude_rms"] == pytest.approx(100.0, rel=1e-3)
        assert ia["magnitude_rms"] == pytest.approx(40.0, rel=1e-3)
        # The true V-I absolute-angle relationship must survive the
        # combined diagram -- never independently zero-referenced.
        assert (va["angle_deg_absolute"] - ia["angle_deg_absolute"]) == pytest.approx(30.0, abs=1e-2)
        assert body["roles"]["Vb"]["angle_deg_relative"] == pytest.approx(-120.0, abs=1e-2)

    def test_partial_bay_via_http(self, client):
        source_id = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0), ("ALPHA1_IA", "A", 40.0, -30.0)])
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
        ])
        resp = _phasor_diagram(client, "ws-1", context["id"], analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["roles"]["Va"]["status"] == "available"
        assert body["roles"]["Ia"]["status"] == "available"
        for role_key in ("Vb", "Vc", "Ib", "Ic"):
            assert body["roles"][role_key]["status"] == "missing"
            assert body["roles"][role_key]["magnitude_rms"] is None
            assert body["roles"][role_key]["channel_ref"] is None


class TestErrorsViaHttp:
    def test_unknown_context_404s(self, client):
        resp = _phasor_diagram(client, "ws-1", "ec-missing", analysis_time=1.5)
        assert resp.status_code == 404

    def test_reference_frequency_conflict_blocks_whole_result(self, client):
        source_id_v = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_VA", "V", 100.0, 0.0)], nominal_frequency_hz=50.0, stem="v_src")
        source_id_i = _upload_sine_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 40.0, -30.0)], nominal_frequency_hz=60.0, stem="i_src")
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id_v, "ALPHA1_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id_i, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
        ])
        resp = _phasor_diagram(client, "ws-1", context["id"], analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "reference_frequency_conflict"
        assert body["roles"]["Va"]["status"] == "needs_configuration"
        assert body["roles"]["Ia"]["status"] == "needs_configuration"


def _phasor_manual(client, workspace_id, **params):
    defaults = dict(voltage_basis="secondary", current_basis="secondary")
    defaults.update(params)
    query = {k: v for k, v in defaults.items() if v is not None}
    return client.get(f"/api/v1/workspaces/{workspace_id}/phasor-manual", params=query)


class TestManualPhasorDiagramEndpoint:
    """Manual Input / Calculator mode (`GET .../phasor-manual`) --
    workspace-scoped only, zero Engineering Context/upload needed at
    all. See docs/project-memory/ANALYSIS_INPUT_SOURCE.md."""

    def test_golden_owner_worked_example_via_http(self, client):
        """Owner's own worked example (task §17) end-to-end through the
        real HTTP endpoint, with zero prior upload/context/source
        setup."""
        resp = _phasor_manual(
            client, "ws-manual-1",
            voltage_basis="primary", vt_primary=132000, vt_secondary=110,
            current_basis="primary", ct_primary=1200, ct_secondary=1,
            va_enabled=True, va_magnitude=132, va_unit="kV", va_angle_deg=0,
            vb_enabled=True, vb_magnitude=132, vb_unit="kV", vb_angle_deg=-120,
            vc_enabled=True, vc_magnitude=132, vc_unit="kV", vc_angle_deg=120,
            ia_enabled=True, ia_magnitude=1200, ia_unit="A", ia_angle_deg=-30,
            ib_enabled=True, ib_magnitude=1200, ib_unit="A", ib_angle_deg=-150,
            ic_enabled=True, ic_magnitude=1200, ic_unit="A", ic_angle_deg=90,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["algorithm_version"] == "phasor_manual_v1"
        for role_key in ("Va", "Vb", "Vc"):
            assert body["roles"][role_key]["status"] == "available"
            assert body["roles"][role_key]["magnitude_rms"] == pytest.approx(110.0, rel=1e-6)
            assert body["roles"][role_key]["unit"] == "V"
        for role_key in ("Ia", "Ib", "Ic"):
            assert body["roles"][role_key]["status"] == "available"
            assert body["roles"][role_key]["magnitude_rms"] == pytest.approx(1.0, rel=1e-6)
            assert body["roles"][role_key]["unit"] == "A"

    def test_no_engineering_context_or_channel_fields_in_response(self, client):
        resp = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=110, va_unit="V", va_angle_deg=0)
        body = resp.json()
        assert "engineering_context_id" not in body
        assert "analysis_time" not in body
        assert "reference_frequency_hz" not in body
        assert "window_seconds" not in body
        for role_key in body["roles"]:
            assert "phase" not in body["roles"][role_key]

    def test_mixed_basis_voltage_primary_current_secondary_via_http(self, client):
        """Task §18's own mixed-basis golden test via real HTTP."""
        resp = _phasor_manual(
            client, "ws-manual-1",
            voltage_basis="primary", vt_primary=132000, vt_secondary=110,
            current_basis="secondary",
            va_enabled=True, va_magnitude=132, va_unit="kV", va_angle_deg=0,
            ia_enabled=True, ia_magnitude=1, ia_unit="A", ia_angle_deg=-30,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["roles"]["Va"]["status"] == "available"
        assert body["roles"]["Va"]["magnitude_rms"] == pytest.approx(110.0, rel=1e-6)
        assert body["roles"]["Ia"]["status"] == "available"
        assert body["roles"]["Ia"]["magnitude_rms"] == pytest.approx(1.0, rel=1e-6)

    def test_ka_equals_a_via_http(self, client):
        resp_a = _phasor_manual(client, "ws-manual-1", ia_enabled=True, ia_magnitude=1200, ia_unit="A", ia_angle_deg=0)
        resp_ka = _phasor_manual(client, "ws-manual-1", ia_enabled=True, ia_magnitude=1.2, ia_unit="kA", ia_angle_deg=0)
        assert resp_a.json()["roles"]["Ia"]["magnitude_rms"] == pytest.approx(
            resp_ka.json()["roles"]["Ia"]["magnitude_rms"], rel=1e-6
        )

    def test_kv_equals_v_via_http(self, client):
        resp_v = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=132000, va_unit="V", va_angle_deg=0)
        resp_kv = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=132, va_unit="kV", va_angle_deg=0)
        assert resp_v.json()["roles"]["Va"]["magnitude_rms"] == pytest.approx(
            resp_kv.json()["roles"]["Va"]["magnitude_rms"], rel=1e-6
        )

    def test_angle_normalization_240_equals_negative_120_via_http(self, client):
        resp = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=110, va_unit="V", va_angle_deg=240)
        assert resp.json()["roles"]["Va"]["angle_deg_absolute"] == pytest.approx(-120.0)

    def test_partial_input_only_va_and_ia_via_http(self, client):
        resp = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=110, va_unit="V", va_angle_deg=0,
                               ia_enabled=True, ia_magnitude=1, ia_unit="A", ia_angle_deg=-30)
        body = resp.json()
        assert body["status"] == "computed"
        assert body["roles"]["Va"]["status"] == "available"
        assert body["roles"]["Ia"]["status"] == "available"
        for role_key in ("Vb", "Vc", "Ib", "Ic"):
            assert body["roles"][role_key]["status"] == "missing"
            assert body["roles"][role_key]["magnitude_rms"] is None

    def test_invalid_ratio_blocks_only_its_own_family_via_http(self, client):
        resp = _phasor_manual(
            client, "ws-manual-1",
            voltage_basis="primary", vt_primary=0, vt_secondary=110,
            current_basis="secondary",
            va_enabled=True, va_magnitude=132, va_unit="kV", va_angle_deg=0,
            ia_enabled=True, ia_magnitude=1, ia_unit="A", ia_angle_deg=-30,
        )
        body = resp.json()
        assert body["status"] == "computed"
        assert body["roles"]["Va"]["status"] == "needs_configuration"
        assert body["roles"]["Ia"]["status"] == "available"

    @pytest.mark.parametrize("bad_magnitude", [-1.0])
    def test_invalid_magnitude_is_missing_never_a_500_via_http(self, client, bad_magnitude):
        resp = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=bad_magnitude, va_unit="V", va_angle_deg=0)
        assert resp.status_code == 200, resp.text
        assert resp.json()["roles"]["Va"]["status"] == "missing"

    def test_zero_magnitude_is_available_via_http(self, client):
        resp = _phasor_manual(client, "ws-manual-1", va_enabled=True, va_magnitude=0.0, va_unit="V", va_angle_deg=0)
        assert resp.json()["roles"]["Va"]["status"] == "available"
        assert resp.json()["roles"]["Va"]["magnitude_rms"] == pytest.approx(0.0)
