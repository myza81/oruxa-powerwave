"""API-level tests for the Compliance & Capability Voltage Measurement
endpoints (`GET .../compliance/voltage/quantities`, `GET .../compliance/
voltage/measurement`). Exercises the real FastAPI app end-to-end for
HTTP wiring/response-shape/error-mapping only -- the full eligibility/
guardrail decision matrix is already covered by
`test_compliance_measurement_service.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.domain.channel_classification import VOLTAGE, WAVEFORM_FORM_INSTANTANEOUS
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.main import create_app

WORKSPACE_ID = "ws-compliance-api-1"
REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _add_va_source(client: TestClient) -> None:
    sample_rate_hz = 5000.0
    duration_s = 2.0
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n) / sample_rate_hz
    values = 100.0 * np.cos(2.0 * np.pi * 50.0 * t)
    analog_channels = [
        AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type=VOLTAGE, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
    ]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file="s1.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": t, "VA": values}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[sample_rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=REF_START, trigger_time=REF_START),
    )
    metadata = SourceMetadata(
        source_id="s1", workspace_id=WORKSPACE_ID, provider_type="COMTRADE",
        original_filenames=("s1.cfg",), created_at=REF_START,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=REF_START, trigger_time=REF_START,
        sample_count=n, duration_seconds=duration_s, elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(sample_rate_hz,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    client.app.state.workspace_registry.add(ActiveSource(metadata=metadata, record=record))


class TestQuantitiesEndpoint:
    def test_returns_nine_quantities_in_order(self, client):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/quantities")
        assert response.status_code == 200
        body = response.json()
        assert [q["id"] for q in body] == [
            "phase_a_lg_rms", "phase_b_lg_rms", "phase_c_lg_rms",
            "phase_ab_ll_rms", "phase_bc_ll_rms", "phase_ca_ll_rms",
            "min_phase_lg_rms", "max_phase_lg_rms",
            "positive_sequence_rms",
        ]
        assert body[0]["display_label"] == "Phase A Voltage"


class TestMeasurementEndpoint:
    def test_unknown_quantity_id_is_400(self, client):
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement", params={"quantity_id": "bogus"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unknown_compliance_quantity"

    def test_missing_inputs_on_empty_workspace(self, client):
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement", params={"quantity_id": "phase_a_lg_rms"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "missing_inputs"
        assert body["missing"] == ["Va"]

    def test_available_after_uploading_a_phase_a_channel(self, client):
        _add_va_source(client)
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement", params={"quantity_id": "phase_a_lg_rms"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "available"
        assert body["input_type"] == "instantaneous"
        assert body["value_representation"] == "fundamental_rms"
        assert body["resolved_roles"][0]["channel_name"] == "VA"
        assert body["base"] is None
        assert body["assessment_unit"] == "engineering_unit"
