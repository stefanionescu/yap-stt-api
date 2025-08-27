#!/usr/bin/env bash
set -euo pipefail

# Debug script for troubleshooting worker startup issues
# Run this if workers are failing to start or accepting connections

echo "=== Sherpa Worker Debug Tool ==="
echo ""

LOG_DIR="/opt/sherpa-logs"
BASE_PORT=8001
WORKERS=3

echo "1. Checking system resources..."
echo "CPU cores: $(nproc)"
echo "Memory: $(free -h | awk '/^Mem:/ {print $2 " total, " $3 " used, " $7 " available"}')"
echo "GPU: $(nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits 2>/dev/null || echo "No GPU detected")"
echo ""

echo "2. Checking Sherpa installation..."
BIN="/opt/sherpa-onnx/build/bin/sherpa-onnx-online-websocket-server"
MOD="/opt/sherpa-models/zh-en-zipformer-2023-02-20"

if [ -x "$BIN" ]; then
    echo "✅ Sherpa binary found: $BIN"
else
    echo "❌ Sherpa binary not found or not executable: $BIN"
fi

if [ -d "$MOD" ]; then
    echo "✅ Model directory found: $MOD"
    echo "   Model files:"
    ls -la "$MOD"/*.onnx "$MOD"/tokens.txt 2>/dev/null || echo "   ❌ Missing model files"
else
    echo "❌ Model directory not found: $MOD"
fi
echo ""

echo "3. Checking running processes..."
if pgrep -f "sherpa-onnx-online-websocket-server" >/dev/null; then
    echo "✅ Sherpa processes running:"
    ps aux | grep "sherpa-onnx-online-websocket-server" | grep -v grep
else
    echo "❌ No Sherpa processes running"
fi
echo ""

echo "4. Checking port usage..."
for port in $(seq $BASE_PORT $((BASE_PORT + WORKERS - 1))); do
    if ss -tulpn | grep ":$port " >/dev/null 2>&1; then
        PROCESS=$(ss -tulpn | grep ":$port " | awk '{print $7}')
        echo "✅ Port $port: listening ($PROCESS)"
    else
        echo "❌ Port $port: not listening"
        # Check what might be using the port
        if fuser ${port}/tcp 2>/dev/null; then
            echo "   Port blocked by: $(fuser ${port}/tcp 2>&1)"
        fi
    fi
done
echo ""

echo "5. Checking recent logs..."
if [ -d "$LOG_DIR" ]; then
    for port in $(seq $BASE_PORT $((BASE_PORT + WORKERS - 1))); do
        echo "=== Worker $port logs ==="
        
        STDOUT_LOG="$LOG_DIR/stdout_${port}.log"
        SERVER_LOG="$LOG_DIR/server_${port}.log"
        
        if [ -f "$STDOUT_LOG" ]; then
            echo "Last 10 lines from stdout:"
            tail -10 "$STDOUT_LOG" 2>/dev/null || echo "   (empty or unreadable)"
        else
            echo "❌ No stdout log: $STDOUT_LOG"
        fi
        
        if [ -f "$SERVER_LOG" ]; then
            echo "Last 10 lines from server log:"
            tail -10 "$SERVER_LOG" 2>/dev/null || echo "   (empty or unreadable)"
            
            # Look for common errors
            if grep -i "error\|failed\|exception" "$SERVER_LOG" >/dev/null 2>&1; then
                echo "⚠ Errors found:"
                grep -i "error\|failed\|exception" "$SERVER_LOG" | tail -5
            fi
        else
            echo "❌ No server log: $SERVER_LOG"
        fi
        echo ""
    done
else
    echo "❌ Log directory not found: $LOG_DIR"
fi

echo "6. Testing WebSocket readiness..."
for port in $(seq $BASE_PORT $((BASE_PORT + WORKERS - 1))); do
    if timeout 5 bash -c "echo > /dev/tcp/127.0.0.1/$port" 2>/dev/null; then
        echo "✅ Port $port: accepting connections"
    else
        echo "❌ Port $port: connection failed"
    fi
done
echo ""

echo "=== Debug Complete ==="
echo ""
echo "💡 Common solutions:"
echo "• If processes are running but ports not listening: Check model files"
echo "• If no processes running: Check GPU memory and system resources"
echo "• If connection refused: Wait 30-60 seconds for model loading"
echo "• If persistent issues: Try single worker first (script 03)"
echo ""
echo "Commands to try:"
echo "• Restart workers: bash 04_run_server_multi_int8.sh"
echo "• Clean restart: bash 99_cleanup_services.sh && bash 08_deployment_chooser.sh"
echo "• Check live logs: tail -f $LOG_DIR/server_*.log"
