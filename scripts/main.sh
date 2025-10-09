#!/usr/bin/env bash
set -euo pipefail

# Bootstrap: run everything in order, no manual steps.
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BASE_DIR

# Require Kyutai API key to be exported before running any scripts
if [ -z "${KYUTAI_API_KEY:-}" ]; then
  echo "[main] ERROR: KYUTAI_API_KEY not set. Please 'export KYUTAI_API_KEY=your_secret' before running scripts/main.sh" >&2
  exit 1
fi

# Load/initialize env
if [ -f "${BASE_DIR}/.env" ]; then
  set -a; source "${BASE_DIR}/.env"; set +a
else
  # Create a default .env if missing
  cat > "${BASE_DIR}/.env" <<'EOF'
# -------- YAP STT RUNPOD ENV --------
HF_HOME=/workspace/hf_cache
HF_HUB_ENABLE_HF_TRANSFER=1
YAP_ADDR=0.0.0.0
YAP_PORT=8000
YAP_LOG_DIR=/workspace/logs
# Point to your local repo config; leave unset to use scripts/env.lib.sh default
# YAP_CONFIG=
TMUX_SESSION=yap-stt
# Optional features
ENABLE_SMOKE_TEST=0
ENABLE_NET_TUNING=0
# Optional: real-time factor for smoke test (1 = realtime, 1000 = as fast as possible)
SMOKETEST_RTF=1000
# Authentication: DO NOT put secrets here. Export KYUTAI_API_KEY in your shell before running scripts.
EOF
  echo "[main] Wrote default .env"
  set -a; source "${BASE_DIR}/.env"; set +a
fi

# Ensure scripts are executable (only if not already)
for script in "${BASE_DIR}"/*.sh; do
  if [ ! -x "$script" ]; then
    chmod +x "$script"
  fi
done

# Run the minimal phases
"${BASE_DIR}/00_prereqs.sh"
"${BASE_DIR}/01_install_yap_server.sh"

# Start server and optionally run smoke test
"${BASE_DIR}/03_start_server.sh"
sleep 10
"${BASE_DIR}/04_status.sh"

if [ "${ENABLE_SMOKE_TEST}" = "1" ]; then
  "${BASE_DIR}/05_smoke_test.sh"
fi

echo
echo "=== All done. Server is running in tmux session '${TMUX_SESSION}' on ${YAP_ADDR}:${YAP_PORT} ==="
echo "Use: scripts/04_status.sh   (tail logs, health)"
echo "Use: scripts/99_stop.sh     (stop and clean session)"
