#!/usr/bin/env bash
set -euo pipefail

WORKERS=${WORKERS:-3}            # Try 3–4 on an L40S
BASE_PORT=${BASE_PORT:-8000}
BIN=/opt/sherpa-onnx/build/bin/sherpa-onnx-online-websocket-server
MOD=/opt/sherpa-models/zh-en-zipformer-2023-02-20
LOG=/opt/sherpa-logs
mkdir -p "$LOG"

# (Optional) CUDA MPS can help multi-process scheduling
if command -v nvidia-cuda-mps-control >/dev/null 2>&1; then
  nvidia-cuda-mps-control -d || true
fi

for i in $(seq 0 $((WORKERS-1))); do
  PORT=$((BASE_PORT + i))
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
  echo "Started sherpa worker on port ${PORT} (PID $!)"
done
