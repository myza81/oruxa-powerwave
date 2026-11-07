"""LIM-001: physical reference proof, independent of numerical base availability."""
import io
import math

import pytest

from tests.test_current_effective_base_inheritance import (
    client, checked, ROOT, WS, configuration_snapshot,
)

NAMES = ["IBT_HV_IR", "IBT_HV_IY"]


def recording(client, fixtures, marker="S", second_marker=None):
    lines = (fixtures / "synth_measurement_groups.cfg").read_text().splitlines()
    for index in range(2, 21):
        fields = lines[index].split(",")
        if fields[4] == "A":
            fields[5] = "0.5"
            fields[-3:] = ["2000", "1", second_marker if second_marker is not None and fields[1] == NAMES[1] else marker]
            lines[index] = ",".join(fields)
    sid = checked(client.post(ROOT + "/sources", files={
        "cfg_file": ("reference.cfg", io.BytesIO("\n".join(lines).encode()), "application/octet-stream"),
        "dat_file": ("reference.dat", io.BytesIO((fixtures / "synth_measurement_groups.dat").read_bytes()), "application/octet-stream"),
    }), 201)["source_id"]
    url = f"{ROOT}/sources/{sid}/measurement-groups"
    for group in checked(client.get(url)):
        assert client.delete(url + "/" + group["id"]).status_code == 204
    return sid


def setup_base(client, sid, method, side="primary", names=NAMES):
    if method.startswith("group"):
        url = f"{ROOT}/sources/{sid}/measurement-groups"
        group = checked(client.post(url, json={
            "kind": "current", "display_name": "Reference safety", "status": "confirmed",
            "channel_refs": [{"kind": "source", "source_id": sid, "channel_name": n} for n in names],
        }), 201)
        path = url + "/" + group["id"] + "/current-config"
        body = {"method": "manual", "manual_ibase_ka": 2, "base_reference_side": side} if method == "group_manual" else {
            "method": "equipment_rating", "equipment_rating_mva": 2 * math.sqrt(3), "manual_voltage_base_kv": 1,
        }
    else:
        path = f"{ROOT}/per-unit/sources/{sid}"
        body = {"current_base_mode": "direct", "direct_current_base_value": 2, "current_base_reference_side": side} if method == "default_direct" else {
            "current_base_mode": "derived", "voltage_base_value": 1, "apparent_power_base_value": 2 * math.sqrt(3),
            "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_line",
        }
    checked(client.put(path, json=body))
    return path


def calculated(client, sid, parent=None):
    count = len(checked(client.get(ROOT + "/calculated-channels")))
    return checked(client.post(ROOT + "/calculated-channels", json={
        "name": f"Reference result {count}", "operation": "absolute_value" if parent else "addition",
        "inputs": [{"kind": "calculated", "calculated_channel_id": parent}] if parent else [
            {"kind": "source", "source_id": sid, "channel_name": n} for n in NAMES],
    }), 201)["id"]


def consumers(client, identity, *, name=None):
    raw = name is not None
    path = ROOT + ("/sources/" if raw else "/calculated-channels/") + identity
    params = {"channel_name": name} if raw else {}
    wave = checked(client.get(path + "/waveform", params={**params, "unit_mode": "per_unit"}))
    provenance = checked(client.get(path + "/per-unit-resolution", params=params))
    cursor = checked(client.post(path + "/cursor-values" if raw else ROOT + "/calculated-channels/cursor-values", json={
        "analog_channel_names" if raw else "calculated_channel_ids": [name if raw else identity],
        "cursor_a_time": 0, "cursor_b_time": .0008, "unit_mode": "per_unit",
    }))["channels"][0]
    anchor = checked(client.post(path + "/annotation-anchor", json={
        **({"channel_name": name} if raw else {}), "approximate_elapsed_seconds": 0, "unit_mode": "per_unit",
    }))
    peaks = checked(client.post(path + "/peak-values" if raw else ROOT + "/calculated-channels/peak-values", json={
        "start_time": 0, "end_time": .001, "unit_mode": "per_unit", "requests": [
            {"channel_name" if raw else "calculated_channel_id": name if raw else identity, "mode": m} for m in ("max", "min")],
    }))["results"]
    return [wave, cursor, anchor, *peaks], provenance


def assert_consumers(client, identity, *, name=None, compatible="compatible", eligible=True, denominator=2000):
    values, provenance = consumers(client, identity, name=name)
    status, unit = ("configured", "pu") if eligible else ("base_required", "A")
    physical = .5 if name else 1.
    expected = physical / denominator if eligible else physical
    for body in values:
        # A known mismatch must fail on status before the new metadata is inspected.
        assert (body["per_unit_status"], body["unit"]) == (status, unit)
        actual = body.get("values", [body.get("a_value", body.get("value"))])
        assert actual == pytest.approx([expected] * len(actual), rel=1e-12)
        if "b_value" in body:
            assert body["b_value"] == pytest.approx(expected, rel=1e-12)
        assert body["per_unit_reference_compatibility"] == compatible
    assert provenance["status"] == status
    assert provenance["reference_compatibility"] == compatible
    if compatible == "incompatible":
        assert "incompatible" in provenance["reason"]
    return provenance


@pytest.mark.parametrize("method,marker,side", [
    (method, "S", "primary") for method in ("group_manual", "group_equipment", "default_direct", "default_derived")
] + [(method, "P", "secondary") for method in ("group_manual", "default_direct")])
def test_known_mismatch_all_consumers(client, comtrade_fixtures_dir, method, marker, side):
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_base(client, sid, method, side)
    cid = calculated(client, sid)
    child = calculated(client, sid, cid)
    before = configuration_snapshot(client)
    assert_consumers(client, sid, name=NAMES[0], compatible="incompatible", eligible=False)
    for result in (cid, child):
        assert_consumers(client, result, compatible="incompatible", eligible=False)
    assert configuration_snapshot(client) == before
    assert checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": NAMES[0]}))["values"] == [.5] * 5
    assert checked(client.get(f"{ROOT}/calculated-channels/{child}/waveform"))["values"] == [1.] * 5
    coverage = checked(client.get(f"{ROOT}/per-unit/sources/{sid}/coverage"))
    assert coverage["measurement_group_count"] == 0
    # Derived Source Default also enables nine unrelated Voltage channels.
    assert coverage["source_default_count"] == (9 if method == "default_derived" else 0)
    assert coverage["unverified_reference_count"] == 0


@pytest.mark.parametrize("marker,side,compatibility", [
    ("P", "primary", "compatible"), ("S", "secondary", "compatible"),
    ("C", "primary", "unverified"), ("", "primary", "unverified"),
    ("P", "unknown", "unverified"), ("S", "unknown", "unverified"), ("C", "unknown", "unverified"),
])
@pytest.mark.parametrize("method", ["group_manual", "default_direct"])
def test_compatible_and_historical_unknown(client, comtrade_fixtures_dir, marker, side, compatibility, method):
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_base(client, sid, method, side)
    cid = calculated(client, sid)
    before = configuration_snapshot(client)
    p = assert_consumers(client, sid, name=NAMES[0], compatible=compatibility)
    assert p["measurement_side"] == {"P": "primary", "S": "secondary"}.get(marker, "unknown")
    assert p["base_reference_side"] == side
    assert_consumers(client, calculated(client, sid, cid), compatible=compatibility)
    coverage = checked(client.get(f"{ROOT}/per-unit/sources/{sid}/coverage"))
    assert coverage["unverified_reference_count"] == ((2 if method == "group_manual" else 9) if compatibility == "unverified" else 0)
    after = configuration_snapshot(client)
    before.pop("assignments"); after.pop("assignments")
    assert before == after


@pytest.mark.parametrize("base_side", ["primary", "unknown"])
def test_mixed_known_sides_are_not_hidden_by_unknown_aggregation(client, comtrade_fixtures_dir, base_side):
    sid = recording(client, comtrade_fixtures_dir, "P", "S")
    setup_base(client, sid, "group_manual", base_side)
    assert_consumers(client, calculated(client, sid), compatible="incompatible", eligible=False)


def test_side_changes_and_rejected_manual_save_are_atomic(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    path = setup_base(client, sid, "group_manual", "secondary")
    cid = calculated(client, sid)
    assert_consumers(client, cid)
    checked(client.put(path, json={"method": "manual", "manual_ibase_ka": 2, "base_reference_side": "primary"}))
    assert_consumers(client, cid, compatible="incompatible", eligible=False)
    before = configuration_snapshot(client), consumers(client, cid)
    r = client.put(f"{ROOT}/calculated-channels/{cid}/per-unit-config", json={
        "mode": "manual", "current_base_value": 2, "current_base_unit": "kA", "base_reference_side": "primary",
    })
    assert r.status_code == 400
    assert (configuration_snapshot(client), consumers(client, cid)) == before
    checked(client.put(path, json={"method": "manual", "manual_ibase_ka": 2, "base_reference_side": "unknown"}))
    assert_consumers(client, cid, compatible="unverified")


def test_legacy_assignment_cannot_bypass_known_reference_mismatch(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir)
    setup_base(client, sid, "group_manual", "primary", [NAMES[0]])
    setup_base(client, sid, "group_manual", "primary", [NAMES[1]])
    setup_base(client, sid, "default_direct", "primary")
    cid = calculated(client, sid)
    client.app.state.per_unit_registry.set_manual_assignment_for_calculated_channel(WS, cid, sid)
    assert_consumers(client, calculated(client, sid, cid), compatible="incompatible", eligible=False)


def test_manual_result_replaces_incompatible_input_base_without_mutation(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "P")
    setup_base(client, sid, "group_manual", "secondary")
    cid = calculated(client, sid)
    assert_consumers(client, cid, compatible="incompatible", eligible=False)
    before = configuration_snapshot(client)
    checked(client.put(f"{ROOT}/calculated-channels/{cid}/per-unit-config", json={
        "mode": "manual", "current_base_value": 1, "current_base_unit": "A", "base_reference_side": "primary",
    }))
    assert_consumers(client, cid, denominator=1)
    after = configuration_snapshot(client)
    before.pop("assignments"); after.pop("assignments")
    assert before == after
    assert_consumers(client, calculated(client, sid, cid), compatible="incompatible", eligible=False)


@pytest.mark.parametrize("provider", ["csv", "ben"])
def test_real_unknown_provider_retains_unverified_current_pu(client, provider):
    if provider == "csv":
        from tests.test_measured_unit_per_unit import _prepared_current_source
        prepared = _prepared_current_source(client, measured_unit="A")
        base = "/api/v1/workspaces/ws-1"
        sid = checked(client.post(base + f"/preparation-sources/{prepared}/convert"))["source_id"]
        name, scale = "IR", 1
    else:
        from tests.test_ben_import_api import _fast_bytes
        base = "/api/v1/workspaces/ws-ben"
        sid = checked(client.post(base + "/sources", files={"ben_file": ("unknown.ben", _fast_bytes(), "application/octet-stream")}), 201)["source_id"]
        name, scale = "LINE1 IR", 1000
    groups = base + f"/sources/{sid}/measurement-groups"
    for group in checked(client.get(groups)):
        assert client.delete(groups + "/" + group["id"]).status_code == 204
    checked(client.put(base + f"/per-unit/sources/{sid}", json={
        "current_base_mode": "direct", "direct_current_base_value": 2, "current_base_reference_side": "primary",
    }))
    path = base + f"/sources/{sid}"
    engineering = checked(client.get(path + "/waveform", params={"channel_name": name}))
    wave = checked(client.get(path + "/waveform", params={"channel_name": name, "unit_mode": "per_unit"}))
    proof = checked(client.get(path + "/per-unit-resolution", params={"channel_name": name}))
    assert proof["measurement_side"] == "unknown" and proof["base_reference_side"] == "primary"
    assert proof["reference_compatibility"] == wave["per_unit_reference_compatibility"] == "unverified"
    assert wave["per_unit_status"] == "configured" and wave["unit"] == "pu"
    assert wave["values"] == pytest.approx([value * scale / 2000 for value in engineering["values"]], rel=1e-12)
    assert checked(client.get(path + "/waveform", params={"channel_name": name})) == engineering


def test_compliance_current_reuse_cannot_bypass_result_unassignment(client, comtrade_fixtures_dir):
    from app.domain.calculated_channel import ChannelRef
    from app.services.compliance_series import Registries, load_series
    sid = recording(client, comtrade_fixtures_dir, "P")
    setup_base(client, sid, "group_manual")
    cid = calculated(client, sid)
    checked(client.put(f"{ROOT}/calculated-channels/{cid}/per-unit-config", json={"mode": "unassigned"}))
    state = client.app.state
    reg = Registries(state.workspace_registry, state.calculated_channel_registry, state.per_unit_registry,
                     state.measurement_group_registry, state.voltage_group_config_registry, state.current_group_config_registry)
    series, problem = load_series(ChannelRef(kind="calculated", calculated_channel_id=cid), "pu", workspace_id=WS, reg=reg)
    assert series is None and "per-unit" in problem
