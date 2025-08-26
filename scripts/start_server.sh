#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
source "$ROOT/.venv/bin/activate"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}      # 8–24 are good starts on L40/L40S
NN_POOL=${NN_POOL:-4}           # 3–6 ORT sessions
MAX_WAIT_MS=${MAX_WAIT_MS:-15}  # batching tick
PROVIDER=${PROVIDER:-cuda}      # or tensorrt if you built TRT EP

LOG="$ROOT/logs/server.out"
MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"

mkdir -p "$ROOT/logs"

echo "[diag] ORT providers:"
python - <<'PY'
import onnxruntime as ort; print(ort.get_available_providers())
PY

[ -f "$MODEL" ]  || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }

echo "[start] sherpa-onnx ONLINE WS (NeMo CTC) :$PORT"
# NOTE: arguments use --key=value form for the C++ server
nohup sherpa-onnx-online-websocket-server \
  --port="$PORT" \
  --max-batch-size="$MAX_BATCH" \
  --nn-pool-size="$NN_POOL" \
  --max-wait-ms="$MAX_WAIT_MS" \
  --provider="$PROVIDER" \
  --tokens="$TOKENS" \
  --nemo-ctc-model="$MODEL" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"


