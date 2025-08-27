#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export HF_HOME HF_HUB_ENABLE_HF_TRANSFER
ulimit -n 1048576 || true

LOG_FILE="${MOSHI_LOG_DIR}/moshi-server.log"
SESSION="${TMUX_SESSION}"

echo "[03] Starting moshi-server in tmux session '${SESSION}'…"
# Kill prior session if exists
tmux has-session -t "${SESSION}" 2>/dev/null && tmux kill-session -t "${SESSION}"

# Start server (no VAD flags; pure streaming STT). Addr/port are CLI flags (not in TOML).
tmux new-session -d -s "${SESSION}" \
  "MOSHI_ADDR=${MOSHI_ADDR} MOSHI_PORT=${MOSHI_PORT} HF_HOME=${HF_HOME} HF_HUB_ENABLE_HF_TRANSFER=${HF_HUB_ENABLE_HF_TRANSFER} \
   moshi-server worker --config '${MOSHI_CONFIG}' --addr '${MOSHI_ADDR}' --port '${MOSHI_PORT}' 2>&1 | tee '${LOG_FILE}'"

# Wait for bind
sleep 2
echo "[03] Server log: ${LOG_FILE}"
echo "[03] Proxy endpoint (inside pod): ws://${MOSHI_ADDR}:${MOSHI_PORT}"
