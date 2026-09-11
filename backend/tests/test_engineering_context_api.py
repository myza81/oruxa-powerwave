"""API-level tests for the Analysis Guardrail Slice 1 Engineering Context
REST exposure (`app/api/v1/engineering_contexts.py`). Exercises the real
FastAPI app end-to-end -- see test_engineering_context_service.py for
the already-proven service-layer behaviour this router only exposes.
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


def _upload_files(client, workspace_id, comtrade_fixtures_dir, cfg_stem, dat_stem):
    cfg = (comtrade_fixtures_dir / f"{cfg_stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{dat_stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{cfg_stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{dat_stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/engineering-contexts"


def _ref(source_id, name):
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _create(client, workspace_id, members, display_name="Alpha 1", status="manual"):
    resp = client.post(
        _contexts_url(workspace_id),
        json={"display_name": display_name, "status": status, "members": members},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestListAndCreate:
    def test_list_is_empty_for_a_fresh_workspace(self, client):
        resp = client.get(_contexts_url("ws-1"))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_create_manual_context(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _create(
            client, "ws-1",
            members=[
                {"channel_ref": _ref(source_id, "N275_VR"), "phase": "A", "phase_source": "engineer_confirmed"},
                {"channel_ref": _ref(source_id, "IBT_HV_IR"), "phase": "A", "phase_source": "engineer_confirmed"},
            ],
            display_name="North 275kV Bay",
        )
        assert body["display_name"] == "North 275kV Bay"
        assert body["status"] == "manual"
        assert len(body["members"]) == 2
        assert body["id"].startswith("ec-")

    def test_create_rejects_unknown_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(
            _contexts_url("ws-1"),
            json={
                "display_name": "Bad", "status": "manual",
                "members": [{"channel_ref": _ref(source_id, "NOT_A_CHANNEL"), "phase": "A"}],
            },
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "engineering_context_channel_not_found"

    def test_create_rejects_invalid_phase(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(
            _contexts_url("ws-1"),
            json={
                "display_name": "Bad", "status": "manual",
                "members": [{"channel_ref": _ref(source_id, "N275_VR"), "phase": "Z"}],
            },
        )
        assert resp.status_code == 422, resp.text  # pydantic Literal rejection

    def test_create_spans_two_sources(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _create(
            client, "ws-1",
            members=[
                {"channel_ref": _ref(source_a, "N275_VR"), "phase": "A"},
                {"channel_ref": _ref(source_b, "IBT_HV_IR"), "phase": "A"},
            ],
        )
        source_ids = {m["channel_ref"]["source_id"] for m in body["members"]}
        assert source_ids == {source_a, source_b}


class TestGetUpdateDelete:
    def test_get_roundtrip(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        resp = client.get(f"{_contexts_url('ws-1')}/{created['id']}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == created["id"]

    def test_get_missing_404s(self, client):
        resp = client.get(f"{_contexts_url('ws-1')}/ec-missing")
        assert resp.status_code == 404

    def test_patch_promotes_status(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}], status="suggested")
        resp = client.patch(f"{_contexts_url('ws-1')}/{created['id']}", json={"status": "confirmed"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "confirmed"

    def test_patch_membership_full_replace(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        resp = client.patch(
            f"{_contexts_url('ws-1')}/{created['id']}",
            json={"members": [
                {"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"},
                {"channel_ref": _ref(source_id, "N275_VY"), "phase": "B"},
            ]},
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["members"]) == 2

    def test_patch_member_phase(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(
            client, "ws-1",
            members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "unknown", "phase_source": "unknown"}],
        )
        resp = client.patch(
            f"{_contexts_url('ws-1')}/{created['id']}/member-phase",
            json={"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"},
        )
        assert resp.status_code == 200, resp.text
        member = resp.json()["members"][0]
        assert member["phase"] == "A"
        assert member["phase_source"] == "engineer_confirmed"

    def test_delete_is_idempotent(self, client):
        resp1 = client.delete(f"{_contexts_url('ws-1')}/ec-missing")
        assert resp1.status_code == 204
        resp2 = client.delete(f"{_contexts_url('ws-1')}/ec-missing")
        assert resp2.status_code == 204

    def test_delete_removes_context(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        resp = client.delete(f"{_contexts_url('ws-1')}/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"{_contexts_url('ws-1')}/{created['id']}").status_code == 404


class TestSuggestEndpoint:
    def test_suggest_creates_multiple_contexts(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(f"/api/v1/workspaces/ws-1/sources/{source_id}/engineering-contexts/suggest", json={})
        assert resp.status_code == 200, resp.text
        created = resp.json()
        names = {c["display_name"] for c in created}
        # N275/S132/E275 (Voltage-only bays), IBT_HV/IBT_LV (Current-only
        # bays), LINEA/LINEB/SPARE (single-member Current bays) -- FREQ
        # (Power/Frequency) and the two digital channels excluded.
        assert names == {"N275", "S132", "E275", "IBT_HV", "IBT_LV", "LINEA", "LINEB", "SPARE"}
        n275 = next(c for c in created if c["display_name"] == "N275")
        assert n275["status"] == "suggested"
        phases = {m["channel_ref"]["channel_name"]: m["phase"] for m in n275["members"]}
        # RYB convention: raw "B" normalizes to canonical C.
        assert phases == {"N275_VR": "A", "N275_VY": "B", "N275_VB": "C"}

    def test_suggest_creates_default_context_for_bare_phasor_roles(self, client, comtrade_fixtures_dir):
        source_id = _upload_files(
            client, "ws-1", comtrade_fixtures_dir,
            cfg_stem="phasor_bare_three_phase", dat_stem="phasor_smoke_three_phase",
        )
        resp = client.post(f"/api/v1/workspaces/ws-1/sources/{source_id}/engineering-contexts/suggest", json={})
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert len(created) == 1
        context = created[0]
        assert context["display_name"] == "Default Context"
        assert context["status"] == "suggested"
        phases = {m["channel_ref"]["channel_name"]: m["phase"] for m in context["members"]}
        assert phases == {"VA": "A", "VB": "B", "VC": "C", "IA": "A", "IB": "B", "IC": "C"}

        listed = client.get(_contexts_url("ws-1"))
        assert listed.status_code == 200, listed.text
        assert [c["id"] for c in listed.json()] == [context["id"]]

    def test_suggest_is_idempotent(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.post(f"/api/v1/workspaces/ws-1/sources/{source_id}/engineering-contexts/suggest", json={})
        second = client.post(f"/api/v1/workspaces/ws-1/sources/{source_id}/engineering-contexts/suggest", json={})
        assert second.json() == []

    def test_suggest_404s_for_unknown_source(self, client):
        resp = client.post("/api/v1/workspaces/ws-1/sources/does-not-exist/engineering-contexts/suggest", json={})
        assert resp.status_code == 404


class TestLifecycleIntegration:
    def test_workspace_reset_clears_contexts(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        assert len(client.get(_contexts_url("ws-1")).json()) == 1
        resp = client.delete("/api/v1/workspaces/ws-1")
        assert resp.status_code == 204
        assert client.get(_contexts_url("ws-1")).json() == []

    def test_removing_one_source_prunes_membership_not_whole_context(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(
            client, "ws-1",
            members=[
                {"channel_ref": _ref(source_a, "N275_VR"), "phase": "A"},
                {"channel_ref": _ref(source_b, "IBT_HV_IR"), "phase": "A"},
            ],
        )
        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_a}")
        assert resp.status_code == 204
        remaining = client.get(f"{_contexts_url('ws-1')}/{created['id']}").json()
        assert len(remaining["members"]) == 1
        assert remaining["members"][0]["channel_ref"]["source_id"] == source_b

    def test_removing_only_source_removes_whole_context(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(client, "ws-1", members=[{"channel_ref": _ref(source_id, "N275_VR"), "phase": "A"}])
        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204
        assert client.get(f"{_contexts_url('ws-1')}/{created['id']}").status_code == 404
