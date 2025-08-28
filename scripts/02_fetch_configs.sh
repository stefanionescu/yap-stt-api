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

# Update batch_size for higher concurrent stream support (from 64 to 128)
echo "[02] Updating batch_size for concurrent stream support…"
if grep -q "batch_size *= *64" "${MOSHI_CONFIG}"; then
  sed -i 's/^batch_size *= *64/batch_size = 128/' "${MOSHI_CONFIG}"
  echo "[02] ✓ Updated batch_size from 64 to 128"
else
  echo "[02] ⚠ batch_size=64 not found in config, manual verification needed"
fi

echo "[02] Using config: ${MOSHI_CONFIG}"