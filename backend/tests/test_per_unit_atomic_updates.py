"""PU-001/002: rejected requests preserve authoritative state and live PU values."""

from dataclasses import asdict
import math

import pytest

from app.domain.calculated_channel import ChannelRef
from tests.test_measurement_group_api import (
    client,  # noqa: F401 -- use the real application fixture
    _base_url,
    _create_current_group,
    _create_voltage_group,
    _refs,
    _upload,
)

WS = "atomic-pu"


@pytest.fixture
def configured(client, comtrade_fixtures_dir):
    source = _upload(client, WS, comtrade_fixtures_dir)
    voltage = _create_voltage_group(client, WS, source, ["N275_VR", "N275_VY", "N275_VB"])
    current = _create_current_group(client, WS, source, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"])
    url = f"{_base_url(WS, source)}/{voltage['id']}"
    assert client.put(url + "/voltage-config", json={"nominal_voltage_ll_kv": 275}).status_code == 200
    assert client.put(f"{_base_url(WS, source)}/{current['id']}/current-config", json={
        "method": "equipment_rating", "equipment_rating_mva": 1000,
        "linked_voltage_group_id": voltage["id"],
    }).status_code == 200
    return source, voltage["id"], current["id"], url


def _waveform(client, source, name, mode="per_unit"):
    response = client.get(f"/api/v1/workspaces/{WS}/sources/{source}/waveform", params={
        "channel_name": name, "unit_mode": mode,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _snapshot(client, source):
    """Compare every group/config, every reverse entry, and fresh HTTP results.

    Registry snapshots distinguish an absent config from an empty default view.
    Engineering arrays also prove that no physical waveform was rewritten.
    """
    state = client.app.state
    active = state.workspace_registry.get(WS, source)
    names = [ch.name for ch in active.metadata.analog_channels]
    return {
        "groups": [asdict(g) for g in state.measurement_group_registry.list_for_workspace(WS)],
        "voltage_configs": [asdict(c) for c in state.voltage_group_config_registry.list_for_workspace(WS)],
        "current_configs": [asdict(c) for c in state.current_group_config_registry.list_for_workspace(WS)],
        "source_defaults": [asdict(c) for c in state.per_unit_registry.list_for_workspace(WS)],
        "reverse_index": dict(state.measurement_group_registry._channel_index),
        "views": client.get(_base_url(WS, source)).json(),
        "waveforms": {(name, mode): _waveform(client, source, name, mode)
                      for name in names for mode in ("per_unit", "engineering")},
    }


VOLTAGE_REJECTIONS = [
    pytest.param({"nominal_voltage_ll_kv": 132, "reference_mode": "manual"}, 400, id="missing-reference"),
    pytest.param({"nominal_voltage_ll_kv": 132, "reference_mode": "manual", "reference_override": "invalid"},
                 422, id="invalid-reference"),
    pytest.param({"nominal_voltage_ll_kv": -1, "reference_mode": "manual", "reference_override": "line_to_line"},
                 400, id="invalid-nominal"),
    pytest.param({"nominal_voltage_ll_kv": 0, "reference_mode": "manual"}, 400, id="multiple-invalid-fields"),
    pytest.param({"nominal_voltage_ll_kv": 132, "reference_mode": "invalid"}, 422, id="invalid-mode"),
]


@pytest.mark.parametrize("initial", [False, True], ids=["existing", "initial"])
@pytest.mark.parametrize("body,status", VOLTAGE_REJECTIONS)
def test_voltage_rejection_preserves_complete_state(client, configured, body, status, initial):
    source, voltage_id, _, url = configured
    if initial:
        client.app.state.voltage_group_config_registry.delete(WS, voltage_id)
    before = _snapshot(client, source)
    response = client.put(url + "/voltage-config", json=body)
    assert response.status_code == status, response.text
    assert _snapshot(client, source) == before


@pytest.mark.parametrize("body,nominal,mode,override", [
    ({"nominal_voltage_ll_kv": 132}, 132, "auto", None),
    ({"nominal_voltage_ll_kv": 132, "reference_mode": "manual", "reference_override": "line_to_line"},
     132, "manual", "line_to_line"),
    ({"reference_mode": "manual", "reference_override": "line_to_ground"}, 275, "manual", "line_to_ground"),
    ({}, 275, "auto", None),
    ({"nominal_voltage_ll_kv": None}, 275, "auto", None),
    ({"reference_mode": "auto", "reference_override": "line_to_line"}, 275, "auto", None),
])
def test_voltage_valid_save_and_omitted_fields(client, configured, body, nominal, mode, override):
    source, voltage_id, current_id, url = configured
    # Starting in manual L-L makes default/omitted mode's return-to-auto observable.
    assert client.put(url + "/voltage-config", json={
        "reference_mode": "manual", "reference_override": "line_to_line",
    }).status_code == 200
    current_before = client.app.state.current_group_config_registry.get(WS, current_id)
    physical_before = _waveform(client, source, "N275_VR", "engineering")
    response = client.put(url + "/voltage-config", json=body)
    assert response.status_code == 200, response.text
    config = response.json()["voltage_config"]
    assert (config["nominal_voltage_ll_kv"], config["reference_mode"], config["reference_override"]) == (
        nominal, mode, override,
    )
    denominator_kv = nominal if override == "line_to_line" else nominal / math.sqrt(3)
    assert _waveform(client, source, "N275_VR")["values"] == pytest.approx([158.77 / denominator_kv] * 5)
    expected_ibase_a = 1000 * 1e6 / (math.sqrt(3) * nominal * 1000)
    assert _waveform(client, source, "IBT_HV_IR")["values"] == pytest.approx([4199 / expected_ibase_a] * 5)
    linked = client.get(f"{_base_url(WS, source)}/{current_id}").json()["current_config"]
    assert linked["resolved_ibase_ka"] == pytest.approx(expected_ibase_a / 1000)
    assert linked["applicable_voltage_ll_kv"] == nominal
    assert linked["linked_voltage_group_id"] == voltage_id
    assert client.app.state.current_group_config_registry.get(WS, current_id) == current_before
    assert _waveform(client, source, "N275_VR", "engineering") == physical_before


@pytest.mark.parametrize("case,status", [
    ("nonexistent", 404), ("wrong-source", 400), ("wrong-quantity", 400),
    ("duplicate", 400), ("assigned", 409), ("calculated", 400), ("invalid-metadata", 422),
])
@pytest.mark.parametrize("kind", ["voltage", "current"])
def test_membership_rejection_preserves_review_gate_and_complete_state(
    client, configured, comtrade_fixtures_dir, case, status, kind,
):
    source, voltage_id, current_id, _ = configured
    target_id = voltage_id if kind == "voltage" else current_id
    url = f"{_base_url(WS, source)}/{target_id}"
    assert client.patch(url, json={"status": "needs_review"}).status_code == 200
    available = "S132_VR" if kind == "voltage" else "LINEA_IR"
    refs = _refs(source, available)
    body = {"display_name": "Must not be saved", "status": "confirmed", "channel_refs": refs}
    if case == "nonexistent":
        body["channel_refs"] = _refs(source, "DOES_NOT_EXIST")
    elif case == "wrong-source":
        other_source = _upload(client, WS, comtrade_fixtures_dir)
        body["channel_refs"] = _refs(other_source, available)
    elif case == "wrong-quantity":
        body["channel_refs"] = _refs(source, "FREQ")
    elif case == "duplicate":
        body["channel_refs"] = refs + refs
    elif case == "assigned":
        create = _create_voltage_group if kind == "voltage" else _create_current_group
        create(client, WS, source, [available], "Other owner")
    elif case == "calculated":
        body["channel_refs"] = [{"kind": "calculated", "calculated_channel_id": "calc-not-a-member"}]
    else:
        body["status"] = "invalid"
    before = _snapshot(client, source)
    response = client.patch(url, json=body)
    assert response.status_code == status, response.text
    assert _snapshot(client, source) == before
    assert client.get(url).json()["status"] == "needs_review"


@pytest.mark.parametrize("fields", ["metadata", "membership", "combined", "empty", "null"])
def test_valid_group_updates_preserve_identity_bases_and_reverse_indices(client, configured, fields):
    source, voltage_id, _, url = configured
    original = client.get(url).json()
    configs_before = client.app.state.voltage_group_config_registry.get(WS, voltage_id)
    body = {}
    if fields in ("metadata", "combined"):
        body.update(display_name="Accepted", status="confirmed")
    if fields in ("membership", "combined"):
        body["channel_refs"] = _refs(source, "S132_VR")
    if fields == "null":
        body = {"display_name": None, "status": None, "channel_refs": None}
    response = client.patch(url, json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    for field in ("id", "workspace_id", "source_id", "kind", "created_at"):
        assert saved[field] == original[field]
    assert saved["display_name"] == ("Accepted" if fields in ("metadata", "combined") else original["display_name"])
    assert saved["status"] == ("confirmed" if fields in ("metadata", "combined") else original["status"])
    registry = client.app.state.measurement_group_registry
    replaced = fields in ("membership", "combined")
    assert registry.group_for_channel(WS, ChannelRef(kind="source", source_id=source, channel_name="N275_VR")) == (
        None if replaced else voltage_id
    )
    assert registry.group_for_channel(WS, ChannelRef(kind="source", source_id=source, channel_name="S132_VR")) == (
        voltage_id if replaced else None
    )
    assert client.app.state.voltage_group_config_registry.get(WS, voltage_id) == configs_before


def test_group_publication_copy_failure_preserves_indices(client, configured, monkeypatch):
    """Fail after validation, where the old update had already de-indexed members."""
    from app.services import measurement_group_registry as module

    source, _, _, url = configured
    before = _snapshot(client, source)
    original_copy = module._copy_group

    def fail_for_candidate(group):
        if group.display_name == "Publication fails":
            raise RuntimeError("injected copy failure")
        return original_copy(group)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_copy_group", fail_for_candidate)
        with pytest.raises(RuntimeError, match="injected copy failure"):
            client.patch(url, json={"display_name": "Publication fails", "channel_refs": _refs(source, "S132_VR")})
    assert _snapshot(client, source) == before
