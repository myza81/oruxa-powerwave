"""Integration tests for DEC-108's shared multi-window waveform-form
detector correction -- proves the fix propagates NATURALLY to every
consumer of `app.domain.rms_detector.classify_waveform_form()`
(Overcurrent, Phasor, Impedance, Distance Protection, and calculated-
channel RMS eligibility) through the ONE shared detector, with zero
analyzer-specific bypasses. See `test_rms_detector.py`'s own
`TestMultiWindowDetection`/`TestMultiWindowDoesNotWeakenGenuineRmsSafety`
for the detector-level unit coverage this file builds on.

Fixture: disturbance_record_multibay(.cfg/.dat) -- ONE bay (`DISTBAY`),
Voltage stays a clean instantaneous sinusoid throughout (never the
reported problem), Current is the exact KPDN1-style disturbance shape
investigation reproduced: clean pre-fault [0, 0.15s), fault [0.15s,
0.25s), near-zero post-clearance collapse for the rest of the record.
`waveform_form` is `"unknown"` for every channel (the real, unavoidable
default for a raw COMTRADE upload -- confirmed directly by code
inspection during investigation), so every readiness/computation check
below genuinely exercises the algorithmic fallback detector, never
trusted metadata.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="disturbance_record_multibay"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _context_id(client, workspace_id):
    contexts = client.get(f"/api/v1/workspaces/{workspace_id}/engineering-contexts").json()
    return contexts[0]["id"]


def _readiness(client, workspace_id, context_id, analysis_kind, mode):
    return client.get(
        f"/api/v1/workspaces/{workspace_id}/engineering-contexts/{context_id}/input-readiness",
        params={"analysis_kind": analysis_kind, "mode": mode},
    )


class TestReadinessPropagatesToEveryConsumer:
    """Section 12: the SAME shared detector fix, exercised through each
    analyzer's own `analysis_kind`, never a per-analyzer bypass."""

    @pytest.mark.parametrize("analysis_kind", ["overcurrent", "phasor", "impedance", "distance", "sequence_components"])
    def test_current_phase_a_is_ready(self, client, comtrade_fixtures_dir, analysis_kind):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = _readiness(client, "ws-1", ctx_id, analysis_kind, "current_phase_a")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "resolved", resp.json()

    def test_voltage_phase_a_is_also_ready(self, client, comtrade_fixtures_dir):
        """Voltage was never reported as the problem -- confirm it was
        never accidentally broken either."""
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = _readiness(client, "ws-1", ctx_id, "impedance", "voltage_phase_a")
        assert resp.json()["status"] == "resolved"

    @pytest.mark.parametrize("phase_mode", ["current_phase_a", "current_phase_b", "current_phase_c"])
    def test_all_three_phases_are_ready(self, client, comtrade_fixtures_dir, phase_mode):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = _readiness(client, "ws-1", ctx_id, "overcurrent", phase_mode)
        assert resp.json()["status"] == "resolved"


class TestActualCalculationSucceeds:
    """Section 13: readiness passing is not enough -- the REAL,
    time-dependent computation must also succeed, at a genuine
    pre-fault analysis_time where the measured current is well-defined."""

    def test_overcurrent_one_cycle_rms_succeeds(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = client.get(
            f"/api/v1/workspaces/ws-1/engineering-contexts/{ctx_id}/overcurrent",
            params={
                "phase": "A", "analysis_time": 0.1, "characteristic_id": "iec_standard_inverse",
                "tms": 0.1, "pickup_current_secondary": 1.0, "recording_basis": "secondary",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed", body
        assert body["measured_rms_current"] == pytest.approx(40.0, rel=0.05)

    def test_impedance_phasor_and_point_succeed(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = client.get(
            f"/api/v1/workspaces/ws-1/engineering-contexts/{ctx_id}/impedance",
            params={"phase": "A", "analysis_time": 0.1, "recording_basis": "secondary", "impedance_basis": "secondary"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "computed", resp.json()

    def test_distance_loop_calculation_succeeds(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = client.get(
            f"/api/v1/workspaces/ws-1/engineering-contexts/{ctx_id}/distance-protection",
            params={
                "loop": "AB", "analysis_time": 0.1, "recording_basis": "secondary",
                "impedance_basis": "secondary", "characteristic": "mho",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "computed", resp.json()

    def test_phasor_diagram_resolves_current_role(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        ctx_id = _context_id(client, "ws-1")
        resp = client.get(
            f"/api/v1/workspaces/ws-1/engineering-contexts/{ctx_id}/phasor-diagram",
            params={"analysis_time": 0.1},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["roles"]["Ia"]["status"] == "available", resp.json()["roles"]["Ia"]
