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

    def test_upload_failure_leaves_nothing_in_the_registry(self, client, comtrade_fixtures_dir):
        dat = _read(comtrade_fixtures_dir / "synth_ascii.dat")

        resp = client.post("/api/v1/workspaces/ws-1/sources", files=_files(b"", dat))
        assert resp.status_code == 400

        assert client.get("/api/v1/workspaces/ws-1/sources").json() == []
