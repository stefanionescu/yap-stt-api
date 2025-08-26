#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update -y
sudo apt-get install -y git python3-venv python3-dev build-essential \
  libsndfile1 libmpg123-0 ffmpeg tmux curl jq
nvidia-smi || true
