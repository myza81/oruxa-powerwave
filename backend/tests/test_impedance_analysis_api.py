"""API-level tests for Impedance Locus v1 (`GET .../impedance`,
`GET .../impedance-locus`, `GET .../impedance-manual`). Exercises the
real FastAPI app end-to-end via a real ASCII-COMTRADE upload, mirroring
`test_phasor_diagram_api.py`'s own fixture-construction pattern. See
docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md.
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
    lines_cfg = [f"{station},IMPEDANCE_DEV,1999", f"{len(channels)},{len(channels)}A,0D"]
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


def _upload_sine_source(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="impedance_ascii"):
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


def _upload_sine_source_without_clearing(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="impedance_ascii"):
    cfg, dat = _build_ascii_comtrade(
        station="ZSTA", channels=channels, sample_rate_hz=sample_rate_hz, duration_s=duration_s,
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


def _create_full_bay(client, workspace_id, source_id, prefix="ZBAY"):
    resp = client.post(_contexts_url(workspace_id), json={
        "display_name": "Zbay 1", "status": "manual", "members": [
            {"channel_ref": _ref(source_id, f"{prefix}_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, f"{prefix}_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, f"{prefix}_VC"), "phase": "C", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, f"{prefix}_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, f"{prefix}_IB"), "phase": "B", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, f"{prefix}_IC"), "phase": "C", "phase_source": "engineer_confirmed"},
        ],
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _impedance(client, workspace_id, context_id, *, phase="A", analysis_time=1.5, recording_basis="secondary", impedance_basis="secondary", **extra):
    params = {
        "phase": phase, "analysis_time": analysis_time,
        "recording_basis": recording_basis, "impedance_basis": impedance_basis,
    }
    params.update(extra)
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/impedance", params=params)


def _impedance_locus(client, workspace_id, context_id, **params):
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/impedance-locus", params=params)


def _impedance_manual(client, workspace_id, **params):
    defaults = dict(phase_label="A", voltage_basis="secondary", current_basis="secondary", impedance_basis="secondary")
    defaults.update(params)
    query = {k: v for k, v in defaults.items() if v is not None}
    return client.get(f"/api/v1/workspaces/{workspace_id}/impedance-manual", params=query)


class TestRecordingImpedanceViaHttp:
    def _bay_with_known_zabc(self, client, workspace_id="ws-imp-1"):
        # Va = 100 V / 0deg, Ia = 1 A / -30deg -> Za = 100 ohm / +30deg (R~86.60, X=50)
        # Vb/Ib, Vc/Ic balanced three-phase equivalents.
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("ZBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("ZBAY_VB", "V", 100.0 * math.sqrt(2), -120.0), ("ZBAY_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("ZBAY_IA", "A", 1.0 * math.sqrt(2), -30.0), ("ZBAY_IB", "A", 1.0 * math.sqrt(2), -150.0), ("ZBAY_IC", "A", 1.0 * math.sqrt(2), 90.0),
        ])
        context = _create_full_bay(client, workspace_id, source_id)
        return workspace_id, context["id"]

    def test_golden_za_via_http(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, phase="A", analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(100.0, rel=1e-3)
        assert body["angle_deg"] == pytest.approx(30.0, abs=0.5)
        assert body["resistance_ohm"] == pytest.approx(86.6025, rel=1e-2)
        assert body["reactance_ohm"] == pytest.approx(50.0, rel=1e-2)

    def test_channel_refs_are_populated_for_related_waveforms(self, client):
        """UAT-reported bug fix: Related Waveforms needs `channel_ref` on
        each quantity to know WHICH channel to fetch -- without it, both
        traces render blank. See docs/project-memory/
        IMPEDANCE_LOCUS_ANALYSIS.md's own "Related Waveforms" section."""
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, phase="A", analysis_time=1.5)
        body = resp.json()
        assert body["voltage_channel_ref"] is not None
        assert body["voltage_channel_ref"]["channel_name"] == "ZBAY_VA"
        assert body["current_channel_ref"] is not None
        assert body["current_channel_ref"]["channel_name"] == "ZBAY_IA"

    def test_channel_refs_populated_even_when_current_too_small(self, client):
        """`voltage_channel_ref`/`current_channel_ref` should still be
        known (identity was resolved) even when the low-current guardrail
        blocks the numeric result -- mirrors `PhasorDiagramRoleResult`'s
        own "channel_ref populated whenever identity is known" precedent."""
        workspace_id = "ws-imp-lowcurrent-channelref"
        source_id = _upload_sine_source(workspace_id=workspace_id, client=client, channels=[
            ("ZBAY_VA", "V", 100.0, 0.0), ("ZBAY_VB", "V", 100.0, -120.0), ("ZBAY_VC", "V", 100.0, 120.0),
            ("ZBAY_IA", "A", 1e-6, -30.0), ("ZBAY_IB", "A", 1e-6, -150.0), ("ZBAY_IC", "A", 1e-6, 90.0),
        ])
        context = _create_full_bay(client, workspace_id, source_id)
        resp = _impedance(client, workspace_id, context["id"], phase="A", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "current_too_small"
        assert body["voltage_channel_ref"] is not None
        assert body["current_channel_ref"] is not None

    def test_phase_b_uses_vb_ib(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, phase="B", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(100.0, rel=1e-3)

    def test_phase_c_uses_vc_ic(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, phase="C", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(100.0, rel=1e-3)

    def test_recording_basis_equal_to_impedance_basis_needs_no_ratios(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, recording_basis="primary", impedance_basis="primary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(100.0, rel=1e-3)

    def test_basis_conversion_requires_ratios(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(client, workspace_id, context_id, recording_basis="secondary", impedance_basis="primary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "invalid_ratio"

    def test_basis_conversion_with_ratios_scales_correctly(self, client):
        workspace_id, context_id = self._bay_with_known_zabc(client)
        resp = _impedance(
            client, workspace_id, context_id, recording_basis="secondary", impedance_basis="primary",
            vt_primary=1200, vt_secondary=1, ct_primary=1200, ct_secondary=1,
        )
        body = resp.json()
        assert body["status"] == "computed"
        # vt_ratio == ct_ratio -> factor 1
        assert body["magnitude_ohm"] == pytest.approx(100.0, rel=1e-3)

    def test_low_current_guardrail_via_recording(self, client):
        workspace_id = "ws-imp-lowcurrent"
        source_id = _upload_sine_source(workspace_id=workspace_id, client=client, channels=[
            ("ZBAY_VA", "V", 100.0, 0.0), ("ZBAY_VB", "V", 100.0, -120.0), ("ZBAY_VC", "V", 100.0, 120.0),
            ("ZBAY_IA", "A", 1e-6, -30.0), ("ZBAY_IB", "A", 1e-6, -150.0), ("ZBAY_IC", "A", 1e-6, 90.0),
        ])
        context = _create_full_bay(client, workspace_id, source_id)
        resp = _impedance(client, workspace_id, context["id"], phase="A", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "current_too_small"
        assert body["magnitude_ohm"] is None

    def test_unknown_context_404s(self, client):
        resp = _impedance(client, "ws-imp-1", "ec-missing")
        assert resp.status_code == 404


class TestImpedanceLocusViaHttp:
    def test_locus_returns_requested_point_count(self, client):
        workspace_id = "ws-imp-locus"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("ZBAY_VA", "V", 100.0, 0.0), ("ZBAY_VB", "V", 100.0, -120.0), ("ZBAY_VC", "V", 100.0, 120.0),
            ("ZBAY_IA", "A", 1.0, -30.0), ("ZBAY_IB", "A", 1.0, -150.0), ("ZBAY_IC", "A", 1.0, 90.0),
        ], duration_s=2.0)
        context = _create_full_bay(client, workspace_id, source_id)
        resp = _impedance_locus(
            client, workspace_id, context["id"], phase="A", start_time=0.5, end_time=1.5, point_count=20,
            recording_basis="secondary", impedance_basis="secondary",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["points"]) == 20
        computed = [p for p in body["points"] if p["status"] == "computed"]
        assert len(computed) > 0
        for p in computed:
            assert p["magnitude_ohm"] == pytest.approx(100.0, rel=1e-2)

    def test_locus_point_count_is_clamped(self, client):
        workspace_id = "ws-imp-locus"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("ZBAY_VA", "V", 100.0, 0.0), ("ZBAY_IA", "A", 1.0, -30.0),
        ], duration_s=2.0)
        resp = client.post(_contexts_url(workspace_id), json={
            "display_name": "Zbay-partial", "status": "manual", "members": [
                {"channel_ref": _ref(source_id, "ZBAY_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "ZBAY_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
            ],
        })
        context = resp.json()
        resp = _impedance_locus(
            client, workspace_id, context["id"], phase="A", start_time=0.0, end_time=1.0, point_count=10_000,
            recording_basis="secondary", impedance_basis="secondary",
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["points"]) <= 300

    def test_locus_is_deterministic_across_repeated_calls(self, client):
        workspace_id = "ws-imp-locus-det"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("ZBAY_VA", "V", 100.0, 0.0), ("ZBAY_IA", "A", 1.0, -30.0),
        ], duration_s=2.0)
        resp = client.post(_contexts_url(workspace_id), json={
            "display_name": "Zbay-det", "status": "manual", "members": [
                {"channel_ref": _ref(source_id, "ZBAY_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "ZBAY_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
            ],
        })
        context_id = resp.json()["id"]
        params = dict(phase="A", start_time=0.5, end_time=1.5, point_count=15, recording_basis="secondary", impedance_basis="secondary")
        first = _impedance_locus(client, workspace_id, context_id, **params).json()
        second = _impedance_locus(client, workspace_id, context_id, **params).json()
        assert first == second


class TestManualImpedanceViaHttp:
    def test_golden_example_via_http_zero_prior_setup(self, client):
        resp = _impedance_manual(
            client, "ws-imp-manual-1", phase_label="A",
            voltage_basis="secondary", current_basis="secondary", impedance_basis="secondary",
            voltage_enabled=True, voltage_magnitude=100, voltage_unit="V", voltage_angle_deg=0,
            current_enabled=True, current_magnitude=1, current_unit="A", current_angle_deg=-30,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(100.0, abs=1e-6)
        assert body["angle_deg"] == pytest.approx(30.0, abs=1e-6)
        assert body["resistance_ohm"] == pytest.approx(86.6025403784, abs=1e-4)
        assert body["reactance_ohm"] == pytest.approx(50.0, abs=1e-6)

    def test_mixed_basis_voltage_primary_current_secondary_output_primary(self, client):
        resp = _impedance_manual(
            client, "ws-imp-manual-1", phase_label="A",
            voltage_basis="primary", vt_primary=132000, vt_secondary=110,
            current_basis="secondary", ct_primary=1200, ct_secondary=1, impedance_basis="primary",
            voltage_enabled=True, voltage_magnitude=132, voltage_unit="kV", voltage_angle_deg=0,
            current_enabled=True, current_magnitude=1, current_unit="A", current_angle_deg=-30,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["voltage_magnitude_secondary"] == pytest.approx(110.0, rel=1e-6)
        assert body["current_magnitude_secondary"] == pytest.approx(1.0, rel=1e-6)

    def test_no_engineering_context_or_analysis_time_fields_in_response(self, client):
        resp = _impedance_manual(
            client, "ws-imp-manual-1",
            voltage_enabled=True, voltage_magnitude=110, voltage_unit="V", voltage_angle_deg=0,
            current_enabled=True, current_magnitude=1, current_unit="A", current_angle_deg=-30,
        )
        body = resp.json()
        assert "engineering_context_id" not in body
        assert "analysis_time" not in body
        assert "reference_frequency_hz" not in body

    def test_missing_current_reports_missing(self, client):
        resp = _impedance_manual(
            client, "ws-imp-manual-1",
            voltage_enabled=True, voltage_magnitude=110, voltage_unit="V", voltage_angle_deg=0,
        )
        body = resp.json()
        assert body["status"] == "missing"

    def test_low_current_guardrail_via_manual(self, client):
        resp = _impedance_manual(
            client, "ws-imp-manual-1",
            voltage_enabled=True, voltage_magnitude=110, voltage_unit="V", voltage_angle_deg=0,
            current_enabled=True, current_magnitude=1e-6, current_unit="A", current_angle_deg=-30,
        )
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "current_too_small"
