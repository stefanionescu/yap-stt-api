#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}
LOOP_MS=${LOOP_MS:-15}
NUM_THREADS=${NUM_THREADS:-1}
MAX_ACTIVE=${MAX_ACTIVE:-400}
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

echo "[start] sherpa-onnx ONLINE WS (NeMo CTC) :$PORT"
nohup python "$ROOT/scripts/ws_server_nemo_ctc.py" \
  --model "$MODEL" \
  --tokens "$TOKENS" \
  --provider "$PROVIDER" \
  --num-threads "$NUM_THREADS" \
  --port "$PORT" \
  --max-batch-size "$MAX_BATCH" \
  --loop-ms "$LOOP_MS" \
  --max-active "$MAX_ACTIVE" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"
