"""API-level tests for the Phase 5C Per-Unit Base Profile endpoints
(DEC-049): profile CRUD, base-field validation, decision 4's conflict/
reassignment rule, and workspace/source/calculated-channel lifecycle
cleanup wired through the real FastAPI app (not just the registry
directly -- see test_per_unit_registry.py for that).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _read(path) -> bytes:
    return path.read_bytes()


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
    dat = _read(comtrade_fixtures_dir / f"{stem}.dat")
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _va_ref(source_id: str) -> dict:
    return {"kind": "source", "source_id": source_id, "channel_name": "VA"}


def _ia_ref(source_id: str) -> dict:
    return {"kind": "source", "source_id": source_id, "channel_name": "IA"}


class TestProfileCrud:
    def test_create_then_list(self, client):
        resp = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "275 kV"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "275 kV"
        assert body["assigned_channels"] == []
        assert body["resolved_current_base"] is None

        listed = client.get("/api/v1/workspaces/ws-1/per-unit/profiles").json()
        assert [p["id"] for p in listed] == [body["id"]]

    def test_update_base_fields_and_resolved_current_base(self, client):
        create_resp = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "275 kV"})
        profile_id = create_resp.json()["id"]

        put_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_id}",
            json={
                "name": "275 kV",
                "voltage_base_value": 275.0,
                "voltage_base_unit": "kV",
                "voltage_basis": "line_to_line",
                "apparent_power_base_value": 500.0,
                "apparent_power_base_unit": "MVA",
                "current_base_mode": "derived",
                "assigned_channels": [],
            },
        )
        assert put_resp.status_code == 200, put_resp.text
        body = put_resp.json()
        assert body["resolved_current_base"]["unit"] == "A"
        assert body["resolved_current_base"]["value"] == pytest.approx(500_000_000.0 / (1.7320508075688772 * 275_000.0))

    def test_invalid_partial_voltage_base_is_rejected(self, client):
        create_resp = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "275 kV"})
        profile_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_id}",
            json={"name": "275 kV", "voltage_base_value": 275.0, "assigned_channels": []},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_per_unit_base"

    def test_delete_unknown_profile_is_404(self, client):
        resp = client.delete("/api/v1/workspaces/ws-1/per-unit/profiles/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "per_unit_profile_not_found"

    def test_assigning_nonexistent_channel_is_rejected(self, client):
        create_resp = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "275 kV"})
        profile_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_id}",
            json={
                "name": "275 kV",
                "assigned_channels": [{"kind": "source", "source_id": "no-such-source", "channel_name": "VA"}],
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_channel_assignment"


class TestChannelAssignmentConflict:
    def test_reassignment_is_rejected_without_flag_then_succeeds_with_it(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        profile_a = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "Profile A"}).json()
        profile_b = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "Profile B"}).json()

        assign_a = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_a['id']}",
            json={"name": "Profile A", "assigned_channels": [_va_ref(source_id)]},
        )
        assert assign_a.status_code == 200

        conflict_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_b['id']}",
            json={"name": "Profile B", "assigned_channels": [_va_ref(source_id)]},
        )
        assert conflict_resp.status_code == 400
        detail = conflict_resp.json()["detail"]
        assert detail["code"] == "channel_already_assigned"
        assert detail["conflicts"][0]["profile_id"] == profile_a["id"]
        assert detail["conflicts"][0]["profile_name"] == "Profile A"

        # Profile A is unaffected by the rejected attempt.
        still_a = client.get(f"/api/v1/workspaces/ws-1/per-unit/profiles").json()
        profile_a_now = next(p for p in still_a if p["id"] == profile_a["id"])
        assert len(profile_a_now["assigned_channels"]) == 1

        move_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile_b['id']}",
            json={"name": "Profile B", "assigned_channels": [_va_ref(source_id)], "reassign_conflicting": True},
        )
        assert move_resp.status_code == 200
        assert len(move_resp.json()["assigned_channels"]) == 1

        after = client.get(f"/api/v1/workspaces/ws-1/per-unit/profiles").json()
        profile_a_after = next(p for p in after if p["id"] == profile_a["id"])
        assert profile_a_after["assigned_channels"] == []


class TestLifecycleCleanup:
    def test_deleting_a_calculated_channel_removes_its_own_assignment(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        profile = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "P"}).json()
        calc_resp = client.post(
            "/api/v1/workspaces/ws-1/calculated-channels",
            json={
                "name": "-VA", "operation": "reverse_polarity",
                "inputs": [_va_ref(source_id)], "parameters": {},
            },
        )
        assert calc_resp.status_code == 201, calc_resp.text
        calc_id = calc_resp.json()["id"]

        assign_resp = client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile['id']}",
            json={
                "name": "P",
                "assigned_channels": [
                    _va_ref(source_id),
                    {"kind": "calculated", "calculated_channel_id": calc_id},
                ],
            },
        )
        assert assign_resp.status_code == 200
        assert len(assign_resp.json()["assigned_channels"]) == 2

        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/calculated-channels/{calc_id}")
        assert delete_resp.status_code == 204

        after = client.get("/api/v1/workspaces/ws-1/per-unit/profiles").json()
        profile_after = next(p for p in after if p["id"] == profile["id"])
        assert len(profile_after["assigned_channels"]) == 1
        assert profile_after["assigned_channels"][0]["channel_name"] == "VA"

    def test_deleting_a_source_removes_its_channels_own_assignments(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        profile = client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "P"}).json()
        client.put(
            f"/api/v1/workspaces/ws-1/per-unit/profiles/{profile['id']}",
            json={"name": "P", "assigned_channels": [_va_ref(source_id), _ia_ref(source_id)]},
        )

        assert client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 204

        after = client.get("/api/v1/workspaces/ws-1/per-unit/profiles").json()
        profile_after = next(p for p in after if p["id"] == profile["id"])
        assert profile_after["assigned_channels"] == []

    def test_deleting_the_workspace_clears_every_profile(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.post("/api/v1/workspaces/ws-1/per-unit/profiles", json={"name": "P"})

        assert client.delete("/api/v1/workspaces/ws-1").status_code == 204

        assert client.get("/api/v1/workspaces/ws-1/per-unit/profiles").json() == []

    def test_deleting_the_workspace_does_not_affect_other_workspaces(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-target", comtrade_fixtures_dir)
        _upload(client, "ws-other", comtrade_fixtures_dir)
        client.post("/api/v1/workspaces/ws-target/per-unit/profiles", json={"name": "Target"})
        client.post("/api/v1/workspaces/ws-other/per-unit/profiles", json={"name": "Other"})

        assert client.delete("/api/v1/workspaces/ws-target").status_code == 204

        assert client.get("/api/v1/workspaces/ws-target/per-unit/profiles").json() == []
        assert len(client.get("/api/v1/workspaces/ws-other/per-unit/profiles").json()) == 1
