"""API-level tests for Slice 3's assisted event-origin detection
(`POST .../synchronization/detect-event`). Exercises the real FastAPI
app end-to-end -- see test_event_detection_service.py/
test_event_detection_domain.py for the already-proven detection-quality
coverage (large synthetic waveforms); this file focuses on HTTP
plumbing/error-code correctness using the small real COMTRADE fixtures
already shared by every other synchronization API test.
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


class TestDetectEventPlumbing:
    def test_short_fixture_returns_found_false_not_an_error(self, client, comtrade_fixtures_dir):
        """The shared synth_ascii fixture is only ~10ms long -- far
        short of one full cycle at 50 Hz, so this exercises the
        detector's own graceful "too short" edge case through the real
        HTTP boundary (task section 28/29: never an error, never a
        fabricated candidate)."""
        ws = "ws-detect-short"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src, "channel_name": "VA"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["found"] is False
        assert body["candidate_source_time"] is None
        assert body["candidate_workspace_time"] is None
        assert isinstance(body["reason"], str) and body["reason"]
        assert body["detector_method"] == "rms_sustained_change"
        assert body["channel_unit"] == "V"
        assert body["nominal_frequency_hz"] == 50.0

    def test_default_sensitivity_is_normal(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-default-sensitivity"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src, "channel_name": "VA"})
        assert resp.status_code == 200
        resp2 = client.post(
            f"{_sync_url(ws)}/detect-event",
            json={"source_id": src, "channel_name": "VA", "sensitivity": "normal"},
        )
        assert resp.json() == resp2.json()

    def test_unknown_source_404s(self, client):
        resp = client.post(
            f"{_sync_url('ws-detect-nosource')}/detect-event",
            json={"source_id": "does-not-exist", "channel_name": "VA"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_unknown_channel_404s(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-nochannel"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src, "channel_name": "NOPE"})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_digital_channel_400s_as_channel_not_analog(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-digital"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src, "channel_name": "BRK_A"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_analog"

    def test_invalid_sensitivity_400s(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-badsens"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        resp = client.post(
            f"{_sync_url(ws)}/detect-event",
            json={"source_id": src, "channel_name": "VA", "sensitivity": "extreme"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_sensitivity"


class TestDetectEventNeverMutatesSynchronizationState:
    """Task section 26: "Do not make this endpoint set t0
    automatically... acceptance should call the existing t0 endpoint
    separately." Verified through the real HTTP boundary."""

    def test_running_detection_leaves_t0_unset(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-no-t0-mutation"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src, "channel_name": "VA"})
        resp = client.get(f"{_sync_url(ws)}/t0")
        assert resp.json()["t0_workspace_time"] is None

    def test_running_detection_leaves_alignment_offset_unchanged(self, client, comtrade_fixtures_dir):
        ws = "ws-detect-no-offset-mutation"
        src = _upload(client, ws, comtrade_fixtures_dir, "synth_ascii")
        src_b = _upload(client, ws, comtrade_fixtures_dir, "synth_binary")
        client.put(f"{_sync_url(ws)}/sources/{src_b}", json={"alignment_offset_s": 0.2})

        client.post(f"{_sync_url(ws)}/detect-event", json={"source_id": src_b, "channel_name": "VA"})

        resp = client.get(f"{_sync_url(ws)}/sources/{src_b}")
        assert resp.json()["alignment_offset_s"] == pytest.approx(0.2)
