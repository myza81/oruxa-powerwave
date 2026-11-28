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

# NF-3I: the Manual nominal-frequency control is shown only when NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED is set to an explicit affirmative
# (1, true or yes), and only for ENVIRONMENT=development: any other environment that carries it fails the container start (the backend
# refuses the same variable the same way), so a copied environment file cannot show the control in PROD. Unset, or anything else, emits
# no flag at all and the page keeps the original read-only row.
NF_OVERRIDE_RAW="$(printf '%s' "${NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED:-}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
case "$NF_OVERRIDE_RAW" in
    1|true|yes) NF_OVERRIDE=1 ;;
    *)          NF_OVERRIDE=0 ;;
esac
if [ "$NF_OVERRIDE" -eq 1 ] && [ "$ENVIRONMENT" != "development" ]; then
    echo "powerwave: ERROR: NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED is released for ENVIRONMENT=development only (got ENVIRONMENT=${ENVIRONMENT})." >&2
    exit 1
fi

{
    echo "window.POWERWAVE_CONFIG = {"
    echo "  apiBaseUrl: \"${API_BASE_URL}\","
    echo "  environment: \"${ENVIRONMENT}\","
    echo "  buildVersion: \"${APP_VERSION}\","
    if [ "$NF_OVERRIDE" -eq 1 ]; then
        echo "  featureFlags: { nominalFrequencyOverride: true },"
    fi
    echo "};"
} > "${CONFIG_DIR}/config.js"

echo "powerwave: API base URL set to ${API_BASE_URL}"
echo "powerwave: build version set to ${APP_VERSION}"
if [ "$NF_OVERRIDE" -eq 1 ]; then echo "powerwave: nominal-frequency Manual override control enabled (DEV)"; fi
