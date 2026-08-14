import pytest

from app.config import (
    DEFAULT_CORS_ORIGINS,
    DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB,
    ConfigurationError,
    load_settings,
)

BASE_ENV = {"STORAGE_PATH": "/data"}


def test_defaults_are_development():
    settings = load_settings(BASE_ENV)

    assert settings.environment == "development"
    assert settings.storage_type == "local"
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.database_url is None
    assert not settings.is_production
    assert settings.max_event_upload_size_mb == DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB


def test_settings_are_frozen():
    settings = load_settings(BASE_ENV)

    with pytest.raises(Exception):
        settings.environment = "production"


def test_missing_storage_path_is_rejected():
    with pytest.raises(ConfigurationError, match="STORAGE_PATH"):
        load_settings({})


def test_blank_storage_path_is_rejected():
    with pytest.raises(ConfigurationError, match="STORAGE_PATH"):
        load_settings({"STORAGE_PATH": "   "})


def test_unsupported_storage_backend_is_rejected():
    with pytest.raises(ConfigurationError, match="Unsupported storage backend"):
        load_settings({**BASE_ENV, "STORAGE_TYPE": "s3"})


def test_cors_origins_are_parsed_and_trimmed():
    settings = load_settings(
        {**BASE_ENV, "CORS_ORIGINS": "https://a.example , https://b.example,"}
    )

    assert settings.cors_origins == ("https://a.example", "https://b.example")


def test_production_requires_explicit_cors_origins():
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        load_settings({**BASE_ENV, "ENVIRONMENT": "production"})


def test_production_with_explicit_origins_is_accepted():
    settings = load_settings(
        {
            **BASE_ENV,
            "ENVIRONMENT": "production",
            "CORS_ORIGINS": "https://powerwave.oruxa.uk",
        }
    )

    assert settings.is_production
    assert settings.cors_origins == ("https://powerwave.oruxa.uk",)


def test_environment_is_normalised():
    settings = load_settings({**BASE_ENV, "ENVIRONMENT": "  PRODUCTION  ",
                              "CORS_ORIGINS": "https://powerwave.oruxa.uk"})

    assert settings.environment == "production"


def test_max_event_upload_size_mb_is_configurable():
    settings = load_settings({**BASE_ENV, "MAX_EVENT_UPLOAD_SIZE_MB": "250"})

    assert settings.max_event_upload_size_mb == 250
    assert settings.max_event_upload_size_bytes == 250 * 1024 * 1024


def test_max_event_upload_size_mb_rejects_non_integer():
    with pytest.raises(ConfigurationError, match="MAX_EVENT_UPLOAD_SIZE_MB"):
        load_settings({**BASE_ENV, "MAX_EVENT_UPLOAD_SIZE_MB": "not-a-number"})


def test_max_event_upload_size_mb_rejects_non_positive():
    with pytest.raises(ConfigurationError, match="MAX_EVENT_UPLOAD_SIZE_MB"):
        load_settings({**BASE_ENV, "MAX_EVENT_UPLOAD_SIZE_MB": "0"})
