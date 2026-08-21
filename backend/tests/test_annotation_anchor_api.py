"""API-level tests for POST .../sources/{source_id}/annotation-anchor
(Phase 4F -- Callout annotation anchor resolution, DEC-045).

Exercises the real end-to-end flow (upload -> parse -> retain -> anchor
resolution) through a fully wired FastAPI TestClient, same pattern as
tests/test_cursor_values_api.py. The synth_ascii fixture: analog channels
VA/VB/IA, 40 samples at 4000 Hz (250 microsecond spacing) -- sample index 4
(0-based) lands exactly at t=0.001s with VA=400.0, VB=-400.0, IA=2.0, used
below as a known, hand-verifiable anchor point. BRK_A is a digital channel
on the same fixture, used to confirm analog-only validation.
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


def _anchor(client, workspace_id, source_id, **body):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/annotation-anchor",
        json=body,
    )


class TestValidRequests:
    def test_click_near_known_anchor_sample_resolves_exact_hand_verified_values(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        # 0.00092s is between sample 3 (0.00075s) and sample 4 (0.001s),
        # closer to sample 4 -- must snap there, not interpolate.
        resp = _anchor(client, "ws-1", source_id, channel_name="VA", approximate_elapsed_seconds=0.00092)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["channel_name"] == "VA"
        assert body["sample_index"] == 4
        assert body["elapsed_seconds"] == pytest.approx(0.001)
        assert body["value"] == pytest.approx(400.0)
        assert body["unit"] == "V"

    def test_exact_sample_time_resolves_to_itself(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", source_id, channel_name="IA", approximate_elapsed_seconds=0.001)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["value"] == pytest.approx(2.0)
        assert body["unit"] == "A"


class TestChannelValidation:
    def test_unknown_channel_name_returns_404_channel_not_found(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", source_id, channel_name="NOT_A_REAL_CHANNEL", approximate_elapsed_seconds=0.001)

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_digital_channel_name_returns_400_channel_not_analog(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", source_id, channel_name="BRK_A", approximate_elapsed_seconds=0.001)

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_analog"


class TestOutOfBounds:
    def test_time_beyond_source_end_returns_400_invalid_time_range(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", source_id, channel_name="VA", approximate_elapsed_seconds=999.0)

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_time_range"

    def test_time_before_source_start_returns_400_invalid_time_range(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", source_id, channel_name="VA", approximate_elapsed_seconds=-1.0)

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_time_range"


class TestSourceIdentity:
    def test_unknown_source_id_returns_404(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _anchor(client, "ws-1", "does-not-exist", channel_name="VA", approximate_elapsed_seconds=0.001)

        assert resp.status_code == 404

    def test_two_sources_with_the_same_channel_name_never_collide(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        assert source_a != source_b

        resp_a = _anchor(client, "ws-1", source_a, channel_name="VA", approximate_elapsed_seconds=0.001)
        resp_b = _anchor(client, "ws-1", source_b, channel_name="VA", approximate_elapsed_seconds=0.001)

        assert resp_a.json()["source_id"] == source_a
        assert resp_b.json()["source_id"] == source_b
        assert resp_a.json()["value"] == pytest.approx(resp_b.json()["value"])
