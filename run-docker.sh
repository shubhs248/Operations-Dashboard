#!/bin/bash
# Build and run the Platform Operations Dashboard container
# Connects to existing platform-portal-postgres and platform-portal-redis via host network
# Usage: sudo bash run-docker.sh

set -e

IMAGE_NAME="platform-ops-dashboard"
CONTAINER_NAME="platform-ops-dashboard"
PORT=9200

echo "==> Stopping existing container (if any)..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

echo "==> Building image..."
docker build \
  --network host \
  --build-arg http_proxy=http://proxy.example.com:8080 \
  --build-arg https_proxy=http://proxy.example.com:8080 \
  --build-arg no_proxy=localhost,127.0.0.1,.example.com \
  -t $IMAGE_NAME .

echo "==> Ensuring DB user and database exist (idempotent)..."
docker exec platform-portal-postgres psql -U platform_user -d platform_portal -c \
  "SELECT 1 FROM pg_roles WHERE rolname='dashboard'" | grep -q 1 || \
  docker exec platform-portal-postgres psql -U platform_user -d platform_portal -c \
  "CREATE USER dashboard WITH PASSWORD 'changeme';"

docker exec platform-portal-postgres psql -U platform_user -d platform_portal -c \
  "SELECT 1 FROM pg_database WHERE datname='platform_ops_dashboard'" | grep -q 1 || \
  docker exec platform-portal-postgres psql -U platform_user -d platform_portal -c \
  "CREATE DATABASE platform_ops_dashboard OWNER dashboard;"

echo "==> Starting container (host network for access to PG/Redis)..."
docker run -d \
  --name $CONTAINER_NAME \
  --network host \
  -v platform-ops-data:/app/data \
  --env-file .env \
  -e APP_PORT=$PORT \
  -e APP_HOST=0.0.0.0 \
  -e DATABASE_URL=postgresql://dashboard:changeme@localhost:5432/platform_ops_dashboard \
  -e REDIS_URL=redis://localhost:6379/2 \
  --restart unless-stopped \
  $IMAGE_NAME

echo ""
echo "==> Dashboard running at http://$(hostname):$PORT"
echo "==> Logs: docker logs -f $CONTAINER_NAME"
echo ""
echo "==> Other containers on this host:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "platform-portal|platform-ops"
