import importlib

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
    assert response.json() == {"status": "ok", "environment": "development"}


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
