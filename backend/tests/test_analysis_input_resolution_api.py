"""API-level tests for the Analysis Guardrail Slice 2 read-only Analysis
Input Resolution endpoint
(`GET .../engineering-contexts/{id}/input-resolution`). Exercises the
real FastAPI app end-to-end -- see test_analysis_input_resolution_
service.py for the already-proven service-layer behaviour (including
the full multi-source timebase matrix) this router only exposes.
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


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_measurement_groups"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
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


def _create_context(client, workspace_id, members, display_name="Test Context"):
    resp = client.post(_contexts_url(workspace_id), json={"display_name": display_name, "status": "manual", "members": members})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _resolution(client, workspace_id, context_id, analysis_kind, mode):
    return client.get(
        f"{_contexts_url(workspace_id)}/{context_id}/input-resolution",
        params={"analysis_kind": analysis_kind, "mode": mode},
    )


class TestResolvedCases:
    def test_single_phase_voltage_resolves(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "N275_VR"), "phase": "A", "phase_source": "engineer_confirmed"},
        ])
        resp = _resolution(client, "ws-1", context["id"], "phasor", "voltage_phase_a")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "resolved"
        assert body["resolved_roles"]["Va"]["channel_name"] == "N275_VR"
        assert body["required_role_specs"][0]["engineering_type"] == "Voltage"
        assert body["required_role_specs"][0]["phase"] == "A"

    def test_three_phase_voltage_resolves_via_suggested_context(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        suggested = client.post(f"/api/v1/workspaces/ws-1/sources/{source_id}/engineering-contexts/suggest", json={}).json()
        n275 = next(c for c in suggested if c["display_name"] == "N275")
        resp = _resolution(client, "ws-1", n275["id"], "phasor", "voltage_three_phase")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "resolved"
        assert set(body["resolved_roles"]) == {"Va", "Vb", "Vc"}
        # RYB convention: raw "B" -> canonical C.
        assert body["resolved_roles"]["Vc"]["channel_name"] == "N275_VB"


class TestIncomplete:
    def test_missing_third_phase_is_needs_configuration(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "N275_VR"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "N275_VY"), "phase": "B", "phase_source": "engineer_confirmed"},
        ])
        resp = _resolution(client, "ws-1", context["id"], "phasor", "voltage_three_phase")
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["missing_roles"] == ["Vc"]
        assert body["missing_role_reasons"]["Vc"] == "role_missing"


class TestAmbiguous:
    def test_two_matching_candidates_is_ambiguous(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "N275_VR"), "phase": "A", "phase_source": "engineer_confirmed"},
            {"channel_ref": _ref(source_id, "S132_VR"), "phase": "A", "phase_source": "engineer_confirmed"},
        ])
        resp = _resolution(client, "ws-1", context["id"], "phasor", "voltage_phase_a")
        body = resp.json()
        assert body["status"] == "ambiguous"
        candidate_names = {c["channel_name"] for c in body["ambiguous_roles"]["Va"]}
        assert candidate_names == {"N275_VR", "S132_VR"}
        assert body["resolved_roles"] == {}


class TestUnknownPhase:
    def test_unresolved_phase_member_does_not_resolve(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        context = _create_context(client, "ws-1", [
            {"channel_ref": _ref(source_id, "N275_VR"), "phase": "unknown", "phase_source": "unknown"},
        ])
        resp = _resolution(client, "ws-1", context["id"], "phasor", "voltage_phase_a")
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["missing_role_reasons"]["Va"] == "phase_identity_missing"


class TestErrors:
    def test_unknown_context_404s(self, client):
        resp = _resolution(client, "ws-1", "ec-missing", "phasor", "voltage_phase_a")
        assert resp.status_code == 404

    def test_unknown_requirement_400s(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        resp = _resolution(client, "ws-1", context["id"], "distance", "phase_a")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unknown_analysis_requirement"
