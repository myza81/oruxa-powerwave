#!/usr/bin/env bash

set -Eeuo pipefail

cd "$(dirname "$0")/.."

APP_VERSION="${APP_VERSION:-local}"
export APP_VERSION

echo "======================================"
echo "Powerwave deployment"
echo "Version: $APP_VERSION"
echo "======================================"

echo
echo "[1/4] Building images..."
docker compose build

echo
echo "[2/4] Starting containers..."
docker compose up -d --force-recreate

echo
echo "[3/4] Checking containers..."
docker compose ps

echo
echo "[4/4] Checking backend health..."

for i in {1..15}; do
    if curl --fail --silent http://127.0.0.1:8100/health > /dev/null; then
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
docker compose logs --tail=50 backend
exit 1
