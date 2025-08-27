#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
echo "[04] Running smoke test (file → server)…"

# Use test audio from the repo
AUDIO="${DSM_REPO_DIR}/audio/bria.mp3"
if [ ! -f "${AUDIO}" ]; then
  echo "[04] Test audio missing at ${AUDIO}"; exit 1
fi

SERVER_URL="ws://${MOSHI_ADDR}:${MOSHI_PORT}"

# The Kyutai client script uses uv-run; RTF=1 simulates real-time; increase to 1000 for max speed.
echo "[04] Server: ${SERVER_URL} | RTF=${SMOKETEST_RTF}"
uv run "${DSM_REPO_DIR}/scripts/stt_from_file_rust_server.py" \
  --server "${SERVER_URL}" \
  --rtf "${SMOKETEST_RTF}" \
  "${AUDIO}"
