#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate
cd "${HOME}/streaming-sensevoice"

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export DEVICE="cuda:0"
export SENSEVOICE_MODEL_PATH="iic/SenseVoiceSmall"
export CHUNK_DURATION="0.10"
export VAD_THRESHOLD="0"
export VAD_MIN_SILENCE_DURATION_MS="0"

# Keep everything on one process to avoid duplicating VRAM
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export UVICORN_WORKERS=1
export CUDA_DEVICE_MAX_CONNECTIONS=32
export NVIDIA_TF32_OVERRIDE=1
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:64,expandable_segments:True

HOST="0.0.0.0"
PORT="8000"
CMD="python realtime_ws_server_demo.py --HOST ${HOST} --PORT ${PORT}"

SESSION="sensevoice"
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" "bash -lc '${CMD}'"

sleep 2
echo "Server up in tmux '${SESSION}'."
echo "WS: ws://<PUBLIC_HOST>:${PORT}/api/realtime/ws?chunk_duration=${CHUNK_DURATION}&vad_threshold=${VAD_THRESHOLD}&vad_min_silence_duration_ms=${VAD_MIN_SILENCE_DURATION_MS}"
echo "Logs: tmux attach -t ${SESSION}"
