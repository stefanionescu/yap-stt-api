#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
# Concurrency/perf knobs
MAX_BATCH=${MAX_BATCH:-16}
NN_POOL=${NN_POOL:-4}
MAX_WAIT_MS=${MAX_WAIT_MS:-15}
NUM_THREADS=${NUM_THREADS:-1}
MAX_ACTIVE=${MAX_ACTIVE:-400}
MAX_QUEUE=${MAX_QUEUE:-32768}

LOG="$ROOT/logs/server.out"
MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
PROVIDER=${PROVIDER:-cuda}

mkdir -p "$ROOT/logs"

echo "[diag] ORT providers:"
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY

[ -f "$MODEL" ] || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }

SERVER_PY="$ROOT/repos/sherpa-onnx/python-api-examples/online_websocket_server.py"
[ -f "$SERVER_PY" ] || { echo "Cannot find $SERVER_PY (update submodule/clone?)"; exit 2; }

# Sanity: ensure this server supports --nemo-ctc
if ! python "$SERVER_PY" --help 2>&1 | grep -q -- "--nemo-ctc"; then
  echo "online_websocket_server.py here doesn’t expose --nemo-ctc (older checkout?)."
  echo "Update repo to latest v1.12.x, or build the C++ WS server (see docs)."
  exit 3
fi

echo "[start] sherpa-onnx ONLINE WS (NeMo CTC) :$PORT"
nohup python "$SERVER_PY" \
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
