"""Measured Unit enhancement (DEC-080), task section AO: a CSV-derived
Voltage measurement group must resolve Per-Unit exactly like a COMTRADE-
derived one, once its channels carry an explicit Measured Unit -- proves
the group-aware path (app.services.group_aware_per_unit, DEC-050) reuses
`app.domain.per_unit.apply_per_unit_to_value()`/`apply_per_unit_to_array()`
the SAME way the legacy path does (see test_measured_unit_per_unit.py),
so this enhancement needed zero changes to either per-unit module.

Group creation here uses STATUS_MANUAL (an explicit channel_refs list,
matching test_group_aware_per_unit_endpoints.py's own `_voltage_group()`
convention) rather than auto-detection -- auto-detection's own phase-
naming pattern is a separate, unrelated concern to this task.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL
from app.main import create_app
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772

WS = "ws-1"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload_csv(client, content: bytes, filename: str = "e.csv") -> str:
    files = {"csv_file": (filename, content, "text/csv")}
    resp = client.post(f"/api/v1/workspaces/{WS}/preparation-sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _voltage_group(client, source_id, channel_names, nominal_kv, display_name):
    group = create_group(
        workspace_id=WS, source_id=source_id, kind=KIND_VOLTAGE, display_name=display_name,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=STATUS_MANUAL,
        registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )
    set_voltage_base(
        workspace_id=WS, measurement_group_id=group.id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _prepared_three_phase_voltage_source(client, *, unit: str = "kV") -> str:
    """VA/VB/VC, each a constant value across 3 samples so expected PU
    can be computed directly (mirrors the COMTRADE fixture's own
    "constant value per channel" convention, and its exact 158.77kV
    value / 275.0kV LG-nominal pairing -- see
    test_group_aware_per_unit_endpoints.py's own N275_VR/VY/VB, which
    resolves to ~1.0 pu via `158.77 / (275.0 / SQRT_3)`)."""
    content = (
        b"Time,VA,VB,VC\n"
        b"0.00,158.77,158.77,158.77\n"
        b"0.02,158.77,158.77,158.77\n"
        b"0.04,158.77,158.77,158.77\n"
    )
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    for col in (1, 2, 3):
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/{col}/role", json={"role": "waveform"})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/{col}/engineering-quantity",
            json={"engineering_quantity": "Voltage"},
        )
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/{col}/measured-unit",
            json={"measured_unit": unit},
        )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


class TestCsvDerivedVoltageMeasurementGroup:
    def test_group_aware_pu_resolves_configured_for_csv_channels(self, client):
        prep_source_id = _prepared_three_phase_voltage_source(client, unit="kV")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        _voltage_group(client, source_id, ["VA", "VB", "VC"], nominal_kv=275.0, display_name="CSV 275kV BUS")

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VA", "unit_mode": "per_unit"},
        ).json()

        expected = 158.77 / (275.0 / SQRT_3)
        assert response["per_unit_status"] == "configured"
        assert response["unit"] == "pu"
        assert response["values"] == pytest.approx([expected, expected, expected], abs=0.001)
        assert response["values"][0] == pytest.approx(1.0, abs=0.01)

    def test_all_three_phases_resolve_independently_and_consistently(self, client):
        prep_source_id = _prepared_three_phase_voltage_source(client, unit="kV")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        _voltage_group(client, source_id, ["VA", "VB", "VC"], nominal_kv=275.0, display_name="CSV 275kV BUS")

        expected = 158.77 / (275.0 / SQRT_3)
        for channel in ("VA", "VB", "VC"):
            response = client.get(
                f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
                params={"channel_name": channel, "unit_mode": "per_unit"},
            ).json()
            assert response["per_unit_status"] == "configured"
            assert response["values"] == pytest.approx([expected, expected, expected], abs=0.001)

    def test_v_unit_still_resolves_with_correct_scale(self, client):
        # Same fixture, but measured in V (not kV) -- nominal base is
        # still declared in kV, so the measured-unit scale factor (1.0
        # for V vs 1000.0 for kV) must be applied before dividing.
        prep_source_id = _prepared_three_phase_voltage_source(client, unit="V")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        _voltage_group(client, source_id, ["VA", "VB", "VC"], nominal_kv=275.0, display_name="CSV BUS (V)")

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VA", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "configured"
        base_volts = 275.0 / SQRT_3 * 1000.0
        expected = 158.77 / base_volts  # measured value (V) / base (V)
        assert response["values"] == pytest.approx([expected, expected, expected])
