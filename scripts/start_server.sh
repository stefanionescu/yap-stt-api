#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}

# Concurrency knobs (tune these):
MAX_BATCH=${MAX_BATCH:-16}          # 8–24 works well on L40/L40S for 80ms CTC
NN_POOL=${NN_POOL:-4}               # number of ORT sessions; 3–6 is typical
LOOP_MS=${LOOP_MS:-15}              # batching tick; 10–20ms

MAX_WAIT_MS=${MAX_WAIT_MS:-15}      # wait to coalesce a batch
NUM_THREADS=${NUM_THREADS:-1}       # CPU thread hint to ORT
MAX_ACTIVE=${MAX_ACTIVE:-400}       # connection cap
MAX_QUEUE=${MAX_QUEUE:-32768}       # per-conn message queue cap

LOG="$ROOT/logs/server.out"
MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
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
echo "[start] sherpa-onnx WS server on :$PORT (provider=$PROVIDER, batch=$MAX_BATCH, pool=$NN_POOL, loop=${LOOP_MS}ms)"
nohup python "$ROOT/repos/sherpa-onnx/python-api-examples/streaming_server.py" \
  --provider="$PROVIDER" \
  --port="$PORT" \
  --nemo-ctc-model "$MODEL" \
  --tokens "$TOKENS" \
  --max-batch-size "$MAX_BATCH" \
  --nn-pool-size "$NN_POOL" \
  --loop-interval-ms "$LOOP_MS" \
  --max-wait-ms "$MAX_WAIT_MS" \
  --num-threads "$NUM_THREADS" \
  --max-active-connections "$MAX_ACTIVE" \
  --max-queue-size "$MAX_QUEUE" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"


