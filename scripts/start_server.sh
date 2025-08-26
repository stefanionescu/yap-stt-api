#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
BIN="$ROOT/bin/sherpa-onnx-online-websocket-server"
ENVFILE="$ROOT/.env.sherpa_ws"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}
MAX_WAIT_MS=${MAX_WAIT_MS:-15}
NUM_THREADS=${NUM_THREADS:-1}
MAX_ACTIVE=${MAX_ACTIVE:-400}
MAX_QUEUE=${MAX_QUEUE:-32768}

MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
LOG="$ROOT/logs/server.out"

[ -x "$BIN" ]    || { echo "Missing binary: $BIN (run scripts/build_ws_server_gpu.sh)"; exit 2; }
[ -f "$MODEL" ]  || { echo "Missing model: $MODEL"; exit 3; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 4; }
[ -f "$ENVFILE" ] && source "$ENVFILE"

mkdir -p "$ROOT/logs"

# Detect which flag the C++ server exposes for CTC models
HELP=$("$BIN" --help 2>&1 || true)

CTC_FLAG=""
if   echo "$HELP" | grep -q -- "--nemo-ctc";   then CTC_FLAG="--nemo-ctc"
elif echo "$HELP" | grep -q -- "--ctc-model";  then CTC_FLAG="--ctc-model"
fi

if [ -z "$CTC_FLAG" ]; then
  echo "This sherpa C++ WS binary does not expose a CTC model flag (--nemo-ctc/--ctc-model)."
  echo "Rebuild or use the Python WS server from the repo's python-api-examples (which supports NeMo CTC)."
  exit 5
fi

echo "[start] sherpa-onnx ONLINE WS (CUDA) :$PORT  using CTC flag: $CTC_FLAG"
nohup "$BIN" \
  --port="$PORT" \
  "$CTC_FLAG=$MODEL" \
  --tokens="$TOKENS" \
  --max-batch-size="$MAX_BATCH" \
  --max-wait-ms="$MAX_WAIT_MS" \
  --num-threads="$NUM_THREADS" \
  --max-active-connections="$MAX_ACTIVE" \
  --max-queue-size="$MAX_QUEUE" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"
