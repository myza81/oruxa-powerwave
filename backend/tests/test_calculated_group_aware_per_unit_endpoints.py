"""Live-endpoint integration tests for DEC-050 Slice 7: group-aware
Per-Unit inheritance wired into the calculated-channel display
endpoints (`GET .../waveform`, `POST .../cursor-values`,
`.../annotation-anchor`, `.../peak-values`). Exercises the real
FastAPI app end-to-end, same fixture and helper conventions as
test_group_aware_per_unit_endpoints.py (Slice 5's own endpoint suite)
-- reused here rather than duplicated logic, only the calculated-
channel creation step and endpoint paths differ.

Fixture: synth_measurement_groups.cfg/.dat (see that module's own
docstring for the full channel list/values).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_MANUAL
from app.main import create_app
from app.services.current_group_config_service import set_current_base_manual, set_current_base_none
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


def _make_group(client, workspace_id, source_id, kind, channel_names, display_name, status=STATUS_MANUAL):
    return create_group(
        workspace_id=workspace_id, source_id=source_id, kind=kind, display_name=display_name,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=status,
        registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )


def _voltage_group(client, workspace_id, source_id, channel_names, nominal_kv, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_VOLTAGE, channel_names, display_name)
    set_voltage_base(
        workspace_id=workspace_id, measurement_group_id=group.id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=client.app.state.measurement_group_registry,
        voltage_config_registry=client.app.state.voltage_group_config_registry,
    )
    return group


def _current_group_manual(client, workspace_id, source_id, channel_names, manual_ibase_ka, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name)
    set_current_base_manual(
        workspace_id=workspace_id, measurement_group_id=group.id, manual_ibase_ka=manual_ibase_ka,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _current_group_none(client, workspace_id, source_id, channel_names, display_name):
    group = _make_group(client, workspace_id, source_id, KIND_CURRENT, channel_names, display_name)
    set_current_base_none(
        workspace_id=workspace_id, measurement_group_id=group.id,
        group_registry=client.app.state.measurement_group_registry,
        current_config_registry=client.app.state.current_group_config_registry,
    )
    return group


def _create_channel(client, workspace_id, name, operation, inputs, **extra):
    body = {
        "name": name, "operation": operation,
        "inputs": [{"kind": "source", "source_id": source_id, "channel_name": channel_name} for source_id, channel_name in inputs],
        **extra,
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/calculated-channels", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _via_waveform(client, workspace_id, calc_id):
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/calculated-channels/{calc_id}/waveform",
        params={"unit_mode": "per_unit"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["per_unit_status"], body["values"][0], body["unit"]


def _via_cursor_values(client, workspace_id, calc_id):
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/calculated-channels/cursor-values",
        json={"calculated_channel_ids": [calc_id], "cursor_a_time": 0.0, "cursor_b_time": None, "unit_mode": "per_unit"},
    )
    assert resp.status_code == 200, resp.text
    channel = resp.json()["channels"][0]
    return channel["per_unit_status"], channel["a_value"], channel["unit"]


def _via_annotation_anchor(client, workspace_id, calc_id):
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/calculated-channels/{calc_id}/annotation-anchor",
        json={"approximate_elapsed_seconds": 0.0, "unit_mode": "per_unit"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["per_unit_status"], body["value"], body["unit"]


def _via_peak_values(client, workspace_id, calc_id):
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/calculated-channels/peak-values",
        json={"start_time": 0.0, "end_time": 0.001, "unit_mode": "per_unit", "requests": [{"calculated_channel_id": calc_id, "mode": "max"}]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["results"][0]
    return result["per_unit_status"], result["value"], result["unit"]


_ALL_ENDPOINTS = [_via_waveform, _via_cursor_values, _via_annotation_anchor, _via_peak_values]


@pytest.fixture(params=_ALL_ENDPOINTS)
def via(request):
    return request.param


class TestSameGroupUnaryVoltageInheritance:
    def test_reverse_polarity_of_a_grouped_voltage_channel_inherits_that_groups_base(
        self, client, comtrade_fixtures_dir, via
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "N275")
        calc_id = _create_channel(client, "ws-1", "NEG_VR", "reverse_polarity", [(source_id, "N275_VR")])
        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "configured"
        assert unit == "pu"
        # N275_VR raw = 158.77 kV, negated; LG group's own denominator is
        # 275/sqrt(3) kV -- healthy phase-ground reading reads ~-1.0 pu.
        assert value == pytest.approx(-158770.0 / ((275.0 / SQRT_3) * 1000.0), abs=1e-6)


class TestSameGroupMultiInputCurrentInheritance:
    def test_addition_of_two_same_group_current_channels_inherits_that_groups_ibase(
        self, client, comtrade_fixtures_dir, via
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _current_group_manual(client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 4.199, "IBT HV")
        calc_id = _create_channel(
            client, "ws-1", "SUM_HV", "addition", [(source_id, "IBT_HV_IR"), (source_id, "IBT_HV_IY")]
        )
        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "configured"
        assert unit == "pu"
        assert value == pytest.approx((4199.0 + 4199.0) / 4199.0, abs=1e-6)


class TestVoltageMultiInputArithmeticNeverInherits:
    """Conservative LG/LL restriction: even a fully confirmed, unanimous
    same-Voltage-group Addition/Subtraction never auto-inherits (see
    app.services.calculated_group_aware_per_unit's own docstring)."""

    def test_subtraction_of_two_same_group_voltage_channels_is_base_required(
        self, client, comtrade_fixtures_dir, via
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "N275")
        calc_id = _create_channel(
            client, "ws-1", "VR_MINUS_VY", "subtraction", [(source_id, "N275_VR"), (source_id, "N275_VY")]
        )
        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "base_required"
        assert unit != "pu"
        assert value == pytest.approx(0.0, abs=1e-6)  # VR - VY, both 158.77 kV


class TestTransformerHvLvCrossGroupNeverInherits:
    """Section 23's own adversarial case, one layer up: a calculated
    channel combining HV-side and LV-side current can never pick either
    group's Ibase, no first-input fallback, no average."""

    def test_hv_plus_lv_current_addition_is_base_required(self, client, comtrade_fixtures_dir, via):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _current_group_manual(client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"], 2.1015, "IBT HV")
        _current_group_manual(client, "ws-1", source_id, ["IBT_LV_IR", "IBT_LV_IY", "IBT_LV_IB"], 4.375, "IBT LV")
        calc_id = _create_channel(
            client, "ws-1", "HV_PLUS_LV", "addition", [(source_id, "IBT_HV_IR"), (source_id, "IBT_LV_IR")]
        )
        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "base_required"
        assert unit != "pu"
        assert value == pytest.approx(4199.0 + 4199.0, abs=1e-6)


class TestDec051PrecedenceForCalculatedChannels:
    """Mirrors TestDec051PrecedenceAcrossMigratedEndpoints in
    test_group_aware_per_unit_endpoints.py one layer up: a calculated
    channel built from a channel grouped into a Current group with
    method=none must resolve base_required, even though a DEC-049
    source-wide profile exists on the same source that WOULD otherwise
    successfully convert it if it were consulted."""

    def test_calculated_channel_never_falls_back_to_dec049_when_its_input_group_is_unresolved(
        self, client, comtrade_fixtures_dir, via
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        put_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"current_base_mode": "direct", "direct_current_base_value": 9.0},
        )
        assert put_resp.status_code == 200, put_resp.text
        _current_group_none(client, "ws-1", source_id, ["LINEA_IR"], "LINE A CURRENT")
        calc_id = _create_channel(client, "ws-1", "ABS_LINEA", "absolute_value", [(source_id, "LINEA_IR")])

        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "base_required"
        # Had DEC-049 fallback incorrectly occurred, this would read
        # 3000/9000 = 0.333... with unit "pu" -- neither may appear.
        assert unit != "pu"
        assert value == pytest.approx(3000.0)


class TestUngroupedCalculatedChannelFallsBackToDec049:
    """The symmetric, positive case: a calculated channel whose only
    input is genuinely ungrouped continues to use the pre-existing
    DEC-049 calculated-channel inheritance, completely unchanged."""

    def test_calculated_channel_from_an_ungrouped_input_uses_dec049(self, client, comtrade_fixtures_dir, via):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        put_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"current_base_mode": "direct", "direct_current_base_value": 9.0},
        )
        assert put_resp.status_code == 200, put_resp.text
        # SPARE_IR is deliberately left ungrouped in the fixture.
        calc_id = _create_channel(client, "ws-1", "ABS_SPARE", "absolute_value", [(source_id, "SPARE_IR")])

        status, value, unit = via(client, "ws-1", calc_id)
        assert status == "configured"
        assert unit == "pu"
        assert value == pytest.approx(500.0 / 9000.0, abs=1e-9)


class TestCalculatedOnCalculatedInheritance:
    def test_a_chain_of_two_calculated_channels_still_inherits_the_same_group(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "N275")
        neg_id = _create_channel(client, "ws-1", "NEG_VR", "reverse_polarity", [(source_id, "N275_VR")])
        abs_resp = client.post(
            f"/api/v1/workspaces/ws-1/calculated-channels",
            json={
                "name": "ABS_NEG_VR", "operation": "absolute_value",
                "inputs": [{"kind": "calculated", "calculated_channel_id": neg_id}],
            },
        )
        assert abs_resp.status_code == 201, abs_resp.text
        abs_id = abs_resp.json()["id"]

        status, value, unit = _via_waveform(client, "ws-1", abs_id)
        assert status == "configured"
        assert unit == "pu"
        assert value == pytest.approx(158770.0 / ((275.0 / SQRT_3) * 1000.0), abs=1e-6)


class TestEngineeringModeUnaffected:
    def test_engineering_mode_values_are_unchanged_by_grouping(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        _voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], 275.0, "N275")
        calc_id = _create_channel(client, "ws-1", "NEG_VR", "reverse_polarity", [(source_id, "N275_VR")])
        resp = client.get(f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}/waveform")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["per_unit_status"] is None
        assert body["unit"] == "kV"
        assert body["values"][0] == pytest.approx(-158.77, abs=1e-6)
