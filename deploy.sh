#!/bin/bash
# Deploy Platform Operations Dashboard to mcp-host.example.com (RHEL)
# Usage: ./deploy.sh [--build-only]

set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-mcp-host.example.com}"
DEPLOY_DIR="/opt/platform-ops-dashboard"
SERVICE_NAME="platform-ops-dashboard"

echo "=== Platform Operations Dashboard Deployment ==="
echo "Target: ${DEPLOY_HOST}:${DEPLOY_DIR}"
echo ""

if [[ "${1:-}" == "--build-only" ]]; then
    echo "[1/1] Building Docker images locally..."
    docker compose build
    echo "Build complete."
    exit 0
fi

echo "[1/5] Syncing project files to ${DEPLOY_HOST}..."
rsync -avz --exclude='.env' --exclude='__pycache__' --exclude='.git' \
    --exclude='*.pyc' --exclude='node_modules' \
    ./ "${DEPLOY_HOST}:${DEPLOY_DIR}/"

echo "[2/5] Setting up .env on remote (if not exists)..."
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_DIR} && [ -f .env ] || cp .env.example .env"

echo "[3/5] Building and starting containers on ${DEPLOY_HOST}..."
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_DIR} && docker compose pull || true"
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_DIR} && docker compose build"

echo "[4/5] Starting services..."
ssh "${DEPLOY_HOST}" "cd ${DEPLOY_DIR} && docker compose up -d"

echo "[5/5] Verifying health..."
sleep 5
if ssh "${DEPLOY_HOST}" "curl -sf http://localhost:9100/ > /dev/null 2>&1"; then
    echo ""
    echo "=== Deployment successful ==="
    echo "Dashboard: http://${DEPLOY_HOST}:9100/"
    echo "API Docs:  http://${DEPLOY_HOST}:9100/docs"
else
    echo ""
    echo "WARNING: Health check failed. Check logs with:"
    echo "  ssh ${DEPLOY_HOST} 'cd ${DEPLOY_DIR} && docker compose logs -f dashboard'"
fi
