#!/usr/bin/env bash
set -euo pipefail

WORKERS=${WORKERS:-3}            # Try 3–4 on an L40S
BASE_PORT=${BASE_PORT:-8001}     # Start at 8001 (8000 reserved for NGINX gateway)
BIN=/opt/sherpa-onnx/build/bin/sherpa-onnx-online-websocket-server
MOD=/opt/sherpa-models/zh-en-zipformer-2023-02-20
LOG=/opt/sherpa-logs
mkdir -p "$LOG"

# (Optional) CUDA MPS can help multi-process scheduling
if command -v nvidia-cuda-mps-control >/dev/null 2>&1; then
  nvidia-cuda-mps-control -d || true
fi

# Kill any existing sherpa processes first
echo "Cleaning up any existing sherpa processes..."
pkill -f "sherpa-onnx-online-websocket-server" || true
sleep 3

echo "Starting $WORKERS workers on ports $BASE_PORT-$((BASE_PORT + WORKERS - 1))"

for i in $(seq 0 $((WORKERS-1))); do
  PORT=$((BASE_PORT + i))
  
  # Check if port is already in use
  if ss -tulpn | grep -q ":${PORT} "; then
    echo "Warning: Port $PORT is already in use, killing processes on that port..."
    fuser -k ${PORT}/tcp 2>/dev/null || true
    sleep 2
  fi
  
  # Enhanced environment for better GPU scheduling
  CUDA_DEVICE_MAX_CONNECTIONS=32 \
  nohup "$BIN" \
    --port="$PORT" \
    --num-work-threads=4 \
    --num-io-threads=2 \
    --tokens="$MOD/tokens.txt" \
    --encoder="$MOD/encoder-epoch-99-avg-1.int8.onnx" \
    --decoder="$MOD/decoder-epoch-99-avg-1.onnx" \
    --joiner="$MOD/joiner-epoch-99-avg-1.int8.onnx" \
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
  echo "Started sherpa worker on port ${PORT} (PID $WORKER_PID)"
  
  # Verify the worker actually started
  sleep 2
  if ! kill -0 $WORKER_PID 2>/dev/null; then
    echo "ERROR: Worker on port $PORT failed to start. Check logs:"
    echo "  tail -20 $LOG/stdout_${PORT}.log"
    echo "  tail -20 $LOG/server_${PORT}.log"
  fi
done

echo ""
echo "=== Multi-worker server started ==="
echo "Workers: $WORKERS"
echo "Ports: $BASE_PORT-$((BASE_PORT + WORKERS - 1))"
echo "Logs: $LOG/"
echo ""
echo "Next steps:"
echo "1. Setup NGINX gateway: bash 07_setup_nginx_gateway.sh"
echo "2. Connect clients to: ws://your-server:8000 (NGINX will round-robin)"
echo "   OR connect directly to: $BASE_PORT-$((BASE_PORT + WORKERS - 1)) (manual round-robin)"
