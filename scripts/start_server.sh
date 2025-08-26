#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
BIN="$ROOT/bin/sherpa-onnx-online-websocket-server"
MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
ENVFILE="$ROOT/.env.sherpa_ws"
LOG="$ROOT/logs/server.out"

PORT=${PORT:-8000}
MAX_BATCH=${MAX_BATCH:-16}
MAX_WAIT_MS=${MAX_WAIT_MS:-15}
NUM_THREADS=${NUM_THREADS:-1}
MAX_ACTIVE=${MAX_ACTIVE:-400}
MAX_QUEUE=${MAX_QUEUE:-32768}

mkdir -p "$ROOT/logs"

[ -x "$BIN" ]    || { echo "Missing server bin: $BIN (run scripts/build_ws_server_gpu.sh)"; exit 2; }
[ -f "$MODEL" ]  || { echo "Missing model: $MODEL"; exit 3; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 4; }
[ -f "$ENVFILE" ] && source "$ENVFILE"

# Pick the correct model flag by probing --help once
HELP=$("$BIN" --help 2>&1 || true)
if   echo "$HELP" | grep -q -- "--nemo-ctc"; then FLAG="--nemo-ctc"
elif echo "$HELP" | grep -q -- "--ctc-model"; then FLAG="--ctc-model"
elif echo "$HELP" | grep -q -- "--zipformer2-ctc-model"; then FLAG="--zipformer2-ctc-model"
else
  echo "Could not find a CTC model flag in server --help output."
  echo "Available help:"
  echo "$HELP"
  exit 5
fi

echo "[start] sherpa-onnx ONLINE WS (CUDA) on :$PORT  using flag $FLAG"
nohup "$BIN" \
  --port="$PORT" \
  "$FLAG" "$MODEL" \
  --tokens "$TOKENS" \
  --max-batch-size "$MAX_BATCH" \
  --max-wait-ms "$MAX_WAIT_MS" \
  --num-threads "$NUM_THREADS" \
  --max-active-connections "$MAX_ACTIVE" \
  --max-queue-size "$MAX_QUEUE" \
  > "$LOG" 2>&1 & echo $! > "$ROOT/server.pid"

sleep 1
echo "PID: $(cat $ROOT/server.pid)"
echo "Logs: $LOG"
