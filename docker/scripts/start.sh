#!/usr/bin/env bash
set -euo pipefail

# Enhanced start that replicates scripts/03_start_server.sh + 04_status.sh + 05_smoke_test.sh

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/environment.sh"

# Config files
YAP_CONFIG_RUNTIME="${YAP_CONFIG}.runtime"
LOG_FILE="${YAP_LOG_DIR}/yap-server.log"

echo "[start] Yap STT container starting..."
echo "[start] Using base config: ${YAP_CONFIG}"

# Create required directories
mkdir -p "${HF_HOME}" "${YAP_LOG_DIR}"

# Inject API key into runtime config (matches 03_start_server.sh logic)
KYU_KEY="${KYUTAI_API_KEY:-}"
if [ -n "${KYU_KEY}" ]; then
    echo "[start] Injecting KYUTAI_API_KEY into authorized_ids"
    awk -v key="${KYU_KEY}" '
        BEGIN { replaced = 0 }
        /^[[:space:]]*authorized_ids[[:space:]]*=/ {
            if (!replaced) {
                print "authorized_ids = [\047" key "\047]"
                replaced = 1
            }
            next
        }
        { print }
        END {
            if (!replaced) {
                print "authorized_ids = [\047" key "\047]"
            }
        }
    ' "${YAP_CONFIG}" > "${YAP_CONFIG_RUNTIME}"
    export YAP_CONFIG="${YAP_CONFIG_RUNTIME}"
    echo "[start] Effective config: ${YAP_CONFIG}"
    grep -n "authorized_ids" "${YAP_CONFIG}" || true
else
    echo "[start] WARNING: KYUTAI_API_KEY not set. Using base authorized_ids from config."
    export YAP_CONFIG="${YAP_CONFIG}"
fi

# Function to check server status (matches 04_status.sh)
check_status() {
    echo "[start] Server status:"
    echo "  tmux sessions:"
    tmux ls 2>/dev/null || echo "    (none)"
    echo "  Listening on port ${YAP_PORT}:"
    ss -lntp 2>/dev/null | grep -E ":${YAP_PORT}\b" || echo "    (not listening)"
    if [ -f "${LOG_FILE}" ]; then
        echo "  Last 10 log lines:"
        tail -n 10 "${LOG_FILE}" | sed 's/^/    /'
    else
        echo "  (no log file yet)"
    fi
}

# Function to run smoke test using warmup.py
run_smoke_test() {
    echo "[start] Running smoke test with warmup.py..."
    if [ -f "/workspace/samples/mid.wav" ] && [ -n "${KYUTAI_API_KEY:-}" ]; then
        cd /workspace
        timeout 30s python3 test/warmup.py --server 127.0.0.1:${YAP_PORT} --rtf ${SMOKETEST_RTF} --kyutai-key "${KYUTAI_API_KEY}" || {
            echo "[start] Smoke test failed or timed out"
            return 1
        }
        echo "[start] ✅ Smoke test passed"
    else
        echo "[start] Skipping smoke test (missing audio file or API key)"
    fi
}

# Handle different startup modes
case "${1:-}" in
    "status")
        check_status
        exit 0
        ;;
    "test")
        run_smoke_test
        exit 0
        ;;
    "yap-server")
        # Default server startup mode
        echo "[start] Starting yap-server in tmux session '${TMUX_SESSION}'..."
        
        # Prefetch: validate config to trigger model/tokenizer downloads (matches 03_start_server.sh)
        echo "[start] Prefetching weights (validate)..."
        set +e
        yap-server validate "${YAP_CONFIG}" || true
        set -e
        
        # Build launch command that always uses the effective ${YAP_CONFIG}.
        # We strip any user-provided --config/--addr/--port and append ours,
        # so the runtime-injected config is honored even if CMD hardcodes a path.
        ARGS=("$@")
        LAUNCH_CMD="$*"
        if [ "${ARGS[0]:-}" = "yap-server" ]; then
            FILTERED=()
            i=0
            while [ $i -lt ${#ARGS[@]} ]; do
                case "${ARGS[$i]}" in
                    --config|--addr|--port)
                        i=$((i+2))
                        continue
                        ;;
                esac
                FILTERED+=("${ARGS[$i]}")
                i=$((i+1))
            done
            FILTERED+=(--config "${YAP_CONFIG}" --addr "${YAP_ADDR}" --port "${YAP_PORT}")
            LAUNCH_CMD="$(printf "%s " "${FILTERED[@]}")"
        fi
        echo "[start] Launch: ${LAUNCH_CMD}"

        # Kill existing session if present
        tmux has-session -t "${TMUX_SESSION}" 2>/dev/null && tmux kill-session -t "${TMUX_SESSION}"
        
        # Start server in tmux with full environment (matches 03_start_server.sh exactly)
        tmux new-session -d -s "${TMUX_SESSION}" \
            "LD_LIBRARY_PATH='${LD_LIBRARY_PATH}' PATH='${PATH}' CUDA_HOME='${CUDA_HOME}' CUDA_PATH='${CUDA_PATH}' CUDA_ROOT='${CUDA_ROOT}' CUDA_COMPUTE_CAP='${CUDA_COMPUTE_CAP}' \
             CUDARC_NVRTC_PATH='${CUDARC_NVRTC_PATH}' HF_HOME='${HF_HOME}' HF_HUB_ENABLE_HF_TRANSFER='${HF_HUB_ENABLE_HF_TRANSFER}' \
             exec ${LAUNCH_CMD} 2>&1 | tee '${LOG_FILE}'"
        
        # Wait for server to be ready (matches 03_start_server.sh)
        echo "[start] Waiting for server to start on port ${YAP_PORT}..."
        READY_TIMEOUT=180
        for i in $(seq 1 ${READY_TIMEOUT}); do
            if (exec 3<>/dev/tcp/${YAP_CLIENT_HOST}/${YAP_PORT}) 2>/dev/null; then
                exec 3>&-
                break
            fi
            sleep 1
            if [ $i -eq ${READY_TIMEOUT} ]; then
                echo "[start] ERROR: Server did not start within ${READY_TIMEOUT}s" >&2
                echo "[start] Last 20 log lines:" >&2
                tail -n 20 "${LOG_FILE}" 2>/dev/null || echo "(no log)"
                exit 1
            fi
        done
        
        echo "[start] ✅ Server ready on ${YAP_ADDR}:${YAP_PORT}"
        echo "[start] WebSocket endpoint: ws://${YAP_CLIENT_HOST}:${YAP_PORT}/api/asr-streaming"
        echo "[start] Logs: ${LOG_FILE}"
        
        # Optional smoke test
        if [ "${RUN_SMOKE_TEST:-}" = "1" ]; then
            sleep 2
            run_smoke_test || echo "[start] Warning: Smoke test failed"
        fi
        
        # Keep container running and show status
        echo "[start] Server running. Use 'docker exec <container> status' to check status."
        echo "[start] Use 'docker exec <container> test' to run smoke test."
        
        # Keep tmux session alive
        while tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; do
            sleep 10
        done
        echo "[start] Server session ended"
        ;;
    *)
        # Direct command execution
        echo "[start] Exec: $*"
        exec "$@"
        ;;
esac