#!/usr/bin/env bash
set -euo pipefail
LOG_DIR="${HOME}/sensevoice-logs"
tail -n 200 -f "${LOG_DIR}/current.log"
