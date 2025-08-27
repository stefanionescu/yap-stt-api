#!/usr/bin/env bash
set -euo pipefail

# Health check script - verify sherpa servers and NGINX are working
# Tests WebSocket connections and shows server logs

echo "=== Sherpa Health Check ==="
echo ""

# 1. Check if processes are running
echo "1. Checking running processes..."
if pgrep -f "sherpa-onnx-online-websocket-server" >/dev/null; then
    WORKER_COUNT=$(pgrep -f "sherpa-onnx-online-websocket-server" | wc -l)
    echo "✅ $WORKER_COUNT Sherpa workers running"
    echo "   PIDs: $(pgrep -f "sherpa-onnx-online-websocket-server" | tr '\n' ' ')"
else
    echo "❌ No Sherpa workers found"
fi

if pgrep nginx >/dev/null; then
    echo "✅ NGINX running (PID: $(pgrep nginx | head -1))"
else
    echo "❌ NGINX not running"
fi
echo ""

# 2. Check listening ports
echo "2. Checking listening ports..."
for port in 8000 8001 8002 8003; do
    if ss -ltn | grep ":$port " >/dev/null 2>&1; then
        echo "✅ Port $port listening"
    else
        echo "❌ Port $port not listening"
    fi
done
echo ""

# 3. Test WebSocket connections (basic HTTP GET to upgrade endpoint)
echo "3. Testing WebSocket endpoints..."
for port in 8000 8001 8002 8003; do
    if timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/$port" 2>/dev/null; then
        echo "✅ Port $port accepting connections"
    else
        echo "❌ Port $port connection refused"
    fi
done
echo ""

# 4. Show recent server logs (not errors)
echo "4. Recent server activity (last 20 lines from each worker)..."
echo ""
for port in 8001 8002 8003; do
    LOG_FILE="/opt/sherpa-logs/server_${port}.log"
    if [ -f "$LOG_FILE" ]; then
        echo "=== Worker on port $port ==="
        tail -20 "$LOG_FILE" 2>/dev/null || echo "No logs yet"
        echo ""
    else
        echo "❌ Log file not found: $LOG_FILE"
    fi
done

# 5. Check NGINX access logs
echo "5. NGINX gateway activity..."
NGINX_ACCESS="/var/log/nginx/access.log"
if [ -f "$NGINX_ACCESS" ]; then
    if [ -s "$NGINX_ACCESS" ]; then
        echo "Recent NGINX access (last 10 lines):"
        tail -10 "$NGINX_ACCESS"
    else
        echo "✅ NGINX running, no client connections yet"
    fi
else
    echo "⚠ NGINX access log not found"
fi
echo ""

# 6. Quick connection test (if curl available)
echo "6. Quick HTTP test..."
if command -v curl >/dev/null; then
    echo "Testing HTTP connection to port 8000..."
    if curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:8000" 2>/dev/null | grep -q "400\|426"; then
        echo "✅ NGINX responding (HTTP 400/426 expected for WebSocket upgrade)"
    else
        echo "⚠ Unexpected response or timeout"
    fi
else
    echo "⚠ curl not available, skipping HTTP test"
fi

echo ""
echo "=== Health Check Complete ==="
echo ""
echo "💡 Tips:"
echo "• Empty error logs = good (no errors)"
echo "• To see live server logs: tail -f /opt/sherpa-logs/server_*.log"
echo "• To see live NGINX logs: tail -f /var/log/nginx/access.log"
echo "• Connect WebSocket clients to: ws://your-server:8000"
