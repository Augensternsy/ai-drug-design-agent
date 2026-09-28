#!/bin/bash
# ============================================================
# Check Live Backend Status & Tailscale Funnel
# ============================================================
set -e

PROJECT_DIR="/mnt/harddisk/wsy/drug-design-agent"
SOCKET_PATH="$PROJECT_DIR/state/tailscaled.sock"
TAILSCALE_BIN="$PROJECT_DIR/bin/tailscale"

echo "=================================================="
echo "1. Checking Systemd FastAPI Service..."
echo "=================================================="
if systemctl --user is-active --quiet drug-design-agent.service; then
    echo "[PASS] drug-design-agent.service is RUNNING."
else
    echo "[FAIL] drug-design-agent.service is NOT running."
fi

echo ""
echo "=================================================="
echo "2. Checking Local Health Endpoint (/api/health)..."
echo "=================================================="
HEALTH_RESP=$(curl -s --connect-timeout 5 http://127.0.0.1:8000/api/health || echo "FAILED")
if [[ "$HEALTH_RESP" == *"\"status\":\"ok\""* ]]; then
    echo "[PASS] /api/health returned OK:"
    echo "$HEALTH_RESP"
else
    echo "[FAIL] /api/health check failed:"
    echo "$HEALTH_RESP"
fi

echo ""
echo "=================================================="
echo "3. Checking Tailscale Daemon & Funnel Status..."
echo "=================================================="
if systemctl --user is-active --quiet tailscaled.service; then
    echo "[PASS] tailscaled.service is RUNNING."
    
    if [ -f "$TAILSCALE_BIN" ];  then
        echo ""
        echo "Tailscale Node Status:"
        "$TAILSCALE_BIN" --socket="$SOCKET_PATH" status || true
        
        echo ""
        echo "Tailscale Funnel Status:"
        "$TAILSCALE_BIN" --socket="$SOCKET_PATH" funnel status || true
    fi
else
    echo "[FAIL] tailscaled.service is NOT running."
fi

echo "=================================================="
