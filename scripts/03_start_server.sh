#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export HF_HOME HF_HUB_ENABLE_HF_TRANSFER

LOG_FILE="${MOSHI_LOG_DIR}/moshi-server.log"
SESSION="${TMUX_SESSION}"

echo "[03] Starting moshi-server in tmux '${SESSION}'…"

# Show current batch_size configuration
echo "[03] Current batch_size configuration:"
if [ -f "${MOSHI_CONFIG}" ]; then
  grep -n "batch_size" "${MOSHI_CONFIG}" || echo "   No batch_size found in config"
else
  echo "   Config file not found: ${MOSHI_CONFIG}"
fi

tmux has-session -t "${SESSION}" 2>/dev/null && tmux kill-session -t "${SESSION}"

tmux new-session -d -s "${SESSION}" \
  "MOSHI_ADDR=${MOSHI_ADDR} MOSHI_PORT=${MOSHI_PORT} HF_HOME=${HF_HOME} HF_HUB_ENABLE_HF_TRANSFER=${HF_HUB_ENABLE_HF_TRANSFER} \
   moshi-server worker --config '${MOSHI_CONFIG}' --addr '${MOSHI_ADDR}' --port '${MOSHI_PORT}' 2>&1 | tee '${LOG_FILE}'"

# Wait for port to listen
for i in {1..30}; do
  if (exec 3<>/dev/tcp/${MOSHI_CLIENT_HOST}/${MOSHI_PORT}) 2>/dev/null; then
    exec 3>&-; break
  fi
  sleep 1
done

LOCAL_URL="ws://${MOSHI_CLIENT_HOST}:${MOSHI_PORT}"
BIND_URL="ws://${MOSHI_ADDR}:${MOSHI_PORT}"
echo "[03] Bound at: ${BIND_URL}"
echo "[03] Local client URL: ${LOCAL_URL}"
[ -n "${MOSHI_PUBLIC_WS_URL}" ] && echo "[03] Public proxy URL: ${MOSHI_PUBLIC_WS_URL}"
echo "[03] Log: ${LOG_FILE}"

# Wait a moment for server to initialize and log configuration
sleep 3
echo "[03] Verifying batch_size configuration in logs:"
if [ -f "${LOG_FILE}" ]; then
  grep -i "batch" "${LOG_FILE}" | tail -3 || echo "   No batch-related logs found yet"
else
  echo "   Log file not created yet"
fi