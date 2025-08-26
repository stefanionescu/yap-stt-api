#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}          # 8–24 is a good starting range on L40/L40S
NN_POOL=${NN_POOL:-4}               # number of ORT sessions; 3–6 typical
MAX_WAIT_MS=${MAX_WAIT_MS:-15}      # micro-batching window
NUM_THREADS=${NUM_THREADS:-1}       # ORT CPU threads (keep low)
MAX_ACTIVE=${MAX_ACTIVE:-400}       # connection cap
MAX_QUEUE=${MAX_QUEUE:-32768}       # per-connection inbound queue
PROVIDER=${PROVIDER:-cuda}          # cuda | tensorrt | cpu

MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
LOG="$ROOT/logs/server.out"
SRV_BIN="$ROOT/.venv/bin/sherpa-onnx-online-websocket-server"

mkdir -p "$ROOT/logs"

echo "[diag] ORT providers:"
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY

[ -x "$SRV_BIN" ] || { echo "Server bin not found: $SRV_BIN"; exit 1; }
[ -f "$MODEL" ] || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }

echo "[start] sherpa-onnx ONLINE WS (NeMo CTC) :$PORT"
# NOTE: --nemo-ctc-model and --tokens are the correct flags for NeMo CTC
nohup "$SRV_BIN" \
  --provider "$PROVIDER" \
  --port "$PORT" \
  --max-batch-size "$MAX_BATCH" \
  --nn-pool-size "$NN_POOL" \
  --max-wait-ms "$MAX_WAIT_MS" \
  --max-active-connections "$MAX_ACTIVE" \
  --max-queue-size "$MAX_QUEUE" \
  --num-threads "$NUM_THREADS" \
  --tokens "$TOKENS" \
  --nemo-ctc-model "$MODEL" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"
