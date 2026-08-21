"""API-level tests for POST .../sources/{source_id}/peak-values
(Phase 4G -- Maximum/Minimum Peak annotations, DEC-046).

Exercises the real end-to-end flow through a fully wired FastAPI
TestClient, same pattern as tests/test_annotation_anchor_api.py. The
synth_ascii fixture: analog channels VA/VB/IA, 40 samples at 4000 Hz (250
microsecond spacing), BRK_A is digital.
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


def _peaks(client, workspace_id, source_id, requests, start_time, end_time):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/peak-values",
        json={"requests": requests, "start_time": start_time, "end_time": end_time},
    )


class TestValidRequests:
    def test_single_channel_max_over_full_record(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(client, "ws-1", source_id, [{"channel_name": "VA", "mode": "max"}], 0.0, 0.01)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert len(body["results"]) == 1
        result = body["results"][0]
        assert result["channel_name"] == "VA"
        assert result["mode"] == "max"
        assert result["available"] is True
        assert result["unit"] == "V"
        assert result["value"] is not None
        assert result["sample_index"] is not None
        assert result["elapsed_seconds"] is not None

    def test_batched_multi_channel_multi_mode_one_request(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(
            client,
            "ws-1",
            source_id,
            [
                {"channel_name": "VA", "mode": "max"},
                {"channel_name": "VA", "mode": "min"},
                {"channel_name": "VB", "mode": "max"},
                {"channel_name": "IA", "mode": "min"},
            ],
            0.0,
            0.01,
        )

        assert resp.status_code == 200, resp.text
        results = resp.json()["results"]
        assert len(results) == 4
        assert [r["channel_name"] for r in results] == ["VA", "VA", "VB", "IA"]
        assert [r["mode"] for r in results] == ["max", "min", "max", "min"]
        assert all(r["available"] for r in results)


class TestNarrowWindow:
    def test_narrow_window_returns_local_not_global_extremum(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        full = _peaks(client, "ws-1", source_id, [{"channel_name": "VA", "mode": "max"}], 0.0, 0.01).json()["results"][0]
        narrow = _peaks(client, "ws-1", source_id, [{"channel_name": "VA", "mode": "max"}], 0.0, 0.0005).json()["results"][0]

        assert narrow["available"] is True
        # A narrower window's max can never exceed the full window's max.
        assert narrow["value"] <= full["value"] + 1e-9


class TestChannelValidation:
    def test_unknown_channel_marks_that_item_unavailable_not_whole_batch(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(
            client,
            "ws-1",
            source_id,
            [{"channel_name": "NOT_A_REAL_CHANNEL", "mode": "max"}, {"channel_name": "VA", "mode": "max"}],
            0.0,
            0.01,
        )

        assert resp.status_code == 200, resp.text
        results = resp.json()["results"]
        assert results[0]["available"] is False
        assert results[0]["value"] is None
        assert results[1]["available"] is True

    def test_digital_channel_marks_that_item_unavailable(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(client, "ws-1", source_id, [{"channel_name": "BRK_A", "mode": "max"}], 0.0, 0.01)

        assert resp.status_code == 200, resp.text
        result = resp.json()["results"][0]
        assert result["available"] is False


class TestSharedIntervalValidation:
    def test_start_after_end_returns_400_invalid_time_range_for_whole_batch(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(client, "ws-1", source_id, [{"channel_name": "VA", "mode": "max"}], 0.01, 0.0)

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_time_range"


class TestSourceIdentity:
    def test_unknown_source_id_returns_404(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _peaks(client, "ws-1", "does-not-exist", [{"channel_name": "VA", "mode": "max"}], 0.0, 0.01)

        assert resp.status_code == 404

    def test_two_sources_never_collide(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp_a = _peaks(client, "ws-1", source_a, [{"channel_name": "VA", "mode": "max"}], 0.0, 0.01)
        resp_b = _peaks(client, "ws-1", source_b, [{"channel_name": "VA", "mode": "max"}], 0.0, 0.01)

        assert resp_a.json()["source_id"] == source_a
        assert resp_b.json()["source_id"] == source_b
        assert resp_a.json()["results"][0]["value"] == pytest.approx(resp_b.json()["results"][0]["value"])
