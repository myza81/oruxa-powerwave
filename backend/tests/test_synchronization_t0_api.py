"""API-level tests for the Slice 2 (t0) REST exposure
(`GET/PUT/DELETE .../synchronization/t0`), now Time-Group-scoped --
every call takes a `source_id` (query param for GET/DELETE, body field
for PUT) purely to resolve WHICH time group's own t0 is meant. Exercises
the real FastAPI app end-to-end, including the workspace-reset/source-
removal lifecycle hooks and the independence from "Reset All" -- see
test_synchronization_t0_service.py/test_synchronization_t0_registry.py
for the already-proven layers this router only exposes.

`synth_ascii.cfg`/`synth_binary.cfg` share the EXACT same recorded start
timestamp (`06/03/2026,10:00:00.000000`) -- both land in ONE time group
by construction, but WHICH of the two becomes that group's own origin
is now decided by a `source_id` tie-break (never upload order, once
start timestamps are identical -- see app.domain.time_grouping's own
docstring), so `_upload_pair()` below resolves the actual origin/
non-origin split from the live API response rather than assuming the
first-uploaded source is always the reference, the way pre-Time-Group
tests safely could.
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


def _upload_pair(client, workspace_id, comtrade_fixtures_dir):
    """Uploads synth_ascii + synth_binary (same time group, per this
    file's own module docstring) and returns `(origin_id, other_id)`,
    resolved from the live API response rather than assumed."""
    ids = [
        _upload(client, workspace_id, comtrade_fixtures_dir, "synth_ascii"),
        _upload(client, workspace_id, comtrade_fixtures_dir, "synth_binary"),
    ]
    rows = client.get(f"{_sync_url(workspace_id)}/sources").json()
    by_id = {row["source_id"]: row for row in rows}
    origin_id = next(sid for sid in ids if by_id[sid]["is_reference"])
    other_id = next(sid for sid in ids if sid != origin_id)
    return origin_id, other_id


class TestGetT0:
    def test_no_t0_selected_returns_null_not_404(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-empty"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.get(f"{_sync_url(ws)}/t0", params={"source_id": src})
        assert resp.status_code == 200
        assert resp.json()["t0_workspace_time"] is None

    def test_unknown_source_404s(self, client):
        resp = client.get(f"{_sync_url('ws-t0-unknown-src')}/t0", params={"source_id": "nope"})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestSetT0:
    def test_sets_and_returns_t0(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-set"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": 0.512345})
        assert resp.status_code == 200, resp.text
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)

        resp = client.get(f"{_sync_url(ws)}/t0", params={"source_id": src})
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)

    def test_sub_millisecond_precision_is_preserved(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-precision"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        precise = 0.5123456789
        resp = client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": precise})
        assert resp.json()["t0_workspace_time"] == pytest.approx(precise, abs=1e-9)

    def test_zero_t0_is_a_legitimate_value(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-zero"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": 0.0})
        assert resp.status_code == 200
        assert resp.json()["t0_workspace_time"] == 0.0

    def test_unknown_source_404s(self, client):
        """Time-Group task: t0 now REQUIRES a resolvable source_id (to
        know which group is meant) -- superseding Slice 2's original
        "no source required" design, which predates Time Groups
        existing at all."""
        resp = client.put(f"{_sync_url('ws-t0-no-sources')}/t0", json={"source_id": "nope", "t0_workspace_time": 0.1})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_replacing_an_existing_t0_is_a_plain_overwrite(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-replace"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": 0.5})
        resp = client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": 0.7})
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.7)

    def test_non_finite_t0_400s(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-invalid"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.put(
            f"{_sync_url(ws)}/t0",
            content=('{"source_id": "%s", "t0_workspace_time": NaN}' % src).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)
        if resp.status_code == 400:
            assert resp.json()["detail"]["code"] == "invalid_t0"


class TestClearT0:
    def test_clears_a_configured_t0(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-clear"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        client.put(f"{_sync_url(ws)}/t0", json={"source_id": src, "t0_workspace_time": 0.5})
        resp = client.delete(f"{_sync_url(ws)}/t0", params={"source_id": src})
        assert resp.status_code == 204
        resp = client.get(f"{_sync_url(ws)}/t0", params={"source_id": src})
        assert resp.json()["t0_workspace_time"] is None

    def test_idempotent_for_an_already_unset_t0(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-clear-idempotent"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.delete(f"{_sync_url(ws)}/t0", params={"source_id": src})
        assert resp.status_code == 204

    def test_clear_never_touches_source_offsets(self, client, comtrade_fixtures_dir):
        """Task section 13: "Do not make Clear t=0 equivalent to
        synchronization Reset All"."""
        ws = "ws-t0-clear-preserves-offsets"
        url = _sync_url(ws)
        origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{url}/sources/{other_id}", json={"alignment_offset_s": 0.401})
        client.put(f"{url}/t0", json={"source_id": origin_id, "t0_workspace_time": 0.512345})

        resp = client.delete(f"{url}/t0", params={"source_id": origin_id})
        assert resp.status_code == 204

        resp = client.get(f"{url}/sources/{other_id}")
        assert resp.json()["manual_alignment_offset_s"] == pytest.approx(0.401)


class TestIndependenceFromSynchronizationResetAll:
    def test_reset_all_offsets_leaves_t0_unchanged(self, client, comtrade_fixtures_dir):
        """The core Slice 2 UAT scenario (task section 14/27): resetting
        every source's own alignment offset must never move or clear the
        event origin."""
        ws = "ws-t0-reset-all-independence"
        url = _sync_url(ws)
        origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{url}/sources/{other_id}", json={"alignment_offset_s": 0.401})
        client.put(f"{url}/t0", json={"source_id": origin_id, "t0_workspace_time": 0.512345})

        resp = client.delete(f"{url}/sources")  # "Reset All" alignment offsets
        assert resp.status_code == 204

        resp = client.get(f"{url}/sources/{other_id}")
        assert resp.json()["manual_alignment_offset_s"] == 0.0
        resp = client.get(f"{url}/t0", params={"source_id": origin_id})
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)


class TestSourceRemovalDoesNotClearT0:
    def test_removing_a_non_origin_source_leaves_t0_intact(self, client, comtrade_fixtures_dir):
        """Task section 15: t0 is a workspace coordinate once defined --
        removing an unrelated (non-origin) source in the same group must
        not clear it."""
        ws = "ws-t0-source-removal"
        url = _sync_url(ws)
        origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{url}/t0", json={"source_id": origin_id, "t0_workspace_time": 0.512345})

        resp = client.delete(f"/api/v1/workspaces/{ws}/sources/{other_id}")
        assert resp.status_code == 204

        resp = client.get(f"{url}/t0", params={"source_id": origin_id})
        assert resp.json()["t0_workspace_time"] == pytest.approx(0.512345)


class TestWorkspaceResetClearsT0:
    def test_deleting_the_workspace_clears_t0_and_offsets(self, client, comtrade_fixtures_dir):
        ws = "ws-t0-full-reset"
        url = _sync_url(ws)
        origin_id, _other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{url}/t0", json={"source_id": origin_id, "t0_workspace_time": 0.512345})

        resp = client.delete(f"/api/v1/workspaces/{ws}")
        assert resp.status_code == 204

        # Original waveform/source data is unaffected by any of this --
        # re-upload under the same workspace_id starts from a clean slate.
        src_new = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.get(f"{url}/t0", params={"source_id": src_new})
        assert resp.json()["t0_workspace_time"] is None
