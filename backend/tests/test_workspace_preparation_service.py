"""Unit-level tests for DEC-104's ONE authoritative shared post-upload
choke point, `app.services.workspace_preparation_service.
prepare_workspace_source()`. See test_measurement_group_api.py's/
test_engineering_context_api.py's own `_upload()` helpers for the API-
level proof that a real upload now triggers this automatically; this
file instead exercises the function directly against the two registries
it orchestrates, focusing on exactly what those API-level tests cannot
easily prove: failure isolation between the two discovery calls, and
that a raised exception never propagates out of this function.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import workspace_preparation_service
from app.services.workspace_preparation_service import prepare_workspace_source


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload_without_triggering_prepare(client, workspace_id, comtrade_fixtures_dir, stem, monkeypatch):
    """Uploads via the real HTTP endpoint (the only way to get a fully
    valid `ActiveSource` into the registry) while neutralizing THIS
    module's own two discovery calls, so each test below can invoke
    `prepare_workspace_source()` itself, directly, under controlled
    conditions -- rather than observing whatever the endpoint's own
    already-tested call already did."""
    monkeypatch.setattr(workspace_preparation_service, "generate_suggested_groups_for_source", lambda **_: [])
    monkeypatch.setattr(workspace_preparation_service, "generate_suggested_contexts_for_source", lambda **_: [])
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _registries(client):
    app = client.app
    return {
        "source_registry": app.state.workspace_registry,
        "group_registry": app.state.measurement_group_registry,
        "context_registry": app.state.engineering_context_registry,
        "calculated_channel_registry": app.state.calculated_channel_registry,
    }


class TestNormalOperation:
    def test_a_multi_bay_source_produces_both_groups_and_contexts_in_one_call(self, client, comtrade_fixtures_dir, monkeypatch):
        source_id = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.undo()  # restore the real detection functions for this call
        result = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **_registries(client))
        assert result.measurement_groups_created > 0
        assert result.measurement_groups_error is None
        assert result.engineering_contexts_created > 0
        assert result.engineering_contexts_error is None

    def test_calling_it_twice_for_the_same_source_is_idempotent_and_creates_nothing_new_the_second_time(
        self, client, comtrade_fixtures_dir, monkeypatch
    ):
        source_id = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.undo()
        registries = _registries(client)
        first = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **registries)
        assert first.measurement_groups_created > 0
        assert first.engineering_contexts_created > 0

        second = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **registries)
        assert second.measurement_groups_created == 0
        assert second.measurement_groups_error is None
        assert second.engineering_contexts_created == 0
        assert second.engineering_contexts_error is None

    def test_two_different_sources_in_the_same_workspace_are_each_prepared_independently(
        self, client, comtrade_fixtures_dir, monkeypatch
    ):
        source_a = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        source_b = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.undo()
        registries = _registries(client)
        result_a = prepare_workspace_source(workspace_id="ws-1", source_id=source_a, **registries)
        result_b = prepare_workspace_source(workspace_id="ws-1", source_id=source_b, **registries)
        assert result_a.measurement_groups_created > 0
        assert result_b.measurement_groups_created > 0

        groups_a = [g for g in registries["group_registry"].list_for_source("ws-1", source_a)]
        groups_b = [g for g in registries["group_registry"].list_for_source("ws-1", source_b)]
        assert {g.id for g in groups_a}.isdisjoint({g.id for g in groups_b})
        assert len(groups_a) == len(groups_b)  # same fixture uploaded twice -> same bay count each


class TestFailureIsolation:
    """DEC-104's own docstring: 'Never turns discovery uncertainty, or a
    discovery failure, into an upload failure' -- these tests exercise
    that guarantee directly, at the function level, rather than relying
    on an HTTP 201 alone (which could still be true even if this
    function secretly swallowed a KeyboardInterrupt-shaped bug; asserting
    the returned *_error field is the stronger check)."""

    def test_measurement_group_discovery_failure_never_raises_and_engineering_context_discovery_still_runs(
        self, client, comtrade_fixtures_dir, monkeypatch
    ):
        source_id = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.undo()  # restore the real functions before selectively re-breaking one
        monkeypatch.setattr(
            workspace_preparation_service,
            "generate_suggested_groups_for_source",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        registries = _registries(client)
        result = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **registries)
        assert result.measurement_groups_created == 0
        assert result.measurement_groups_error == "measurement_group_discovery_failed"
        # The OTHER discovery call must be unaffected by the first one's failure.
        assert result.engineering_contexts_created > 0
        assert result.engineering_contexts_error is None

    def test_engineering_context_discovery_failure_never_raises_and_measurement_group_discovery_still_ran(
        self, client, comtrade_fixtures_dir, monkeypatch
    ):
        source_id = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.undo()  # restore the real functions before selectively re-breaking one
        monkeypatch.setattr(
            workspace_preparation_service,
            "generate_suggested_contexts_for_source",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        registries = _registries(client)
        result = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **registries)
        assert result.measurement_groups_created > 0
        assert result.measurement_groups_error is None
        assert result.engineering_contexts_created == 0
        assert result.engineering_contexts_error == "engineering_context_discovery_failed"

    def test_both_discovery_calls_failing_still_never_raises(self, client, comtrade_fixtures_dir, monkeypatch):
        source_id = _upload_without_triggering_prepare(
            client, "ws-1", comtrade_fixtures_dir, "synth_measurement_groups", monkeypatch
        )
        monkeypatch.setattr(
            workspace_preparation_service,
            "generate_suggested_groups_for_source",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(
            workspace_preparation_service,
            "generate_suggested_contexts_for_source",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        registries = _registries(client)
        result = prepare_workspace_source(workspace_id="ws-1", source_id=source_id, **registries)  # must not raise
        assert result.measurement_groups_error == "measurement_group_discovery_failed"
        assert result.engineering_contexts_error == "engineering_context_discovery_failed"


class TestUploadEndpointNeverFailsOnDiscoveryFailure:
    """API-level proof of the same guarantee: a discovery exception
    raised from INSIDE the upload endpoint's own call to
    `prepare_workspace_source()` must never turn a successful upload
    into an HTTP error."""

    def test_upload_still_returns_201_even_if_measurement_group_discovery_raises(
        self, client, comtrade_fixtures_dir, monkeypatch
    ):
        monkeypatch.setattr(
            workspace_preparation_service,
            "generate_suggested_groups_for_source",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        cfg = (comtrade_fixtures_dir / "synth_measurement_groups.cfg").read_bytes()
        dat = (comtrade_fixtures_dir / "synth_measurement_groups.dat").read_bytes()
        files = {
            "cfg_file": ("x.cfg", io.BytesIO(cfg), "application/octet-stream"),
            "dat_file": ("x.dat", io.BytesIO(dat), "application/octet-stream"),
        }
        resp = client.post("/api/v1/workspaces/ws-1/sources", files=files)
        assert resp.status_code == 201, resp.text
        # Engineering Context discovery (unaffected) still ran normally.
        contexts = client.get("/api/v1/workspaces/ws-1/engineering-contexts").json()
        assert len(contexts) > 0
