"""API-level tests for Distance Protection v1 (`GET .../distance-
protection`, `GET .../distance-protection-locus`, `GET .../distance-
protection-manual`). Exercises the real FastAPI app end-to-end via a
real ASCII-COMTRADE upload, mirroring `test_impedance_analysis_api.py`'s
own fixture-construction pattern. See docs/project-memory/
DISTANCE_PROTECTION_ANALYSIS.md.
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
    lines_cfg = [f"{station},DISTANCE_DEV,1999", f"{len(channels)},{len(channels)}A,0D"]
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


def _upload_sine_source(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="distance_ascii"):
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


def _upload_sine_source_without_clearing(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="distance_ascii"):
    cfg, dat = _build_ascii_comtrade(
        station="DSTA", channels=channels, sample_rate_hz=sample_rate_hz, duration_s=duration_s,
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


def _create_full_bay(client, workspace_id, source_id, prefix="DBAY"):
    resp = client.post(_contexts_url(workspace_id), json={
        "display_name": "Dbay 1", "status": "manual", "members": [
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


_ZONE_DISABLED_PARAMS = {
    f"zone{n}_enabled": False for n in (1, 2, 3)
}


def _mho_zone_params(n, *, enabled=True, reach_ohm=10.0, characteristic_angle_deg=0.0, delay_s=0.0):
    return {
        f"zone{n}_enabled": enabled, f"zone{n}_reach_ohm": reach_ohm,
        f"zone{n}_characteristic_angle_deg": characteristic_angle_deg, f"zone{n}_delay_s": delay_s,
    }


def _distance(client, workspace_id, context_id, *, loop="AB", analysis_time=1.5, recording_basis="secondary", impedance_basis="secondary", characteristic="mho", **extra):
    params = {
        "loop": loop, "analysis_time": analysis_time,
        "recording_basis": recording_basis, "impedance_basis": impedance_basis, "characteristic": characteristic,
    }
    params.update(_ZONE_DISABLED_PARAMS)
    params.update(extra)
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/distance-protection", params=params)


def _distance_locus(client, workspace_id, context_id, **params):
    merged = dict(_ZONE_DISABLED_PARAMS)
    merged.update(params)
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/distance-protection-locus", params=merged)


def _distance_manual(client, workspace_id, **params):
    defaults = dict(loop_label="AB", voltage_basis="secondary", current_basis="secondary", impedance_basis="secondary", characteristic="mho")
    defaults.update(_ZONE_DISABLED_PARAMS)
    defaults.update(params)
    query = {k: v for k, v in defaults.items() if v is not None}
    return client.get(f"/api/v1/workspaces/{workspace_id}/distance-protection-manual", params=query)


class TestRecordingDistanceViaHttp:
    def _bay_with_balanced_set(self, client, workspace_id="ws-dist-1"):
        # Balanced set with a deliberate current-angle offset so the loop
        # impedance golden value is 10 ohm /20 deg (see
        # test_distance_protection_domain.py's own identical golden case).
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("DBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("DBAY_VB", "V", 100.0 * math.sqrt(2), -120.0), ("DBAY_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("DBAY_IA", "A", 10.0 * math.sqrt(2), -20.0), ("DBAY_IB", "A", 10.0 * math.sqrt(2), -140.0), ("DBAY_IC", "A", 10.0 * math.sqrt(2), 100.0),
        ])
        context = _create_full_bay(client, workspace_id, source_id)
        return workspace_id, context["id"]

    def test_golden_ab_loop_via_http(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="AB", analysis_time=1.5)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(10.0, rel=1e-2)
        assert body["angle_deg"] == pytest.approx(20.0, abs=0.5)

    def test_golden_bc_loop_via_http(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="BC", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(10.0, rel=1e-2)

    def test_golden_ca_loop_via_http(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="CA", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(10.0, rel=1e-2)

    def test_channel_refs_are_populated_for_related_waveforms(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="AB", analysis_time=1.5)
        body = resp.json()
        assert body["v1_channel_ref"]["channel_name"] == "DBAY_VA"
        assert body["v2_channel_ref"]["channel_name"] == "DBAY_VB"
        assert body["i1_channel_ref"]["channel_name"] == "DBAY_IA"
        assert body["i2_channel_ref"]["channel_name"] == "DBAY_IB"

    def test_bc_loop_uses_vb_vc_ib_ic(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="BC", analysis_time=1.5)
        body = resp.json()
        assert body["v1_channel_ref"]["channel_name"] == "DBAY_VB"
        assert body["v2_channel_ref"]["channel_name"] == "DBAY_VC"

    def test_zone_state_reported_when_zones_enabled(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(
            client, workspace_id, context_id, loop="AB", analysis_time=1.5,
            **_mho_zone_params(1, reach_ohm=20.0), **_mho_zone_params(2, reach_ohm=5.0), **_mho_zone_params(3, enabled=False),
        )
        body = resp.json()
        assert body["status"] == "computed"
        # |Z|=10/20deg is well within a reach=20 mho circle centered near
        # the loop angle -> zone1 operated; reach=5 is far too small ->
        # zone2 not operated; zone3 disabled -> not operated regardless.
        assert body["zone1"]["state"] == "operated"
        assert body["zone2"]["state"] == "not_operated"
        assert body["zone3"]["enabled"] is False
        assert body["zone3"]["state"] == "not_operated"

    def test_multiple_zones_can_operate_simultaneously(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(
            client, workspace_id, context_id, loop="AB", analysis_time=1.5,
            **_mho_zone_params(1, reach_ohm=15.0), **_mho_zone_params(2, reach_ohm=20.0), **_mho_zone_params(3, reach_ohm=25.0),
        )
        body = resp.json()
        assert body["zone1"]["state"] == "operated"
        assert body["zone2"]["state"] == "operated"
        assert body["zone3"]["state"] == "operated"

    def test_configured_delay_is_informational_only(self, client):
        workspace_id, context_id = self._bay_with_balanced_set(client)
        resp = _distance(client, workspace_id, context_id, loop="AB", analysis_time=1.5, **_mho_zone_params(1, reach_ohm=20.0, delay_s=0.4))
        body = resp.json()
        assert body["zone1"]["delay_s"] == pytest.approx(0.4)
        assert "trip" not in body["message"].lower()

    def test_low_current_guardrail_via_recording(self, client):
        workspace_id = "ws-dist-lowcurrent"
        source_id = _upload_sine_source(workspace_id=workspace_id, client=client, channels=[
            ("DBAY_VA", "V", 100.0, 0.0), ("DBAY_VB", "V", 100.0, -120.0), ("DBAY_VC", "V", 100.0, 120.0),
            ("DBAY_IA", "A", 1e-6, -30.0), ("DBAY_IB", "A", 1e-6, -30.0), ("DBAY_IC", "A", 1e-6, 90.0),
        ])
        context = _create_full_bay(client, workspace_id, source_id)
        resp = _distance(client, workspace_id, context["id"], loop="AB", analysis_time=1.5)
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "loop_current_too_small"

    def test_unknown_context_404s(self, client):
        resp = _distance(client, "ws-dist-1", "ec-missing")
        assert resp.status_code == 404


class TestDistanceLocusViaHttp:
    def test_locus_returns_requested_point_count_with_no_zone_state(self, client):
        workspace_id = "ws-dist-locus"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("DBAY_VA", "V", 100.0, 0.0), ("DBAY_VB", "V", 100.0, -120.0), ("DBAY_VC", "V", 100.0, 120.0),
            ("DBAY_IA", "A", 10.0, -20.0), ("DBAY_IB", "A", 10.0, -140.0), ("DBAY_IC", "A", 10.0, 100.0),
        ], duration_s=2.0)
        context = _create_full_bay(client, workspace_id, source_id)
        resp = _distance_locus(
            client, workspace_id, context["id"], loop="AB", start_time=0.5, end_time=1.5, point_count=20,
            recording_basis="secondary", impedance_basis="secondary", characteristic="mho",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["points"]) == 20
        computed = [p for p in body["points"] if p["status"] == "computed"]
        assert len(computed) > 0
        for p in computed:
            assert p["magnitude_ohm"] == pytest.approx(10.0, rel=1e-2)
            assert "state" not in p

    def test_locus_point_count_is_clamped(self, client):
        workspace_id = "ws-dist-locus"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("DBAY_VA", "V", 100.0, 0.0), ("DBAY_VB", "V", 100.0, -120.0),
            ("DBAY_IA", "A", 10.0, -20.0), ("DBAY_IB", "A", 10.0, -140.0),
        ], duration_s=2.0)
        resp = client.post(_contexts_url(workspace_id), json={
            "display_name": "Dbay-partial", "status": "manual", "members": [
                {"channel_ref": _ref(source_id, "DBAY_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_IB"), "phase": "B", "phase_source": "engineer_confirmed"},
            ],
        })
        context = resp.json()
        resp = _distance_locus(
            client, workspace_id, context["id"], loop="AB", start_time=0.0, end_time=1.0, point_count=10_000,
            recording_basis="secondary", impedance_basis="secondary", characteristic="mho",
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["points"]) <= 300

    def test_locus_is_deterministic_across_repeated_calls(self, client):
        workspace_id = "ws-dist-locus-det"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("DBAY_VA", "V", 100.0, 0.0), ("DBAY_VB", "V", 100.0, -120.0),
            ("DBAY_IA", "A", 10.0, -20.0), ("DBAY_IB", "A", 10.0, -140.0),
        ], duration_s=2.0)
        resp = client.post(_contexts_url(workspace_id), json={
            "display_name": "Dbay-det", "status": "manual", "members": [
                {"channel_ref": _ref(source_id, "DBAY_VA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_VB"), "phase": "B", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_IA"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "DBAY_IB"), "phase": "B", "phase_source": "engineer_confirmed"},
            ],
        })
        context_id = resp.json()["id"]
        params = dict(loop="AB", start_time=0.5, end_time=1.5, point_count=15, recording_basis="secondary", impedance_basis="secondary", characteristic="mho")
        first = _distance_locus(client, workspace_id, context_id, **params).json()
        second = _distance_locus(client, workspace_id, context_id, **params).json()
        assert first == second


class TestManualDistanceViaHttp:
    def test_golden_ab_loop_via_http_zero_prior_setup(self, client):
        resp = _distance_manual(
            client, "ws-dist-manual-1", loop_label="AB",
            voltage_basis="secondary", current_basis="secondary", impedance_basis="secondary",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
            v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
            i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20,
            i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["magnitude_ohm"] == pytest.approx(10.0, abs=1e-6)
        assert body["angle_deg"] == pytest.approx(20.0, abs=1e-6)

    def test_ab_loop_never_requires_phase_c_via_http(self, client):
        """Section requirement: Manual input for AB must never require
        entering unrelated phase-C values."""
        resp = _distance_manual(
            client, "ws-dist-manual-2", loop_label="AB",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
            v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
            i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20,
            i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140,
        )
        body = resp.json()
        assert body["status"] == "computed"

    def test_zone_state_reported_in_manual_mode(self, client):
        resp = _distance_manual(
            client, "ws-dist-manual-3", loop_label="AB",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
            v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
            i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20,
            i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140,
            **_mho_zone_params(1, reach_ohm=20.0),
        )
        body = resp.json()
        assert body["zone1"]["state"] == "operated"

    def test_no_engineering_context_or_analysis_time_fields_in_response(self, client):
        resp = _distance_manual(
            client, "ws-dist-manual-4", loop_label="AB",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
            v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
            i1_enabled=True, i1_magnitude=10, i1_unit="A", i1_angle_deg=-20,
            i2_enabled=True, i2_magnitude=10, i2_unit="A", i2_angle_deg=-140,
        )
        body = resp.json()
        assert "engineering_context_id" not in body
        assert "analysis_time" not in body
        assert "reference_frequency_hz" not in body

    def test_missing_leg_reports_missing(self, client):
        resp = _distance_manual(
            client, "ws-dist-manual-5", loop_label="AB",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
        )
        body = resp.json()
        assert body["status"] == "missing"

    def test_low_current_guardrail_via_manual(self, client):
        resp = _distance_manual(
            client, "ws-dist-manual-6", loop_label="AB",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0,
            v2_enabled=True, v2_magnitude=100, v2_unit="V", v2_angle_deg=-120,
            i1_enabled=True, i1_magnitude=1e-6, i1_unit="A", i1_angle_deg=-30,
            i2_enabled=True, i2_magnitude=1e-6, i2_unit="A", i2_angle_deg=-30,
        )
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "loop_current_too_small"
