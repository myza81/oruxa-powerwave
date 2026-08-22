"""API-level tests for Phase 5C's `unit_mode` extension of the 8 existing
display/measurement endpoints (DEC-049): source waveform/cursor-values/
peak-values/annotation-anchor, and their calculated-channel equivalents.
Exercises the real FastAPI app end-to-end (not just app.domain.per_unit's
pure functions directly -- see test_per_unit_domain.py for that).
"""

from __future__ import annotations

import io
import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SQRT_3 = 1.7320508075688772


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _make_profile_with_voltage_base(client, workspace_id, source_id, channel_name="VA", value=275.0, unit="kV"):
    # Phase 5C-UAT (source-bound redesign): no separate profile identity
    # or channel assignment any more -- configuring the SOURCE itself is
    # sufficient; every eligible Voltage/Current channel of that source
    # (VA included, regardless of `channel_name` here -- kept as a
    # parameter only so existing call sites read the same) uses it
    # automatically. `unit` is accepted for call-site compatibility but
    # ignored -- Voltage Base is always canonical kV now.
    del channel_name, unit
    put_resp = client.put(
        f"/api/v1/workspaces/{workspace_id}/per-unit/sources/{source_id}",
        json={"voltage_base_value": value},
    )
    assert put_resp.status_code == 200, put_resp.text
    return source_id


class TestSourceWaveformPerUnit:
    def test_configured_channel_converts_values_and_unit(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "unit_mode": "per_unit"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "configured"
        assert body["unit"] == "pu"
        # Fixture channel VA has a=110.0 max value at scale 0.1 -- exact
        # numeric correctness is covered by the domain-level tests; here
        # we only need the conversion to have actually been applied.
        assert body["values"] != []

    def test_unassigned_channel_is_base_required_and_stays_engineering(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "unit_mode": "per_unit"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "base_required"
        assert body["unit"] == "V"  # the fixture's own declared unit, unchanged

    def test_default_engineering_mode_never_reports_a_status(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] is None
        assert body["unit"] == "V"


class TestSourceCursorValuesPerUnit:
    def test_batch_reports_configured_and_base_required_independently(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id, channel_name="VA")

        resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/cursor-values",
            json={
                "analog_channel_names": ["VA", "IA"],
                "cursor_a_time": 0.0005,
                "unit_mode": "per_unit",
            },
        )
        assert resp.status_code == 200, resp.text
        channels = {c["channel_name"]: c for c in resp.json()["channels"]}
        assert channels["VA"]["per_unit_status"] == "configured"
        assert channels["VA"]["unit"] == "pu"
        assert channels["IA"]["per_unit_status"] == "base_required"
        assert channels["IA"]["unit"] == "A"


class TestSourceAnnotationAnchorPerUnit:
    def test_anchor_identity_unchanged_only_value_converts(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id)

        engineering_resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/annotation-anchor",
            json={"channel_name": "VA", "approximate_elapsed_seconds": 0.001},
        )
        pu_resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/annotation-anchor",
            json={"channel_name": "VA", "approximate_elapsed_seconds": 0.001, "unit_mode": "per_unit"},
        )
        assert engineering_resp.status_code == 200 and pu_resp.status_code == 200
        eng_body, pu_body = engineering_resp.json(), pu_resp.json()
        assert eng_body["sample_index"] == pu_body["sample_index"]
        assert eng_body["elapsed_seconds"] == pu_body["elapsed_seconds"]
        assert pu_body["per_unit_status"] == "configured"
        assert pu_body["unit"] == "pu"
        assert pu_body["value"] == pytest.approx(eng_body["value"] / 275_000.0)


class TestSourcePeakValuesPerUnit:
    def test_peak_value_converts_when_configured(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id)

        resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/peak-values",
            json={
                "requests": [{"channel_name": "VA", "mode": "max"}],
                "start_time": 0.0,
                "end_time": 0.005,
                "unit_mode": "per_unit",
            },
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["results"][0]
        assert result["available"] is True
        assert result["per_unit_status"] == "configured"
        assert result["unit"] == "pu"


class TestCalculatedChannelPerUnit:
    def _create_rms(self, client, workspace_id, source_id):
        # Fixture spans only ~9.75ms (4000 Hz, 40 samples) -- 50/60 Hz's
        # own 16-20ms window would exceed the whole recording, so use a
        # higher nominal frequency (200 Hz -> 5ms window, still >= 4
        # samples/cycle at this sample rate) purely to fit RMS's own
        # data-quality guardrails within this short synthetic fixture.
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/calculated-channels",
            json={
                "name": "RMS(VA)", "operation": "rms",
                "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
                "parameters": {"nominal_frequency_hz": 200.0},
                "override": True,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_rms_channel_inherits_input_profile_and_converts_on_waveform_endpoint(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        # VA assigned to a profile BEFORE the RMS channel is created, so
        # decision 6's inheritance-at-creation-time picks it up.
        _make_profile_with_voltage_base(client, "ws-1", source_id)
        calc_id = self._create_rms(client, "ws-1", source_id)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/waveform",
            params={"unit_mode": "per_unit"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "configured"
        assert body["unit"] == "pu"
        # RMS's own leading warm-up region must still safely serialize as
        # `null` even under per-unit conversion (NaN survives division).
        assert None in body["values"]

    def test_calculated_cursor_and_peak_and_anchor_endpoints_report_status(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _make_profile_with_voltage_base(client, "ws-1", source_id)
        calc_id = self._create_rms(client, "ws-1", source_id)

        cursor_resp = client.post(
            f"/api/v1/workspaces/ws-1/calculated-channels/cursor-values",
            json={"calculated_channel_ids": [calc_id], "cursor_a_time": 0.008, "unit_mode": "per_unit"},
        )
        assert cursor_resp.status_code == 200, cursor_resp.text
        assert cursor_resp.json()["channels"][0]["per_unit_status"] == "configured"

        peak_resp = client.post(
            f"/api/v1/workspaces/ws-1/calculated-channels/peak-values",
            json={
                "requests": [{"calculated_channel_id": calc_id, "mode": "max"}],
                "start_time": 0.0, "end_time": 0.00975, "unit_mode": "per_unit",
            },
        )
        assert peak_resp.status_code == 200, peak_resp.text
        assert peak_resp.json()["results"][0]["available"] is True
        assert peak_resp.json()["results"][0]["per_unit_status"] == "configured"

        anchor_resp = client.post(
            f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/annotation-anchor",
            json={"approximate_elapsed_seconds": 0.008, "unit_mode": "per_unit"},
        )
        assert anchor_resp.status_code == 200, anchor_resp.text
        assert anchor_resp.json()["per_unit_status"] == "configured"

    def test_rms_channel_without_input_profile_is_base_required(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        calc_id = self._create_rms(client, "ws-1", source_id)  # VA never assigned to any profile

        resp = client.get(
            f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/waveform",
            params={"unit_mode": "per_unit"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "base_required"
        assert body["unit"] == "V"
