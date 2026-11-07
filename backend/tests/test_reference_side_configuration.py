"""Stage 5A provider provenance, backward compatibility and atomic side saves."""
import io

import pytest

from app.domain.reference_side import comtrade_measurement_side
from tests.test_current_effective_base_inheritance import (
    client, checked, WS, ROOT, upload_side, manual, create_chain, configuration_snapshot,
)
from tests.test_measured_unit_per_unit import _prepared_current_source, WS as CSV_WS
from tests.test_ben_import_api import _fast_bytes


@pytest.mark.parametrize("marker,expected", [
    ("P", "primary"), ("p", "primary"), ("S", "secondary"),
    ("", "unknown"), ("C", "unknown"), ("P/S", "unknown"), ("PS", "unknown"),
])
def test_comtrade_structured_side_preserves_scaled_samples(client, comtrade_fixtures_dir, marker, expected):
    source = upload_side(client, comtrade_fixtures_dir, marker)
    active = client.app.state.workspace_registry.get(WS, source)
    raw = next(ch for ch in active.record.analog_channels if ch.name == "IBT_HV_IR")
    summary = next(ch for ch in active.metadata.analog_channels if ch.name == raw.name)
    channels = checked(client.get(f"{ROOT}/sources/{source}/channels"))["analog_channels"]
    wire = next(ch for ch in channels if ch["name"] == raw.name)
    assert raw.measurement_side == summary.measurement_side == wire["measurement_side"] == expected
    assert raw.primary_ratio == 4000 and raw.secondary_ratio == 5
    assert raw.scale == 4199 and raw.offset == 0
    assert active.record.waveform_data[raw.name].tolist() == [4199.] * 5
    assert comtrade_measurement_side(None) == "unknown"


def test_csv_and_ben_have_unknown_side_without_inference(client):
    prepared = _prepared_current_source(client, measured_unit="A")
    converted = checked(client.post(f"/api/v1/workspaces/{CSV_WS}/preparation-sources/{prepared}/convert"))
    active = client.app.state.workspace_registry.get(CSV_WS, converted["source_id"])
    assert all(ch.measurement_side == "unknown" for ch in active.metadata.analog_channels)
    assert all(ch.measurement_side == "unknown" for ch in active.record.analog_channels)
    imported = checked(client.post(ROOT + "/sources", files={
        "ben_file": ("synthetic.ben", io.BytesIO(_fast_bytes()), "application/octet-stream"),
    }), 201)
    active = client.app.state.workspace_registry.get(WS, imported["source_id"])
    assert all(ch.measurement_side == "unknown" for ch in active.metadata.analog_channels)
    assert all(ch.measurement_side == "unknown" for ch in active.record.analog_channels)


def test_group_omission_reset_and_method_transitions(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    group, url = manual(client, source, "IBT_HV_IR")
    def save(body):
        return checked(client.put(url, json=body))["current_config"]
    assert save({"method": "manual", "manual_ibase_ka": 3})["base_reference_side"] == "primary"
    assert save({"method": "manual", "manual_ibase_ka": 3, "base_reference_side": "unknown"})["base_reference_side"] == "unknown"
    assert save({"method": "equipment_rating", "equipment_rating_mva": 100, "manual_voltage_base_kv": 275})["base_reference_side"] == "primary"
    assert save({"method": "manual", "manual_ibase_ka": 3})["base_reference_side"] == "unknown"
    assert save({"method": "none"})["base_reference_side"] == "unknown"
    provenance = checked(client.get(f"{ROOT}/sources/{source}/per-unit-resolution", params={"channel_name": "IBT_HV_IR"}))
    assert provenance["measurement_side"] == "primary"
    assert provenance["base_reference_side"] == "unknown"


def test_default_omission_reset_and_method_transitions(client, comtrade_fixtures_dir):
    source = upload_side(client, comtrade_fixtures_dir)
    url = f"{ROOT}/per-unit/sources/{source}"
    base = {"current_base_mode": "direct", "direct_current_base_value": 2}
    assert checked(client.put(url, json=base))["current_base_reference_side"] == "unknown"
    assert checked(client.put(url, json={**base, "current_base_reference_side": "secondary"}))["current_base_reference_side"] == "secondary"
    assert checked(client.put(url, json=base))["current_base_reference_side"] == "secondary"
    assert checked(client.put(url, json={**base, "current_base_reference_side": "unknown"}))["current_base_reference_side"] == "unknown"
    derived = {"current_base_mode": "derived", "apparent_power_base_value": 100, "voltage_base_value": 275}
    assert checked(client.put(url, json=derived))["current_base_reference_side"] == "primary"
    assert checked(client.put(url, json=base))["current_base_reference_side"] == "unknown"
    assert checked(client.put(url, json={}))["current_base_reference_side"] == "unknown"


@pytest.mark.parametrize("scope", ["group", "default"])
@pytest.mark.parametrize("side", [None, True, False, 1, "Primary", "invalid", ["primary"], {"side": "primary"}])
def test_invalid_side_rejection_preserves_all_configuration_and_values(client, comtrade_fixtures_dir, scope, side):
    source = upload_side(client, comtrade_fixtures_dir)
    _, url = manual(client, source, "IBT_HV_IR")
    manual(client, source, "IBT_HV_IY")
    cid = create_chain(client, source, 2)
    waveform = f"{ROOT}/calculated-channels/{cid}/waveform?unit_mode=per_unit"
    before_values = checked(client.get(waveform))
    before = configuration_snapshot(client)
    if scope == "group":
        response = client.put(url, json={"method": "manual", "manual_ibase_ka": 4, "base_reference_side": side})
    else:
        response = client.put(f"{ROOT}/per-unit/sources/{source}", json={
            "current_base_mode": "direct", "direct_current_base_value": 4, "current_base_reference_side": side,
        })
    assert response.status_code == 422
    assert configuration_snapshot(client) == before
    assert checked(client.get(waveform)) == before_values


@pytest.mark.parametrize("scope", ["group", "default"])
@pytest.mark.parametrize("side", ["secondary", "unknown"])
def test_derived_side_contradiction_is_atomic(client, comtrade_fixtures_dir, scope, side):
    source = upload_side(client, comtrade_fixtures_dir)
    _, url = manual(client, source, "IBT_HV_IR")
    before = configuration_snapshot(client)
    if scope == "group":
        response = client.put(url, json={"method": "equipment_rating", "equipment_rating_mva": 100,
            "manual_voltage_base_kv": 275, "base_reference_side": side})
    else:
        response = client.put(f"{ROOT}/per-unit/sources/{source}", json={"current_base_mode": "derived",
            "apparent_power_base_value": 100, "voltage_base_value": 275, "current_base_reference_side": side})
    assert response.status_code == 400
    assert configuration_snapshot(client) == before


def test_failed_publication_does_not_change_group_config(client, comtrade_fixtures_dir, monkeypatch):
    source = upload_side(client, comtrade_fixtures_dir)
    _, url = manual(client, source, "IBT_HV_IR")
    before = configuration_snapshot(client)
    def fail(_):
        raise RuntimeError("publication fault")
    monkeypatch.setattr(client.app.state.current_group_config_registry, "upsert", fail)
    with pytest.raises(RuntimeError, match="publication fault"):
        client.put(url, json={"method": "manual", "manual_ibase_ka": 4, "base_reference_side": "secondary"})
    assert configuration_snapshot(client) == before
