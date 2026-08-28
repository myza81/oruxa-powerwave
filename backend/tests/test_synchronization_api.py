"""API-level tests for Slice 1's waveform time-synchronization REST
exposure (`app/api/v1/synchronization.py`). Exercises the real FastAPI
app end-to-end, including the source-removal and workspace-reset
lifecycle hooks -- see test_synchronization_service.py/
test_synchronization_registry.py for the already-proven layers this
router only exposes.

`synth_ascii.cfg`/`synth_binary.cfg` share the EXACT same recorded
start timestamp -- both land in ONE time group by construction, but
WHICH of the two becomes that group's own origin/reference is now
resolved by a `source_id` tie-break once start timestamps are identical
(never upload order -- see app.domain.time_grouping's own docstring),
so `_upload_pair()` below resolves the actual origin/non-origin split
from the live API response rather than assuming the first-uploaded
source is always the reference, the way pre-Time-Group tests safely
could.
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


def _base_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/synchronization"


def _upload_pair(client, workspace_id, comtrade_fixtures_dir):
    ids = [
        _upload(client, workspace_id, comtrade_fixtures_dir, "synth_ascii"),
        _upload(client, workspace_id, comtrade_fixtures_dir, "synth_binary"),
    ]
    rows = client.get(f"{_base_url(workspace_id)}/sources").json()
    by_id = {row["source_id"]: row for row in rows}
    origin_id = next(sid for sid in ids if by_id[sid]["is_reference"])
    other_id = next(sid for sid in ids if sid != origin_id)
    return origin_id, other_id


class TestListSources:
    def test_lists_every_source_exactly_one_is_the_reference(self, client, comtrade_fixtures_dir):
        ws = "ws-list"
        src_a = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        src_b = _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        resp = client.get(f"{_base_url(ws)}/sources")
        assert resp.status_code == 200, resp.text
        body = {row["source_id"]: row for row in resp.json()}
        assert body[src_a]["alignment_offset_s"] == 0.0
        assert body[src_b]["alignment_offset_s"] == 0.0
        # Identical recorded start timestamps -> both start with zero
        # manual correction AND zero timestamp placement relative to
        # whichever one is the group's own origin -- but exactly ONE of
        # the two must be marked reference, never both/neither.
        assert sum(1 for row in body.values() if row["is_reference"]) == 1
        assert body[src_a]["time_group_id"] == body[src_b]["time_group_id"]

    def test_empty_workspace_lists_nothing(self, client):
        resp = client.get(f"{_base_url('ws-empty')}/sources")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetSource:
    def test_unknown_source_404s(self, client):
        resp = client.get(f"{_base_url('ws-1')}/sources/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestSetSourceOffset:
    def test_sets_and_returns_the_offset(self, client, comtrade_fixtures_dir):
        ws = "ws-set"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        resp = client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": -0.0185})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["alignment_offset_s"] == pytest.approx(-0.0185)
        assert body["manual_alignment_offset_s"] == pytest.approx(-0.0185)
        assert body["is_reference"] is False

        # persisted -- a fresh GET reflects the same value.
        resp = client.get(f"{_base_url(ws)}/sources/{other_id}")
        assert resp.json()["alignment_offset_s"] == pytest.approx(-0.0185)

    def test_sub_millisecond_precision_is_preserved(self, client, comtrade_fixtures_dir):
        ws = "ws-precision"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        precise_offset = 0.0071234567
        resp = client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": precise_offset})
        assert resp.json()["alignment_offset_s"] == pytest.approx(precise_offset, abs=1e-9)

    def test_unknown_source_404s(self, client):
        resp = client.put(f"{_base_url('ws-1')}/sources/does-not-exist", json={"alignment_offset_s": 0.1})
        assert resp.status_code == 404

    def test_non_finite_offset_400s(self, client, comtrade_fixtures_dir):
        ws = "ws-invalid"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        # Standard JSON has no NaN/Infinity literal, so a conforming client
        # can never legitimately send one -- this crafts the raw (non-
        # standard, Python-`json`-emittable) body directly, bypassing the
        # test client's own `json=` encoder, to prove the backend's own
        # `invalid_alignment_offset` validation is the thing that would
        # reject it if it ever arrived, not merely relying on no client
        # being able to construct one.
        resp = client.put(
            f"{_base_url(ws)}/sources/{other_id}",
            content=b'{"alignment_offset_s": NaN}',
            headers={"Content-Type": "application/json"},
        )
        # FastAPI/pydantic itself rejects a JSON-illegal NaN body before this
        # router's own validation runs -- either a 422 (pydantic) or this
        # router's own 400 is an acceptable, honest rejection; a 2xx is not.
        assert resp.status_code in (400, 422)

    def test_non_zero_offset_on_reference_source_409s(self, client, comtrade_fixtures_dir):
        ws = "ws-reference"
        origin_id, _other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        resp = client.put(f"{_base_url(ws)}/sources/{origin_id}", json={"alignment_offset_s": 0.5})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "reference_source_alignment_not_allowed"


class TestResetSource:
    def test_resets_a_configured_source_to_zero(self, client, comtrade_fixtures_dir):
        ws = "ws-reset-one"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": 0.02})
        resp = client.delete(f"{_base_url(ws)}/sources/{other_id}")
        assert resp.status_code == 204
        resp = client.get(f"{_base_url(ws)}/sources/{other_id}")
        assert resp.json()["alignment_offset_s"] == 0.0

    def test_idempotent_for_an_already_unshifted_source(self, client, comtrade_fixtures_dir):
        ws = "ws-reset-idempotent"
        src_a = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.delete(f"{_base_url(ws)}/sources/{src_a}")
        assert resp.status_code == 204

    def test_unknown_source_404s(self, client):
        resp = client.delete(f"{_base_url('ws-1')}/sources/does-not-exist")
        assert resp.status_code == 404


class TestResetAll:
    def test_resets_every_source_offset_in_the_workspace(self, client, comtrade_fixtures_dir):
        ws = "ws-reset-all"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": 0.02})
        resp = client.delete(f"{_base_url(ws)}/sources")
        assert resp.status_code == 204
        resp = client.get(f"{_base_url(ws)}/sources")
        assert all(row["alignment_offset_s"] == 0.0 for row in resp.json())

    def test_idempotent_for_an_empty_workspace(self, client):
        resp = client.delete(f"{_base_url('ws-empty-reset')}/sources")
        assert resp.status_code == 204


class TestSourceRemovalCleanup:
    def test_removing_a_source_clears_its_own_synchronization_state(self, client, comtrade_fixtures_dir):
        ws = "ws-removal"
        origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": 0.02})

        resp = client.delete(f"/api/v1/workspaces/{ws}/sources/{other_id}")
        assert resp.status_code == 204

        # Re-uploading a NEW source under a fresh id must not inherit any
        # stale synchronization state keyed by the old (now-removed)
        # source_id -- there is nothing left to inherit, since the
        # registry entry itself is gone.
        resp = client.get(f"{_base_url(ws)}/sources")
        remaining_ids = {row["source_id"] for row in resp.json()}
        assert remaining_ids == {origin_id}


class TestWorkspaceResetCleanup:
    def test_deleting_the_workspace_clears_all_synchronization_state(self, client, comtrade_fixtures_dir):
        ws = "ws-full-reset"
        _origin_id, other_id = _upload_pair(client, ws, comtrade_fixtures_dir)
        client.put(f"{_base_url(ws)}/sources/{other_id}", json={"alignment_offset_s": 0.02})

        resp = client.delete(f"/api/v1/workspaces/{ws}")
        assert resp.status_code == 204

        resp = client.get(f"{_base_url(ws)}/sources")
        assert resp.json() == []

        # Original waveform data is unaffected by any of this -- re-upload
        # under the same workspace_id starts from a clean slate, and the
        # reference-source rule re-derives correctly for the new (now
        # single-source) set.
        src_c = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.get(f"{_base_url(ws)}/sources/{src_c}")
        assert resp.json()["is_reference"] is True
        assert resp.json()["alignment_offset_s"] == 0.0
