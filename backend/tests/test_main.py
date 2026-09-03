import importlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.main
from app.config import ConfigurationError
from app.main import create_app
from app.storage import LocalStorage


def test_importing_main_has_no_side_effects(monkeypatch):
    """Import must stay side-effect free.

    The previous layout read os.environ["STORAGE_PATH"] and built storage at
    module scope, so a missing variable crash-looped the container with a bare
    KeyError. Factory mode means importing the module does neither.
    """
    monkeypatch.delenv("STORAGE_PATH", raising=False)
    monkeypatch.delenv("STORAGE_TYPE", raising=False)

    importlib.reload(app.main)


def test_misconfiguration_fails_with_a_clear_error(monkeypatch):
    monkeypatch.delenv("STORAGE_PATH", raising=False)

    with pytest.raises(ConfigurationError, match="STORAGE_PATH"):
        create_app()


def test_storage_is_not_constructed_before_startup(settings, tmp_path):
    create_app(settings)

    assert list(tmp_path.iterdir()) == []


def test_health_reports_ok(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "development",
        "version": "local",
        "git_sha": "local",
    }


def test_health_reports_the_configured_build_provenance(settings):
    deployed = replace(settings, git_sha="331cca07555c09edd24f09589b59c5cae0aa200b", version="331cca0")
    with TestClient(create_app(deployed)) as client:
        response = client.get("/health")

    body = response.json()
    assert body["version"] == "331cca0"
    assert body["git_sha"] == "331cca07555c09edd24f09589b59c5cae0aa200b"


def test_storage_is_built_during_startup(settings):
    app = create_app(settings)

    assert not hasattr(app.state, "storage")

    with TestClient(app):
        assert isinstance(app.state.storage, LocalStorage)


def test_configured_origin_is_allowed(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/health", headers={"Origin": "http://localhost:8101"}
        )

    assert response.headers["access-control-allow-origin"] == "http://localhost:8101"


def test_unconfigured_origin_is_not_allowed(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/health", headers={"Origin": "https://evil.example"}
        )

    assert "access-control-allow-origin" not in response.headers


def test_content_disposition_is_exposed_for_cross_origin_downloads(settings):
    """CSV/Excel ingestion Slice 12 (DEC-072) regression: `Content-
    Disposition` is not one of the CORS-safelisted response headers a
    browser exposes to JavaScript by default -- without an explicit
    `expose_headers` on `CORSMiddleware`, the frontend's cross-origin
    `.../preparation-sources/{id}/export` download silently loses the
    real filename and falls back to a generic default (a real defect
    caught live by the Slice 12 browser UAT, invisible to a same-process
    `TestClient` call that enforces no CORS restriction at all -- see
    docs/project-memory/CSV_EXCEL_INGESTION_ARCHITECTURE.md item 12)."""
    with TestClient(create_app(settings)) as client:
        files = {"csv_file": ("event.csv", b"1,2\n", "text/csv")}
        upload = client.post(
            "/api/v1/workspaces/ws-1/preparation-sources", files=files,
            headers={"Origin": "http://localhost:8101"},
        )
        source_id = upload.json()["source_id"]
        response = client.post(
            f"/api/v1/workspaces/ws-1/preparation-sources/{source_id}/export",
            headers={"Origin": "http://localhost:8101"},
        )

    assert "Content-Disposition" in response.headers.get("access-control-expose-headers", "")
