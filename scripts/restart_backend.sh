#!/bin/bash
# ============================================================
# Restart Drug Design Agent Backend Services
# ============================================================
set -e

PROJECT_DIR="/mnt/harddisk/wsy/drug-design-agent"
SOCKET_PATH="$PROJECT_DIR/state/tailscaled.sock"
TAILSCALE_BIN="$PROJECT_DIR/bin/tailscale"

echo "Restarting tailscaled.service..."
systemctl --user restart tailscaled.service

echo "Restarting drug-design-agent.service..."
systemctl --user restart drug-design-agent.service

echo "Waiting for backend startup..."
sleep 3

if [ -f "$PROJECT_DIR/scripts/check_live_backend.sh" ]; then
    bash "$PROJECT_DIR/scripts/check_live_backend.sh"
fi
