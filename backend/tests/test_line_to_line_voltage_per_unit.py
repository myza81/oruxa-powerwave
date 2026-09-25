"""Per-Unit regression for Line-to-Line Voltage outputs (DEC-115).

The 275 kV vs 158.77 kV ambiguity must never recur:

    nominal system = 275 kV L-L
    Va  (phase-to-ground source)   base = 275 / sqrt(3) kV
    VAB (declared line_to_line)    base = 275 kV

Covered on BOTH resolution paths -- a confirmed Voltage Measurement Group
(DEC-050) and the Source Default profile (DEC-049) -- and for unary
descendants (RMS(VAB)), while generic Subtraction keeps DEC-052's
`base_required`. The representation comes from the channel's own
declared metadata, never from its name (a renamed "first" channel still
resolves L-L).
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL
from app.main import create_app
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772
WS = "ws-pu"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload_clearing_groups(client, comtrade_fixtures_dir):
    stem = "line_to_line_multibay"
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO((comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO((comtrade_fixtures_dir / f"{stem}.dat").read_bytes()), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{WS}/sources", files=files)
    assert resp.status_code == 201, resp.text
    source_id = resp.json()["source_id"]
    groups_url = f"/api/v1/workspaces/{WS}/sources/{source_id}/measurement-groups"
    for group in client.get(groups_url).json():
        client.delete(f"{groups_url}/{group['id']}")
    return source_id


def _kpdn1_context_id(client):
    return next(
        c["id"] for c in client.get(f"/api/v1/workspaces/{WS}/engineering-contexts").json()
        if c["display_name"] == "KPDN1"
    )


def _create_ll(client, output="all_three", **extra):
    resp = client.post(
        f"/api/v1/workspaces/{WS}/calculated-channels/line-to-line-voltage",
        json={"engineering_context_id": _kpdn1_context_id(client), "output": output, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["channels"]


def _create_generic(client, name, operation, inputs, **extra):
    resp = client.post(
        f"/api/v1/workspaces/{WS}/calculated-channels",
        json={"name": name, "operation": operation, "inputs": inputs, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _calc_pu(client, calc_id):
    resp = client.get(f"/api/v1/workspaces/{WS}/calculated-channels/{calc_id}/per-unit-resolution")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _source_pu(client, source_id, channel_name):
    resp = client.get(
        f"/api/v1/workspaces/{WS}/sources/{source_id}/per-unit-resolution", params={"channel_name": channel_name}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _kpdn1_voltage_group_275(client, source_id):
    group = create_group(
        workspace_id=WS, source_id=source_id, kind=KIND_VOLTAGE, display_name="KPDN1 275 kV",
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in ("KPDN1_VR", "KPDN1_VY", "KPDN1_VB")],
        status=STATUS_MANUAL,
        registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry,
    )
    set_voltage_base(
        workspace_id=WS, measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


class TestMeasurementGroupPath:
    @pytest.fixture
    def source_id(self, client, comtrade_fixtures_dir):
        source_id = _upload_clearing_groups(client, comtrade_fixtures_dir)
        _kpdn1_voltage_group_275(client, source_id)
        return source_id

    def test_phase_ground_source_uses_lg_base(self, client, source_id):
        pu = _source_pu(client, source_id, "KPDN1_VR")
        assert pu["status"] == "configured"
        assert pu["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)  # 158.77 kV

    def test_each_ll_output_uses_ll_base(self, client, source_id):
        for channel in _create_ll(client):
            pu = _calc_pu(client, channel["id"])
            assert pu["status"] == "configured", channel["name"]
            assert pu["effective_base_amount"] == pytest.approx(275.0), channel["name"]  # never 158.77
            assert pu["nominal_reference"] == "line_to_line"

    def test_waveform_pu_values_divide_by_ll_base(self, client, source_id):
        vab = _create_ll(client, "AB")[0]
        engineering = client.app.state.calculated_channel_registry.get(WS, vab["id"]).values
        resp = client.get(
            f"/api/v1/workspaces/{WS}/calculated-channels/{vab['id']}/waveform",
            params={"unit_mode": "per_unit", "point_budget": 5000},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] == "configured"
        np.testing.assert_allclose(np.array(body["values"], dtype=float), engineering / 275.0, rtol=1e-12)
        # Healthy pre-fault VAB peaks at sqrt(2) x 1.0 pu (not sqrt(2) x
        # sqrt(3), nor sqrt(2)/sqrt(3)). At 20 samples/cycle the nearest
        # sample can sit up to half a step (9 deg) from the true crest.
        pre_fault_peak = np.max(np.abs(np.array(body["values"][:400], dtype=float)))
        assert np.sqrt(2) * np.cos(np.radians(9)) <= pre_fault_peak <= np.sqrt(2) + 1e-9

    def test_representation_is_not_read_from_the_name(self, client, source_id):
        renamed = _create_ll(client, "BC", names={"BC": "first"})[0]
        assert _calc_pu(client, renamed["id"])["effective_base_amount"] == pytest.approx(275.0)

    def test_unary_descendant_stays_line_to_line(self, client, source_id):
        vab = _create_ll(client, "AB")[0]
        rms = _create_generic(
            client, "RMS KPDN1 VAB", "rms", [{"kind": "calculated", "calculated_channel_id": vab["id"]}],
            parameters={"nominal_frequency_hz": 50},
        )
        assert rms["voltage_representation"] == "line_to_line"
        assert rms["phase_member"] == "AB"
        assert _calc_pu(client, rms["id"])["effective_base_amount"] == pytest.approx(275.0)

    def test_generic_subtraction_keeps_dec052_base_required(self, client, source_id):
        generic = _create_generic(client, "VR - VY", "subtraction", [
            {"kind": "source", "source_id": source_id, "channel_name": "KPDN1_VR"},
            {"kind": "source", "source_id": source_id, "channel_name": "KPDN1_VY"},
        ])
        assert generic["voltage_representation"] is None
        assert _calc_pu(client, generic["id"])["status"] == "base_required"

    def test_multi_input_of_ll_channels_does_not_propagate(self, client, source_id):
        vab, vbc, _ = _create_ll(client)
        total = _create_generic(client, "VAB + VBC", "addition", [
            {"kind": "calculated", "calculated_channel_id": vab["id"]},
            {"kind": "calculated", "calculated_channel_id": vbc["id"]},
        ])
        assert total["voltage_representation"] is None


class TestSourceDefaultPath:
    @pytest.fixture
    def source_id(self, client, comtrade_fixtures_dir):
        source_id = _upload_clearing_groups(client, comtrade_fixtures_dir)
        resp = client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source_id}", json={"voltage_base_value": 275.0})
        assert resp.status_code == 200, resp.text
        return source_id

    def test_phase_ground_source_uses_lg_base(self, client, source_id):
        pu = _source_pu(client, source_id, "KPDN1_VR")
        assert pu["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_ll_outputs_use_ll_base_despite_lg_source_detection(self, client, source_id):
        """The source's own channels auto-detect as line-to-ground; the
        derived VAB/VBC/VCA must still divide by the L-L base."""
        for channel in _create_ll(client):
            pu = _calc_pu(client, channel["id"])
            assert pu["status"] == "configured"
            assert pu["effective_base_amount"] == pytest.approx(275.0)
            assert pu["nominal_reference"] == "line_to_line"
