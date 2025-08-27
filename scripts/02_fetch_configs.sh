#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[02] Fetching Kyutai DSM repo…"

if [ ! -d "${DSM_REPO_DIR}" ]; then
  git clone --depth=1 https://github.com/kyutai-labs/delayed-streams-modeling "${DSM_REPO_DIR}"
else
  git -C "${DSM_REPO_DIR}" pull --ff-only || true
fi

cp "${DSM_REPO_DIR}/configs/config-stt-en_fr-hf.toml" "${MOSHI_CONFIG}"
echo "[02] Using config: ${MOSHI_CONFIG}"