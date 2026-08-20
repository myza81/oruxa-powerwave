"""API-level tests for POST .../sources/{source_id}/cursor-values (Phase 4C1).

Exercises the real end-to-end flow (upload -> parse -> retain -> cursor-
values request) through a fully wired FastAPI TestClient, same pattern as
tests/test_waveform_api.py. The synth_ascii fixture: analog channels
VA/VB/IA, 40 samples at 4000 Hz (250 microsecond spacing), scale 0.1/0.1/0.01
respectively (see the .cfg fixture) -- sample index 4 (0-based) lands
exactly at t=0.001s with VA=400.0, VB=-400.0, IA=2.0, used below as a known,
hand-verifiable anchor point.
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


def _cursor_values(client, workspace_id, source_id, **body):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/cursor-values",
        json=body,
    )


class TestValidRequests:
    def test_known_anchor_sample_returns_exact_hand_verified_values(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA", "VB", "IA"], cursor_a_time=0.001, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["cursor_a"]["sample_time"] == pytest.approx(0.001)
        assert body["cursor_b"] is None
        by_name = {c["channel_name"]: c for c in body["channels"]}
        assert by_name["VA"]["a_value"] == pytest.approx(400.0)
        assert by_name["VB"]["a_value"] == pytest.approx(-400.0)
        assert by_name["IA"]["a_value"] == pytest.approx(2.0)
        assert by_name["VA"]["unit"] == "V"
        assert by_name["IA"]["unit"] == "A"
        # cursor_b was not supplied -- every channel's own b_value is null.
        assert all(c["b_value"] is None for c in body["channels"])

    def test_both_cursors_in_one_request(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA"], cursor_a_time=0.0, cursor_b_time=0.001,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        va = body["channels"][0]
        assert va["a_value"] == pytest.approx(0.0)  # first sample, raw 0 * 0.1
        assert va["b_value"] == pytest.approx(400.0)

    def test_batched_request_covers_every_requested_channel_in_one_call(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA", "VB", "IA"], cursor_a_time=0.001, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        assert len(resp.json()["channels"]) == 3


class TestBoundsAndUnknownChannels:
    def test_cursor_time_beyond_source_end_returns_null_not_clamped(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA"], cursor_a_time=999.0, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cursor_a"]["sample_time"] is None
        assert body["channels"][0]["a_value"] is None

    def test_unknown_channel_name_is_silently_omitted(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA", "NOT_A_REAL_CHANNEL"], cursor_a_time=0.001, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        names = [c["channel_name"] for c in resp.json()["channels"]]
        assert names == ["VA"]

    def test_digital_channel_name_is_silently_omitted(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA", "BRK_A"], cursor_a_time=0.001, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        names = [c["channel_name"] for c in resp.json()["channels"]]
        assert names == ["VA"]


class TestSourceIdentity:
    def test_unknown_source_id_returns_404(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", "does-not-exist",
            analog_channel_names=["VA"], cursor_a_time=0.001, cursor_b_time=None,
        )

        assert resp.status_code == 404

    def test_two_sources_with_the_same_channel_name_never_collide(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        assert source_a != source_b

        resp_a = _cursor_values(
            client, "ws-1", source_a, analog_channel_names=["VA"], cursor_a_time=0.001, cursor_b_time=None
        )
        resp_b = _cursor_values(
            client, "ws-1", source_b, analog_channel_names=["VA"], cursor_a_time=0.001, cursor_b_time=None
        )
        assert resp_a.json()["source_id"] == source_a
        assert resp_b.json()["source_id"] == source_b
        # Same fixture uploaded twice -- values agree, but each response is
        # scoped to its own source_id (identity, not a shared cache key).
        assert resp_a.json()["channels"][0]["a_value"] == pytest.approx(
            resp_b.json()["channels"][0]["a_value"]
        )


class TestNeitherCursorSupplied:
    def test_empty_cursor_request_still_succeeds_with_null_values(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(client, "ws-1", source_id, analog_channel_names=["VA"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cursor_a"] is None
        assert body["cursor_b"] is None
        assert body["channels"][0]["a_value"] is None
        assert body["channels"][0]["b_value"] is None


class TestDigitalValidRequests:
    """Phase 4C2. synth_ascii's own digital channels: BRK_A transitions
    0 -> 1 exactly at sample index 20 (t=0.005s); BRK_B transitions 0 -> 1
    exactly at sample index 10 (t=0.0025s) -- both hand-verified directly
    against synth_ascii.dat."""

    def test_exact_transition_timestamp_reads_the_new_state(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A"], cursor_a_time=0.005, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["digital_channels"][0]["a_state"] == 1

    def test_sample_just_before_transition_reads_the_old_state(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A"], cursor_a_time=0.00475, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["digital_channels"][0]["a_state"] == 0

    def test_analog_and_digital_channels_batched_in_one_request(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            analog_channel_names=["VA"], digital_channel_names=["BRK_A", "BRK_B"],
            cursor_a_time=0.005, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["channels"][0]["a_value"] == pytest.approx(0.0)  # VA raw 0 at index 20
        by_name = {c["channel_name"]: c for c in body["digital_channels"]}
        assert by_name["BRK_A"]["a_state"] == 1
        assert by_name["BRK_B"]["a_state"] == 1  # already flipped earlier, at t=0.0025s

    def test_digital_state_is_plain_integer_in_the_json_response(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A"], cursor_a_time=0.005, cursor_b_time=None,
        )

        state = resp.json()["digital_channels"][0]["a_state"]
        assert isinstance(state, int) and not isinstance(state, bool)


class TestDigitalBoundsAndUnknownChannels:
    def test_digital_cursor_time_beyond_source_end_returns_null_not_clamped(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A"], cursor_a_time=999.0, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["digital_channels"][0]["a_state"] is None

    def test_unknown_digital_channel_name_is_silently_omitted(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A", "NOT_A_REAL_CHANNEL"], cursor_a_time=0.005, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        names = [c["channel_name"] for c in resp.json()["digital_channels"]]
        assert names == ["BRK_A"]

    def test_analog_channel_name_passed_as_digital_is_silently_omitted(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = _cursor_values(
            client, "ws-1", source_id,
            digital_channel_names=["BRK_A", "VA"], cursor_a_time=0.005, cursor_b_time=None,
        )

        assert resp.status_code == 200, resp.text
        names = [c["channel_name"] for c in resp.json()["digital_channels"]]
        assert names == ["BRK_A"]
