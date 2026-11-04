"""Stage 5B result-owned Current configuration, independent physical references."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from tests.test_current_effective_base_inheritance import (
    client, checked, ROOT, WS, upload_side, manual, create_chain,
    configuration_snapshot, _ALL_ENDPOINTS,
)


def config_url(cid):
    return f"{ROOT}/calculated-channels/{cid}/per-unit-config"


def put_manual(client, cid, value=4, unit="kA", side="primary", expected=200):
    response = client.put(config_url(cid), json={
        "mode": "manual", "current_base_value": value,
        "current_base_unit": unit, "base_reference_side": side,
    })
    return checked(response, expected)


def setup_result(client, fixtures, marker="P", equal=False):
    sid = upload_side(client, fixtures, marker)
    manual(client, sid, "IBT_HV_IR", 2)
    manual(client, sid, "IBT_HV_IY", 2 if equal else 4)
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "current_base_mode": "direct", "direct_current_base_value": 1,
    }))
    return sid, create_chain(client, sid, 0)


def observations(client, cid, expected):
    physical = checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform"))
    assert physical["values"] == [8398.] * 5
    for endpoint in _ALL_ENDPOINTS:
        status, value, unit = endpoint(client, WS, cid)
        assert (status, unit) == (("base_required", "A") if expected is None else ("configured", "pu"))
        assert value == pytest.approx(8398. if expected is None else expected, rel=1e-12, abs=0)
    p = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert p["status"] == ("base_required" if expected is None else "configured")
    return p


@pytest.mark.parametrize("equal", [False, True])
def test_manual_lifecycle_all_consumers_and_input_integrity(client, comtrade_fixtures_dir, equal):
    sid, cid = setup_result(client, comtrade_fixtures_dir, equal=equal)
    initial = deepcopy(configuration_snapshot(client))
    observations(client, cid, 4.199 if equal else None)
    assert checked(client.get(config_url(cid)))["mode"] == "automatic"
    result = put_manual(client, cid)
    assert result["mode"] == "manual" and result["current_base_amps"] == 4000
    assert result["base_reference_side"] == "primary"
    provenance = observations(client, cid, 2.0995)
    assert provenance["resolution_origin"] == "manual_calculated_current"
    assert provenance["configuration_mode"] == "manual"
    assert provenance["source_kind"] is None and provenance["measurement_group_id"] is None
    assert checked(client.get(config_url(cid))) == result  # Re-open/reload reads authoritative state.
    put_manual(client, cid, 2000, "A")
    observations(client, cid, 4.199)
    checked(client.put(config_url(cid), json={"mode": "unassigned"}))
    p = observations(client, cid, None)
    assert p["configuration_mode"] == "unassigned" and p["resolution_origin"] == "explicit_unassigned"
    # A Source Default recompute cannot reactivate explicit unassignment.
    checked(client.put(f"{ROOT}/per-unit/sources/{sid}", json={
        "current_base_mode": "direct", "direct_current_base_value": 1,
    }))
    observations(client, cid, None)
    checked(client.put(config_url(cid), json={"mode": "automatic"}))
    observations(client, cid, 4.199 if equal else None)
    after = configuration_snapshot(client)
    # Only the target assignment can change; all original authorities/indices stay identical.
    initial.pop("assignments"); after.pop("assignments")
    assert initial == after


@pytest.mark.parametrize("body", [
    {"current_base_value": 0}, {"current_base_value": -1}, {"current_base_value": True},
    {"current_base_value": False}, {"current_base_value": "NaN"}, {"current_base_value": "Infinity"},
    {"current_base_value": 1e308}, {"current_base_value": 5e-324, "current_base_unit": "A"},
    {"current_base_unit": "V"}, {"base_reference_side": "secondary"},
    {"current_base_value": None},
    {"base_reference_side": "unknown"}, {"base_reference_side": None},
    {"mode": "wrong"}, {"mode": "automatic"}, {"mode": "unassigned"},
])
@pytest.mark.parametrize("previous_manual", [False, True])
def test_rejected_candidates_preserve_complete_state_and_values(client, comtrade_fixtures_dir, body, previous_manual):
    _, cid = setup_result(client, comtrade_fixtures_dir)
    if previous_manual: put_manual(client, cid)
    before = configuration_snapshot(client)
    config = checked(client.get(config_url(cid)))
    waveform = checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform?unit_mode=per_unit"))
    request = dict(mode="manual", current_base_value=4, current_base_unit="kA", base_reference_side="primary")
    request.update(body)
    assert client.put(config_url(cid), json=request).status_code in (400, 422)
    assert configuration_snapshot(client) == before
    assert checked(client.get(config_url(cid))) == config
    assert checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform?unit_mode=per_unit")) == waveform


@pytest.mark.parametrize("marker", ["S", "C", ""])
def test_manual_cannot_declare_unknown_or_secondary_samples_primary(client, comtrade_fixtures_dir, marker):
    _, cid = setup_result(client, comtrade_fixtures_dir, marker)
    before = configuration_snapshot(client)
    assert client.put(config_url(cid), json=dict(mode="manual", current_base_value=4,
        current_base_unit="kA", base_reference_side="primary")).status_code == 400
    assert configuration_snapshot(client) == before


@pytest.mark.parametrize("equal", [False, True])
def test_automatic_child_does_not_inherit_parent_manual_or_unassignment(client, comtrade_fixtures_dir, equal):
    _, parent = setup_result(client, comtrade_fixtures_dir, equal=equal)
    child = checked(client.post(ROOT + "/calculated-channels", json={
        "name": "Child", "operation": "absolute_value",
        "inputs": [{"kind": "calculated", "calculated_channel_id": parent}],
    }), 201)["id"]
    put_manual(client, parent)
    observations(client, parent, 2.0995)
    observations(client, child, 4.199 if equal else None)
    put_manual(client, child, 2)
    observations(client, child, 4.199)
    checked(client.put(config_url(parent), json={"mode": "unassigned"}))
    observations(client, parent, None)
    observations(client, child, 4.199)
    checked(client.put(config_url(child), json={"mode": "automatic"}))
    observations(client, child, 4.199 if equal else None)


def test_input_base_absence_does_not_block_physically_valid_manual_result(client, comtrade_fixtures_dir):
    sid, cid = setup_result(client, comtrade_fixtures_dir)
    groups = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))
    for group in groups:
        checked(client.put(f"{ROOT}/sources/{sid}/measurement-groups/{group['id']}/current-config", json={"method": "none"}))
    before = configuration_snapshot(client)
    put_manual(client, cid)
    observations(client, cid, 2.0995)
    after = configuration_snapshot(client)
    assert all(before[k] == after[k] for k in before if k != "assignments")


@pytest.mark.parametrize("change", ["review", "side", "unit", "numerical"])
def test_live_inapplicability_retains_manual_choice_without_automatic_fallback(client, comtrade_fixtures_dir, change):
    sid, cid = setup_result(client, comtrade_fixtures_dir, equal=True)
    accepted = put_manual(client, cid, 1e-300, "A") if change == "numerical" else put_manual(client, cid)
    state = client.app.state
    if change == "review":
        group = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))[0]
        checked(client.patch(f"{ROOT}/sources/{sid}/measurement-groups/{group['id']}", json={"status": "needs_review"}))
    elif change in ("side", "unit"):
        metadata = next(c for c in state.workspace_registry.get(WS, sid).metadata.analog_channels if c.name == "IBT_HV_IR")
        if change == "side": metadata.measurement_side = "unknown"
        else: metadata.unit = "V"
    else:
        state.calculated_channel_registry.get(WS, cid).values[:] = 1e308
    p = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert p["status"] == "base_required" and p["configuration_mode"] == "manual"
    assert p["resolution_origin"] == "manual_calculated_current" and p["reason"]
    assert checked(client.get(config_url(cid))) == accepted
    wave = checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform?unit_mode=per_unit"))
    assert (wave["unit"], wave["per_unit_status"]) == ("A", "base_required")
    assert wave["values"] == ([1e308] * 5 if change == "numerical" else [8398.] * 5)


@pytest.mark.parametrize("mode", ["manual", "unassigned"])
def test_recompute_started_before_explicit_selection_cannot_overwrite_it(client, comtrade_fixtures_dir, mode):
    sid, cid = setup_result(client, comtrade_fixtures_dir)
    if mode == "manual": put_manual(client, cid)
    else: checked(client.put(config_url(cid), json={"mode": mode}))
    before = configuration_snapshot(client)
    # Force the publication part of a legacy recompute that already read auto mode.
    client.app.state.per_unit_registry.set_auto_assignment_for_calculated_channel(WS, cid, sid)
    assert configuration_snapshot(client) == before
    observations(client, cid, 2.0995 if mode == "manual" else None)


def test_publication_failure_preserves_previous_config_and_all_outputs(client, comtrade_fixtures_dir, monkeypatch):
    _, cid = setup_result(client, comtrade_fixtures_dir)
    put_manual(client, cid)
    registry = client.app.state.per_unit_registry
    before = configuration_snapshot(client)
    class RejectPublication(dict):
        def __setitem__(self, key, value):
            raise RuntimeError("injected assignment publication fault")
    monkeypatch.setattr(registry, "_calc_assignments", RejectPublication(registry._calc_assignments))
    with pytest.raises(RuntimeError, match="publication fault"):
        put_manual(client, cid, 2)
    assert configuration_snapshot(client) == before
    observations(client, cid, 2.0995)


def test_delete_during_validation_cannot_resurrect_configuration(client, comtrade_fixtures_dir, monkeypatch):
    _, cid = setup_result(client, comtrade_fixtures_dir)
    registry = client.app.state.per_unit_registry
    publish = registry.set_current_configuration_for_calculated_channel
    def deletion_before_publication(workspace_id, calculated_channel_id, config):
        client.app.state.calculated_channel_registry.remove(workspace_id, calculated_channel_id)
        registry.remove_calculated_channel(workspace_id, calculated_channel_id)
        publish(workspace_id, calculated_channel_id, config)
    monkeypatch.setattr(registry, "set_current_configuration_for_calculated_channel", deletion_before_publication)
    put_manual(client, cid, expected=404)
    assert (WS, cid) not in registry._calc_assignments
    assert client.get(config_url(cid)).status_code == 404


@pytest.mark.parametrize("cleanup", ["calculated", "source", "workspace"])
def test_configuration_lifetime_cleanup(client, comtrade_fixtures_dir, cleanup):
    sid, cid = setup_result(client, comtrade_fixtures_dir)
    put_manual(client, cid)
    path = f"{ROOT}/calculated-channels/{cid}" if cleanup == "calculated" else f"{ROOT}/sources/{sid}" if cleanup == "source" else ROOT
    assert client.delete(path).status_code == 204
    assert (WS, cid) not in client.app.state.per_unit_registry._calc_assignments
    assert client.get(config_url(cid)).status_code == 404


@pytest.mark.parametrize("same_authority", [False, True])
def test_secondary_requires_established_single_authority(client, comtrade_fixtures_dir, same_authority):
    sid = upload_side(client, comtrade_fixtures_dir, "S")
    if same_authority:
        from tests.test_calculated_group_aware_per_unit_endpoints import _current_group_manual
        _current_group_manual(client, WS, sid, ["IBT_HV_IR", "IBT_HV_IY"], 2, "Shared secondary context")
    else:
        manual(client, sid, "IBT_HV_IR"); manual(client, sid, "IBT_HV_IY")
    cid = create_chain(client, sid, 0)
    put_manual(client, cid, side="secondary", expected=200 if same_authority else 400)
    if same_authority: observations(client, cid, 2.0995)


def test_target_ownership_and_voltage_policy_are_not_extended(client, comtrade_fixtures_dir):
    sid, cid = setup_result(client, comtrade_fixtures_dir)
    before = configuration_snapshot(client)
    assert client.get(config_url(cid).replace(WS, "another-workspace")).status_code == 404
    assert client.put(config_url("calc-missing"), json={"mode": "unassigned"}).status_code == 404
    voltage = checked(client.post(ROOT + "/calculated-channels", json={
        "name": "Voltage", "operation": "absolute_value",
        "inputs": [{"kind": "source", "source_id": sid, "channel_name": "N275_VR"}],
    }), 201)["id"]
    target_assignment = deepcopy(client.app.state.per_unit_registry._calc_assignments[(WS, voltage)])
    assert client.get(config_url(voltage)).status_code == 400
    assert client.put(config_url(voltage), json={"mode": "unassigned"}).status_code == 400
    assert client.app.state.per_unit_registry._calc_assignments[(WS, voltage)] == target_assignment
    after = configuration_snapshot(client)
    assert all(before[k] == after[k] for k in before if k != "assignments")


@pytest.mark.parametrize("value,unit,amps", [(4000, "A", 4000), (4, "kA", 4000),
    (1e308, "A", 1e308), (1e-300, "A", 1e-300)])
def test_canonical_si_units_and_valid_extreme_values(client, comtrade_fixtures_dir, value, unit, amps):
    _, cid = setup_result(client, comtrade_fixtures_dir)
    result = put_manual(client, cid, value, unit)
    assert result["current_base_amps"] == amps
    observations(client, cid, 8398 / amps)


@pytest.mark.parametrize("amps", [5e-324, 1e-320, 1e-310])
def test_subnormal_manual_base_provenance_never_fabricates_zero_or_loses_si_reference(client, comtrade_fixtures_dir, amps):
    sid = upload_side(client, comtrade_fixtures_dir)
    record = client.app.state.workspace_registry.get(WS, sid).record
    record.waveform_data["IBT_HV_IR"] = 0.
    record.waveform_data["IBT_HV_IY"] = 0.
    cid = create_chain(client, sid, 0)
    assert put_manual(client, cid, amps, "A")["current_base_amps"] == amps
    p = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert p["status"] == "configured" and p["effective_base_amount"] == amps
    assert p["effective_base_unit"] == "A"
    for endpoint in _ALL_ENDPOINTS:
        assert endpoint(client, WS, cid) == ("configured", 0., "pu")


def test_linked_input_bases_are_independent_of_result_override(client, comtrade_fixtures_dir):
    from tests.test_calculated_group_aware_per_unit_endpoints import _voltage_group
    sid, cid = setup_result(client, comtrade_fixtures_dir)
    voltage = _voltage_group(client, WS, sid, ["N275_VR"], 275, "Linked Voltage")
    groups = checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups"))
    current = next(g for g in groups if g["kind"] == "current")
    checked(client.put(f"{ROOT}/sources/{sid}/measurement-groups/{current['id']}/current-config", json={
        "method": "equipment_rating", "equipment_rating_mva": 1000, "linked_voltage_group_id": voltage.id,
    }))
    before = configuration_snapshot(client)
    put_manual(client, cid)
    observations(client, cid, 2.0995)
    after = configuration_snapshot(client)
    assert all(before[k] == after[k] for k in before if k != "assignments")
    url = f"{ROOT}/sources/{sid}/measurement-groups/{voltage.id}/voltage-config"
    checked(client.put(url, json={"nominal_voltage_ll_kv": 132}))
    changed = next(g for g in checked(client.get(f"{ROOT}/sources/{sid}/measurement-groups")) if g["id"] == current["id"])
    assert changed["current_config"]["resolved_ibase_ka"] == pytest.approx(1000 / (3**.5 * 132), rel=1e-12)
    observations(client, cid, 2.0995)
    accepted = configuration_snapshot(client)
    assert client.put(url, json={"nominal_voltage_ll_kv": 66, "reference_mode": "manual"}).status_code == 400
    assert configuration_snapshot(client) == accepted
    observations(client, cid, 2.0995)
