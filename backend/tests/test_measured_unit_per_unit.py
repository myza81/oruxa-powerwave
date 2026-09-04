"""Measured Unit enhancement (DEC-080) -- the core Per-Unit acceptance
criterion (task section M/AN): a CSV/Excel Voltage or Current channel
with an explicit, valid Measured Unit ("V"/"kV"/"A"/"kA") and a
configured base becomes `per_unit_status = "configured"` and its values
scale into `pu`, exactly like a COMTRADE channel already does -- the
root-cause gap this enhancement closes (AnalogChannel.unit was always
""` for every CSV/Excel channel before this task, so
`app.domain.per_unit._measured_unit_scale()` could never recognize it).

Wired through the real FastAPI app end-to-end: CSV preparation ->
Engineering Quantity + Measured Unit selection -> canonical conversion
-> per-unit base configuration -> waveform fetch under
`unit_mode=per_unit`. Existing DEC-049/DEC-050/DEC-078 regression
coverage (COMTRADE, and the Angle guardrail) is untouched -- see
test_per_unit_api.py and test_angle_axis_per_unit_guardrail.py, both
still green after this change with zero modifications to
app.domain.per_unit itself.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


WS = "ws-1"


def _upload_csv(client, content: bytes, filename: str = "e.csv") -> str:
    files = {"csv_file": (filename, content, "text/csv")}
    resp = client.post(f"/api/v1/workspaces/{WS}/preparation-sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _prepared_voltage_source(client, *, measured_unit: str | None) -> str:
    content = b"Time,VR\n0.00,1.32\n0.02,1.33\n0.04,1.31\n"
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Voltage"},
    )
    if measured_unit is not None:
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/measured-unit",
            json={"measured_unit": measured_unit},
        )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


def _prepared_current_source(client, *, measured_unit: str | None) -> str:
    content = b"Time,IR\n0.00,105.0\n0.02,106.0\n0.04,104.0\n"
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Current"},
    )
    if measured_unit is not None:
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/measured-unit",
            json={"measured_unit": measured_unit},
        )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


def _prepared_voltage_angle_source(client, *, measured_unit: str | None) -> str:
    content = b"Time,VR Angle\n0.00,10.0\n0.02,10.1\n0.04,9.9\n"
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Voltage Angle"},
    )
    if measured_unit is not None:
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/measured-unit",
            json={"measured_unit": measured_unit},
        )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


class TestCsvVoltagePerUnitBecomesConfigured:
    @pytest.mark.parametrize("unit", ["V", "kV"])
    def test_valid_unit_and_configured_base_resolves_configured(self, client, unit):
        prep_source_id = _prepared_voltage_source(client, measured_unit=unit)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 1.32})

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "configured"
        assert response["unit"] == "pu"

    def test_values_scale_correctly_by_the_measured_unit(self, client):
        # unit=V, base=1320 V (1.32 kV) -> scale factor 1.0, so pu = value / base
        prep_source_id = _prepared_voltage_source(client, measured_unit="V")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 1.32})

        engineering = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "engineering"},
        ).json()
        per_unit_mode = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "per_unit"},
        ).json()

        base_volts = 1.32 * 1000.0  # voltage_base_value is canonical kV
        expected = [v / base_volts for v in engineering["values"]]
        assert per_unit_mode["values"] == pytest.approx(expected)

    def test_kv_unit_applies_the_1000x_scale_factor(self, client):
        # unit=kV: measured value * 1000 / base_volts.
        prep_source_id = _prepared_voltage_source(client, measured_unit="kV")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 1.32})

        engineering = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "engineering"},
        ).json()
        per_unit_mode = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "per_unit"},
        ).json()

        base_volts = 1.32 * 1000.0
        expected = [(v * 1000.0) / base_volts for v in engineering["values"]]
        assert per_unit_mode["values"] == pytest.approx(expected)


class TestCsvCurrentPerUnitBecomesConfigured:
    @pytest.mark.parametrize("unit", ["A", "kA"])
    def test_valid_unit_and_configured_base_resolves_configured(self, client, unit):
        prep_source_id = _prepared_current_source(client, measured_unit=unit)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(
            f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}",
            json={"current_base_mode": "direct", "direct_current_base_value": 0.105},
        )

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "IR", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "configured"
        assert response["unit"] == "pu"


class TestBlankMeasuredUnitStaysBaseRequired:
    """Task section F/M: blank unit never guesses -- status remains
    base_required even with a configured base, preserving the existing
    fail-closed behavior."""

    def test_voltage_with_no_measured_unit_stays_base_required(self, client):
        prep_source_id = _prepared_voltage_source(client, measured_unit=None)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 1.32})

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "base_required"

    def test_current_with_no_measured_unit_stays_base_required(self, client):
        prep_source_id = _prepared_current_source(client, measured_unit=None)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(
            f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}",
            json={"current_base_mode": "direct", "direct_current_base_value": 0.105},
        )

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "IR", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "base_required"


class TestAngleGuardrailUnaffectedByMeasuredUnit:
    """Task section N: DEC-078 must remain unchanged -- a valid angle
    unit (deg/rad) must never make an Angle channel PU-eligible."""

    @pytest.mark.parametrize("unit", ["deg", "rad"])
    def test_voltage_angle_stays_not_applicable_even_with_a_valid_angle_unit(self, client, unit):
        prep_source_id = _prepared_voltage_angle_source(client, measured_unit=unit)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 132.0})

        response = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "per_unit"},
        ).json()

        assert response["per_unit_status"] == "not_applicable"

    def test_voltage_angle_values_unchanged_with_a_valid_angle_unit(self, client):
        prep_source_id = _prepared_voltage_angle_source(client, measured_unit="deg")
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 132.0})

        engineering = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "engineering"},
        ).json()
        per_unit_mode = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "per_unit"},
        ).json()

        assert per_unit_mode["values"] == pytest.approx(engineering["values"])
        assert per_unit_mode["unit"] == "deg"
