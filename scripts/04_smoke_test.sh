#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

export PATH="$HOME/.local/bin:$PATH"
echo "[04] Smoke test…"

AUDIO="${DSM_REPO_DIR}/audio/bria.mp3"
[ -f "${AUDIO}" ] || { echo "[04] Missing audio at ${AUDIO}"; exit 1; }

SERVER_URL="${MOSHI_PUBLIC_WS_URL:-ws://${MOSHI_CLIENT_HOST}:${MOSHI_PORT}}"
echo "[04] Server: ${SERVER_URL} | RTF=${SMOKETEST_RTF}"

uv run "${DSM_REPO_DIR}/scripts/stt_from_file_rust_server.py" \
  --url "${SERVER_URL}" \
  --rtf "${SMOKETEST_RTF}" \
  "${AUDIO}"