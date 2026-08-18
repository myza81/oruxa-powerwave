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
    # Phase 4A-UAT3: no APP_VERSION set -- truthful "local" fallback, never
    # a fabricated commit hash.
    assert settings.git_sha == "local"
    assert settings.version == "local"


class TestBuildProvenance:
    """Phase 4A-UAT3: APP_VERSION -> Settings.git_sha/.version.

    Sourced ONLY from the APP_VERSION environment variable -- never by
    running `git` or inspecting the filesystem (see load_settings()'s own
    comment).
    """

    def test_full_sha_is_recorded_verbatim(self):
        full_sha = "331cca07555c09edd24f09589b59c5cae0aa200b"
        settings = load_settings({**BASE_ENV, "APP_VERSION": full_sha})

        assert settings.git_sha == full_sha

    def test_version_is_the_short_seven_character_form(self):
        full_sha = "331cca07555c09edd24f09589b59c5cae0aa200b"
        settings = load_settings({**BASE_ENV, "APP_VERSION": full_sha})

        assert settings.version == "331cca0"

    def test_blank_app_version_falls_back_to_local(self):
        settings = load_settings({**BASE_ENV, "APP_VERSION": "   "})

        assert settings.git_sha == "local"
        assert settings.version == "local"

    def test_unset_app_version_falls_back_to_local_in_production_too(self):
        settings = load_settings(
            {**BASE_ENV, "ENVIRONMENT": "production", "CORS_ORIGINS": "https://powerwave.oruxa.uk"}
        )

        assert settings.git_sha == "local"
        assert settings.version == "local"

    def test_app_version_is_stripped_of_surrounding_whitespace(self):
        settings = load_settings({**BASE_ENV, "APP_VERSION": "  abc1234  "})

        assert settings.git_sha == "abc1234"


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
