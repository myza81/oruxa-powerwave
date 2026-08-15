"""API-level tests for GET .../sources/{source_id}/waveform (Phase 2A).

Exercises the real end-to-end flow (upload -> parse -> retain -> waveform
request) through a fully wired FastAPI TestClient, same pattern as
tests/test_sources_api.py. Also covers the lifecycle-cleanup regression
this phase specifically introduces risk for: Remove and whole-workspace
DELETE must release the retained waveform data, not just the metadata.
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


def _files(cfg_bytes: bytes, dat_bytes: bytes, cfg_name="event.cfg", dat_name="event.dat"):
    return {
        "cfg_file": (cfg_name, io.BytesIO(cfg_bytes), "application/octet-stream"),
        "dat_file": (dat_name, io.BytesIO(dat_bytes), "application/octet-stream"),
    }


def _read(path) -> bytes:
    return path.read_bytes()


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_ascii"):
    cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
    dat = _read(comtrade_fixtures_dir / f"{stem}.dat")
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=_files(cfg, dat))
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


class TestValidRequests:
    def test_valid_analog_channel_returns_waveform_response(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["channel_name"] == "VA"
        assert body["unit"] == "V"
        assert body["representation"] == "full_resolution"
        assert body["original_sample_count"] == 40
        assert body["returned_point_count"] == 40
        assert len(body["time"]) == 40
        assert len(body["values"]) == 40

    def test_values_and_times_match_the_parsed_provider_output_exactly(
        self, client, comtrade_fixtures_dir
    ):
        # Direct comparison against the provider's own output for the same
        # fixture -- not just status codes/lengths (per the task's explicit
        # "do not test only lengths and status codes" instruction).
        from pathlib import Path

        from app.providers.comtrade import ComtradeProvider

        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        expected_record = ComtradeProvider().load(Path(comtrade_fixtures_dir / "synth_ascii.cfg"))
        expected_time = expected_record.waveform_data["time"].tolist()
        expected_va = expected_record.waveform_data["VA"].tolist()

        body = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA"},
        ).json()

        assert body["time"] == pytest.approx(expected_time)
        assert body["values"] == pytest.approx(expected_va)

    def test_first_and_last_channel_by_name_all_resolvable(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        for channel_name in ("VA", "VB", "IA"):
            resp = client.get(
                f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
                params={"channel_name": channel_name},
            )
            assert resp.status_code == 200, (channel_name, resp.text)
            assert resp.json()["channel_name"] == channel_name


class TestErrorCases:
    def test_unknown_workspace_has_no_source_returns_404(self, client):
        resp = client.get(
            "/api/v1/workspaces/never-used/sources/does-not-exist/waveform",
            params={"channel_name": "VA"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_unknown_source_returns_404(self, client, comtrade_fixtures_dir):
        _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            "/api/v1/workspaces/ws-1/sources/does-not-exist/waveform",
            params={"channel_name": "VA"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_unknown_channel_returns_404_channel_not_found(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "NOT_A_REAL_CHANNEL"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "channel_not_found"

    def test_digital_channel_name_rejected_as_channel_not_analog(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "BRK_A"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "channel_not_analog"

    def test_invalid_time_range_start_after_end_returns_400(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "start_time": 0.5, "end_time": 0.1},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_time_range"

    def test_range_before_record_is_defined_empty_behavior_not_an_error(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "start_time": -10.0, "end_time": -5.0},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["original_sample_count"] == 0
        assert body["time"] == []
        assert body["values"] == []

    def test_range_after_record_is_defined_empty_behavior_not_an_error(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "start_time": 100.0, "end_time": 200.0},
        )

        assert resp.status_code == 200
        assert resp.json()["original_sample_count"] == 0

    def test_missing_channel_name_is_a_validation_error(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform")

        assert resp.status_code == 422

    def test_non_positive_point_budget_is_a_validation_error(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "point_budget": 0},
        )

        assert resp.status_code == 422


class TestPointBudgetBoundary:
    def test_point_budget_covering_the_whole_fixture_returns_full_resolution(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "point_budget": 40},
        )

        assert resp.json()["representation"] == "full_resolution"

    def test_point_budget_below_the_fixture_size_returns_display_representation(
        self, client, comtrade_fixtures_dir
    ):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)

        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA", "point_budget": 10},
        )

        body = resp.json()
        assert body["representation"] == "min_max_envelope"
        assert body["returned_point_count"] < body["original_sample_count"]


class TestLifecycleCleanupReleasesWaveformData:
    """Phase 2A's central risk (task §25/§26): this phase changes memory
    ownership from metadata-only to metadata+full-resolution-record, so
    Remove/whole-workspace-DELETE must be proven to release the waveform
    reference too, not just make metadata disappear.
    """

    def test_remove_source_makes_its_waveform_unavailable(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        assert (
            client.get(
                f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
                params={"channel_name": "VA"},
            ).status_code
            == 200
        )

        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert delete_resp.status_code == 204

        after_resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/waveform",
            params={"channel_name": "VA"},
        )
        assert after_resp.status_code == 404
        assert after_resp.json()["detail"]["code"] == "source_not_found"

    def test_whole_workspace_delete_releases_every_sources_waveform_data(
        self, client, comtrade_fixtures_dir
    ):
        source_ids = [_upload(client, "ws-multi", comtrade_fixtures_dir) for _ in range(3)]
        for source_id in source_ids:
            assert (
                client.get(
                    f"/api/v1/workspaces/ws-multi/sources/{source_id}/waveform",
                    params={"channel_name": "VA"},
                ).status_code
                == 200
            )

        delete_resp = client.delete("/api/v1/workspaces/ws-multi")
        assert delete_resp.status_code == 204

        for source_id in source_ids:
            resp = client.get(
                f"/api/v1/workspaces/ws-multi/sources/{source_id}/waveform",
                params={"channel_name": "VA"},
            )
            assert resp.status_code == 404

    def test_reference_count_drops_after_source_removal(self, client, comtrade_fixtures_dir):
        """Not just "inaccessible via the API" -- the actual authoritative
        waveform_data DataFrame must lose its reference from the registry
        (garbage-collection eligibility), matching the rigor already
        applied to Phase 1's WorkspaceRegistry.remove_workspace() tests.

        Weak-references the DataFrame itself (not the DisturbanceRecord,
        which is a slots dataclass and doesn't support weakrefs) -- it's
        the actual large array-backed object whose release is the point
        of this test.
        """
        import gc
        import weakref

        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        app = client.app
        active = app.state.workspace_registry.get("ws-1", source_id)
        waveform_data_ref = weakref.ref(active.record.waveform_data)
        del active

        client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        gc.collect()

        assert waveform_data_ref() is None, (
            "the authoritative waveform_data DataFrame is still referenced "
            "somewhere after source removal"
        )
