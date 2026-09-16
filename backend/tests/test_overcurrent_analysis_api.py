"""API-level tests for Overcurrent Analysis v1's read-only endpoints
(`GET .../overcurrent-characteristics`, `GET .../overcurrent-curve`,
`GET .../engineering-contexts/{id}/overcurrent`). Exercises the real
FastAPI app end-to-end, including a real ASCII-COMTRADE upload -- mirrors
test_phasor_analysis_api.py's own builder pattern exactly. See
test_overcurrent_analysis_service.py for the already-proven service-layer
guardrail matrix this router only exposes.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _build_ascii_comtrade(
    *, station: str, channels: list[tuple[str, str, float]], sample_rate_hz: float, duration_s: float,
    nominal_frequency_hz: float = 50.0,
) -> tuple[bytes, bytes]:
    """`channels`: list of `(name, unit, rms_amps)` -- a pure sinusoid at
    `nominal_frequency_hz`, `a=1.0, b=0.0` so raw sample values ARE the
    engineering values directly."""
    n = int(round(duration_s * sample_rate_hz))
    dt_us = 1_000_000.0 / sample_rate_hz
    lines_cfg = [f"{station},OCDEV,1999", f"{len(channels)},{len(channels)}A,0D"]
    for i, (name, unit, _rms) in enumerate(channels, start=1):
        lines_cfg.append(f"{i},{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,P")
    lines_cfg.append(str(nominal_frequency_hz))
    lines_cfg.append("1")
    lines_cfg.append(f"{sample_rate_hz},{n}")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("ASCII")
    lines_cfg.append("1.0")
    cfg_text = "\n".join(lines_cfg) + "\n"

    t = np.arange(n) / sample_rate_hz
    values = [rms * np.sqrt(2.0) * np.cos(2.0 * np.pi * nominal_frequency_hz * t) for _name, _unit, rms in channels]
    lines_dat = []
    for row in range(n):
        parts = [str(row + 1), f"{row * dt_us:.1f}"] + [f"{values[c][row]:.6f}" for c in range(len(channels))]
        lines_dat.append(",".join(parts))
    dat_text = "\n".join(lines_dat) + "\n"
    return cfg_text.encode("ascii"), dat_text.encode("ascii")


def _upload_current_source(client, workspace_id, *, channels, sample_rate_hz=5000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="oc_ascii"):
    cfg, dat = _build_ascii_comtrade(
        station="OCSTA", channels=channels, sample_rate_hz=sample_rate_hz, duration_s=duration_s,
        nominal_frequency_hz=nominal_frequency_hz,
    )
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/engineering-contexts"


def _ref(source_id, name):
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _create_context(client, workspace_id, members, display_name="Alpha 1"):
    resp = client.post(_contexts_url(workspace_id), json={"display_name": display_name, "status": "manual", "members": members})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _overcurrent(client, workspace_id, context_id, **params):
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/overcurrent", params=params)


class TestCharacteristicsMetadataEndpoint:
    def test_lists_exactly_three_iec_idmt_characteristics(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/overcurrent-characteristics")
        assert resp.status_code == 200, resp.text
        ids = {c["id"] for c in resp.json()["characteristics"]}
        assert ids == {"iec_standard_inverse", "iec_very_inverse", "iec_extremely_inverse"}

    def test_each_characteristic_carries_its_own_constants(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/overcurrent-characteristics")
        by_id = {c["id"]: c for c in resp.json()["characteristics"]}
        assert by_id["iec_standard_inverse"]["k"] == pytest.approx(0.14)
        assert by_id["iec_standard_inverse"]["alpha"] == pytest.approx(0.02)
        assert by_id["iec_very_inverse"]["k"] == pytest.approx(13.5)
        assert by_id["iec_extremely_inverse"]["k"] == pytest.approx(80.0)


class TestCurveEndpoint:
    def test_curve_points_for_known_characteristic(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/overcurrent-curve", params={"characteristic_id": "iec_standard_inverse", "tms": 0.1})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["characteristic_id"] == "iec_standard_inverse"
        assert len(body["points"]) > 10
        assert all(p["multiple_of_pickup"] > 1.0 for p in body["points"])
        assert all(p["operating_time_seconds"] > 0 for p in body["points"])

    def test_unknown_characteristic_is_422(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/overcurrent-curve", params={"characteristic_id": "nonexistent", "tms": 0.1})
        assert resp.status_code == 422

    def test_invalid_tms_is_422(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/overcurrent-curve", params={"characteristic_id": "iec_standard_inverse", "tms": -1.0})
        assert resp.status_code == 422


class TestComputedThroughRealUpload:
    def test_secondary_basis_via_http(self, client):
        source_id = _upload_current_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 4.2)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _overcurrent(
            client, "ws-1", context["id"], phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0, recording_basis="secondary",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["algorithm_version"] == "overcurrent_idmt_v1"
        assert body["measured_rms_current"] == pytest.approx(4.2, rel=1e-3)
        assert body["relay_secondary_current"] == pytest.approx(4.2, rel=1e-3)
        assert body["multiple_of_pickup"] == pytest.approx(4.2, rel=1e-3)
        assert body["expected_operating_time_seconds"] is not None
        assert body["expected_operating_time_seconds"] > 0
        assert body["channel_ref"]["channel_name"] == "ALPHA1_IA"

    def test_primary_basis_ct_conversion_via_http(self, client):
        source_id = _upload_current_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 4200.0)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _overcurrent(
            client, "ws-1", context["id"], phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0,
            recording_basis="primary", ct_primary=1000.0, ct_secondary=1.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["measured_rms_current"] == pytest.approx(4200.0, rel=1e-3)
        assert body["relay_secondary_current"] == pytest.approx(4.2, rel=1e-3)

    def test_below_pickup_via_http(self, client):
        source_id = _upload_current_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 0.3)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _overcurrent(
            client, "ws-1", context["id"], phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0, recording_basis="secondary",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expected_operating_time_seconds"] is None
        assert body["threshold_exceeded"] is False

    def test_kA_primary_recording_ct_conversion_via_http(self, client):
        """Owner UAT golden scenario end-to-end through a real ASCII-
        COMTRADE upload: a 2.4 kA primary channel through a 1200:1 CT
        must resolve to a 2.0 A relay-equivalent current (2.5x a 0.8 A
        secondary pickup), never the un-normalized 0.002 A."""
        source_id = _upload_current_source(client, "ws-1", channels=[("ALPHA1_IA", "kA", 2.4)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _overcurrent(
            client, "ws-1", context["id"], phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=0.8,
            recording_basis="primary", ct_primary=1200.0, ct_secondary=1.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["measured_rms_current"] == pytest.approx(2.4, rel=1e-3)
        assert body["measured_rms_current_unit"] == "kA"
        assert body["relay_secondary_current"] == pytest.approx(2.0, rel=1e-3)
        assert body["multiple_of_pickup"] == pytest.approx(2.5, rel=1e-3)

    def test_missing_engineering_context_is_404(self, client):
        resp = _overcurrent(
            client, "ws-1", "ec-missing", phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0, recording_basis="secondary",
        )
        assert resp.status_code == 404

    def test_no_relay_operation_claims_in_response_wording(self, client):
        """Owner instruction: never say 'relay tripped'/'relay should
        trip'/'relay failed to trip' anywhere the endpoint returns text."""
        source_id = _upload_current_source(client, "ws-1", channels=[("ALPHA1_IA", "A", 20.0)])
        context = _create_context(client, "ws-1", [{"channel_ref": _ref(source_id, "ALPHA1_IA"), "phase": "A", "phase_source": "engineer_confirmed"}])
        resp = _overcurrent(
            client, "ws-1", context["id"], phase="A", analysis_time=1.5,
            characteristic_id="iec_standard_inverse", tms=0.025, pickup_current_secondary=1.0, recording_basis="secondary",
        )
        assert resp.status_code == 200, resp.text
        text = resp.text.lower()
        assert "tripped" not in text
        assert "should trip" not in text
        assert "relay operated" not in text
        assert "failed to trip" not in text


class TestManualAnalysisEndpoint:
    """Manual Input / Calculator mode (`GET .../overcurrent-manual`) --
    workspace-scoped only, no Engineering Context/upload needed at all."""

    def _manual(self, client, workspace_id="ws-manual-1", **params):
        defaults = dict(
            characteristic_id="iec_standard_inverse", tms=0.10, pickup_current_secondary=1.0,
            input_current=30000.0, input_current_unit="A", recording_basis="primary",
            ct_primary=1200.0, ct_secondary=1.0,
        )
        defaults.update(params)
        # `None` values are OMITTED entirely (never sent as an empty-string
        # query param, which FastAPI would reject as an invalid float) --
        # mirrors `_overcurrent()`'s own established convention above of
        # simply not passing ct_primary/ct_secondary at all when unused.
        query = {k: v for k, v in defaults.items() if v is not None}
        return client.get(f"/api/v1/workspaces/{workspace_id}/overcurrent-manual", params=query)

    def test_golden_30000_a_primary_via_http(self, client):
        """Owner's own worked example end-to-end through the real HTTP
        endpoint, with zero prior upload/context/source setup."""
        resp = self._manual(client)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["algorithm_version"] == "overcurrent_idmt_v1"
        assert body["relay_secondary_current"] == pytest.approx(25.0, rel=1e-6)
        assert body["multiple_of_pickup"] == pytest.approx(25.0, rel=1e-6)
        assert body["expected_operating_time_seconds"] is not None
        assert body["expected_operating_time_seconds"] > 0
        assert body["input_basis"] == "primary"
        assert body["input_current"] == pytest.approx(30000.0)
        assert body["input_current_unit"] == "A"

    def test_no_engineering_context_or_channel_fields_in_response(self, client):
        """The response shape must never carry recording-only concepts
        that don't exist for a standalone manual value."""
        resp = self._manual(client)
        body = resp.json()
        for absent_field in ("engineering_context_id", "phase", "analysis_time", "channel_ref", "above_pickup_duration_seconds", "threshold_exceeded"):
            assert absent_field not in body

    def test_30_ka_equals_30000_a_via_http(self, client):
        resp_ka = self._manual(client, input_current=30.0, input_current_unit="kA")
        resp_a = self._manual(client, input_current=30000.0, input_current_unit="A")
        assert resp_ka.json()["relay_secondary_current"] == pytest.approx(resp_a.json()["relay_secondary_current"], rel=1e-6)

    def test_secondary_basis_bypasses_ct_via_http(self, client):
        resp = self._manual(client, input_current=2.5, input_current_unit="A", recording_basis="secondary",
                             ct_primary=None, ct_secondary=None)
        assert resp.status_code == 200, resp.text
        assert resp.json()["relay_secondary_current"] == pytest.approx(2.5, rel=1e-6)

    def test_below_pickup_via_http(self, client):
        resp = self._manual(client, input_current=0.5, input_current_unit="A", recording_basis="secondary",
                             ct_primary=None, ct_secondary=None, pickup_current_secondary=1.0)
        body = resp.json()
        assert body["multiple_of_pickup"] == pytest.approx(0.5, rel=1e-6)
        assert body["expected_operating_time_seconds"] is None

    @pytest.mark.parametrize("bad_current", [0.0, -1.0])
    def test_invalid_input_current_via_http(self, client, bad_current):
        resp = self._manual(client, input_current=bad_current, input_current_unit="A", recording_basis="secondary",
                             ct_primary=None, ct_secondary=None)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "needs_configuration"
        assert body["reason_code"] == "invalid_input_current"

    def test_missing_required_query_param_is_422(self, client):
        resp = client.get(
            "/api/v1/workspaces/ws-manual-1/overcurrent-manual",
            params={"characteristic_id": "iec_standard_inverse", "tms": 0.1, "pickup_current_secondary": 1.0},
        )
        assert resp.status_code == 422

    def test_no_relay_operation_claims_in_response_wording(self, client):
        resp = self._manual(client, tms=0.025)
        assert resp.status_code == 200, resp.text
        text = resp.text.lower()
        assert "tripped" not in text
        assert "should trip" not in text
        assert "relay operated" not in text
        assert "failed to trip" not in text
