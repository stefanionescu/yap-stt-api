#!/usr/bin/env bash
set -euo pipefail
SESSION=${SESSION:-sherpa}
SCRIPT=${SCRIPT:-03_run_server_single.sh}
LOG=/opt/sherpa-logs/current.log
mkdir -p /opt/sherpa-logs

tmux kill-session -t "$SESSION" >/dev/null 2>&1 || true
tmux new -d -s "$SESSION" "bash $SCRIPT | tee -a $LOG"
echo "== Server started in tmux '$SESSION' =="
echo "Port(s): check your script (default 8000)"
echo "Tail logs: tail -f $LOG"
echo "Attach:   tmux attach -t $SESSION"
