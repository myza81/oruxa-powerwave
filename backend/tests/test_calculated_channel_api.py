"""API-level tests for the Phase 5A Calculated Channels endpoints
(DEC-047). Exercises the real end-to-end flow (upload -> parse -> retain
-> calculate) through a fully wired FastAPI TestClient, same pattern as
tests/test_peak_value_api.py / test_annotation_anchor_api.py. The
synth_ascii fixture: analog channels VA/VB/IA, 40 samples at 4000 Hz.
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


def _create(client, workspace_id, **body):
    return client.post(f"/api/v1/workspaces/{workspace_id}/calculated-channels", json=body)


class TestCreateBasicOperations:
    def test_reverse_polarity(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="-VA", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "-VA"
        assert body["operation"] == "reverse_polarity"
        assert body["unit"] == "V"
        assert body["sample_count"] == 40
        # Phase 5A-UAT4: additive field -- VA's own "V" unit classifies
        # as Voltage (app.domain.channel_classification), inherited here.
        assert body["engineering_type"] == "Voltage"

    def test_absolute_value(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="Abs(VA)", operation="absolute_value",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        )
        assert resp.status_code == 201, resp.text

    def test_multiply_by_constant(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="2xVA", operation="multiply_constant",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"constant": -2.5},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["parameters"] == {"constant": -2.5}

    def test_addition_two_channels(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="VA+VB", operation="addition",
            inputs=[
                {"kind": "source", "source_id": source_id, "channel_name": "VA"},
                {"kind": "source", "source_id": source_id, "channel_name": "VB"},
            ],
        )
        assert resp.status_code == 201, resp.text

    def test_subtraction_two_channels(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="VA-VB", operation="subtraction",
            inputs=[
                {"kind": "source", "source_id": source_id, "channel_name": "VA"},
                {"kind": "source", "source_id": source_id, "channel_name": "VB"},
            ],
        )
        assert resp.status_code == 201, resp.text

    def test_no_rms_operation_accepted(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="RMS", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        )
        assert resp.status_code == 422  # pydantic Literal rejects an unsupported operation outright


class TestListAndDelete:
    def test_created_channel_appears_in_list_immediately(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _create(
            client, "ws-1", name="-VA", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        )
        resp = client.get("/api/v1/workspaces/ws-1/calculated-channels")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert "-VA" in names

    def test_delete_removes_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create(
            client, "ws-1", name="-VA", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        ).json()
        resp = client.delete(f"/api/v1/workspaces/ws-1/calculated-channels/{created['id']}")
        assert resp.status_code == 204
        assert client.get("/api/v1/workspaces/ws-1/calculated-channels").json() == []

    def test_delete_blocked_by_dependent(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        sum_channel = _create(
            client, "ws-1", name="Sum", operation="addition",
            inputs=[
                {"kind": "source", "source_id": source_id, "channel_name": "VA"},
                {"kind": "source", "source_id": source_id, "channel_name": "VB"},
            ],
        ).json()
        _create(
            client, "ws-1", name="Scaled", operation="multiply_constant",
            inputs=[{"kind": "calculated", "calculated_channel_id": sum_channel["id"]}],
            parameters={"constant": 2.0},
        )
        resp = client.delete(f"/api/v1/workspaces/ws-1/calculated-channels/{sum_channel['id']}")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "calculated_channel_has_dependents"
        assert "Scaled" in resp.json()["detail"]["message"]


class TestValidationErrors:
    def test_incompatible_units_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="bad", operation="addition",
            inputs=[
                {"kind": "source", "source_id": source_id, "channel_name": "VA"},
                {"kind": "source", "source_id": source_id, "channel_name": "IA"},
            ],
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "incompatible_unit"

    def test_single_channel_addition_rejected_for_arity(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="bad", operation="addition",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_operation_arity"

    def test_two_channels_for_reverse_polarity_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="bad", operation="reverse_polarity",
            inputs=[
                {"kind": "source", "source_id": source_id, "channel_name": "VA"},
                {"kind": "source", "source_id": source_id, "channel_name": "VB"},
            ],
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_operation_arity"

    def test_unknown_source_channel_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="bad", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "NOPE"}],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_digital_channel_rejected(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="bad", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "BRK_A"}],
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_analog"


class TestWaveformCursorPeakAnchorEndpoints:
    def _make_channel(self, client, comtrade_fixtures_dir, workspace_id="ws-1"):
        source_id = _upload(client, workspace_id, comtrade_fixtures_dir)
        return source_id, _create(
            client, workspace_id, name="-VA", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        ).json()

    def test_waveform_range(self, client, comtrade_fixtures_dir):
        _, channel = self._make_channel(client, comtrade_fixtures_dir)
        resp = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{channel['id']}/waveform")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["representation"] == "full_resolution"
        assert len(body["time"]) == 40

    def test_cursor_values_batch(self, client, comtrade_fixtures_dir):
        _, channel = self._make_channel(client, comtrade_fixtures_dir)
        resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/cursor-values",
            json={"calculated_channel_ids": [channel["id"]], "cursor_a_time": 0.001, "cursor_b_time": None},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["channels"][0]
        assert result["a_value"] == pytest.approx(-400.0)  # VA sample at t=0.001 is 400.0
        assert result["b_value"] is None

    def test_peak_values_batch(self, client, comtrade_fixtures_dir):
        _, channel = self._make_channel(client, comtrade_fixtures_dir)
        resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/peak-values",
            json={"requests": [{"calculated_channel_id": channel["id"], "mode": "min"}], "start_time": 0.0, "end_time": 0.01},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["results"][0]
        assert result["available"] is True

    def test_annotation_anchor(self, client, comtrade_fixtures_dir):
        _, channel = self._make_channel(client, comtrade_fixtures_dir)
        resp = client.post(
            f"/api/v1/workspaces/ws-1/calculated-channels/{channel['id']}/annotation-anchor",
            json={"approximate_elapsed_seconds": 0.001},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["value"] == pytest.approx(-400.0)


class TestLifecycle:
    def test_source_removal_cascades_to_calculated_channels(self, client, comtrade_fixtures_dir):
        source_id, channel = self._helper_make_channel(client, comtrade_fixtures_dir)
        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204
        listing = client.get("/api/v1/workspaces/ws-1/calculated-channels").json()
        assert listing == []

    def test_start_new_workspace_clears_calculated_channels(self, client, comtrade_fixtures_dir):
        source_id, channel = self._helper_make_channel(client, comtrade_fixtures_dir)
        resp = client.delete("/api/v1/workspaces/ws-1")
        assert resp.status_code == 204
        listing = client.get("/api/v1/workspaces/ws-1/calculated-channels").json()
        assert listing == []

    def _helper_make_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        channel = _create(
            client, "ws-1", name="-VA", operation="reverse_polarity",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        ).json()
        return source_id, channel
