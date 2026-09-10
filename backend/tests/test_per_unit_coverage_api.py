"""API-level tests for the Per-Unit Settings hierarchy, Slice 2 coverage
endpoint (`GET .../per-unit/sources/{source_id}/coverage`). Exercises the
real FastAPI app end-to-end with the `synth_measurement_groups` fixture
(the same fixture `test_measurement_group_api.py` already uses) --
service-level classification edge cases already have focused coverage in
`test_per_unit_coverage_service.py`; this file only proves the live
endpoint wires that service correctly and matches real upload metadata.

Fixture channel inventory (synth_measurement_groups.cfg): 9 Voltage
channels (N275_VR/VY/VB, S132_VR/VY/VB, E275_VRY/VYB/VBR), 9 Current
channels (IBT_HV_IR/IY/IB, IBT_LV_IR/IY/IB, LINEA_IR, LINEB_IR,
SPARE_IR), 1 Frequency channel (not applicable), 2 digital channels
(not counted) -- 18 applicable Voltage/Current channels total.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

APPLICABLE_TOTAL = 18


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_measurement_groups"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _coverage(client, workspace_id, source_id):
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/per-unit/sources/{source_id}/coverage")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _refs(source_id, *names):
    return [{"kind": "source", "source_id": source_id, "channel_name": n} for n in names]


class TestCoverageEndpoint:
    def test_404_for_unknown_source(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/per-unit/sources/does-not-exist/coverage")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_fresh_upload_is_entirely_needs_configuration(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _coverage(client, "ws-1", source_id)
        assert body["source_id"] == source_id
        assert body["applicable_channel_count"] == APPLICABLE_TOTAL
        assert body["measurement_group_count"] == 0
        assert body["source_default_count"] == 0
        assert body["needs_configuration_count"] == APPLICABLE_TOTAL

    def test_progressive_mixed_configuration_end_to_end(self, client, comtrade_fixtures_dir):
        """Builds up exactly the Slice 2 "mixed source" scenario through
        the real Measurement Group and Source Default APIs, checking
        coverage after each step -- never a shortcut through the
        service/registry layer directly."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        # Step 1: create a Voltage group (3 channels) but do not configure
        # its base yet -- created via POST, so status is already "manual"
        # (authoritative), but pu_status stays base_required until a base
        # is set. Coverage must be unchanged (still all ungrouped-shaped
        # needs_configuration, just now routed through the group path).
        group_resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups",
            json={
                "kind": "voltage",
                "display_name": "275 NORTH BUS",
                "channel_refs": _refs(source_id, "N275_VR", "N275_VY", "N275_VB"),
            },
        )
        assert group_resp.status_code == 201, group_resp.text
        group_id = group_resp.json()["id"]

        body = _coverage(client, "ws-1", source_id)
        assert body["applicable_channel_count"] == APPLICABLE_TOTAL
        assert body["measurement_group_count"] == 0
        assert body["needs_configuration_count"] == APPLICABLE_TOTAL

        # Step 2: configure the group's own base -- those 3 channels move
        # to Measurement Groups.
        cfg_resp = client.put(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups/{group_id}/voltage-config",
            json={"nominal_voltage_ll_kv": 275.0},
        )
        assert cfg_resp.status_code == 200, cfg_resp.text

        body = _coverage(client, "ws-1", source_id)
        assert body["applicable_channel_count"] == APPLICABLE_TOTAL
        assert body["measurement_group_count"] == 3
        assert body["source_default_count"] == 0
        assert body["needs_configuration_count"] == APPLICABLE_TOTAL - 3

        # Step 3: configure Source Default (Voltage only, Current left
        # "none") -- the 6 remaining ungrouped Voltage channels
        # (S132_V*, E275_V*) move to Source Default; the grouped 3 stay
        # under Measurement Groups (DEC-051: never re-consulted); the 9
        # Current channels stay needs_configuration (no current base
        # configured).
        default_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 132.0},
        )
        assert default_resp.status_code == 200, default_resp.text

        body = _coverage(client, "ws-1", source_id)
        assert body["applicable_channel_count"] == APPLICABLE_TOTAL
        assert body["measurement_group_count"] == 3
        assert body["source_default_count"] == 6
        assert body["needs_configuration_count"] == 9
        assert (
            body["measurement_group_count"] + body["source_default_count"] + body["needs_configuration_count"]
            == body["applicable_channel_count"]
        )

    def test_grouped_but_incomplete_never_falls_back_to_source_default(self, client, comtrade_fixtures_dir):
        """Critical DEC-051 requirement, verified through the live API: a
        group left unconfigured must count as needs_configuration even
        when a fully valid Source Default already covers the same
        engineering type."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        # A fully usable Source Default exists for Voltage up front.
        default_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 275.0},
        )
        assert default_resp.status_code == 200, default_resp.text

        # Now group 3 Voltage channels but never configure the group's
        # own base.
        group_resp = client.post(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/measurement-groups",
            json={
                "kind": "voltage",
                "display_name": "275 NORTH BUS",
                "channel_refs": _refs(source_id, "N275_VR", "N275_VY", "N275_VB"),
            },
        )
        assert group_resp.status_code == 201, group_resp.text

        body = _coverage(client, "ws-1", source_id)
        # The 3 grouped channels must NOT be counted as source_default
        # merely because a usable Source Default exists on the source.
        assert body["measurement_group_count"] == 0
        # The 6 remaining ungrouped Voltage channels DO use Source
        # Default normally.
        assert body["source_default_count"] == 6
        # The 3 grouped-but-unconfigured + 9 Current channels.
        assert body["needs_configuration_count"] == 12
