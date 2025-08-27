#!/usr/bin/env bash
set -euo pipefail
echo "[01] Installing moshi-server (CUDA)…"

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

# Force reinstall only if missing. (If you want to force: cargo uninstall moshi-server)
if ! command -v moshi-server >/dev/null 2>&1; then
  cargo install --features cuda moshi-server
else
  echo "[01] moshi-server already installed, skipping."
fi

echo "[01] moshi-server location: $(command -v moshi-server)"
