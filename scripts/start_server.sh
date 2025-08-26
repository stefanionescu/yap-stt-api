#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"

PORT=${PORT:-8000}
# Concurrency/perf knobs
MAX_BATCH=${MAX_BATCH:-16}          # 8–24 is sensible on L40/L40S for 80ms CTC
MAX_WAIT_MS=${MAX_WAIT_MS:-15}      # coalescing delay for batcher
NUM_THREADS=${NUM_THREADS:-1}
MAX_ACTIVE=${MAX_ACTIVE:-400}
MAX_QUEUE=${MAX_QUEUE:-32768}

MODEL="$ROOT/models/nemo_ctc_80ms/model.onnx"
TOKENS="$ROOT/models/nemo_ctc_80ms/tokens.txt"
BIN="$ROOT/bin/sherpa-onnx-online-websocket-server"
LOG="$ROOT/logs/server.out"

mkdir -p "$ROOT/logs"

[ -f "$MODEL" ]  || { echo "Missing model: $MODEL"; exit 1; }
[ -f "$TOKENS" ] || { echo "Missing tokens: $TOKENS"; exit 1; }
[ -x "$BIN" ]    || { echo "Server bin not found or not executable: $BIN"; echo "Run scripts/build_ws_server.sh"; exit 2; }

echo "[start] sherpa-onnx ONLINE WS (NeMo CTC, CUDA) :$PORT"
nohup "$BIN" \
  --port="$PORT" \
  --nemo-ctc="$MODEL" \
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
