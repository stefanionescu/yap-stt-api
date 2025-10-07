#!/usr/bin/env bash
set -euo pipefail

# Defaults
YAP_CONFIG_DEFAULT="/workspace/server/config-stt-en_fr-hf.toml"
YAP_CONFIG_RUNTIME="${YAP_CONFIG_DEFAULT}.runtime"

CONFIG_IN="${YAP_CONFIG_DEFAULT}"
CONFIG_OUT="${YAP_CONFIG_RUNTIME}"

KYU_KEY="${KYUTAI_API_KEY:-}"

echo "[entrypoint] Yap STT container starting..."
echo "[entrypoint] Using base config: ${CONFIG_IN}"

if [ -n "${KYU_KEY}" ]; then
  echo "[entrypoint] Injecting KYUTAI_API_KEY into authorized_ids"
  awk -v key="${KYU_KEY}" '
    BEGIN { replaced = 0 }
    /^[[:space:]]*authorized_ids[[:space:]]*=/ {
      if (!replaced) {
        print "authorized_ids = [\047" key "\047]"
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) {
        print "authorized_ids = [\047" key "\047]"
      }
    }
  ' "${CONFIG_IN}" > "${CONFIG_OUT}"
  export YAP_CONFIG="${CONFIG_OUT}"
  echo "[entrypoint] Effective config: ${YAP_CONFIG}"
  grep -n "authorized_ids" "${YAP_CONFIG}" || true
else
  echo "[entrypoint] WARNING: KYUTAI_API_KEY not set. Using base authorized_ids from config."
  export YAP_CONFIG="${CONFIG_IN}"
fi

mkdir -p "${YAP_LOG_DIR:-/workspace/logs}"

echo "[entrypoint] Exec: $*"
exec "$@"


