#!/bin/bash
# refresh-ocp-token.sh — Auto-refresh OCP token and restart dashboard
# Schedule via cron: 0 */12 * * * /opt/platform-ops-dashboard/refresh-ocp-token.sh >> /var/log/ocp-token-refresh.log 2>&1
#
# Supports two modes:
#   1. ServiceAccount Secret (preferred, no credentials needed)
#   2. User login via OCP OAuth (fallback, needs OC_USER/OC_PASS)

set -euo pipefail

# ── Configuration ──
DASHBOARD_DIR="${DASHBOARD_DIR:-/opt/platform-ops-dashboard}"
ENV_FILE="$DASHBOARD_DIR/.env"

OCP_API="https://api.ocp-cluster.example.com:6443"
OCP_OAUTH="https://oauth-openshift.apps.ocp-cluster.example.com"

SA_NAMESPACE="nexus-mcp"
SA_SECRET_NAME="platform-monitoring-sa-token"

# For user-login fallback (set these in environment or uncomment below)
# OC_USER="shubhas8"
# OC_PASS="your-password"

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log()  { echo "$LOG_PREFIX $*"; }
fail() { log "FAIL: $*"; exit 1; }

# ── Method 1: Read token from ServiceAccount Secret (non-expiring) ──
get_sa_token() {
  log "Attempting ServiceAccount Secret token retrieval..."

  local EXISTING_TOKEN
  EXISTING_TOKEN=$(grep '^OCP_TOKEN=' "$ENV_FILE" | head -1 | cut -d'=' -f2-)

  if [ -z "$EXISTING_TOKEN" ]; then
    fail "No existing OCP_TOKEN in .env to bootstrap API call"
  fi

  local RESP
  RESP=$(curl -sk \
    -H "Authorization: Bearer $EXISTING_TOKEN" \
    "$OCP_API/api/v1/namespaces/$SA_NAMESPACE/secrets/$SA_SECRET_NAME" 2>&1)

  local B64_TOKEN
  B64_TOKEN=$(echo "$RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d['data']['token'])
except:
    print('')
" 2>/dev/null)

  if [ -n "$B64_TOKEN" ] && [ "$B64_TOKEN" != "" ]; then
    echo "$B64_TOKEN" | base64 -d 2>/dev/null
    return 0
  fi
  return 1
}

# ── Method 2: OAuth login to get a fresh user token ──
get_oauth_token() {
  local user="${OC_USER:-}"
  local pass="${OC_PASS:-}"

  if [ -z "$user" ] || [ -z "$pass" ]; then
    log "OC_USER/OC_PASS not set, skipping OAuth method"
    return 1
  fi

  log "Attempting OAuth token retrieval for $user..."

  local LOCATION
  LOCATION=$(curl -sk -I -u "$user:$pass" \
    "$OCP_OAUTH/oauth/authorize?response_type=token&client_id=openshift-challenging-client" \
    2>/dev/null | grep -i '^location:' | head -1)

  if [ -z "$LOCATION" ]; then
    return 1
  fi

  local TOKEN
  TOKEN=$(echo "$LOCATION" | sed -E 's/.*access_token=([^&]+).*/\1/' | tr -d '\r\n')

  if [ -n "$TOKEN" ] && [ ${#TOKEN} -gt 10 ]; then
    echo "$TOKEN"
    return 0
  fi
  return 1
}

# ── Main ──
log "=== OCP Token Refresh Start ==="

if [ ! -f "$ENV_FILE" ]; then
  fail ".env not found at $ENV_FILE"
fi

OLD_TOKEN=$(grep '^OCP_TOKEN=' "$ENV_FILE" | head -1 | cut -d'=' -f2- || echo "")

NEW_TOKEN=""

# Try SA Secret first
if NEW_TOKEN=$(get_sa_token) && [ -n "$NEW_TOKEN" ]; then
  log "Got token from ServiceAccount Secret"
elif NEW_TOKEN=$(get_oauth_token) && [ -n "$NEW_TOKEN" ]; then
  log "Got token from OAuth login"
else
  fail "Could not obtain a new token via any method"
fi

# Skip if token hasn't changed
if [ "$NEW_TOKEN" = "$OLD_TOKEN" ]; then
  log "Token unchanged, skipping restart"
  exit 0
fi

# Update .env
if grep -q '^OCP_TOKEN=' "$ENV_FILE"; then
  sed -i "s|^OCP_TOKEN=.*|OCP_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
else
  echo "OCP_TOKEN=$NEW_TOKEN" >> "$ENV_FILE"
fi
log "Updated OCP_TOKEN in $ENV_FILE"

# Restart dashboard
log "Restarting dashboard container..."
cd "$DASHBOARD_DIR"
docker compose down && docker compose up -d --build
log "Container restarted"

# Verify health
sleep 10
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9200/api/mcp/metrics 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  log "Health check passed (HTTP 200)"
else
  log "WARNING: Health check returned HTTP $HTTP_CODE"
fi

log "=== OCP Token Refresh Complete ==="
