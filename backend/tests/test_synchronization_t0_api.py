"""API-level tests for the Slice 2 (t0) REST exposure
(`GET/PUT/DELETE .../synchronization/t0`). Exercises the real FastAPI
app end-to-end, including the workspace-reset/source-removal lifecycle
hooks and the independence from "Reset All" -- see
test_synchronization_t0_service.py/test_synchronization_t0_registry.py
for the already-proven layers this router only exposes.
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


def _sync_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/synchronization"


class TestGetT0:
    def test_no_t0_selected_returns_null_not_404(self, client):
        resp = client.get(f"{_sync_url('ws-t0-empty')}/t0")
        assert resp.status_code == 200
        assert resp.json() == {"t0_workspace_time": None}


class TestSetT0:
    def test_sets_and_returns_t0(self, client):
        resp = client.put(f"{_sync_url('ws-t0-set')}/t0", json={"t0_workspace_time": 0.512345})
        assert resp.status_code == 200, resp.text
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)

        resp = client.get(f"{_sync_url('ws-t0-set')}/t0")
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)

    def test_sub_millisecond_precision_is_preserved(self, client):
        precise = 0.5123456789
        resp = client.put(f"{_sync_url('ws-t0-precision')}/t0", json={"t0_workspace_time": precise})
        assert resp.json()["t0_workspace_time"] == pytest.approx(precise, abs=1e-9)

    def test_zero_t0_is_a_legitimate_value(self, client):
        resp = client.put(f"{_sync_url('ws-t0-zero')}/t0", json={"t0_workspace_time": 0.0})
        assert resp.status_code == 200
        assert resp.json()["t0_workspace_time"] == 0.0

    def test_does_not_require_any_source_to_exist(self, client):
        """t0 is a pure workspace-time coordinate -- a workspace with no
        uploaded sources at all can still have a t0 set."""
        resp = client.put(f"{_sync_url('ws-t0-no-sources')}/t0", json={"t0_workspace_time": 0.1})
        assert resp.status_code == 200

    def test_replacing_an_existing_t0_is_a_plain_overwrite(self, client):
        url = _sync_url("ws-t0-replace")
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.5})
        resp = client.put(f"{url}/t0", json={"t0_workspace_time": 0.7})
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.7)

    def test_non_finite_t0_400s(self, client):
        resp = client.put(
            f"{_sync_url('ws-t0-invalid')}/t0",
            content=b'{"t0_workspace_time": NaN}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)
        if resp.status_code == 400:
            assert resp.json()["detail"]["code"] == "invalid_t0"


class TestClearT0:
    def test_clears_a_configured_t0(self, client):
        url = _sync_url("ws-t0-clear")
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.5})
        resp = client.delete(f"{url}/t0")
        assert resp.status_code == 204
        resp = client.get(f"{url}/t0")
        assert resp.json()["t0_workspace_time"] is None

    def test_idempotent_for_an_already_unset_t0(self, client):
        resp = client.delete(f"{_sync_url('ws-t0-clear-idempotent')}/t0")
        assert resp.status_code == 204

    def test_clear_never_touches_source_offsets(self, client, comtrade_fixtures_dir):
        """Task section 13: "Do not make Clear t=0 equivalent to
        synchronization Reset All"."""
        ws = "ws-t0-clear-preserves-offsets"
        url = _sync_url(ws)
        _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        src_b = _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        client.put(f"{url}/sources/{src_b}", json={"alignment_offset_s": 0.401})
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.512345})

        resp = client.delete(f"{url}/t0")
        assert resp.status_code == 204

        resp = client.get(f"{url}/sources/{src_b}")
        assert resp.json()["alignment_offset_s"] == pytest.approx(0.401)


class TestIndependenceFromSynchronizationResetAll:
    def test_reset_all_offsets_leaves_t0_unchanged(self, client, comtrade_fixtures_dir):
        """The core Slice 2 UAT scenario (task section 14/27): resetting
        every source's own alignment offset must never move or clear the
        event origin."""
        ws = "ws-t0-reset-all-independence"
        url = _sync_url(ws)
        _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        src_b = _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        client.put(f"{url}/sources/{src_b}", json={"alignment_offset_s": 0.401})
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.512345})

        resp = client.delete(f"{url}/sources")  # "Reset All" alignment offsets
        assert resp.status_code == 204

        resp = client.get(f"{url}/sources/{src_b}")
        assert resp.json()["alignment_offset_s"] == 0.0
        resp = client.get(f"{url}/t0")
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)


class TestSourceRemovalDoesNotClearT0:
    def test_removing_the_source_that_helped_select_t0_leaves_it_intact(self, client, comtrade_fixtures_dir):
        """Task section 15: t0 is a workspace coordinate once defined --
        removing whichever source's cursor originally helped select it
        must not clear it."""
        ws = "ws-t0-source-removal"
        url = _sync_url(ws)
        src_a = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.512345})

        resp = client.delete(f"/api/v1/workspaces/{ws}/sources/{src_a}")
        assert resp.status_code == 204

        resp = client.get(f"{url}/t0")
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)


class TestWorkspaceResetClearsT0:
    def test_deleting_the_workspace_clears_t0_and_offsets(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-full-reset"
        url = _sync_url(ws)
        src_a = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        client.put(f"{url}/t0", json={"t0_workspace_time": 0.512345})

        resp = client.delete(f"/api/v1/workspaces/{ws}")
        assert resp.status_code == 204

        resp = client.get(f"{url}/t0")
        assert resp.json()["t0_workspace_time"] is None

        # Original waveform/source data is unaffected by any of this --
        # re-upload under the same workspace_id starts from a clean slate.
        src_new = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        assert src_new != src_a
        resp = client.get(f"{url}/t0")
        assert resp.json()["t0_workspace_time"] is None
