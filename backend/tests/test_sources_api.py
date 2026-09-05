"""API-level tests for the Phase 1 COMTRADE source/channel endpoints.

Covers the "Upload tests", "Lifecycle tests", and "API tests" categories
from docs/project-memory/MIGRATION_PLAN.md's testing strategy, all through
one FastAPI TestClient against a fully wired app (real Settings, real
in-memory WorkspaceRegistry via the app's own lifespan) -- no mocking of
the import path.
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


class TestUpload:
    @pytest.mark.parametrize("stem", ["synth_ascii", "synth_binary"])
    def test_valid_upload_returns_201_with_source_summary(self, client, comtrade_fixtures_dir, stem):
        cfg = _read(comtrade_fixtures_dir / f"{stem}.cfg")
        dat = _read(comtrade_fixtures_dir / f"{stem}.dat")

        resp = client.post(
            "/api/v1/workspaces/ws-1/sources",
            files=_files(cfg, dat, f"{stem}.cfg", f"{stem}.dat"),
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["workspace_id"] == "ws-1"
        assert body["provider_type"] == "COMTRADE"
        assert body["station_name"] == "SYNTH_STATION"
        assert body["analog_channel_count"] == 3
        assert body["digital_channel_count"] == 2
        assert body["status"] == "ready"
        # Slice 1 (CSV/Excel ingestion, DEC-072): file_size_bytes is a
        # new, additive field on SourceSummaryOut (the Recording Events
        # table's File Size column, computed the same way for every
        # format) -- for COMTRADE it must equal the combined cfg+dat
        # byte size actually uploaded, never a guess or a partial count.
        assert body["file_size_bytes"] == len(cfg) + len(dat)
        # Phase 3B: duration_seconds/sample_count are new, additive fields
        # on SourceSummaryOut (the Recordings page's list Duration column) --
        # cross-checked against the pre-existing timebase.* fields on the
        # channels endpoint, the values these two new fields are computed
        # from, rather than a hardcoded magic number.
        channels_body = client.get(
            f"/api/v1/workspaces/ws-1/sources/{body['source_id']}/channels"
        ).json()
        assert body["sample_count"] == channels_body["timebase"]["sample_count"]
        assert body["duration_seconds"] == pytest.approx(channels_body["timebase"]["duration_seconds"])
        # No waveform data anywhere in the response.
        assert "waveform_data" not in body
        assert "VA" not in body

    def test_missing_dat_field_is_a_validation_error(self, client, comtrade_fixtures_dir):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")

        resp = client.post(
            "/api/v1/workspaces/ws-1/sources",
            files={"cfg_file": ("event.cfg", io.BytesIO(cfg), "application/octet-stream")},
        )

        assert resp.status_code == 422

    def test_wrong_extension_for_cfg_field_is_rejected(self, client, comtrade_fixtures_dir):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post(
            "/api/v1/workspaces/ws-1/sources",
            files=_files(cfg, dat, cfg_name="event.txt"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unsupported_file_type"

    def test_wrong_extension_for_dat_field_is_rejected(self, client, comtrade_fixtures_dir):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post(
            "/api/v1/workspaces/ws-1/sources",
            files=_files(cfg, dat, dat_name="event.bin"),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unsupported_file_type"

    def test_mismatched_pair_is_a_parse_error(self, client, comtrade_fixtures_dir):
        # ASCII-format CFG paired with a binary-format DAT: the ASCII parser
        # will fail to interpret the binary bytes as CSV text.
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_binary.dat")

        resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat))

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "parse_error"

    def test_malformed_cfg_is_rejected(self, client, comtrade_fixtures_dir):
        cfg = b"not,a,valid,comtrade,cfg\nfile at all\n"
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat))

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] in {"parse_error", "invalid_file"}

    def test_empty_cfg_is_rejected(self, client, comtrade_fixtures_dir):
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(b"", dat))

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_file"

    def test_oversized_upload_is_rejected_without_parsing(self, comtrade_fixtures_dir, tmp_path):
        from app.config import Settings

        tiny_limit_settings = Settings(
            environment="development",
            storage_type="local",
            storage_path=str(tmp_path),
            cors_origins=("http://localhost:8101",),
            database_url=None,
            max_event_upload_size_mb=1,  # 1 MB combined ceiling
            git_sha="local",
            version="local",
        )
        app = create_app(tiny_limit_settings)
        with TestClient(app) as client:
            cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
            # Larger than 1 MB on its own.
            oversized_dat = b"9" * (2 * 1024 * 1024)

            resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(cfg, oversized_dat))

        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "upload_too_large"

    def test_unsupported_comtrade_variant_is_rejected(self, client, comtrade_fixtures_dir, tmp_path):
        cfg_text = (comtrade_fixtures_dir / "synth_ascii.cfg").read_text(encoding="latin-1")
        cfg_text = cfg_text.replace("ASCII", "BINARY32")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post(
            "/api/v1/workspaces/ws-1/sources",
            files=_files(cfg_text.encode("latin-1"), dat),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "unsupported_comtrade_variant"


class TestReadEndpoints:
    def test_get_channels_returns_full_channel_list_without_waveform_arrays(
        self, client, comtrade_fixtures_dir
    ):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]

        resp = client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels")

        assert resp.status_code == 200
        body = resp.json()
        assert [c["name"] for c in body["analog_channels"]] == ["VA", "VB", "IA"]
        assert [c["name"] for c in body["digital_channels"]] == ["BRK_A", "BRK_B"]
        assert body["timebase"]["sample_count"] == 40
        assert body["timebase"]["sampling_rates"] == [4000.0]
        # Response is metadata only.
        response_text = resp.text
        assert "waveform_data" not in response_text

    def test_analog_channels_carry_a_backend_computed_engineering_type(
        self, client, comtrade_fixtures_dir
    ):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]

        body = client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels").json()

        types_by_name = {c["name"]: c["engineering_type"] for c in body["analog_channels"]}
        # synth_ascii.cfg: VA/VB are unit "V" (Voltage), IA is unit "A" (Current) --
        # see tests/fixtures/comtrade/synth_ascii.cfg.
        assert types_by_name == {"VA": "Voltage", "VB": "Voltage", "IA": "Current"}

    def test_engineering_quantity_enhancement_leaves_comtrade_completely_unaffected(
        self, client, comtrade_fixtures_dir
    ):
        # DEC-077, task section X: COMTRADE is never touched to populate
        # the richer field -- its channels' own AnalogChannel.
        # parameter_type stays None, so canonical_engineering_quantity(None)
        # resolves "Undefined" by construction, with zero lines changed in
        # app.services.import_service/app.providers.comtrade. The broad
        # `engineering_type` above is completely unaffected (still
        # Voltage/Voltage/Current, asserted above).
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]

        body = client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels").json()

        quantities = {c["engineering_quantity"] for c in body["analog_channels"]}
        assert quantities == {"Undefined"}

    def test_get_unknown_source_is_404(self, client):
        resp = client.get("/api/v1/workspaces/ws-1/sources/does-not-exist/channels")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

    def test_list_only_returns_sources_in_that_workspace(self, client, comtrade_fixtures_dir):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        client.post("/api/v1/workspaces/ws-a/sources", files=_files(cfg, dat))
        client.post("/api/v1/workspaces/ws-b/sources", files=_files(cfg, dat))

        resp_a = client.get("/api/v1/workspaces/ws-a/sources")
        resp_b = client.get("/api/v1/workspaces/ws-b/sources")

        assert len(resp_a.json()) == 1
        assert len(resp_b.json()) == 1
        assert resp_a.json()[0]["source_id"] != resp_b.json()[0]["source_id"]

    def test_list_includes_duration_and_sample_count(self, client, comtrade_fixtures_dir):
        # Phase 3B: the Recordings page's list table reads duration/sample
        # count straight from GET .../sources (no per-row .../channels
        # fetch) -- confirm the LIST endpoint specifically carries them,
        # not just the upload/get-one response.
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-list-duration/sources", files=_files(cfg, dat)
        ).json()["source_id"]
        channels_body = client.get(
            f"/api/v1/workspaces/ws-list-duration/sources/{source_id}/channels"
        ).json()

        resp = client.get("/api/v1/workspaces/ws-list-duration/sources")

        assert resp.status_code == 200
        [row] = resp.json()
        assert row["sample_count"] == channels_body["timebase"]["sample_count"]
        assert row["duration_seconds"] == pytest.approx(channels_body["timebase"]["duration_seconds"])
        assert row["elapsed_start_seconds"] == pytest.approx(
            channels_body["timebase"]["elapsed_start_seconds"]
        )
        assert row["elapsed_end_seconds"] == pytest.approx(
            channels_body["timebase"]["elapsed_end_seconds"]
        )
        assert row["elapsed_start_seconds"] == pytest.approx(0.0)
        assert row["elapsed_end_seconds"] == pytest.approx(0.00975)

    def test_list_includes_timing_reference_and_timestamps(self, client, comtrade_fixtures_dir):
        # Phase 3B-UAT5: the Recordings page's per-recording "Details"
        # panel reads timing_reference/start_time/trigger_time/
        # sampling_rates straight from GET .../sources too -- confirm the
        # LIST endpoint specifically carries them, matching the
        # .../channels endpoint's own timebase.* values exactly (same
        # underlying SourceMetadata fields, never a second computation).
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-list-timing/sources", files=_files(cfg, dat)
        ).json()["source_id"]
        channels_body = client.get(
            f"/api/v1/workspaces/ws-list-timing/sources/{source_id}/channels"
        ).json()

        resp = client.get("/api/v1/workspaces/ws-list-timing/sources")

        assert resp.status_code == 200
        [row] = resp.json()
        assert row["timing_reference"] == channels_body["timebase"]["timing_reference"]
        assert row["start_time"] == channels_body["timebase"]["start_time"]
        assert row["trigger_time"] == channels_body["timebase"]["trigger_time"]
        assert row["sampling_rates"] == channels_body["timebase"]["sampling_rates"]


class TestListIncludesTimeOfDayReferenceSeconds:
    """Recording Events metadata display fix: `time_of_day_reference_
    seconds` already existed on `TimebaseOut` (the single-source
    `.../channels` response, Time of Day presentation-layer task) but was
    NOT on `SourceSummaryOut` (the `.../sources` LIST response Recording
    Events actually renders from) -- so a Time of Day source's known
    clock-time origin was invisible to that page even though `start_time`
    is correctly `None` for it (non-absolute family, no fabricated date).
    Confirms the newly-added field is threaded onto the list endpoint too,
    matching the `.../channels` endpoint's own value exactly (same
    underlying `SourceMetadata` field, never a second computation) -- and
    that a plain elapsed/sample-only source still reports `None`."""

    def test_time_of_day_source_reports_reference_seconds_on_list(self, client):
        source_id = client.post(
            "/api/v1/workspaces/ws-tod-list/preparation-sources",
            files={"csv_file": ("e.csv", io.BytesIO(b"13:14:01,1.0\n13:14:02,2.0\n"), "text/csv")},
        ).json()["source_id"]
        client.put(f"/api/v1/workspaces/ws-tod-list/preparation-sources/{source_id}/working/columns/0/role", json={"role": "time_axis"})
        client.put(f"/api/v1/workspaces/ws-tod-list/preparation-sources/{source_id}/working/columns/1/role", json={"role": "waveform"})
        client.put(
            f"/api/v1/workspaces/ws-tod-list/preparation-sources/{source_id}/working/time-axis",
            json={"column_indices": [0], "interpreter_id": "time_of_day", "confirmed": True},
        )
        converted = client.post(f"/api/v1/workspaces/ws-tod-list/preparation-sources/{source_id}/convert").json()

        channels_body = client.get(
            f"/api/v1/workspaces/ws-tod-list/sources/{converted['source_id']}/channels"
        ).json()
        [row] = client.get("/api/v1/workspaces/ws-tod-list/sources").json()

        assert row["timing_reference"] == "time_of_day"
        assert row["start_time"] is None
        assert row["time_of_day_reference_seconds"] == pytest.approx(13 * 3600 + 14 * 60 + 1)
        assert row["time_of_day_reference_seconds"] == channels_body["timebase"]["time_of_day_reference_seconds"]

    def test_absolute_source_reports_none(self, client, comtrade_fixtures_dir):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        client.post("/api/v1/workspaces/ws-tod-none/sources", files=_files(cfg, dat))

        [row] = client.get("/api/v1/workspaces/ws-tod-none/sources").json()

        assert row["time_of_day_reference_seconds"] is None


class TestLifecycle:
    def test_delete_releases_ownership_and_prevents_later_access(
        self, client, comtrade_fixtures_dir
    ):
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]

        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id}")
        assert delete_resp.status_code == 204

        assert client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}").status_code == 404
        assert (
            client.get(f"/api/v1/workspaces/ws-1/sources/{source_id}/channels").status_code
            == 404
        )
        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []

    def test_delete_unknown_source_is_404(self, client):
        resp = client.delete("/api/v1/workspaces/ws-1/sources/does-not-exist")

        assert resp.status_code == 404

    def test_delete_one_source_leaves_other_sources_in_the_same_workspace_intact(
        self, client, comtrade_fixtures_dir
    ):
        # Regression guard for the new whole-workspace DELETE endpoint
        # (app/api/v1/workspaces.py, DEC-018): single-source "Remove" must
        # keep behaving as a narrowly-scoped operation, not accidentally
        # widen to affect siblings in the same workspace.
        cfg = _read(comtrade_fixtures_dir / "synth_ascii.cfg")
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")
        source_id_1 = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]
        source_id_2 = client.post(
            "/api/v1/workspaces/ws-1/sources", files=_files(cfg, dat)
        ).json()["source_id"]

        delete_resp = client.delete(f"/api/v1/workspaces/ws-1/sources/{source_id_1}")

        assert delete_resp.status_code == 204
        assert client.get(f"/api/v1/workspaces/ws-1/sources/{source_id_1}").status_code == 404
        assert client.get(f"/api/v1/workspaces/ws-1/sources/{source_id_2}").status_code == 200
        remaining_ids = {s["source_id"] for s in client.get("/api/v1/workspaces/ws-1/sources").json()}
        assert remaining_ids == {source_id_2}

    def test_upload_failure_leaves_nothing_in_the_registry(self, client, comtrade_fixtures_dir):
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(b"", dat))
        assert resp.status_code == 400

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []
