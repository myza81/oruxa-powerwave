"""D4-suggest: non-persisted VT suggestion fields on VoltageGroupConfigOut.

Tests that vt_suggested_primary_v / vt_suggested_secondary_v / vt_suggested_ratio
are computed by _build_voltage_view() under the correct conditions and that
they disappear once a VT is explicitly configured.

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


# ---- Test 1: 275 kV nominal → suggestions present ---------------------------

def test_suggest_275kv(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_authority"] == "not_configured"
    assert math.isclose(vc["vt_suggested_primary_v"], 275_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_suggested_secondary_v"], 110.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_suggested_ratio"], 275_000.0 / 110.0, rel_tol=1e-9)


# ---- Test 2: 132 kV nominal → correct primary suggestion --------------------

def test_suggest_132kv(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 132.0)
    vc = _get_vc(client, ws, src, gid)
    assert math.isclose(vc["vt_suggested_primary_v"], 132_000.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_suggested_secondary_v"], 110.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_suggested_ratio"], 132_000.0 / 110.0, rel_tol=1e-9)


# ---- Test 3: manual VT configured → no suggestions -------------------------

def test_no_suggest_when_manual_vt(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    _set_vt(client, ws, src, gid, 275_000.0, 110.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_authority"] == "manual"
    assert vc["vt_suggested_primary_v"] is None
    assert vc["vt_suggested_secondary_v"] is None
    assert vc["vt_suggested_ratio"] is None


# ---- Test 4: no nominal voltage → no suggestions ----------------------------

def test_no_suggest_without_nominal(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    # Don't set nominal voltage — group starts with needs_review or no base
    vc = _get_vc(client, ws, src, gid)
    # Fresh group from upload has no manual nominal voltage set
    assert vc["vt_suggested_primary_v"] is None


# ---- Test 5: 500 kV nominal → suggestions coexist with other null VT fields -

def test_suggest_500kv_coexists_with_other_fields(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 500.0)
    vc = _get_vc(client, ws, src, gid)
    assert math.isclose(vc["nominal_voltage_ll_kv"], 500.0, rel_tol=1e-9)
    assert math.isclose(vc["vt_suggested_primary_v"], 500_000.0, rel_tol=1e-9)
    # VT fields remain null (suggestion is never auto-persisted)
    assert vc["vt_primary_v"] is None
    assert vc["vt_ratio"] is None


# ---- Test 6: after saving suggestion, suggestions disappear -----------------

def test_suggest_disappears_after_save(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 275.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_suggested_primary_v"] is not None  # suggestion present before save
    _set_vt(client, ws, src, gid, 275_000.0, 110.0)
    vc2 = _get_vc(client, ws, src, gid)
    assert vc2["vt_authority"] == "manual"
    assert vc2["vt_suggested_primary_v"] is None
    assert math.isclose(vc2["vt_primary_v"], 275_000.0, rel_tol=1e-9)


# ---- Test 7: clearing VT restores suggestions if nominal kV still valid -----

def test_suggest_returns_after_clearing_vt(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 132.0)
    _set_vt(client, ws, src, gid, 132_000.0, 110.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_suggested_primary_v"] is None  # no suggestion while VT configured
    # Clear VT
    resp = client.put(
        f"/api/v1/workspaces/{ws}/sources/{src}/measurement-groups/{gid}/voltage-config",
        json={"clear_vt": True},
    )
    assert resp.status_code == 200, resp.text
    vc2 = _get_vc(client, ws, src, gid)
    assert vc2["vt_authority"] == "not_configured"
    assert math.isclose(vc2["vt_suggested_primary_v"], 132_000.0, rel_tol=1e-9)


# ---- Test 8: vt_suggested_ratio = primary_v / 110 (never stored) ------------

def test_suggest_ratio_equals_primary_over_110(client, comtrade_fixtures_dir):
    ws = "ws-1"
    src = _upload(client, ws, comtrade_fixtures_dir)
    gid = _first_voltage_group_id(client, ws, src)
    _set_nominal_kv(client, ws, src, gid, 400.0)
    vc = _get_vc(client, ws, src, gid)
    assert vc["vt_suggested_ratio"] is not None
    expected = 400_000.0 / 110.0
    assert math.isclose(vc["vt_suggested_ratio"], expected, rel_tol=1e-9)
