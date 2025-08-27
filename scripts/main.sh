#!/usr/bin/env bash
set -euo pipefail

# Bootstrap: run everything in order, no manual steps.
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BASE_DIR

# Load/initialize env
if [ -f "${BASE_DIR}/.env" ]; then
  set -a; source "${BASE_DIR}/.env"; set +a
else
  # Create a default .env if missing
  cat > "${BASE_DIR}/.env" <<'EOF'
# -------- KYUTAI STT RUNPOD ENV --------
HF_HOME=/workspace/hf_cache
HF_HUB_ENABLE_HF_TRANSFER=1
MOSHI_ADDR=0.0.0.0
MOSHI_PORT=8000
MOSHI_LOG_DIR=/workspace/logs
DSM_REPO_DIR=/workspace/delayed-streams-modeling
MOSHI_CONFIG=/workspace/moshi-stt.toml
TMUX_SESSION=moshi-stt
# Optional: real-time factor for smoke test (1 = realtime, 1000 = as fast as possible)
SMOKETEST_RTF=1000
EOF
  echo "[master] Wrote default .env"
  set -a; source "${BASE_DIR}/.env"; set +a
fi

# Ensure scripts are executable
chmod +x "${BASE_DIR}"/scripts/*.sh

# Run each phase
"${BASE_DIR}/scripts/00_prereqs.sh"
"${BASE_DIR}/scripts/01_install_moshi_server.sh"
"${BASE_DIR}/scripts/02_fetch_configs.sh"
"${BASE_DIR}/scripts/03_start_server.sh"
sleep 10
"${BASE_DIR}/scripts/05_status.sh"
"${BASE_DIR}/scripts/04_smoke_test.sh"

echo
echo "=== All done. Server is running in tmux session '${TMUX_SESSION}' on ${MOSHI_ADDR}:${MOSHI_PORT} ==="
echo "Use: scripts/05_status.sh   (tail logs, health)"
echo "Use: scripts/06_stop.sh     (stop and clean session)"
