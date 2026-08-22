"""API-level tests for the Phase 5A Calculated Channels endpoints
(DEC-047). Exercises the real end-to-end flow (upload -> parse -> retain
-> calculate) through a fully wired FastAPI TestClient, same pattern as
tests/test_peak_value_api.py / test_annotation_anchor_api.py. The
synth_ascii fixture: analog channels VA/VB/IA, 40 samples at 4000 Hz.
"""

from __future__ import annotations

import io
import math

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


def _synthetic_sinusoid_ascii_comtrade(*, fs=5000.0, f0=50.0, duration=0.5, amplitude=100.0):
    """A minimal single-analog-channel ASCII COMTRADE pair (Phase 5B) --
    dense/long enough (2500 samples at 5kHz = 0.5s) for RMS creation
    (>1 window, well above MIN_SAMPLES_PER_CYCLE), unlike the shared
    synth_ascii fixture (40 samples at 4kHz = 10ms, shorter than even one
    20ms RMS window). Same CFG structure/format as
    tests/fixtures/comtrade/synth_ascii.cfg, just one analog channel and
    a much longer/denser record."""
    n = int(round(fs * duration))
    cfg_lines = [
        "SYNTH_STATION,SYNTH_DEV,1999",
        "1,1A,0D",
        "1,VA,A,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
        "50",
        "1",
        f"{fs},{n}",
        "06/03/2026,10:00:00.000000",
        "06/03/2026,10:00:00.000000",
        "ASCII",
        "1.0",
    ]
    cfg_bytes = ("\r\n".join(cfg_lines) + "\r\n").encode("ascii")

    dat_lines = []
    for i in range(n):
        timestamp_us = round(i * (1_000_000.0 / fs))
        value = amplitude * math.sin(2 * math.pi * f0 * (i / fs))
        dat_lines.append(f"{i + 1},{timestamp_us},{value:.6f}")
    dat_bytes = ("\r\n".join(dat_lines) + "\r\n").encode("ascii")
    return cfg_bytes, dat_bytes


def _upload_sinusoid(client, workspace_id, **kwargs):
    cfg_bytes, dat_bytes = _synthetic_sinusoid_ascii_comtrade(**kwargs)
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        files=_files(cfg_bytes, dat_bytes, cfg_name="rms.cfg", dat_name="rms.dat"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


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

    def test_unsupported_operation_rejected(self, client, comtrade_fixtures_dir):
        """Phase 5B added `rms` as a supported operation (see
        TestRmsOperation below) -- this test now covers a operation this
        project still does not support at all (e.g. sequence/phasor RMS,
        explicitly out of scope per DEC-048), which pydantic's `Literal`
        still rejects outright, unchanged."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="Sequence", operation="sequence_rms",
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


class TestRmsOperation:
    """Phase 5B (DEC-048): full HTTP round trip for RMS create + the
    dedicated eligibility endpoint."""

    def test_create_rms_channel_success(self, client):
        source_id = _upload_sinusoid(client, "ws-1")
        resp = _create(
            client, "ws-1", name="RMS(VA)", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": 50.0},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["operation"] == "rms"
        assert body["waveform_form"] == "rms"
        assert body["parameters"] == {
            "nominal_frequency_hz": 50.0, "window_mode": "trailing", "rms_kind": "true_rms",
        }
        assert body["sample_count"] == 2500

    def test_create_rms_without_override_blocked_when_metadata_says_rms(self, client):
        # No current provider (COMTRADE) sets waveform_form away from
        # "unknown" (see app.domain.channel_classification's own module
        # docstring) -- this simulates a future importer's explicit
        # trusted metadata by reaching into the already-uploaded source's
        # own retained metadata directly, exercising the SAME
        # check_rms_eligibility() code path a real importer would feed,
        # without building one.
        from app.domain.channel_classification import WAVEFORM_FORM_RMS

        source_id = _upload_sinusoid(client, "ws-1")
        active = client.app.state.workspace_registry.get("ws-1", source_id)
        active.metadata.analog_channels[0].waveform_form = WAVEFORM_FORM_RMS

        eligibility_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/rms-eligibility",
            json={"input": {"kind": "source", "source_id": source_id, "channel_name": "VA"}, "nominal_frequency_hz": 50.0},
        )
        assert eligibility_resp.status_code == 200, eligibility_resp.text
        assert eligibility_resp.json()["status"] == "likely_already_rms_or_magnitude"
        assert eligibility_resp.json()["override_required"] is True

        resp = _create(
            client, "ws-1", name="RMS(VA)", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": 50.0},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "rms_override_required"

        resp_override = _create(
            client, "ws-1", name="RMS(VA)override", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": 50.0}, override=True,
        )
        assert resp_override.status_code == 201, resp_override.text

    def test_rms_eligibility_suitable_for_unknown_metadata_sinusoid(self, client):
        source_id = _upload_sinusoid(client, "ws-1")
        resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels/rms-eligibility",
            json={"input": {"kind": "source", "source_id": source_id, "channel_name": "VA"}, "nominal_frequency_hz": 50.0},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "suitable"
        assert resp.json()["override_required"] is False

    def test_invalid_nominal_frequency_rejected(self, client):
        source_id = _upload_sinusoid(client, "ws-1")
        resp = _create(
            client, "ws-1", name="RMS(VA)", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": -50.0},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "invalid_nominal_frequency"

    def test_recording_too_short_rejected(self, client, comtrade_fixtures_dir):
        # The shared synth_ascii fixture is only 10ms long -- shorter than
        # even one 20ms RMS window. override=True is passed to reach past
        # eligibility (a short/uncertain slice would otherwise be blocked
        # there first) and prove the length check is a SEPARATE, harder,
        # never-overridable gate (section 40).
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = _create(
            client, "ws-1", name="RMS(VA)", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": 50.0}, override=True,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "rms_recording_too_short"

    def test_rms_waveform_response_serializes_nan_as_null_not_crash(self, client):
        # Regression test for the allow_nan=False finding: FastAPI's
        # default JSONResponse would 500 on a raw NaN in the response
        # body. An RMS channel's leading warm-up region is routine,
        # guaranteed NaN -- fetching a range that includes it must
        # succeed (200) with `null` at the affected positions, never crash.
        source_id = _upload_sinusoid(client, "ws-1")
        channel = _create(
            client, "ws-1", name="RMS(VA)", operation="rms",
            inputs=[{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
            parameters={"nominal_frequency_hz": 50.0},
        ).json()
        resp = client.get(
            f"/api/v1/workspaces/ws-1/calculated-channels/{channel['id']}/waveform",
            params={"start_time": 0.0, "end_time": 0.01},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["values"], "expected at least one point in the warm-up-only range"
        assert all(v is None for v in body["values"])
        assert all(v is not None for v in body["time"])


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
