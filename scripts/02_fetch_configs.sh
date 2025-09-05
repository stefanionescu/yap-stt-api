#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[02] Fetching DSM repo…"

if [ ! -d "${DSM_REPO_DIR}" ]; then
  git clone --depth=1 https://github.com/kyutai-labs/delayed-streams-modeling "${DSM_REPO_DIR}"
else
  git -C "${DSM_REPO_DIR}" pull --ff-only || true
fi

echo "[02] Using config: ${YAP_CONFIG}"
if [ -f "${YAP_CONFIG}" ]; then
  echo "[02] ✓ Found local config (no changes made)"
else
  echo "[02] ✗ Config not found at ${YAP_CONFIG}"
  echo "    Please ensure your repo contains server/config-stt-en_fr-hf.toml or set YAP_CONFIG in scripts/.env"
  exit 1
fi