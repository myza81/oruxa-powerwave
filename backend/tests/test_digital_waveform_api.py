"""API-level tests for GET .../sources/{source_id}/digital-waveform (Phase
4A) and the `classification` field on GET .../channels' digital channels.

Exercises the real end-to-end flow (upload -> parse -> classify at import
-> digital-waveform request) through a fully wired FastAPI TestClient,
same pattern as tests/test_waveform_api.py. The synth_ascii fixture's two
real digital channels (BRK_A, BRK_B) both transition 0->1 partway through
the record (confirmed in test_comtrade_provider.py), so both classify as
"triggered" -- sufficient to verify end-to-end wiring; the full
classification precedence matrix (Spare/Never Triggered/always-high) is
exhaustively covered as pure-function tests in
test_digital_classification.py, not re-derived here.
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


class TestChannelsClassificationField:
    def test_digital_channels_carry_classification_from_channels_endpoint(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels")

        assert resp.status_code == 200, resp.text
        digital = {c["name"]: c for c in resp.json()["digital_channels"]}
        assert digital["BRK_A"]["classification"] == "triggered"
        assert digital["BRK_B"]["classification"] == "triggered"


class TestValidDigitalWaveformRequests:
    def test_single_channel_returns_transition_list(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["BRK_A"]},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["channels"]) == 1
        chan = body["channels"][0]
        assert chan["source_id"] == source_id
        assert chan["channel_name"] == "BRK_A"
        assert chan["classification"] == "triggered"
        assert chan["initial_state"] == 0
        assert chan["sample_count"] == 40
        # BRK_A goes high at sample index 20 of a 4000 Hz, 40-sample
        # record (confirmed in test_comtrade_provider.py) -> transition
        # at t = 20/4000 = 0.005s, to state 1.
        assert len(chan["transitions"]) >= 1
        first_transition = chan["transitions"][0]
        assert first_transition["time"] == pytest.approx(0.005)
        assert first_transition["state"] == 1

    def test_batch_request_returns_all_channels_in_requested_order(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["BRK_B", "BRK_A"]},
        )

        assert resp.status_code == 200, resp.text
        names = [c["channel_name"] for c in resp.json()["channels"]]
        assert names == ["BRK_B", "BRK_A"]

    def test_transitions_preserve_exact_timing_not_reduced(self, client, comtrade_fixtures_dir):
        # BRK_B transitions at sample index 10 -> t = 10/4000 = 0.0025s.
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["BRK_B"]},
        )

        assert resp.status_code == 200, resp.text
        chan = resp.json()["channels"][0]
        assert chan["transitions"][0]["time"] == pytest.approx(0.0025)
        assert chan["transitions"][0]["state"] == 1


class TestDigitalWaveformErrors:
    def test_unknown_channel_name_returns_404(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["NOT_A_REAL_CHANNEL"]},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_analog_channel_name_rejected_as_channel_not_digital(
        self, client, comtrade_fixtures_dir
    ):
        # Symmetric with test_waveform_api.py's own
        # test_digital_channel_name_rejected_as_channel_not_analog.
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/digital-waveform",
            params={"channel_names": ["VA"]},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_digital"

    def test_unknown_source_returns_404(self, client):
        resp = client.get(
            "/api/v1/workspaces/ws-1/sources/does-not-exist/digital-waveform",
            params={"channel_names": ["BRK_A"]},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"


class TestSourceIsolation:
    def test_two_sources_digital_data_does_not_leak(self, client, comtrade_fixtures_dir):
        # Section 63: classification/digital state for one source must
        # never leak into another's response.
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        assert source_a != source_b

        resp_a = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_a}/digital-waveform",
            params={"channel_names": ["BRK_A"]},
        )
        resp_b = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_b}/digital-waveform",
            params={"channel_names": ["BRK_A"]},
        )

        assert resp_a.status_code == 200 and resp_b.status_code == 200
        assert resp_a.json()["channels"][0]["source_id"] == source_a
        assert resp_b.json()["channels"][0]["source_id"] == source_b
