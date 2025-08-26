#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-12}          # try 8–16; tune with load
LOOP_MS=${LOOP_MS:-15}              # batching tick; 10–20 ms is typical
LOG="$ROOT/logs/server.out"

MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"

# Use CUDA EP (TensorRT EP can be added later if needed)
PROVIDER=${PROVIDER:-cuda}

# Make logs directory
mkdir -p "$ROOT/logs"

# Diagnostic: check available providers
echo "[diag] Checking ONNX Runtime providers:"
python - <<'PY'
import onnxruntime as ort
print("[diag] ORT available providers:", ort.get_available_providers())
PY

# Fail fast if model assets are missing
[ -f "$MODEL" ] || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }

# Start server in background and save PID
echo "[start] sherpa-onnx WS server on :$PORT (provider=$PROVIDER, batch=$MAX_BATCH, loop=${LOOP_MS}ms)"
nohup python "$ROOT/repos/sherpa-onnx/python-api-examples/streaming_server.py" \
  --provider="$PROVIDER" \
  --port="$PORT" \
  --max-batch-size="$MAX_BATCH" \
  --loop-interval-ms="$LOOP_MS" \
  --nemo-ctc-model "$MODEL" \
  --nemo-ctc-tokens "$TOKENS" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"


