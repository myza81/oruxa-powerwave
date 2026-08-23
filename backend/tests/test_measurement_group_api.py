"""API-level tests for DEC-050 Slice 6's thin Measurement Group / Voltage
/ Current configuration REST exposure
(`app/api/v1/measurement_groups.py`). Exercises the real FastAPI app
end-to-end -- see `test_measurement_group_service.py`/
`test_voltage_group_config_service.py`/`test_current_group_config_service.py`
for the already-proven service-layer behaviour this router only exposes,
never re-implements.
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


def _base_url(workspace_id, source_id):
    return f"/api/v1/workspaces/{workspace_id}/sources/{source_id}/measurement-groups"


def _refs(source_id, *names):
    return [{"kind": "source", "source_id": source_id, "channel_name": n} for n in names]


def _create_voltage_group(client, workspace_id, source_id, names, display_name="VOLTAGE GROUP"):
    resp = client.post(
        _base_url(workspace_id, source_id),
        json={"kind": "voltage", "display_name": display_name, "channel_refs": _refs(source_id, *names)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_current_group(client, workspace_id, source_id, names, display_name="CURRENT GROUP"):
    resp = client.post(
        _base_url(workspace_id, source_id),
        json={"kind": "current", "display_name": display_name, "channel_refs": _refs(source_id, *names)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestListAndCreate:
    def test_list_is_empty_for_a_fresh_source(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.get(_base_url("ws-1", source_id))
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_list_404s_for_an_unknown_source(self, client):
        resp = client.get(_base_url("ws-1", "does-not-exist"))
        assert resp.status_code == 404

    def test_create_voltage_group_returns_201_with_embedded_config(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"], "275 NORTH BUS")
        assert body["kind"] == "voltage"
        assert body["voltage_config"]["effective_reference"] == "line_to_ground"
        assert body["current_config"] is None
        assert body["pu_status"] == "base_required"
        assert len(body["channel_refs"]) == 3

    def test_create_current_group_returns_201(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        body = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"], "LINE A CURRENT")
        assert body["kind"] == "current"
        assert body["current_config"]["method"] == "none"
        assert body["voltage_config"] is None

    def test_create_rejects_a_channel_of_the_wrong_engineering_type(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(
            _base_url("ws-1", source_id),
            json={"kind": "voltage", "display_name": "BAD", "channel_refs": _refs(source_id, "FREQ")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_wrong_engineering_type"

    def test_create_rejects_a_channel_from_a_different_source(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(
            _base_url("ws-1", source_a),
            json={"kind": "voltage", "display_name": "BAD", "channel_refs": _refs(source_b, "N275_VR")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_wrong_source"


class TestGetUpdateDelete:
    def test_get_returns_the_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.get(f"{_base_url('ws-1', source_id)}/{created['id']}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == created["id"]

    def test_get_404s_for_a_group_from_a_different_source(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.get(f"{_base_url('ws-1', source_b)}/{created['id']}")
        assert resp.status_code == 404

    def test_patch_updates_display_name_and_status(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.patch(
            f"{_base_url('ws-1', source_id)}/{created['id']}",
            json={"display_name": "RENAMED", "status": "confirmed"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["display_name"] == "RENAMED"
        assert body["status"] == "confirmed"

    def test_patch_replaces_channel_membership(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        resp = client.patch(
            f"{_base_url('ws-1', source_id)}/{created['id']}",
            json={"channel_refs": _refs(source_id, "LINEB_IR")},
        )
        assert resp.status_code == 200, resp.text
        names = [r["channel_name"] for r in resp.json()["channel_refs"]]
        assert names == ["LINEB_IR"]

    def test_delete_is_idempotent(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.delete(f"{_base_url('ws-1', source_id)}/{created['id']}")
        assert resp.status_code == 204
        resp2 = client.delete(f"{_base_url('ws-1', source_id)}/{created['id']}")
        assert resp2.status_code == 204
        assert client.get(f"{_base_url('ws-1', source_id)}/{created['id']}").status_code == 404

    def test_delete_404s_for_a_group_from_a_different_source(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.delete(f"{_base_url('ws-1', source_b)}/{created['id']}")
        assert resp.status_code == 404
        # Untouched in its real (source_a) home.
        assert client.get(f"{_base_url('ws-1', source_a)}/{created['id']}").status_code == 200


class TestVoltageConfigEndpoint:
    def test_set_nominal_base_resolves_configured(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": 275.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["voltage_config"]["nominal_voltage_ll_kv"] == 275.0
        assert body["pu_status"] == "configured"

    def test_manual_reference_override(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": 275.0, "reference_mode": "manual", "reference_override": "line_to_line"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["voltage_config"]["reference_mode"] == "manual"
        assert body["voltage_config"]["effective_reference"] == "line_to_line"

    def test_return_to_auto_clears_the_override(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        client.put(
            f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config",
            json={"reference_mode": "manual", "reference_override": "line_to_line"},
        )
        resp = client.put(f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config", json={"reference_mode": "auto"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["voltage_config"]["reference_mode"] == "auto"
        assert body["voltage_config"]["effective_reference"] == "line_to_ground"

    def test_rejects_invalid_base_value(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": -5.0},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_voltage_base_value"

    def test_rejects_a_current_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{created['id']}/voltage-config",
            json={"nominal_voltage_ll_kv": 275.0},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "voltage_configuration_not_applicable"


class TestCurrentConfigEndpoint:
    def test_equipment_rating_with_linked_voltage_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        voltage = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        client.put(f"{_base_url('ws-1', source_id)}/{voltage['id']}/voltage-config", json={"nominal_voltage_ll_kv": 275.0})
        current = _create_current_group(client, "ws-1", source_id, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"])

        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{current['id']}/current-config",
            json={"method": "equipment_rating", "equipment_rating_mva": 1000.0, "linked_voltage_group_id": voltage["id"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["current_config"]["resolved_ibase_ka"] == pytest.approx(2.0995, abs=0.001)
        assert body["pu_status"] == "configured"

    def test_equipment_rating_with_manual_voltage_base(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        current = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{current['id']}/current-config",
            json={"method": "equipment_rating", "equipment_rating_mva": 500.0, "manual_voltage_base_kv": 275.0},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_config"]["resolved_ibase_ka"] == pytest.approx(1.0497, abs=0.001)

    def test_manual_ibase(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        current = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{current['id']}/current-config",
            json={"method": "manual", "manual_ibase_ka": 1.5},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["current_config"]["manual_ibase_ka"] == 1.5
        # A manually-created group defaults to status="manual", which
        # IS authoritative -- resolves immediately, no separate confirm step.
        assert body["pu_status"] == "configured"

    def test_none_method_clears_stale_fields(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        current = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        client.put(
            f"{_base_url('ws-1', source_id)}/{current['id']}/current-config",
            json={"method": "manual", "manual_ibase_ka": 1.5},
        )
        resp = client.put(f"{_base_url('ws-1', source_id)}/{current['id']}/current-config", json={"method": "none"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["current_config"]["manual_ibase_ka"] is None
        assert body["current_config"]["method"] == "none"

    def test_rejects_cross_source_linked_voltage_group(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        voltage_a = _create_voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"])
        client.put(f"{_base_url('ws-1', source_a)}/{voltage_a['id']}/voltage-config", json={"nominal_voltage_ll_kv": 275.0})
        current_b = _create_current_group(client, "ws-1", source_b, ["IBT_HV_IR", "IBT_HV_IY", "IBT_HV_IB"])

        resp = client.put(
            f"{_base_url('ws-1', source_b)}/{current_b['id']}/current-config",
            json={"method": "equipment_rating", "equipment_rating_mva": 1000.0, "linked_voltage_group_id": voltage_a["id"]},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_linked_voltage_group"

    def test_rejects_a_voltage_group(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        voltage = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{voltage['id']}/current-config",
            json={"method": "manual", "manual_ibase_ka": 1.5},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "current_configuration_not_applicable"

    def test_rejects_ambiguous_voltage_source(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        voltage = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        client.put(f"{_base_url('ws-1', source_id)}/{voltage['id']}/voltage-config", json={"nominal_voltage_ll_kv": 275.0})
        current = _create_current_group(client, "ws-1", source_id, ["LINEA_IR"])
        resp = client.put(
            f"{_base_url('ws-1', source_id)}/{current['id']}/current-config",
            json={
                "method": "equipment_rating", "equipment_rating_mva": 500.0,
                "linked_voltage_group_id": voltage["id"], "manual_voltage_base_kv": 275.0,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "ambiguous_current_voltage_source"


class TestSuggestGroups:
    def test_suggest_is_never_triggered_automatically(self, client, comtrade_fixtures_dir):
        """Just uploading a source, or GETting the (empty) group list,
        must never itself create any group -- Slice 2's own standalone-
        only scope, unchanged."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.get(_base_url("ws-1", source_id))
        client.get(_base_url("ws-1", source_id))
        assert client.get(_base_url("ws-1", source_id)).json() == []

    def test_suggest_creates_groups_only_when_explicitly_called(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.post(f"{_base_url('ws-1', source_id)}/suggest", json={})
        assert resp.status_code == 200, resp.text
        suggested = resp.json()
        assert len(suggested) > 0
        assert all(g["status"] == "suggested" for g in suggested)
        # Now reflected in the list.
        listed = client.get(_base_url("ws-1", source_id)).json()
        assert len(listed) == len(suggested)

    def test_suggest_is_idempotent_and_additive_only(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        first = client.post(f"{_base_url('ws-1', source_id)}/suggest", json={}).json()
        second = client.post(f"{_base_url('ws-1', source_id)}/suggest", json={}).json()
        assert len(first) > 0
        assert second == []  # nothing new left to suggest


class TestSourceIsolation:
    def test_lists_are_independent_across_sources(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        _create_voltage_group(client, "ws-1", source_a, ["N275_VR", "N275_VY", "N275_VB"], "A's group")

        assert len(client.get(_base_url("ws-1", source_a)).json()) == 1
        assert client.get(_base_url("ws-1", source_b)).json() == []


class TestLifecycleCleanupStillIntact:
    def test_deleting_the_source_removes_its_groups_via_the_new_api_view(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        created = _create_voltage_group(client, "ws-1", source_id, ["N275_VR", "N275_VY", "N275_VB"])
        assert client.get(f"{_base_url('ws-1', source_id)}/{created['id']}").status_code == 200

        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204
        assert client.get(_base_url("ws-1", source_id)).status_code == 404
