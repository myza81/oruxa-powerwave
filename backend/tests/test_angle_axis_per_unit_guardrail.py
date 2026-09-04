"""Angle-axis enhancement (DEC-078) -- the per-unit guardrail: a
Voltage-Angle/Current-Angle `engineering_quantity` must resolve
`not_applicable` for per-unit conversion, regardless of its own broad
`engineering_type` (Voltage/Current) or whether a Voltage/Current Base
is configured -- see `app.services.waveform_service.
_resolve_effective_per_unit()`'s own docstring for the exact seam this
guards. Wired through the real FastAPI app end-to-end: CSV preparation
-> Engineering Quantity selection -> canonical conversion -> per-unit
base configuration -> waveform fetch under `unit_mode=per_unit`.

Existing DEC-049/DEC-050/DEC-052 regression coverage (COMTRADE, no
Engineering Quantity involved at all) is untouched -- see
test_per_unit_api.py, test_group_aware_per_unit_service.py, and the
rest of the existing per-unit suite, all still green after this change.
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


def _voltage_and_voltage_angle_source(client) -> str:
    """Time,VR Magnitude,VR Angle -- header row, 3 active rows, both
    Waveform columns explicitly classified via Engineering Quantity."""
    content = (
        b"Time,VR Magnitude,VR Angle\n"
        b"0.00,132.1,10.0\n"
        b"0.02,132.2,10.1\n"
        b"0.04,132.0,9.9\n"
    )
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/2/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Voltage"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/2/engineering-quantity",
        json={"engineering_quantity": "Voltage Angle"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


def _current_and_current_angle_source(client) -> str:
    content = (
        b"Time,IR Magnitude,IR Angle\n"
        b"0.00,10.5,50.0\n"
        b"0.02,10.6,50.1\n"
        b"0.04,10.4,49.9\n"
    )
    source_id = _upload_csv(client, content)
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
        json={"start_row": 2, "end_row": 4},
    )
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
    client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/2/role", json={"role": "waveform"})
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/engineering-quantity",
        json={"engineering_quantity": "Current"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/2/engineering-quantity",
        json={"engineering_quantity": "Current Angle"},
    )
    client.put(
        f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
        json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
    )
    return source_id


class TestVoltageAnglePerUnitGuardrail:
    def test_voltage_angle_not_applicable_even_with_configured_base(self, client):
        # Note: the MAGNITUDE channel's own status here is "base_required"
        # rather than "configured" -- a separate, pre-existing,
        # unrelated-to-this-guardrail limitation: CSV/Excel-converted
        # AnalogChannel.unit is always "" (DEC-077's own conversion-gap
        # finding), and _measured_unit_scale() never recognizes an empty
        # unit string, regardless of whether a base is configured. That
        # is not this test's concern -- what matters here is the
        # CONTRAST: the Angle channel is "not_applicable" (this
        # guardrail), never merely "base_required" (which would wrongly
        # imply it just needs a base/unit fixed, when it should never be
        # eligible at all).
        prep_source_id = _voltage_and_voltage_angle_source(client)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 132.0})

        magnitude = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Magnitude", "unit_mode": "per_unit"},
        ).json()
        angle = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "per_unit"},
        ).json()

        assert magnitude["per_unit_status"] == "base_required"
        assert angle["per_unit_status"] == "not_applicable"

    def test_voltage_angle_values_never_divided_by_voltage_base(self, client):
        # Task section AC: angle values must never be transformed by the
        # per-unit guardrail -- confirmed directly against the raw,
        # unconverted engineering values.
        prep_source_id = _voltage_and_voltage_angle_source(client)
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
        assert per_unit_mode["unit"] == engineering["unit"]

    def test_voltage_angle_without_any_configured_base_is_still_not_applicable(self, client):
        # No per-unit base configured at all -- the legacy DEC-049
        # fallback would normally report base_required for an ordinary
        # Voltage channel; an Angle channel must report not_applicable
        # instead, never base_required (task section P's own explicit
        # rule -- angle is never "needs configuration", it is simply
        # exempt).
        prep_source_id = _voltage_and_voltage_angle_source(client)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]

        magnitude = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Magnitude", "unit_mode": "per_unit"},
        ).json()
        angle = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "per_unit"},
        ).json()

        assert magnitude["per_unit_status"] == "base_required"
        assert angle["per_unit_status"] == "not_applicable"

    def test_engineering_mode_unaffected_regardless_of_quantity(self, client):
        prep_source_id = _voltage_and_voltage_angle_source(client)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 132.0})

        angle = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "VR Angle", "unit_mode": "engineering"},
        ).json()

        assert angle["per_unit_status"] is None


class TestCurrentAnglePerUnitGuardrail:
    def test_current_angle_not_applicable_even_with_configured_base(self, client):
        prep_source_id = _current_and_current_angle_source(client)
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{prep_source_id}/convert").json()
        source_id = converted["source_id"]
        client.put(
            f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}",
            json={"voltage_base_value": 132.0, "current_base_mode": "direct", "direct_current_base_value": 12.0},
        )

        magnitude = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "IR Magnitude", "unit_mode": "per_unit"},
        ).json()
        angle = client.get(
            f"/api/v1/workspaces/{WS}/sources/{source_id}/waveform",
            params={"channel_name": "IR Angle", "unit_mode": "per_unit"},
        ).json()

        # Same pre-existing CSV-unit-gap caveat as the Voltage test above.
        assert magnitude["per_unit_status"] == "base_required"
        assert angle["per_unit_status"] == "not_applicable"


class TestLegacyUndefinedQuantityBehaviorPreserved:
    """Task section P's own explicit backward-compatibility requirement:
    a channel with `engineering_quantity = Undefined` (every COMTRADE
    channel today, and any CSV/Excel Waveform column the engineer never
    classified) must preserve EXACTLY the pre-existing engineering_type-
    only per-unit behavior -- confirmed here for a CSV/Excel Voltage
    channel deliberately left Undefined, and separately for a real
    COMTRADE fixture (test_per_unit_api.py's own existing suite, which
    remains green, unmodified, and is the authoritative COMTRADE
    regression proof for this guardrail)."""

    def test_csv_voltage_left_undefined_still_resolves_normally(self, client):
        content = b"Time,VR\n0.00,132.1\n0.02,132.2\n0.04,132.0\n"
        source_id = _upload_csv(client, content)
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/header", json={"row_number": 1})
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/data-region",
            json={"start_row": 2, "end_row": 4},
        )
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
        client.put(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
        # Deliberately never setting Engineering Quantity for column 1 --
        # stays "Undefined".
        client.put(
            f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "elapsed_numeric", "unit": "seconds", "confirmed": True},
        )
        converted = client.post(f"/api/v1/workspaces/{WS}/preparation-sources/{source_id}/convert").json()
        canonical_source_id = converted["source_id"]

        body = client.get(f"/api/v1/workspaces/{WS}/sources/{canonical_source_id}/channels").json()
        channel = next(c for c in body["analog_channels"] if c["name"] == "VR")
        assert channel["engineering_quantity"] == "Undefined"
        assert channel["engineering_type"] == "Undefined"
        # An Undefined broad type is per-unit not_applicable for a
        # DIFFERENT reason (unit "" never resolves Voltage/Current at
        # all, task's own CSV-conversion-gap finding) -- not because of
        # the new Angle guardrail. Confirms the guardrail adds a NEW
        # veto without disturbing this pre-existing, unrelated outcome.
        per_unit = client.get(
            f"/api/v1/workspaces/{WS}/sources/{canonical_source_id}/waveform",
            params={"channel_name": "VR", "unit_mode": "per_unit"},
        ).json()
        assert per_unit["per_unit_status"] == "not_applicable"
