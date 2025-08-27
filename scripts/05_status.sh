#!/usr/bin/env bash
set -euo pipefail
echo "[05] Status"
echo "tmux sessions:"
tmux ls || true
echo
echo "Listening sockets:"
ss -lntp | grep -E ":${MOSHI_PORT}\b" || true
echo
echo "Last 20 log lines:"
tail -n 20 "${MOSHI_LOG_DIR}/moshi-server.log" || true
