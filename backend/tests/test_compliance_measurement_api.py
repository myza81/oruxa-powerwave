"""API-level tests for the Compliance & Capability Voltage Measurement
endpoints (`GET .../compliance/voltage/quantities`, `GET .../compliance/
voltage/measurement-groups`, `GET .../compliance/voltage/measurement`).
Exercises the real FastAPI app end-to-end for HTTP wiring/response-
shape/error-mapping only -- the full eligibility/guardrail decision
matrix is already covered by `test_compliance_measurement_service.py`.
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


def _add_va_source(client: TestClient, *, source_id: str = "s1") -> None:
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
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": t, "VA": values}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[sample_rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=REF_START, trigger_time=REF_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WORKSPACE_ID, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=REF_START,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=REF_START, trigger_time=REF_START,
        sample_count=n, duration_seconds=duration_s, elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(sample_rate_hz,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    client.app.state.workspace_registry.add(ActiveSource(metadata=metadata, record=record))


def _add_multibay_source(client: TestClient, *, source_id: str, bay_channel_names: list[str]) -> None:
    """A source carrying an arbitrary list of bare Voltage channel
    names (e.g. `KPDN1_VR`/`KPDN1_VY`/`KPDN1_VB`/`KPDN2_VR`/...) -- used
    to exercise the real `app.domain.measurement_group_detection`
    algorithm through `POST .../measurement-groups/suggest`, never a
    hand-constructed `MeasurementGroup`."""
    sample_rate_hz = 1000.0
    duration_s = 1.0
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n) / sample_rate_hz
    columns = {"time": t}
    analog_channels = []
    for index, name in enumerate(bay_channel_names):
        columns[name] = 100.0 * np.cos(2.0 * np.pi * 50.0 * t)
        analog_channels.append(
            AnalogChannelSummary(name=name, index=index, unit="V", engineering_type=VOLTAGE, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[sample_rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=REF_START, trigger_time=REF_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WORKSPACE_ID, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=REF_START,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=REF_START, trigger_time=REF_START,
        sample_count=n, duration_seconds=duration_s, elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(sample_rate_hz,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    client.app.state.workspace_registry.add(ActiveSource(metadata=metadata, record=record))


def _suggest_groups(client: TestClient, *, source_id: str):
    response = client.post(f"/api/v1/workspaces/{WORKSPACE_ID}/sources/{source_id}/measurement-groups/suggest", json={})
    assert response.status_code == 200, response.text
    return response.json()


def _create_voltage_group(client: TestClient, *, source_id: str = "s1", channel_names: tuple[str, ...] = ("VA",)) -> str:
    response = client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/sources/{source_id}/measurement-groups",
        json={
            "kind": "voltage", "display_name": "Bus A", "status": "confirmed",
            "channel_refs": [{"kind": "source", "source_id": source_id, "channel_name": name} for name in channel_names],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


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


class TestMeasurementGroupsEndpoint:
    def test_empty_workspace_returns_empty_list(self, client):
        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_confirmed_voltage_group_with_stable_id(self, client):
        _add_va_source(client)
        group_id = _create_voltage_group(client)
        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == group_id
        assert body[0]["display_name"] == "Bus A"
        assert body[0]["status"] == "confirmed"

    def test_excludes_current_kind_groups(self, client):
        _add_va_source(client)
        current_response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/sources/s1/measurement-groups",
            json={"kind": "current", "display_name": "Current Bank", "status": "confirmed", "channel_refs": []},
        )
        assert current_response.status_code == 201, current_response.text
        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert response.status_code == 200
        assert response.json() == []

    def test_includes_needs_review_groups_2026_09_23_correction(self, client):
        """The exact owner-reported dead end this correction fixes: a
        review-required group must never look identical to a genuinely
        empty workspace at this endpoint -- bucketing into usable vs
        review-required is the CALLER's job now, not this endpoint's."""
        _add_va_source(client)
        group_response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/sources/s1/measurement-groups",
            json={
                "kind": "voltage", "display_name": "Needs Review Bay", "status": "needs_review",
                "channel_refs": [{"kind": "source", "source_id": "s1", "channel_name": "VA"}],
            },
        )
        assert group_response.status_code == 201, group_response.text
        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["status"] == "needs_review"


class TestMeasurementGroupBootstrapDiscovery:
    """2026-09-23 UAT correction: reproduces the exact owner-reported
    scenario (a workspace containing obvious multi-bay Voltage channel
    sets, e.g. KPDN1/KPDN2/SLKS, each with a full phase triplet) and
    proves the existing, unchanged detection pipeline
    (`app.domain.measurement_group_detection`/`generate_suggested_
    groups_for_source()`) is sufficient once actually triggered --
    Compliance needed a caller for it, not a new engine."""

    def test_group_list_reflects_authoritative_registry_state(self, client):
        _add_multibay_source(client, source_id="s1", bay_channel_names=[
            "KPDN1_VR", "KPDN1_VY", "KPDN1_VB",
            "KPDN2_VR", "KPDN2_VY", "KPDN2_VB",
            "SLKS_VR", "SLKS_VY", "SLKS_VB",
        ])
        # Before bootstrap: registry genuinely empty -- reproduces the
        # owner-reported "No Measurement Group is available" dead end.
        before = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert before.json() == []

        suggested = _suggest_groups(client, source_id="s1")
        assert {g["display_name"] for g in suggested} == {"KPDN1 VOLTAGE", "KPDN2 VOLTAGE", "SLKS VOLTAGE"}
        assert all(g["status"] == "suggested" for g in suggested)

        after = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert after.status_code == 200
        names = {g["display_name"] for g in after.json()}
        assert names == {"KPDN1 VOLTAGE", "KPDN2 VOLTAGE", "SLKS VOLTAGE"}

    def test_review_required_groups_are_distinguishable_from_no_groups(self, client):
        # Deliberately mixed single+pair phase representation within one
        # cluster -- verified directly (this task's own investigation)
        # to produce STATUS_NEEDS_REVIEW, never silently resolved.
        _add_multibay_source(client, source_id="s1", bay_channel_names=["MCRS_VR", "MCRS_VB", "MCRS_VRY"])
        suggested = _suggest_groups(client, source_id="s1")
        assert len(suggested) == 1
        assert suggested[0]["status"] == "needs_review"

        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        body = response.json()
        assert len(body) == 1  # NOT an empty list -- discovered, just uncertain
        assert body[0]["status"] == "needs_review"

    def test_bootstrap_is_idempotent_calling_suggest_twice_never_duplicates(self, client):
        _add_multibay_source(client, source_id="s1", bay_channel_names=["KPDN1_VR", "KPDN1_VY", "KPDN1_VB"])
        first = _suggest_groups(client, source_id="s1")
        assert len(first) == 1
        second = _suggest_groups(client, source_id="s1")
        assert second == []  # nothing new -- already fully grouped

        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        assert len(response.json()) == 1

    def test_multi_source_groups_remain_valid_after_bootstrap(self, client):
        _add_multibay_source(client, source_id="s1", bay_channel_names=["KPDN1_VR", "KPDN1_VY", "KPDN1_VB"])
        _add_multibay_source(client, source_id="s2", bay_channel_names=["KPDN2_VR", "KPDN2_VY", "KPDN2_VB"])
        _suggest_groups(client, source_id="s1")
        _suggest_groups(client, source_id="s2")

        response = client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement-groups")
        body = response.json()
        names = {g["display_name"] for g in body}
        assert names == {"KPDN1 VOLTAGE", "KPDN2 VOLTAGE"}

        # Each group remains independently selectable/usable for a real
        # measurement (task section 11 -- multi-source groups, here
        # multiple SEPARATE single-source groups within one workspace,
        # each scoped correctly).
        kpdn1_id = next(g["id"] for g in body if g["display_name"] == "KPDN1 VOLTAGE")
        measurement = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": kpdn1_id, "quantity_id": "phase_a_lg_rms"},
        )
        assert measurement.status_code == 200
        assert measurement.json()["status"] == "available"
        assert measurement.json()["resolved_roles"][0]["channel_name"] == "KPDN1_VR"


class TestMeasurementEndpoint:
    def test_measurement_group_id_is_a_required_query_param(self, client):
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement", params={"quantity_id": "phase_a_lg_rms"}
        )
        assert response.status_code == 422

    def test_unknown_measurement_group_id_is_404(self, client):
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": "does-not-exist", "quantity_id": "phase_a_lg_rms"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "measurement_group_not_found"

    def test_current_kind_group_id_is_400(self, client):
        _add_va_source(client)
        current_response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/sources/s1/measurement-groups",
            json={"kind": "current", "display_name": "Current Bank", "status": "confirmed", "channel_refs": []},
        )
        current_group_id = current_response.json()["id"]
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": current_group_id, "quantity_id": "phase_a_lg_rms"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "compliance_measurement_group_not_voltage_kind"

    def test_unknown_quantity_id_is_400(self, client):
        _add_va_source(client)
        group_id = _create_voltage_group(client)
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": group_id, "quantity_id": "bogus"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unknown_compliance_quantity"

    def test_group_missing_required_channel_reports_missing_inputs(self, client):
        _add_va_source(client)
        group_id = _create_voltage_group(client)  # only VA is a member
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": group_id, "quantity_id": "positive_sequence_rms"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "missing_inputs"
        assert body["missing"] == ["Vb", "Vc"]

    def test_available_after_uploading_and_grouping_a_phase_a_channel(self, client):
        _add_va_source(client)
        group_id = _create_voltage_group(client)
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": group_id, "quantity_id": "phase_a_lg_rms"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "available"
        assert body["measurement_group_id"] == group_id
        assert body["input_type"] == "instantaneous"
        assert body["value_representation"] == "fundamental_rms"
        assert body["resolved_roles"][0]["channel_name"] == "VA"
        assert body["base"] is None
        assert body["assessment_unit"] == "engineering_unit"

    def test_two_bays_with_the_same_channel_name_never_conflict(self, client):
        """task section 7: a duplicate Va across different bays is
        resolved independently once a group is selected, never reported
        as ambiguous."""
        _add_va_source(client, source_id="s1")
        _add_va_source(client, source_id="s2")
        bay_a = _create_voltage_group(client, source_id="s1")
        bay_b = _create_voltage_group(client, source_id="s2")

        response_a = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": bay_a, "quantity_id": "phase_a_lg_rms"},
        )
        assert response_a.json()["status"] == "available"
        assert response_a.json()["resolved_roles"][0]["channel_ref"]["source_id"] == "s1"

        response_b = client.get(
            f"/api/v1/workspaces/{WORKSPACE_ID}/compliance/voltage/measurement",
            params={"measurement_group_id": bay_b, "quantity_id": "phase_a_lg_rms"},
        )
        assert response_b.json()["status"] == "available"
        assert response_b.json()["resolved_roles"][0]["channel_ref"]["source_id"] == "s2"
