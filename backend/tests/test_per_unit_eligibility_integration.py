"""Audit PU-003/004: metadata readiness must agree with real conversion.

Synthetic raw RMS series are constant *RMS measurements*, not instantaneous
sines. Their independent reference is 132 / sqrt(3) kV (phase) or 132 kV
(line-line). No RMS processing or primary/secondary scaling is bypassed.
"""

from dataclasses import asdict, replace
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.calculated_channel import ChannelRef
from app.domain.per_unit import (
    apply_per_unit_to_array, apply_per_unit_to_value,
    convert_array_to_pu, convert_value_to_pu,
)
from app.main import create_app
from app.services.compliance_series import Registries, load_series, unit_problem
from app.services.calculated_channel_service import _resolve_effective_per_unit_for_calculated_channel
from app.services.waveform_service import _resolve_effective_per_unit
from tests.test_per_unit_coverage_service import _active_source, _channel, _group, WORKSPACE, SOURCE
from tests.test_measured_unit_per_unit import _prepared_voltage_source
from tests.test_compliance_readiness_api import _add_reference
from tests.test_compliance_measurement_service import _sine_source


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as value:
        yield value


URL = f"/api/v1/workspaces/{WORKSPACE}"


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def seed(client, quantity=VOLTAGE, unit="V", name="VA", *, scope="source_default", configured=True):
    # Source metadata represents an absent unit as ""; the domain also
    # accepts None, which is exercised separately in the same assertions.
    meta = replace(_channel(name, quantity), unit=unit or "", waveform_form="rms")
    source = _active_source([meta])
    # Independently specified engineering measurements: 1 pu voltage,
    # or 1 pu on a manual 2 kA Current base.
    scale = 1000 if str(unit).strip().lower() in ("kv", "ka") else 1
    actual = (132000 / math.sqrt(3) if quantity == VOLTAGE else 2000) / scale
    source.record.waveform_data[name] = np.full(4, actual)
    client.app.state.workspace_registry.add(source)
    checked(client.put(f"{URL}/per-unit/sources/{SOURCE}", json={
        "voltage_base_value": 132, "current_base_mode": "direct", "direct_current_base_value": 2,
    }))
    if scope == "measurement_group":
        group = _group("group", "voltage" if quantity == VOLTAGE else "current", (name,))
        client.app.state.measurement_group_registry.add(group)
        if configured:
            suffix = "voltage-config" if quantity == VOLTAGE else "current-config"
            body = {"nominal_voltage_ll_kv": 132} if quantity == VOLTAGE else {"method": "manual", "manual_ibase_ka": 2}
            checked(client.put(f"{URL}/sources/{SOURCE}/measurement-groups/group/{suffix}", json=body))
    elif not configured:
        assert client.delete(f"{URL}/per-unit/sources/{SOURCE}").status_code == 204
    return source, actual


def reg(client):
    s = client.app.state
    return Registries(s.workspace_registry, s.calculated_channel_registry, s.per_unit_registry,
                      s.measurement_group_registry, s.voltage_group_config_registry, s.current_group_config_registry)


def resolution(client, source, name, quantity):
    r = reg(client)
    return _resolve_effective_per_unit(
        source, name, quantity, r.per_unit.get(WORKSPACE, SOURCE),
        [ch.name for ch in source.metadata.analog_channels if ch.engineering_type == VOLTAGE],
        workspace_id=WORKSPACE, group_registry=r.group, voltage_config_registry=r.voltage_config,
        current_config_registry=r.current_config,
    )


@pytest.mark.parametrize("scope", ["measurement_group", "source_default"])
@pytest.mark.parametrize("quantity,unit,ready", [
    (VOLTAGE, "V", True), (VOLTAGE, "kV", True), (VOLTAGE, " Kv ", True),
    (CURRENT, "A", True), (CURRENT, "kA", True),
    (VOLTAGE, "", False), (VOLTAGE, None, False), (CURRENT, "", False), (CURRENT, None, False),
    (VOLTAGE, "MW", False), (VOLTAGE, "A", False), (VOLTAGE, "mV", False),
    (CURRENT, "kV", False), (CURRENT, "Hz", False),
])
def test_raw_readiness_matches_scalar_array_and_waveform(client, quantity, unit, ready, scope):
    source, actual = seed(client, quantity, unit, scope=scope)
    r = resolution(client, source, "VA", quantity)
    original = asdict(r)
    values = np.asarray([actual, actual / 2])
    before = values.copy()
    scalar, scalar_unit, scalar_status = apply_per_unit_to_value(actual, unit, quantity, r)
    array, array_unit, array_status = apply_per_unit_to_array(values, unit, quantity, r)
    empty_value, empty_unit, empty_status = apply_per_unit_to_value(None, unit, quantity, r)
    waveform = checked(client.get(f"{URL}/sources/{SOURCE}/waveform", params={"channel_name": "VA", "unit_mode": "per_unit"}))
    provenance = checked(client.get(f"{URL}/sources/{SOURCE}/per-unit-resolution", params={"channel_name": "VA"}))
    coverage = checked(client.get(f"{URL}/per-unit/sources/{SOURCE}/coverage"))
    status = "configured" if ready else "base_required"
    assert scalar_status == array_status == empty_status == waveform["per_unit_status"] == provenance["status"] == status
    assert scalar_unit == array_unit == empty_unit == ("pu" if ready else unit)
    assert waveform["unit"] == ("pu" if ready else unit or "")
    assert scalar == pytest.approx(1 if ready else actual)
    np.testing.assert_allclose(array, [1, .5] if ready else values)
    np.testing.assert_allclose(waveform["values"], np.full(4, 1 if ready else actual))
    assert empty_value is None
    assert coverage[scope + "_count"] == int(ready)
    assert coverage["needs_configuration_count"] == int(not ready)
    assert coverage["applicable_channel_count"] == 1
    # An unavailable unit must not discard the accepted configuration/base.
    assert provenance["source_kind"] == scope
    assert provenance["effective_base_amount"] == pytest.approx(132 / math.sqrt(3) if quantity == VOLTAGE else 2)
    assert provenance["effective_base_unit"] == ("kV" if quantity == VOLTAGE else "kA")
    if not ready:
        assert "measured unit" in provenance["reason"].lower()
        assert convert_value_to_pu(actual, unit, r, quantity) is None
        assert convert_array_to_pu(values, unit, r, quantity) is None
    else:
        assert convert_value_to_pu(actual, unit, r, quantity) == pytest.approx(1)
        np.testing.assert_allclose(convert_array_to_pu(values, unit, r, quantity), [1, .5])
    assert asdict(r) == original
    np.testing.assert_array_equal(values, before)


@pytest.mark.parametrize("scope", ["measurement_group", "source_default"])
@pytest.mark.parametrize("quantity,unit", [(VOLTAGE, "V"), (CURRENT, "A")])
def test_incomplete_configuration_never_borrows_another_base(client, scope, quantity, unit):
    seed(client, quantity, unit, scope=scope, configured=False)
    provenance = checked(client.get(f"{URL}/sources/{SOURCE}/per-unit-resolution", params={"channel_name": "VA"}))
    waveform = checked(client.get(f"{URL}/sources/{SOURCE}/waveform", params={"channel_name": "VA", "unit_mode": "per_unit"}))
    coverage = checked(client.get(f"{URL}/per-unit/sources/{SOURCE}/coverage"))
    assert provenance["status"] == waveform["per_unit_status"] == "base_required"
    assert provenance["effective_base_amount"] is None
    assert coverage["needs_configuration_count"] == 1


@pytest.mark.parametrize("scope", ["measurement_group", "source_default"])
@pytest.mark.parametrize("quantity,unit,ready", [
    (VOLTAGE, "V", True), (VOLTAGE, "kV", True), (VOLTAGE, "", False), (VOLTAGE, "MW", False),
    (CURRENT, "A", True), (CURRENT, "kA", True), (CURRENT, "", False), (CURRENT, "V", False),
])
def test_calculated_units_use_the_same_readiness_contract(client, scope, quantity, unit, ready):
    _, actual = seed(client, quantity=quantity, unit=unit, scope=scope)
    channel = checked(client.post(f"{URL}/calculated-channels", json={
        "name": "Negative VA", "operation": "reverse_polarity",
        "inputs": [{"kind": "source", "source_id": SOURCE, "channel_name": "VA"}],
    }), 201)
    cid = channel["id"]
    provenance = checked(client.get(f"{URL}/calculated-channels/{cid}/per-unit-resolution"))
    waveform = checked(client.get(f"{URL}/calculated-channels/{cid}/waveform", params={"unit_mode": "per_unit"}))
    assert provenance["status"] == waveform["per_unit_status"] == ("configured" if ready else "base_required")
    assert provenance["source_kind"] == scope
    assert provenance["effective_base_amount"] == pytest.approx(132 / math.sqrt(3) if quantity == VOLTAGE else 2)
    np.testing.assert_allclose(waveform["values"], np.full(4, -1 if ready else -actual))
    r = reg(client)
    stored = r.calc.get(WORKSPACE, cid)
    resolved = _resolve_effective_per_unit_for_calculated_channel(
        stored, r.per_unit.get(WORKSPACE, SOURCE), ["VA"] if quantity == VOLTAGE else [],
        workspace_id=WORKSPACE, calc_registry=r.calc, group_registry=r.group,
        voltage_config_registry=r.voltage_config, current_config_registry=r.current_config,
    )
    scalar, out_unit, status = apply_per_unit_to_value(-actual, unit, quantity, resolved)
    assert status == waveform["per_unit_status"]
    assert out_unit == waveform["unit"]
    assert scalar == pytest.approx(waveform["values"][0])
    if quantity == VOLTAGE:
        ref = ChannelRef(kind="calculated", calculated_channel_id=cid)
        series, problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=r)
        assert (problem is None) == ready
        if ready:
            np.testing.assert_allclose(series.values, waveform["values"], rtol=1e-12)
        else:
            assert series is None


def test_original_csv_missing_unit_reproduction(client):
    prep = _prepared_voltage_source(client, measured_unit=None)
    sid = checked(client.post(f"{URL}/preparation-sources/{prep}/convert"))["source_id"]
    groups_url = f"{URL}/sources/{sid}/measurement-groups"
    for group in checked(client.get(groups_url)):
        assert client.delete(f"{groups_url}/{group['id']}").status_code == 204
    checked(client.put(f"{URL}/per-unit/sources/{sid}", json={"voltage_base_value": 132}))
    waveform = checked(client.get(f"{URL}/sources/{sid}/waveform", params={"channel_name": "VR", "unit_mode": "per_unit"}))
    provenance = checked(client.get(f"{URL}/sources/{sid}/per-unit-resolution", params={"channel_name": "VR"}))
    coverage = checked(client.get(f"{URL}/per-unit/sources/{sid}/coverage"))
    assert waveform["per_unit_status"] == provenance["status"] == "base_required"
    assert waveform["values"] == [1.32, 1.33, 1.31]
    assert waveform["unit"] == ""
    assert coverage["source_default_count"] == 0 and coverage["needs_configuration_count"] == 1


@pytest.mark.parametrize("unit", ["V", "kV"])
@pytest.mark.parametrize("name,reference", [("VA", "line_to_ground"), ("VAB", "line_to_line")])
def test_compliance_source_default_auto_matches_waveform_rms(client, unit, name, reference):
    source, _ = seed(client, unit=unit, name=name)
    actual = (132 / math.sqrt(3) if reference == "line_to_ground" else 132) * (1000 if unit == "V" else 1)
    source.record.waveform_data[name] = np.full(4, actual)
    ref = ChannelRef(kind="source", source_id=SOURCE, channel_name=name)
    assert unit_problem(ref, "pu", workspace_id=WORKSPACE, reg=reg(client)) is None
    series, problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
    assert problem is None
    np.testing.assert_allclose(series.values, np.ones(4), rtol=1e-12)
    waveform = checked(client.get(f"{URL}/sources/{SOURCE}/waveform", params={"channel_name": name, "unit_mode": "per_unit"}))
    assert waveform["per_unit_status"] == "configured"
    np.testing.assert_allclose(series.values, waveform["values"], rtol=1e-12)


@pytest.mark.parametrize("unit,name,manual,ready", [
    ("V", "Unknown", None, False), ("V", "Unknown", "line_to_ground", True),
    ("V", "VAB", "line_to_ground", True), ("", "VA", None, False),
    ("MW", "VA", None, False), ("V", "VA", "line_to_line", True),
])
def test_compliance_source_default_manual_and_unavailable_inputs(client, unit, name, manual, ready):
    source, _ = seed(client, unit=unit, name=name)
    if manual:
        checked(client.put(f"{URL}/per-unit/sources/{SOURCE}", json={
            "voltage_base_value": 132, "voltage_reference_mode": "manual", "voltage_reference_override": manual,
        }))
    denominator = 132000 if manual == "line_to_line" else 132000 / math.sqrt(3)
    source.record.waveform_data[name] = np.full(4, denominator)
    ref = ChannelRef(kind="source", source_id=SOURCE, channel_name=name)
    problem = unit_problem(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
    series, load_problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
    assert (problem is None) == ready
    assert load_problem == problem
    if ready:
        np.testing.assert_allclose(series.values, np.ones(4), rtol=1e-12)
    else:
        assert series is None


@pytest.mark.parametrize("unit,ready", [("V", True), ("", False), ("A", False)])
def test_compliance_readiness_and_actual_trace_keep_group_precedence(client, unit, ready):
    seed(client, unit=unit, scope="measurement_group")
    # A conflicting source base must never override the group's 132 kV.
    checked(client.put(f"{URL}/per-unit/sources/{SOURCE}", json={"voltage_base_value": 275}))
    # This shared helper targets a different test workspace; create the same
    # real profile/layer via a small request adapter, not a separate model.
    class WorkspaceClient:
        def post(self, url, **kwargs):
            return client.post(url.replace("ws-readiness-1", WORKSPACE), **kwargs)
    _add_reference(WorkspaceClient(), representation="phase_ground_rms", treatment="single", member="A")
    readiness = checked(client.get(f"{URL}/compliance/voltage/readiness", params={"measurement_group_id": "group"}))
    traces = checked(client.get(f"{URL}/compliance/voltage/measurement-traces", params={"measurement_group_id": "group"}))
    assert readiness["status"] == traces["readiness_status"] == ("ready" if ready else "action_required")
    if ready:
        assert len(traces["traces"]) == 1
        np.testing.assert_allclose(traces["traces"][0]["y"], np.ones(4), rtol=1e-12)
        assert traces["traces"][0]["unit"] == "pu"
    else:
        assert traces["traces"] == []


@pytest.mark.parametrize("scope", ["source_default", "measurement_group"])
def test_angle_quantity_stays_excluded_even_with_voltage_units_and_base(client, scope):
    source, _ = seed(client, scope=scope)
    source.metadata.analog_channels[0].engineering_quantity = "Voltage Angle"
    r = resolution(client, source, "VA", VOLTAGE)
    assert apply_per_unit_to_value(10, "V", VOLTAGE, r) == (10, "V", "not_applicable")
    waveform = checked(client.get(f"{URL}/sources/{SOURCE}/waveform", params={"channel_name": "VA", "unit_mode": "per_unit"}))
    provenance = checked(client.get(f"{URL}/sources/{SOURCE}/per-unit-resolution", params={"channel_name": "VA"}))
    assert waveform["per_unit_status"] == provenance["status"] == "not_applicable"
    coverage = checked(client.get(f"{URL}/per-unit/sources/{SOURCE}/coverage"))
    assert coverage["applicable_channel_count"] == 0
    ref = ChannelRef(kind="source", source_id=SOURCE, channel_name="VA")
    assert unit_problem(ref, "pu", workspace_id=WORKSPACE, reg=reg(client)) is not None


def test_ambiguous_auto_reference_remains_unavailable_until_manual_override(client):
    source, _ = seed(client)
    source.metadata.analog_channels.append(_channel("VAB", VOLTAGE))
    source.record.waveform_data["VAB"] = 132000
    ref = ChannelRef(kind="source", source_id=SOURCE, channel_name="VA")
    assert unit_problem(ref, "pu", workspace_id=WORKSPACE, reg=reg(client)) is not None
    checked(client.put(f"{URL}/per-unit/sources/{SOURCE}", json={
        "voltage_base_value": 132, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground",
    }))
    series, problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
    assert problem is None
    np.testing.assert_allclose(series.values, np.ones(4), rtol=1e-12)


@pytest.mark.parametrize("scope", ["source_default", "measurement_group"])
@pytest.mark.parametrize("unit", ["V", "kV"])
def test_real_rms_calculated_voltage_matches_compliance_without_instantaneous_rms_confusion(client, scope, unit):
    seed(client, unit=unit, scope=scope)
    # 50 Hz instantaneous phase voltage with independently chosen RMS
    # 132/sqrt(3) kV. Let the real shared RMS operation produce the series.
    amplitude = 132 * math.sqrt(2 / 3) * (1000 if unit == "V" else 1)
    source = _sine_source(SOURCE, [("VA", amplitude, 0)], duration_s=.1)
    source.metadata = replace(source.metadata, workspace_id=WORKSPACE,
                              analog_channels=[replace(source.metadata.analog_channels[0], unit=unit)])
    client.app.state.workspace_registry.add(source)
    calculated = checked(client.post(f"{URL}/calculated-channels", json={
        "name": "RMS VA", "operation": "rms", "parameters": {"nominal_frequency_hz": 50},
        "inputs": [{"kind": "source", "source_id": SOURCE, "channel_name": "VA"}],
    }), 201)
    ref = ChannelRef(kind="calculated", calculated_channel_id=calculated["id"])
    series, problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
    assert problem is None
    finite = series.values[np.isfinite(series.values)]
    assert len(finite) > 300
    np.testing.assert_allclose(finite, np.ones(len(finite)), rtol=1e-12)
    waveform = checked(client.get(f"{URL}/calculated-channels/{calculated['id']}/waveform",
                                 params={"unit_mode": "per_unit"}))
    assert waveform["per_unit_status"] == "configured"
    values = np.asarray([np.nan if v is None else v for v in waveform["values"]])
    np.testing.assert_allclose(series.values, values, rtol=1e-12, equal_nan=True)
