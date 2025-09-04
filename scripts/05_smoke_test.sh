#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

export PATH="$HOME/.local/bin:$PATH"
echo "[05] Smoke test…"

AUDIO="${DSM_REPO_DIR}/audio/bria.mp3"
[ -f "${AUDIO}" ] || { echo "[05] Missing audio at ${AUDIO}"; exit 1; }

SERVER_URL="${YAP_PUBLIC_WS_URL:-ws://${YAP_CLIENT_HOST}:${YAP_PORT}}"
echo "[05] Server: ${SERVER_URL} | RTF=${SMOKETEST_RTF}"

uv run "${DSM_REPO_DIR}/scripts/stt_from_file_rust_server.py" \
  --url "${SERVER_URL}" \
  --rtf "${SMOKETEST_RTF}" \
  "${AUDIO}"


