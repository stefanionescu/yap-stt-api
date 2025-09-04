#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[04] Status"

echo "tmux sessions:"
tmux ls || true
echo

echo "Listening sockets:"
ss -lntp | grep -E ":${YAP_PORT}\b" || echo "(none)"
echo

echo "Last 20 log lines:"
tail -n 20 "${YAP_LOG_DIR}/yap-server.log" || echo "(no log yet)"


