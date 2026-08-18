#!/bin/sh
# Regenerate the frontend runtime configuration from the environment.
#
# nginx:alpine runs every executable in /docker-entrypoint.d before starting
# nginx, which lets one image serve any environment.

set -eu

# Overridable so the validation below can be exercised by tests. Defaults to
# the path nginx serves from, so container behaviour is unchanged.
CONFIG_DIR="${POWERWAVE_CONFIG_DIR:-/usr/share/nginx/html}"

ENVIRONMENT="${ENVIRONMENT:-development}"

# Blank (unset, empty, or whitespace only) counts as missing.
case "${API_BASE_URL:-}" in
    *[![:space:]]*) API_BASE_URL_SET=1 ;;
    *)              API_BASE_URL_SET=0 ;;
esac

# In production the localhost fallback would produce a frontend that loads but
# silently cannot reach its backend. Fail the container start instead.
if [ "$ENVIRONMENT" = "production" ] && [ "$API_BASE_URL_SET" -eq 0 ]; then
    echo "powerwave: ERROR: API_BASE_URL must be set when ENVIRONMENT=production." >&2
    echo "powerwave: refusing to fall back to a local development URL." >&2
    exit 1
fi

# Development and local use keep the convenient default.
: "${API_BASE_URL:=http://127.0.0.1:8000}"

# Phase 4A-UAT3: build provenance. APP_VERSION is set by deploy.sh/CI to the
# full deployed Git commit SHA (github.sha) -- never computed here by
# executing git inside the container, and never fabricated: a container
# started without it (bare `docker run`, local `docker compose up` without
# deploy.sh) truthfully reports "local", matching scripts/deploy.sh's own
# `APP_VERSION="${APP_VERSION:-local}"` fallback exactly, so DEV/PROD and an
# ad-hoc local container never disagree about what "unknown" means.
: "${APP_VERSION:=local}"

cat > "${CONFIG_DIR}/config.js" <<EOF
window.POWERWAVE_CONFIG = {
  apiBaseUrl: "${API_BASE_URL}",
  environment: "${ENVIRONMENT}",
  buildVersion: "${APP_VERSION}",
};
EOF

echo "powerwave: API base URL set to ${API_BASE_URL}"
echo "powerwave: build version set to ${APP_VERSION}"
