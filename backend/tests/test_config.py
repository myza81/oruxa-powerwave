import pytest

from app.config import DEFAULT_CORS_ORIGINS, ConfigurationError, load_settings

BASE_ENV = {"STORAGE_PATH": "/data"}


def test_defaults_are_development():
    settings = load_settings(BASE_ENV)

    assert settings.environment == "development"
    assert settings.storage_type == "local"
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.database_url is None
    assert not settings.is_production


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
