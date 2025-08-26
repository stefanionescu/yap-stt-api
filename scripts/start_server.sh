#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}         # try 8–24 on L40/L40S
NN_POOL=${NN_POOL:-4}              # number of ORT sessions (3–6 typical)
MAX_WAIT_MS=${MAX_WAIT_MS:-15}     # batching coalesce delay
NUM_THREADS=${NUM_THREADS:-1}      # ORT CPU hint
MAX_ACTIVE=${MAX_ACTIVE:-400}      # connection cap
MAX_QUEUE=${MAX_QUEUE:-32768}      # per-conn msg queue
PROVIDER=${PROVIDER:-cuda}

MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
LOG="$ROOT/logs/server.out"

mkdir -p "$ROOT/logs"

echo "[diag] ORT providers:"
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY

[ -f "$MODEL" ]  || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }

echo "[start] sherpa-onnx Python WS (NeMo CTC) on :$PORT"
nohup python "$ROOT/repos/sherpa-onnx/python-api-examples/streaming_server.py" \
  --provider "$PROVIDER" \
  --port "$PORT" \
  --tokens "$TOKENS" \
  --nemo-ctc "$MODEL" \
  --nn-pool-size "$NN_POOL" \
  --max-batch-size "$MAX_BATCH" \
  --max-wait-ms "$MAX_WAIT_MS" \
  --num-threads "$NUM_THREADS" \
  --max-active-connections "$MAX_ACTIVE" \
  --max-queue-size "$MAX_QUEUE" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"
