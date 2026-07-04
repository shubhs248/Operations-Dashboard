#!/bin/bash
# Alternative: Deploy without Docker using systemd on RHEL
# Prerequisites: Python 3.12+, PostgreSQL, Redis (optional)

set -euo pipefail

DEPLOY_DIR="/opt/platform-ops-dashboard"
VENV_DIR="${DEPLOY_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/platform-ops-dashboard.service"

echo "=== Systemd deployment for Platform Operations Dashboard ==="

echo "[1/5] Creating virtualenv..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

echo "[2/5] Installing dependencies..."
pip install --upgrade pip
pip install -r "${DEPLOY_DIR}/requirements.txt"

echo "[3/5] Setting up .env..."
if [ ! -f "${DEPLOY_DIR}/.env" ]; then
    cp "${DEPLOY_DIR}/.env.example" "${DEPLOY_DIR}/.env"
    echo "IMPORTANT: Edit ${DEPLOY_DIR}/.env with your credentials"
fi

echo "[4/5] Creating systemd service..."
cat > "${SERVICE_FILE}" << 'UNIT'
[Unit]
Description=AT Tools Operations Dashboard
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/platform-ops-dashboard
Environment=PATH=/opt/platform-ops-dashboard/venv/bin:/usr/local/bin:/usr/bin
ExecStart=/opt/platform-ops-dashboard/venv/bin/python -m app.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

echo "[5/5] Enabling and starting service..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo ""
echo "=== Service status ==="
systemctl status "${SERVICE_NAME}" --no-pager || true
echo ""
echo "Dashboard: http://$(hostname):9100/"
echo "Logs:      journalctl -u ${SERVICE_NAME} -f"
