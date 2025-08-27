#!/usr/bin/env bash
set -euo pipefail

WORKERS=${WORKERS:-3}            # Try 3–4 on an L40S
BASE_PORT=${BASE_PORT:-8001}     # Start at 8001 (8000 reserved for NGINX gateway)
BIN=/opt/sherpa-onnx/build/bin/sherpa-onnx-online-websocket-server
MOD=/opt/sherpa-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
LOG=/opt/sherpa-logs
mkdir -p "$LOG"

# (Optional) CUDA MPS can help multi-process scheduling
if command -v nvidia-cuda-mps-control >/dev/null 2>&1; then
  nvidia-cuda-mps-control -d || true
fi

# Kill any existing sherpa processes and clean ports
echo "Cleaning up any existing sherpa processes and port conflicts..."
pkill -f "sherpa-onnx-online-websocket-server" || true

# Force kill any processes on our target ports
for port in $(seq $BASE_PORT $((BASE_PORT + WORKERS - 1))); do
    if fuser ${port}/tcp 2>/dev/null; then
        echo "Killing processes on port $port..."
        fuser -k ${port}/tcp 2>/dev/null || true
    fi
done
sleep 3

echo "Starting $WORKERS workers on ports $BASE_PORT-$((BASE_PORT + WORKERS - 1))"

for i in $(seq 0 $((WORKERS-1))); do
  PORT=$((BASE_PORT + i))
  
  echo "Starting worker $((i+1))/$WORKERS on port $PORT..."
  
  # Start the worker
  CUDA_DEVICE_MAX_CONNECTIONS=32 \
  nohup "$BIN" \
    --port="$PORT" \
    --num-work-threads=4 \
    --num-io-threads=2 \
    --tokens="$MOD/tokens.txt" \
    --encoder="$MOD/encoder-epoch-99-avg-1.onnx" \
    --decoder="$MOD/decoder-epoch-99-avg-1.onnx" \
    --joiner="$MOD/joiner-epoch-99-avg-1.onnx" \
    --decoding-method=greedy_search \
    --enable-endpoint=true \
    --rule1-min-trailing-silence=0.12 \
    --rule2-min-trailing-silence=0.15 \
    --rule3-min-trailing-silence=0.00 \
    --max-batch-size=24 \
    --loop-interval-ms=10 \
    --log-file="$LOG/server_${PORT}.log" \
    >"$LOG/stdout_${PORT}.log" 2>&1 &
  
  WORKER_PID=$!
  
  # Wait for worker to fully initialize (model loading takes time)
  echo "   Waiting for model to load..."
  sleep 8
  
  # Verify the worker is running and accepting connections
  READY=false
  if kill -0 $WORKER_PID 2>/dev/null; then
    # Check if port is listening
    if ss -tulpn | grep -q ":${PORT} "; then
      # Test WebSocket connection readiness
      if timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/$PORT" 2>/dev/null; then
        echo "✅ Worker on port $PORT started successfully (PID $WORKER_PID)"
        READY=true
      else
        echo "⚠ Worker on port $PORT is binding but not ready for connections yet"
      fi
    else
      echo "❌ Worker on port $PORT process running but port not listening"
    fi
  else
    echo "❌ Worker on port $PORT process died"
  fi
  
  if [ "$READY" = false ]; then
    echo "   Check logs: tail -20 $LOG/stdout_${PORT}.log"
    if [ -f "$LOG/server_${PORT}.log" ]; then
        echo "   Recent errors:"
        tail -10 "$LOG/server_${PORT}.log" | grep -E "(error|Error|ERROR|failed|Failed|FAILED)" || echo "   No errors in server log"
    fi
    echo "   Process may still be starting - check again in 30 seconds"
  fi
done

echo ""
echo "=== Verifying all workers are ready ==="

# Give any slower workers extra time to start
echo "Giving slower workers additional time to initialize..."
sleep 10

# Final readiness check for all workers
ALL_READY=true
for i in $(seq 0 $((WORKERS-1))); do
  PORT=$((BASE_PORT + i))
  if timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/$PORT" 2>/dev/null; then
    echo "✅ Worker on port $PORT ready"
  else
    echo "❌ Worker on port $PORT not ready"
    ALL_READY=false
  fi
done

echo ""
echo "=== Multi-worker server deployment status ==="
echo "Workers: $WORKERS"
echo "Ports: $BASE_PORT-$((BASE_PORT + WORKERS - 1))"
echo "Logs: $LOG/"

if [ "$ALL_READY" = true ]; then
    echo "Status: ✅ All workers ready"
else
    echo "Status: ⚠ Some workers still starting"
    echo ""
    echo "💡 If workers are still starting:"
    echo "   - Wait 30-60 seconds and run health check: bash 09_health_check.sh"
    echo "   - Check logs: tail -f $LOG/server_*.log"
fi

echo ""
echo "Next steps:"
echo "1. Setup NGINX gateway: bash 07_setup_nginx_gateway.sh"
echo "2. Connect clients to: ws://your-server:8000 (NGINX will round-robin)"
echo "   OR connect directly to: $BASE_PORT-$((BASE_PORT + WORKERS - 1)) (manual round-robin)"
