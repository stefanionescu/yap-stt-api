#!/usr/bin/env bash
set -euo pipefail

# Enhanced entrypoint that replicates scripts/03_start_server.sh + 04_status.sh + 05_smoke_test.sh

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/environment.sh"

# Config files
YAP_CONFIG_RUNTIME="${YAP_CONFIG}.runtime"
LOG_FILE="${YAP_LOG_DIR}/yap-server.log"

echo "[entrypoint] Yap STT container starting..."
echo "[entrypoint] Using base config: ${YAP_CONFIG}"

# Create required directories
mkdir -p "${HF_HOME}" "${YAP_LOG_DIR}"

# Inject API key into runtime config (matches 03_start_server.sh logic)
KYU_KEY="${KYUTAI_API_KEY:-}"
if [ -n "${KYU_KEY}" ]; then
    echo "[entrypoint] Injecting KYUTAI_API_KEY into authorized_ids"
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
    echo "[entrypoint] Effective config: ${YAP_CONFIG}"
    grep -n "authorized_ids" "${YAP_CONFIG}" || true
else
    echo "[entrypoint] WARNING: KYUTAI_API_KEY not set. Using base authorized_ids from config."
    export YAP_CONFIG="${YAP_CONFIG}"
fi

# Function to check server status (matches 04_status.sh)
check_status() {
    echo "[entrypoint] Server status:"
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
    echo "[entrypoint] Running smoke test with warmup.py..."
    if [ -f "/workspace/samples/mid.wav" ] && [ -n "${KYUTAI_API_KEY:-}" ]; then
        cd /workspace
        timeout 30s python3 test/warmup.py --server 127.0.0.1:${YAP_PORT} --rtf ${SMOKETEST_RTF} --kyutai-key "${KYUTAI_API_KEY}" || {
            echo "[entrypoint] Smoke test failed or timed out"
            return 1
        }
        echo "[entrypoint] ✅ Smoke test passed"
    else
        echo "[entrypoint] Skipping smoke test (missing audio file or API key)"
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
        echo "[entrypoint] Starting yap-server in tmux session '${TMUX_SESSION}'..."
        
        # Kill existing session if present
        tmux has-session -t "${TMUX_SESSION}" 2>/dev/null && tmux kill-session -t "${TMUX_SESSION}"
        
        # Start server in tmux (matches 03_start_server.sh)
        tmux new-session -d -s "${TMUX_SESSION}" \
            "exec $* 2>&1 | tee '${LOG_FILE}'"
        
        # Wait for server to be ready (matches 03_start_server.sh)
        echo "[entrypoint] Waiting for server to start on port ${YAP_PORT}..."
        READY_TIMEOUT=180
        for i in $(seq 1 ${READY_TIMEOUT}); do
            if (exec 3<>/dev/tcp/${YAP_CLIENT_HOST}/${YAP_PORT}) 2>/dev/null; then
                exec 3>&-
                break
            fi
            sleep 1
            if [ $i -eq ${READY_TIMEOUT} ]; then
                echo "[entrypoint] ERROR: Server did not start within ${READY_TIMEOUT}s" >&2
                echo "[entrypoint] Last 20 log lines:" >&2
                tail -n 20 "${LOG_FILE}" 2>/dev/null || echo "(no log)"
                exit 1
            fi
        done
        
        echo "[entrypoint] ✅ Server ready on ${YAP_ADDR}:${YAP_PORT}"
        echo "[entrypoint] WebSocket endpoint: ws://${YAP_CLIENT_HOST}:${YAP_PORT}/api/asr-streaming"
        echo "[entrypoint] Logs: ${LOG_FILE}"
        
        # Optional smoke test
        if [ "${RUN_SMOKE_TEST:-}" = "1" ]; then
            sleep 2
            run_smoke_test || echo "[entrypoint] Warning: Smoke test failed"
        fi
        
        # Keep container running and show status
        echo "[entrypoint] Server running. Use 'docker exec <container> status' to check status."
        echo "[entrypoint] Use 'docker exec <container> test' to run smoke test."
        
        # Keep tmux session alive
        while tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; do
            sleep 10
        done
        echo "[entrypoint] Server session ended"
        ;;
    *)
        # Direct command execution
        echo "[entrypoint] Exec: $*"
        exec "$@"
        ;;
esac