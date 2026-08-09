#!/usr/bin/env bash
#
# Deploy Powerwave using the portable base plus one environment overlay.
#
#   ./scripts/deploy.sh            # production (default)
#   TARGET=dev ./scripts/deploy.sh # development

set -Eeuo pipefail

cd "$(dirname "$0")/.."

APP_VERSION="${APP_VERSION:-local}"
TARGET="${TARGET:-prod}"
export APP_VERSION

case "$TARGET" in
    dev|prod) ;;
    *)
        echo "ERROR: TARGET must be 'dev' or 'prod' (got '$TARGET')." >&2
        exit 2
        ;;
esac

COMPOSE_FILES=(-f compose.yaml -f "compose.${TARGET}.yaml")

# Load .env so the health check below targets the same port Compose published.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

HEALTH_HOST="${POWERWAVE_HEALTHCHECK_HOST:-127.0.0.1}"
HEALTH_PORT="${POWERWAVE_BACKEND_PORT:-8100}"
HEALTH_URL="http://${HEALTH_HOST}:${HEALTH_PORT}/health"

echo "======================================"
echo "Powerwave deployment"
echo "Target:  $TARGET"
echo "Version: $APP_VERSION"
echo "Health:  $HEALTH_URL"
echo "======================================"

echo
echo "[1/4] Building images..."
docker compose "${COMPOSE_FILES[@]}" build

echo
echo "[2/4] Starting containers..."
docker compose "${COMPOSE_FILES[@]}" up -d --force-recreate

echo
echo "[3/4] Checking containers..."
docker compose "${COMPOSE_FILES[@]}" ps

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
docker compose "${COMPOSE_FILES[@]}" logs --tail=50 backend
exit 1
