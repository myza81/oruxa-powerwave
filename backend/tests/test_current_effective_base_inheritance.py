"""PC-001: grouped Current bases cannot be overridden by ambient defaults.

These initial cases do not rely on choosing a primary/secondary contract:
different or missing bases are incompatible regardless of that distinction.
Engineering arithmetic always adds the recorded A values before normalization.
"""

from dataclasses import asdict
import io

import pytest

from tests.test_calculated_group_aware_per_unit_endpoints import (
    client, _upload, _current_group_manual, _current_group_none, _create_channel,
    _ALL_ENDPOINTS,
)

WS = "current-effective-base"
ROOT = f"/api/v1/workspaces/{WS}"


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def create_chain(client, source, depth):
    cid = _create_channel(client, WS, "Physical sum", "addition", [
        (source, "IBT_HV_IR"), (source, "IBT_HV_IY"),
    ])
    for operation in ["reverse_polarity", "absolute_value"][:depth]:
        cid = checked(client.post(ROOT + "/calculated-channels", json={
            "name": operation, "operation": operation,
            "inputs": [{"kind": "calculated", "calculated_channel_id": cid}],
        }), 201)["id"]
    return cid


def configuration_snapshot(client):
    state = client.app.state
    return {
        "groups": [asdict(g) for g in state.measurement_group_registry.list_for_workspace(WS)],
        "voltage": [asdict(c) for c in state.voltage_group_config_registry.list_for_workspace(WS)],
        "current": [asdict(c) for c in state.current_group_config_registry.list_for_workspace(WS)],
        "defaults": [asdict(c) for c in state.per_unit_registry.list_for_workspace(WS)],
        "reverse": dict(state.measurement_group_registry._channel_index),
        "assignments": {k: asdict(v) for k, v in state.per_unit_registry._calc_assignments.items()},
    }


@pytest.mark.parametrize("via", _ALL_ENDPOINTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("depth", [0, 1, 2])
@pytest.mark.parametrize("groups", ["different", "missing", "ungrouped", "same"])
def test_current_group_policy_and_transitive_engineering_invariance(
    client, comtrade_fixtures_dir, via, depth, groups,
):
    source = _upload(client, WS, comtrade_fixtures_dir)
    checked(client.put(f"{ROOT}/per-unit/sources/{source}", json={
        "current_base_mode": "direct", "direct_current_base_value": 1,
    }))
    if groups == "same":
        _current_group_manual(client, WS, source, ["IBT_HV_IR", "IBT_HV_IY"], 2, "Same authority")
    elif groups != "ungrouped":
        _current_group_manual(client, WS, source, ["IBT_HV_IR"], 2, "First")
        if groups == "different":
            _current_group_manual(client, WS, source, ["IBT_HV_IY"], 4, "Second")
        else:
            _current_group_none(client, WS, source, ["IBT_HV_IY"], "Unresolved")
    cid = create_chain(client, source, depth)
    physical = -8398. if depth == 1 else 8398.
    engineering = checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform"))
    assert engineering["unit"] == "A"
    assert engineering["per_unit_status"] is None
    assert engineering["values"] == [physical] * 5
    before = configuration_snapshot(client)
    status, value, unit = via(client, WS, cid)
    provenance = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert configuration_snapshot(client) == before
    assert checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform")) == engineering
    if groups in ("different", "missing"):
        assert status == provenance["status"] == "base_required"
        assert unit == "A" and value == physical
        assert provenance["source_kind"] != "source_default"
        assert provenance["effective_base_amount"] is None
    else:
        assert status == provenance["status"] == "configured"
        assert unit == "pu"
        assert value == pytest.approx(physical / (2000 if groups == "same" else 1000), rel=1e-12)
        assert provenance["effective_base_amount"] == (2 if groups == "same" else 1)


def upload_side(client, fixtures, marker="P"):
    # Set the actual COMTRADE marker, not names/ratios or post-import metadata.
    lines = (fixtures / "synth_measurement_groups.cfg").read_text().splitlines()
    for i in range(2, 2 + int(lines[1].split(",")[1][:-1])):
        fields = lines[i].split(",")
        fields[-1] = marker
        lines[i] = ",".join(fields)
    response = checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("side.cfg", io.BytesIO("\n".join(lines).encode()), "application/octet-stream"),
        "dat_file": ("side.dat", io.BytesIO((fixtures / "synth_measurement_groups.dat").read_bytes()), "application/octet-stream"),
    }), 201)
    source = response["source_id"]
    url = f"{ROOT}/sources/{source}/measurement-groups"
    for group in checked(client.get(url)):
        assert client.delete(f"{url}/{group['id']}").status_code == 204
    return source


def manual(client, source, name, base=2, side="primary"):
    group = _current_group_manual(client, WS, source, [name], base, name)
    url = f"{ROOT}/sources/{source}/measurement-groups/{group.id}/current-config"
    checked(client.put(url, json={"method": "manual", "manual_ibase_ka": base, "base_reference_side": side}))
    return group, url


@pytest.mark.parametrize("via", _ALL_ENDPOINTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("depth", [0, 1, 2])
@pytest.mark.parametrize("marker,side,eligible", [
    ("P", "primary", True), ("P", "secondary", False),
    ("S", "primary", False), ("S", "secondary", False),
    ("P", "unknown", False), ("", "primary", False), ("C", "primary", False),
])
def test_cross_group_reference_matrix(client, comtrade_fixtures_dir, via, depth, marker, side, eligible):
    source = upload_side(client, comtrade_fixtures_dir, marker)
    checked(client.put(f"{ROOT}/per-unit/sources/{source}", json={
        "current_base_mode": "direct", "direct_current_base_value": 1,
    }))
    manual(client, source, "IBT_HV_IR", side=side)
    manual(client, source, "IBT_HV_IY", side=side)
    cid = create_chain(client, source, depth)
    before = configuration_snapshot(client)
    physical = -8398. if depth == 1 else 8398.
    status, value, unit = via(client, WS, cid)
    provenance = checked(client.get(f"{ROOT}/calculated-channels/{cid}/per-unit-resolution"))
    assert configuration_snapshot(client) == before
    assert checked(client.get(f"{ROOT}/calculated-channels/{cid}/waveform"))["values"] == [physical] * 5
    assert status == provenance["status"] == ("configured" if eligible else "base_required")
    assert unit == ("pu" if eligible else "A")
    assert value == pytest.approx(physical / 2000 if eligible else physical, rel=1e-12)
    assert provenance["source_kind"] is None
    assert provenance["measurement_group_id"] is None
    assert provenance["resolution_origin"] == "automatic_common_base"
    if eligible:
        assert provenance["effective_base_amount"] == 2
        assert provenance["measurement_side"] == provenance["base_reference_side"] == "primary"
