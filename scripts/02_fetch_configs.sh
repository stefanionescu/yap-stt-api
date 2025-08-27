#!/usr/bin/env bash
set -euo pipefail
echo "[02] Cloning Kyutai DSM repo (for configs & scripts)…"

if [ ! -d "${DSM_REPO_DIR}" ]; then
  git clone --depth=1 https://github.com/kyutai-labs/delayed-streams-modeling "${DSM_REPO_DIR}"
else
  echo "[02] Repo exists; pulling latest..."
  git -C "${DSM_REPO_DIR}" pull --ff-only || true
fi

# Copy the STT (1B en/fr, Hugging Face backend) config locally.
# File name is 'config-stt-en_fr-hf.toml' in the official repo.
cp "${DSM_REPO_DIR}/configs/config-stt-en_fr-hf.toml" "${MOSHI_CONFIG}"

echo "[02] Using config: ${MOSHI_CONFIG}"
