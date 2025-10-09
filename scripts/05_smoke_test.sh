#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

echo "[05] Smoke test using warmup.py..."

# Use local samples instead of external DSM repo
AUDIO_FILE="samples/mid.wav"
if [ ! -f "${AUDIO_FILE}" ]; then
    echo "[05] Missing audio file: ${AUDIO_FILE}" >&2
    exit 1
fi

SERVER_URL="ws://${YAP_CLIENT_HOST}:${YAP_PORT}"
echo "[05] Server: ${SERVER_URL} | RTF=${SMOKETEST_RTF}"

# Run warmup.py as smoke test
if [ -n "${KYUTAI_API_KEY:-}" ]; then
    cd "$(dirname "$0")/.."
    python3 test/warmup.py \
        --server "${YAP_CLIENT_HOST}:${YAP_PORT}" \
        --rtf "${SMOKETEST_RTF}" \
        --kyutai-key "${KYUTAI_API_KEY}" \
        --file "${AUDIO_FILE}"
    echo "[05] ✅ Smoke test completed"
else
    echo "[05] ERROR: KYUTAI_API_KEY not set. Cannot run smoke test." >&2
    exit 1
fi