#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

export PATH="${CUDA_PREFIX}/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export HF_HOME HF_HUB_ENABLE_HF_TRANSFER

LOG_FILE="${YAP_LOG_DIR}/yap-server.log"
SESSION="${TMUX_SESSION}"

echo "[03] Starting yap-server in tmux '${SESSION}'…"

# CUDA sanity checks before starting server
echo "[03] CUDA sanity:"
echo "  Driver says CUDA: $(nvidia-smi | awk -F'CUDA Version: ' '/CUDA Version/ {print $2}' | awk '{print $1}' | head -n1)"
echo "  nvcc: $(nvcc --version | sed -n 's/^.*release //p' | head -n1)"
echo "  Using CUDA prefix: ${CUDA_PREFIX}"
echo "  LD_LIBRARY_PATH: ${LD_LIBRARY_PATH}"
echo "  CUDA_COMPUTE_CAP: ${CUDA_COMPUTE_CAP}"
echo "  NVRTC chosen: $(ldconfig -p | awk '/libnvrtc\\.so/{print $NF; exit}')"

# Show all CUDA libs the loader will see first
ldconfig -p | grep -E 'lib(cudart|nvrtc|cuda)\.so' | sort -u | sed 's/^/    /'

# Show config file being used
echo "[03] Using config file: ${YAP_CONFIG}"

# Ensure CUDARC_NVRTC_PATH is set for the server process
export CUDARC_NVRTC_PATH="${CUDA_PREFIX}/lib64/libnvrtc.so"

# Prepare runtime config with Kyutai API key injected into authorized_ids
# Note: This is the Kyutai server key, not a RunPod token
TMP_CONFIG="${YAP_CONFIG}.runtime"
if [ "${KYUTAI_API_KEY:-}" != "" ]; then
  EFFECTIVE_KEY="${KYUTAI_API_KEY:-}"
  echo "[03] Writing runtime config with authorized_ids = ['${EFFECTIVE_KEY}'] -> ${TMP_CONFIG}"
  awk -v key="${EFFECTIVE_KEY}" '
    BEGIN{done=0}
    /^authorized_ids\s*=\s*\[/ {
      print "authorized_ids = [\x27" key "\x27]"; done=1; next
    }
    { print }
    END{ if (!done) print "authorized_ids = [\x27" key "\x27]" }
  ' "${YAP_CONFIG}" > "${TMP_CONFIG}"
  export YAP_CONFIG="${TMP_CONFIG}"
else
  echo "[03] KYUTAI_API_KEY not set; using existing authorized_ids in ${YAP_CONFIG}"
fi

# Prefetch: validate config to trigger model/tokenizer downloads before starting the server
echo "[03] Prefetching weights (validate)..."
set +e
yap-server validate "${YAP_CONFIG}" || true
set -e

tmux has-session -t "${SESSION}" 2>/dev/null && tmux kill-session -t "${SESSION}"

SERVER_BIN="$(command -v yap-server)"
tmux new-session -d -s "${SESSION}" \
  "LD_LIBRARY_PATH='${LD_LIBRARY_PATH}' PATH='${PATH}' CUDA_HOME='${CUDA_HOME}' CUDA_PATH='${CUDA_PATH}' CUDA_ROOT='${CUDA_ROOT}' CUDA_COMPUTE_CAP='${CUDA_COMPUTE_CAP}' \
   CUDARC_NVRTC_PATH='${CUDARC_NVRTC_PATH}' HF_HOME='${HF_HOME}' HF_HUB_ENABLE_HF_TRANSFER='${HF_HUB_ENABLE_HF_TRANSFER}' \
   ${SERVER_BIN} worker --config '${YAP_CONFIG}' --addr '${YAP_ADDR}' --port '${YAP_PORT}' 2>&1 | tee '${LOG_FILE}'"

# Wait for port to listen with explicit timeout (first run may download weights)
READY_TIMEOUT=180
for i in $(seq 1 ${READY_TIMEOUT}); do
  if (exec 3<>/dev/tcp/${YAP_CLIENT_HOST}/${YAP_PORT}) 2>/dev/null; then
    exec 3>&-; break
  fi
  sleep 1
  if [ $i -eq ${READY_TIMEOUT} ]; then
    echo "[03] ERROR: Server did not open port ${YAP_PORT} within ${READY_TIMEOUT}s" >&2
    echo "[03] Last 50 log lines:" >&2
    tail -n 50 "${LOG_FILE}" || true
    exit 1
  fi
done

LOCAL_URL="ws://${YAP_CLIENT_HOST}:${YAP_PORT}"
BIND_URL="ws://${YAP_ADDR}:${YAP_PORT}"
echo "[03] Bound at: ${BIND_URL}"
echo "[03] Local client URL: ${LOCAL_URL}"
[ -n "${YAP_PUBLIC_WS_URL}" ] && echo "[03] Public proxy URL: ${YAP_PUBLIC_WS_URL}"
echo "[03] Log: ${LOG_FILE}"

# Wait a moment for server to initialize
sleep 3
echo "[03] Server initialization complete. Check log file for details: ${LOG_FILE}"