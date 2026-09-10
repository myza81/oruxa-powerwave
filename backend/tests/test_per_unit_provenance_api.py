"""API-level tests for the Per-Unit Settings hierarchy, Slice 3
channel-level provenance endpoints:
`GET .../sources/{source_id}/per-unit-resolution?channel_name=...` and
`GET .../calculated-channels/{id}/per-unit-resolution`. Exercises the
real FastAPI app end-to-end with the `synth_measurement_groups` fixture
(same one `test_measurement_group_api.py`/
`test_calculated_group_aware_per_unit_endpoints.py` already use) --
service-level classification edge cases have their own focused coverage
in `test_per_unit_provenance_service.py`; this file only proves the live
endpoints wire that service correctly against real upload metadata.

Fixture channel inventory (synth_measurement_groups.cfg): N275_VR/VY/VB
(Voltage, phase-to-ground), E275_VRY/VYB/VBR (Voltage, phase-to-phase),
IBT_HV_IR/IY/IB, LINEA_IR (Current), FREQ (not applicable).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL
from app.main import create_app
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_measurement_groups"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _voltage_group(client, workspace_id, source_id, channel_names, nominal_kv, display_name="VOLTAGE GROUP"):
    group = create_group(
        workspace_id=workspace_id, source_id=source_id, kind=KIND_VOLTAGE, display_name=display_name,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=STATUS_MANUAL,
        registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )
    set_voltage_base(
        workspace_id=workspace_id, measurement_group_id=group.id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _resolution(client, workspace_id, source_id, channel_name):
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/per-unit-resolution",
        params={"channel_name": channel_name},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_channel(client, workspace_id, name, operation, inputs, **extra):
    body = {
        "name": name, "operation": operation,
        "inputs": [{"kind": "source", "source_id": source_id, "channel_name": channel_name} for source_id, channel_name in inputs],
        **extra,
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/calculated-channels", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _calc_resolution(client, workspace_id, calc_id):
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/calculated-channels/{calc_id}/per-unit-resolution")
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSourceChannelResolutionEndpoint:
    def test_404_for_unknown_source(self, client):
        resp = client.get(
            "/api/v1/workspaces/ws-1/sources/does-not-exist/per-unit-resolution",
            params={"channel_name": "VR"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_404_for_unknown_channel_name(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution",
            params={"channel_name": "DOES_NOT_EXIST"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_400_for_a_digital_channel_name(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution",
            params={"channel_name": "BRK_A"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_analog"

    def test_grouped_lg_voltage_channel_matches_the_worked_example(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "BRDC 275 kV")

        body = _resolution(client, "ws-1", source_id, "N275_VR")
        assert body["status"] == "configured"
        assert body["source_kind"] == "measurement_group"
        assert body["measurement_group_id"] == group.id
        assert body["measurement_group_name"] == "BRDC 275 kV"
        assert body["nominal_base_kv"] == 275.0
        assert body["nominal_reference"] == "line_to_ground"
        assert body["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)
        assert body["effective_base_unit"] == "kV"

    def test_grouped_ll_voltage_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["E275_VRY", "E275_VYB", "E275_VBR"], 275.0, "E275 LINE")
        body = _resolution(client, "ws-1", source_id, "E275_VRY")
        assert body["status"] == "configured"
        assert body["nominal_reference"] == "line_to_line"
        assert body["effective_base_amount"] == pytest.approx(275.0, abs=1e-6)

    def test_grouped_current_channel(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group_resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups",
            json={
                "kind": "current", "display_name": "IBT1 HV",
                "channel_refs": [
                    {"kind": "source", "source_id": source_id, "channel_name": n}
                    for n in ("IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB")
                ],
            },
        )
        assert group_resp.status_code == 201, group_resp.text
        group_id = group_resp.json()["id"]
        cfg_resp = client.put(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups/{group_id}/current-config",
            json={"method": "equipment_rating", "equipment_rating_mva": 1000.0, "manual_voltage_base_kv": 275.0},
        )
        assert cfg_resp.status_code == 200, cfg_resp.text

        body = _resolution(client, "ws-1", source_id, "IBT_HV_IR")
        assert body["status"] == "configured"
        assert body["source_kind"] == "measurement_group"
        assert body["equipment_rating_mva"] == 1000.0
        assert body["applicable_voltage_ll_kv"] == 275.0
        assert body["effective_base_amount"] == pytest.approx(1000.0 / (SQRT_3 * 275.0), abs=1e-3)
        assert body["effective_base_unit"] == "kA"
        assert body["nominal_base_kv"] is None

    def test_grouped_incomplete_reports_a_useful_reason(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups",
            json={
                "kind": "voltage", "display_name": "275 NORTH BUS",
                "channel_refs": [
                    {"kind": "source", "source_id": source_id, "channel_name": n}
                    for n in ("N275_VR", "N275_VY", "N275_VB")
                ],
            },
        )
        body = _resolution(client, "ws-1", source_id, "N275_VR")
        assert body["status"] == "base_required"
        assert body["source_kind"] == "measurement_group"
        assert body["reason"] == "Voltage base is not configured for this group."

    def test_source_default_voltage_channel_is_truthful_no_ll_lg_label(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        # Manual line-to-line override: this fixture's own FULL voltage-
        # channel-name list spans both individual-phase (N275_V*/S132_V*)
        # and paired-phase (E275_V*) evidence, which under DEC-049's own
        # source-wide (never per-group) reference model is a genuine,
        # pre-existing "cannot auto-detect one reference for a source
        # spanning multiple conventions" case -- unrelated to and not
        # solved by this Slice 4 arithmetic fix. A manual override is
        # the realistic, existing escape hatch (section 7's own
        # "engineer authority" principle), and keeps this test's own
        # actual purpose (truthful display, not auto-detection) isolated.
        put_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 132.0, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_line"},
        )
        assert put_resp.status_code == 200, put_resp.text

        body = _resolution(client, "ws-1", source_id, "S132_VR")
        assert body["status"] == "configured"
        assert body["source_kind"] == "source_default"
        assert body["measurement_group_id"] is None
        assert body["nominal_base_kv"] is None
        assert body["nominal_reference"] is None
        assert body["effective_base_amount"] == pytest.approx(132.0, abs=1e-6)
        assert body["effective_base_unit"] == "kV"

    def test_ungrouped_channel_with_no_source_default_reports_a_useful_reason(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _resolution(client, "ws-1", source_id, "S132_VR")
        assert body["status"] == "base_required"
        assert body["source_kind"] == "source_default"
        assert body["reason"] == "No usable source-wide per-unit base is configured."

    def test_grouped_channel_never_reports_source_default_even_with_a_valid_one(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}", json={"voltage_base_value": 999.0})
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0)

        body = _resolution(client, "ws-1", source_id, "N275_VR")
        assert body["source_kind"] == "measurement_group"
        assert body["status"] == "configured"
        assert body["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_frequency_channel_is_not_applicable(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _resolution(client, "ws-1", source_id, "FREQ")
        assert body["status"] == "not_applicable"
        assert body["source_kind"] is None
        assert body["effective_base_amount"] is None


class TestCalculatedChannelResolutionEndpoint:
    def test_unary_calculated_channel_inherits_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "BRDC 275 kV")
        calc_id = _create_channel(
            client, "ws-1", "NEG_VR", "reverse_polarity", [(source_id, "N275_VR")]
        )
        body = _calc_resolution(client, "ws-1", calc_id)
        assert body["status"] == "configured"
        assert body["source_kind"] == "measurement_group"
        assert body["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_multi_input_voltage_addition_does_not_inherit_per_dec_052(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "BRDC 275 kV")
        calc_id = _create_channel(
            client, "ws-1", "VR_MINUS_VY", "subtraction", [(source_id, "N275_VR"), (source_id, "N275_VY")]
        )
        body = _calc_resolution(client, "ws-1", calc_id)
        assert body["status"] == "base_required"
        assert body["source_kind"] == "source_default"
        assert body["measurement_group_id"] is None
