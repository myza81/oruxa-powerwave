#!/usr/bin/env bash
#
# Deploy Powerwave using the portable base plus one environment overlay.
#
#   ./scripts/deploy.sh            # production (default)
#   TARGET=dev ./scripts/deploy.sh # development
#
# TARGET selects the overlay and the Compose project name together, so DEV and
# PROD stay isolated even when deployed to the same host. Every Compose command
# below addresses services by name (backend/frontend); no container name is
# assumed anywhere.

set -Eeuo pipefail

cd "$(dirname "$0")/.."

APP_VERSION="${APP_VERSION:-local}"
TARGET="${TARGET:-prod}"

case "$TARGET" in
    dev|prod) ;;
    *)
        echo "ERROR: TARGET must be 'dev' or 'prod' (got '$TARGET')." >&2
        exit 2
        ;;
esac

# Both are exported for Compose interpolation: TARGET qualifies the image tag
# so DEV and PROD never share a mutable one.
export APP_VERSION TARGET

# Must match the `name:` declared in the corresponding overlay.
PROJECT="powerwave-${TARGET}"

COMPOSE=(docker compose -p "$PROJECT" -f compose.yaml -f "compose.${TARGET}.yaml")

# Load .env so the health check below targets the same port Compose published.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Defaults mirror the overlays: PROD 8100/8101, DEV 8200/8201.
if [[ "$TARGET" == "prod" ]]; then
    DEFAULT_BACKEND_PORT=8100
else
    DEFAULT_BACKEND_PORT=8200
fi

HEALTH_HOST="${POWERWAVE_HEALTHCHECK_HOST:-127.0.0.1}"
HEALTH_PORT="${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"
HEALTH_URL="http://${HEALTH_HOST}:${HEALTH_PORT}/health"

echo "======================================"
echo "Powerwave deployment"
echo "Target:  $TARGET"
echo "Project: $PROJECT"
echo "Version: $APP_VERSION"
echo "Health:  $HEALTH_URL"
echo "======================================"

echo
echo "[1/4] Building images..."
"${COMPOSE[@]}" build

echo
echo "[2/4] Starting containers..."
"${COMPOSE[@]}" up -d --force-recreate

echo
echo "[3/4] Checking containers..."
"${COMPOSE[@]}" ps

echo
echo "[4/4] Checking backend health..."

for i in {1..15}; do
    if curl --fail --silent "$HEALTH_URL" > /dev/null; then
        echo "Powerwave backend is healthy."
        echo
        echo "Deployment successful."
        exit 0
    fi

    echo "Waiting for backend... ($i/15)"
    sleep 2
done

echo
echo "ERROR: Powerwave backend health check failed."
"${COMPOSE[@]}" logs --tail=50 backend
exit 1
