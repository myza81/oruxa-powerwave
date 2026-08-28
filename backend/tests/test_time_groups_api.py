"""API-level tests for `GET .../synchronization/time-groups`. Exercises
the real FastAPI app end-to-end -- see test_time_grouping_service.py/
test_time_grouping_domain.py for the already-proven layers this router
only exposes.
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


def _upload(client, workspace_id, comtrade_fixtures_dir, stem):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/synchronization/time-groups"


class TestGetTimeGroups:
    def test_empty_workspace_returns_no_groups(self, client):
        resp = client.get(_url("ws-tg-empty"))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_two_sources_with_identical_start_share_one_group(self, client, comtrade_fixtures_dir):
        ws = "ws-tg-same-start"
        src_a = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        src_b = _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        resp = client.get(_url(ws))
        assert resp.status_code == 200
        groups = resp.json()
        assert len(groups) == 1
        group = groups[0]
        assert set(group["source_ids"]) == {src_a, src_b}
        assert group["time_reference_type"] == "recorded_absolute"
        assert group["group_id"] == group["origin_source_id"]
        assert group["group_id"] in {src_a, src_b}
        assert group["note"] is None

    def test_group_id_matches_the_is_reference_flag_on_sources_endpoint(self, client, comtrade_fixtures_dir):
        ws = "ws-tg-cross-check"
        _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        _upload(client, ws, comtrade_fixtures_dir, "synth_binary")

        groups = client.get(_url(ws)).json()
        sources = client.get(f"/api/v1/workspaces/{ws}/synchronization/sources").json()

        origin_id = groups[0]["origin_source_id"]
        by_id = {row["source_id"]: row for row in sources}
        assert by_id[origin_id]["is_reference"] is True
        assert by_id[origin_id]["time_group_id"] == groups[0]["group_id"]
