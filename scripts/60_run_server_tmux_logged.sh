#!/usr/bin/env bash
set -euo pipefail

# ---- config ----
VENV="${HOME}/.venvs/sensevoice"
REPO="${HOME}/streaming-sensevoice"
SESSION="sensevoice"
HOST="0.0.0.0"
PORT="${PORT:-8000}"
LOG_DIR="${HOME}/sensevoice-logs"
KEEP_LOGS=7  # keep last N logs

# ---- env ----
source "${VENV}/bin/activate"
export PYTHONPATH="${REPO}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export DEVICE="cuda:0"
export SENSEVOICE_MODEL_PATH="${SENSEVOICE_MODEL_PATH:-iic/SenseVoiceSmall}"
# No server VAD; Pipecat does segmentation
export CHUNK_DURATION="${CHUNK_DURATION:-0.10}"
export VAD_THRESHOLD="0"
export VAD_MIN_SILENCE_DURATION_MS="0"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export CUDA_DEVICE_MAX_CONNECTIONS=32
export NVIDIA_TF32_OVERRIDE=1
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:64,expandable_segments:True"

mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/server_${TS}.log"
ln -sfn "${LOG_FILE}" "${LOG_DIR}/current.log"

# rotate old logs
ls -1t "${LOG_DIR}"/server_*.log 2>/dev/null | tail -n +$((KEEP_LOGS+1)) | xargs -r rm -f

# pick server module: prefer no-VAD file if present
cd "${REPO}"
if [ -f "${REPO}/realtime_ws_server_novad.py" ]; then
  SERVER_MODULE="realtime_ws_server_novad"
else
  SERVER_MODULE="realtime_ws_server_demo"
fi

# build uvicorn cmd (import module:app so we get env-based config)
UVICORN_CMD="python -m uvicorn ${SERVER_MODULE}:app --host ${HOST} --port ${PORT} --log-level info"

# write a tiny runner so tmux can tee logs cleanly
RUN_SH="${LOG_DIR}/run_${TS}.sh"
cat > "${RUN_SH}" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ulimit -n 65536 || true
# shellcheck disable=SC2154
echo "[boot] $(date -Is) starting: ${UVICORN_CMD}" | tee -a "${LOG_FILE}"
# line-buffered stdout/stderr -> tee
exec stdbuf -oL -eL ${UVICORN_CMD} 2>&1 | tee -a "${LOG_FILE}"
EOS
chmod +x "${RUN_SH}"

# export vars for the runner
export LOG_FILE UVICORN_CMD

# kill any stale session and start fresh
tmux kill-session -t "${SESSION}" 2>/dev/null || true
tmux new-session -d -s "${SESSION}" "bash -lc '${RUN_SH}'"

sleep 1
echo "== Server started in tmux '${SESSION}' =="
echo "Log file: ${LOG_FILE}"
echo "Tail:     tail -f ${LOG_DIR}/current.log"
echo "Attach:   tmux attach -t ${SESSION}"
echo
echo "WS URL (no server VAD):"
echo "  ws://<PUBLIC_HOST>:${PORT}/api/realtime/ws?chunk_duration=${CHUNK_DURATION}&vad_threshold=0&vad_min_silence_duration_ms=0"
