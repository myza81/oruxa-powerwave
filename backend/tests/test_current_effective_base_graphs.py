"""PC-001 live dependencies, global tolerance, units and numerical safety."""
import math

import pytest

from app.domain.calculated_channel import ChannelRef
from app.services.calculated_current_per_unit import resolve_calculated_current_per_unit
from tests.test_current_effective_base_inheritance import (
    client, checked, WS, ROOT, upload_side, manual, create_chain, configuration_snapshot, _ALL_ENDPOINTS,
)


def output(client, cid, expected=None):
    before = configuration_snapshot(client)
    for via in _ALL_ENDPOINTS:
        status, value, unit = via(client, WS, cid)
        assert status == ("base_required" if expected is None else "configured")
        if expected is not None:
            assert unit == "pu" and value == pytest.approx(expected, rel=1e-12, abs=0)
        else:
            assert unit == "A"
    assert configuration_snapshot(client) == before


def default(client, source, base, side="primary"):
    return checked(client.put(f"{ROOT}/per-unit/sources/{source}", json={
        "current_base_mode": "direct", "direct_current_base_value": base, "current_base_reference_side": side,
    }))


def calc(client, name, refs):
    return checked(client.post(ROOT + "/calculated-channels", json={
        "name": name, "operation": "addition", "inputs": refs,
    }), 201)["id"]


@pytest.mark.parametrize("second,eligible", [
    (math.nextafter(2., math.inf), True), (2 * (1 + 0.9e-12), True),
    (2 * (1 + 1.1e-12), False), (2.000001, False),
])
def test_strict_relative_tolerance(client, comtrade_fixtures_dir, second, eligible):
    source = upload_side(client, comtrade_fixtures_dir)
    manual(client, source, "IBT_HV_IR", 2)
    manual(client, source, "IBT_HV_IY", second)
    cid = create_chain(client, source, 2)
    output(client, cid, 8398 / 2000 if eligible else None)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("repeated", [False, True])
def test_deterministic_order_and_repeated_contributors(client, comtrade_fixtures_dir, reverse, repeated):
    source = upload_side(client, comtrade_fixtures_dir)
    manual(client, source, "IBT_HV_IR", math.nextafter(2., math.inf))
    manual(client, source, "IBT_HV_IY", 2)
    refs = [{"kind": "source", "source_id": source, "channel_name": n} for n in ("IBT_HV_IR", "IBT_HV_IY")]
    if repeated:
        refs.append(refs[0])
    if reverse:
        refs.reverse()
    cid = calc(client, "Repeated sum", refs)
    output(client, cid, 4199 * len(refs) / 2000)
    provenance = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert provenance["effective_base_amount"] == 2


def test_nested_multi_input_compares_global_extrema(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    names = ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"]
    for name, factor in zip(names, [1, 1 + 0.75e-12, 1 + 1.5e-12]):
        manual(client, source, name, factor)
    refs = [{"kind": "source", "source_id": source, "channel_name": name} for name in names]
    pair = calc(client, "Close pair", refs[1:])
    output(client, pair, 8398 / (1000 * (1 + 0.75e-12)))
    nested = calc(client, "Global extrema", [refs[0], {"kind": "calculated", "calculated_channel_id": pair}])
    output(client, nested)


@pytest.mark.parametrize("scope", ["mixed", "different_sources", "different_sources_mixed"])
def test_group_default_and_cross_source_agreement(client, comtrade_fixtures_dir, scope):
    a = upload_side(client, comtrade_fixtures_dir)
    b = a if scope == "mixed" else upload_side(client, comtrade_fixtures_dir)
    default(client, a, 2)
    default(client, b, 2)
    if scope != "different_sources":
        manual(client, a, "IBT_HV_IR", 2)
    refs = [{"kind": "source", "source_id": sid, "channel_name": name}
            for sid, name in [(a, "IBT_HV_IR"), (b, "IBT_HV_IY")]]
    cid = calc(client, "Cross authority", refs)
    output(client, cid, 8398 / 2000)
    default(client, b, 4)
    output(client, cid)


def test_live_side_base_review_and_group_deletion(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    first, first_url = manual(client, source, "IBT_HV_IR")
    second, second_url = manual(client, source, "IBT_HV_IY")
    default(client, source, 1)
    cid = create_chain(client, source, 2)
    engineering = checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform"))
    for side, base, eligible in [("primary", 2, True), ("unknown", 2, False),
                                  ("primary", 4, False), ("secondary", 2, False), ("primary", 2, True)]:
        checked(client.put(second_url, json={"method": "manual", "manual_ibase_ka": base, "base_reference_side": side}))
        output(client, cid, 8398 / 2000 if eligible else None)
        assert checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform")) == engineering
    group_url = second_url.removesuffix("/current-config")
    checked(client.patch(group_url, json={"status": "needs_review"}))
    output(client, cid)
    checked(client.patch(group_url, json={"status": "confirmed"}))
    output(client, cid, 8398 / 2000)
    assert client.delete(group_url).status_code == 204
    output(client, cid)  # Remaining group=2 kA and genuinely ungrouped default=1 kA.
    assert client.delete(first_url.removesuffix("/current-config")).status_code == 204
    output(client, cid, 8398 / 1000)  # Both now genuinely ungrouped, one shared default.


def test_linked_voltage_changes_recompute_common_current_base(client, comtrade_fixtures_dir):
    from tests.test_calculated_group_aware_per_unit_endpoints import _voltage_group
    source = upload_side(client, comtrade_fixtures_dir)
    voltage = _voltage_group(client, WS, source, ["N275_VR", "N275_VY", "N275_VB"], 275, "Voltage")
    manual(client, source, "IBT_HV_IR", 2)
    _, url = manual(client, source, "IBT_HV_IY", 2)
    checked(client.put(url, json={"method": "equipment_rating", "equipment_rating_mva": 2 * math.sqrt(3) * 275,
                                  "linked_voltage_group_id": voltage.id}))
    cid = create_chain(client, source, 2)
    output(client, cid, 8398 / 2000)
    voltage_url = f"{ROOT}/sources/{source}/measurement-groups/{voltage.id}/voltage-config"
    before = configuration_snapshot(client)
    assert client.put(voltage_url, json={"nominal_voltage_ll_kv": 550, "reference_mode": "manual"}).status_code == 400
    assert configuration_snapshot(client) == before
    output(client, cid, 8398 / 2000)
    checked(client.put(voltage_url, json={"nominal_voltage_ll_kv": 550}))
    output(client, cid)


@pytest.mark.parametrize("fault", ["missing", "cycle", "unit", "source_deleted"])
def test_missing_dependency_and_measured_units_fail_closed(client, comtrade_fixtures_dir, fault):
    source = upload_side(client, comtrade_fixtures_dir)
    manual(client, source, "IBT_HV_IR")
    manual(client, source, "IBT_HV_IY")
    cid = create_chain(client, source, 0)
    state = client.app.state
    channel = state.calculated_channel_registry.get(WS, cid)
    if fault in ("missing", "cycle"):
        channel.inputs[0] = ChannelRef(kind="calculated", calculated_channel_id="missing" if fault == "missing" else cid)
    elif fault == "unit":
        next(ch for ch in state.workspace_registry.get(WS, source).metadata.analog_channels if ch.name == "IBT_HV_IR").unit = ""
    else:
        assert client.delete(f"{ROOT}/sources/{source}").status_code == 204
    resolution = resolve_calculated_current_per_unit(workspace_id=WS, channel=channel,
        source_registry=state.workspace_registry, per_unit_registry=state.per_unit_registry,
        calc_registry=state.calculated_channel_registry, group_registry=state.measurement_group_registry,
        voltage_config_registry=state.voltage_group_config_registry, current_config_registry=state.current_group_config_registry)
    assert resolution.resolution.status == "base_required"


def test_subnormal_base_result_safety_and_legacy_manual_pointer(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    _, url = manual(client, source, "IBT_HV_IR", 5e-324)
    manual(client, source, "IBT_HV_IY", 5e-324)
    cid = create_chain(client, source, 0)
    output(client, cid)  # Finite nonzero measurements cannot normalize to this base.
    default(client, source, 1)
    checked(client.put(url, json={"method": "manual", "manual_ibase_ka": 2, "base_reference_side": "primary"}))
    state = client.app.state
    state.per_unit_registry.set_manual_assignment_for_calculated_channel(WS, cid, source)
    # Existing internal manual pointer behavior stays on its legacy path in 5A.
    output(client, cid, 8398 / 1000)


@pytest.mark.parametrize("base,value", [(1e-310, 5e-310), (5e-324, 5e-324)])
def test_representable_subnormal_common_base(client, comtrade_fixtures_dir, base, value):
    source = upload_side(client, comtrade_fixtures_dir)
    for name in ("IBT_HV_IR", "IBT_HV_IY"):
        manual(client, source, name, base)
        client.app.state.workspace_registry.get(WS, source).record.waveform_data[name] = value
    cid = create_chain(client, source, 0)
    output(client, cid, (value + value) / (base * 1000))
    assert checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform"))["values"] == [value + value] * 5


def test_physical_cancellation_does_not_normalize_inputs_first(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    record = client.app.state.workspace_registry.get(WS, source).record
    for name, value in [("IBT_HV_IR", 1e308), ("IBT_HV_IY", -1e308)]:
        manual(client, source, name, 1e-300)
        record.waveform_data[name] = value
    cid = create_chain(client, source, 0)
    output(client, cid, 0.)
