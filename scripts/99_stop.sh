#!/usr/bin/env bash
set -euo pipefail
SESSION="${TMUX_SESSION:-moshi-stt}"
if tmux has-session -t "${SESSION}" 2>/dev/null; then
  tmux kill-session -t "${SESSION}"
  echo "[06] Stopped tmux session '${SESSION}'."
else
  echo "[06] Session '${SESSION}' not running."
fi
