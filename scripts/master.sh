#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

# Create a default .env once (optional)
if [ ! -f "${ROOT_DIR}/.env" ]; then
  cat > "${ROOT_DIR}/.env" <<'EOF'
HF_HOME=/workspace/hf_cache
HF_HUB_ENABLE_HF_TRANSFER=1
MOSHI_ADDR=0.0.0.0
MOSHI_PORT=8000
# Client should usually hit localhost (inside pod) or your Runpod proxy URL:
MOSHI_CLIENT_HOST=127.0.0.1
# MOSHI_PUBLIC_WS_URL=wss://<RUNPOD_ID>-8000.proxy.runpod.net   # optional
MOSHI_LOG_DIR=/workspace/logs
DSM_REPO_DIR=/workspace/delayed-streams-modeling
MOSHI_CONFIG=/workspace/moshi-stt.toml
TMUX_SESSION=moshi-stt
SMOKETEST_RTF=1000
EOF
  echo "[master] Wrote default .env"
fi

chmod +x "${ROOT_DIR}/"*.sh

"${ROOT_DIR}/00_prereqs.sh"
"${ROOT_DIR}/01_install_moshi_server.sh"
"${ROOT_DIR}/02_fetch_configs.sh"
"${ROOT_DIR}/03_start_server.sh"
sleep 6
"${ROOT_DIR}/05_status.sh"
"${ROOT_DIR}/04_smoke_test.sh"

echo
echo "=== Up. tmux session '${TMUX_SESSION}' on ${MOSHI_ADDR}:${MOSHI_PORT} ==="
echo "Stop: ${ROOT_DIR}/99_stop.sh"
