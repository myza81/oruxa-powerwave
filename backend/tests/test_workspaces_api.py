"""API-level tests for the Phase 1 whole-workspace lifecycle endpoint.

Distinct from tests/test_sources_api.py's TestLifecycle, which covers
single-source DELETE ("Remove") -- these tests cover the whole-workspace
DELETE ("Start new workspace"'s backend counterpart, DEC-018), including
that it does not disturb other workspaces or leave partial state behind.
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


def _files(cfg_bytes: bytes, dat_bytes: bytes, cfg_name="event.cfg", dat_name="event.dat"):
    return {
        "cfg_file": (cfg_name, io.BytesIO(cfg_bytes), "application/octet-stream"),
        "dat_file": (dat_name, io.BytesIO(dat_bytes), "application/octet-stream"),
    }


def _read(path) -> bytes:
    return path.read_bytes()


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
    dat = _read(comtrade_fixtures_dir / f"{stem}.dat")
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=_files(cfg, dat))
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


class TestWorkspaceDelete:
    def test_delete_single_source_workspace_makes_the_source_inaccessible(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.delete("/api/v1/workspaces/ws-1")

        assert resp.status_code == 204
        assert resp.content == b""
        assert client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 404
        assert (
            client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels").status_code
            == 404
        )
        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []

    def test_delete_multi_source_workspace_makes_every_source_inaccessible(
        self, client, comtrade_fixtures_dir
    ):
        source_ids = [
            _upload(client, "ws-1", comtrade_fixtures_dir) for _ in range(3)
        ]
        assert len(set(source_ids)) == 3  # sanity: three distinct sources exist

        resp = client.delete("/api/v1/workspaces/ws-1")

        assert resp.status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []
        for source_id in source_ids:
            assert (
                client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 404
            )

    def test_delete_workspace_does_not_affect_other_workspaces(
        self, client, comtrade_fixtures_dir
    ):
        target_source_id = _upload(client, "ws-target", comtrade_fixtures_dir)
        other_source_id = _upload(client, "ws-other", comtrade_fixtures_dir)

        resp = client.delete("/api/v1/workspaces/ws-target")

        assert resp.status_code == 204
        assert client.get("/api/v1/workspaces/ws-target/sources").json() == []
        # The untouched workspace's source is still fully readable.
        other_resp = client.get(f"/api/v1/workspaces/ws-other/sources/{other_source_id}")
        assert other_resp.status_code == 200
        assert client.get("/api/v1/workspaces/ws-other/sources").json()[0]["source_id"] == (
            other_source_id
        )

    def test_delete_empty_workspace_is_a_successful_no_op(self, client):
        resp = client.delete("/api/v1/workspaces/never-used")

        assert resp.status_code == 204

    def test_delete_unknown_workspace_is_a_successful_no_op(self, client):
        # No "workspace not found" error: a workspace is never explicitly
        # created server-side, so an unknown id and an empty id are
        # indistinguishable and both succeed as a no-op (see
        # app/api/v1/workspaces.py).
        resp = client.delete("/api/v1/workspaces/totally-unknown-id")

        assert resp.status_code == 204

    def test_delete_blank_workspace_id_is_rejected(self, client):
        # A literal blank segment collapses the URL (no path parameter to
        # match), so this exercises the validation with a whitespace id.
        resp = client.delete("/api/v1/workspaces/%20")

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_workspace"

    def test_workspace_delete_then_reupload_into_the_same_id_works(
        self, client, comtrade_fixtures_dir
    ):
        _upload(client, "ws-1", comtrade_fixtures_dir)
        assert client.delete("/api/v1/workspaces/ws-1").status_code == 204

        new_source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        sources = client.get("/api/v1/workspaces/ws-1/sources").json()
        assert [s["source_id"] for s in sources] == [new_source_id]
