#!/usr/bin/env bash
set -euo pipefail
tmux kill-session -t sensevoice 2>/dev/null || true
echo "Stopped tmux session 'sensevoice'."
