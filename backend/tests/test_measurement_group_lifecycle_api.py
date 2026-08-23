"""Integration tests proving the measurement-group registry's lifecycle
is actually wired into the real running app (Slice 1 of DEC-050) --
not just that MeasurementGroupRegistry/measurement_group_service work
correctly in isolation (see test_measurement_group_registry.py and
test_measurement_group_service.py for that), but that `DELETE
/api/v1/workspaces/{id}/sources/{id}` and `DELETE
/api/v1/workspaces/{id}` actually call through to
`app.state.measurement_group_registry`, exactly like they already do
for `app.state.per_unit_registry`/`app.state.calculated_channel_registry`.

No new API endpoint exists to CREATE a measurement group in this slice
(deliberately -- see the module docstring on
app.services.measurement_group_service), so these tests upload a real
source through the existing API, then create a measurement group
directly against the app's own live registries (exactly the shape a
Slice 2+ endpoint would eventually call), then exercise the EXISTING
delete endpoints and assert the registry reacted.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_VOLTAGE
from app.main import create_app
from app.services.measurement_group_service import create_group, list_groups_for_source, list_groups_for_workspace
from app.services.voltage_group_config_service import set_voltage_base


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = comtrade_fixtures_dir.joinpath(f"{stem}.cfg").read_bytes()
    dat = comtrade_fixtures_dir.joinpath(f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _create_empty_group(client, workspace_id, source_id, display_name="TEST GROUP"):
    """Creates a group with no channel membership directly against the
    live app's own registries -- sufficient to prove lifecycle wiring
    without depending on any particular fixture's own channel names."""
    return create_group(
        workspace_id=workspace_id, source_id=source_id, kind=KIND_VOLTAGE, display_name=display_name,
        channel_refs=[], registry=client.app.state.measurement_group_registry,
        source_registry=client.app.state.workspace_registry,
    )


class TestSourceRemovalLifecycle:
    def test_deleting_a_source_removes_its_own_measurement_groups(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = _create_empty_group(client, "ws-1", source_id)
        assert list_groups_for_source("ws-1", source_id, registry=client.app.state.measurement_group_registry) != []

        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204

        assert list_groups_for_source("ws-1", source_id, registry=client.app.state.measurement_group_registry) == []
        assert client.app.state.measurement_group_registry.get("ws-1", group.id) is None

    def test_deleting_a_source_with_no_groups_is_a_safe_no_op(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204

    def test_deleting_one_source_never_touches_another_sources_groups(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        group_a = _create_empty_group(client, "ws-1", source_a, "A")
        group_b = _create_empty_group(client, "ws-1", source_b, "B")

        client.delete(f"/api/v1/workspaces/ws-1/sources/{source_a}")

        assert client.app.state.measurement_group_registry.get("ws-1", group_a.id) is None
        assert client.app.state.measurement_group_registry.get("ws-1", group_b.id) is not None


class TestWorkspaceRemovalLifecycle:
    def test_deleting_a_workspace_removes_all_its_measurement_groups(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = _create_empty_group(client, "ws-1", source_id)
        assert list_groups_for_workspace("ws-1", registry=client.app.state.measurement_group_registry) != []

        resp = client.delete("/api/v1/workspaces/ws-1")
        assert resp.status_code == 204

        assert list_groups_for_workspace("ws-1", registry=client.app.state.measurement_group_registry) == []
        assert client.app.state.measurement_group_registry.get("ws-1", group.id) is None

    def test_deleting_a_workspace_never_touches_a_different_workspace(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-a", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-b", comtrade_fixtures_dir)
        group_a = _create_empty_group(client, "ws-a", source_a, "A")
        group_b = _create_empty_group(client, "ws-b", source_b, "B")

        client.delete("/api/v1/workspaces/ws-a")

        assert client.app.state.measurement_group_registry.get("ws-a", group_a.id) is None
        assert client.app.state.measurement_group_registry.get("ws-b", group_b.id) is not None

    def test_deleting_an_empty_or_unknown_workspace_is_idempotent(self, client):
        resp = client.delete("/api/v1/workspaces/does-not-exist")
        assert resp.status_code == 204


class TestRegistryIsWiredIntoAppState:
    def test_measurement_group_registry_exists_on_app_state(self, client):
        # A direct check that Slice 1's fourth sibling registry is
        # actually constructed during the app's lifespan, exactly like
        # the other three -- catches a "forgot to wire it into
        # create_app" regression that no endpoint-behavior test alone
        # would surface if no group happened to be created during the
        # test.
        assert client.app.state.measurement_group_registry is not None
        assert client.app.state.measurement_group_registry.count() == 0

    def test_voltage_group_config_registry_exists_on_app_state(self, client):
        # Slice 3's fifth sibling registry, same reasoning as above.
        assert client.app.state.voltage_group_config_registry is not None
        assert client.app.state.voltage_group_config_registry.count() == 0


class TestVoltageGroupConfigLifecycle:
    """Slice 3: proves DELETE .../sources/{id} and DELETE
    /workspaces/{id} actually call through to
    `app.state.voltage_group_config_registry` too, the same lifecycle
    guarantee every other workspace-owned resource already has."""

    def _create_voltage_group_with_base(self, client, workspace_id, source_id, display_name="TEST GROUP"):
        group = _create_empty_group(client, workspace_id, source_id, display_name)
        set_voltage_base(
            workspace_id=workspace_id, measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry,
        )
        return group

    def test_deleting_a_source_removes_its_groups_own_voltage_configuration(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = self._create_voltage_group_with_base(client, "ws-1", source_id)
        assert client.app.state.voltage_group_config_registry.get("ws-1", group.id) is not None

        resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert resp.status_code == 204

        assert client.app.state.voltage_group_config_registry.get("ws-1", group.id) is None

    def test_deleting_one_source_never_touches_another_sources_voltage_configuration(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-1", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-1", comtrade_fixtures_dir)
        group_a = self._create_voltage_group_with_base(client, "ws-1", source_a, "A")
        group_b = self._create_voltage_group_with_base(client, "ws-1", source_b, "B")

        client.delete(f"/api/v1/workspaces/ws-1/sources/{source_a}")

        assert client.app.state.voltage_group_config_registry.get("ws-1", group_a.id) is None
        assert client.app.state.voltage_group_config_registry.get("ws-1", group_b.id) is not None

    def test_deleting_a_workspace_removes_all_its_voltage_group_configurations(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = self._create_voltage_group_with_base(client, "ws-1", source_id)
        assert client.app.state.voltage_group_config_registry.count() == 1

        resp = client.delete("/api/v1/workspaces/ws-1")
        assert resp.status_code == 204

        assert client.app.state.voltage_group_config_registry.get("ws-1", group.id) is None

    def test_deleting_a_workspace_never_touches_a_different_workspaces_voltage_configuration(self, client, comtrade_fixtures_dir):
        source_a = _upload(client, "ws-a", comtrade_fixtures_dir)
        source_b = _upload(client, "ws-b", comtrade_fixtures_dir)
        group_a = self._create_voltage_group_with_base(client, "ws-a", source_a, "A")
        group_b = self._create_voltage_group_with_base(client, "ws-b", source_b, "B")

        client.delete("/api/v1/workspaces/ws-a")

        assert client.app.state.voltage_group_config_registry.get("ws-a", group_a.id) is None
        assert client.app.state.voltage_group_config_registry.get("ws-b", group_b.id) is not None
