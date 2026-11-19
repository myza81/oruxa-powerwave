"""D4-effective: vt_effective_* authority hierarchy on VoltageGroupConfigOut.

Tests that vt_effective_primary_v / vt_effective_secondary_v / vt_effective_authority
are computed by _build_voltage_view() under the correct authority hierarchy
(manual > recording_metadata > auto_nominal > not_configured).

Uses the auto-discovered groups created by upload rather than creating manual
groups (which would clash with the channel-claim index).
"""

from __future__ import annotations

import io
import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _first_voltage_group_id(client, workspace_id, source_id):
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups")
    assert resp.status_code == 200
    for g in resp.json():
        if g["kind"] == "voltage":
            return g["id"]
    raise AssertionError("no voltage group found after upload")


def _set_nominal_kv(client, workspace_id, source_id, group_id, kv):
    resp = client.put(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups/{group_id}/voltage-config",
        json={"nominal_voltage_ll_kv": kv},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["voltage_config"]


def _set_vt(client, workspace_id, source_id, group_id, primary_v, secondary_v):
    resp = client.put(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups/{group_id}/voltage-config",
        json={"vt_primary_v": primary_v, "vt_secondary_v": secondary_v},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["voltage_config"]


def _get_vc(client, workspace_id, source_id, group_id):
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups")
    assert resp.status_code == 200
    for g in resp.json():
        if g["id"] == group_id:
            return g["voltage_config"]
    raise AssertionError(f"group {group_id} not found in listing")


# ---- Test 1: 275 kV nominal → auto_nominal effective values ------------------

def test_effective_275kv_auto_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_authority"] == "not_configured"
    assert vc["vt_effective_authority"] == "auto_nominal"
    assert math.isclose(vc["vt_effective_primary_v"], 275_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_effective_secondary_v"], 110.0, rel_tol=1e-9)


# ---- Test 2: 132 kV nominal → correct auto_nominal primary ------------------

def test_effective_132kv_auto_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 132.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "auto_nominal"
    assert math.isclose(vc["vt_effective_primary_v"], 132_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_effective_secondary_v"], 110.0, rel_tol=1e-9)


# ---- Test 3: manual VT configured → effective reflects manual values --------

def test_effective_manual_vt_overrides_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    _set_vt(client, ws, src, gid, 275_000.0, 110.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_authority"] == "manual"
    assert vc["vt_effective_authority"] == "manual"
    assert math.isclose(vc["vt_effective_primary_v"], 275_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_effective_secondary_v"], 110.0, rel_tol=1e-9)


# ---- Test 4: no nominal voltage → not_configured ----------------------------

def test_no_effective_without_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    # Fresh group from upload has no manual nominal voltage
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "not_configured"
    assert vc["vt_effective_primary_v"] is None
    assert vc["vt_effective_secondary_v"] is None


# ---- Test 5: 500 kV nominal → auto_nominal, stored VT fields still null -----

def test_effective_coexists_with_null_stored_vt(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 500.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "auto_nominal"
    assert math.isclose(vc["vt_effective_primary_v"], 500_000.0, rel_tol=1e-9)
    # Stored VT fields remain null — auto_nominal is never persisted
    assert vc["vt_primary_v"] is None
    assert vc["vt_ratio"] is None


# ---- Test 6: after saving VT, effective reflects manual ---------------------

def test_effective_reflects_manual_after_save(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "auto_nominal"
    _set_vt(client, ws, src, gid, 275_000.0, 110.0)
    vc2 = _get_vc(client, ws, src, gid)
    assert vc2["vt_effective_authority"] == "manual"
    assert math.isclose(vc2["vt_effective_primary_v"], 275_000.0, rel_tol=1e-9)
    assert math.isclose(vc2["vt_primary_v"], 275_000.0, rel_tol=1e-9)


# ---- Test 7: clearing VT restores auto_nominal if nominal kV still valid ----

def test_clearing_vt_restores_auto_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 132.0)
    _set_vt(client, ws, src, gid, 132_000.0, 110.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "manual"
    # Clear VT
    resp = client.put(
        f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{gid}/voltage-config",
        json={"clear_vt": True},
    )
    assert resp.status_code == 200, resp.text
    vc2 = _get_vc(client, ws, src, gid)
    assert vc2["vt_authority"] == "not_configured"
    assert vc2["vt_effective_authority"] == "auto_nominal"
    assert math.isclose(vc2["vt_effective_primary_v"], 132_000.0, rel_tol=1e-9)


# ---- Test 8: vt_effective_primary_v = nominal_kv * 1000 exactly -------------

def test_effective_primary_equals_nominal_times_1000(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 400.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "auto_nominal"
    assert math.isclose(vc["vt_effective_primary_v"], 400_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_effective_secondary_v"], 110.0, rel_tol=1e-9)


# ---- Test 9: vt_suggested_* fields are absent (replaced by vt_effective_*) --

def test_vt_suggested_fields_absent(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    vc = _get_vc(client, ws, src, gid)
    assert "vt_suggested_primary_v" not in vc
    assert "vt_suggested_secondary_v" not in vc
    assert "vt_suggested_ratio" not in vc


# ---- Test 10: vt_effective_* fields are present on the wire -----------------

def test_vt_effective_fields_present(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    vc = _get_vc(client, ws, src, gid)
    assert "vt_effective_primary_v" in vc
    assert "vt_effective_secondary_v" in vc
    assert "vt_effective_authority" in vc


# ---- Test 11: manual VT with custom secondary (100 V) reflects exactly ------

def test_effective_manual_custom_secondary(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    _set_vt(client, ws, src, gid, 275_000.0, 100.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "manual"
    assert math.isclose(vc["vt_effective_primary_v"], 275_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_effective_secondary_v"], 100.0, rel_tol=1e-9)


# ---- Test 12: not_configured authority when no VT and no valid nominal -------

def test_not_configured_authority_no_vt_no_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_effective_authority"] == "not_configured"
    assert vc["vt_effective_primary_v"] is None
    assert vc["vt_effective_secondary_v"] is None
