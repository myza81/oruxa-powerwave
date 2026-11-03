"""Audit PU-006/007: numeric base safety, input types and atomic rejection."""

from decimal import Decimal, localcontext
import math

import numpy as np
import pytest

from app.domain.per_unit import (
    PerUnitResolution, apply_per_unit_to_array, apply_per_unit_to_value,
    convert_array_to_pu, convert_value_to_pu,
)
from tests.test_per_unit_atomic_updates import (
    WS, _snapshot, _waveform, client, configured,  # noqa: F401 -- real app/group fixtures
)
from tests.test_measurement_group_api import _base_url
from app.domain.per_unit import voltage_base_valid, direct_current_base_valid, apparent_power_base_valid
from app.domain.current_group_config import (
    equipment_rating_mva_valid, manual_voltage_base_kv_valid, manual_ibase_ka_valid,
    equipment_rating_ibase_ka,
)
from app.domain.voltage_group_config import voltage_base_valid as group_voltage_base_valid
from app.domain.calculated_channel import ChannelRef
from app.services.compliance_series import load_series, unit_problem
from tests.test_per_unit_eligibility_integration import seed, checked, reg, URL, WORKSPACE, SOURCE


@pytest.fixture
def numeric_configured(client, configured):
    source, voltage, current, voltage_url = configured
    assert client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source}", json={
        "voltage_base_value": 275, "voltage_reference_mode": "manual",
        "voltage_reference_override": "line_to_ground", "current_base_mode": "derived",
        "apparent_power_base_value": 1000,
    }).status_code == 200
    return source, voltage, current, voltage_url


FIELDS = [
    ("voltage", "nominal_voltage_ll_kv"),
    ("current", "manual_ibase_ka"),
    ("current", "equipment_rating_mva"),
    ("current", "manual_voltage_base_kv"),
    ("source", "voltage_base_value"),
    ("source", "direct_current_base_value"),
    ("source", "apparent_power_base_value"),
]


def request_for(configured, scope, field, value):
    source, voltage, current, voltage_url = configured
    if scope == "voltage":
        url, body = voltage_url + "/voltage-config", {}
    elif scope == "current":
        url = f"{_base_url(WS, source)}/{current}/current-config"
        if field == "manual_ibase_ka":
            body = {"method": "manual"}
        elif field == "manual_voltage_base_kv":
            body = {"method": "equipment_rating", "equipment_rating_mva": 1000}
        else:
            body = {"method": "equipment_rating", "linked_voltage_group_id": voltage}
    else:
        url = f"/api/v1/workspaces/{WS}/per-unit/sources/{source}"
        body = {"voltage_base_value": 275, "voltage_reference_mode": "manual",
                "voltage_reference_override": "line_to_ground", "current_base_mode": "derived",
                "apparent_power_base_value": 1000}
        if field == "direct_current_base_value":
            body["current_base_mode"] = "direct"
    body[field] = value
    return url, body


@pytest.mark.parametrize("scope,field", FIELDS)
@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("initial", [False, True])
def test_boolean_numeric_inputs_rejected_without_any_state_change(client, numeric_configured, scope, field, value, initial):
    source = numeric_configured[0]
    if initial:
        state = client.app.state
        registry, key = {
            "voltage": (state.voltage_group_config_registry, numeric_configured[1]),
            "current": (state.current_group_config_registry, numeric_configured[2]),
            "source": (state.per_unit_registry, source),
        }[scope]
        registry.delete(WS, key)
    before = _snapshot(client, source)
    url, body = request_for(numeric_configured, scope, field, value)
    response = client.put(url, json=body)
    assert response.status_code in (400, 422), response.text
    assert _snapshot(client, source) == before


@pytest.mark.parametrize("scope,field,value", [
    ("voltage", "nominal_voltage_ll_kv", 1e308),
    ("current", "manual_ibase_ka", 1e308),
    ("current", "manual_voltage_base_kv", 1e308),
    ("source", "voltage_base_value", 1e308),
    ("source", "direct_current_base_value", 1e308),
])
def test_unrepresentable_si_base_rejection_is_atomic(client, numeric_configured, scope, field, value):
    source = numeric_configured[0]
    before = _snapshot(client, source)
    url, body = request_for(numeric_configured, scope, field, value)
    response = client.put(url, json=body)
    assert response.status_code in (400, 422), response.text
    assert _snapshot(client, source) == before


@pytest.mark.parametrize("scope", ["current", "source"])
@pytest.mark.parametrize("rating,voltage", [(1e308, 1e-300), (1e-320, 1e300)])
def test_invalid_derived_current_base_rejection_is_atomic(client, numeric_configured, scope, rating, voltage):
    source, _, current, _ = numeric_configured
    before = _snapshot(client, source)
    if scope == "current":
        url = f"{_base_url(WS, source)}/{current}/current-config"
        body = {"method": "equipment_rating", "equipment_rating_mva": rating, "manual_voltage_base_kv": voltage}
    else:
        url = f"/api/v1/workspaces/{WS}/per-unit/sources/{source}"
        body = {"voltage_base_value": voltage, "voltage_reference_mode": "manual",
                "voltage_reference_override": "line_to_ground", "current_base_mode": "derived",
                "apparent_power_base_value": rating}
    response = client.put(url, json=body)
    assert response.status_code in (400, 422), response.text
    assert _snapshot(client, source) == before


@pytest.mark.parametrize("denominator", [0.0, -1.0, math.inf, math.nan])
def test_invalid_effective_denominator_never_reports_configured(denominator):
    resolution = PerUnitResolution("configured", "profile", denominator, "V", None)
    values = np.asarray([1., -1., 0.])
    scalar = apply_per_unit_to_value(1., "V", "Voltage", resolution)
    array, unit, status = apply_per_unit_to_array(values, "V", "Voltage", resolution)
    assert scalar == (1., "V", "base_required")
    assert (unit, status) == ("V", "base_required")
    np.testing.assert_array_equal(array, values)
    assert convert_value_to_pu(1., "V", resolution, "Voltage") is None
    assert convert_array_to_pu(values, "V", resolution, "Voltage") is None


@pytest.mark.parametrize("value,unit,base,expected", [
    (1e308, "kV", 1e308, 1000.),  # finite quotient despite SI numerator overflow
    (1e-320, "V", 1e-320, 1.),   # valid subnormal division; no reciprocal needed
    (0., "V", 1e-320, 0.),       # real zero stays a valid zero
    (-132000., "V", 132000., -1.),
    (np.nextafter(0., 1.), "V", 1., np.nextafter(0., 1.)),
])
def test_stable_finite_scalar_array_results(value, unit, base, expected):
    resolution = PerUnitResolution("configured", "profile", base, "V", None)
    scalar = apply_per_unit_to_value(value, unit, "Voltage", resolution)
    vector, out_unit, status = apply_per_unit_to_array(np.asarray([value]), unit, "Voltage", resolution)
    assert scalar[1:] == (out_unit, status) == ("pu", "configured")
    assert math.isfinite(scalar[0])
    assert scalar[0] == pytest.approx(expected, rel=1e-12, abs=0)
    assert vector[0] == scalar[0]


@pytest.mark.parametrize("value,base", [(1e308, 1e-308), (-1e308, 1e-308),
                                        (np.nextafter(0., 1.), 2.), (1e-300, 1e308)])
def test_unrepresentable_result_is_unavailable_not_false_zero_or_null_configured(value, base):
    resolution = PerUnitResolution("configured", "profile", base, "V", None)
    scalar = apply_per_unit_to_value(value, "V", "Voltage", resolution)
    vector, unit, status = apply_per_unit_to_array(np.asarray([value]), "V", "Voltage", resolution)
    assert scalar == (value, "V", "base_required")
    assert (unit, status) == ("V", "base_required")
    assert vector[0] == value
    assert convert_value_to_pu(value, "V", resolution, "Voltage") is None
    assert convert_array_to_pu(np.asarray([value]), "V", resolution, "Voltage") is None


def test_tiny_but_representable_base_has_honest_channel_readiness(client, numeric_configured):
    source, _, _, url = numeric_configured
    # This base has a finite positive SI denominator; the recorded ordinary
    # voltage cannot be normalized into float64. Configuration and result
    # availability are separate, using the existing base_required status.
    response = client.put(url + "/voltage-config", json={"nominal_voltage_ll_kv": 1e-320})
    assert response.status_code == 200, response.text
    waveform = _waveform(client, source, "N275_VR")
    engineering = _waveform(client, source, "N275_VR", "engineering")
    provenance = client.get(f"/api/v1/workspaces/{WS}/sources/{source}/per-unit-resolution",
                            params={"channel_name": "N275_VR"}).json()
    assert waveform["per_unit_status"] == provenance["status"] == "base_required"
    assert waveform["values"] == engineering["values"]
    assert waveform["unit"] == engineering["unit"]
    assert all(v is not None and math.isfinite(v) and v != 0 for v in waveform["values"])


def test_source_derived_current_avoids_intermediate_mva_overflow(client, numeric_configured):
    source = numeric_configured[0]
    response = client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source}", json={
        "voltage_base_value": 1e300, "voltage_reference_mode": "manual",
        "voltage_reference_override": "line_to_ground", "current_base_mode": "derived",
        "apparent_power_base_value": 1e308,
    })
    assert response.status_code == 200, response.text
    with localcontext() as ctx:
        ctx.prec = 80
        expected = float(Decimal('1e308') / Decimal('1e300') * Decimal(1000) / Decimal(3).sqrt())
    assert response.json()["resolved_current_base"]["value"] == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("scope,field", FIELDS)
@pytest.mark.parametrize("value", [132, 132.5, "132.5"])
def test_numeric_input_compatibility(client, numeric_configured, scope, field, value):
    url, body = request_for(numeric_configured, scope, field, value)
    response = checked(client.put(url, json=body))
    config = response if scope == "source" else response[scope + "_config"]
    assert config[field] == float(value)
    assert not isinstance(config[field], bool)


@pytest.mark.parametrize("scope,field", FIELDS)
@pytest.mark.parametrize("value", [0, -1])
def test_nonpositive_api_inputs_are_atomic(client, numeric_configured, scope, field, value):
    before = _snapshot(client, numeric_configured[0])
    url, body = request_for(numeric_configured, scope, field, value)
    assert client.put(url, json=body).status_code in (400, 422)
    assert _snapshot(client, numeric_configured[0]) == before


@pytest.mark.parametrize("validate", [voltage_base_valid, group_voltage_base_valid, direct_current_base_valid,
                                      apparent_power_base_valid, equipment_rating_mva_valid,
                                      manual_voltage_base_kv_valid, manual_ibase_ka_valid])
@pytest.mark.parametrize("value", [None, True, False, 0, -1, math.nan, math.inf, -math.inf])
def test_domain_rejects_invalid_numeric_types_and_values(validate, value):
    assert not validate(value)


def test_omissions_and_explicit_null_keep_existing_contract(client, numeric_configured):
    source, _, current, voltage_url = numeric_configured
    assert checked(client.put(voltage_url + "/voltage-config", json={"nominal_voltage_ll_kv": None}))[
        "voltage_config"]["nominal_voltage_ll_kv"] == 275
    assert checked(client.put(voltage_url + "/voltage-config", json={}))[
        "voltage_config"]["nominal_voltage_ll_kv"] == 275
    before = _snapshot(client, source)
    assert client.put(f"{_base_url(WS, source)}/{current}/current-config", json={
        "method": "manual", "manual_ibase_ka": None,
    }).status_code == 400
    assert _snapshot(client, source) == before
    # Source Default PUT is full replacement, unlike the nominal omission
    # semantics of the Voltage Group endpoint. Missing bases remain allowed.
    for body in ({}, {"voltage_base_value": None, "direct_current_base_value": None,
                      "apparent_power_base_value": None, "current_base_mode": "derived"}):
        response = checked(client.put(f"/api/v1/workspaces/{WS}/per-unit/sources/{source}", json=body))
        assert response["voltage_base_value"] is None
        assert response["resolved_current_base"] is None


@pytest.mark.parametrize("rating,voltage", [(1000., 132.), (1000., 275.), (1e308, 1e300),
                                           (1e-320, 1e-320), (1e-310, 1.)])
def test_derived_current_against_independent_decimal(rating, voltage):
    with localcontext() as ctx:
        ctx.prec = 100
        expected = float(Decimal.from_float(rating) / (Decimal(3).sqrt() * Decimal.from_float(voltage)))
    actual = equipment_rating_ibase_ka(rating, voltage)
    assert actual == pytest.approx(expected, rel=1e-12, abs=np.nextafter(0., 1.))
    assert math.isfinite(actual) and actual > 0


@pytest.mark.parametrize("linked", [False, True])
def test_group_derived_current_large_finite_accepted(client, numeric_configured, linked):
    source, voltage, current, voltage_url = numeric_configured
    checked(client.put(voltage_url + "/voltage-config", json={"nominal_voltage_ll_kv": 1e300}))
    body = {"method": "equipment_rating", "equipment_rating_mva": 1e308}
    body.update({"linked_voltage_group_id": voltage} if linked else {"manual_voltage_base_kv": 1e300})
    config = checked(client.put(f"{_base_url(WS, source)}/{current}/current-config", json=body))["current_config"]
    with localcontext() as ctx:
        ctx.prec = 80
        expected = float(Decimal('1e8') / Decimal(3).sqrt())
    assert config["resolved_ibase_ka"] == pytest.approx(expected, rel=1e-12)
    waveform = _waveform(client, source, "IBT_HV_IR")
    assert waveform["per_unit_status"] == "configured" and waveform["unit"] == "pu"
    assert waveform["values"] == pytest.approx([4199 / (expected * 1000)] * 5, rel=1e-12)


@pytest.mark.parametrize("scope", ["measurement_group", "source_default"])
@pytest.mark.parametrize("quantity,base,values,ready", [
    ("Voltage", 1e-320, [1., -1., 0., 2.], False),
    ("Voltage", 1e-320, [1e-320, -1e-320, 0., 2e-320], True),
    ("Current", 1e-320, [1., -1., 0., 2.], False),
    ("Current", 1e-320, [1e-320, -1e-320, 0., 2e-320], True),
    ("Voltage", 132., [1e-320, 1., -1., 0.], False),  # nonzero underflow
    ("Voltage", 132., [132000 / math.sqrt(3), -132000 / math.sqrt(3), 0., 1.], True),
])
def test_full_channel_readiness_matches_viewports_cursors_calculated_and_compliance(
    client, scope, quantity, base, values, ready,
):
    source, _ = seed(client, quantity=quantity, unit="V" if quantity == "Voltage" else "A", scope=scope)
    source.record.waveform_data["VA"] = np.asarray(values)
    before = source.record.waveform_data.copy(deep=True)
    if scope == "measurement_group":
        suffix = "voltage-config" if quantity == "Voltage" else "current-config"
        body = {"nominal_voltage_ll_kv": base} if quantity == "Voltage" else {"method": "manual", "manual_ibase_ka": base}
        checked(client.put(f"{URL}/sources/{SOURCE}/measurement-groups/group/{suffix}", json=body))
    else:
        checked(client.put(f"{URL}/per-unit/sources/{SOURCE}", json={
            "voltage_base_value": base, "current_base_mode": "direct", "direct_current_base_value": base,
        }))
    status = "configured" if ready else "base_required"
    unit = "pu" if ready else ("V" if quantity == "Voltage" else "A")
    root = f"{URL}/sources/{SOURCE}"
    waveform = checked(client.get(root + "/waveform", params={"channel_name": "VA", "unit_mode": "per_unit"}))
    provenance = checked(client.get(root + "/per-unit-resolution", params={"channel_name": "VA"}))
    coverage = checked(client.get(f"{URL}/per-unit/sources/{SOURCE}/coverage"))
    assert waveform["per_unit_status"] == provenance["status"] == status
    assert waveform["unit"] == unit
    assert coverage[scope + "_count"] == int(ready)
    assert coverage["needs_configuration_count"] == int(not ready)
    assert all(v is not None and math.isfinite(v) for v in waveform["values"])
    if ready:
        # Independent SI denominator, deliberately not reciprocal-based.
        denominator = base * 1000 / (math.sqrt(3) if quantity == "Voltage" else 1)
        assert waveform["values"] == pytest.approx([v / denominator for v in values], rel=1e-12, abs=0)
    else:
        assert waveform["values"] == values
        assert "cannot be represented" in provenance["reason"]
    for cursor_b in (None, .25):
        body = {"analog_channel_names": ["VA"], "cursor_a_time": .5, "unit_mode": "per_unit"}
        if cursor_b is not None:
            body["cursor_b_time"] = cursor_b
        cursor = checked(client.post(root + "/cursor-values", json=body))["channels"][0]
        assert cursor["per_unit_status"] == status and cursor["unit"] == unit
    # A viewport containing only real zero must not claim readiness when
    # another sample elsewhere on this channel cannot be represented.
    zoom = checked(client.get(root + "/waveform", params={
        "channel_name": "VA", "start_time": .49, "end_time": .51, "unit_mode": "per_unit",
    }))
    assert zoom["per_unit_status"] == status
    calculated = checked(client.post(f"{URL}/calculated-channels", json={
        "name": "Negative VA", "operation": "reverse_polarity",
        "inputs": [{"kind": "source", "source_id": SOURCE, "channel_name": "VA"}],
    }), 201)
    cid = calculated["id"]
    calculated_waveform = checked(client.get(f"{URL}/calculated-channels/{cid}/waveform", params={"unit_mode": "per_unit"}))
    calculated_provenance = checked(client.get(f"{URL}/calculated-channels/{cid}/per-unit-resolution"))
    assert calculated_waveform["per_unit_status"] == calculated_provenance["status"] == status
    assert calculated_waveform["unit"] == unit
    np.testing.assert_allclose(calculated_waveform["values"], -np.asarray(waveform["values"]), rtol=1e-12, atol=0)
    if quantity == "Voltage":
        for ref in (ChannelRef(kind="source", source_id=SOURCE, channel_name="VA"),
                    ChannelRef(kind="calculated", calculated_channel_id=cid)):
            problem = unit_problem(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
            series, trace_problem = load_series(ref, "pu", workspace_id=WORKSPACE, reg=reg(client))
            assert (problem is None) == ready
            assert trace_problem == problem
            if ready:
                assert np.all(np.isfinite(series.values))
            else:
                assert series is None
    assert source.record.waveform_data.equals(before)


def test_original_input_gaps_are_preserved_without_fabricating_numerical_faults():
    resolution = PerUnitResolution("configured", "profile", 1000., "A", None)
    values = np.asarray([np.nan, np.inf, -np.inf, 0., 1000., -1000.])
    before = values.copy()
    converted, unit, status = apply_per_unit_to_array(values, "A", "Current", resolution)
    assert (unit, status) == ("pu", "configured")
    np.testing.assert_array_equal(converted, [np.nan, np.inf, -np.inf, 0., 1., -1.])
    np.testing.assert_array_equal(values, before)
    assert apply_per_unit_to_value(None, "A", "Current", resolution) == (None, "pu", "configured")
