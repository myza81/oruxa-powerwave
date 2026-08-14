"""Application configuration.

All environment reads happen here. The rest of the application receives a
``Settings`` instance and never touches ``os.environ`` directly, which keeps
configuration testable and makes the full set of knobs discoverable in one
place.
"""

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_CORS_ORIGINS = ("http://localhost:8101", "http://127.0.0.1:8101")

# MVP operating assumption, not a permanent technical limit -- see
# docs/project-memory/MIGRATION_PLAN.md's Phase 1 update. Deployment-specific
# values belong in configuration, not hard-coded business logic.
DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB = 100


class ConfigurationError(RuntimeError):
    """Raised when the environment does not describe a usable configuration."""


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    storage_type: str
    storage_path: str
    cors_origins: tuple[str, ...]
    database_url: str | None
    max_event_upload_size_mb: int

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_event_upload_size_bytes(self) -> int:
        return self.max_event_upload_size_mb * 1024 * 1024


def _split_origins(raw: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build ``Settings`` from a mapping, defaulting to the process environment.

    Reading configuration is deliberately separate from acting on it: this
    function performs no filesystem or network access, so importing the
    application is always side-effect free.
    """
    env = os.environ if env is None else env

    environment = env.get("ENVIRONMENT", "development").strip().lower()

    storage_type = env.get("STORAGE_TYPE", "local").strip().lower()
    if storage_type != "local":
        raise ConfigurationError(
            f"Unsupported storage backend: {storage_type!r} (expected 'local')"
        )

    storage_path = env.get("STORAGE_PATH", "").strip()
    if not storage_path:
        raise ConfigurationError(
            "STORAGE_PATH must be set to a writable directory for local storage"
        )

    raw_origins = env.get("CORS_ORIGINS", "").strip()
    cors_origins = _split_origins(raw_origins) if raw_origins else DEFAULT_CORS_ORIGINS
    if environment == "production" and not raw_origins:
        raise ConfigurationError(
            "CORS_ORIGINS must be set explicitly when ENVIRONMENT=production"
        )

    database_url = env.get("DATABASE_URL", "").strip() or None

    raw_max_upload = env.get("MAX_EVENT_UPLOAD_SIZE_MB", "").strip()
    if raw_max_upload:
        try:
            max_event_upload_size_mb = int(raw_max_upload)
        except ValueError as exc:
            raise ConfigurationError(
                f"MAX_EVENT_UPLOAD_SIZE_MB must be an integer, got {raw_max_upload!r}"
            ) from exc
        if max_event_upload_size_mb <= 0:
            raise ConfigurationError("MAX_EVENT_UPLOAD_SIZE_MB must be a positive integer")
    else:
        max_event_upload_size_mb = DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB

    return Settings(
        environment=environment,
        storage_type=storage_type,
        storage_path=storage_path,
        cors_origins=cors_origins,
        database_url=database_url,
        max_event_upload_size_mb=max_event_upload_size_mb,
    )
