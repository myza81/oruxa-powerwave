"""Application configuration.

All environment reads happen here. The rest of the application receives a
``Settings`` instance and never touches ``os.environ`` directly, which keeps
configuration testable and makes the full set of knobs discoverable in one
place.
"""

import os
from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_CORS_ORIGINS = ("http://localhost:8101", "http://127.0.0.1:8101")

# MVP operating assumption, not a permanent technical limit -- see
# docs/project-memory/MIGRATION_PLAN.md's Phase 1 update. Deployment-specific
# values belong in configuration, not hard-coded business logic.
DEFAULT_MAX_EVENT_UPLOAD_SIZE_MB = 100

# Relay Import Slice 3: relay setting sheets (text/table PDFs, even scanned
# ones) are orders of magnitude smaller than COMTRADE/BEN recordings, so the
# recording limit above is deliberately NOT reused. Configurable via
# MAX_RELAY_IMPORT_UPLOAD_SIZE_MB.
DEFAULT_MAX_RELAY_IMPORT_UPLOAD_SIZE_MB = 20

# Event Reconstruction (DEC-124): a gap of at least this many seconds in a
# reconstruction timeline produces an advisory warning, never a rejection.
# Central default only -- deliberately not read from the environment and
# not user-facing yet (owner direction); change it here.
DEFAULT_EVENT_RECONSTRUCTION_LARGE_GAP_WARNING_S = 3600.0

# Relay review integrity (DEC-198 Amendment 5): the upload returns a signed, opaque validation token
# (HMAC-SHA256 with RELAY_REVIEW_SIGNING_KEY) that validation and Apply verify before trusting the
# interpretation it carries. A token expires after this many hours (RELAY_REVIEW_TOKEN_TTL_HOURS);
# the user then uploads the setting file again.
DEFAULT_RELAY_REVIEW_TOKEN_TTL_HOURS = 24
# A shorter key is refused: the key is a shared secret, not a password to remember.
MIN_RELAY_REVIEW_SIGNING_KEY_LENGTH = 32


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
    # Phase 4A-UAT3: build provenance. Sourced ONLY from the APP_VERSION
    # environment variable (compose.yaml passes through the exact value
    # deploy.yml sets to `github.sha` -- the full 40-character commit SHA),
    # never computed by running `git` inside the running container/process.
    # "local" is the deliberate, truthful fallback when no deployment set
    # it (bare `docker run`, a plain `uvicorn` dev session) -- same
    # convention scripts/deploy.sh's own `APP_VERSION="${APP_VERSION:-local}"`
    # already uses, never a fabricated commit hash.
    git_sha: str
    version: str
    event_reconstruction_large_gap_warning_s: float = DEFAULT_EVENT_RECONSTRUCTION_LARGE_GAP_WARNING_S
    max_relay_import_upload_size_mb: int = DEFAULT_MAX_RELAY_IMPORT_UPLOAD_SIZE_MB
    # DEC-198 Amendment 5. The shared secret that signs relay review validation tokens; every
    # instance serving one deployment must use the same value. Never logged, never in a response.
    # ``None`` only outside a deployment (local development / tests): the application then signs
    # with a random per-process key (see app.services.relay_review_token.signer_from_settings).
    relay_review_signing_key: str | None = field(default=None, repr=False)
    relay_review_token_ttl_hours: int = DEFAULT_RELAY_REVIEW_TOKEN_TTL_HOURS

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_deployed(self) -> bool:
        """A deployed build: production, or any build the deploy workflows started (they set
        APP_VERSION to the deployed commit; it is "local" otherwise). DEV on the VPS runs with
        ENVIRONMENT=development, so the environment name alone does not say "deployed"."""
        return self.is_production or self.git_sha != "local"

    @property
    def max_event_upload_size_bytes(self) -> int:
        return self.max_event_upload_size_mb * 1024 * 1024

    @property
    def max_relay_import_upload_size_bytes(self) -> int:
        return self.max_relay_import_upload_size_mb * 1024 * 1024


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

    raw_relay_max = env.get("MAX_RELAY_IMPORT_UPLOAD_SIZE_MB", "").strip()
    if raw_relay_max:
        try:
            max_relay_import_upload_size_mb = int(raw_relay_max)
        except ValueError as exc:
            raise ConfigurationError(
                f"MAX_RELAY_IMPORT_UPLOAD_SIZE_MB must be an integer, got {raw_relay_max!r}"
            ) from exc
        if max_relay_import_upload_size_mb <= 0:
            raise ConfigurationError("MAX_RELAY_IMPORT_UPLOAD_SIZE_MB must be a positive integer")
    else:
        max_relay_import_upload_size_mb = DEFAULT_MAX_RELAY_IMPORT_UPLOAD_SIZE_MB

    # Phase 4A-UAT3: APP_VERSION is the full deployed Git commit SHA
    # (deploy.yml sets it to `github.sha`; compose.yaml passes it through
    # unchanged) -- read verbatim, never derived by running `git` here.
    # "local" (blank/unset) is the truthful fallback, never a fabricated
    # hash; `version` is simply its short (7-char) form, matching `git rev-parse
    # --short` convention, except "local" itself is already short enough to
    # pass through unchanged rather than being truncated into nonsense.
    git_sha = env.get("APP_VERSION", "").strip() or "local"
    version = git_sha if git_sha == "local" else git_sha[:7]

    # DEC-198 Amendment 5: required in every deployed build (never generated there, so all instances
    # of a deployment verify each other's tokens); optional for local development and tests. The
    # value is never echoed in an error.
    signing_key = env.get("RELAY_REVIEW_SIGNING_KEY", "").strip() or None
    deployed = environment == "production" or git_sha != "local"
    if signing_key is None and deployed:
        raise ConfigurationError(
            "RELAY_REVIEW_SIGNING_KEY must be set in a deployed environment "
            f"(a random secret of at least {MIN_RELAY_REVIEW_SIGNING_KEY_LENGTH} characters, the same for every instance)"
        )
    if signing_key is not None and len(signing_key) < MIN_RELAY_REVIEW_SIGNING_KEY_LENGTH:
        raise ConfigurationError(
            f"RELAY_REVIEW_SIGNING_KEY must be at least {MIN_RELAY_REVIEW_SIGNING_KEY_LENGTH} characters long"
        )

    raw_ttl = env.get("RELAY_REVIEW_TOKEN_TTL_HOURS", "").strip()
    if raw_ttl:
        try:
            relay_review_token_ttl_hours = int(raw_ttl)
        except ValueError as exc:
            raise ConfigurationError(
                f"RELAY_REVIEW_TOKEN_TTL_HOURS must be an integer, got {raw_ttl!r}"
            ) from exc
        if relay_review_token_ttl_hours <= 0:
            raise ConfigurationError("RELAY_REVIEW_TOKEN_TTL_HOURS must be a positive integer")
    else:
        relay_review_token_ttl_hours = DEFAULT_RELAY_REVIEW_TOKEN_TTL_HOURS

    return Settings(
        environment=environment,
        storage_type=storage_type,
        storage_path=storage_path,
        cors_origins=cors_origins,
        database_url=database_url,
        max_event_upload_size_mb=max_event_upload_size_mb,
        max_relay_import_upload_size_mb=max_relay_import_upload_size_mb,
        git_sha=git_sha,
        version=version,
        relay_review_signing_key=signing_key,
        relay_review_token_ttl_hours=relay_review_token_ttl_hours,
    )
