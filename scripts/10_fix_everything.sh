#!/usr/bin/env bash
set -euo pipefail

# Emergency fix script - reset everything and start fresh
# Use this when things are broken and you want a clean restart

echo "=== EMERGENCY RESET & RESTART ==="
echo "This script will:"
echo "1. Kill all sherpa and nginx processes"  
echo "2. Clean up config conflicts"
echo "3. Restart everything properly"
echo ""

# 1. Kill everything
echo "Step 1: Killing all processes..."
pkill -f "sherpa-onnx" || true
pkill nginx || true
sleep 3

# 2. Clean up NGINX config issues
echo "Step 2: Fixing NGINX configuration..."
rm -f /etc/nginx/sites-enabled/default || true
rm -f /etc/nginx/sites-enabled/default.bak || true

# Ensure sites-enabled is included in nginx.conf
if ! grep -q "sites-enabled" /etc/nginx/nginx.conf; then
    echo "Adding sites-enabled include to nginx.conf..."
    sed -i '/^[[:space:]]*}[[:space:]]*$/i\    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
fi

# Test NGINX config
nginx -t

# 3. Clean up any port conflicts
echo "Step 3: Cleaning up port conflicts..."
for port in 8000 8001 8002 8003; do
    if ss -tulpn | grep -q ":${port} "; then
        echo "Killing processes on port $port..."
        fuser -k ${port}/tcp 2>/dev/null || true
    fi
done
sleep 3

# 4. Start multi-worker servers
echo "Step 4: Starting sherpa workers..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/04_run_server_multi_int8.sh"

echo ""
echo "Step 5: Starting NGINX gateway..."
bash "$SCRIPT_DIR/07_setup_nginx_gateway.sh"

echo ""
echo "Step 6: Final health check..."
sleep 3
bash "$SCRIPT_DIR/09_health_check.sh"

echo ""
echo "=== EMERGENCY RESET COMPLETE ==="
echo "If everything shows ✅, you're good to go!"
echo "Connect clients to: ws://your-server:8000"
